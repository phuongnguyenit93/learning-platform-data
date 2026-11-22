# Host Agents in Java Logging: Collection, Buffering, and Transport

## 1. What is a host agent?

In a logging architecture, a **host logging agent** is a process running on a host, virtual machine, or node that reads logs produced by one or more applications, enriches metadata, processes formatting, buffers during network outages, and forwards logs to a collector, message broker, or observability backend.

For example, a Java service writes logs via SLF4J + Logback to stdout or a rolling file. An agent such as **Fluent Bit, Filebeat, Vector**, or **OpenTelemetry Collector deployed in agent mode** can collect those records without the application having to connect directly to every destination.

~~~text
Java service A --- stdout/file ---+
                                  |
Java service B --- stdout/file ---+--> Host agent
                                  |      |
Other host logs --- journald -----+      +--> Parse/enrich/filter
                                         +--> Memory/disk buffer
                                         +--> Batch/retry
                                                 |
                                                 v
                                        TLS / network gateway
                                                 |
                                                 v
                                         Collector / storage
                                                 |
                                                 v
                                         Search / alerts / SIEM
~~~

An agent is not a **logger**, **MDC adapter**, **broker**, or **the final storage system itself**. The logger emits events; the agent ingests and transports events according to the configured pipeline. The fact that an agent succeeds in reading a line does not mean the backend has received or durably stored that line.

Learning objectives for this lesson: know where to place an agent, which source to choose, how to ensure framing/offset/rotation, how to tune buffering and backpressure, how to control privacy, how to test retry mechanisms, and how to verify the pipeline from the Java service to the backend.

## 2. Why not let every application push all logs directly?

An application can send logs directly over HTTP/OTLP/TCP or a dedicated appender. This approach has valid use cases, but a host agent provides several advantages:

- **Separation of concerns:** Java code focuses on business logic; transport, retries, endpoints, credentials, and batching are managed by the agent.
- **Shared resources:** multiple processes can share a single collection pipeline instead of each app maintaining its own client.
- **Unified configuration:** host/service metadata, redaction policies, routing, diagnostic log sampling, and TLS are managed centrally.
- **Reduced direct coupling:** when the backend experiences transient errors, the agent can hold data in a queue, subject to capacity limits and policies.
- **Observability beyond Java:** systemd journal, container logs, and certain OS or daemon logs can be collected in the same stream.
- **Backend switching:** the application only needs to keep a stable log schema, while the agent/collector adjusts the output.

However, an agent also introduces its own costs and failure modes: parsing CPU, memory queues, disk spooling, log volume, latency, deadlocks caused by full disks, file read permissions, and configuration errors. **Having an agent does not mean logs are delivered exactly-once.** Retries after a lost ACK can create duplicates; lacking a durable buffer or having short retention can cause event loss.

## 3. How do agent, sidecar, gateway, and collector differ?

| Role | Deployment | Typical responsibilities |
| --- | --- | --- |
| **Host agent** | Per VM/node, systemd service, or Windows service | Read multiple local sources, track file positions, send logs |
| **Kubernetes DaemonSet** | One or a set of agent pods per eligible node | Collect container stdout/stderr and host-level logs |
| **Sidecar** | Same pod/deployment unit as the app | Read workload-specific volumes/logs |
| **Central gateway/collector** | Centralized service with load balancing and HA | Receive from agents, enrich, route, and export |
| **Logging backend** | Search/warehouse/object store/SIEM | Store, index, retain, and query |
| **Java logging provider** | Inside the JVM, e.g., Logback | Create/format events by level/context |

A single product can serve multiple roles depending on configuration. For example, **OpenTelemetry Collector** can run on a node as an agent or at the gateway tier. A tool's name alone does not uniquely determine its deployment placement.

**DaemonSet does not mean one agent per pod:** it is typically per-node; this affects mounted path permissions, namespace names, resource limits, and how log sources are selected. A sidecar has an ownership boundary close to the app but increases the process count when there are many pods. A host-level agent is simpler to manage centrally on a node, but requires a way to distinguish data from multiple workloads.

## 4. Choosing log sources from a Java application

A host agent can read the following sources:

| Source | How Java writes to it | Key considerations |
| --- | --- | --- |
| **stdout/stderr** | ConsoleAppender / standard streams | Container runtime or service manager is usually the first log storage layer |
| **Rolling file** | RollingFileAppender | Rotation, inode/file identity, rename, copytruncate, access permissions |
| **systemd journal** | JVM stdout/stderr running under systemd | Journal cursor, persistence, permissions, rate limiting |
| **Container log files** | stdout/stderr written on the node by the runtime | Pod/container metadata and rotation managed by runtime/kubelet |
| **Windows event sources** | Specific app/host integration | Providers and source APIs vary by environment |
| **Socket or OTLP receiver** | Appender/SDK exporting directly via protocol | Requires endpoint/batching and is not "tailing a file" |

**Do not unintentionally collect the same event from two paths simultaneously.** For example, if an app writes to both console and a file, an agent collecting both will create duplicates in the backend. Establish a clear **source of truth**; if multiple paths must be collected, there must be a strategy to distinguish or deduplicate them.

For containerized applications, prioritize understanding the stdout -> runtime logs -> node agent path. Files inside a container's private filesystem are not necessarily readable by the host agent unless volumes/mounts/drivers support it.

For JVMs running on a VM, you can use console under systemd journal or files; base the decision on retention policy, rotation, permissions, and the agent's collection capabilities.

## 5. Event format: prefer a contracted structure

An agent works more reliably when the application outputs **one log event per JSON line (NDJSON/JSON Lines)**, if supported by the framework and pipeline. For example:

~~~json
{"timestamp":"2026-11-10T03:15:00Z","level":"INFO","service":"order-api","event":"order_accepted","requestId":"req-42","durationMs":18}
~~~

The **JSON serializer** must escape newlines, quotation marks, and control characters in strings. Never manually concatenate JSON from raw user input; a valid JSON object does not by itself guarantee that sensitive data has been redacted.

Useful fields:

| Field | Principle |
| --- | --- |
| timestamp | Event emission time, with explicit timezone/UTC |
| level | DEBUG/INFO/WARN/ERROR determined by the logger |
| service, version, environment | Low-cardinality metadata; can be enriched at the agent |
| host.name, node, container.id | Source metadata; prevent spoofing from payload |
| event/eventCode | Standardized value, not arbitrary free text |
| requestId, traceId, spanId | Validated correlation identifiers |
| loggerName, threadName | For Java troubleshooting |
| exception.type, stacktrace | Error data following schema and policy |
| message | For description; do not use as the sole source for alerts |
| schemaVersion | Helps parsers transition formats in a controlled manner |

If the app outputs a timestamp and the agent also adds a received timestamp, distinguish **event time** from **ingestion time**. Do not overwrite the event timestamp with the agent's clock without preserving a separate field if doing so distorts the timeline.

**Message IDs and trace IDs should not be used as metric labels** due to high cardinality; keep them in logs/traces and use aggregated metrics for throughput and errors.

## 6. Internal stages inside a host agent

An abstract pipeline:

~~~text
Source read
    |
    v
Framing (line / journal entry / protocol frame)
    |
    v
Parser (JSON, regex, or multiline)
    |
    v
Enrichment (host, service, env, source)
    |
    v
Filter / transform / redaction
    |
    v
Memory queue or filesystem-backed buffer
    |
    v
Batch + compress if supported
    |
    v
Transport (TLS / mTLS / authenticated protocol)
    |
    v
Remote acknowledgment
    |
    v
Advance durable checkpoint / release buffered record
~~~

This is a **logical model**; the actual order among parsing, buffering, read checkpointing, and sending depends on the agent/plugin. Some implementations update the **file read offset** before the remote ACK while storing the record in an accepted disk buffer; therefore, you must not infer a single fixed mechanism from the diagram.

The key distinction is two different kinds of state:

- **Read position/checkpoint:** how far the agent has read in the source.
- **Delivery/persisted buffer state:** where the data is durably stored and whether it is still awaiting a destination ACK.

A pipeline may have read up to EOF while thousands of events remain unsent; seeing an incremented offset alone does not mean transport is complete.

## 7. Offset, cursor, and state persistence

When tailing a file, an agent needs to know where it left off to avoid re-reading everything on restart. For regular files, state may involve **file identity + byte offset** (specific identification depends on the OS and agent). For journald, a **journal cursor** is typically used; for protocol streams, sequences, ACKs, or other state may be used.

Avoid two assumptions:

1. **An incremented offset means the backend has received the data.** False: the offset may describe source reading, not remote delivery.
2. **Restarting from the exact offset guarantees exactly-once.** False: if the remote side received the data but the ACK was lost, retrying can send duplicates. If the checkpoint advances too early and the buffer is lost, events may be gone before being sent.

A solid design needs to define:

- Where the state/checkpoint file or database lives and whether it persists across restarts.
- Whether file identity recognizes the file after rename rotation.
- How the agent synchronizes the read offset with the spool.
- Whether a remote ACK means received, queued, or durably stored (per protocol).
- Whether losing the state file leads to re-reading from the beginning, from the end, or another recovery policy.
- Whether state backups accompany log/buffer backups, and whether restoring causes duplicates or truncation.

**Choose explicit delivery semantics.** At-least-once is usually the pragmatic target when duplicates are acceptable and buffering/retries are present; do not claim exactly-once merely because a file offset checkpoint exists.

## 8. File rotation: rename vs. copytruncate

Java applications using `RollingFileAppender` can rotate by size or time. Two common operational patterns have different impacts:

### Rename/create

~~~text
Before:
  app.log   (inode A)  <- JVM writes

Rotation:
  app.log -> app.log.1 (inode A)
  new app.log (inode B) <- JVM starts writing
~~~

The agent must continue reading the **unprocessed remainder of inode A** and start tracking the new file B. If it only tracks the name `app.log` without tracking file identity and a rotation grace period, data around the transition can be lost or duplicated.

### Copytruncate

~~~text
app.log is copied to archive, then truncated in place
~~~

If the app writes between the copy and the truncate, bytes can be lost from both the archive and the current file; it is also hard for the agent to detect the new position if the file shrinks. **Prefer avoiding copytruncate when designing for high reliability**, if the rolling/logger stack supports rename/create appropriately.

Important tests to run:

- Rotate while the file is being written continuously.
- Restart the agent mid-rotation before the buffer is fully flushed.
- Multiple files matching the pattern; are archived files re-read?
- File deleted early before the agent finishes reading it.
- Disk space when rolling/archives and agent spool share the same partition.
- Are agent permissions for the new file properly inherited after rotation?

Do not change rotation policies on gut feeling; measure lag, check plugin behavior, and test in a production-like environment.

## 9. Multiline Java exceptions and framing

Traditional Java stack traces span multiple lines:

~~~text
2026-11-10T03:15:00Z ERROR event=order_failed requestId=req-42
java.lang.IllegalStateException: payment unavailable
    at example.OrderService.pay(OrderService.java:42)
    at example.OrderHandler.handle(OrderHandler.java:18)
Caused by: java.io.IOException: connection closed
    at example.HttpClient.call(HttpClient.java:73)
~~~

If the agent treats **each physical line as one event**, the stack trace is split into multiple records missing timestamp/level/requestId. If the agent groups multiline records too greedily, it can merge stack traces from two threads or two applications.

Preferred solutions:

1. **Structured JSON with one event per line**, with the stacktrace as a JSON-escaped string.
2. If text logs must be used, configure a **multiline parser** with event start/end rules matching the actual logging pattern.
3. Set line/byte limits and a flush timeout on the multiline buffer.
4. Test nested causes, suppressed exceptions, lines starting with fake timestamps, and CR/LF payloads.
5. Verify whether the parser corrupts Unicode or mixes two events under concurrency.

**There is no single multiline regex that works for every Java application.** Stack traces can pass through custom throwable formatting, async appenders, JSON encoders, and runtime wrappers, so test with real data.

**Log forging:** if a user can inject newlines and fake timestamp/level strings, a line-pattern parser may interpret part of that message as a separate event. Validate IDs, output-escape untrusted data, and prefer properly formatted NDJSON.

## 10. Java 17 example: simulating a host agent reading a file and delivering with ACKs

The following standalone example creates a temporary UTF-8 log file, reads it line by line, simulates a collector that **rejects the first send attempt of the second event**, retries, and updates a logical checkpoint after the ACK. It illustrates **how to reason about delivery**, not a production agent capable of tailing a growing file, network/TLS, or disk spooling.

Create **HostLogAgentDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public class HostLogAgentDemo {

    private static boolean collectorAck(String event, int attempt) {
        boolean transientFailure =
                event.contains("\"event\":\"retry\"") && attempt == 1;
        return !transientFailure;
    }

    public static void main(String[] args) throws Exception {
        Path source = Files.createTempFile("host-log-agent-", ".jsonl");
        try {
            Files.write(source, List.of(
                    "{\"event\":\"start\",\"requestId\":\"req-42\"}",
                    "{\"event\":\"retry\",\"requestId\":\"req-42\"}",
                    "{\"event\":\"finish\",\"requestId\":\"req-42\"}"),
                    StandardCharsets.UTF_8);

            List<String> events = Files.readAllLines(
                    source, StandardCharsets.UTF_8);
            int checkpoint = 0;
            int acknowledgments = 0;

            for (int index = 0; index < events.size(); index++) {
                String event = events.get(index);
                int attempt = 1;
                boolean acknowledged = false;

                while (!acknowledged && attempt <= 2) {
                    System.out.println("send line=" + (index + 1)
                            + " attempt=" + attempt);
                    acknowledged = collectorAck(event, attempt);
                    if (acknowledged) {
                        System.out.println("ack line=" + (index + 1));
                    } else {
                        System.out.println("retry line=" + (index + 1));
                        attempt++;
                    }
                }

                if (!acknowledged) {
                    throw new IllegalStateException(
                            "unacknowledged log event");
                }
                checkpoint = index + 1;
                acknowledgments++;
            }

            System.out.println("checkpoint=" + checkpoint
                    + " acknowledgments=" + acknowledgments);
        } finally {
            Files.deleteIfExists(source);
        }
    }
}
~~~

Compile and run on JDK 17 or newer:

~~~bash
javac HostLogAgentDemo.java
java HostLogAgentDemo
~~~

**Exact program stdout:**

~~~text
send line=1 attempt=1
ack line=1
send line=2 attempt=1
retry line=2
send line=2 attempt=2
ack line=2
send line=3 attempt=1
ack line=3
checkpoint=3 acknowledgments=3
~~~

Explanation:

- **Files.write / readAllLines** creates and reads three single-line JSON records using UTF-8.
- **collectorAck** is a method simulating confirmation from a collector; it does not send a real network request.
- The event named **retry** is rejected at `attempt=1`, so it is resent and acknowledged at `attempt=2`.
- **checkpoint** is incremented only after the logical ACK in the example; after three events, its value is 3.
- **acknowledgments=3** counts events acknowledged in the model, not proof of actual remote storage.
- The temporary file is deleted in `finally`; there are no background threads.
- This example **has no persistent checkpoint**, nor does it handle rename/copytruncate, partial lines, concurrent writers, partial batch ACKs, TLS transport, dead-lettering, clock skew, or crashes between send and ACK.
- In a real host agent, the checkpoint may represent a **byte offset** or journal cursor, while unacknowledged data may reside in a **filesystem-backed queue**. Do not use a line index in place of a byte offset when tailing UTF-8 in production.

**Takeaway:** reading a file once and sending once does not mean completion. You must verify acknowledged checkpoints, buffer state, and retry/restart behavior; even with proper ACKs, duplicates can still occur if a remote ACK is lost after the receiver has already persisted the data.

## 11. Example agent file-reading configuration: Fluent Bit

A **classic Fluent Bit** configuration can illustrate the placement of a tail input, state DB, filesystem storage, and output. This example is for a lab environment; plugin/option names, behavior, and security requirements must be checked against the **deployed Fluent Bit version**.

Illustrative configuration file:

~~~ini
[SERVICE]
    Flush              1
    Log_Level          info
    storage.path       /var/lib/fluent-bit/storage

[INPUT]
    Name               tail
    Path               /var/log/myapp/*.jsonl
    Tag                java.app
    DB                 /var/lib/fluent-bit/tail.db
    Read_from_Head     Off
    Refresh_Interval   5
    storage.type       filesystem

[OUTPUT]
    Name               forward
    Match              java.app
    Host               log-gateway.example.net
    Port               24224
    Retry_Limit        False
    tls                On
    tls.verify         On
~~~

Key concepts explained:

- **tail input** reads files matching the path; files must exist or be created by the Java service.
- **DB** stores tail state to support restarts; the volume containing the DB needs proper permissions and lifecycle management.
- **Read_from_Head Off** is a bootstrap decision: newly discovered files may not resend pre-existing history. Behavior also depends on the DB, plugin version, and configuration.
- **storage.type filesystem** allows the pipeline to use filesystem buffering according to engine/plugin policies, but requires capacity limits and understanding actual semantics.
- **forward output** sends to a gateway supporting the corresponding protocol; **tls On** and **tls.verify On** are only effective when the endpoint has a valid certificate and proper trust chain.
- **Retry_Limit False** indicates intent for unlimited retries per the plugin; it does not mean data cannot be lost if disk fills up, source files are deleted, or overload persists.
- **log-gateway.example.net** is an illustrative lab domain name, not a live service. Configuration must be replaced with an organization-managed endpoint and have connectivity verified.

Never place credentials or private keys directly in logs; if the agent needs a client certificate or token, manage it via a secret store and appropriate file permissions. The forward receiver/gateway configuration must also support the corresponding TLS/protocol; otherwise, the agent will fail to connect.

A production deployment also requires **memory/disk quotas, output timeouts, monitoring, file rotation behavior, service lifecycle, crash recovery, and retry limits**. Do not copy the configuration above into a real environment without testing those conditions.

## 12. Deploying an agent on a VM or bare metal

When running as a systemd service on Linux, define:

- A **dedicated user/group** with least-privilege permissions to read log sources.
- Agent write access to its own **state DB** and **spool directory**.
- State/spool located on an appropriate filesystem that does not vanish on restart if resuming is required.
- Service restart policies, rate limiting, and enough shutdown time to flush.
- Monitoring for file handle counts, CPU, memory, and disk.
- New file permissions after rotation so the agent does not lose read access.
- Collector connections using TLS, authentication, and valid retry configuration.
- Agent's own logs collected via a sensible route while avoiding **recursive ingestion**.

With systemd journald, the agent can read the journal instead of tailing text files if the plugin/agent supports it. In that case, the file offset is replaced by a journal cursor/state; check persistent journal configuration and journal read permissions. If journal rate limiting or drops occur before the agent reads, the agent cannot recover lines that were never saved.

**Do not run the agent as root just to bypass permission errors** when an ACL/group or narrower permission policy suffices. Unnecessary elevated privileges increase the blast radius of a buggy plugin or compromised host.

## 13. Kubernetes: DaemonSet, volumes, and metadata

In Kubernetes, a common pattern is a DaemonSet agent reading container logs on each node. Understand the path:

~~~text
Java container stdout/stderr
          |
          v
Container runtime creates node log
          |
          v
Node agent (DaemonSet)
          |
          v
Kubernetes metadata enrichment
          |
          v
Collector / storage
~~~

Items to verify:

- Node log paths/mounts match the runtime and cluster configuration.
- Pod/namespace/container metadata is attached from a trusted source; do not allow applications to spoof all fields.
- Duplicate collection of stdout and application log files is avoided.
- The agent runs on all nodes requiring observability, including nodes with different taints/tolerations.
- `hostPath`/RBAC/ServiceAccount permissions are restricted.
- If a pod is deleted, node container logs and state cursors are retained long enough to finish collection.
- Agent resource requests/limits do not cause frequent evictions.
- Kubelet/runtime rotation and log truncation are tested.
- Agent health checks and rollouts do not lose state or disrupt ingestion across all nodes simultaneously.

When strong isolation or per-workload custom log formats are needed, a sidecar may be appropriate; however, it increases process count, CPU/memory usage, and complexity. Avoid assuming "a sidecar is always more reliable than a DaemonSet."

## 14. Buffering, retries, and backpressure

In unstable network environments, agents typically use a memory buffer or filesystem-backed queue:

~~~text
Input throughput (logs/s)
        |
        v
Queue/backlog -------------------> Retry/batch output
        |                               |
        v                               v
Memory + disk quotas              Remote ACK/timeout
        |
        +--> warning / throttle / drop / pause input
~~~

**Backpressure** occurs when downstream cannot keep up, requiring the pipeline to throttle its rate or handle a full queue according to policy. Consequences may include:

- The agent pauses reading files while the source continues writing.
- The filesystem spool grows and may hit capacity.
- The memory queue fills up; plugins may block, drop, or back off depending on configuration.
- Collector timeouts and agent retries cause delayed or duplicate logs.
- Rotation deletes source files before the agent finishes reading them -> event loss.
- A full disk on a shared partition can prevent the **Java application from writing logs or data**, amplifying the incident.

A policy must answer:

1. What are the maximum bytes/records in memory and on disk?
2. When limits are exceeded, should the agent **pause input, block the app, drop newest, drop oldest**, or fail over to a backup route?
3. Which log levels/event classes are prioritized? Are there mandatory audit logs?
4. Are threshold alerts configured before the disk fills up?
5. When storage/network recovers, at what rate does the agent drain the queue, and will it overload the backend?
6. What does a backend ACK actually guarantee: request received, durable queue, or final storage?
7. Is the buffer encrypted and access-controlled if it contains PII/secrets?

**Never describe "infinite retry" as a guarantee against data loss.** If the disk runs out, a policy purges the spool, the node is terminated, or source rotation deletes the file, retries cannot recover vanished bytes.

## 15. At-most-once, at-least-once, and duplicate records

Design must cover not just network connection retries, but **end-to-end semantics**:

| Semantics | What can happen | How to handle |
| --- | --- | --- |
| Best effort / at-most-once | An event can be lost if transport fails | Use for non-mandatory diagnostic logs |
| At-least-once within supported bounds | Retries can cause an event to appear multiple times | Idempotent writes/dedup at the backend if needed |
| End-to-end exactly-once | Requires protocol/state and atomicity at every boundary | Do not assume from a tail DB or ACK |

Example failure window:

~~~text
Agent sends event E
      |
      v
Collector stores E
      |
      +--> ACK response lost
                |
                v
            Agent retries E
                |
                v
       Backend may see duplicate E
~~~

If deduplication is needed, choose an explicit event identifier (such as an `eventId` from the application, or a stable ID generated by the pipeline based on content/source and policy). Do not use a hash of the message text as a "unique ID" without considering two legitimate events with identical content.

**A log message is not a business message:** duplicates in an observability backend may not cause business side effects, but they inflate alert/metric counts if computed from log volume. Dashboards should account for counting and deduplicating when policy requires it.

## 16. Secure log transmission: transport and access control

A host agent runs close to source data and often has read access to many files/services. Apply the **least privilege** principle:

- Mount/read only the exact log paths; restrict access to home directories, secrets, and out-of-scope files.
- Ensure proper permissions on the state DB and spool—never world-readable.
- Use TLS/mTLS or appropriate authentication between the agent and gateway; verify certificates and never disable verification just to "make it work."
- Manage credentials in a secret store or tightly permissioned files; rotate periodically per policy.
- Redact/omit sensitive data **at the application** when possible; agent processors are defense-in-depth.
- Control metadata schemas/allowlists so the agent does not accidentally ship private headers, environment secrets, or full payloads.
- Protect against **log forging** and injection during parsing, especially with multiline text.
- Restrict dashboard/index read permissions and set appropriate retention.

**Do not rely on TLS to protect data already written to source files or spools.** TLS protects data in transit; files and state still require filesystem access controls, encryption at rest per policy, and retention controls.

**Do not treat `requestId`/`traceId` as secrets, nor assume they are harmless:** dynamic IDs can correlate user activity or expose infrastructure topology, so apply appropriate access control and retention.

## 17. Resources: CPU, memory, disk, and network

Agent capacity depends on:

- **Number of log sources**, tailed files, and scan frequency.
- **Event rate** and average size, especially with long stack traces.
- CPU for JSON/regex/multiline parsing and metadata enrichment.
- Buffer memory, disk spool, disk speed, and filesystem durability.
- Batching, compression, network RTT, bandwidth, and remote throttling.
- Number of output destinations and routing/replication policies.
- DEBUG/TRACE log levels of JVMs on the host.

An initial capacity estimate:

~~~text
raw_bytes_per_second ≈ events_per_second × average_encoded_event_bytes

spool_bytes_needed ≈ raw_bytes_per_second × outage_seconds
                     × overhead_factor
~~~

**overhead_factor** accounts for metadata/encoding, indices, batch framing, and retries; actual values must be measured. Some sources compress very well, while high-entropy JSON payloads compress poorly; do not treat a fixed compression ratio as a guarantee.

Illustrative calculation: with 2,000 events/s averaging 500 encoded bytes each, raw throughput is about 1,000,000 bytes/s (roughly 1 MB/s in decimal). A 10-minute network outage can accumulate around 600 MB of raw data, before overhead. **Actual results** depend on compression, queue configuration, and log bursts.

Set disk watermarks, timeouts, retry/backoff, and alerts **before** hard limits. If a single partition is shared between app data and the spool, be especially careful about disk-full cascades.

## 18. Agent health and metrics

A host agent must be monitored itself. Useful indicators:

| Metric or signal | Interpretation |
| --- | --- |
| `input_records_total` / `input_bytes_total` | How much source data is being read |
| `output_sent` / `output_acknowledged` | Sent/acknowledged per protocol |
| `output_errors` / `retries` | Destination errors or active retries |
| `buffer_queue_depth` / `buffer_bytes` | Remaining backlog |
| `buffer_dropped` / `discarded` | Data dropped per policy |
| `tail_files_open` / `watched` | Number of files currently tracked |
| `checkpoint_age` / `read_lag` | Whether state is progressing |
| `input_parse_errors` | Lines failing format/JSON/multiline parsing |
| `ingestion_delay` | Gap between event time and received time |
| `spool_disk_usage` | Queue size on disk |
| `last_successful_export` | Last time the destination confirmed success |
| `agent_restarts` | Crash loops or abnormal rollouts |

The metric names above are **illustrative concepts**, not standard names available in every agent. When deploying, choose metrics exposed by the actual product and version.

An alive agent does not mean it is collecting the right files: health checks should cover source readability, checkpoint progress, queue depth, output ACKs, and an end-to-end synthetic canary when possible.

Do not create an **infinite self-ingestion loop where the agent collects its own logs**. If the agent emits transport errors into the same source it is tailing, a network outage can continuously multiply log volume. Separate pipelines or filter tags and rate-limit agent diagnostics.

## 19. Investigation runbook when Java logs do not appear

When the application executes logger calls but the backend has no events:

1. **Check Java:** is the logger level/filter enabled? Which stdout/file and encoding is the event written to?
2. **Check the local source:** does the file exist; are permissions, symlinks, rotation, and stdout driver/journald retaining lines?
3. **Check the agent source:** do path/tag/input plugins match, is the state DB/cursor valid, and is the agent tailing the new file?
4. **Check the parser:** JSON parsing, multiline grouping, time parser, field limits; are records dropped or quarantined?
5. **Check the queue:** backlog, disk fullness, memory limits, input pauses, dropped records.
6. **Check the output:** DNS, TLS certificates, authentication, port, remote 429/5xx/throttling, retry rate.
7. **Check the collector:** is the receiver alive, are route/index/schema correct, is a filter dropping records, is the backend hitting a quota limit?
8. **Check search:** time range/timezone, service/env filters, retention, ingest delay, index alias.
9. **Reconcile:** compare record counts across input, spool, ACK, and backend within a defined time window.
10. **Explain state:** clearly note the last proven stage and where evidence is missing; do not claim "the application isn't logging" when the agent is reading the wrong path.

Common scenarios:

| Symptom | Possible cause | Verification |
| --- | --- | --- |
| Old logs resent after restart | Lost state DB/changed volume or different read-from-head | Compare DB/cursor policy and event IDs |
| New logs vanish after rotation | Agent tracks filename, not old inode/new file | Test rename/create and rotate wait |
| Stack trace lines split into multiple events | Missing or incorrect multiline parser | Inspect raw source and parser output |
| Backend receives logs minutes late | Queue backlog or remote throttling | Check buffer/ACK/ingestion delay |
| Only one service is missing logs | Different permissions, path, tag, or config | Compare service stdout/file and agent inputs |
| Host disk full | Unbounded spool or misbehaving log rotation | Check disk watermark and queue policy |
| Logs duplicated 2x | Collecting stdout + file or lost ACK retries | Check source config, event IDs, transport |
| ERROR logs present but missing `requestId` | MDC not set, encoder drops field, parse error | Check Java event and collector schema |
| Continuous TLS handshake failures | Trust chain/endpoint/protocol mismatch | Check agent error counters and cert config |
| Agent healthy but backend empty | Empty input path, wrong route, output filtered | End-to-end canary and per-stage metrics |

## 20. Pre-production testing

A minimum staging test suite:

| Case | What to prove |
| --- | --- |
| Java service emits valid NDJSON | Agent parser receives one event cleanly, Unicode intact |
| Multiline stack trace | Proper multiline grouping or JSON string escaping |
| Agent restart | No loss of unsent source data; duplicates within accepted semantics |
| Rename rotation | Old file read completely, new file tracked |
| Copytruncate | Understand and evaluate byte-loss risk, select suitable policy |
| Collector down 5-10 minutes | Spool stays within quota, retries, and drains after recovery |
| Queue/disk near full | Backpressure/pause/drop follows policy and triggers alerts |
| Backend ACK lost | Duplicates possible; idempotency/dedup works as required |
| File permission change | Agent reports clear error rather than silently skipping source |
| Container reschedule/node restart | Log persistence and source visibility match contract |
| Parser encounters CR/LF payload | Does not create forged events or break multiline |
| Data contains fake tokens | Redaction policy blocks before out-of-scope sinks |
| Expired TLS certificate | Export rejects insecure connection and alerts |
| Multiple Java services on same host | Tags/service/host metadata do not mix |
| Agent log self-ingestion | Does not multiply events infinitely |
| Application log burst | CPU/memory/spool stay within resource budget |

**Do not disable TLS verification or push real sensitive data for testing.** Use canary events without secrets, authorized environments, and test endpoints.

For **end-to-end** verification, emit a canary event with a stable `eventId`, timestamp, and clear service name, then verify the backend receives it within SLA. A test that only checks whether the agent process is running **does not prove** the collector stored the data.

## 21. Common configuration mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Logging only to file while agent reads stdout | Desired source is not collected | Standardize source path and runtime |
| Unintentionally collecting both file and stdout | Duplicates | Decide on a single source of truth |
| No state DB/checkpoint | Restarts re-read or skip history | Persistent state, test restore |
| Using copytruncate without evaluation | Risk of losing bytes during rotation | Prefer rename/create where suitable |
| Reading stack traces line by line | Wrong event counts and lost correlation | NDJSON or multiline parser |
| Infinite retries without disk quota | Full disk impacting the app | Buffer limits, alerts, overflow policy |
| Placing spool next to business data unbounded | Cascading disk-full failure | Separate capacity/quotas and watermarks |
| Unauthenticated output config | Blocked connections or data leaks | Appropriate TLS/mTLS/auth |
| Looking only at tail offset | Confusing source read with successful delivery | Measure buffer, ACK, backend ingestion |
| Using message text as ID/dedup key | Undercounting or misclassifying legitimate repeats | Stable `eventId` and clear semantics |
| Generic regex to redact payloads | Can miss secrets | Minimize at Java source, field allowlist |
| Running agent as root unnecessarily | Expanded blast radius | Least privilege and file ACLs |
| Not monitoring agent log drops | Missing evidence with nobody noticing | Metrics, canaries, and runbooks |

## 22. Adoption checklist

| Item | Criteria |
| --- | --- |
| Architecture | Clear app/logger, host agent, gateway, backend |
| Sources | No duplicate stdout/file/journal, agent reads right paths |
| Schema | Clear JSON/text encoding, event time, and metadata |
| Cursor | State DB/offset/cursor persisted, restart tested |
| Rotation | Rename/copytruncate, inode identity, archive retention |
| Multiline | Java `Throwable`/stack traces framed accurately |
| Delivery | ACK/buffer/retry semantics documented |
| Disk/queue | Quotas, backpressure/overflow policy, and alerts |
| TLS/auth | Certificate verification enabled, credentials protected |
| Access control | Agent has least privilege, spool is not public |
| Privacy | No raw tokens/PII emitted; log forging prevented |
| Health | Queue, retries, parse/drop rates, agent restarts monitored |
| Reliability | Outage/restart/rotation/lost ACK tested |
| Validation | End-to-end canary and source-to-backend reconciliation |
| Operations | Runbook pinpoints breakages and recovery conditions |

**Conclusion:** a host agent is the **log collection and transport** layer between the Java logging provider and the backend. Making a pipeline reliable requires more than configuring a file tail path: you must understand **source framing, file identity/rotation, offsets/cursors, filesystem buffers, ACK/retry, backpressure, TLS, privacy, and observability of the agent itself**. With a verifiable architecture, operators know whether logs are still being produced in the JVM, waiting in the agent, or have reached the backend—and know when they only have an assumption rather than proof.