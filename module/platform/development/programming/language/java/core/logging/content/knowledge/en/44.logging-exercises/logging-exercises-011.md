# Creating an Operational Runbook for Java Logging: A Hands-On Project from Alert to Recovery

## 1. Project Objectives and Final Deliverables

An **operational runbook** is an actionable document that helps on-call engineers, SREs, developers, and relevant stakeholders **detect, verify, triage, mitigate, recover, and document** an incident. For Java Logging, a runbook does not merely instruct "open the log file"; it clearly describes **the log path, the meaning of events, required evidence to collect, decision points, execution permissions, and the criteria to confirm an incident is resolved**.

After this hands-on exercise, you will produce a sample runbook for a hypothetical Java service `orders-api` covering two incident types:

- **Application incident:** `POST /orders` requests fail with HTTP 503 due to a dependency timeout. Logs contain `REQUEST_STARTED`, `DEPENDENCY_TIMEOUT`, and `REQUEST_FAILED` events.
- **Observability incident:** the application is still running, but logs do not appear in the backend because of an issue with the level/filter, output sink, agent, Collector, or exporter.

**Final deliverables** include: a runbook with an owner and scope, a signal/alert table, evidence collection steps, a decision tree, safe diagnostic actions, escalation/rollback/recovery criteria, log pipeline verification instructions, rehearsal scenarios, and a **standalone Java 17** program that generates JSON Lines data for practicing log reading.

This lesson belongs to the **Hands-On Project** section, so the commands and scenarios are written so learners can apply them in a test environment before turning them into an SOP for a real system. **Do not treat the service names, namespaces, alert thresholds, or timeframes in this lesson as existing enterprise configurations.** They are intentional assumptions for the lab.

## 2. How Does a Runbook Differ from Logging Documentation and a Playbook?

An introductory logging document might explain `INFO`, `WARN`, `ERROR`, and how to configure Logback. A **runbook** must answer operational questions in the exact order of action:

1. **What is the trigger signal?** Increased 5xx alerts, collector exporter errors, log gaps, disk watermark, or increased latency?
2. **Who receives and owns it?** Service on-call, platform, database, security, or incident commander?
3. **What should be checked first?** Scope, time window, request volume, deployments, metrics, service health, and access permissions?
4. **How do we isolate the incident?** Is the service failing or are logs simply missing? One tenant, one pod, or the whole cluster?
5. **Which actions are permitted?** Read-only steps, mitigations under change policy, and approved rollbacks.
6. **When must we stop and escalate?** Suspected data loss, security incidents, unreliable dashboards, or prolonged outages?
7. **When do we close the incident?** Metrics recovered, canary/trace/consumer flows succeeding, log pipeline re-verified, and an observation window completed.
8. **Where is the record kept?** Incident ID, timeline, decisions, approvers, and evidence with sensitive data redacted.

A **playbook** usually covers the strategy for handling an entire class of incidents and may reference multiple runbooks. An **SOP** may define routine procedures or mandatory controlled steps. Naming conventions vary across organizations; what matters is that the document is **clear, actionable, and verifiable**.

## 3. Defining Scope Before Writing

This project's sample runbook uses the following assumptions:

| Attribute | Lab Value | What to Replace With in a Real System |
| --- | --- | --- |
| Service | `orders-api` Java 17 | Actual workload/resource name |
| Entry point | `/orders` | Corresponding endpoint and HTTP method |
| Error status | HTTP `503` | Status/exception per API contract |
| Dependency | Simulated `inventory` | Exact dependency from architecture lookup |
| Event code | `DEPENDENCY_TIMEOUT`, `REQUEST_FAILED` | Approved event taxonomy |
| Log transport | JSON Lines from stdout | Actual stdout/file/OTLP and agent |
| Infrastructure | Kubernetes deployable, optional | Cluster, namespace, deployment/VM owner |
| Timestamp | UTC, fixed in lab | Real runtime UTC, with potential clock skew |
| Trace context | `trace_id` in JSON | Real W3C Trace Context/OpenTelemetry instrumentation |
| Backend query | Hypothetical syntax for explanation | Query API and schema of the backend in use |

For a real system, the runbook must link to the **service catalog**, architecture, dashboards, alert rules, SLOs, change history, on-call routing, vault/secrets policy, and access policy. This lesson does not fabricate those internal URLs; implementers must link to verified resources.

**Out-of-scope definition:** Do not manually edit databases, delete logs, grant yourself access permissions, change production configs, or mass-restart pods in this hands-on exercise. Actions that may cause data loss or destroy evidence are only performed under the real system's change management and authorization procedures.

## 4. The Observability Flow to Understand

~~~text
Client / Gateway
       │
       ▼
orders-api (Java)
   ├─ business request / dependency call
   ├─ Logger facade (JUL / SLF4J / Log4j 2)
   └─ metric + tracing instrumentation
       │
       ▼
Stdout/stderr, file, or OTLP exporter
       │
       ▼
Container runtime / node agent / file shipper
       │
       ▼
OpenTelemetry Collector or log gateway
       ├─ parse / enrich / filter / transform
       ├─ batch / queue / retry
       └─ exporter
       │
       ▼
Log backend / index / search API
       │
       ▼
Dashboard / Alert / Investigation
~~~

Each hop is a **distinct verification boundary**:

- Calling a logger **does not prove** the record reached a file or stdout.
- Appearing in a file/stdout **does not prove** the agent read it.
- The Collector receiving an event **does not prove** the exporter sent it successfully.
- An exporter reporting success **does not automatically prove** the data is queryable in the final index.
- A record not found on a dashboard **does not prove** the application never performed the action.

Therefore, a runbook must always distinguish between a **business incident** and a **logging pipeline incident**. If service 503s spike while logs temporarily vanish, do not rush to conclude "there are no exceptions."

## 5. Standard Structure Template for Every Runbook

A runbook can maintain the following fixed sections:

| Section | Required Content |
| --- | --- |
| **Document metadata** | ID, title, owner, reviewers, version, effective date, last rehearsal |
| **Scope/assumptions** | Service/env, dependencies, versions, what is not covered |
| **Trigger/symptoms** | Alert name, severity, user-facing symptoms |
| **Prerequisites** | Read-only permissions, VPN/auth, dashboards, access logging |
| **Safety/guardrails** | Data privacy, change approval, no evidence deletion, rollback requirements |
| **First response** | Alert verification, time window, blast radius, customer impact |
| **Diagnosis** | Step sequence/decision tree with expected observations |
| **Mitigation** | Authorized mitigation options, approvers |
| **Recovery** | Multi-signal recovery criteria, observation window |
| **Escalation** | When to page service/platform/security/DB owners |
| **Communication** | Incident updates, scope, and verified facts |
| **Evidence** | Trace/request/event IDs, metric snapshots, redacted logs |
| **Post-incident** | Timeline, root-cause hypothesis, action owners, review date |
| **Validation** | Rehearsals, test results, assumptions needing updates |

Headings can be stored in Git or an internal documentation system. There should be a **specific owner by role/team** to avoid unowned runbooks or stale docs after service handovers.

## 6. Defining Alert Criteria and Severity Levels

A good alert should reflect **observable impact** rather than just seeing a single `ERROR` line. Hypothetical examples:

| Signal | Illustrative Threshold | Purpose |
| --- | --- | --- |
| HTTP 5xx ratio for `orders-api` | Above 5% over 5 minutes **and** at least 100 requests | Distinguish real errors from low-traffic noise |
| P95 request latency | Exceeds SLO for 10 minutes | Verify user experience |
| Dependency timeout rate | Significant increase over baseline | Check integration failures |
| Readiness failure | Consecutive probe failures | Identify unready instances |
| Log ingestion gap | Traffic exists but logs from service do not increase over observation window | Detect lost observability |
| Exporter queue/drops | Growing backlog or continuous failed exports | Detect pipeline failures |

**All thresholds are examples** and must be tuned to your SLOs, load history, and actual metrics configuration. Avoid ratio-only expressions when sample sizes are tiny: one failed request out of one request yields 100% 5xx, which is not necessarily a widespread incident.

Example severities:

- **SEV1:** most customers cannot use a core service, risk of data loss/corruption, or severe security incident; triggers incident command.
- **SEV2:** a key feature is noticeably degraded, affecting many users or likely to spread.
- **SEV3:** limited failure or partial telemetry loss, with a workaround within acceptable limits.

**A logging pipeline incident can be severe** if it blinds security detection or drops mandatory audit evidence, even when HTTP endpoints still return 200. Severity must be evaluated based on the purpose and obligations of the log data.

## 7. Before Acting: Safety Checklist

The on-call engineer must:

1. Confirm the **correct environment**, cluster, account, tenant, and service; all example commands below are for the lab only.
2. Use **read-only** permissions for the initial phase. Do not escalate privileges just to view full sensitive payloads.
3. Create/record an **incident ID** in the incident management system before sharing evidence.
4. Record the alert start time, UTC timezone, and query time range to avoid confusing stale data.
5. Do not copy full production logs into chat, tickets, or public dashboards.
6. Do not log raw passwords, tokens, cookies, HTTP bodies, payment details, or raw SQL binds "for easier debugging."
7. Do not silence/edit alerts, delete files, truncate indices, flush buffers, or blindly restart pods before understanding the impact.
8. If a data breach or security incident is suspected, notify the appropriate security team/incident commander and follow evidence-preservation procedures.
9. If considering temporarily enabling DEBUG, evaluate log volume, retention, sensitive data, and **when to turn it back off**.
10. For any system-changing action, record the approver, change scope, rollback criteria, and outcome.

Do not treat finding a `SEVERE` line as a reason to restart immediately. A restart can wipe in-memory evidence, increase errors, and mask the root cause.

## 8. The First 5 Minutes After Receiving an Alert

**T0 — Alert arrives:** Confirm the alert name, ID, service/environment labels, observed time, severity, and whether it is still active. Check whether it pertains to production or staging.

**T+1 — Blast radius:** Check request rate, success/error ratio, p95/p99 latency, instance count, dependency health, and affected tenants/regions. If metrics are unreliable, explicitly note the gap.

**T+2 — Recent changes:** Check releases/deploys near the incident start, config/feature flags, dependency rollouts, certificate/token rotations, or quota/rate limits. "There was a recent deploy" is a hypothesis, **not a root-cause conclusion**.

**T+3 — Find logs by ID:** Start with event code, request/trace ID, service, time window, and reason code; do not rely on a free-text message string.

**T+4 — Branch:** If source logs exist but backend logs do not, switch to the pipeline runbook; if `DEPENDENCY_TIMEOUT` and 503 appear, investigate the dependency and error propagation.

**T+5 — Decide:** If impact/severity crosses the threshold, escalate and open an incident channel; if contained, continue time-boxed triage. Update what is **known**, what is **unknown**, and the next action.

Minute marks are a **reference sequence of actions**, not a promised SLA. In a SEV1, you may need to page incident command at T0 rather than waiting until the end.

## 9. Overall Decision Tree

~~~text
Alert / error report received
     │
     ├─ Do metrics/health confirm user impact?
     │         │
     │         ├─ YES → Check business traces/logs
     │         │          │
     │         │          ├─ Clear dependency / code error
     │         │          │   → Isolate and apply approved mitigations
     │         │          └─ No logs / inconsistent logs
     │         │              → Investigate pipeline in parallel
     │         └─ UNCLEAR → Check telemetry freshness,
     │                      sampling, query window, and canary
     │
     ├─ Do logs appear at the source?
     │         ├─ NO → Level/filter/appender/process/lifecycle
     │         └─ YES
     │             └─ Did the agent pick them up?
     │                 ├─ NO → Path/permissions/CRI/rotation/checkpoint
     │                 └─ YES
     │                     └─ Did the Collector export them?
     │                         ├─ NO → Processor/drop/queue/exporter
     │                         └─ YES → Backend ingest/index/query/RBAC
     │
     └─ Impact mitigated + verified by multiple signals?
               ├─ NO → continue handling/escalate
               └─ YES → monitor, record evidence, post-incident
~~~

**Note:** Missing logs are just one observation. If the pipeline fails, application metrics and traces may still exist; conversely, **all three signals** could break due to shared infrastructure. The runbook should check independent sources whenever possible.

## 10. Hands-On: Requirements for the Java 17 Lab

The lab builds a single Java class named `LoggingRunbookLab` using **JUL**, running with zero external dependencies:

- `healthy` mode: emits `REQUEST_STARTED` and `REQUEST_SUCCEEDED`, final HTTP status 200.
- `incident` mode: emits `REQUEST_STARTED`, `DEPENDENCY_TIMEOUT`, `REQUEST_FAILED` with status 503; then emits a `RECOVERY_PROBE_OK` log **belonging to an independent probe request**.
- Each event includes UTC timestamp, service, event code, level, trace ID, request ID, route, HTTP status, reason code, and message.
- Output is **JSON Lines on stdout**, one physical line per event; by default JUL does not print a duplicate to stderr.
- Contains a fake secret string in code scope, never passed to the Logger.
- Fixed timestamps **for testing only**; must not be treated as real-time production logs.
- Intentionally has **no** real exporter, agent, Collector, or backend: this lab practices **source-level triage** before connecting to a staging environment.

This design lets engineers focus on **reading signals, correlation, and recovery boundaries** without installing Kafka, Docker, or a heavy logging stack.

## 11. Standalone Java 17 Program — LoggingRunbookLab.java

Create `LoggingRunbookLab.java` with the **complete** contents below:

~~~java
import java.time.Instant;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LoggingRunbookLab {
    private static final Logger LOG = Logger.getLogger("lab.orders-api");
    private static final String TRACE = "0123456789abcdef0123456789abcdef";
    private static final String PROBE_TRACE = "fedcba9876543210fedcba9876543210";

    record Event(String eventCode, String traceId, String requestId,
                 String route, int httpStatus, String reasonCode) {}

    static String quote(String text) {
        StringBuilder out = new StringBuilder("\"");
        for (int i = 0; i < text.length(); i++) {
            char c = text.charAt(i);
            switch (c) {
                case '"': out.append("\\\""); break;
                case '\\': out.append("\\\\"); break;
                case '\n': out.append("\\n"); break;
                case '\r': out.append("\\r"); break;
                case '\t': out.append("\\t"); break;
                default:
                    if (c < 0x20) {
                        out.append("\\u");
                        for (int shift = 12; shift >= 0; shift -= 4) {
                            out.append(Character.forDigit((c >>> shift) & 0xf, 16));
                        }
                    } else {
                        out.append(c);
                    }
            }
        }
        return out.append('"').toString();
    }

    static void stringField(StringBuilder line, String key, String value) {
        if (line.length() > 1) line.append(',');
        line.append(quote(key)).append(':').append(quote(value));
    }

    static final class JsonHandler extends Handler {
        JsonHandler() { setLevel(Level.ALL); }
        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record)) return;
            Object[] args = record.getParameters();
            if (args == null || args.length != 1 || !(args[0] instanceof Event)) {
                throw new IllegalArgumentException("safe Event required");
            }
            Event e = (Event) args[0];
            StringBuilder line = new StringBuilder("{");
            stringField(line, "timestamp", record.getInstant().toString());
            stringField(line, "service", "orders-api");
            stringField(line, "event_code", e.eventCode());
            stringField(line, "level", record.getLevel().getName());
            stringField(line, "trace_id", e.traceId());
            stringField(line, "request_id", e.requestId());
            stringField(line, "route", e.route());
            line.append(",\"http_status\":").append(e.httpStatus());
            stringField(line, "reason_code", e.reasonCode());
            stringField(line, "message", record.getMessage());
            System.out.println(line.append('}'));
        }
        @Override public void flush() { System.out.flush(); }
        @Override public void close() { flush(); }
    }

    static void emit(Level level, String message, Event event, String time) {
        LogRecord r = new LogRecord(level, message);
        r.setInstant(Instant.parse(time));
        r.setLoggerName(LOG.getName());
        r.setParameters(new Object[]{event});
        LOG.log(r);
    }

    public static void main(String[] args) {
        if (args.length != 1 ||
                (!"healthy".equals(args[0]) && !"incident".equals(args[0]))) {
            System.err.println("Usage: java LoggingRunbookLab healthy|incident");
            System.exit(2);
            return;
        }
        Handler out = new JsonHandler();
        boolean oldParent = LOG.getUseParentHandlers();
        Level oldLevel = LOG.getLevel();
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);
        LOG.addHandler(out);
        try {
            String privateToken = "FAKE_TOKEN_NEVER_LOG";
            if (privateToken.isEmpty()) throw new IllegalStateException();
            emit(Level.INFO, "request received",
                    new Event("REQUEST_STARTED", TRACE, "req-42",
                            "/orders", 0, "NONE"),
                    "2026-11-10T02:00:00Z");
            if ("healthy".equals(args[0])) {
                emit(Level.INFO, "request completed",
                        new Event("REQUEST_SUCCEEDED", TRACE, "req-42",
                                "/orders", 200, "NONE"),
                        "2026-11-10T02:00:01Z");
            } else {
                emit(Level.WARNING, "inventory lookup timed out",
                        new Event("DEPENDENCY_TIMEOUT", TRACE, "req-42",
                                "/orders", 0, "DB_TIMEOUT"),
                        "2026-11-10T02:00:01Z");
                emit(Level.SEVERE, "request failed safely",
                        new Event("REQUEST_FAILED", TRACE, "req-42",
                                "/orders", 503, "UPSTREAM_UNAVAILABLE"),
                        "2026-11-10T02:00:02Z");
                emit(Level.INFO, "independent readiness probe passed",
                        new Event("RECOVERY_PROBE_OK", PROBE_TRACE, "probe-42",
                                "/health/ready", 200, "NONE"),
                        "2026-11-10T02:00:04Z");
            }
        } finally {
            LOG.removeHandler(out);
            LOG.setUseParentHandlers(oldParent);
            LOG.setLevel(oldLevel);
            out.flush();
            out.close();
        }
    }
}
~~~

**Technical notes:**

- `JsonHandler` is a demo collector that builds JSON strings manually for learning; production should use a **maintained JSON encoder** to handle Unicode, surrogate pairs, escaping, schemas, errors, and throughput.
- `http_status=0` in the start/timeout events is a **lab-defined sentinel value for "no HTTP response yet"**, not a valid HTTP status code.
- JUL's `Level.SEVERE` is kept as `"SEVERE"`. Backends often map it to ERROR, but **do not assume** it is mapped by default; verify your actual pipeline.
- `RECOVERY_PROBE_OK` only reports that **an independent probe** succeeded; it does not prove request `req-42` recovered or that the entire service is error-free.
- `setUseParentHandlers(false)` prevents the JUL root handler from writing duplicates to stderr; `LOG.removeHandler` and restoring the level prevent the lab from leaving global state behind if run in a shared JVM.
- The fake secret never enters `Event` or the message. Real sensitive values must **never** be used as fixtures.

## 12. Compiling, Running, and Exact Output

Requires **JDK 17 or later** with `javac`, no external frameworks needed.

~~~bash
javac --release 17 LoggingRunbookLab.java
java LoggingRunbookLab healthy
~~~

**Stdout in healthy mode** (two JSON Lines, in the order below):

~~~json
{"timestamp":"2026-11-10T02:00:00Z","service":"orders-api","event_code":"REQUEST_STARTED","level":"INFO","trace_id":"0123456789abcdef0123456789abcdef","request_id":"req-42","route":"/orders","http_status":0,"reason_code":"NONE","message":"request received"}
{"timestamp":"2026-11-10T02:00:01Z","service":"orders-api","event_code":"REQUEST_SUCCEEDED","level":"INFO","trace_id":"0123456789abcdef0123456789abcdef","request_id":"req-42","route":"/orders","http_status":200,"reason_code":"NONE","message":"request completed"}
~~~

Run incident mode:

~~~bash
java LoggingRunbookLab incident
~~~

**Stdout in incident mode** (four JSON Lines):

~~~json
{"timestamp":"2026-11-10T02:00:00Z","service":"orders-api","event_code":"REQUEST_STARTED","level":"INFO","trace_id":"0123456789abcdef0123456789abcdef","request_id":"req-42","route":"/orders","http_status":0,"reason_code":"NONE","message":"request received"}
{"timestamp":"2026-11-10T02:00:01Z","service":"orders-api","event_code":"DEPENDENCY_TIMEOUT","level":"WARNING","trace_id":"0123456789abcdef0123456789abcdef","request_id":"req-42","route":"/orders","http_status":0,"reason_code":"DB_TIMEOUT","message":"inventory lookup timed out"}
{"timestamp":"2026-11-10T02:00:02Z","service":"orders-api","event_code":"REQUEST_FAILED","level":"SEVERE","trace_id":"0123456789abcdef0123456789abcdef","request_id":"req-42","route":"/orders","http_status":503,"reason_code":"UPSTREAM_UNAVAILABLE","message":"request failed safely"}
{"timestamp":"2026-11-10T02:00:04Z","service":"orders-api","event_code":"RECOVERY_PROBE_OK","level":"INFO","trace_id":"fedcba9876543210fedcba9876543210","request_id":"probe-42","route":"/health/ready","http_status":200,"reason_code":"NONE","message":"independent readiness probe passed"}
~~~

Both modes: **empty stderr, exit code 0** on normal execution. No line contains `FAKE_TOKEN_NEVER_LOG`.

**Do not treat these timestamps as the current time during an investigation.** In the lab, they are **fixed** to verify output. In a real application, timestamps must reflect the log record's event time, and backend queries must use the time range matching the incident.

## 13. Exercise: Generating Local Evidence Files

Operate only inside the **lab directory**. The following commands write the compiled program's output to two files:

~~~bash
java LoggingRunbookLab healthy > healthy.jsonl
java LoggingRunbookLab incident > incident.jsonl
~~~

In PowerShell (Windows), if your shell uses a different encoding, you can read the file as UTF-8 with `Get-Content -Encoding UTF8`. The demo content is ASCII so both cases are easy to compare; production should enforce UTF-8 charset at the logger/encoder.

**PowerShell example filtering by request ID:**

~~~powershell
Get-Content .\incident.jsonl -Encoding UTF8 |
    ForEach-Object { $_ | ConvertFrom-Json } |
    Where-Object { $_.request_id -eq 'req-42' } |
    Select-Object timestamp,event_code,level,reason_code,http_status
~~~

**Linux/macOS example if `jq` is available:**

~~~bash
jq -c 'select(.request_id == "req-42")' incident.jsonl
jq -c 'select(.event_code == "REQUEST_FAILED")' incident.jsonl
~~~

In incident mode, filtering for `req-42` must return **three events**, while `probe-42` is an event with a **different request and trace**. When the simulated incident has a 503, inspect `reason_code=DB_TIMEOUT` before deciding whether the fault lies in application code, the dependency, or infrastructure.

**Do not force `jq` commands onto production logs that are plain text**. If the backend has already parsed JSON into Resource/Attributes/Body per OpenTelemetry, query syntax and field locations may differ. Use the actual schema of your sink.

## 14. Operational Scenario A — HTTP 503 Spike

Assume an alert for `orders-api` in staging reports rising 5xx errors.

**Step A1 — Confirm impact:** Check request rate, 5xx ratio, p95/p99, route, region, per-instance ratio, and affected customer count. If traffic is low, cross-check absolute request counts.

**Step A2 — Select window:** Take a range from before the alert started to after it fired, in UTC. Do not run an unbounded search that lets old results pollute the view.

**Step A3 — Find events:** Query `service=orders-api AND event_code=REQUEST_FAILED` combined with the time window and environment, then drill into a specific `request_id` or `trace_id`.

**Step A4 — Reconstruct timeline:** `REQUEST_STARTED` → `DEPENDENCY_TIMEOUT` → `REQUEST_FAILED` for `req-42`. In the lab, `http_status=503` is attached to the final event, while `reason_code=UPSTREAM_UNAVAILABLE` describes how the service responded to the failure.

**Step A5 — Verify dependency:** Check dependency signals, saturation, connection pool, timeout budget, retry rate, and recent changes. **A single string "inventory lookup timed out" is not enough to declare the database as the root cause**; it is a hypothesis to verify.

**Step A6 — Choose an approved mitigation:** Options include load shedding, limiting concurrency, disabling a non-critical feature, switching to a designed fallback, or rolling back the offending release. Do not increase timeouts/retries indefinitely, as that can worsen congestion.

**Step A7 — Evaluate outcome:** 5xx ratio and latency return within acceptable thresholds, traffic and critical routes work, dependency error rate drops, and corresponding logs/traces are present. **A `RECOVERY_PROBE_OK` probe alone is not sufficient**.

**Step A8 — Monitor and hand off:** Record the mitigation, timestamp, approver, verified data, and remaining uncertainties. Maintain monitoring for the duration specified by the on-call policy.

## 15. Operational Scenario B — Logs Vanish While Metrics Keep Rising

Symptom: `orders-api` traffic is still increasing, but the search API returns no new logs.

**Rule:** Do not mark the service healthy just because no ERRORs are visible, and do not claim the application stopped logging. Check each hop:

| Hop | Read-First Check | If Failing |
| --- | --- | --- |
| JVM/logger | Level, filters, logger category, appender lifecycle | Trace code/config/logger hierarchy |
| App sink | stdout/stderr, file path, FileHandler/Logback/Log4j 2 output | Identify actual output, rotation, or disk full |
| Runtime | Container logs, CRI wrapper, truncation/partial events | Check node log path/runtime |
| Shipper/agent | Input include path, permissions, checkpoint, parser rejects | Coordinate with platform/agent owner |
| Collector | Receiver/pipeline active, processors, queue, exporter | Check internal telemetry/errors |
| Backend | Ingest, index, mapping, tenant, retention, query time | Check raw records and access scope |
| UI | Timezone, saved filters, role access | Compare direct query with dashboard |

If **stdout has new JSONL but the Collector sees nothing**, prioritize agent input/permissions/CRI parsing rather than editing `log.info` in Java. If the Collector debug exporter receives events that backend queries do not see, prioritize exporter/backend/mapping/retention. Caution: the debug exporter only shows that the Collector received/processed at that stage, not that the backend persisted the data.

When a log pipeline outage coincides with a business incident, run two tracks: **restoring service operations** and **restoring observability**. Explicitly report what cannot be concluded due to missing telemetry.

## 16. Illustrative Kubernetes Inspection Commands

Execute only after confirming **context/namespace and permissions**. All names here belong to the lab.

~~~bash
kubectl -n logging-lab get pods -l app=orders-api
kubectl -n logging-lab get deploy orders-api
kubectl -n logging-lab logs deploy/orders-api --since=15m --tail=200 --timestamps=true
kubectl -n logging-lab get events --sort-by=.lastTimestamp
~~~

Explanation:

- `get pods`: identifies running pods, restarts, readiness, replica count, and placement; this command alone does not diagnose every root cause.
- `get deploy`: checks rollout status, replica count, and generation.
- `logs deploy/orders-api`: views logs of one pod selected by kubectl for the workload; **this does not mean you have retrieved logs from all replicas**.
- `--since=15m` and `--tail=200` limit output so you do not pull excessive sensitive data into your terminal or ticket.
- `get events`: views cluster/namespace activities; event retention is also bounded.

**Do not run** `kubectl delete pod`, `rollout restart`, `scale`, or edit a ConfigMap/Secret just to view logs. If mitigation is needed, use a separate change approval and rollback process.

For Logback/JUL setups that write to files inside a container, `kubectl logs` may **not contain** the file appender's contents. Verify the environment's log collection path (sidecar, shared volume, node agent, or direct OTLP).

## 17. Correlation: Do Not Trace Using a Single Message Sentence

When an incident spans an API gateway, service, queue, and consumer, one request can emit many logs across multiple processes. The runbook should prioritize:

- `trace_id` to link spans/logs per the tracing contract.
- `request_id` to link events belonging to the same HTTP request.
- `message_id` or `event_id` for logical events and retries.
- `event_code` for stable event filtering independent of message wording.
- `service.name`, environment, and timestamp to narrow scope.
- `reason_code` to classify failures without dumping exception messages.

In the lab, `req-42` shares one trace ID across three events; `probe-42` has a different trace. If an on-call engineer lumps all four events together and declares "request req-42 recovered," that is a **correlation mistake**.

A trace may be sampled and lack complete spans. Failing to find a trace **does not prove** an event never happened; rely on request IDs, event IDs, and other metrics. Never use trace IDs as metric labels with unbounded cardinality.

## 18. Interpreting Severity and Choosing Signals

JUL uses `SEVERE`, `WARNING`, `INFO`, `CONFIG`, `FINE`, `FINER`, `FINEST`. SLF4J/Logback/Log4j 2 typically use ERROR/WARN/INFO/DEBUG/TRACE.

**Runbook rules:**

- Before querying `severity=ERROR`, verify whether the pipeline maps **JUL SEVERE → ERROR**.
- A `WARNING` can be a high-severity incident if it indicates data loss; a `SEVERE` is not automatically a SEV1.
- Do not enable TRACE system-wide to find a single request ID if structured INFO/WARN already provides enough context.
- A single failure can emit multiple lines across controller/service/callback/retry; count **logical events/request failures** by event code/ID rather than counting lines containing `ERROR`.
- Logger levels/filters can differ between the JVM and appender, and the Collector may still apply drop/sampling processors.

Only change levels dynamically if the framework supports governed management. JUL has `Logger.setLevel`; in a real JVM, changing it affects event volume and requires a revert plan. Logback/Log4j 2 have their own management APIs/configs; do not assume an actuator endpoint exists in every Java service.

## 19. Preserving Evidence When Data Loss or Security Breach Is Suspected

If an incident shows signs of affecting integrity, audit, or security:

1. Record the incident ID, time, environment, and affected resources.
2. Keep **minimal yet sufficient** permitted metadata: event IDs, hashes if required by policy, timestamps, error codes, redacted configs, and metrics.
3. Do not delete indices, files, or queues to reclaim disk space without consulting the data owner and responsible parties.
4. Do not copy raw production logs into unapproved email or chat.
5. Do not accidentally alter artifacts/evidence by modifying the log source.
6. Follow legal hold/retention exception procedures as appropriate.
7. Distinguish "logs cannot be queried" from "evidence was actually deleted"; a backend may hide records due to permissions/time range, or they may reside in cold tier.
8. If a secret entered logs, coordinate with security to handle permissions, copies, credential rotation as needed, and scope investigation.

**Operational logging does not replace an audit trail** that has dedicated immutability or preservation requirements. If the business requires auditing, the runbook must point to the appropriate retention system rather than relying on stdout as the sole evidence.

## 20. Log Pipeline Failures from Backend 429/503, Queues, and Retries

Collectors, exporters, or shippers may encounter:

- `429 Too Many Requests` or quota throttling.
- `503 Service Unavailable` from the gateway/backend.
- Timeouts where it is unclear whether downstream received the batch.
- Queue full / agent buffer pressure.
- Ingest rejects due to schema/index mapping.
- Authentication/TLS errors.
- Disk full or checkpoint failures.

**Diagnosis by symptom:**

| Signal | Possible Explanation | First Action |
| --- | --- | --- |
| Continuous Exporter 429 | Throttling/quota | Measure ingest rate, backoff, pending queue, rate-limit contract |
| Exporter 503 | Backend/gateway unavailable | Check health, retry policy, and queue deadline |
| Parse errors | JSON/CRI/multiline violates schema | Inspect synthetic/redacted sample and parser config |
| Growing queue, no exports | Downstream slow or unreachable | Monitor backlog, disk/memory, alerts |
| Retries rising with duplicate records | ACK response may be lost | Use event IDs where appropriate and check delivery semantics |
| No data from one pod | Agent path/permission/metadata error | Compare local source against shipper receiver |
| Query misses despite export success | Index reject, tenant/time range/mapping | Check ingestion and search API |

Do not respond to every 429 by increasing concurrency indefinitely; that can push you further over quota. Do not grow RAM queues indefinitely trying "never to lose a log": a crash can lose all pending records, and memory pressure can impact the application.

For mandatory audit logs, consider a durable recorder/queue independent of the best-effort diagnostic log pipeline.

## 21. Disk Pressure, Rotation, and Retention

When a node's disk fills up due to logs, the runbook must distinguish:

- **Active files** currently written by a Java appender.
- **Rotated archives** managed by Logback/Log4j 2 policies.
- **Container runtime logs** whose rotation is managed by kubelet.
- **Agent spool/queue** which may hold unexported data.
- **Backend indices/object storage** with their own lifecycle.
- **Snapshots/backups/exports** with independent retention and holds.

Read-only actions should prioritize measuring usage, archive age, file count, growth rate, and pending shipper queue. **Do not blindly run `rm -rf` or `truncate` on active files**: this can destroy evidence, fail to fix the root cause, and even fail to free expected disk space while file descriptors remain open.

**Approved mitigations** may include temporarily lowering DEBUG, rate-limiting non-essential logs, adding controlled capacity, or tuning shipping/rotation. For audit/security logs, premature deletion can violate policy; escalate to the proper owner.

**Retention is not just `maxHistory`.** Logback's local archive retention does not delete data already indexed in the backend; backend retention does not delete local files either. When assessing log completeness, account for all copies.

## 22. When to Escalate

A runbook must state **specific triggers** and relevant roles, not just "contact the person in charge":

| Symptom | Team to Engage | First On-Call Action |
| --- | --- | --- |
| 503 spike affecting many customers | Service owner + incident commander | Verify impact, timestamp, request sample |
| Clear dependency timeout across many requests | Dependency/DB owner | Share reason codes, safe metrics/timeline |
| No logs across all services/clusters | Platform/observability | Check Collector/backend/agent health |
| Logging pipeline dropping audit/security events | Security/compliance + platform | Preserve evidence, determine severity/hold |
| Disk pressure threatening workload stability | Infrastructure owner | Gather metrics, prepare safe mitigation |
| Suspected token/PII exposure | Security/privacy | Stop sharing raw logs, trigger incident process |
| Rollback or production config change needed | Change approver + service owner | Present evidence and rollback plan |
| Conflicting signals, root cause unclear | Incident lead / SRE | State uncertainty clearly and split investigation tracks |

Specific escalation timelines are governed by the organization's on-call policy. **Do not fabricate phone numbers, chat room IDs, or internal SLAs** in a runbook. Link to verified directories/on-call schedules when deploying to production.

## 23. How to Write a Useful Incident Update

An update should separate **facts, hypotheses, and actions**:

~~~text
Incident: INC-TEST-042 (lab)
Scope: orders-api / staging / route /orders
Observed: 503s spiked in the investigation window; logs show
          REQUEST_FAILED reason_code=UPSTREAM_UNAVAILABLE
          and DEPENDENCY_TIMEOUT reason_code=DB_TIMEOUT.
Confirmed: request req-42 failed; independent readiness probe probe-42 succeeded.
Unknown: whether service-wide error rate has returned to baseline;
         whether the dependency is the root cause or a consequence of high load.
Action: cross-check dependency metrics and release timeline,
        evaluate mitigation only after verification.
Next update: per approved incident coordination schedule.
~~~

Do not write "the database is dead" just because one log message says timeout. Do not write "fully recovered" just because a readiness probe returned 200. If telemetry is missing, explicitly state **the gap** instead of guessing the outcome.

Updates do not need raw payloads, session cookies, or full stack traces. Providing request/trace IDs is enough for authorized personnel to pull additional data from the appropriate system.

## 24. Recovery Confirmation Criteria — Never Rely on a Single Signal

Require at least three layers:

**A. Service health:** Error rate, latency, and throughput return to acceptable thresholds over sufficient traffic; readiness/liveness are stable; no ongoing cascading failures.

**B. Business correctness:** Critical operations return valid results, no data loss/duplication beyond contract, queue/retry backlogs are draining, and reconciliation (if applicable) is verified.

**C. Observability restored:** Logs from canaries/new requests appear at the source, shipper/Collector, and backend search; exporter queues are not growing unboundedly; telemetry-loss alerts have cleared for a stable period.

**Do not treat the following as sufficient:** A single successful request, a READY pod, one INFO `RECOVERY_PROBE_OK`, or temporarily muting an alert. Post-mitigation observation time must align with SLOs and incident severity, not just a few seconds to close a ticket quickly.

If the log pipeline is still broken, you may need to keep the incident open or file a clear follow-up owner even after HTTP 503s subside.

## 25. Shift Handoff

A handoff should include:

- Incident ID, current owner, severity level, and incoming on-call engineer.
- Scope (service/env/region/tenant), start time, and change timestamps.
- Verified impact (request errors, availability, backlog, user impact).
- Safe log queries or event IDs used; **do not paste raw log secrets**.
- Ruled-out hypotheses and hypotheses still pending verification.
- Actions taken, approvals, outcomes, config changes made, and how to revert them.
- Active mitigations and metrics to watch.
- Data risks, legal holds, logging gaps, and Collector/backend status.
- Immediate escalation triggers and next responsible owner.
- Review/runbook update deadlines per process.

**Hand off only when the incoming engineer acknowledges** if required by on-call policy. A dashboard link without interpretation and clear scope is not a sufficient handoff.

## 26. Post-Incident Review and Runbook Updates

After recovery, conduct a systematic review:

1. UTC timeline: alert, first response, triage, mitigations, recovery, closure.
2. What the **user impact** and actual blast radius were.
3. Which root cause is supported by evidence; which hypotheses remain unconfirmed.
4. Why alerts did/did not fire accurately and how early the signals were.
5. Which logs were useful, which were missing, and whether gaps came from the **application** or the **pipeline**.
6. Whether correlation IDs helped link request/queue/consumer.
7. Whether there was excessive INFO/DEBUG noise or data leaked in exception messages.
8. Whether mitigations caused side effects like restart loops or retry storms.
9. Which runbook steps confused readers or lacked clear permissions/endpoints.
10. Action items with owners, acceptance criteria, and review due dates.
11. Update the runbook version and re-test after configuration changes.
12. Capture lessons learned and preventive actions without blaming individuals.

A good runbook **must be rehearsed** after major changes to architecture, logging backends, clusters, or alert rules. Documentation that has never been tested can give on-call engineers false confidence.

## 27. Advanced Rehearsal: Safe Failure Injection

Execute in **staging or a simulated environment**, never breaking production:

| Scenario | Lab Action | What to Verify |
| --- | --- | --- |
| Healthy baseline | Run `healthy` | Two JSON records, including `REQUEST_SUCCEEDED=200` |
| Dependency timeout | Run `incident` | `WARNING DEPENDENCY_TIMEOUT` then `SEVERE REQUEST_FAILED=503` |
| Correlation | Filter `req-42` | Three events share the same trace; probe is not mixed in |
| Secret test | Search `FAKE_TOKEN_NEVER_LOG` | Absent from stdout/event sink |
| Wrong time window | Query a window outside demo timestamps | Missing records **do not mean** records were never emitted |
| Severity mapping | Compare JUL `SEVERE/WARNING` with backend | Backend preserves/maps per contract |
| Missing logs | Block source in test fixture | Runbook detects telemetry gap via positive control |
| Collector outage | Mock receiver returning 503 | Queue/retry/drop follows policy, alert fires |
| Exporter 429 | Mock throttling | Backoff and queue limits engage |
| Duplicate delivery | Mock ACK loss then retry | Distinguish logical event ID from transport attempts |
| Rotation/CRI | Use filelog/container fixture | Parser preserves event boundaries, no out-of-contract loss/duplication |
| Privacy | Synthetic secret/CRLF in fixture | Masked/escaped through to final sink |
| Recovery probe | Run probe after failure | Single probe is not treated as service recovery |
| Handoff | Rotate on-call role in lab | Incoming engineer reconstructs timeline and next steps |

**Acceptance:** The practitioner must be able to explain *why* the same request logs WARNING then SEVERE, why a probe does not confirm recovery, and why logs missing from the backend may be caused by the exporter rather than the logger.

## 28. Upgrade Project: Adding a Real Collector and Backend in Staging

If Docker/Kubernetes/Collector is available in a test environment, extend the setup:

~~~text
LoggingRunbookLab (or instrumented Java service)
    │ stdout JSONL / file JSONL / OTLP exporter
    ▼
Runtime + agent (if using stdout/file)
    ▼
Collector receiver/processor/exporter
    ▼
Test backend index/search
    ▼
Query by eventId / requestId / traceId
~~~

**Verification steps:**

1. Confirm the transport path: stdout JSONL needs an agent/filelog parser; **do not send raw JSONL to an OTLP receiver** expecting it to become a standard LogRecord.
2. Use **unique** test event IDs per staging run; fixed lab IDs are only for illustrative output.
3. Verify mapping: service usually lands in Resource, severity in its dedicated field, and event code/correlation in attributes per schema.
4. Wait for events to become searchable by polling with a deadline, not a single `Thread.sleep` followed by declaring FAIL.
5. Verify all event IDs, not just counts; account for duplicates from retries.
6. Check parser errors, receiver rejections, exporter failures, queue depth, and backend ingest errors.
7. Emit an approved synthetic privacy sentinel event and verify it does not appear in the final sink, pipeline error logs, or test backups.
8. Check dashboard/query time ranges based on event time versus ingest time.
9. Clean up test logs and stop test fixtures; do not leave debug exporters or trace logging enabled indefinitely.

A pipeline configured in the Collector is not necessarily active: receivers, processors, and exporters must be wired into **`service.pipelines.logs`**. Testing through to backend queries confirms the end-to-end path, subject to storage durability guarantees.

## 29. Anti-Patterns in Operational Runbooks

| Anti-Pattern | Consequence | Fix |
| --- | --- | --- |
| "On error, check the logs" | Does not say where to look or what to search | Provide queries, event codes, scope/time window |
| Looking only at `ERROR` | Misses critical WARN or data loss | Combine metrics, event taxonomy, impact |
| Concluding root cause from one text line | Error-prone since timeout is just a symptom | Cross-check dependency metrics/traces |
| Confusing service and logging pipeline | No logs leads to "no errors" conclusion | Triage two independent tracks |
| Pasting full logs into tickets | Leaks PII/tokens | Share IDs/sanitized evidence |
| Querying without time/env | Stale results cause noise | Clear scope, UTC timestamps |
| Treating one passing probe as recovery | Errors may still impact users | Check traffic, 5xx, latency, and business correctness |
| Restarting all pods immediately | Loses state, adds load, destroys evidence | Evaluate approved mitigations |
| Enabling DEBUG indefinitely | High log volume, security risk, disk full | Set expiry, scope, revert plan |
| Changing retention/deleting files for disk space | Can lose audit/evidence | Follow ownership/hold and cleanup policy |
| Assuming exporter HTTP 200 = durable index | Ignores storage boundary | Query and verify backend contract |
| Not monitoring the log collector | Pipeline can silently drop logs | Internal telemetry and canaries |
| Commands with unclear namespace/role | Accidental execution in production | Put scope/context/checklist before commands |
| No owner/escalation path | On-call does not know whom to page | Link service catalog and on-call |
| Copying sample alert thresholds to production | Alert noise or missed failures | Tune to SLOs/baselines |
| Skipping drills after infra updates | Stale runbook | Periodic drills and owner reviews |

## 30. Hands-On Project Grading Rubric

Evaluated across four categories; each category is graded **pass/fail** based on evidence:

**A. Operational documentation** — Runbook includes scope, prerequisites, owner, alerts, severity, safety, triage, mitigation, escalation, recovery, handoff, and post-incident.

**B. Java 17 lab** — Compiles/runs `healthy` and `incident`; valid JSONL output; produces two and four records respectively; accurate event codes/HTTP statuses/correlation; fake secret never appears.

**C. Engineering judgment** — Clearly states the Logger → stdout → agent → Collector → backend boundaries, does not confuse "no logs" with "no errors," does not declare a single probe as full recovery, and does not treat exporter retries as exactly-once.

**D. Safety and repeatability** — No destructive actions on real environments; no real credentials/PII; knows how to revert debug config; includes test evidence and a process to update the runbook when architecture changes.

**Completion criteria:** All four categories pass; answers to the questions in the next section are backed by concrete output and actions, not just theory.

## 31. Self-Check Questions

1. Why does `log.info("done")` not prove the search backend received the event?
2. How does a **runbook** differ from introductory logging API documentation?
3. In the lab, why does `RECOVERY_PROBE_OK` not prove request `req-42` succeeded?
4. Which fields help filter a request's log chain instead of free-text searching?
5. Why shouldn't every `WARNING` be escalated to SEV1?
6. When dashboards show no logs while request metrics keep rising, which two investigation tracks must run?
7. If local stdout has records but the backend does not, which hops should be checked?
8. Why is `kubectl logs deploy/orders-api` not guaranteed to return logs from every replica?
9. When a Collector reports exporter 429s, why can increasing retry concurrency indefinitely make things worse?
10. Why does HTTP 200 from a proxy/Collector not automatically prove the backend durably indexed the data?
11. Why can a query showing "no logs in the last 5 minutes" be misleading when clocks and index lag diverge?
12. If a token is suspected to have been logged, what is the first step?
13. Can a best-effort DEBUG channel be shared for audit logs that require evidence preservation?
14. Why must a runbook specify who approves mitigations/rollbacks?
15. When is an on-call engineer allowed to mark a service recovered?
16. Does testing the two lab modes confirm that a real Collector/Kubernetes/backend works?
17. Why should each staging run use a unique test event ID?
18. If ERRORs disappear after a mitigation while 503s remain high, what must the runbook conclude?
19. What information must be handed off during a shift change?
20. What proves a runbook is still usable after changing the logging backend or alert rules?

**Suggested answers:** (1) sink, transport, Collector, and backend hops remain; (2) a runbook is an actionable decision procedure; (3) the probe has a different request/trace and only checks one endpoint; (4) service, event code, request/trace ID, time, reason; (5) severity must reflect impact; (6) application incident and telemetry incident; (7) runtime/agent/Collector/exporter/backend/query; (8) it picks one representative pod rather than aggregating all pods; (9) exceeds quota, growing queues and load; (10) ACK differs from indexed/durable state; (11) time window/ingestion delay; (12) stop spreading raw logs, trigger security process; (13) no, if separate durability is required; (14) reduces data-loss-inducing actions; (15) metrics, business correctness, and observability are all verified; (16) no, the lab only tests at the source; (17) avoids confusing stale events; (18) not recovered yet, continue investigating; (19) impact, timeline, safe evidence, mitigation, owner/next steps; (20) successful drill results and updated review.

## 32. Production Runbook Implementation Checklist

1. [ ] Title/ID/version, service owner, approver, and review schedule are confirmed.
2. [ ] Env/region/tenant scope, dependency graph, and service catalog links are accurate.
3. [ ] Alert triggers, severity policy, dashboards, and SLOs/baselines are verified.
4. [ ] Read-only permissions, account/cluster context, and safety guardrails are clear.
5. [ ] Steps to verify incidents using metrics/traces before reading a single log line.
6. [ ] Backend query syntax by event code, request/trace ID, and time window.
7. [ ] Clear separation between logger sink, shipper/agent, Collector, and backend/query.
8. [ ] Runbook includes branches for missing logs, parse errors, 429/503, and disk pressure.
9. [ ] Security requirements for handling PII/tokens/stack traces and escalation mechanisms.
10. [ ] Mitigations include approvals, rollback plans, limits, and impact checks.
11. [ ] Recovery criteria cover user impact, business correctness, and telemetry health.
12. [ ] Handoffs and incident updates separate facts, hypotheses, and actions.
13. [ ] Post-incident follow-ups have owners, review dates, and acceptance criteria.
14. [ ] Rehearsed `healthy`/`incident` with Java 17, verifying JSONL and correlation.
15. [ ] If production uses a Collector/backend, tested end-to-end in staging.
16. [ ] Rehearsed after changes to frameworks, agents, Collectors, backends, or alert rules.

**Practical takeaway:** A good runbook is not a long list of commands. It is an **evidence-driven decision chain** that tells the on-call engineer *when to read where, when to change what, when to ask for help, and by what criteria recovery can be declared*.

## 33. Official References for Verifying and Updating Runbooks

- [Oracle Java SE 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): Logger, levels, `LogRecord`, and handlers.
- [Oracle Java SE 17 — LogRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html): timestamps, parameters, logger metadata.
- [Oracle Java SE 17 — Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html): `publish`, `flush`, and lifecycle.
- [Oracle Java SE 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html): UTC timestamps in the lab.
- [SLF4J — Manual](https://www.slf4j.org/manual.html): facade, levels, parameterized/structured logging.
- [Logback — Manual](https://logback.qos.ch/manual/index.html): appenders, logger hierarchy, configuration.
- [Apache Log4j 2 — Manual](https://logging.apache.org/log4j/2.x/manual/index.html): logging API, configuration, layouts, appenders.
- [Kubernetes — Logging Architecture](https://kubernetes.io/docs/concepts/cluster-administration/logging/): stdout/stderr, container logs, node agents, and node-level retention.
- [Kubernetes — kubectl logs](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_logs/): `--since`, `--tail` flags, pod/deployment log retrieval.
- [OpenTelemetry — Collector Troubleshooting](https://opentelemetry.io/docs/collector/troubleshooting/): receivers, processors, exporters, debug, telemetry when logs are lost.
- [OpenTelemetry — Collector Configuration](https://opentelemetry.io/docs/collector/configuration/): service pipeline wiring, components, exporters.
- [OpenTelemetry — Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/): Resource, Body, Severity, Attributes, TraceId/SpanId.
- [Prometheus — Alerting Best Practices](https://prometheus.io/docs/practices/alerting/): actionable alerts with useful labels/annotations.
- [Google SRE Book — Managing Incidents](https://sre.google/sre-book/managing-incidents/): roles, command structure, and communication during incidents.
- [Google SRE Workbook — Incident Response](https://sre.google/workbook/incident-response/): incident response practices and process improvement.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): what to log/not log, sanitization, security, and access.
