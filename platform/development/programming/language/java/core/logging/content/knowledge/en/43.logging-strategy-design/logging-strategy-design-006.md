# Choosing Log Destinations in Java Logging Strategy Design

## 1. What Is a Log Destination and Why Design It?

In Java, calling `logger.info(...)` creates a **log event**. Whether that event is actually useful depends on where it is routed: a terminal, container stdout/stderr, a file, syslog/journald, a log collector, a centralized search platform, or a high-durability audit store.

**Choosing a log destination** means deciding how to **emit, transport, retain, and retrieve** a log type according to its purpose and operational constraints. This is an architectural decision, not just a `target=System.out` parameter. A misconfiguration can cause logs to:
- Not appear in `kubectl logs` because Java writes to a separate file.
- Be lost when a container restarts or a file rotates too quickly.
- Be duplicated due to logger additivity or two agents reading the same source.
- Slow down requests when an appender writes synchronously to a remote service.
- Expose sensitive information in stdout, files, dashboards, alerts, or exports.
- Be present in the console but never reach the query system.
- Lack sufficient durability to serve as audit evidence.

**Core idea:** there is no single optimal destination for every case. Microservice diagnostic logs, security events, and mandatory audit events may require different paths and guarantee levels.

### Learning Objectives

After this lesson, you will be able to:
1. Distinguish between logging API, logger, appender/handler, formatter, stream, collector, and backend.
2. Evaluate stdout, stderr, file, rolling file, syslog, remote transport, and central logging.
3. Choose a strategy for a JVM on a developer machine, VM, Docker/Kubernetes, batch jobs, and systems requiring audit.
4. Understand trade-offs around buffering, blocking, async queues, rotation, retry, loss, and duplication.
5. Write a **standalone Java 17** program that emits operational events to stdout and security events to a temporary file.
6. Read Logback/Log4j 2 configurations, design routing rules, and test end-to-end.

## 2. Distinguishing the Layers of the Log Path

A typical flow:

```text
Java business code
        |
        v
SLF4J / JUL / Log4j API
        |
        v
Logger + level + filter + context
        |
        v
Handler / Appender / Encoder
        |
        +--------------+-----------------+
        |              |                 |
        v              v                 v
stdout/stderr     Rolling file     Network transport
        |              |                 |
        v              v                 |
Container runtime  File tail agent       |
        |              |                 |
        +--------------+-----------------+
                       |
                  Collector
                       |
               Buffer / Retry / TLS
                       |
                       v
                Central backend
                       |
              Search / Alert / Archive
```

| Component | Responsibility | Examples |
| --- | --- | --- |
| **Logging facade/API** | Interface used by application code | SLF4J, `java.util.logging` |
| **Logger** | Logger name, log level, filters, event propagation | `com.example.orders` |
| **Appender/Handler** | Emits events to one or more destinations | Logback ConsoleAppender, JUL FileHandler |
| **Encoder/Formatter** | Formats an event into text/JSON | Pattern encoder, structured JSON |
| **Direct destination** | Where the JVM writes bytes | stdout, stderr, file, socket, HTTP |
| **Collector/Agent** | Receives, parses, enriches, buffers, and ships | Node agent or intermediate service |
| **Backend** | Stores/indexes/queries/applies retention | Log search service, archive |
| **Audit store** | Stores mandatory evidence under a dedicated contract | Transactional table, outbox, protected append-only store |

**The direct destination is not the final storage destination.** A ConsoleAppender sends to stdout; the container runtime writes to the node; the collector then ships to the backend. When `logger.info` returns, it does not prove that the backend has indexed the record.

### 2.1. An Event Can Be Sent to Multiple Destinations

An event in the same JVM can be fanned out to both stdout and a rolling file. If the collector gathers **both copies**, a single business operation may appear to have generated two events. That is a **duplicate ingestion** issue, not proof that the business logic executed twice. Before fanning out, you must know the purpose of each destination and whether collection paths overlap.

### 2.2. Log Level Does Not Equal Destination

`ERROR` does not default to stderr, and `INFO` does not necessarily go to stdout. Log levels are determined by the framework; stdout/stderr are data streams. Alert severity is yet another decision, based on impact and alerting policy. Do not treat the stream or the number of ERROR lines as an absolute proxy for system health.

## 3. Questions to Answer Before Choosing a Destination

| Question | Impact on the Decision |
| --- | --- |
| Is the log for debugging, operations, security, or mandatory audit? | Durability, access permissions, and provability |
| Is losing 1% of INFO logs acceptable? | Best-effort vs durable pipeline |
| If the sink is down for 10 minutes, can business operations continue? | Drop, buffer, block, or fail closed |
| What are the peak throughput and record size? | Queue, file size, network, CPU, and disk |
| Who needs to read/query it and for how long? | Centralization, IAM, retention, archive |
| Does the data contain PII or security-sensitive fields? | Classification, encryption, masking, access audit |
| Running on a laptop, VM, Docker, or Kubernetes? | Console vs file, filesystem lifecycle |
| Can an event be duplicated due to retries/collector? | Event ID, idempotent ingestion, and count semantics |
| Need to search across multiple services? | Correlation ID, collector, structured schema |
| Is there a storage/indexing/egress budget? | Sampling, retention, aggregation, and event size |
| Who owns pipeline failures? | Monitoring, runbook, alerts, and rollback |
| Can the vendor be swapped without changing business code? | Facade/backend separation, collector |

**Do not use a blanket rule like “all logs go to file X” when different log types have different obligations.** At the same time, do not build dozens of destinations when a single simple pipeline can satisfy the requirements.

## 4. Comparing Common Destinations

| Destination | Pros | Risks/Limitations | Best-Fit Use Cases |
| --- | --- | --- | --- |
| **stdout** | Simple, container-friendly, no application-managed files | Pipe can block; runtime/agent can drop/rotate | Containerized applications, CLI |
| **stderr** | Separates diagnostics/errors in supporting tools | Does not trigger alerts by itself; stdout/stderr interleaving order is not guaranteed | CLI, dual-stream policies |
| **Rolling file** | Local file available, easy for an agent to tail | Rotation/disk/permission management, ephemeral containers | JVM on VM, legacy systems |
| **Syslog/journald** | Uses host logging service | Depends on OS config, queue, retention, permissions | VM/host-centric deployments |
| **Network appender** | Sends directly to collector/remote endpoint | TLS, timeout, retry, queue, and network coupling | Controlled integrations |
| **Central collector** | Standardizes format/metadata, batches/retries, easy backend swap | Can duplicate, drop, or lag; not exactly-once by default | Microservices, multi-node |
| **Database audit/outbox** | Can tie audit row to business transaction | Increases storage/writes, requires schema and replay | High-durability audits |
| **Protected audit storage** | Integrity protection mechanisms, independent permissions | Depends on service contract, cost | Compliance/security audit |

**There is no “absolute guarantee” column.** Every solution must be configured, operated, and tested against concrete requirements. For example, stdout may suffice for diagnostics, but it has no transactional atomicity with the business database.

## 5. JVM stdout and stderr

In Java:
- `System.out` is standard output.
- `System.err` is standard error.
- JUL `ConsoleHandler` writes to **System.err** by default.
- Logback `ConsoleAppender` lets you choose `System.out` or `System.err`.
- Log4j 2 `Console` has targets `SYSTEM_OUT` and `SYSTEM_ERR`.
- SLF4J is a **facade**: the actual destination depends on the backend/provider and configuration.

Some collector platforms attach `stream=stdout` or `stream=stderr` metadata. However, do not assume:
- stderr is retained longer than stdout;
- a `logger.error` on stderr means on-call has been paged;
- timestamps/ordering across the two streams always match execution order in code;
- writing bytes to stdout means the backend has stored them;
- one physical line means one event was parsed successfully.

### 5.1. Choosing Console in Containers

For a Java service running on Docker/Kubernetes, a common setup is:

```text
SLF4J + Logback
        |
Structured JSON ConsoleAppender
        |
stdout / stderr
        |
Docker/CRI runtime
        |
Node log files
        |
DaemonSet/collector
        |
Centralized backend
```

Pros: reduces file management inside the container, the platform can attach Pod/container/namespace metadata, and you can query centrally after a container is replaced. Still, you must account for kubelet rotation, collector checkpoints, ingest lag, and backend retention. `kubectl logs` is not a long-term archive.

### 5.2. When Does Writing to a File in a Container Lose Logs?

If Java writes to `/var/log/app/app.log` while the infrastructure only collects stdout/stderr, `kubectl logs` will not see those logs. When a container is replaced, its ephemeral filesystem disappears. If you want to use a file, you must have a volume/persistence, a file-tailing agent, rotation, and clear ownership.

## 6. Rolling Files on VMs and Legacy Systems

Files remain a valid choice when VMs/bare-metal hosts have a standardized file collector or an application requires a specific file path. Before using them, verify:

1. **Permissions:** directory/files readable/writable only by required principals, not world-readable if containing internal data.
2. **Rotation:** by size/time, number of retained files, rename handling, and compression.
3. **Disk quota:** a log storm must not fill the partition hosting the OS or database.
4. **Concurrency:** do not let multiple JVM processes overwrite/rotate the same file if the handler does not support it.
5. **Checkpoint:** how does the agent track the file across rename/truncate/inode changes?
6. **Retention:** local files are kept long enough for the agent to ship and to support short-term incident triage.
7. **Storage security:** encryption, backups/snapshots, export permissions, and legal hold if needed.
8. **Write errors:** if a file cannot be opened, what status does the appender report? Is there a dedicated metric/alert?
9. **Shutdown:** are buffered events flushed within a reasonable grace period?
10. **Collection path:** is the same event also printed to stdout for another collector to pick up?

**Local rotation is not backend retention.** Deleting a file after 7 days does not delete records already indexed in the log service, snapshots, backups, or exports. Conversely, 30-day backend retention cannot recover bytes that the agent never read before the file was deleted.

### 6.1. Do Not Turn File Paths Into an Access Control Mechanism

Naming a file `security.log` does not prevent anyone with read access to the node, volume, backup, or container root from reading it. Classification must be enforced across the appender, file/volume, node, collector, and backend. If production log read access is highly sensitive, an appropriate infrastructure model is required.

## 7. Direct Network Logging: Choose Only When You Understand the Failure Modes

A remote appender can send over HTTP/gRPC/TCP/UDP or a proprietary protocol. The advantage is that the JVM needs no local file and can send directly to the collection service. However, it adds network dependency to the logging execution path.

Risks include:
- Backend returns 429/503 or times out.
- DNS, TLS, certificate, or authentication failures.
- Appender buffer/queue grows and fills up.
- Retries after a lost ACK cause duplicates.
- Synchronous network path blocks request threads.
- Java process crashes before queued bytes leave the process.
- Credentials hardcoded in source/image with overly broad read/export permissions.
- Appender shuts down before flushing completes.
- Changing the backend forces every microservice to update dependencies/configs.

**Define behavior when the sink is unavailable**:
- Diagnostic INFO/DEBUG: typically prioritize not causing an outage, using a bounded buffer and drop telemetry.
- Security detection events: evaluate non-loss requirements, especially during an active incident.
- Mandatory audit: may require durable writes before business commit or fail-closed semantics per contract.
- An order-creation request should not fail just because a DEBUG event could not be sent, unless a mandatory requirement specifies otherwise.

### 7.1. TLS and Ingest Permissions

A collector/remote endpoint should require source authentication, appropriate TLS/mTLS, and write-only permissions scoped per index/tenant. Do not allow client input to control the remote log destination; otherwise, misconfiguration could lead to exfiltration or SSRF. When credentials expire, rotation and dedicated error reporting are needed without printing raw tokens into logs.

## 8. Collectors and Centralized Backends

A collector does more than forward bytes:
- Reads node container logs, files, or journal.
- Parses Docker/CRI envelopes containing timestamp/stream/partial markers.
- Reassembles partial/multiline records when needed.
- Parses application JSON or patterned text.
- Enriches with Pod, namespace, service, environment, and deployment metadata.
- Filters/limits size and performs additional policy-based redaction.
- Batches, spools, retries with backoff, and ships over secure transport.
- Emits metrics on parse failures, queue depth, dropped/exported records, and ingest lag.

**Strategic benefit:** changing the log backend does not necessarily require modifying all Java code; applications simply emit events with a stable schema.

**Limitations:** agents can also lose checkpoints, crash, hit quotas, miss rotated files, or create duplicates on retry. Duplicate documents in a backend do not prove Java executed twice.

### 8.1. Fan-out and Duplicate Ingestion

A single request can produce three different log events, all sharing one `request_id`. Therefore, **do not use request ID as the sole deduplication key**. If deduplication is needed in the collector, use a log event instance identity or contract-based idempotent ingestion. Also check whether two agents are reading the same `/var/log/containers` or whether the same event is shipped from both stdout and a file.

### 8.2. Multiple Time Sources

Timestamp fields may include:
- `event_time`: when the JVM created the event.
- `container_time`: when the runtime recorded stdout/stderr.
- `ingest_time`: when the backend received/indexed the record.

Late-arriving data due to retries or buffering can make dashboard order differ from business order. Use correlation/trace IDs and business event IDs when needed; do not infer that a request committed just because one log has an earlier timestamp than another.

## 9. Choosing Format Alongside Destination

A destination may accept plain text, JSON, or a structured protocol. For centralized systems, **one JSON object per physical line** is usually easy to parse and query.

Illustrative event example:

```json
{"timestamp":"2026-11-10T03:00:00Z","level":"INFO","service":"orders-api","event":"order_created","request_id":"req-42","result":"SUCCESS"}
```

A good schema typically includes timestamp, severity, service/env, event code, error code when applicable, resource type, route template, duration, correlation/trace ID, outcome, and schema version. Do not put high-cardinality user IDs or request IDs into **metric labels**.

**A JSON encoder does not automatically mask sensitive data.** If a payload contains a password and the encoder produces valid JSON, the password is still exposed. Use an allowlist of fields at the Java call site and inspect exception messages/causes, MDC/ThreadContext, and HTTP payload logging.

### 9.1. Multiline Exceptions and Partial Fragments

Java stack traces span multiple lines. If a collector treats each line as an independent record, a single exception can turn into dozens of contextless events. Two common design approaches:
- Single-line JSON: the stack trace is escaped as `\n` inside a field; a proper encoder ensures valid JSON escaping.
- Multiline text: the collector is configured with a start-of-record rule to stitch stack frames from the right container/stream source.

Even with single-line JSON, the runtime may split oversized records into **partial fragments**. The collector must understand the corresponding CRI/Docker format to avoid merging fragments from two different containers.

Do not log raw request bodies or full binary uploads just to “have enough data”; that increases cost and leakage risk.

## 10. Java 17 Demo: Writing Operational Events to stdout and Security Events to a File

This **standalone JDK 17** example uses no Maven/Gradle and relies on JUL `java.util.logging`. It intentionally routes two event types:
- Operational logs to stdout via a small `Handler`.
- Illustrative security events to a temporary file via JUL `FileHandler`.
- After flushing the file, the program reads back an event and prints verification info.

This is only a **routing model**. A temporary file is not a durable or immutable audit store, nor is it transactionally tied to business operations. The program does not simulate a container runtime or network collector.

Create `LogDestinationDemo.java`:

```java
import java.io.IOException;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LogDestinationDemo {
    private static final class LineFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            return record.getLevel().getName()
                    + " " + record.getMessage() + "\n";
        }
    }

    private static final class StdoutHandler extends Handler {
        private final PrintStream out;

        StdoutHandler(PrintStream out) {
            this.out = out;
            setLevel(Level.ALL);
        }

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                out.println("STDOUT " + record.getLevel().getName()
                        + " " + record.getMessage());
            }
        }

        @Override
        public void flush() {
            out.flush();
        }

        @Override
        public void close() {
            flush(); // Do not close System.out.
        }
    }

    public static void main(String[] args) throws IOException {
        String fakeSecret = "fake-password-not-real";
        Path file = Files.createTempFile("java-log-route-", ".log");

        Logger operations =
                Logger.getLogger("lesson.destination.operations");
        Logger security =
                Logger.getLogger("lesson.destination.security");

        operations.setUseParentHandlers(false);
        security.setUseParentHandlers(false);
        operations.setLevel(Level.ALL);
        security.setLevel(Level.ALL);

        Handler console = new StdoutHandler(System.out);
        operations.addHandler(console);

        FileHandler fileHandler = null;
        try {
            fileHandler = new FileHandler(file.toString(), true);
            fileHandler.setFormatter(new LineFormatter());
            fileHandler.setLevel(Level.ALL);
            security.addHandler(fileHandler);

            operations.info("event=request_completed"
                    + " route=/orders status=200 requestId=req-42");
            security.warning("event=access_denied"
                    + " actor=anonymous resource=doc-9");

            fileHandler.flush();
            String stored = Files.readString(file, StandardCharsets.UTF_8)
                    .strip();
            System.out.println("FILE " + stored);
            System.out.println("secretInFile="
                    + stored.contains(fakeSecret));
        } finally {
            operations.removeHandler(console);
            console.close();
            if (fileHandler != null) {
                security.removeHandler(fileHandler);
                fileHandler.close();
            }
            Files.deleteIfExists(file);
        }
    }
}
```

Compile and run in an environment that allows creating temporary files:

```bash
javac LogDestinationDemo.java
java LogDestinationDemo
```

**Exact stdout**, on a fresh JVM when the temporary file is created and written normally:

```text
STDOUT INFO event=request_completed route=/orders status=200 requestId=req-42
FILE WARNING event=access_denied actor=anonymous resource=doc-9
secretInFile=false
```

**Stderr:** the program does not intentionally write anything to stderr.

### 10.1. How It Works

1. `operations` and `security` are two distinct loggers. They have separate handlers, so routing does not require level-based filtering.
2. `setUseParentHandlers(false)` prevents propagation to JUL parent/root handlers, which typically stops a duplicate record from going to stderr.
3. `StdoutHandler` prints one operational line without dynamic timestamps, keeping output deterministic.
4. `FileHandler` uses `LineFormatter` to write level/message to the temporary file. `flush()` ensures bytes are flushed at the stream handler layer before reading in the demo; it does not prove durability across power loss.
5. `FILE ...` is **a line printed by the program after reading the file**, not the security logger sending its event to stdout.
6. `fakeSecret` exists only in RAM; it is never placed into an event. `secretInFile=false` checks the temporary file, which does not prove the entire production pipeline never logs secrets.
7. `finally` closes the handlers and deletes the file to avoid leaving demo data behind; it does not close the JVM's `System.out`.

### 10.2. What the Demo Does Not Prove

- No transactional durability or append-only audit guarantees.
- No concurrency control for multiple writers to the same file.
- No rotation, quota, retention, encryption, IAM, collector, or remote transport.
- The custom handler is not a logging backend designed for multithreaded workloads.
- If the process is killed before `finally`, the file may remain.
- It can fail if the host disallows creating/writing temporary files; that is an environmental condition with no standard stdout on failure.
- It does not escape control characters in messages; production needs a proper encoder/validator.

## 11. Logback: Configuring Destinations via Appenders

For an application using **SLF4J + Logback**, `logback.xml` can route operational logs to stdout and a dedicated logger group to a file if the platform has an appropriate file-tailing agent.

```xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level service=orders %logger{36} %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="SECURITY_FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>/var/log/app/security.log</file>
        <rollingPolicy
              class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>/var/log/app/security.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
            <maxHistory>7</maxHistory>
        </rollingPolicy>
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.security.audit"
            level="INFO" additivity="false">
        <appender-ref ref="SECURITY_FILE"/>
    </logger>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

This is an **illustrative integration configuration**, not a recommendation to use files for mandatory audits. It requires the right Logback version, writable directories, rotation/volume/collector/retention setup, and appropriate read permissions.

- The root logger uses `STDOUT`; container infrastructure collects logs via the console pipeline.
- Logger `com.example.security.audit` goes to `SECURITY_FILE` and sets `additivity="false"` so it does not forward to root stdout.
- If `additivity="false"` is omitted, a security event can go to both the file and stdout, causing **duplicate ingestion or leaking a restricted event into the standard pipeline**.
- If the platform only collects stdout, the security file will **not be shipped** without a file agent.
- `maxHistory` only controls local rolling file history per policy; it does not govern backend retention.
- The `%msg` pattern can still carry newlines or secrets; data minimization and safe structured encoding are still required.

A pure container application may **use only a single JSON ConsoleAppender**, and let the collector route by verified source/metadata/classification. That reduces file management, but you must verify that readers of the standard index cannot see restricted records.

### 11.1. SLF4J Does Not Decide the Sink

In business code:

```java
// Integration snippet; requires SLF4J and a corresponding backend.
logger.info("event=order_created orderId={} status={}",
        safeOrderId, "CREATED");
```

`logger.info` does not reveal whether Logback or Log4j 2 is used, or whether it goes to a file or stdout. That is the strength of the facade: backends and routing can change per environment. However, `{}` does not mask data automatically; `safeOrderId` must be chosen and validated according to policy.

### 11.2. Log4j 2 Console Appender

```xml
<Configuration status="WARN">
  <Appenders>
    <Console name="Stdout" target="SYSTEM_OUT">
      <PatternLayout pattern="%d{ISO8601} %-5level %c - %msg%n"/>
    </Console>
  </Appenders>
  <Loggers>
    <Root level="info">
      <AppenderRef ref="Stdout"/>
    </Root>
  </Loggers>
</Configuration>
```

This is an illustrative **Log4j 2** configuration, not standalone like the Java demo. `SYSTEM_OUT` is stdout, not a guarantee of JSON, TLS, centralization, or persistence. When adding appenders, review filters, additivity, and duplicate routing.

### 11.3. JUL ConsoleHandler Defaults to stderr

```properties
handlers=java.util.logging.ConsoleHandler
.level=INFO
java.util.logging.ConsoleHandler.level=INFO
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
```

This `logging.properties` snippet only configures JUL to output to the console using the default ConsoleHandler; **it does not force stdout**. If the collector only reads stdout, you must replace the handler or change the pipeline; do not guess based on the word “Console”.

## 12. AsyncAppender, File Buffers, and Network Backpressure

Every layer can drop or buffer an event at some point:

```text
Caller thread
    |
    | logger level/filter
    v
Async queue (optional) ----> queue overflow: block/drop/reject
    |
    v
Encoder/handler
    |
    | file/pipe/socket write
    v
Container runtime / file agent
    |
    | rotation, checkpoint, retry
    v
Collector
    |
    | batch, TLS, quota, backoff
    v
Backend indexed / retained record
```

**Do not conflate these milestones:**
- **Accepted:** the event enters the logging layer.
- **Emitted:** bytes are written to stdout/file/socket per the appender's contract.
- **Collected:** the agent has received/read them.
- **Exported:** the collector sent them over transport with some acknowledgement.
- **Indexed:** the backend stored and made them queryable.
- **Retained:** the log persists for the policy-required duration.

An appender returning does not prove `Indexed`. A collector receiving an ACK is not equivalent to an audit transaction.

### 12.1. Blocking vs Non-Blocking

**Synchronous:** easier to reason about, but slow network/file/stdout can drag down business threads. **Asynchronous:** reduces caller-thread latency under normal conditions, but queues have finite size, limits, and overflow policies; a crash before flush can lose events.

Parameters to review:
- Queue capacity and enqueue timeout.
- Block/drop/reject behavior when full.
- Worker threads and batch flush interval.
- Shutdown grace period and drain capability.
- Local buffer/spool retention and quota.
- Dropped event count and exporter retries.
- Concurrency and ordering across multiple streams.

Do not assume “async enabled = never blocks” or “writing to a file = never loses logs.” Check the exact backend/version configuration.

### 12.2. Late Data and Duplicates

A collector may successfully send a batch but lose the ACK response; retrying causes the backend to index it twice. Dual collection from stdout and a file can also occur. To count business operations accurately, use metrics or business events with clear semantics and identity rather than raw log document counts.

### 12.3. Failures of the Pipeline Itself

When an appender/collector fails, do not call `logger.error` through the same broken appender to describe the failure (it may recurse or fail to emit). Use an independent internal status logger or health metrics, plus alerts for queue depth, drops, ingest lag, and no-data checks.

## 13. Mandatory Audits May Need Storage Beyond stdout/File

An event such as “an administrator changed user permissions” may require:
- Actor, action, resource, actual outcome, `occurred_at`, and event ID.
- Records that cannot be deleted or altered arbitrarily.
- Separate retrieval paths and read/export permissions.
- Proof that the business change and the audit record **committed together**.
- Retention, legal hold, and lookup capabilities per requirements.

One strategy uses an **outbox in the same transaction**:

```text
BEGIN TRANSACTION
  update business state
  insert audit/outbox event with unique event_id
COMMIT
   |
   v
Reliable publisher / retry
   |
   v
Protected audit store / downstream index
```

Limitations:
- If both the business update and audit insert belong to **the same database transaction**, both commit or roll back together.
- Publishing from the outbox after commit can send duplicates on retry; downstream must support idempotency/deduplication.
- Side effects outside the transaction (emails, third-party APIs) need separate idempotency keys or reconciliation.
- A stdout write or `FileHandler.flush()` **does not guarantee atomicity with a database commit**.
- Kafka, syslog, or an HTTP appender does not become an immutable audit ledger simply by being configured for higher durability.
- Depending on requirements, append-only/WORM storage, signing, IAM, key management, and access auditing may be needed.

Do not blindly sample mandatory audit events to reduce log volume. At the same time, do not log raw payloads just because it is an audit; the event schema should select only the required fields.

## 14. Security and Retention by Destination

An event can exist in:
- Process stdout/stderr and node container files.
- Local rolling files, volumes, and backups.
- Collector queues/buffers or local spools.
- Central indexes, object storage archives, and snapshots.
- Dashboards, CSV/ZIP exports, alerts, email/chat, or incident tickets.

That is why **dashboard read permissions are not the entirety of log security**. You must evaluate ingest, read, export, delete, configure, retention, and archive IAM separately.

### 14.1. Log the Right Data from Java

Do not log passwords, refresh/access tokens, API keys, private keys, session cookies, raw Authorization headers, bodies, or SQL bind values. Use event codes, route templates, statuses, validated IDs, and error categories.

An event can be valid structured JSON and still leak a secret if it contains a raw DTO. Redaction in collectors/dashboards is only a defense-in-depth layer; the original may already have been written to stdout/files earlier.

### 14.2. Access Control Across the Log Path

- Collectors should have **ingest-only** access to the target destination, not system-wide read/export.
- On-call engineers should only read datasets within their service/team/incident scope.
- Exports require separate permissions and auditing because data leaves the backend.
- Anyone who can modify pipeline configuration can indirectly redirect logs elsewhere; require change control and auditing.
- Backups/object storage require managed IAM and encryption keys.
- Retention must be defined for local files, central backends, archives, and exported files.

If a credential is exposed in production logs, stop further emission, identify all copies/sinks, revoke or rotate the credential per policy, and review read access and incident procedures.

## 15. Cost: A Cheap Destination in Code Can Be Expensive in Operations

Illustrative example: at 1 KiB per event and 1,000 events/s, the application produces roughly 1 MiB/s **before compression, indexing, and replicas**. Running continuously, daily raw volume is very large, and backend indexes and metadata can multiply actual storage further.

Cost drivers:
1. CPU/GC for formatting messages and stack traces.
2. Heap for queues, serialization, and object snapshots.
3. Disk for rolling files, node logs, and spools.
4. Network egress/transport and TLS.
5. Ingest/indexing/search and hot/cold storage.
6. Alert fatigue, false positives, and pipeline maintenance effort.

Reduce cost at the right layer:
- Do not log raw request/response bodies.
- Use a compact event schema and stable error codes.
- Log stack traces only at appropriate boundaries; avoid logging the same exception three times.
- Move aggregates such as error counts, latency, and queue depth into **metrics** instead of dumping every object.
- Apply controlled sampling for DEBUG/TRACE; keep required audits intact.
- Choose different retention periods by classification and purpose.

**Do not turn cost control into silent loss**: if drops or sampling occur, make them visible with metrics; mandatory evidence must have a dedicated path.

## 16. Selection Matrix by Scenario

| Scenario | Reasonable Starting Destination | Must Verify |
| --- | --- | --- |
| Learning Java CLI | stdout/stderr via logger | Level, output, secret-free |
| Spring Boot container | Structured stdout → runtime → collector | Parsing, rotation, metadata, loss |
| Legacy JVM on VM | Rolling file → agent | Disk quota, rotation, checkpoint |
| Batch/CI job | Console + archive when needed | Execution ID, retention, flush |
| High-traffic debugging | Filters or sampling, bounded pipeline | No PII exposure, volume budget |
| Error diagnostics | Primary appender + central backend | Correlation, exception formatting, dedup |
| Security investigation | Restricted dataset with access audit | MFA/JIT/export restrictions |
| Mandatory admin/payment audit | Transactional outbox/protected store | Atomicity, idempotency, integrity |
| Edge/offline workload | Bounded local encrypted spool + retry | Overflow policy, storage durability |
| SLO alerting | Metrics/SLI + alert manager; logs aid investigation | No-data, routing, runbook |

Each row is a **starting suggestion**, not a rigid mandate. If a container has critical audits yet still sends them via stdout, document why that best-effort level does or **does not meet** the contract.

## 17. Investigating When Logs Do Not Reach Their Destination

**Step 1 — Did Java create the event?** Check code paths, levels, logger names, filters, providers, exception paths, and actual logging configuration. For JUL, check default ConsoleHandler going to stderr; for Logback, check root/child appenders and additivity.

**Step 2 — Are bytes at the direct destination?** Check stdout/stderr, file path, write permissions, disk/full quota, process entrypoint, appender errors, and async queue drops.

**Step 3 — Did the runtime/agent read them?** In containers, use `docker logs`/`kubectl logs` within granted permissions. For files, check whether the agent tails the right path, rotation, and checkpoints. Avoid using these tools as proof of centralization.

**Step 4 — Did the collector ship them?** Check parse failures, multiline/partial handling, filters, TLS, retries, backlog, quota, agent restarts, and accepted/dropped/exported metrics.

**Step 5 — Does the backend display them?** Check index/tenant, time range, event time vs ingest time, query labels, mappings, retention, and read permissions.

**Step 6 — Are there duplicates?** Compare logger invocations against stdout/file and backend record counts. If Java emitted one record and the backend has two, suspect collector/fan-out/retry. If Java logged twice, suspect additivity or duplicated instrumentation.

**Do not enable TRACE across all of production** just because logs are missing. Use a synthetic canary event, trace it through each hop, and pinpoint where it is lost.

## 18. End-to-End Design Testing

| Test | Expectation |
| --- | --- |
| Emit an INFO event | Correct destination, schema, and record count |
| Emit ERROR with Throwable | Has code/context; stack trace parses cleanly and leaks no secrets |
| Child/root logger | No unintended double emission |
| stdout + file fan-out | No policy-violating double ingestion |
| Collector network loss | Bounded retry/drop/block as designed |
| Async appender queue full | Expected metrics and latency/drop behavior |
| File rotation | Agent checkpoints properly without silent loss |
| Container restart | Backend retains history per its own retention |
| CRI partial/multiline | One event is not counted as multiple unrelated records |
| Backend returns quota/429 | Recovery or failure policy verified |
| Shutdown/SIGTERM | Drains within grace period; SIGKILL limits understood |
| Fake secret in request | Absent from stdout, file, collector, index, and notifications |
| Audit outbox after DB commit | Event exists per transactional contract |
| Viewer on restricted dataset | Backend blocks unauthorized access |
| No-data collector | Health/synthetic/telemetry alert triggers |
| Query after retry lag | Timestamp and ordering semantics are clear |

A staging procedure:
1. Finalize the schema and actual destination for each log type.
2. Emit `event=log_pipeline_test` with a fake correlation ID.
3. Count logs at JVM stdout/file, then check the runtime.
4. Query the collector/backend by time window and service.
5. Test network failures, rotation, restarts, and JSON/multiline parsing in the test environment.
6. Measure CPU, memory, latency, queue depth, disk, and dropped records.
7. Run negative authorization tests on export/search APIs.
8. Document the pipeline diagram, owner, and runbook.

Do not cause production outages or use real credentials for testing.

## 19. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `System.out.println` instead of a logger everywhere | Missing levels, schema, context | Logging framework + appender |
| Assuming JUL ConsoleHandler writes to stdout | Collector ignores stderr | Verify stream/config |
| Writing to a file in a container without shipping | Logs vanish when the pod is replaced | Console or file agent + volume |
| Rolling file without rotation | Disk fills up | Quota/max history/monitoring |
| Rotating too fast | Agent cannot keep up | Size for bursts/outages |
| Sync direct network appender in request path | Backend outage spikes latency | Bounded async/collector |
| Trusting async queue as durable | Crash/drop loses events | Know failure policy; separate audit store |
| Logback child and root share appender | Duplicated console records | Check additivity |
| Disabling additivity without checking routing | Can lose audit/security logs | Test every logger path |
| Shipping both stdout and file to one index | Duplicate ingestion | Pick a canonical source |
| Treating stdout as an audit ledger | No atomicity/integrity | Outbox/protected store |
| Building JSON by concatenating raw user input | Log injection, invalid JSON | Proper encoder + validation |
| Logging full request bodies | Secret leaks, high cost | Metadata allowlist |
| Stack trace split into many physical lines | Wrong counts/parsing | Escaped JSON or multiline parser |
| Relying only on ERROR logs to detect outages | If collector dies, logs vanish | Meta-monitoring |
| Exporting logs via unlimited shared URLs | Data leakage | TTL, IAM, access audit |
| Unclear sink ownership | Nobody fixes broken pipelines | Owner and runbook |
| Counting logs as transaction counts | Duplicates/sampling skew numbers | Metrics/business events with proper semantics |

## 20. Exercises and Answers

**Exercise 1.** A Java service on Kubernetes uses the default JUL ConsoleHandler. The collector only collects stdout; why are no records visible?

**Answer:** ConsoleHandler writes to **stderr** by default, not stdout. Verify that the pipeline collects both streams or switch to an appropriate handler target.

**Exercise 2.** An event is written to stdout and a file, and both are shipped to the backend. Do two documents prove Java processed two business requests?

**No.** It may be fan-out of the same event. Compare logger invocations, event instance IDs, and source metadata.

**Exercise 3.** The JVM called `FileHandler.flush()` before committing the database. Does this guarantee the audit transaction exists if the JVM crashes?

**No.** Flushing a file does not create atomicity with a business transaction. Use an audit/outbox in the same transaction or a proven durable mechanism.

**Exercise 4.** A synchronous remote logger hits a network timeout and request latency spikes. What should you inspect?

**Answer:** Network logging is on the request path; review buffer/block/drop policies, async collector usage, deadlines, and business impact.

**Exercise 5.** A file is kept for 7 days, and the backend for 30 days. Does deleting the local file after 7 days erase all data?

**No.** The backend, backups, snapshots, and exports have independent retention.

**Exercise 6.** All ERROR logs go to stdout. Is that a misconfiguration?

**Not necessarily.** stdout is a transport stream; event severity lives inside the log record. Verify that the collector reads the right stream and alerts are driven by appropriate signals.

**Exercise 7.** No new error logs have appeared for an hour, yet users cannot call the API. What might be happening?

**Answer:** The service or telemetry pipeline may be down or not ingesting. Synthetic health checks and no-data alerts are needed.

**Exercise 8.** Why does `LogDestinationDemo` print `FILE WARNING ...` to stdout if the security logger only writes to a file?

**Answer:** The demo **reads the file back and prints a confirmation line**. That is not the security logger emitting directly through `StdoutHandler`.

## 21. Adoption Checklist

1. **Purpose:** define diagnostic, security, and audit logs separately.
2. **Destination:** know whether the JVM writes to stdout/stderr/file/network and what the final backend is.
3. **Runtime:** fit for VM/container; do not leave files stranded in ephemeral filesystems.
4. **Schema:** timestamp, level, event code, service, error code, and correlation are controlled.
5. **Data minimization:** do not log passwords, tokens, or unnecessary PII/raw payloads.
6. **Routing:** no duplicate or dropped events due to additivity or multiple appenders.
7. **Performance:** measure serialization, CPU/GC, queues, stdout blocking, and disk/network.
8. **Failure policy:** document block/drop/retry, restart, and shutdown behavior.
9. **Centralization:** agent parses Docker/CRI/file/JSON/multiline and maintains checkpoints.
10. **Retention:** local rotation, backend retention, backups, and exports have clear owners.
11. **Audit:** if mandatory, prove durability/atomicity/integrity separately.
12. **IAM:** ingest-only collector; do not bundle read/export/delete/configure permissions.
13. **Monitoring:** track drops, queues, lag, no-data, parse errors, and alert owners.
14. **Testing:** end-to-end, failure injection, duplicate/loss, and secret canary tests.
15. **Documentation:** pipeline diagram, per-logger routing, and sink incident runbook.

## 22. Conclusion

**Choosing a log destination** means choosing the right path and guarantee level for a log type, not just picking `ConsoleAppender` or `FileHandler`. For containerized Java services, **structured stdout → runtime → collector → central backend** is usually the simplest, easiest-to-manage choice. For JVMs on VMs, **rolling file → file agent** works well when rotation, permissions, and checkpoints are controlled. For mandatory audits, design a **transaction/outbox or protected store** that meets actual compliance requirements.

A good design answers: *where are logs emitted, where can they be lost or duplicated, who can view them, how long are they kept, what do they cost, and what happens when the sink fails?* When those questions have clear, tested answers, logging supports investigations instead of causing new incidents or creating a false sense of security.
