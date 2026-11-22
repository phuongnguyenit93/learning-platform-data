# Inspecting Effective Logging Configuration in Java

## Objectives

A `logback.xml`, `log4j2.xml`, or `logging.properties` file that looks correct **is not enough to conclude** that the application is logging according to that configuration. At runtime, Java may load a different file, select a different logging provider, apply profiles or environment variables, inherit a log level from a parent logger, filter further at an appender, or output logs to an unexpected destination.

This lesson guides you through **inspecting the effective/runtime logging configuration** of a Java application: verifying the active logging framework, the loaded configuration source, the effective log level, handlers/appenders, inheritance behavior, and where logs actually appear. The focus is on **observing and cross-checking the running configuration**, then diagnosing root causes when logs are missing, duplicated, or routed to the wrong destination.

After this lesson, you will be able to:

- Distinguish between *configured level* (explicitly declared level), *effective level* (level resolved through the hierarchy), and handler/appender filters.
- Inspect runtime logging with Java 17 `java.util.logging` (JUL), SLF4J + Logback, Log4j 2, and Spring Boot applications.
- Create an identifiable log probe to verify the full path from the API to the actual output destination.
- Diagnose cases where the configuration file looks right, but runtime behavior differs from expectations.

## 1. What Does “Effective Configuration” Include?

A typical logging message passes through multiple decision points:

```text
Java code calls logger
        |
        v
Logging API / facade (e.g., SLF4J)
        |
        v
Selected backend/provider
        |
        v
Logger name + inherited level + filter
        |
        v
Handler/Appender + own level/filter + additivity
        |
        v
Layout/Encoder + File/Console/Network destination
        |
        v
stdout, stderr, file, collector, or log backend
```

If `logger.info("ready")` does not appear, the cause could be at **any** link in this chain. For example, the logger accepts `INFO` while the appender only accepts `WARN` and above; or the application writes to `stderr` while the operator is only checking a file.

Questions to answer from the **running process**:

| What to verify | Example |
| --- | --- |
| API and backend | Is SLF4J using Logback, Log4j 2, JUL, or another provider? |
| Loaded configuration source | File inside the JAR, external file, profile-specific config, or default config? |
| Specific logger | Does `com.example.orders` have its own configured level or does it inherit? |
| Effective level | Is `INFO` actually permitted at the logger? |
| Path to sink | Which appenders/handlers does the logger pass events to? Does it propagate to parents? |
| Additional filters | Does the appender/handler have its own threshold, marker, filter, or sampling? |
| Destination and format | `stdout`, `stderr`, absolute file path, rolling file, JSON, or network? |
| Actual write capability | Does the process account have write permissions? Did the log event reach the destination or collector? |

**There is no single “global log level”**: levels can be decided at the logger, handler/appender, filter, and log collection system. Checking only a file name or environment variable is not enough.

## 2. Finding the Active Provider and Configuration Source at Runtime

### 2.1. Identifying the Logging Stack

Common Java logging ecosystems:

- **JUL (`java.util.logging`)**: API and implementation built into the JDK, controlled via `LogManager`, `Logger`, and `Handler`.
- **SLF4J**: a logging facade; final behavior depends on the provider/backend on the classpath, such as Logback or Log4j 2. SLF4J itself does not verify which Logback file was loaded.
- **Logback**: a backend commonly used with SLF4J, featuring a logger hierarchy, `LoggerContext`, and `Appender`s.
- **Log4j 2**: uses Log4j API/Core or bridges from facades; features `Configuration`, `LoggerConfig`, `Appender`, and `Filter`.
- **Frameworks like Spring Boot**: may determine configuration based on starters, higher-precedence property sources, active profiles, and framework lifecycle.

If the application uses SLF4J, at runtime you can print **the class name of the factory in use**:

```java
import org.slf4j.ILoggerFactory;
import org.slf4j.LoggerFactory;

public class IdentifyLoggingBackend {
    public static void main(String[] args) {
        ILoggerFactory factory = LoggerFactory.getILoggerFactory();
        System.out.println(factory.getClass().getName());
    }
}
```

This is an **example requiring the SLF4J dependency**, not a JDK-only program. The output depends on the provider on the classpath; do not expect a fixed output string. If the provider is not what you expected, check your dependencies, logging bridges, and SLF4J initialization messages. Do not confuse “the API used in source code” with “the backend actually receiving logs”.

### 2.2. Tracing the Configuration File

Common configuration sources:

1. A file packaged with the application (`src/main/resources` and then into the classpath/JAR).
2. A file outside the JAR specified via a JVM system property or a backend-specific configuration mechanism.
3. Properties from the environment/framework, profiles, or runtime configuration.
4. Default configuration when the backend cannot find a valid file.
5. Level changes via an API, admin interface, or a runtime component after application startup.

**Reading a file on the host machine does not prove the process loaded that file.** You must verify the configuration source path and diagnostic messages from **the process itself**. Watch out for multiple files with the same name on the classpath or in repackaged JARs. When running via an IDE, Gradle, Docker, or `java -jar`, the working directory and classpath may differ.

For JUL, the typical system property is `java.util.logging.config.file`; for other backends, property naming depends on the product and version. Consult the documentation for the running version and read the startup diagnostic logs emitted by the backend to see which configuration was selected.

## 3. Understanding Level Inheritance and Filters

Logging configuration is typically based on a logger name hierarchy, for example:

```text
(root)
  └── com
       └── com.example
            └── com.example.orders
```

A child logger may not declare a level; in that case, a level from an ancestor determines whether a log is accepted. **“Configured level = null” is not necessarily an error**: in JUL/Logback, it can indicate inheritance.

Suppose:

- Parent logger `com.example` has level `WARN`.
- Logger `com.example.orders` has no explicit level set.
- The file appender only accepts `ERROR` and above.

When logging:

| Event | Passes logger? | Passes file appender? | Result |
| --- | --- | --- | --- |
| `INFO` | No | Not evaluated | Not output |
| `WARN` | Yes | No | Not written to file |
| `ERROR` | Yes | Yes | May be output if other filters/I/O allow |

You must check **both the logger threshold and the appender threshold**. With Logback, also check `additivity`: when enabled, events can propagate up to ancestor appenders and cause duplicate logs if the same sink is attached in multiple places. With JUL, the equivalent mechanism is `useParentHandlers`.

In JUL, `logger.isLoggable(level)` answers the decision at the **logger** level. It does not fully account for every handler, handler filter, or output destination. For Logback/Log4j 2, level, additivity, and filters must also be evaluated according to each backend’s actual model, without imposing JUL semantics on every library.

## 4. Standalone Java 17 Example: Inspecting JUL Configuration at Runtime

This example uses pure JDK without Maven or external libraries. It creates a parent logger `lesson.shop` and a child logger `lesson.shop.checkout`, setting:

- Parent level to `WARNING`.
- Child to **inherit** the parent's level.
- Child not to forward events to the parent's handlers.
- Child with a `ConsoleHandler` that only accepts `SEVERE` and above.

By printing values *from the running objects*, we can clearly see why a `WARNING` log can be accepted by the logger yet never appear on the console.

Save as `InspectLoggingConfig.java`:

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.Logger;

public final class InspectLoggingConfig {
    public static void main(String[] args) {
        Logger parent = Logger.getLogger("lesson.shop");
        Logger logger = Logger.getLogger("lesson.shop.checkout");

        parent.setLevel(Level.WARNING);
        logger.setLevel(null); // Inherit level.
        logger.setUseParentHandlers(false);

        Handler handler = new ConsoleHandler();
        handler.setLevel(Level.SEVERE);
        logger.addHandler(handler);

        try {
            System.out.println("logger.name=" + logger.getName());
            System.out.println("logger.configured=" +
                    (logger.getLevel() == null
                            ? "<inherit>" : logger.getLevel().getName()));
            System.out.println("parent.name=" +
                    logger.getParent().getName());
            System.out.println("parent.level=" +
                    logger.getParent().getLevel().getName());
            System.out.println("logger.INFO=" +
                    logger.isLoggable(Level.INFO));
            System.out.println("logger.WARNING=" +
                    logger.isLoggable(Level.WARNING));
            System.out.println("logger.SEVERE=" +
                    logger.isLoggable(Level.SEVERE));
            System.out.println("use.parent.handlers=" +
                    logger.getUseParentHandlers());
            System.out.println("local.handler.count=" +
                    logger.getHandlers().length);
            System.out.println("handler.type=" +
                    handler.getClass().getSimpleName());
            System.out.println("handler.level=" +
                    handler.getLevel().getName());
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }
    }
}
```

Compile and run with JDK 17+ in a fresh JVM with the default JUL configuration:

```bash
javac InspectLoggingConfig.java
java InspectLoggingConfig
```

Stdout:

```text
logger.name=lesson.shop.checkout
logger.configured=<inherit>
parent.name=lesson.shop
parent.level=WARNING
logger.INFO=false
logger.WARNING=true
logger.SEVERE=true
use.parent.handlers=false
local.handler.count=1
handler.type=ConsoleHandler
handler.level=SEVERE
```

Explanation of each output line:

1. `logger.getLevel() == null` indicates that **the child logger has no directly configured level**; it inherits `WARNING` from its parent.
2. `logger.isLoggable(Level.INFO)` is `false`, while `WARNING` and `SEVERE` are `true`, because the logger's decision is based on the inherited level.
3. `logger.getUseParentHandlers() == false` indicates that events are not forwarded to the parent's handlers.
4. The child logger has a `ConsoleHandler` with level `SEVERE`. Therefore, if `logger.warning("...")` is called, the logger will accept and create the record, but **this handler** will not publish it. `logger.severe("...")` passes both checks (assuming no other filters). The example does not emit actual log records to keep stdout deterministic and avoid timestamps/`stderr` output from the formatter.
5. The `finally` block detaches and closes the handler created by the program, following the principle that whoever creates a resource closes it.

**Determinism caveats:** this example assumes a fresh JVM with the default JUL configuration and no external configuration automatically attaching handlers to `lesson.shop.checkout`. A real application may already have handlers/filters registered; in that case, you must inspect the handler count and output targets directly rather than assuming 1. `isLoggable` only checks the logger, not whether publishing to the sink succeeds.

### 4.1. Checking `logging.properties` with JUL

A JUL configuration file may declare properties such as:

```properties
.level=INFO
handlers=java.util.logging.ConsoleHandler
java.util.logging.ConsoleHandler.level=WARNING
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
com.example.orders.level=FINE
```

To specify the file for a JUL application, for example:

```bash
java -Djava.util.logging.config.file=logging.properties -cp . YourMainClass
```

`YourMainClass` is the main class name of the **actual application**, not the sample program above. Verify that the JVM option is passed at startup and points to the right file in the working directory, or use an absolute path. Loggers/handlers created at startup receive configuration according to JUL's lifecycle; editing the file afterward does not automatically guarantee the running configuration updates. If the application calls `LogManager.readConfiguration()` or configures logging programmatically, the runtime state may differ from the initial file.

**Note:** `FINE` corresponds to a more detailed level than `INFO` in JUL; JUL level names do not map 1-to-1 to Logback or Log4j 2 level names. Do not compare raw level strings while ignoring each backend's semantics.

## 5. Inspecting SLF4J and Logback at Runtime

If Logback Classic is the backend, you can inspect the context and loggers via its runtime API. The snippet below is **integration code** for a project that already includes SLF4J and Logback Classic; it is not a standalone pure-Java program.

```java
import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.LoggerContext;
import org.slf4j.ILoggerFactory;
import org.slf4j.LoggerFactory;

import java.util.Iterator;

public final class InspectLogback {
    public static void show(String loggerName) {
        ILoggerFactory factory = LoggerFactory.getILoggerFactory();

        if (!(factory instanceof LoggerContext context)) {
            System.out.println("Active SLF4J backend is not Logback");
            return;
        }

        Logger logger = context.getLogger(loggerName);
        Level configured = logger.getLevel();
        System.out.println("configured=" +
                (configured == null ? "<inherit>" : configured));
        System.out.println("effective=" + logger.getEffectiveLevel());
        System.out.println("additive=" + logger.isAdditive());

        Iterator<ch.qos.logback.core.Appender<
                ch.qos.logback.classic.spi.ILoggingEvent>> it =
                logger.iteratorForAppenders();
        while (it.hasNext()) {
            var appender = it.next();
            System.out.println("local appender=" + appender.getName()
                    + ", started=" + appender.isStarted());
        }
    }
}
```

In application code with an active logging lifecycle, you can call `InspectLogback.show("com.example.orders")` at a guarded diagnostic point or inside an integration test.

How to interpret the output:

- `configured` is the level set directly on the logger; `<inherit>` means it is inherited from an ancestor.
- `effective` is the resolved level after inheritance and is more directly meaningful when asking which levels the logger accepts.
- `additive` indicates whether events propagate up to ancestor appenders.
- `iteratorForAppenders()` only lists appenders **attached directly** to the queried logger. If no appender appears on this logger, it can still write to ancestor appenders when additivity is enabled.
- `started=false` suggests the appender is not yet started or is no longer active; you still need to check lifecycle, filters, and I/O errors.

Note: `context.getLogger(name)` may create the corresponding logger if it does not already exist; when inspecting only already-registered loggers, use the non-creating lookup API for your Logback version. Never call stop, reset, or reconfigure methods just to inspect, as they mutate runtime logging.

### 5.1. Reading Logback Configuration and Verifying Execution

Illustrative `logback.xml` example:

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.orders" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

This configuration **intends** to allow `DEBUG` on `com.example.orders` and propagate to the root appender while additivity remains enabled. However, to know whether it is actually in effect, you must verify that the active backend is Logback, the file was loaded, the runtime effective level is `DEBUG`, `CONSOLE` is started, and log events appear on the expected stream.

When the file does not load as expected, check Logback's **status/internal diagnostics** during startup or use the status utilities appropriate for your version; they typically reveal parse errors, missing appenders, which resource was selected, or file open failures. Do not rely on “`logback.xml` exists in the repository,” because the build or deployment may use a different resource.

## 6. Inspecting Log4j 2

For Log4j 2, you should inspect at least three layers:

1. **Active logger**: Does the source code obtain loggers via the Log4j API or through an SLF4J bridge? Is the backend receiving events actually Log4j 2 Core?
2. **Selected Configuration/LoggerConfig**: Does the logger name match a specific configuration, which `LoggerConfig` does its level inherit from, and what are its additivity and filters?
3. **Attached and active appenders**: Which console/file/rolling/async appenders receive the event; is a `ThresholdFilter` or another filter blocking a specific level?

Conceptual `log4j2.xml` example:

```xml
<Configuration status="WARN">
  <Appenders>
    <Console name="Console" target="SYSTEM_OUT">
      <PatternLayout pattern="%d{HH:mm:ss.SSS} %-5p %c - %m%n"/>
    </Console>
  </Appenders>
  <Loggers>
    <Logger name="com.example.orders" level="debug" additivity="false">
      <AppenderRef ref="Console"/>
    </Logger>
    <Root level="info">
      <AppenderRef ref="Console"/>
    </Root>
  </Loggers>
</Configuration>
```

In this example, `com.example.orders` has its own appender and `additivity="false"` to avoid propagating events to root. However, accurate conclusions must come from the running context/configuration and an actual event, not from the XML alone. When you suspect the wrong resource or a parse error, enable **Log4j 2 internal diagnostics** according to the documentation for your version and observe bootstrap.

Do not copy the `Logback LoggerContext` mental model directly onto Log4j 2; the APIs, configuration structure, and filter interactions differ. In particular, if multiple logging bridges/providers are declared, identify the actual backend before analyzing levels.

## 7. Spring Boot: Configuration from Multiple Sources

In a Spring Boot application, logging configuration can be influenced by:

- `application.properties` or `application.yml` files.
- Active profiles and profile-specific files.
- Environment variables, startup arguments, JVM system properties, or external configs.
- A backend-specific logging file selected by the framework for initialization.
- Post-startup level changes via management APIs or dynamic configuration mechanisms, if enabled.

Example of a common Spring Boot configuration:

```yaml
logging:
  level:
    root: INFO
    com.example.orders: DEBUG
  file:
    name: logs/application.log
```

This is an **intended configuration**; it does not by itself prove that the runtime is writing `DEBUG` logs to a file at a given location. Relative paths such as `logs/application.log` are resolved in the context of the runtime environment; you must verify the actual location, write permissions, and rotation.

When Spring Boot Actuator is installed, configured, and the logging endpoint is accessible, the `/actuator/loggers` endpoint can help inspect current logger levels. A response typically includes `configuredLevel` and `effectiveLevel`. Use this endpoint only in accordance with your security configuration and Actuator version. Endpoints that allow changing levels mutate runtime state; never issue an update operation merely to “inspect”.

Distinguish between:
- “A property is present in the Environment” vs. “the logging backend has read and applied that property”.
- “Configured level in Actuator” vs. “the log event reached the appender”.
- “Declared log file path” vs. “the actual path inside the container or host”.

If changing the config does not change behavior, verify you are checking the right process, active profiles, higher-precedence property sources, logging initialization timing, and whether a restart or reconfiguration is required.

## 8. Performing an End-to-End Check

Inspecting configuration means verifying behavior, not just reading metadata. Practical workflow:

**Step 1 — Identify the process and version:** record the startup command line, PID/container instance, build/JAR, JDK version, provider/backend, and active profiles. Avoid inspecting the wrong/old process or a different pod.

**Step 2 — Define expectations:** choose a specific logger namespace, expected level, appender, format, output target, and filter conditions. For example, `com.example.orders.CheckoutService` at `INFO` should appear on the console and include a `trace_id` field when a trace is active.

**Step 3 — Collect runtime configuration:** inspect configured/effective levels, logger hierarchy, additivity, appenders/handlers, started status, config file source, and diagnostic messages. Check the root logger as well if the child logger inherits.

**Step 4 — Emit an identifiable test log:** in a test environment or safe scenario, log a unique message with an ID:

```java
// Integration snippet in an application with SLF4J and a valid logger variable.
logger.info("LOG_CONFIG_PROBE id={} component={}",
        "probe-2026-11-a1", "checkout");
```

This is not a standalone program; you can use a dynamic timestamp/ID per attempt to avoid confusing it with old logs. Avoid logging secrets or generating excessive log volume in production.

**Step 5 — Locate the log at the actual destination:** search for the same probe ID in container console output, mounted files, or the centralized logging platform. If the log is missing, observe each layer: does the logger accept `INFO`? Filters? Is the appender started? Does it write to `stdout` or `stderr`? Does the file have permissions/correct path? Is the collector reading the right stream/path?

**Step 6 — Cross-check:** verify level, timestamp, logger name, thread, exception stack trace, encoder, and context fields. Async appenders can introduce delay; avoid concluding “not written” before the pipeline flushes or enough time has elapsed for output.

**Step 7 — Conclude the check:** if you temporarily changed levels or enabled diagnostics, restore them per operational procedure and record the evidence: process, logger name, effective level, appender, target, probe ID, and result.

Minimum evidence for a verification run can be recorded as:

```text
Process: orders-service instance A / build 2026.11
Backend: SLF4J + Logback
Logger: com.example.orders.CheckoutService
Configured level: <inherit>
Effective level: INFO
Appender path: logger -> root -> CONSOLE
Target: container stdout
Probe ID: probe-2026-11-a1
Observed: one matching event at the expected destination
```

This is a **template example**, not measurement output from a running application. Only record the “Observed” line like this after actually querying and finding the corresponding record.

## 9. Common Failures and Inspection Paths

| Symptom | Hypothesis to check | How to verify |
| --- | --- | --- |
| Config file edited but runtime unchanged | Process loaded a different file, not restarted, different profile, runtime override | Inspect actual loaded config source, command line, profile, internal diagnostics, and effective level |
| `DEBUG` does not appear | Parent level is still `INFO`/`WARN`, different provider, handler/appender has threshold | Check effective level on the exact logger and appender/handler filters |
| `INFO` passes `isLoggable` but no log appears | Handler does not accept `INFO`; no appender; wrong sink | Inspect handler/appender directly, additivity, output path, and probe |
| Logs duplicated twice | Appender attached to both child and parent; additivity enabled | Check hierarchy and appender refs at all levels |
| Logs visible in IDE but missing when running JAR | Different working directory/classpath/env | Compare startup command, packaged files, external files, and output streams |
| Logs written to unexpected file | Relative path, profile, volume mount, rolling strategy | Verify process working directory/absolute path and file mount location |
| Logs missing `trace_id` | MDC/context not set, async context propagation broken | Check at event creation, thread handoff, and encoder configuration |
| Configuration errors fail silently | Backend fell back to defaults, diagnostics disabled | Check status/internal logger and bootstrap `stderr` |
| Logs reach appender but missing in centralized system | Agent/collector filtering, permissions, network, pipeline lag | Compare local sink with collector/backend using the same probe ID |
| Level changes after startup | Actuator/admin API/code mutates runtime state | Read state at observation time, check audit/config reload |
| Application does not close log files | Backend/handler not stopped or flushed cleanly on shutdown | Check shutdown order, appender lifecycle, and pending queues |
| Error logs truncate stack traces | Encoder, multiline collection, truncation, or log pipeline | Inspect record at source appender and downstream parser |

## 10. Limitations to Keep in Mind During Diagnosis

**Runtime configuration can change:** A level snapshot at time A is not guaranteed to match time B when the application supports dynamic level changes, hot reload, or framework-managed logger reconfiguration.

**Async logging is not instantaneous:** The logger and appender may have accepted the event while it is still in a queue, buffer, or collector. Testing must account for timeouts, queue overflow, and flush mechanisms. An event not appearing immediately is not enough to conclude it was dropped.

**Do not expose sensitive configuration:** In production environments, avoid printing usernames/passwords in appender endpoints, URIs containing tokens, the entire environment, or secret configs. Logging management endpoints must be secured; changing levels in production can generate high log volume and leak data.

**Not seeing an event does not mean the code did not run:** Distinguish between the application branch not executing, logger level rejecting, filter dropping, appender failing, filesystem not writing, collector not picking up, and querying the wrong time range or instance.

**Do not stop/reset the backend for read-only diagnosis:** Methods like `LoggerContext.stop()` or reset/reconfigure mutate the running system. When changes are needed for remediation, follow a separate procedure after gathering evidence.

**Do not extrapolate parameters across libraries:** JUL uses `FINE/INFO/WARNING/SEVERE`, while Logback/Log4j 2 typically use `TRACE/DEBUG/INFO/WARN/ERROR`; hierarchy structure, handlers/appenders, and filters also differ. Use the API of the active backend.

## 11. Effective Configuration Inspection Checklist

A conclusion that “logging is configured correctly” should be backed by evidence for these items:

1. Identified the **correct process/instance**, JDK, build, and active backend/provider.
2. Verified the **actual config source** along with any overriding properties/profiles.
3. Read the **specific logger**, its configured level, and **effective level**; understood the inheritance path.
4. Inspected **handlers/appenders**, filters, additivity, started status, and output destination.
5. Emitted a **safe log probe**, observed it at the expected sink, and matched the ID/timestamp.
6. Checked **async delay**, file path/permissions, and downstream collector when relevant.
7. Recorded evidence and ensured any temporary changes were reverted per lifecycle procedures.

Inspecting effective logging configuration means cross-checking **loaded configuration → logger decision → handler/appender decision → record at final destination**. Only with evidence across all of these layers can you reliably explain why a log level appears, disappears, duplicates, or goes to the wrong place.