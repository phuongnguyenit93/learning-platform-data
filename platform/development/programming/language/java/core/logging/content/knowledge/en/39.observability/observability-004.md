# Log Aggregation in Java: Collecting, Normalizing, and Querying Centralized Logs

## 1. What Is Log Aggregation?

**Log aggregation** is the process of **collecting log records from multiple processes, hosts, containers, and services**, normalizing them into searchable data, routing them through an observable pipeline, and storing them in one or more centralized systems. The goal is not merely to dump text into a single large file, but to answer questions such as: *Which request failed? Which services were involved? In what sequence did events occur? Are any logs missing, duplicated, or containing unauthorized data?*

In a small Java application running on a personal machine, you can inspect logs directly from the console or a single file. When a system spans multiple instances, microservices, Kubernetes pods, scheduled jobs, or message consumers, that approach is no longer enough:

- A single error may traverse an HTTP gateway → Java service → queue → worker → database.
- Instances can autoscale or restart, making local logs unavailable.
- Each service may use JUL, SLF4J/Logback, Log4j 2, or another library.
- Some services write to stdout/stderr, some write to files, and others send telemetry directly.
- Queries need to filter by `service.name`, `environment`, `trace_id`, `event.code`, level, and time range.

**Aggregation is not the same as a logging API.** JUL/SLF4J/Log4j 2 emit events; a shipper/agent/Collector transports and transforms them; an index/storage/search layer stores and queries them. Calling `log.info(...)` **does not by itself prove** that an event reached the centralized store.

This lesson focuses on designing and testing **the path of Java logs into an aggregation system**, without prescribing a single vendor as the only answer.

## 2. Overall Architecture and Responsibility Boundaries

~~~text
┌───────────────────────────────────────────────┐
│ Java services / jobs / message consumers      │
│ JUL, SLF4J+Logback, Log4j 2                   │
│ eventCode, severity, timestamp, traceId ...   │
└───────────────────────┬───────────────────────┘
                        │ stdout/stderr, file, OTLP ...
                        ▼
         Container runtime / file / agent
                        │
                        ▼
           Shipper / OpenTelemetry Collector
           ├─ receiver: tail file / OTLP / API
           ├─ parse JSON, multiline, normalize
           ├─ enrich resource/service metadata
           ├─ redact/drop per policy
           ├─ batch, retry, bounded queue
           └─ exporter: backend / gateway
                        │
                        ▼
              Central log storage
           Index + retention + access control
                        │
                        ▼
           Query, dashboards, alerts, audit
                        │
                        └── correlate with traces/metrics
~~~

**Questions specific to each hop:**

1. *Application:* Was the record created? Did the level/filter allow emission? Are the body and attributes safe?
2. *Runtime:* Did the bytes reach stdout/file? Did the container runtime accept them?
3. *Shipper/agent:* Did it read the log line? Did parsing succeed? Where is the file cursor/checkpoint?
4. *Collector:* Did it process and forward the record? Are there retries, queues, drops, filters, or exporter errors?
5. *Backend:* Did it receive the record? Was it indexed? Can it be queried by field? How long is the data retained?
6. *UI/alerts:* Do access permissions, query time windows, and alerts match operational needs?

**Do not equate "enqueued" with "durably stored."** Each layer has its own buffers, timeouts, acknowledgments, and error policies. Across many paths, network disruptions can cause **lost or duplicated records**; the goal should be an explicit reliability contract rather than an assumption of exactly-once delivery.

## 3. Three Common Java Log Sources

| Application Source | Collection Method | Best Fit | Considerations |
| --- | --- | --- | --- |
| **stdout/stderr** | Captured by container runtime or systemd/journald, tailed by agent | Containers, Kubernetes, cloud-native platforms | Distinguish app logs from diagnostic stderr, line size limits, runtime rotation |
| **File** | Agent tails file and tracks position/rotation | VMs/bare metal, legacy apps, internal file requirements | Paths/permissions, disk full, inode, copytruncate/rename rotation, multiline |
| **OTLP/direct export** | SDK/bridge/exporter → OTLP receiver or logging service | Projects using OpenTelemetry with unified tracing/metrics | Batch/queue/timeout, network, TLS/auth, exporter compatibility and lifecycle |
| **Syslog/legacy endpoint** | Receiver/forwarder ingests and normalizes | Legacy platforms, mixed appliances and applications | Field structure, timezone, framing, transport reliability |

**Choose one clear default path per application group.** If you ship both a file and stdout containing the same content, a single event can be collected **twice**. If a separate audit channel exists, give it an independent identifier and policy instead of mixing all logs together.

For containerized Java applications, **stdout/stderr + node-level agent** is usually the simplest starting point. For applications that need standardized OpenTelemetry data attributes, an OTLP bridge/exporter can be appropriate; avoid configuring duplicate delivery across both paths.

## 4. Good Log Data Must Be Structured Before Aggregation

A plain string such as:

~~~text
Something failed for order 42
~~~

is much harder to search than an event with stable fields. Without structure, the collector must rely on regex to guess fields, which breaks easily when message wording changes or unexpected characters appear.

Example of JSON Lines with one record per line:

~~~json
{"timestamp":"2026-11-10T02:00:00Z","service.name":"checkout-service","severity":"INFO","event.code":"ORDER_ACCEPTED","trace_id":"0123456789abcdef0123456789abcdef","order_ref":"ord-42","outcome":"SUCCESS","body":"order accepted"}
~~~

This is an illustrative schema. Using JSONL/NDJSON helps because **each physical line is a complete JSON object**, even when `body` contains escaped newlines. However, **"JSON text" does not automatically become an OpenTelemetry Logs Data Model or OTLP payload**: the collector must parse and map fields to the target data model according to a contract.

Benefits:

- Query `service.name = checkout-service AND event.code = ORDER_ACCEPTED`.
- Count `outcome` by environment, service, or time window.
- Correlate with traces via `trace_id` (when present).
- Apply consistent keep/drop/mask field policies.
- Maintain a machine-readable format independent of human-readable phrasing.

Do not automatically serialize every DTO or raw exception into JSON: having a schema does not prevent secrets or PII from entering logs.

## 5. Practical Schema: Which Fields Are Required vs. Optional?

| Field/Group | Meaning | Recommendation |
| --- | --- | --- |
| `timestamp` | Time when the event actually occurred | UTC, ISO 8601/RFC 3339; do not rely on default timezone |
| `observedTimestamp` | Time when the Collector received/observed it | Keep separate when diagnosing shipper latency |
| `service.name` | Workload/service name | Stable name across pods/instances |
| `service.version` | Release version | Useful when comparing incidents after a deploy |
| `deployment.environment.name` or equivalent | Prod/staging/dev | Avoid mixing environments |
| `severity`/`severityText` | Log level | Normalize JUL WARNING ↔ WARN in backend; keep raw level if needed |
| `logger` | Emission source in code | Can be package/class/logger category |
| `event.code` | Stable event identifier | Enum/allowlist such as `PAYMENT_RETRY` |
| `body` | Human-readable message | Controlled content, free of secrets |
| `trace_id` / `span_id` | Request/span correlation | Use the tracing system's format; not a user identifier |
| `request_id` / `message_id` | Business/transport correlation | Distinguish request ID from business event ID |
| `outcome` / `reason_code` | Outcome and categorized cause | Must not contain raw exception messages |
| `host.name`, `k8s.pod.name`, `container.id` | Infrastructure metadata | Usually enriched more reliably by agent/collector than the app |
| `tenant_ref` / `user_ref` | Controlled traceability | Only when policy permits; minimize personal data |
| `schemaVersion` | Project-defined log schema version | Needed for downstream parsers or pipeline migrations |

**Avoid turning `trace_id`, `order_ref`, or message IDs into metric labels**: their values have very high cardinality. In the log store, index only the fields you genuinely need to query; storage and query costs depend on the backend.

**Do not use "standard" field names arbitrarily.** For example, `service.name` is an OpenTelemetry semantic convention, whereas a custom JSON schema merely has a key with that name. To map cleanly to the OpenTelemetry model, map it to **Resource attributes** rather than leaving it solely inside `Body`.

## 6. Timestamps, Severity, and Event Ordering

### Producer Timestamp vs. Collector Observed Time

- **Event time:** timestamp generated by the JVM when the event is emitted.
- **Observed/ingest time:** timestamp when the agent/collector receives the record.
- **Indexed time:** timestamp when the backend makes the record queryable, which may be later.

If JVM clocks drift or the network lags, events may arrive in storage **out of event-time order**. An aggregation pipeline cannot guarantee global ordering across multiple threads, services, and regions without dedicated design.

For durations, measure with `System.nanoTime()` or an appropriate monotonic clock API; do not subtract two timestamps from different machines to claim exact latency when clocks can skew.

### Severity Mapping

| JUL | Approximate Meaning | Common Equivalent in Other Systems |
| --- | --- | --- |
| `SEVERE` | Serious failure | ERROR |
| `WARNING` | Warning | WARN |
| `INFO` | Informational | INFO |
| `CONFIG` | Configuration information | No universal 1:1 mapping |
| `FINE` | Diagnostic | DEBUG |
| `FINER` / `FINEST` | Detailed diagnostic | TRACE |

OpenTelemetry defines both `SeverityText` and `SeverityNumber`, not just a single `severity` string. Mapping should be performed by the bridge/collector according to the API and version; do not force every backend into the same table via naive text substitution.

## 7. Standalone Java 17 Example: JSON Lines on Stdout

To demonstrate an aggregation-friendly log format, the following program uses only **JDK 17** with no external dependencies. It:

1. Uses a JUL `Logger` and a custom `Handler` to write JSONL to stdout.
2. Attaches `timestamp`, service, severity, logger name, event code, trace ID, order reference, outcome, and body.
3. Escapes `"`, backslashes, newlines, tabs, carriage returns, and control characters so **one event never splits across multiple physical lines**.
4. Passes only safe data in `SafeEvent`; never logs the dummy secret.
5. Uses **fixed** timestamps for deterministic test output; in real applications, capture event time when the log is emitted rather than hard-coding it.
6. Does not send OTLP or connect to a log store directly; it acts solely as a **JSONL source** that an agent can ship and parse.

Create **LogAggregationDemo.java**:

~~~java
import java.time.Instant;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LogAggregationDemo {
    private static final Logger LOG = Logger.getLogger("demo.aggregation");

    record SafeEvent(String eventCode, String traceId,
                     String orderRef, String outcome) {}

    static final class JsonFormatter extends Formatter {
        private static void field(StringBuilder out, String key, String value,
                                  boolean comma) {
            if (comma) out.append(',');
            quote(out, key);
            out.append(':');
            quote(out, value);
        }

        private static void quote(StringBuilder out, String input) {
            out.append('"');
            for (int i = 0; i < input.length(); i++) {
                char c = input.charAt(i);
                switch (c) {
                    case '"': out.append("\\\""); break;
                    case '\\': out.append("\\\\"); break;
                    case '\n': out.append("\\n"); break;
                    case '\r': out.append("\\r"); break;
                    case '\t': out.append("\\t"); break;
                    default:
                        if (c < 0x20) {
                            out.append(String.format("\\u%04x", (int)c));
                        } else {
                            out.append(c);
                        }
                }
            }
            out.append('"');
        }

        @Override
        public String format(LogRecord record) {
            Object[] parameters = record.getParameters();
            if (parameters == null || parameters.length != 1 ||
                    !(parameters[0] instanceof SafeEvent)) {
                throw new IllegalArgumentException("SafeEvent required");
            }
            SafeEvent data = (SafeEvent) parameters[0];
            StringBuilder out = new StringBuilder(256);
            out.append('{');
            field(out, "timestamp", record.getInstant().toString(), false);
            field(out, "service.name", "checkout-service", true);
            field(out, "severity", record.getLevel().getName(), true);
            field(out, "logger", record.getLoggerName(), true);
            field(out, "event.code", data.eventCode(), true);
            field(out, "trace_id", data.traceId(), true);
            field(out, "order_ref", data.orderRef(), true);
            field(out, "outcome", data.outcome(), true);
            field(out, "body", record.getMessage(), true);
            out.append('}').append(System.lineSeparator());
            return out.toString();
        }
    }

    static final class StdoutHandler extends Handler {
        StdoutHandler() {
            setLevel(Level.ALL);
            setFormatter(new JsonFormatter());
        }
        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                System.out.print(getFormatter().format(record));
            }
        }
        @Override public void flush() { System.out.flush(); }
        @Override public void close() { flush(); }
    }

    private static void emit(Level level, String body,
                             SafeEvent safe, Instant time) {
        LogRecord record = new LogRecord(level, body);
        record.setLoggerName(LOG.getName());
        record.setInstant(time);
        record.setParameters(new Object[]{safe});
        LOG.log(record);
    }

    public static void main(String[] args) {
        Handler handler = new StdoutHandler();
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);
        LOG.addHandler(handler);
        try {
            String sensitive = "TEST_SECRET_DO_NOT_LOG";
            boolean credentialPresent = !sensitive.isEmpty();
            if (!credentialPresent) throw new IllegalStateException();
            String trace = "0123456789abcdef0123456789abcdef";
            emit(Level.INFO, "order accepted",
                    new SafeEvent("ORDER_ACCEPTED", trace, "ord-42",
                            "SUCCESS"), Instant.parse("2026-11-10T02:00:00Z"));
            emit(Level.WARNING, "provider said \"retry\"\nrequest queued",
                    new SafeEvent("PAYMENT_RETRY", trace, "ord-42",
                            "PENDING"), Instant.parse("2026-11-10T02:00:01Z"));
        } finally {
            LOG.removeHandler(handler);
            handler.flush();
            handler.close();
        }
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 LogAggregationDemo.java
java LogAggregationDemo
~~~

**Exact standard output (stdout)** in a normal UTF-8/JDK environment:

~~~json
{"timestamp":"2026-11-10T02:00:00Z","service.name":"checkout-service","severity":"INFO","logger":"demo.aggregation","event.code":"ORDER_ACCEPTED","trace_id":"0123456789abcdef0123456789abcdef","order_ref":"ord-42","outcome":"SUCCESS","body":"order accepted"}
{"timestamp":"2026-11-10T02:00:01Z","service.name":"checkout-service","severity":"WARNING","logger":"demo.aggregation","event.code":"PAYMENT_RETRY","trace_id":"0123456789abcdef0123456789abcdef","order_ref":"ord-42","outcome":"PENDING","body":"provider said \"retry\"\nrequest queued"}
~~~

**Standard error (stderr):** empty, **exit code:** `0`.

Note: the two lines above contain a literal **backslash-n** inside the second JSON string; there is no physical newline inside `body`. When a JSON parser decodes `body`, the resulting string value contains an actual newline.

### 7.1. Mechanism Breakdown

- `LOG.setUseParentHandlers(false)` prevents the root logger from writing a duplicate copy in a different format.
- `StdoutHandler.publish` invokes the formatter and writes to `System.out`. This is a **learning** handler—it has no queue, smart buffering, I/O error handling, or batch exporter.
- `JsonFormatter.quote` escapes basic JSON characters. For complex Unicode data and production workloads, **use a maintained JSON encoder** rather than a hand-rolled serializer.
- `SafeEvent` uses intentionally selected fields. `LogRecord.getParameters()` is used here as a specialized mechanism to pass structured data in the demo; it is **not JUL's standard structured-attributes mechanism**.
- `record.getInstant()` represents the event time; fixed timestamps are used only so test output can be matched deterministically.
- `sensitive` is never passed into `SafeEvent`, `body`, or parameters; it exists solely to illustrate that having secret data in application scope **does not mean it should be logged**.

Do not adopt `StdoutHandler` and `JsonFormatter` verbatim as a production logging framework: production systems require richer backends, batching, error handling, thread synchronization, sampling, exception rendering, Unicode escaping, masking, and rollover/collector policies.

## 8. Testing JSONL Before Connecting an Aggregator

You can redirect the demo's stdout to a test file and parse it **line by line**:

~~~bash
java LogAggregationDemo > app.jsonl
~~~

Checks should verify:

1. The file has exactly **two physical lines**, and each line parses as a valid JSON object.
2. `event.code` is `ORDER_ACCEPTED` and `PAYMENT_RETRY`, respectively.
3. `timestamp` is valid, and levels are `INFO` and `WARNING`, respectively.
4. `trace_id` is consistent across events belonging to the same request.
5. `body` on the second line decodes with quotes and a newline, without splitting the file into a third line.
6. The sentinel `TEST_SECRET_DO_NOT_LOG` does not appear on **any line**.
7. No raw fields such as `password`, `access_token`, `Authorization`, or full payloads appear.
8. If exported through a collector, field types and backend mappings are verified after ingestion.

A parseable JSONL line **does not** prove it has been shipped or indexed. Test every boundary. In CI, also verify collector log output under misconfiguration and its behavior when the downstream backend is unavailable.

## 9. Logback and Log4j 2: Using the Right Encoder/Layout

Java applications commonly log through **SLF4J**, backed by Logback Classic or a provider/bridge to Log4j 2.

**SLF4J application call:**

~~~java
// Illustration requiring SLF4J and pre-created safe variables.
LOG.info("orderRef={} outcome={} traceId={}",
        safeOrderRef, "SUCCESS", traceId);
~~~

Parameterized logging defers string formatting when the level is disabled; **it does not automatically produce a JSON object with a field named `orderRef`**. To make fields individually queryable in a log store, use structured key-value pairs (SLF4J 2.x fluent API), controlled MDC, or a schema-compliant JSON encoder/layout.

**Plain-text Logback ConsoleAppender:**

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

This configuration requires a compatible Logback Classic version. It outputs **plain text** rather than JSONL; to query by field, a collector would need to parse the text or you must switch to a JSON encoder. When choosing a JSON encoder from the Logback ecosystem, check its version, dependencies, stack-trace formatting, and MDC output; never assume that enabling a JSON encoder automatically prevents data leaks.

**Plain-text Log4j 2 PatternLayout:**

~~~xml
<Configuration>
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <PatternLayout pattern="%d{ISO8601} %-5p %c - %m%n"/>
        </Console>
    </Appenders>
    <Loggers>
        <Root level="info">
            <AppenderRef ref="CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
~~~

If you use Log4j 2's **JSON Template Layout**, define a template schema and verify the layout/encoder output along with the `log4j-layout-template-json` dependency. Do not concatenate JSON with `String.format` at every log site to invent ad-hoc schemas; that leads to double-escaping and missing fields.

**Separate channels when needed:** use console stdout for application logs and a dedicated sink for audit/security logs when retention and integrity requirements differ. Never ship the same source twice via both stdout **and** a file and end up with duplicates.

## 10. Kubernetes: stdout/stderr, Node Agents, and Log Rotation

Kubernetes recommends that containerized applications write logs to **stdout/stderr**. The container runtime captures these streams using its logging driver, and kubelet exposes recent output via `kubectl logs`. However, **Kubernetes does not provide a built-in cluster-wide centralized log storage and query system**; a separate aggregation backend is required.

~~~text
Java container stdout/stderr
   -> container runtime / CRI log file on node
   -> DaemonSet agent tail/parse logs
   -> gateway/Collector
   -> durable backend/index
   -> search/dashboards
~~~

In a common architecture, a node-level agent runs as a **DaemonSet** that reads logs from all pods on the node. Alternatives include a sidecar reading application files or the application sending logs directly to the backend. Each option has different cost and complexity trade-offs.

**Common pitfalls:**

- `kubectl logs` is great for debugging, but **it does not replace centralized retention and search**.
- Pod deletion, node failure, or container log rotation can remove data from the node.
- The runtime writes lines in **CRI format** with stream/timestamp metadata; an agent must strip this wrapper **before or during parsing of the application JSON**.
- Long log lines can be split into **partial records**; the collector/agent must support reassembly and appropriate size limits.
- Kubelet performs **container log rotation**, so the agent must track files by inode/path/checkpoint to avoid duplicate reads or missed lines during rename/truncate.
- A container can write to both stdout and stderr; the aggregation schema should preserve the stream source when useful, without assuming `stderr` always means ERROR across all libraries.

If any service still writes internal files inside a container, choose a dedicated shipping path and avoid losing logs when the container is replaced.

## 11. Shippers, Collectors, Gateways, and Backends Compared

| Component | Role | Common Examples |
| --- | --- | --- |
| **Node agent / shipper** | Reads files/stdout/CRI, attaches metadata, forwards | Fluent Bit, Vector, Filebeat, OpenTelemetry Collector with appropriate receivers |
| **Collector/processor** | Receives data, batches, transforms, redacts, routes, retries | OpenTelemetry Collector, dedicated ingest pipelines |
| **Gateway** | Centralized endpoint receiving telemetry from many agents/services | Horizontally scaled Collector gateway |
| **Transport buffer** | Absorbs slow-backend spikes, decouples cross-region traffic | Durable queue/broker when appropriate |
| **Log backend** | Stores, indexes, retains, searches, and powers dashboards | Elasticsearch/OpenSearch, Loki, cloud log services |
| **Alert/incident platform** | Turns aggregated events into alerts and workflows | Alert rules, notifications, incident management |

There is no "best stack for every project." The choice depends on throughput, indexing cost, query patterns, multi-tenancy, compliance requirements, existing ecosystem, and operational expertise.

A Java logger may only need to write schema-compliant stdout while the platform team operates the agent/Collector/backend. When multiple teams share responsibility, establish **schema contracts, ownership, and pipeline SLOs**; otherwise each team assumes its job is done once data is handed off to the next hop.

## 12. OpenTelemetry Logs Data Model and OTLP

OpenTelemetry defines a **log record data model** with the following fields:

- `Timestamp` and `ObservedTimestamp`.
- `SeverityText` and `SeverityNumber`.
- `Body`.
- `Resource` (e.g., `service.name`, deployment metadata).
- `Attributes`, `InstrumentationScope`.
- `TraceId`, `SpanId`, and trace flags when present.
- `EventName` for named events.

This is a **data model**, not a guarantee that any JSON object with similar key names will automatically be understood as OTLP.

~~~text
JSONL on stdout (demo example)
       │
       ▼
filelog receiver / agent parses JSON
       │
       ▼
Map timestamp, level, body, trace_id, service.name...
       │
       ▼
OpenTelemetry LogRecord data model
       │
       ▼
OTLP exporter / backend
~~~

An alternative path:

~~~text
Java app + configured SDK/bridge/exporter
       │
       ▼
OTLP/gRPC or OTLP/HTTP
       │
       ▼
OpenTelemetry Collector OTLP receiver
       │
       ▼
Backend
~~~

**Do not wire the wrong components together:** the Collector's `otlp` receiver **does not tail stdout JSONL** from the Java example in Section 7. To ingest stdout, use a runtime/agent/filelog receiver; to use the OTLP receiver, the application or agent must send **OTLP-formatted payloads**.

OpenTelemetry also provides Java logging bridges and instrumentation depending on framework and version. Verify the exact library, context-propagation semantics, and exporter before routing the same event through two paths (which can create duplicates).

## 13. Example Collector OTLP Config for Pipeline Testing

The **otel-collector.yaml** example below defines a **test OTLP logs** pipeline—it is not a configuration for reading stdout JSONL from the demo app. It requires a Collector distribution with the `otlp` receiver, `batch` processor, and `debug` exporter. Bind only to loopback in development environments:

~~~yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 127.0.0.1:4317
      http:
        endpoint: 127.0.0.1:4318

processors:
  batch:
    timeout: 5s
    send_batch_size: 256

exporters:
  debug:
    verbosity: normal

service:
  pipelines:
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
~~~

**Explanation:**

- The receiver accepts logs **over OTLP**, not raw `System.out.println(...)`.
- Batching improves throughput, but if the process dies unexpectedly, events still in RAM can be lost.
- The debug exporter is for verifying the path; **never use it as a production store**.
- In Kubernetes, `127.0.0.1` only accepts connections within the same network namespace. If the application runs in another pod, expose a reachable endpoint with TLS/auth/network policies; **do not blindly change it to public `0.0.0.0` without protection**.
- To ingest files/CRI logs, use the **filelog receiver** in a distribution that includes it (typically Collector Contrib) to handle parsing, partial records, and runtime file metadata; that is a **separate pipeline**.
- A component is active only if listed under `service.pipelines.logs`. A declared receiver omitted from the pipeline will not receive data for that flow.

Verify before deployment: whether the Collector binary/distribution includes these components, whether the config matches the Collector version, whether network/TLS/credentials are valid, and whether the real backend acknowledges writes as required.

## 14. Parsing, Multiline, and Log Event Boundaries

A common issue is **multiline stack traces**:

~~~text
ERROR payment failed
java.lang.IllegalStateException: invalid state
    at com.example.PaymentService.process(PaymentService.java:42)
    at ...
~~~

If the agent treats each physical line as an independent event, stack-trace lines lose their level and timestamp and become hard to correlate with the error. Options include:

1. **JSONL:** encode the body/exception into a JSON field with escaped newlines so each event remains on a single physical line.
2. **Multiline parser:** when a plain-text source cannot be changed, the agent stitches lines using a timestamp/start-of-event pattern, bounded by timeouts and size limits.
3. **OTLP/native structured:** send exception type, message, and stack trace as structured attributes/body according to schema, avoiding newline-based boundary guessing.

Multiline parsers also carry risks:

- Interleaving lines from two events when multiple threads log concurrently.
- Buffering too many bytes in RAM for very long stack traces.
- Flush timeouts splitting or dropping an event.
- Timestamp regexes failing when locales change.
- Malicious input containing forged newlines or fake headers.

If you control the Java logger, **formatting one JSON object per line with a standard encoder** is usually simpler than reconstructing structure from multiline text. Test CRLF/LF, Unicode, quotes, and large payloads.

## 15. Enrichment and Semantic Metadata: Add It in the Right Place

Some metadata belongs to the application:

- `event.code`, `operation`, `outcome`, reason code.
- `request_id`, `message_id`, `trace_id` when context is available.
- Safe business references, never raw entities.

Other metadata belongs to the deployment environment:

- `k8s.namespace.name`, `k8s.pod.name`, `k8s.container.name`.
- `host.name`, `cloud.region`, `deployment.environment.name`.
- Collector instance or ingest path when needed for troubleshooting.

Agents/Collectors generally enrich infrastructure metadata more reliably than each Java app trying to look up hostnames or pod names on its own. However, misconfigured infrastructure schemas or stale pod metadata can produce mismatches; validate enrichment by UID, instance, and time.

**Do not assume a standard-looking field name automatically satisfies semantic conventions.** For example, `service.name` may be carried as OpenTelemetry resource attributes over OTLP, whereas in custom JSONL you must map it explicitly. If the application name comes from multiple places (Spring application name, service name, Kubernetes label), define a clear precedence and conflict policy.

## 16. Correlating Logs, Metrics, and Distributed Traces

Aggregation becomes far more powerful when you can pivot from a single log line to the full request trace:

~~~text
HTTP request
   trace_id=0123456789abcdef0123456789abcdef
       │
       ├── API service log: REQUEST_ACCEPTED
       │
       ├── Payment service log: PAYMENT_RETRY
       │
       ├── Broker producer log: MESSAGE_ACKED
       │
       └── Consumer log: ORDER_UPDATED
       │
       ▼
Search query: trace_id = ...
       │
       ▼
Pivot to trace/spans + metrics + relevant logs
~~~

Principles:

1. Use proper tracing instrumentation or W3C Trace Context to generate and propagate trace IDs; **do not invent an arbitrary UUID and call it a standard trace ID**.
2. When sending messages, pass context in headers/envelopes per API and security policy; consumers must extract context explicitly.
3. With thread pools, async callbacks, virtual threads, or reactive flows, **ThreadLocal/MDC does not automatically cross every boundary**. Test propagation, cleanup, and scope.
4. Record trace IDs in log events/attributes when present, but do not treat trace sampling as a guarantee of log retention.
5. Never place raw users, tokens, or PII into baggage, MDC, or metric labels.
6. Do not use `trace_id` as a partition key or index everywhere unless truly needed; high cardinality can drive up costs.

If a log lacks a trace ID, it should still carry an event ID, service, timestamp, and error code for investigation. Do not halt all logging simply because tracing instrumentation is temporarily absent.

## 17. Buffering, Batching, Backpressure, and Log-Loss Policies

Aggregation reduces I/O using **batches** and queues:

~~~text
Java log call → appender queue → stdout/file/OTLP
                                  ↓
                               agent queue
                                  ↓
                              collector queue
                                  ↓
                             backend indexing
~~~

Each queue has different guarantees:

| Scenario | Possible Consequence | Mitigation |
| --- | --- | --- |
| Slow backend | Collector queue grows, latency increases | Bounded batches, backpressure, scale throughput |
| Backend outage for several minutes | Retries climb, queues fill | Durable queue if supported, backlog alerts, retry limits |
| App logs faster than stdout/file sink | Appender queue and runtime buffer grow | Rate-limit debug logs, control event volume, monitor discards |
| Container killed with SIGKILL | Data still in process queues is lost | Do not rely on memory-only queues for mandatory audit logs |
| Agent/node restart | Unpersisted cursor/checkpoint or buffer | Managed checkpoints, durable queues where required |
| Network error / ambiguous ACK | Retries may create duplicates | Event IDs and contract-based deduplication |
| Disk full | Agent cannot buffer more data | Disk quotas, retention, health alerts |
| Parser rejection | Records dropped or quarantined | Controlled dead-letter/quarantine, parse-error metrics |

**Batch size/timeout** trades off throughput, memory, and latency. **Retries** improve resilience to brief faults without creating infinite buffers: disk and memory remain finite. **Backpressure** protects the pipeline from data loss by slowing producers, but it can also affect business-request latency.

Choose policies by event class: debug logs can be sampled, whereas critical audit events may require a durable outbox or separate store rather than relying on a best-effort aggregator for business history.

## 18. Delivery Semantics: At-Most-Once, At-Least-Once, and Duplicates

A common claim is: "Once logs are aggregated, nothing is ever lost or duplicated." That is false.

- **At-most-once:** no retries or drops accepted; fewer duplicates, but events can be lost.
- **At-least-once:** retry when delivery is uncertain; higher delivery likelihood, but duplicates can occur.
- **End-to-end exactly-once:** requires coordination across application, transport, storage, and deduplication/transactions; it does not emerge automatically from a log shipper.

Example:

~~~text
Agent sends eventId=EVT-42 -> backend stores successfully
      │
      └─ ACK is lost, agent retries eventId=EVT-42
               │
               ▼
          Backend may receive two copies
~~~

An immutable event ID plus contract-based deduplication can help. However, many routine diagnostic logs lack unique IDs; **do not deduplicate lines solely by body + timestamp**, because two real actions can produce identical text. Base deduplication on an explicit event ID or a well-defined key.

Ordering across hosts, regions, and partitions is not guaranteed. If a workflow requires reconstructing order, use synchronized timestamps, scoped sequence numbers, and well-defined transaction milestones.

**Aggregation does not replace a transactional outbox** when a business event must be recorded atomically with a database change. A log line on stdout is not proof that an event was committed to a broker or audit store.

## 19. Security: Secrets Must Never Enter the Pipeline

A centralized log store creates **a single repository holding data from many systems**, so data-exposure and authorization risks scale accordingly.

Never log raw:

- Passwords, OTPs, PINs, bearer/refresh tokens, API keys, cookies, or private keys.
- HTTP `Authorization` headers, or request/response bodies containing PII or payment details.
- JDBC URLs containing credentials or sensitive SQL bind values.
- `Throwable.getMessage()` or stack traces when they might include URL tokens or user data.
- Unvetted MDC/baggage/headers, or `toString()` on domain objects that contain secrets.

**Defense in depth, in order of priority:**

1. **Data minimization at the source:** log only explicitly permitted fields.
2. **Validation and structured encoding:** allowlisted event codes and reason codes, length limits, and proper JSON escaping.
3. **Collector redaction/transforms:** a secondary safety net to catch known patterns before export; never a substitute for source hygiene.
4. **Transport security:** TLS/mTLS, authenticated exporters/receivers, secrets from a secret manager, never hard-coded.
5. **Storage security:** RBAC, tenant isolation, encryption at rest, and auditing of log read/export access.
6. **Lifecycle:** retention, proper purge/deletion, and policies for backups, archives, and exports.

Masking in a dashboard **does not remove** the original data from indexes, files, shipper buffers, or backups. If a secret is discovered in logs, treat it as a security incident: restrict access, assess copy scope, revoke/rotate credentials as needed, and follow applicable internal/legal procedures.

**Multi-tenancy:** a misconfigured filter or overly broad token can expose another tenant's events. Enforce authorization at the backend and gateway, not merely by hiding a tenant selector in the UI.

## 20. Log Injection, Large Payloads, and Schema Evolution

A user-controlled value can contain:

~~~text
invalid input
ERROR admin authenticated
~~~

If concatenated directly into line-oriented text logs, downstream parsers may interpret it as **two separate events**. With JSONL, a proper encoder escapes newlines inside string values so physical line boundaries remain intact; however, **JSON escaping does not remove tokens or PII**.

Recommended guardrails:

- Sanitize CR/LF and control characters when emitting plain text.
- Use a standard JSON serializer; never build JSON by concatenating raw input with `+`.
- Enforce field/event size limits and controlled truncation rules with metadata markers such as `truncated=true` if business requirements allow.
- Use locale-invariant formatting for timestamps and numbers when part of a contract.
- Maintain schema versions and compatibility rules when adding or renaming fields.
- Standardize null/missing/empty semantics: those three states can carry different meanings.
- Test Unicode, emoji, multiline strings, quotes, backslashes, and chained exceptions with causes.
- Never dump raw binary/blobs or unbounded stack traces into every event.

**Do not confuse parser errors with application failures.** If `ORDER_ACCEPTED` actually occurred but the parser dropped it for exceeding size limits, dashboards may make it look like business logic never ran. The pipeline needs parse-reject and quarantine metrics.

## 21. Retention, Indexing, and Cost Optimization

Log aggregation incurs costs across **ingest**, **indexing**, **storage**, and **query**. Not every field needs to be indexed or kept long-term.

Classification template:

| Log Category | Query Need | Policy Considerations |
| --- | --- | --- |
| DEBUG/TRACE | Short-term troubleshooting, high volume | Candidates for sampling, short retention, search by time/service |
| Operational INFO | Activity and incident analysis | Batching, standard metadata, retention per operational need |
| WARN/ERROR | Investigation and alerting | Keep sufficient context, avoid duplicates, fast query |
| Security/audit | Purpose-built traceability and compliance | Dedicated retention/access/integrity; do not auto-sample |
| Access logs | HTTP route/status/latency | Never log raw query strings/cookies; bound cardinality |
| Platform/collector logs | Pipeline health | Store separately to investigate missing logs |

Example plan:

- Keep **hot** logs short-term for interactive queries, and **warm/cold** logs for infrequent lookups when required.
- Index `service.name`, severity, `event.code`, timestamp, and select approved context fields; avoid indexing every JSON key.
- Measure bytes/s, events/s, compression ratio, index size, and query latency before changing policies.
- Do not pick a single "universal retention days" number for every organization; base it on risk, policy, contracts, applicable laws, and privacy.

Backends such as Loki, OpenSearch, and cloud logging services use different indexing strategies; optimize fields and cardinality according to your actual backend's documentation.

## 22. End-to-End Testing of an Aggregation Pipeline

Java unit tests only prove the **source event**. Integration tests must verify the entire path to the query layer.

| Test | Action | Assertion |
| --- | --- | --- |
| JSONL source | Run `LogAggregationDemo` | Two lines, each valid JSON, containing no secrets |
| CRI/file parsing | Feed fixture through agent | Timestamp/stream/body parsed accurately without leaking wrapper into JSON |
| Normalization | Map custom event → target schema | `service.name`, severity, `event.code` have expected types and placement |
| Trace correlation | Emit 2 events with same `traceId` | Query returns both events and trace link when present |
| Multiline | Body contains `\n` and quotes | Single event, logical body preserved |
| Unicode | Vietnamese text / emoji messages | No encoding corruption, no false line splits |
| Missing optional field | Omit `spanId` | Collector handles per contract without unintended drops |
| Bad timestamp | Invalid event time | Rejected/quarantined/metered, not silently faked |
| Network outage | Temporarily disconnect backend | Retries/backlog/drops follow policy; alerts fire |
| Agent restart | Restart before/during file rotation | Duplicates/loss stay within documented bounds |
| Pod restart | Terminate container | Logs collected if flushed to runtime; not mistaken for durable guarantee |
| Very large record | Body exceeds limit | Truncated/dropped/quarantined per policy without crashing agent |
| Redaction | Event contains dummy sentinel | Sentinel absent from index, exports, dashboards, and fallback logs |
| Authorization | User role restricted from other tenant | Backend denies query/exfiltration |
| Retention | Event exceeds retention period | Data purged per policy across applicable tiers |
| Duplicate | Lost ACK triggers retry | Deduplicated/counted per contract |
| High throughput | Controlled log-rate spike | Bounded memory/queues, no OOM, ingest delay measured |

**Never use `Thread.sleep(1000)` as proof that an event has been indexed.** For async pipelines, poll by test event ID with a bounded timeout, track completion/ACKs, and record elapsed time. Negative tests must wait for an appropriate stability boundary; "not visible yet" does not prove filtering.

## 23. Observing the Aggregation System Itself

A log pipeline can fail silently while the application keeps running. Measure **telemetry of the telemetry pipeline**:

- Records/bytes received per receiver.
- Records exported successfully, export failures, and retries.
- Pending queue depth, dropped records, and buffer disk usage.
- Parse error rate, unmapped events, and oversized records.
- `ingest_delay = observed/indexed time - event time`, accounting for clock skew.
- Remaining disk space, rotation lag, and checkpoint persistence.
- Collector CPU, memory, restart count, and readiness/health.
- Rate of logs missing `trace_id`, missing `schemaVersion`, or having wrong types.
- Duplicate count by event ID (when available).
- Ingest/index cost and p95/p99 query latency.

Example alerts: **sustained backend exporter errors**, unbounded queue growth, ingest delay exceeding thresholds, or a sharp drop in received source events while application request rates remain normal.

**Avoid logging feedback loops:** Collector fails → logs excessive errors into the same failing pipeline → increases pipeline load → worsens failure. Apply rate limits and maintain a minimal, independent diagnostic channel.

## 24. Runbook: "The App Logged It, but the Dashboard Doesn't Show It"

Instead of cranking log levels up to `DEBUG` everywhere, investigate hop by hop:

1. **At the JVM:** Is the logger enabled? Are filters blocking it? Did the handler/appender start? Is output going to stdout or a specific file?
2. **At the container:** Does `kubectl logs` show the event? Did the runtime rotate the file? Were stdout/stderr streams preserved?
3. **At the agent:** Is the filelog include path right, can it read the file, and are checkpoints and permissions intact? Are there parse errors?
4. **At the Collector:** Is the receiver enabled in `service.pipelines.logs`? Is a processor dropping fields/events? What do queue, retry, and exporter metrics report?
5. **At the backend:** Did ingestion accept the schema and timestamp? Was it routed to the wrong tenant/index? Did retention delete it? Is the query filtering the wrong time window or environment?
6. **At the dashboard:** Are permissions, display timezone, sampling, search delay, or trace-linking settings causing confusion?

Symptom table:

| Symptom | Common Cause | Verification |
| --- | --- | --- |
| Present in `kubectl logs`, missing in backend | Agent path/permissions, collector pipeline, or exporter failure | Check file cursor, receiver metrics, exporter errors |
| Present in backend, not queryable by field | JSON kept as raw body text without parsing/mapping | Inspect raw record and schema mapping |
| Only first few lines of stack trace | Misconfigured multiline parser or partial records | Compare raw CRI log with post-parser event |
| Log timestamp outside query window | Clock skew, timezone, or timestamp parse error | Compare event, observed, and indexed times |
| Same event appears twice | Shipping both stdout and file, or retry after lost ACK | Check source labels and event ID |
| Intermittent log loss under load | Async queue/agent buffer drops, rotation, backend throttling | Check drop metrics, queue depth, and rates |
| Trace ID fails to correlate | Context not propagated, or format/mapping mismatch | Compare IDs across source, agent, and backend |
| Slow queries / high cost | Over-indexing or high-cardinality fields | Review backend indexes and query plans |
| Secret appears in index despite dashboard mask | UI-only masking or unredacted secondary sink | Fetch raw record and audit pipeline from source |

Never "fix" missing logs by blindly increasing `retention` or `queueSize` before knowing which hop is dropping events; that can increase cost without solving the root cause.

## 25. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Assuming stdout means it reached the dashboard | Missing agent/Collector/backend | Test end-to-end |
| Assuming any JSONL is OTLP | OTLP receiver does not tail raw JSONL | Use filelog/agent parser or a real OTLP exporter |
| Logging free-form text and regex-parsing everything | Breaks when format/locale changes | Structured schema and standard JSON encoder |
| Ignoring the runtime CRI wrapper | JSON parser chokes on envelope | Parse container log format before application body |
| Shipping both file and stdout | Duplicate events | Pick one source/route and deduplicate |
| Over-relying on `kubectl logs` | No cluster-level retention | Centralized log backend |
| Treating `flush()` as fsync/remote commit | False durability assumptions | Define every ACK/queue/storage boundary |
| Neglecting multiline handling | Stack traces split into multiple records | Escaped JSONL or multiline parser |
| Omitting `service.name` and event codes | Hard cross-service querying | Schema and resource enrichment |
| Using raw message IDs as metric labels | High cardinality | Low-cardinality metrics; keep IDs in logs/traces |
| Logging raw payloads/exceptions/headers | PII and credential leaks | Field allowlists and source-side redaction |
| Relying on dashboard masking alone | Raw secrets remain in indexes/backups | Pre-ingest sanitization and access control |
| Unbounded retries in RAM | OOM, log storms, higher latency | Bounded queues, backpressure, and alerts |
| Assuming retries never create duplicates | Skewed counts, noisy workflows | Event IDs and contract-based deduplication |
| Using ingest timestamp as event time | Wrong business order under delay | Keep both event and observed timestamps |
| Disabling audit via DEBUG sampling | Loss of mandatory event evidence | Separate audit pipeline per policy |
| Testing with sleep then immediate assert | Flaky tests | Bounded await with query verification |
| Not monitoring the collector | Pipeline silently loses logs | Independent metrics, health checks, and alerts |

## 26. Java Log Aggregation Implementation Checklist

1. Identify **log sources** (stdout/stderr, file, OTLP) and avoid duplicate collection.
2. Define **schema version**, field names, data types, event codes, and resource attributes.
3. Standardize on UTC timestamps; distinguish event time from observed/ingest time.
4. Ensure the structured formatter/encoder fits the framework and preserves valid JSONL.
5. Never log unnecessary secrets/PII; run sentinel tests at both source and sink.
6. Define collector agent/gateway deployment and file/metadata read permissions.
7. On Kubernetes, handle CRI format, partial records, rotation, and pod lifecycles.
8. With OpenTelemetry, clearly separate the JSONL parse path from the OTLP receiver path.
9. Set limits on batches, queues, retries, and memory/disk; measure backpressure and drops.
10. Define delivery guarantees and duplicate handling; do not promise exactly-once without proof.
11. Propagate trace context and correlation IDs across async threads and message brokers.
12. Choose appropriate indexed fields, retention, and access controls per log category.
13. Configure TLS/auth/mTLS, tenant isolation, secret management, and access auditing.
14. Maintain end-to-end tests covering app → agent → collector → backend/query.
15. Add metrics and alerts for ingest errors, delay, drops, duplicates, queues, and disk.
16. Document a hop-by-hop runbook for missing logs and an outage recovery plan.
17. Separate observability logs from mandatory audit events; use durable recorders when required.
18. Evaluate cost and throughput before enabling DEBUG/TRACE across many instances.

## 27. Self-Check Questions

1. How does "log aggregation" differ from `Logger.info(...)` and "writing to one big file"?
2. Why does a JSON object on stdout not automatically become an OpenTelemetry `LogRecord`?
3. In Kubernetes, does `kubectl logs` replace a centralized log backend?
4. Which fields help locate all logs related to a single trace?
5. How do event timestamp and observed timestamp differ during network delays?
6. Why are `getLoggerName()` and `service.name` not the same concept?
7. When a body contains a newline, how do you ensure a JSONL event does not split across two lines?
8. Why can an emitted `INFO` log still fail to reach the collector?
9. What can happen when an exporter retries because an ACK was lost?
10. If you need to search by `order_ref`, should you put it in a metric label?
11. Why is DEBUG sampling unsuitable as the sole policy for mandatory audit logs?
12. When logs are missing from the dashboard, why inspect agent checkpoints and the Collector pipeline?
13. How does `SeverityText` differ from `SeverityNumber` in OpenTelemetry?
14. Does writing `trace_id` into JSON prove the trace ID is valid?
15. Is a test confirming JSON parses enough to prove the backend indexed the fields properly?
16. Why cannot dashboard masking fully remediate an accidental secret leak?
17. Why does a Collector need its own telemetry to monitor the pipeline itself?
18. Does a JVM demo calling `System.out.print(...)` guarantee the file is durable on the node?

**Hints:** (1) collects across sources, normalizes, transports, stores, and queries; (2) requires a parser/mapping or an OTLP exporter; (3) no, Kubernetes lacks built-in centralized log storage; (4) trace ID with service/time/event code; (5) emitted at JVM vs. observed at collector; (6) class/logger category vs. service resource; (7) proper JSON escaping or structured encoding; (8) runtime/agent/queue/network/backend sit in between; (9) duplicates; (10) no, high cardinality; (11) audit has stricter retention/integrity policies; (12) troubleshoot hop by hop; (13) original text vs. normalized severity number; (14) no; (15) not yet; (16) raw indexes and backups still retain it; (17) to detect silent data loss; (18) no.

## 28. References

- [Kubernetes — Logging Architecture](https://kubernetes.io/docs/concepts/cluster-administration/logging/): stdout/stderr, CRI logs, rotation, node agents, sidecars, and cluster-level logging.
- [OpenTelemetry — Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/): Timestamp, ObservedTimestamp, SeverityText/Number, Body, Resource, Attributes, TraceId, and SpanId.
- [OpenTelemetry — Logs Concepts](https://opentelemetry.io/docs/concepts/signals/logs/): log signal concepts, bridges, and exporters.
- [OpenTelemetry — Collector Architecture](https://opentelemetry.io/docs/collector/architecture/): receivers, processors, exporters, and pipelines.
- [OpenTelemetry — Collector Configuration](https://opentelemetry.io/docs/collector/configuration/): component declarations, service pipelines, and basic configuration.
- [OpenTelemetry — Install Collector with Docker](https://opentelemetry.io/docs/collector/install/docker/): example OTLP receiver and debug exporter configuration.
- [OpenTelemetry — Collector Troubleshooting](https://opentelemetry.io/docs/collector/troubleshooting/): diagnosing unreceived, unprocessed, or unexported data.
- [OpenTelemetry — Agent-to-Gateway Pattern](https://opentelemetry.io/docs/collector/deploy/other/agent-to-gateway/): separating agent and gateway roles and operational trade-offs.
- [Java SE 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): writing `LogRecord` and levels.
- [Java SE 17 — LogRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html): timestamp, logger name, parameters, and event metadata.
- [Java SE 17 — Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html): `publish`, `flush`, and lifecycle.
- [Logback — Appenders](https://logback.qos.ch/manual/appenders.html): console/file/async appenders and configuration.
- [Log4j 2 — JSON Template Layout](https://logging.apache.org/log4j/2.x/manual/json-template-layout.html): structured JSON layout and schema.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): sensitive data, injection, log protection, and logging operations.
