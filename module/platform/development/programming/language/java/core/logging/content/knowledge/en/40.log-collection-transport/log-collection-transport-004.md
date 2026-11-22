# Container stdout: Collecting and Transporting Java Application Logs

## 1. Overview: What Does “Logging to Container stdout” Mean?

When deploying a Java application in Docker, Kubernetes, or a similar container platform, the application process's **stdout** (standard output, file descriptor 1) and **stderr** (standard error, file descriptor 2) are typically the two streams that the container platform can collect. Instead of requiring the application to create and manage `/var/log/myapp.log` files inside the container, a common design is:

1. The application uses a **logging framework** such as Logback, Log4j 2, or JUL to create structured log events.
2. An appender/handler writes formatted logs to **stdout** (or stderr according to policy).
3. The container runtime captures bytes/lines from both streams; the infrastructure layer manages log files or logging drivers.
4. A log collector/agent reads or receives these records, enriches them with container/pod metadata, and forwards them to a backend for storage, search, and alerting.
5. Operators query logs using `docker logs`, `kubectl logs`, or a centralized logging system depending on the stage and retention capability.

**Container stdout** is not a message broker, database, or complete observability solution. It is only the **interface** between the Java process and the runtime/orchestrator's log collection mechanism. Calling `logger.info(...)` and writing to stdout **does not guarantee** that the final record has been indexed in the centralized system.

### Lesson Objectives

After this lesson, you will be able to:
- Understand stdout/stderr and the differences between `System.out.println`, `System.err.println`, and ConsoleAppender/Handler.
- Describe the flow **Java logger → stdout/stderr → runtime → kubelet/driver → collector → log backend**.
- Configure Java logging to emit events to the console while avoiding duplicate writes across multiple appenders.
- Use Docker and Kubernetes commands to view logs, and understand container lifecycle and rotation limits.
- Design a **one-event-per-line** format and JSON with structured fields, timestamps, severity, and correlation IDs.
- Recognize risks such as **multiline exceptions**, dropped logs, blocking/backpressure, restarts, container rotation, and duplicate ingestion.
- Test end-to-end readback and protect secrets/PII in logs.

## 2. Three Concepts to Distinguish

| Concept | What Is It? | Primary Responsibility |
| --- | --- | --- |
| **Logging API/framework** | SLF4J + Logback, Log4j 2, `java.util.logging` | Event creation, level, message, throwable, MDC, formatting/routing |
| **stdout/stderr** | Two standard byte streams of a process, typically bound to file descriptors 1/2 | Outputting data from the process; no built-in query, indexing, or retention |
| **Container logging infrastructure** | Docker logging driver, Kubernetes CRI/kubelet, node agent/collector, backend | Capturing, attaching metadata, storing/rotating, forwarding, querying per architecture |

**`System.out.println` is not a logging framework.** It can print a line that the runtime collects, but it lacks levels, schemas, configuration, MDC, and governance by logger name. In real applications, use a logger with a properly designed ConsoleAppender/Handler.

**`stderr` does not mean “guaranteed alert”** and does not automatically translate into alert severity. It is simply another stream. Some platforms/collectors attach a `stream=stderr` label, but alerting rules should be based on level, error code, metrics/SLIs, and actual impact—not by assuming every byte on stderr is a critical incident.

**“Written to stdout” is different from “stored in the backend”.** Between these two points, there can be buffering, rotation, network outages, agent retries, drop policies, and crash points.

## 3. Typical Collection Architecture

```text
                    Java application (container)
                    +----------------------------+
Business code ---->|  SLF4J / Log4j 2 / JUL     |
                    |     |                      |
                    |  encoder / appender        |
                    |     |                      |
                    +-----+----------------------+
                          |
                       stdout (fd 1)
                       stderr (fd 2)
                          |
                          v
               Container runtime / CRI
                          |
                  node log files/driver
                          |
                     Log collector
                 (node agent/forwarder)
                          |
                   network transport
                          |
                      Log backend
               parse / index / retention
                          |
                     search / alert
```

Each layer has a specific responsibility:
- **Application:** choose safe fields, decide log levels, add correlation ID/trace ID, format according to schema.
- **Runtime:** attach to the container's stdout/stderr streams and implement the logging driver or write files according to its specification.
- **Node/collector:** receive/read records, identify pod/container source, handle line and multiline parsing, maintain checkpoints, retry, and batch.
- **Transport:** send over the network with authentication/encryption, bound backlogs, and manage errors.
- **Backend:** parse, index, retain, enforce access control, and provide search/alerting.

Some layers may be skipped or replaced by managed services, but **you must know which layer owns buffering, retries, capacity, and delivery confirmation**. Logs required for mandatory auditing may need a separate durable mechanism, because stdout is typically a best-effort diagnostic stream depending on the actual pipeline.

### 3.1. Why Is Console Logging Preferred in Containers?

Common benefits include:
- **No need to manage log files inside the image/container:** reduces issues with file paths, write permissions, and local cleanup.
- **Standard tooling compatibility:** `docker logs`, `kubectl logs`, and platform collectors can read the output.
- **Separation of concerns:** the application only emits events; infrastructure decides where to store, index, rotate, and retain them.
- **Scale-out support:** each replica writes to the console; the collector enriches with pod/container metadata.
- **Consistent deployment:** log configuration can vary by environment without mounting dedicated log directories.
- **Convenient testing:** a demo Docker container can be observed immediately via log commands.

However, stdout does not eliminate all decisions: synchronous writes can **block**, excessive log volume can cause resource pressure, collectors can drop records, node disks can still fill up, and tracing after a pod is deleted depends on centralized storage.

### 3.2. When Might File Logs Still Be Needed?

Some legacy systems or libraries require files, or audit logs need a separate durable/append-only sink. In such cases, you must manage:
- Volumes/persistence and access permissions.
- Rotation, retention, locking, disk quotas, and crash policies.
- Agents tailing files with offsets/checkpoints, handling inode/rename/truncate events.
- Avoiding writing the **same event** to both stdout and a file while collecting from both sources, which causes duplicate logs.
- Designing integrity guarantees for mandatory auditing; do not treat default log files as a transactional store.

File logging can be a deliberate choice, but **do not write to files inside a container merely out of habit from traditional servers**.

## 4. stdout and stderr of a Java Process

In Java:
- `System.out` is the standard `PrintStream` for stdout.
- `System.err` is the standard `PrintStream` for stderr.
- Logging frameworks use configured **handlers/appenders**; the `ERROR` level does not automatically force output to stderr.
- Output may involve buffering and encoding; flushing/closing must match the lifecycle.

Small example:

```java
// Illustrative snippet: actual output goes to two separate streams.
System.out.println("service startup complete");
System.err.println("diagnostic: startup validation warning");
```

When run directly in a terminal, both streams may appear side by side. When collected by a container runtime, they may be stored under `stream=stdout` and `stream=stderr` fields. **The relative ordering between the two streams does not necessarily reflect the exact program execution order**, due to separate buffers and collection mechanisms. Do not build business invariants relying on the interleaved order of stdout/stderr.

### 4.1. JUL Defaults Differ from Logback

The JDK's `java.util.logging.ConsoleHandler` outputs to **`System.err`** by default, not stdout. Therefore, running an application configured only with JUL's `ConsoleHandler` does not mean events go to stdout, even though `docker logs` may still display both stdout and stderr.

With Logback's `ConsoleAppender`, you can choose `System.out` or `System.err`; Log4j 2's Console appender also allows choosing the target. Always inspect the active configuration rather than assuming from the name “Console”.

**Do not route all errors to stderr just for “tradition”** if the production pipeline only collects stdout. It is best to establish a consistent policy to collect both streams or route intentionally, and use the `level`/`severity` field in the record for classification.

### 4.2. Synchronous Behavior and Performance Characteristics

Even when a logger calls a very simple appender, writing to stdout can block if the pipe buffer is full or the downstream reader is slow; details depend on the OS, container runtime, logging driver, buffering, and configuration. Potential consequences:
- Business threads experience increased latency when a synchronous appender waits.
- Slow backends/collectors cause queues/buffers to grow.
- CPU/GC usage increases when formatting large stack traces or complex JSON events.
- Disk/node storage faces pressure from high log volume.
- If using an async appender, a full queue may **drop or block** depending on the backend's policy; never assume async means zero log loss.

**The goal is bounded behavior:** limit event size, avoid dumping raw payloads, measure queue depth, dropped events, and stdout write latency, and know the policy when the log sink fails.

## 5. Standalone Java 17: Writing JUL Directly to stdout

The following example uses **JDK 17**, requiring no Maven or external libraries. JUL creates log records, and a custom `Handler` writes events to `System.out` **line by line**, instead of using the default `ConsoleHandler` which writes to stderr.

Create the file `ContainerStdoutDemo.java`:

```java
import java.io.PrintStream;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class ContainerStdoutDemo {
    private static final class StdoutLineHandler extends Handler {
        private final PrintStream out;

        StdoutLineHandler(PrintStream out) {
            this.out = out;
            setLevel(Level.ALL);
        }

        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record)) {
                return;
            }

            out.println(record.getLevel().getName()
                    + " " + record.getMessage());
        }

        @Override
        public void flush() {
            out.flush();
        }

        @Override
        public void close() {
            flush(); // Do not close the JVM's System.out.
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("lesson.container.stdout");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);

        Handler handler = new StdoutLineHandler(System.out);
        logger.addHandler(handler);

        try {
            logger.info("event=service_started service=orders");
            logger.info("event=request_completed service=orders"
                    + " route=/orders status=201 requestId=req-42");
            logger.warning("event=dependency_retry service=orders"
                    + " dependency=inventory attempt=1");
        } finally {
            logger.removeHandler(handler);
            handler.flush();
            handler.close();
        }
    }
}
```

Compile and run:

```bash
javac ContainerStdoutDemo.java
java ContainerStdoutDemo
```

**Exact stdout** in a fresh JVM when no other code interferes with the logger:

```text
INFO event=service_started service=orders
INFO event=request_completed service=orders route=/orders status=201 requestId=req-42
WARNING event=dependency_retry service=orders dependency=inventory attempt=1
```

**Stderr of the example:** no output intentionally generated by this code.

### 5.1. Why Does the Example Work?

1. JUL's `Logger` creates three records with levels INFO/INFO/WARNING.
2. `StdoutLineHandler` writes each record using a single `println` call with a newline character, allowing the runtime to process text records line by line.
3. `logger.setUseParentHandlers(false)` prevents logs from propagating to parent/root handlers, avoiding an extra record on stderr via JUL's `ConsoleHandler`.
4. `handler.setLevel(Level.ALL)` allows the handler to accept records whenever the logger is at an appropriate level.
5. `close()` only flushes and **does not close `System.out`**. Closing process-wide stdout could affect other components.
6. The messages are fixed values containing no passwords, raw request bodies, or client-supplied data. `requestId=req-42` is merely a dummy illustrative ID.

### 5.2. Limitations of the Demo

- The custom handler is for learning only, **not a production logger**: it lacks a structured JSON encoder, advanced concurrency controls, retries, queues, or health metrics.
- A single `println` per record **does not guarantee atomicity for all record sizes and all sinks**. Do not rely on it for very large messages or multiple processes writing concurrently.
- The demo omits timestamps so that stdout is deterministic; in practice, properly configured timestamp/correlation metadata is required, distinguishing event time from ingest time.
- The Docker/Kubernetes runtime **does not run inside this Java snippet**; only when the program runs as a container process is stdout captured by container logging.
- Completing `logger.info` does not prove the log has reached the centralized backend.

You can run this demo in an image with a suitable JDK and use `docker logs` to observe it; the **Java file remains identical**, while building the image is part of a separate packaging/deployment step.

## 6. Configuring Logback to Write to stdout

Many Java applications use **SLF4J + Logback**. With Logback Classic/Core on the classpath, an illustrative `logback.xml` could be:

```xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level
                service=orders logger=%logger{36}
                traceId=%X{traceId:-} %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

**Note:** the multiline pattern in the XML example is for readability; in real operations, place the pattern **on a single line** to avoid unintended whitespace/newlines that complicate downstream parsing. A cleaner pattern:

```xml
<configuration>
  <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
    <target>System.out</target>
    <encoder>
      <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level service=orders logger=%logger{36} traceId=%X{traceId:-} %msg%n</pattern>
    </encoder>
  </appender>
  <root level="INFO">
    <appender-ref ref="STDOUT"/>
  </root>
</configuration>
```

The application can call:

```java
// Integration snippet; requires SLF4J and a Logback/Log4j 2 backend.
logger.info("event=order_created orderId={} status={}",
        safeOrderId, "CREATED");
```

Here, `safeOrderId` is a value approved for logging. **Using `{}` does not automatically mask secrets.** The `%msg` pattern can contain newline characters from input or stack traces if messages/throwables are printed; an escaping policy is needed, and raw user input should not be logged.

### 6.1. Why Avoid Attaching Duplicate Appenders?

If a child logger references `STDOUT` and simultaneously propagates up to the root logger which also references `STDOUT`, **a single log event can be emitted twice**. Check logger additivity and appender references. Do not disable `additivity` indiscriminately if that is how an audit sink on the root logger receives events; you must define the intended routing.

If the system writes to both stdout and a file, and the collector gathers from **both stdout and the file**, a single logical event can be indexed twice. Define a **single collection path** for each log type or establish a clear event ID/deduplication policy.

### 6.2. Log4j 2 Console Appender

Illustrative XML snippet for **Log4j 2**, requiring the corresponding Log4j 2 dependencies:

```xml
<Configuration status="WARN">
  <Appenders>
    <Console name="Stdout" target="SYSTEM_OUT">
      <PatternLayout pattern="%d{ISO8601} %-5level %c{1.} - %msg%n"/>
    </Console>
  </Appenders>
  <Loggers>
    <Root level="info">
      <AppenderRef ref="Stdout"/>
    </Root>
  </Loggers>
</Configuration>
```

`target="SYSTEM_OUT"` specifies stdout. `Console` does not imply JSON or guaranteed transport; the layout/encoder and dependencies must be chosen appropriately.

**Do not use multiple SLF4J providers/bindings simultaneously** or wire JUL/SLF4J/Log4j 2 bridges into a cycle. Check the runtime configuration whenever duplicate logs, missing logs, or logging initialization warnings appear.

## 7. One-Line Text and Structured JSON for Container Logs

### 7.1. Why Is “One Event per Line” Useful?

Many container tools and log collectors process streams **line by line**. If an event's message contains literal newlines, it may be split into multiple records or require a multiline merging rule. For example:

```text
INFO event=request_completed requestId=req-42
ERROR event=dependency_failure errorCode=DB_TIMEOUT
java.io.IOException: timed out
    at example.Repository.read(Repository.java:42)
    at example.Service.handle(Service.java:18)
```

If each line is indexed separately, the two stack frames lose `requestId`/`errorCode` and can easily be miscounted. A collector with a multiline parser can merge them, but **it must be configured with the exact log format, source, and event boundaries**.

An alternative is structured JSON with **one physical line per event**, where newlines inside `stack_trace` are encoded as the escape sequence `\n` rather than literal newlines. This generally makes parsing and correlation much easier.

### 7.2. Example JSON Schema

```json
{"timestamp":"2026-11-10T03:40:00.000Z","level":"INFO","service":"orders","event":"request_completed","route":"/orders","status":201,"request_id":"req-42","trace_id":"trace-demo-7"}
```

This is **illustrative data**, not output from the JUL code in Section 5. Commonly useful fields:
- `timestamp` in UTC/ISO 8601 for when the event was created, alongside the platform's ingest timestamp if available.
- `level`/`severity` using a stable enum, not inferred solely from stdout/stderr.
- `service`, `environment`, `component`, `version`; infrastructure enriches with `pod`/`container`/`namespace` when available.
- `event`/`error_code`: a stable event identifier or error category for querying, rather than using raw exception messages as an “error code”.
- `route` as a route template rather than a URL containing query parameters/tokens.
- `request_id`, `trace_id`, `span_id` for correlating logs/tracing per policy; do not use high-cardinality IDs as metric labels.
- `duration_ms`, `status`, `retry_attempt`, `result` when accurately measured.

**JSON must be generated using a standard encoder**, not by manually concatenating strings with user-supplied data. The encoder must properly escape `"`, backslashes, newlines, and control characters. If you want to use a Logback/Log4j 2 JSON layout, verify the exact encoder/layout and dependencies for your actual version; `ConsoleAppender` does not automatically convert text to JSON.

### 7.3. When Are Multiline Stack Traces Still Reasonable?

Full stack traces are valuable for debugging, but:
- Inspect `Throwable.getMessage()` and cause/suppressed exceptions: they may contain URIs, SQL, headers, or credentials.
- You can output stack traces in an escaped JSON field, or use a multiline parser in the collector.
- The collector must recognize the **start of a record** and associate subsequent lines with the right container/stream. Never blindly merge lines from two different containers.
- Limit stack trace length/depth to avoid oversized events.
- Test high log rates and cases where records are split into partial fragments by the runtime.

Do not use a multiline parser just to “log the entire request payload”: data safety is always an application-level decision made before writing to stdout.

## 8. Docker: How Does the Runtime Capture stdout?

A container running Java via an appropriate entrypoint can emit logs:

```dockerfile
# Illustrative Dockerfile snippet; requires app.jar in the build context.
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY app.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

**Note:** The image/tag only illustrates how to launch Java and does not confirm a specific image version is available at the time of reading. The application must already be packaged into `app.jar` with its dependencies and console logging configuration. A Dockerfile does not replace building the artifact.

The `ENTRYPOINT ["java", ...]` form launches Java directly, avoiding an intermediate shell that might not forward signals properly. If a shell script is unavoidable, use `exec java ...` at the final step to replace the shell process, ensuring cleaner signal/shutdown semantics.

Examples for viewing container logs:

```bash
docker run --name orders-demo orders-app:local
docker logs --tail 100 orders-demo
docker logs --since 10m --timestamps orders-demo
docker logs -f orders-demo
docker inspect -f '{{.HostConfig.LogConfig.Type}}' orders-demo
```

These commands show **how to operate**, with no fixed stdout since output depends on the actual image/container. `docker logs` typically displays stdout and stderr stored/integrated by the logging driver; **specific retrieval capabilities depend on the logging driver and Docker configuration**. `--timestamps` adds the log record timestamp per Docker's mechanism, which does not necessarily match the event timestamp written by the application.

### 8.1. Logging Drivers, Rotation, and Retention

Docker supports multiple logging drivers. For example, `json-file` or `local` have different storage/rotation mechanisms; some drivers forward directly to a remote system or cache records depending on version/configuration.

Do not assume:
- Every host uses the same driver or the same `max-size`/`max-file` settings.
- `docker logs` can always read full history when using a remote driver.
- Logs will remain after the container is removed.
- Logs are retained forever just because the application is running.
- A Docker logging driver provides the same semantics as Kafka or a transactional store.

**Know your actual runtime configuration and disk budget.** If log rotation/caps delete files before the collector ships them, data can be lost. If volume is unbounded, the node disk can fill up. Storage capacity, rotation, persistence, and security are infrastructure responsibilities that must be monitored.

### 8.2. Blocking and Non-Blocking Delivery

Some logging driver/runtime modes have a **blocking** policy when logs cannot be delivered, or a **non-blocking** policy with a bounded buffer that drops messages when full. Do not assume all configurations behave identically.

Trade-offs:
- Blocking can stall the process or increase latency if the log path backs up.
- Non-blocking can prioritize business continuity but **lose logs** when the buffer fills.
- Async appenders inside the JVM also have their own queues and can drop or block before bytes ever reach the runtime.
- If infrastructure loses logs at one layer, increasing retries at another layer cannot recover bytes that were never saved.

For applications requiring mandatory transaction auditing, **stdout is not an exactly-once persistence guarantee**. Design a separate audit store/outbox with transactions and dedicated policies for events that must never be lost.

## 9. Kubernetes: From Container stdout to `kubectl logs`

In standard Kubernetes, a container runtime implementing the CRI interface emits logs in a format/container log stream that kubelet knows how to access. Kubelet manages container logging on the node, including rotation according to node configuration.

Conceptual diagram:

```text
Java stdout/stderr inside pod
             |
             v
Container runtime (CRI logging)
             |
             v
Node container log files
             |
             +--> kubectl logs via kubelet/API
             |
             +--> node-level log agent (DaemonSet)
                         |
                         v
               centralized logging backend
```

On many Linux/Kubernetes systems, log files reside under paths like `/var/log/pods/...` with symlinks in `/var/log/containers/...`, but **do not hardcode a single path as universal** without checking the node OS, runtime, and cluster configuration.

### 9.1. Commands for Observing Pod Logs

```bash
kubectl logs pod/orders-abc -c app --tail=100
kubectl logs pod/orders-abc -c app --since=10m --timestamps
kubectl logs -f pod/orders-abc -c app
kubectl logs pod/orders-abc -c app --previous --tail=100
```

`orders-abc` and `app` are **illustrative names**; substitute your actual Pod/container names. Meaning:
- `-c app` specifies the container when a Pod has multiple containers, avoiding confusion between the app and sidecars.
- `--tail`, `--since` limit the number of lines and time range retrieved.
- `--timestamps` adds timestamps provided by the container logging layer.
- `-f` continues streaming output while the container runs.
- `--previous` attempts to fetch logs from the **most recently** terminated container run if kubelet still has them; it is not a full restart history.

**Limitation:** `kubectl logs` is a tool for inspecting currently available node/container logs, **not a long-term archive**. Kubelet rotation, pod deletion/eviction, node loss, and storage policies can make older logs inaccessible. In practice, Kubernetes only exposes whatever logs remain under its storage/rotation mechanism; do not rely on `kubectl logs` for long-term auditing.

### 9.2. CRI Format and Partial Lines

In environments using the CRI log format, an entry may include a timestamp, stream name (`stdout`/`stderr`), and a marker indicating whether the line is complete or partial (commonly represented as `F` and `P`). This is **runtime-layer metadata**, not the JSON format written by the Java application.

Key points:
- An oversized Java log event can be split into **fragments** at the runtime layer.
- The collector needs a parser suitable for **CRI/Docker format**, which may need to reassemble partial fragments and handle multiline stack traces separately.
- Simply splitting files on every newline and assuming **each line is always a complete event** can corrupt large records.
- When reassembling, never merge fragments from two different containers/streams into one event.
- A CRI parser may not parse JSON fields written by the app; **two layers** are typically needed: parse the container envelope first, then parse the application message.

Do not design your application to depend on an exact log path or internal marker without verifying the runtime/collector configuration.

### 9.3. Pod Metadata and Labels

A node log agent can enrich logs with:
- Namespace, Pod name/UID, container name/ID.
- Node name, cluster/region, workload/deployment labels.
- Stream, runtime-recorded timestamp, source file.
- Labels permitted for indexing and access control.

**The application does not necessarily need to print all Pod metadata in every message**; collectors handle that more reliably. However, the app should still emit `service`, `event`, `error_code`, and `trace_id` as needed, and avoid relying solely on Pod names since Pod names change on redeployment.

Never attach raw secrets to Kubernetes labels/annotations for “easier log searching”. Labels can also appear across many collection and monitoring systems.

## 10. Collector: From Node Files to the Search Backend

A DaemonSet or agent may use Fluent Bit, Vector, OpenTelemetry Collector, or another platform to read container log streams and ship them to a centralized system.

Common functions:
1. **Tail/watch** log sources and manage offsets/checkpoints.
2. **Parse the container runtime envelope** (timestamp, stream, partial/complete).
3. **Merge fragments and multiline records** if required by the format.
4. **Parse the application schema** (JSON or text pattern) and normalize fields.
5. **Enrich metadata** with Pod/container/namespace/service.
6. **Filter/transform/redact** according to additional policies.
7. **Batch/retry/backoff/buffer** when the backend is slow or disconnected.
8. **Export** to the backend while monitoring errors, queue depth, throughput, and lost events.

Plugin/config names vary by collector product and version, so do not copy a sample pipeline verbatim from one tool to another without verifying the actual documentation.

### 10.1. Choose a Single Source, Avoid Duplicate Ingestion

A common mistake is:
- Agent A reads `/var/log/containers`.
- Agent B also reads the same source from another chart.
- Or the same application is collected from both stdout and a separate file, both shipping to the same index.

The result is **duplicate log ingestion**. This can skew log-based alerts, inflate storage costs, and make a single request appear processed twice. To investigate:
- Count logger invocations in Java.
- Compare raw `kubectl logs`/Docker logs against the backend.
- Compare collector metadata, source paths, container IDs, and ingestion IDs.
- Check shipper retries on lost ACKs, checkpointing, and destination deduplication.

Do not blindly deduplicate logs by `request_id`: a single request can legitimately produce multiple log events. You need an **event instance identity** and a deduplication policy at the right layer.

### 10.2. Checkpointing and Rotation

When a node agent tails a file, if the file is rotated/renamed/truncated or the container restarts, the checkpoint must track **how far it has read**. Depending on the algorithm, the agent may:
- Re-read a segment (duplicate).
- Miss a segment if the file disappears too quickly (loss).
- Follow the wrong file if the file fingerprint/identity is not stable enough.

Therefore:
- Configure rotation with enough capacity for the expected log rate and maximum outage duration.
- Monitor ingest lag, file tailing errors, backlog, and dropped records.
- Test log bursts and agent restarts.
- Do not rely on exactly-once delivery across stdout → collector → backend unless the pipeline has a mechanism that proves it.

### 10.3. Timestamps and Ordering

A record can have multiple timestamps:
- `event_time`: when the application created the log event.
- `container_time`: when the runtime recorded the line.
- `ingest_time`: when the backend received or indexed it.
- `processing_time`: when the query/alert pipeline processed it.

Differences between them can arise from buffering, network retries, clock skew, or backend queues. **Do not assume ingest order equals business order.** For critical workflows, use correlation IDs and sequence/business event IDs as appropriate, rather than inferring from log timestamps alone that operations committed in that order.

If the backend parses a JSON log containing `timestamp` while the node agent also attaches a CRI timestamp, explicitly configure which time source is used for queries/alerts. Timezones should be normalized (usually UTC), and clocks across nodes/services must be synchronized.

## 11. Practical Risks of Container stdout Logging

| Risk | Example | Mitigation |
| --- | --- | --- |
| **Excessive logging** | DEBUG logging every request body | Use an allowlist schema, volume budgets, and proper levels |
| **Secret/PII exposure** | Tokens, cookies, passwords, document contents in logs | Exclude at the call site; downstream redaction is only secondary |
| **Blocking stdout** | Slow collector/runtime stalls business threads | Use bounded appenders/buffers, measure latency, know drop policy |
| **Async queue drops** | Queue fills during traffic spikes | Track drop metrics, queue depth, and sensible priority configs |
| **Rotation history loss** | Kubelet/Docker deletes files before agent ships them | Set size/retention/lag budgets and monitor backlogs |
| **Pod/node disappearance** | Pod evicted or node fails | Centralize logs with retention; don't rely solely on `kubectl logs` |
| **Split multiline logs** | Java exception indexed as 30 separate events | One-line JSON or properly formatted multiline parser |
| **Partial log fragments** | Oversized line split by runtime | Cap event size and enable CRI partial recombination |
| **Duplicate collector** | Two agents reading the same file | Plan pipeline; use source/event identification |
| **Duplicate appender** | Root + package logger both attach ConsoleAppender | Check additivity/handler tree |
| **Wrong severity** | Everything sent to stderr treated as ERROR in queries | Use `level`/`severity` from the app schema |
| **Wrong timestamp** | Dashboard uses ingest time while data arrives late | Record event time and define parse time |
| **Log injection** | User input contains CR/LF to forge records | Standard encoder, character/size limits |
| **Log loss on crash** | Async queue unflushed when container is killed | Shutdown policy, separate audit store when mandatory |
| **No-data false healthy** | Service dies so no ERROR logs appear | Heartbeat/synthetic checks and pipeline monitoring |

### 11.1. Log Storms and Container Resources

During a dependency outage, a million stack traces can cause:
- High CPU from formatting and serialization.
- Increased heap allocations/GC, hurting latency.
- Disk pressure on the node even though the app “doesn't write files”.
- Collectors having to parse/retry large batches, increasing ingest costs.
- Log-based alerts counting retry attempts multiple times as separate incidents.

Do not use “print full stack trace on every retry” as a default observability strategy. Separate `attempt_failed` from `operation_failed`, and use error codes and metric counters. When stack traces are needed, limit them by event type/volume and read permissions without losing mandatory audit signals.

### 11.2. Container Restarts and Graceful Shutdown

When Docker/Kubernetes requests a stop, the Java process needs a chance to flush appenders/async queues within the configured grace period. Pay attention to:
- Using exec-form entrypoints or `exec` in shell scripts so signals reach the right process.
- Having shutdown hooks/lifecycle managed by the logging framework; test with SIGTERM.
- Stopping new requests/jobs and completing/acking in-flight work per contract before exiting.
- Not assuming `Runtime.addShutdownHook` runs when the JVM is forcibly killed, suffers severe OOM, or the node loses power.
- With `SIGKILL` or sudden crashes, unflushed JVM buffers can be lost.
- Container stdout and downstream collectors also have their own buffers; flushing the Java logger **does not mean** the backend has indexed all logs.

For mandatory auditing, never rely solely on a shutdown flush as proof of delivery.

## 12. Correlating Logs with Requests, Traces, and Workloads

A container does not handle just one request. Within a single minute, there can be thousands of logs from multiple threads and async callbacks. If you only log:

```text
ERROR database timeout
ERROR database timeout
```

it is hard to tell which error belongs to which request. Instead:

```text
ERROR event=dependency_timeout service=orders operation=create_order requestId=req-42 traceId=trace-demo-7 dependency=inventory
```

These IDs are dummy data. In real applications:
- **request ID** is generated by the server or validated for length/characters; never blindly trust an arbitrary header.
- **trace/span ID** comes from a verified/standardized tracing context; do not use it as a metric label.
- **service/operation** are stable fields for querying and routing.
- **pod/container metadata** is added later by the platform/collector, not as business IDs.
- Never put passwords, raw Bearer tokens, Cookies, request bodies, or SQL bind values into MDC just “for extra context”.
- If using MDC/ThreadContext with thread pools, clean up/restore per scope and propagate properly across async boundaries.

**One well-contextualized log event at the right moment** is often more useful than five logs without correlation IDs. In microservices architectures, combining trace samples, error codes, deployment versions, and source containers helps pinpoint failure paths.

## 13. Security: Container stdout Still Holds Sensitive Data

Just because logs go to the console instead of a file does not make them “ephemeral” or “harmless”. Data can be copied to:
- Node log files and backups/snapshots.
- Cluster log collectors.
- Centralized indexes, dashboards, and exports.
- Notifications, incident tickets, and chat when alert templates quote messages.
- Development/staging environments if someone copies raw production logs.

**Apply data minimization at the source**:
1. Never log raw credentials, access tokens, refresh tokens, passwords, API keys, private keys, session cookies, or signed URLs.
2. Never print whole request/response bodies, DTOs containing PII, headers, or SQL bind values.
3. Use route templates, result/error codes, and approved correlation IDs.
4. Use structured encoders for escaping; never manually concatenate JSON with raw user input.
5. Enforce role-based access, appropriate TLS/mTLS, encryption at rest, retention, and audit exports.
6. Never put real secrets into examples/tests; use completely fake canary values.
7. If a secret leaks into the pipeline, stop further emission, assess sinks/copies, and revoke/rotate the credential per policy; deleting a single log line is not enough.

In Kubernetes, Pod log access may be governed by RBAC; anyone authorized to inspect container logs can read sensitive data if the app printed it. **Do not treat `kubectl logs` permissions as a substitute for not logging secrets.**

## 14. End-to-End Testing: Does stdout Actually Reach Its Destination?

A proper test should verify **all three layers**:
- Does the Java application emit the right events?
- Do the container runtime and log inspection tools capture the records?
- Does the collector/backend index them completely, parse them accurately, apply the right tenant/access controls, and avoid duplication?

### 14.1. On a Development Machine

1. Run the Java demo and verify stdout matches Section 5; confirm stderr has no app-generated output.
2. Package the app using console logging and run the container.
3. Use `docker logs --timestamps` to inspect; verify level, message, timestamp, and record count.
4. Emit a log event with dummy values containing quotes/newlines to test escaping/parsing. **Do not use real secrets.**
5. Test a bounded high log rate and observe CPU, memory, and blocking/dropped events per configuration.
6. Restart the container, check available logs, retention duration, and rotation effects.

### 14.2. In Kubernetes/Staging

1. Identify the exact Pod/container and inspect with `kubectl logs -c app`.
2. Check Pods with sidecars: do not confuse application logs with sidecar logs.
3. Send a test request with a controlled correlation ID and verify the fields in `kubectl logs`.
4. Query the centralized backend by service/trace/request ID; match record counts.
5. For stack traces, confirm the collector merges multiline entries or parses JSON fields properly without creating multiple independent events.
6. Test container restarts and `--previous` if data remains; verify the backend retains history per retention policy even after the old Pod disappears.
7. Fault-inject collector/network downtime **in staging**: check retries, backlogs, dropped logs, ingest lag, and rotation.
8. Verify separate stdout/stderr routing, timestamps, and Kubernetes metadata.
9. Verify that fake canary values do not appear in structured fields, exception text, alert annotations, or exports.

You do not need and should not cause a production outage just to test the log path. For systems requiring zero log loss, add durable storage designs and dedicated transaction/crash tests.

### 14.3. Recommended Assertions

| Condition | Test Meaning |
| --- | --- |
| Emit 1 INFO event → 1 record on stdout | No duplicate appenders |
| Emit 1 event → 1 backend document per policy | No duplicate collector/shipper |
| Pod/container metadata added | Enrichment at the right place/instance |
| JSON parsed into level/service/event fields | Queries and alerts can use stable fields |
| Brief collector outage | Queue/retry/loss matches configuration |
| Large log burst | Memory/disk/log-budget stays within expectations |
| CRI partial + multiline | No unintended record loss or splitting |
| Container restart/rotation | Proper recovery/retention; `kubectl logs` limits understood |
| Enable DEBUG in staging | No accidental emission of tokens, bodies, or secrets |
| Appender failure or missing logs | Health/meta-monitoring detects missing data |

**Important:** “`docker logs` shows it” only verifies up to the runtime. “The backend has one sample record” does not prove all logs were transported. You need metrics for emitted, dropped, exported, and failed counts where supported by each layer.

## 15. Investigating Missing Container Logs

Follow a structured sequence of questions to avoid guesswork:

### 15.1. Is the Application Emitting Events?
- Is the `INFO/DEBUG` log level filtered out at the logger or appender?
- Is Java using JUL's default `ConsoleHandler` writing to stderr while the collector only reads stdout?
- Did the framework redirect console output to a file, or is the appender not attached to the root logger?
- Are there initialization bugs, bridge conflicts, or a different logger object?
- Did execution actually reach the code path, or did a handler throw earlier?
- Were process stdout/stderr closed or redirected by mistake?

### 15.2. Is the Runtime Receiving the Stream?
- Is the main process in the container running directly, or is a shell wrapper redirecting output to a file?
- Is the logging driver configured to capture logs? Does `docker logs` support/cache records for that driver?
- Was the container restarted/deleted, or did the node log file rotate?
- Are there size caps/limits or dropped logs at the runtime layer?
- Are formatting errors or binary data making logs hard to display?

### 15.3. Is the Collector Reading and Exporting?
- Is the agent reading the right node/path/pod/container?
- Do filter rules drop events or discard `DEBUG` level logs?
- Are CRI/Docker and multiline parsers handling records properly?
- Did the checkpoint skip a file position after rotation?
- Is the backend rejecting records due to JSON parse errors, field size limits, quotas, or write permissions?
- Are there queue backlogs, retry storms, or network/TLS failures?

### 15.4. Is the Backend/Query Displaying Correctly?
- Does the time range account for timezone and event-vs-ingest time?
- Are `service`, `namespace`, and `container` labels enriched properly?
- Is the query accidentally excluding `stream=stderr`?
- Were records quarantined due to mapping/schema issues or retention?
- Does the querying user have permission to access the index/tenant?

**Do not rush to raise the log level to TRACE across production.** First trace a single safe test event layer by layer to find where it disappears.

## 16. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Writing logs to a container file without mounting/shipping | Logs vanish when the container is replaced | Use stdout or a properly designed file collector/persistence |
| Assuming JUL `ConsoleHandler` prints to stdout | Records go to stderr | Configure the handler properly and collect both streams if needed |
| Child logger and root both attach `ConsoleAppender` | Duplicate logs | Check additivity/routing |
| Using only `System.out.println` in production | Lacks schema, levels, MDC, configuration | Use a logging framework and console appender |
| Printing multiline stack traces without a parser | Lost context, wrong alert counts | One-line JSON or a multiline parser |
| Dumping binary/request bodies to console | Data exposure and log storms | Log only metadata/allowlisted fields |
| Using `docker logs` as long-term storage | History depends on driver/container | Centralized logging and retention policies |
| Using `kubectl logs --previous` to find all restarts | Only shows whatever recent log remains | Centralize and query by workload/time |
| Counting stdout lines as business operations | Duplicates/partials/multiline skew counts | Outcome metrics, IDs, and proper parsing |
| Assuming stdout cannot block | Latency/timeouts when log path backs up | Measure throughput, use bounded appenders/queues |
| Using async queues without measuring drops | Silent loss under overload | Health metrics and fallback/audit policies |
| No rotation | Node disk fills up, impacting workloads | Set retention, quotas, disk/ingest lag alerts |
| Rotating too fast | Agent loses files before reading them | Size for worst-case log throughput/outages |
| Treating ingest timestamp as event time | Wrong ordering during retries/backlogs | Standardize event time vs. ingest time |
| Putting request IDs in metric labels | High cardinality | Keep IDs in logs/traces |
| Collecting both stdout and the same log file | Duplicate backend documents | Single primary pipeline or event-identity dedup |
| Alerting on “no ERROR logs” | Dead service/collector emits no logs | Meta-monitoring and synthetic checks |
| Flushing Java and claiming backend delivery | Runtime/collector may still buffer or fail | Monitor end-to-end pipeline and real ACKs |

## 17. Practice Questions

**Q1.** A Java app uses JUL's default `ConsoleHandler`. The Pod emitted logs, but the system only collects `stdout`. Why don't operators see the logs?

**Answer:** JUL's `ConsoleHandler` sends records to **stderr** by default. If the agent filters for stdout only, the logs are ignored. Adjust the routing/configuration or configure the collector to gather both streams per policy.

**Q2.** A container has 2 replicas; both call `logger.info` for an event. Can this be assumed to be a single log record?

**Answer:** No. Each replica/process can emit a record; you need to know whether they processed independent business events, a message redelivery, the same event generated twice, or collector duplication. Use business event IDs, workload metadata, and appropriate transaction context.

**Q3.** Does `kubectl logs --previous` guarantee viewing all restarts and logs of deleted Pods?

**Answer:** No. Availability depends on whether the previous container instance is still retained by kubelet/runtime and rotation; it is not an archive. To preserve history, use a centralized backend with dedicated retention.

**Q4.** A 20-line stack trace is ingested by a log collector as 20 documents. Does that necessarily mean Java threw 20 exceptions?

**Answer:** No. It may be a single throwable rendered across multiple lines. Parse/merge multiline records per source and check how many times the logger was actually invoked.

**Q5.** A service uses an async appender and a non-blocking Docker logging driver. Does `logger.info` returning successfully prove the log reached the backend?

**Answer:** No. Logs can be dropped in the JVM queue, runtime buffer, or collector; measure accepted/emitted/dropped/exported counts and verify actual delivery guarantees.

**Q6.** Can stdout output be used to store mandatory exactly-once payment events?

**Answer:** It should not be assumed. Container stdout is a stream-based diagnostic channel, not a transactional audit ledger. For durable obligations, use commit/outbox/idempotency mechanisms and storage with appropriate guarantees.

**Q7.** A JSON log has a `timestamp` field, the collector adds `time`, and the backend has `ingest_at`. Which field should be used when debugging?

**Answer:** It depends on the goal: event time tells when the application recorded it, runtime time tells when the container emitted it, and ingest time shows pipeline latency. Configure consistent mappings/queries and do not confuse the three timestamps.

**Q8.** When the log backend receives no events from a pod, what is the most reasonable first step?

**Answer:** Identify a safe, reproducible event and check whether the application emits it, `kubectl logs` receives it, the agent reads/parses it, network/ingest has errors, and the query uses the right scope/time. Do not immediately enable TRACE or log raw request bodies.

## 18. Checklist for Taking Container stdout Logging to Production

1. **Application emit:** Loggers have a single designed appender/handler; stdout/stderr routing is explicit with no duplication across root/child loggers.
2. **Event schema:** Level, service, event code, correlation ID, timestamp, and required metadata are emitted in a structured format; no raw payloads/secrets.
3. **One event / line:** Use a JSON encoder with proper escaping or a tested multiline parser; enforce event size limits.
4. **Docker config:** Know the logging driver, how `docker logs` behaves, rotation settings, and storage budgets.
5. **Kubernetes config:** Understand CRI/node log lifecycles, `kubectl logs`, and `--previous`/rotation limits.
6. **Collector:** Correct source, accurate Docker/CRI parsing, partial/multiline merging, checkpointing, and container metadata enrichment.
7. **Delivery semantics:** Know where buffering, retries, drops, and duplicates occur; do not claim exactly-once without proof.
8. **Performance:** Measure log volume, CPU/GC, sync stdout blocking, async queue depth, disk/network usage, and collector lag.
9. **Security:** Strip secrets/PII before the logger, enforce read/export permissions, encrypt in transit/at rest, set retention and incident response.
10. **Correlation:** Propagate request/trace IDs across async boundaries; avoid using high-cardinality IDs as metric labels.
11. **Lifecycle:** Test startup/shutdown, SIGTERM, restarts, node loss, log rotation, and graceful flushes; understand `SIGKILL` limits.
12. **Observability of observability:** Have metrics/alerts for appender errors, collector backlogs, dropped events, no-data, and storage pressure.
13. **End-to-end validation:** Match a sample event across the app, Docker/Kubernetes, and the backend, without relying on a single log viewer.
14. **Audit exception:** For records that must never be lost, use a separate durable/transactional mechanism instead of stdout alone.

## 19. Conclusion

**Container stdout** is the natural log transport boundary between a Java application and a container platform. Java still needs a **properly configured logging framework**, a stable schema, and data minimization; Docker/Kubernetes provide the capture layer, while the log collector/backend handle parsing, enrichment, shipping, retention, and search.

Good design is not just “logs appear when running `docker logs`”. Ensure that:
- Each event is emitted to the right destination without accidental duplication or improper splitting into multiple records.
- stdout/stderr, timestamps, JSON/multiline formatting, and CRI fragments are properly understood.
- Rotation, restarts, buffering, retries, and loss are measured and tested.
- Credentials/PII are kept out of logs, and stdout is not treated as a transactional audit store.
- You can trace from a JVM log event to the final backend, along with the health of the pipeline itself.

Only when both **log content** and the **log delivery path** are governed does a Java system achieve container logging that is useful, reliable within its design limits, and safe to operate.
