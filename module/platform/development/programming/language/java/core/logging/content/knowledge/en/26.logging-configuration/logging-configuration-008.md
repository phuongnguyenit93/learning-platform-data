# Reloading Logging Configuration in Java

## 1. What is configuration reloading and when is it needed?

**Reloading logging configuration** is the act of a running application **re-reading and applying log configuration** without restarting the entire JVM, provided the logging framework and implementation support it. For example: while running at the `INFO` level, an operator wants to temporarily enable `DEBUG` for `com.example.payment` to investigate an issue; or needs to change the format, filters, or log output destination under a controlled procedure.

Three actions often loosely referred to as "reload" must be distinguished:

1. **Changing the runtime log level**: modifying a `Logger` level via an administrative API or framework API, which may not require reading a file.
2. **Reloading the logging file**: watching for changes to `logback.xml`, `log4j2.xml`, or a custom configuration file, parsing it, and applying the new configuration.
3. **Restarting the application**: reinitializing all of logging and the application; this is required for certain parameters that do not support live updates.

**Reloading logging does not mean reloading all application configuration.** Changing `application.properties` or environment variables after the JVM has started does not automatically guarantee that those properties will be re-read. Re-reading only occurs when a specific mechanism handles the changed configuration source.

Practical goals include reducing incident resolution time, controlling log volume, adjusting output per environment, and rolling back configuration when an operational change fails to meet expectations. Each goal requires a different reload scope and verification approach.

## 2. Operating model: configuration source, watcher, and effective configuration

```text
[Config file / admin command]
              │
              ▼
 [Detect change or receive request]
              │
              ▼
       [Read and parse]
              │
              ▼
         [Validate]
              │
       ┌──────┴────────┐
       ▼               ▼
    [Valid]        [Invalid]
       │               │
       ▼               ▼
 [Apply config]    [Report error; handle per
       │            framework mechanism]
       ▼
 [New logger / filter / appender]
       │
       ▼
 [Observe actual logs, verify impact]
```

Each component plays a distinct role:

- **Configuration source**: XML/properties file, Java API, application environment, or administrative API. The source must be the one the logging system actually uses.
- **Detection mechanism**: periodic scanning (*polling*), file watching (*watch*), an administrative endpoint/button, or an explicit API call.
- **Parser and validator**: detects syntax errors in configuration, unsupported elements or attributes, invalid appender names, or missing parameters.
- **LoggerContext / configuration manager**: applies log levels, filters, appenders, encoders, and related resources according to the framework's specific contract.
- **Appender/sink**: writes to console, file, socket, or centralized logging systems; these resources have their own lifecycle.
- **Verification step**: checks logs after reload, internal status, and error/dropped-log counts, rather than merely confirming that the file changed.

**Updating the file successfully ≠ reloading successfully ≠ logs reaching the backend.** The file may be saved properly yet go unseen by the watcher; the framework may report a configuration error; the appender may be applied yet lack write permissions or become congested.

## 3. Which parts of logging can be changed at runtime?

| Component | Purpose of change | Limitations to watch out for |
| --- | --- | --- |
| `Logger` level | Enable `DEBUG` or reduce from `DEBUG` back to `INFO` | Levels may be inherited along the logger name hierarchy; check the **effective level** |
| Filter | Select events by level or attributes | Changing a filter may drop critical logs |
| Pattern/layout/encoder | Add `trace_id`, timestamp, JSON fields | Downstream collectors/parsers may be incompatible with the new format |
| Appender/sink | Change file or log output destination | Requires opening/closing resources; check path, write permissions, and flushing |
| Async logging queue | Adjust asynchronous logging behavior | Not all parameters can be applied without recreating the appender/worker |
| Rolling policy | Adjust file rotation/retention | May affect file names, locks, open files, or archived data |
| Package-specific logger | Isolate investigation scope | Avoid enabling DEBUG on the root logger system-wide unnecessarily |

The scope of updates depends on the Logback, Log4j2, or JUL version, the application, and the environment. Do not assume that **every property** of an appender changes immediately after a single reload. For instance, some resources must be reopened; some frameworks may retain the old resource or ignore a change if hot-swapping risks losing events.

When the goal is simply adjusting a log level for investigation, updating the specific logger via API can be simpler than replacing the entire appender tree. Only consider a full configuration reload when you need to change a sink or JSON structure.

## 4. Automatic file reloading mechanism in Logback

Logback-classic supports scanning for changes in the configuration file and automatically reconfiguring when enabled. For a Java application using **Logback directly**, you can place the configuration file outside the JAR and declare:

```xml
<!-- /etc/myapp/logback.xml: example for standard Logback -->
<configuration scan="true" scanPeriod="30 seconds">
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.payment" level="INFO"/>

    <root level="WARN">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

In this example:

- `scan="true"` instructs Logback to watch for configuration changes.
- `scanPeriod="30 seconds"` sets the scanning interval. If not configured, Logback documentation states the default scan interval is about **one minute**.
- `com.example.payment` has its own `INFO` level; the root level is `WARN`. Loggers in the same branch can inherit the level from a parent logger if they do not declare their own.
- The `CONSOLE` appender is attached at root; the payment logger has appender inheritance (*additivity*) enabled by default, so qualifying events are emitted through root.
- When edited to `level="DEBUG"` and saved, after a valid scan cycle, DEBUG lines for this logger group can appear.
- Logback tracks `include`d files via its reconfiguration mechanism; actual detection behavior still needs to be tested on the filesystem in use.

If using a file outside the classpath and you want Logback to locate it accurately, set the Java system property **before logging initializes**. Example command:

```bash
java -Dlogback.configurationFile=/etc/myapp/logback.xml -jar myapp.jar
```

This is a command pattern for a **standalone Logback application** packaged as a JAR. In Spring Boot, file loading is also governed by Boot's logging configuration mechanism; do not treat this command pattern as a universal procedure for all Boot applications.

**Note on time units:** Logback's `scanPeriod` supports units such as `milliseconds`, `seconds`, `minutes`, and `hours`. If no unit is specified, some configurations interpret the value in **milliseconds**, which can easily cause the application to scan too aggressively. Always specify the unit explicitly, e.g., `30 seconds`.

**When the new configuration is invalid:** Logback documentation describes a mechanism to fall back to a previous **XML-syntactically** valid configuration when the latest edit has a syntax error. Do not generalize that statement into a promise that every resource error, appender name issue, file write failure, network issue, or semantically invalid configuration will be fully recovered. You must monitor **internal status messages** and independently verify the output data.

### How to verify a Logback log level change

1. Confirm the process is using the declared external JAR file; check the actual path and read permissions.
2. Emit `INFO` and `DEBUG` logs from `com.example.payment` while the current level is `INFO`; observe that only INFO appears (assuming no additional filter alters this).
3. Change `<logger name="com.example.payment" level="INFO"/>` to `DEBUG` in the file and save.
4. Wait past the scan period; re-emit the same events and observe DEBUG.
5. Check Logback's internal status if no change appears, then restore the INFO level once investigation is complete.

The `scanPeriod` interval is a **check cycle**, not a guarantee of exact application timing; file write timing, scheduler delay, I/O, and volume mount behavior can cause actual timing to vary.

## 5. File reloading in Log4j2

**Log4j2** provides the `monitorInterval` attribute on the `Configuration` element when the configuration source allows change monitoring. In Log4j2 2.x, the unit of this value is **seconds**; the default `0` means polling is disabled.

Example **`log4j2.xml`** file for an application actually using Log4j2 Core:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration monitorInterval="30">
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <PatternLayout pattern="%d{HH:mm:ss.SSS} %-5p %c - %m%n"/>
        </Console>
    </Appenders>

    <Loggers>
        <Logger name="com.example.payment" level="INFO"/>
        <Root level="WARN">
            <AppenderRef ref="CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
```

After changing `level="INFO"` of `com.example.payment` to `DEBUG` and Log4j2 detects the modified file, the system can reconfigure without restarting the application.

Key differences from Logback:

- The parameter name is `monitorInterval`, not `scanPeriod`.
- Log4j2's implementation has its own reconfiguration and resource-reuse strategies; in some cases, the framework **ignores changes to an appender attribute** to avoid losing logs while closing/opening resources.
- Editing the file only takes effect if it is the file currently used by the LoggerContext and the source supports change detection.
- In applications configured via API or custom sources, auto-reload behavior depends on the actual configuration source, not on the file name.
- Details of file handling, resources, and polling timing may vary by version; consult the documentation for the exact version in use during real deployments.

You should inspect the **Log4j2 Status Logger**, emitted logs, source, and file location after reloading. Do not claim "zero log loss" for the entire pipeline: appenders may depend on disk, stdout collectors, network, containers, or backends outside the LoggerContext.

## 6. Special case: Spring Boot and log level change mechanisms

### 6.1. `logback-spring.xml` and conflict with Logback scan

Spring Boot provides extension tags such as `<springProfile>` and `<springProperty>` for Logback. Spring Boot documentation confirms **these extensions cannot be used with Logback's configuration scanning mode**.

The example below is **not a valid configuration to expect hot reload via scan**:

```xml
<!-- Example illustrating a combination NOT RECOMMENDED for hot reload -->
<configuration scan="true" scanPeriod="30 seconds">
    <springProfile name="dev">
        <!-- ... -->
    </springProfile>
</configuration>
```

If the scanner reloads a file containing those tags, parser errors such as `no applicable action for [springProfile]` or `[springProperty]` may occur.

In Boot applications using `logback-spring.xml` and its extension tags, choose an administrative mechanism supported by the application/Boot, or implement a controlled restart procedure when a full configuration change is needed. Do not enable `scan="true"` and assume Spring Boot features will continue to apply normally after each reload.

### 6.2. Changing log levels only: Spring Boot Actuator Loggers

If the Actuator dependency is present and the `loggers` endpoint is **authorized, exposed, and properly secured**, log levels can be read and changed at runtime. Example request for an authenticated management environment:

```http
GET /actuator/loggers/com.example.payment
```

The returned information distinguishes between:

- `configuredLevel`: the level set directly on the logger; may be `null` if inherited.
- `effectiveLevel`: the actual level in effect after inheritance is resolved.

Switch to DEBUG:

```http
POST /actuator/loggers/com.example.payment
Content-Type: application/json

{"configuredLevel":"DEBUG"}
```

Once the investigation is done, you can send `{"configuredLevel":null}` to clear the directly configured level, allowing the logger to return to its inherited/default configuration according to the endpoint contract.

Points to remember:

- Updating via Actuator changes the **runtime log level state**; it does not automatically update the source file or persist across restarts.
- If another configuration source auto-reloads, it can overwrite the log level set via the endpoint; clarify which source holds final authority over the level.
- Do not expose management endpoints that mutate log levels to the public Internet; require authentication, authorization, and auditing of who made the change, the before/after values, and how long DEBUG remains enabled.
- Enabling DEBUG application-wide can generate massive log volume and inadvertently expose sensitive data in log messages; prefer targeting only the specific logger/package under investigation.
- Do not assume that editing `logging.level.*` in `application.yml` on disk will cause Boot to apply it automatically. Reloading requires a mechanism that genuinely supports it.

### 6.3. What requires a restart?

Changes involving logging libraries on the classpath, how logging is bootstrapped, system initialization with Spring extensions, or resource configurations that cannot be safely swapped may require a restart. Distinguish between **logger levels**, **appender structure**, and **non-logging application configuration** before choosing an update method.

## 7. Self-contained Java 17 example: re-reading log level from a file

To understand the principle before using a framework, this example uses **`java.util.logging` (JUL)** built into the JDK. The application writes configuration to a temporary `.properties` file, calls `reload` to read and validate the new level, and then calls `Logger#setLevel`. Afterward, it tests an invalid configuration to demonstrate **keeping the previous level when parsing fails**.

This is an **explicitly triggered reload**, not an automatic file watcher. The program only changes the **logger level**, not complex handlers or formatters.

Save as **`LoggingConfigReloadDemo.java`**:

```java
import java.io.IOException;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import java.util.Properties;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LoggingConfigReloadDemo {
    private static final Logger LOGGER =
            Logger.getLogger("demo.payment");

    private static final Handler OUTPUT = new Handler() {
        {
            setLevel(Level.ALL);
        }

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                System.out.println(
                    record.getLevel().getName() + " | "
                    + record.getMessage());
            }
        }

        @Override
        public void flush() {
            // No separate buffer in this illustrative handler.
        }

        @Override
        public void close() {
            // Owns no resources that need closing.
        }
    };

    private static void reload(Path file) throws IOException {
        Properties properties = new Properties();

        try (Reader reader =
                Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
            properties.load(reader);
        }

        String raw = properties.getProperty("log.level");
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("Missing log.level");
        }

        // Validate completely before modifying the running logger.
        Level next = Level.parse(raw.trim().toUpperCase(Locale.ROOT));
        LOGGER.setLevel(next);
        System.out.println("RELOAD OK: " + next.getName());
    }

    public static void main(String[] args) throws Exception {
        LOGGER.setUseParentHandlers(false);
        LOGGER.addHandler(OUTPUT);

        Path file = Files.createTempFile("logging-reload-", ".properties");
        try {
            Files.writeString(file, "log.level=INFO\n",
                    StandardCharsets.UTF_8);
            reload(file);
            LOGGER.info("application started");
            LOGGER.fine("query parameters"); // Not printed yet.

            Files.writeString(file, "log.level=FINE\n",
                    StandardCharsets.UTF_8);
            reload(file);
            LOGGER.fine("query parameters");

            Files.writeString(file, "log.level=INVALID\n",
                    StandardCharsets.UTF_8);
            try {
                reload(file);
            } catch (IllegalArgumentException ex) {
                System.out.println("RELOAD FAILED, keeping FINE");
            }

            LOGGER.fine("still visible");
        } finally {
            LOGGER.removeHandler(OUTPUT);
            OUTPUT.close();
            Files.deleteIfExists(file);
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac --release 17 LoggingConfigReloadDemo.java
java LoggingConfigReloadDemo
```

Standard output (contains no random timestamps):

```text
RELOAD OK: INFO
INFO | application started
RELOAD OK: FINE
FINE | query parameters
RELOAD FAILED, keeping FINE
FINE | still visible
```

Why is this output deterministic?

1. The program runs sequentially on a single thread; the file is updated first, and `reload` reads it afterward.
2. The logger starts at `INFO`, so the first `FINE` message is filtered out; the handler is set to `ALL` and no parent handler duplicates output.
3. After the second `reload`, `LOGGER.setLevel(FINE)` makes FINE messages visible.
4. `Level.parse("INVALID")` throws `IllegalArgumentException` **before** the `setLevel` statement; therefore, the previous FINE level remains in effect.
5. The handler formats directly to stdout, so there are no environment-dependent timestamps, thread names, or file locations.

Understand the limitation: this example has valid rollback because it only updates **a single log level field** after parsing completes. For a full configuration with multiple appenders, encoders, and network resources, a lifecycle-managed application mechanism is required; do not generalize that every system performs atomic reloads like this example.

## 8. Automatic change detection with WatchService or polling

If an application manages files outside a framework, Java NIO provides `WatchService` to register for events such as `ENTRY_CREATE`, `ENTRY_MODIFY`, and `ENTRY_DELETE` on the **parent directory containing the file**. Upon receiving a signal, the application checks the file name, re-reads the configuration, validates it, and applies it.

However, this is a building block for a reload mechanism, not a "turn on hot reload" switch for Logback/Log4j2. When using `WatchService`, you must handle:

- A single file save can emit multiple events; you should **coalesce/debounce** them and ensure only one apply runs at a time.
- Editors or deployment systems may write a temporary file and then rename it; listening only for `ENTRY_MODIFY` on an existing file can miss updates.
- While a file is still being written, a scanner might read a **partial** version. You can validate beforehand and publish the file using an atomic rename when supported by the filesystem; verify in practice rather than assuming all filesystems/mounts support it.
- Watchers in containers, network filesystems, or config mounts behave differently; test on the target infrastructure. Polling may be more suitable in some environments.
- If the file is deleted, do not automatically apply an "empty configuration" without an explicit policy; you can retain the last-known-good state and emit an alert.
- File read errors, invalid XML, permission issues, and retries must be bounded to avoid reload loops and log spam.

If you are already using a framework-supported scanner mechanism, it is usually better to configure that scanner rather than writing an overlapping custom watcher for the same source.

## 9. Safe configuration change procedure in a running environment

### Step 1 — Confirm the initial state

Record the logging library version, the file actually loaded, the target source, effective logger levels, and appender count. Capture a state snapshot in a way that **contains no secrets**. Verify whether the application uses Logback, Log4j2, JUL, or bridges via SLF4J, because a framework's configuration does not activate based on file name alone.

### Step 2 — Choose the smallest scope

Investigating one package? Change that package's level. Changing the entire JSON format? Review the collector/schema. Switching from file to stdout? Check file-closing behavior, the container log pipeline, and write permissions. Do not use a large reload to solve a problem that only needs a single logger level change.

### Step 3 — Prepare a valid configuration

Verify XML/properties syntax, logger names, appender references, paths/permissions, formats, and retention criteria. For files outside the JAR, prefer writing to a temporary file and replacing in a way supported by your infrastructure to reduce the risk of the scanner reading a half-written configuration.

Do not put passwords, tokens, cookies, or personal data into debug/log configurations just for convenience during investigation.

### Step 4 — Apply and observe

Save the configuration or call the appropriate management API. Check the response/reload status, then emit **test events** with a distinct ID at key levels. Confirm the events reach the expected sink in the expected format. Check queue backlog/drops for asynchronous logging and file/socket resources if an appender changed.

### Step 5 — Monitor and revert

Monitor request latency, CPU, I/O, file size, queue depth, appender errors, and log drop rate. If unsatisfactory, restore the verified configuration through the same active apply mechanism. If DEBUG was enabled temporarily, define in advance when and by whom it will be reverted to INFO.

**A source file rollback** must also be detected and applied; simply copying the old file back is not enough if the scanner does not notice the change.

## 10. Consistency and risks during reload

### State transition timing

While the system is running, threads can emit logs before, during, and after a configuration change. Therefore:

- Do not assume every event timestamped after the file save uses the new configuration.
- There may be a transition window depending on how the LoggerContext/appender is managed.
- Each sink and queue has its own buffer; events enqueued before the reload may be written out later.
- If the pattern changes mid-stream, **two log line formats** may appear during the same time window; collectors must be able to handle the transition period.
- Logs already written **are not retroactively converted** to the old or new format just because the framework reloaded.

### Appenders and lost or duplicate logs

For file appenders, changing the path or rolling policy can create a new file or affect an open file. For network appenders, new connections and retries can produce errors or duplicates. For async appenders, shutting down/recreating with an undrained queue can drop events if the framework or application does not handle it completely.

Do not rely on a "reload succeeded" message to conclude that delivery is guaranteed. If logging is a mandatory audit trail, use a dedicated durable write path rather than treating in-memory logging like an exactly-once transaction.

### Multiple instances / Kubernetes

Editing a file inside one container affects only that container. When running multiple pods, the same configuration change may be applied at different times. Volumes, file mounts, and ConfigMaps update differently; **new configuration values do not automatically trigger a reload** in the JVM. You need a rollout strategy, per-instance status checks, proper permissions, and a rollback plan. In all cases, observe the version/config checksum (containing no secrets) on each instance.

## 11. Common issues and root-cause troubleshooting

| Symptom | Possible cause | How to check and resolve |
| --- | --- | --- |
| File edited but level did not change | Application is using a different file or scanner is not enabled | Identify the actual configuration source, JVM arguments, and status logs |
| Scan enabled but reload is very slow | Polling interval, scheduler, or filesystem delay | Check `scanPeriod`/`monitorInterval` and test-event emission timing |
| No reload after updating ConfigMap | Mount/path/file signal not behaving as expected | Check volume/mount type, inode/rename behavior, and scanner logs on the pod |
| Boot reports `springProfile` error during scan | Using Spring Boot extensions with Logback scan | Remove the unsupported combination; choose an appropriate level-change or restart approach |
| No DEBUG logs seen after reload | Logger still inherits another level, filter/appender blocks it, wrong package name | Check effective level, filters, appender thresholds, and sample logger |
| Too much DEBUG output appears | Enabled on root or too broad a package | Narrow the logger scope and set a scheduled revert per procedure |
| Log pattern changed but backend fails to parse | Collector/parser expects the old schema | Test parser configuration and the coexistence period of both formats |
| Cannot write to file after reload | Directory/file permissions, disk full, file handle, wrong path | Check appender status, filesystem, and verify actual events are emitted |
| Duplicate or missing logs around reload | Old/new appenders, async queue, retries, or sink changes | Correlate event IDs/counts, dropped metrics, and appender status |
| Invalid XML file yet application keeps running | Framework retains old configuration or applies partially per contract | Read status and verify effective levels/sinks instead of guessing |
| Level changed via Actuator then reverted later | Another configuration source reloaded and overwrote it | Determine precedence and which source ultimately owns the logger |
| Levels revert to old values after restart | Runtime changes were not persisted to the startup source | Record the official change if persistence is required |

## 12. Testing reload functionality

A meaningful test must cover **before/after** states and the failure path:

1. **INFO → DEBUG → INFO transition:** emit logs at both levels and count the results. Prove the configuration took effect, not just that the file changed.
2. **Correct scope:** raise the level for `com.example.payment` while unrelated loggers remain at their old levels.
3. **Syntax error or invalid level value:** test an invalid configuration in a staging/test environment, observing status and the old-config retention policy.
4. **Concurrent load:** multiple requests emitting logs during reload; check for crashes, exceptions, deadlocks, event/drop counts, and latency.
5. **Appender changes:** if changing sinks, verify the new file/collector receives events, the old sink is handled per contract, and no resources leak.
6. **Multiple instances:** verify every instance in the rollout scope receives the expected configuration version.
7. **Restart:** verify post-restart behavior matches intent; temporary changes should disappear or permanent configurations should persist as decided.
8. **Independent observability:** when log configuration breaks, a status/metric/alert channel still surfaces that the reload failed.

Avoid relying on the ordering of a few log lines during concurrency tests: logs may be buffered, written asynchronously, or routed through a collector. Define clearly what milestone counts as "written" before claiming log loss.

## 13. Distinguishing reload, rotate, and log level change

| Action | Purpose | Requires configuration change? |
| --- | --- | --- |
| **Configuration reload** | Reload source to update loggers/filters/appenders as supported | Has a clear configuration source/trigger |
| **Runtime level change** | Toggle a logger's log level at runtime | Can use an API alone without reading a file |
| **Log rotation** | Close/roll log files by size/time | Can run under the current rolling policy without reloading |
| **Restart** | Reinitialize the entire JVM and logging | Used when changes do not support live apply or operations require it |

Do not mistake `app.log` rotating for a logging configuration reload. Similarly, a `setLevel` call does not prove the change was written back to `logback.xml`.

## 14. Checklist before concluding a reload succeeded

- Identified the exact framework, version, name, and location of the configuration file/source.
- Selected a supported mechanism: Logback scan, Log4j2 monitor, management API, or restart.
- Verified **Spring Boot extensions are not combined with Logback configuration scanning**.
- Checked syntax, appender references, write permissions, and collector compatibility.
- Modified only the necessary logger/sink and kept a clear rollback path.
- Checked status/errors from the framework; did not stop at verifying the file has a new timestamp.
- Emitted test logs and verified the actual level, format, trace context, and output destination.
- Checked queue/drop/retry metrics for asynchronous logging, especially if an appender changed.
- Confirmed the effective state across all required instances and after a restart if required.
- Limited the duration and permissions for enabling DEBUG, and avoided logging secrets or sensitive data.

**Remember:** reloading is **the process of applying a new logging state to a running application**, not simply saving a file. Verify three separate stages: **configuration source changed → framework applied it → actual logs written correctly**.

### Official documentation for version-specific reference

- [Logback: Configuration, automatic reloading](https://logback.qos.ch/manual/configuration.html)
- [Apache Log4j2: Configuration and monitorInterval](https://logging.apache.org/log4j/2.x/manual/configuration.html)
- [Spring Boot: Logging and Logback extensions](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [Spring Boot Actuator: Loggers endpoint](https://docs.spring.io/spring-boot/reference/actuator/loggers.html)
