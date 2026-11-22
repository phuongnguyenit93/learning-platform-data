# Incident Investigation in Java Logging for Production Operations

## 1. What is Incident Investigation?

In a production environment, **incident investigation (troubleshooting)** is the process of collecting, correlating, and verifying evidence to answer **where the system is affected, since when, why, the scope of impact, and how to recover safely**. Java logging provides detailed traces of application behavior; combining logs with metrics, distributed tracing, infrastructure state, and business data helps form a reliable diagnosis.

An example incident:

~~~text
10:01  Users report payments returning 503 errors
10:02  Metrics record an increased error rate in payment-api
10:03  Logs show timeouts when calling inventory-service
10:04  Traces indicate increasing connection pool wait time
10:05  Pool metrics and DB dashboard confirm connection bottleneck
10:06  Trigger load shedding plan according to the runbook
~~~

This timeline is **for illustration only**, not real incident data. The key point is that the timeout log line is only a **signal**. If the true cause is connection pool exhaustion or an overloaded dependency, merely increasing the HTTP timeout may mask the symptom without resolving the underlying cause.

It is necessary to distinguish:

- **Symptom:** users experience 5xx errors or slow requests.
- **Signal:** increased error rate, increased p99 latency, TIMEOUT appearing in logs.
- **Evidence:** log events, trace spans, metrics, configurations, deployments, and verified business state commits.
- **Hypothesis:** pool exhausted due to a connection leak.
- **Root cause:** the mechanism causing the incident after cross-checking evidence and ruling out alternative hypotheses.
- **Mitigation:** load shedding, rollback, or rerouting to restore service.
- **Permanent fix:** fixing code/configuration and adding controls to prevent recurrence.

**Do not equate "no more ERROR logs" with "the incident is over."** Logging may be affected by level filtering, sampling, collector outages, or disruptions in the collection pipeline itself.

## 2. First Questions When Receiving an Alert

Before diving into stack traces, establish the context:

| Question | Data to Confirm |
| --- | --- |
| Who is affected? | Users, tenant, region, API, message consumer, or job |
| Since when? | Start time and time range in UTC/offset |
| Impact? | Availability, latency, throughput, backlog, incorrect or lost data |
| Severity? | Impacted SLOs, security/data risks, critical functionality |
| Recent changes? | Deploy, config, secret/certificate rotation, schema, feature flag |
| External dependencies? | Database, cache, broker, HTTP gateway, DNS, or cloud service |
| Mitigation options? | Rollback, traffic shifting, rate limit, circuit breaker, pause job |
| What evidence must be preserved? | Log queries, traces, metric snapshots, version, timeline, and correlation IDs |

In a high-impact incident, **restoring service per the runbook** may take priority over full root-cause analysis. However, every recovery change must be recorded to avoid losing facts and to know which change actually worked.

**Set a clear time window.** Data before the start time, during the failure, and after intervention is crucial; searching only for the keyword "ERROR" in the last minute may miss the triggering event or an earlier configuration change.

## 3. Controlled Investigation Process

An investigation cycle can follow these steps:

1. **Confirm impact:** use SLI/SLO, synthetic probes, or business state, not just log counts.
2. **Isolate scope:** region, service, endpoint, version, tenant, instance, consumer group.
3. **Collect minimal evidence:** timestamp, requestId/traceId, errorCode, metrics, deploy events.
4. **Reconstruct timeline:** stitch events by source system and appropriate time.
5. **Formulate hypothesis:** state specifically what could explain the symptoms.
6. **Test hypothesis:** look for both supporting signals and counter-evidence.
7. **Mitigate impact:** rollback/load shed/reroute according to permissions and runbook.
8. **Verify recovery:** whether latency, error rate, business outcomes, and backlog have actually improved.
9. **Record evidence and decisions:** relevant configurations/versions/correlations and reasons for intervention.
10. **Post-incident follow-up:** permanent fix, regression tests, dashboards, and alerting.

**Every significant claim should include its evidence source and the limitations of that source.** For example, "seeing TIMEOUT on the client" does not prove the dependency did not receive the request; the server may have finished processing, while the response was delayed or lost on the network.

In reports, distinguish between **observed**, **inferred**, **unknown**, and **confirmed**. This prevents other teams from turning an initial hypothesis into a conclusion while the incident is still unfolding.

## 4. Signal Sources and Relative Reliability

| Source | Useful For | Limitations |
| --- | --- | --- |
| **Application logs** | Error codes, lifecycle events, exceptions, request context | Events may be missing due to level/sampling/drops |
| **Structured audit logs** | Security- or business-significant actions | Do not replace full debug traces |
| **Metrics** | Error rate, p95/p99 latency, throughput, saturation | Often lack per-request detail |
| **Distributed traces** | Cross-service timeline, per-span duration | Subject to sampling, missing propagation |
| **JVM diagnostics** | Heap, GC pauses, thread states, safepoints | Must be captured at the right time, requires access permissions |
| **Database/broker telemetry** | Slow queries, pool pressure, queue lag, retries | May not directly show Java code causes |
| **Infrastructure events** | OOMKill, restarts, deployments, node pressure | Do not by themselves prove an application bug |
| **Business database/outbox** | Verifying side effects and final state | May lack technical timeline details |
| **Third-party status** | External outages and upstream changes | Causal link still requires verification |

**Logs describe what was recorded; metrics show scale; traces show timing relationships.** A trace showing a span timeout while the business database still committed successfully is entirely possible when the response or ACK arrives late.

Do not run commands to change configuration, clear logs, or restart services just to "try something quickly" before assessing impact. In production, preserve evidence and follow operational permissions.

## 5. Designing Logs for Effective Investigation

An easily investigable Java event typically includes:

| Field | Purpose |
| --- | --- |
| timestamp | Time the event was emitted with an explicit timezone |
| level | Event severity; does not replace errorCode |
| service / environment / version | Isolate the deployed build |
| instanceId / host / pod / region | Identify where the event was emitted |
| eventCode | Stable event name, suitable for aggregation |
| requestId / correlationId | Track a single request/workflow |
| traceId / spanId | Correlate logs with distributed traces |
| Approved userRef / tenantRef | Scope impact; avoid raw PII |
| operation / routeTemplate | Functionality where the error occurred |
| outcome / reasonCode | Standardized status and reason codes |
| errorCode / exceptionType | Error grouping, alerts, and dashboards |
| durationMs / attemptNo | Duration and attempt number |
| dependencyName / statusCode | Dependency and response code if applicable |
| schemaVersion | Enables controlled changes to serialization contracts |

Example of a structured event:

~~~json
{
  "timestamp": "2026-11-10T03:02:41Z",
  "level": "WARN",
  "service": "payment-api",
  "environment": "production",
  "version": "2.8.1",
  "instanceId": "payment-api-3",
  "eventCode": "DEPENDENCY_TIMEOUT",
  "requestId": "req-42",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "operation": "authorize_payment",
  "dependencyName": "inventory-service",
  "attemptNo": 1,
  "durationMs": 1200,
  "errorCode": "INVENTORY_TIMEOUT"
}
~~~

This is a **schema example**, not the default output of Logback/JUL. Field names must be standardized according to your organization and actual instrumentation. Version/instance information helps compare errors that only appear after a deployment or on a specific subset of nodes.

Do not log raw request bodies, tokens, or Authorization headers simply because you are investigating production. **Evidence must be sufficient without exposing sensitive data.**

## 6. Correlation ID, Request ID, and Trace ID

When a request traverses an API gateway, services, databases, and message brokers, it can generate dozens of log lines across multiple machines. IDs must have distinct meanings:

- **requestId:** identifies a request at a single boundary; typically used for quick lookup.
- **correlationId/workflowId:** links a workflow spanning multiple requests/messages.
- **traceId:** ties together spans belonging to a distributed trace via propagation.
- **spanId:** identifies a single operation/span within a trace; does not replace traceId.
- **messageId/eventId:** helps locate a logical event across retries/redeliveries.
- **attemptNo:** distinguishes multiple attempts of the same operation.
- **jobId:** groups events belonging to a background job or batch.

A single trace can contain multiple HTTP calls or messages; a single logical message can be redelivered across multiple attempts. **Do not use traceId as a business deduplication key**. Do not use email/phone as a default requestId.

IDs extracted from HTTP headers or message envelopes are **not inherently trustworthy**. Validate grammar, length, and encoding; if a client sends a malformed ID containing CR/LF, generate a new ID or apply a safe policy to prevent log forging.

In systems using SLF4J/Logback, MDC often holds requestId/traceId. However, **MDC is only context on a thread/adapter** and does not automatically propagate across the network. For executors, CompletableFuture, async servlets, Reactor, or message consumers, you must properly capture/activate/restore the scope.

## 7. Reconstructing Timelines Amid Clock Skew and Ingestion Delays

A log query can sort by timestamp, yet the displayed order **does not always equal the order of occurrence**. Causes include:

- Clock skew between hosts/VMs/containers and across regions.
- Buffered/async appenders and network queues delaying log delivery to the backend.
- Collectors assigning an ingestion timestamp different from the event timestamp.
- Retries/redeliveries occurring out of order relative to the original request.
- Overlapping spans; asynchronous operations have no global ordering relationship.
- Application timestamp recorded before a DB commit even though the commit completes later.

An event should keep **eventTime** and **observed/ingestedTime** separate when needed. Search for traces over a slightly wider time window than the symptom, and use correlation and causal/sequence ordering when available; do not rely solely on timestamp sorting.

Example:

~~~text
eventTime=03:02:00.000 service=api       REQUEST_STARTED req-42
eventTime=03:02:00.020 service=api       CALL_INVENTORY req-42
eventTime=03:02:01.220 service=api       INVENTORY_TIMEOUT req-42
eventTime=03:02:01.250 service=api       FALLBACK_USED req-42
eventTime=03:02:01.310 service=api       REQUEST_COMPLETED req-42
ingestedTime=03:02:05.xxx collector=central
~~~

This is a simulated timeline. **A timeout appearing before REQUEST_COMPLETED may be a transient error that was recovered from**, not necessarily a failed final request.

When strict ordering is needed for a workflow, use sequence/eventId/causationId or committed transaction state. Timestamp alone is not proof of exactly-once execution or business completion.

## 8. From Symptoms to Initial Queries

Each type of symptom suggests a search direction:

| Symptom | Suggested Log Fields / Metrics | What You Must Not Conclude Yet |
| --- | --- | --- |
| Increased HTTP 5xx rate | routeTemplate, statusCode, exceptionType, version | All 5xx errors are caused by a JVM bug |
| Increased p99 latency | durationMs, dependencyName, pool wait, GC pause | CPU is definitely insufficient |
| Java process restarts | startup events, shutdown reason, pod events | Every restart is an OOM |
| OOM/heap pressure | OutOfMemoryError, heap usage, GC, memory limit | Every memory increase is a leak |
| Connection timeout | dependency, timeout class, DNS, retries | The dependency never processed the request |
| Database errors | SQLState, pool wait, slow query fingerprint | Every SQLException is a DB outage |
| Queue backlog | consumer group, lag, DLQ, attempts | The broker has lost messages |
| Inconsistent business data | eventId, transaction outcome, outbox/inbox | ACK equals commit |
| Missing logs | logger level, agent queue, collector drop | The application did not emit events |
| Errors only in one version | deployment markers, version, flags | The new code version definitely caused the bug |

Before running a broad search across all of production, specify **service + environment + time window + a correlation key**. This is faster and reduces the risk of reading excessive sensitive information.

**Do not search only for the word ERROR and treat it as the entire incident.** WARN may contain early indicators, while INFO contains recovery confirmation or deployment events.

## 9. Formulating Hypotheses and Seeking Counter-Evidence

A valuable hypothesis must produce **testable indicators**, not just a vague description like "the system is overloaded."

Example hypothesis: **JDBC connection pool exhaustion is causing the API to return timeouts**.

Testable predictions:

- During the same window, active pool connections approach max and pending requests/wait time increase.
- Logs contain an errorCode or exceptionType corresponding to failing to acquire a connection.
- The DB may or may not be healthy; if the DB is slow, connection hold time increases.
- Only endpoints using the DB are heavily impacted.
- After reducing request volume/restoring the pool or fixing long-held transactions, latency/errors improve.

Counter-evidence:

- The pool still has many idle connections when timeouts occur.
- Timeouts originate from a different DNS/HTTP dependency with no JDBC step involved.
- Symptoms started before the supposedly related pool configuration change.

Do not cherry-pick only the logs that support your first conclusion. Record **hypothesis, supporting evidence, refuting evidence, and confidence level** in incident notes. When possible, compare the failing cohort against the succeeding cohort to see what actually differs.

## 10. Exception Analysis in Java

Stack traces have multiple layers:

~~~text
java.lang.IllegalStateException: order request failed
    at example.OrderService.process(OrderService.java:52)
Caused by: java.net.SocketTimeoutException: Read timed out
    at example.InventoryClient.fetch(InventoryClient.java:91)
~~~

Elements to distinguish:

- **Exception type:** represents the outermost error type, often useful for grouping errors.
- **Cause chain:** exceptions wrapped by higher layers; the root cause may lie deep down.
- **Suppressed exceptions:** appear with try-with-resources and certain cleanup paths.
- **First application frame:** helps pinpoint where the exception was thrown or wrapped, not necessarily the underlying bug.
- **Thread name, requestId, dependency:** helps tie the error to actual execution.
- **Retry context:** the same exception may appear multiple times for a single request.
- **Terminal outcome:** after the error, a fallback may have succeeded.

**Reading the root cause does not mean just grabbing the last line.** The final message may only be the result of a network timeout; you need metrics/traces to know why the dependency was slow, DNS failed, or the pool saturated.

Do not stuff raw requests/responses into a Throwable message for easier debugging; exception text can contain tokens, signed URLs, SQL parameters, and personal data. Use errorCode, exception class, dependency name, and correlation ID; store sensitive data through controlled procedures only when truly necessary.

### SLF4J parameterized logging does not automatically strip secrets

Integration example:

~~~java
logger.error("event={} requestId={} errorCode={}",
        "inventory_failed", validatedRequestId, "DEPENDENCY_TIMEOUT",
        exception);
~~~

This line requires SLF4J and a backend. When the exception is passed properly as the trailing Throwable, the provider can output the stack trace; the Throwable itself can also contain sensitive data. Placeholders are **not redaction**.

Do not call logger.error on every retry and treat the total ERROR count as the total number of failed requests. You must separate **attempt failure** from **logical operation failure**.

## 11. JVM: GC Pauses, Heap, and OutOfMemoryError

Runtime-related symptoms:

- Sudden latency spikes coinciding with long GC pauses.
- Heap approaching its limit, frequent GC runs, and degraded throughput.
- Different types of OutOfMemoryError: Java heap space, Metaspace, direct buffer memory, or thread creation failure each have distinct mechanisms and facts.
- Containers **OOMKilled by OS/cgroup limits** may leave no OutOfMemoryError in Java logs.
- Liveness/readiness probe timeouts can trigger orchestration restarts, causing JVM traces to be lost when the old container disappears.

Sources to check:

| Source | Role |
| --- | --- |
| GC logs or JFR | Pauses, allocation pressure, collector behavior |
| Heap usage metrics | Old gen, heap committed/used over time |
| Container memory RSS/limits | Distinguish heap from off-heap memory and OOMKill |
| JVM flags/heap limits | Determine actual runtime configuration |
| Thread counts, native memory | When suspecting thread/native allocation leaks |
| Deploy/config timeline | Identify if errors only occur on a new version/memory limit |

In authorized environments, **jcmd** can query a Java process for thread or heap information. Operational idea example:

~~~text
jcmd <java-pid> Thread.print
jcmd <java-pid> GC.heap_info
~~~

The commands above are **operational patterns**; substitute the actual PID according to permissions and JVM version guidelines. Do not run heap dumps indiscriminately in production: dumps can contain secrets/PII, consume large amounts of disk, and impact service availability; perform them only according to incident procedures.

**GC coinciding with an error does not automatically prove GC is the root cause.** You must cross-check pause duration, request latency, and affected dependencies.

## 12. JVM: Deadlocks, Thread Pools, and Blocking

When requests are slow while CPU is not high, suspect threads waiting on locks, I/O, or pools.

Signs:

- Many threads in WAITING/BLOCKED state on the same resource.
- Executor queue length growing, active threads hitting max.
- CompletableFuture or reactive code calling blocking APIs on an inappropriate scheduler.
- Thread count rising continuously because an executor is not shut down or is leaking.
- Deadlock detection or thread dumps showing a lock cycle.
- HTTP client/DB connection pool waiting long; the application does not necessarily use high CPU.

Inspect using JVM thread dumps/JFR and executor metrics, while correlating stage logs: REQUEST_RECEIVED → HANDLER_STARTED → CALL_DEPENDENCY → TIMEOUT. **Do not infer a deadlock merely from WAITING threads**; many normal threads wait on queues, timers, or sockets.

When capturing thread dumps, ensure proper authorization and protect the output file because stacks/ThreadLocals can reflect sensitive system information. Do not post dumps containing sensitive content to unpermissioned chat channels/tickets.

Reproduction tests in staging can use CountDownLatch/CyclicBarrier to create contention conditions; do not use Thread.sleep to claim you have proven a race condition.

## 13. HTTP Clients: Timeouts and Retry Storms

When a Java service calls an HTTP dependency, distinguish between timeout types:

| Type | Phase | Investigation Direction |
| --- | --- | --- |
| Connect timeout | Failed to connect to endpoint | DNS, route, network, listener |
| Read/response timeout | Waited too long for response data | Upstream latency, thread/pool saturation |
| Connection acquisition timeout | Waiting to borrow a connection from client pool | Pool limits, leaked/held connections |
| Deadline/cancellation | Total request or RPC time budget | Deadline propagation and retries |
| TLS handshake failure | Encrypted handshake failed | Cert chain, truststore, protocol version |

**Do not equate a client timeout with the upstream not having processed the request.** The upstream may have written the data while the response was slow or the ACK was lost. Retrying a non-idempotent operation can multiply side effects.

Logs should include dependencyName, operation, timeoutCategory, attemptNo, durationMs, statusCode (if a response was received), retryable, and terminal outcome. Do not log raw Authorization headers, URLs with tokens, or sensitive bodies.

When a backend slows down, too many clients retrying simultaneously can cause a **retry storm**, worsening the incident. Check exponential backoff + jitter, retry budgets, circuit breakers, concurrency limits, and timeout chains.

## 14. JDBC/Database: Connections, Transactions, and Slow Queries

Database errors often manifest as SQLException or timeouts in Java logs, but must be cross-checked with pool and database metrics.

Check:

1. **Pool active/idle/pending:** is the pool exhausted, and when did time-to-acquire spike?
2. **Slow queries:** query fingerprint, elapsed time, locks, missing indexes, execution plans.
3. **Transaction boundaries:** is any transaction holding a connection while waiting on HTTP?
4. **Lock contention/deadlock:** trace from the database and SQLState.
5. **Connection lifetime/recovery:** network idle timeout, proxy reset, database failover.
6. **Schema migrations:** did the incident start after a deploy or DDL?
7. **Error classification:** transient connection errors differ from constraint violations or validation failures.

Example of a standardized log:

~~~json
{
  "eventCode": "DB_CONNECTION_ACQUIRE_FAILED",
  "service": "order-api",
  "dependencyName": "orders-db",
  "errorCode": "POOL_TIMEOUT",
  "requestId": "req-42",
  "durationMs": 3000
}
~~~

This is an **illustrative event**. Do not log SQL bind parameters or credentials for investigation. When SQL diagnostics are needed, use query identifiers/fingerprints and controlled query systems. JDBC/ORM DEBUG loggers can expose raw values and add load, so do not enable them arbitrarily in production.

**Pool exhaustion can be a consequence** of a slow database or the application holding connections too long, not necessarily a pool configured too small. Check the timeline before increasing max pool size.

## 15. Message Brokers and Background Jobs

With Kafka, RabbitMQ, or other queue systems, the HTTP request completes while asynchronous work may still be processing.

Stages to observe:

~~~text
EVENT_CREATED
   |
   v
PUBLISH_REQUESTED
   |
   v
PUBLISH_CONFIRMED
   |
   v
DELIVERY_RECEIVED
   |
   v
PROCESSING_STARTED
   |
   +-- SUCCESS --> ACKNOWLEDGED / OFFSET_COMMITTED
   |
   +-- FAILED --> RETRY_SCHEDULED --> REDELIVERED
                                      |
                                      v
                                  DEAD_LETTERED
~~~

**PUBLISH_REQUESTED does not mean the broker received it.** **Broker confirm does not mean the consumer processed it.** **ACK/offset commit does not by itself prove the DB side effect committed** without a transaction/idempotency contract.

When investigating an incident:

- Search by messageId/eventId, consumer group, topic/partition/offset, or queue.
- Distinguish a single logical message from multiple attempts.
- Check backlog/lag, DLQ, retry delay, consumer rebalances, and broker health.
- Cross-check outbox/inbox and the business database to confirm the event was processed correctly.
- If redelivered, verify idempotency and duplicate side effects.
- When replaying from DLQ, preserve causation/correlation and audit who executed it.

A missing log event may be due to log drops, not a lost message. Verification sources must include broker metadata and business state.

## 16. Infrastructure: Containers, Kubernetes, and Linux Hosts

When Java runs on Kubernetes/VMs, incidents can stem from infrastructure:

| Symptom | Source to Check |
| --- | --- |
| Repeated pod restarts | Pod/container status, restart reason, prior logs |
| OOMKilled | cgroup memory, container limits, node pressure |
| CPU throttling | CPU quotas/throttling metrics, request latency |
| Readiness/liveness failures | Probe events, JVM pauses, startup time |
| DNS/TLS failures | Resolver, cert expiry/rotation, network policy |
| Node disk pressure | Logging spool, ephemeral storage, volume health |
| Skewed deployment rollout | Pod version, image digest, config checksum |
| Failures in only one zone/region | Instance/zone metadata, upstream route |

Do not assume a pod restart means the application crashed on its own. The orchestrator may kill it due to cgroup memory, probe timeouts, or node eviction. Check both deployment events and previous container logs before the restart when the system retains them.

Do not change production resource limits/connection strings based on a single WARN log. Execute changes in a controlled manner, recording baselines and post-change metrics.

## 17. If Logs Are Missing: Investigating the Logging Pipeline

A severe incident can be accompanied by **loss of the observability logs themselves**. The pipeline typically consists of:

~~~text
Java logger / Logback / JUL
       |
       v
stdout / rolling file / journald
       |
       v
Host agent / DaemonSet / sidecar
       |
       v
Queue, retry, parsing, buffering
       |
       v
Collector / gateway
       |
       v
Index / archive / dashboard
~~~

Questions to answer:

- Is a log level/filter blocking the event? Are the logger name and effective level correct?
- Is the AsyncAppender queue full and dropping events?
- Is the console/file path correct, and is the rolling policy deleting files before the agent reads them?
- Is the container/runtime/journald rate-limiting or rotating logs?
- Does the agent have the right offset/cursor state and permissions?
- Is the multiline parser merging/splitting stack traces incorrectly?
- Is the collector retrying/throttling, returning 429/5xx errors, or disk-full?
- Does the backend index/query have the right time window and filters?
- Is trace sampling/retention hiding part of the evidence?

**Not seeing a log does not prove the action did not happen.** Before concluding an event is missing, check collector health, backlog, drop metrics, sampling, and local sources. However, in some systems, a mandatory audit event not being created is itself an independent incident to investigate against the business source/outbox.

## 18. Log Queries Using a Pivot Strategy

Do not start by dumping all production logs. An effective query sequence typically follows:

1. Select **service + environment + time range** based on the alert.
2. Identify abnormally spiking **eventCode/errorCode**; break down by version/region.
3. From a specific event, grab **requestId or traceId**.
4. Search for all events with that ID, not just ERROR.
5. Open the trace to view upstream/downstream spans and durations.
6. Pivot by **dependencyName** if multiple requests are timing out together.
7. Compare the failing cohort with the succeeding cohort in the same version.
8. Check config/deploy/feature flags right at the start time.
9. Look for counter-evidence and cross-check metrics/broker/DB.
10. Record queries, time windows, and evidence so they are reproducible.

Example pseudo-query (not specific syntax for Elasticsearch, Loki, or Splunk):

~~~text
WHERE environment = "production"
  AND service = "payment-api"
  AND timestamp BETWEEN "03:00Z" AND "03:10Z"
GROUP BY eventCode, version, region
COUNT events
~~~

A second query can filter **requestId = req-42** and sort by event timestamp. However, total log count does not equal the number of users or business failures if one request emits multiple logs or retries.

When using Elasticsearch/Kibana, Grafana Loki, OpenSearch, or Splunk, syntax and index fields may differ. Do not copy the pseudo-query above and assume it works as-is without verifying the backend schema.

## 19. Standalone Java 17 Example: Tracing Two Requests with JUL

The example below uses **java.util.logging (JUL)** built into Java SE, requiring no SLF4J/Logback/Maven. An in-memory Handler retains structured events, which are then queried by requestId. The first case encounters a timeout but succeeds via fallback; the second case only observes the start event and a dependency error.

Create the file **IncidentInvestigationDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class IncidentInvestigationDemo {
    record Event(String requestId, String service,
                 String stage, String errorCode) {}

    record Captured(Level level, Event event) {}

    static final class CaptureHandler extends Handler {
        final List<Captured> records = new ArrayList<>();

        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record)) {
                return;
            }
            Object[] params = record.getParameters();
            if (params != null && params.length == 1
                    && params[0] instanceof Event event) {
                records.add(new Captured(record.getLevel(), event));
            }
        }

        @Override
        public void flush() {}

        @Override
        public void close() {}
    }

    private static void emit(Logger logger, Level level, Event event) {
        logger.log(level, "structured-event", new Object[]{event});
    }

    private static void inspect(List<Captured> records, String requestId) {
        List<Captured> matches = records.stream()
                .filter(row -> row.event().requestId().equals(requestId))
                .toList();

        System.out.println("TRACE " + requestId);
        for (Captured row : matches) {
            Event event = row.event();
            System.out.println(row.level().getName() + " "
                    + event.service() + " " + event.stage()
                    + " code=" + event.errorCode());
        }

        boolean terminalObserved = matches.stream()
                .anyMatch(row -> row.event().stage().equals("REQUEST_COMPLETED")
                        || row.event().stage().equals("REQUEST_FAILED"));

        System.out.println("SUMMARY " + requestId
                + " events=" + matches.size()
                + " terminalObserved=" + terminalObserved);
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("incident.investigation.demo");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);

        CaptureHandler handler = new CaptureHandler();
        handler.setLevel(Level.ALL);
        logger.addHandler(handler);
        try {
            emit(logger, Level.INFO,
                    new Event("req-42", "gateway", "REQUEST_STARTED", "NONE"));
            emit(logger, Level.WARNING,
                    new Event("req-42", "catalog", "DOWNSTREAM_TIMEOUT",
                            "CATALOG_TIMEOUT"));
            emit(logger, Level.INFO,
                    new Event("req-42", "gateway", "FALLBACK_USED", "NONE"));
            emit(logger, Level.INFO,
                    new Event("req-42", "gateway", "REQUEST_COMPLETED", "NONE"));

            emit(logger, Level.INFO,
                    new Event("req-43", "gateway", "REQUEST_STARTED", "NONE"));
            emit(logger, Level.WARNING,
                    new Event("req-43", "inventory", "DB_POOL_EXHAUSTED",
                            "POOL_TIMEOUT"));

            inspect(handler.records, "req-42");
            inspect(handler.records, "req-43");
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }
    }
}
~~~

Compile and run:

~~~bash
javac IncidentInvestigationDemo.java
java IncidentInvestigationDemo
~~~

**Exact stdout of the program:**

~~~text
TRACE req-42
INFO gateway REQUEST_STARTED code=NONE
WARNING catalog DOWNSTREAM_TIMEOUT code=CATALOG_TIMEOUT
INFO gateway FALLBACK_USED code=NONE
INFO gateway REQUEST_COMPLETED code=NONE
SUMMARY req-42 events=4 terminalObserved=true
TRACE req-43
INFO gateway REQUEST_STARTED code=NONE
WARNING inventory DB_POOL_EXHAUSTED code=POOL_TIMEOUT
SUMMARY req-43 events=2 terminalObserved=false
~~~

### Why Is This Demo Useful?

- It uses a real **JUL Logger + Handler + LogRecord**, capturing data in memory instead of sending it to a backend.
- **Event** data is passed via LogRecord parameters rather than parsing a concatenated message string. The Handler checks the type and extracts the Level to store.
- **req-42** has a timeout warning, followed by a fallback and the terminal event REQUEST_COMPLETED. Grepping only for WARNING could falsely report that the request ultimately failed.
- **req-43** only has two events, with the last observed event being DB_POOL_EXHAUSTED; **terminalObserved=false** only means **no terminal event was seen in the log sample**, not that the request was lost or that the DB pool is definitely the root cause.
- The output uses the **WARNING** level name per JUL, which differs from the **WARN** label commonly seen in SLF4J/Logback.
- Timestamps are omitted so stdout does not depend on the clock. In production, events need timestamps, service/version, traceId, duration, dependency, and proper correlation.
- The model uses a single thread; **ArrayList is not a thread-safe collector**. Do not use this CaptureHandler as-is for a production logging backend or unsynchronized concurrency tests.
- The demo has no collector, sampling, GC, HTTP/DB calls, real retries, durability, or access control. It illustrates **how to reason based on observed stages**, not real evidence of an incident.

**Extension exercise:** add REQUEST_FAILED for req-43 and verify that terminalObserved becomes true; add another WARN event before REQUEST_COMPLETED for req-42 and verify that the final outcome is still inferred from the terminal stage rather than just the log level.

## 20. Workflow for Investigating an HTTP 503 in Production

Suppose the error rate for the POST /orders route increases after a rollout.

**Step 1 — Confirm the issue:** measure the HTTP 503 rate, p95/p99 latency, and committed order count. Identify version, region, and start time.

**Step 2 — Find error patterns:** group by eventCode, errorCode, dependencyName; if all errors go through inventory, inspect inventory and connection pools.

**Step 3 — Pick a sample request:** use the requestId/traceId of a failing request and inspect the full timeline from REQUEST_STARTED to terminal. Look for fan-out calls, retries/fallbacks, timeouts, and transaction results.

**Step 4 — Check changes:** new deploys, timeout configs, caches, DNS/TLS certs, database pools, feature flags. Compare a failing instance/version with a healthy one.

**Step 5 — Cross-check telemetry:** CPU, GC, threads, pool wait, dependency metrics, DB locks, broker lag, Kubernetes events.

**Step 6 — Mitigate:** if evidence points to the rollout increasing request concurrency, rollback/shed load or cap concurrency per the runbook; do not change both timeout and pool size at the same time if doing so destroys your ability to distinguish the cause.

**Step 7 — Verify recovery:** error rate and latency return to baseline, queue backlog drains, orders are neither missing nor duplicated, and customer-facing probes succeed.

**Step 8 — Document evidence and follow-ups:** root cause once sufficiently substantiated, permanent fixes, detection gaps, and regression prevention tests.

**Investigation is not "fixing logs to eliminate ERRORs"**. Any logging configuration change must preserve essential observability and audit requirements.

## 21. Production Logging: Increasing Detail Under Control

When existing logs are insufficient, operations teams sometimes need to enable DEBUG temporarily. Controls required:

| Risk | Mitigation |
| --- | --- |
| DEBUG exposes headers/body/tokens/PII | Review library loggers, redact/omit at the source |
| Volume spike fills disk/collector | Limit scope: service/instance/logger/time window |
| Async queue drops events | Monitor dropped logs, queue depth, and backpressure |
| CPU/GC spikes from stack trace formatting | Profile, avoid dumping large objects |
| Dynamic level fails to revert | Assign owner, expiry/rollback, and audit changes |
| Log forging from user data | Structured encoding, validate IDs, escape control chars |
| Unauthorized log access | RBAC, query/export auditing, data minimization |

Do not log raw Authorization, Cookie, access tokens, credit cards, or SQL bind parameters to investigate incidents. You can record **eventCode, requestId, payload schema, size, status, exceptionType**, and use a separately protected evidence store if sensitive details are genuinely required by procedure.

**Log level is a choice of observability detail, not field security classification.** An ERROR line containing a token is still a leak, whereas a DEBUG line logging only a fixed errorCode can be safer.

## 22. Querying Multiple Sources Without Losing Context

When spotting an event in a dashboard, record:

- Query and time range used, timezone, environment.
- Service name, deployment version, host/pod, or region.
- requestId/traceId, spanId, and eventCode.
- Authorized internal dashboard panel/metric or trace URL.
- Events before and after, not just a screenshot of a single exception.
- Ingestion time and source timestamp if clock skew is suspected.
- Changes made during the incident and when they occurred.

**Do not share public URLs containing tokens or personal data**. When attaching evidence to an incident ticket, prefer reference IDs, permissioned internal links, and policy-redacted screenshots/snippets.

A log query returning 0 records may be due to the wrong index, sampling, retention, different schema tokenization, or a timeline off by just a few minutes. Always check collector health if observability data appears to vanish en masse.

## 23. Incident Response, Mitigation, and Outcome Verification

In many incidents, mitigation and root-cause analysis run in parallel, but they are not the same task.

**Mitigation** may include:

- Rolling back a release with evidence of causing degradation.
- Limiting concurrency, traffic, or retry budgets.
- Temporarily pausing a noncritical background job per the runbook.
- Failing over to a healthy dependency when the consistency model allows.
- Rotating certificates/secrets when there is evidence of authentication issues and proper authorization procedures.
- Enabling a pre-designed and pre-tested circuit breaker/fallback.

**After mitigation**, verify using independent signals:

1. Whether error rate and latency improvements are sustained or only temporary.
2. Throughput and backlog are genuinely recovering.
3. Business transactions are neither lost nor duplicated.
4. Connection/thread counts and GC pauses return to reasonable levels.
5. No new errors appear downstream or in other cohorts.
6. Logging/collectors remain operational and are not dropping due to increased load.

A rollback may reduce errors without resolving **messages stuck in the DLQ** or duplicate side effects. Define "incident resolved" by user experience and business state, not just a single service's dashboard.

## 24. Postmortem: From Incident to a Better System

A useful postmortem must be an **evidence-based narrative**, not merely a list of individual mistakes.

Recommended sections:

| Section | Content |
| --- | --- |
| Summary | Symptoms and impact on users/SLOs |
| Timeline | Events, alerts, deployments, mitigation, recovery |
| Detection | Which alerts fired; any delays or blind spots |
| Technical cause | Failure mechanism, trigger conditions, tested counter-evidence |
| Contributing factors | Backpressure, missing timeout budgets, config, capacity, monitoring |
| Impact | Request failures, latency, downtime, incorrect/duplicate data |
| Mitigation | What was done, who approved it, and the outcome |
| Recovery verification | Metrics, traces, and business checks |
| Corrective actions | Owners, priorities, and acceptance tests |
| Monitoring gaps | What new eventCodes/metrics/traces/alerts are needed |
| Privacy/security | Any leaked secrets in logs or evidence access issues |

Avoid claiming certainty when data is insufficient. If an incident had multiple contributing causes, describe the causal chain instead of forcing a single root cause.

**Postmortems must not increase privacy risk:** quote only redacted logs or store references to a permissioned evidence vault; never copy raw credentials, raw payloads, or customer data.

## 25. Common Mistakes During Incident Investigation

| Wrong Practice | Why It Is Dangerous | Better Approach |
| --- | --- | --- |
| Searching ERROR and concluding the request failed | A fallback/retry may have succeeded | Verify terminal outcome |
| Treating lastObserved stage as final state | Logs may be missing/dropped | Reconcile business state |
| Counting log errors = failed users | One user can have multiple retries/events | Count by request/eventId |
| Trusting a single timestamp as absolute order | Clock skew, buffered logs | Correlation + causal metadata |
| Seeing a timeout and concluding upstream did not process | ACK/response may be lost | Idempotency and upstream sources |
| Increasing timeout/pool before measuring | Masks root cause and adds load | Check metrics and baselines |
| Enabling DEBUG across all of production | Leak risk, disk full, perf overhead | Enable with narrow scope, audit, expiry |
| Logging full request/exception payloads | May expose secrets and PII | Schema allowlist and redaction |
| Believing missing logs mean no event occurred | Collector may be failing/sampling | Check source→agent→backend |
| Looking only at the service reporting errors | Dependency/infrastructure may be the cause | Pivot via traces/metrics |
| Resetting a service without saving evidence | Loses critical state and timeline | Capture appropriate evidence before intervening |
| Verifying only that the app has no more ERRORs | Backlog/business data may be wrong | Business reconciliation |
| Assuming GC occurrence is the root cause | GC may just be a symptom | Compare pause/latency and allocation |
| Using a single trace to conclude for the whole system | Trace may be sampled/an outlier | Compare cohorts + aggregate metrics |

## 26. Testing Investigability Before a Real Incident

Investigation capabilities should be tested while the system is healthy:

- **Synthetic canary request** with a safe correlation ID, verifying events from gateway to backend.
- **Timeout simulation** in dependency tests: accurate errorCode/attemptNo logging; terminal outcome not misrecorded.
- **Crash/restart** in staging: know whether the last logs were flushed or what the queue might lose.
- **Collector outage:** verify backlog, retries, log drop metrics, and time-to-drain.
- **Concurrency:** interleaved requests A/B do not mix MDC.
- **JVM pressure:** test CPU/GC/thread pools in an authorized environment to observe metrics and alerts.
- **DB pool exhaustion:** test connection limits and error classification.
- **Message redelivery/DLQ:** preserve eventId and attempt without multiplying side effects.
- **Deployment rollback drill:** ensure version markers and acceptance checks are clear.
- **Privacy test:** IDs containing newlines/fake tokens do not leak data or create forged logs.
- **Time skew/ingestion delay:** queries and timelines can still explain time offsets.
- **Access test:** incident responders can view only the data they need.

Evaluate tests not just on "logs exist." Verify that an operator can **go from an alert to root-cause candidates and distinguishing evidence** without enabling sensitive data dumps or making arbitrary production edits.

## 27. Production Incident Investigation Practice Checklist

| Item | Check |
| --- | --- |
| Context | Identify impact, severity, scope, start time, and owner |
| Logging | Structured eventCode, requestId, traceId, version, and outcome |
| Query | Scope service/env/time range first, then pivot by correlation |
| Timeline | Distinguish eventTime from ingestionTime and clock skew |
| Exceptions | Read cause chain, classify timeouts, do not leak secrets |
| JVM | GC/heap/thread metrics/JFR available when needed and authorized |
| HTTP | Distinguish connect/read/pool timeouts, retry budget/idempotency |
| DB | Compare pool saturation, SQL fingerprints, locks, and transactions |
| Messaging | Publish confirm, consumer attempts, ACK/commit, and DLQ |
| Infrastructure | Pod/container restarts, OOMKill, node resources, DNS/TLS |
| Pipeline | Check log drops, rotation, agent queue, collector, and retention |
| Hypotheses | Record supporting, refuting, unknowns, and confidence level |
| Mitigation | Intentional changes, rollback/load shedding per runbook |
| Verification | SLOs, backlog, business state, and telemetry all recovered |
| Security | RBAC, redaction, protection of incident evidence |
| Learning | Postmortem, regression tests, alerts, and action item owners |

**Conclusion:** incident investigation with Java Logging is a process of **correlating traces and verifying hypotheses**. Start from impact and time window, use eventCode along with requestId/traceId to build a timeline, inspect JVM, HTTP, database, message broker, infrastructure, and the log collection pipeline, then cross-check against metrics/traces/business state. Logs are a strong source of evidence when backed by proper schema and correlation, but **a single ERROR line or a log gap is not the whole truth**.