# Logging Runbook in Java Production

## 1. Purpose and Usage Principles

A **logging runbook** is an actionable operational document used when the system that writes, ships, searches, or protects logs in production encounters an incident. The runbook must help on-call engineers quickly answer: **what the symptom is, at which stage data is lost, what the impact is, what safety checks are needed, how to recover, how to verify, and when to escalate**.

This is not a list of commands to “delete log files to free up disk space” or “enable DEBUG globally.” Logs are both operational data and potential security evidence. Recovery actions must protect **the service, secrets, audit event completeness, and investigation capability**.

This runbook applies to a Java application using SLF4J with Logback/Log4j2 or `java.util.logging` (JUL), running on a VM or Kubernetes, shipping logs via stdout/file/collector to a centralized storage system. Service names and namespaces below are **illustrative examples**, not representations of a real environment.

### Expected Outcomes After Handling

- Identify the **actual failure point** along the logging pipeline, rather than seeing an empty dashboard and concluding the application is not logging.
- Restore the ability to **emit, ship, search, and view logs** with an honest assessment of data loss.
- Avoid adding latency to the request path through uncontrolled changes.
- Avoid accidentally logging passwords, tokens, cookies, PII, or payment details during investigation.
- For critical audit/security events, distinguish between **not yet visible**, **delayed**, **dropped**, and **durably stored**.
- Record who did what, timestamps, before/after evidence, monitoring duration, and handoff status.

## 2. Map of a Log Event in Production

```text
[Request / Job / Business operation]
                 |
                 v
        [Java call-site]
                 |
          [Level / Filter]
                 |
            [Log event]
            /         \
           v           v
  [Sync appender]   [Async queue] --(full: block / discard / fallback)
           |           |
           |           v
           |      [Consumer]
           |           |
           +-----+-----+
                 |
          [Encoder / Layout]
                 |
         [stdout / file / socket]
                 |
         [Node agent / collector]
                 |
          [Buffer / Transport]
                 |
        [Gateway / Ingestion API]
                 |
       [Parser / Pipeline / Index]
                 |
      [Search API / Dashboard / Alert]
                 |
     [Archive / Snapshot / Export]
```

**Observation point definition:** a completed `logger.info` call does **not** guarantee the backend has received or stored the event. With async logging, it may only be enqueued. An HTTP success response from a collector may only confirm batch receipt, not that the event is searchable or in the archive.

### Fault Isolation Table

| Checkpoint | Evidence to Look For | Common Causes |
| --- | --- | --- |
| Call-site | Code actually executed, appropriate level | Branch not reached, logger disabled, exception before log |
| Logger/filter | Effective level, marker/filter | Log filtered out by logger, appender, or sampling |
| Appender/encoder | Error counters, status, file/stdout | Invalid pattern, formatter error, appender failed to start |
| Async queue | Depth, enqueue wait, dropped, consumer lag | Queue full, slow consumer, discard policy |
| Node stdout/file | Whether event appears at the source | Wrong file path, permissions, rotation, disk full |
| Agent/collector | Read offset, parser errors, send/retry | Log path not mounted, pipeline crash, network/TLS |
| Backend/index | Ingest rate, rejected events, mapping | Quota, index lifecycle, malformed JSON, tenant routing |
| Search/dashboard | Time window, permissions, query, timezone | Wrong filter, index alias, field mapping, clock skew |
| Archive/export | Inventory, checksum, restore | Retention policy, snapshot, stale replica |

Do not jump straight to backend configuration before knowing whether the log exists at the app source. **Move from the closest point with evidence** to the next stage.

## 3. Incident Severity Levels and Responsibilities

The levels below are **operational guidelines**; cross-reference them with your organization's incident classification.

| Priority | Signal | Initial Action |
| --- | --- | --- |
| **P0 — Security Emergency** | Tokens/passwords/PII in logs accessed inappropriately; audit logs tampered with/deleted with signs of attack | Trigger security incident response, preserve evidence, limit exposure, and revoke secrets |
| **P1 — Critical Impact** | Loss of mandatory security/audit events; logging causes service outage or severe p99 degradation | Incident commander, application + platform + security owners coordinate |
| **P2 — Degraded Observability** | Logs delayed by several minutes, growing backlog, partial service missing from dashboard | Isolate the pipeline stage and apply controlled remediation |
| **P3 — Limited-Scope Issue** | Misconfigured single logger, non-audit field missing, broken dashboard query | File ticket and change through standard process |

At minimum, assign these roles: **incident owner** to coordinate, **application owner** to check code/logger, **platform/observability owner** to check agent/collector/backend, **security/compliance owner** when secrets or audit logs are involved, and **service on-call** when throughput/latency is impacted.

**Do not self-escalate privileges or delete evidence.** If an action exceeds on-call permissions, trigger escalation. Legal situations, personal data deletion, and legal holds require proper approval.

## 4. First Five Minutes: Safe Inspection Actions

1. **Record detection time (UTC)**, service, environment, instance/pod, affected business flows, and specific symptoms.
2. **Confirm impact scope:** all logs missing or only DEBUG, one pod or all pods, only dashboard or alerts too, any audit/security events affected?
3. **Do not enable TRACE/DEBUG globally**, do not dump request bodies, do not mass-restart, and do not delete files/indices to “clean up” before understanding the root cause.
4. **Pick a reference time window** (e.g., 15 minutes) and keep a consistent timezone; note timestamps of recent config/deploy changes.
5. **Gather evidence at the source** using read-only operations: metrics, pod status, existing logs, collector errors, timestamp of the latest event.
6. **Form a falsifiable hypothesis**: “app is not emitting,” “agent is not reading,” “queue is full,” or “backend index is misconfigured.”
7. **Communicate impact using facts**, explicitly stating what is not yet verified. Avoid claiming “no logs were lost” just because the producer reported no errors.

### Incident Note Template

```text
Incident ID: INC-20261110-001 (example)
Detected at: 2026-11-10T03:00:00Z
Service/environment: checkout-api / production
Symptom: INFO events appear delayed in the search backend
First known good event time: 2026-11-10T02:47:00Z
Latest observed ingestion time: 2026-11-10T02:51:00Z
Scope: single deployment, other services unconfirmed
Business impact: no request errors detected yet; audit status under check
Evidence: pod running; collector retry counter increasing
Current hypothesis: ingestion lag, event loss not yet proven
Action owner: observability on-call
Next checkpoint: after each controlled change
```

Sample values are **mock data**, not measurements from a real system. Never put access tokens, passwords, raw session cookies, or user content into tickets.

## 5. Read-Only Inspection Commands for Kubernetes

The following examples assume namespace `prod` and deployment `checkout-api`. **Replace with names confirmed in your operational environment.** Use only when authorized and avoid leaking data when sharing outputs.

```bash
# Pod status and serving instances
kubectl -n prod get pods -l app=checkout-api -o wide

# Deployment status, revision, and replica count
kubectl -n prod get deployment checkout-api
kubectl -n prod describe deployment checkout-api

# Fetch a portion of recent logs from the deployment;
# this command does not prove all replicas were captured.
kubectl -n prod logs deployment/checkout-api --since=15m --tail=100 --timestamps

# Infrastructure events and signs of restart/eviction
kubectl -n prod get events --sort-by=.lastTimestamp
```

**Limitations:** `kubectl logs deployment/...` may pick a single pod; do not treat it as complete output for the entire deployment. For multi-container pods, specify the container or use appropriate flags; how much history `kubectl logs` can read depends on container runtime/node retention. Do not assume logs are “lost” solely because `kubectl logs` no longer has the file after a pod restart or log rotation.

Fetch collector information from the **actual namespace and selector confirmed by the platform team**. For example:

```bash
kubectl -n observability get pods -l app=otel-collector -o wide
kubectl -n observability get deployment
```

The selector `app=otel-collector` is illustrative only: clusters may use DaemonSets, Fluent Bit, Vector, OpenTelemetry Collector, or different labels. Do not restart/delete the collector to test an initial hypothesis.

### VM or systemd Environments

```bash
# Example Java service managed by systemd
systemctl status checkout-api.service --no-pager
journalctl -u checkout-api.service --since "15 minutes ago" --no-pager

# Check filesystem status holding logs when appropriate
df -h
```

Do not run tools that print the entire environment or secret configurations into a ticket. For file appenders, verify the actual output path and granted read permissions.

## 6. Metrics to Open on the Dashboard

The names below are **suggested metric contracts**, not default metrics from Java, SLF4J, Logback, or every collector:

| Metric | Question Answered |
| --- | --- |
| `logging_events_attempted_total` | How many events did the application attempt to log? |
| `logging_events_filtered_total` | How many events were intentionally dropped by level/filter? |
| `logging_events_enqueued_total` | How many events entered the async queue? |
| `logging_events_dropped_total` | Are events being lost due to overload/exception/policy? |
| `logging_queue_depth` | Is the current backlog growing or shrinking? |
| `logging_enqueue_wait_seconds` | Is the producer blocking when the queue is full? |
| `logging_sink_errors_total` | Are file/socket/appender writes failing? |
| `collector_received_total` | How many events did the collector receive from the source? |
| `collector_sent_total` / `collector_retry_total` | Are backend sends succeeding or retrying? |
| `backend_ingested_total` / `backend_rejected_total` | Is the backend accepting or rejecting data? |
| `event_to_search_lag_seconds` | How long until logs become searchable in the backend? |
| `last_seen_event_timestamp` | When did the data gap start? |
| `audit_sequence_gaps_total` | Are there gaps in a designed sequence mechanism? |
| `service_request_duration_seconds` | Is logging impacting request p95/p99 latency? |
| `process_cpu_usage` / GC / heap | Resource cost when changing logging levels |

If a metric does not exist, record “not instrumented”; do not substitute 0. **Zero means something different from no data.**

### Notes on Reconciling Counters

An “attempted” counter measures logger calls, “enqueued” measures events accepted by the queue, and “backend ingested” measures post-parser writes—these often have **different latencies and reset times**. Do not compare them across misaligned windows and conclude all differences are lost logs. Additionally, replay/retry and duplicates can make ingested counts higher than unique event counts.

For reliable reconciliation, define a **measurement boundary**, standardize event IDs, observation windows, retry semantics, and filtered-by-design cases. A “messages accepted” chart is not proof of durable storage.

## 7. Playbook A — No Logs Visible in Dashboard

**Symptom:** the system handles requests normally, but the search UI shows no new logs; log-based alerts do not fire either.

### Step A1. Verify Query and Time Range

- Check environment, service, tenant, index/data stream, namespace, route, level filter, and query fields.
- Compare event timestamp with ingestion timestamp. Client clock skew or collector timezone mismatch can place events outside the search window.
- Check search permissions: users lacking permissions may see empty results or query errors.
- Search by **permitted** event ID/correlation ID; do not use raw tokens/emails as filters.

**Do not conclude “app is not logging” after checking only one dashboard.**

### Step A2. Is the Application Actually Emitting Events?

- Does the endpoint/job execute the log statement?
- What is the effective logger level? Is a parent/root logger inheriting an unexpected level?
- Is a filter, marker, sampling rule, or appender threshold dropping the event?
- Did the appender initialize successfully? Are there Logback config errors at startup?
- In Spring Boot, `logging.level.com.example.checkout=INFO` sets the level, not a guarantee that the sink will write.
- With JUL, both logger and handler have separate levels/filters. With Logback/Log4j2, backend and location filters determine acceptance.

**Illustrative Spring Boot configuration** example—do not use as a production default without evaluation:

```properties
logging.level.root=INFO
logging.level.com.example.checkout=INFO
```

If INFO is not appearing, do not rush to switch root to DEBUG. Identify the target logger and log source first.

### Step A3. Are Events Present at stdout/file?

If the source has logs but the backend does not, move on to the agent/collector. With async logging, check queue depth/drops and the consumer; when the queue is full, events may be discarded by policy without throwing an exception to the caller.

If the source **has no** logs, investigate code paths, effective level, filters, appenders, file permissions, or startup errors. Never assume `logger.info()` always emits a text line.

### Step A4. Collector and Backend

- Is the agent reading the right file/container ID? Is the offset stuck after rotation?
- Is the collector parser reporting malformed JSON, oversized payloads, quota limits, or TLS errors?
- Were there route/index/tenant mapping changes in the latest deployment?
- Is the backend rejecting writes due to read-only index, exhausted quota, mapping conflict, or permissions?
- Did index lifecycle/retention delete the backing index being queried?

**Safe actions:** fix misconfiguration on a reviewed branch, roll back the faulty deployment, or resolve connectivity/permissions with the owner. Do not blindly replay from old files before evaluating duplicate/event ID handling and ingest volume.

### Close Playbook A When

- The same non-secret test event appears at both the expected source and sink.
- A backend query by the exact event ID returns data within SLO.
- Counters and lag are stable; corresponding parser/auth errors are gone.
- Historical data gaps and backfill needs have been assessed.

## 8. Playbook B — Delayed Logs, Collector Retries, or Queue Backlog

**Symptom:** source has logs, but the dashboard lags; queues grow, collector retries increase, or ingest latency exceeds SLO.

### Isolation

1. Check **event time vs ingestion time** using a few permitted reference events.
2. Inspect both the **Java appender** queue and the **agent/collector** buffer; the two stages can bottleneck independently.
3. Check source throughput, sink speed, retry/backoff behavior, and network/TLS status.
4. Check if the sink is slow at processing/parsing/indexing; are there oversized or malformed records?
5. Check recent deployments, DEBUG/TRACE increases, traffic spikes, and encoder changes.

```text
If incoming_rate > sustained_consumption_rate:
    backlog grows, regardless of queue size
```

A large queue can absorb short bursts but **does not increase long-term sink capacity**.

### Risk-Based Remediation

- Reduce **non-essential noisy logs** at the source via reviewed level/rate-limit changes; never drop mandatory audit logs.
- Limit oversized messages or expensive formatters; avoid dumping unnecessary bodies/headers/stack traces.
- Address collector or backend capacity/stability with the owner, watching circuit breakers and throttling.
- If scaling collectors is needed, consider partitioning, duplicates, ordering, connection counts, and cost; adding replicas is not always faster.
- Clarify queue-full policy: **block producer**, **discard**, **fallback sync**, or **spool disk**. Each choice has trade-offs in latency, log loss, and durability.
- Drain spooled events in a controlled order; never purge a queue just to make a depth graph drop to 0.

**Do not treat low producer latency as a healthy system.** An async appender can return fast while collector backlogs grow and the backend is not searchable.

### Close Playbook B When

Queues stop growing under steady load, end-to-end log lag returns within target, retries/drops are recorded, and past data is processed or unrecoverable portions are classified.

## 9. Playbook C — Sudden Log Volume Spike, CPU/Disk Increase

**Symptom:** log event count or byte volume surges after a release, during a retry/error loop, brute-force traffic, or when someone enables DEBUG/TRACE. CPU, disk I/O, ingest cost, and request p99 may rise.

### Quick Checks

- When did the spike start, and which version/config change does it align with?
- Which package/logger, endpoint, or exception type is emitting the events? Use **metadata and sanitized samples**, avoiding sensitive content.
- Did the **number of events** increase, or the **size per event** (stack traces, JSON fields, bodies)?
- Is the collector starting to drop or is the queue filling up? Are disk quotas/rotation approaching limits?
- Is logging synchronous on the request thread? Is the appender contending on locks or writing slowly to console?
- Is there a real business error causing WARN/ERROR spikes? Do not just “turn down logging” and ignore the root cause.

### Priority Safe Actions

1. If this is an **application incident**, fix the root cause of repeated events; reducing spam is secondary.
2. For temporarily enabled DEBUG/TRACE, **revert the specific logger/package** per the change record if available; do not change root uncontrollably.
3. Remove unnecessary payload/raw object logging, preferring a safe-field allowlist.
4. Evaluate queue policy; blocking producers can hurt p99, while dropping can lose evidence.
5. Check disk/log rotation; do not delete active files or archives currently being tailed by the collector.
6. If storage/budget is near threshold, escalate to platform to add resources or adjust routing/retention per process.

**Do not delete log files still held open by a process file descriptor** expecting immediate disk reclamation: on many filesystems, space is not freed until the descriptor is closed. Also, do not truncate audit files without approval, as that destroys evidence.

### Verification

Monitor event rate, bytes/sec, CPU, GC, disk free, app p95/p99, dropped events, and collector lag after changes. A drop in CPU alone is not success if logs are now being dropped en masse.

## 10. Playbook D — Logging Slowing Requests or Hanging the Application

**Symptom:** request latency increases after a logging config change; thread dumps show appender/write/lock contention, or the async queue blocks producers.

### Common Causes

- `logger.debug("{}", expensiveObject.toString())` forces Java to evaluate arguments before the method call even when DEBUG is disabled.
- JSON formatters, stack traces, caller location, MDC snapshots, or serializing oversized objects.
- Slow I/O on synchronous file/console/network appenders on the request thread.
- `AsyncAppender` queue full; depending on policy, producers block or events are dropped.
- Lock contention or encoder/parser errors causing repeated retries/flushes.
- CPU/GC pressure from allocations when emitting high event rates.

**Suboptimal** code example:

```java
// Non-standalone snippet; requires logger and buildDebugSnapshot().
logger.debug("snapshot={}", buildDebugSnapshot());
```

Even with DEBUG disabled, Java executes `buildDebugSnapshot()` before calling the logger. Approach to consider:

```java
if (logger.isDebugEnabled()) {
    logger.debug("snapshot={}", buildDebugSnapshot());
}
```

This is still a snippet; if an appender filter later drops the event, some work may have already occurred. SLF4J 2.x offers a fluent supplier API in some scenarios—test against your actual version and backend.

### Investigation Procedure

1. Compare request latency, throughput, CPU, GC, and logging configuration before/after the change under the **same workload**.
2. If JFR or an approved profiler is available, check CPU hot methods, allocations, File/Socket I/O, and thread contention.
3. Separate the costs of **call-site**, **queue**, **consumer**, and **sink**; do not look only at how fast `logger.info()` returns.
4. Consider adjusting verbose loggers, formatters/fields, or sinks per plan; prefer the least invasive change.
5. For high traffic, check queue thresholds and behavior when the sink is slow. Test failure conditions in staging first if feasible.
6. Verify that mandatory security/audit records are not sacrificed just to lower p99.

Do not assume “async is always fast and lossless.” Service priority vs. log durability requirements must be decided in SLO/incident policies.

## 11. Playbook E — Tokens, Passwords, or PII Appearing in Logs

**Symptom:** a field containing secrets or sensitive data is written to stdout, stack traces, access logs, collectors, dashboards, or exports. This situation requires contacting security on-call per policy.

### Immediate Response

1. **Contain spread:** never copy raw tokens into tickets, chat, screenshots, or emails; use a case ID and sanitized samples.
2. **Stop new emission at the source:** identify the logger/encoder/endpoint/HTTP client/exception writing the data; apply a reviewed change to stop payload capture or switch to an allowlist of fields.
3. **Revoke or rotate exposed secrets** based on secret type and blast radius; deleting a log line does not invalidate a credential.
4. **Assess copy scope:** app file/stdout → collector buffer → index → archive → snapshot → export/download links.
5. **Restrict access:** temporarily lock down affected indices or exports if authorized by the appropriate owner.
6. **Preserve required evidence:** keep timelines, sources, and access/export logs; do not self-destruct data under legal hold or audit requirements.
7. **Permanent fix:** regression test with a mock canary, block sensitive bodies/headers, and check encoding/masking and dependency loggers.

### Easily Missed Indicators

- Raw `Authorization`, `Cookie`, or `Set-Cookie` in request/response headers.
- Tokens in **query strings or paths** of reset URLs.
- DTO `toString()` containing passwords/PII.
- HTTP client DEBUG logs or exception messages containing raw URIs/response bodies.
- Tracing baggage/MDC copied into every log.
- Dashboard masking applied, while raw indices/exports still retain the data.

**Do not rely solely on regex at the collector.** Data minimization must begin before the event is constructed. For data that should not be collected, the best solution is **never passing it to the logger**.

### Closure Criteria

Evidence confirms new emission is stopped, valid secrets have been handled, historical data scope and access permissions are classified, and security/compliance confirms the handling process is valid. Do not claim “no copies remain” without checking backups/exports.

## 12. Playbook F — Trace ID, Request ID, or MDC Missing/Incorrect

**Symptom:** searching by trace ID misses services, events from request A carry `tenant_id`/`user_id` from B, or async events lose correlation context.

### Causes

- Context was never created or propagated across thread pools, queues, or HTTP clients.
- `MDC.put` lacks `finally` cleanup; reused threads leak data between requests.
- Async logger reads MDC on the consumer thread instead of snapshotting at producer time.
- Client-supplied `traceparent` or `X-Request-ID` is not validated.
- Gateway alters/strips headers, downstream starts a new trace, or the log encoder fails to serialize MDC.
- Collector field mapping renames `trace_id` or nests it under an object.

### Remediation Steps

1. Pick a **secret-free** test request with a permitted request ID/trace ID.
2. Check at gateway, HTTP middleware, business events, async workers, collector, and backend to pinpoint where context is lost.
3. Verify IDs are generated/parsed per system spec and namespace; do not derive user identity from trace IDs.
4. Check MDC save/restore in `try/finally` and propagation in executor/task contexts.
5. Check encoder schema: is the `trace_id` key renamed, missing, or written as an empty string?
6. Test concurrency and tenant isolation with simultaneous requests.

SLF4J snippet requiring libraries and application context, **not standalone**:

```java
String before = org.slf4j.MDC.get("request_id");
org.slf4j.MDC.put("request_id", validatedRequestId);
try {
    handleRequest();
} finally {
    if (before == null) {
        org.slf4j.MDC.remove("request_id");
    } else {
        org.slf4j.MDC.put("request_id", before);
    }
}
```

This snippet only saves/restores **one key**. For multiple keys, framework context propagation or scoped MDC should be designed consistently; do not blindly call `MDC.clear()` when an outer layer still holds valid context.

**Warning:** a well-formatted `trace_id` does not mean the actor is authenticated. Security/audit logs require verified principal/workload identity, not client-chosen headers.

## 13. Playbook G — Wrong Retention or Logs Deleted Prematurely

**Symptom:** logs only go back a few days instead of the expected retention; files/indices/archives were purged, or historical queries return no data.

### Separate Three Scopes

| Scope | Mechanism | What to Check |
| --- | --- | --- |
| **Local file** | Logback `RollingFileAppender` / Log4j2 Rollover Strategy | Pattern, rollover, maxHistory, totalSizeCap, disk cleanup |
| **Container/node** | Kubelet/container runtime rotation | Node file limits, pod restarts/evictions, ship speed |
| **Backend/archive** | Index lifecycle, object lifecycle, snapshots | Index age, event time vs ingest time, retention class, legal hold |

**Rotation is not retention**, and retention is not **deleting all copies**. The backend deleting an index does not mean archives, snapshots, and CSV exports are gone.

### When Premature Deletion Is Suspected

1. Halt all non-emergency lifecycle changes; **do not disable all retention indefinitely on your own**.
2. Check event class, policy version, age calculation start date, timezone, and index rollover.
3. Confirm whether copies exist in archives/snapshots/backups and check restore permissions.
4. Check legal holds and authority to modify policies; if mandatory audit logs are at risk of loss, engage compliance/security.
5. Compare source data with backend data and clearly document what **may be permanently lost**; do not assume restores will succeed.
6. For policy changes, run dry-runs, impact count/size estimates, approvals, and rollback plans before applying.

**Do not run bulk deletes or index deletes to “test retention” in production.** Use a test environment and mock data to verify cleanup jobs.

## 14. Playbook H — Audit/Security Events Missing or Duplicated

**Symptom:** a permission change committed, but no audit event is found; or a single transaction has multiple SUCCESS records due to retries.

### Distinguish States

- **Attempted:** processing started.
- **Authorized/Denied:** authorization check result.
- **Committed:** business change committed.
- **Enqueued:** event entered a queue, not yet guaranteed durable.
- **Written/ingested:** sink/backend received per its own definition.
- **Indexed/searchable:** event is queryable.
- **Archived:** long-term storage confirmed per process.

If an application log emits `SUCCESS` before transaction commit and then rolls back, that is an **incorrect outcome**, not necessarily “lost logging.” If a request creates an async job, HTTP 202 means accepted, not completed.

### Procedure

1. Locate the business operation/transaction using a permitted ID.
2. Determine the true outcome timestamp from the database/outbox or business state.
3. Search for the event at the source, async queue/outbox, collector, and backend by `event.id`/`operation_id`.
4. Measure retries/duplicates and ingest time; avoid counting log lines as business operations under at-least-once delivery.
5. For high-durability audit requirements, evaluate a transactional outbox or dedicated audit store rather than relying on a debug log queue with discard policies.
6. If unauthorized evidence tampering/deletion is detected, preserve evidence and notify security immediately.

**Do not backfill historical events with guessed actors/outcomes.** If reconstruction is required, tag the source, timestamp, and confidence level of reconstructed events, keeping a trail of the backfill action.

## 15. Playbook I — JSON Logs, Schema, or Parser Suddenly Broken

**Symptom:** collector reports parse errors, dashboard is missing `trace_id` or numbers turn into strings after a deploy; source logs exist, but backend mapping is broken.

### Checks

- Are events JSONL or plain text? Are multi-line stack traces spilling outside JSON?
- Are CR/LF, quotes, and Unicode control characters properly escaped?
- Is `http.status_code` a number or string; does `duration_ms` use the right unit?
- Did the backend encoder / Logback layout / Log4j2 JSON Template Layout change?
- Is the collector parser/mapping reading flat keys or nested objects?
- Are there duplicate fields, field collisions, or index mapping conflicts?
- Are errors caused by oversized events or deeply nested payloads?
- Do logs contain untrusted data risking dashboard/CSV export injection?

**Syntactically** safe JSONL example:

```json
{"event.name":"checkout.failed","http.status_code":502,"duration_ms":36,"message":"gateway\nretry"}
```

Here `\n` is **inside the JSON string after escaping**, not a physical newline between two records.

### Remediation

1. Capture a **sanitized event** at the source and the post-encoder output.
2. Parse it with an independent JSON parser and check required fields/types.
3. Compare against the deployed schema contract/version.
4. If a new release/encoder broke the format, roll back the configuration per change process or roll out a small tested fix.
5. Reconcile rejected events and handle replay/backfill if truly needed, watching out for duplicates.
6. Verify dashboard/alert queries as well once the schema is restored.

Never force malformed JSON to look “valid” by stripping all quotes or dumping raw payloads into parser error logs.

## 16. Java 17 Runnable: Simulating Incident Snapshot Classification

To practice stage-by-stage thinking, **`LoggingRunbookDemo.java`** below is **a mock snapshot evaluator** that touches no infrastructure, makes no network calls, and deletes no logs. It checks counters that share a **reconciled boundary and state** in a simplified model:

- `offered`: events sent to the mock pipeline.
- `accepted`: events entering the mock queue.
- `consumed`: events pulled from the queue by workers.
- `ingested`: events received by the mock backend per model.
- `dropped`: events rejected from the queue by policy.
- `backlog`: events still waiting in the queue.
- `sensitiveCanaryDetected`: mock test flag indicating potential secrets in the sink.

Because the model is reconciled, it enforces `offered = accepted + dropped` and `backlog = accepted - consumed`. **In production, do not apply these identities directly to counters read across multiple processes/time windows** due to resets, retries, replays, duplicates, filters, late-arriving events, or events processed prior to the observation window.

Save as **`LoggingRunbookDemo.java`**:

```java
import java.util.List;
import java.util.Objects;

public final class LoggingRunbookDemo {
    enum Diagnosis {
        SECRET_EXPOSURE,
        EVENT_LOSS,
        QUEUE_BACKLOG,
        INGEST_LAG,
        HEALTHY
    }

    record Snapshot(
            String name,
            long offered,
            long accepted,
            long consumed,
            long ingested,
            long dropped,
            long backlog,
            boolean sensitiveCanaryDetected) {

        Snapshot {
            Objects.requireNonNull(name, "name");
            if (name.isBlank() || offered < 0 || accepted < 0
                    || consumed < 0 || ingested < 0
                    || dropped < 0 || backlog < 0
                    || dropped > offered
                    || accepted != offered - dropped
                    || consumed > accepted
                    || ingested > consumed
                    || backlog != accepted - consumed) {
                throw new IllegalArgumentException("Inconsistent snapshot");
            }
        }
    }

    private static Diagnosis diagnose(Snapshot s) {
        if (s.sensitiveCanaryDetected()) {
            return Diagnosis.SECRET_EXPOSURE;
        }
        if (s.dropped() > 0) {
            return Diagnosis.EVENT_LOSS;
        }
        if (s.backlog() > 0) {
            return Diagnosis.QUEUE_BACKLOG;
        }
        if (s.ingested() < s.consumed()) {
            return Diagnosis.INGEST_LAG;
        }
        return Diagnosis.HEALTHY;
    }

    public static void main(String[] args) {
        List<Snapshot> samples = List.of(
                new Snapshot("healthy",
                        1000, 1000, 1000, 1000, 0, 0, false),
                new Snapshot("queue_full",
                        1000, 800, 760, 700, 200, 40, false),
                new Snapshot("collector_slow",
                        600, 600, 600, 500, 0, 0, false),
                new Snapshot("worker_backlog",
                        600, 600, 550, 550, 0, 50, false),
                new Snapshot("secret_canary",
                        200, 200, 200, 200, 0, 0, true));

        for (Snapshot snapshot : samples) {
            System.out.println(snapshot.name() + " -> "
                    + diagnose(snapshot)
                    + " | backlog=" + snapshot.backlog()
                    + " dropped=" + snapshot.dropped());
        }

        boolean invalidRejected = false;
        try {
            new Snapshot("bad",
                    10, 9, 9, 9, 0, 0, false);
        } catch (IllegalArgumentException expected) {
            invalidRejected = true;
        }
        if (!invalidRejected) {
            throw new AssertionError("Invalid snapshot was accepted");
        }
        System.out.println("invalid_snapshot -> REJECTED");
        System.out.println("ALL CHECKS PASSED");
    }
}
```

Compile and run with **JDK 17+**:

```bash
javac --release 17 LoggingRunbookDemo.java
java LoggingRunbookDemo
```

**Exact stdout:**

```text
healthy -> HEALTHY | backlog=0 dropped=0
queue_full -> EVENT_LOSS | backlog=40 dropped=200
collector_slow -> INGEST_LAG | backlog=0 dropped=0
worker_backlog -> QUEUE_BACKLOG | backlog=50 dropped=0
secret_canary -> SECRET_EXPOSURE | backlog=0 dropped=0
invalid_snapshot -> REJECTED
ALL CHECKS PASSED
```

**Educational explanation:**

- `queue_full`: 200 events dropped, prioritized as **EVENT_LOSS** even though queue backlog and ingestion lag are also present.
- `collector_slow`: no drops or queue backlog in the snapshot, but the backend has fewer events than workers processed, hence **INGEST_LAG**.
- `worker_backlog`: 50 events remaining in the queue, hence **QUEUE_BACKLOG**.
- `secret_canary`: mock flag indicates canary detection, prioritized as **SECRET_EXPOSURE** even though counts balance.
- `invalid_snapshot` is rejected because offered does not equal accepted + dropped under the synchronous mock model.

**Do not use this demo as a production monitoring system.** Real counters have different time windows, partitions, clocks, stage semantics, and ack types; leak detection also requires canary/secret scanning for data protection, not a single boolean. This demo does not replace organization-defined incident priorities and performs no automated remediation.

## 17. Production Logging Configuration: Controlled Adjustments

### Logger Levels and Scope of Change

With Spring Boot, configure levels per package instead of enabling root globally:

```properties
logging.level.root=INFO
logging.level.com.example.checkout=INFO
logging.level.com.example.checkout.payment=WARN
```

Values are examples. A setting like `logging.level.com.example.checkout.payment=DEBUG` can aid investigation, but requires **reviewing log content, setting an expiration time, assigning a rollback owner**, and ensuring no tokens/bodies/PII are captured. Changing levels does not automatically alter `AccessLogValve`, collectors, or backends.

### Logback Async Example, Highlighting Trade-Offs

```xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ASYNC"
              class="ch.qos.logback.classic.AsyncAppender">
        <queueSize>8192</queueSize>
        <discardingThreshold>0</discardingThreshold>
        <neverBlock>false</neverBlock>
        <appender-ref ref="STDOUT"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="ASYNC"/>
    </root>
</configuration>
```

**This is an experimental configuration for understanding policies, not a recommendation to copy into production.**

- `queueSize=8192` is a queue limit (by event count), not bytes, and does not solve sustained sink overload.
- `discardingThreshold=0` disables Logback AsyncAppender's default early-discard behavior for low-level events; **it does not mean logs can never be lost**, especially during crashes/termination or sink errors.
- `neverBlock=false` means producers **can block when the queue is full**, directly affecting request p99 latency.
- With `neverBlock=true`, a full queue may drop events instead of blocking producers; assess data-loss tolerance.
- A text pattern configuration **does not automatically escape untrusted data or mask secrets**; build safe messages/fields at the source.
- If durable audit guarantees are needed, consider a dedicated channel/outbox rather than relying solely on an async debug appender.

Before changing queue policies, test slow sinks, burst traffic, shutdowns, and failure modes with clear counters.

### JUL and Log4j2

- **JUL** has levels/filters on both `Logger` and `Handler`; enabling a level on the logger does not guarantee the handler accepts it.
- **Log4j2** has multiple filter placements, synchronous/async loggers, appenders, and layouts; configure according to your deployed version.
- **SLF4J** is a facade; the underlying backend determines the actual encoder/queue/file behavior.
- Do not copy “Logback tricks” to Log4j2/JUL without checking APIs and versions.

## 18. Procedure for Temporarily Enabling DEBUG During an Incident

A log level change can aid diagnosis, but it can also increase volume or expose secrets.

1. **State the specific question to answer:** e.g., “why are HTTP client retries increasing” instead of “want to see everything.”
2. **Target a specific package/logger**, a few instances, or a canary scope if infrastructure supports it.
3. **Review code/fields that may appear at DEBUG**, especially headers/bodies/tokens and exceptions.
4. **Set an end time/checkpoint and rollback owner**; record the config version before changing.
5. **Deploy via an approved change path**, not by hitting an exposed admin endpoint.
6. **Monitor queue/drops, CPU, GC, disk, collector lag, and request p95/p99**.
7. **Collect sanitized evidence** for the hypothesis; never copy raw credentials.
8. **Revert and verify effective levels** across all instances, then close the change record.

If the application exposes Spring Boot Actuator `/actuator/loggers`, protect the endpoint with authentication/authorization and audit level changes. Never put public commands or URLs in a runbook to toggle DEBUG directly without controls.

## 19. Rollback and Recovery: Rules Before Changing Production

Every change must answer:

| Question | Required Content |
| --- | --- |
| **What** | Exactly which logger, collector pipeline, deployment, ILM, or sink is changing? |
| **Why** | Evidence linking the change to the symptom |
| **Owner** | Implementer, approver, and person authorized to roll back |
| **Blast radius** | One pod, one service, one tenant, or entire cluster? |
| **Data effect** | Could it drop/duplicate/delay logs, alter retention, or widen read access? |
| **Before** | Config version, metrics, sanitized event sample |
| **Success criteria** | What thresholds for lag/drops/errors/request latency? |
| **Rollback trigger** | Which metric or event forces an immediate revert? |
| **Rollback method** | Tested method using existing deployment tooling |
| **After** | Source/backend reconciliation, monitoring duration, and incident log |

**Prefer small, reversible changes.** Do not restart the entire collector or purge queues just to see if charts turn green; that can destroy unsent data.

When rolling back an encoder config, consider the event schema of data already in the queue; an older collector may fail to parse newer events, or vice versa. For index migrations, rollback may require supporting both schemas concurrently.

## 20. When Log Loss Is Possible: How to Communicate

Distinguish three statements:

- **Not found yet:** could be due to time filters, permissions, lag, or index queries; loss is not proven.
- **Delayed:** events exist at source/enqueue, collector/backend have backlog; final delivery is not yet certain.
- **Lost:** counters/acks/gaps or evidence of drop/rotation/crash mechanisms show events cannot be recovered through the current pipeline.

Avoid claiming 100% lost or 100% intact based solely on an empty dashboard.

**Example of a grounded incident update:**

```text
03:20 UTC — checkout-api is emitting source logs normally on inspected pods.
Collector retries are elevated; backend ingestion lags behind event time by
several minutes on the sampled set. No confirmed evidence of data loss yet;
drop counters are not fully instrumented, so risk remains. No change in
business error rate observed in the reference window. Observability owner
is isolating the sink. No configuration changes have been made yet.
```

The mock text above illustrates precise phrasing; do not send it as a report for a real system without corresponding observations.

## 21. Periodic Runbook Testing in Staging

**Runbooks must be rehearsed**, not just stored on a wiki. Safe drills should use test services, canary logs, and isolated backends/namespaces.

| Test Scenario | Purpose |
| --- | --- |
| Effective DEBUG disabled | Locate the right logger/level stage |
| Change appender path or simulate permission denied | Detect sink write errors |
| Block mock collector connection | Detect retries, backlog, data-lag |
| Bounded queue + slow sink | Observe block/drop behavior per policy |
| Enable DEBUG on test package | Measure CPU/p99/volume and rollback |
| Event with mistyped JSON | Diagnose parser/mapping conflicts |
| Request with test trace ID | Trace correlation across gateway/service/backend |
| MDC not restored in test code | Detect context bleed across requests |
| Canary in mock secret field | Verify secrets do not appear in logs |
| Replay an already-ingested batch | Check duplicate semantics |
| Test index lifecycle on mock data | Verify retention, archive, legal hold |
| Shutdown with async queue backlog | Evaluate drain/potential event loss |

Set explicit **PASS/FAIL** criteria for each drill: time to detect, alert recipient, time to isolate, lost/duplicate event count, rollback capability, and handoff quality.

For secret drills, use `SENSITIVE_CANARY_314` or a similar mock string, **never a real token**. For retention/deletion, use dry-runs and test indices/buckets; never delete production logs.

## 22. Post-Remediation Checks and Incident Closure Criteria

Do not close just because “the dashboard is green.” Verify:

1. A test event with a valid ID appears across **source → collector → backend query** within the expected window and time.
2. Ingest/queue lag is back within SLO or steadily decreasing under normal load.
3. Dropped/error counters are not growing abnormally; if data was lost, document the scope and recovery/reconciliation plan.
4. Request p95/p99, CPU, heap, GC, disk, and throughput have not degraded after the change.
5. Security/audit events are independently verified when required.
6. No new credentials/PII appear in test events; backends/exports are reviewed where relevant.
7. Effective configuration is accurate on **all affected instances**; temporary DEBUG has been rolled back.
8. Retention/archival was not unintentionally altered.
9. Incident owner and service owner confirm closure criteria; remaining risks are assigned to an owner for tracking.

### Closure Checklist Template

```text
[ ] Incident scope and timeline confirmed
[ ] Pipeline failure point identified with evidence
[ ] Before/after config and change rationale recorded
[ ] Source, collector, and backend readback/ingest reconciled
[ ] Dropped/duplicated/backlog quantified or marked unverified
[ ] Security/audit status evaluated by owner
[ ] Secrets/PII no longer leaking into logs
[ ] Latency, throughput, and pipeline SLOs met
[ ] Temporary DEBUG and workarounds reverted/documented
[ ] Follow-up tracking, postmortem, and recurrence prevention assigned
```

## 23. Post-Incident Review and Runbook Improvement

After an incident, compile a **UTC timeline**, config/deploy changes, source/backend evidence, true/false hypotheses, and approved decisions. A good review answers:

- Why didn't alerts/metrics detect it sooner?
- Which stage lacked telemetry (appender/queue/collector/index)?
- During the failure, did the system block producers, drop logs, or retry, and what was the business impact?
- How much data loss can be confirmed; were critical events affected?
- Were there sensitive data risks or overly broad access permissions?
- Where did rollback or coordination between app/platform/security hit friction?
- Which test suite prevents recurrence of logger level/schema/retention/MDC bugs?
- Which runbook lacks clear commands/fields/owners and needs updating?

Action items should have an owner, completion criteria, and regression tests—not just “improve monitoring.”

## 24. Quick Symptom Reference Card

| Symptom | Check First | Runbook Branch |
| --- | --- | --- |
| No logs in search | Query/time/permission → source stdout/file | A |
| Source present, backend delayed | Collector retries, queue, lag, TLS/ingest | B |
| Sharp disk/CPU spike | Logging level, event rate/size, sink | C |
| p99 spikes after logging change | Async full/block, formatter, thread I/O | D |
| Secret in logs | Contain spread, security response, revoke/rotate | E |
| Wrong trace/request ID | MDC scope, propagation, encoder field | F |
| Old logs disappeared | File/node vs backend retention, archive/hold | G |
| Audit event missing/duplicated | Business commit vs event/outbox/ingest | H |
| JSON mapping broken | Actual encoder output, parser, schema version | I |

## 25. Production Runbook Maintenance Checklist

- [ ] Service and logging owners are clearly named; escalation paths to platform and security exist.
- [ ] Pipeline map matches the current stack (Logback/Log4j2/JUL, stdout/file, collector, backend).
- [ ] Metrics/alerts exist for drops, queues, ingest lag, sink errors, and storage capacity.
- [ ] A controlled reconciliation method exists by event ID/correlation ID.
- [ ] Read-only commands exist to inspect pods/VMs/sources without dumping secrets.
- [ ] Log levels are not used as a substitute for security events/audit trails.
- [ ] Backpressure, discard, spool, shutdown, and sink-failure policies are known.
- [ ] Runbooks exist for secret/PII leaks and evidence preservation procedures.
- [ ] Rules exist for temporary DEBUG, expiration, rollback owner, and access control.
- [ ] Policies exist for retention, legal hold, archive, snapshots, and backups.
- [ ] Clear distinctions exist between missing, delayed, filtered by design, and irrecoverable loss.
- [ ] Tests cover concurrency/MDC, JSON schema, and end-to-end ingest.
- [ ] Incident closure criteria, approvers, postmortems, and regression actions are defined.

**Remember:** a useful logging runbook does not start with “change the level” or “restart the collector,” but by **identifying the right pipeline stage, protecting evidence, choosing reversible actions, re-measuring results, and honestly reporting unverified data**. Production observability is only trustworthy when logging can be diagnosed and recovered without introducing new risks to the service or security data.

### References

- [SLF4J Manual](https://www.slf4j.org/manual.html)
- [Logback — Appenders and AsyncAppender](https://logback.qos.ch/manual/appenders.html)
- [Logback — Configuration](https://logback.qos.ch/manual/configuration.html)
- [Log4j2 — Configuration](https://logging.apache.org/log4j/2.x/manual/configuration.html)
- [Java 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html)
- [Kubernetes — Logging architecture](https://kubernetes.io/docs/concepts/cluster-administration/logging/)
- [Kubernetes — kubectl logs](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_logs/)
- [OpenTelemetry — Collector](https://opentelemetry.io/docs/collector/)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [NIST SP 800-92 — Guide to Computer Security Log Management](https://csrc.nist.gov/pubs/sp/800/92/final)
