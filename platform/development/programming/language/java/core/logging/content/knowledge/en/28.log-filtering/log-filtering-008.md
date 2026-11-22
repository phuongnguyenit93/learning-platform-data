# Dropping Unnecessary Logs in Java Core Logging

## Lesson Objectives

The topic **Filtering → Dropping Unnecessary Logs** helps you reduce redundant log volume in Java applications while retaining sufficient data to diagnose errors, monitor system health, and meet audit requirements. After this lesson, you will be able to:

- Identify which logs should be dropped, kept, sampled, or aggregated instead of logging every single event.
- Choose the right place to filter: before creating the log event, at the logger, at the appender, or at the collector.
- Understand the difference between **intentional filtering** and **unintentional log loss** when a queue/collector is overloaded.
- Use log levels, package-specific loggers, conditional filters, sampling, and rate limiting.
- Write a standalone Java 17 example using `java.util.logging.Filter` and apply the same mindset to SLF4J, Logback, and Log4j 2.
- Measure log reduction effectiveness while verifying that warnings, exceptions, critical transactions, and traceability are preserved.

**Principle:** Only drop logs when you clearly understand the reason and scope. Saving CPU, I/O, storage, and search costs is a valid goal; hiding errors or audit data can make the system much harder to operate than the cost saved.

## 1. What Does “Dropping Unnecessary Logs” Mean?

**Dropping** here means deciding **not to emit or not to store** a log event because its value is low compared to its cost. For example, a health check probe returns `200 OK` every second; logging each check as an `INFO` line can generate millions of identical lines, whereas **failed** checks need to be logged.

There are different forms of log reduction:

| Form | Example | Consequence |
| --- | --- | --- |
| **Suppress by log level** | Disable `DEBUG` for an HTTP library during normal operation | Log calls below the threshold do not create full events in the logging pipeline (Java argument evaluation costs may still occur). |
| **Conditional drop** | Drop `INFO healthcheck.ok`, keep `WARN healthcheck.failed` | Excludes a specific event type by package, marker, or event code. |
| **Sampling** | Log only about 1% of successful requests | Reduces statistical log volume, but individual successful events are no longer complete. |
| **Rate limiting** | Limit repeated logs of an auxiliary error while counting suppressed occurrences | Controls log storms, but must preserve the error signal and total occurrence count. |
| **Aggregation** | Replace 10,000 “cache hit” lines with a metric/cache hit count | Preserves aggregate information, loses per-event detail. |
| **Routing/filtering by sink** | Audit events go to an audit store, other technical logs go to stdout | An event may be dropped at one appender while still being stored at another destination. |
| **Drop due to full queue/pipeline failure** | Async appender discards events or collector is overloaded | This is operational data loss that must be measured/alerted on; do not confuse it with an approved filtering policy. |

Saying “we dropped 90% of logs” is not enough to evaluate success. You need to know whether that 90% was useless `DEBUG` noise or `ERROR` events, whether the remaining logs still support tracing, and whether there is visibility into the volume of dropped events.

### Which Logs Can Usually Be Reduced?

- `DEBUG` logs inside hot loops, continuous polling, or normal cache lookups.
- Repetitive **successful** health/readiness check messages when success counts/rates are already reflected in metrics.
- Third-party libraries printing excessive `INFO`-level information that the application does not use for diagnostics.
- “Entering method” / “exiting method” logs for every call, especially when proper tracing/profiling is already in place.
- Duplicate logs caused by the same exception being logged at multiple layers of the same processing path.
- High-volume success events with low per-event diagnostic value that are already covered by other observability mechanisms.

### Which Logs Must Not Be Dropped Indiscriminately?

- `ERROR` events related to actual failures, critical state changes, or incomplete transactions.
- Warnings about resources, timeouts, exhausted retries, integration failures, and abnormal behavior requiring investigation.
- Security alerts, unauthorized access attempts, policy violations, and events required for regulatory compliance.
- Mandatory audit trails, especially when integrity, durable storage, and auditability are required.
- Essential correlation information such as trace ID/request ID used to link error chains.

Detailed logs can sometimes be genuinely critical during an investigation. Therefore, log levels and filters should be configurable by environment, package, and time window, with testing before release.

## 2. Where Does Filtering Happen in the Pipeline?

Conceptual pipeline:

```text
Application / library
    |
    |  1. Check level or decide not to call logger
    v
Logger / early filter
    |
    |  2. Create LogRecord/LoggingEvent, capture context
    v
LoggerConfig / appender filter
    |
    |  3. Encode, format, enqueue if async
    v
Console / file / network appender
    |
    |  4. Agent / collector / ingest filter
    v
Storage / search / dashboard
```

Stage names and exact locations vary across JUL, Logback, Log4j 2, and async configurations. However, the cost rule is general: **the earlier you filter, the more downstream work you avoid**.

- Filtering before event creation saves event allocation, MDC/context capture, serialization, and enqueuing.
- Filtering at the appender saves writing to that sink, but the application may have already paid the cost of creating the event; if there are multiple appenders, the event may still appear in another appender.
- Filtering at the collector reduces storage/indexing, but the application has already formatted and transmitted bytes over the network or stdout; it does not eliminate producer cost.
- Log level is a simple and highly effective first layer of filtering for verbosity.
- Filtering by event code, marker, or logger name is more reliable than parsing free-form formatted message strings.

### Costs That Still Exist Even When a Log Is Dropped

Java evaluates arguments before invoking a method. The following example still runs the expensive function even if `DEBUG` is disabled:

```java
logger.debug("state=" + expensiveToString());
```

Parameterized logging avoids eager string concatenation, but the argument expression is still evaluated:

```java
logger.debug("state={}", expensiveToString());
```

If computing the data is expensive, wrap it in a log level check:

```java
if (logger.isDebugEnabled()) {
    logger.debug("state={}", expensiveToString());
}
```

This is an **illustrative snippet** using the SLF4J API and requires SLF4J dependencies and a backend to run. With SLF4J 2's fluent API, you can also use a lazy supplier compatible with your backend, though you should verify that the supplier is actually evaluated lazily and does not perform work beforehand. Avoid building JSON strings, stack traces, or large object dumps only to filter out the event at the end of the pipeline.

## 3. Filtering by Log Level and Package/Logger

Common levels in SLF4J/Logback/Log4j 2 in increasing order of severity are: `TRACE < DEBUG < INFO < WARN < ERROR`. If a logger has an effective level of `INFO`, normal `TRACE` and `DEBUG` logs are discarded; `INFO`, `WARN`, and `ERROR` are evaluated further depending on filters/appenders. Frameworks may support `OFF` to disable logging or `ALL` to accept all levels.

For Java Util Logging (JUL), common levels include `FINEST`, `FINER`, `FINE`, `INFO`, `WARNING`, and `SEVERE`; the names and configuration differ. Do not assume JUL has `DEBUG` or `ERROR` constants.

Example Spring Boot configuration for an application using SLF4J:

```yaml
logging:
  level:
    root: INFO
    org.hibernate.SQL: WARN
    org.apache.http: WARN
    com.example.checkout: INFO
    com.example.checkout.diagnostics: DEBUG
```

This is an `application.yml`/`application-staging.yml` snippet, **not a standalone Java application**. Library package names and logger hierarchies may vary by dependency/version. What it does:

1. Sets root to `INFO` to reduce system-wide verbose logging.
2. Restricts noisy SQL/HTTP logs to `WARN` in environments where needed, while keeping warnings and errors.
3. Enables `DEBUG` only for the diagnostics package currently under investigation, then reverts it once done.
4. Log levels apply per logger, whereas event filters can handle records that share the same level but have different operational value.

**Do not arbitrarily set `root: ERROR` to “reduce logs.”** Doing so can suppress `WARN` signals, startup/configuration messages, or useful diagnostic information. Start by profiling which loggers emit the most events.

## 4. Conditional Dropping: Event Code, Marker, Context

When the same `INFO` level contains both repetitive “healthcheck succeeded” and “order created” messages, disabling all `INFO` logs is too broad. Instead, use stable conditions:

```text
IF level == INFO
   AND logger == "com.example.monitor.HealthProbe"
   AND event_code == "healthcheck.ok"
THEN DROP
ELSE KEEP
```

A good practice is an **exact-condition allowlist/filter** for low-value events, rather than `message.contains("health")`. Free-text substring conditions can accidentally drop `healthcheck.failed` or error lines containing similar keywords.

If the framework supports **markers** or structured key-value pairs, emit events with stable codes such as `event=healthcheck.ok` or `event=cache.hit`. Context fields like `service`, `environment`, `component`, or HTTP status can serve as secondary criteria, keeping in mind that MDC/tracing may not yet be set at filter time and can change across async boundaries.

**Where a filter is placed determines its scope:**

- Logger-level/global filter: can block an event across all applicable appenders.
- Appender-level filter: controls events only for that appender; another appender may still log them.
- Agent/collector rule: affects stored and queried data, but still consumes application CPU and transport bandwidth before the collector.

If the system has a dedicated audit store, never apply a global filter that drops audit events just to reduce technical logs. Separate the pipelines or classification criteria and verify across all output destinations.

## 5. Standalone Java 17: Dropping Successful Heartbeats with a JUL Filter

The following program requires only JDK 17+—no Maven, Spring Boot, or SLF4J dependencies. It demonstrates **two filtering layers**:

1. `Logger.setLevel(Level.INFO)` drops `FINE` logs before invoking `Filter`.
2. `Logger.setFilter(...)` drops only the `INFO healthcheck.ok` event, while keeping business logs and healthcheck failure warnings.

The `droppedByFilter` counter confirms that exactly one event was filtered conditionally. This counter **does not count** the `FINE` event that was already excluded by level before `Filter` ran; therefore, a single counter cannot be treated as the total number of events “the application attempted to log but did not store” in all cases.

Create the file **`DropUnnecessaryLogsDemo.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class DropUnnecessaryLogsDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.filtering");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        AtomicInteger droppedByFilter = new AtomicInteger();
        logger.setFilter(record -> {
            boolean noise =
                    record.getLevel().equals(Level.INFO)
                    && "healthcheck.ok".equals(record.getMessage());

            if (noise) {
                droppedByFilter.incrementAndGet();
            }
            return !noise;
        });

        Handler stdout = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println(
                            record.getLevel().getName()
                            + " event=" + record.getMessage());
                }
            }

            @Override
            public void flush() {
            }

            @Override
            public void close() {
            }
        };
        stdout.setLevel(Level.ALL);
        logger.addHandler(stdout);

        try {
            logger.fine("cache.detail");
            logger.info("healthcheck.ok");
            logger.info("order.created");
            logger.warning("healthcheck.failed");
            logger.severe("payment.unavailable");
        } finally {
            logger.removeHandler(stdout);
            stdout.close();
            logger.setFilter(null);
        }

        System.out.println("droppedByFilter=" + droppedByFilter.get());
    }
}
```

Compile and run:

```bash
javac DropUnnecessaryLogsDemo.java
java DropUnnecessaryLogsDemo
```

**Exact stdout**:

```text
INFO event=order.created
WARNING event=healthcheck.failed
SEVERE event=payment.unavailable
droppedByFilter=1
```

Explanation:

- `logger.fine("cache.detail")` is not printed because the logger's effective level is `INFO`. This event does not pass through the custom filter, so the counter is not incremented.
- `logger.info("healthcheck.ok")` passes the level check but the filter returns `false`, so it is not forwarded to the `Handler`.
- `logger.info("order.created")`, `logger.warning("healthcheck.failed")`, and `logger.severe("payment.unavailable")` are kept. The condition **only** excludes a specific `INFO` success event.
- `setUseParentHandlers(false)` prevents events from propagating to parent handlers (avoiding duplicate output from the default JUL root handler). The custom handler prints to `System.out` without timestamps, keeping the output deterministic.
- `Handler.isLoggable(record)` respects the handler's own level/filter; in this example, the handler accepts all remaining levels because of `Level.ALL`.
- `finally` removes the handler and filter installed by the program. Modifying global/shared logger configuration in a real application should be managed at startup so concurrent threads do not unexpectedly observe changing configuration.

**Experiment:** Change `"healthcheck.ok"` to `"healthcheck.failed"` in the filter condition to see whether the warning log is kept. Because the filter also requires `INFO` level, the `WARNING healthcheck.failed` warning is still preserved. This illustrates the value of conditioning on both **level and event code**.

The takeaway from this example is **filtering a known log pattern**, not automatically guessing which logs are “unnecessary.” A JUL `Filter` receives `LogRecord` after the level check; in other frameworks, interception can happen earlier.

## 6. Logback: Appender Filters and TurboFilters

When an application uses **SLF4J + Logback**, Logback Classic provides two key mechanisms:

- **Regular Filter** on an appender: receives an already-created `ILoggingEvent` and returns `DENY`, `NEUTRAL`, or `ACCEPT`. Suitable when you want one sink to drop an event while still allowing another sink to receive it.
- **TurboFilter**: attached to the logging context and evaluated before creating an event on many logger call paths. It can save more event creation/capture overhead by dropping logs at the source.

Meaning of the three filter decisions in Logback:

| Result | Behavior |
| --- | --- |
| `DENY` | Drops the event at that filtering stage, skipping subsequent filters in that chain. |
| `NEUTRAL` | Makes no decision; continues evaluating the next filter or default logic. |
| `ACCEPT` | Accepts at that stage, skipping subsequent filters in the same chain; scope of effect depends on placement. |

**Note:** `ACCEPT` does not mean bypassing every filter and every sink in the pipeline. An event can pass a filter at one layer and still be blocked at another. Depending on code and configuration, a filter may apply to the entire logger context or only to a single appender.

### Example Regular Filter Dropping Only INFO healthcheck.ok

This is a **Logback integration** class and requires compatible `logback-classic`/`logback-core`/SLF4J dependencies on the classpath. It is not pure JDK code.

Create the file `src/main/java/com/example/logging/IgnoreHealthSuccessFilter.java`:

```java
package com.example.logging;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.filter.Filter;
import ch.qos.logback.core.spi.FilterReply;

public class IgnoreHealthSuccessFilter
        extends Filter<ILoggingEvent> {

    @Override
    public FilterReply decide(ILoggingEvent event) {
        if (event.getLevel() == Level.INFO
                && "com.example.monitor.HealthProbe"
                        .equals(event.getLoggerName())
                && "healthcheck.ok".equals(event.getMessage())) {
            return FilterReply.DENY;
        }
        return FilterReply.NEUTRAL;
    }
}
```

A complete `logback.xml` snippet for a simple appender configuration:

```xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <filter class="com.example.logging.IgnoreHealthSuccessFilter"/>

        <encoder>
            <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

How it works:

1. The logger `com.example.monitor.HealthProbe` emits an `INFO` message with the exact template `healthcheck.ok`.
2. The filter returns `DENY` before the event reaches the `STDOUT` appender's encoder; the message does not appear on this console.
3. A `WARN healthcheck.failed` or `ERROR` from the same logger is still processed normally because the condition does not match.
4. If the configuration has another appender **without** this filter, an event dropped at `STDOUT` may still be written to that other appender. Always verify all sinks when designing filters.
5. Comparing `event.getMessage()` generally checks the **raw message template** in Logback. When using parameterized messages, avoid building fragile rules based on formatted output.

This is an illustrative example using a literal event string. In real projects, use consistent **structured event codes/markers** and test against real appenders. Do not rely on `message.contains("ok")` or broad regexes that can accidentally drop important events.

### When Do You Need a TurboFilter?

If success logs are called thousands of times per second, a regular filter runs **after** the event is created, so allocation and event-capture costs remain. A `TurboFilter` can decide earlier based on logger name, level, marker, format template, or parameters. For example, a `TurboFilter.decide(Marker, Logger, Level, String, Object[], Throwable)` implementation can return `DENY` when:

```text
level = INFO
loggerName = "com.example.monitor.HealthProbe"
messageTemplate = "healthcheck.ok"
```

A `TurboFilter` has a broader scope than an appender filter, so check its impact on destinations that must retain events. Additionally, it cannot undo the cost of **Java expressions evaluated before calling the logger**. When filter logic is complex, measure CPU and allocations; the filter itself can become a bottleneck.

## 7. Log4j 2: Choosing the Right Filtering Layer

Log4j 2 allows placing filters at layers such as global Logger, `LoggerConfig`, `AppenderRef`, and `Appender`. Common filters include level/threshold, marker, and context-based filters appropriate for the version in use.

Log4j 2 also uses `ACCEPT`, `DENY`, and `NEUTRAL` results; their exact meaning depends on the layer. At some stages, `ACCEPT` can bypass that stage's level check, so do not configure an overly broad global `ACCEPT` assuming other levels will still be blocked as before. According to Log4j 2 documentation, filtering earlier in the pipeline generally saves more overhead than filtering at the appender after the event has been created.

Example **Log4j 2 XML** configuration using only logger thresholds:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="Console" target="SYSTEM_OUT">
            <PatternLayout
                pattern="%d{ISO8601} %-5level %logger - %msg%n"/>
        </Console>
    </Appenders>

    <Loggers>
        <Logger name="org.hibernate.SQL"
                level="warn"
                additivity="false">
            <AppenderRef ref="Console"/>
        </Logger>
        <Root level="info">
            <AppenderRef ref="Console"/>
        </Root>
    </Loggers>
</Configuration>
```

This example **does not automatically drop `healthcheck.ok` events**; it sets the `org.hibernate.SQL` logger to `WARN` to reduce routine SQL output. To drop by event type, add a conditional filter at the appropriate layer and verify against the exact version/plugins you are using.

Log4j 2 provides rate-limiting mechanisms such as `BurstFilter`. However, the level threshold, `rate`, and `maxBurst` settings determine which events are throttled; you must specifically test warnings and critical errors. Never copy a rate-limit configuration from one environment to another without verifying that `ERROR` and security events remain intact.

## 8. Sampling and Rate Limiting: Reducing Volume While Keeping Signal

**Sampling** selects a subset of events to log. **Rate limiting** caps how frequently events are allowed to be logged. They address high log volume in different ways.

| Scenario | Approach | Risk to Manage |
| --- | --- | --- |
| 100,000 successful requests/minute | Controlled sampling, keeping metrics that count all requests | Per-request logs are no longer complete; the sample may be biased. |
| A health probe succeeding every second | Drop success details, keep counters/rates and failure logs | No per-success detail, which is usually acceptable. |
| An exception repeating thousands of times/second | Rate-limit detailed records, emit separate aggregate counts/alerts | Can miss changes in error behavior if grouped by too broad a key. |
| Step-by-step retries | Log when retry policy starts, retries are exhausted, state transitions, and total retry count | Loses per-attempt detail if no complementary tracing/metrics exist. |
| Transaction audit | Do not sample arbitrarily; design an audit store that meets requirements | Missing events can break reconciliation. |

### 8.1. When Sampling, Know What “1%” Is 1% Of

- Random per-event sampling does not guarantee that every observed transaction has all its related logs.
- **Consistent sampling by trace ID** keeps logs belonging to the same selected trace together, which is helpful for end-to-end debugging; policy exceptions can still apply for `ERROR` or special events. Trace sampling and log sampling are not the same mechanism and must be designed explicitly.
- If using hash/modulo on an ID for sampling, use a stable hash with uniform distribution and handle missing IDs; do not use part of an ID as a threshold without understanding its distribution.
- Do not measure latency or error counts solely from sampled events and assume the whole system is healthy. Separate metrics must track total event volume.

Example policy expressed as conditions, not direct framework syntax:

```text
if event.level in {ERROR, WARN}:
    keep
else if event.type == "healthcheck.ok":
    drop
else if event.type == "request.success":
    keep only when stableHash(traceId) falls into selected 1%
else:
    keep according to configured log level
```

This is **policy pseudocode**. If `WARN` volume becomes high enough to require throttling, consider designing separate alerts/aggregations based on business meaning rather than turning all `WARN` events into droppable logs.

### 8.2. Key-Based Rate Limiting

A token bucket or leaky bucket can limit logs to `N` per second per event group. The key should be based on error type, component, or a stable event code. Including per-request user IDs or trace IDs in the key can cause cardinality to explode, making rate limiting ineffective and consuming excessive memory.

When throttling, also record the **number of suppressed events** as a metric or periodic summary log. For example:

```text
WARN event=downstream-timeout detail=first-occurrence
WARN event=downstream-timeout-summary suppressed=124 interval=60s
```

These lines are structured examples, **not default output**. Do not implement a counter by emitting a log for every dropped log; that recreates a log storm. Counters must be thread-safe when multiple requests emit events concurrently, and metric label cardinality must be kept bounded.

## 9. Avoid Confusing Intentional Filtering with Log Loss from Async Overflow

An async appender has a bounded queue. When the sink slows down or volume spikes, the queue can fill up. Depending on framework configuration, the producer may **block**, drop events, discard lower-level events, or fall back to synchronous logging. This is **backpressure/overload**, not the same as a filter intentionally dropping `healthcheck.ok`.

In a system using async logging, track separately:

- `filtered_by_policy`: events dropped by rules intentionally configured by the team, by event type/level.
- `sampled_out` or `rate_limited`: events excluded by sampling or rate-limiting policies.
- `queue_dropped` / `appender_errors`: events lost due to overload or runtime errors.
- `emitted`, `accepted`, `written`, or collector-ingested counts, with clear definitions for each checkpoint.
- `queue_depth`, `enqueue_block_duration`, `sink_write_latency`, and `end_to_end_visibility_latency`.

Not every framework exposes these counters out of the box. You may need instrumentation at call sites, appenders, agents, or collectors. If a log is dropped **before creating a `LogRecord`/`LoggingEvent`**, a downstream filter cannot know it ever existed. Never claim “100% logs delivered” by counting only events that reached the sink.

**Example:** If a sink processes 2,000 logs/s while the application produces 5,000 logs/s, increasing queue size only delays when the queue fills up. Dropping 4,000 low-value logs/s at the source can bring load below sink capacity. However, you must verify that those 4,000 logs/s are genuinely droppable and retain all exceptions/critical events per policy. Letting the queue drop logs on overflow leaves you with no control over which logs are lost.

## 10. Avoiding Duplicate Logs Without Losing Information

Another source of noise is **logging the same error at multiple layers**:

```text
Repository: ERROR database timeout
Service:    ERROR database timeout
Controller: ERROR database timeout
Global handler: ERROR request failed: database timeout
```

You can improve this with a clear policy:

1. At lower layers, **throw exceptions with the cause attached** and add context via exception types or error codes when needed; do not automatically log `ERROR` and rethrow at every layer.
2. At the **error-handling boundary**, log one complete error event with trace ID, error code, impact, and an appropriate stack trace.
3. If a lower layer performs recovery/retries, log key state transitions when useful (such as retries exhausted) rather than repeating the full stack trace on every attempt.
4. Maintain metrics to know how often an error repeats, even when detailed records are rate-limited.

There is no universal “log only once” rule for distributed systems. An error event may need to appear in multiple services with different context. The goal is to avoid **duplicate information that adds no value** within a single processing path, while preserving sufficient traces at service boundaries.

## 11. Security: Noise Reduction Does Not Replace Redaction

Filtering by log level does not guarantee that sensitive data will not leak into other logs. An `ERROR` event can accidentally include passwords, bearer tokens, cookies, access keys, connection strings, or request bodies. Apply the principle of **never logging secrets in the first place**, followed by redaction/masking at appropriate points to reduce remaining risk.

Policies should distinguish between:

- **Dropping events** because the information is unnecessary, such as repetitive healthcheck successes.
- **Redacting fields** because the event is still needed but contains sensitive fields, such as keeping a transaction ID while removing a token.
- **Not emitting sensitive data**: better than masking after data has already entered the pipeline.
- **Preserving audit logs**: security/audit logs have separate governance, access controls, and retention; they must not be dropped by routine technical filters.

For logs derived from untrusted input, avoid concatenating strings containing unescaped newlines, which can cause log injection or break structured formats. Use encoders with proper escaping and stable schemas. When implementing message-based filters, do not use values containing personal data as decision keys without a valid reason and protective controls.

## 12. Measuring Effectiveness Before and After Filtering

A filtering experiment should evaluate **retained information value**, not just bytes saved. Measure under the same workload, duration, and sink configuration:

| Metric | Why It Matters |
| --- | --- |
| Log events/s by level/logger/event code | Finds the largest sources of noise and verifies rules target the right events. |
| Total bytes/s, index storage, network egress | Evaluates actual cost savings. |
| CPU, allocation, GC pauses, logger call p95/p99 | Checks JVM cost benefits; collector-side filtering usually saves little producer CPU. |
| Queue occupancy, enqueue blocking, async drops | Distinguishes intentional noise dropping from overload log loss. |
| `ERROR`/`WARN` event counts and error detection latency | Verifies critical logs remain intact and alerts are not blinded. |
| Trace/request ID coverage | Checks that enough data remains to debug real incidents. |
| Dropped-by-rule/sampling counters | Shows which policy drives the reduction and catches misconfigurations. |

Process:

1. Collect baseline metrics; use top-N loggers/packages/event codes by volume to locate noise hotspots.
2. Choose specific rules and document **criteria**, **scope**, **rationale**, **owner**, and **rollback procedure**.
3. Test against similar-looking events with different meanings: `healthcheck.ok`, `healthcheck.failed`, `payment.failed`, `payment.retry`, `order.created`.
4. Re-measure log volume, cost, and p95/p99 under an equivalent workload. Verify aggregate metrics and alerts.
5. Trigger a test error with a trace ID; verify diagnostic logs exist at the source, collector, and search system.
6. Test behavior during traffic bursts, deploy/restart, collector failures, or full queues. Report **filtered** volume and **lost** volume separately.
7. Roll out with versioning and rollback capability. Monitor volume reduction alongside error detection over several operational cycles.

**Quantitative example:** An application emits 10,000 events/s, of which 7,000 events/s are `INFO healthcheck.ok`. If you drop only that exact event type, events written to the sink drop to about 3,000/s—a 70% reduction in **event count**. You cannot automatically conclude a 70% reduction in **storage**, since events vary in size; nor can you conclude a 70% reduction in CPU, because the work saved depends on where filtering occurs.

## 13. Common Pitfalls and Fixes

| Symptom | Cause | Check / Fix |
| --- | --- | --- |
| Healthcheck warning logs disappeared | Rule too broad, relying on `message.contains("health")` | Use exact level + logger + event code; test success and failure separately. |
| Volume dropped but CPU did not | Dropped at appender/collector, or app still builds expensive messages | Filter earlier, use log levels, remove unnecessary computation, and benchmark. |
| `DEBUG` log not printed even though filter returned `ACCEPT` | Another level/filtering stage still blocks it; `ACCEPT` behavior depends on placement | Check effective level and the full filter chain for your framework. |
| Logs still appear in a second sink | Filter attached to only one appender | Check additivity/routing and all appender paths. |
| Only partial logs appear during a major error spike | Rate limiting or async overflow | Compare `rate_limited` and `queue_dropped`; verify the policy. |
| Event code does not match | Message format changed, rule relied on text | Use stable structured codes or markers; add regression tests. |
| Drop counter is 0 while volume decreased | Events were dropped before the filter/counter ran | Add instrumentation at the right layer or rely on business metrics. |
| Missing audit/critical events | Global filter or overly broad sampling | Separate the audit pipeline; add allowlist/exception policies; test durably. |
| Logging filter slows down requests | Expensive regex/serialization/locks per log call | Use lightweight conditions, stable keys, minimize allocations, and measure p99. |
| `DEBUG` disabled but expression side effects still occur | Argument expression ran before the method call | Use `isDebugEnabled()` or a compatible lazy supplier API. |
| Config changes have no effect | Profile/property override, wrong logger name, different backend than expected | Check effective logger level, appender attachments, and loaded config. |

## 14. Review Checklist for a Log-Dropping Rule

Before merging or enabling a filtering rule in production, be able to answer:

1. **Which event?** Are there concrete examples and a stable identifier key?
2. **Is it safe to lose?** Does it relate to security, audit, transactions, errors, or incident diagnostics?
3. **At which layer is the rule placed?** Does it save the intended cost and does it affect all sinks?
4. **What is kept instead?** Does a counter, metric, summary, trace sample, or representative event still reflect system state?
5. **Are exceptions handled?** Are `WARN`/`ERROR`, failures, exhausted retries, and security events preserved?
6. **Are drops counted?** Are policy drops separated from queue/collector overflow drops?
7. **Is it testable?** Are there success/noise and failure/critical examples proving correct behavior?
8. **How do you roll back?** When an investigation requires higher verbosity, can the rule be relaxed by package and time window without a risky rebuild?
9. **What is the real impact?** Have events/s, bytes, CPU, latency, error detection, and storage been compared on a representative workload?

**Passing criteria:** You filter the right low-value events, retain critical logs, understand the costs incurred at each layer, and prove with tests/metrics that log reduction is not caused by the system silently losing essential data.

## References

- [Oracle Java SE 17 — Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html) — level checking, creating `LogRecord`, and applying a `Logger` `Filter`.
- [Oracle Java SE 17 — Filter](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Filter.html) — `isLoggable(LogRecord)`.
- [Logback Manual — Filters](https://logback.qos.ch/manual/filters.html) — `Filter`, `TurboFilter`, `DENY`, `ACCEPT`, `NEUTRAL`.
- [Logback Manual — Architecture](https://logback.qos.ch/manual/architecture.html) — log levels, logger hierarchy, and selection rules.
- [Apache Log4j 2 — Filters](https://logging.apache.org/log4j/2.x/manual/filters.html) — filtering stages, levels, filter results, and overhead.
- [Apache Log4j 2 — Asynchronous Loggers](https://logging.apache.org/log4j/2.x/manual/async.html) — queues, overload/backpressure, and what to measure with async logging.
- [SLF4J Manual](https://www.slf4j.org/manual.html) — logger API, parameterized messages, and fluent API.
