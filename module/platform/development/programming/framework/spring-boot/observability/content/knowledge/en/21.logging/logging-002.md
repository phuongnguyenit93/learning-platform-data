# Environment-Based Log Levels in Spring Boot

**Environment-based log levels** are the practice of configuring logging detail according to the runtime environment of an application, such as local, dev, test, staging, and prod. The same Spring Boot artifact may need verbose logs during development, moderate logs during integration testing, and concise logs in production to support operations without generating excessive data or exposing sensitive information.

In the **SPRING_BOOT_OBSERVABILITY** module, logging is one of the three observability signals alongside metrics and distributed tracing. Log levels determine which events are recorded; correlation fields link logs with Trace ID/Span ID; resource and deployment metadata identify the service/version/environment that emitted the event. This lesson belongs to the **Logging** chapter and focuses on profiles, `application-{profile}.yml`, environment variables, logger hierarchy, logging groups, Actuator, and safe operational practices.

## 1. What Is a Log Level?

A log level is the severity or level of detail of a logging event. Common levels in SLF4J/Logback and Spring Boot:

| Level | Meaning | Common scenarios |
| --- | --- | --- |
| TRACE | Very fine-grained detail for deep analysis | Tracing internal steps briefly |
| DEBUG | Diagnostic information for developers | Execution branches, internal state, sanitized data |
| INFO | Normal operational events worth noting | Service started, request completed, job ran |
| WARN | Unusual condition where the application still continues | Retry, fallback, configuration nearing threshold |
| ERROR | Error causing an operation to fail or needing intervention | Unhandled exception, dependency call failure |

A logger normally records only events whose level is equal to or higher in severity than the configured threshold. For example, a logger set to `INFO` allows `INFO`, `WARN`, and `ERROR`, while ignoring `DEBUG` and `TRACE`.

\[
TRACE \rightarrow DEBUG \rightarrow INFO \rightarrow WARN \rightarrow ERROR
\]

`OFF` can be used to disable a logger; `ALL` typically allows every level. Do not set the root logger broadly to `TRACE`/`DEBUG` in production.

## 2. Why Should Log Levels Differ by Environment?

- **Local/development:** developers need more detail to follow code paths and diagnose bugs.
- **Test/CI:** logs must be clear enough to pinpoint test failures, without generating overly huge output.
- **Staging:** close to production to verify operational behavior, integrations, and tracing.
- **Production:** prioritize operationally valuable, stable, searchable signals with controlled cost.

| Environment | Illustrative level | Purpose |
| --- | --- | --- |
| local | DEBUG | Observe business flows |
| test | INFO | Concise output showing key events |
| staging | INFO or selective DEBUG | Investigate integrations before release |
| production | INFO | Normal operational logging |
| production incident | Temporary DEBUG for a specific logger | Time-bounded investigation, then revert |

There is no single log level table that fits every system. Needed levels depend on traffic, data sensitivity, logging backend, filtering, retention, and incident investigation workflows.

## 3. Logger Hierarchy: Root, Package, and Class

Log levels are typically configured by logger name. In Java, loggers are commonly named after the class, such as `com.example.order.OrderService`. Logback supports hierarchy by package/name. A child logger inherits the level from its parent logger unless configured explicitly.

Example:
- Root logger: `INFO`.
- Package `com.example`: `INFO`.
- Package `com.example.order`: `DEBUG`.
- Class `com.example.order.PaymentClient`: `TRACE`.

### 3.1. Multi-Level Configuration Example

```yaml
logging:
  level:
    root: INFO
    com.example: INFO
    com.example.order: DEBUG
    com.example.order.PaymentClient: TRACE
    org.springframework.web: WARN
```

A child logger's level overrides the level inherited from its parent package. Avoid enabling `TRACE` on large packages because log volume can grow very rapidly.

### 3.2. Root Logger and Specific Loggers

`root` is the default threshold for loggers without their own explicit level. Setting `root` to `WARN` can drop important `INFO` events; setting `root` to `DEBUG` can generate massive log volume from frameworks, HTTP clients, and third-party libraries.

Practical configurations usually keep `root` at a moderate level, application packages at `INFO` or `DEBUG` depending on the environment, noisy libraries at `WARN`, and a specific class/package at `DEBUG` during investigation.

## 4. Basic Configuration in `application.yml`

Spring Boot supports configuring log levels via `logging.level`.

```yaml
logging:
  level:
    root: INFO
    com.example: INFO
    org.springframework.web: WARN
    org.hibernate.SQL: WARN
```

`application.yml` holds the default configuration. When no profile-specific override applies, the application uses these values. Start with a simple baseline covering the root logger, application packages, and a few framework loggers that need tuning. Identify logger names from actual output instead of adding arbitrary packages.

## 5. Using Spring Profiles to Separate Log Levels

Spring Profiles allow different configurations per environment. A common pattern uses `application.yml`, `application-local.yml`, `application-test.yml`, `application-staging.yml`, and `application-prod.yml`.

`application.yml`:

```yaml
spring:
  application:
    name: order-service

logging:
  level:
    root: INFO
    com.example: INFO
    org.springframework: WARN
```

`application-local.yml`:

```yaml
logging:
  level:
    root: INFO
    com.example: DEBUG
    org.springframework.web: INFO
    org.hibernate.SQL: DEBUG
```

`application-test.yml`:

```yaml
logging:
  level:
    root: INFO
    com.example: INFO
    com.example.order: DEBUG
```

`application-prod.yml`:

```yaml
logging:
  level:
    root: INFO
    com.example: INFO
    org.springframework: WARN
    org.hibernate: WARN
    org.hibernate.SQL: WARN
```

When `prod` is active, Spring Boot loads the corresponding profile configuration and merges it with the default configuration via externalized configuration. Verify the effective configuration when multiple override sources exist.

### 5.1. Activating a Profile

```bash
SPRING_PROFILES_ACTIVE=prod
```

Or:

```bash
java -jar app.jar --spring.profiles.active=prod
```

When running inside a container/orchestrator, environment variables or deployment configuration are usually convenient. Do not hardcode `prod` into an artifact shared across all environments.

### 5.2. Profile Config Is Not a Secrets File

Files like `application-prod.yml` are typically packaged with the application. Do not store passwords, tokens, or private keys in them. Secrets must come from proper secret management.

## 6. Multi-Document YAML with `on-profile`

You can split multiple YAML documents in a single file using document separators and profile activation conditions.

```yaml
spring:
  application:
    name: order-service

logging:
  level:
    root: INFO
    com.example: INFO

---
spring:
  config:
    activate:
      on-profile: local

logging:
  level:
    com.example: DEBUG
    org.springframework.web: INFO
    org.hibernate.SQL: DEBUG

---
spring:
  config:
    activate:
      on-profile: prod

logging:
  level:
    root: INFO
    com.example: INFO
    org.springframework: WARN
    org.hibernate: WARN
```

A document with `on-profile` applies only when the matching profile is active. If multiple profiles/documents match at once, order and precedence must be considered. Keep configuration clear to avoid two documents unintentionally setting the same logger to different levels.

## 7. Configuring via Environment Variables

Spring Boot properties can be externalized via environment variables.

```bash
LOGGING_LEVEL_ROOT=INFO
LOGGING_LEVEL_COM_EXAMPLE=DEBUG
SPRING_PROFILES_ACTIVE=local
```

For simple properties, relaxed binding converts property names to uppercase with underscores. However, **logger names can contain underscores or special characters**, so mapping complex logger names to environment variables can be ambiguous or fail to represent them accurately. Class names with uppercase letters or `$` for nested classes also need verification.

For complex logger names, profile-specific YAML, ConfigMap/configuration sources, or the Actuator `loggers` endpoint are usually clearer.

### 7.1. Placeholder for Root Level

You can use a variable agreed upon by deployment conventions:

```yaml
logging:
  level:
    root: ${APP_LOG_LEVEL:INFO}
```

`APP_LOG_LEVEL` defaults to `INFO` if unset. You can similarly externalize a stable package, but avoid creating too many individual variables for every single class.

### 7.2. Never Take the Profile from a Request

`spring.profiles.active` must be chosen from trusted deployment configuration. Never allow an HTTP request, header, or client input to activate a `dev`/`debug` profile in production.

## 8. Externalized Configuration and Precedence

Spring Boot reads configuration from multiple sources: config files, profile-specific files, environment variables, system properties, command-line arguments, config trees, and other sources depending on the application. Higher-precedence sources determine the effective value.

| Source | `logging.level.com.example` |
| --- | --- |
| `application.yml` | INFO |
| `application-prod.yml` | INFO |
| Mapped environment variable | DEBUG |
| Higher-precedence command-line argument | WARN |

The table illustrates multiple sources setting the same property; the exact effective precedence should be checked against the property sources and Spring Boot configuration in use.

### How to Find the Source of an Override

1. Check which profile is actually active.
2. Check process/container environment variables.
3. Check Java system properties and command-line arguments.
4. Check config server, mounted config trees, or deployment overlays.
5. Check the current Actuator logger level.
6. Check native logging configuration such as `logback-spring.xml`.

Do not edit multiple sources simultaneously before finding the overriding source. Record the effective value and the changed source in the deployment record.

## 9. Logging Groups

Spring Boot supports logging groups to set levels for a related collection of loggers using a group name. Some built-in groups depend on the version; applications can also define custom groups.

```yaml
logging:
  group:
    order-flow:
      - com.example.order
      - com.example.inventory
      - com.example.payment
  level:
    root: INFO
    order-flow: DEBUG
```

Setting `order-flow` to `DEBUG` adjusts the loggers in the group to the group's level. This is convenient when turning on logging for a subsystem spanning multiple packages.

Built-in groups such as `web` or `sql` depend on the Spring Boot version. Check the reference documentation or runtime logger state.

## 10. Log Levels for Libraries and Frameworks

```yaml
logging:
  level:
    root: INFO
    com.example: INFO
    org.springframework.web: WARN
    org.springframework.security: INFO
    org.hibernate.SQL: WARN
    org.apache.kafka: WARN
    com.zaxxer.hikari: INFO
```

Logger names and behavior can vary by library version. Do not lower a framework logger to `ERROR` just to keep logs clean if doing so hides warnings or important information.

### 10.1. Hibernate SQL and Bind Parameters

SQL logging is helpful when debugging queries, but SQL text and bind values can contain sensitive information. Each request can also generate many log lines. Do not enable bind parameter logging in production without evaluating PII, credentials, payment data, and retention.

### 10.2. HTTP Client/Server Logs

Logging raw request/response headers or bodies can expose cookies, authorization tokens, and personal data. A `DEBUG` log level is not a security control; logging code must still redact sensitive data before writing.

## 11. Combining Log Levels with Logback

Spring Boot supports Logback when the appropriate dependency is present. When custom layouts, appenders, rolling policies, or filters are needed, an application can use `logback-spring.xml`.

Example root logger fragment:

```xml
<configuration>
    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

This is only an illustrative fragment; the `CONSOLE` appender must be defined. When native logging configuration exists, understand how Spring Boot combines it with `logging.level` and profile-specific sections.

`logback-spring.xml` supports certain Spring Boot extensions such as referencing profiles/properties during configuration. Not all extensions work in plain `logback.xml` because that file may be loaded too early by the logging system.

Avoid configuring the same logger in two places. Before adding custom Logback configuration, confirm the real need: JSON layout, remote appender, rolling, async logging, or redaction. If you only need to change levels, `logging.level` is usually simpler.

## 12. Changing Log Levels at Runtime via Actuator

Spring Boot Actuator provides the `loggers` endpoint to read and change log levels at runtime when the endpoint is exposed and properly secured.

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
          - loggers
```

Read a logger:

```http
GET /actuator/loggers/com.example.order
```

Change level:

```http
POST /actuator/loggers/com.example.order
Content-Type: application/json

{
  "configuredLevel": "DEBUG"
}
```

The URL may differ if the management base path/port is configured differently. The `configuredLevel` payload can accept `DEBUG`, `INFO`, `WARN`, `ERROR`, or `null` to clear the runtime override and fall back to the inherited/configured level per the implementation.

### 12.1. Runtime Overrides May Not Persist

Overrides via Actuator typically live in process memory. They can be lost when the service restarts, a pod is replaced, or configuration is reloaded.

After investigation:
- Revert the logger to an appropriate level.
- Record who changed it, when, why, and for how long.
- If the new log level must remain permanent, update the managed configuration source.
- Check all replicas; changing one pod does not necessarily change the whole service.

### 12.2. Securing the Actuator `loggers` Endpoint

This endpoint can alter telemetry volume and expose internal details. Do not expose it publicly on the Internet. Restrict it using authentication/authorization, network policy, a separate management port, and proper auditing. Only authorized operators should adjust production log levels.

## 13. Log Levels, Metrics, Logs, and Tracing

Log levels affect which events appear in logs, but they do not automatically alter metrics or tracing sampling.

| Component | Role | Example |
| --- | --- | --- |
| Log level | Filter log events | Root INFO, package DEBUG |
| Metrics | Count/measure aggregate behavior | Request count, latency, error rate |
| Tracing sampling | Choose traces/spans to record/export | Trace ratio 10% |
| Trace/log correlation | Link log event to trace | Trace ID, Span ID in MDC |
| Resource attributes | Identify telemetry source | `service.name`, `environment`, `version` |

A request may lack a trace in the backend due to sampling while `WARN`/`ERROR` logs are still written. Conversely, a trace may exist without `DEBUG` logs because the logger is set to `INFO`.

When the tracing integration puts Trace ID/Span ID into MDC, the log pattern can display them. Having correlation fields does not require enabling `DEBUG`. You can keep root at `INFO` and still link `INFO`, `WARN`, and `ERROR` log events to traces.

Do not log a `DEBUG` line per request just to infer request rate or latency. Use Micrometer metrics for aggregates, traces for sampled request journeys, and logs for events needing explanation.

## 14. Production Logging: Sufficient Detail and Safety

A good production configuration usually:
- Keeps the root logger at `INFO` or an operationally agreed baseline.
- Elevates `DEBUG` only for targeted packages/classes and for a limited duration.
- Selectively suppresses noisy framework logs without hiding critical errors.
- Uses structured logging when the backend needs to parse/search fields.
- Includes Trace ID/Span ID in log correlation when tracing is enabled.
- Redacts credentials, cookies, PII, and raw payloads.
- Configures retention and access control for the log backend.
- Monitors log volume, ingestion errors, dropped events, and disk usage.

### 14.1. Log Volume Is an Operational Cost

For example, a service writing 500 lines/second with an average of 1 KB per line:

\[
500 \times 1\text{ KB} \times 86\,400 \approx 43.2\text{ GB/day}
\]

This is a rough estimate before compression, batching, indexing, and retention. Enabling `DEBUG` and increasing line count by 5x can increase data volume substantially.

Consider transport, indexing, storage, query costs, and CPU/I/O impact.

### 14.2. Redaction Must Happen at the Source

Do not log secrets hoping the backend will always strip them. Redact where the log is generated and audit exception messages, headers, DTO `toString()`, SQL, structured fields, and third-party library logs.

Do not serialize entire request/response objects at default `DEBUG`. Use field allowlists and length limits.

## 15. Configuration Templates by Environment

### 15.1. Local

```yaml
# application-local.yml
logging:
  level:
    root: INFO
    com.example: DEBUG
    org.springframework.web: INFO
    org.hibernate.SQL: DEBUG
```

### 15.2. Test

```yaml
# application-test.yml
logging:
  level:
    root: INFO
    com.example: INFO
    com.example.order: DEBUG
    org.springframework: WARN
```

### 15.3. Staging

```yaml
# application-staging.yml
logging:
  level:
    root: INFO
    com.example: INFO
    com.example.integration: DEBUG
    org.springframework: WARN
```

Staging can enable `DEBUG` for an integration package while testing downstream behavior, but it should have a reason and expiration. When staging simulates production traffic, keep log levels close to production to accurately measure volume and performance.

### 15.4. Production

```yaml
# application-prod.yml
logging:
  level:
    root: INFO
    com.example: INFO
    org.springframework: WARN
    org.hibernate: WARN
```

The levels above are reference baselines. Replace them with logger names and levels verified against the actual application version.

## 16. Troubleshooting Environment-Based Log Levels

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| DEBUG does not appear locally | Profile not active or wrong package logger name | Check active profiles and logger name |
| Production still emits DEBUG | Environment/command-line override or Actuator runtime override | Check effective logger level and property sources |
| Changed YAML but no effect | Profile file not loaded, wrong profile, or native config overrides | Check config loading and logging system |
| Too many framework logs | Root/package level too low | Set explicit level for noisy framework logger |
| Missing INFO in production | Root/package set to WARN/ERROR | Check hierarchy and effective level |
| Package does not inherit root | Child logger has its own explicit level | Read configured/effective level |
| Actuator level change lost on restart | Runtime override is not persistent | Update durable configuration source |
| Actuator returns 404 | Endpoint not exposed or different management path/port | Check exposure and base path |
| Actuator returns 401/403 | Authentication/authorization policy | Check security chain/operator permissions |
| Only one replica changes level | Endpoint called on a single pod | Follow procedure for each instance |
| Env var does not control class logger | Logger name does not map cleanly | Use YAML/config source or Actuator |
| Sudden spike in log volume | Broad DEBUG/TRACE or retry loop | Compare config and volume per logger |
| Logs contain sensitive data | Logging code/third-party logger did not redact | Redact at source and reduce output |
| Trace ID missing from logs | Tracing/MDC not configured or context lost | Check integration and async propagation |
| Logs do not reach backend | Appender/agent/collector pipeline error | Check shipper/collector separately |

### Debugging Workflow

1. Confirm the active environment/profile.
2. Check the logger name and hierarchy.
3. Read the effective level of `root` and the specific logger.
4. Check configuration from YAML, environment, system properties, or command line.
5. Check Actuator runtime overrides.
6. Check native Logback configuration if present.
7. Check log output at the process/container before investigating the shipper/backend.
8. If logs leave the app but do not appear in the backend, check the shipping and ingestion pipeline.
9. After investigation, revert any elevated loggers and verify log volume returns to normal.

## 17. Lab Exercise: Configuring Log Levels for Four Environments

The goal is to have a Spring Boot application use the same artifact while running different log levels across `local`, `test`, `staging`, and `prod`.

### Preparation

- A Spring Boot application with SLF4J/Logback.
- A service class with a logger.
- Separate profile configuration files.
- Actuator if you want to practice with the runtime `loggers` endpoint.

Example class:

```java
package com.example.order;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private static final Logger log =
            LoggerFactory.getLogger(OrderService.class);

    public void createOrder(String orderReference) {
        log.trace("Entering createOrder");
        log.debug("Validating order reference");
        log.info("Creating order");
        log.warn("Using fallback inventory source");
        log.error("Order creation failed");
    }
}
```

This is an example illustrating levels, not a complete production error-logging implementation. Do not put real `orderReference` values or personal data into logs unless permitted.

### Step 1 — Baseline Configuration

In `application.yml`, set `root` to `INFO` and the application package to `INFO`. Run the app without activating a custom profile; verify `INFO`, `WARN`, and `ERROR` appear while `DEBUG` and `TRACE` are filtered out.

### Step 2 — Activate `local`

Run with `SPRING_PROFILES_ACTIVE=local`. Verify `com.example` logger is at `DEBUG` and the SQL logger is at the declared level. Check that framework logs remain controlled.

### Step 3 — Run `test`

Activate the `test` profile; verify output is informative enough when tests fail without being noisy. Run the same test and compare output with `local`.

### Step 4 — Run `staging`

Activate `staging`; enable only the integration package needed for testing. Document why that logger's level was raised.

### Step 5 — Run Production Config in Lab

Activate `prod`; verify `root`/application packages remain at baseline. You do not need to deploy to real production to practice.

### Step 6 — Override with an Environment Variable

Set `APP_LOG_LEVEL=DEBUG` if the config file uses the corresponding placeholder, or try `LOGGING_LEVEL_ROOT`. Check the effective level to see which source took precedence.

### Step 7 — Try Actuator `loggers`

Expose the `loggers` endpoint in the lab and read logger `com.example.order`. Change `configuredLevel` to `DEBUG`, verify output changes, then send `null` or revert to baseline to clear the runtime override.

### Step 8 — Try Multiple Replicas

Run two instances in the lab. Call the endpoint on one instance and verify only that instance changes when the runtime override is applied locally.

### Step 9 — Verify Correlation and Privacy

If tracing is enabled, verify Trace ID/Span ID in the log pattern. Confirm fields are redacted and there are no secrets/tokens or raw payloads.

### Step 10 — Revert and Sign Off

Return all loggers to the chosen environment levels. Verify there are no unintended `DEBUG` overrides remaining and log volume is stable.

### Verification Checklist

| What to demonstrate | Passing criteria |
| --- | --- |
| Level semantics | Can explain `TRACE` through `ERROR` |
| Logger hierarchy | Understands `root`, package, and class loggers |
| Profiles | Chooses the right file/config for each environment |
| Baseline | Safe, operationally manageable default configuration |
| Overrides | Identifies environment/system/command-line sources |
| Logging groups | Knows how to group loggers and verify group support |
| Logback | Understands when native logging configuration is needed |
| Actuator | Reads/changes runtime level in lab and knows how to revert |
| Security | `loggers` endpoint secured, sensitive data redacted |
| Observability | Distinguishes log levels from metrics/tracing sampling |
| Replicas | Understands runtime overrides may affect only one instance |
| Cleanup | Reverts `DEBUG`/`TRACE` after investigation |

## 18. Key Principles to Remember

1. **Use a stable baseline for every environment.** Root `INFO` is a common starting point; package/class loggers are raised only with justification.
2. **Profiles separate configuration by deployment.** Use `application-local.yml`, `application-test.yml`, `application-staging.yml`, `application-prod.yml`, or YAML documents with `on-profile`.
3. **Logger hierarchy turns on detail at the right scope.** Root, package, and class can have different levels; check whether a child logger has an explicit level.
4. **Environment variables and command-line arguments can override files.** When a log level behaves unexpectedly, find the effective property source.
5. **Logging groups reduce repetitive multi-package configuration**, though you should verify group support in your Spring Boot version.
6. **Actuator `loggers` assists runtime investigation**, but overrides typically live only in process memory and must be reverted.
7. **Protect management endpoints.** Never expose log-level modification permissions to public users.
8. **`DEBUG`/`TRACE` can spike log volume and data leakage risk.** Enable only needed loggers, with a time limit and clear ownership.
9. **Log levels do not control metrics or trace sampling.** Each signal has its own pipeline; Trace ID/Span ID correlation can still appear at `INFO`.
10. **Redact at the source.** Never log secrets, tokens, cookies, PII, or raw payloads expecting the backend to strip them.
11. **Revert after incidents.** Record changes, inspect all replicas, and restore standard log levels after investigation.

Environment-based log level configuration allows Spring Boot to provide ample detail during development and testing while keeping log volume manageable in production. When combining profiles, logger hierarchy, externalized configuration, and secured Actuator endpoints, development teams can adjust visibility precisely where needed, maintain correlation with traces and metrics, and reduce operational risk from overly verbose logging.
