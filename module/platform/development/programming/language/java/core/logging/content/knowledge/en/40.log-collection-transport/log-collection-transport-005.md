# File Shippers in Java Core Logging: Collecting and Transporting Logs from Files

## 1. What is a file shipper?

A **file shipper** is a process or agent dedicated to watching log files on a host, reading newly written bytes from applications, packaging them into records, and **transporting** them to a Collector, message broker, or centralized logging system. In Java, applications typically emit messages through `java.util.logging` (JUL), SLF4J/Logback, or Log4j2; the appender/handler writes to a file, and the shipper reads that file independently of the application.

```text
Java application
      |
      | logger.info(...) / logger.error(...)
      v
Logback / Log4j2 / JUL file handler
      |
      | append bytes
      v
app.log, app.log.1, ...             <- rotation/retention
      |
      v
File shipper
  discover -> read -> frame -> parse -> enrich
       -> buffer -> retry -> send -> checkpoint
      |
      v
Collector / broker / log backend
      |
      v
Search, dashboard, alert
```

The term "shipper" emphasizes the transport responsibility; related terms include **tailer**, **log agent**, **harvester**, and **collector file input**. A file shipper does not replace the logger API or business logic. It **cannot recover** a `DEBUG` event that was disabled before being written to the file, and it does not by itself guarantee that a read log will be indexed or queryable at the destination.

A well-designed pipeline must be able to answer: **which file** the agent is reading, **from which byte offset**, **how far it has processed**, whether a line is **complete**, **at which level the receiver has ACKed it**, and how **loss, duplication, or re-reading** behave when the process, file, or network changes.

## 2. When do you need a file shipper?

Common use cases include:

- A Java service running on a VM or bare metal, writing rolling files, where logs from multiple hosts need to be aggregated into a single backend.
- A single host running multiple applications; the shipper attaches `service.name`, environment, host, and version to records before sending.
- An organization wants separation of concerns: the application only writes files, while the agent holds the credentials and network permissions to transfer data.
- Buffering, retries, and state/checkpoints are needed independently of the Java process lifecycle.
- Legacy applications that only have a `FileHandler` or file appender and do not yet integrate an exporter.

However, **having Java logging does not automatically mean you must use a file shipper**. On Kubernetes, the commonly recommended approach is to log to **stdout/stderr** and let a node agent collect container logs. Applications can also emit OTLP Logs through a compatible SDK, appender, or Collector. If both stdout and a file containing the same event are read and shipped, the backend may see duplicate logs and incur double ingest and storage costs.

| Environment | Common model | Risks to verify |
| --- | --- | --- |
| VM or bare metal | Rolling file + local agent | File permissions, rotation, registry, disk full |
| Kubernetes | Stdout/stderr + node-level collection | Container runtime rotation, pod/node restart |
| Container with dedicated files | Sidecar/agent reading a shared volume | Ephemeral volume, startup/shutdown sequencing, duplication |
| Serverless | Platform logging or telemetry exporter | Files do not live long enough, no agent available |
| Mandatory business audit | Durable audit/outbox and appropriate export path | File shipper is not atomic with DB transactions |

An "intermediate" option can be having Java write to both stdout and a file. Only do this when each sink has a **distinct purpose** and a deduplication policy; do not enable both and then count logs in the backend as a business metric.

## 3. Lifecycle of a log file

Overview of the steps:

1. **File discovery:** scan paths/globs, such as `/var/log/orders/*.log`, to identify existing and newly created files.
2. **File identity:** recognize a file by a stable identity where supported (inode/device, file key, fingerprint, etc.), rather than by name alone.
3. **Open/read:** read bytes from an offset and process newly appended bytes.
4. **Framing:** determine event boundaries by LF/CRLF or a multiline parser.
5. **Parsing/enrichment:** parse JSON/text, attach service/host metadata, normalize timestamps, and redact if needed.
6. **Buffer/output:** enqueue, batch, compress if configured, and send to a Collector or backend.
7. **ACK/commit:** record progress at the point matching the delivery contract.
8. **Cleanup:** close readers, handle rotation/truncation, and manage checkpoints and retention.

```text
File discovery
    |
    +-- app.log     identity=A   offset=1200
    +-- app.log.1   identity=B   offset=9800
    |
Reader/harvester per file
    |
records with event boundaries
    |
queue + retry + output
    |
registry/checkpoint
```

Specific component names vary across Filebeat, Fluent Bit, Vector, and OpenTelemetry Collector. Do not assume an option has the same name or behavior across different shippers.

### Offsets are measured in bytes, not characters

If a UTF-8 file is 25,000 bytes long, a checkpoint `offset=12.000` points to a **position in the byte sequence**. Java's `String.length()` returns the number of UTF-16 code units and cannot be used in place of a file byte offset. For Vietnamese and Unicode characters, a single character can be encoded into multiple UTF-8 bytes.

For an accurate reader, the shipper must handle **byte boundaries**, and the decoder must avoid decoding an incomplete byte sequence. The offset is updated after a record has been framed and according to the commit/ACK contract.

### File path is not file identity

The name `app.log` may point to yesterday's old file and an entirely new file today. During rename/rotate, the same file may change its name while keeping its identity. Storing only `app.log + offset` can cause:

- Re-reading all old data when the existing identity is not recognized.
- Skipping the beginning of a new file because the old file's offset is applied.
- Missing the tail of a renamed file that still has unread bytes.

Some shippers use inode/device on Linux, file keys on other filesystems, or a fingerprint of the file header. Each strategy has limitations: inodes can be reused, fingerprints may lack enough data when a file is too short, and copytruncate preserves identity even though the content changes. Always test against your **actual filesystem and rotation policy**.

## 4. Framing: assembling bytes into a log event

A file is written as a **byte stream**, not a list of Java objects. Each logger `write` call does not necessarily correspond to one shipper read. A single event may be written in multiple fragments, and a single read may contain multiple events.

For example, after the first write:

```text
INFO started\n
WARN partial
```

Reading up to this point yields only **one complete line**. Second write:

```text
 warning\n
ERROR timeout\n
```

The shipper must send three events in total: `INFO started`, `WARN partial warning`, and `ERROR timeout`. If `WARN partial` is emitted immediately on the first read, the event will be split incorrectly.

Key considerations when designing framing:

- **Line delimiter:** usually LF (`\n`), though CRLF (`\r\n`) may appear; avoid keeping stray CR characters in the message.
- **Unterminated final line:** the shipper may hold it until an LF arrives, a timeout expires, or the file closes/rotates per policy; it should not be sent by default.
- **Max record length:** very long lines may be truncated or rejected; track parse error/drop metrics and enforce payload limits at the source.
- **Charset:** consistent UTF-8 from the Java encoder through the shipper; the decoder needs a policy for malformed bytes.
- **Multiple writers:** bytes can interleave when multiple processes write to the same file without proper locking or framing.
- **Buffered I/O:** the logger may buffer before flushing; the shipper can only read bytes that are already present in the file.

**Do not use `URLDecoder` or character-based text processing to compute file offsets.** Keep message parsing separate from the reader's byte position.

## 5. Rolling files and the two key rotation styles

### Rename-and-create

```text
Before:
  app.log    (identity A, size 10 MB)

Rotation:
  rename app.log -> app.log.1
  create new app.log

After:
  app.log.1  (identity A, may still have an unread tail)
  app.log    (identity B, read from offset 0)
```

The shipper must continue reading the remaining tail of identity A even though its path changed, while opening a new reader for identity B. If the application still holds the old file descriptor, it may continue writing to the renamed file; you need to determine when it is safe to close reader A.

### Copytruncate

```text
copy app.log to app.log.1
truncate app.log to length 0
application continues writing app.log
```

With copytruncate, the active file's identity may **stay the same** while its size drops to 0. Serious risk: the application writes new bytes **between the copy and the truncate**; those bytes are not in the copy yet are wiped out by the truncate. The shipper cannot reconstruct data that has vanished from both files. Resetting the offset when the size is smaller than the checkpoint helps resume reading, **but cannot fix the race condition that loses bytes**.

When you have a choice, rolling coordinated by the logging framework with a shipper that supports identity/rename is generally preferred over unverified copytruncate. However, you should test in practice with your OS, appender, writer, and agent; no single strategy fits every platform unconditionally.

### Compression and retention

Rotated files may be compressed to `.gz` or deleted according to retention rules. Many tail shippers **do not automatically read compressed files as active logs**; compressing or deleting a file before the shipper finishes drains will cause lost deliveries. You must tune:

- Keep files on disk longer than **worst-case shipper lag + recovery margin**.
- Configure globs and identity tracking so active and rotated files are not read twice.
- Ensure the shipper still has access to the old file after rename, even after the appender switches files.
- Ensure compression does not run too early and deprive the agent of the unsent original.
- Monitor disk quota and retention so the Java process is not impacted if the log destination stops accepting data.

Do not simply set `maxHistory=1` and expect the pipeline to survive a day-long network outage.

## 6. Checkpoints, ACKs, and delivery semantics

### What does a checkpoint actually mean?

A registry/checkpoint may record the position that was **read**, **parsed**, **enqueued**, or **output-ACKed**. That distinction determines whether logs are lost or duplicated during a crash.

```text
Read from file
   |
Parse event
   |
Enqueue
   |
Send to destination
   |
ACK at some layer
   |
Commit checkpoint
```

If the checkpoint is written before the event is successfully sent, a crash in the gap afterward can cause **data loss**. If the event is sent but the ACK is lost and a retry happens, the backend may receive a **duplicate**. "The agent shipped successfully" also needs a precise definition: whether the Collector returned HTTP 200, a message broker durably committed it, or the event is queryable in final storage.

| Guarantee level | Bounded meaning | Trade-off |
| --- | --- | --- |
| **At-most-once** | An event is attempted at most once per contract | May lose data on failure |
| **At-least-once** | An event may be resent after an error under stated conditions | May duplicate, requires dedup |
| **Exactly-once effect** | Logical effect is applied once within a transactional/idempotent boundary | Does not come automatically from tailing or retries; must be designed in the backend |

Log events should carry a **stable event ID** when reconciliation or deduplication is needed. A single request can emit multiple log events, so `request_id` is not always a suitable dedup key. Likewise, logging the same exception at multiple layers is **duplicate semantic logging**, which is distinct from a single event being resent multiple times due to a lost ACK.

**Mandatory audit/billing** must not rely solely on a file shipper to stay synchronized with business data changes. To guarantee atomicity between a DB transaction and an audit event, a transactional outbox or dedicated durable audit store may be required.

## 7. Standalone Java 17 example: byte offsets and partial lines

The following program uses **only JDK 17+**. It creates a temporary log file, writes one complete line and one unterminated line, and then simulates three shipper polls. State is stored in a separate checkpoint file; each poll reads the offset from that file.

This example only demonstrates **byte-based offsets and LF framing**; it intentionally does not model cloud backends, rotation, ACKs, or transactions. Do not use this code as a production shipper.

Save as **`FileShipperDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public final class FileShipperDemo {
    private static void ship(Path logFile, Path checkpointFile)
            throws IOException {
        long offset = Files.exists(checkpointFile)
                ? Long.parseLong(
                        Files.readString(
                                checkpointFile,
                                StandardCharsets.UTF_8).trim())
                : 0L;

        // Simple demo: read the entire small file into RAM.
        byte[] bytes = Files.readAllBytes(logFile);
        if (offset < 0 || offset > bytes.length) {
            throw new IOException("Checkpoint does not match file size");
        }

        int start = Math.toIntExact(offset);
        int committed = start;

        for (int i = start; i < bytes.length; i++) {
            if (bytes[i] != (byte) '\n') {
                continue;
            }

            int length = i - start;
            if (length > 0 && bytes[i - 1] == (byte) '\r') {
                length--;
            }

            String line = new String(
                    bytes, start, length, StandardCharsets.UTF_8);
            System.out.println("SHIP " + line);

            start = i + 1;
            committed = start;
        }

        Files.writeString(
                checkpointFile,
                Integer.toString(committed),
                StandardCharsets.UTF_8);
        System.out.println("CHECKPOINT=" + committed);
    }

    public static void main(String[] args) throws IOException {
        Path folder = Files.createTempDirectory("file-shipper-demo-");
        Path logFile = folder.resolve("app.log");
        Path checkpointFile = folder.resolve("checkpoint.txt");

        try {
            Files.writeString(
                    logFile,
                    "INFO started\nWARN partial",
                    StandardCharsets.UTF_8);

            ship(logFile, checkpointFile);

            Files.writeString(
                    logFile,
                    " warning\nERROR timeout\n",
                    StandardCharsets.UTF_8,
                    StandardOpenOption.APPEND);

            ship(logFile, checkpointFile);
            ship(logFile, checkpointFile);
        } finally {
            Files.deleteIfExists(checkpointFile);
            Files.deleteIfExists(logFile);
            Files.deleteIfExists(folder);
        }
    }
}
```

Compile and run:

```bash
javac FileShipperDemo.java
java FileShipperDemo
```

**Exact stdout:**

```text
SHIP INFO started
CHECKPOINT=13
SHIP WARN partial warning
SHIP ERROR timeout
CHECKPOINT=48
CHECKPOINT=48
```

Explanation:

1. `INFO started\n` is **13 UTF-8 bytes** long (all characters here are ASCII), so the first checkpoint is 13. `WARN partial` has no LF yet, so it is held back.
2. The application appends ` warning\nERROR timeout\n`, forming two complete records. The reader resumes from byte 13 and emits `WARN partial warning`, then `ERROR timeout`.
3. The two new records take 21 and 14 bytes respectively, including LF. The new offset is 13 + 21 + 14 = **48**.
4. The third poll finds no newline after offset 48, so it only prints `CHECKPOINT=48` and does not resend earlier lines.

**Limitations that must not be overlooked:**

- `Files.readAllBytes` loads the entire file into memory, which is unsuitable for large files; production shippers use streaming readers/buffers and proper resource management.
- It does not store **file identity** and cannot detect rename/recreate/copytruncate. If a new file has size ≥ the old offset, the demo may skip the beginning of the file; if smaller, it throws an exception.
- The checkpoint only writes an integer offset without atomic replacement or `fsync`; crashing mid-write can corrupt state.
- Printing `SHIP` to stdout is **not a durable backend ACK**. Crashing after printing but before checkpointing can cause replay; checkpointing before sending can cause loss.
- There is no file watcher, bounded queue, retry, dedup, TLS, authentication, record size limit, or parallel file handling.
- The decoder `new String(bytes,...,UTF_8)` in the demo may replace malformed bytes with the replacement character; a real shipper needs an explicit encoding error policy.
- One newline maps to one record, so multiline text stack traces require a multiline parser or JSON Lines.

The point of the example is to clarify two rules: **partial records must not be treated as processed** and **offsets are not line numbers**.

## 8. Log formats for shippers: text, multiline, and JSON Lines

### Text logs and stack traces

A Java exception is usually formatted across multiple lines in text mode:

```text
2026-01-01T10:00:00Z ERROR Payment failed
java.net.SocketTimeoutException: Read timed out
    at com.example.PaymentClient.call(PaymentClient.java:51)
    at com.example.OrderService.submit(OrderService.java:99)
```

If the shipper treats every LF as a separate event, the backend will receive multiple separate records instead of one exception. To handle this properly, you need **multiline framing**: detect the line that starts a record and merge subsequent lines until the next record starts. The rules must be tested against client-supplied messages containing timestamp-like strings to avoid incorrect merges or splits.

### JSON Lines

If the formatter writes one JSON object per line, newlines inside stack traces are encoded inside a JSON string:

```json
{"timestamp":"2026-01-01T10:00:00Z","severity":"ERROR","service.name":"checkout-api","event.name":"dependency.failed","exception.type":"java.net.SocketTimeoutException","message":"Payment failed","stack":"Read timed out\nat PaymentClient.call(...)"}
```

JSON Lines are generally easier to frame and parse by LF, but **that does not automatically mean the data is complete or error-free**. The encoder must escape control characters, and the shipper parser must match the schema, enforce size limits, and convert fields and timestamps to the right types. If a JSON line exceeds the shipper's max line size, it may be truncated or dropped.

**Do not log raw user input** containing newlines directly into text lines: it can cause log injection, tricking parsers into misreading the actor, severity, or event. Use a verified structured encoder and validate at the source.

Useful fields for searching:

| Field | Purpose |
| --- | --- |
| `timestamp` | Event time, for querying by occurrence time |
| `severity` | INFO/WARN/ERROR with consistent mapping |
| `service.name` / `environment` | Distinguish service, deployment, and tenant per policy |
| `event.name` / `error.code` | Search by stable event type or error code |
| `request_id`, `trace_id` | Cross-service correlation |
| `exception.type` | Group Java exceptions |
| `log.file.path` | Diagnose source file; do not turn into an arbitrary high-cardinality metric label |

A parser may ingest JSON and add host/pod metadata; field ownership must be agreed upon. Do not allow client input to overwrite `service.name` or `tenant_id` used for search authorization.

## 9. Writing files from Java: JUL and Logback

### JUL FileHandler

The Java JDK includes `java.util.logging.FileHandler` with support for pattern, limit, count, and append. A minimal program:

```java
import java.io.IOException;
import java.util.logging.FileHandler;
import java.util.logging.Logger;
import java.util.logging.SimpleFormatter;

public final class JulFileLoggingExample {
    public static void main(String[] args) throws IOException {
        Logger logger = Logger.getLogger("example.file.logging");
        logger.setUseParentHandlers(false);

        FileHandler handler = new FileHandler(
                "app-%g.log", 1_000_000, 3, true);
        handler.setFormatter(new SimpleFormatter());
        logger.addHandler(handler);
        try {
            logger.info("Started application");
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }
    }
}
```

Save as `JulFileLoggingExample.java` and run `javac JulFileLoggingExample.java`, `java JulFileLoggingExample` if you want to try it. The program writes files in the working directory; the actual filenames depend on `%g`, rotation, OS, and existing file state. `SimpleFormatter` outputs text with no JSON schema or guarantee that a shipper will parse stack traces cleanly. `FileHandler` has its own rotation policy; test your agent configuration against the file naming/indexing and write permissions.

### Logback RollingFileAppender

An **illustrative** configuration for an application that already has the Logback dependency:

```xml
<configuration>
  <appender name="FILE"
      class="ch.qos.logback.core.rolling.RollingFileAppender">
    <file>logs/app.log</file>
    <rollingPolicy
        class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
      <fileNamePattern>logs/app.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
      <maxHistory>7</maxHistory>
    </rollingPolicy>
    <encoder>
      <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
    </encoder>
  </appender>
  <root level="INFO">
    <appender-ref ref="FILE"/>
  </root>
</configuration>
```

This uses a **text pattern**, not JSON Lines. Verify the `logs` directory, Logback version, log level, flush policy, rolling behavior, and actual `maxHistory`. Rotation with archive compression can interact with the shipper: test scenarios where the agent is lagging, a file has just been renamed, a new file is created, and the appender still holds the old descriptor.

Log4j2 has a `RollingFile` appender and corresponding policies, but its XML/YAML syntax and lifecycle differ from Logback; do not reuse a Logback configuration directly for Log4j2.

In multi-process environments, avoid having multiple JVMs write to the same file without coordination; separate files per service/instance are usually easier to ship and enrich with metadata.

## 10. Common file shippers

File shippers can be deployed as host services, node agents, sidecars, or parts of an observability pipeline.

| Tool | Core concepts | Version-specific checks |
| --- | --- | --- |
| **Filebeat** | File input/filestream, harvester, and state registry | File identity, checkpoint, close/ignore policy, rotation, output ACK |
| **Fluent Bit** | Tail input, parser, filter, and output plugins | State DB, multiline, buffer storage, rotation wait, retry |
| **Vector** | File source, transforms, and sinks | Fingerprint, checkpoint, multiline, disk buffer, and acknowledgements |
| **OpenTelemetry Collector filelog receiver** | Reads files and feeds events into the logs pipeline | Whether the distribution includes the receiver, storage extension, parsing, and exporter |

Option names, YAML configuration, and "ACK" semantics are **not identical** across products or versions. Before deploying, build a configuration checklist:

```text
source paths / globs
file identity policy
starting position for an unseen file
checkpoint/registry storage and persistence
line framing / multiline / max event size
encoding / timestamp / JSON parsing
metadata enrichment and redaction
bounded memory/disk queue and batch settings
destination TLS/auth and retry policy
rotation, compressed archives and retention
self-metrics, healthcheck and failure alerts
```

Do not apply a sample configuration to production without verifying that your build supports each option. In particular, the **OpenTelemetry Collector filelog receiver** may not be bundled in every distribution; installing a Collector binary and adding `filelog` config is not guaranteed to work out of the box.

## 11. Buffering, backpressure, and backend outages

Suppose Java generates logs **faster** than the agent can send them. The file continues to grow and the agent's queue may fill up; if rotation deletes old files before the agent finishes reading them, logs are lost.

```text
Java writer: 2 MB/s
     |
     v
app.log grows
     |
File shipper reads
     |
memory/disk queue --> network --> backend
     |                              |
     +-- queue full                 +-- timeout/429/503
         |                              |
      pause/drop                    retry/backoff
```

Policies you should have in place:

- **Bounded queue:** cap RAM/disk usage, with depth/bytes/age metrics. Do not assume memory buffering survives a process crash.
- **Retry:** for network timeouts and backend 429/503 responses, use exponential backoff with jitter and appropriate limits. Retries can create duplicates.
- **Backpressure:** the agent may pause reading files. Java keeps writing to files, making disk space and retention the final buffer.
- **Poison events:** an oversized or invalid JSON record must be handled by policy rather than stalling the pipeline indefinitely without alerts.
- **Disk full:** the appender/file writer may fail and impact business logic; configure quotas, rotation, alerts, and fail-open/fail-closed policies per event type.
- **Shutdown:** wait for flush/ACK within a reasonable deadline and persist recoverable state; do not claim zero event loss simply because a process exited "gracefully."

A rough sizing model:

```text
source_bytes_per_second
  ≈ events_per_second × average_serialized_bytes_per_event

buffer_bytes_needed (estimate)
  ≳ peak_bytes_per_second × expected_destination_outage_seconds
```

This is only an estimate: batching, compression, metadata, disk overhead, duplication, and buffer format change actual requirements. At 2 MB/s for 30 minutes, newly generated logs total about **3,600 MB** before overhead; a 500 MB buffer cannot hold everything if the backend is unreachable for the entire window.

File retention must exceed the worst-case backlog and recovery time with margin; otherwise the shipper may still be healthy while **older events have already been deleted**.

## 12. File shippers in Kubernetes and ephemeral environments

In Kubernetes, the standard path is for Java to write to stdout/stderr, the container runtime to manage logs on the node, and a DaemonSet collector to gather them. If an application writes to private files inside a container while the node agent only reads stdout, those files may **never reach the backend**.

Common options:

1. **Stdout/stderr + node agent:** simple for the app, but you must verify runtime rotation, pod metadata, node disk, and agent lifecycle.
2. **Files on a shared volume + sidecar:** appender and shipper see the same files; requires managing volume permissions, startup/shutdown ordering, and resource requests/limits.
3. **Files on a persistent volume + agent:** files can survive pod restarts depending on the PV and policy; requires verifying file identity, ownership, and retention.
4. **Direct telemetry exporter:** the appender/SDK sends directly over a protocol with appropriate buffering; avoids file tailing, but requires managing retries, shutdown, and backpressure yourself.

**Do not read both stdout and a file containing the same event** unless you have a clear strategy to distinguish sources or deduplicate. Do not assume a sidecar is guaranteed to stay alive until it drains every file when a pod is killed: test shutdown grace periods and termination ordering.

In serverless or ephemeral compute, writing to a local file and expecting an external shipper to read it after the instance is torn down is a design very prone to log loss.

## 13. Security of files, shippers, and export paths

Log data may contain request context, stack traces, identifiers, or personal information. Shippers must follow **least privilege and source-side data protection**:

- The Java application should only have write access to its required log directory; the shipper should only read the files it needs to ship and write its registry/buffer in a separate directory.
- Avoid overly broad globs that accidentally collect secrets, other tenants' audit trails, or out-of-scope files.
- Be cautious with symlinks and file paths controlled by untrusted actors so the shipper cannot be tricked into reading files outside policy.
- Output credentials must be protected via a secret store or credential provider; never hardcode tokens in source code, log messages, or publicly shared configs.
- Use TLS and endpoint authentication across untrusted network boundaries; grant ingest permissions only to the intended project, tenant, and environment.
- Do not log passwords, access tokens, session cookies, private keys, or unnecessary personal data **at the Java call site**. Redacting at the shipper does not remove data already written to local disk.
- JSON encoders and parsers must escape newlines, CRs, and control characters to prevent log injection, and must validate actor, tenant, and severity from trusted sources.
- Backend **search/export/delete** permissions should be separated from agent ingest permissions; retention across files, queues, and backend must follow policy.
- Mandatory audit logs require tamper-evidence, durability, and separate reconciliation; an ordinary log file is not immutable evidence by itself.

A shipper can enrich service/host/pod metadata, but must not allow a field from client-supplied messages to override system identity or the tenant scope used for access control.

## 14. Metadata, request IDs, and trace correlation

An event can be enriched with metadata during shipping:

```json
{
  "timestamp": "2026-01-01T10:00:03Z",
  "severity": "ERROR",
  "service.name": "orders-api",
  "deployment.environment.name": "prod",
  "host.name": "vm-01",
  "log.file.path": "/var/log/orders/app.log",
  "event.name": "order.process.failed",
  "request_id": "req-42",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "error.code": "DOWNSTREAM_TIMEOUT",
  "message": "Payment provider timed out"
}
```

This is an illustrative schema, not a set of field names automatically mapped by every backend. In Java applications, `MDC`/`ThreadContext` can attach `request_id` and `trace_id` to events. However, MDC is typically thread-bound and **does not automatically propagate across all `ExecutorService`, `CompletableFuture`, or reactive tasks**; proper context propagation and cleanup after tasks are required.

When the agent parses JSON, distinguish application-emitted fields from deployment/agent-emitted fields, and define precedence rules if keys collide. Do not synthesize a fake `request_id` at the agent, as it cannot know the full request flow if the application did not propagate it.

To troubleshoot errors, query logs by service/time/error code and then open the timeline by request or trace ID. Do not turn request IDs or trace IDs into **high-cardinality metric labels**, even though they are valuable in log search.

## 15. Observing and monitoring shipper health

A shipper reporting "process is running" does not prove it is reading or delivering data. Track:

| Observability signal | Purpose |
| --- | --- |
| `files_discovered` / `files_active` | Whether the input finds the right files and readers remain active |
| `bytes_read_total` | Read throughput and ability to keep up with the source |
| `events_parsed_total` | Number of parsed records |
| `parse_errors_total` | Invalid JSON, multiline, or encoding issues |
| `queue_depth` / `queue_usage_bytes` | Backlog and buffer pressure |
| `events_sent_total` | Volume of events attempted for delivery |
| `events_acked_total` | Count confirmed at the output contract level |
| `events_dropped_total` | Dropped due to limits, filters, or failures |
| `output_retries_total` | Network, quota, or output errors |
| `oldest_unshipped_event_age` | Age of the oldest undelivered event |
| `checkpoint_errors_total` | Registry failed to persist or restore properly |
| `ingestion_lag_seconds` | Time from event occurrence until queryable in the backend (if measurable) |

**These metric names are design suggestions**, not the default names in every version of Filebeat, Fluent Bit, Vector, or Collector. Map them to the actual metrics exposed by your tool and view them on a dashboard.

An **end-to-end canary test**:

1. Java writes a unique event ID containing no secrets.
2. Confirm the log is flushed to the file as a complete record, with valid JSON if using JSON.
3. Observe agent discovery, reader, and output activity.
4. Query the backend by event ID within the appropriate time window and SLO deadline.
5. Verify metadata, occurrence count, ingest latency, and related events.
6. Repeat after app/agent restarts, rotation, network partitions, and quota/429 conditions.

Do not use `Thread.sleep(1000)` and assume ACK; wait on explicit conditions with timeouts and measure at the true point of success.

## 16. Diagnosing common issues

| Symptom | Possible causes | What to check |
| --- | --- | --- |
| Logs appear in file but not in backend | Wrong glob, permissions, agent stopped, exporter error, wrong query | Input discovery, agent metrics, time window, destination |
| Many logs resent after restart | Lost registry or starting position reset to beginning | Checkpoint persistence, file fingerprint, version migration |
| Beginning of new file lost on rotation | Old offset applied to new file identity | Identity and rename/create tests |
| Tail of old file lost | Reader closed too early, archive compressed/deleted | Rotate wait, lifecycle, retention |
| A few lines lost during copytruncate | Copy/truncate race | Switch to another rolling strategy or accept risk per policy |
| One exception split into multiple events | Text stack trace split on LF | Multiline parser or JSON Lines |
| JSON truncated or corrupted | Max line length, malformed encoding, partial line | Framing, parser errors, size limits |
| Vietnamese logs show garbled characters | Charset mismatch or UTF-8 byte split | Source encoder, agent decoder |
| Delayed delivery to backend | Queueing, retries, 429/503, slow network | Oldest event age, queue depth, exporter errors |
| Single event appears twice | Lost ACK/retry, checkpoint reset, two agents | Event ID, owner/input policy, dedup |
| Missing request ID | Logger/encoder omits MDC or context was dropped | App logger, propagation, JSON parser |
| Disk full | Writer faster than shipper, insufficient retention/quota | Disk usage, output throughput, rotation |
| Some files skipped | Ignore policy, file too old, fingerprint threshold | Input rules and identity metrics |
| High shipper CPU/memory | Expensive regex/multiline, too many files, large queue | Profiling, bounded state, parser tuning |
| Logs containing secrets shipped | App logged secrets, redacted too late | Fix at source, review file + queue + backend |

Do not blindly delete the registry and replay all files as a universal fix: that can flood the backend with millions of duplicate events. Understand the state, file identity, scope, and recovery policy before taking action.

## 17. Pre-production testing checklist

| Scenario | Expected behavior |
| --- | --- |
| Java writes a complete JSON line | One event is parsed and sent per contract |
| Event written in multiple chunks without LF | Partial line is not emitted prematurely |
| CRLF and multi-byte Unicode | Decoder preserves exact values and byte offsets |
| Multiline stack trace | Merged into one event without swallowing the next event |
| Rename/create | Old file is drained; new file starts at the right offset |
| Copytruncate | Byte-loss risk is measured; no false zero-loss claims |
| Compressed/expired archives | Unshipped logs are not deleted within policy |
| Java/agent restart | Checkpoints and file identities remain accurate |
| Crash after send, before ACK | Retry/duplicate behavior matches expectations |
| Network outage / HTTP 429/503 | Bounded queue, retry, backoff, and alerts activate |
| Full disk / permission denied | Does not break the application outside failure policy |
| Multiple agents on the same path | Single owner/dedup prevents unintended duplication |
| Kubernetes pod restart | State/volume/stdout collection behaves as required |
| Secrets/PII in messages | Secrets are not logged at the source; redaction works |
| Invalid destination auth/TLS | Export fails clearly without sending insecurely |
| End-to-end query | Event ID is searchable within deadline with correct schema/metadata |

For system testing, inspect logs from Java, file contents, registry/checkpoint state, agent queues, Collector/output metrics, and the search backend. Testing a single `readLine` function does not prove a reliable log shipping pipeline.

## 18. Common mistakes

| Mistake | Consequence | Solution |
| --- | --- | --- |
| Re-reading the entire file on every poll | Wastes I/O, creates duplicates | Offsets + checkpoints |
| Storing only the file path | Fails to detect rotation | Platform-appropriate file identity/fingerprint |
| Using character counts as UTF-8 offsets | Resumes at wrong byte after restart | Track offsets in bytes |
| Shipping lines without a newline | Corrupted or split events | Buffer partial records |
| Checkpointing before successful delivery | Data loss on crash | Commit per ACK contract |
| Treating retries as exactly-once | May produce duplicates | Event IDs, idempotent sink |
| Ignoring copytruncate risks | Unrecoverable byte loss | Test races, choose a safer policy |
| Compressing/deleting rotated files too early | Reader cannot finish tailing | Retention > lag + margin |
| Using text stack traces without multiline | One exception becomes many records | Multiline parser or JSON |
| Collecting both stdout and file duplicates | Higher volume and backend cost | Single collection path or explicit dedup |
| Not persisting registry across restarts | Re-ingestion or gaps depending on start policy | Persistent checkpoints |
| Checking only that the agent is alive | Misses backlogs, drops, and parse errors | Metrics, canaries, and alerts |
| Writing tokens to disk and redacting only at Collector | Exposed on local disk | Data minimization at the call site |
| Using file shipper as DB-atomic audit | Business data commits while log is lost | Transactional outbox / audit storage |

## 19. File shipper deployment checklist for Java

- [ ] Confirmed a file shipper is the right choice instead of stdout/OTLP for the environment?
- [ ] Java appender configured with the right level, file path, UTF-8, and rolling policy?
- [ ] Logs formatted as JSON Lines or paired with a reliable multiline parser for stack traces?
- [ ] Agent supports file identity, byte offsets, checkpoints, and rename/create/copytruncate handling?
- [ ] File retention exceeds worst-case backlog, recovery time, and rotation delay?
- [ ] Delivery ACK, retry, dedup, buffering, and failure policies defined and tested?
- [ ] On backend 429/503 or network loss, agent enforces bounded queues, backoff, and alerts?
- [ ] Prevented two shippers or two sinks from unintentionally collecting the same event?
- [ ] Files, checkpoints, credentials, and network configured with least privilege and TLS?
- [ ] Secrets/PII omitted from logger calls; client-supplied fields properly escaped?
- [ ] Events include timestamp, service/environment, event name, and request/trace ID where needed?
- [ ] Metrics for bytes read, parse errors, drops, queue backlog, retries, and ingest lag on dashboards?
- [ ] Tested log rotation, restarts, full disk, lost ACK, UTF-8, multiline, retention, and pod deletion?
- [ ] End-to-end canary confirms an event ID is queryable in the backend within the deadline?

**Conclusion:** A file shipper is the **bridge between Java log files and centralized observability**. Simply reading newly appended lines is not enough: the design must also address **file identity, rotation, partial lines, byte checkpoints, ACK/retry, durability, and access control**. Use an appropriate logger/encoder to produce structured events, a dedicated shipper to collect and transport them, and end-to-end measurements to prove logs arrive when needed.
