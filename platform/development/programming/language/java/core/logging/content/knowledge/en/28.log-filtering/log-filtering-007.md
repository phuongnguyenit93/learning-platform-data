# Environment-Based Filtering in Java Core Logging

## 1. Objectives

**Environment-based filtering** is the practice of determining which log events are recorded when an application runs in different environments: `dev` (development), `test` (testing), `staging` (pre-production), and `prod` (production). The exact same `logger.debug(...)` or `logger.info(...)` call can be retained, discarded, or routed to different destinations depending on the runtime configuration.

It is important to distinguish **level-based filtering** (for example, enabling DEBUG in dev while keeping only INFO/WARN/ERROR in prod) from **content- or event-attribute-based filtering** (for example, dropping repetitive health-check events while keeping error and audit events). They are often combined, but one does not replace the other.

By the end of this lesson, you will be able to:
- Design distinct logging policies for `dev`, `test`, `staging`, and `prod` based on operational goals.
- Explain the order of evaluation across logger levels, logger filters, handler/appender filters, and log destinations.
- Write a Java 17+ filter using `java.util.logging.Filter`, run it, and verify the output for each environment.
- Configure Logback/Log4j 2 per environment, understanding what belongs to the logging backend versus what belongs to a framework such as Spring Boot.
- Test filtering policies, avoid misconfigurations, prevent data leaks, and preserve essential diagnostic information during incidents.

## 2. Why Do Different Environments Need Different Policies?

A log line that is helpful during development can become a liability in production. For instance, 30 DEBUG lines per request help trace data flow in dev, but in prod with thousands of requests per second, that volume of DEBUG logs consumes CPU, storage, and ingestion costs. Conversely, turning off too many logs in prod leaves incident investigations without evidence.

The following table is an **illustrative policy** that should be adjusted based on your system's observability and reliability requirements:

| Environment | Typical Log Level | Event Filtering Policy | Log Destination | Purpose |
| --- | --- | --- | --- | --- |
| `dev` | DEBUG or FINE for code under active development | Keep details needed for debugging; optionally drop noisy repetitive events | Console/local file | Tracing individual execution flows |
| `test` | INFO/WARN by default, DEBUG per test | Capture deterministic events; limit framework noise and random data | In-memory appender/CI console | Stable assertions and useful logs when tests fail |
| `staging` | INFO/WARN, with controlled DEBUG | Drop overly frequent health probes; keep errors, request IDs, traces | Test collector and console | Validating near-production behavior |
| `prod` | INFO or WARN depending on the service | Reduce repetitive logs, prioritize errors/abnormal latency, limit expensive logs | Centralized pipeline with retention | Observability, alerting, and incident investigation |

These are **not hard rules**: a critical service may need structured INFO logs in production; an individual unit test may enable DEBUG. Decisions should be based on event volume, diagnostic value, cost, and retention requirements.

**Note:** environment names are merely configuration inputs. Java SE does not assign any special meaning to `app.env`, `spring.profiles.active`, or `APP_ENV` on its own. The application or framework must define how to read these values and translate them into levels, filters, and appenders.

## 3. Distinguishing Logger Levels from Event Filters

A generalized logging pipeline:

```text
Code calls logger.debug/info/warn(...)
              |
              v
      Early level / filter
              |
       Is the event accepted?
         |              |
         No             Yes
         |              |
      Discard           v
                Create/capture LogEvent
                        |
                        v
                 Appender/Handler
                 + target filter
                        |
                        v
                  Console / file /
                  collector / test
```

The exact order **depends on the backend**:
- In **JUL** (`java.util.logging`), `Logger` has a level and a `Filter`; `Handler` also has a level and a `Filter`. If a logger rejects an event by level, configuring a filter on the handler alone cannot recover it.
- In **Logback**, the logger level determines the baseline log threshold. A `TurboFilter` can intervene early before an event is created; standard filters on an appender are evaluated after the event reaches that appender. Filter results use `DENY`, `NEUTRAL`, and `ACCEPT`.
- In **Log4j 2**, filter layers exist at the global, logger, logger configuration, appender reference, and appender levels. `DENY` drops the event; `NEUTRAL` passes it to subsequent rules; `ACCEPT` has layer-dependent semantics and should not be assumed to always go through the exact same level check.

**Early filtering** is generally more cost-effective: there is no need to allocate an event or enqueue it asynchronously when you already know the log should not be recorded. **Appender-level filtering** is suitable when an event should go to a file but not appear on the console; the trade-off is that event creation overhead may have already been incurred.

### Level, Marker, and Context

| Criterion | Example | Use Case |
| --- | --- | --- |
| Level | DEBUG, INFO, WARN, ERROR; JUL: FINE, INFO, WARNING, SEVERE | Distinguishing verbosity and severity |
| Logger name/package | `com.example.order` | Temporarily enabling DEBUG for a specific module |
| Marker/event type | `HEALTHCHECK`, `PAYMENT_FAILED` | Dropping repetitive probes, keeping meaningful errors |
| Context | `requestId`, `tenantId`, `traceId` | Searching, routing, or scoping by context |
| Environment | `dev`, `test`, `staging`, `prod` | Selecting the policy appropriate for the deployment stage |
| Destination | Console, file, audit sink | Each destination receives a distinct subset of events |

Do not infer importance solely from the level: an INFO event can carry critical business information, while a WARN event might be a familiar warning that still needs to be retained for trend detection. If the goal is to separate mandatory audit logs from diagnostic logs, use a dedicated reliable write path so general filters do not accidentally drop audit records.

## 4. Designing the Policy Before Writing Code

A clear approach is to establish a **policy matrix** reviewed alongside the application. Example for an order-processing service:

| Event | Level | Dev | Test | Staging | Prod |
| --- | --- | --- | --- | --- | --- |
| `debug_cache` | DEBUG/FINE | Keep | Drop by default | Drop | Drop |
| `order_created` | INFO | Keep | Keep | Keep | Keep if needed for business tracking |
| `health_probe` | INFO | May keep | May keep | Drop or sample | Drop or measure via metrics |
| `order_failed` | ERROR/WARNING | Keep | Keep | Keep | Keep and trigger alerts when needed |
| `security_audit` | Separate audit channel | Keep | Test data | Keep | Ensure retention and durability policies |

Clearly define **who owns the policy** and its constraints:
1. Read the environment from a configuration source **controlled at deployment time**, not from arbitrary HTTP headers sent by clients.
2. Normalize and validate the environment value against an allowlist. For unknown names, either fail fast at startup or fall back to a well-defined conservative policy; avoid defaulting to DEBUG.
3. Keep event/marker names stable as part of a contract rather than searching for an arbitrary word inside a user-facing message string.
4. Scope log changes strictly to what is needed for investigation, with a time limit and a rollback mechanism after the incident.
5. Preserve meaningful WARN/ERROR events, exceptions, and audit logs according to business requirements. Do not treat log filtering as a data-security mechanism.

A production policy does not have to be strictly "WARN and above only." For example, you might keep structured INFO events for orders while filtering out health-check events at the same level; in that case, an event-type-based filter is necessary.

## 5. Standalone Java 17+ Example: Environment-Based Level and Event Filtering

This example uses **Java Util Logging**, built into the JDK with no external dependencies. The program:
- Reads the `app.env` system property; defaults to `prod` when omitted; rejects unknown values.
- Sets the logger level based on the environment.
- Attaches a `java.util.logging.Filter` to drop `health_probe` events in `staging`/`prod`.
- Attaches a dedicated `Handler` that prints to stdout, disabling parent handler propagation to avoid duplicate output.
- Leaves no JVM-wide global state after the example; the logger is created privately via `getAnonymousLogger()`.

Create the file **`EnvironmentLogFilterDemo.java`**:

```java
import java.util.Locale;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class EnvironmentLogFilterDemo {
    enum Environment { DEV, TEST, STAGING, PROD }

    static Environment readEnvironment(String raw) {
        String value = raw.trim().toLowerCase(Locale.ROOT);
        return switch (value) {
            case "dev" -> Environment.DEV;
            case "test" -> Environment.TEST;
            case "staging" -> Environment.STAGING;
            case "prod" -> Environment.PROD;
            default -> throw new IllegalArgumentException(
                    "Unknown app.env: " + raw);
        };
    }

    static Level minimumLevel(Environment env) {
        return switch (env) {
            case DEV -> Level.FINE;
            case TEST, STAGING -> Level.INFO;
            case PROD -> Level.WARNING;
        };
    }

    static boolean allowEvent(Environment env, LogRecord record) {
        if ((env == Environment.STAGING
                || env == Environment.PROD)
                && "health_probe".equals(record.getMessage())) {
            return false;
        }
        return true;
    }

    public static void main(String[] args) {
        Environment env = readEnvironment(
                System.getProperty("app.env", "prod"));

        Logger logger = Logger.getAnonymousLogger();
        logger.setUseParentHandlers(false);
        logger.setLevel(minimumLevel(env));
        logger.setFilter(record -> allowEvent(env, record));

        Handler sink = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println(record.getLevel().getName()
                            + " " + record.getMessage());
                }
            }

            @Override
            public void flush() {}

            @Override
            public void close() {}
        };
        sink.setLevel(Level.ALL);
        logger.addHandler(sink);

        try {
            logger.fine("debug_cache");
            logger.info("order_created");
            logger.info("health_probe");
            logger.warning("order_failed");
        } finally {
            logger.removeHandler(sink);
            sink.close();
        }
    }
}
```

Compile with JDK 17 or later:

```bash
javac EnvironmentLogFilterDemo.java
```

Run each environment separately (the `-D` flag must appear **before** the class name):

```bash
java -Dapp.env=dev EnvironmentLogFilterDemo
java -Dapp.env=test EnvironmentLogFilterDemo
java -Dapp.env=staging EnvironmentLogFilterDemo
java -Dapp.env=prod EnvironmentLogFilterDemo
```

**Expected output, with each run as an independent command:**

`dev`:

```text
FINE debug_cache
INFO order_created
INFO health_probe
WARNING order_failed
```

`test`:

```text
INFO order_created
INFO health_probe
WARNING order_failed
```

`staging`:

```text
INFO order_created
WARNING order_failed
```

`prod`:

```text
WARNING order_failed
```

Explanation:
- `dev` sets `Level.FINE`, so it keeps FINE, INFO, and WARNING; the filter also does not drop health checks.
- `test` sets `Level.INFO`, so FINE is dropped by the logger before reaching `Filter`.
- `staging` keeps INFO and WARNING, but `allowEvent` specifically drops `health_probe`.
- `prod` sets `Level.WARNING`, so both INFO and FINE are dropped by level; the `health_probe` condition in the filter no longer has to decide for that INFO line.
- When `-Dapp.env` is omitted, it defaults to `prod`; passing an invalid value such as `-Dapp.env=production` throws an `IllegalArgumentException` so operators catch misconfigurations immediately.

Comparing `LogRecord.getMessage()` by exact string in the filter is **for illustration only**. In larger applications, use a standardized event code, marker, or structured field; free-form messages can change due to localization, parameters, or refactoring.

The example uses `Logger.getAnonymousLogger()` to avoid affecting loggers used by tests or frameworks. For named loggers in real applications, remember that levels, filters, and handlers can be configured across multiple tiers; never mutate the global root logger from business code.

## 6. JUL: File Configuration and Filter Placement

JUL supports configuring levels and handlers via a properties file. Example production-specific resource **`config/logging-prod.properties`**:

```properties
handlers = java.util.logging.ConsoleHandler
.level = WARNING
java.util.logging.ConsoleHandler.level = WARNING
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter
com.example.orders.level = INFO
```

Note: the `com.example.orders` logger is set to INFO, but the root handler is set to WARNING, so INFO events from this logger **will not appear in ConsoleHandler**. To let INFO reach the console, the handler level must also be adjusted; this is an intentional example demonstrating **two distinct filtering points**.

Run the application using JUL (illustrative launcher command, where `com.example.Main` is your application class):

```bash
java -Djava.util.logging.config.file=config/logging-prod.properties com.example.Main
```

This property must be supplied before `LogManager` initializes; a real application also needs the proper classpath or module path. When deploying via a container or service manager, ensure the file path exists in that environment rather than guessing the working directory.

Two places to attach filters in code:
- `Logger.setFilter(Filter)`: decides whether an event is emitted or dropped by the current logger.
- `Handler.setFilter(Filter)`: decides whether a specific handler/sink receives the event.

Because both the logger and the handler enforce acceptance checks, attaching a filter on a handler to accept INFO cannot "recover" an INFO event already dropped by the logger's level. Do not rely on a parent logger's filter to override all rules of child loggers; verify JUL's logger hierarchy and handler propagation model during deployment.

When testing, use an in-memory handler and restore the previous configuration in `finally`. Avoid calling `LogManager.reset()` in parallel tests because it affects logging across the entire JVM.

## 7. Logback: Environment-Based Configuration

In applications using SLF4J + Logback Classic, **SLF4J** provides the API while **Logback** reads the configuration file and evaluates levels and filters. Two common approaches are:
1. Using separate configuration files (`logback-dev.xml`, `logback-test.xml`, `logback-prod.xml`) and selecting the file at startup.
2. Using a single parameterized configuration for levels and destinations, receiving values from the deployment system or framework configuration mechanism.

Example **`config/logback-prod.xml`**:

```xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <filter class="ch.qos.logback.classic.filter.ThresholdFilter">
            <level>WARN</level>
        </filter>
        <encoder>
            <pattern>%level %logger{32} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

What happens here:
- The root level `INFO` allows INFO, WARN, and ERROR to pass the logger level check.
- `ThresholdFilter` on `ConsoleAppender` **drops events below WARN** only at this console destination.
- If another appender accepts INFO, those events can still be retained at that other destination. If you **only have the console** and do not need INFO anywhere, setting root to `WARN` earlier usually saves event creation and dispatching overhead.
- `ThresholdFilter` returns `DENY` for levels below the threshold and `NEUTRAL` for all other levels; it does not reject everything other than WARN.

With default Logback configuration (not overridden by a framework or custom configurator), you can select the file at startup:

```bash
java -Dlogback.configurationFile=config/logback-prod.xml -jar app.jar
```

This is an illustrative command for an application packaged as `app.jar` with Logback on the runtime classpath. The property must be set **before Logback initializes**. Logback automatically searches for `logback-test.xml` and `logback.xml` on the classpath if no other configuration is specified; ensure test resources are never accidentally packaged into production artifacts.

**To receive DEBUG in dev:** create a dev configuration with root DEBUG and a console threshold of DEBUG (or omit `ThresholdFilter` if unnecessary). Keep level and filter configuration as deployment data rather than scattering `if (env) log(...)` checks throughout business logic.

### When You Need Event-Type Filtering

If prod should receive order INFO logs while dropping health-check INFO logs, `ThresholdFilter` is not enough because both share the same level. You can use **markers/MDC and a custom Logback Filter**, or a separate appender for the corresponding event type. A standard Logback filter extends `ch.qos.logback.core.filter.Filter<ILoggingEvent>` and returns `DENY`, `NEUTRAL`, or `ACCEPT`. Attach it to the right appender, and verify upstream levels and additivity behavior. For early filtering before event creation, consider a `TurboFilter` according to your Logback version's documentation.

Do not rely on a string-matching filter for secret contents to "filter out leaks"; sensitive data may already have been formatted into the message before the appender rejects it.

## 8. Log4j 2: Using Markers for Environment-Based Event Filtering

Log4j 2 Core includes `MarkerFilter` out of the box. Example production configuration **`config/log4j2-prod.xml`** that drops events carrying the `HEALTHCHECK` marker at the console while keeping other INFO/WARN events:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <MarkerFilter marker="HEALTHCHECK"
                          onMatch="DENY"
                          onMismatch="NEUTRAL"/>
            <PatternLayout pattern="%p %c - %m%n"/>
        </Console>
    </Appenders>

    <Loggers>
        <Root level="INFO">
            <AppenderRef ref="CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
```

On the application side using the **Log4j 2 API**, mark the event:

```java
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.apache.logging.log4j.Marker;
import org.apache.logging.log4j.MarkerManager;

// Integration snippet; requires Log4j API/Core in the project.
Logger logger = LogManager.getLogger("com.example.health");
Marker health = MarkerManager.getMarker("HEALTHCHECK");

logger.info(health, "health_probe"); // Dropped at prod ConsoleAppender.
logger.info("order_created");        // Still accepted by ConsoleAppender.
logger.warn("order_failed");         // Still accepted by ConsoleAppender.
```

The code above is an **integration snippet**, not a standalone program runnable with the plain JDK. To select an external configuration when using Log4j Core:

```bash
java -Dlog4j2.configurationFile=config/log4j2-prod.xml -jar app.jar
```

In dev, you can use `log4j2-dev.xml` without the health-check `MarkerFilter` and set the level to DEBUG as needed.

**Point of caution:** an appender-level filter only affects that specific appender and does not automatically prevent events from reaching other appenders. Log4j 2 has filter layers globally, at the logger, at the appender reference, and at the appender. `ACCEPT` and `NEUTRAL` are not synonymous across all layers: especially at the global level, `ACCEPT` can let an event proceed while bypassing a level comparison at that tier. For "if it doesn't match, continue normal processing," use `NEUTRAL` as documented rather than blindly using `ACCEPT`.

## 9. Frameworks and Environment Selection Sources

### 9.1. Java SE, Maven, Gradle, Containers

In plain Java, you define `app.env` yourself or use an environment variable provided by your deployment system. For example:

```bash
java -Dapp.env=staging EnvironmentLogFilterDemo
```

`app.env` is a **custom property defined in this example**, not a property automatically understood by Logback or Log4j 2. To make a backend load a specific file, use the backend's own property (`logback.configurationFile` / `log4j2.configurationFile`) or a mechanism supported by your framework.

Use your deployment pipeline to supply configurations:
- Test environments send logs only to the test console or a mock sink.
- Staging sends logs to the staging collector, never using production credentials or endpoints.
- Production uses the production collector, retention, rate limits, and alerts according to policy.
- Environment variables and system properties should have an allowlist of valid values; log the loaded policy name or configuration version at application startup (without printing secrets).

Changing OS environment variables **after a process has started** typically does not cause the logger to reload its configuration automatically. Reloading or hot-updating only occurs if the specific backend/framework and configuration support it. Changing runtime levels in a live service requires access control, verification of effect, and a rollback mechanism.

### 9.2. Spring Boot (If the Project Uses Spring Boot)

Spring Boot can select `application-dev.properties`, `application-test.properties`, or `application-prod.properties` via active profiles. For example, **`application-prod.properties`**:

```properties
logging.level.root=WARN
logging.level.com.example.orders=INFO
```

This is **level-based filtering** via the Spring Environment. When you need marker/MDC or appender-specific filtering, you still need the appropriate backend configuration, such as `logback-spring.xml` or `logging.config` depending on your version. Spring Boot extensions are not available in plain Logback.

Do not confuse `spring.profiles.active` with `app.env` from the Java SE example—they are read by two different mechanisms. In a Boot application, avoid arbitrarily mixing multiple configuration styles without understanding the precedence between profiles, properties, backend files, and configurations loaded by the framework at startup.

## 10. Filtering, Asynchronous Logging, and Performance

When using async loggers or async appenders, the timing of filtering affects both cost and log observability:

```text
Application thread
   |
   +-- early level / filter --> drop event: usually avoids creation/copy/enqueue
   |
   +-- create event --> async queue --> worker --> appender filter --> sink
                                                  |
                                                  +--> may drop event after enqueue
```

This is a **conceptual diagram**; actual backends may place certain filters before or after the queue. If you only filter at the final appender, the event has already consumed CPU/heap and may have occupied queue space even though it is ultimately discarded.

Therefore:
- **Optimize at the entry point:** disable DEBUG/TRACE early in environments that do not need them, and use parameterized or lazy logging to avoid unnecessary message evaluation.
- **Keep useful information:** if you need certain structured INFO logs in prod, do not blindly set root to WARN; target specific loggers/categories and markers instead.
- **Monitor full queues:** async logging may block, drop events, or fall back to synchronous logging depending on policy; environment filtering does not guarantee an enqueued log will reach the collector.
- **Count dropped events:** distinguish between intentional level/filter drops, sampling, full-queue drops, and I/O or collector failures. If the backend does not expose direct metrics, use proper instrumentation instead of counting console lines.
- **Evaluate the whole system:** measure requests/s, logs generated/accepted/written/dropped, appender latency, p95/p99 request latency, CPU, heap, and ingestion errors.

For example, when testing sampling to reduce health-check logs from 100 events/s to 1 event/s, confirm that your metrics system still tracks service health; do not erase the signals needed to detect outages.

## 11. Testing the Environment Filter Matrix

A filtering policy should have **automated tests** for every environment rather than relying solely on manual console inspection.

### 11.1. Expected Matrix from the JUL Example

| Environment | `debug_cache` | `order_created` | `health_probe` | `order_failed` |
| --- | --- | --- | --- | --- |
| dev | Yes | Yes | Yes | Yes |
| test | No | Yes | Yes | Yes |
| staging | No | Yes | No | Yes |
| prod | No | No | No | Yes |

With the Java file in Section 5, you can run the four commands and verify the exact output for each case. Also test omitting `app.env` and passing an unknown value to verify the `prod` fallback or fail-fast behavior by design.

### 11.2. Event-Level and Backend-Level Checks

Good unit tests should assert on the collected **LogRecord/ILoggingEvent/LogEvent** objects or their markers/levels, rather than comparing full formatted log lines containing variable timestamps or thread IDs.

Examples of meaningful checks:
1. Prod drops `health_probe` but keeps `order_failed` without losing stack traces.
2. An INFO event in a dedicated logger still reaches the appropriate sink when required by policy.
3. A filter attached to the console does not drop events destined for a separate audit sink.
4. Switching environments actually loads the right configuration from the test/deployment runtime.
5. When using async logging, tests wait for the worker to drain or for the event to appear with a timeout; never use a fixed `Thread.sleep` and assume logs have flushed.

Avoid letting parallel tests mutate the root level, global appenders, or system properties without restoring them. If you need to test startup configuration loading, run each environment in a separate JVM so results do not depend on test execution order.

### 11.3. Operational Behavior Checks

Beyond unit tests, run an integration test with real logging:
- Emit events at the same level with different markers and verify the filter drops only the intended event type.
- Throw an exception with a stack trace and confirm the event still reaches the appropriate sink in prod.
- Send logs to the staging collector and verify there is no leakage of production endpoints or credentials.
- Run under high load; observe throughput, queue depth, sampling, and drop rates.
- Shut down the application gracefully, verifying flush/drain behavior according to backend capabilities—never assume durability simply because a logger method returned.

## 12. Security and Audit Requirements

**Environment-based filtering is not a safeguard against leaking sensitive data.** Sensitive values may already have been formatted into strings, stored in an event, routed to another appender, or sent down a pipeline before your intended filter blocks them.

Safer practices:
- Never log passwords, tokens, session cookies, API keys, payment details, or sensitive payloads.
- Standardize redaction/masking and use synthetic data in tests. Review exception logging paths because stack traces can sometimes expose internal details.
- Separate mandatory audit logs from regular DEBUG/INFO logs; only apply sampling or dropping if business policy explicitly permits it.
- Never allow clients to dictate the environment, global debug levels, or collector targets.
- Restrict configuration edit permissions and enable change auditing for level/filter modifications in production.
- Never let test/staging configurations accidentally point to real production destinations or credentials.

A dropped log event can erase the trail to an incident's root cause; for security and audit events, design a pipeline with appropriate reliability rather than relying solely on an in-memory queue or a single INFO log line.

## 13. Common Pitfalls and Troubleshooting

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Prod still prints DEBUG | Wrong file loaded, override enabled, or a different backend is active | Check config path/backend/profile and effective logger level |
| Staging drops even WARN | Filter returns DENY too broadly, wrong threshold, or overlapping logger/appender configs | Inspect each tier; test one WARN and one INFO separately |
| Handler filter allows INFO, but no INFO appears | Logger already dropped the event by level upstream | Lower the logger threshold appropriately, then check handler level/filter |
| Single event appears twice | Multiple appenders/handlers attached, additivity, or a logging bridge | Trace the routing path and parent references |
| Dropping health-checks also drops business events | Using `contains("health")` on free-form message strings | Use stable markers or event codes instead of keywords |
| Tests pass locally but fail in CI | Wrong env selected, different system properties, shared root state, undrained async | Use explicit test configs, isolated JVMs, and bounded waits |
| Environment changed, but logs remain the same | Backend initialized before property was set, or auto-reload is not enabled | Supply config early, restart, or use a supported reconfiguration mechanism |
| Enabling DEBUG in prod spikes latency | Too many events created/formatted; appender/queue cannot keep up | Limit DEBUG scope and duration; monitor throughput and drops |
| Logger is INFO, but console shows nothing | Appender ThresholdFilter/Filter rejects INFO, or logger additivity is off | Check both the logger and the target destination |
| "No logs seen" interpreted as "event never happened" | Log may have been filtered, sampled, or dropped asynchronously | Cross-check with traces, metrics, and event sources |

**Effective investigation steps:** identify the active backend/provider; read the effective environment/profile; confirm which config file was loaded; check logger levels first; check filters and appenders/sinks next; finally inspect async queues, collectors, and retention. Only raise DEBUG for the exact package or scope needed.

## 14. Practice Exercises

1. Run `EnvironmentLogFilterDemo` on `dev`, `test`, `staging`, and `prod`. Explain why FINE only appears in dev and why health-check is absent in staging.
2. Change the prod policy to INFO while still dropping `health_probe`. Update `minimumLevel` and verify the output while keeping `allowEvent` unchanged.
3. Add a high-frequency `db_ping` event type. Design a stable event code and per-environment policy without filtering on a word that might appear in other business messages.
4. In a Logback project, configure a `ConsoleAppender` accepting WARN and above and a test destination accepting INFO. Verify that an appender filter only affects its own destination.
5. In Log4j 2, attach a `HEALTHCHECK` marker, switch between `log4j2-prod.xml` and `log4j2-dev.xml`, and compare event counts by level and marker.
6. Write tests for an invalid environment and a missing environment. Verify that the application rejects invalid configs or falls back to the defined safe default.
7. Test async logging under burst traffic; verify that early-filtered logs do not enter the queue and measure filter-dropped events separately from queue-full drops.

## 15. Key Takeaways

- **Environment** determines the observability policy; **level** controls verbosity; **event filters/markers** distinguish event types at the same level; **appender filters** control which destinations receive them.
- Early filtering is generally cheaper than late filtering, especially with async queues.
- Configuration should live at runtime/deployment, validate against allowed values, be tested across an environment matrix, and have a rollback plan.
- Never let log filtering strip away critical error traces, audit records, or essential production observability data.
- Know your exact logging backend (JUL, Logback, or Log4j 2) before applying configuration files. Spring Boot's profile mechanism is a separate layer.

### References

- Oracle Java SE 21 — `java.util.logging.Filter`: https://docs.oracle.com/en/java/javase/21/docs/api/java.logging/java/util/logging/Filter.html
- Oracle Java SE 21 — `java.util.logging.Logger`: https://docs.oracle.com/en/java/javase/21/docs/api/java.logging/java/util/logging/Logger.html
- Logback — *Filters*: https://logback.qos.ch/manual/filters.html
- Logback — *Configuration*: https://logback.qos.ch/manual/configuration.html
- Apache Log4j 2 — *Filters*: https://logging.apache.org/log4j/2.x/manual/filters.html
- Apache Log4j 2 — *Configuration*: https://logging.apache.org/log4j/2.x/manual/configuration.html
- Spring Boot — *Logging*: https://docs.spring.io/spring-boot/reference/features/logging.html
