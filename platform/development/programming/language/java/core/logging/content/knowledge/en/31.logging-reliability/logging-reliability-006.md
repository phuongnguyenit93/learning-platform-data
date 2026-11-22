# Unavailable Destination: Designing Reliable Logging in Java

## 1. The Problem: The Application Keeps Running, But Logs May Not Arrive

A **logging sink/destination** is the target that receives log events: the console (stdout/stderr), a file on disk, a network log collector, a centralized service, or a custom appender implemented by the application. An **unavailable destination** means that at a given point in time, that target cannot accept or store events as expected.

Common examples:

- Full disk, missing log directory, denied write permissions, or the filesystem switching to read-only mode.
- Locked log file or failing rotation/reopen operations; container missing the configured volume/path.
- Log collector, syslog server, TCP endpoint, or logging gateway experiencing network loss, DNS failure, timeouts, overload, or connection refusal.
- Closed stdout/stderr, malfunctioning container log collection pipeline, or a process writing too fast for the downstream pipe/agent to keep up.
- Full async appender queue while the worker/sink cannot consume events, leading to blocking or dropping depending on configuration.

Illustrative scenario:

```text
HTTP request
    |
    v
logger.info("Payment accepted")
    |
    v
Async queue --------> Logging worker --------> File / collector
                                           X   destination unavailable
    |
    v
The application may continue processing the request,
but the log event is not guaranteed to be persisted.
```

**First principle:** completing a `logger.info(...)` call does not mean the log has been durably written. Even an appender being invoked does not prove that a remote collector has received and stored the event. If the system requires zero-loss audit logs, a separate storage and acknowledgment contract is needed rather than assuming a standard logging framework guarantees it.

## 2. Distinguishing Levels of "Successfully Written"

An event can pass through multiple stages:

| State | Meaning | What Is Not Yet Guaranteed |
| --- | --- | --- |
| `Created` | The application has created the event or called the logging API | Logger level/filter may discard it immediately |
| `Accepted` | The backend accepts the event according to its policy | The event may only reside in memory |
| `Queued` | The event is in the async appender's queue | Worker has not processed it yet; a crash can lose it |
| `Appended` | The appender has processed or written it to a buffer/stream | Data may not have reached a durable file/collector |
| `Sent` | The client has sent bytes over a socket or API | Successful send does not mean the remote side has stored it |
| `Acknowledged` | The receiving side acknowledges per the protocol | Acknowledgment scope depends on the protocol/provider |
| `Durable` | Data has been stored with contractual durability | Requires defining replication, fsync, retention, crash recovery |

Not every framework exposes all of these states. Many loggers only provide a one-way write API without a `Future` or per-event acknowledgment. Therefore:

- **No log loss** must be scoped clearly: no drops when the queue is full, no loss during graceful shutdown, or survival across process/host crashes.
- **At-most-once**: no retries so duplicates are rare, but failures can lose events.
- **At-least-once**: retries/replays until acknowledgment is received, which can produce duplicate events; requires event IDs/deduplication if needed.
- **Exactly-once** across the entire pipeline is a strong requirement that typically needs transactional mechanisms and dedicated identifiers; it does not happen simply by enabling an async logger or retries.

For ordinary diagnostic logs, a system can choose **best effort** and prioritize not blocking requests. For audit logs with legal/financial constraints, policy may require writing the transaction to durable storage before confirming the business operation; in that case, design an audit mechanism with explicit states/acks.

## 3. Causes and Symptoms to Distinguish

| Destination | Common Failure | Symptoms | How to Diagnose |
| --- | --- | --- | --- |
| File | Out of space, missing permissions, wrong path, read-only filesystem | Appender reports open/write errors, file stops growing | Check permissions, mounts, quota, filesystem state, and Logback status |
| Console | Closed pipe, slow consumer, or redirected stdout | Missing logs in container/terminal, slow writing process | Check runtime/container logging driver and collector |
| Network collector | Connection loss, DNS, TLS, timeout, server 429/5xx | Increasing retries, large backlog, drop in backend log volume | Transport metrics, connection state, ack/HTTP responses |
| Async queue | Sink slower than producer, queue full | Producer blocks, events dropped, or log latency increases | Queue depth, discarded count, enqueue/dequeue rates |
| Encoder/formatter | Serialization failure, invalid pattern config, special data fields | Event fails to render or appender reports error | Test encoder, status/error handler, sample payload |
| Rotation/restart | File rename, handle close/reopen, undrained shutdown | Missing log segment near restart time, old/new file mismatch | Check lifecycle, rolling policy, and shutdown synchronization |
| Collector pipeline | Agent receives logs but ingest/index fails | Logs exist on node but are missing in queries | Agent metrics, DLQ/spool, ingest time, and sampling |

**Do not diagnose every "missing log" case as an I/O error.** The cause can also be logger level, filters, wrong service name, wrong index/time range, timezone, parser, sampling, missing MDC query fields, or events dropped by configuration policy.

### Difference Between Transient Disconnection and Persistent Failure

- **Transient:** brief network drop for a few seconds, collector restart, short rate limit; retries with backoff and bounded buffering can help.
- **Permanent or prolonged:** wrong path, expired credentials, full volume, changed endpoint; retrying every event continuously only increases CPU usage, repetitive error logs, and system pressure. You need alerting, load shedding, or controlled rerouting.
- **Partial failure:** file sink fails while console still works; appender A breaks while B still receives; collector accepts part of a batch. Observe each sink and acknowledgment step independently.

## 4. Synchronous and Asynchronous Logging Behavior on Sink Failure

### 4.1. Synchronous Logging

With a synchronous appender, sink operations may run on the business thread. If the sink is very slow, requests may experience increased latency or stall waiting on a lock/I/O. If the sink throws an exception, behavior depends on the backend and appender implementation.

**Note on SLF4J + Logback:** do not write business code assuming `logger.error(...)` will throw an `IOException` for you to `catch`. Many appenders report write errors through an **internal status/error handler** instead of propagating checked exceptions through the facade. Verify the actual appender type, version, and configuration.

### 4.2. Asynchronous Logging

With Logback `AsyncAppender`, producers place events into a queue and a worker dispatches them to the target appender. Under overload:

- `queueSize` sets the internal queue limit.
- `discardingThreshold` controls dropping low-priority events (typically TRACE/DEBUG/INFO) when the queue is nearly full; setting `0` disables threshold-based discarding.
- `neverBlock=false` means the producer **may block** when the queue is full; `neverBlock=true` uses non-blocking enqueueing and may **drop events** when space runs out.
- `maxFlushTime` controls how long to wait for the worker to drain the queue on shutdown; if the timeout expires before draining completes, unprocessed events may remain.

These are **Logback AsyncAppender settings**, not universal rules for every backend/version. Options for Log4j2 AsyncLogger, async appenders, and network logging agents may differ.

More importantly: **an in-memory queue does not automatically become durable storage**. During a sudden JVM crash, OOM, or host restart, events still in the queue can be lost. If the target appender fails to write while the worker keeps pulling events from the queue, a "drained" queue **does not prove** events reached their destination.

### 4.3. Business Impact

A policy can prioritize:

1. **Availability:** requests continue, logs are written on a best-effort basis; accepts potential partial log loss.
2. **Backpressure:** producer waits for a bounded time to improve log delivery odds; accepts increased latency.
3. **Durability:** temporarily writes to a durable spool and deletes only after receiving an ack; accepts extra I/O, complexity, and duplicate event handling.
4. **Fail closed:** rejects a business operation when a mandatory audit record cannot be stored/acknowledged; choose only when business/regulatory requirements mandate it.

There is no single right choice for every log type. Debug logs and payment audit events typically require different reliability contracts.

## 5. Strategies When the Destination Is Unavailable

### 5.1. Using an Independent Fallback Write Path

For example, an application writes to a file while also writing to stdout for platform collection. When the file fails, stdout **may** still be written if that appender remains healthy. These are two parallel channels, **not automatic failover by default**: when both are healthy, an event can appear in both sinks. To achieve "write to B only when A fails," explicit monitoring and routing logic is required.

The fallback path should be relatively independent of the primary failure mode. For instance, if the log file fills up because the entire application partition is full, another spool on the **same partition** may also fail. stdout can also back up if the runtime log driver malfunctions.

### 5.2. Bounded Buffering and Intentional Backpressure

Buffers help absorb brief outages, but they must always have a **capacity** and a full-buffer policy:

| Policy | Benefit | Trade-off |
| --- | --- | --- |
| Block producer | Can reduce drops during short incidents | Increases tail latency, risks cascading failure to requests |
| Drop low-priority events | Protects business processing path | Loses diagnostic data, requires drop metrics |
| Drop oldest/newest | Bounds memory usage | Shifts which time window of logs is retained |
| Spill to disk spool | Can survive longer outages than a memory queue | Requires disk space, cleanup, replay, data protection |
| Sampling/rate limit | Reduces repetitive logs | Does not keep every event; exceptions must be defined |

**Do not use an unbounded queue** to "avoid losing logs": during a prolonged sink outage, memory will grow until the application runs out of RAM or crashes. Every finite buffer must eventually decide to **block, drop, switch sinks, or reject work**.

### 5.3. Retry and Recovery

For a remote collector, retries only make sense when the failure is recoverable. You should have:

- Timeouts for connecting and sending batches, never waiting indefinitely.
- Bounded exponential backoff with jitter so multiple instances do not retry in lockstep.
- Limits on retry count or duration, a circuit breaker, and controlled recovery checks.
- Ability to resend **only the unacknowledged batch**; do not treat a successful network write as a durable ack unless the protocol specifies it.
- Event IDs and deduplication when state is ambiguous: the collector may have received the batch while the response/ack was lost.
- Metrics for retries, pending event count, oldest wait time, and ultimately dropped events.

Retries can also generate **error logs from the logging pipeline itself**. Do not let the logger inside a failing transport route through the same failing transport, causing infinite recursion. Use a status listener, metrics, or an independent emergency channel, and rate-limit alerts.

### 5.4. Durable Spooling and Replay

If requirements demand surviving long outages, you can use an agent or pipeline that supports **disk buffering/spooling**:

```text
Application -> stdout / local agent -> bounded disk spool
                                        |
                                        v
                          retry + remote acknowledgment
                                        |
                                        v
                                    Collector
```

This design must clearly answer: are spool writes fsynced or only in the page cache? When are records deleted? If a crash occurs between send and ack, how are replay duplicates handled? How is a full spool/capacity limit handled? Must log data in the spool be encrypted and retention-limited?

A spool does not guarantee infinite capacity: disks can still fill up, fail, or be deleted. Set limits and monitor capacity; test recovery after a restart rather than only testing retries while the process stays alive.

## 6. Java 17 Example: Simulating Sink Failure and Fallback

To understand failure boundaries, this example uses **a minimal custom logging pipeline to illustrate the mechanism**, without assuming SLF4J/Logback automatically behaves identically. `PrimarySink` deterministically simulates a file I/O failure; `EmergencySink` writes to stdout. After the first failure, the pipeline switches to degraded mode and does not retry the primary on every event.

Create `SinkFailureDemo.java`:

```java
import java.io.IOException;

public class SinkFailureDemo {

    @FunctionalInterface
    interface PrimarySink {
        void write(String event) throws IOException;
    }

    @FunctionalInterface
    interface EmergencySink {
        void write(String event);
    }

    static final class ResilientWriter {
        private final PrimarySink primary;
        private final EmergencySink emergency;
        private boolean degraded;

        ResilientWriter(PrimarySink primary, EmergencySink emergency) {
            this.primary = primary;
            this.emergency = emergency;
        }

        // synchronized preserves ordering and state when multiple threads call concurrently.
        synchronized void log(String event) {
            if (!degraded) {
                try {
                    primary.write(event);
                    return;
                } catch (IOException failure) {
                    degraded = true;
                    emergency.write("ALERT primary unavailable: "
                            + failure.getMessage());
                }
            }

            emergency.write("FALLBACK " + event);
        }
    }

    public static void main(String[] args) {
        PrimarySink unavailableDisk = event -> {
            throw new IOException("simulated disk full");
        };
        EmergencySink console = System.out::println;

        ResilientWriter writer =
                new ResilientWriter(unavailableDisk, console);

        writer.log("INFO requestId=r-7 started");
        writer.log("ERROR requestId=r-7 failed");
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac SinkFailureDemo.java
java SinkFailureDemo
```

**Exact stdout:**

```text
ALERT primary unavailable: simulated disk full
FALLBACK INFO requestId=r-7 started
FALLBACK ERROR requestId=r-7 failed
```

Key takeaways:

1. Sending the first event to primary encounters an `IOException`. That event **was not persisted by primary**, so the pipeline attempts to write it to emergency.
2. The `degraded` flag prevents subsequent log calls from repeatedly hitting a destination already known to be broken. The alert message is emitted only once.
3. The `synchronized` keyword preserves observed ordering according to lock acquisition order in the example while protecting `degraded` state. This **does not guarantee global business ordering** across concurrent requests.
4. There is no automatic retry/reopen; a real system needs a health probe, recovery mechanism, and a way to avoid staying in degraded mode permanently.
5. stdout is an illustrative channel so output is easy to inspect. stdout itself can also stall or fail, and `PrintStream` has its own error reporting; calling `println` is not a durable ack.
6. Do not use `ResilientWriter` as-is as a production logging framework: the fallback write runs inside the lock and can block requests, there is no record size bound, no metrics, no recovery circuit breaker, no multi-sink strategy, and no emergency error handling. Its purpose is to clarify **detect -> reroute -> continue logging** with deterministic output.

If the application uses SLF4J, configure the backend/appender or logging agent to handle failures and monitoring at the appropriate layer. Do not wrap every `logger.info(...)` in `try/catch (IOException)` because the logging facade does not expose checked I/O exceptions that way.

## 7. Logback: Multi-Destination Configuration and Error Observation

Minimal `logback.xml` example for an application using SLF4J + Logback:

```xml
<configuration>
    <statusListener
        class="ch.qos.logback.core.status.OnConsoleStatusListener"/>

    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="FILE"
              class="ch.qos.logback.core.FileAppender">
        <file>logs/application.log</file>
        <append>true</append>
        <encoder>
            <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
        <appender-ref ref="FILE"/>
    </root>
</configuration>
```

This example sends each event to **both** appenders if they are operational and pass filters; it is **not a conditional router**. When the file cannot be opened/written, Logback can report errors via the status system while the console appender continues working. Do not rely on console-printed status as the sole alerting mechanism if the console/collector can also fail.

Limitations of this minimal configuration:

- `FileAppender` in this example **does not rotate files automatically**. Production requires a rotation strategy, size limits, and appropriate retention (typically `RollingFileAppender`).
- The path `logs/application.log` is relative to the working directory and depends on write permissions/volumes at deployment time.
- Two healthy appenders create two copies across two sinks; if the platform collects both files and stdout into the same collector, it can cause duplicates, extra cost, and inflated counts without deduplication.
- Appenders may report errors differently at startup vs. runtime depending on type and version. Do not treat the presence of `FILE` in XML as proof that the actual file is being updated.
- Verify that the backend has a single SLF4J provider, which config file name is actually loaded, and any profile overrides.

For Spring Boot applications, `logback-spring.xml` supports profile-based configuration; if `<springProfile>` is used, that is a Spring Boot extension rather than plain Logback XML. Before adding file/remote appenders, check whether the deployment platform already provides a stdout collector.

### Combining with AsyncAppender

If you wrap an appender with `AsyncAppender`, the target appender can perform I/O on a worker thread. That limits producer wait time **only until the queue fills up**, rather than providing durable storage or automatic failover to another destination. If the queue fills or the async worker fails, you still need a monitored block/drop policy and shutdown verification.

Some centralized collectors provide clients or agents with independent queuing/disk spooling/retry support. Understand the boundary where acknowledgment occurs and verify that the mechanism is actually enabled in the current configuration.

## 8. Recovering After the Destination Comes Back Online

Suppose a collector is disconnected for 30 seconds and then comes back online. A pipeline with buffering/retries must transition from **degraded** back to **healthy** without blindly dropping or duplicating events.

Conceptual workflow:

1. Detect that the endpoint is reachable again via a health probe or **bounded** trial sends.
2. Reopen connections/file handles according to safe rules; do not block all requests while probing.
3. Send remaining spooled events in a defined order/priority. If sending in batches, retain per-batch metadata and ack state.
4. Delete records only after reaching the appropriate **ack checkpoint**. If delivery state is ambiguous, replay and deduplicate using `eventId`.
5. Record outage duration, backlog size, lost/replayed event counts, and recovery timestamp.
6. Return to normal policy once the queue/spool stabilizes; avoid thundering-herd replays across many instances simultaneously.

**Processing order** should not be over-promised: a single-producer FIFO queue is easy to reason about, but multiple producers, multiple workers, batch retries, and networks can deliver events to the collector out of creation order. When reconstructing event sequences, use reliable timestamps within clock skew bounds, correlation IDs, and scoped sequence/event IDs.

For file sinks, recovery may require reopening the file due to log rotation or mount changes. Coordinate with the backend's rolling/reopen mechanism; do not arbitrarily close/open handles from an arbitrary thread without understanding the lifecycle.

## 9. Observability When the Logging System Itself Fails

A major risk is that **you cannot use the broken log path to report that it is broken**. Therefore, observability must also rely on a relatively independent channel:

| Metric/Signal | Value |
| --- | --- |
| `log_appender_errors_total` | Number of appender/sink failures |
| `log_dropped_events_total` | Number of events dropped by policy |
| `log_retry_attempts_total` | Retry activity, indicator of prolonged outage |
| `log_queue_depth` / capacity | Backlog and risk of blocking/dropping |
| `log_spool_bytes` / quota | Remaining fallback storage capacity |
| `log_last_successful_delivery_age` | How long since the sink last reported successful delivery |
| `log_delivery_latency` | Processing/drain rate compared to log generation |
| Synthetic canary/probe | Verifies test events actually appear in the collector |

These are **illustrative metric names**, not default metrics built into Logback. You need to instrument them or use metrics provided by your agent/backend, depending on the system. Alerting should be based on **outage duration, backlog growth rate, and drop rate**, not just raw IOException counts.

In Kubernetes/container deployments, metrics from the node/log agent are just as important as in-application metrics. An application may write to stdout successfully while the upstream collector fails ingestion. End-to-end visibility requires observing the tail of the pipeline.

### Avoiding Logging Incident Loops

Anti-pattern example:

```text
RemoteAppender send failure -> logger.error("RemoteAppender failed")
    -> RemoteAppender receives that event again -> continues failing -> ...
```

Rate-limit alerts, use the backend's status channel, or use independent metrics. If the fallback also fails, have a clear last-resort strategy and never silently violate audit guarantees when business contracts forbid it.

## 10. Testing Destination Failures (Fault Injection)

Testing only that normal logs appear is insufficient. You need to actively simulate sink outages in a repeatable way without affecting production resources.

### 10.1. Unit Testing with a Mock/Fake Sink

Based on the `ResilientWriter` model in section 6, you can replace `PrimarySink` with a fake that counts invocations and throws `IOException` on a chosen call. Key assertions:

- Events emitted before the failure reach primary.
- The event during which primary throws an exception is routed to fallback **once per the example policy**.
- After switching to degraded mode, new events stop calling primary.
- The primary failure alert is not emitted repeatedly for every event.
- If a reset/retry mechanism exists, it only returns to primary after a defined recovery check.

Tests should use a `List` or `BlockingQueue` to collect events and compare contents, without relying on real files or arbitrary timing. For multi-threaded tests, use thread-safe collectors and assert by set/ID rather than scheduler interleaving order.

### 10.2. File Appender Integration Tests

- Create a dedicated temporary directory for tests; do not touch the machine's real logs.
- Simulate permission errors, invalid paths, or replace the sink with an `OutputStream` that throws `IOException`. For example, create **a regular file** and attempt to use it as a log directory to force a file-open error in a controlled environment.
- Start a real Logback configuration, verify that the status/error handler records the error, and confirm an independent appender still receives events.
- Restore permissions/paths and check whether the file appender self-recovers or requires reinitialization according to the chosen backend.
- Clean up the logger context, appenders, and temporary files in `finally`; do not mutate the root logger configuration for the whole test suite and leak state to other tests.

Do not fill up the system partition to trigger `ENOSPC` in CI. To simulate write failures, use fake sinks, isolated filesystem quotas/containers, or controlled fault injection.

### 10.3. Network Collector Integration Tests

Use a test collector or controllable proxy, then:

1. Send several events with unique IDs while the collector is healthy and confirm receipt.
2. Disconnect or return controlled 429/503 responses, observing retries, queue depth, and producer latency.
3. Maintain the outage long enough to test buffer thresholds; verify that the block/drop/spool policy **matches configuration**.
4. Bring the collector back online, wait for drain with an explicit timeout, then compare event IDs and duplicate counts.
5. Restart the agent/process while a backlog exists (if durability is required) to test replay.
6. Read metrics/status logs from an independent channel; do not infer "no errors" just because the logger did not throw an exception.

If the protocol lacks per-event acks, tests can only conclude within what is observable. Do not claim end-to-end exactly-once simply because every event in a single test run appeared.

### 10.4. Testing Shutdown and Full Queues

For async appenders, specifically test these cases:

- Worker consuming normally, invoke graceful stop, and observe events reaching the sink.
- Worker blocked at the sink, queue full, producer blocked or dropping per configuration. Use `CountDownLatch` to control timing; do not use `Thread.sleep` as definitive proof.
- Abrupt process termination: events remaining in the memory queue may be lost. This is a durability test and must run in an isolated environment with cleanup procedures.
- For mandatory audit logs, verify that the application does not return "business success" when audit storage status has not met the committed criteria.

Set finite timeouts on tests, release latches in `finally` to avoid deadlocks, and clean up resources after each case.

## 11. Common Mistakes

| Mistake | Why It Is Dangerous | Better Approach |
| --- | --- | --- |
| "`logger.info` didn't throw, so the log is saved" | Backend may swallow/report I/O errors, queue may not have drained | Monitor status/metrics and verify the actual sink |
| Using an unbounded queue to avoid losing logs | Prolonged outages cause OOM | Bounded queue, full-queue policy, alerting |
| Writing fallback to the same full disk | Both sinks may fail together | Choose independent failure domains, test failover |
| Retrying continuously without backoff | Amplifies incident, wastes CPU/network | Exponential backoff, jitter, circuit breaker |
| No event IDs during replay | Events can duplicate after ack timeouts | Deduplicate by ID when needed |
| Assuming async logging is durable | Memory queues are lost on crashes | Durable spool if required, test restarts |
| Logging logger errors to the same failing logger | Recursion, congestion, or spam | Independent status/metric channel, rate limiting |
| Seeing a file exist and assuming it is being written | File may be stale, appender inactive | Probe actual writes and check mtime/collector |
| Ignoring stdout because a file exists | File may fail while console remains viable | Design multi-sink explicitly and avoid unintended duplicates |
| Treating audit log loss the same as DEBUG loss | Different risk levels | Separate pipelines/durability contracts and fail-closed policies |
| Checking only application-side errors | Agent/collector ingestion may fail after stdout | Observe the pipeline end-to-end |
| Testing with fixed sleeps | Async workers/remote collectors have no fixed timing | Barriers, acks, polling with timeout, event IDs |

## 12. Practical Incident Response Workflow

When the system reports missing logs, follow this sequence:

1. **Verify whether events were generated:** log level, filters, code conditions, logger name, sampling.
2. **Check the sink closest to the application:** file, stdout, or appender; cross-reference event IDs and timestamps.
3. **Check error status and backlog:** status manager, queue metrics, drops, retries, connections.
4. **Isolate where data was lost:** application -> agent -> transport -> collector -> storage/index/query.
5. **Mitigate business impact:** if producers are blocked, evaluate timeout/drop/failover policies and audit requirements.
6. **Fix the root cause:** file permissions, quota, mount config, DNS/TLS, tokens, collector capacity, rotation, or encoding.
7. **Controlled recovery:** reconnect the sink, replay backlog if any, check for duplicate events and post-recovery capacity.
8. **Quantify actual data loss:** document the time window, event types, evidence-based estimated count, and measurement limitations.
9. **Prevent recurrence:** independent alerts, periodic outage tests, queue/spool limits, incident runbooks.

If **there are no acks or end-of-pipeline counts**, you can only estimate what was lost; do not claim 100% recovery just because new logs appear after the fix.

## 13. Design and Operations Checklist

- [ ] Clearly classify diagnostic, operational, security, and audit logs by retention requirements.
- [ ] Define the "successfully delivered" boundary: accepted, queued, appended, acknowledged, or durable.
- [ ] Configure timeouts, queue/buffer capacity, discard/backpressure policies, and controlled fallback capabilities.
- [ ] Know whether the alternative sink is independent of the primary failure mode; avoid unintended log duplication.
- [ ] Record failures, drops, retries, queue/spool depth, and last successful delivery via independent metrics/channels.
- [ ] Test short outages, long outages, full queues, lost file permissions, collector restarts, and graceful shutdown.
- [ ] If replay exists, implement event IDs, acks, deduplication, and ordering/retention checks per contract.
- [ ] Ensure logs/spools are protected from leaking tokens, passwords, and sensitive data.
- [ ] Have runbooks for restarting appenders/agents, handling backlogs, and measuring log gaps.
- [ ] Do not let logger errors alter business outcomes unless mandatory audit rules are explicitly designed to do so.

**Remember:** when a destination is unavailable, the critical question is not just "does the application keep running?" but also **which checkpoint events reached, which events could be lost, how failures are detected, and how the system recovers**. Choose clear policies based on data criticality, design fallback paths and bounded queues, and validate them with fault injection rather than assuming a successful logger call means the log was saved.
