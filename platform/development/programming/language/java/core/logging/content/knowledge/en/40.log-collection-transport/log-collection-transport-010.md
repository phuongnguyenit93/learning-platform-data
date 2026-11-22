# End-to-End Pipeline Testing in Java Logging

## 1. The Problem: Proving Logs Travel the Entire Observable Path

**End-to-end (E2E) pipeline testing for logging** means verifying that an event emitted by a Java application is **collected, transported, processed, stored, and queried** in accordance with the system contract. This is a **log collection and transport** problem, not merely unit-testing a `logger.info(...)` call.

A microservices system typically has these stages:

~~~text
Java application
  JUL / SLF4J + Logback / Log4j 2 / SDK
       │ produces message, fields, time, trace ID
       ▼
Local sink
  stdout/stderr, file, OTLP exporter
       │
       ▼
Container runtime / node file / shipper
       │ parse, checkpoint, queue, retry
       ▼
Collector / gateway / ingestion pipeline
       │ normalize, enrich, filter, route, batch
       ▼
Log backend
       │ receive, persist, index, apply retention
       ▼
Search API / dashboard / alert
       │
       ▼
E2E assertion: find the exact event, fields, and count
~~~

**Key point:** A Java program running without errors, a line appearing on stdout, an HTTP `200` from the collector, or an `exported=1` metric **does not automatically prove** that the record exists durably and is searchable in the final backend.

A proper E2E test must define a clear **start point** and **end point**. For example, "from emitting a message from the JVM until querying the test backend returns the event with `testRunId`" is much stronger than "the logger called the appender".

### Learning Outcomes

After this lesson, learners can:

1. Diagram and define each ACK/observability boundary of the pipeline.
2. Emit a synthetic event with a unique ID to trace it from source to destination.
3. Verify schema, timestamp, severity, correlation, and data protection.
4. Design tests for success, retry, duplicates, connection loss, and crashes.
5. Wait for real conditions using deadlines instead of arbitrary `Thread.sleep`.
6. Distinguish between a simulated test harness and real Collector/backend integration.
7. Observe the pipeline itself to detect "silent" log loss.

## 2. Distinguishing Unit Tests, Component Tests, Integration Tests, and E2E

| Test Level | Scope | What It Proves | What It Does Not Prove |
| --- | --- | --- | --- |
| Logging call unit test | Business method + mock logger | Code calls the API with the right arguments | Whether level/filter/sink actually emits the event |
| Handler/appender unit test | Logger + in-memory collector | Level, template, Throwable, fields, count | Whether the agent read it and the backend stored it |
| Encoder component test | Log event → JSON/PatternLayout | Formatted content, escaping, schema | Network, retry, indexing |
| Shipper integration test | File/stdout → fake agent/Collector | Parser, routing, batch, retry within test scope | Whether the real backend can query it |
| Backend integration test | Collector → test backend | Ingest, index, query by schema | Whether the Java app emitted/shipped properly |
| **Production-like E2E** | Java process → runtime → shipper → Collector → backend → query | Full path in the tested environment/configuration | Every extreme failure mode and every production environment version |

A test does not need to be forced into E2E if the goal is only "is the message format right?". E2E is more expensive, slower, and requires environment management. Allocating many unit/component tests and a few high-risk E2E scenarios is usually more effective.

Conversely, never use green unit tests to claim that the Kubernetes log pipeline or collector is working.

## 3. Defining Delivery and Storage Contracts

Define the **expected endpoint** for each event class:

| Milestone | Clear Status Name | What Cannot Yet Be Claimed |
| --- | --- | --- |
| `Logger.log(...)` executed | Produced | Handler received it |
| Handler/appender accepted | Accepted locally | Left the JVM buffer |
| Stream/file flushed | Written to local stream | Disk fsynced, agent read it |
| Agent/shipper read | Collected | Exporter sent it |
| Collector receiver received | Ingested by Collector | Processor didn't drop it, backend indexed it |
| Exporter sent and received response | Exported according to protocol | Backend durable commit if the ACK does not promise it |
| Backend query returns event | Searchable | Infinite retention or tamper/delete protection |
| Durable store confirms per contract | Persisted | Full business reconstruction if the source event was wrong |

**An E2E contract can be "searchable within 30 seconds"** for operational logs, whereas mandatory audit logs require designing higher durability and integrity controls. The 30-second mark here **is only an SLO example**, not a standard applicable to every system.

For each test, define beforehand:

- The milestone at which `emit` is considered to have occurred.
- The verification target: file, collector stdout, fake receiver, test backend, or real search API.
- The maximum deadline for the event to become queryable.
- Whether duplicates are acceptable. Is there idempotency/dedup?
- If the sink cannot receive, must the application block, drop, buffer, or retry?
- If restarted mid-flight, what is the recovery expectation?

Do not write a "sent successfully" assertion when you only have a Future or a queue insertion.

## 4. Choosing Test Events with Clear Identifiers

An event used for E2E testing should **contain no real user data**, have a unique identifier, and follow a stable schema.

~~~json
{
  "timestamp": "2026-11-10T02:00:00Z",
  "service.name": "order-service",
  "severity": "INFO",
  "event.code": "ORDER_ACCEPTED",
  "testRunId": "run-qa-42",
  "eventId": "evt-run-qa-42-001",
  "trace_id": "0123456789abcdef0123456789abcdef",
  "body": "order accepted"
}
~~~

This is an **illustrative** JSON example. Both `testRunId` and `eventId` must be **unique in each real test run** (usually a UUID/ULID is suitable); use fixed strings like these only when presenting readable examples.

**Why two IDs?**

- `testRunId` filters all events belonging to one test run, preventing CI from accidentally reading old logs.
- `eventId` allows counting/deduping individual events or identifying which specific event disappeared.
- `trace_id` is tied to distributed tracing, but one trace can have multiple events; it does not replace `eventId`.
- `requestId` or message IDs have a different business scope; they should not be used as unique event IDs if one request generates multiple events.

When testing two replicas, attach `instanceId`/resource metadata if you need to know which replica emitted the event; avoid using high-cardinality values as global metric labels.

## 5. Fields to Verify After Aggregation

| Field | Suggested Assertion | Reason |
| --- | --- | --- |
| `timestamp` | Parses to UTC time, within a reasonable range | Prevents timezone/clock parsing bugs |
| `observedTimestamp` | Not unreasonably early/late compared to event time within tolerance | Detects delays or clock skew |
| `service.name` | Correct service and mapped to Resource if using OTel | Avoids accidentally querying all logs by body |
| `severity` | Correct level, does not turn WARN into INFO | Ensures filtering/alerting |
| `event.code` | Code from allowlist | Stable querying across text wording changes |
| `eventId`/`testRunId` | Present, matches emitted values | Cross-referencing and test isolation |
| `trace_id`/`span_id` | Valid format/scope and correlated | Pivoting to traces |
| `body` | Decoded string preserves meaning | Avoids losing newlines/quotes/Unicode |
| `errorCode`/exception attributes | Present only on error, does not omit needed details | Incident classification |
| `resource/attributes` | Correct host/container/service/environment | Route/replica investigation |
| `tenantRef` | Present only when allowed, no cross-tenant leakage | Access control and data isolation |
| Forbidden fields | No passwords, bearer tokens, raw body/headers | Privacy control |

If the backend has a JSON schema, **parse the JSON and assert field types**; do not compare key order. When using OpenTelemetry, verify whether a field is in **Resource, Attributes, Body**, or a LogRecord field as expected; a JSON key `service.name` in body text does not automatically become a resource attribute.

## 6. Basic E2E Scenario: Source to Query

~~~text
[Test runner]
    │ 1. Generate testRunId, eventId, and test trace ID
    ▼
[Java app]
    │ 2. Emit N safely classified events
    ▼
[stdout/file/OTLP]
    │ 3. Verify output/encoder at source
    ▼
[agent]
    │ 4. Verify read/parsing/offset
    ▼
[Collector]
    │ 5. Verify receiver, processor, exporter
    ▼
[test backend]
    │ 6. Query by testRunId with deadline
    ▼
[Test runner]
       7. Check count, IDs, fields, privacy, latency
       8. Report PASS/FAIL, collect diagnostics, cleanup
~~~

The log emission call **must not be used as the sole completion condition**. If a run fails, you need to know which stage lost the data; save agent and collector metrics/configs/logs along with `testRunId` for diagnosis.

**Test independence:** Each run needs its own prefix/ID or namespace, its own synthetic data, time limits, and controlled cleanup. Do not query "the last 5 ERROR lines" because other tests or real traffic may interfere.

## 7. Java 17 Example: HTTP Pipeline E2E Harness

The example below **runs standalone with JDK 17** and simulates a multi-stage pipeline within the same test suite:

~~~text
JUL Logger
   → JsonlHandler (serializes controlled metadata)
   → bounded queue
   → HTTP client sends batch
   → FakeCollector on localhost
   → in-memory list as test sink
   → assertions
~~~

The fake collector returns HTTP `503` on the first call, then returns `200` and stores **two JSONL records** in memory on retry. The test verifies content, correlation ID, JSON escaping, record count, and that no fake secret enters the output.

**Limitations to state clearly:** This is a **test harness E2E** (from Java handler to fake HTTP receiver) and **does not include a real agent/Collector, backend index, disk persistence, or production security**. It is suitable for learning and fast checks without Docker/Kubernetes, but does not replace real-environment tests in the following sections.

### 7.1. Create LoggingPipelineE2ETest.java

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LoggingPipelineE2ETest {
    record SafeEvent(String eventCode, String traceId) {}

    static String jsonString(String input) {
        StringBuilder out = new StringBuilder("\"");
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
                        out.append(String.format("\\u%04x", (int) c));
                    } else {
                        out.append(c);
                    }
            }
        }
        return out.append('"').toString();
    }

    static final class JsonlHandler extends Handler {
        final ArrayBlockingQueue<String> queue = new ArrayBlockingQueue<>(16);
        JsonlHandler() { setLevel(Level.ALL); }
        @Override public void publish(LogRecord record) {
            if (!isLoggable(record)) return;
            Object[] args = record.getParameters();
            if (args == null || args.length != 1 || !(args[0] instanceof SafeEvent)) {
                throw new IllegalArgumentException("safe event required");
            }
            SafeEvent safe = (SafeEvent) args[0];
            String json = "{"
                    + "\"timestamp\":" + jsonString(record.getInstant().toString())
                    + ",\"service.name\":\"order-service\""
                    + ",\"severity\":" + jsonString(record.getLevel().getName())
                    + ",\"event.code\":" + jsonString(safe.eventCode())
                    + ",\"trace_id\":" + jsonString(safe.traceId())
                    + ",\"body\":" + jsonString(record.getMessage())
                    + "}";
            if (!queue.offer(json)) {
                throw new IllegalStateException("test queue full");
            }
        }
        @Override public void flush() {}
        @Override public void close() {}
    }

    static final class FakeCollector implements AutoCloseable {
        final HttpServer server;
        final AtomicInteger requests = new AtomicInteger();
        final List<String> received = new CopyOnWriteArrayList<>();
        FakeCollector() throws IOException {
            server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
            server.createContext("/ingest", this::ingest);
            server.start();
        }
        void ingest(HttpExchange exchange) throws IOException {
            try {
                int n = requests.incrementAndGet();
                byte[] bytes = exchange.getRequestBody().readAllBytes();
                int status;
                if (!"POST".equals(exchange.getRequestMethod())) {
                    status = 405;
                } else if (n == 1) {
                    status = 503; // Deliberate transient failure.
                } else {
                    String batch = new String(bytes, StandardCharsets.UTF_8);
                    for (String line : batch.split("\\R")) {
                        if (!line.isEmpty()) received.add(line);
                    }
                    status = 200; // In-memory receipt, not a durable commit.
                }
                byte[] response = (status == 200 ? "ok" : "retry")
                        .getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(status, response.length);
                exchange.getResponseBody().write(response);
            } finally {
                exchange.close();
            }
        }
        URI endpoint() {
            return URI.create("http://127.0.0.1:" + server.getAddress().getPort()
                    + "/ingest");
        }
        @Override public void close() { server.stop(0); }
    }

    static void require(boolean valid, String what) {
        if (!valid) throw new AssertionError(what);
    }

    static void emit(Logger log, Level level, String body, SafeEvent safe,
                     String timestamp) {
        LogRecord record = new LogRecord(level, body);
        record.setLoggerName(log.getName());
        record.setInstant(Instant.parse(timestamp));
        record.setParameters(new Object[]{safe});
        log.log(record);
    }

    public static void main(String[] args) throws Exception {
        Logger log = Logger.getLogger("test.pipeline");
        boolean oldParent = log.getUseParentHandlers();
        Level oldLevel = log.getLevel();
        JsonlHandler source = new JsonlHandler();
        log.setUseParentHandlers(false);
        log.setLevel(Level.INFO);
        log.addHandler(source);

        try (FakeCollector collector = new FakeCollector()) {
            String trace = "0123456789abcdef0123456789abcdef";
            String secret = "TEST_SECRET_DO_NOT_LOG";
            emit(log, Level.INFO, "order accepted",
                    new SafeEvent("ORDER_ACCEPTED", trace),
                    "2026-11-10T02:00:00Z");
            emit(log, Level.WARNING, "provider said \"retry\"\nrequest queued",
                    new SafeEvent("PAYMENT_RETRY", trace),
                    "2026-11-10T02:00:01Z");

            List<String> batch = new ArrayList<>();
            source.queue.drainTo(batch);
            require(batch.size() == 2, "source event count");
            String payload = String.join("\n", batch) + "\n";
            require(!payload.contains(secret), "secret escaped source");
            System.out.println("PASS: source produced 2 structured events");

            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(2)).build();
            int status = 0;
            for (int attempt = 1; attempt <= 2; attempt++) {
                HttpRequest request = HttpRequest.newBuilder(collector.endpoint())
                        .timeout(Duration.ofSeconds(3))
                        .header("Content-Type", "application/x-ndjson")
                        .POST(HttpRequest.BodyPublishers.ofString(
                                payload, StandardCharsets.UTF_8)).build();
                HttpResponse<String> response = client.send(request,
                        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
                status = response.statusCode();
                if (status == 200) break;
                require(status == 503, "unexpected HTTP status");
            }
            require(status == 200 && collector.requests.get() == 2,
                    "retry and HTTP result");
            System.out.println("PASS: HTTP 503 retried to 200");

            List<String> records = collector.received;
            require(records.size() == 2
                    && records.get(0).contains("\"event.code\":\"ORDER_ACCEPTED\"")
                    && records.get(1).contains("\"event.code\":\"PAYMENT_RETRY\"")
                    && records.stream().allMatch(v ->
                        v.contains("\"trace_id\":\"" + trace + "\"")),
                    "collector records/correlation");
            System.out.println("PASS: collector received 2 correlated events");

            require(records.get(1).contains(
                    "\"body\":\"provider said \\\"retry\\\"\\nrequest queued\"")
                    && records.stream().noneMatch(v -> v.contains(secret)),
                    "JSON escape/privacy");
            System.out.println("PASS: escaped newline/quotes and no secret");
        } finally {
            log.removeHandler(source);
            log.setUseParentHandlers(oldParent);
            log.setLevel(oldLevel);
            source.close();
        }
    }
}
~~~

**APIs in the example:** JUL is built into `java.util.logging`; `HttpClient` belongs to `java.net.http`; `HttpServer` belongs to the `jdk.httpserver` module, which provides a lightweight HTTP server for testing. Use a **full JDK 17** to compile and run, not a stripped-down runtime that excludes this module.

### 7.2. Execution and Exact Output

~~~bash
javac --release 17 LoggingPipelineE2ETest.java
java LoggingPipelineE2ETest
~~~

**Stdout:**

~~~text
PASS: source produced 2 structured events
PASS: HTTP 503 retried to 200
PASS: collector received 2 correlated events
PASS: escaped newline/quotes and no secret
~~~

**Stderr:** empty. **Exit code:** `0` when all assertions pass. On failure, an `AssertionError` or exception fails the test.

### 7.3. What the Example Actually Proves

- `JsonlHandler` only accepts `SafeEvent`, creates an event with a fixed schema, and puts it into a bounded queue of size 16.
- Two events are emitted before transport; the batch is built from the queue and sent via an HTTP request.
- `FakeCollector` returns `503` on the first attempt, so the test shipper retries a second time.
- After the second attempt, the server returns `200` and two JSONL records are stored in an **in-memory list**.
- The event code and `trace_id` are present in the data reaching the test destination.
- A line containing quotes and a newline is escaped so it does not split into separate physical log records.
- A secret sentinel is declared in the application but is not included in the outgoing JSON.

### 7.4. What the Example Does Not Prove

- There is no shipper reading file/container logs, real OpenTelemetry Collector, standard receiver-side JSON parsing, indexing, or search API.
- `FakeCollector` **does not parse JSON into structured schema data**: it keeps raw JSONL strings. Assertions only check string patterns meaningful for this scenario.
- There is no durable queue, fsync, TLS/mTLS, authorization, backup, or retention.
- The first `503` is **pre-scripted and stores nothing**; the test does not simulate the case where the backend persisted the data but the ACK was lost, leading to duplicates.
- `HttpClient` and HTTP loopback operate within the test process/machine; they do not simulate a multi-node network.
- The queue of 16 is a test fixture, not a production backpressure solution. If full, the handler throws an exception to fail the test explicitly.
- The minimal JSON escape function is for instructional purposes and must not replace a proven JSON encoder in production.

You must still run **a real-environment E2E test** to verify all hops used by the production application.

## 8. Moving from a Fake Receiver to a Real Pipeline

To test a real system, choose a path with an explicit configuration:

**Path A — stdout/file → agent/filelog → Collector → backend**

~~~text
Java app
  → .jsonl file or stdout/container log
  → node agent/filelog receiver
  → JSON parser + timestamp/severity mapping
  → Collector processors
  → exporter
  → test backend
  → search/query API
~~~

**Path B — Java OpenTelemetry exporter → OTLP → Collector → backend**

~~~text
Java app + configured OTel logging bridge/SDK
  → OTLP/gRPC or OTLP/HTTP
  → Collector OTLP receiver
  → processors / exporter
  → test backend
  → search/query API
~~~

These two paths **are not automatically interchangeable**. An `application/x-ndjson` HTTP POST from the section 7 demo **is not an OTLP request**; sending it directly to an `otlp` receiver will not be processed as an OpenTelemetry LogRecord.

**Before testing**, document the backend/version configuration, ingress path, parser, output schema, query endpoint, deadlines, and permissions. If a production app writes to a file but the test uses direct OTLP, the test may miss bugs in file reading/rotation — in which case it is not truly E2E along the production path.

## 9. Collector filelog: Example for Testing JSONL Files

If using OpenTelemetry Collector Contrib or a distribution that includes the **`filelog` receiver**, you can create an `app.jsonl` file in a **test directory** and read it with the following pipeline:

~~~yaml
receivers:
  filelog:
    include:
      - /tmp/log-e2e-fixture/*.jsonl
    start_at: beginning
    operators:
      - type: json_parser
        parse_from: body

exporters:
  debug:
    verbosity: detailed

service:
  pipelines:
    logs:
      receivers: [filelog]
      exporters: [debug]
~~~

Save this as `otelcol-filelog.yaml`, then run a Collector distribution binary that includes the `filelog` component with the corresponding configuration and mount path. Example commands (binary name depends on the distribution):

~~~bash
otelcol-contrib validate --config=otelcol-filelog.yaml
otelcol-contrib --config=otelcol-filelog.yaml
~~~

**Key points to understand:**

- `filelog` is not included in every Collector core build; check `otelcol-contrib components` or the component list of your actual binary.
- `start_at: beginning` is suitable for fresh test fixtures; production has checkpoint/restart/retention and different requirements.
- `json_parser` reads the string in `body` and by default may place parsed keys into **attributes**. **This minimal configuration does not automatically map** `timestamp` and `severity` from the JSON fixture into the OpenTelemetry LogRecord Timestamp/SeverityNumber fields; you must add parsing/transforms per schema.
- The `debug` exporter prints data for observation **during testing**, and does not store an index or provide a durable search API.
- `/tmp/log-e2e-fixture/*.jsonl` is a path inside the **Collector process's filesystem**. When running in a container, you must mount the appropriate directory; host paths do not automatically appear inside the container.
- Files existing before the collector starts with `start_at: beginning` may be read from the start; to test checkpoint/restart, a dedicated test is required.
- You must verify that newlines/rotation/partial records are handled accurately by the actual agent, not just the JSON parser.

To truly verify **all the way to the log store**, replace the `debug` exporter with an exporter and test backend supported by your distribution, then query the backend endpoint. Never commit backend credentials into public config files.

## 10. Collector OTLP: Different Configuration from filelog

For **actual OTLP requests**, you can use a different minimal pipeline:

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

This is a **dev/test** configuration. An application must send **OTLP messages** via an SDK/bridge/exporter or a compatible converter; do not use the custom HTTP JSONL from `LoggingPipelineE2ETest` to call `/v1/logs` as if it were OTLP JSON encoding.

**Proper testing steps:**

1. Confirm the application is using the appropriate OTel logger provider/bridge/exporter, not just having the library in dependencies.
2. Start the Collector and verify the receiver is listening on the expected endpoint.
3. Emit a single test event.
4. Use the debug exporter to see it pass through the Collector and verify Resource/Attributes/Body mapping.
5. Replace the debug exporter with a test backend exporter and query the record after indexing.
6. Observe the exporter queue, retries, and metrics when the backend experiences transient errors.

Bind only to loopback in local tests. If the Collector is in another pod or machine, you need a reachable endpoint, authentication, and proper TLS; do not expose `0.0.0.0:4317` unconditionally to external networks.

## 11. Emitting Logs via stdout and Container Runtime

In Kubernetes, stdout/stderr from a Java container typically goes through the container runtime/CRI log and then a node-level agent. An E2E test must include the **CRI envelope unwrapping** step, not just parse JSON directly from a stdout source.

~~~text
Java JSONL stdout
    → runtime writes CRI log: timestamp stream flag body
    → agent parses CRI metadata
    → application JSON parser
    → Collector
    → backend
~~~

Failures to check:

- **CRI partial records** caused by long lines; the parser must reassemble them according to contract.
- Stream metadata stdout vs stderr must not be assumed by default to equal INFO vs ERROR.
- When a pod restarts or a node rotates files, the agent may miss, duplicate, or re-read records if checkpoints are incorrect.
- An event with raw newlines in a stack trace can be split; JSONL with escaped newlines preserves event boundaries if the encoder is correct.
- When a container is deleted, `kubectl logs` is not centralized history with guaranteed retention.
- If both a file appender and stdout are shipped, there is a risk of duplicates.

Do not test "app to collector" by bypassing the container runtime if production failures usually occur in rotation, CRI parsing, or agent permissions.

## 12. E2E Testing from Files and Rotation

For Java applications running on VMs or writing to files, the fixture should include:

- A newly created UTF-8 JSONL file in a dedicated directory.
- First and last events with IDs to verify the parser does not drop records.
- Unicode, escaped newlines, and exceptions matching the schema.
- File rename/rotate/truncate actions matching the real appender mechanism.
- Agent checkpoint and restart verification.
- Tests with both small files and large events near the parser limit.

Typical scenario:

~~~text
T0: start agent with dedicated test file path
T1: app writes EVT-1, EVT-2
T2: confirm query sees EVT-1, EVT-2
T3: rotate file via appender mechanism
T4: app writes EVT-3 to new file
T5: restart agent with checkpoint
T6: confirm EVT-1/2/3 per duplicate/loss policy
~~~

Do not use `copytruncate` or rename assuming every agent handles them identically; inode/path tracking, checkpoints, and fallbacks differ by product.

If a file is rotated before the agent has a chance to finish reading it, zero-loss cannot be claimed without an appropriate buffer/backpressure or retention policy.

## 13. Waiting for Backend Events with a Deadline, Not Blind Sleep

A good E2E test has an **eventual assertion**: after emitting events, query the backend by ID until the condition is met or the deadline expires.

Backend-neutral pseudo-code:

~~~java
// Pseudo-code, NOT a standalone runnable Java class.
// queryByTestRunId is the test backend's API adapter.
long deadlineNanos = System.nanoTime()
        + java.util.concurrent.TimeUnit.SECONDS.toNanos(30);

while (System.nanoTime() < deadlineNanos) {
    var records = queryByTestRunId(testRunId);
    if (records.stream().map(LogRecordView::eventId)
            .collect(java.util.stream.Collectors.toSet())
            .containsAll(expectedEventIds)) {
        verifySchemaAndPrivacy(records);
        return;
    }
    java.util.concurrent.locks.LockSupport.parkNanos(
            java.util.concurrent.TimeUnit.MILLISECONDS.toNanos(200));
}
throw new AssertionError("Expected E2E logs did not become queryable");
~~~

In production tests, handle query exceptions and stop polling cleanly. This is only a **timeout/poll concept** and does not declare `LogRecordView`, `expectedEventIds`, or the adapter.

Why is `Thread.sleep(1000)` followed by a single assert insufficient?

- Backend indexing is asynchronous; timing varies with CI and load.
- Network and batch windows can exceed 1 second.
- A test passing locally can become flaky on CI.
- A fixed long sleep slows down tests even when logs arrived long ago.

**Negative assertions are harder than positive ones:** "No secret found" or "no duplicates" is only meaningful after a proven processing milestone or an **observation window matching policy**. If the sink is silent due to misconfiguration, a negative test can falsely PASS; a positive event in the same scope is mandatory.

## 14. Checking Counts, Duplicates, and Ordering

Suppose you emit `N=10` events with unique event IDs:

- **Source:** all 10 events are created/captured.
- **Backend:** verify all 10 IDs appear within the test scope.
- **Duplicates:** count each ID; determine whether the contract allows retry duplicates or requires backend dedup.
- **Event order:** only assert ordering if the pipeline actually has an ordering contract in that scope.
- **Completeness:** verify no ID is missing, rather than just counting 10 arbitrary lines.

For example, a batch is sent, the backend stores it, but the response is lost:

~~~text
Agent sends eventId=evt-42
    → backend stores evt-42
    → response lost
    → agent retries evt-42
    → backend may now contain 2 copies
~~~

**At-least-once** prevents loss on retry but risks duplicates. **End-to-end exactly-once** requires dedup/transaction mechanisms across layers; it does not arise automatically from a Collector config.

Do not blindly dedup by body/timestamp: two distinct business events can be valid yet have identical text. Use `eventId` and an appropriate identity contract.

**Global ordering** across multiple services, partitions, and regions is usually not guaranteed. For protocols with ordering within a partition/connection, assert only within that contract's scope. Different system clocks also have clock skew.

## 15. Error Injection: Faults Worth Testing

| Injected Fault | Expectation to Verify | What Must Not Be Inferred |
| --- | --- | --- |
| Collector returns transient 503 | Shipper retries, backoff and metrics follow policy | 503 always means data was not received |
| Collector returns 400/invalid schema | Record rejected/quarantined clearly | Infinite retries will fix the data |
| Timeout/connection reset | Outcome unknown; retry may create duplicates | Certainty that the record did not reach destination |
| TLS handshake/auth failure | Alert raised and credentials not leaked | Turning off TLS to make tests pass |
| Collector restarts mid-batch | Checkpoint/queue/routing recovers per contract | Zero loss/duplicates without a durable queue |
| Disk full on agent | Error/drop/backpressure observed, not silent | Growing RAM buffer forever is safe |
| Backend rate limit | Bounded queue, retries, alert | Zero impact on business latency |
| Backend index reject | Event may have reached exporter but is not queryable | HTTP 200 at Collector is enough |
| File rotation mid-stream | Cursor/checkpoint follows product mechanism | All file tailers behave the same |
| Pod force-killed | Loss within stated bounds, recovery if supported | Shutdown hook always flushes |
| Processor drops/masks wrongly | Missing event/field or leaked secret detected | Debug exporter always matches final output |
| Collector OOM/restart | Health/queue/drop metrics alert | Receiving a request means durable |

**Do not run destructive chaos tests in production** without an established process and isolation boundaries. Use a test namespace, mock server, test broker, or staging environment with synthetic data and a cleanup plan.

## 16. Retry, Backoff, and Backpressure: Testing the Right Semantics

A transport pipeline may use queues, batching, retries, and backpressure. E2E tests need to verify **decisions when delivery fails**.

- On transient 503 errors, retry according to the retryable status policy, up to the defined max attempts or duration.
- On 400 errors due to invalid schema, retrying the same payload may be futile; clearly reject/quarantine with a metric.
- When the queue is full, policy must be block, drop, disk spool, or fail-fast per event; do not fabricate zero-loss.
- When the broker/backend is slow, queues must not grow unboundedly and cause OOM.
- On shutdown, wait for flush/drain if time remains; a forced kill prevents the process from continuing to flush.
- When an ACK response is lost, retries can create duplicates, requiring IDs/dedup per contract.

With a **fake HTTP receiver** test, log the actual retry count and statuses to avoid guessing. The demo performs **exactly one retry** after `503`; it has no exponential backoff because it is just a fast fixture, **not a production-ready policy**.

Run two separate tests: "503 before commit" and "commit succeeded but ACK lost". The delivery semantics differ even though the caller sees an error in both.

## 17. Verifying Timestamp and Correlation Accuracy

A pipeline can distort time:

- Java emits ISO 8601 UTC, but the parser interprets it in the Collector machine's timezone.
- The agent assigns file read time instead of event timestamp.
- The Collector overwrites the timestamp in an enrichment stage.
- The backend queries by ingest time while the dashboard displays event time.
- Clock skew between nodes causes "event occurred before request".

Tests should preserve and compare:

~~~text
event.timestamp
collector.observed_timestamp
backend.ingested_at
trace_id / request_id
event_id
~~~

`ingestLatencyMs` can be computed between milestones **when clocks are synchronized or within an appropriate tolerance**. Do not take the raw difference between two unsynchronized hosts as proof of millisecond-accurate latency.

With OpenTelemetry, `TraceId` and `SpanId` are dedicated LogRecord fields; if `trace_id` only exists as a string in attributes/body, the backend may not support automatic log-to-trace linking. Tests must verify the actual mapping, not just `contains(traceId)`.

**Security note:** trace IDs/correlation IDs can link multiple activities and may fall under protected data scope. Do not put emails, bearer tokens, or raw user IDs into baggage just to correlate logs.

## 18. Structured Logs: Parsing, Transformation, and Schema Compatibility

An E2E test must assert **post-parser data semantics**, not just the raw string.

For example, the source emits:

~~~json
{"timestamp":"2026-11-10T02:00:00Z","severity":"WARNING","event.code":"PAYMENT_RETRY","attempt":2,"credentialPresent":false}
~~~

After the Collector, the contract might require:

- `timestamp` becomes event time, not a body string.
- `severity` is normalized with the proper mapping (JUL WARNING → corresponding WARN).
- `event.code` becomes a string-typed attribute.
- `attempt` remains a number, `credentialPresent` remains a boolean.
- `service.name` resides in Resource if using OpenTelemetry.
- `Body` is the message or object per the chosen schema, not automatically containing every attribute.

If the schema changes from `event.code` to `eventCode`, you must decide on versioning, aliases, or query migration. Do not silently rename keys in a collector processor and break dashboards.

**Multiline:** An exception has a multi-line stack trace. Text-file tailing requires a multiline parser; structured JSONL with a proper encoder keeps one event on one physical line. Test newlines, quotes, backslashes, Unicode, and long/partial records according to the real runtime.

## 19. Privacy and Security in the E2E Pipeline

Centralized logs can contain data from multiple systems and tenants. Therefore, sensitive data tests must run **from source to final destination**, not just unit-test a masking function.

Use a **synthetic sentinel** with high specificity, such as `TEST_SECRET_DO_NOT_LOG`; never put real API keys, real passwords, or production PII into fixtures.

Verify:

1. Source events do not contain passwords, tokens, full HTTP headers, or raw request bodies.
2. Regex/transforms in the agent/Collector do not leak values into new keys.
3. Exception messages, stack traces, MDC/ThreadContext, and suppressed/cause exceptions are not overlooked.
4. The JSON serializer escapes CR/LF/quotes, preventing fake events via log injection.
5. Backend index/query/export contains no sentinel in any field, raw message, or attributes.
6. Secrets are not emitted into debug exporters, processor error logs, retry dead-letter/quarantine, or metric labels.
7. Log read permissions match tenant and role; unauthorized users cannot read records.
8. Stored/backed-up/exported data has its own retention and encryption policies applied.

A **negative assertion** (token not found) must be paired with a **positive assertion** (safe event ID emitted in the same run is found) to avoid false PASSes when the pipeline is broken and receives nothing.

Do not equate UI dashboard masking with removing raw data from the index, queues, backups, or prior exports.

## 20. Load Testing, Latency, and Sampling

E2E tests are not just for a single record. For high-throughput systems, check:

- Source and sink events/sec within the same observation window.
- p50/p95/p99 latency from source to searchable, accounting for clock skew.
- Queue depth, dropped records, retry rate, and exporter failures.
- Java service CPU/heap/GC, shipper/Collector CPU/memory.
- Disk write rate, spool usage, checkpoint lag.
- Batch size, batch timeout, and network utilization.
- Parser reject rate, truncated events, oversized records.
- Backend query latency and index size.
- Sampling strategy and rate limiting when DEBUG/TRACE is enabled.

**Sampling:** If the pipeline only samples 10% of DEBUG events, an E2E test cannot require every DEBUG event to be stored. Tests must know the **policy** and use events guaranteed not to be sampled (or check statistical ratios with a sufficiently large sample).

**Mandatory audit logs** must not be sent through a pipeline with only sampling/best-effort guarantees if policy requires complete retention. Use a durable recorder/outbox/audit store and test it separately.

## 21. Measuring the Health of the Pipeline Itself

A pipeline can silently lose logs even while the app continues processing requests. Thus, metrics are needed at the source and each hop.

| Stage | Metrics to Monitor | Warning Signals |
| --- | --- | --- |
| Java application | Total created/filtered events, appender drops, queue fill | Logger unintentionally disabled, queue overflow |
| Agent/file tail | Files read, bytes/records, cursor lag, parse errors | New files not read, rotation missed |
| Collector receiver | Accepted/rejected log records | Source sends but receiver count does not rise |
| Processor | Filtered/dropped records, parse/transform failures | Events dropped or schema invalid |
| Exporter | Sent/failed records, retry count, pending queue | Backend unavailable, queue growing continuously |
| Backend | Ingest rate, rejected docs, indexing delay | Export succeeds but records are not queryable |
| Search UI/API | Query errors, latency, auth failures | Users cannot search or scope is wrong |

**Specific metric names depend on version/distribution.** OpenTelemetry Collector has internal telemetry for accepted/refused/sent/failed records and queues; check the documentation and metrics exposed by the running build rather than hard-coding a guessed metric name and concluding there is no data.

Consider a **periodic canary log event** in pipeline monitoring, with a unique ID/timestamp and an alert if it is not seen at the sink past the deadline. However, canaries must be rate-limited, contain no secrets, and not replace real traffic metrics.

## 22. Designing Repeatable CI/Staging Tests

An E2E pipeline test should run in an isolated environment with a clear lifecycle:

~~~text
CI job
  ├─ allocate testRunId and create temp namespace/filesystem
  ├─ start test backend + appropriate Collector/agent
  ├─ check readiness and config validation
  ├─ run Java app emitting fixture events
  ├─ await ingest/search with deadline
  ├─ verify IDs/count/schema/security/correlation
  ├─ fault injection if part of scenario
  ├─ save secret-scrubbed diagnostics on FAIL
  └─ stop containers / delete test data
~~~

**Not every step runs in the same process.** For example, `LoggingPipelineE2ETest` is only sufficient for a developer-level "Java handler → fake HTTP receiver" check. In advanced CI, use a test backend with an independent query API and a real Collector distribution.

**Keep tests reproducible:**

- Pin Java, appender, Collector distribution, and backend image versions in CI when needed.
- Use versioned configs and validate them before running.
- Do not share the root logger or production log files.
- Do not share `testRunId` across CI jobs.
- Wait for real health/readiness instead of fixed sleeps.
- Set timeouts per hop and for the overall test.
- Clean up in `finally`/CI post-job; do not delete out-of-scope resources.
- Mask secrets when saving test runner logs for debugging.

If a test uses dynamically allocated network ports, print the address in internal diagnostics when needed without logging credentials. If an endpoint is only for local testing, bind to loopback and restrict permissions.

## 23. Kubernetes filelog E2E Testing: Must-Have Scenarios

When production runs on Kubernetes, add these scenarios:

| Scenario | Test Activity | Expectation |
| --- | --- | --- |
| Normal pod | Emit two JSONL events | Agent receives and backend queries exact IDs |
| Pod restart | Restart app after emit | Shipped events remain queryable; pending per contract |
| Node agent restart | Restart DaemonSet agent | Checkpoint causes no loss/duplicates beyond stated bounds |
| Log rotation | Write near limit then rotate | Agent continues reading records after rotation |
| Partial CRI record | One very long event | Parser reassembles properly or rejects/quarantines with metric |
| Multiline stack trace | Multi-line exception | One logical log event, not split into fake ERRORs |
| Mixed stdout/stderr | Both streams | Preserves stream labels, no wrong default severity |
| Pod scaling | N instances emitting concurrently | Instance metadata accurate, no cross-querying |
| Multi-tenant | Two namespaces/tenants | Queries enforce scope, no cross-reads |
| Node disk pressure | Agent falls behind shipping | Alerts/drops/backpressure per policy |

Do not run high-pressure tests directly on a production cluster. In staging, strictly bound the namespace, resources, duration, and log volume emitted.

Note: Kubelet/container runtime has local storage limits and rotation mechanisms; `kubectl logs` only aids diagnostics and does not guarantee long-term centralized log retention.

## 24. Runbook When an E2E Test Fails

When a test emits events but the final query finds nothing, trace from source to destination:

1. **JVM:** was the event created properly? Did level/filter/appender accept it? Does `LogRecord` have safe body/fields?
2. **Sink:** did stdout/file/OTLP send it? Are there flushes, bounded queues, or write errors?
3. **Container/file:** are CRI format, permissions, rotation, or partial logs interfering?
4. **Agent:** are include/exclude paths, checkpoints, cursors, parse errors, or pending batches correct?
5. **Collector:** is the receiver both declared **and** used in `service.pipelines.logs`? Is a processor filtering/dropping/transforming wrongly?
6. **Exporter:** are there endpoint/TLS/token/quota/retry/queue errors? Are send errors monitored?
7. **Backend:** did it receive the request and parse/index it? Are the query index/tenant/time window correct?
8. **Dashboard:** are timezone, field mapping, or permissions hiding or misfiltering the query?

Quick troubleshooting table:

| Symptom | First Hypothesis | Evidence to Collect |
| --- | --- | --- |
| JVM logs, stdout empty | Different appender filter/route, async not flushed | Appender config and source metrics |
| stdout present, collector empty | Agent not tailing, CRI parse error, file permissions | Agent metrics, file cursor |
| Collector debug exporter sees it, backend doesn't | Exporter auth/network/schema/index reject | Exporter logs, backend ingest errors |
| Backend has record, ID query misses | Wrong field mapping or wrong tenant/time query | Raw indexed document, mapping, and query |
| Event duplicated twice | Shipped from two sources or retry after lost ACK | Source labels, event ID, exporter retries |
| Only WARN missing | Wrong severity mapping/filter | Raw LogRecord, pipeline processors |
| Timestamp far from current time | Locale/timezone/parser or clock skew | Event/observed/index timestamps |
| Newline creates extra log records | Wrong JSON escaping or multiline handling | Raw bytes/filelog parser |
| Secret appears in backend | App logged raw data, layout didn't redact, or alternate ship path | Event chain and per-hop outputs |
| Test fails only on CI | Async timing, shared state, fixed sleep | Deadline logs, `testRunId`, readiness |

Do not increase `queueSize` or sleep times indefinitely to "fix" a failing test before knowing which stage lost the data.

## 25. Anti-Patterns in End-to-End Log Testing

| Anti-Pattern | Why It Is Dangerous | Solution |
| --- | --- | --- |
| Only verifying `logger.info` and calling it E2E | Does not test transport | Query at the final sink |
| Treating HTTP `200` as durable commit by default | ACKs have different semantics | Read endpoint contract and test persistence |
| Sending JSONL to an OTLP receiver | Wrong protocol | Use filelog/agent or a real OTLP exporter |
| Querying "latest ERROR" | Noise from other tests | Unique `testRunId`/`eventId` |
| Comparing a free-form log message string | Fragile across format/locale changes | Assert typed fields and event code |
| Testing with `Thread.sleep(1000)` | Flaky under load | Poll/await with a deadline |
| Negative test without positive control | False PASS when pipeline is dead | Verify safe control event is present |
| Not checking for duplicates | Retries cause miscounts | Compare distinct event IDs and counts |
| Asserting global ordering | Multi-thread/multi-node can reorder | Test within the ordering contract scope |
| Not testing file rotation | Records lost on agent restart/rename | Test checkpoint + rotation |
| Ignoring container wrapper | JSON parser receives CRI envelope | Parse CRI before application JSON |
| Assuming `start_at: beginning` is a production policy | Can re-read old logs, causing duplicates | Choose explicit policy/checkpoint |
| Using debug exporter as a durable backend | Only prints data for testing | Test storage and querying separately |
| Not isolating network and resources | Causes interference or writes to production | Local/test namespace, fake secrets |
| Logging raw payloads "to verify" | Leaks PII/tokens and increases ingest cost | Structured safe fields and fake sentinels |
| Retrying 400 infinitely | Does not fix malformed records | Quarantine/reject with a metric |
| Claiming "no log loss" with a RAM queue | Crash loses pending records | Durable buffer if required, test crashes |
| Not monitoring pipeline health | Silent log loss | Internal metrics, canaries, and alerts |

## 26. Checklist for Executing a Proper E2E Test

1. Is there a clear diagram of source → sink → agent → Collector → backend → query?
2. Is there a unique **testRunId** and **eventId** for each test run?
3. Is the success contract defined: received, exported, searchable, or durable?
4. Are schema/version, timestamp, severity, Resource, and attributes configured?
5. Are JSON escaping, Unicode, multiline, and event size tested?
6. Does the test actually follow the production path (stdout/file + agent or OTLP), without mismatched substitution?
7. If using filelog, does the Collector binary include the component and have the right path/mount?
8. Does the receiver actually appear in `service.pipelines.logs`?
9. Are processor mappings and the exporter to a real backend verified in integration tests?
10. Do you query by ID with a deadline and check all expected event IDs?
11. Are duplicates, dropped/rejected events, retries, and unknown outcomes checked?
12. Do you distinguish callback/HTTP ACK from backend indexing or durability?
13. Are queues, sender/receiver/exporter metrics, and parsing failures monitored?
14. Are collector outages, malformed records, rotation, and agent restarts tested within risk scope?
15. Is there a positive control for every negative assertion, especially secret-leak checks?
16. Are tenant log view/export permissions and retention policies tested?
17. Is there controlled cleanup, with no real secrets or real user data?
18. Are safe diagnostics saved on CI FAIL, along with a recovery scenario?
19. Do you avoid relying on global clocks or unguaranteed event ordering?
20. Are the things the test **does not prove** explicitly documented, especially durability on crash/power loss?

## 27. Self-Check Questions

1. Why does a passing mock test for `logger.info(...)` still not prove the Collector works?
2. Distinguish `received by collector`, `exported`, and `queryable`.
3. Why must `testRunId` be unique across CI jobs?
4. How does `eventId` help detect duplicates?
5. Why doesn't a JSONL body automatically become an OpenTelemetry LogRecord via an OTLP receiver?
6. In `filelog`, what are the roles of `include`, `start_at`, and `json_parser`?
7. Why doesn't `json_parser` map timestamp/severity to OTel standards by default without extra configuration?
8. Does the Java 17 `LoggingPipelineE2ETest` use a real Collector or backend index?
9. Why can a `503` status after a request lead to duplicates on retry?
10. Does a query finding no event after 500 ms prove the record was lost?
11. Why does a "contains no token" test also need to test that an event appeared?
12. When timezone changes or clocks skew, what affects time-based queries?
13. In Kubernetes, what CRI/rotation factors must the agent handle?
14. When a backend index rejects a document due to schema, which hop's metrics help detect it?
15. When is a durable queue needed instead of a memory queue?
16. Can a single `trace_id` be used as the unique event ID for every log event?
17. Does an E2E test of "two records, one retry" prove end-to-end exactly-once delivery?
18. Why should the Collector be monitored with internal telemetry and canaries?

**Answer hints:** (1) all hops after Java are still missing; (2) distinct milestones, only queryable once the backend has processed it; (3) avoids reading old logs/other tests; (4) count occurrences per ID; (5) different protocol and data model; (6) select files, read position, and parse; (7) requires explicit mapping; (8) no, fake receiver stores in RAM; (9) ACK may be lost after backend received it; (10) not yet, ingestion is asynchronous; (11) a dead pipeline also shows no token; (12) event/index time/query window; (13) envelope, partial records, checkpoint, rotation; (14) exporter/backend ingest; (15) when loss prevention across process restart/crash is required by contract; (16) no, one trace has many events; (17) no; (18) to detect silent pipeline failures.

## 28. Official References

- [OpenTelemetry — Collector Configuration](https://opentelemetry.io/docs/collector/configuration/): `receivers/processors/exporters/service.pipelines` structure, configuration, and validation.
- [OpenTelemetry — Collector Components](https://opentelemetry.io/docs/collector/components/): receivers, processors, exporters, connectors, and distributions.
- [OpenTelemetry — Collector Troubleshooting](https://opentelemetry.io/docs/collector/troubleshooting/): debug exporter, internal telemetry, diagnosing lost data in the pipeline.
- [OpenTelemetry Collector Contrib — filelog receiver](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/receiver/filelogreceiver/README.md): `include`, `start_at`, tailing/checkpoints.
- [OpenTelemetry Collector Contrib — json_parser operator](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/pkg/stanza/docs/operators/json_parser.md): `parse_from`/`parse_to`, timestamp/severity handling.
- [OpenTelemetry — Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/): timestamp, observed timestamp, body, severity, Resource, attributes, TraceId.
- [OpenTelemetry — Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/): `service.name` and resource/telemetry fields.
- [Kubernetes — Logging Architecture](https://kubernetes.io/docs/concepts/cluster-administration/logging/): stdout/stderr, CRI logs, node agent, sidecar, log rotation.
- [Java SE 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): logger, levels, and LogRecord.
- [Java SE 17 — java.util.logging.Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html): `publish`, `flush`, and lifecycle.
- [Java SE 17 — LogRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html): message, parameters, timestamp, and metadata.
- [Java SE 17 — java.net.http.HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): HTTP client used in the harness.
- [Java SE 17 — jdk.httpserver](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/module-summary.html): HTTP server for testing.
- [Logback — Appenders](https://logback.qos.ch/manual/appenders.html): console/file/async, flush, and lifecycle.
- [Apache Log4j 2 — Appenders](https://logging.apache.org/log4j/2.x/manual/appenders.html): logging sinks, buffering, and flush.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): log injection, sensitive data, secure transport/storage.
