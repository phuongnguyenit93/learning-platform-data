# Log collector in Java: collecting and transporting logs from applications to a centralized system

## 1. Objectives

In a Java program, calling **logger.info**, **logger.warn**, or **logger.error** is only the point where a log event is created. To search logs from multiple instances, multiple containers, and multiple services in one place, you need to collect logs from their sources, normalize them into a unified format, forward them reliably, and store them in an appropriate backend.

A **log collector** is a component that ingests logs from files, stdout/container runtimes, or telemetry protocols, and can parse, enrich with metadata, filter, batch, and export them to one or more destinations. A collector is not synonymous with **SLF4J, JUL, Logback, or Log4j2**, nor is it a database or dashboard by default.

This lesson helps you:

- Distinguish between a logger, appender/handler, agent, collector gateway, exporter, storage, and viewer.
- Design a **Java → file/stdout/OTLP → collector → backend** pipeline.
- Understand **agent, sidecar, Kubernetes DaemonSet, and gateway** deployment models.
- Understand the **receiver → processor → exporter** pipeline, along with parsing, enrichment, batching, queuing, retries, and checkpoints.
- Run a standalone Java 17 example simulating **producer writes to file → collector reads by offset**, including duplicates after a restart without a persisted checkpoint.
- Read an illustrative OpenTelemetry Collector configuration and distinguish core vs. contrib components.
- Know how to test file rotation, multiline Java stack traces, log loss, duplicate logs, wrong-tenant logs, and backend outages.
- Set up metrics and a runbook to investigate when an event does not appear in the dashboard.

## 2. Layers of a logging system

A typical architecture:

~~~text
Java Service A                    Java Service B
    |                                  |
    v                                  v
SLF4J/Logback                     JUL/Log4j2
    |                                  |
    v                                  v
stdout / file / OTLP              stdout / file / OTLP
    |                                  |
    +-------------+--------------------+
                  v
           Agent / Collector
                  |
                  +-- Receiver: file tail / OTLP / other sources
                  +-- Parser: JSON Lines, text, multiline
                  +-- Processor: enrich, redact, filter, batch
                  +-- Queue / retry / storage (when supported)
                  +-- Exporter: send to backend/gateway
                  |
                  v
          Log storage / index
                  |
                  v
         Search / dashboard / alert
~~~

| Component | Responsibility | What must not be assumed |
| --- | --- | --- |
| **Logger API** | Creates events from Java code. | That the event has been durably written. |
| **Logging backend** | Filters, formats, and sends to a handler/appender. | That the collector has received the event. |
| **Source-side agent** | Reads logs on a host, node, or pod. | That it can read every file or never lose logs. |
| **Collector gateway** | Receives from multiple agents or SDKs; processes and forwards. | That it is a permanent storage system. |
| **Exporter** | Sends data to a backend or another collector. | That the backend has indexed and made the log searchable. |
| **Storage/index** | Stores, queries, retains, and enforces access control. | That no records were lost before ingestion. |
| **Viewer** | Displays and queries stored data. | That a negative query proves a log was lost. |

An event may fail to appear for many reasons: the logger filtered DEBUG according to policy, FileAppender hit a disk error, the agent read the wrong path, the parser failed, a processor dropped it, the exporter queue filled up, the backend rejected ingestion, or the dashboard queried the wrong tenant or time range. **Each boundary needs its own evidence.**

## 3. Three common Java collection paths

### 3.1. Writing to stdout/stderr

~~~text
Java logger
   → ConsoleAppender / ConsoleHandler
   → container runtime / host log
   → agent
   → gateway / storage
~~~

Advantages: the application does not need to manage multiple files itself; it fits containers well. However, you must check **stdout vs. stderr**, runtime log read permissions, container log rotation, and how the agent reads data. For example, **JUL ConsoleHandler** typically writes to stderr, whereas another ConsoleAppender may write to stdout.

**Do not assume stdout is immune to all failures**: the runtime has buffers, container log files have retention limits, the collector can fall behind, and a node can still lose data when its disk is full.

### 3.2. Writing to a file and tailing

~~~text
Java FileHandler / RollingFileAppender
   → /var/log/my-service/application.log
   → file receiver / tailing agent
   → processing + export
   → storage
~~~

Suitable for systems already using log files or needing buffering near the source. You must manage: **file paths, read permissions, format, file rotation, timestamps, offsets/checkpoints, disk quota, and old file age**. If a container is replaced before the agent finishes reading a file on an ephemeral filesystem, logs can disappear.

### 3.3. Sending telemetry via OTLP

~~~text
Java logger + suitable bridge/SDK/provider
   → OTLP gRPC/HTTP exporter
   → Collector OTLP receiver
   → processors/exporters
   → backend
~~~

Advantages: structured data aligned with OpenTelemetry; can share the same tracing/metrics ecosystem. Disadvantages: requires the right dependency/provider/exporter, endpoint configuration, TLS, credentials, batching, queuing, and shutdown lifecycle handling. Simply adding an OpenTelemetry library to the classpath does not automatically ship all SLF4J logs.

**Avoid sending the same event to the backend via two paths unnecessarily**. For example, sending the same log directly via OTLP while an agent also tails it from stdout can cause **duplicates**.

## 4. Collector deployment models

| Model | Where is it placed? | When is it suitable? | Risks |
| --- | --- | --- | --- |
| **Host agent** | A process on a VM/host. | Machines with multiple apps writing files. | File permissions, shared host, resources. |
| **Sidecar** | A container alongside the app in the same Pod. | Workload-specific config, shared volume. | Per-Pod overhead, lifecycle and shutdown. |
| **DaemonSet** | Typically one agent per Kubernetes node. | Centralized container log collection per node. | hostPath and access to logs from multiple Pods. |
| **Collector gateway** | A separate pool/deployment. | Routing, centralized credentials, batching, policy, and export. | Bottleneck, overload, HA, retries. |
| **Direct SDK** | Instrumentation running inside the JVM. | Sending structured telemetry directly. | SDK overhead, network, resources, and app lifecycle. |

Distributed systems often use **agent → gateway**:

~~~text
Node A → Agent A ──+
Node B → Agent B ──+──> Gateway pool ──> Backend
Node C → Agent C ──+
~~~

The agent handles local files/containers; the gateway can control routing per backend, credentials, and export policy. However, two tiers introduce additional checkpoints to monitor: **agent accepted**, **gateway accepted**, **exporter sent**, and **backend indexed**.

Choose a deployment model based on where data originates, isolation requirements, workload count, log volume, and operational capacity. There is no rule that Java must run a sidecar or must use a DaemonSet.

## 5. OpenTelemetry Collector pipeline

The OpenTelemetry Collector is a common example of the **receivers / processors / exporters** architecture, alongside connectors and extensions.

### 5.1. Receiver

A receiver ingests logs from one or more sources:

- **filelog**: tails files matching a glob, manages file reading and parsing operators.
- **otlp**: receives telemetry over OTLP HTTP or gRPC.
- Other receivers can ingest data from specific protocols/runtimes depending on the distribution.

A receiver that is **declared but not attached to service.pipelines.logs** does not participate in the pipeline. Do not use a receiver name that is not actually packaged in the binary.

### 5.2. Processor

A processor can perform:

- **Filter**: intentionally drop specific events.
- **Transform**: modify fields or severity.
- **Resource enrichment**: service.name, deployment.environment.name, host/k8s metadata.
- **Redaction**: mask or remove sensitive data per data policy.
- **Memory limiting**: reduce the risk of overload.
- **Batch**: reduce the number of outbound requests.

**Processing order matters.** The memory limiter is usually placed at the start of the pipeline; batching is usually placed after filtering/transform steps in configurations that use the batch processor. If a filter drops WARN/ERROR due to a faulty rule, data can be lost even though the Java logger emitted the event properly.

### 5.3. Exporter

An exporter forwards data to a destination system, such as a Collector gateway or an OTLP-capable backend. Exporters can support **sending queue, timeout, and retry_on_failure**. With the debug exporter, data is printed for inspection, **not durably stored in a production repository**.

An exporter that is declared but not listed in service.pipelines.logs will not run either.

### 5.4. Extensions and connectors

- **Extensions** can provide storage, authentication, health checks, or diagnostics.
- **Connectors** can route data between pipelines when the design requires it.

Not every application log pipeline needs a connector. If you configure a file storage extension but forget to add it to **service.extensions**, the persistent queue may not work as expected.

## 6. Schema normalization and log formats

A log collector works much more reliably if the application emits **structured logs**, avoiding reliance on regex over free-form message text.

Example of a JSON log record:

~~~json
{
  "timestamp": "2026-11-10T03:20:01Z",
  "severity_text": "WARN",
  "event": "inventory.slow",
  "service.name": "order-service",
  "deployment.environment.name": "staging",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "http.route": "/orders/{id}",
  "duration_ms": 920,
  "message": "Inventory call was slow"
}
~~~

This is illustrative data, not the default output of Logback or JUL.

| Field | Purpose | Notes |
| --- | --- | --- |
| **Timestamp** | When the event occurred at the source. | Include explicit timezone/UTC. |
| **Observed timestamp** | When the collector received the event. | May differ due to backlog or clock skew. |
| **Severity** | Classifies INFO/WARN/ERROR or JUL levels. | Map accurately to the backend; do not infer from HTTP status. |
| **Body** | Event message content. | Do not include tokens/secrets or excessively long messages. |
| **Service name** | Identifies the emitting service. | Obtain from a trusted deployment source. |
| **Environment** | dev/test/staging/prod. | Prevent staging from accidentally sending to production. |
| **Trace ID** | Correlates logs with traces. | May be absent; do not fabricate fake IDs. |
| **Logger name** | Identifies class/package/category. | Helps configure levels and locate the source. |
| **Event ID** | Detects replays/duplicates when needed. | Having an ID does not guarantee deduplication on its own. |
| **Tenant ID** | Partitions customer data. | Scope must be validated; do not trust client-supplied claims. |

### JSON Lines

For file tailing, **one JSON object per physical line** is an easy-to-parse choice. Message strings containing CR/LF must be escaped inside the string by a **JSON encoder**. Never concatenate JSON manually using raw quotes or delimiters.

An exception with a multi-line stack trace should be serialized into **a single JSON string field**, or the collector must have a **multiline parser** configured. You cannot assume each stack trace line is an independent log event.

### Resource vs. event attributes

In the OpenTelemetry log data model, some fields describe the **source** (resource attributes, e.g., service.name), while others describe the **event** (log record attributes, e.g., http.response.status_code). Separating these two groups helps standardize pipelines and reduces repeating metadata in every message.

## 7. Standalone Java 17 example: simulating a file collector

The following program demonstrates the mechanism:

1. JUL Logger writes two events via FileHandler to a temporary file.
2. FileCollector reads the file and prints a normalized form.
3. A simple checkpoint is **the number of lines read in RAM**.
4. A second poll does not reprint already-read events.
5. Java appends another event; the collector reads only the new line.
6. Simulating a restart **without saving the checkpoint**: a new collector reads from the beginning again, creating the risk of duplicate logs.

The test format is **LEVEL|event.name|event_id** with program-controlled values. This is **not a production-safe format for untrusted input**. The goal is to illustrate reading and checkpointing mechanics, not to build a full file tailer.

### 7.1. File LogCollectorDemo.java

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LogCollectorDemo {

    record Event(Level level, String payload) {
    }

    private static void writeBatch(
            Path path, boolean append, List<Event> events)
            throws IOException {

        Logger logger = Logger.getLogger("demo.orders.Application");
        Level previousLevel = logger.getLevel();
        boolean previousUse = logger.getUseParentHandlers();

        FileHandler file = new FileHandler(path.toString(), append);
        file.setEncoding(StandardCharsets.UTF_8.name());
        file.setLevel(Level.ALL);
        file.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + "|"
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });

        logger.setLevel(Level.ALL);
        logger.setUseParentHandlers(false);
        logger.addHandler(file);

        try {
            for (Event event : events) {
                logger.log(event.level(), event.payload());
            }
        } finally {
            logger.removeHandler(file);
            file.close();
            logger.setLevel(previousLevel);
            logger.setUseParentHandlers(previousUse);
        }
    }

    static final class FileCollector {
        // In-memory (RAM) checkpoint; a new collector does not know the old offset.
        private int nextLine = 0;

        void poll(Path path) throws IOException {
            List<String> lines = Files.readAllLines(
                    path, StandardCharsets.UTF_8);
            int from = nextLine;

            for (int i = from; i < lines.size(); i++) {
                String[] fields = lines.get(i).split("\\|", -1);

                boolean valid = fields.length == 3
                        && Set.of("INFO", "WARNING", "SEVERE")
                                .contains(fields[0])
                        && fields[1].matches("[a-z]+\\.[a-z]+")
                        && fields[2].matches("evt-\\d{3}");

                if (!valid) {
                    System.out.println("REJECT line=" + (i + 1));
                    continue;
                }

                System.out.println("INGEST service=orders"
                        + " level=" + fields[0]
                        + " event=" + fields[1]
                        + " event_id=" + fields[2]);
            }

            nextLine = lines.size();
            System.out.println("POLL new_lines="
                    + (lines.size() - from)
                    + " checkpoint=" + nextLine);
        }
    }

    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory(
                "java-log-collector-demo-");
        Path file = dir.resolve("application.log");

        writeBatch(file, false, List.of(
                new Event(Level.INFO,
                        "order.created|evt-001"),
                new Event(Level.WARNING,
                        "inventory.slow|evt-002")));

        FileCollector collector = new FileCollector();
        collector.poll(file);
        collector.poll(file);

        writeBatch(file, true, List.of(
                new Event(Level.SEVERE,
                        "payment.failed|evt-003")));

        collector.poll(file);

        System.out.println("RESTART without checkpoint:");
        FileCollector restarted = new FileCollector();
        restarted.poll(file);
    }
}
~~~

### 7.2. Compile and run

With JDK 17 or later:

~~~bash
javac LogCollectorDemo.java
java LogCollectorDemo
~~~

**Expected stdout** on a successful run:

~~~text
INGEST service=orders level=INFO event=order.created event_id=evt-001
INGEST service=orders level=WARNING event=inventory.slow event_id=evt-002
POLL new_lines=2 checkpoint=2
POLL new_lines=0 checkpoint=2
INGEST service=orders level=SEVERE event=payment.failed event_id=evt-003
POLL new_lines=1 checkpoint=3
RESTART without checkpoint:
INGEST service=orders level=INFO event=order.created event_id=evt-001
INGEST service=orders level=WARNING event=inventory.slow event_id=evt-002
INGEST service=orders level=SEVERE event=payment.failed event_id=evt-003
POLL new_lines=3 checkpoint=3
~~~

### 7.3. Explaining the output

- The file is created in a **unique temporary directory**, avoiding overwriting any existing file. The random path is not printed, so stdout stays deterministic.
- The logger is set to level ALL, attached to a single FileHandler, and parent handlers are disabled so it does not also print through JUL's ConsoleHandler.
- The formatter writes only the level and fixed payload, without timestamps or thread IDs.
- FileHandler is **closed before FileCollector reads**, ensuring data has passed through the handler's flush step.
- FileCollector stores **nextLine** in RAM; when a poll sees no new lines, new_lines=0.
- After append=true, the third event is at the end of the file and is read once by the initial collector.
- A newly initialized collector with nextLine=0 reads all three records again. This is a **replay**; if downstream does not deduplicate by event ID, duplicate logs may occur.

### 7.4. Limitations of the simulation

**Do not use this program as a production collector** because:

- Files.readAllLines loads the entire file into RAM on every poll; unsuitable for large files.
- The offset is a **line count**, not a byte offset, inode/file identity, or fingerprint.
- It does not handle file rotation, rename, truncate, symlinks, or multiple writers.
- The checkpoint is only in RAM and is lost on restart.
- There is no network exporter, queue, retry, ACK, or persistent storage.
- Unparseable lines print REJECT and still advance the checkpoint; production needs an explicit quarantine/retry policy for important data.
- There is no TLS, authentication, redaction, rate limiting, or multi-tenant isolation.
- A pipe-delimited field format is unsafe if user input contains delimiters or CRLF. Use a real JSON encoder instead.
- The demo code only tests a single thread and does not verify that a backend stored the events.

**Core takeaway:** a file collector is a **stateful reader**. Checkpoint placement, restart handling, and the relationship with the exporter queue determine the likelihood of replay, data loss, or duplicates.

## 8. Illustrative OpenTelemetry Collector configuration

The example below assumes an **OpenTelemetry Collector distribution that includes the filelog receiver** (typically the **contrib** distribution or another distribution containing this component). Do not assume filelog is included in every core distribution.

Suppose logs are at **/tmp/java-logs/application.log** on a Linux test machine. Create **collector.yaml**:

~~~yaml
receivers:
  filelog:
    include:
      - /tmp/java-logs/*.log
    start_at: beginning
    encoding: utf-8

processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 256
    spike_limit_mib: 64
  batch: {}

exporters:
  debug: {}

service:
  pipelines:
    logs:
      receivers: [filelog]
      processors: [memory_limiter, batch]
      exporters: [debug]
~~~

**How to read this:**

- **filelog** ingests files matching the glob, starting from the beginning when appropriate for source state.
- **memory_limiter** limits memory pressure; tune it to actual available resources.
- **batch** groups telemetry for export.
- **debug** outputs data to inspect the pipeline; **not a production storage backend**.
- **service.pipelines.logs** actually enables and wires the components together.

This is an **illustrative configuration requiring the appropriate binary and environment**, not a Java snippet or guaranteed to run out of the box on every OS. Component names and config options can vary by release; validate against the binary you are running.

### 8.1. Checking the binary and configuration

Example with a properly installed binary named **otelcol-contrib**:

~~~bash
otelcol-contrib components
otelcol-contrib validate --config=collector.yaml
otelcol-contrib --config=collector.yaml
~~~

The executable name may vary by packaging or OS. The **components** command checks whether the distribution includes **filelog, memory_limiter, batch, debug**. The **validate** command catches invalid configuration before running.

Create test data on Linux:

~~~bash
mkdir -p /tmp/java-logs
printf 'INFO order-created\nWARN inventory-slow\n' \
  > /tmp/java-logs/application.log
~~~

These lines are **plain text for testing the receiver**, not JSON Lines and not in the Java temporary directory from section 7. Verify the path **inside the filesystem visible to the collector**; when the collector runs in a container, the host path must be mounted properly.

**Do not use the debug exporter in production with PII or secrets** if it prints payloads to a channel with broad read access. When moving to a real backend, configure the appropriate exporter, auth, TLS, queue, and retention.

### 8.2. When it runs but no logs appear

Check in order:

1. Whether the actual binary includes the filelog component.
2. Whether the config file is being read as expected.
3. Whether service.pipelines.logs references both filelog and the exporter.
4. Whether the glob path matches real files in the **collector process's filesystem**.
5. Whether the process has permission to read the file and traverse directories.
6. Whether start_at is positioned at the end of an existing file and waiting only for new lines.
7. Which stdout/stderr the debug exporter is writing to.
8. Whether a receiver/processor is failing to parse/filter or the memory limiter is refusing records.

Do not blindly switch the Java root logger to DEBUG if the real issue is the agent reading the wrong file.

## 9. Sending queue, retries, and persistent storage

In production, a Collector/gateway typically sends over the network:

~~~text
Received events
      |
      v
Sending queue ---> Network exporter ---> Destination
      ^                   |
      +----- retry -------+
~~~

**Design-only** exporter example (not runnable as-is because the endpoint is a placeholder):

~~~yaml
exporters:
  otlphttp:
    endpoint: https://otel-gateway.example.invalid
    sending_queue:
      enabled: true
      queue_size: 1000
    retry_on_failure:
      enabled: true
      initial_interval: 5s
      max_interval: 30s
      max_elapsed_time: 10m
~~~

**example.invalid** is only a non-routable placeholder. To run it, you need a real endpoint, TLS trust, authentication, and complete wiring under **service.pipelines.logs**. Some exporter helper names/values may differ by version.

### 9.1. A sending queue does not mean zero-loss

A queue helps survive **short outages**. However:

- A bounded queue can fill up when the backend is slow.
- Retries have time and capacity limits.
- A collector crash loses anything held only in RAM.
- The backend may have received a batch while the ACK was lost; retrying can create duplicates.
- Invalid credentials or permission policies will not fix themselves via retries.

**queue_size** is typically measured in **exporter requests/batches**, not individual log records. Actual RAM usage also depends on event size and batch size.

### 9.2. A persistent queue is an additional layer

Some exporters support the **file_storage extension** for their sending queue:

~~~yaml
extensions:
  file_storage:
    directory: /var/lib/otelcol/queue

exporters:
  otlphttp:
    endpoint: https://otel-gateway.example.invalid
    sending_queue:
      enabled: true
      storage: file_storage
      queue_size: 5000

service:
  extensions: [file_storage]
  pipelines:
    logs:
      receivers: [otlp]
      exporters: [otlphttp]
~~~

**This is an incomplete illustrative snippet**, missing the otlp receiver declaration and connection details. It only shows that **file_storage must be declared and enabled**, and referenced by the exporter.

A persistent queue can help recover pending batches after a collector restart. However, **a full disk, lost volume, storage corruption, retry exhaustion, or a full queue** can still cause data loss. If the directory resides on a container's ephemeral volume, the label "persistent" does not mean data survives Pod replacement.

### 9.3. Distinguishing checkpoint from exporter queue

- **Source checkpoint:** how far the file reader has read.
- **Exporter sending queue:** events that have passed through receiver/processors but have not yet been delivered to the destination.

Having a durable checkpoint with an in-memory-only queue can lose events that were **read but not yet sent** after a crash if the ACK mechanism is not aligned. Having a durable queue while losing the checkpoint can **re-read old files**. Both states must be tested together across the pipeline.

## 10. File rotation, multiline, and lifecycle

### 10.1. Rotation

A real file receiver must handle:

- **Rename/create:** the old file is renamed; a new file is created at the same path.
- **Copy/truncate:** the old file's contents are copied, then the source file is truncated to empty.
- New files may have different permissions than the old file.
- Rotated files may be deleted before the agent finishes reading them.
- A collector restart may lose the offset/file identity mapping.

The OpenTelemetry **File Log Receiver** supports common rotation mechanisms based on file identity/fingerprinting, but results still depend on configuration, old file retention time, permissions, and filesystem behavior. Do not assume every rotation tool is seamlessly compatible.

### 10.2. start_at beginning vs. end

- **beginning:** useful for backfill/testing; without an existing matching checkpoint, it may re-read the entire file.
- **end:** suitable when you only want new logs after monitoring starts, though it can miss historical logs.

Existing checkpoints, receiver versions, and file identification also affect behavior. Never look only at **start_at** and conclude the collector is guaranteed not to duplicate or miss logs.

### 10.3. Multiline Java stack traces

A Java error can span multiple lines:

~~~text
ERROR order.failed
java.lang.IllegalStateException: stock mismatch
    at com.example.orders.OrderService.reserve(OrderService.java:42)
Caused by: java.io.IOException: downstream unavailable
~~~

If filelog treats **each line as a separate record**, the stack trace fragments into events missing level and timestamp. Two solutions:

1. **Prefer JSON Lines**, placing the stack trace in an escaped string field.
2. For legacy plain text, configure a **multiline parser** defining the pattern that starts a new event, a timeout, and a record size limit.

Avoid overly broad regexes that cause **two independent events to merge into one**. Test exceptions with **Caused by**, suppressed exceptions, and concurrent multi-threaded logging.

### 10.4. Restarts, shutdown, and file deletion

The collector may not have finished reading a file when the application exits. If container logs are deleted early or an ephemeral volume disappears, **Collector queues/retries cannot recover bytes that were never read**. Coordinate application shutdown, log runtime retention, shipper lag, and collector lifecycle.

## 11. Metadata and correlation

Centralized logs that lack **service.name, environment, or trace_id** are hard to use during investigations.

Commonly useful fields:

- **service.name**: source service.
- **deployment.environment.name**: dev/test/staging/prod.
- **logger.name**: Java class/package emitting the log.
- **host.name / host.id**: execution location when permitted.
- **k8s.namespace.name / k8s.pod.name**: Kubernetes metadata when available.
- **severity_text / severity_number**: log level.
- **trace_id / span_id**: trace correlation when available.
- **event_id**: duplicate/gap detection for important events.
- **tenant_id**: customer partitioning with appropriate read access control.

Metadata must come from a **trusted source**. Do not use an unvalidated client header as tenant_id for authorization or routing into sensitive indexes. A traceId copied from a header also needs validation; if async context propagation breaks, the Collector cannot infer the right traceId from a message that lacks one.

**Cardinality:** do not use raw URLs containing UUIDs as metric labels or partition keys if the backend is not suited for high cardinality. Use a **route template**, such as **/orders/{id}**, and put request IDs in an appropriately indexed field.

## 12. Security for the log pipeline

Necessary control layers:

| Boundary | Safeguard |
| --- | --- |
| **Java application** | Never log passwords, access tokens, API keys, Cookies, or unnecessary raw PII. |
| **Encoder** | Structured JSON and proper escaping; prevent log injection. |
| **Local file/stdout** | Least-privilege read permissions, appropriate disk/rotation/retention. |
| **Agent** | Mount/read only authorized sources; run with an account without excess privileges. |
| **Collector receiver** | Protect network ports; require authentication for external sources. |
| **Processor** | Policy-based redaction/filtering, but never as a substitute for source hygiene. |
| **Exporter** | TLS, validated endpoints, scoped credentials, safe retries. |
| **Backend** | Tenant/environment isolation, RBAC, retention, encryption, access auditing. |
| **Dashboard/export** | Proper permissions for querying, sharing, downloading, and data residency. |

**Redaction in the Collector cannot erase raw copies already on the node/file.** If Java already wrote a secret to stdout, having a processor strip it before storage only protects part of the path. You must fix the application and handle any copies already emitted.

The **debug exporter** should only be used in controlled test environments. If it prints sensitive logs to Collector stderr, you have created another location that requires read-access control.

**Log injection**: user input containing CR/LF or delimiters can forge fake log lines if formatted into unescaped text. Keep message templates fixed, validate IDs, use a structured encoder, and test all the way through the Collector parser.

## 13. Collector observability: seeing the log path

A log collection system needs **its own metrics and health checks**. If the Collector fails and only reports errors through the broken pipeline itself, detection becomes very difficult.

Metrics an OpenTelemetry Collector may expose, depending on version:

| Metric | Meaning |
| --- | --- |
| **otelcol_receiver_accepted_log_records** | Records accepted into the pipeline by the receiver. |
| **otelcol_receiver_refused_log_records** | Log records refused by the receiver/pipeline. |
| **otelcol_exporter_sent_log_records** | Records reported as successfully sent by the exporter. |
| **otelcol_exporter_send_failed_log_records** | Send failures; may still be retrying, not necessarily lost. |
| **otelcol_exporter_enqueue_failed_log_records** | Failed to enqueue; high risk of loss. |
| **otelcol_exporter_queue_size** | Current queue length. |
| **otelcol_exporter_queue_capacity** | Total queue capacity. |
| **Process CPU / memory / uptime** | Health of the Collector process. |
| **Parse errors / file lag / dropped by reason** | Receiver/backend-dependent; helps pinpoint failures. |

Metric names may change across Collector versions; verify the telemetry endpoint and the actual exported metric list.

**Do not simply subtract accepted - sent and call that data loss**: records may still be in a batch, queue, or retry; multiple pipelines or sampling can also skew the denominator. To measure completeness, use **event IDs from a test set** and allow sufficient ingestion time.

### Suggested alerts

- **refused/enqueue failed** rising continuously on a pipeline that must retain logs.
- Sustained high queue utilization with increasing oldest-pending age.
- Exporter send failures lasting longer than the outage tolerance window.
- Collector restarts/OOMs, or persistent queue disk nearing full.
- Log throughput from a service dropping to 0 while traffic continues.
- Parsing errors spiking after a deployment that changed log format.
- Ingestion delay exceeding SLO.

There is no single percentage threshold right for every application; calibrate thresholds to traffic volume, event size, and retention requirements.

## 14. At-most-once, at-least-once, and duplicates

**At-most-once**: attempts delivery once; few duplicates but can lose data on failure.

**At-least-once**: retries/replays on failure; reduces data loss risk but can deliver duplicates.

**Exactly-once**: requires an end-to-end contract for identity, storage, and acknowledgement; **not guaranteed by default** by FileAppender + Filelog Receiver + OTLP.

Typical scenario:

~~~text
Collector sends evt-001 to backend
Backend has saved evt-001
ACK is lost on the network
Collector retries evt-001
Backend may save another copy
~~~

When reconciliation is needed, use **event_id**, source identity, and deduplication rules in the backend or consumer. For routine operational logs, a measured rate of duplicates is often acceptable. For **critical business events that must not be lost** (payments, state transitions), use transactions, an outbox, and a durable broker/store—do not treat a logger as a durable event bus.

## 15. Performance and backpressure

A collector can receive records faster than the backend can ingest them. When that happens:

- Queues grow.
- Batches wait longer.
- Memory/disk pressure increases.
- When full, the pipeline may return errors, block, or drop records depending on the component.
- Prolonged retries increase ingestion latency.
- Some logs appear only minutes after their event time.

Mitigations:

1. Limit volume at the source; do not print DEBUG inside every production loop.
2. Use batching in the right places to reduce network requests.
3. Measure **records/second and bytes/second**, not just counts.
4. Size queues for the bursts and outages the system must tolerate.
5. Use retry with backoff for transient errors; fix misconfigured auth/TLS directly.
6. Scale agents/gateways by CPU, RAM, queue depth, and throughput when appropriate.
7. Set size limits so a single oversized record cannot stall the pipeline.
8. Use compression if supported and measure the CPU trade-off.
9. Distinguish sampleable logs from audit/critical events that must not be dropped arbitrarily.
10. Verify drain time during shutdown.

**Increasing queue size does not cure a chronically slow backend**. An unbounded queue increases OOM risk; a large in-memory queue increases how many logs can be lost if the process is killed.

## 16. End-to-end testing across each boundary

An ideal test uses synthetic event IDs and verifies each stage:

~~~text
Java emits evt-001
  → stdout/file has evt-001
  → receiver accepted evt-001
  → processor keeps evt-001
  → exporter sends evt-001
  → backend indexes evt-001
  → query finds evt-001
~~~

### Test matrix

| Scenario | What to verify |
| --- | --- |
| Baseline 10 event IDs | Exact count and correct schema/tenant. |
| INFO/WARN/ERROR from Java | Consistent severity mapping. |
| CR/LF in message | JSON Lines does not produce forged records. |
| Multiline Java stack trace | Not split into multiple events outside the contract. |
| Vietnamese diacritics, emoji | UTF-8 is not corrupted. |
| File rotate rename/create | Neither drops the tail nor re-reads excessively. |
| File copy/truncate | Offset/file identity handled accurately. |
| Collector restart | Checkpoint and queue recover per policy. |
| Queue full | Drop/refused metrics emitted, no silent loss. |
| Backend offline then recovers | Retries recover within configured bounds. |
| Lost ACK | Duplicates detected via event ID. |
| Collector lacks file permissions | Failure is observable, no fabricated logs. |
| Wrong source path/glob | Test detects that logs are not being ingested. |
| K8s Pod restart | Check runtime retention and lag. |
| Dual stdout + OTLP paths | Same event is not ingested twice unintentionally. |
| Tenant A/B | No cross-tenant routing or querying. |
| Invalid TLS/auth | Fails closed, does not silently downgrade connection. |
| Oversized event | Explicit reject/truncate policy and metric. |
| Slow storage indexing | Distinguish late arrival from data loss. |

Do not conclude an event is lost from a single empty query. You need to know **the last boundary that saw event_id** and within what time window.

## 17. Runbook for investigating missing logs

Example: the orders application logs:

~~~text
WARN inventory.slow event_id=evt-804
~~~

but the dashboard does not show the record.

**Step 1:** Identify which logger actually emitted the event and which appender it wrote to. Check the effective level, exceptions, and output.

**Step 2:** Read the authorized source (stdout/file) for event_id. If the file contains the log, verify the agent has read permissions, the right path/glob, and a valid checkpoint.

**Step 3:** Check receiver accepted/refused, parsing/multiline, processor filters, and metadata routing. An intentionally filtered event is different from an unintended queue drop.

**Step 4:** Check exporter queue, retries, send failures, TLS/auth, endpoint, and gateway/backend health.

**Step 5:** Query the backend by service/environment/tenant and check **both event timestamp and ingest timestamp**; inspect index lag, retention, and read permissions.

**Step 6:** Fix the exact failing boundary, then add a test/alert at that boundary. Do not turn on root DEBUG across all of production just to diagnose an overloaded pipeline.

### Symptom guide

| Symptom | Where to check |
| --- | --- |
| File has event, receiver accepted=0 | Glob, mount, permissions, start_at, offset. |
| Receiver accepted rises, exporter sent does not | Processor drop, queue, network, retry. |
| Exporter sent rises, missing in dashboard | Backend index, tenant, timestamp, query. |
| Duplicates after restart | Offset checkpoint, replay, exporter retry, two agents. |
| Only stack traces are lost | Multiline parser, size limit, escaping. |
| Only one Pod is missing | Runtime log path, node agent, namespace routing. |
| Broken after new deployment | Schema, config version, level, and permission drift. |

## 18. Common mistakes

**1. Thinking the collector and logging framework are the same thing.** Java creates logs; the collector transports them.

**2. Assuming logger.info() returning means the event is indexed.** Many processing layers sit downstream.

**3. Declaring a receiver but forgetting service.pipelines.logs.** The component is not enabled.

**4. Using a Collector binary that lacks filelog.** Core and contrib/distributions ship different components.

**5. Two agents tailing the same file.** Likely to produce duplicates.

**6. Exporting both stdout and OTLP for the same event to one backend.** Easy to duplicate.

**7. Not persisting checkpoints while using start_at beginning on restart.** Can replay the entire file.

**8. Using start_at end and expecting historical backfill.** Can miss data written before monitoring started.

**9. Using line numbers as a production checkpoint.** Fails to handle rotation/truncation accurately.

**10. Not configuring multiline for text stack traces.** One exception splits into many records.

**11. Parser trusting delimiters in client-supplied data.** Log injection / field injection.

**12. Increasing queue size instead of fixing an overloaded backend.** Latency and memory pressure increase.

**13. Claiming zero data loss just because retries exist.** Full queues, retry timeouts, and disk failures can still lose data.

**14. Placing a persistent queue on an ephemeral volume.** Pod replacement restarts can wipe the queue.

**15. No collector internal telemetry.** No visibility into where the pipeline is blocked.

**16. Assigning tenant solely from an untrusted header.** Risk of routing logs to the wrong place or violating isolation.

**17. Redacting only at storage.** Raw logs may already exist on the host and collector.

**18. Using the debug exporter with sensitive data.** Creates another copy of payloads in collector logs.

**19. Not testing file permissions after rotation.** New files may have a different owner/group.

**20. Using logs for exact request counts when the pipeline samples/drops.** Metrics and logs have different semantics.

**21. Confusing event timestamp with observed timestamp.** Querying the wrong time range makes logs look missing.

**22. Forgetting to verify the destination.** Debug exporter passing does not mean the production backend received/indexed the data.

## 19. Pre-deployment checklist

- [ ] Identify the JVM log source: stdout, file, or OTLP.
- [ ] Know the exact logging backend/provider in use: JUL, Logback, Log4j2, etc.
- [ ] Each event has one primary export path to the backend, unless duplication is intentional.
- [ ] The collector binary includes the required receiver/processor/exporter.
- [ ] The receiver is declared **and enabled in the logs pipeline**.
- [ ] Glob, path, mount, and permissions are tested on real infrastructure.
- [ ] JSON Lines or multiline parser is tested with Unicode/CRLF.
- [ ] Resource fields service/environment/tenant come from trusted sources.
- [ ] No secrets or unnecessary personal data are logged.
- [ ] TLS/auth/RBAC for agent, gateway, backend, and dashboard.
- [ ] File rotation/retention does not delete files before the shipper reads them.
- [ ] Checkpoint/queue/retry meet the target outage window.
- [ ] Queue and memory/disk limits have alerts before saturation.
- [ ] Metrics accepted/refused/sent/failed/queue are observable.
- [ ] Tested restarts, backend outages, duplicates, partial writes, and schema changes.
- [ ] Backend queries verify event_id after indexing, not just the debug exporter.
- [ ] Runbook and owners are defined for every layer.

## 20. Exercises

1. Run **LogCollectorDemo.java**, explain each **POLL** line, and explain why a restart causes a replay.
2. Try modifying FileCollector to save the checkpoint to a small file. If the source file rotates or truncates, is a line count still sufficient?
3. Design an event_id to detect duplicates after an exporter retry.
4. Identify the four blocks in collector.yaml: receiver, processor, exporter, and service pipeline.
5. Explain why the filelog receiver is not always included in the core distribution.
6. Design a multiline Java stack trace test and compare it with JSON Lines.
7. A service writes WARN to a file, but it does not appear in the dashboard: list the evidence to collect at each layer.
8. Explain why exporter retries cannot preserve logs that the agent **has not read yet**.
9. Design tenant A/B isolation so a request with a forged tenant header cannot route logs to the wrong tenant.
10. In an isolated test environment, simulate a gateway going offline and recovering; measure queue depth, retries, missing, and duplicate event IDs.
11. Describe the risks of sending the same record both directly via OTLP and via a node agent.
12. Write alerts for a near-full collector queue, backend send failures, and a sudden drop in log ingestion.

## 21. Conclusion

**A log collector bridges Java logging and centralized observability infrastructure.** It ingests records via receivers, handles metadata/parsing/filtering, and delivers them to a backend via exporters. Understanding **offsets, rotation, queues, retries, storage, security, and metrics** helps you distinguish intentionally filtered logs from lost logs, duplicates, or records that simply cannot be found in the dashboard.

Three principles to remember:

1. **Separate responsibilities cleanly:** loggers/backends in the JVM create events; collectors gather and forward them; storage/indexes handle search and retention.
2. **Monitor every boundary:** track accepted/refused/sent/failed/queue metrics and use event IDs when verifying completeness.
3. **Never claim zero-loss just because retries exist:** checkpoints, persistent queues, and ACKs reduce risk, but do not provide end-to-end exactly-once delivery by default.

### Official references

- OpenTelemetry Collector Configuration: https://opentelemetry.io/docs/collector/configuration/
- OpenTelemetry Collector Resiliency: https://opentelemetry.io/docs/collector/resiliency/
- OpenTelemetry Collector Internal Telemetry: https://opentelemetry.io/docs/collector/internal-telemetry/
- File Log Receiver (Collector Contrib): https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/filelogreceiver
- OpenTelemetry Collector Exporter Helper: https://github.com/open-telemetry/opentelemetry-collector/tree/main/exporter/exporterhelper
- OpenTelemetry Logs Data Model: https://opentelemetry.io/docs/specs/otel/logs/data-model/
- Oracle Java SE 17 FileHandler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html
- Oracle Java SE 17 Logger: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html
- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html