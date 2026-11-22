# Handling Misconfiguration in Java Logging

## 1. Why is logging misconfiguration a critical operational bug?

**Logging misconfiguration** is a state where an application fails to initialize or operate its logging system according to the intended policy: the configuration file cannot be found, the wrong provider is selected, invalid levels/filters/appenders are declared, file write permissions are missing, logs cannot be delivered to the destination, or a configuration is loaded but behaves differently from expectations.

The impact ranges from **missing DEBUG logs during incident investigation** to **complete log loss, duplicate entries, sensitive data exposure, startup failure, or application slowdowns due to I/O**. The most dangerous failure mode is when "the application appears to run normally" while logging has silently fallen back to a no-op or has no target appender.

Three categories of conditions must be distinguished:

1. **Unable to read/parse configuration:** missing file, invalid XML/JSON/properties syntax, or missing required components.
2. **Loaded but not applied as expected:** another file takes precedence, a property name is misspelled or ignored by the framework, incorrect level/additivity, or an incompatible provider.
3. **Valid configuration but broken sink:** missing directory write permissions, full disk, unreachable network endpoint, or full/discarding async queue.

Because logging frameworks do not share a uniform error-handling policy, **do not infer that a successful startup means healthy logging**. Both the framework's internal status messages and the actual presence of logs at the target sink must be verified.

## 2. Identifying symptoms and probable causes

| Symptom | Common Causes | Evidence to Look For |
| --- | --- | --- |
| No log lines appear at all | SLF4J has no provider, missing root/appender, level `OFF`, broken sink | SLF4J warnings; active provider; logger tree; test write |
| Only WARN/ERROR appear | Logger level or handler/appender threshold is too high | Effective level on logger, handler, filter, and root |
| Logs appear on console despite file config | Wrong config file loaded or framework using default config | Config path, startup status messages, classpath |
| Every message appears twice | Logger propagates to parent/root and writes to multiple appenders | `additivity`, `useParentHandlers`, appender-ref |
| XML parse or appender class error | Wrong syntax/tag/namespace, missing dependency, or wrong class/plugin name | Stack trace/status logger and declaration location |
| Unable to create log file | Directory, permissions, mount, path, lock, disk/quota | `IOException`, filesystem state, and JVM user |
| DEBUG works locally but not in production | Profile/config override, different root level and filter policy | Effective config and environment variables |
| Logs disappear after reloading new config | Reload failed, resources closed prematurely, provider does not support updates as assumed | Reload status messages, before/after smoke test, rollback |
| Partial log loss under high load | Async queue full, discard/drop policy, sink too slow | Queue depth, drop counter, sink throughput, shutdown timeout |

**One symptom can have multiple causes.** For example, "missing DEBUG" may happen because the logger filters events before creation, the console handler filters them again, or both.

## 3. Principles for handling failures in logging itself

Logging is an infrastructure component: if a logger is broken, calling that same logger to report "the logger is broken" may produce no evidence. Therefore:

- During initialization, **emit minimal diagnostic messages via `System.err` or an independent status logger**. Do not use this as a long-term business logging channel; never print passwords, tokens, or connection strings containing credentials.
- **Classify the criticality of logging requirements:** debug logs can usually fall back to a backup configuration; audit logs or mandatory compliance records must not allow business processing to continue without a sufficiently guaranteed write channel.
- **Do not swallow configuration exceptions:** when switching to a fallback, emit a clear signal that degraded mode is active and requires remediation.
- **Verify the actual end-to-end path of an event:** logger call → level/filter → appender/handler → file/stdout/network → collector. A "sent" record does not prove the collector persisted it.
- **Keep a known-good configuration for rollback:** load the new configuration in a test environment, verify minimal log output, and only then roll out broadly.
- **Do not automatically disable logging** just to "save" startup when the business strictly requires activity history or auditing.

## 4. Step-by-step investigation workflow

1. **Isolate the scope:** identify the exact JVM, build artifact, JDK version, logging libraries, container/pod, timestamp of occurrence, and the event that should have been logged.
2. **Identify the actual framework:** JUL (`java.util.logging`), SLF4J API bound to Logback or another provider, Log4j 2 Core, or bridges between systems. The `org.slf4j.Logger` API alone does not indicate which sink is in use.
3. **Determine which configuration file was loaded:** check paths from JVM system properties, classpath, profiles, volume mounts, and framework precedence rules. Do not inspect only files in the repository.
4. **Enable controlled startup diagnostics:** use the framework's internal status/diagnostics and read the process stderr at startup. Record errors such as class not found, missing appender, or invalid level.
5. **Verify loggers and sinks:** check effective levels, filters, additivity, root appenders, and sink permissions. Emit a test event with a unique ID and observe it at the intended destination.
6. **Fix only one group of causes at a time:** adjust the config file/provider or write permissions, then retry with the exact same build and environment; avoid simultaneous changes that obscure the root cause.
7. **Verify after fixing:** confirm startup messages, test INFO/WARN/ERROR logs as appropriate, no duplicates, stability under high load, and proper handling of buffered logs on restart/shutdown.

Do not rely solely on `logger.isLoggable(Level.INFO)` or `log.isDebugEnabled()` as a complete check: those APIs only evaluate level/filter conditions within a limited scope and do not prove that file/network writes succeeded.

## 5. Java Util Logging (JUL): effective configuration and common pitfalls

JUL is built into the JDK via `java.util.logging`. Default initialization configuration may come from the JDK's file, or from a file specified via a JVM property:

~~~bash
java -Djava.util.logging.config.file=conf/jul.properties -cp out com.example.Main
~~~

The `-D...` argument must be passed when launching the JVM (placed before the main class name). Minimal `jul.properties` file:

~~~properties
handlers=java.util.logging.ConsoleHandler
.level=INFO
java.util.logging.ConsoleHandler.level=INFO
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
~~~

In JUL, both **logger level** and **handler level** can filter messages. For example, if a logger allows `FINE` but `ConsoleHandler.level=INFO`, `FINE` records will still not be output by the handler. Child loggers can inherit levels from parent loggers; `setUseParentHandlers(false)` stops propagating events to parent handlers and can cause logs to disappear if the child logger has no handler of its own.

Items to diagnose:

- `java.util.logging.config.file` points to a wrong path: observe startup errors and confirm the file actually exists in the runtime environment.
- Wrong handler or formatter class name: check stderr/JUL internal messages; do not assume the application will always halt.
- Writing to `FileHandler`: verify `java.util.logging.FileHandler.pattern`, parent directory, lock files, and write permissions.
- Calling `LogManager.getLogManager().readConfiguration(...)` while the application is running can **reset existing loggers**, altering handlers/levels attached programmatically. Per the Java 17 API, when updating configuration at runtime, look at `updateConfiguration(...)` instead of arbitrarily calling `readConfiguration(...)`.
- JUL does not guarantee that every misspelled property will raise an error sufficient to fail startup. For critical application-owned configuration, implement a validation layer for required keys and values before applying them.

The pure-JDK configuration validation example below demonstrates how to reject an invalid value explicitly rather than silently ignoring it.

## 6. Java 17 example: validating configuration before applying

This example uses an **application-defined properties file** with the key `app.level`. It is not a replacement for full JUL configuration syntax, but rather a demonstration of **validate → apply → fail-fast error reporting**. The program requires no external dependencies beyond the JDK.

Create **LoggingConfigDemo.java**:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import java.util.Properties;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LoggingConfigDemo {
    private static final Logger LOG =
            Logger.getLogger(LoggingConfigDemo.class.getName());

    private static Level parseLevel(Properties props) {
        String raw = props.getProperty("app.level");
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("app.level is required");
        }
        return switch (raw.trim().toUpperCase(Locale.ROOT)) {
            case "SEVERE" -> Level.SEVERE;
            case "WARNING" -> Level.WARNING;
            case "INFO" -> Level.INFO;
            case "CONFIG" -> Level.CONFIG;
            case "FINE" -> Level.FINE;
            case "FINER" -> Level.FINER;
            case "FINEST" -> Level.FINEST;
            default -> throw new IllegalArgumentException(
                    "unsupported app.level: " + raw);
        };
    }

    private static void startLogging(Level level) {
        ConsoleHandler handler = new ConsoleHandler();
        handler.setLevel(Level.ALL);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " "
                        + formatMessage(record) + System.lineSeparator();
            }
        });

        LOG.setUseParentHandlers(false);
        LOG.setLevel(level);
        LOG.addHandler(handler);
        try {
            LOG.info("startup ok");
        } finally {
            LOG.removeHandler(handler);
            handler.close();
        }
    }

    public static void main(String[] args) {
        if (args.length != 1) {
            System.err.println("CONFIG_ERROR expected one properties path");
            System.exit(2);
            return;
        }
        try (InputStream input = Files.newInputStream(Path.of(args[0]))) {
            Properties props = new Properties();
            props.load(input);
            Level level = parseLevel(props); // Validate before applying.
            startLogging(level);
            System.out.println("CONFIG_OK level=" + level.getName());
        } catch (IOException | IllegalArgumentException ex) {
            System.err.println("CONFIG_ERROR " + ex.getMessage());
            System.exit(2);
        }
    }
}
~~~

Create **logging-good.properties**:

~~~properties
app.level=INFO
~~~

And **logging-bad.properties**:

~~~properties
app.level=VERBOSE
~~~

Compile with JDK 17 or newer:

~~~bash
javac --release 17 LoggingConfigDemo.java
java LoggingConfigDemo logging-good.properties
~~~

**Valid case**, exact stream outputs:

- Standard error (because JUL's `ConsoleHandler` writes to stderr): `INFO startup ok`
- Standard output: `CONFIG_OK level=INFO`
- Exit code: `0`

Test invalid configuration:

~~~bash
java LoggingConfigDemo logging-bad.properties
~~~

**Invalid case**: stderr outputs `CONFIG_ERROR unsupported app.level: VERBOSE`, stdout has no output, and the exit code is `2`. The program also reports `app.level is required` if the key is missing or blank.

**How it works:**

1. `Properties.load(...)` reads the file from the CLI path; missing or unreadable files raise `IOException`.
2. `parseLevel(...)` validates the required key against the application's accepted level list. `VERBOSE` is invalid under the demo policy and is rejected immediately.
3. Only after validation succeeds is `ConsoleHandler` created and attached. `setUseParentHandlers(false)` prevents duplicate output from the root handler; setting the handler level to `ALL` avoids a second filter layer on top of the selected logger level.
4. On error, the message goes directly to stderr without depending on the logger being initialized, and the program exits with a non-zero status code.
5. The handler is removed and closed in `finally` so the example does not leak resources.

This example only demonstrates validating one configuration key and handling an invalid level; in a real application, validate other critical fields such as sink URLs/paths, formats, permissions, and compatibility. Because the test log is emitted at INFO level, a `WARNING` configuration will filter out the test record; in a real health check, emit an event at an appropriate level or check the logger level separately.

A useful policy is: **reject unknown keys for critical application-managed operational configurations**, reporting the invalid key name and suggesting the correct key. Frameworks differ in whether they accept or reject unknown keys, so validation must match the specific version and schema in use.

## 7. SLF4J: missing provider or multiple providers

SLF4J is a facade/API; it requires a **provider** to write to a destination. Starting with **SLF4J 2.x**, providers are discovered via `ServiceLoader`. Two typical cases:

**Missing provider:**

~~~text
SLF4J: No SLF4J providers were found.
SLF4J: Defaulting to no-operation (NOP) logger implementation
~~~

This can allow the application to keep running while **producing no logs through SLF4J**. The fix is to add **one compatible provider** (for example, Logback Classic compatible with the active API version), then verify via startup logs and a test event.

**Multiple providers/bindings:** the classpath may simultaneously contain multiple backends; SLF4J may emit a warning and select an unexpected provider. Remove redundant providers, typically keeping only **one** backend to avoid ambiguity.

**Version mismatch:** SLF4J 2.x no longer uses the legacy 1.7 `StaticLoggerBinder` binding mechanism. If a 1.7-era binding is accidentally included in an SLF4J 2.x application, the backend may not be recognized.

Verification checklist:

- Identify the effective `slf4j-api` version and provider in the runtime dependency tree, including transitive dependencies; inspecting only direct entries in `pom.xml` or `build.gradle` can miss dependencies pulled in by other libraries.
- Read startup warnings and confirm which provider was selected.
- Do not declare a provider in a reusable library if the library only needs the SLF4J API; the host application should decide the backend.
- After fixing dependencies, re-verify actual log output; avoid silencing the warning by adding an NOP provider when logging is actually desired.

The warning messages above are real examples published by SLF4J, not a guaranteed API across all versions.

## 8. Logback: reading internal status and fixing broken appenders

When using **Logback Classic**, configuration typically resides in `logback.xml` or is managed via another file by a framework. Minimal example for a console backend:

~~~xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

This configuration is for an application that already includes the Logback dependency, not for running with plain JDK `java`. Common errors:

- `<appender-ref ref="CONSOLE"/>` points to a non-existent name or an appender that failed to initialize.
- Defining a `FileAppender` with an unwritable path; check directory, permissions, and I/O errors.
- Misspelled appender/encoder class name, malformed XML, or placing the configuration file where it is not loaded.
- Root level allows INFO, but a child logger is configured to `OFF`/`ERROR`; or `additivity=false` while the child logger references no appenders.
- Two appenders process the same event because both the child logger and root are configured; inspect both additivity and appender references.

**Enabling diagnostic output:** Logback has an internal status system; it automatically prints status messages when warnings/errors occur during configuration parsing, except in certain cases where a status listener is registered. In a test environment, you can add `debug="true"` to the `<configuration>` element for detailed status output:

~~~xml
<configuration debug="true">
    <!-- Keep appenders, loggers, and root as in the configuration under test. -->
</configuration>
~~~

Do not leave overly verbose diagnostics enabled long-term in production if there is a risk of log noise or exposing file paths/configuration details. Resolve warnings/errors by fixing the **root cause**: paths, dependencies, appender names, and references.

**Reloading configuration:** Logback supports scan/reconfigure depending on configuration and version. When a new configuration is invalid, inspect status messages to see which configuration is active and run a smoke test; never assume editing a file on disk means the application has successfully loaded it.

## 9. Log4j 2: status logger, configuration paths, and plugins

Log4j 2 Core uses a plugin system to instantiate appenders, filters, layouts, and configuration components. Plugin or property errors can be recorded in the **Status Logger**, an internal logger separate from application loggers.

When investigating, temporarily start with:

~~~bash
java -Dlog4j2.debug=true -cp "app-and-dependencies/*" com.example.Main
~~~

`-Dlog4j2.debug=true` enables detailed Status Logger output to show configuration discovery/loading and internal errors. The command above uses an illustrative classpath; replace it with the application's actual classpath and main class. Log4j 2 also supports `log4j2.statusLoggerLevel` to control status verbosity; in newer versions, the `status` attribute on `<Configuration>` has been deprecated since 2.24.0. Configure the status level via system property so it takes effect from the very beginning of startup.

A basic console **log4j2.xml** file:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_ERR">
            <PatternLayout pattern="%d{HH:mm:ss.SSS} %-5level %logger - %msg%n"/>
        </Console>
    </Appenders>
    <Loggers>
        <Root level="info">
            <AppenderRef ref="CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
~~~

This configuration requires Log4j 2 Core and does not apply to JUL or Logback. A specific configuration file can be designated via a Log4j 2 property:

~~~bash
java -Dlog4j2.configurationFile=conf/log4j2.xml -cp "app-and-dependencies/*" com.example.Main
~~~

When failures occur, determine:

1. Is Log4j 2 Core actually in use, or is the API bridged to another backend? A Log4j 2 configuration will not control a Logback backend just because the application imports a different API.
2. Which config file did Log4j discover? Wrong file extensions, paths, or mounts can cause the framework to use defaults or fallbacks.
3. Are there plugin/class/layout/appender errors in the Status Logger?
4. Does `AppenderRef` point to a defined appender? Do root/logger levels and filters block the event before it reaches the appender?
5. If `monitorInterval` is set for reloading, did reconfiguration occur and is the application still logging?

**Do not use Log4j 1.x configurations as if they were Log4j 2.** Class names, file structure, and compatibility mechanisms differ. Always consult documentation matching the active backend version.

## 10. Misconfigured levels, filters, and propagation: easily misdiagnosed bugs

A log event can be dropped at several different stages:

~~~text
Logger at business class
   │ logger level / filter
   ▼
Parent or root logger (if propagation/additivity)
   │ root level / filter per framework
   ▼
Handler/Appender
   │ handler/appender threshold / filter
   ▼
Layout / Encoder
   ▼
File / Console / Network
~~~

Key points to remember:

- `DEBUG`/`FINE` can be blocked before reaching the sink. Lowering the appender level is **not enough** if an upstream logger still filters it out.
- In JUL, `Logger.setUseParentHandlers(false)` stops propagation to parent handlers; in Logback/Log4j 2, `additivity=false` has a similar effect on parent logger linkage, though the syntax differs.
- Duplicate logs usually occur because the same event traverses **multiple appenders/handlers**. Trace the event's path before deleting an appender by mistake.
- Broken formats/patterns can omit fields (timestamp, trace ID, MDC) even when the event is written. Check the format string and context configuration instead of assuming every blank field is an event delivery failure.
- With async appenders, a successful producer enqueue does not guarantee sink delivery; if the queue fills up or shutdown happens too fast, logs can be lost due to backpressure/discard policies.

Broken example:

~~~properties
# JUL: root logs INFO, ConsoleHandler only logs WARNING and above.
.level=INFO
java.util.logging.ConsoleHandler.level=WARNING
~~~

To display INFO on the console, **both** thresholds must allow INFO, provided `ConsoleHandler` is actually attached to the root logger.

## 11. Path and write permission errors in appenders

When a backend uses file logging, seemingly valid configurations can still fail to produce logs:

- **Relative paths:** `logs/app.log` is typically resolved against the process working directory, which can differ across IDEs, services, cron jobs, and containers.
- **Missing directory or insufficient permissions:** the JVM user lacks permission to create files/directories, a volume is mounted read-only, or SELinux/AppArmor/container policies block access.
- **Full disk/quota:** the appender initializes successfully but starts failing hours later; inspect disk/quota and the appender's error channel.
- **File locks/rotation:** multiple JVMs writing to the same path or incompatible rollover settings cause contention, interleaved data, or unintended file renames.
- **Remote sinks:** DNS, authentication, TLS certificates, timeouts, or queue limits cause log delivery to fail even after configuration parsing succeeds.

Do not rely solely on `Files.isWritable(path)` before startup: permissions can change, and a pre-check does not prove open/write operations will succeed. Handle I/O exceptions properly, capture errors from the framework's status logger, and trigger alerts when a sink becomes unavailable.

When testing, distinguish between **lines emitted by the application**, **events accepted by the backend**, and **records appearing in the receiving system**.

## 12. Controlled fallback, rollback, and reload

Handling strategies depend on business requirements:

| Context | Appropriate Handling |
| --- | --- |
| Local tools or non-mandatory diagnostic logs | Can fall back to console with a clear warning and degraded indicator |
| Production services needing diagnostics without durable audit requirements | Retain last known-good config if supported; otherwise consider failing startup or falling back per operational policy |
| Systems requiring mandatory audit logs | Never silently continue without the audit channel; fail closed or use a pre-designed durable write channel |
| High load with async appenders | Monitor dropped events, queue depth, backpressure, and drain/shutdown; fallback cannot recover already-lost logs |
| Runtime reload | Validate new config, activate via framework mechanism, emit test event, verify output, and roll back if checks fail |

In high-availability systems, **do not retry infinitely in an unbounded loop** when configuration is invalid. Syntax errors will not fix themselves on retry. Distinguish **permanent** errors (wrong key, malformed XML, missing provider) from **transient** errors (temporary network loss to a remote sink) when deciding on retry/backoff.

A safe deployment workflow:

1. Lint/parse and validate the configuration in CI against the exact logging framework version used by the application.
2. Verify dependency resolution and confirm a test record reaches a mock sink or test filesystem.
3. Roll out a small canary/rolling update, observing internal status and log appearance rates.
4. On failure, roll back to a known-good configuration/build; avoid patching a single replica's file and forgetting the rest.
5. After remediation, assess the number of missing records (if possible) and document the observation gap window.

Never log passwords or secrets in invalid-config messages, public stack traces, or full dumps of all environment variables.

## 13. Automated testing to catch misconfiguration early

Do not just test whether a file "exists". A useful test suite covers:

1. **Valid configuration:** the application initializes logging and writes INFO/WARN to the expected sink with the expected structured fields and format.
2. **Missing file:** meaningful error detection; if fail-fast policy applies, the process exits with a non-zero code.
3. **Syntax error:** malformed XML tags or invalid property types; status/internal errors must indicate the failure rather than silently succeeding.
4. **Invalid level/key:** non-whitelisted or misspelled properties must be caught during validation.
5. **Missing/multiple SLF4J providers:** inspect the dependency tree and actual backend startup warnings.
6. **Unwritable sink:** test with an unwritable directory, full quota, or simulated I/O error via a test double; health signals must report the failure.
7. **Propagation/filters:** verify an event appears the exact expected number of times without being misfiltered or duplicated.
8. **Reload/rolling deployment:** verify the new configuration is applied, rollback works, and loggers continue operating under concurrent log load.
9. **Async and graceful shutdown:** verify queued events, discard policies, timeouts, and appender flushing.

For file-based tests, use an isolated file/directory per test, clean up resources after closing appenders, and avoid depending on developer machine log files or fixed paths prone to conflict.

You can use a **smoke event** with a unique identifier (such as `event=logging_smoke_check` and `buildId`) to verify the path from application to collector. Separate test configurations from operational policies so sensitive data is never emitted into logs.

## 14. Common mistakes

| Mistake | Consequence | How to Fix |
| --- | --- | --- |
| "App started up, so logging must be fine" | SLF4J NOP/default provider or broken sink still lets the app run | Check internal status and verify events at the sink |
| Using a broken logger to report logger errors | Initialization failure evidence is completely lost | Emit minimal warnings via stderr/status logger |
| Changing only the root level | Handler/appender filters still block events | Inspect the entire event pipeline |
| Lowering production level to TRACE indefinitely | Increased load, data exposure, harder investigation | Enable time-boxed and roll back afterward |
| Ignoring classpath/transitive dependencies | Multiple providers or version mismatches | Inspect runtime dependency graph; keep one compatible provider |
| Reading repo config while ignoring runtime env | Service loads a different config, stale mount, or profile override | Confirm the effective config path inside the JVM |
| Ignoring errors when opening/writing files | Logs are lost silently | Report I/O errors, health metrics, alerts, and policy-based fallback |
| Arbitrarily reloading JUL with `readConfiguration()` | Resets existing loggers/handlers | Use appropriate update APIs and verify side effects |
| Closing appenders while async workers are active | Buffered logs are lost | Stop producers, drain queues, stop context per lifecycle |
| Adding NOP provider to silence warnings | Warnings disappear, but application writes no logs | Add a real provider targeting the desired sink |
| Treating flush as durable persistence | Crash/kill can still lose data | Use durable storage/ACKs when durability is required |

## 15. Self-check questions and answer hints

1. An application calls `log.info(...)` normally, but no logs appear in production. Why is checking `isInfoEnabled()` insufficient?
2. When using JUL, why does `.level=FINE` not guarantee `FINE` output if `ConsoleHandler.level=WARNING`?
3. SLF4J 2.x warns "No SLF4J providers were found". What does this usually mean and what should you check next?
4. Why can a logger with `additivity=false` become completely silent if it has no appender of its own?
5. What channels do Logback and Log4j 2 provide to diagnose initialization errors without depending on application loggers?
6. When no log file is created in a container, what should you check besides XML syntax?
7. Why should you not rely on `Thread.sleep(...)` to confirm async logging has finished writing?
8. When is falling back to console acceptable, and when should startup fail?

**Hints:** (1) the event may be blocked at a filter/appender/sink or provider; (2) the handler filters again; (3) SLF4J may be using NOP, so add a compatible provider; (4) propagation to parent is disabled, leaving no destination; (5) Logback internal status, Log4j 2 Status Logger; (6) path, working directory, permissions, disk/quota, mount, locks, network; (7) waiting an arbitrary duration does not establish a barrier/drain; (8) depends on business policy and audit/durability requirements.

## 16. Official references

- [JDK 17 — LogManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogManager.html): loading JUL config, `java.util.logging.config.file`, effects of `readConfiguration()` and `updateConfiguration()`.
- [JDK 17 — Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): levels, filters, handlers, and `setUseParentHandlers`.
- [SLF4J — Diagnostic messages](https://www.slf4j.org/codes.html): missing provider, multiple providers, differences between API 1.7 and 2.x.
- [Logback — Configuration](https://logback.qos.ch/manual/configuration.html): configuration syntax and internal status.
- [Logback — Architecture](https://logback.qos.ch/manual/architecture.html): logger hierarchy, effective level, and additivity.
- [Log4j 2 — Status Logger](https://logging.apache.org/log4j/2.x/manual/status-logger.html): `log4j2.debug`, `log4j2.statusLoggerLevel`, and startup diagnostics.
- [Log4j 2 — Configuration](https://logging.apache.org/log4j/2.x/manual/configuration.html): config files, root/logger/appender, plugins, and reload.
