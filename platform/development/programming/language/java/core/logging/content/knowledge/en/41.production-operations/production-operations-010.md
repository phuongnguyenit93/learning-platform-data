# Post-Deployment Verification of Java Logging Systems in Production

## 1. Objectives of Post-Deployment Verification

**Post-deployment verification** is the process of confirming that the logging configuration and log transport pipeline **actually work in the new release**, not just in source code or test environments. A service may start successfully, return HTTP 200, and pass readiness probes yet **still fail to send logs** because of an incorrect logger level, an unloaded appender, missing file write permissions, an agent unable to read stdout/files, collector rejections, or data not yet being queryable in the backend.

For Java applications using JUL, SLF4J, Logback, Log4j 2, or OpenTelemetry, the goal is to verify **end-to-end** across clearly defined boundaries:

```text
Business execution / smoke request
           |
           v
Logger receives invocation
           |
           v
Backend creates/formats event
           |
           v
Console / file / appender / OTLP exporter
           |
           v
Agent / Collector receives and processes
           |
           v
Backend stores/indexes log
           |
           v
Explore / dashboard can query it
           |
           v
Alert / runbook operates per policy
```

A successful `logger.info(...)` call only proves **that code path executed**; it does not prove the event reached a file, was picked up by a shipper, or appeared on a dashboard. Conversely, a dashboard returning "No data" is not enough to conclude the application is not logging: it could be due to wrong labels, timezone, query permissions, sampling, ingestion delay, or retention.

After this lesson, learners can:
- Define logging acceptance criteria before rollout.
- Inspect runtime log levels, formatters, appenders, files/stdout, Java configuration, and environment settings.
- Use a **non-sensitive** canary event to verify from source to storage, including latency.
- Verify correlation ID/trace ID, status, route, service name, version, and schema consistency.
- Evaluate queues, retries, dropped logs, collector metrics, rotation, and rollback capability.
- Execute a standalone Java 17+ smoke test with an HTTP server and an in-memory log-capturing handler.
- Design CI/CD gates, checklists, test evidence, and handling procedures when the log pipeline fails.

This lesson belongs to **Production Operations**. Direct actions in production must follow approved permissions and change windows. Do not enable global DEBUG, do not intentionally take down collectors, and do not send real tokens just to "see logs".

## 2. When Should Verification Be Run?

Not only after a major release. You should verify when:
1. Deploying a new application version, adding dependencies, or changing Spring Boot/JVM configuration.
2. Changing `logback-spring.xml`, `log4j2.xml`, `logging.properties`, encoders, or levels.
3. Changing image/container runtime, user/UID, mounts, or log paths.
4. Changing collector, agent, sidecar, OTLP endpoint, TLS, credentials, or network policies.
5. Migrating file logging to stdout, stdout to OTLP, or switching log storage providers.
6. Changing sampling, masking, retention, parsers, index labels, or dashboards/alerts.
7. Scaling replicas, performing canary/blue-green rollouts, or changing async request processing strategies.
8. After incidents involving missing logs, duplicate events, lost trace correlation, or data exposure.

**Operational principle:** treat logging verification as part of release criteria, not an "inspect when free" step. A release with working business functionality that loses all operational/audit logs may violate security and compliance policies.

## 3. Pre-Verification Preparation: Know What You Expect to See

Before deployment, document the service's **observability contract**:

| Item | Example Value | Acceptance Criteria |
| --- | --- | --- |
| Service, environment | `orders-api` / `prod` | Logs from the right source, not mixed with staging |
| Deployment identity | image digest, version, commit ID | New events can be tied to the release |
| Effective log level | root INFO, component WARN | ERROR is not suppressed and DEBUG is not accidentally enabled |
| Sink | stdout, rolling file, or OTLP | An active transport path exists |
| Event schema | `event`, `service`, `status`, `route`, `duration_ms` | Parseable, with correct types and units |
| Correlation | `correlation_id` and/or W3C `trace_id` | Can trace from request to event/trace |
| Ingestion freshness | Per internal SLO | Canary appears within the approved deadline |
| Log loss | 0 dropped events for mandatory paths | Metrics exist to detect queue/delivery failures |
| Privacy | No passwords, tokens, raw bodies | Synthetic canary secrets do not appear in sinks |
| Operational config | rotation, quota, retention, RBAC | Does not fill disk or expose logs publicly |
| Alerting | 5xx/collector failure/no-data | Correct source, alert routing, and runbook |

**There is no single fixed deadline that fits every system.** For example, one environment may target "canary searchable within 60 seconds," while another has longer batching/queueing. Choose thresholds based on architecture, load, and organizational investigation goals; explicitly document the wait timeout and the action to take when exceeded.

### 3.1. Choosing Repeatable Evidence

Record in the release log or change management system:
- Release/commit/image digest, deployment timestamp, cluster/namespace, service/env.
- List of critical log paths/sinks verified.
- Random canary event ID, **containing no personal data**.
- Emission timestamp at the application and first searchable timestamp in the backend.
- Log query results, event count, and schema, safely summarized.
- Exporter/collector metrics for accepted, failed, dropped, and queue size.
- PASS/FAIL status, approver, and rollout hold/rollback decision.

Do not copy raw production logs containing PII into tickets as proof. Use only canary IDs, safe summaries, or controlled links.

## 4. Verifying the Application and Process Layer After Deployment

### 4.1. Confirm the Release Is Actually Running

Before checking logs, confirm:
1. The deployment/pod/instance is running the expected version or image digest.
2. Startup/readiness/liveness probes are not failing continuously.
3. There are no restart loops, OOMKills, or abnormal JVM shutdowns.
4. Log configuration sources (profiles, environment variables, mounted files, system properties) match the target environment.
5. There is no discrepancy between the canary pod and the remaining replicas.

Readiness **does not prove the logging pipeline works** unless the health check is explicitly designed to verify it. However, checking process health prevents blaming logging when the service itself failed to start.

### 4.2. Questions When Reading Startup Logs

Check whether:
- The expected backend (Logback/Log4j 2/JUL) was initialized.
- There are appender configuration errors, missing directories, permission denied, invalid encoders, or missing plugins.
- There are warnings related to the OTLP endpoint, TLS handshake, DNS, credentials, clock, or queue.
- Startup logs print passwords, connection strings, or tokens.
- There is excessive duplicate logging due to logger additivity, JUL ↔ SLF4J bridge loops, or multiple appenders.
- **Service name/environment/version** are declared accurately on events/collectors.

For asynchronous network appenders, a startup log saying "exporter initialized" **does not mean** a batch has been received. You need the end-to-end canary in section 7.

## 5. Verifying Effective Log Levels and Active Configuration

### 5.1. Runtime Levels Differ from Configuration Files

A service may have `logging.level.root=INFO` in source code, but the deployment environment can override it via:
- Spring profile or environment variable.
- Java system property / command-line argument.
- Configuration server or mounted config file.
- Runtime log level modification API (when permitted).
- Level inherited from a parent logger or backend configuration.
- Filter/appender threshold blocking a specific route.

Merely reading a config file does not prove the **effective** log level. With Spring Boot Actuator (e.g., version 3.5), the `loggers` endpoint can return both:
- `configuredLevel`: the level explicitly assigned to that logger, which may be `null`.
- `effectiveLevel`: the active level computed by the backend from configuration/inheritance.

Example read-only call in a **test environment or secured management endpoint**:

```bash
curl --fail --silent \
  http://127.0.0.1:8080/actuator/loggers/com.example.orders
```

An **illustrative** response, not a guaranteed output of every service:

```json
{
  "configuredLevel": null,
  "effectiveLevel": "INFO"
}
```

The endpoint only works if Actuator is present, exposed, and authorized for the caller. **Do not expose `/actuator/loggers` to the public internet**; some configurations allow changing log levels at runtime, so authentication/authorization is required.

### 5.2. Levels to Test

| Scenario | Expected Behavior |
| --- | --- |
| Normal successful request | INFO event or metric per policy; no ERROR flood |
| Expected business error | INFO/WARN per taxonomy, not misclassified as SEVERE |
| Unexpected system error | Useful ERROR/SEVERE event with error code and correlation |
| DEBUG/TRACE in production | Not accidentally enabled for sensitive components |
| INFO event when logger effective is WARN | May **not be emitted**; this is correct filtering |
| Error at appender/collector | Must have a separate transport failure signal |

Do not assume `logging.level.root=ERROR` is "safest": it can silence required access/audit events or operational signals. Appropriate configuration depends on application requirements.

**Do not POST log level changes in production just to test** without an approval workflow and a revert plan. If temporary DEBUG is needed for investigation, scope it to a specific logger, set a time limit, assess security impact, and assign an owner.

## 6. Inspecting Events at the Output Near the Application

Depending on the architecture, inspect the right output point:
- **stdout/stderr:** container/systemd console logs; check whether raw output has the right format/level.
- **file appender:** verify the new file is actually created, check owner/group/ACL, size, rotation, write permissions, and tail/shipper access.
- **OTLP exporter:** confirm the appender/bridge/instrumentation attaches logs to the OTel SDK, not only the tracer.
- **systemd journal:** inspect the journal by unit/service, but do not assume a copy has reached the collector.
- **agent-side buffer:** check discovered sources, paths/positions/offsets, and parse errors.

An event appearing only in pod stdout but not found in Loki/Elastic/OpenSearch **is not an E2E PASS**. It narrows the fault down to the runtime log driver, agent, network, collector, or backend.

### 6.1. Format Verification Rules

Pick a known event (startup, smoke request, or canary) and verify:
1. Every record has a timezone-aware timestamp, or an internal timestamp mapped accurately.
2. `service`/`environment`/`version` are consistent with the release.
3. `event`/`error_code` uses stable names, not fragile free-text strings.
4. `level` is normalized per schema; no `SEVERE`/`ERROR` mismatch from bad mapping.
5. Numeric fields such as `duration_ms` and `status` have the right type and unit.
6. Request route is `/orders/{id}`, not a raw path containing email/token/ID.
7. JSON/logfmt parses cleanly; CR/LF does not forge extra records.
8. `trace_id`/`span_id` have valid values or are omitted when there is no active span.
9. Events do not log Authorization headers, Cookies, passwords, tokens, or sensitive query strings.
10. A single request is not accidentally logged twice at the same layer due to additivity/filters/sidecars.

### 6.2. Do Not Judge by Old Logs Alone

After deployment, filter by **release identity + recent time**. If a dashboard still shows pre-deploy logs or events from an old-version replica, you may falsely assume the new system is shipping properly.

Use labels/fields with appropriate reliability, for example:
- `service.name=orders-api`;
- `deployment.environment=prod`;
- `service.version=2026.11.10`;
- `instance/pod` only when distinguishing replicas and permitted.

Field names depend on the OpenTelemetry/Grafana/Elastic pipeline; do not assume they are attached automatically. Use real deployment config/metadata, never raw client headers to identify the environment.

## 7. E2E Canary: From Application to Queryable Storage

A **canary logging event** is a test event with harmless data that travels through the **exact transport path** used by production logs. The goal is to prove the event:
1. Is generated by the right service version.
2. Is processed by the logging backend.
3. Is received and exported by the agent/collector.
4. Can be found in log storage via an authorized query.
5. Appears within the defined freshness SLO.

### 7.1. Applicable Procedure

1. Generate a random `probe_id` unique to the release; do not use real emails/accounts.
2. Send a smoke request to an **approved** endpoint or trigger an operational event with a safe schema.
3. Record the UTC timestamp of the request and expected service/version/route.
4. Verify the event at the local sink (stdout/file/test appender).
5. Monitor exporter/collector accepted/sent/failed metrics if available.
6. Query the backend by `probe_id`, service, and a narrow time range; do not query the entire log store.
7. Compare the actual event against the schema; verify the expected record count.
8. Compute `freshness = first_searchable_time - event_time`, accounting for clock skew and how the system timestamps records.
9. Record the result and do not poll indefinitely; if the deadline expires, mark **FAIL/UNVERIFIED** per policy.
10. Verify the canary triggers no real business side effects, leaks no secrets, and does not become a false alert.

**Distinguish the milestones:**

```text
emit_time -> enqueue_time -> exporter_ack_time -> ingest_time -> searchable_time
```

An export ACK **does not always mean searchable**. An exporter may receive an acknowledgement from the collector while the collector is still batching, retrying, or storage has not indexed it yet. Therefore, the "visible on dashboard" criterion must be checked at the real backend/query endpoint.

### 7.2. What Should a Canary Not Contain?

Never use real passwords, session cookies, API tokens, customer information, account numbers, or real business payloads. Use synthetic test IDs, event codes, and a test route that causes no unintended mutations.

If **redaction** must be tested, use a special dummy string like `FAKE_SECRET` **only in an authorized test environment**; do not turn a security test into injecting strange headers into production without approval. A production probe should focus on minimal metadata and a safe route.

### 7.3. Misreading Canary Results

| Observed Result | What Can Be Inferred | What Cannot Be Inferred Yet |
| --- | --- | --- |
| App log has event | Local appender or sink received it | Collector received it |
| Collector receiver accepted increases | Collector received data at receiver | Backend stored it successfully |
| Exporter sent increases | Exporter confirmed send per contract | Record is immediately searchable |
| Backend query finds canary | Path to backend/query works for canary | No other requests are being dropped |
| Canary not found | There is a point to investigate | Logger was definitely not called |
| Two events share the same probe ID | Possible duplication | Producer definitely sent two requests |

A passing canary is good evidence for the tested path, **not an absolute guarantee for all traffic**. Combine it with pipeline metrics, retention, sampling, and controlled failure tests.

## 8. Standalone Java 17+ Example: HTTP Smoke Test and Local Access Log Verification

The following code uses **pure JDK**: `com.sun.net.httpserver.HttpServer` to serve HTTP on `127.0.0.1`, `HttpClient` to send two requests, `java.util.logging` (JUL) to record access events, and an in-memory `Handler` to inspect logs. No Spring Boot, Maven, or external services are required.

What the example verifies:
- The health endpoint returns 200.
- The probe request returns 200.
- Exactly two events reach the local handler.
- `correlation_id` is included in the event in a validated format.
- The logged route is the template `/orders/{id}`, not the raw path `/orders/42`.
- Headers/URLs containing a **dummy secret** only for local redaction testing do not appear in the events.
- stdout prints predictable test results rather than fluctuating timing measurements.

Create **`PostDeployLoggingDemo.java`**:

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class PostDeployLoggingDemo {
    private static final Logger ACCESS =
            Logger.getAnonymousLogger();

    private static final class Capture extends Handler {
        private final List<LogRecord> records = new ArrayList<>();
        final CountDownLatch received = new CountDownLatch(2);

        @Override
        public synchronized void publish(LogRecord record) {
            if (isLoggable(record)) {
                records.add(record);
                received.countDown();
            }
        }

        @Override public void flush() {}
        @Override public void close() {}

        synchronized List<LogRecord> snapshot() {
            return List.copyOf(records);
        }
    }

    private static void handle(HttpExchange exchange)
            throws java.io.IOException {
        long started = System.nanoTime();

        try {
            byte[] body =
                    "ok".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, body.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(body);
            }
        } finally {
            String path = exchange.getRequestURI().getPath();
            String route = "/healthz".equals(path)
                    ? "/healthz"
                    : path.matches("/orders/[0-9]{1,8}")
                        ? "/orders/{id}" : "/unmapped";

            String id = exchange.getRequestHeaders()
                    .getFirst("X-Request-ID");
            if (id == null
                    || !id.matches("[A-Za-z0-9_-]{1,32}")) {
                id = "invalid";
            }

            int code = exchange.getResponseCode();
            long millis = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - started);

            ACCESS.info(
                    "event=http_access method=GET route="
                    + route
                    + " status="
                    + (code >= 100 && code <= 599
                        ? code : "unknown")
                    + " correlation_id=" + id
                    + " duration_ms=" + millis);
            exchange.close();
        }
    }

    public static void main(String[] args) throws Exception {
        ACCESS.setUseParentHandlers(false);
        ACCESS.setLevel(Level.INFO);

        Capture capture = new Capture();
        capture.setLevel(Level.ALL);
        ACCESS.addHandler(capture);

        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext(
                "/healthz", PostDeployLoggingDemo::handle);
        server.createContext(
                "/orders", PostDeployLoggingDemo::handle);
        server.start();

        try {
            String base = "http://127.0.0.1:"
                    + server.getAddress().getPort();
            HttpClient client = HttpClient.newHttpClient();

            HttpResponse<String> health = client.send(
                HttpRequest.newBuilder(
                        URI.create(base + "/healthz"))
                    .header("X-Request-ID", "health_1")
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build(),
                HttpResponse.BodyHandlers.ofString());

            HttpResponse<String> probe = client.send(
                HttpRequest.newBuilder(
                        URI.create(base
                            + "/orders/42?token=FAKE_SECRET"))
                    .header("X-Request-ID", "req_42")
                    .header("Authorization",
                            "Bearer FAKE_SECRET")
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build(),
                HttpResponse.BodyHandlers.ofString());

            if (!capture.received.await(
                    5, TimeUnit.SECONDS)) {
                throw new AssertionError(
                        "Missing local log event");
            }

            List<String> lines = capture.snapshot()
                    .stream()
                    .map(LogRecord::getMessage)
                    .toList();

            if (lines.size() != 2
                    || lines.stream().noneMatch(s ->
                        s.contains("route=/healthz status=200 "
                                + "correlation_id=health_1"))
                    || lines.stream().noneMatch(s ->
                        s.contains("route=/orders/{id} status=200 "
                                + "correlation_id=req_42"))
                    || lines.stream().anyMatch(s ->
                        s.contains("FAKE_SECRET")
                        || s.contains("token=")
                        || s.contains("/orders/42"))) {
                throw new AssertionError(
                        "Local log contract failed");
            }

            System.out.println(
                    "health_status=" + health.statusCode());
            System.out.println(
                    "probe_status=" + probe.statusCode());
            System.out.println(
                    "captured_events=" + lines.size());
            System.out.println(
                    "correlation_verified=true");
            System.out.println(
                    "secret_in_local_logs=false");
        } finally {
            server.stop(0);
            ACCESS.removeHandler(capture);
            capture.close();
        }
    }
}
```

Compile and run with JDK 17 or newer that includes the `jdk.httpserver` module:

```bash
javac --add-modules jdk.httpserver PostDeployLoggingDemo.java
java --add-modules jdk.httpserver PostDeployLoggingDemo
```

**Exact standard output when localhost sockets are permitted:**

```text
health_status=200
probe_status=200
captured_events=2
correlation_verified=true
secret_in_local_logs=false
```

### 8.1. Step-by-Step Explanation

1. `HttpServer` binds to `127.0.0.1` and port `0` so the OS assigns an ephemeral port; it is not exposed to the internet.
2. `HttpClient` calls `/healthz` and `/orders/42`, with **dummy sensitive** query/headers on the probe.
3. The JUL logger is set to INFO with parent handlers disabled so duplicate console logs are not printed.
4. A synchronized local `Handler` collects `LogRecord` instances; `CountDownLatch` avoids races while the HTTP server and client run on different threads.
5. `route` is determined via path allowlisting rather than logging raw queries/paths containing real IDs.
6. `X-Request-ID` is validated for length/characters to prevent CRLF injection. **Validation does not prove a client ID is trustworthy**: production ingress should generate or validate correlation IDs, not treat self-declared headers as proof of identity.
7. `System.nanoTime()` measures duration, so millisecond values are not printed to deterministic stdout; real events still include `duration_ms`.
8. Event count, both routes, status codes, correlation, and absence of `FAKE_SECRET` are asserted before printing PASS-like output.
9. `finally` stops the HTTP server and detaches the handler to prevent resource leaks.

### 8.2. Example Limitations

**This is a local log smoke test, not an E2E collector check.** Events are kept in the in-memory `Capture` and do not pass through files/stdout, OTLP, agents, collectors, or a search backend. Thus `secret_in_local_logs=false` only holds for **the two events captured by this handler**, and does not prove other logging libraries or network access logs redact properly.

Furthermore:
- The example exercises successful requests only, not 4xx/5xx responses, async servlets, retries, or exporter failures.
- A real application needs proper routing/method/status handling; this minimal example is for demonstration only.
- JSON formatting, OpenTelemetry fields, retention, and backend auth are not configured here.
- A probe containing a dummy canary secret is only for authorized learning/test environments; production canaries should be minimal and do not need a fake Authorization header.
- If the JVM is not allowed to open loopback sockets, the program may fail due to sandbox/network policy. That is an environment constraint, not a reason to relax production permissions.
- When using Spring Boot/Logback, add tests through a real appender, then verify the collector separately as in section 7.

## 9. Spring Boot Post-Deployment Checks

For Spring Boot, a concise checklist:
1. Identify the actual logging configuration loaded from `application.properties/yaml`, `logback-spring.xml`, `log4j2-spring.xml`, or environment variables.
2. Verify runtime effective levels on key loggers, if Actuator `loggers` is secured and accessible to the verification role.
3. Check log lines for `service`, `environment`, `version`, status/route, and correlation ID.
4. Check access logs if using an embedded servlet container: **Spring application INFO logs do not replace Tomcat/Jetty/Undertow access logs**.
5. Check actuator health/readiness; remember they do not verify log delivery outside the cluster.
6. With OTLP, verify both the appender/bridge and endpoint; merely setting `management.otlp.logging.endpoint` or `otel.logs.exporter` **does not prove** every logger is automatically instrumented.
7. Have a plan to adjust logger levels at runtime during incidents, with RBAC/audit logging and time-bounded reversion.

In Spring Boot Actuator, `configuredLevel=null` can mean the logger is not explicitly configured and inherits its effective level—it does **not** mean logging is disabled.

**Do not expose Actuator endpoints to the public internet** just so a CI pipeline can read them. If automation needs to inspect levels, run it from a management network with credentials protected by a secret manager; never print credentials into command output/logs.

## 10. Kubernetes/Containers: Checking Logs from the Right Pod

On Kubernetes, the commands below are **read-only operational examples**. Replace namespace/deployment/pod/container with actual values, requiring appropriate RBAC:

```bash
# Confirm rollout and instance status.
kubectl rollout status deployment/orders-api -n prod --timeout=120s
kubectl get pods -n prod -l app=orders-api -o wide

# View raw stdout/stderr of a specific pod/container.
kubectl logs pod/orders-api-EXAMPLE -n prod \
  -c app --since=10m --timestamps

# If the container restarted, view logs from the previous instance if still available.
kubectl logs pod/orders-api-EXAMPLE -n prod \
  -c app --previous --tail=200

# View events related to a specific pod (if permitted).
kubectl describe pod orders-api-EXAMPLE -n prod
```

`orders-api-EXAMPLE` is an **illustrative name** only; replace it with the real pod name. `--previous` does not create permanent log archives, and data may be lost due to rotation/runtime policy.

**Key considerations:**
- `kubectl logs` shows logs collected by the container runtime per Kubernetes mechanisms; it does not prove Loki/Elastic received them.
- A deployment has multiple pods; check at least the canary pod and consistency across required replicas.
- If logs are missing in the pod, check logger level/appender; if present in the pod but missing in the backend, check agent, namespace, labels, network, and collector.
- For Java writing to files inside a container, stdout may be empty even though the file has logs; identify the exact transport path and volume permissions.
- Do not run `kubectl exec` to edit files/properties or `chmod 777` in production without an approved change procedure.
- Do not pull raw logs containing PII onto personal laptops for long-term storage. Only view authorized lines or use an RBAC-protected search tool.

### 10.1. Missing Logs Immediately After a Rolling Update

Check:
1. Is the agent reading the new file after rollover/restart?
2. Did the runtime rotate container logs so `kubectl logs` only holds partial data?
3. Do new pods have the right labels/mounts for agent discovery?
4. Is a sidecar crashing or using stale credentials?
5. Did service version/namespace/tenant mappings change so old queries no longer match?
6. Is clock skew placing events in a different time range?
7. Is the query filtering on the wrong `pod` or an old replica?

A fresh canary event emitted by the new pod helps distinguish "not emitted" from "emitted but not delivered."

## 11. OpenTelemetry Collector: Metrics to Watch

To verify logging end-to-end, in addition to querying the backend, inspect the **internal telemetry** of the OpenTelemetry Collector if the pipeline uses one. Official documentation groups these into:
- Receiver: records accepted/refused.
- Processor: incoming/outgoing items.
- Exporter: sent records, send failures, failed enqueue.
- Exporter queue: size/capacity.
- Process: CPU/memory/uptime.

**OTLP-style metric names** in documentation may include:

| Example Collector Metric | Meaning |
| --- | --- |
| `otelcol_receiver_accepted_log_records` | Number of log records successfully accepted by the receiver |
| `otelcol_receiver_refused_log_records` | Number of log records refused by the receiver |
| `otelcol_exporter_sent_log_records` | Number of log records successfully sent by the exporter per contract |
| `otelcol_exporter_send_failed_log_records` | Number of log records that failed to send |
| `otelcol_exporter_enqueue_failed_log_records` | Number of log records that failed to enter the queue |
| `otelcol_exporter_queue_size` | Number of batches currently in the sending queue |
| `otelcol_exporter_queue_capacity` | Sending queue capacity, typically measured in batches |

**Version warning:** Prometheus-exposed metric names may differ from the OTLP names above depending on how the exporter adds or omits suffixes like `_total` or units, and metric stability can change. Inspect the **actual** `/metrics` endpoint or data source of your Collector rather than copying queries verbatim and assuming a missing name means lost logs.

If the Collector uses its default internal Prometheus endpoint configuration, a listener may exist on `127.0.0.1:8888/metrics`. Do not assume this endpoint is reachable from a laptop or should be exposed to the internet. Ports/hostnames may be customized per deployment.

### 11.1. Interpreting Metrics Accurately

- `receiver_accepted` increases → receiver accepted logs; **does not prove** the backend stored them.
- `exporter_sent` increases → exporter recorded a successful send; **does not prove immediately searchable**.
- `exporter_send_failed` increases → export errors are occurring; retries may still be active, so logs are not necessarily permanently lost.
- `enqueue_failed` increases → the queue cannot accept data; risk of log loss.
- `queue_size` stays near `queue_capacity` → downstream is congested or the exporter is too slow.
- Collector metrics do not increase while the source emits logs → either the application-agent/receiver link is broken or metrics are not being scraped; check both.

Example verification chain:

```text
Java emits canary
   |
   +--> Seen at local sink?        If no: logger/backend
   |
   +--> Receiver accepted up?      If no: agent/OTLP/network
   |
   +--> Exporter sent up?          If no: queue/retry/backend
   |
   +--> Query finds canary?        If no: storage/query/RBAC/time
```

Read *counter deltas* over the same window as traffic, avoiding single cumulative snapshots since Collector startup. With multiple collectors, select the corresponding instance or aggregate labels properly. Differences between accepted and sent counts do not always mean lost logs because of batch buffering, intentional processor drops, restarts, and separate pipelines.

## 12. Post-Deployment Correlation and Tracing

A release may write complete messages yet lose `trace_id` or request IDs after an OpenTelemetry/Logback upgrade.

Verify using a specific request:
1. Generate a valid request/correlation ID at ingress; do not rely on arbitrary client-provided secrets.
2. Access event contains route/status and correlation ID.
3. Application logs within the same request carry the matching ID.
4. If tracing is enabled, log events contain **valid `trace_id`/`span_id`** when an active span exists.
5. The trace backend receives spans for the right service/version.
6. Links from the log viewer open the trace or locate the span by ID.
7. Across thread pools, async handlers, Kafka consumers, or virtual threads, context is properly propagated and cleaned up.

With the OpenTelemetry Java Agent, MDC auto-instrumentation can populate `trace_id`, `span_id`, and `trace_flags` into the logging event's MDC copy when configured compatibly. **Installing the agent alone does not guarantee your pattern/layout prints these fields**; formatters/encoders must support them, and actual output must be checked. When no valid active span exists, do not fabricate a trace ID.

**Custom correlation IDs differ from W3C TraceId.** The string `req_42` in the Java example is a log-matching ID, **not** a standard-format trace ID. Do not build trace links from malformed IDs.

If the logging framework or appender is asynchronous, capture context as an event snapshot at log time rather than reading the exporter worker's thread-local MDC later at send time. Clean up context in `finally`/scopes so requests do not bleed into one another when threads are reused.

## 13. Data Security, Permissions, and Retention

Production smoke tests must prove not only that logs exist, but also that **prohibited data is not emitted**:
- No passwords, OTPs, API keys, bearer tokens, Authorization headers, or Cookies.
- No raw HTTP bodies, request headers, or queries containing personal data without an approved purpose.
- No SQL parameters or exception messages leaking unnecessary secrets.
- No emails, tokens, or payloads stored in MDC/ThreadContext.
- No lines broken by CR/LF from raw input (log injection).
- No `0666`/`0777` files or public buckets/exports just so a shipper can read them.
- No debug logging left enabled after deployment without a time limit and approval.

### 13.1. Watching All Copies

An event may exist in:
- stdout and container runtime buffers;
- current files and rotated/archived files;
- agent queues or disk spools;
- Collector batch/retry queues;
- primary log storage and older indices/tiers;
- dashboard snapshots, CSV exports, or incident attachments;
- backups and audit stores.

Therefore, "redaction at the collector" is an additional safeguard, **not a replacement for removing secrets at the source**. Test a dummy canary along the real path to the collector and, if policy requires, inspect the exporter/raw file as well. If a real secret is found in logs, follow the security incident process and rotate active credentials as needed; deleting a line from a dashboard does not revoke an exposed token.

### 13.2. File Permissions and Rotation

When using a file appender:
- The service UID/GID/Windows identity can create/append logs without needing root privileges.
- Parent directories have appropriate ACLs/modes; do not inspect file permissions alone.
- After rotation, new files and archives are no more permissive than policy allows.
- The agent has read/traverse access without modify/delete permissions unless required.
- Retention/logrotate does not conflict with the backend's `RollingFileAppender`.
- Disk space and inodes are sufficient, with file quotas, alerts, and a recovery path.

After a rolling update, inspect **new files created by the new version**, not just old files that were manually `chmod`ded.

## 14. Ingestion Timing, Backlog, and Completeness

Post-deploy ingestion speed may be slower than normal due to:
- Appender/OTel exporter queues warming up.
- DNS/TLS/auth handshakes to the collector.
- Batch timeouts, retries/backoff, rate limits, or Collector saturation.
- Backend indexing lag or object store/retention issues.
- Network policy changes in the new deployment.
- Clock skew causing time-range queries to miss events.
- Collector/agent pods not yet ready when application pods emit startup logs.

A delayed log line **does not mean it is lost**, but if it exceeds the **freshness SLO**, mark it FAIL per operational criteria. For logs mandatory to incident response, "it will appear eventually" may not be sufficient.

### 14.1. Log-Derived RPS and Error Rates Can Be Wrong

If a deployment changes `logging.level` or sampling, access log volume can drop even when request traffic has not. Log-based dashboards may:
- Show zero errors when the exporter actually stopped sending.
- Inflate 5xx rates if success events are sampled more aggressively than errors.
- Double-count when both gateway and app log access events.
- Mistake retry messages for new requests.
- Plot inaccurate p95 latencies if logs are dropped unevenly.

Cross-check **metrics** at primary measurement points against log counts, especially after changing sampling or route labels. Use log-derived numbers for SLOs only when the pipeline meets appropriate reliability conditions and definitions.

## 15. Deciding to Proceed, Pause, or Rollback

Not every logging issue automatically requires a rollback. Decisions depend on signal criticality, blast radius, and safe remediation options.

| Situation | Suggested Classification | Response |
| --- | --- | --- |
| Canary appears in backend within SLO, schema/fields valid | PASS | Continue monitoring |
| Event arrives slightly late but within threshold | Observe | Watch backlog, verify across replicas |
| Non-critical debug event filtered per policy | Not an error | Do not arbitrarily enable DEBUG |
| Collector overloaded, queue near full, exporter retrying continuously | DEGRADED | Pause rollout expansion, investigate capacity/network |
| No canary in backend after deadline | FAIL/UNVERIFIED | Hold rollout, analyze hop by hop |
| Mandatory ERROR/audit events lost | Critical | Apply release gate/rollback per policy |
| Real secret logged to sink | Security incident | Isolate data, rotate tokens, handle incident |
| Logs filling disk, JVM/request latency spiking | Critical | Mitigate resources, limit impact; consider rollback |
| Dashboard query uses wrong label while backend has events | UI observability bug | Fix query/config, do not conclude app is not logging |

**Rollback is not a magic fix.** If the fault lies in a central Collector or expired backend credentials, rolling back the app may not help and can cause additional disruption. Identify the failing layer before acting. For lost audit logging or data exposure, follow emergency procedures rather than waiting for the full checklist to finish.

### 15.1. Recommended Check Order During Rollout

1. **Before rollout:** baseline current log delivery, saved queries/metrics, approvals, and SLO thresholds.
2. **Canary/first replica:** verify process, local events, E2E canary, privacy/schema, and metric sources.
3. **Expanding rollout percentage:** watch errors/dropped logs/latency, and check other pods rather than only one replica.
4. **After completion:** confirm no old workers/versions remain and backend queries find new events.
5. **Post-deploy monitoring:** alert/no-data signals and queue trends remain stable over the policy-defined period.

The duration of each phase depends on the service, risk, traffic, and deployment goals; do not treat any generic number as a universal commitment.

## 16. Integrating Logging Checks into CI/CD

You can build a **deploy verification job** that does not mutate production configuration:
1. Read the release identity and approved smoke endpoint from the deploy system.
2. Wait for rollout readiness to succeed with a timeout.
3. Send an **idempotent** canary request or use an observe-only endpoint.
4. Record the UTC timestamp and `probe_id`; do not print real tokens into logs.
5. Verify the application HTTP response.
6. Query the log backend authenticated via a secret manager over a narrow time range.
7. Poll with exponential backoff and a deadline; do not repeatedly query the entire log store.
8. Assert expected service/env/version/probe ID/schema/level.
9. Verify the canary has 1 event at the target layer, without duplication or broken redaction.
10. Read collector/exporter metrics and check failures/dropped counts against thresholds.
11. Return a structured PASS/FAIL result and store safe evidence.
12. On FAIL, hold the rollout, trigger the rollback policy, or require on-call approval.

### 16.1. Backend Verification Pseudocode

This is **pseudocode**, not a standalone runnable script:

```text
probeId = newRandomSafeId()
sentAt = utcNow()
sendApprovedSmokeRequest(probeId)

deadline = monotonicNow() + allowedFreshness
while monotonicNow() < deadline:
    hits = backendQuery(
        service = expectedService,
        environment = expectedEnv,
        release = expectedVersion,
        probeId = probeId,
        timeRange = [sentAt - clockSkewBudget, utcNow()]
    )

    if hits match expected event schema and count:
        verify no forbidden fields
        verify pipeline counters and alert health
        return PASS

    sleepWithBoundedBackoff()

return FAIL("Canary not searchable within deadline")
```

**Do not hardcode** backend APIs/credentials, do not build raw text queries from untrusted input, and do not confuse "No data" with zero errors. If the backend returns an error/403, report a distinct **INCONCLUSIVE/ACCESS_DENIED** status instead of falsely concluding the application is not logging.

### 16.2. Why Can Automation Produce False Negatives?

- Backend queries have indexing lag.
- Clock skew shifts the effective time range.
- The canary event is sampled out as a normal success request.
- The query requires an app/env/version label that the pipeline does not attach.
- The pod is replaced mid-rollout and data arrives under a different instance.
- The backend received the log, but the job's identity lacks permission to read that tenant.
- The job asserts "exactly one line" when both gateway and app log; the source scope is wrong.

Define the scope clearly and include diagnostic stages so operators know where a failure occurred rather than merely seeing "log not found."

## 17. Failure and Chaos Tests Recommended for Staging

Perform only in authorized environments with bounded blast radius:
- Disable the log appender on one test instance: verify E2E canary FAILS.
- Change effective level to WARN: INFO does not reach the sink; verify the test does not misdiagnose.
- Temporarily disconnect the Collector network: observe retries, queue, backlog, delay, and error metrics.
- Fill the exporter queue: verify `enqueue_failed`/dropped alerts fire.
- Backend rejects due to expired credentials: pod logs still exist while exporter/send failures rise.
- Enable a broken JSON encoder: parser/query no longer recognizes the schema.
- Simulate clock skew: canary falls outside the expected time range, detected by query checks.
- Configure a duplicate appender: one event is duplicated; dashboard count inflates falsely.
- Rotate/change test file permissions: agent cannot read the new file.
- Shut down before flush: pending logs in RAM queues are lost, confirming the failure mode.
- Lose trace context across another thread: correlation breaks, testing propagation.
- Probe with dummy data like `FAKE_SECRET` in staging: verify it does not appear in sinks.

Do not run tests that drop logs, partition networks, trigger mass restarts, or send fake secret traffic directly in production outside an approved change plan.

## 18. Symptom-Based Troubleshooting

| Symptom | Where to Check First | Conclusion to Avoid |
| --- | --- | --- |
| Service healthy but no logs | Effective level, appender, stdout/file source | "Readiness PASS means logging PASS" |
| Pod stdout has logs, backend missing them | Agent, receiver, exporter, RBAC, labels/time | "Application is definitely not logging" |
| No startup logs from new version | Pod/version, source/file path, time range | "Old logs mean new version works" |
| Only ERROR logged, INFO missing | Logger level/filter, sampling, backend parser | "Collector is dropping everything" |
| New logs present but missing trace ID | MDC/agent instrumentation, active span, encoder | "Trace backend exists so logs auto-attach traces" |
| Event has right ID but wrong schema | Encoder, version mapping, parser, label transform | "Event present means full PASS" |
| Logs arrive minutes late | Batch delay, queue, retry, storage index | "Exporter ACK means searchable" |
| Duplicate access logs | Multiple layers, additivity, retries | "Traffic doubled" |
| Cannot read file after rotation | Directory permissions, new inode, shipper offsets | "chmod on old file was enough" |
| 429/503 errors on export | Backend throttle, network, rate policy | "Infinite retries will fix it" |
| Collector queue full | Downstream latency, queue size, rate, disk | "Unlimited RAM is fine" |
| Dashboard No Data | Selector, time range, label, tenant, query syntax | "No production errors" |
| Secret appears in logs | Call site, MDC, exception, formatter, pipeline | "Masking in one place is enough" |
| Smoke test fails while app returns 200 | Log pipeline, status scope, backend query | "Testing only needs HTTP 200" |

The most effective investigation method: **walk hop by hop starting close to the application**, keeping timestamps and probe IDs consistent. Do not start by turning on global DEBUG in production and flooding millions of extra events into an already congested pipeline.

## 19. Post-Deployment Acceptance Checklist

- [ ] Confirmed correct service, environment, release/version, and instance.
- [ ] Rollout/readiness stable; no restart loops, OOMs, or boot errors.
- [ ] Logging backend initialized cleanly; no appender/encoder/file permission errors.
- [ ] Runtime effective levels match policy; no accidental DEBUG/TRACE enabled.
- [ ] Local sink (stdout/file/OTLP bridge) receives new events from the new release.
- [ ] Events include timestamp, service/env/version, level, event code, and fields with valid types/units.
- [ ] No tokens, passwords, or sensitive raw bodies/headers/queries logged; JSON/logfmt escaping works.
- [ ] Valid correlation ID present; trace ID/span ID populated when an active span exists.
- [ ] E2E canary queried in backend within approved time range and deadline.
- [ ] Agent/Collector receiver/exporter healthy, without abnormal enqueue/send/drop errors.
- [ ] Queue has no sustained backlog; freshness is within acceptable bounds.
- [ ] No unexpected duplicate events; sampling/retention documented clearly.
- [ ] For files, ownership/permissions/rotation and disk space are appropriate.
- [ ] Log UI/dashboards/alerts use the right source, timezone, labels, version, and RBAC.
- [ ] Safe evidence recorded for results, with incident/runbook links on FAIL.
- [ ] Rollout hold/rollback conditions evaluated; do not proceed blindly when mandatory logs are missing.
- [ ] Temporary debug/probe changes after verification reverted/cleaned up per procedure.

## 20. Hands-On Exercises

1. Run `PostDeployLoggingDemo`. Explain the difference between `health_status=200`, `captured_events=2`, and being able to query logs in a collector.
2. Set the JUL logger level to WARNING while still sending successful HTTP requests; what happens to INFO events and `CountDownLatch`? Adjust the test timeout to observe a controlled failure.
3. Change route mapping to log raw `getRequestURI()`; use a dummy canary to see why it can leak queries/paths.
4. Use Logback `ListAppender` or JUL `Handler` in a unit test; distinguish API invocation from an emitted event.
5. In a Spring Boot Actuator test, compare `configuredLevel` with `effectiveLevel`; why does `null` not mean OFF?
6. Deploy a Java app in a test Kubernetes cluster and inspect it with `kubectl logs`. Find a canary in Loki/Elastic and compare timestamps.
7. Trigger an HTTP 5xx in staging, verify the error code/trace ID event, and locate the matching log in the dashboard.
8. Create a test where application stdout works but the collector endpoint is unreachable; inspect accepted/sent/failed metrics.
9. Test a canary that fails to appear due to wrong time range/labels. Write logic distinguishing a query failure from a logging failure.
10. Simulate an event logged twice due to appender additivity; fix the config and verify the count.
11. Change file rotation in staging and test new file permissions/agent shipper readability.
12. Build a post-deploy checklist in a CI/CD pipeline: unique probe ID, deadline, status, event query, and safe evidence.
13. Test exporter retry/backoff with a slow receiver in staging; measure log freshness and backlog after recovery.
14. Write a test that loses trace context across a thread pool, then fix propagation/cleanup per your logging framework.
15. Design a decision matrix for three failures: wrong dashboard query, collector outage, and logs containing a real token. Why do the responses differ?

## 21. Key Takeaways

- **Post-deployment verification** must confirm **the right logs arrive at the right destination, within the right deadline, without leaking data, and remain investigable**, not just that the app returns HTTP 200.
- Logger invocation, local event, receiver accepted, exporter sent, and backend searchable are **distinct milestones**.
- Verify `effectiveLevel`, appenders, encoders, startup errors, file permissions, and the actual running service configuration.
- Use a **harmless canary** with a unique probe ID and query the backend with a bounded time range/deadline; never use real tokens or PII.
- Cross-check logs against metrics and traces; inspect trace correlation, sampling, duplicates, queue/dropped events, and ingestion latency.
- OpenTelemetry Collector internal metrics help isolate receiver/exporter/queue issues, though names/suffixes can vary by version and export format.
- Never expose Actuator or management metrics to the internet just for testing. Never enable broad DEBUG to fix missing logs.
- Verification results must become release evidence and inform rollout/rollback criteria; treat secrets logged to sinks as a security incident.

### Official References

- Spring Boot 3.5 — Actuator Loggers: https://docs.spring.io/spring-boot/3.5/reference/actuator/loggers.html
- Spring Boot — Actuator management endpoint access: https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html
- Kubernetes — `kubectl logs`: https://kubernetes.io/docs/reference/kubectl/generated/kubectl_logs/
- Kubernetes — `kubectl rollout status`: https://kubernetes.io/docs/reference/kubectl/generated/kubectl_rollout/kubectl_rollout_status/
- OpenTelemetry — Collector internal telemetry and exporter metrics: https://opentelemetry.io/docs/collector/internal-telemetry/
- OpenTelemetry — Java instrumentation, logger MDC: https://github.com/open-telemetry/opentelemetry-java-instrumentation/blob/main/docs/logger-mdc-instrumentation.md
- OpenTelemetry — Logs Data Model: https://opentelemetry.io/docs/specs/otel/logs/data-model/
- Oracle Java — `HttpServer` (JDK 21 docs, API also available in JDK 17): https://docs.oracle.com/en/java/javase/21/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html
- Oracle Java — `Logger`: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html
- OWASP — Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
