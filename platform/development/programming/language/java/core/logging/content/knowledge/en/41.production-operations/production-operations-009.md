# Restoring Java Logging Configuration in Production

## 1. The Goal of "Configuration Recovery"

**Logging configuration recovery** means returning the logging system from an incorrect, unstable, or non-compliant operational state back to a **known-good state** (last-known-good configuration), while verifying that critical logs are still being generated, delivered to their destinations, and searchable.

In **Production Operations**, this is not just about changing `DEBUG` back to `INFO`. A logging configuration consists of multiple interdependent parts:

- **Logger levels:** root level, package level, logger level, level inheritance.
- **Appender/handler:** console, rolling file, remote HTTP/TCP, Syslog, or OTLP.
- **Filters:** accepting/denying logs by level, marker, message, or request context.
- **Layouts/encoders:** pattern, JSON schema, timestamp, stack trace, charset.
- **Routing:** root logger, appender references, additivity, async wrappers.
- **Buffers/queues:** queue size, drop policy, flush/drain, backpressure.
- **Destinations:** file path, write permissions, disk quota, DNS, TLS, receiver/auth.
- **Context and security:** MDC/ThreadContext, trace ID, personal data, secret masking.
- **Lifecycle:** startup configuration, file watcher, runtime reload, rollout/restart.
- **Operational controls:** config version, owner, audit trail, checksum, rollback, and alerting.

Therefore, **"being able to parse the XML/YAML" is not enough to conclude that recovery succeeded**. A new configuration may be syntactically valid, yet logs go to the wrong destination, get filtered out completely, fail to ingest, or leak sensitive data.

A typical recovery flow:

```text
Detection: missing logs / sudden spike / wrong destination
                 |
                 v
     Isolate scope and failure type
                 |
                 v
     Select tested last-known-good
                 |
                 v
   Validate + staged restore / controlled rollout
                 |
                 v
     Verify: logs, sinks, latency, privacy
                 |
           +-----+-----+
           |           |
         PASS         FAIL
           |           |
      Keep version    Halt rollout,
      and monitor     safe fallback
```

**Principle:** recovery must have a **clear target state, a deterministic application mechanism, and verification evidence**, rather than just editing a file and assuming the framework picked up the change.

## 2. Symptoms That Point to Logging Configuration

| Symptom | Possible Configuration Cause | What to Check |
| --- | --- | --- |
| No application logs visible | Level too high, DENY filter, appender not attached | Effective level, logger name, root/appender refs |
| INFO present but ERROR missing | Different filter/routing, async drop, broken remote path | Appender-specific filters, status logger, queue |
| Single log appears multiple times | Additivity, root + child sharing appender, dual ingest | Logger tree, appender references, shipper/OTLP |
| Logs fill disk or spike ingest cost | Broad DEBUG/TRACE enabled, stack traces, batch logging | Volume by level/logger, rotation, sampling |
| Request latency increases after config change | Synchronous network appender, queue blocking, expensive encoder | Thread dump, send timeouts, queue depth |
| File receives no new lines | Wrong path/permissions, read-only mount, rotation/lock | Resolved path, OS permissions, disk quota |
| Logs present but missing trace ID | Broken MDC injection/encoder/context propagation | Active trace, MDC keys, structured output |
| Backend JSON parser errors | Layout/schema change, multiline, charset | Raw event at source and parsed event at sink |
| Startup reports parse error | Invalid XML/YAML/properties or missing plugin/class | Internal status output and config artifact |
| New level not applied after deploy | Different config location/precedence, no restart/reload | Active file, profile, environment, effective level |
| Tokens/PII exposed after config change | Redaction removed, logging body/headers/MDC/SQL binds | Canary secret test and pipeline controls |
| Logs on console but missing in backend | Independent collector/exporter/receiver/network issue | Shipper offsets, retries, queue, TLS, backend query |

**Do not assume every logging incident is caused by the configuration file.** A down collector, wrong dashboard query time range, expired certificate, full node disk, sampling, or the application not calling the logger can produce similar symptoms.

## 3. Before Restoring: Determine the Running Configuration Scope

An application can have multiple "sources of truth":

```text
Source control (Git)
    |
    +-- packaged logback.xml / log4j2.xml / logging.properties
    |
    +-- application.yml / application.properties
    |
    +-- environment variables / JVM system properties
    |
    +-- ConfigMap / Secret / mounted files
    |
    +-- runtime API: Actuator /loggers or JMX
    |
    +-- logging library defaults / auto-configuration
                 |
                 v
       Effective configuration per JVM
```

When an incident occurs, determine the **effective configuration** currently running, not just the file in the repository. For example:
- A package level was changed via Spring Boot Actuator, while Git still shows `INFO`.
- The container uses `logging.config=/etc/app/logback-spring.xml`, not the packaged `logback-spring.xml`.
- Log4j 2 loads its config from a different location via a system property.
- One pod was restarted while another pod is still running the old configuration.
- A ConfigMap changed, but the process only reads it at startup.
- The file watcher encountered a parser error and retained or reverted to the previous state according to framework behavior.

### 3.1. Minimum Information to Record

Before editing configuration, collect **secret-free** metadata:
- Service name, environment, instance/pod, application version, and logging backend.
- Version/digest of the deployed configuration; commit or artifact ID.
- Actual path/source loaded and active profile.
- Incident start time and most recent deploy/change time.
- Effective level of the affected logger and the root level.
- Appender names, logical sink destinations, and queue policy.
- Where the failure occurs: inside the JVM, file/stdout, shipper, Collector, or backend.
- Logs/metrics of the logging infrastructure on an **independent channel** that is still operational.

Do not print raw configs if they contain passwords, API keys, auth headers, or TLS keystore secrets. Use versioned checksums/digests and redacted copies for comparison.

## 4. Last-Known-Good Is More Than Just "The Previous File"

A good baseline should be an **identified and tested configuration bundle**, including:
1. The XML/properties/YAML file and all included files.
2. The corresponding framework version and encoder/plugin dependencies.
3. Approved logger names, appenders, filters, and routing paths.
4. Required configuration variables, without **copying raw secret values** into public backups.
5. Path/mount/destination assumptions and read/write permissions.
6. Canary log test results, expected levels, and privacy checks.
7. A hash or release ID to prove which version was applied.

A config that "worked fine yesterday" may be **incompatible** with a new application version if a plugin/appender changed its class name or the runtime upgraded Java/Logback/Log4j 2. Therefore, you must tie the **config version to the application/library version** and check compatibility before rolling back.

Example deployment metadata:

```yaml
logging_configuration:
  version: "logging-v12"
  git_revision: "example-commit-123"
  compatible_service_release: "orders-2026.11"
  backend: "logback"
  root_level: "INFO"
  required_sinks: ["stdout", "central-logs"]
  rollback_target: "logging-v11"
  validation: ["startup", "canary", "error-event", "sensitive-data"]
```

This is an illustrative schema for a deployment manifest, **not a standard configuration for Logback to read directly**. It helps the operations team trace whether the right bundle was selected for rollback.

## 5. Safe Production Recovery Runbook

### Step 1 — Stabilize the Situation

When facing missing logs or a log storm:
- Determine whether the failure affects **mandatory security/audit events** or only DEBUG/INFO.
- If overly verbose log levels are causing congestion, prioritize lowering the level via an **authorized runtime mechanism** or a controlled rollout rollback.
- If a failing remote destination is blocking requests, reduce coupling according to approved policy—do not strip out all ERROR logging.
- Keep a **minimal diagnostic channel** alive, such as stderr/container console/health metrics if still working.
- Record timestamps and config versions; do not generate additional logs containing credentials while debugging.

### Step 2 — Isolate Scope and Gather Evidence

Answer: which service, all pods or only one pod, since when, which sink is missing, and was there a coinciding config rollout? Observe source event counts, appender errors, Collector queue/export metrics, and backend queries.

### Step 3 — Select the Rollback Target

Pull a **verified last-known-good from Git/immutable artifact or config registry**. Do not "pick the newest `.bak` file" by modification time if you do not know which deploy it corresponds to. Check dependencies, schema, paths, permissions, secret references, and routing before activating.

### Step 4 — Validate Before Applying

Check at minimum:
- XML/JSON/YAML/properties parse syntactically.
- Appender classes/plugins are present and layout/encoder properties are supported.
- No references to undeclared appenders; no filter accidentally returns DENY for all events.
- File paths/mounts/permissions are valid; network/TLS destinations are valid.
- Root/package levels and additivity match the target state.
- Mandatory WARN/ERROR/audit channels are not disabled.
- No raw secrets, request bodies, Authorization headers, or SQL bind values are logged.
- No duplicates created across console/file/OTLP/shipper.
- Queue/retry/blocking policies align with the service SLO.

**Parser validation does not prove a network endpoint is alive or that the backend stored the event.** You must test actual behavior after applying.

### Step 5 — Apply via a Specific Mechanism

Choose one of:
- **Redeploy/restart** with a pinned version: most reliable when config is only read at startup or for major changes.
- **File-based automatic reload** if the backend supports it and the full lifecycle has been tested.
- **Runtime level override** for narrow emergencies, such as Spring Boot Actuator `/loggers`.
- **Programmatic update** for certain JUL/custom configuration setups, provided you understand handler lifecycle.

Do not apply multiple new sources simultaneously (Git, environment, runtime API) and lose track of which one wins. When rolling back multiple pods, use a canary/rolling strategy and keep a path back to the currently running version.

### Step 6 — Verify with a Canary Event

Emit a synthetic event with a safe identifier, such as:

```text
INFO event=logging.config_verified config_version=logging-v11
     verification_id=verify-20261110-01 service=orders
```

Check it at:
1. Logger/appender source (if a local sink exists).
2. File/stdout or remote receiver.
3. Collector/shipper ingestion.
4. Backend search/dashboard filtered by the right service, environment, and time range.
5. Expected record count, JSON schema, timestamp, level, and trace metadata.
6. Absence of any synthetic password/token canary values.

**A single successful event does not prove all loggers/levels work.** Also test WARN/ERROR, check filters, and verify other critical logging paths.

### Step 7 — Operational Verification

During the post-rollback observation window:
- Have log rates by level and logger category returned to baseline?
- Have appender errors/drops/retries/queue depth decreased?
- Are error events reaching the expected sink?
- Have HTTP latency, CPU, GC, and disk/network metrics improved?
- Are there duplicate logs from additivity or multi-ingest?
- Has Collector/backend ingest delay returned to acceptable levels?
- Is any PII/token leaking in parsed output?

### Step 8 — Finalize or Halt the Rollout

Only consider the rollback complete if the new version is **actually active** and all verification criteria pass. If not, halt the rollout, place the application into fallback operational mode per approved procedure, or roll back the application and config together. Document the incident timeline, approver, scope of change, and outcome.

## 6. Logback: Reloading, Fallback, and Limits to Remember

Logback Classic supports XML configuration, typically in `logback.xml` or a specified config path. Local example:

```xml
<configuration scan="true" scanPeriod="30 seconds">
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{ISO8601} %-5level [%thread] %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.repository" level="WARN"/>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Explanation:
- `scan="true"` instructs Logback to watch for configuration file changes.
- `scanPeriod="30 seconds"` defines the check interval; **include the unit** to avoid ambiguity.
- `root level="INFO"` sets the base threshold, while the repository logger overrides it to WARN.
- `CONSOLE` provides a local path to preserve signals when a remote sink fails.

When the file changes and the watcher supports it, Logback can reconfigure. **Logback documentation states that if the new configuration has XML syntax errors, it can fall back to a previously valid configuration**. However, important limits apply:
- That mechanism **does not guarantee** fallback when the XML is completely valid, yet logs are filtered out, the file path is wrong, a plugin is missing, or the remote endpoint rejects events.
- Do not assume changes are detected instantaneously; detection depends on the scan interval and file type.
- Do not assume every external URL/mounted source is watched the same way as a local file.
- Replacing appenders can trigger lifecycle/queue changes; verify actual event output and status diagnostics.
- Auto-reload is **a configuration mechanism**, not a production change-management/rollback orchestrator.

### 6.1. Do Not Edit the Active File Character-by-Character

If a file watcher is active, writing a file across multiple writes can expose an **incomplete intermediate file** to the watcher. A safer process:
1. Create a separate candidate file on the same controlled filesystem/mount.
2. Parse, review, and test the candidate outside production or on a canary.
3. Deploy the complete file using an atomic replace mechanism appropriate for the platform, or swap an immutable config artifact and restart/roll.
4. Record the version/digest and monitor reconfigure status.
5. Emit a canary log and verify.

Not every storage/mount supports atomic replace with the same semantics; for Kubernetes ConfigMaps or immutable container filesystems, **rollout/restart is usually easier to control**.

### 6.2. Spring Boot with Logback: A Special Exception

Spring Boot supports extensions in `logback-spring.xml` such as `<springProfile>` and `<springProperty>`. Spring Boot documentation warns that **these extensions are incompatible with Logback configuration scanning**.

Here is an illustrative configuration following the right approach when using Boot extensions (without enabling scan):

```xml
<configuration>
    <springProfile name="prod">
        <appender name="CONSOLE"
                  class="ch.qos.logback.core.ConsoleAppender">
            <encoder>
                <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
            </encoder>
        </appender>
        <root level="INFO">
            <appender-ref ref="CONSOLE"/>
        </root>
    </springProfile>
</configuration>
```

This illustrative file must be placed in **`logback-spring.xml`** in a Spring Boot/Logback project that supports extensions, not in a plain `logback.xml` file. When restoring a configuration that uses `<springProfile>`/`<springProperty>`, prefer deploying/restarting the right version or using a supported Spring Boot mechanism; **do not add `scan="true"` as a hotfix**.

If `no applicable action for [springProfile]` or `[springProperty]` errors appear after enabling scanning, check configuration lifecycle compatibility before editing the XML.

## 7. Log4j 2: monitorInterval and Reconfiguration

With Apache Log4j 2 Core, a file configuration can enable polling:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration monitorInterval="30">
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_ERR">
            <PatternLayout
                pattern="%d{ISO8601} %-5p %c - %m%n"/>
        </Console>
    </Appenders>

    <Loggers>
        <Logger name="com.example.repository"
                level="warn" additivity="true"/>
        <Root level="info">
            <AppenderRef ref="CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
```

`monitorInterval="30"` is the number of **seconds** between polls per Log4j 2 documentation; `0` disables it. Replacing the config file that the framework loaded and the watcher monitors triggers reconfiguration.

Notes:
- The watcher only works for **sources/configurations supported by Log4j**; files inside a JAR/classpath or remote sources may not reconfigure like a real file on the filesystem.
- Log4j 2 tries to minimize log loss during reconfiguration, can reuse appender resources, and may ignore certain option changes that risk log loss; **there is no end-to-end zero-loss guarantee across network/backend**.
- A syntactically valid configuration can still cause wrong routing or dropped logs; verify both source and sink.
- If using async loggers/appenders, understand queues and shutdown; do not treat "config loaded" as "queue drained".
- Internal error messages are logged via the **Status Logger**; on newer Log4j 2 versions, the diagnostic level can be configured with the `log4j2.statusLoggerLevel` system property. Do not leave internal TRACE enabled long-term in production.

### 7.1. Watch Out for Additivity

A specific logger and the root logger both having appenders attached can cause an event to appear multiple times if additivity is enabled. In the example above, `com.example.repository` does **not** attach its own appender, so letting events propagate up to root is appropriate.

If you want a separate file for the repository logger, decide:
- Should events still propagate up to the root console?
- Is the same appender attached to both parent and child?
- Could `additivity=false` accidentally drop logs from the central pipeline?

Rolling back a level while overlooking additivity or appender refs is not a complete recovery.

## 8. Java Util Logging (JUL): Avoid Arbitrary System-Wide Resets

JUL in the JDK uses `java.util.logging.Logger`, `Handler`, `Filter`, and `LogManager`. Startup configuration can be specified via a JVM property:

```bash
java -Djava.util.logging.config.file=/path/to/logging.properties \
     -jar application.jar
```

This is a **Bash** example: it requires an existing file path and JAR. On Windows PowerShell/cmd, line continuation and quoting differ; do not copy Bash's `\` character verbatim into other shells.

An illustrative `logging.properties` configuration:

```properties
handlers=java.util.logging.ConsoleHandler
.level=INFO
java.util.logging.ConsoleHandler.level=ALL
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
com.example.repository.level=WARNING
```

When recovery is needed, prefer restoring a verified file and restarting in a controlled manner, or using the appropriate update API.

### 8.1. Why `LogManager.reset()` Is Risky

According to JDK 17 documentation, `LogManager.reset()`:
- Removes and closes all `Handler`s on managed loggers.
- Sets logger levels to their default/inherited state per JUL rules.
- Clears properties currently held in LogManager.

Therefore, calling:

```java
LogManager.getLogManager().reset();
```

**Is not a "safe default recovery" for every service.** It can close file/network handlers and cause logs to vanish if not properly reinitialized. If you must manage JUL at runtime, look into `LogManager.updateConfiguration(...)` (JDK 9+) and handler lifecycles, but do not assume all handler properties update in place: some changes only apply to newly created handlers.

`readConfiguration(InputStream)` on an application that has already initialized loggers can **reset existing loggers**, per the JDK 17 API note; do not call it on a live request path without planning and testing.

## 9. Spring Boot Actuator: Runtime Logger Level Changes Do Not Update Config Artifacts

Spring Boot Actuator provides the `/actuator/loggers` endpoint to view/update effective logger levels when enabled/exposed and properly authorized.

Read example (protected internal endpoint, illustrative shell syntax):

```bash
curl --fail --silent \
  "http://127.0.0.1:8080/actuator/loggers/com.example.repository"
```

Temporary logger level change example:

```bash
curl --fail --silent --show-error \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"configuredLevel":"WARN"}' \
  "http://127.0.0.1:8080/actuator/loggers/com.example.repository"
```

Reset a logger's override back to inherited/default:

```bash
curl --fail --silent --show-error \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"configuredLevel":null}' \
  "http://127.0.0.1:8080/actuator/loggers/com.example.repository"
```

**Distinguish clearly:** `configuredLevel:null` means **clearing the explicitly configured level for that logger** so it falls back to its default/inherited level. It **does not mean** restoring the entire previous configuration file, appenders, filters, or layouts.

Operational notes:
- This endpoint may be disabled or unexposed by default. Configure and secure it per security policy.
- Changes are **runtime state** and usually do not update Git, YAML, or config artifacts; a process restart may revert to startup configuration.
- With multiple pods, calling one pod's endpoint affects only that pod. Check cluster-wide rollout.
- Never expose write endpoints to the public Internet; use authentication/authorization, network restrictions, and audit trails.
- When recovering after an emergency DEBUG change, remember to reset runtime overrides **and** confirm the config source remains accurate; avoid leaving silent overrides that cause pods to drift.

**Do not treat Actuator `/loggers` as a rollback tool for all types of logging config.** It is most useful when you need fast, controlled **logger level** changes.

## 10. Java 17 Runnable: Validate Candidate First, Keep Last-Known-Good, and Roll Back

This example **uses only JDK 17**. It simulates a small config registry containing `version` and `level`, distinguishing three operations:

1. Apply baseline `v1` with INFO.
2. Apply candidate `v2` with FINE.
3. Reject configuration `v3` with an invalid level **before mutating the logger**, then actively roll back to `v1`.

For deterministic stdout, the program uses an in-memory custom `Handler`; it omits timestamps/stack traces and does not depend on machine speed. This is **not a production XML/Logback/Log4j 2 reloader**; it demonstrates the *stage → validate → apply → rollback* pattern scoped to **a single logger level**.

Save as `LoggingConfigRecoveryDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LoggingConfigRecoveryDemo {
    private record Config(String version, Level level) { }

    private static final class CaptureHandler extends Handler {
        private final List<String> events = new ArrayList<>();

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                events.add(record.getLevel().getName()
                        + " " + record.getMessage());
            }
        }

        @Override public void flush() { }
        @Override public void close() { }

        List<String> events() {
            return List.copyOf(events);
        }
    }

    private static Config parseConfig(String text) {
        String[] lines = text.split("\\n", -1);
        if (lines.length != 2
                || !lines[0].startsWith("version=")
                || !lines[1].startsWith("level=")) {
            throw new IllegalArgumentException("INVALID_FORMAT");
        }

        String version = lines[0].substring("version=".length());
        String levelText = lines[1].substring("level=".length());
        if (!version.matches("v[0-9]+")) {
            throw new IllegalArgumentException("INVALID_VERSION");
        }

        Level level = switch (levelText) {
            case "INFO" -> Level.INFO;
            case "FINE" -> Level.FINE;
            case "WARNING" -> Level.WARNING;
            default -> throw new IllegalArgumentException("INVALID_LEVEL");
        };
        return new Config(version, level);
    }

    private static void apply(Logger logger, Config config) {
        logger.setLevel(config.level());
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.config.recovery");
        CaptureHandler capture = new CaptureHandler();
        capture.setLevel(Level.ALL);
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);
        logger.addHandler(capture);

        try {
            Config lastKnownGood =
                    parseConfig("version=v1\nlevel=INFO");
            apply(logger, lastKnownGood);
            logger.info("event=service.started config_version=v1");

            Config candidate =
                    parseConfig("version=v2\nlevel=FINE");
            apply(logger, candidate);
            logger.fine("event=diagnostics.enabled config_version=v2");

            try {
                Config invalid =
                        parseConfig("version=v3\nlevel=BOGUS");
                apply(logger, invalid);
            } catch (IllegalArgumentException ex) {
                logger.warning("event=config.rejected "
                        + "candidate=v3 reason=INVALID_LEVEL");
            }

            apply(logger, lastKnownGood);
            logger.info("event=config.rollback restored_version=v1");
            logger.fine("event=debug.after_rollback");
            logger.info("event=service.ready config_version=v1");

            for (String event : capture.events()) {
                System.out.println(event);
            }
        } finally {
            logger.removeHandler(capture);
            capture.close();
        }
    }
}
```

Compile and run:

```bash
javac --release 17 LoggingConfigRecoveryDemo.java
java LoggingConfigRecoveryDemo
```

**Exact** stdout:

```text
INFO event=service.started config_version=v1
FINE event=diagnostics.enabled config_version=v2
WARNING event=config.rejected candidate=v3 reason=INVALID_LEVEL
INFO event=config.rollback restored_version=v1
INFO event=service.ready config_version=v1
```

Explanation:
- `parseConfig` is the **pre-apply validation step**: it only accepts levels from the allowlist and properly formatted versions.
- When `v3` has `BOGUS`, parsing throws an exception and `setLevel` is never called; the logger is still at FINE when logging WARNING.
- `apply(logger, lastKnownGood)` actively restores INFO. Afterward, `FINE event=debug.after_rollback` **does not appear** because the logger is back at INFO.
- `CaptureHandler` accepts ALL, so filtering out FINE after rollback comes from the **logger level**, not the handler level.
- `setUseParentHandlers(false)` prevents the root logger from printing extra timestamps or duplicate output.
- The config contains only a single level so applying it is trivial; a production config with multiple appenders, filters, network destinations, and threads **is not an atomic transaction** just by calling a few setters.
- No external files, no Spring/Logback dependencies, no network; thus this example exercises recovery logic, not proof that a log backend persisted an event.

**Key takeaway:** you need an identified good configuration, a validation step separate from apply, an active rollback mechanism, and actual output testing. For large runtime configurations, prefer versioned redeploys over mutating individual properties in application code.

## 11. Checking Effective Logger Levels, Appenders, and Filters

A very common reason rollbacks fail: "root is INFO" yet no INFO logs appear. Level is only one of the necessary conditions.

Simplified flow:

```text
logger.isEnabledFor(level)?
         |
         v
Logger filters / hierarchy
         |
         v
Appender reference(s) / additivity
         |
         v
Appender filter (ACCEPT, DENY, NEUTRAL)
         |
         v
Encoder/layout -> stdout/file/network
         |
         v
Collector -> backend
```

Check:
- Does a specific logger have `level=ERROR` overriding root INFO?
- Does an appender have a `ThresholdFilter` filtering out INFO?
- Does an AsyncAppender/queue have a discard policy and is currently dropping events?
- Does a child logger have `additivity=false` without an appender attached?
- Is a message/marker filter mistakenly denying events?
- Do root/child wrappers share the same appender, causing duplicates?
- Has a remote appender destination or certificate changed?
- Is the JSON encoder using different keys that cause the backend parser to drop records?

**Logback** example:

```xml
<logger name="com.example.payment" level="INFO"/>
<root level="INFO">
    <appender-ref ref="CONSOLE"/>
</root>
```

This is only a fragment. If `com.example.payment` had `additivity="false"` without any `appender-ref`, logs could disappear even with logger level INFO.

Do not just check "file loaded cleanly": emit canaries at **at least INFO, WARN, and ERROR**, and verify the sink and schema for each path. For privacy, also ensure no filter/redaction was removed.

## 12. Restoring Appenders and Delivery Pipelines

A config rollback can alter log routing:

```text
JVM Logger
  |---- ConsoleAppender -> container stdout -> shipper
  |---- FileAppender -> rolling file -> filelog receiver
  |---- RemoteAppender -> OTLP/TCP/HTTP -> Collector
                                       |
                                       v
                                  Log backend
```

Each stage has its own failure modes. Logs appearing on stdout but missing in the backend do not prove a logger-level bug. Check in order:
1. Is the logger creating the event and is the appender referenced?
2. Is the appender writing bytes/records successfully to the local sink?
3. Are file paths and rotation valid?
4. Is the shipper reading the right file/pod/node/offset?
5. Are the OTLP endpoint/port/protocol/TLS/auth correct?
6. Is the Collector `logs` pipeline active with its receiver/processors/exporters?
7. Are Collector exporter queues, retries, and drop counters normal?
8. Are the backend parser, index/retention, time range, and tenant correct?
9. Are duplicates occurring from simultaneous stdout and OTLP ingestion?
10. Did the new config change `service.name` or timestamp format so dashboards no longer match?

### 12.1. TCP/HTTP ACK Does Not Guarantee Backend Durability

A successful TCP write does not prove the receiver persisted the data; an HTTP 2xx/OTLP success only means success **per the ingest endpoint's contract**. The Collector still has queues, batching, retries, and downstream exporters. When recovering a remote appender, checking "connected" is not enough: you must **find the canary event in the backend** within a reasonable timeframe.

### 12.2. AsyncAppender: Rollback Must Account for Queues and Shutdown

If an appender sends over the network synchronously, changing config may reduce log volume while in-flight I/O/queues still remain. If an async queue is full, events may be blocked or dropped per policy. During rollout/restart:
- Know the queue capacity and current depth.
- Allow a sufficient grace period to drain per operational requirements.
- Check dropped/retry counters.
- Do not assume SIGKILL/crash will invoke shutdown hooks.
- When audit requires zero-loss, use durable audit/outbox storage instead of relying solely on an in-memory async appender.

## 13. Kubernetes and GitOps: Rolling Back at Multi-Pod Scale

For Java applications deployed on Kubernetes, logging configuration typically comes from:
- Files packaged in the image.
- ConfigMaps mounted as files.
- Environment variables or JVM system properties.
- Helm/Kustomize overlays and GitOps deployment manifests.
- External configuration services/secret managers.

**Changing a ConfigMap does not guarantee the Java process will auto-reload.** Reload capability depends on the framework's file watcher, mount type, and lifecycle. Environment variables passed at process startup **do not automatically change inside the JVM** when a ConfigMap is edited. Volumes using `subPath` typically do not receive ConfigMap updates via projected volume mechanisms like regular mounts do.

A safe workflow:
1. Pin the config version/digest to the release.
2. Deploy one canary pod with the tested logging bundle.
3. Verify startup status, INFO/WARN/ERROR canaries, remote ingest, privacy, and performance.
4. Perform a rolling update respecting readiness/availability constraints.
5. Monitor what active config version each pod reports.
6. Halt the rollout if loss/duplicates/leaks/latency exceed thresholds.
7. When rolling back, revert to the exact previous artifact/version rather than relying on an unaudited manually edited file.

Do not restart all pods at once just for a single wrong logger level if a narrow Actuator change can mitigate temporarily; conversely, do not leave runtime overrides in place long-term and let the cluster drift from Git.

### 13.1. Change Auditing and Access Control

Record who requested/approved the change, the redacted config diff, apply timestamp, affected pods/versions, test results, and rollback target. Only allow authorized personnel to modify production logging. A logging config can contain remote endpoints, auth references, redaction regexes, and output paths: uncontrolled changes can cause log loss or secret leaks.

## 14. Detecting "Recovery Not Truly Complete"

Some log pipelines fail silently. Therefore, maintain **independent health/metrics**:

| Signal | Why It Matters |
| --- | --- |
| Log records emitted by level | Is the JVM actually emitting events? |
| Appender failures/status logger | Are there class/path/connection config errors? |
| Queue depth/capacity | Is ingest congested and risking drops? |
| Dropped event counter | Observe log loss directly instead of just noticing missing logs |
| Collector exporter queue/retry | Has the delivery path recovered? |
| Source-to-backend canary delay | How long until an event becomes queryable? |
| Duplicate ratio / event IDs | Is data being ingested from two paths? |
| Application request latency | Is an async/sync appender slowing down workloads? |
| Disk usage/rotation | Are rolling files filling up disk? |
| Security/PII canary test | Was redaction/schema accidentally altered? |

These names are **suggested metric categories**, not default API names across all logging frameworks. Use the actual metrics/health signals provided by Logback, Log4j 2, the Collector, and your infrastructure.

### 14.1. What Should a Canary Event Contain?

A test event is designed to:
- Identify the config version (a safe field).
- Include a unique synthetic ID for the verification run.
- Be emitted at a log level guaranteed to be allowed by policy.
- Carry no credentials/PII.
- Clearly identify the source service and environment.
- Be easy to search by event code and time range.
- Not pollute security audit streams as if it were a real transaction.

Example:

```json
{
  "event": "logging.config_verified",
  "config.version": "logging-v11",
  "verification_id": "verify-demo-01",
  "service.name": "orders-service",
  "severity": "INFO"
}
```

This is an illustrative schema. Every application does not need these exact keys; what matters is an **agreed-upon end-to-end verification criterion**.

## 15. Security and Privacy During Logging Rollback

A rollback must never "fix missing logs" by enabling full request logging that contains secrets. Risks include:
- Enabling `TRACE` on Hibernate bind parameters, exposing emails/tokens/PII.
- Dumping `Authorization`, `Cookie`, or request/response bodies.
- Putting access tokens into MDC or span baggage.
- Changing the JSON encoder and exposing nested fields that the old allowlist blocked.
- Dropping critical regex redactions/filters when reverting to an older config.
- Switching logs from a TLS endpoint to plain TCP/HTTP as a "quick fix".
- Using a debug exporter on the Collector in production to inspect real payloads.
- Leaking passwords in file paths, URLs, status errors, or exception messages.

A configuration that is **last-known-good** for availability may **no longer meet current security policy**. Check privacy requirements before applying an older version. If you must temporarily reduce log detail, preserve mandatory security events per policy.

Secret references (such as key aliases or mounted secret paths) must also be checked: an old config might point to an expired certificate or rotated credential. Never roll back to an old secret value just to match an old logging file.

## 16. Typical Rollback Scenarios

### 16.1. Broad DEBUG Enabled Causing a Log Storm

**Symptom:** rising ingest costs, full disks, degraded request latency. **Recovery:** lower package/root level via controlled runtime override or redeploy known-good. **Verify:** log rate, disk, Collector queue, request p95, and INFO/WARN/ERROR canaries. **Do not:** disable all logs or drop security errors.

### 16.2. New XML Prevents App Startup

**Symptom:** Logback/Log4j 2 parser/plugin exception. **Recovery:** restore a valid version from artifact; with Logback scanning, understand syntax fallback may occur, but do not rely on it to save startup. **Verify:** startup logs, active config, and actual sinks receiving events.

### 16.3. Logs Appear on Console but Not in Centralized System

**Symptom:** logger still works; receiver/exporter/cert or Collector pipeline is failing. **Recovery:** check remote appender, OTLP endpoint, TLS, queue, filelog receiver, and credentials. You may not need to roll back the entire logging config if the issue is in the backend. **Verify:** canary query in the backend.

### 16.4. JSON Layout Change Breaks Trace Correlation

**Symptom:** source emits events, but the backend does not map trace/span IDs. **Recovery:** use a compatible encoder schema, check MDC injection and parser. **Verify:** a request with an active span has its log tagged with the trace ID and the trace is found if sampling/retention allows.

### 16.5. Rollback Increases Duplicates

**Symptom:** one event produces two records in the same index. **Check:** root+child appenders, stdout shipper running alongside direct OTLP, retry/duplicate transport. **Recovery:** define one source path per logical event and check additivity, but do not delete a critical route without knowing other retention/consumers.

### 16.6. Runtime Logger Levels Inconsistent Across Pods

**Symptom:** pod A is DEBUG, pod B is INFO after a hotfix. **Recovery:** inspect runtime overrides per pod, reset to inherited/default, or redeploy the pinned standard config. **Verify:** effective levels and canaries across multiple pods. **Do not:** edit Git alone and assume every running process will update itself.

## 17. Post-Recovery Verification Matrix

| Test | Action | Expected Result |
| --- | --- | --- |
| Config parses | Start process with candidate | No parser/plugin errors |
| Active config version | Query process metadata/status | Matches pinned version/hash |
| INFO event | Emit synthetic INFO | Appears in required sinks per policy |
| WARN/ERROR event | Emit synthetic WARN and ERROR | Not mistakenly filtered or dropped |
| Package override | Emit DEBUG in specific package | Effective level correct, not too broad |
| Appender additivity | Single event through child logger | Expected number of records |
| File appender | Write then rotate in lab | Path/perms/quota valid, no abnormal truncation |
| Remote appender | Send event to receiver | Ingested with right schema and time range |
| TLS certificate change | Test valid/invalid cert in lab | Verifies hostname/trust, no silent downgrade |
| Collector outage | Stop receiver in test | Bounded queue/retry/drop per policy, app SLO preserved |
| Async shutdown | Graceful stop | Drains/flushes per contract and timeout |
| JVM crash | Controlled kill in lab | Log-loss window understood, no false zero-loss assumption |
| Logging privacy | Emit synthetic token canary | No raw secrets exposed in any sink |
| Trace correlation | Emit log inside active span | Trace/span fields present when instrumented |
| Multi-pod | Rolling canary/rest | No unintended pod drift |
| Restart | Restart with same artifact | Runtime levels do not unexpectedly differ from baseline |
| ERROR dispatch | Trigger HTTP/DB exception | Error summary has correct outcome |
| Performance | Benchmark equivalent workload | Latency/CPU/log volume within acceptable bounds |
| Backend query | Search `verification_id` | Record exists with right time/resource and no duplicates |
| Revert again | Test rollback path in staging | Can restore another last-known-good if needed |

Tests should use **synthetic data**; do not emit production tokens into logs. Not every test must run in production; unit/integration/staging verify the mechanics first, while production canaries verify essential points without disruption.

## 18. Common Mistakes

**Mistake 1 — only changing the file without checking if the app reloaded:** the effective state may still be the old version. Check the version and event output.

**Mistake 2 — confusing parser success with operational success:** syntactically valid XML does not prove logs reach the backend.

**Mistake 3 — enabling `scan=true` on `logback-spring.xml` with Spring extensions:** incompatible with the extension lifecycle per Spring Boot documentation.

**Mistake 4 — trusting Logback to auto-fallback on every error:** XML syntax fallback does not rescue appender/filter/network failures.

**Mistake 5 — mistaking Log4j 2 `monitorInterval` for milliseconds:** in Log4j 2 the value is in seconds; `0` disables polling.

**Mistake 6 — using `LogManager.reset()` as a "quick fix" for JUL:** can close all handlers and make logs disappear.

**Mistake 7 — using Actuator `configuredLevel:null` to restore the whole pipeline:** only resets the logger-level override; does not fix appenders/layouts/TLS.

**Mistake 8 — rolling back config without rolling back plugin versions:** classes/attributes may be incompatible with the running library.

**Mistake 9 — forgetting configuration precedence:** environment/command-line overrides still beat the restored file.

**Mistake 10 — forgetting other pods/instances:** rolling back one pod leaves the cluster in an inconsistent state.

**Mistake 11 — overwriting a file in place while the watcher is reading it:** can expose an incomplete XML snapshot.

**Mistake 12 — disabling redaction or enabling SQL bind TRACE:** can expose secrets/PII, far worse than the original logging incident.

**Mistake 13 — keeping HTTP remote appenders synchronous:** slow logging backends increase request latency.

**Mistake 14 — assuming TCP write/HTTP ACK means durable:** verify the backend receiver and queue semantics.

**Mistake 15 — looking only at logs to confirm the log pipeline is healthy:** the log path itself may be broken; use independent metrics/health.

**Mistake 16 — not measuring duplicates/drops:** after restoring, it may look like more events are arriving when it is actually duplicate routing/tracing.

## 19. Checklist Before, During, and After Rollback

### Before Rollback
- [ ] Confirm the incident and scope of services/pods/sinks.
- [ ] Save version/config digest metadata and incident timestamp.
- [ ] Select a last-known-good compatible with the application/library.
- [ ] Check syntax, plugins, levels, additivity, filters, file paths, and destinations.
- [ ] Assess privacy/TLS/auth and current secret rotation state.
- [ ] Define the rollback strategy, change owner, and halt criteria.

### During Rollback
- [ ] Apply through an approved channel (versioned deploy, file reload, runtime override).
- [ ] Do not silently edit multiple configuration sources at once.
- [ ] Keep a minimal diagnostic channel operational.
- [ ] Monitor startup/status logger and rollback status.
- [ ] Canary on one instance first if doing a rolling deployment.
- [ ] Do not arbitrarily open DEBUG/TRACE or disable TLS.

### After Rollback
- [ ] Confirm the active version on every instance.
- [ ] Ensure INFO/WARN/ERROR match policy.
- [ ] Confirm appenders/collector/backend actually receive events.
- [ ] Check duplicates, drops, queue depth, retries, and disk quota.
- [ ] Check schema, timestamp, trace ID, and absence of synthetic secret leaks.
- [ ] Measure log volume, CPU, request latency, and error rate.
- [ ] Document the outcome, commit/config version, and preventive lessons.
- [ ] Reconcile any runtime hotfix back into GitOps/source of truth when appropriate.

**Conclusion:** restoring production logging configuration is **restoring reliable observability**, not just editing a file. Maintain versioned last-known-good configurations, apply them following the proper lifecycle of Logback/Log4j 2/JUL/Spring Boot, and verify with canary events, metrics, and privacy checks across the entire pipeline. Until you have verified that data reaches the intended sink, do not declare the rollback complete.

## Official References

- [Logback — Configuration: automatic scanning, previous safe configuration](https://logback.qos.ch/manual/configuration.html).
- [Logback — Appenders, levels, filters, and additivity](https://logback.qos.ch/manual/architecture.html).
- [Apache Log4j 2 — Configuration file, monitorInterval, reliability](https://logging.apache.org/log4j/2.x/manual/configuration.html).
- [Apache Log4j 2 — Status Logger](https://logging.apache.org/log4j/2.x/manual/status-logger.html).
- [Spring Boot — Logging and Logback extensions](https://docs.spring.io/spring-boot/reference/features/logging.html).
- [Spring Boot Actuator — Loggers endpoint](https://docs.spring.io/spring-boot/reference/actuator/loggers.html).
- [Oracle JDK 17 — LogManager: reset, readConfiguration, updateConfiguration](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogManager.html).
- [Oracle JDK 17 — Logger and Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html).
- [OpenTelemetry — Collector resiliency](https://opentelemetry.io/docs/collector/resiliency/).
- [OpenTelemetry — Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/).
- [OWASP — Logging Cheat Sheet, data to exclude](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).