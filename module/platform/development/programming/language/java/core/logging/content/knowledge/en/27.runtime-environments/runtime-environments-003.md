# Staging Configuration for Java Core Logging

## Objectives

This lesson belongs to the **Runtime Environments** group, covering **Staging Configuration** in Java Core Logging. After completing it, you will be able to design and verify logging configurations for a staging environment, distinguish appropriate choices across development, staging, and production, enable controlled verbose logging, verify log flow from the JVM to the observability system, and prevent sensitive data leaks or log loss during deployment.

**Staging** is a pre-production testing environment that typically shares the same deployment architecture, logging framework, packaging, log structure, and log collection pipeline as production. Staging does not necessarily have the same scale or production data. The goal of staging logging is to detect configuration, integration, performance, and observability issues **before release**, while keeping noise, cost, and risk at reasonable levels.

An application's staging configuration should clearly answer:

1. Which logs are generated (log level, logger/package, filter)?
2. How are events represented (timestamp, level, service, environment, trace/correlation ID, message, exception)?
3. Where do logs go (stdout, file, collector, search system)?
4. What happens when the sink is slow or fails (backpressure, retry, drop, shutdown)?
5. Who can read the logs, how long are they retained, and what data must never be logged?
6. How do we prove the configuration is correct and causes no side effects under staging load?

## 1. How does staging differ from development and production?

| Criterion | Development | Staging | Production |
| --- | --- | --- | --- |
| Purpose | Debugging on a developer's machine | Validating releases, configuration, integration, and operability | Operating the live service |
| Reference default log level | `DEBUG` for the package under active work; `INFO` for the rest | `INFO` system-wide, temporary `DEBUG` for specific packages | `INFO` or `WARN` based on operational needs and volume |
| Format | Human-readable text may suffice | **As close to production as possible**, preferring structured logging if production uses JSON | Unified structured logging |
| Output | IDE console or local file | stdout/collector similar to production | stdout/collector or managed sink |
| Trace/correlation ID | Useful | Full propagation and indexing must be verified | Must operate reliably |
| Retention and access control | Local-only scope | Dedicated policy, restricted access, and bounded retention | Per product, operational, and legal requirements |
| Error details | Can be enabled during debugging | Selectively enabled, time-bounded, avoiding sensitive data | Strictly controlled |

These are **design guidelines**, not rigid rules of Java, SLF4J, or Spring Boot. Staging does not mean turning on `TRACE`/`DEBUG` for every package. Doing so creates excessive log volume, obscures critical errors, increases cost, and can alter performance characteristics compared to production.

Keep properties that directly affect testing quality consistent: JSON field names, timestamp format, MDC/tracing, stdout capture, exception formatting, appender behavior, size limits, and queue-full strategies. Intentional differences between staging and production must be documented and justified.

## 2. Designing configuration around the one-build, many-environments principle

The same JAR file should be able to run in staging and production with **different deployment configurations**, rather than rebuilding just to change a log level constant. Common configuration sources include:

- Application configuration files, such as `application.yml` and `application-staging.yml` for Spring Boot.
- Environment variables, JVM system properties, or command-line arguments provided by the deployment platform.
- Logging library configurations such as `logback-spring.xml`, `logback.xml`, or `log4j2.xml`.
- ConfigMaps, secret managers, and container/orchestrator runtime configurations.

**Separation of concerns**: profile files declare levels, endpoints, and policies; encoders/appenders define format and log destinations. Never embed passwords, access tokens, connection strings with credentials, or API keys in logging configuration files or log messages. Secrets should come from an approved secret management mechanism and must not be printed in startup logs.

Standardize a meaningful set of operational parameters, for example:

| Parameter | Role | Staging recommendation |
| --- | --- | --- |
| `APP_ENV` | Environment label recorded in logs | `staging` |
| `SPRING_PROFILES_ACTIVE` | Selects the Spring profile (if using Spring Boot) | `staging` |
| `spring.application.name` | Consistent service name across logs and metrics/traces | Example: `checkout-service` |
| `logging.level.root` | Baseline log level | `INFO` |
| `logging.level.com.example.checkout` | Detailed logging scoped to the investigation target | `DEBUG` when needed |
| Collector endpoint | Log destination path | Connects to staging observability; configured via deployment |
| Retention/access | Permissions and retention period | Dedicated staging policy, time-bounded |

When changing levels at runtime, understand the actual configuration precedence rules of your framework. In Spring Boot, command-line arguments, environment variables, and configuration files follow a defined precedence order, but you should not guess blindly when multiple sources share the same key. Verify the **effective value** using controlled configuration/diagnostics and observe actual log behavior, without dumping the entire environment or secrets to the console.

## 3. What should a standard staging log event contain?

A useful record for integration testing typically includes:

- **timestamp** with an explicit timezone and sufficient precision; standardize on UTC in the pipeline where appropriate.
- **level**: `ERROR`, `WARN`, `INFO`, `DEBUG`, or `TRACE`.
- **service**, **environment**, **version/release**, and instance/pod if provided by the infrastructure.
- **logger**, **thread**, or execution context when helpful.
- **trace_id**, **span_id**, or `correlation_id` if the task has a valid context.
- **event/message** that is concise and meaningful; error codes or statuses in separate fields if the system uses structured logging.
- **exception type/stack trace** according to log level and data-protection policies.

**Illustrative JSON** example (not Logback's default output):

```json
{
  "timestamp": "2026-11-10T02:30:14.123Z",
  "level": "WARN",
  "service": "checkout-service",
  "environment": "staging",
  "release": "2026.11.10-rc1",
  "logger": "com.example.checkout.PaymentClient",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "event": "payment-retry",
  "attempt": 2,
  "status": 503
}
```

The timestamp, release, service, and ID values in this example are **illustrative data**. In a real application, use a JSON encoder from your logging stack or a proper structured logging solution; do not simply wrap concatenated strings in JSON braces and assume it is safe. Strings, exceptions, and newline characters must be properly escaped.

**Distinguish fields from sensitive data:** Trace IDs/correlation IDs help correlate logs, not authenticate requests; never include bearer tokens, passwords, session cookies, Authorization headers, full request/response bodies, card numbers, or personal data in logs. Staging sometimes contains data from real integrations or sanitized/copied production-like data, so security policies still apply.

**Context fields do not appear automatically.** MDC only works when the application or instrumentation populates it with the right values. Adding `trace_id=%X{trace_id}` to a Logback pattern produces an empty field if there is no context injection. When using asynchronous tasks or thread pools, ensure proper propagation and restore/clear MDC to avoid leaking IDs across requests.

## 4. Spring Boot: configuring staging with Logback

This is a practical approach when an application uses **Spring Boot + SLF4J + Logback**. Configuration has two parts: selecting levels by profile, and defining output format/destination. The examples add no dependencies beyond the logging components included in the corresponding starter; projects using Log4j 2 or excluding Logback must use a different configuration.

### 4.1. `application-staging.yml` file

Located at `src/main/resources/application-staging.yml`:

```yaml
spring:
  config:
    activate:
      on-profile: staging

logging:
  level:
    root: INFO
    com.example.checkout: DEBUG
    org.springframework: INFO
```

Explanation:

- `spring.config.activate.on-profile: staging` restricts this configuration document to staging. Do not put `spring.profiles.active` inside a profile-specific file to self-activate it.
- `root: INFO` keeps overall log volume under control.
- `com.example.checkout: DEBUG` enables debug information only within the application namespace being observed. This is an **illustrative package**; replace it with your real service package, and avoid setting all of `org.springframework` or Hibernate to `DEBUG` by default.
- Other loggers follow appropriate inherited levels. If a subpackage declares a different explicit level, the effective level is determined by the logger hierarchy and runtime configuration.

Activate the profile when running:

```bash
APP_ENV=staging SPRING_PROFILES_ACTIVE=staging java -jar app.jar
```

The command above uses POSIX shell syntax (Linux/macOS). On Windows PowerShell:

```powershell
$env:APP_ENV = "staging"
$env:SPRING_PROFILES_ACTIVE = "staging"
java -jar app.jar
```

The name `app.jar` represents the deployed build artifact. Use a single deployment-controlled source for the active profile; when other configurations can override it, verify the actual active value. You do not need to rebuild the JAR every time you change a log level.

**Note:** `application-staging.yml` is a Spring Boot example. Plain Java SE does not automatically read that file; without Boot, you must configure the logging framework or initialization code directly.

### 4.2. `logback-spring.xml` file

Located at `src/main/resources/logback-spring.xml`:

```xml
<configuration>
    <springProperty scope="context"
                    name="APP_NAME"
                    source="spring.application.name"
                    defaultValue="java-service"/>

    <property name="ENV" value="${APP_ENV:-unknown}"/>

    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%d{ISO8601} level=%-5level env=${ENV} service=${APP_NAME} thread=%thread trace_id=%X{trace_id} span_id=%X{span_id} logger=%logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

In this example:

- `ConsoleAppender` writes to the console, fitting container models where the runtime/agent collects stdout. You still need to verify the pipeline to ensure logs are actually collected and searchable.
- `springProperty` reads the service name from the Spring Environment; it only works when loaded through Spring Boot's extension-aware mechanism, such as `logback-spring.xml`. Do not copy this tag verbatim into plain `logback.xml` and expect it to work.
- `APP_ENV` is provided by the deployment; if missing, the pattern writes `unknown` so environment-labeling errors stand out. Do not hard-code `env=staging` in a shared configuration used across all environments.
- `%X{trace_id}` and `%X{span_id}` read from MDC when the log event is created/captured. Whether they have values depends on application instrumentation.
- `%msg%n` outputs the message and a newline; in text logs, messages containing newlines can split one event across multiple lines. A structured JSON encoder makes the collection pipeline more reliable if production uses JSON.

Specific levels in `application-staging.yml` can be applied by Spring Boot on top of loggers; root `INFO` in the XML sets the baseline. If the application also uses `logging.config` or another logging library, verify the actual configuration path and avoid defining duplicate appenders that cause duplicated logs.

**Do not arbitrarily enable Logback's automatic config scanning** when using Spring Boot extensions in `logback-spring.xml`. If you need to change log levels at runtime, use a platform-supported configuration mechanism with clear permissions and auditing; avoid editing files inside a container without version control.

### 4.3. When structured JSON is needed

If production outputs JSON, staging should use the **same encoder/schema** to test parsing, queries, correlation, and dashboards; do not treat the text pattern example above as the final standard. Choose a JSON encoder compatible with your Spring Boot/Logback version, then verify the actual output including timestamp, level, service, env, trace fields, and exceptions.

Why schema checks matter: renaming `trace_id` to `traceId` or changing `status` from a string to a number can break queries, alerts, and dashboards even though logs are still written successfully. With JSON, each log event should ideally be a single JSON object on one line (JSON Lines), rather than multiple JSON fragments scattered across a stack trace.

## 5. Plain Java and other logging stacks

Not every Java application uses Spring Boot:

| Stack | Staging organization | What to verify |
| --- | --- | --- |
| **Java Util Logging (JUL)** | `logging.properties` or programmatic/JVM configuration | Logger/handler levels, filters, format, and handler output |
| **SLF4J + Logback** without Boot | `logback.xml` or an external configuration loaded at startup | Do not use `springProfile` or `springProperty` in plain Logback |
| **Log4j 2** | `log4j2.xml` or equivalent configuration | LoggerConfig, Appender, PatternLayout/JsonTemplateLayout, async mode |
| **Spring Boot** | `application-staging.yml` + appropriate logging configuration | Actual active profile, precedence, logging backend on classpath |

With **plain Logback**, you can load a dedicated staging configuration at startup if the file exists:

```bash
java -Dlogback.configurationFile=/opt/app/conf/logback-staging.xml -jar app.jar
```

This is an example path for a pre-deployed system; it is not a standalone command you can run without the JAR, libraries, and XML file. Avoid hard-coding developer machine paths in Docker images. Paths outside the image should be managed via deployment manifests or versioned mounts.

Do not unintentionally include multiple SLF4J backends at the same time. Running with a different logging backend than expected can prevent XML files from being read or produce unexpected log formatting. When investigating staging, check the logging framework's startup diagnostics and the build's dependency tree where accessible.

## 6. Standalone Java 17: simulating verbose staging logging

This example uses only **JDK 17+** and `java.util.logging` to demonstrate selecting a log level by environment, formatting an environment field, and writing logs to `stdout`. It does **not** execute the Spring Boot/Logback configuration from the previous section, and does not assume a JSON encoder or log collector.

Create `StagingLoggingDemo.java`:

```java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class StagingLoggingDemo {
    public static void main(String[] args) {
        String environment = System.getProperty("app.env", "staging");

        Logger logger = Logger.getLogger("demo.checkout");
        logger.setUseParentHandlers(false);
        logger.setLevel("staging".equals(environment)
                ? Level.FINE : Level.INFO);

        Handler stdout = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                return "env=" + environment
                        + " level=" + record.getLevel().getName()
                        + " event=" + record.getMessage()
                        + System.lineSeparator();
            }
        }) {
            @Override
            public synchronized void publish(LogRecord record) {
                super.publish(record);
                flush();
            }

            @Override
            public synchronized void close() {
                flush();
            }
        };

        stdout.setLevel(Level.ALL);
        logger.addHandler(stdout);
        try {
            logger.info("service-started");
            logger.fine("cache-check");
            logger.warning("retrying-downstream");
        } finally {
            logger.removeHandler(stdout);
            stdout.close();
        }
    }
}
```

Compile and run with defaults:

```bash
javac StagingLoggingDemo.java
java StagingLoggingDemo
```

Exact **stdout** for the default `app.env=staging`:

```text
env=staging level=INFO event=service-started
env=staging level=FINE event=cache-check
env=staging level=WARNING event=retrying-downstream
```

Run in another mode to observe verbose log suppression:

```bash
java -Dapp.env=production StagingLoggingDemo
```

**stdout** when using `app.env=production`:

```text
env=production level=INFO event=service-started
env=production level=WARNING event=retrying-downstream
```

Explanation:

1. The `demo.checkout` logger disables parent handlers to avoid duplicate output from the root logger. `StreamHandler(System.out, ...)` is configured to write to stdout and calls `flush()` after each event, keeping the example deterministic.
2. JUL uses `FINE` for a level more detailed than `INFO`; the level name in the output is `FINE`, **not** `DEBUG` as in SLF4J/Logback.
3. In staging, the logger level is `FINE`, so all three events are emitted; in production, `FINE` is filtered out. JUL's `WARNING` corresponds closely to `WARN` in many logging stacks.
4. The example logs literal events without user data purely for easy comparison. In production code, use a formatter/structured logger that handles escaping, sensitive data, and exceptions properly. Never concatenate untrusted input into text and call it safe JSON.
5. This is a single-JVM program with no concurrency, network collector, or real `AsyncAppender` overhead. Evaluating real staging logging requires testing with the actual stack and workload.

Try experimenting further: run `java -Dapp.env=staging StagingLoggingDemo` and `java -Dapp.env=test StagingLoggingDemo`. With `test`, `FINE` is hidden because the program only enables it when the environment equals `staging` exactly. Using exact string comparison avoids ambiguity around environment names.

## 7. Async logging in staging: testing performance and log loss

If production uses asynchronous logging, staging should test that exact queue/worker/sink mechanism. Async logging usually reduces how long the caller waits to log **while the queue still has capacity**, but it does not guarantee the event is durable at the destination when `logger.info(...)` returns.

Measure at least:

- **Caller latency** of log calls and their impact on endpoint p95/p99.
- **Queue occupancy**, high-water mark, enqueue blocking, and worker/sink throughput.
- **Dropped/discarded events**, retries, and writer/collector errors.
- **Event-to-searchable latency**: time from log generation until it can be queried in the centralized system.
- **Shutdown drain**: counts of emitted/received/written events and time taken by workers to process remaining events.

Queue-full policies can include blocking, dropping, discarding lower log levels, or synchronous fallback depending on the logging stack. Settings that reduce blocking can increase log loss; settings that prevent drops can slow down requests when the sink is congested. **Do not evaluate async logging solely by producer throughput**; a benchmark that emits logs quickly while dropping most events is unreliable.

Tests should cover steady load, heavy log bursts, slow filesystem/stdout, unreachable collectors, and graceful shutdown. For audit logs requiring durability guarantees, an in-memory queue is no substitute for a durable storage path with its own policy.

## 8. Sensitive data and staging access control

By default, treat staging as an environment that may contain data requiring protection:

- Never log passwords, API keys, OAuth tokens, session cookies, Authorization headers, verification codes, payment details, or full request bodies.
- When you need to observe a request, prefer **request ID/trace ID** and event codes; store personal data only when permitted, minimized, and with testable masking/redaction.
- Also check **exception messages**, stack traces, and HTTP client interceptors: libraries sometimes print URLs with query tokens, headers, or payloads even when business code does not log them directly.
- Apply access controls, retention, data partitioning, and transport encryption aligned with staging policy. Do not automatically route staging logs into production indexes or vice versa.
- For temporary `DEBUG` levels, specify the package scope, start/end times, owner, and how to verify it has been turned off. Avoid letting verbose logging linger and become the default.

**Redaction should happen before logs leave the application or at a controlled pipeline stage**, and must be tested with representative structured test data. Relying on "nobody reads staging logs" is not enough, because logs can still be copied, forwarded, or retained long-term.

## 9. Staging configuration verification workflow

Run checks after every configuration or logging dependency change. The goal is to verify **effective runtime values**, not just inspect YAML/XML files:

| Check | How to test | Expected result |
| --- | --- | --- |
| Profile | Start the same image with `SPRING_PROFILES_ACTIVE=staging`, verify via behavior/safe diagnostics | Staging config is active and not overridden by another source |
| Default level | Emit `INFO`/`WARN` and `DEBUG` from a package without verbose logging | `INFO`/`WARN` appear; out-of-scope `DEBUG` is filtered out |
| Specific level | Emit `DEBUG` from the configured package | Debug logs for that package appear; no flood from underlying libraries |
| Log fields | Emit a sample event with release/service/environment | Timestamp, level, service, env, and valid schema are present |
| Trace/MDC | Send a request across two services and async processing | Trace ID is consistent within the trace; no ID leakage across requests |
| Exception | Trigger a known test error | Event includes useful error type and stack trace, with no leaked secrets |
| Collector | Query a unique test event ID in the backend | Event is received and searchable within the expected timeframe |
| Overload | Generate a burst exceeding sink capacity | Queue metrics and block/drop behavior follow policy; no silent log loss |
| Shutdown | Stop the service gracefully | Appender/worker has a chance to flush; any loss limits are recorded |
| Security | Send a payload containing fake tokens and simulated sensitive data | No raw tokens/PII appear in output, collector, or index |

Send a **test event with a unique ID**, then trace it end to end: application emits → console/file contains event → agent/collector ingests → backend indexes → query/dashboard displays it. Distinguish between the application-generated timestamp and the time the backend makes it searchable. If logs appear on the console but not in the dashboard, the issue may lie in the agent, parser, transport, index mapping, retention, or access permissions.

When testing trace or debug levels, choose safe test requests/data and keep emission rates bounded so you do not accidentally generate millions of lines. In containers, verify stdout/stderr are collected properly and log lines are not truncated due to size limits.

### Pre-release smoke test

1. Deploy the exact release candidate build to staging; verify service name, `env=staging`, and release tag are attached correctly.
2. Trigger one successful request and one controlled error; verify level, message, exception, and correlation.
3. Emit logs from a `DEBUG`-enabled package and from a non-enabled package; confirm filtering works.
4. Query the event in the log backend; check ingestion/indexing latency and field formatting.
5. Send dummy data shaped like secrets to prove masking works; never use real credentials for testing.
6. Check metrics for log volume, dropped events, and endpoint latency during bursts.
7. Restore levels for packages whose verbosity was raised once the investigation ends; record the deployed config version and rollback plan.

## 10. Common staging configuration mistakes

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Staging only prints `INFO` despite `DEBUG` in YAML | Profile not active, wrong logger name, or higher-precedence config source | Verify active profile, effective level, and actual package name |
| Config uses `springProfile` but fails at startup | Using plain Logback or `logback.xml` without Spring extension support | Use `logback-spring.xml` in Spring Boot or plain Logback syntax |
| Same event appears twice | Two appenders attached to the same sink, additivity, or misconfigured parent handler | Check logger hierarchy and appender references |
| `trace_id` is always empty | Missing MDC/trace context injection or async processing drops context | Check instrumentation, propagation, and scopes |
| Logs appear on console but not in backend | Collector not shipping, or parser/index/drop/permission failure | Trace each pipeline stage using a test event ID |
| Staging logs are labeled as production | Wrong environment variable, hard-coded field, or profile override | Use standardized env vars and verify actual output |
| Backend fails to parse JSON | Text pattern looks like JSON but escapes incorrectly or schema changed | Use a compatible JSON encoder; validate parser with test payloads |
| Excessive logs, endpoint p99 increases | System-wide DEBUG, huge stack traces, slow sink, or full queue | Scope loggers, reduce payload size, measure queue/sink, tune policy |
| Logs lost when container stops | Async queue not drained or shutdown grace period too short | Configure graceful stop and reconcile event counts; evaluate durable sinks |
| Secrets appear in error logs | HTTP interceptor, exception, or filter printing raw input | Redact/mask at the source and verify at every capture point |

## 11. Managing changes so staging remains useful

Store configuration as code and review it alongside application changes; when temporary `DEBUG` is needed, document the package, reason, duration, and owner. Automatically validate schema/test events on deployment and compare against production to catch configuration drift. Never edit one pod manually and assume all instances match; autoscaling can leave configuration versions inconsistent.

Only diverge from production on values that genuinely depend on the environment: levels, log destinations, retention, access control, sample rates, and verbosity of specific packages. Keep the same format and field semantics if dashboards or alerts will be reused in production. When staging is testing a major logging change, deploy it with versioning, add verification metrics, and prepare a release-based rollback instead of judging by "more logs is better."

Operationally, express requirements as measurable outcomes, such as: "Under standard test load, all `ERROR` events are received by the pipeline or trigger a clear failure indicator; test events are searchable within the defined SLO; no fake token strings leak; endpoint p99 stays within budget." Specific thresholds must be decided by product and infrastructure teams. The goal is for staging to catch issues accurately before release, with enough diagnostic data and controlled risk.

## 12. Self-check questions

1. Why should staging keep the same log schema as production while levels may differ?
2. If `logger.debug` does not appear despite configuring `DEBUG` in `application-staging.yml`, what do you check first?
3. Why might `%X{trace_id}` in a Logback pattern evaluate to empty, and what changes when using `ExecutorService`?
4. Why can enabling `DEBUG` for all of Hibernate or Spring make staging performance measurements unrepresentative of production?
5. A log appears on stdout but cannot be found in the log backend: which pipeline stages do you check?
6. How do you prove that masking works for exceptions, HTTP clients, and structured logging?
7. When `AsyncAppender` uses an in-memory queue, why can already-enqueued events still be lost after a container is killed?

**Completion criteria:** You can activate a staging configuration suited to your stack, explain the effective levels and output, read log events with context, confirm the collector indexes logs, check for data-exposure risks, and identify how slow, lost, or duplicated logs are handled.

## References

- [Spring Boot Reference — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html) — logging configuration, backends, and logging levels.
- [Spring Boot Reference — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html) — activating and scoping configuration by profile.
- [Logback Manual — Configuration](https://logback.qos.ch/manual/configuration.html) — loggers, appenders, and XML configuration.
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html) — ConsoleAppender, file appenders, and AsyncAppender.
- [Apache Log4j 2 — Configuration](https://logging.apache.org/log4j/2.x/manual/configuration.html) — logger, appender, and layout configuration.
- [Java SE 17 — java.util.logging](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/package-summary.html) — built-in JDK logging API.
