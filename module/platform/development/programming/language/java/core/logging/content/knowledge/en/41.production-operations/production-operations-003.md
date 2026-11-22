# Monitoring Log Write Failures in Java Core Logging

## Learning Objectives

This lesson belongs to the **Production Operations** group, focusing on **Monitoring Log Write Failures**. Logging is an observability tool for the system, yet **the logging path itself can fail**. An application may continue running and returning HTTP 200 while an appender fails to write to a file, an async queue silently drops events, stdout is blocked, a log agent fails to ship data, or a collector receives events that the index fails to store. If operators only look for error messages inside the broken log pipeline itself, they may miss alerts entirely.

This lesson guides you through building **self-monitoring for the logging pipeline** from the JVM to the search backend, distinguishing log write failures from business errors, detecting lost or delayed logs, and designing independent, reliable alerting mechanisms.

After this lesson, you will be able to:

- Distinguish between **logger/formatter errors**, **appender/handler errors**, **queue overflow**, **stdout/file issues**, **agent/collector errors**, **backend/index issues**, and **query errors**.
- Define the boundaries of key metrics: `log call`, `event eligible`, `event accepted`, `write attempted`, `write succeeded`, `collector acknowledged`, and `searchable`.
- Monitor signals from `java.util.logging.ErrorManager`, Logback status, Log4j 2 status, agent/collector metrics, and infrastructure signals.
- Write a **standalone Java 17** program that simulates write/flush failures, captures error events via `ErrorManager`, and proves that "logger was called" must not be confused with "write succeeded".
- Design metrics, dashboards, and alerts for errors, latency, backlog, and abnormal log volume.
- Use **canary logs** and end-to-end reconciliation to detect silent log loss, even when the logging system does not report errors itself.
- Handle production incidents with a safe runbook: protect audit data, avoid recursion, and never casually disable TLS or leak sensitive logs.
- Test failure injection and recovery: disk full, permission issues, rotation, agent crash, queue full, collector outage, index lag, and shutdown.

**Key Principle:** The fact that a log event was created, enqueued, or even returned from an appender **does not by itself prove** that the data was durably stored and made searchable. Monitoring log write failures requires observing distinct boundaries and maintaining a **monitoring channel independent** of the log pipeline itself.

## 1. What Is a "Log Write Failure"?

Incidents commonly grouped together as "logs aren't showing up" can have very different root causes:

| Symptom | Example | First Layer to Check |
| --- | --- | --- |
| No events generated | Effective log level blocks DEBUG or a filter returns `DENY` | Logger level, filter, profile configuration |
| Events exist, but appender cannot write | Missing file permissions, disk full, encoder exception | Handler/Appender, filesystem, status diagnostics |
| Producer blocked while logging | Slow sync write, async queue full with blocking policy | Thread dump, caller latency, queue occupancy |
| Events dropped at async queue | Queue full, discarding policy | AsyncAppender/AsyncLogger metrics and policy |
| Written to stdout/file, but agent does not read | Agent down, wrong glob/path, container driver failure | File/stdout, log shipper |
| Agent reads, but fails to send | TLS handshake, auth token, network timeout, retry backlog | Agent exporter, network, collector endpoint |
| Collector receives, but does not process | Parser rejection, transform/filter drops event, quota | Collector pipeline and rejection counters |
| Backend receives, but not yet searchable | Indexing lag, shard rejection, retention/permission | Storage/index/query |
| Not found due to bad query | Wrong namespace, timezone, query filter, or read permissions | Search/query layer |
| Duplicate logs | Root additivity, both file + stdout ingested, non-idempotent retry | Routing and event ID |

**Write failures** are different from **intentionally filtered logs**. If INFO logs are sampled at 10%, the rest are excluded from the index by policy and must not be reported as "90% write failure". Conversely, an event selected by the sampler that gets dropped by an async queue must not be counted in `sampled_out`. Keep counters separate so reporting remains honest.

### Four States Often Conflated

```text
logger called
    |
    v
event admitted / sampled-in
    |
    v
appender/queue accepted
    |
    v
sink write completed
    |
    v
shipper / collector acknowledged
    |
    v
backend durable / searchable
```

This is a conceptual diagram; a specific architecture may not have every step. "Write completed" might only mean a syscall or library buffer flush, **not necessarily an fsync to disk**. An HTTP 2xx from a collector might mean "received" rather than "indexed". Each hop must define **what success means** before choosing metrics and SLOs.

## 2. Map the Entire Log Path Before Monitoring

Example Java architecture in a container:

```text
Java logger
   |
   +-- Logback / Log4j2 / JUL handler
   |         |
   |         +-- sync/async queue, encoder, filters
   |
   v
stdout or application log file
   |
   v
container runtime / node filesystem
   |
   v
log shipper / agent
   |
   v
gateway / collector
   |
   +-- authentication / parser / filter / batching
   |
   v
message broker / ingest service
   |
   v
index / storage / query / alert
```

Another system might use an appender that sends HTTP/gRPC directly, a broker in front of the collector, or multi-region forwarding. Do not mechanically apply a "collector" checklist to an application that only uses local files; instead, map the **actual path** for each log type.

Monitor each hop in two dimensions:

1. **Positive:** events traverse the hop and are accepted according to contract.
2. **Negative:** events are not misrouted, duplicated, or leaked to a less secure sink.

If a service has two routes (application console and security audit), separate their SLIs; a dashboard looking only at total volume may fail to notice that **the audit path has stopped** while the console path continues working.

## 3. Classifying Failures in Java Logging Frameworks

### 3.1. java.util.logging (JUL)

In the JDK, `java.util.logging.Logger` dispatches a `LogRecord` to a `Handler`. A `Handler` may reject an event due to level/filter, fail to format it, write to a file/socket/console, or throw/record errors depending on the implementation.

JUL provides `java.util.logging.ErrorManager` and the protected method `Handler.reportError(...)`. A custom `Handler` can report standard error codes:

| ErrorManager Code | General Meaning |
| --- | --- |
| `GENERIC_FAILURE` | Generic handler failure |
| `WRITE_FAILURE` | Unable to write data |
| `FLUSH_FAILURE` | Unable to flush data |
| `CLOSE_FAILURE` | Unable to close resource |
| `OPEN_FAILURE` | Unable to open destination |
| `FORMAT_FAILURE` | Unable to format a record |

**ErrorManager is not a complete production telemetry system.** Its default implementation may only print a limited number of messages to stderr to avoid spam; you should not treat "every error produces a stderr line" as an SLO. Dedicated instrumentation is needed for counters, health, and alerts when policy requires it.

Notes:

- `Logger#log(...)` may return normally even if a `Handler` reports an internal error. Do not assume you should retry a business operation just because the logger returned.
- A custom `Handler` you write must **catch and report errors appropriately**; do not log error messages through the same broken handler, as that risks recursion.
- `ErrorManager.error(...)` is a callback; do not make slow synchronous network calls or throw exceptions from this callback in production.
- Error categories such as "disk full", "permission denied", or "format error" should be classified, but **do not put raw messages containing secrets** into metric labels.
- If a `Handler` only calls `reportError` when a write fails, events dropped **before the Handler receives them** will not be counted by this counter.

### 3.2. SLF4J + Logback

SLF4J is a façade; Logback Classic/Core provides appenders and status infrastructure when using the Logback backend. Important signals include:

- Status messages emitted by appenders, encoders, rolling policies, or the configuration system.
- `StatusManager` and status listeners/console if configured; verify the version and lifetime of status entries.
- File appender failing to open, rolling/rotation errors, encoder errors, and write/flush/close issues.
- `AsyncAppender` has a bounded queue, discarding policy, and `neverBlock`; a full queue can cause **producer blocking** or **event drops**, depending on configuration.
- Logger levels/filters before the appender may intentionally drop events, which must not be counted as write failures.

**Logback status ≠ standardized default metrics.** Some statuses are only logged at startup or when a component reports an error, without complete counters for every failed event. If production needs SLIs, use appropriate instrumentation/metrics adapters, and verify overhead and independent metric export capability.

An illustrative Logback configuration example:

```xml
<configuration debug="true">
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

In Logback, `debug="true"` can print configuration status details during initialization, which is useful for finding loader/appender errors. **Do not treat this as a complete production error-monitoring configuration** or leave it permanently enabled across all services. Status messages may contain file paths, endpoints, or system details; adjust according to security and volume guidelines.

### 3.3. Log4j 2

Log4j 2 has **StatusLogger**/status reporting for internal and configuration errors. Depending on the logger/async/appender mode:

- A network appender may retry, skip enqueuing, fill its buffer, drop events, or emit warnings according to version semantics.
- `ignoreExceptions` on some appenders affects whether exceptions from the appender propagate to the caller or are handled inside the framework; verify the specific configuration.
- AsyncLogger/AsyncAppender has queue-full policies. When full, the caller may bear the cost or events may be dropped according to the configured strategy.
- Startup config errors can leave an appender non-functional even while the application starts up normally.

Do not apply Logback's `neverBlock` attribute name to Log4j 2. Verify the actual backend, running version, status channels, and metrics from the relevant components; do not assume all of them expose `dropped_events_total` out of the box.

### 3.4. Frameworks and Logging Bridges

Spring Boot, Quarkus, or other environments may configure levels/root appenders, redirect JUL to SLF4J, or use logging bridges. When you see "no logs", check:

- Actual SLF4J binding/provider and startup messages.
- Which configuration file is loaded in the current environment.
- Logger hierarchy, package levels, and filters.
- Whether multiple backends/bridges are causing loops or unexpected routing.
- Which diagnostics channel receives errors from appenders to JUL/Logback/Log4j 2.

**Do not rely on `logback.xml` in the repo if production uses a different config override.** Track the effective configuration/version and test in practice using an event with a unique ID.

## 4. Monitoring Goal: Detect Errors Without Causing More Errors

A log write failure monitoring system must not depend entirely on **the failing sink itself**. If a file or collector is broken, calling `logger.error("log shipper failed")` to the same file or collector may go nowhere and can also trigger recursion or queue pressure.

A typical design uses independent layers:

1. **In-process counters/gauges** in JVM memory, exposed via a metrics endpoint or independent monitoring system.
2. **Internal status diagnostics** of the logger/backend for local debugging, with volume limits and redaction.
3. **Host/container metrics** for disk space/inodes, file descriptors, CPU/GC, stdout driver, and network.
4. **Agent/collector metrics** for input accepted, exporter success/failure, queue depth, retries, and bytes.
5. **End-to-end canary** emitting a non-sensitive event and observing it at the target sink/backend.
6. **Independent alert routing** (monitoring/pager) that does not wait for the log search system to process its own outage.

You do not need a "monitoring system that never fails". However, avoid a single failure domain where **both logs and missing-log alerts disappear together**. If the metrics endpoint is on the same node and the node goes down, other infrastructure health checks/node alerts must detect it.

## 5. Which Boundaries Should Be Measured?

Events can be dropped at many points. A good metric set must define **the right denominator**.

| Suggested Metric | Where to Count | Meaning |
| --- | --- | --- |
| `logging_calls_total` | At wrapper/call site if any | Total calls passing the instrumentation point; does not automatically cover every library logger |
| `logging_events_eligible_total` | After level/filter as defined | Events eligible for consideration before sampling |
| `logging_events_sampled_out_total` | Sampling policy | Intentionally excluded by policy |
| `logging_events_admitted_total` | Point after sampling | Events decided to be kept |
| `logging_appender_received_total` | When appender/handler receives record | Does not reflect events dropped earlier |
| `logging_sink_write_attempts_total` | Before write operation at sink | Number of write attempts, may include retries |
| `logging_sink_write_failures_total` | When actual write reports error | Write failure at that sink |
| `logging_sink_write_success_total` | When write API reports success | Does not guarantee durability or collector receipt |
| `logging_queue_dropped_total` | Async queue/admission | Logs lost due to queue policy/overflow, not sampling |
| `logging_queue_depth` | Appender/agent queue | Current backlog level |
| `logging_enqueue_block_seconds` | When caller waits to enqueue | Logging impact on application latency |
| `logging_agent_input_total` | Agent received/read | Logs from file/stdout that passed through the agent |
| `logging_export_failures_total` | Agent/collector exporter | Failure sending to the next hop |
| `logging_collector_accepted_total` | Collector receiver | Collector accepted event per API contract |
| `logging_collector_rejected_total` | Parser/quota/security policy | Events rejected at collector |
| `logging_indexed_total` | Backend/index | Events stored/searchable as defined |
| `logging_end_to_end_lag_seconds` | Canary by event ID | From event emission to backend visibility |

These are **suggested metric names**, not default metrics present in every JUL/Logback/Log4j 2/OpenTelemetry Collector setup. When implementing, verify the actual names and semantics of each component, including version and cardinality.

### How to Design Labels

Reasonable labels include `service`, `environment`, `sink`, `error_category`, `outcome`, and `policy_version` with bounded value sets. **Do not** use `trace_id`, `request_id`, `message_id`, user ID, arbitrary paths, or raw exception messages as Prometheus metric labels. High-cardinality values will blow up label cardinality and can overload the monitoring system itself.

Example of a write failure metric:

```text
logging_sink_write_failures_total{
  service="checkout",
  environment="production",
  sink="application-file",
  error_category="permission_denied"
}
```

This is an **illustrative** exposition format, not a metric automatically exported by Java. To get these counters, you must instrument at the exact write/error callback point. Do not increment 10 times if a single underlying error produces 10 duplicate status lines, unless the metric is explicitly defined as report count rather than lost event count.

## 6. "Silent" Failures: Why Listening Only to Status Is Not Enough

Several causes of log loss do not throw exceptions in the application:

- `DEBUG` is disabled or logger levels are changed during deployment.
- A filter or sampler drops events because a key is missing or incorrect.
- An async queue fills up and its drop policy does not report errors to the caller.
- Container stdout/files still have data, but the agent is reading the wrong path.
- The agent reads data, hits its queue/disk spool limit, and drops it.
- A collector transform drops valid events due to a bad rule.
- A query uses the wrong timezone/index/tenant and returns 0 results.
- The collector/backend is in eventual consistency, so logs are not yet searchable.

Therefore, you need an **independent signal of event presence**. A canary log with a fixed ID/sequence per emission is a useful option. Do not rely solely on "there are recent logs", because those may come from another service, another host, or one healthy instance while another instance has lost all its logs.

### Heartbeat vs. Canary

- **Heartbeat** typically checks liveness of a service/agent; if it shares the logging path, a missing heartbeat may indicate an outage without pinpointing the failing hop.
- **Canary log** is a test event with `event_id`, source timestamp, service/instance, and expected destination; the system verifies that **this exact event** reaches the backend within a deadline.
- **Synthetic trace** can verify correlation from a synthetic request across services; note that trace sampling or log sampling does not automatically guarantee all synthetic events are kept.

Canaries should use an approved route, contain no secrets, avoid flooding, and not be confused with business audit records. If the pipeline has sampling/filtering, configure a **controlled bypass or design the canary to match the rule**, so its absence is not simply due to intentional sampling.

## 7. Standalone Java 17: Simulating Write and Flush Failures with ErrorManager

The following example uses **JDK 17+** with no Maven, JUnit, or external libraries. The program deliberately simulates a `Handler` doing two things:

1. Receiving three `LogRecord`s from JUL; two records go into an **in-memory fake sink**, and one record triggers a simulated write failure.
2. On `flush()`, simulating a flush failure and reporting it via a custom `ErrorManager`.

All output and error counts are **deterministic**. The handler reports errors via `reportError(...)` instead of using the logger itself to log error messages. The custom `ErrorManager` only increments counters, avoiding reliance on stdout/stderr which could also be broken.

Note: **"accepted" in this example means stored in an in-memory `List`**, which does not represent successful file write, fsync, or backend durability. Those boundaries require separate integration tests.

### File `LogWriteFailureMonitoringDemo.java`

```java
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.ErrorManager;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LogWriteFailureMonitoringDemo {
    private static final class CountingErrorManager
            extends ErrorManager {
        private final AtomicInteger writeFailures =
                new AtomicInteger();
        private final AtomicInteger flushFailures =
                new AtomicInteger();
        private final AtomicInteger otherFailures =
                new AtomicInteger();

        @Override
        public void error(String message, Exception exception, int code) {
            if (code == WRITE_FAILURE) {
                writeFailures.incrementAndGet();
            } else if (code == FLUSH_FAILURE) {
                flushFailures.incrementAndGet();
            } else {
                otherFailures.incrementAndGet();
            }
        }

        int writesFailed() {
            return writeFailures.get();
        }

        int flushesFailed() {
            return flushFailures.get();
        }

        int othersFailed() {
            return otherFailures.get();
        }
    }

    private static final class SimulatedSinkHandler extends Handler {
        private final List<String> accepted = new ArrayList<>();
        private int recordsReceived;

        SimulatedSinkHandler(ErrorManager errorManager) {
            setLevel(Level.ALL);
            setErrorManager(errorManager);
        }

        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record)) {
                return;
            }
            recordsReceived++;

            // A simulated I/O error, without touching the real filesystem.
            if ("evt-2".equals(record.getMessage())) {
                reportError("synthetic write failure",
                        new IOException("disk unavailable"),
                        ErrorManager.WRITE_FAILURE);
                return;
            }
            accepted.add(record.getMessage());
        }

        @Override
        public void flush() {
            reportError("synthetic flush failure",
                    new IOException("flush unavailable"),
                    ErrorManager.FLUSH_FAILURE);
        }

        @Override
        public void close() {
        }

        int received() {
            return recordsReceived;
        }

        List<String> acceptedIds() {
            return List.copyOf(accepted);
        }
    }

    private static void require(boolean condition, String name) {
        if (!condition) {
            throw new IllegalStateException(
                    "Assertion failed: " + name);
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.logwrite.monitor");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);

        CountingErrorManager diagnostics = new CountingErrorManager();
        SimulatedSinkHandler sink =
                new SimulatedSinkHandler(diagnostics);
        logger.addHandler(sink);

        try {
            logger.info("evt-1");
            logger.warning("evt-2");
            logger.info("evt-3");
            sink.flush();

            List<String> accepted = sink.acceptedIds();
            require(sink.received() == 3, "received count");
            require(accepted.equals(List.of("evt-1", "evt-3")),
                    "accepted events");
            require(diagnostics.writesFailed() == 1,
                    "write failures");
            require(diagnostics.flushesFailed() == 1,
                    "flush failures");
            require(diagnostics.othersFailed() == 0,
                    "other failures");

            System.out.println("handler_received="
                    + sink.received());
            System.out.println("fake_sink_accepted="
                    + accepted.size());
            System.out.println("write_failures="
                    + diagnostics.writesFailed());
            System.out.println("flush_failures="
                    + diagnostics.flushesFailed());
            System.out.println("accepted_ids="
                    + String.join(",", accepted));
            System.out.println("test=PASS");
        } finally {
            logger.removeHandler(sink);
            sink.close();
        }
    }
}
```

Compile and run:

```bash
javac LogWriteFailureMonitoringDemo.java
java LogWriteFailureMonitoringDemo
```

**Exact stdout:**

```text
handler_received=3
fake_sink_accepted=2
write_failures=1
flush_failures=1
accepted_ids=evt-1,evt-3
test=PASS
```

### Explaining the Result

1. `Logger` has `Level.ALL` enabled, and `Handler` also has `Level.ALL` enabled; all three events reach the Handler without being blocked by level filters.
2. Upon receiving `evt-2`, the Handler calls `reportError(..., WRITE_FAILURE)` and does not add that event to the accepted list. This is a **simulated write failure at the Handler**, not log loss due to sampling.
3. After the three events, `sink.flush()` is called. The Handler reports a simulated `FLUSH_FAILURE`, but does not remove the two events already stored in the list.
4. `CountingErrorManager#error` receives the error code and increments the corresponding counter; it does not call the logger or print exceptions, so there is no recursion or interleaved stderr output.
5. Assertions verify the number of events received by the Handler, the accepted list, and error counts by type. Only when all pass does it print `test=PASS`.
6. `setUseParentHandlers(false)` prevents JUL parent handlers from emitting unrelated output. The Handler is detached/closed in `finally` so it does not affect other tests.
7. This is a **sequential single-threaded** test. `ArrayList`/`recordsReceived` are not thread-safe if multiple threads call `publish` concurrently; when implementing a Handler shared across threads, use appropriate thread-safe structures/counters or synchronize according to the implementation contract.

### What Have We Proven?

- Counters at the **exact `Handler.reportError` point** detect one write failure and one flush failure.
- **Records received ≠ records simulated as successfully written.**
- We do not need to rely on error logs in the same pipeline to know a failure occurred.
- The `logger.warning("evt-2")` call returns normally in the program even though the sink reported an internal write failure.

We **have not proven** recovery, fsync, network delivery, retention, or collector indexing. In production, a Handler reporting an error may be formatted/printed through another implementation; a custom handler must report errors in its real failure branches. Errors from third-party appenders do not automatically flow into this Handler's `CountingErrorManager`.

### Learning Experiments

- Change the failure condition to `"evt-3"`: the accepted list assertion will fail; the test catches the change in failure path.
- Remove `sink.flush()`: the flush failures assertion will fail; proves flush failure is a distinct boundary.
- Change logger level to `Level.SEVERE`: both INFO and WARNING are filtered before the Handler, so `handler_received=3` is no longer true.
- Remove `reportError(...)` in the failure branch: accepted events drop, but the write failure counter does not increment; this is **silent loss**. The lesson is that instrumentation on the exact failure path matters.
- Add a second Handler receiving events: you must decide whether the test measures failures of a single sink or across all sinks, avoiding mistaking intentional fan-out for abnormal duplication.

## 8. From ErrorManager to Production Metrics

In a real environment, you should not use the demo's `ArrayList` as a sink. A custom adapter can use thread-safe counters from the metrics library your organization uses.

Illustrative pseudocode:

```text
on handler receives record:
    received_counter.increment()
    try:
        write_record_to_sink(record)
        successful_write_counter.increment()
    catch known write exception:
        write_failure_counter.increment(error_category)
        report_internal_error_without_using_same_logger()
        apply documented sink failure policy
```

This is **pseudocode**; the contract differs if writes are asynchronous or buffered. If `write_record_to_sink` only enqueues, name it `enqueue_success` instead of `write_success`. If an exception occurs during formatting, increment `format_failure` rather than lumping it into `disk_failure`.

### Be Careful with Error Callbacks

- Callbacks should be **cheap and non-blocking**, as they often run on critical caller or worker threads.
- Counters can use `LongAdder` or the primitives of the actual metrics SDK in use, depending on concurrency/performance. Do not use unsynchronized `int++` across multiple threads.
- Use error categories from an allowlist: `disk_full`, `permission_denied`, `timeout`, `tls_failure`, `format_failure`. Do not turn arbitrary exception messages into labels.
- Do not log another message through the same appender from `ErrorManager.error` or a Logback error callback.
- Test what happens when the metrics exporter itself fails: it must not create a loop that increments errors and keeps calling the logger.
- `ErrorManager` only reflects **errors reported by the handler**; metrics from queues and collectors must be instrumented separately.

## 9. Monitoring Files, Stdout, and Rotation

### 9.1. File Appender

A service writing logs to a file can encounter:

- Parent directory does not exist or lacks permissions.
- File is locked or permissions change after deployment.
- Disk runs out of space or out of inodes.
- Filesystem switches to read-only, I/O errors, or very high latency.
- File rotation/rename/truncate causes the appender to keep writing to the old inode; the shipper may read the wrong file.
- Rolling policy deletes files before the shipper finishes reading, or creates too many files.
- File descriptor leaks, ulimit too low, or container/volume quota exceeded.

Monitor **filesystem free bytes/inodes**, write error counts, appender status, file size/last update, open file descriptors, rotate counters, shipper offsets, and ingest lag.

**Do not treat stagnant file size as a guaranteed error.** Business traffic might be zero, or levels/sampling may have changed. Combine traffic/eligible event signals with canaries.

### 9.2. Stdout/Container Logging

Many containerized Java applications write to stdout/stderr, which the runtime/agent collects. Risks:

- Stdout pipe/driver stalls, causing a synchronous `ConsoleAppender` to block application threads.
- Container logging driver truncates/drops events when enforcing quotas or rotating.
- Agent DaemonSet/sidecar is not running or lacks permissions to read container logs.
- Pod is replaced/evicted before buffered logs are shipped.
- Log entries are split/truncated due to multiline stack traces or large message sizes.
- Container timestamp/metadata does not match application timestamp.

Monitor the **stdout/stderr pipeline** and agent, not just the Java appender. If the appender reports write success to stdout, that does not prove logs reached the collector.

### 9.3. Rotation Test

A test can:

1. Emit an event before rotation and confirm the file/agent saw it.
2. Trigger rotation in staging or via a test configuration.
3. Emit an event after rotation and observe file descriptors/shipper offsets.
4. Verify no events disappear and none are unintentionally duplicated.
5. Verify disk/inodes do not grow unbounded.
6. Re-verify new file permissions and retention configuration.

Do not manually delete or rename production log files without a procedure, as this can destroy evidence or cause the appender to keep writing to the old inode.

## 10. Async Logging: Queue Full, Drops, and Application Impact

AsyncAppender/AsyncLogger decouples slow writes from business threads, but can still lose logs or block the application when the queue fills up.

```text
application threads
     |
     v
async queue (bounded) ---> writer thread ---> file/stdout/network
     ^                        |
     |                        v
     +--- full / backpressure / write error
```

Signals to measure:

- `queue_depth` and `queue_capacity` (observed at the same timestamp).
- `enqueue_attempts`, `enqueue_success`, `enqueue_dropped`.
- `producer_block_duration` or a histogram of logger-call duration.
- `worker_write_latency`, `flush_latency`, `worker_unhealthy`.
- `discarded_by_policy` separated from `dropped_due_to_overflow`.
- `shutdown_pending_events` and `shutdown_drain_failures` if supported by the SDK.

**A successful enqueue is not a successful write.** This distinction is especially important when the collector is backed up: the queue may hold many events while the backend only accepts a few events per second. When the queue is full, production may:

- Block the caller waiting for space.
- Discard events according to a discard policy.
- Drop immediately to preserve latency.
- Write synchronously on the caller thread under certain mechanisms/policies.
- Buffer/disk-spool depending on the agent/exporter design.

Never conclude "async logging never blocks". When p99 request latency rises alongside high queue occupancy, take thread dumps/JFR in an authorized environment and check whether appenders are waiting on locks, I/O, or queues.

### Distinguishing Blocked, Dropped, and Delayed

| Situation | Symptom | Needs Alerting |
| --- | --- | --- |
| Producer waits to enqueue | Caller latency/p99 increases, many threads waiting | Impacts application availability |
| Queue accepts, writer is slow | Queue depth and event age increase | Risk of queue full and delayed investigation |
| Queue drops INFO by policy | Drop counter rises, logger caller stays fast | Observability data lost intentionally/under overload per rule |
| ERROR events also dropped | Critical delivery gap per policy | Severe incident if ERROR requires full retention |
| Writer fails on flush | Appender ErrorManager/status reports error | No guarantee buffered logs were pushed |
| Collector/index is slow | JVM/appender may look normal, visibility lag increases | Operators see logs late or not at all |

For proactive monitoring, set alerts **before the queue is full** and separate alerts when drops occur; 90% utilization for one minute may be dangerous depending on bursts, but it is not a universal threshold. Calibrate to the service's volume and throughput.

## 11. Monitoring the Agent, Collector, and Backend

In a multi-hop pipeline, JVM metrics alone are not enough. You must observe **what the agent/collector sends and receives**.

### 11.1. Agent/Shipper

Check:

- Bytes/records read from stdout/files.
- Input parser errors, multiline errors, truncated records.
- Export requests, request failures, retry attempts, timeouts.
- Queue/spool utilization and backlog age.
- Last successful export timestamp or age of the oldest pending batch.
- Process availability/restart count, OOM/CPU/memory.
- TLS certificate expiry, authentication failures, proxy/DNS errors.

If the agent is alive but not reading files due to a wrong glob, a liveness check may still PASS. Canary logs and agent input counters will catch this discrepancy.

### 11.2. Collector

Watch the counts of records **accepted**, **refused/rejected**, **filtered by policy**, **exported**, **failed**, and pending queues per actual processor/exporter. Do not assume fixed metric names or semantics across versions/distributions of OpenTelemetry Collector, Fluent Bit, Vector, Filebeat, or other systems.

A collector may receive records and then:

- Drop them intentionally via filter/transform rules.
- Reject them due to schema/quota.
- Retry/queue when the backend is unavailable.
- Lose batches when queue/spool runs out of space.
- Export successfully while the backend is not yet searchable.

When using OpenTelemetry, distinguish logs/metrics/traces pipelines; logs exporter errors do not necessarily appear in trace exporter metrics. Query the right pipeline, endpoint, tenant, and routing configuration.

### 11.3. Backend/Index

Monitor:

- Ingest request rate, errors/rejections, queue/backlog.
- Shard/index write failures or indexing lag.
- Storage capacity, retention/rollover, and quotas.
- Search/query availability and permissions.
- Queryability of canary events by `event_id`, `service`, `environment`, and `timestamp`.
- Duplication from retries/fan-out, mapping conflicts, and field truncation.

**A query returning 0 records does not by itself prove an event was lost.** You might be querying the wrong index, namespace, timezone, policy, hitting eventual consistency, or the ID may have been transformed. When investigating, start from the hop closest to the source confirmed to have received the event, then check each subsequent hop in order.

## 12. Canary Logs: End-to-End Verification from Source to Search

A good canary has these properties:

- A fixed event code, e.g. `logging.pipeline.canary`.
- A unique `canary_id` per emission, e.g. `svcA-instance2-20261110T090000Z-7f2a`.
- `service`, `environment`, `instance`, and `emitted_at`.
- No tokens, PII, business data, or sensitive raw payloads.
- Travels through **the exact route** being tested, with no shortcut bypassing the collector.
- Sampling/filtering configured so canary events are not dropped by normal policies.
- An independent checker waits for the event in the backend with an appropriate deadline and records receipt/search time.
- Rate-limited so canaries cannot become a log storm source.

Example JSON record:

```json
{
  "event": "logging.pipeline.canary",
  "canary_id": "checkout-a1-20261110T090000Z-7f2a",
  "service": "checkout",
  "environment": "production",
  "instance": "checkout-a1",
  "emitted_at": "2026-11-10T09:00:00Z"
}
```

This is a **sample event**, not a default schema for Java or a collector. A canary only proves **one route succeeded at the time of the check**. It does not prove no future log event or audit path will be lost. If a route has multiple sinks, you need independent canaries or explicit assertions for each route.

### Key Canary Signals

- `canary_emitted_total` at the independent monitoring source.
- `canary_seen_total` at the backend by event ID.
- `canary_missing_total` after the observation deadline.
- `canary_delivery_lag_seconds`: emitted-to-searchable delay.
- `canary_duplicate_total`: number of event IDs appearing multiple times outside policy.
- `last_successful_canary_at` per service/instance/route.

Canaries can be emitted a few times per minute or per an appropriate policy; there is no single cadence for all systems. If a pipeline has low traffic, periodic canaries help detect "silence due to failure" without needing business traffic.

**Note on clocks:** If `emitted_at` is measured on one node and `searchable_at` on another, clock skew can produce negative latency. If accurate SLOs are needed, use synchronized time or measure elapsed time in the checker under a consistent contract; alert on clock drift separately.

## 13. Building Production Dashboards and Alerts

A good dashboard must answer **"where are logs being lost and what is the impact?"**, not just plot a single log volume chart.

### Group 1: JVM Signals

- Handler/Appender write failures by error category and sink.
- Async queue occupancy, dropped/discarded events, worker health.
- Logger call p95/p99 and blocked enqueue duration.
- Number of logger config/load errors or rolling policy failures.
- Critical event counters from business/audit sources if available.
- Number of instances with metrics present; missing metrics is also an important signal.

### Group 2: Intermediate Infrastructure

- Disk free bytes/inodes, FD usage, container restarts.
- Agent input/output records, rejected and retry totals.
- TLS/auth failures, collector availability/latency.
- Pending queue age/spool utilization.
- Ingest refused/rejected, exporter errors.

### Group 3: End-to-End

- Canary missing rate by service/environment/route.
- Median/p95/p99 emitted-to-searchable lag when data is sufficient and clocks are valid.
- Number of instances without a successful canary within the check window.
- Record counts per expected route, accounting for sampling/filtering/retries.
- Critical-audit reconciliation gap (when an authoritative store exists).

### Example Alert Rules Requiring Calibration

| Alert Name | Example Condition | Severity/Action |
| --- | --- | --- |
| **AppenderWriteFailure** | `increase(write_failures[5m]) > 0` on a critical sink | Triage immediately; check disk/permissions/status |
| **AsyncQueueNearCapacity** | Queue occupancy persistently high and rising | Check sink throughput; safely reduce noise |
| **LoggingQueueDropped** | Overflow drops increase over 5 minutes | Investigate drop policy and impact on logs |
| **CollectorExportFailure** | Export errors rising + oldest pending batch aging | Check TLS/auth/network/collector |
| **CanaryMissing** | Canary not found within deadline with sufficient evidence | Trace hop by hop; separate query failure from delivery failure |
| **CanaryLagHigh** | p95 delivery-to-search exceeds approved budget | Investigate queue/backlog/index |
| **CriticalAuditGap** | Committed business events exceed confirmed audit events past deadline | Check outbox/store/reconciliation |
| **MetricsMissing** | Service/agent stops exporting metrics past timeout | Distinguish service down from monitoring down |

These conditions are **illustrative**, not copy-paste rules for Prometheus; actual metric names and vector labels must be defined first. For critical audit, a `>0` threshold may be reasonable, but only if the counter is reliable, avoids restart/cold-start false alerts, and is approved by operations.

### Do Not Use Raw Log Line Counts Alone as Error Rate

For example, an application receives 10,000 requests and encounters 2 business errors, but the code logs ERROR 3 times per error across multiple catch-and-rethrow layers. A dashboard counting 6 ERROR lines exaggerates the error rate. Conversely, a broken logging sink makes the dashboard show 0 ERROR lines even while the service is failing heavily.

For **business error rate** or SLOs, use request counters, transaction outcomes, or source metrics independent of log sampling/delivery. Logs support detailed investigation, not as the sole source for numerator/denominator when the pipeline can drop data.

## 14. SLOs/SLIs: Defining Honest Observability

Useful indicators include:

### 14.1. Selected Log Export Rate

If full instrumentation exists at an appender:

\[
\text{Appender write success rate} =
\frac{\text{successful writes}}{\text{write attempts}}
\]

Use this only when attempts and successes are counted consistently. If an event is retried 3 times, **successful writes / write attempts** is no longer the ratio of unique events delivered successfully. Clearly state the unit (attempts vs. unique events).

### 14.2. Canary Delivery Ratio

\[
\text{Canary delivery ratio} =
\frac{\text{unique canary IDs observed by deadline}}
{\text{unique canary IDs emitted and eligible}}
\]

Exclude canaries whose deadline has not yet passed, distinguish intentional policy filtering, and ensure the checker has proper query permissions. If the backend query fails, the checker should conclude **UNKNOWN** instead of marking all events as "missing".

### 14.3. Visibility Lag

\[
\text{Visibility lag} =
t_{\text{searchable}} - t_{\text{emitted}}
\]

If the two timestamps come from unsynchronized clocks, this estimate can be skewed. You can use source event timestamp and backend observed timestamp with a note on time synchronization; never treat negative lag as evidence of events traveling backward in time.

### 14.4. You Cannot Assume 100% Delivery from "No Errors"

If events are uninstrumented or fail silently, a write failure counter of 0 **is not enough to prove** no logs were lost. Canaries, end-to-end reconciliation, and per-route controls complement status counters.

Each SLO should specify **service/route scope, time window, calculation point, log type, event ID, and valid exclusions**. An SLO for sampled DEBUG logs is not the same as for mandatory audit logs, and a log written to stdout is not equivalent to a "durable backend event".

## 15. Principles When the Log Pipeline Fails

An incident policy must be decided **before** an outage occurs.

### 15.1. Keep the Application Running or Stop?

- **Fail-open:** business continues even if log delivery fails, with monitoring/alerting and buffering/recovery mechanisms appropriate to criticality. Suitable for most diagnostic logs.
- **Fail-closed:** reject operations if mandatory audit logging cannot be guaranteed per contract. May be appropriate for sensitive changes, but requires careful design, testing, and availability impact assessment.

Do not apply the same policy to every log line. For instance, "adding DEBUG for investigation" should not take down a payment service just because the collector is slow. Conversely, a mandatory audit event may need a dedicated durable store/trust boundary rather than best-effort logging.

### 15.2. Bounded Buffering, Retry, and Backpressure

- Bounded queues prevent unbounded RAM growth, but require a full-queue policy.
- Disk spooling can improve resilience to short outages, but requires quotas, at-rest security, permissions, and retention.
- Retries need backoff/jitter, deadlines, and error classification; do not retry indefinitely on 401/403 auth errors or invalid payloads.
- Failures after sending but before receiving an ACK can cause duplicates on retry; use event IDs and idempotency if needed.
- Document clearly when an event is considered "accepted", "sent", "acknowledged", and "durable".
- Avoid automatically falling back to HTTP/plaintext or a less secure sink when TLS/authorization fails.
- When disk spool fills up, never silently delete audit/security events outside policy.

### 15.3. Avoid Error-Reporting Loops

A dangerous scenario:

```text
appender.write() throws IOException
   |
   v
error handler calls logger.error("write failed")
   |
   v
same appender.write() throws IOException
   |
   v
... recursive failure / log storm
```

How to reduce the risk:

- `ErrorManager`/status callbacks should only update counters or report through an internal channel designed not to depend on the same sink.
- Send pager/alerts from an independent metrics backend/health checker.
- Throttle internal diagnostics; avoid printing a stack trace for every lost event.
- If you must log a message about a logging failure, use an isolated channel with evaluated load/failure behavior.
- Inject failures in testing to prove there is no recursion or deadlock.

## 16. Production Incident Triage and Runbook

When receiving a missing canary or write failure alert, proceed in order:

1. **Verify user impact:** request latency, availability, business error rate, audit compliance; determine whether this is an observability-only issue or affecting the service.
2. **Isolate the path:** service, environment, instance, logger name, appender, file/stdout, agent, collector, index/tenant, and time range.
3. **Verify source events:** do source metrics or canary IDs show the event was intended to be emitted? Did level/filter/sampling policies intentionally drop it?
4. **Check the JVM:** Logback/Log4j2/JUL internal status, write/flush errors, queue depth, dropped events, and thread dumps if p99 is rising.
5. **Check the host/container:** disk space, inodes, permissions, file descriptors, stdout driver, rotation, pod restarts, and OOMs.
6. **Check the agent:** is it reading the right file/stdout path? Are input records increasing? What about exporter retries, spool, and auth/TLS errors?
7. **Check the collector:** receivers accepted/refused, processors, exporters, queues, filtering policies, limits, and schema errors.
8. **Check the backend:** index writes/rejects/lag, mappings, retention, query permissions, and timezone; verify you can search an event known to have arrived.
9. **Shed load per policy:** reduce noisy DEBUG/INFO, fix the sink/collector, increase throughput, or apply controlled backpressure. Never disable mandatory audit/security logs or turn off TLS just to "make logs appear again".
10. **Verify recovery:** canaries pass before deadline, queues drain, write errors stop, critical event gaps are reconciled, and app p95/p99 recovers.
11. **Backfill if permitted:** re-ship from disk spool/outbox with idempotency/dedup and an audit trail of the backfill; never fabricate events that were never recorded.
12. **Postmortem:** document the first point where logs were lost, scope of missing data, time to detect, missing signals, and action items.

### Hop-by-Hop Investigation Table

| Point | Evidence to Collect | Valid Conclusion |
| --- | --- | --- |
| Caller/metric | `events_admitted_total` increases | Eligible events passed sampling |
| Handler/Appender | `received` increases, `write_failures` increases | Error at sink/handler likely causing event loss |
| Local file/stdout | Record with test ID exists | Succeeded at this local sink |
| Agent | ID read and export pending | Entered agent, not yet confirmed downstream |
| Collector | Ingest/accepted by ID or batch | Collector received per its semantics |
| Backend | ID searchable in correct index/tenant | Visible in backend within observation window |

Avoid concluding "the collector is broken" when you only know the console lacks events: the problem could be the logger level. Conversely, if the local file has the event but the backend does not, do not blindly modify the source logger.

## 17. Failure-Injection Tests Needed Before Production

A reliable test suite does not only run the happy path.

| ID | Scenario | What Must Be Observed |
| --- | --- | --- |
| F1 | Custom handler hits IOException on write | Write failure counter increments, no recursive logging |
| F2 | Formatter/encoder fails | Format failure/status reports the right category, not confused with disk full |
| F3 | File appender cannot open file | Startup status/health reflects it, not silent |
| F4 | Disk full or inode full on staging volume | Write errors, backlog/drop, alert, recovery |
| F5 | File rotation while agent is reading | No loss/dup beyond policy, offsets/permissions correct |
| F6 | Slow console/stdout pipe | Caller latency/blocked threads/queue occupancy measured |
| F7 | Async queue full | Blocks/drops per policy, separate metrics for deliberate sampling vs. overflow |
| F8 | Agent process killed/restarted | Canary missing, spool recovery, backlog drain |
| F9 | Collector timeout/TLS/auth failure | Bounded retries, queue age increases, no plaintext fallback |
| F10 | Backend index rejects due to schema | Collector rejection metrics, event ID traceable |
| F11 | Backend query unavailable | Checker returns UNKNOWN/QUERY_ERROR, does not report all events missing |
| F12 | Service has no traffic | Canary or expected idle policy avoids false alerts from low log volume |
| F13 | One of many replicas loses logs | Per-instance canary/metrics detect it, not masked by total volume |
| F14 | Mass DEBUG enabled | Sampling/rate limiting, disk/queue budgets, and business p99 |
| F15 | Shutdown with pending async events | Drain/flush within budget, unpersisted event count recorded |
| F16 | Audit sink loses connectivity | Fail-open/closed per policy, critical event reconciliation |
| F17 | Sink recovers and agent backfills | Duplicate event IDs, index lag, and quotas monitored |
| F18 | Log contains fake canary secret | No secret payload leaked into diagnostics/status/alerts |

**Do not arbitrarily run disk-full, kill-collector, or permission-change tests in production.** Use staging, isolated volumes/containers, or organization-approved fault injection with rollback/cleanup. A test that merely shuts down an endpoint and watches log counts drop is insufficient; you must verify how the logger/backend records the error and whether business traffic is impacted.

### Testing Alerts

Do not only prove that metrics increment. Also verify:

- The rule/alert actually transitions to firing with the right labels and severity.
- Alert routing reaches the owning team via an independent channel.
- Dashboards provide drill-down by service, route, instance, and error category.
- Alerts have flood protection when multiple pods fail simultaneously.
- Recovery/clear conditions do not "close" an incident before backlogs or critical gaps are resolved.
- Runbook links, escalation paths, and owners are up to date per environment.

## 18. A Practical Failure Analysis Example

**Illustrative scenario:** After a container upgrade, the Java application continues serving APIs normally, but the log dashboard shows no new records. Querying by request ID returns empty. Do not jump to the conclusion that the application stopped generating logs.

Steps:

1. Request metrics are still increasing; source logging counters show eligible INFO/ERROR events.
2. ConsoleAppender/JUL Handler reports no write errors; local stdout contains the canary event ID.
3. Log agent metric `input_records` is not increasing, even though the pod is running.
4. Checking the runtime path reveals the agent still uses a glob for the old container log format.
5. Fix the agent config in staging, and confirm the canary is read and appears in the index.
6. Roll out the config through the proper process, monitor the oldest pending backlog, and record the window of potentially lost data.
7. Update regression tests for the path/format and add an alert for "source canary emitted but not ingested".

**This is a hypothetical example**, not an actual incident or real test result. Key takeaway: zero write failures in the JVM can still go hand-in-hand with **log loss at the agent**.

### Another Scenario: Disk Full Slowing Down the Service

If a synchronous `FileAppender` slows down or fails when the disk is full, callers can be impacted. At the same time, application error logs cannot be written, so the "disk full" log itself disappears. Alternative signals: filesystem alerts, request p99, thread dumps, async queue occupancy, `ErrorManager`/status. The right fix is to restore disk space/quota or switch sink routes per the runbook, not to keep logging more ERRORs to the same full disk.

## 19. Common Operational Mistakes

| Misconception / Design Flaw | Why It Is Wrong | Correct Practice |
| --- | --- | --- |
| "No ERROR logs means no errors" | Logger/sink/collector may be broken or filtered | Use business metrics, tracing, canaries, and independent status |
| "`logger.info` returned means log is saved" | It may only be enqueued or buffered | Define ACK/durability per hop |
| "App has a new log file means backend has logs" | Agent, collector, or index may be failing | Trace hop by hop using event IDs |
| "Just monitor Logback StatusManager" | It misses downstream drops and ingest failures | Combine JVM, agent/collector/backend, and canary signals |
| "No status errors means everything is fine" | Silent filtering, queue discards, and bad queries may not emit errors | Cross-check counts + synthetic events |
| "A bigger queue solves all bottlenecks" | Sink rate is still lower than sustained production rate | Fix throughput/volume, watch backlog age |
| "AsyncAppender never blocks business threads" | Queue-full policy can block or fall back to synchronous | Measure enqueue wait and caller p99 |
| "Turn on more ERROR logging to see why the logger failed" | Can cause recursive failures or log storms | Use separate metrics/status channels |
| "Collector 2xx = searchable/durable" | Response semantics may only ACK ingest | Verify backend/index separately |
| "Log every failed attempt with raw exceptions" | Leaks PII/secrets and increases cost | Use error categories, redaction, and throttled diagnostics |
| "Sampled-out and dropped are both error-based log loss" | Sampling is policy; overflow is failure/overload | Two separate counters with clear denominators |
| "Total log volume looks fine so all pods are fine" | One pod losing logs is masked by other pods | Per-instance/route canaries |
| "Canary not seen => collector definitely lost logs" | Bad query, clock skew, deadline not yet reached | Distinguish UNKNOWN/QUERY_ERROR/MISSING |
| "Every event written once is exactly-once" | Retries/fan-out/republish can duplicate | Stable event IDs and idempotent pipelines |
| "A log write failure must fail the request" | Depends on criticality; diagnostic logs are usually best-effort | Choose fail-open/closed by requirement |
| "TLS failed, so temporarily switch to HTTP" | Leaks sensitive logs and loses identity verification | Fix certs/trust/auth via proper process |

## 20. Production Readiness Checklist

- [ ] Have all logging routes from JVM to final sink been mapped, including separate audit/security routes if any?
- [ ] Are level filters, intentional sampling, queue overflow, write errors, and backend rejections distinguished?
- [ ] Are there metrics or status signals from loggers/handlers/appenders appropriate for the actual backend?
- [ ] Are appender write failures prevented from being logged recursively through the same broken appender?
- [ ] Are there counters at `received`, `admitted`, `write attempted`, and `write success/failure` boundaries where needed?
- [ ] Are queue depth/capacity, blocked enqueue duration, and dropped event counters present when using async logging?
- [ ] Is there monitoring for filesystem free bytes/inodes, FD quotas, container stdout, and rotation?
- [ ] Do agents/collectors expose metrics for input, output, retries, rejections, backlog age, and auth/TLS failures?
- [ ] Does the backend monitor ingest/index rejections and query visibility?
- [ ] Is there a non-sensitive end-to-end canary log with unique ID, deadline, and independent checker?
- [ ] Is canary `NOT_SEEN` distinguished from `QUERY_ERROR`/`UNKNOWN`?
- [ ] Are metric labels free of message IDs, trace IDs, user IDs, and raw exception messages?
- [ ] Are alerts scoped by service/environment/route/instance so total volume does not mask single-replica loss?
- [ ] Is there a dedicated policy for audit/critical events, durability, and reconciliation?
- [ ] Are fail-open/fail-closed, retry, spool, backpressure, and shutdown behaviors documented?
- [ ] Has failure injection been tested in staging and verified that alerts actually reach operations?
- [ ] Are runbooks, owners, escalation paths, rollbacks, and postmortem/recovery plans in place?
- [ ] Do systems avoid downgrading TLS, disabling certificate validation, or sending sensitive logs to broad-access sinks on error?
- [ ] After recovery, are backlog drain, duplicate event IDs, backfill feasibility, and data-loss scope verified?
- [ ] Is a zero failure counter never treated as absolute proof of zero log loss?

**Completion Criteria:** You can pinpoint which hop is losing logs; read failure signals from JUL/Logback/Log4j 2 and infrastructure; design metrics/canaries/alerts independent of the failing pipeline; run the Java 17 example distinguishing handler received, fake sink accepted, write failure, and flush failure; and present a recovery runbook that protects critical logs.

## 21. Self-Check Questions

1. Why can `logger.error(...)` return normally and still correspond to a log write failure?
2. In JUL, what failures do `Handler.reportError` and `ErrorManager` help track? What failures do they **not** detect?
3. Is Logback `StatusManager` a default counter for all events lost at the collector?
4. Why must `sampled_out` be separated from `queue_dropped`?
5. If stdout contains the canary but agent input does not increase, what should you check first?
6. If collector accepted increases but the backend cannot find the event, which hops could be failing?
7. Why is a query returning zero not definitive proof that logs were lost?
8. When an async queue is full, which signals show that the application is being blocked by logging?
9. Why must a metrics exporter/status callback not call the same logger/appender that is reporting an error?
10. Why does "write success" not automatically mean fsync or backend durability?
11. Does a canary prove all audit events were saved? What additional mechanisms are needed for mandatory audit logs?
12. How do you distinguish a pipeline that is quiet due to zero traffic from one that has lost all logs?
13. Why should `trace_id` or raw exception messages not be used as metric labels?
14. When one replica loses logs while other replicas keep sending steadily, how can a total-volume alert mask the incident?
15. If an agent's TLS certificate expires, why must it not automatically fall back to plaintext?
16. During a collector outage and agent retries, can duplicate events occur?
17. What is the goal of a disk-full failure-injection test beyond throwing an `IOException`?
18. What production risks can a repeatedly failing `ErrorManager` callback create?
19. If backend queries are unavailable, should the checker conclude `MISSING` or `UNKNOWN`?
20. When an incident ends, what must be verified before closing the log delivery incident?

## References

- [Java SE 17 — ErrorManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/ErrorManager.html) — Handler error reporting mechanism and WRITE/FLUSH/OPEN/FORMAT codes.
- [Java SE 17 — Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html) — publish, flush, close, and reportError.
- [Java SE 17 — Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html) — effective levels, hierarchy, and record processing.
- [Logback Manual — Configuration](https://logback.qos.ch/manual/configuration.html) — config/status messages and status listeners.
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html) — FileAppender, ConsoleAppender, AsyncAppender, and queue behavior.
- [Apache Log4j 2 — Status Logger](https://logging.apache.org/log4j/2.x/manual/status-logger.html) — internal diagnostics/status.
- [Apache Log4j 2 — Appenders](https://logging.apache.org/log4j/2.x/manual/appenders.html) — appenders and related errors.
- [OpenTelemetry Collector — Internal Telemetry](https://opentelemetry.io/docs/collector/internal-telemetry/) — monitoring collector pipeline metrics.
- [OpenTelemetry — Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/) — log record, observed timestamp, and logging semantics.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) — security, data minimization, integrity, and logging failures.
