# Choosing a Logging Implementation in Java: Facade, Provider, and Backend

## 1. Why Do We Have to Choose an Implementation?

In Java, the logging call in application code and the system that actually processes the log can be two separate layers of responsibility.

For example, a business class using SLF4J:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class OrderService {
    private static final Logger LOG =
            LoggerFactory.getLogger(OrderService.class);

    public void accept(String orderId) {
        LOG.info("event=order_accepted orderId={}", orderId);
    }
}
```

This is an **illustrative class**, not a program with a `main` method. The `LOG.info(...)` line does not itself decide whether to write to the console, a file, or a JSON collector. It calls the **SLF4J API**; a compatible implementation/provider at runtime will process the event through a specific backend.

With a system using Logback:

```text
Application code
    |
    | LoggerFactory.getLogger(...), log.info(...)
    v
SLF4J API (facade)
    |
    | Find SLF4J provider on the classpath (SLF4J 2.x)
    v
Logback provider/backend
    |
    | Logger level, filter, appender, encoder/layout
    v
Console / File / Log collection system
```

This is the logical model: the **provider** is the part that connects the SLF4J API to the implementation; the backend typically provides the actual logger, filters, formatting, and appenders. With Logback, the `logback-classic` artifact contains the SLF4J integration and uses `logback-core`.

**Choosing an implementation** means deciding which backend the system will use at runtime, depending on requirements for formatting, performance, configuration, framework compatibility, security, and operations. It is not about renaming a logger or changing an `info` method call to `debug`.

## 2. Distinguishing Facade, API, Provider, and Backend

| Component | Responsibility | Examples |
|---|---|---|
| **Logging API** | The methods that source code calls to record events | `org.slf4j.Logger`, `java.util.logging.Logger`, `org.apache.logging.log4j.Logger` |
| **Facade** | Unified interface that limits direct dependency on a backend | SLF4J API |
| **Provider/binding** | Connects the facade to a concrete implementation at runtime | SLF4J integration in Logback, `log4j-slf4j2-impl`, `slf4j-simple` |
| **Backend/implementation** | Filters levels, creates events, handles appenders, formats, and outputs logs | Logback, Log4j 2 Core, JUL, simple backend |
| **Bridge/adapter** | Routes calls from one logging API to another logging API | `jul-to-slf4j`, `log4j-to-slf4j` |
| **Collector/agent** | Receives, transports, stores, and searches logs after the application emits them | Agent reading stdout/files or a centralized pipeline |

### Example: One API, Multiple Backends

The same SLF4J code snippet at the beginning of this article can run with:

- Logback, using the provider from `logback-classic`.
- Log4j 2, using the `log4j-slf4j2-impl` provider and the appropriate Log4j 2 implementation.
- `slf4j-simple`, a minimal provider.
- `slf4j-jdk14`, a provider that forwards SLF4J calls to **JUL**.
- `slf4j-nop`, an implementation that intentionally discards all logs.

**This does not mean the backends produce the same output or have the same features.** SLF4J provides a unified way to make logging calls, whereas layout, MDC/structured fields, file rotation, async, filters, and configuration belong to the capabilities of the actual implementation.

Conversely, an application that calls `java.util.logging.Logger` directly is using the **JUL API** and does not automatically go through SLF4J. Routing JUL logs into the backend used by SLF4J requires a bridge or a separate integration mechanism.

## 3. How Does SLF4J 2.x Find an Implementation?

In **SLF4J 2.x**, the API uses the `ServiceLoader` mechanism to locate compatible `SLF4JServiceProvider` instances present on the runtime classpath/module path. The provider concept replaces the binding mechanism of SLF4J 1.7 and earlier, which was typically identified by the `org.slf4j.impl.StaticLoggerBinder` class.

### 3.1. Important Rule: One Compatible Provider at Runtime

For a typical application, ensure **one SLF4J 2.x provider** is selected on the classpath. For example:

```text
CORRECT:
slf4j-api 2.x
   └── logback-classic (compatible version)

NEEDS FIXING:
slf4j-api 2.x
   ├── logback-classic
   └── slf4j-simple

NEEDS FIXING:
slf4j-api 2.x
   └── only backend/binding for SLF4J 1.7
```

If multiple providers are present, SLF4J may emit a warning and pick one provider; **do not rely on classpath ordering as a configuration policy**. The resulting behavior can be unexpected and change after updating dependencies or packaging.

If no compatible provider is found, SLF4J 2.x may fall back to a no-operation implementation and emit a warning, causing SLF4J calls to produce no logs as expected. A binding that only works with SLF4J 1.7 is not a 2.x provider; it does not solve a missing provider at runtime.

### 3.2. Version Compatibility

Do not choose an implementation based solely on artifact names. Check all of the following together:

- Major version of `slf4j-api`: 1.7 and 2.x use different binding/provider mechanisms.
- Backend version compatible with the SLF4J API and the target JDK.
- Transitive dependencies that pull in `slf4j-api`, another provider, or a bridge.
- Frameworks or application servers with their own default logging stack and classloaders.
- Supported versions, security patches, and the BOM/dependency management used by the project.

For example, `log4j-slf4j2-impl` is for **SLF4J 2.x**; `log4j-slf4j-impl` (without the 2) belongs to the integration with the previous SLF4J generation. Do not swap the two artifacts just because their names look similar.

**Remember:** the facade does not "select a backend via an annotation on the logger"; the provider is determined by what is present and loadable **when the application initializes logging**.

## 4. Common Backend Choices

| Choice | When it fits | Things to keep in mind |
|---|---|---|
| **Logback** | Common SLF4J applications needing patterns, rolling files, async appenders, and logger tuning | Requires `logback-classic` with matching dependencies; JSON/structured logging may need extra configuration or encoders |
| **Log4j 2** | When you want to use the Log4j 2 API/Core or need configuration, routing, async, and layout features provided by Log4j 2 | With SLF4J 2.x, requires the `log4j-slf4j2-impl` provider and a compatible implementation; avoid bridge loops |
| **JUL** | Java CLIs, libraries, or services minimizing dependencies with simple console/file logging needs | Built into the JDK, but rich MDC/JSON/rolling/async support is not fully available out of the box |
| **slf4j-simple** | Demos, small examples, tests, or very simple utilities | Minimal output/config; does not replace a production backend for advanced requirements |
| **slf4j-nop** | Cases where you intentionally silence all SLF4J calls | Easy to lose diagnostic evidence if packaged into runtime by mistake |
| **SLF4J → JUL provider** (`slf4j-jdk14`) | Code calls SLF4J, but you want to use JUL handlers/config | Understand the forwarding direction; do not pair with an opposing bridge that causes a loop |

These are **selection guidelines**, not a ranking of speed or safety. Criteria such as latency, throughput, memory, JDK version, and supported features must be verified against the actual version and configuration.

### Logback Is Not SLF4J

SLF4J is an API/facade; Logback is a popular implementation. Many projects use them together, making it easy to mistakenly refer to "SLF4J logging" as if the facade itself decides file rotation or pattern layouts. When an error occurs at the appender/encoder layer, you must check the **Logback** configuration, not just the signatures of `Logger.info`.

### Log4j 2 API Is Not Log4j 2 Core

An application can call the Log4j 2 API directly; the runtime needs an appropriate provider/implementation to emit logs. In the common model, `log4j-api` defines the API and `log4j-core` performs the backend processing. If application code calls **SLF4J**, the bridge/provider between SLF4J and Log4j 2 must be chosen in the right direction.

### JUL Is Not Automatically an SLF4J Implementation

JUL has its own loggers, handlers, formatters, and levels in the JDK. It only becomes the target of SLF4J calls when an appropriate adapter such as `slf4j-jdk14` is present. Conversely, `jul-to-slf4j` forwards logs emitted by the JUL API **to SLF4J**, not SLF4J into JUL.

## 5. Defining Implementation Selection Criteria from Real Requirements

Before changing dependencies, answer a short but concrete set of questions:

1. **What is the event source?** Does new code use SLF4J, JUL, or the Log4j 2 API? Which APIs do third-party libraries use?
2. **What is the framework's default backend?** Spring Boot, application servers, and starters may already have selected one.
3. **What is the log destination?** Console collected by a container, rolling files, a search system, or an agent-based collector?
4. **What format is needed?** Human-readable text, schema-based JSON, key–value fields, or message/trace correlation?
5. **What is the expected log volume?** Throughput, peak load, target latency, disk/CPU/RAM, and potential downstream slowness?
6. **What are the error-handling requirements?** Must stack traces/cause chains, retries, diagnostic logs, alerts, or independent audits be preserved?
7. **How will it be operated?** Do you need level changes without restarts, profile-based configuration, data masking, and retention control?
8. **What are the dependency policies?** JDK version, supported versions, security patches, licenses, and organizational dependency/BOM rules?

### Indicative Decision Matrix

| Primary requirement | Usually suitable simple direction |
|---|---|
| Very small application needing only basic logging and zero extra dependencies | Use JUL |
| Code already uses SLF4J and needs standard pattern + rolling/async config | Use a provider such as Logback |
| System is standardized on Log4j 2 with specific configuration/observability conventions | Use Log4j 2 and a provider compatible with the current API |
| Spring Boot application already defaults to Logback with no special requirements | Keep the default backend and configure it properly before considering a change |
| Logging requires JSON/OTel/trace fields | Choose a backend/encoder compatible with the pipeline and verify the schema; do not rely on the backend name alone |
| Small test cases not needing complex features | Consider `slf4j-simple` or a test appender within an appropriate scope |

**Do not choose Log4j 2 just because you heard it is "faster", or choose Logback just because "everyone uses it".** Speed and reliability depend on async mechanisms, appenders, formatters, log levels, I/O, logger context, and configuration policies. Measure benchmarks representative of your real system rather than extrapolating from marketing or mismatched microbenchmarks.

## 6. Complete Example: SLF4J 2.x + Logback with Java 17

This example uses **SLF4J as the API** and **Logback as the provider/backend**. You can run the same Java code under two level configurations without modifying the business code.

Requirements: **JDK 17+**, Maven, and the ability to download dependencies. Versions are pinned so the example is reproducible, **not as a claim that they are the latest releases or security recommendations for every project**.

### 6.1. Project Structure

```text
logging-choice-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/example/logging/LoggingChoiceDemo.java
        └── resources/
            └── logback.xml
```

### 6.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>logging-choice-demo</artifactId>
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
                    <mainClass>com.example.logging.LoggingChoiceDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`logback-classic` provides the backend and SLF4J provider, pulling in related dependencies (including the SLF4J API) in compatible versions. For larger projects, use appropriate dependency management/BOMs to lock versions and avoid pulling in multiple providers.

### 6.3. `src/main/resources/logback.xml`

```xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%level %logger{0} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

The pattern outputs the level, shortened logger name, and message, ending each event with a newline. Specifying `System.out` directs the demo output to **stdout**, unlike JUL's `ConsoleHandler`, which normally writes to stderr.

### 6.4. `src/main/java/com/example/logging/LoggingChoiceDemo.java`

```java
package com.example.logging;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class LoggingChoiceDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(LoggingChoiceDemo.class);

    public static void main(String[] args) {
        LOG.info("event=app_started service={}", "orders-api");
        LOG.debug("event=cache_lookup key={}", "ORD-7");
        LOG.warn("event=retry_scheduled attempt={}", 1);
    }
}
```

`LoggerFactory` belongs to SLF4J, not the Logback API; this business code makes no mention of `ConsoleAppender` or `logback.xml`. It is the provider on the runtime classpath that decides how to handle the calls.

### 6.5. Running and Verifying stdout

In the directory containing `pom.xml`, run:

```bash
mvn -q compile exec:java
```

With the configuration file above, **the lines produced by the program's Logback appender** are:

```text
INFO LoggingChoiceDemo - event=app_started service=orders-api
WARN LoggingChoiceDemo - event=retry_scheduled attempt=1
```

`DEBUG` is not emitted because root is set to INFO. Maven may print its own build/dependency messages depending on the environment configuration; the lines above are the application's logging output, with no guarantee that all Maven messages are suppressed. The name `LoggingChoiceDemo` is printed because `%logger{0}` displays the rightmost segment of the logger name.

### 6.6. Changing the Level Without Editing Java Code

Change the line:

```xml
<root level="INFO">
```

to:

```xml
<root level="DEBUG">
```

and run again. The lines emitted by the appender are:

```text
INFO LoggingChoiceDemo - event=app_started service=orders-api
DEBUG LoggingChoiceDemo - event=cache_lookup key=ORD-7
WARN LoggingChoiceDemo - event=retry_scheduled attempt=1
```

There are no changes in `LoggingChoiceDemo.java`. This is the benefit of separating **API calls** from **backend policy**. In production, choose levels, appenders, and formats according to operational needs; avoid enabling root DEBUG broadly without controlling volume.

## 7. What If We Replace Logback with `slf4j-simple`?

In the demo project from Section 6, you can **replace** the `logback-classic` dependency with:

```xml
<dependency>
    <groupId>org.slf4j</groupId>
    <artifactId>slf4j-simple</artifactId>
    <version>2.0.16</version>
</dependency>
```

**Replace** means removing the old Logback dependency from `pom.xml`, not adding them side by side. `slf4j-simple` provides an SLF4J provider and minimal output handling, so the `LoggingChoiceDemo.java` code can remain unchanged.

Key differences:

- `logback.xml` is no longer the active backend configuration; the simple provider does not read Logback XML files.
- The `{}` placeholder substitution syntax in messages still belongs to the SLF4J API.
- The default format/destination and level configuration belong to `slf4j-simple`; it typically writes to **stderr** with a noticeably different format from the Logback example. Do not expect the two sample lines from Section 6 to match identically.
- The simple backend works for certain demos or small utilities, but lacks many appender/rolling/encoder capabilities of a full backend.

Versions `2.0.16` and `1.5.12` in this article are **pinned examples** to illustrate swapping implementations, not a list of the latest releases. When upgrading versions, verify SLF4J API/provider compatibility along with transitive dependencies.

This experiment shows: **swapping a provider/backend generally does not require changing logging calls in business code if the code only uses the SLF4J API**. However, if application code directly imports Logback-specific classes, it is coupled to that backend and must be modified when switching.

## 8. Choosing Log4j 2 as the Backend for SLF4J 2.x

When you want to use Log4j 2 while keeping SLF4J calls in your code, the typical setup is:

```text
SLF4J API 2.x
    |
    v
log4j-slf4j2-impl (SLF4J provider)
    |
    v
Log4j 2 API / Core
    |
    v
Log4j 2 Appenders / Layouts
```

Minimal dependencies by **role** include:

- `slf4j-api`: the API called by business code (may arrive as a transitive dependency).
- `log4j-slf4j2-impl`: the provider that routes SLF4J 2.x to Log4j 2.
- `log4j-core`: the implementation that processes events; `log4j-api` is the foundational API of Log4j 2.

This is a **dependency diagram**, not a version-pinned `pom.xml`; Log4j 2 artifacts must be kept on compatible synchronized versions via dependency management. This backend is typically configured with `log4j2.xml` or an equivalent Log4j 2 configuration format, **not `logback.xml`**.

When migrating from Logback:

1. Remove or exclude `logback-classic` from runtime.
2. Add the Log4j 2 provider for SLF4J 2.x and the required Core components at compatible versions.
3. Translate appender/layout/filter configurations to Log4j 2 mechanisms.
4. Verify levels, placeholders, `Throwable` handling, MDC/context, output, and production configuration.
5. Confirm that the runtime has only the chosen provider, rather than both Logback and Log4j 2 competing for binding.

Log levels and configuration strategies may look similar, but not every pattern/layout or async behavior maps one-to-one.

## 9. Bridges: When Applications or Libraries Use Different APIs

A large application can contain calls to SLF4J, JUL, and the Log4j 2 API at the same time. You should not rush to rewrite all library code. **Bridges** route events to a single backend to unify formatting and collection.

### 9.1. Reading Bridge Directions Correctly

| Artifact or adapter | Typical forwarding direction | Use case |
|---|---|---|
| `jul-to-slf4j` | JUL API → SLF4J API | Libraries/JDK use JUL; application standardizes on the SLF4J backend |
| `log4j-to-slf4j` | Log4j 2 API → SLF4J API | Libraries use Log4j 2 API; application uses Logback as backend |
| `slf4j-jdk14` | SLF4J API → JUL | Business code uses SLF4J, but the actual target is JUL |
| `log4j-slf4j2-impl` | SLF4J 2.x API → Log4j 2 | Business code uses SLF4J; backend is Log4j 2 |

**Critical point: two adapters running in opposite directions must never be paired into a loop.**

For example:

```text
DANGEROUS:
SLF4J -> Log4j 2   (log4j-slf4j2-impl)
Log4j 2 -> SLF4J   (log4j-to-slf4j)
=> can create a forwarding loop / configuration conflict
```

Similarly, pairing `jul-to-slf4j` (JUL → SLF4J) with `slf4j-jdk14` (SLF4J → JUL) is an opposing configuration to avoid.

In practice, some adapters detect the conflict and fail early instead of looping infinitely; the exact behavior depends on the library and version. **Whether it manifests as a startup error or a loop, this is not a valid topology.**

### 9.2. Installing JUL → SLF4J Requires Intentional Design

When using `jul-to-slf4j`, many applications configure `SLF4JBridgeHandler` to forward JUL `LogRecord` events to SLF4J. The statements below are an **API illustration snippet, not a standalone Java program**:

```java
import org.slf4j.bridge.SLF4JBridgeHandler;

// Call during startup when you want to replace the JUL root handlers:
SLF4JBridgeHandler.removeHandlersForRootLogger();
SLF4JBridgeHandler.install();
```

Ensure `jul-to-slf4j` is present and the SLF4J backend does not route back into JUL. Removing root handlers can affect JUL log sources that depend on those handlers; do not apply this indiscriminately inside containers or frameworks that already manage logging.

JUL calls forwarded by the bridge are still subject to JUL levels and filters. For very high JUL log volumes, evaluate bridge overhead and related performance settings. A bridge cannot manufacture a request ID or structured field that was never supplied.

### 9.3. You May Not Need a Bridge Just to Share a Collector

Sometimes a library writes JUL to stderr while the application writes Logback to stdout, and an agent collects both. That may be enough for basic requirements without installing a bridge. However, formatting, correlation, and level control will be less consistent. Decide whether to bridge based on operational needs and cost, not merely the desire to force "every API into one".

## 10. Spring Boot and Ecosystems with a Preselected Default Backend

Spring Boot typically uses SLF4J with **Logback** in the default logging configuration of many starters. If the application is running well and Logback meets your requirements, **there is no need to switch implementations** just because another backend exists.

If you have a concrete reason to use Log4j 2, you should:

1. Inspect the dependency tree to confirm where the default logging starter comes from.
2. Exclude `spring-boot-starter-logging` from the appropriate dependencies as documented for your Spring Boot version.
3. Add `spring-boot-starter-log4j2` or the compatible integration supported by your Spring Boot version.
4. Use the configuration file matching Log4j 2 and Spring Boot's conventions.
5. Verify the dependency tree, runtime provider, test logging, stack traces, profiles, and output.

This is a **directional workflow**, not a copy-paste `pom.xml` for every Spring Boot version. Do not exclude the default dependency and add another provider without checking what else libraries depend on.

Some application servers have their own logging systems, layered classloaders, or preinstalled JUL/SLF4J bridges. In those environments, "exactly one provider" must be verified in the **actual runtime**, not just by looking at project dependencies.

## 11. Should a Java Library Choose an API or a Backend?

A **library** embedded into multiple applications should generally avoid forcing the host application to adopt a specific backend, unless there is a very specific reason. A common design approach is:

- The library calls `slf4j-api` and lets the end application supply the provider/runtime implementation.
- Do not bundle `logback-classic` or `slf4j-simple` as a required runtime dependency of the library unless explicitly required.
- Do not unilaterally alter the root logger, remove handlers, change global configuration, or decide where logs are stored on behalf of the host application.
- Use clear logger names by package/class and pass `Throwable`/context properly.

Maven example for a **library**:

```xml
<dependency>
    <groupId>org.slf4j</groupId>
    <artifactId>slf4j-api</artifactId>
    <version>2.0.16</version>
</dependency>
```

This is a **dependency snippet**, not a complete `pom.xml`. Applications consuming the library remain free to choose Logback, Log4j 2, a JUL adapter, or another provider. Special projects that must keep dependencies to a minimum may choose JUL directly, but must consider how host applications will unify logging.

**Do not bundle a hidden provider inside a library and cause consuming applications to end up with two providers.** If library developers need logging during the library's own tests, add a separate test-scoped provider and avoid shipping it as a runtime dependency.

## 12. Verifying Which Implementation Is Actually Running

Do not infer the backend solely from importing `org.slf4j.Logger`. Verify both dependencies and runtime behavior.

### 12.1. Inspecting the Dependency Tree

With Maven:

```bash
mvn dependency:tree
```

Or filter for relevant artifacts in the output:

```text
org.slf4j:slf4j-api
ch.qos.logback:logback-classic
org.slf4j:slf4j-simple
org.apache.logging.log4j:log4j-slf4j2-impl
org.slf4j:jul-to-slf4j
org.apache.logging.log4j:log4j-to-slf4j
```

The list above is **artifacts to watch for**, not a valid dependency tree containing all of them at once. Check scopes (compile, runtime, test), `dependencyManagement`, transitive dependencies, fat/shaded JARs, and the actual deployment classpath. The build-time Maven tree does not automatically guarantee every container will load the exact same JARs.

### 12.2. Checking the Logger Factory at Runtime

In a program with `slf4j-api`:

```java
// Illustrative snippet, inside the application's main:
System.out.println(
        org.slf4j.LoggerFactory.getILoggerFactory()
                .getClass().getName());
```

With the common Logback provider, the factory class output is typically `ch.qos.logback.classic.LoggerContext`. With other providers, the output will differ. Do not write business logic that hard-depends on a provider's class name; use this check for **diagnostics**, not as a general API.

SLF4J may emit startup warnings if a provider is missing or multiple providers are found. Read those warnings instead of only checking whether the code compiles.

### 12.3. Testing an Event at Runtime

Emit an `INFO` call with an easily recognizable message and check:

- Which backend receives the log?
- Does the event go to stdout, stderr, a file, or a collector?
- Are DEBUG/INFO/WARN levels filtered correctly?
- Are logger names, message parameters, and stack traces rendered accurately?
- Are there duplicate logs caused by bridges, appenders, or additivity?
- Is any context data lost when crossing a bridge?

Do not print secrets or real sensitive data just to run this test.

## 13. Common Mistakes When Choosing a Backend and How to Fix Them

| Symptom | Common cause | How to fix |
|---|---|---|
| SLF4J reports no provider found | Only `slf4j-api` is present, with no valid 2.x implementation | Add exactly one compatible provider or use the framework's logging system |
| SLF4J reports multiple providers | Logback and simple/Log4j providers are both on the runtime classpath | Remove extra providers; inspect transitive dependencies |
| `StaticLoggerBinder` binding does not work with SLF4J 2 | Provider/binding belongs to SLF4J 1.7 | Upgrade the integration to match the major version |
| `logback.xml` does not change output | Runtime is using a different backend or the file is not loaded | Check the actual provider, config file location, and classpath |
| `log4j2.xml` is ignored | Runtime is not running Log4j 2 Core or config is not loaded | Confirm provider/Core, config loading path, and startup logs |
| Logs do not appear | No-op backend, level/filter drops events, or output goes elsewhere | Check runtime implementation, effective level, and output target |
| Logs appear multiple times | Multiple appenders attached, propagation, or bridge/collector duplication | Check topology and additivity, not just logger calls |
| Application fails on bridge startup | Two opposing bridges or incompatible versions | Remove the adapter causing a loop; standardize on one routing direction |
| Missing JSON fields or MDC | Only message placeholders and text patterns are configured | Add appropriate structured arguments/encoder/context |
| Tests log differently from production | Different test-scoped provider/config | Check the test runtime and test configuration files |
| Backend has CVEs or compatibility issues | Outdated version or mismatched transitive dependencies | Audit dependency management, advisories, and update with testing |

## 14. Operations: What Does Backend Choice Affect?

### 14.1. Structured Logging and Observability

If you need JSON logs with `traceId`, `requestId`, `service.name`, and queryable business fields, the backend must support the corresponding encoder/schema. Using only SLF4J `{}` placeholders normally produces a text message, **and does not guarantee the collector receives separate structured fields**.

Desired JSON example:

```json
{
  "timestamp": "2026-11-09T08:15:03.125Z",
  "level": "INFO",
  "service": "orders-api",
  "logger": "com.example.orders.OrderService",
  "traceId": "trace-42",
  "event": "order_accepted",
  "orderId": "ORD-7"
}
```

This is an **illustrative output**, not the automatic output of the program in Section 6. Generating trace IDs, propagating context, and enforcing schemas are the responsibility of the application and observability pipeline. Switching providers cannot invent data that was never passed into the event.

### 14.2. Exceptions and Security

The application must pass the `Throwable` through the appropriate API if stack traces are needed. Do not log only `error.getMessage()` when the goal is investigating a cause chain. Choose a backend with a layout/encoder that preserves exceptions without accidentally exposing credentials, tokens, or sensitive request payloads.

No backend automatically guarantees that all sensitive data is masked. You need protection policies at the source, sanitization/escaping, log access controls, encryption, retention rules, and real-world testing.

### 14.3. Async, File Rotation, and Reliability

Different backends implement async logging, buffering, rolling, and file retention in their own ways. Async can reduce request-path latency, but also introduces the risk of losing events when the queue fills up or the process crashes. A `RollingFileAppender` does not by itself guarantee data has reached the collector. Evaluate:

- Log levels and events/second at peak load.
- Serialization/formatting cost for JSON and stack traces.
- Queue size, drop/block policy, and shutdown/flush behavior.
- Path to the collector, network failures, and retries.
- Disk quota, rotation, retention, and file permissions.
- The difference between when an event occurs and when it is written.

**A strong backend does not replace proper pipeline design.** An application using Logback or Log4j 2 can still produce duplicate logs, miss trace IDs, or lose data if misconfigured.

## 15. A Safe Backend Migration Process

When the current backend no longer meets requirements, proceed in order:

1. **Document the current state:** APIs being called, runtime provider/backend, config files, libraries using JUL/Log4j 2, and where logs are emitted.
2. **Lock down output requirements:** levels, JSON fields, stack traces, MDC, routing, rotation, async, security, retention, and target throughput.
3. **Choose a one-way topology:** SLF4J 2.x → one compatible provider → backend; add bridges for other APIs only when needed, without creating loops.
4. **Swap dependencies deliberately:** remove the old provider, add the new provider and backend dependencies, and align versions via a BOM.
5. **Migrate configuration:** patterns, logger levels, appenders, filters, exception conversion, structured encoders, and profiles.
6. **Verify in tests and runtime:** dependency tree, startup warnings, effective provider, INFO/DEBUG/ERROR output, `Throwable`, context, and duplicates.
7. **Measure before and after:** throughput, p95/p99 latency, CPU/RAM, dropped logs, disk/collector lag, and log volume.
8. **Roll out gradually:** test in staging, watch warnings, and ensure a rollback path if targets are not met.
9. **Update operational runbooks:** clarify who owns logging configuration, how to raise levels temporarily, how to query logs, and the patching cadence.

If you only want to change where logs are stored, **changing the appender/collector** is sometimes enough. You do not need to replace the entire API/backend if the issue lies in the log shipping pipeline.

## 16. Final Checklist: Did You "Choose the Implementation" Correctly?

- [ ] Business code uses one intentional logging API, typically SLF4J or the framework's default API.
- [ ] Runtime has **exactly one compatible SLF4J 2.x provider** if using SLF4J 2.x.
- [ ] No 1.7 binding remains mistaken for a 2.x provider.
- [ ] No opposing bridges exist, such as JUL ↔ SLF4J or Log4j 2 ↔ SLF4J.
- [ ] JDK, backend, facade/provider, and framework dependencies are version-compatible.
- [ ] The **actually running** implementation has been verified via dependency tree and runtime diagnostics.
- [ ] Logger names, levels, message formatting, exceptions, and MDC/structured fields are accurate.
- [ ] The backend config file is loaded properly, without confusing `logback.xml` and `log4j2.xml`.
- [ ] Console/file/collector outputs and additivity do not cause duplicate or dropped logs.
- [ ] Security boundaries, rotation, retention, and performance have been tested for the target environment.
- [ ] A process exists to change configuration, deploy, and roll back without modifying business logic.

**Conclusion:** choosing a logging implementation is a **runtime architecture** decision. SLF4J decouples business code from the backend, but it does not remove the responsibility of selecting **one right provider**, managing dependencies/versions, configuring the backend, and keeping bridges one-way. Logback, Log4j 2, JUL, and the simple backend all have valid uses; the right choice is the one that meets verifiable operational requirements rather than being picked by technology name alone.
