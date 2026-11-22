# Log Loss in Java: Causes, Detection, and Protecting the Logging Pipeline

## 1. Lesson Objectives

**Log loss** is a situation where an event that should have been recorded according to the system's observability policy **fails to reach the required storage or query destination**. This is a **logging reliability** issue, not merely about how many lines appear in the terminal.

For example: the application generated a payment failure event, the logger received an `ERROR` call, yet the dashboard has no corresponding record. You need to determine whether the event was filtered in the JVM, dropped when a queue filled up, still in memory when the JVM crashed, failed to be sent to the collector, rejected during indexing, or simply searched in the wrong place.

After this lesson, you will be able to:

- Distinguish between **no log generated, intentional filtering, unintentional drops, delays, and unfound logs**.
- Understand the stages of an event from Java code to the storage system and the limits of data durability.
- Identify common causes in JUL, SLF4J/Logback, Log4j2, async logging, files, containers, and collectors.
- Practice with a Java 17 program reproducing **queue full → event loss** and comparing it with **backpressure + drain**.
- Design tests, metrics, alerts, and an investigation workflow when log loss is suspected.
- Choose the appropriate reliability guarantee for operational logs, error logs, and critical audit/business events.

## 2. First, Define What "Lost" Means

A missing log line in search results does not automatically mean the system lost data. At least six situations should be distinguished:

| Situation | Nature | Is It Necessarily Log Loss? |
| --- | --- | --- |
| Code never reached the logger call | No event was generated. | No. Investigate the business execution path. |
| `DEBUG` discarded because logger is at `INFO` | **Filtering** per configured policy. | No, if that is the intended behavior. |
| Event accepted, but queue is full and drops it | **Loss** at the enqueue / async appender step. | Yes, if policy requires retaining that event. |
| Event is in a buffer, not yet exported | **Delay / backlog**. | Inconclusive; at risk of loss if stopped or expired. |
| Event is in storage, but queried with wrong time range, tenant, index, or permissions | **Not observed**. | Possibly not lost; verify at the storage layer. |
| Event deleted after retention or approved sampling | **Removed by policy**. | Not a technical bug if the data contract is still met. |

In a real system, you must clearly define a **logging contract**: which event types are produced, where they must be received, maximum latency, retention, and acceptable loss levels. Without this contract, the same missing line might be considered normal for `DEBUG` but a severe incident for audit logs.

**Example:** if production intentionally disables `TRACE`, missing `TRACE` lines is not an incident. However, if the application emitted an `ERROR` event to the logger, the backend is configured to send it to the collector, and the event disappears without explanation, that is an issue that needs investigation.

## 3. The Log Delivery Pipeline: Where Can Logs Be Lost?

A typical event passes through the following boundaries:

~~~text
Business event occurs
    │
    ▼
Application calls logger?
    │
    ▼
Logger / filter / level accepts?
    │
    ▼
Logging backend creates event
    │
    ├──── Synchronous ────────┐
    │                         │
    └──── Async queue ────────┤
                              ▼
                       Appender / Handler
                              │
                              ▼
                       Console / File / Socket
                              │
                              ▼
                 Runtime / Agent / Collector
                              │
                              ▼
                      Queue / Retry / Export
                              │
                              ▼
                     Storage / Index / Query
~~~

Each arrow is a **handoff boundary**. "`Logger.info()` returned" does not prove the entire pipeline succeeded.

| Checkpoint | Question | Common Failure Categories |
| --- | --- | --- |
| Business code | Did the code branch execute? | `if` conditions, early exception/return, event never actually occurred. |
| Logger API | Is the right provider/backend present? | SLF4J missing provider, wrong logger name, level blocks it. |
| Filter / configuration | Is the event allowed through? | Threshold, marker filter, custom filter, additivity, misrouting. |
| Async queue | Was the event actually accepted into the queue? | Queue full, discard policy, sampling, backpressure timeout. |
| Appender / handler | Did the backend write to the target successfully? | I/O error, missing file permissions, disk full, formatter/encoder exception. |
| Process / container | Was the log written to stdout/file before the process died? | JVM crash, `SIGKILL`, OOM kill, undrained buffer. |
| Collector | Did it receive and process the record? | Agent crash, receiver/pipeline disabled, parser failure, batching, expired retries. |
| Storage | Did it store and index the record? | Quota, index rejection, retention, wrong tenant, invalid timestamp field. |
| Query | Are you searching in the right place/time? | Timezone, clock skew, index pattern, access permissions, wrong filter. |

Do not look only at application logs. An exporter or storage failure can easily happen after the application has already written successfully to stdout.

## 4. Causes of Log Loss Inside the Java Application

### 4.1. Log Levels and Event Filtering

JUL has levels such as `SEVERE`, `WARNING`, `INFO`, `FINE`; Logback/Log4j2 use `ERROR`, `WARN`, `INFO`, `DEBUG`, `TRACE`, plus backend-specific levels. If root is configured at `INFO`, a `DEBUG` call usually does not produce an accepted event. This is **valid filtering**, not a queue dropping data.

Cases to check:

- A child logger has a different effective level than expected from root.
- The logger level allows the event, but a handler/appender/filter blocks it further down.
- A custom filter drops the event based on marker, message, or metadata.
- The logger name does not match the configured package.
- Dev/test and production configs differ, or the wrong profile is active.
- The event is created, but logger routing has no matching target appender.

**Important distinction:** if policy requires **WARN and above**, filtering out `INFO` is not a bug. If policy requires retaining `ERROR`, but a misconfigured custom filter drops `ERROR`, that is **unintended event loss**.

### 4.2. SLF4J Missing Provider or Wrong Backend

SLF4J is a facade/API, not the component that writes logs. With SLF4J 2.x, if no compatible provider is on the runtime classpath, SLF4J may warn and fall back to a NOP logger: logger calls produce no useful output. Applications with multiple backends or conflicting bridges can also route logs differently than expected.

Check runtime dependencies, startup warnings, and the selected provider. Do not see an `slf4j-api` dependency and assume the system already has a `FileAppender` or `ConsoleAppender`.

### 4.3. No Appender/Handler Actually Writing

A logger may accept an event without any destination consuming it. For example, in Logback/Log4j2, setting `additivity=false` on a package without attaching an appender, or in JUL calling `useParentHandlers(false)` without attaching a dedicated handler. Result: the record neither reaches the root appender/handler nor has its own sink.

Conversely, attaching the same appender at multiple levels can produce **duplicate logs**. Loss and duplication are two different routing bugs; both degrade incident investigation quality.

### 4.4. Exceptions in the Logging Path

Errors in a formatter, encoder, filesystem, network appender, or layout configuration can prevent an event from being written. Some backends report errors via a status logger or error handler rather than throwing exceptions into the business thread. Therefore, the application continuing to run normally **does not prove the logger is still working**.

In JUL, a `Handler` can report via `ErrorManager`; in Logback/Log4j2, inspect internal status and startup logs. When the logging pipeline itself is failing, do not rely **solely** on that same logging pipeline to raise alerts.

## 5. Async Logging and Queue Full: A Common Drop Point

Async logging decouples the caller thread from the writing thread. Events are typically placed into a queue/buffer, and a worker transfers them to the appender. The benefit is reduced caller latency while the queue still has capacity. The trade-off is that events may exist only in **RAM** before being written to the destination.

~~~text
Producer:  8,000 events/s ──┐
                            ▼
                      Bounded queue ── Worker: 5,000 events/s
                            │
                            ▼
                 Backlog grows 3,000 events/s
                            │
                            ▼
                        Queue full
                            │
         ┌──────────────────┼─────────────────┐
         ▼                  ▼                 ▼
       Block               Drop           Fallback
   caller waits        drops some         writes via
                        events          another path
~~~

At the example rates above, if the burst lasts 4 seconds and the worker sustains 5,000 events/s, the backlog grows by **approximately (8,000 − 5,000) × 4 = 12,000 events**, not counting scheduling, event size variance, and actual sink throughput. A smaller queue may fill up before the burst ends. A larger queue absorbs longer bursts, but holds more data in RAM and increases the time needed to drain on shutdown.

Three policy groups when the queue is full:

| Policy | Behavior | Reliability Impact |
| --- | --- | --- |
| **Block / backpressure** | Caller waits for space. | Reduces event loss from a full queue, but increases request latency and can cause stalls. |
| **Drop / discard** | Drops some events, sometimes by level. | Keeps the application unblocked, but loses information; must be counted and alerted on. |
| **Fallback** | Some backends switch to synchronous processing or another route. | Can avoid dropping events on some paths, but increases latency and complicates ordering. |

No policy alone protects against log loss from a JVM crash, disk failure, or unreachable collector. In particular, **`queue.put` succeeding only guarantees the event was accepted into the in-memory queue**, not that the event is durable.

### 5.1. Logback AsyncAppender

Logback Classic provides `AsyncAppender` with the following properties:

- **queueSize**: queue capacity.
- **discardingThreshold**: threshold that triggers discarding certain lower-level events per `AsyncAppender`'s policy. The default mechanism may drop `TRACE`/`DEBUG`/`INFO` when the queue is nearly full.
- **neverBlock**: if `true`, the application avoids waiting when the queue is full, but may drop messages; `false` typically blocks when full.
- **maxFlushTime**: maximum time to wait for remaining events when stopping the appender; if exceeded, unprocessed records may be dropped.

As an illustrative example in a project already using Logback, the following **logback.xml** snippet prioritizes **not intentionally dropping events via AsyncAppender's discard mechanism**, accepting blocking and bounding shutdown wait time:

~~~xml
<configuration>
    <appender name="FILE" class="ch.qos.logback.core.FileAppender">
        <file>logs/application.log</file>
        <append>true</append>
        <encoder>
            <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ASYNC" class="ch.qos.logback.classic.AsyncAppender">
        <queueSize>2048</queueSize>
        <discardingThreshold>0</discardingThreshold>
        <neverBlock>false</neverBlock>
        <maxFlushTime>5000</maxFlushTime>
        <appender-ref ref="FILE"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="ASYNC"/>
    </root>
</configuration>
~~~

Explanation:

1. **`discardingThreshold=0`** disables this `AsyncAppender`'s near-full threshold dropping of low-level events; it does not eliminate loss risks at other layers.
2. **`neverBlock=false`** allows the caller to wait when the queue is full. If the sink cannot keep up, business latency can still increase.
3. **`maxFlushTime=5000`** gives the worker about 5 seconds to finish when stopping the context. If backlog remains after that timeout, logs can still be lost; set this according to actual shutdown limits.
4. **`FILE`** depends on the filesystem and write permissions; `AsyncAppender` cannot fix disk full, file permission errors, or container kills.
5. Root attaches only **`ASYNC`**, avoiding accidentally attaching `FILE` directly to root and creating two duplicate write paths.

This is not an absolute durability configuration. Production needs to consider rolling/retention and a collector. Defaults/syntax can vary across Logback versions; read the documentation and test against the version you run.

### 5.2. Log4j2 Async Logger / Async Appender

Log4j2 offers **Async Appender** and **Async Logger**; their implementations differ, but both can face situations where logs are produced faster than the appender/sink can consume them. In modern Log4j2, the **`log4j2.asyncQueueFullPolicy`** property has typical options:

- **Default**: waits when no enqueue space is available per default policy; this does not mean loss cannot happen from other failures.
- **Discard**: when the queue is full, discards events whose severity does not exceed **`log4j2.discardThreshold`**; a common illustrative threshold is `INFO`.

You cannot conclude "`ERROR` is never lost" just because a drop policy prioritizes higher levels. Events can still be lost after enqueue, during shutdown, at the exporter, or in storage. Check the queue-full policy for your **exact Log4j2 version**, inspect the status logger, and measure under sustained overload.

## 6. Standalone Java 17 Example: Full Queue Dropping Events

The following program intentionally uses an **`ArrayBlockingQueue`** with capacity 2 and submits 3 events **before the worker starts reading**. Using **`offer`**, the third event is rejected without blocking the caller. The second part uses **`put`** with the same capacity and a background worker: the caller may have to wait, but all three events are processed before the program exits.

This is a **learning model** of queues/backpressure, not a production logging library. The worker writes results to an in-memory list instead of disk to clearly demonstrate **queue drops** without confusing them with filesystem errors.

Save as **LostLogsDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class LostLogsDemo {
    private static final String STOP = "<STOP>";

    public static void main(String[] args) throws InterruptedException {
        // Part 1: attempt to write 3 events before the worker starts.
        BlockingQueue<String> dropping = new ArrayBlockingQueue<>(2);
        List<String> dropWritten = new ArrayList<>();
        int attempted = 0;
        int accepted = 0;

        for (String event : List.of("A", "B", "C")) {
            attempted++;
            if (dropping.offer(event)) {
                accepted++;
            }
        }

        final int acceptedCount = accepted;
        Thread dropWorker = new Thread(() -> {
            try {
                for (int i = 0; i < acceptedCount; i++) {
                    dropWritten.add(dropping.take());
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "drop-worker");
        dropWorker.start();
        dropWorker.join();

        System.out.println("DROP: attempted=" + attempted
                + " accepted=" + accepted
                + " dropped=" + (attempted - accepted));
        System.out.println("DROP: written=" + dropWritten);

        // Part 2: block the producer instead of dropping events when the queue is full.
        BlockingQueue<String> blocking = new ArrayBlockingQueue<>(2);
        List<String> blockWritten = new ArrayList<>();

        blocking.put("A");
        blocking.put("B");

        Thread blockWorker = new Thread(() -> {
            try {
                while (true) {
                    String event = blocking.take();
                    if (STOP.equals(event)) {
                        break;
                    }
                    blockWritten.add(event);
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "block-worker");
        blockWorker.start();

        blocking.put("C");       // May wait until the worker takes an event.
        blocking.put(STOP);      // Signal the worker to stop after processing C.
        blockWorker.join();      // Print results only after the worker has stopped.

        System.out.println("BLOCK: written=" + blockWritten);
    }
}
~~~

Compile and run with **JDK 17 or later**, with no external dependencies:

~~~bash
javac LostLogsDemo.java
java LostLogsDemo
~~~

**Deterministic stdout** on a normal run:

~~~text
DROP: attempted=3 accepted=2 dropped=1
DROP: written=[A, B]
BLOCK: written=[A, B, C]
~~~

Why the output is deterministic:

- In the **DROP** section, the worker starts **only after** all three `offer` calls finish, so the capacity-2 queue is guaranteed to accept only `A` and `B`; `C` is rejected.
- In the **BLOCK** section, the worker starts before the producer sends `C` and the `STOP` sentinel. If the queue is still full, `put("C")` blocks; the worker taking an event frees a slot. FIFO guarantees the worker receives `A`, `B`, `C`, and then `STOP`.
- **`join()`** ensures `main` reads both lists only after the worker has finished, so output does not depend on thread scheduling order.
- The `STOP` sentinel is generated internally by the program; if real messages could match the sentinel, use a dedicated event type or a safer shutdown mechanism.
- The code does not simulate crashes, `fsync`, retries, disk, or collectors. The `BLOCK` section shows no drops due to a full queue under normal conditions; **it does not prove durability**.

Try changing **`offer`** in the `DROP` section to **`put`** while the worker **has not started yet**: with a capacity-2 queue, the third `put` can wait forever because nobody is consuming. This is a risk of a blocking policy when no consumer exists or the consumer has died. In a real logging framework, monitor worker health and use bounded shutdown rather than relying solely on "never drop."

## 7. Flush, Close, and Shutdown Do Not Mean Durable Storage

In a Java application, there are multiple levels of completion:

~~~text
Event created
    ↓
Enqueued in RAM async queue
    ↓
Worker takes event
    ↓
Appender.write() / stream.write()
    ↓
Flush library/OS-level buffers
    ↓
Filesystem/collector receives data
    ↓
Durably stored, indexed, and queryable
~~~

**Flush** usually means pushing data out of the caller layer's buffer, not necessarily writing it physically to disk or having it safely stored by a central backend. **Close** usually flushes and releases the stream/handler's resources, but still provides no end-to-end guarantee. With JUL `FileHandler`, each record is flushed per the JDK's documented implementation behavior, yet an OS/disk crash or log shipper failure can still lose it afterward.

### 7.1. Graceful Shutdown

When a service stops normally:

1. Stop accepting new requests/tasks, or control the phase that generates new logs.
2. Finish in-flight tasks; if using async workers, allow them to drain the queue within the allotted time.
3. Invoke the logging backend's stop/close mechanism according to the framework lifecycle.
4. Wait the necessary grace period before the process exits.
5. Monitor remaining queued events, flush duration, and sink errors if the backend exposes telemetry.

Do **not** call `System.exit` abruptly to "reset the logger" mid-request. In Spring Boot, let the application context and logging system close via the framework lifecycle instead of manually closing the backend while threads are still using it.

### 7.2. Situations Where Shutdown Cannot Save Logs

- **`SIGKILL`**, `Runtime.halt`, power loss, or a severe JVM crash can bypass shutdown hooks.
- **OOM kill** or forced container termination can destroy an undrained queue.
- Shutdown grace period is too short for the backlog.
- The sink hangs, the queue cannot drain, or the logging worker encounters I/O errors.
- New log files reside on temporary/ephemeral storage and are deleted when the container is replaced.

Therefore, a **large `maxFlushTime`** or a **shutdown hook** only reduces risk; it does not replace a durability strategy when events have strict retention requirements.

## 8. Log Files, Rotation, and the Operating System

At the file layer, logs can be lost or become unobservable due to:

- **Missing write permissions** on the directory, disk full, quota exceeded, or broken file handles.
- `FileHandler`/appender creating the file in an **unexpected working directory**.
- The appender writing to the right file, while the agent only reads stdout or a different glob pattern.
- **Rotation** renaming and deleting/archiving the file before the shipper finishes reading it, or the shipper falling behind.
- Files written inside an **ephemeral container filesystem** and lost when the pod/container is replaced.
- Log files truncated, deleted, or overwritten because `append=false` is configured.
- The parser/shipper having a line-size limit and dropping very long events.

**Logback `RollingFileAppender`**, JUL `FileHandler` rotation, and external rotation tools coordinate differently. Do not configure two mechanisms to rotate the same file without understanding how they interact; the risk is writing to a stale inode, missing the tail end, or deleting a file before the shipper reads it.

In containers, many architectures prefer writing to **stdout/stderr** and letting the platform collect them. However, stdout also has buffers and its own collection path; the Docker/Kubernetes runtime, log driver, and collector can be overloaded or have different retention settings. Switching to console does not automatically make logs "unlosable."

### Relative Paths and stdout/stderr

For example, an application writing **`logs/application.log`** in an IDE may create the file in the project directory; when run as a service, that path may resolve to a different working directory. JUL `ConsoleHandler` typically writes to **`System.err`**, whereas another backend's console appender may choose stdout. Looking in the wrong stream can also make it seem like logs have vanished.

## 9. Distributed Log Pipelines: Collector, Retry, and Storage

A pipeline typically consists of an agent/receiver, processors, exporters, and storage. For example, OpenTelemetry Collector components are configured per pipeline; **declaring a receiver without wiring it into a service pipeline** means the receiver will not actually process data.

Common causes:

| Layer | Failure Example | Consequence |
| --- | --- | --- |
| Agent/file tailer | Wrong path, missing permissions, fails to follow rotation. | Some lines are never read by the agent. |
| Receiver | Wrong protocol/port, pipeline not enabled, overloaded. | Collector does not receive or refuses records. |
| Processor | Filter/drop/sampling, parser error, memory protection. | Records are dropped or transformed unexpectedly. |
| Queue | Out of capacity, no persistent storage, process dies. | Unexported records may be lost. |
| Exporter | Network error, auth failure, retries exhausted, slow backend. | Records back up and may eventually be dropped. |
| Storage/indexer | Quota, rejection, TTL/retention, mapping/timestamp error. | Cannot be queried or data is discarded. |

**Retries** reduce loss from transient errors, but are not free: if retries run too long, the queue fills up; if retries are too short, brief network blips can cause drops. If the backend already received the event but the ACK is lost and the exporter resends, **duplicates** can occur. Depending on design, a system may provide at-least-once, best-effort, or similar semantics; do not assume end-to-end exactly-once delivery.

OpenTelemetry Collector documents using a **sending queue, `retry_on_failure`, and optional persistent storage** for supported exporters. Check your actual version and exporter: enabling an in-memory queue helps survive brief outages but does not preserve the queue across crashes; enabling a persistent queue still depends on healthy disk and available quota.

**Metrics worth checking** if your collector supports them: queue size/capacity, enqueue failed log records, receiver accepted/refused, exporter sent/send failed, and retry errors. Exact metric names can vary by Collector/component version; consult the documentation and observe actual telemetry.

## 10. Unfound Logs Are Not Necessarily Lost

An event may already be stored yet not appear in a dashboard because of:

1. **Wrong search time range:** event timestamp differs from ingest timestamp; mismatched timezones; clock skew pushes records outside the query window.
2. **Searching the wrong log stream/index/tenant:** the application sends under a different environment, service, or namespace.
3. **Unexpected logger/trace fields:** `traceId` was not propagated across a thread pool; searching by `traceId` misses events lacking that field, even though the record is in storage.
4. **Index lag:** the record has been received but is not yet queryable.
5. **Retention:** the event existed but was deleted per TTL.
6. **Query permissions:** the account lacks permission to view a specific tenant/index.
7. **Parser field changes:** the event has the message, but `level`/`logger_name` was renamed or remains in the raw payload.
8. **Truncation/chunking:** large messages are split or truncated, so searching for a full string fails.

A useful diagnostic workflow:

~~~text
Event not visible in dashboard
      │
      ├─ Search by service + event_id + wider time window?
      ├─ Search raw stream / ingest timestamp instead of only parsed fields?
      ├─ Could the agent read the file/stdout containing the event?
      ├─ Did the collector receive and export the record?
      └─ Does storage confirm ingest/index and query permissions?
~~~

Conclude loss only when evidence shows the event should exist yet **does not exist at a committed boundary** or was dropped at a confirmed layer. Do not rely on a single negative query.

## 11. Detecting Log Loss with Telemetry and Reconciliation

### 11.1. Tracking Event Handoff Milestones

A measurement model:

~~~text
Produced → Accepted → Enqueued → Written → Collected → Indexed
    P          A          Q          W          C          I
~~~

These variables are **conceptual milestones**, not metrics every library provides out of the box. Each milestone must be measured in a verifiable way:

- **Produced**: code actually calls logging or generates the business event.
- **Accepted**: logger/filters accept it; levels filtered by policy are counted separately if needed.
- **Enqueued**: event is placed into the async queue.
- **Written**: appender reports success at the point defined by the backend.
- **Collected**: agent/collector receives the record.
- **Indexed**: backend stores/indexes it for querying within SLA.

Do not mechanically subtract **`P − I`** and declare that the number of lost logs. Layers are asynchronous, have time windows, batching/retries, duplicates, and sampling. Normalize to the same event scope, the same time window, and an appropriate lag allowance.

### 11.2. Essential Metrics and Alerts

| Metric or Signal | Value |
| --- | --- |
| Async queue occupancy / capacity | Detects backlog and queue-full risk. |
| Dropped/discarded event count by level/reason | Shows logs were dropped and assesses severity. |
| Enqueue block duration | Measures business latency impact when not dropping. |
| Appender error count/status | Detects sink I/O errors, encoder/rotation failures. |
| Collector accepted/refused, exporter send failed | Pinpoints failures between ingest and export. |
| Retry queue size, age, oldest item | Detects outages lasting longer than tolerance. |
| Process restarts / OOM kills / shutdown duration | Correlates with events still in RAM at termination. |
| Disk usage, quota, file permission errors | Detects inability to write log files. |
| Delay between event timestamp and ingest/index timestamp | Distinguishes delayed logs from lost logs. |

Alert on **rates and duration**—for example, non-zero dropped `WARN`/`ERROR` within an approved window, retry queue >80% for 5 minutes, sustained collector exporter failures, or log ingestion suddenly dropping to 0 while traffic remains normal. These thresholds are examples only: calibrate them to your workload and SLOs.

**Note:** if the logging system is broken, alerts written only via that logger may never arrive. Maintain metrics/health checks or a monitoring channel independent of the logging path being observed.

### 11.3. Event IDs and Completeness Checks

For a deterministic set of test events, assign a unique **`event_id`** to each and send them through the entire pipeline. After waiting long enough for ingestion delay, count:

- How many IDs were generated by the test.
- How many IDs are present in the primary sink.
- Which IDs are missing (gaps) and which appear more than once (duplicates).
- Whether missing/duplicate IDs correlate with overload, restarts, or collector errors.

Tests must scope test data appropriately and never use real secrets or PII. If the system uses intentional sampling/dropping, include only events **committed to be retained** in the reconciliation.

## 12. Proactive Failure Testing (Failure Injection)

| Test Scenario | Purpose | Expected Verification |
| --- | --- | --- |
| Normal load, clear queue | Establish baseline. | Correct level/destination; latency within SLO. |
| Short burst exceeding sink rate | Test buffering. | Queue grows and recovers; verify full-queue policy. |
| Sustained overload | Test real limits. | Block/drop/fallback follows policy, no silent loss. |
| Graceful stop with backlog | Test drain. | Remaining events processed within grace period; telemetry recorded. |
| Forced termination in test | Understand RAM queue limits. | Recognize possible log loss; do not assume zero-loss. |
| Disk full / unwritable path | Test appender errors. | Error signal emitted and fallback behaves as designed. |
| Collector/network offline then recovered | Test retries. | No premature drops outside policy; queue recovers. |
| Collector crash without persistent queue | Test durability. | In-RAM portion may be lost; quantity is measured. |
| Rotation/retention under load | Test file tailer. | No unintended gaps before/after rotation. |
| Querying wrong timezone/index | Avoid misdiagnosis. | Event can be found via raw timestamp/correct sink. |
| Multiple producers / multiple workers | Test ordering. | Do not assume global ordering; `event_id` remains traceable. |
| Extremely long log message | Test truncation/parser. | Know size limits and how oversized records are handled. |

Inject failures only in an isolated test environment. Never shut down a collector or fill up production disks "to test." Use synthetic data, tag with a test run ID, and clean up test logs per retention.

## 13. Remediation by Failure Location

### 13.1. If Lost at Logger/Filter

- Check the logger's effective level and handlers/appenders/filters.
- Identify the actual runtime backend/provider; do not edit an XML file for a library not used at runtime.
- Check `additivity`/`useParentHandlers` and verify an actual appender is attached.
- Fix the policy on the specific package/logger; do not blindly set root to `DEBUG`.
- Write tests for `WARN`/`ERROR` events that are committed to be retained.

### 13.2. If Lost at Async Queue

- Measure producer rate, consumer throughput, queue occupancy, and dropped count.
- Check `neverBlock`, `discardingThreshold`, queue-full policy, and worker count per backend.
- If event retention is prioritized, choose bounded backpressure; monitor latency.
- Reduce log volume at the source: remove redundant messages, use intentional sampling, set sensible levels; do not use unbounded queues.
- Improve sink or pipeline throughput rather than merely increasing queue size.
- Manage startup/shutdown lifecycle and test stopping under backlog.

### 13.3. If Lost at File/Console

- Verify path, filesystem, write permissions, disk/quota, and working directory.
- Inspect the backend's status/error handler.
- Check rotation, retention, and whether the file shipper keeps up.
- Check stdout/stderr and the runtime log driver.
- Ensure appenders are not closed while tasks are still using them.

### 13.4. If Lost at Collector/Storage

- Check receiver pipelines, parsers/filters, queue/retry settings, and exporter errors.
- Verify endpoint, auth, network, namespace, index, and mapping.
- Monitor collector overload and memory/disk usage.
- Review retry and persistent queue policies when outage tolerance is needed; understand cases where drops can still occur.
- Use `event_id` to pinpoint which boundary lost the event rather than passing blame across teams based solely on missing logs.

## 14. Required Guarantees by Event Type

Not all logs carry the same business value. A suggested classification:

| Data Type | Appropriate Policy |
| --- | --- |
| Detailed `TRACE`/`DEBUG` | May allow sampling/dropping if operations approves; must be transparent. |
| Operational `INFO` | Set appropriate completeness and latency targets; monitor backlog/drops. |
| `WARN`/`ERROR` | Higher retention priority; monitor loss or sink failures, do not assume every `ERROR` is automatically durable. |
| Security audit | Requires access control, integrity, and regulatory retention policies; do not rely on ordinary RAM queues. |
| Events affecting money, transactions, state changes | Persist in a business data store with appropriate durability/atomicity; logs are only an observability view. |

**Important:** if **zero event loss** is a hard business requirement, do not rely solely on a logger. For example, when an order is recorded successfully and a downstream event must be delivered: use a durable event table, a transactional outbox, or an event store/message broker with acknowledgements, retries, idempotency, and explicit error-handling rules.

A common design:

~~~text
Business transaction
      │
      ├── update state in DB
      └── write outbox event in same transaction
                    │
                    ▼
            Worker reads outbox
                    │
                    ▼
          Publish + ACK/retry
                    │
                    ▼
          Idempotent consumer
~~~

Even this pattern must handle retries/duplicates and infrastructure failures, but it moves critical delivery guarantees out of the best-effort logging path. Do not use a single `INFO` line in a file as the sole record for financial or audit events with retention obligations.

## 15. Investigation Scenario: ERROR Logs Vanish After Deploy

A newly deployed Java service shows an increased HTTP 500 error rate, but the dashboard has no corresponding `ERROR` logs.

### Step 1: Check Independent Signals

Confirm HTTP 500s actually increased via request metrics (not just logs). Find a test request with a request ID/trace ID. Verify whether the code path emits an `ERROR` event.

### Step 2: Check Inside the JVM

- Did the backend/provider change after deploy?
- What is the effective level on the logger class/package?
- Was a new filter added, `additivity=false` set, or an appender removed from root?
- Is the async appender dropping or building a backlog?
- Does the file/console appender report any error status?

### Step 3: Check the Process

Did the deployment restart or get OOM-killed? Is the container writing stdout/stderr where the collector reads? Is a file appender writing to an ephemeral directory? Is the shutdown grace period long enough to drain the backlog?

### Step 4: Check the Collector and Storage

Did the collector show increased `rejected`/`enqueue failed`/`send failed`? Is the retry queue full? Is the exporter pipeline enabled? Is the backend returning auth/quota errors? Search by ingest timestamp and raw stream, not only by `traceId` or event timestamp.

### Step 5: Isolate and Improve

If lost due to a full queue, adjust the queue policy or increase sink capacity; if lost due to configuration, fix the right backend/route; if not lost but searched in the wrong place, fix the field/index/query. After recovery, add a test or metric at the **broken boundary** to catch regressions early on the next deploy.

Avoid enabling `DEBUG` across all of production just to find an `ERROR` event: that can increase logging load and make a full queue worse.

## 16. Common Misconceptions

1. **"`Logger.info()` returned, so the log is saved."** False. It may not have left RAM or been received by the collector yet.
2. **"Async logging never drops logs."** False. Queue-full and shutdown policies determine much of the risk.
3. **"Just make the queue size huge and loss goes away."** False. If the producer outpaces the consumer over time, any bounded queue fills up; RAM usage and drain time also increase.
4. **"A high `maxFlushTime` guarantees no loss when the process is killed."** False. `SIGKILL`/crashes may not run shutdown logic.
5. **"`ERROR` is always retained."** False. Some policies prioritize it, but do not guarantee survival across every layer.
6. **"Not seeing a record in the dashboard means it was lost."** False. You may be querying the wrong index, timezone, field, permissions, or before indexing completes.
7. **"Flush equals `fsync` and end-to-end durability."** False. Each layer has a different meaning for flush/ACK.
8. **"The collector has retries, so it never drops."** False. Queues are bounded, retries can expire, and disks can still fail.
9. **"Retrying multiple times is exactly-once."** False. Retries can create duplicates without idempotency/deduplication.
10. **"A separate log file is a safe audit store."** False. Audits require appropriate storage, access control, retention, and integrity policies.
11. **"Disabling a level is unintended log loss."** False if filtering is an agreed-upon policy.
12. **"The application didn't crash, so logging must be working."** False. Appenders can fail silently or downstream pipelines can stop accepting records.

## 17. Practice Exercises

**Exercise 1 — Bounded queue.** Run `LostLogsDemo.java`, change capacity from `2` to `3`, and predict how the `DROP` output changes. Explain why the `BLOCK` section still receives all events.

**Exercise 2 — Handoff.** Draw the pipeline of a Spring Boot application using Logback `AsyncAppender` → stdout → collector → storage. Attach observable evidence (metric, status, an event ID) to each milestone.

**Exercise 3 — Shutdown.** Design a test that stops an application while it still has a backlog. How do you measure pending count, sent count, and total drain time? What can happen if the container is forcefully killed?

**Exercise 4 — Lost or mis-queried?** A log does not appear when searching by `traceId`, but is found by raw message at the same timestamp. Determine whether this is a queue drop; check MDC propagation and the parser before concluding.

**Exercise 5 — Mandatory events.** Choose an example of an order state-change event that must not disappear. Analyze why a log file/async logger is insufficient and propose an outbox/ACK/idempotency mechanism.

**Exercise 6 — Failure injection.** In a test environment, simulate the collector being unreachable briefly and then recovering. Monitor queue, retries, accepted/sent counts, and event IDs to determine whether any actual drops occurred.

## 18. Summary

Log loss is a **failure in the information delivery pipeline**, not always a bug in a single logger statement. Verify each boundary from **code → level/filter → async queue → appender → stdout/file → collector → storage → query**, distinguishing **true drops** from **delays, intentional filtering, and incorrect queries**.

Three most important habits:

1. **Define a contract by event type:** which events can be dropped, which must be retained, and where they must arrive.
2. **Make the path and error states measurable:** queue occupancy, discarded count, appender errors, collector retry/export, ingest lag, and test event IDs.
3. **Design verified recovery:** clear backpressure/drop policies, shutdown draining, overload/crash testing, and separate durable storage for truly critical business events.

### Technical References

- Logback — AsyncAppender, queue, discardingThreshold, neverBlock, maxFlushTime: https://logback.qos.ch/manual/appenders-async-sift.html
- Log4j2 — Asynchronous Loggers and trade-offs: https://logging.apache.org/log4j/2.x/manual/async.html
- Log4j2 — Configuration properties and asyncQueueFullPolicy: https://logging.apache.org/log4j/2.x/manual/systemproperties.html
- Oracle Java SE 17 — FileHandler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html
- Oracle Java SE 17 — ArrayBlockingQueue: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html
- OpenTelemetry Collector — Troubleshooting: https://opentelemetry.io/docs/collector/troubleshooting/
- OpenTelemetry Collector — Resiliency: https://opentelemetry.io/docs/collector/resiliency/
