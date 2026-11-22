# Production Log Levels in Java Logging

## 1. Why choose different log levels in production?

**Production** is the environment where an application serves real users or real business workloads. In this environment, logs must help operate the system and diagnose incidents without slowing the system down, consuming excessive storage, or exposing sensitive data.

During development, developers may enable **DEBUG/TRACE** or **FINE/FINER/FINEST** to observe every execution branch in detail. In production, keeping that same level of detail across all components easily leads to the following problems:

- **Information noise:** Thousands of debug lines obscure the actual errors that need investigation.
- **Cost:** Logging consumes CPU to construct messages, buffer memory, I/O, network bandwidth, storage, indexing, and query costs.
- **Latency:** Synchronous logging configurations or excessive event volume can lengthen request processing times.
- **Data risk:** Accidentally logging tokens, passwords, request payloads, personal information, or payment data.
- **Operational difficulty:** Inconsistent log lines make dashboards, error-search queries, and alerts less effective.

A good log level policy has two goals: **keeping essential operational signals always available** and **allowing controlled diagnostic information to be enabled when needed**.

**A log level only indicates the priority of each record.** Whether an event requires paging an on-call engineer, opening an incident, or sending an alert also depends on business impact, urgency, and observability rules. You should not assume every ERROR/SEVERE line equals an incident that must wake up the operations team.

## 2. Choosing a default level for production

In many Java applications, the **INFO** threshold is a common starting point in production: it retains important operational events and filters out most detailed debug information. However, **INFO is not a mandatory value for every system**. Extremely high-traffic services, overly chatty third-party libraries, or specific compliance requirements may need per-package, per-class, and per-event-type configuration.

### Comparing JUL with the SLF4J ecosystem

Java includes **java.util.logging (JUL)** out of the box; systems using SLF4J can connect to backends such as Logback or Log4j 2. The two groups use different level names:

| General meaning | JUL | Commonly used in SLF4J/Logback | Production usage |
| --- | --- | --- | --- |
| Serious error | **SEVERE** | **ERROR** | Log genuine failures that require investigation, prioritizing sufficient appropriate evidence |
| Anomaly or risk | **WARNING** | **WARN** | Log slow dependencies, fallbacks, notable retries, risk of degradation |
| Important operational event | **INFO** | **INFO** | Startup, shutdown, job results, useful business milestones |
| Configuration | **CONFIG** | No separate equivalent level | Log safe configuration details when needed to verify how the app started |
| Diagnostics | **FINE** | **DEBUG** (approximate) | Usually disabled for most classes in production; enabled selectively during investigation |
| Detailed tracing | **FINER, FINEST** | **TRACE** (approximate) | Enable only in a very narrow scope and for a short duration |
| Filter control | **OFF, ALL** | Depends on API/backend | Not ordinary business event levels |

This table only compares **usage semantics**, not the exact technical mapping of every bridge. JUL also has a numeric priority order: **SEVERE(1000) > WARNING(900) > INFO(800) > CONFIG(700) > FINE(500) > FINER(400) > FINEST(300)**. When a Logger is set to **Level.INFO**, the standard levels **INFO, WARNING, SEVERE** pass the Logger threshold; lower levels are dropped. Filters on the Handler can still determine the final outcome.

### A common starting configuration

| Target | Illustrative threshold | Reason |
| --- | --- | --- |
| Application root logger | **INFO** | Visibility into key events, errors, and warnings |
| A dependency producing too much unhelpful logging | **WARNING** | Reduce noise while keeping noteworthy anomalies |
| A class with a hard-to-reproduce bug | **FINE/DEBUG** temporarily | Expand evidence in the exact right place |
| Low-level libraries/frameworks | **WARNING/INFO** depending on library | Avoid pushing internal details into business logs |
| Components handling secrets or sensitive data | Appropriate level **with redaction** | Changing levels alone does not protect data |
| Mandatory audit or security logs | Separate stream/policy | Do not rely solely on the root logger threshold to decide what to keep or drop |

**Do not disable all INFO logs just to cut costs** if INFO contains essential operational or audit events. First, reduce low-value logs, tune specific loggers precisely, use metrics for repetitive counts, and design appropriate retention.

## 3. What to log at each level in production?

### SEVERE / ERROR: failures with clear impact

Examples: a transaction cannot be completed, required data cannot be persisted, a critical feature stops working, or an important job fails after recovery steps.

An error log should state **which operation failed, where, why, and what the impact is**, attaching the exception when appropriate. Avoid logging the same exception at multiple layers if it represents a single incident.

**Not every exception is an ERROR.** A user input validation error or a valid "not found" result may be a normal business case. Conversely, data loss requires attention even if it happens only once.

### WARNING / WARN: anomalies where the system can still continue

Examples: a retry succeeds after a timeout, a dependency responds slowly, a cache fallback is used, or a suboptimal configuration has a safe fallback path.

If a warning repeats on every request at high throughput, it can flood the logs. Adjust where the event is emitted, rate-limit it, or use aggregated metrics/alerts; do not silently downgrade every meaningful warning just to save space.

### INFO: milestones that need regular observation

Examples: service version started, batch completed, key operational configuration selected, or an important transaction changed state after processing.

**Avoid turning INFO into a mirror of the entire execution flow.** For high-traffic endpoints, logging "start processing" and "end processing" for every request can generate massive volume. Typically, you should use dedicated access logs, tracing, or metrics according to your system's standards.

### FINE / DEBUG: details for investigation

Examples: which business branch was chosen, retry count, cache hit/miss, strategy selection result, or internal step duration.

This level is useful when reproducing difficult issues, but should generally be **disabled by default on classes that do not need active tracking**, especially in high-traffic production. DEBUG messages must still follow data protection rules; "not enabled often" is not an excuse to log secrets.

### FINER/FINEST / TRACE: very deep execution traces

Examples: individual loop iterations, individual parsing steps, many intermediate values, or very fine-grained internal interactions. These messages can produce orders of magnitude more logs than INFO and alter performance characteristics when enabled.

Prefer enabling **TRACE/FINEST** in test environments or on a single instance, a single package, or a controlled diagnostic session. If it must be enabled in production, you must define the scope, time limit, owner, volume limit, and rollback procedure.

## 4. Filtering mechanism: why might a log line still not appear after enabling DEBUG?

Log levels usually have multiple filtering layers. In JUL:

1. **Logger** has an effective level. Records below this threshold are typically blocked at the Logger immediately.
2. **Filter** on the Logger can reject a record even if its level meets the threshold.
3. **Handler** receives records along the configured route and has its **own threshold/Filter**.
4. **Formatter** determines the log line format; the **destination** can be console, file, or collector.

A typical mistake:

~~~java
logger.setLevel(Level.FINE);
// ConsoleHandler still has level INFO.
logger.fine("Chi tiet dieu tra");
~~~

The FINE line may not appear because the Handler is at INFO. For FINE to get through, **both the Logger and the receiving Handler must allow it**. In JUL, child loggers can forward records to parent logger Handlers (typically enabled by default); the parent logger's own level does not necessarily re-filter a record already accepted by the child logger, but the parent's Handler still has its own level/filter. Therefore, you must check the entire Handler chain and the **useParentHandlers** property.

Key points to remember:

- **Level.INFO** accepts INFO, WARNING, and SEVERE in JUL, unless a Filter/Handler drops them later.
- **Level.WARNING** accepts WARNING and SEVERE.
- **Level.FINE** extends down to FINE; it does not automatically allow FINER/FINEST.
- **Level.ALL** allows all standard levels at the configured point; **Level.OFF** blocks them.
- When a Logger has **setLevel(null)**, it inherits its effective threshold from its parent logger in the JUL logger hierarchy.
- To see class/package names, the Formatter or layout must be configured to output **logger name**; merely declaring a logger per class is not enough.

In SLF4J, the API calls **logger.debug(...)** or **logger.trace(...)**; the underlying backend and its appenders/filters decide whether the record is emitted. Therefore, you should not apply **Level.FINE** naming directly to SLF4J code.

## 5. Standalone Java 17 example: INFO by default, FINE per class when investigating

This example illustrates a common production strategy:

- Two Loggers named after classes: **app.orders.OrderService** and **app.payment.PaymentClient**.
- Both start at **INFO**.
- When investigating a payment issue, temporarily raise only the **PaymentClient** Logger to **FINE**.
- After the investigation, return that Logger to **INFO**; the order Logger still does not emit FINE.
- A custom Handler formats output to **stdout** so the execution result can be verified deterministically. This is a single-JVM simulation, not a centralized level-management system for all of production.

Create **ProductionLogLevelDemo.java**:

~~~java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ProductionLogLevelDemo {
    private static final Logger ORDER =
            Logger.getLogger("app.orders.OrderService");

    private static final Logger PAYMENT =
            Logger.getLogger("app.payment.PaymentClient");

    public static void main(String[] args) {
        Handler output = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (!isLoggable(record)) {
                    return;
                }

                System.out.println(
                        record.getLoggerName()
                        + " | " + record.getLevel().getName()
                        + " | " + record.getMessage());
            }

            @Override
            public void flush() {
                // Demo prints directly; there is no buffer to flush.
            }

            @Override
            public void close() {
                // Demo does not own resources to close.
            }
        };
        output.setLevel(Level.ALL);

        configure(ORDER, Level.INFO, output);
        configure(PAYMENT, Level.INFO, output);

        ORDER.info("Order request accepted");
        PAYMENT.fine("Initial payment details");
        PAYMENT.warning("Gateway response slow");

        System.out.println("--- Scoped diagnostics ---");
        PAYMENT.setLevel(Level.FINE);
        PAYMENT.fine("Gateway retries=2");
        ORDER.fine("Order internal validation");

        System.out.println("--- Restore baseline ---");
        PAYMENT.setLevel(Level.INFO);
        PAYMENT.fine("Hidden after restore");
        PAYMENT.info("Payment recovered");

        ORDER.removeHandler(output);
        PAYMENT.removeHandler(output);
        output.close();
    }

    private static void configure(Logger logger, Level level, Handler output) {
        logger.setUseParentHandlers(false);
        logger.setLevel(level);
        logger.addHandler(output);
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 ProductionLogLevelDemo.java
java ProductionLogLevelDemo
~~~

**Exact stdout:**

~~~text
app.orders.OrderService | INFO | Order request accepted
app.payment.PaymentClient | WARNING | Gateway response slow
--- Scoped diagnostics ---
app.payment.PaymentClient | FINE | Gateway retries=2
--- Restore baseline ---
app.payment.PaymentClient | INFO | Payment recovered
~~~

Explanation:

1. At **INFO**, the call **PAYMENT.fine("Initial payment details")** is ignored; the **WARNING** record is still emitted.
2. When **PAYMENT.setLevel(Level.FINE)** is set, the PaymentClient FINE line appears.
3. **ORDER.fine("Order internal validation")** remains blocked because ORDER stays at INFO.
4. After restoring PAYMENT to INFO, new FINE lines from PAYMENT are blocked again.
5. The demo Handler is set to **Level.ALL** so it does not drop records accepted by the Logger; **setUseParentHandlers(false)** prevents duplicate output from parent Logger Handlers.
6. Output uses **System.out** intentionally; JUL's default **ConsoleHandler** writes to **stderr**. In real deployments, let logging configuration manage Handlers, formatting, and collection destinations.

**This is an in-memory level change within a single process.** If a service runs across multiple JVMs or pods, **setLevel(...)** in one JVM does not automatically apply to other JVMs, nor does it persist across process restarts. Dynamic level-change mechanisms in production must have access control, scoping, expiration, and a way to revert configuration to baseline.

## 6. Configuring production JUL with logging.properties

In systems using **java.util.logging**, logger and Handler thresholds can be configured from a properties file. Example:

~~~properties
# logging.properties
handlers = java.util.logging.ConsoleHandler

# Default level for the root Logger
.level = INFO

# Handler must accept FINE if enabling FINE per class
java.util.logging.ConsoleHandler.level = FINE
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter

# Details for the class under investigation
com.example.payment.PaymentClient.level = FINE

# Overly noisy library: keep only warnings and errors
com.vendor.chatty.level = WARNING
~~~

This configuration illustrates an application where the PaymentClient Logger is named **com.example.payment.PaymentClient**. The root Logger is at INFO, while that specific Logger is set to FINE and ConsoleHandler allows FINE through. Thus, detailed logs can appear exclusively for that logger. Always use the actual logger name; a framework may name loggers differently from Java packages.

You can instruct the JVM to load JUL configuration from the file at startup:

~~~bash
java -Djava.util.logging.config.file=logging.properties -cp out com.example.Main
~~~

The command above is an **example for running a compiled application** whose main class is **com.example.Main**, not the command to run the **ProductionLogLevelDemo** from section 5. When using a configuration file, the application should also avoid programmatically overriding levels/Handlers elsewhere in code, or actual behavior may differ from expectations.

In real projects, do not leave FINE enabled long-term after a one-off investigation. When finished, change it back:

~~~properties
com.example.payment.PaymentClient.level = INFO
~~~

Or remove the specific entry so the class inherits its threshold from the parent Logger, provided the logger naming hierarchy has been verified. **Editing the file on disk does not necessarily change log levels in a running JVM**; dynamic updates require an explicit reload mechanism or configuration management system that supports it. Otherwise, changes may only take effect after a restart following operational procedures.

## 7. Using Spring Boot/SLF4J in production

In projects using **Spring Boot** with a compatible logging setup, you can configure levels per package or class via **logging.level** properties. Example **application.properties**:

~~~properties
logging.level.root=INFO
logging.level.com.example.orders=INFO
logging.level.com.example.payment.PaymentClient=DEBUG
logging.level.com.vendor.chatty=WARN
~~~

In this case:

- **root=INFO:** General baseline.
- **com.example.orders=INFO:** Keeps the operational threshold for the orders package.
- **PaymentClient=DEBUG:** Enables diagnostics specifically for the payment client.
- **com.vendor.chatty=WARN:** Suppresses unnecessary INFO lines from a specific dependency.

This is a **Spring Boot configuration example**, not raw JUL configuration, and the **DEBUG/WARN** level names match the logging system managed by Spring Boot. Libraries that log via JUL may need a bridge or appropriate configuration to converge into the shared backend. Do not mix JUL configuration syntax with another backend's syntax without clearly understanding the pipeline.

In some Spring Boot versions/configurations, the **Actuator loggers endpoint** can view or change levels at runtime. If used, you must explicitly enable and secure the endpoint with authentication, authorization, network restrictions, and auditing; **never assume the endpoint exists or is accessible in production by default**. Activation details depend on the application version and deployment policy.

File-based configuration is suited for long-term baselines; runtime change mechanisms are suited for managed, short-term investigations. If a runtime level is changed, there should be an owner, an expiration time, a way to synchronize across instances, and a way to revert to the baseline.

## 8. Safe procedure for enabling detailed logs during a production incident

Scenario: PaymentClient occasionally reports timeouts that cannot be reproduced in staging. The right response is not necessarily enabling DEBUG across all services.

**Step 1 — Define the investigation question.**

For example: does the timeout occur before sending the request, while waiting for a connection, or after the third retry? Identify which fields or events are needed to answer the question.

**Step 2 — Identify the exact logger.**

Find the logger name **com.example.payment.PaymentClient** or a narrowly relevant package group. If there are multiple JVMs or instances, identify which instance is failing and the scope of the change.

**Step 3 — Assess cost and potential data exposure.**

Estimate events per second, log size, and payload sensitivity. Do not enable DEBUG if the code might print full authorization headers, tokens, or payment data. Updating the logger to redact or omit sensitive data must come before expanding the log level.

**Step 4 — Enable only the needed level for a limited duration.**

Start with **DEBUG/FINE**, and only escalate to **TRACE/FINER/FINEST** if necessary. Record who made the change, start time, specific logger, and end time. With multiple instances, ensure the adjustment method matches your deployment architecture; avoid a state where only part of the fleet has changed levels without the investigation team knowing.

**Step 5 — Monitor signals and impact.**

Watch error rates, p95/p99 latency, CPU, I/O, log volume per second, pipeline lag, and signs of dropped logs. If enabling debug degrades the system, stop or narrow the scope.

**Step 6 — Collect enough evidence, then restore the baseline.**

Disable detailed logging once the question is answered or the time limit expires, even if the incident is still ongoing if logging is causing excessive cost. Verify that all instances have returned to the expected level.

**Step 7 — Improve long-term observability.**

If the incident recurs, improve **structured events**, metrics, traces, tests, and runbooks. Do not leave system-wide DEBUG enabled permanently to compensate for insufficient observability.

## 9. Performance and cost related to log levels

### Cost is not only in the number of lines written

When a log call is blocked by its level, the system can avoid many record-processing steps. However, **expressions passed into the Java call are still evaluated before the method is invoked** if the developer builds strings or calls expensive functions beforehand.

Example that wastes resources even when FINE is disabled:

~~~java
logger.fine("Expensive state: " + generateLargeDebugReport());
~~~

The snippet above is an **illustration inside a class that has a logger and a generateLargeDebugReport() method**. The report-generation function is evaluated before the logger call executes.

With JUL, you can use a **Supplier**:

~~~java
logger.log(
        Level.FINE,
        () -> "Expensive state: " + generateLargeDebugReport()
);
~~~

Or check before performing the computation:

~~~java
if (logger.isLoggable(Level.FINE)) {
    String report = generateLargeDebugReport();
    logger.fine("Expensive state: " + report);
}
~~~

These APIs avoid constructing expensive payloads when the Logger blocks FINE. However, a Handler or Filter can still drop the record later; checking **isLoggable** on the Logger does not guarantee the record will ultimately be written to disk.

In SLF4J, use **{}** placeholders instead of eager string concatenation when appropriate:

~~~java
log.debug("Payment attempt={}, state={}", attempt, state);
~~~

This snippet assumes an SLF4J Logger is declared in the class. Passing arguments through the API like this generally avoids string formatting when DEBUG is disabled. If you invoke an expensive function to compute an argument, that function is still evaluated before the call, so use a guard or corresponding lazy API.

### Volume estimation example

Suppose there are **1,000 requests/second**. Enabling extra DEBUG logging generates **3 lines per request**, averaging **500 bytes per line**:

~~~text
1,000 requests/s × 3 logs/request × 500 bytes/log
= 1,500,000 bytes/s
≈ 129.6 GB/day (decimal GB)
~~~

This is only the **additional raw data generated** assuming steady load for 24 hours; it excludes metadata, indexing, replication, multi-tier storage, and query costs. Actual figures depend on traffic, record size, compression, sampling, and collection methods. That is why enabling debug for a few minutes on one class is vastly different from enabling it on every request for days.

### Synchronous and asynchronous logging

Some backends support asynchronous logging to reduce I/O wait time on business-logic threads. However, queues can fill up or records can be lost if the JVM crashes; backpressure handling and reliability policies must be chosen per log category.

Detailed operational logs can use sampling or rate limiting, but **error, security, and audit logs** must be evaluated separately because improper sampling can lose evidence or skew error-rate statistics. Counts used for SLOs should generally come from **metrics**, rather than assuming logs are always 100% complete.

## 10. Designing searchable and operable production logs

Beyond the level, a production log record should carry consistent context. Depending on the system, useful fields typically include:

| Field | Purpose |
| --- | --- |
| **timestamp** | When the event occurred; should include an explicit timezone, usually UTC |
| **level** | INFO/WARN/ERROR or corresponding JUL level |
| **service / environment** | Identifies the service and production/staging |
| **logger_name** | Class/package name emitting the event |
| **event_code** | Stable event code independent of wording |
| **trace_id / request_id** | Correlates events within a single request |
| **operation / outcome** | Identifies the operation and result |
| **exception type / stack trace** | Diagnoses errors when needed |
| **release / instance** | Compares across versions and instances |

Illustrative structured log example:

~~~json
{
  "timestamp": "2026-11-09T10:15:00Z",
  "level": "ERROR",
  "service": "checkout",
  "environment": "production",
  "logger_name": "com.example.payment.PaymentClient",
  "event_code": "PAYMENT_PROVIDER_TIMEOUT",
  "trace_id": "trace-123",
  "operation": "authorize",
  "outcome": "failed",
  "message": "Payment provider timeout after retry"
}
~~~

This is a **JSON example**, not JUL's default format. To emit JSON, you need an appropriate Formatter/encoder and configuration. Fields like `trace_id` should be generated and propagated by your project's tracing/context mechanism; raising the log level alone does not produce them.

**Data principles:** collect only what is necessary, minimize personal identifiers, mask or strip secrets before writing, and set appropriate retention and access controls. Avoid logging full requests/responses for every request even at DEBUG. Once a secret enters the log pipeline, purging all copies can be harder than fixing the application code.

## 11. How do levels relate to monitoring and alerting?

**Log levels are a filtering mechanism; alerts are an operational decision.** Do not design paging rules around "send an alert whenever ERROR appears."

A service might emit many WARN logs during successful retries with zero user impact. Conversely, a sudden drop in INFO logs to zero might mean a scheduled job stopped running. Reliable alerts should be based on clear impact such as **error rate, latency, task success rate, heartbeats, or verified business events**, paired with logs to find the root cause.

Example classification:

| Situation | How to log | Appropriate incident detection |
| --- | --- | --- |
| Dependency call fails after all retries | ERROR/SEVERE and relevant exception | Failed request rate, SLO, circuit breaker |
| First retry fails, next succeeds | WARN or DEBUG per convention | Retry metrics and increased latency |
| Nightly job fails to run | May produce no error log | Job heartbeat, schedule check, timeout threshold |
| Login rejected due to wrong password | Safe log per security policy | Frequency analysis, behavior patterns, account protection |
| DEBUG enabled on a class for investigation | Temporary DEBUG/FINE | Track cost and diagnostic expiration time |

If you raise the threshold from INFO to WARNING, INFO events previously used by dashboards or alerts may disappear. Before lowering verbosity, audit **which queries, alerts, and audits actually depend on those logs**. A better approach may be keeping key events, removing low-value logs, and creating dedicated metrics.

## 12. Common mistakes

1. **Enabling DEBUG/TRACE across all of production long-term.** Creates noise, increases costs, and can expose more data than necessary.
2. **Lowering all loggers to ERROR to save money.** Loses useful operational events and can break dashboards or alerts.
3. **Confusing Logger thresholds with Handler/appender thresholds.** The Logger may be at FINE while the output destination still blocks FINE.
4. **Not setting an expiration for runtime changes.** A temporary investigation turns into an expensive configuration lasting weeks.
5. **Changing only one instance without realizing there are multiple instances.** Data becomes inconsistent and the investigation team can draw wrong conclusions.
6. **Not controlling sensitive data at DEBUG.** Temporary logs can still be centralized and retained for a long time.
7. **Concatenating strings or building expensive payloads before the log call.** Even when the level is off, CPU still processes the data.
8. **Logging the same exception at every layer.** Causes duplicate records and inflates error counts.
9. **Equating ERROR with paging.** Generates too many false alerts; actual impact must be evaluated.
10. **Renaming loggers during refactoring without updating configuration.** Rules tied to old class/package names stop working.
11. **Relying solely on the absence of error logs to conclude the system is healthy.** A dead process or broken log pipeline emits no new events.
12. **Using logs as a substitute for metrics or traces.** Telemetry types complement each other and serve distinct purposes.

## 13. Checklist for applying log levels in production

Before deploying:

- Identify the **logging API and backend** in use: JUL, SLF4J + Logback, Log4j 2, or a bridge.
- Choose an application baseline, typically starting at **INFO**, then refine based on real observations.
- Use consistent **logger names** by class/package to allow narrow-scoped adjustments.
- Ensure **Logger, Handler/appender, Filter, and collector** configurations are aligned.
- Distinguish **key business events**, genuine errors, recoverable anomalies, and diagnostic traces.
- Protect **secrets/PII**, with defined retention and access permissions.
- Set up appropriate **metrics/alerts** so you do not depend on raw log line counts.
- Establish a process for **temporary verbose logging**, including expiration, policy-compliant approval, and rollback.
- Monitor **log volume, cost, throughput, and latency** when changing levels.
- Verify dashboards and alert rules after changing log levels.

## 14. Self-check questions

1. **Is production required to use the WARN level?** No. INFO is a common starting point; the final level depends on observability needs, noise, cost, and specific configuration.
2. **Does enabling FINE for PaymentClient mean every FINE record will appear?** No. Handlers, Filters, and the record-routing chain can still drop them.
3. **Is DEBUG automatically safe if enabled for only a few minutes?** No. Sensitive data can still be collected and retained.
4. **Does calling setLevel(Level.FINE) on one JVM change other JVMs?** No; you need centralized configuration management or separate actions matching your deployment design.
5. **How much data does a system at 1,000 requests/second generate if it adds 3 logs × 500 bytes per request?** Roughly 1.5 MB/second, or 129.6 GB/day of raw data if the load remains constant.
6. **When DEBUG is disabled, does generateLargeDebugReport() in string concatenation before a logger call still run?** Yes; use a Supplier or an `isLoggable` check in JUL.
7. **Is every ERROR necessarily an urgent alert?** No. Alerts must be based on impact, urgency, and actionability.

**Key takeaway:** Managing log levels in production is not just about choosing INFO or WARN. You need to preserve operationally valuable events, avoid logging redundant or sensitive data, understand all filtering layers, and have a mechanism to enable detailed logging for the right class over a limited time window. When an investigation ends, restore the baseline threshold and continue using metrics, traces, and logs together to observe the system.
