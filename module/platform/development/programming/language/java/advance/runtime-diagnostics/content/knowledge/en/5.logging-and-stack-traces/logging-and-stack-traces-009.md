# 5.9. Controlling Log Volume, Secrets, and Synchronous Logging Impact

Logging helps find bugs, investigate incidents, and support auditing; yet every log record consumes CPU, memory, I/O, storage, and sometimes adds request latency. A single log line can pass through many stages: creating the event object, formatting, capturing thread/trace context, serializing, locking an appender, writing to stdout/file, container runtime, collector, network, and storage/indexing. Excessive logging can turn the observability system itself into a source of latency or even leak secrets.

The goal of this lesson in **5. Logging and Stack Traces** is balancing three things:

- **Sufficient evidence:** retain key events, outcomes, errorCodes, timestamps, durations, and correlation/trace IDs to trace an operation.
- **Within budget:** control events/second, bytes/second, CPU, allocation/GC, queues, p95/p99 latency impact, and storage cost.
- **Safe:** prevent passwords, tokens, session secrets, personal data, sensitive payloads, exception contents, or private infrastructure details from entering logs.

**Principle:** cut low-value logs *before creation*, strip secrets *before serialization*, measure cost *on the real execution path*, and treat async logging as a **bounded queue with failure policies**, not magic that eliminates cost.

## 1. Why Can a Logger Call Slow Down an Application?

Look at the general path:

~~~text
Request thread
   |
   | logger.info/debug/error(...)
   v
Level check / filter / sampling
   |
   +-- build arguments, message, context, stack/caller data
   |
   v
Encoder / formatter (text, JSON)
   |
   +-- synchronous appender --> stdout / file / network
   |                            --> container / collector / storage
   |
   +-- async appender -------> bounded queue
                                |
                                +--> background writer --> sink
                                |
                                +--> queue full: block / drop / fallback
~~~

The diagram is a conceptual model: argument creation, formatting, and context capture can occur in different places depending on framework/backend/configuration. Even when DEBUG is disabled or logs go to a queue, Java still **evaluates method arguments** before calling the logger; expensive computations can spend CPU/heap before the level check.

Common cost sources:
1. **CPU:** serializing DTOs/JSON, formatting stack traces, generating timestamps, stringifying collections, escaping strings.
2. **Allocation/GC:** each record can allocate multiple strings, arrays, objects, buffers, and MDC snapshots.
3. **Locking/waiting:** multiple threads contending on one appender or stdout stream; lock contention drives up p99.
4. **Disk/pipe/network:** stdout in a container is a buffered pipe; when the consumer lags, writes can block. File rotation, flushing, and network retries also create backpressure.
5. **Queue memory:** async logging retains events on heap awaiting the writer; larger queues increase memory footprint and flush time.
6. **Storage and search:** ingestion, replication, indexing, retention, and exports all cost money and resources.

Never infer from `log.info(...)` that writing is asynchronous. SLF4J is a facade; the appender/backend determines how records are transported and processed.

## 2. Budgeting Log Volume with Numbers

### 2.1. Basic Formulas

~~~text
events_per_second ≈ requests_per_second × avg_events_per_request
                    + events_from_jobs_and_background_tasks

raw_bytes_per_second ≈ events_per_second × avg_serialized_event_bytes
~~~

Hypothetical example: a service handles **2,000 requests/s**, each request emits **4 records**, and each serialized record averages **600 bytes**; ignoring background events for now.

~~~text
events/s = 2,000 × 4 = 8,000
bytes/s = 8,000 × 600 = 4,800,000 bytes = 4.8 MB/s
bytes/hour = 4,800,000 × 3,600
           = 17,280,000,000 bytes = 17.28 GB/hour
~~~

Here MB/GB are **decimal units**, not MiB/GiB. This is **raw serialized log** volume, excluding compression, indexes, metadata, replication, retention, or multi-sink duplication. Enabling DEBUG to double events/request generally doubles volume; logging large payloads multiplies it even faster.

Look beyond line count alone. Two systems both emitting 10,000 records/s—one with 30 KB stack traces per record and the other 300 bytes—have vastly different costs.

### 2.2. Metrics to Watch

| Metric | What you need to know |
| --- | --- |
| `log_events_total` by service, level, event name | Which events dominate traffic? |
| `log_bytes_total` and bytes/s | Is growth driven by event count or event size? |
| `log_event_size_bytes` p50/p95/p99 | Which stack traces and payloads are oversized? |
| `log_dropped_total` by reason/level | Drops from sampling, filters, queue full, or exporter? |
| Queue occupancy/capacity, enqueue/dequeue rate | Is the writer keeping up with producers? |
| Log call/enqueue p95/p99 | Are callers blocking or spending significant CPU? |
| Sink write latency, retries, exporter backlog | Is the collector, file, stdout, or network slow? |
| Disk space/inodes, file rotation, retention | Risk of full disk, lost logs, or self-inflicted service outage? |
| Request latency/throughput, CPU, allocation/GC | Is logging degrading JVM performance? |

These are **suggested metric names/groups**, not default metrics built into every Java logger. Distinguish **log created**, **successfully enqueued**, **written to sink**, and **ingested by backend**; an appender accepting an event does not prove durable storage at the destination.

### 2.3. Finding "Top Talkers" and Cardinality

Group volume by `service`, `environment`, `version`, `level`, `eventName`, `logger`, `normalized route`, `instance`. Avoid putting `requestId`, `userId`, URLs with query params, or exception messages into **metric labels**: cardinality explodes. Detailed IDs belong in logs/traces when legitimately justified; metrics use bounded-value labels.

When inspecting a service where 99% of INFO logs come from an item-processing loop, ask: **can this become one summary event + counter/histogram?** Removing event generation at the source beats dropping at the collector, because collector filtering never refunds CPU/heap already spent in the JVM.

## 3. Reducing Volume While Preserving Diagnostic Value

### 3.1. Logging at the Right Level and Milestones

| Common level | When to use | Volume control |
| --- | --- | --- |
| **ERROR** | An operation genuinely failed, with errorCode/cause | Log where the outcome is decided; avoid re-logging at every layer |
| **WARN** | Recoverable anomaly, retry/fallback | Bound repeating events while preserving total error counts and context |
| **INFO** | Lifecycle milestones, outcomes, major config changes | Prefer completion logs with duration/outcome over step-by-step chatter |
| **DEBUG** | Detailed processing decisions, especially when investigating | Enable per logger/service with time bounds and sensible sampling |
| **TRACE** | Very granular steps, high volume | Enable only with narrow targets and safe load bounds |

Do not classify every contractually expected HTTP 4xx as ERROR; conversely, do not downgrade genuine errors merely to stay under quota. If an exception is logged ERROR in a low layer, again in the controller, and again at the gateway, one incident turns into three duplicate logs. Distinguish **intermediate errors resolved by retry** from **final failed outcomes**.

Before:
~~~text
INFO validating record 1
INFO validating record 2
INFO validating record 3
...
INFO validating record 10000
~~~

After (illustrative data example):
~~~json
{"level":"INFO","event":"batch.validation.completed","items":10000,"invalid":42,"durationMs":825,"outcome":"PARTIAL_FAILURE"}
~~~

If investigating the 42 invalid items, log errorCodes and policy-compliant references, or use tracing/controlled sampled details. Never dump full DTOs for every item automatically.

### 3.2. Sampling, Rate Limiting, and Aggregation

- **Request/trace-based sampling:** decide keep/drop based on a stable ID to preserve full context for one flow, rather than sampling individual lines randomly and fragmenting timelines.
- **Probabilistic sampling:** 1%, 5%, or traffic-appropriate rates; keep sampling bias in mind when inferring statistics.
- **Deterministic hash sampling:** hash request/trace ID (never put sensitive personal IDs in metrics) so branches make consistent decisions; document the policy clearly.
- **Rate limiting:** cap at N events per interval to prevent log storms when a dependency fails. Keep a metric for suppressed counts and bounded summary notices.
- **Aggregation/deduplication:** "timeout to inventory-api occurred 8,432 times in 1 minute" is more useful than 8,432 identical lines, provided representative context is retained when needed.

**Never arbitrarily sample or disable** audit events, mandatory security telemetry, or logs required by contract/law. Even for ERROR/WARN, policies must handle failure log storms: keep exact error counts via metrics, throttle duplicate log lines, and route legally significant events via a separate pipeline.

With **tail sampling**, the collection pipeline buffers data until the outcome is known; you cannot "keep every error trace" if events were already dropped upfront before deciding. Collector-side sampling also does not save formatting CPU already spent in the application.

### 3.3. Bounding Record Size

Common sources of bloat: request/response bodies, headers, cookies, collections, DB rows, SQL bind parameters, base64 binaries, nested DTOs, and long or repeated multi-layer stack traces.

Best practices:
- Use a **schema/allowlist**, logging only `event, outcome, statusCode, errorCode, durationMs, correlationId` and approved valuable attributes.
- Cap text length, collection element counts, stack frame depth, or detailed events per operation per investigation needs.
- Explicitly emit `truncated=true` or aggregate counts when truncating; never chop raw JSON mid-string and break syntax.
- Avoid serializing whole objects only to truncate at the collector: CPU/memory cost and secret exposure have already happened inside the application.

## 4. Secrets: Prevent Exposure Before Serialization

Logs are easily replicated to consoles, files, collectors, dashboards, SIEMs, archives, tickets, and chat. A secret written to a log can persist long after the original session expires.

### 4.1. Fields That Must Never Be Logged Verbatim

| Category | Examples | Appropriate alternative |
| --- | --- | --- |
| **Authentication** | Passwords, OTPs, access/refresh tokens, JWTs, API keys, Authorization headers | Auth outcome event, method, failure code only |
| **Session** | Session cookies, session IDs, signed URLs, CSRF secrets | Internal correlation ID containing no secret |
| **PII** | Emails, phone numbers, addresses, government IDs, health data | Omit if unnecessary; if permitted, mask/tokenize per policy |
| **Financial/payment** | Card numbers, CVVs, account details | Approved business reference, status, and errorCode |
| **Infrastructure** | Private keys, DB URLs with passwords, secret env vars, config secrets | Config key name, present/missing flag, connection status |
| **Payloads** | Login forms, images/documents, raw HTTP requests/responses | Content type, byte size, route, validation outcome |
| **Exception internals** | Throwable messages containing URL tokens, SQL bind data, or user inputs | Exception type + stable errorCode, sanitized stack/cause |

**Never pass domain objects or credentials to a logger just because the API has placeholders.** `logger.info("request={}", request)` can still invoke a `toString()` containing passwords/tokens/PII. Specifically audit nested exceptions, request headers, MDC, HTTP client interceptors, ORM SQL parameters, and debug wire logs.

### 4.2. Allowlisting Beats Single-Layer Regex Redaction

The safer flow constructs a **new log event solely from approved fields**, such as:

~~~json
{"level":"WARN","event":"payment.authorize.failed","correlationId":"req-42","errorCode":"DOWNSTREAM_TIMEOUT","durationMs":782}
~~~

Do not serialize a raw `PaymentRequest` hoping regexes catch every encoding of a token. Redaction at the encoder and collector remains useful as **defense in depth**, never the sole defense.

Limitations:
- **Masking** such as partial email masking can still constitute personal data; comply with purpose and handling policies.
- **Hashing emails/phones** does not automatically anonymize them: dictionary attacks remain possible. Where linkability is needed, consider managed-key tokenization/HMAC for approved purposes.
- **Log injection:** input containing newlines/control characters or fake timestamps can forge log entries in plain text. Validate inputs and use properly escaping structured encoders.
- **Secrets in Throwables:** HTTP/DB error messages can embed URL queries or credentials; passing Throwables requires content protection mechanisms.
- **Cross-environment logs:** DEBUG allowed in staging does not mean raw payloads belong there or in production; staging must also protect real data if present.

### 4.3. Protecting the Log Lifecycle

Apply layered controls: least-privilege access, encryption in transit/at rest, purpose-bound retention, export authorization, access audit trails, policy-driven deletion of copies, and monitoring who reads logs. Never store log files in public directories or on critical shared partitions without quotas/rotation.

If a token/password leaks into logs, merely "hiding the line in the dashboard" **is not enough**. Assess every destination the data reached, isolate/revoke access, purge copies where possible, investigate exposure scope, and revoke/rotate compromised credentials as appropriate. Temporary snippets pasted into tickets or external tools must also be accounted for.

## 5. Why Synchronous Logging Can Spike p99 Latency

A **synchronous appender** performs write work on the caller's path, sometimes waiting on locks, output buffers, disk, stdout pipes, rotation, or network. Costs can vary wildly. **Illustrative** breakdown of a single request:

~~~text
business work:                   10.0 ms
format log on caller:             0.3 ms
wait for appender/stdout write:  15.0 ms
business work:                    5.0 ms
-----------------------------------------
approx elapsed:                 30.3 ms
~~~

In these sequential steps, waiting on writes dominates added latency even though business logic uses little CPU. This is **not a real benchmark**; a logger may buffer without flushing every record, or a sink may be fast when unloaded.

Often-overlooked blocking sources:
- `ConsoleAppender` or `System.out` writing over a pipe; a slow collector/container runtime fills the buffer and blocks writes.
- `FileAppender` locking/flushing/rotating, subject to filesystem latency and full disks.
- Direct network appenders encountering timeouts/reconnects; retry rules depend on the backend.
- Formatting Throwable stack traces costing CPU/strings even when file I/O is fast.
- Multiple workers calling the same appender concurrently, concentrating lock contention in tail latency.

**Synchronous writes do not equal durability:** a successful file write may sit in OS page cache without `fsync`; an accepted stdout write may not have reached the backend yet. Distinguish `logged/enqueued`, `written`, `flushed`, and `ingested`.

### Argument Evaluation: Disabled DEBUG Can Still Spend CPU

The two snippets below **illustrate SLF4J usage** and are not standalone runnable because they require application logger, DTO, and helpers:

~~~java
logger.debug("payload={}", expensiveSerialize(payload));
~~~

`expensiveSerialize(payload)` **is still called** because Java evaluates method arguments prior to the call, even when DEBUG is off. If computing a summary is expensive, guard it:

~~~java
if (logger.isDebugEnabled()) {
    logger.debug("payloadSummary={}", safeSummary(payload));
}
~~~

In real apps, use lazy/supplier APIs supported by the backend where available, and never serialize sensitive raw payloads. Remember an object's `toString()` itself can run heavy logic or leak data.

## 6. Asynchronous Logging: Decoupling the Sink Without Removing Backpressure

An async appender has **producer threads** pushing records into a queue and a **writer thread** draining to the sink. This can reduce caller I/O waits, yet enqueueing, allocation, and context capture still cost resources. Memory queues are bounded, and the writer must keep pace with log emission.

### 6.1. What Happens When the Queue Fills?

| Policy | Effect | Risk |
| --- | --- | --- |
| **Block producer** | Waits for queue space, reducing short-term drops | Request threads stall, timeouts, pool saturation, potential outage if sink dies |
| **Drop new records** | Keeps caller latency minimally impacted | Logs vanish right during incidents, starving investigations of evidence |
| **Severity priority** | Keeps WARN/ERROR near full, drops TRACE/DEBUG/INFO | Does not guarantee all high-severity logs survive full/kill; not a substitute for audit |
| **Spill/buffer to disk** | Absorbs brief network interruptions | Consumes disk, I/O, cleanup complexity, disk-full risk |
| **Fallback to sync** | May preserve critical events | Reintroduces I/O onto the critical path, spiking p99 right under overload |

No single policy fits every system. "Never block" trades off potential event loss, whereas "never drop" via blocking can trade off availability. Mandatory audit events need channels with explicit delivery/durability semantics rather than relying solely on async loggers.

### 6.2. Logback AsyncAppender: Configuration Example and Trade-offs

With Logback Classic dependencies present, the XML below **illustrates only the switches**, not a blanket production recommendation:

~~~xml
<configuration>
  <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
      <pattern>%d{ISO8601} %-5level [%thread] %logger - %msg%n</pattern>
    </encoder>
  </appender>
  <appender name="ASYNC" class="ch.qos.logback.classic.AsyncAppender">
    <queueSize>1024</queueSize>
    <discardingThreshold>0</discardingThreshold>
    <neverBlock>false</neverBlock>
    <maxFlushTime>2000</maxFlushTime>
    <appender-ref ref="STDOUT"/>
  </appender>
  <root level="INFO">
    <appender-ref ref="ASYNC"/>
  </root>
</configuration>
~~~

- `queueSize=1024`: maximum number of events in the queue, **not maximum bytes**. Large events or long stack traces can still consume significant heap.
- `discardingThreshold=0`: disables Logback's automatic low-level event discarding near queue saturation, **without guaranteeing zero log loss**.
- `neverBlock=false`: when the queue is full, producers may **block** waiting. Setting `true` causes drops when the queue cannot accept records.
- `maxFlushTime=2000`: during normal shutdown, waits up to the timeout (ms) to drain the queue; if exceeded or killed/crashed, flushing everything is not guaranteed.
- The underlying appender is still stdout; **pipe/container/collector stalls can still back up**. Wrapping in AsyncAppender does not make stdout infinite.
- This pattern outputs plain text only—it **does not redact secrets** or attach trace IDs/correlation IDs. Production safety requires proper encoders/context and secret protection.

Logback defaults to dropping lower-level events near full queue in certain versions, and `discardingThreshold` alters that behavior. **Read the manual for the exact version in use**; other backends have different settings and semantics. Dropping INFO does not guarantee ERROR events are preserved unconditionally.

### 6.3. Shutdown, Ordering, Retries, and Loss

- During normal service shutdown, flush/stop loggers cleanly within an adequate termination grace period. SIGKILL/OOM/crashes can lose un-flushed events.
- Async queues can reorder across producers and services at the backend. Always keep event timestamps and traceId/spanId.
- Exporter retries can create duplicates; queue drops and collector failures create gaps. Never assume exactly-once delivery.
- MDC/trace context must be captured at emission time and propagated across executors; the writer thread does not inherently know the originating request.
- A steadily growing queue signals producers outpacing the sink; merely enlarging `queueSize` delays failure and increases heap usage.
- Monitor `queue_size`, `dropped_total`, `write_duration`, exporter errors, and request p99 whenever changing configuration.

## 7. Standalone Java 17+: Sampling, Allowlisting, and Log Injection Defense

This example uses `System.out` to **illustrate event selection and data protection**, not to benchmark synchronous vs. async logging. It processes 12 inputs; retains 2 error events, samples 4 success events, and suppresses the remaining 6. Email/token fields in the object **are never written to logs**; a reference containing a newline is rejected.

**Note:** keeping "every third request" is solely to produce deterministic output; on live traffic, positional sampling can skew results and does not replace consistent sampling by request/trace ID.

File **`SafeLogBudgetDemo.java`**:

~~~java
import java.time.Instant;
import java.util.Locale;
import java.util.regex.Pattern;

public final class SafeLogBudgetDemo {
    private static final Pattern SAFE_REF =
            Pattern.compile("[A-Z0-9-]{1,20}");
    private static final Instant BASE =
            Instant.parse("2026-10-29T00:00:00Z");

    private record Incoming(
            String orderRef,
            String email,
            String accessToken) { }

    private static String allowedRef(String raw) {
        return raw != null && SAFE_REF.matcher(raw).matches()
                ? raw : "[omitted]";
    }

    public static void main(String[] args) {
        int observed = 0;
        int sampledSuccess = 0;
        int emittedErrors = 0;
        int suppressed = 0;

        for (int i = 1; i <= 12; i++) {
            Incoming input = new Incoming(
                    i == 6 ? "BAD\nFORGED" : "ORD-" + i,
                    "private@example.invalid",
                    "demo-token-not-for-log"
            );
            observed++;

            boolean failed = (i % 5 == 0);
            boolean sampleSuccess = !failed && (i % 3 == 0);

            if (!failed && !sampleSuccess) {
                suppressed++;
                continue;
            }

            String level = failed ? "ERROR" : "INFO";
            String event = failed
                    ? "order.failed" : "order.sampled_success";
            String safeRef = allowedRef(input.orderRef());
            String requestId = "req-" + i;

            System.out.printf(Locale.ROOT,
                    "%s level=%s event=%s requestId=%s orderRef=%s%n",
                    BASE.plusSeconds(i), level, event,
                    requestId, safeRef);

            if (failed) {
                emittedErrors++;
            } else {
                sampledSuccess++;
            }
        }

        System.out.printf(Locale.ROOT,
                "summary observed=%d sampledSuccess=%d errors=%d suppressed=%d%n",
                observed, sampledSuccess, emittedErrors, suppressed);
    }
}
~~~

Compile and run:

~~~bash
javac SafeLogBudgetDemo.java
java SafeLogBudgetDemo
~~~

**Exact stdout**:

~~~text
2026-10-29T00:00:03Z level=INFO event=order.sampled_success requestId=req-3 orderRef=ORD-3
2026-10-29T00:00:05Z level=ERROR event=order.failed requestId=req-5 orderRef=ORD-5
2026-10-29T00:00:06Z level=INFO event=order.sampled_success requestId=req-6 orderRef=[omitted]
2026-10-29T00:00:09Z level=INFO event=order.sampled_success requestId=req-9 orderRef=ORD-9
2026-10-29T00:00:10Z level=ERROR event=order.failed requestId=req-10 orderRef=ORD-10
2026-10-29T00:00:12Z level=INFO event=order.sampled_success requestId=req-12 orderRef=ORD-12
summary observed=12 sampledSuccess=4 errors=2 suppressed=6
~~~

**Interpretation:**
- 4 success logs (3, 6, 9, 12) and 2 error logs (5, 10); 6 success events are suppressed per policy.
- On request 6, `orderRef` contains an invalid newline; code prints `[omitted]` rather than forging an extra log line.
- `email` and `accessToken` exist inside `Incoming`, yet the logger receives only `requestId`, event, and the validated reference. The whole input object is never serialized.
- Fixed timestamps make stdout testable; production must use real event times with proper timezone/trace context.
- Because the program prints synchronously via `System.out.printf`, it **does not prove** async behavior or p99 improvement. Benchmark real backends/appenders under real workloads and sinks.
- Keeping every error in **12 illustrative records** does not mean logging unlimited ERRORs under unbounded load is free. Real pipelines still need capacity/aggregation and separate durable channels for audit/security.

## 8. Fairly Measuring Synchronous vs. Asynchronous Logging Impact

A meaningful experiment holds workload, event size, logging level, encoder, host/container, disk/collector, and duration constant. Include warm-up, enough samples, and at least two stable runs before comparing p99.

Steps:
1. **Baseline:** record request p50/p95/p99, throughput, CPU, allocation rate, GC pauses, events/s, bytes/s, dropped events.
2. **Synchronous configuration:** measure logger/appender call duration, lock contention, stdout/file latency, and events reaching the backend.
3. **Async configuration:** keep identical log payloads; measure enqueue time, queue occupancy, drops/blocks, writer latency, and ingestion counts.
4. **Slow sink scenario:** simulate collector downtime/full pipe/slow disk safely in a test environment; observe whether the app blocks or drops.
5. **Shutdown:** test graceful stop and abrupt kill; measure logs remaining in the queue and document durability limits.
6. **Conclusion:** a p99 improvement counts as a success only if diagnostic evidence quality and audit/security requirements remain intact.

Interval measurement snippet in Java:

~~~java
long startNanos = System.nanoTime();
// Actual logging call to measure goes here in the test.
long elapsedNanos = System.nanoTime() - startNanos;
~~~

This snippet only **illustrates measurement boundaries**; it is not a standalone benchmark. Timing a single tiny log call suffers measurement overhead. An async logger returning quickly may **only be enqueueing**, not writing to the sink. Use appender and collector metrics to tell them apart.

### Symptom and Hypothesis Matrix

| Symptom | Possibility | Verification |
| --- | --- | --- |
| Request p99 rises after enabling DEBUG | Eager serialization, log locks, I/O | CPU profiler, log call timing, allocation, bytes/s |
| CPU still rises with DEBUG filtered out | Code evaluates arguments before level check | Inspect serialization/`toString` calls and level guards |
| Async queue nearly full, p99 rises | Producers blocking on queue | Enqueue latency, full count, `neverBlock` |
| p99 drops yet many error logs vanish | Queue drops or exporter/collector loss | Dropped counter, written vs. ingested counts |
| GC rises when async queue is large | Buffered events occupy heap | Queue memory, heap usage, allocation, GC |
| Disk fills rapidly after deploy | More events, larger payloads, missing rotation/retention | Bytes/event, file sizes, disk/inodes, collector |
| Logs contain tokens in exceptions | Unsanitized Throwable/headers/bodies | Audit exception messages, encoders, collector filters |
| No logs seen although requests ran | Filters, sampling, queue drops, unflushed buffers | Pipeline metrics, traces, appender config |

## 9. Classifying Log Sources by Reliability Requirements

| Source | Purpose | Reference policy |
| --- | --- | --- |
| DEBUG/TRACE | Detailed diagnostics | Can sample, short TTL, rate limit, drop with metrics |
| Operational INFO | Outcomes, latency, lifecycle | Keep key milestones, curb repetition, aggregate hot paths |
| WARN/ERROR | Incident diagnostics | Keep codes/context, monitor drops, cap repetition safely |
| Security telemetry | Detect anomalous behavior | Strict event schema, integrity, permissions, and retention |
| Mandatory audit trail | Auditing, accountability, recovery | Durable pipeline with explicit delivery/failure semantics |

**Operational logging is not automatically an audit trail.** When an event must persist after a transaction commits, consider a transactional outbox, durable queue, or event store with replay, deduplication, and explicit retention. Switching `ConsoleAppender` to `AsyncAppender` does not create an exactly-once guarantee.

**Fail-open or fail-closed when the logger fails?**
- For non-essential diagnostics, usually keep serving requests while emitting metrics/alerts about log loss.
- For mandatory audit/security, policy may require halting or restricting operations when evidence cannot be recorded; base this decision on risk and legal requirements, never as a blanket rule.
- Avoid feedback loops when the logger/collector itself fails; do not spam "failed to log" through the very broken pipeline.

## 10. Before-and-After Scenarios

**A. INFO inside a hot loop.** Before: every request emitted 8 records, saturating the stdout pipe; after: log only completion with `outcome/durationMs/traceId` and track item counts via metrics. Re-measure bytes/s and request p99 instead of counting lines alone.

**B. Async appender helps p99 but loses evidence.** Small queue + nonblocking config dropped logs whenever the collector slowed. After: add queue/dropped metrics, apply severity-aware policies, size capacity based on tests, verify shutdown flushing, and separate audit channels where needed. Do not just "make `queueSize` huge".

**C. Secret leaked in exception.** A request URL containing an access token was embedded in a Throwable message; ERROR logging sent it straight to storage. After: strip secrets from URLs, build safe errorCodes, apply redaction to exceptions/contexts, and evaluate rotating the exposed token.

**D. Enabling DEBUG worsens OOM.** Serializing large object graphs plus retaining events in an async queue spiked heap/GC. After: cap event sizes, sample purposefully, measure allocation/heap/queue, and auto-expire debug overrides.

**E. Logs lost on shutdown.** The async worker still had queued items when the container was killed; trailing lines disappeared. After: add graceful shutdown/flush timeouts, adjust grace periods, measure event gaps; use a separate durable channel for audit.

**F. Log volume becomes a security incident.** Production raw requests/responses contained emails and cookies, stored for weeks. After: allowlist fields, enforce short purpose-bound retention, tighten access controls, redact, and purge/protect existing copies.

## 11. Common Reasoning Pitfalls

- **"One small INFO line has no impact."** Thousands of lines per second across multiple sinks compound into CPU, I/O, storage, and tail latency.
- **"DEBUG disabled means zero cost."** Java method arguments can still be evaluated before the logger call.
- **"Async is always non-blocking."** Full queues can block, drop, or fall back; every policy has trade-offs.
- **"Making `queueSize` bigger prevents drops forever."** Queues remain finite, shutdowns and sink failures still occur, and huge queues inflate heap.
- **"Logging errors at every layer helps investigation."** Repeated stack traces bloat volume, overload search, and multiply secret-leak risk.
- **"When DEBUG is on, dump the whole payload."** Bodies/headers carry PII, cookies, and secrets; always allowlist.
- **"Collector regexes catch all secrets."** Secrets already traversed stdout/files and appear in many nested encodings.
- **"Hashing emails makes them anonymous."** Data can still be re-identified; assess against risk and policy.
- **"Missing logs mean the event didn't happen."** It could be level-filtered, sampled, dropped, failed at the sink, or delayed in ingestion.
- **"Once the app enqueues it, the log is saved."** Producer, queue, sink, collector, and backend are distinct stages.
- **"Synchronous file write means guaranteed durability."** OS cache/`fsync`, filesystem, and rotation govern durability differently.
- **"`requestId` makes a great metric label."** It usually explodes cardinality.
- **"Deleting the log in the dashboard fixes a secret leak."** Inspect all copies and revoke/rotate the secret where appropriate.
- **"Leaving TRACE on after an incident is harmless."** Cost and data exposure persist; enforce expiration and authorization.

## 12. Production Checklist

**Before release:**
1. Define event schemas/allowlists with level, service, event, errorCode, outcome, duration, and correlation/trace IDs.
2. Test that no passwords/tokens/PII appear in messages, DTOs, headers, MDC, exceptions, or debug libraries.
3. Budget events/s, bytes/s, event sizes, and retention for expected traffic and failure bursts.
4. Use metrics and appropriate sampling/rate limits on hot paths without arbitrarily dropping audit/security events.
5. Audit effective log levels, eager argument formatting costs, and record size limits.
6. Document sync/async appenders, queue capacity, block/drop policies, fallbacks, retries, shutdown flush, and loss metrics.
7. Verify disk/pipe/collector quotas, read permissions, encryption, and rotation/retention; avoid shared disk exhaustion.

**When proving performance improvements:**
1. Hold workload, JDK, backend, event size, and sink constant against the baseline.
2. Measure request p95/p99, throughput, CPU/GC, log call/enqueue latency, queue occupancy, and dropped events.
3. Simulate slow collector/full disk/full queue/kill in staging to confirm failure behavior.
4. Compare emitted vs. written vs. backend-ingested counts; verify errors remain findable by correlation ID.
5. Document trade-off decisions: where availability wins, where audit durability wins, and who approved adjustments.
6. Time-box elevated DEBUG/TRACE overrides and re-audit secrets/cost afterward.

**Key takeaway:** cut logs **at the source**, block secrets **before serialization**, track **events/s and bytes/s**, measure **synchronous cost on the critical path**, and assume **async queues are always finite**. A sound logging strategy aids incident investigation without becoming the incident itself.

### References

- OWASP, Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- Logback, AsyncAppender manual: https://logback.qos.ch/manual/appenders-async-sift.html
- OpenTelemetry, Logs Data Model: https://opentelemetry.io/docs/specs/otel/logs/data-model/
- Java SE 17, PrintStream API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintStream.html

Actual appender behavior and drop policies depend on library version, sink, and runtime. Cross-check real deployment configs with metrics rather than treating illustrative examples as mandatory configurations.
