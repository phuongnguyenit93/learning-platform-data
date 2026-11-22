# Profile Logging in Java: Environment-Based Log Configuration

## 1. What is Profile Logging?

**Profile logging** is the practice of selecting a logging configuration based on the application's **runtime environment** or operating mode: `dev`, `test`, `staging`, `prod`. Each environment has different goals, so verbosity levels, formatting, log destinations, and retention policies may differ.

For example, during development, developers need `DEBUG` information to troubleshoot issues; in production, storing all `DEBUG` logs can generate huge volumes of data, consume excessive resources, and inadvertently expose sensitive information. In automated tests, logs should be sufficient to diagnose test failures while avoiding cluttering test results with background noise.

```text
                 Same code calling the logger
                 log.debug(...)
                 log.info(...)
                 log.warn(...)
                         |
                         v
                 Select active profile
                 /        |        \
                /         |         \
             dev         test       prod
         DEBUG+INFO     WARN/INFO   INFO+WARN
      readable console compact console stdout/collector
```

Important distinctions:

- **Profile** is the name of an active configuration set. Java SE and SLF4J do not natively define `dev/test/prod` profiles; that is either an application convention or a capability provided by a framework such as Spring Boot.
- **Log level** is the threshold used by a logger to decide whether to create/emit an event. The more verbose the threshold, the larger the potential log volume.
- **Appender/handler** determines whether logs are sent to the console, a file, or a collection system; **encoder/formatter** determines whether the output is plain text or structured data.
- **MDC/correlation ID** describes the context of a specific request/task; it can appear in any profile, but it is not the profile itself.
- **Environment variables, system properties, configuration files, and command-line arguments** are mechanisms for supplying configuration values to a program. Do not confuse the "profile name" with "where the configuration is placed."

The primary goal of profile logging is **one codebase, multiple environment-appropriate ways of observing it**, while keeping security rules, event identifiers, and logger names consistent.

## 2. Designing a Logging Policy per Environment

A starting policy might look like this:

| Environment | Recommended Level | Output | Purpose | Recommended Guardrails |
| --- | --- | --- | --- | --- |
| `dev` | `DEBUG` for application code, `INFO` for common libraries | Readable console with class/thread names | Trace execution flow and debug issues | Never log secrets, even on a local machine |
| `test` | `INFO` or `WARN` depending on test purpose | Console or a test-specific log capture | Diagnose test failures, keep CI readable | Limit repetitive logs, isolate logs between tests |
| `staging` | Similar to `prod`, with short-term verbosity if needed | Console/collector like production | Verify configuration, performance, integration, and operations | Revert temporary level changes once investigation ends |
| `prod` | `INFO` for operational events, `WARN`/`ERROR` for anomalies | Console with a collector or centralized sink | Operations, alerting, incident tracing | Mask sensitive data, limit log volume and retention |

These are **recommendations**, not mandatory standards. `INFO` may be too noisy for certain libraries, while `DEBUG` may need to be enabled for a limited time during a production investigation. Adjust according to your product and your log pipeline's capacity.

### Common Levels

In the SLF4J/Logback ecosystem, the verbosity order is typically:

```text
TRACE  ->  DEBUG  ->  INFO  ->  WARN  ->  ERROR
most verbose                         most severe
```

A logger set to `INFO` typically passes `INFO`, `WARN`, and `ERROR`, and does not emit `DEBUG` or `TRACE`. A logger set to `DEBUG` additionally allows `DEBUG`. `java.util.logging` (JUL) has different level ordering and names: `FINE` typically corresponds to diagnostic needs close to `DEBUG`, while `INFO` and `WARNING` correspond to levels with similar meanings.

You also need to consider filtering at the **handler/appender** level: a logger allowing an event does not mean every sink will record it. Filters, appender thresholds, sampling, and async discard policies can still drop or reroute the event afterward.

### Configuration Design Principles

1. Set a safe default level, typically `INFO`; increase verbosity selectively by scope—such as the `com.example.payment` package—rather than enabling `DEBUG` for the entire framework.
2. Keep logger names, field names such as `requestId` and `traceId`, and event structure rules consistent across environments so log queries remain uniform.
3. Differentiate clearly on **verbosity and destination**, avoiding letting a profile change the business meaning of a log message.
4. Production configurations lean toward structured logging, often writing to stdout for a container/platform log collector; only claim logs are JSON when a proper JSON encoder is configured and verified.
5. Treat retention policies, access control, and sensitive data handling as part of logging—not just a single `logging.level` line.

## 3. Standalone Java 17 Example with java.util.logging

Java SE has no built-in active profile concept. An application can define a system property, such as `app.profile`, and select the corresponding `java.util.logging` configuration.

The example below **requires no Maven or external libraries**. It uses `java.util.logging.Logger`, `ConsoleHandler`, and `Formatter` to demonstrate how log thresholds change across `dev`, `test`, and `prod`.

Create `ProfileLoggingDemo.java`:

```java
import java.util.Locale;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ProfileLoggingDemo {
    public static void main(String[] args) {
        String profile = System.getProperty("app.profile", "prod")
                .trim()
                .toLowerCase(Locale.ROOT);

        Level minimumLevel = switch (profile) {
            case "dev" -> Level.FINE;
            case "test" -> Level.WARNING;
            case "prod" -> Level.INFO;
            default -> throw new IllegalArgumentException(
                    "Unsupported logging profile: " + profile);
        };

        Logger logger = Logger.getLogger("example.profile");
        logger.setUseParentHandlers(false);
        logger.setLevel(minimumLevel);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.ALL);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " " + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        logger.addHandler(console);

        try {
            logger.fine("Loading local options");
            logger.info("Service ready");
            logger.warning("Retry scheduled");
        } finally {
            logger.removeHandler(console);
            console.close();
        }
    }
}
```

Compile:

```bash
javac ProfileLoggingDemo.java
```

Run each command:

```bash
java -Dapp.profile=dev ProfileLoggingDemo
java -Dapp.profile=test ProfileLoggingDemo
java -Dapp.profile=prod ProfileLoggingDemo
```

Output **on the console (stderr)** when running **each command individually**:

```text
# dev
FINE Loading local options
INFO Service ready
WARNING Retry scheduled

# test
WARNING Retry scheduled

# prod
INFO Service ready
WARNING Retry scheduled
```

The `# dev`, `# test`, and `# prod` markers are only labels separating the three runs in this document, not output printed by the program. `ConsoleHandler` writes to `System.err` by default; do not describe this output as stdout. The messages and order of the three log calls in each run are deterministic because the example executes sequentially on a single thread.

Explanation of design choices:

- `System.getProperty("app.profile", "prod")` defaults to `prod` if the caller does not pass a value; this is an **example-specific choice**, not default Java SE behavior.
- `Locale.ROOT` normalizes the profile name consistently regardless of the machine's language/locale.
- The `switch` rejects unsupported values. This prevents typos in a profile name from silently enabling an overly verbose logging configuration.
- `logger.setLevel(minimumLevel)` sets the threshold at the logger; `console.setLevel(Level.ALL)` lets the handler accept every event that passed the logger threshold.
- `setUseParentHandlers(false)` prevents events from being logged twice through parent logger handlers.
- `finally` removes and closes the handler created specifically for the example. Real applications should initialize logging once at bootstrap and manage handler lifecycles through proper configuration.

In a large application, you should not duplicate dozens of `switch(profile)` blocks. Read configuration centrally and pass the same policy to the logging system. In a Spring Boot project with SLF4J/Logback, Spring's profile mechanism handles this for you.

## 4. Spring Boot: Configuring Log Levels with application-<profile>.yml

Spring Boot supports profiles and multi-source configuration. For simple logging needs, `application.yml` and `application-{profile}.yml` files are sufficient in most cases; you do not immediately need a separate Logback configuration file.

Assume a project with the application package `com.example`.

`src/main/resources/application.yml` — default:

```yaml
spring:
  application:
    name: example-service

logging:
  level:
    root: INFO
    com.example: INFO
```

`src/main/resources/application-dev.yml` — more detail in application code:

```yaml
logging:
  level:
    root: INFO
    com.example: DEBUG
```

`src/main/resources/application-test.yml` — keeps CI output concise while still allowing application logs:

```yaml
logging:
  level:
    root: WARN
    com.example: INFO
```

`src/main/resources/application-prod.yml` — keeps log levels suitable for production operations:

```yaml
logging:
  level:
    root: INFO
    com.example: INFO
    org.springframework: WARN
```

How this works:

- `logging.level.root` is the threshold for the root logger. Specific loggers such as `com.example` can be given different thresholds.
- Child loggers under `com.example` inherit the configured level of the nearest parent logger in the logger hierarchy unless a more specific configuration exists.
- Values in `application-{profile}.yml` override **matching keys** from the shared configuration when that profile is activated, according to Spring Boot's configuration source precedence rules.
- `com.example` is only an example; replace it with your actual package. Enabling `DEBUG` for the application package is usually far less expensive than enabling `DEBUG` for `root`.
- If the project also configures levels via another mechanism, environment variables, or command-line flags, you must understand the precedence order to determine the effective value. Do not look at a single YAML file in isolation and assume it reflects the running level.

### Activating a Profile Externally

With a packaged Spring Boot JAR, for example:

```bash
java -jar example-service.jar --spring.profiles.active=dev
java -jar example-service.jar --spring.profiles.active=test
java -jar example-service.jar --spring.profiles.active=prod
```

Or on a POSIX shell:

```bash
SPRING_PROFILES_ACTIVE=prod java -jar example-service.jar
```

If using PowerShell, you can set the environment variable for the terminal session before running:

```powershell
$env:SPRING_PROFILES_ACTIVE = "prod"
java -jar example-service.jar
```

The commands above assume **an existing Spring Boot application**, not the standalone `ProfileLoggingDemo.java` example from the previous section.

Important note: `spring.profiles.active=prod` activates the **entire application configuration** for the `prod` profile (databases, endpoints, feature flags if any), not just logging settings. Therefore, do not enable the production profile on a local machine just to inspect log formatting unless you understand which dependencies and environments it will connect to.

Do not place `spring.profiles.active` inside `application-prod.yml` itself or inside a profile-specific YAML document to "self-activate" a profile. Select the active profile from valid shared configuration or from the deployment environment. When multiple profiles are active simultaneously, check the override rules and avoid combining conflicting profiles.

## 5. When Appenders or Formats Differ: logback-spring.xml

`logging.level.*` is enough to change logger thresholds. If `dev` needs a shorter pattern, `prod` needs a correlation ID, or each environment requires different appenders, Spring Boot with **Logback** can use `logback-spring.xml` and the `<springProfile>` element.

This is a **complete/alternative configuration approach** to the simple YAML level configuration above. Do not set conflicting logger/root levels in both YAML and XML at the same time; assign clear ownership for each setting.

Example `src/main/resources/logback-spring.xml` (only for Spring Boot + Logback):

```xml
<configuration>
    <springProfile name="dev">
        <appender name="DEV_CONSOLE"
                  class="ch.qos.logback.core.ConsoleAppender">
            <encoder>
                <pattern>%d{HH:mm:ss.SSS} %-5level [%thread] %logger{36} - %msg%n</pattern>
            </encoder>
        </appender>
        <logger name="com.example" level="DEBUG"/>
        <root level="INFO">
            <appender-ref ref="DEV_CONSOLE"/>
        </root>
    </springProfile>

    <springProfile name="test">
        <appender name="TEST_CONSOLE"
                  class="ch.qos.logback.core.ConsoleAppender">
            <encoder>
                <pattern>%-5level %logger{36} - %msg%n</pattern>
            </encoder>
        </appender>
        <logger name="com.example" level="INFO"/>
        <root level="WARN">
            <appender-ref ref="TEST_CONSOLE"/>
        </root>
    </springProfile>

    <springProfile name="prod">
        <appender name="PROD_CONSOLE"
                  class="ch.qos.logback.core.ConsoleAppender">
            <encoder>
                <pattern>%d{ISO8601} %-5level requestId=%X{requestId} %logger{36} - %msg%n</pattern>
            </encoder>
        </appender>
        <logger name="com.example" level="INFO"/>
        <root level="INFO">
            <appender-ref ref="PROD_CONSOLE"/>
        </root>
    </springProfile>

    <springProfile name="!dev &amp; !test &amp; !prod">
        <appender name="DEFAULT_CONSOLE"
                  class="ch.qos.logback.core.ConsoleAppender">
            <encoder>
                <pattern>%d{ISO8601} %-5level %logger{36} - %msg%n</pattern>
            </encoder>
        </appender>
        <root level="INFO">
            <appender-ref ref="DEFAULT_CONSOLE"/>
        </root>
    </springProfile>
</configuration>
```

**How to read this configuration:**

1. `<springProfile name="dev">` is applied only when the `dev` profile is active. `test` and `prod` work the same way.
2. In `dev`, application code under `com.example` allows `DEBUG`, while root is `INFO`. Libraries without an explicit level configuration inherit the nearest threshold in the logger hierarchy.
3. In `prod`, `%X{requestId}` inserts the MDC value for the current log event. If that key is absent, the field may be empty. **Adding `requestId` to the pattern does not automatically propagate context across threads or services.**
4. The profile expression `!dev &amp; !test &amp; !prod` provides an `INFO` console configuration when none of the three listed profiles are active. `&amp;` is the required XML escape for `&` in an attribute.
5. These patterns still produce **plain-text logs**, not JSON. To emit JSON logs, you need an encoder/layout that supports JSON formatting, and you must verify the actual events at the collector.
6. The example assumes **only one of the `dev/test/prod` profiles is active at a time**. If both `dev` and `prod` are active, both blocks can contribute loggers, root settings, and appenders, and behavior will no longer follow a single policy. Define deployment profiles clearly or use exclusion expressions for environment groups.

The filename **`logback-spring.xml`** matters: the `springProfile` element is a Spring Boot extension to Logback, not standard Logback syntax. Do not use it in a plain `logback.xml` and expect Spring to process it; also avoid enabling Logback's `scan="true"` auto-reload alongside Spring extension tags, because Logback's default reconfiguration mechanism does not understand those tags. When using Log4j2 or JUL, use their corresponding APIs and configurations; `springProfile` here does not apply verbatim to every backend.

### Choosing Console, File, or Collector Output

- **Container/Kubernetes:** writing to stdout/stderr generally enables centralized platform collection. Ensure the collector captures timestamp, service name, environment, and correlation ID.
- **Running as a VM process:** a rolling file appender can be used if the infrastructure requires it; paths, size limits, and retention must align with OS file permissions.
- **Production with structured logging:** choose a supported JSON encoder, standardize keys such as `timestamp`, `level`, `logger`, `message`, and `traceId`, and verify the index/ingest pipeline as well as any fields that might contain sensitive data.
- **Automated tests:** typically use console or an in-memory/temporary file appender, avoiding calls to external logging services when only testing application logic.

Do not assume that `logger.info(...)` returning means the log has been durably written if the backend uses an async appender or buffering; in tests, include an appropriate wait, flush, or shutdown step for the implementation.

## 6. Which Configuration Takes Effect at Startup?

A very common mistake is editing the right file but running the wrong profile, or having a level overridden by another configuration source. To diagnose this, distinguish between the **active profile** and the **effective level of the logger**.

In Spring Boot, example sources that can contribute values include:

```text
application.yml                 -> shared configuration
application-dev.yml             -> keys applied when dev is active
environment / system property   -> configuration provided by the environment
command-line arguments          -> e.g. --logging.level.com.example=DEBUG
logging backend configuration   -> appenders, filters, encoders, and possibly levels
                     |
                     v
       Effective logger / appender at runtime
```

The order in the diagram illustrates **participating sources**, not an exhaustive precedence list for every situation. Spring Boot has its own configuration precedence rules, and the logging backend also has its own configuration. If a log level appears in multiple places, check the exact precedence order for the framework version in use rather than guessing from filenames.

Example of activating a profile and overriding a package level in a single run:

```bash
java -jar example-service.jar \
  --spring.profiles.active=prod \
  --logging.level.com.example.payment=DEBUG
```

The trailing backslash is line-continuation syntax for POSIX shells; on Windows, put the command on a single line or use your shell's line-continuation syntax. Only enable `DEBUG` with a deliberate scope and time limit: this change can increase log volume for production requests.

### Ways to Verify Without Guessing

1. **Confirm the active profile** from deployment configuration, startup logs, or `Environment.getActiveProfiles()` in Spring Boot (when the application exposes this information).
2. **Check the effective level** of the specific logger after the logging system initializes; do not look only at `logging.level.root` if a package/class has its own level.
3. **Emit a non-sensitive probe event** at the expected level, locate it in the intended sink/collector, and verify the basic fields. Never use tokens, passwords, or customer data as "test data."
4. **Inspect filters/appenders** when an event does not appear even though the logger level allows it; with async queues, check whether the event has been processed.
5. **Compare startup logs** against the actual config inside the image/JAR and environment sources; editing a local file has no effect if the deployed artifact does not contain the new version.

If the application enables the Spring Boot Actuator endpoint `/actuator/loggers` and grants access to it, that endpoint can inspect or change logger levels at runtime according to its access-control configuration. This feature requires strict access control; it does not replace long-term profile and configuration management, and dynamic changes may be lost on restart.

## 7. Testing Profile Logging

Testing should cover two aspects: **selecting the right profile/configuration** and **verifying that events are actually written to the right destination**.

### 7.1. Test Matrix

| Scenario | Expectation |
| --- | --- |
| `dev`; application package `DEBUG` | `DEBUG` logs from application code appear on the console |
| `test`; root `WARN` and application package `INFO` | Application `DEBUG` is filtered, application `INFO` appears; root library `INFO` logs may be filtered |
| `prod`; root `INFO` | Appropriate `INFO/WARN/ERROR` events appear; `DEBUG` does not appear unless overridden |
| No profile specified; safe fallback config | Verbose levels are not enabled unintentionally |
| Unsupported profile in the Java SE example | Fails fast with a misconfiguration error |
| With correlation ID | Pattern picks up the MDC field without leaking secrets |
| Running in a container | Collector actually receives logs and parses the agreed format |
| Runtime level switch or override | Effective level changes for the intended scope; restoration procedure is known |

With Spring Boot, you can use `@ActiveProfiles("test")` in integration tests to activate a profile. A test that only reads `Environment.getActiveProfiles()` proves **the profile is active**, not that the pattern and appenders are correct. To verify logging, check the effective level or capture events from an appropriate sink.

### 7.2. Example Level Check in a Spring Boot + Logback Project

The following is an **integration test snippet for a Spring Boot project that already has an application class and the `spring-boot-starter-test` dependency**; it is not a standalone Java file that can run outside a project.

```java
import ch.qos.logback.classic.Level;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@ActiveProfiles("test")
class LoggingProfileIntegrationTest {
    @Test
    void applicationLoggerUsesInfoLevel() {
        ch.qos.logback.classic.Logger logger =
                (ch.qos.logback.classic.Logger)
                        LoggerFactory.getLogger("com.example.OrderService");

        assertEquals(Level.INFO, logger.getEffectiveLevel());
    }
}
```

This test expects the `com.example` package to be set to `INFO` in `application-test.yml` or in the `test` profile of `logback-spring.xml`. If the application uses a backend other than Logback, do not cast to `ch.qos.logback.classic.Logger`; use the corresponding configuration inspection API. Because the test involves **application-wide** logging configuration, avoid running multiple tests that mutate the root logger in parallel without context isolation.

To verify log content, attach a dedicated test appender to a named logger or use the framework's log-capture utility. With async logging, wait for the event using a signal/collector with a timeout before asserting; avoid arbitrary `Thread.sleep(...)` calls.

### 7.3. Testing Against Sensitive Data Leakage

A useful negative test is to send a mock request containing a distinctive synthetic token/PII string defined by the test, run the logging code, and assert that the string does **not** appear in the captured output. Combine this with reviewing log statements and masking/redaction rules: relying solely on the `prod` profile with `INFO` **does not guarantee** that sensitive data will never be written to an `INFO` log.

## 8. Common Pitfalls and Troubleshooting

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `dev` selected but no `DEBUG` logs appear | Level configured on another root/package, appender filter, or profile not active | Check active profile and effective level of the specific logger, then check appenders |
| Heavy `DEBUG` volume in production | Leftover CLI/env override, conflicting XML and YAML, or multiple active profiles | Trace the source of the effective value; remove overrides and scope diagnostics narrowly |
| Logs appear twice | Appender attached to both child logger and root with `additivity=true` | Inspect logger hierarchy and `appender-ref`; set `additivity=false` when truly needed |
| Application ignores `<springProfile>` | Plain Logback filename, wrong filename, or incompatible scan setting | Use `logback-spring.xml` in Spring Boot and inspect startup diagnostics |
| Production format is hard to parse | Plain-text pattern used when collector expects JSON | Configure a version-compatible JSON encoder/structured logging and test ingest end-to-end |
| Log file does not appear | Missing path permissions, nonexistent directory, or appender config not active | Check startup appender errors, write permissions, and container policies |
| Missing logs from async tasks | Context not propagated, appender not drained, or overflow policy dropping events | Separate MDC propagation issues from event delivery; check worker, queue, filters, and flush |
| Flaky CI failures on log assertions | Another test mutates root logger or assertion runs before async sink receives event | Isolate logger/context, restore configuration, wait on a proper signal with timeout |
| Editing `application-prod.yml` has no effect | Different profile active, stale artifact, or higher-precedence config source | Inspect active profiles, config sources, and effective level at runtime |
| Local test hits production services | Using `spring.profiles.active=prod` just to check log output | Create an independently testable log config instead of carelessly enabling the full prod profile |

## 9. Operations and Security

Logging is part of system observability, so profiles must be paired with operational discipline:

- **Never log secrets** such as passwords, API keys, session tokens, cookies, access tokens, or connection strings containing credentials. Do not rely on "production disables DEBUG" for safety.
- **Keep correlation IDs consistent** across threads, processes, and services using proper context propagation. Use MDC and tracing frameworks correctly; a profile does not create or propagate trace IDs on its own.
- **Control volume:** enabling DEBUG, large stack traces, object `toString()` output, and request/response bodies can drive up CPU, I/O, storage, and ingest costs.
- **Access control and retention:** production logs can still contain sensitive information despite minimization efforts; restrict who can read them, how long they are retained, and where they are copied.
- **Use the same core log fields** across staging and production so dashboards and alerts do not require completely different queries.
- **Record temporary log level changes:** document the reason, package scope, start time, and who/what condition triggers restoration. For runtime changes, re-verify after a restart.
- **Do not swallow business errors with logging:** if an operation needs a retry, rollback, or error response, business code must still handle it; `ERROR` only records an observable event and does not perform error handling.
- **Be ready for different infrastructures:** developer machines can use rich console output, while production/containers must match actual collection, rotation, and monitoring mechanisms.

## 10. End-to-End Scenario

Suppose `OrderService` has three log statements:

```java
log.debug("Validated order fields for orderId={}", orderId);
log.info("Order accepted: orderId={}", orderId);
log.warn("Order validation retried: orderId={}", orderId);
```

This snippet is **illustrative inside an application with an initialized SLF4J logger**, not a standalone Java program. `orderId` should be an identifier already assessed as safe to log; do not arbitrarily log order contents or payment details.

With the example policy:

- **`dev`:** `com.example` logger set to `DEBUG`, showing all three events to help trace the request path.
- **`test`:** `com.example` logger set to `INFO`, showing only `INFO` and `WARN`; output from other libraries is reduced by root `WARN`.
- **`prod`:** `com.example` logger set to `INFO`, showing `INFO` and `WARN` without `DEBUG`; if the pattern includes `requestId`, logs also include that field when MDC is properly set.

During a production incident, operations can temporarily enable `DEBUG` for `com.example.order` via an approved configuration source or runtime tool, verify events reach the collector, and then restore `INFO`. Do not enable `DEBUG` on root or switch the entire active profile from `prod` to `dev`, as doing so can affect configuration outside logging.

## 11. Checklist Before Adopting Profile Logging in a Project

- [ ] Profile names and purposes (`dev`, `test`, `staging`, `prod`) are defined.
- [ ] Safe default levels, per-package override conventions, and ownership of each setting are clear.
- [ ] Log destinations match each environment (console, file, or collector) and formatting has been verified.
- [ ] Spring Boot uses `application-{profile}.yml` and, if needed, `logback-spring.xml` without conflicting configurations.
- [ ] Deployment environments explicitly set the active profile, and the effective profile is verified at startup.
- [ ] Profile logging is not confused with MDC, distributed tracing, or async log delivery.
- [ ] Tests cover log levels, actual emitted events, and no-secret policies; async tests wait properly on the sink.
- [ ] A procedure exists for temporary verbosity increases, volume monitoring, and configuration rollback.
- [ ] All production configuration changes are validated in staging or an equivalent environment before rollout, when appropriate.

**Key takeaway:** a single logger call can stay identical from local development to production; **profiles, levels, appenders, and encoders** decide which logs appear and where they go. A clean profile design improves diagnostics, reduces unnecessary log noise, and protects data without modifying code for every environment change.
