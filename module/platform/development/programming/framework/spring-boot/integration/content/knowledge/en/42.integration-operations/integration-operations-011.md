# Alerting on Sustained Errors, Latency, and Work Backlogs

## 1. The Integration Operations Problem: The App Is Up, Yet Work Makes No Progress

In a **Spring Boot Integration** service, an HTTP request may create an order, write to PostgreSQL, store an outbox record, publish a message to Kafka, and wait for a consumer in another service to process it. Another adapter might call a partner API, refresh Redis, or run a scheduled task. Each step has its own failure modes, retries, timeouts, and transactions.

An application reporting `/actuator/health = UP` can still suffer severe breakdowns:

- A Kafka consumer stays connected yet **fails to process** records due to repeated database errors.
- An HTTP client fails for 20 minutes straight; retries execute as designed, yet no business outcome happens.
- An outbox relay keeps running, yet emits slower than writes arrive, causing **queues to grow and oldest work age to stretch**.
- One Kafka partition is stuck while average latency of completed records looks healthy.
- A scheduler stops creating new work after a deployment; an empty queue does not mean the system is doing enough work.

Therefore, **operational alerting must examine integration flow outcomes over time**, especially across three signal groups: **sustained errors**, **breached latency**, and **work backlogs**. A single transient blip rarely needs to wake on-call; a retry loop burning through processing deadlines or a steadily growing backlog must be caught early.

~~~mermaid
flowchart LR
    HTTP["HTTP / scheduler"] --> DB[("Database")]
    DB --> Outbox[("Outbox PENDING")]
    Outbox --> Relay["Outbox relay"]
    Relay --> Kafka[("Kafka topic")]
    Kafka --> Consumer["Consumer / worker"]
    Consumer --> Target["Partner HTTP / DB / cache"]
    DB -. "Errors / creation time" .-> Observe["Metrics + logs + traces"]
    Outbox -. "Backlog + record age" .-> Observe
    Relay -. "Retries + publish time" .-> Observe
    Consumer -. "Lag + progress + outcome" .-> Observe
    Observe --> Rules["Prometheus / alert rules"]
    Rules --> Oncall["On-call / runbook"]
~~~

**Lesson objective:** define incidents by business impact; design metrics and thresholds reflecting that impact; write sustained alert rules that avoid noise; distinguish lag, backlog, and latency; and build runbooks, alert tests, and end-to-end observability across adapters.

## 2. From Technical Symptoms to Business Impact

Before setting thresholds, define **success for one unit of work**. For an order flow, you might pick:

- **Accepted:** request validated and durably persisted to database/outbox.
- **Dispatched:** message acknowledged by the broker.
- **Processed:** consumer updated target data and committed state/offset per design.
- **Business completed:** final state satisfies the user or partner contract.

These milestones are not equivalent. An HTTP 202 response means the app **accepted the work** per contract—not that downstream finished. A Kafka producer ack does not mean consumers processed it; committing an offset does not prove all non-Kafka side effects ran once.

Example SLO (Service Level Objective) for a specific flow:

> Within an evaluation window, at least **99.5% of valid work items** reach accurate business completion within **5 minutes** of durable acceptance.

This is an **illustrative SLO**, not a default threshold for every system. To measure accurately, define each component explicitly:

| SLO Component | Must Be Explicitly Defined |
|---|---|
| Counting unit | One valid `businessOperationId`/event; never count each retry as new work |
| Start point | Timestamp when work is durably persisted to outbox/job store |
| End point | Target state committed and eligible to count as completed |
| Deadline | 5 minutes from start point, aligned with business intent |
| Success | Final contract outcome, including explicit business-error handling rules |
| Failure | Missed deadline or terminal failure state, even if retries continue |
| Exclusions | Properly canceled work, maintenance windows, invalid inputs—must follow consistent rules |

**Important:** counting only completed records excludes stuck queued records from the denominator, making percentiles look great while customers wait. Final SLOs must therefore track **overdue work**, while latency and backlog act as supporting diagnostics.

## 3. Three Core Alert Groups

| Group | Operational Question | Typical Signals | Why Not Alert on a Single Instantaneous Sample |
|---|---|---|---|
| **Sustained errors** | Are many operations failing consecutively or is error ratio meaningfully high? | Terminal failure rate, attempt errors, retry counts, DLQ | One timeout can self-heal; tiny traffic makes ratios noisy |
| **Latency** | Is successful work slower than target? Is work missing deadlines? | End-to-end p95/p99, per-hop durations, overdue count | Short spikes rarely break SLOs; completion-only latency hides stuck items |
| **Backlog** | Is work arriving faster than processing, or has progress stopped? | Queue depth, oldest pending age, consumer lag, in-flight, last progress | Queue growth during bursts can be normal; empty queues when intake stops can signal failure |

Good alerts combine **severity**, **sustained duration**, and **actionability**. Metrics tell you "something is wrong"; logs, traces, and runbooks help answer "why" and "what to do."

## 4. Designing Metrics Around the Lifecycle of a Unit of Work

### 4.1. Choosing Bounded Names and Labels

Assuming Micrometer and Prometheus, define illustrative series:

| Planned Metric | Type | Meaning |
|---|---|---|
| `integration_operation_completed_total{integration,result}` | Counter | Total work **reaching terminal state**, `result=success/failed`; counted once per business operation |
| `integration_operation_attempts_total{integration,outcome}` | Counter | Every HTTP/broker/DB execution attempt, including retries |
| `integration_operation_duration_seconds_bucket{integration,le}` | Histogram | End-to-end duration from durable acceptance to successful completion |
| `integration_pending_items{integration}` | Gauge | Snapshot count of items awaiting processing or retry |
| `integration_oldest_pending_age_seconds{integration}` | Gauge | Current age of the oldest pending item |
| `integration_inflight_items{integration}` | Gauge | Count of items currently held/processed by workers |
| `integration_last_progress_timestamp_seconds{integration}` | Gauge | Unix epoch timestamp of the last committed progress |
| `integration_dead_letter_events_total{integration}` | Counter | Events routed to DLQ/DLT |
| `integration_dead_letter_items{integration}` | System-dependent Gauge | Unresolved items sitting in dead-letter storage |

These names represent an **application-owned observability contract**, not built-in Spring Boot defaults. In Micrometer you typically name them `integration.operation.completed`; Prometheus exports counters as `integration_operation_completed_total`. With `Timer`, the Prometheus exporter emits `_count`, `_sum`, and `_bucket` when percentile histograms are enabled on the registry.

Keep label values **low-cardinality**:

~~~text
Good:
  integration = partner-order-sync | outbox-publish | inventory-consume
  result      = success | failed
  outcome     = success | timeout | rate_limited | server_error

Never put in metric labels:
  orderId, eventId, userId, email, requestId,
  URLs with dynamic parameters, message payloads, SQL statements.
~~~

`traceId`, `businessOperationId`, and `eventId` belong in **logs/traces** to investigate individual events; putting millions of unique IDs in metric labels overloads Prometheus and skyrockets observability costs.

### 4.2. Distinguish Attempt Errors from Terminal Errors

Suppose one operation calls a partner API four times: three return HTTP 503, and the fourth succeeds.

- `integration_operation_attempts_total`: increments by **4** (3 failed attempts + 1 success).
- `integration_operation_completed_total{result="success"}`: increments by **1**.
- `integration_operation_completed_total{result="failed"}`: **does not increment**.

Alerting on attempt error rate reflects **dependency health** and retry overhead; alerting on terminal error rate reflects **final customer-facing outcomes**. Both serve different purposes. A consumer retrying endlessly without entering a terminal failed state **will not raise terminal errors**, which is why oldest-age and stall alerts remain necessary.

### 4.3. Distinguish Processing Latency from End-to-End Latency

~~~text
T0:   HTTP received, work persisted to DB/outbox
T1:   Worker begins processing
T2:   Partner HTTP returns result
T3:   DB commits success state

Queue wait       = T1 - T0
Processing time  = T3 - T1
End-to-end delay = T3 - T0
~~~

Measuring only `T3 - T1` can show a snappy 100 ms partner response while work sat 40 minutes in a queue—keeping latency graphs "green" while breaking a 5-minute SLO. Across multi-adapter flows, **end-to-end latency** and **incomplete-work age** align much closer with business impact.

Choose clocks and timestamps carefully. Within a single process, use monotonic clocks where supported; for cross-DB/message end-to-end timestamps, ensure synchronized clocks, consistent UTC timezones, and validation against skewed timestamps. Never record negative durations into histograms silently.

## 5. Collecting Metrics with Spring Boot Actuator and Micrometer

### 5.1. Dependencies and Example Configuration

For a BOM-managed Spring Boot project, add:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Example `application.yml` for Prometheus scraping:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  endpoint:
    health:
      probes:
        enabled: true
  metrics:
    tags:
      application: integration-service
~~~

Protect `/actuator/prometheus` with **network policies or authentication** suited to your deployment; never expose metrics publicly to the Internet by default. Spring Boot and registry versions can alter autoconfigured metric names and details; always inspect **live scrape output** before wiring metric names into alert rules.

Spring Boot Actuator exposes JVM, HTTP server, connection pool, and framework metrics. Those help diagnose root causes, **yet do not replace** business metrics such as outbox age, unfinished jobs, or last successful completion time.

### 5.2. Recording Business Outcomes

Example adapter recording metrics after a business operation reaches terminal state and **the state-saving transaction has committed**:

~~~java
package example.integration.operations;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.time.Duration;
import java.time.Instant;
import java.util.Set;
import org.springframework.stereotype.Component;

@Component
public class IntegrationOutcomeMetrics {

    private static final Set<String> KNOWN_INTEGRATIONS =
            Set.of("partner-order-sync", "outbox-publish", "inventory-consume");

    private final MeterRegistry registry;

    public IntegrationOutcomeMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void completedSuccessfully(String integration, Instant acceptedAt) {
        validate(integration);
        registry.counter("integration.operation.completed",
                "integration", integration, "result", "success").increment();

        Duration elapsed = Duration.between(acceptedAt, Instant.now());
        if (!elapsed.isNegative()) {
            Timer.builder("integration.operation.duration")
                    .description("Accepted-to-successful-completion delay")
                    .tag("integration", integration)
                    .publishPercentileHistogram()
                    .register(registry)
                    .record(elapsed);
        }
    }

    public void completedWithFailure(String integration) {
        validate(integration);
        registry.counter("integration.operation.completed",
                "integration", integration, "result", "failed").increment();
    }

    private void validate(String integration) {
        if (!KNOWN_INTEGRATIONS.contains(integration)) {
            throw new IllegalArgumentException("Unknown integration name");
        }
    }
}
~~~

This illustrates **metric recording**, not a full job-processing engine. With retries or multiple replicas, gate completion behind an **atomic DB state transition** (e.g., `PENDING → SUCCEEDED` or `RUNNING → FAILED`) so reprocessed events are not double-counted. Call the recorder **after commit succeeds** (or via post-commit domain events safely consumed); recording before commit and rolling back reports false successes.

This success timer does not measure operations that remain **pending** or failed. Therefore it cannot serve as the sole SLO alert source; compute overdue work directly from durable state storage. In production, align histogram buckets with real deadlines; without enabled histograms or matching buckets, `histogram_quantile` will mis-estimate.

### 5.3. Measuring Backlog and Record Age

Assuming a PostgreSQL outbox with `state IN ('PENDING', 'RETRY', 'SENT')` and `created_at`:

~~~sql
SELECT
    COUNT(*) AS pending_items,
    COALESCE(
        EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - MIN(created_at))),
        0
    ) AS oldest_pending_age_seconds
FROM integration_outbox
WHERE state IN ('PENDING', 'RETRY');
~~~

Meaning:

- `pending_items`: incomplete backlog at that snapshot.
- `oldest_pending_age_seconds`: how long the oldest job has waited; `0` when no pending rows exist.

At scale, running full-table `COUNT(*)` on every Prometheus scrape is expensive. **Sample periodically via a rate-limited background worker**, optimize indexes/queries, or use dedicated summary stores, updating registered gauges from cached snapshots. Never run blocking SQL inside scrape callbacks or HTTP event loops, and never keep returning a stale "last gauge value" forever when sampling fails. Track **last snapshot timestamp**, alert on stale telemetry, and never mistake stale gauges for live truth.

For Kafka, **consumer lag** is the gap between committed consumer offsets and head offsets as computed by the exporter; it does not directly measure message age or missing business operations. Metrics may come from Kafka clients, Spring Kafka/Micrometer, or external exporters, and **exact names vary by source**. Never copy PromQL written for exporter A onto exporter B without checking labels, semantics, partitions, and group scope.

## 6. Alerting on Sustained Errors

### 6.1. Why "Sustained"?

Across HTTP and message brokers, brief timeouts, rebalances, network blips, or HTTP 429s often self-heal. Paging on every failed request floods on-call with unactionable noise.

A reliable rule combines:

1. **Error ratio** over a meaningful window.
2. **Minimum volume threshold** so 1/1 failure does not fire a 100% alert.
3. **Continuous breach duration** via Prometheus `for:`.
4. **Severity separation**: self-healed retry spikes may warrant warnings; terminal failures or missed deadlines warrant pages.

Example: "Terminal failure rate exceeds 5% over a 10-minute window, with at least 50 completed operations in that window, sustained for 5 minutes." Numbers below are **illustrative thresholds**; calibrate from actual SLOs, traffic, and retry characteristics.

### 6.2. Prometheus Rules

Rules below assume the app exports the exact series defined in section 4:

~~~yaml
groups:
  - name: integration-operations
    rules:
      - alert: IntegrationSustainedTerminalFailures
        expr: |
          (
            sum by (integration) (
              rate(integration_operation_completed_total{result="failed"}[10m])
            )
            /
            clamp_min(
              sum by (integration) (
                rate(integration_operation_completed_total[10m])
              ), 1e-9
            )
          ) > 0.05
          and on (integration)
          sum by (integration) (
            increase(integration_operation_completed_total[10m])
          ) >= 50
        for: 5m
        labels:
          severity: page
          team: integrations
        annotations:
          summary: "Sustained failure rate: {{ $labels.integration }}"
          description: "Inspect terminal errors, retries, dependencies, and backlog."
~~~

Explanation:

- `rate(...[10m])` computes per-second rate over 10 minutes; numerator/denominator yields the failed completion share.
- `clamp_min(..., 1e-9)` prevents division by zero without turning zero traffic into an error.
- `increase(...[10m]) >= 50` suppresses noise on very low-traffic integrations.
- `for: 5m` requires the expression to stay true across evaluation intervals for 5 minutes.

This rule **misses** flows with zero completions because everything is stuck; pair it with **oldest pending age**, **no progress**, and **missing telemetry** alerts. For very low-traffic integrations, alert on "overdue items" or business heartbeats instead of requiring 50 operations.

Never use `rate(errors)` as the denominator if you want an error ratio; the denominator must be **all completed operations** matching the same integration, contract, and window. Inconsistent `integration`, `result`, or `environment` labels across metrics produce empty or cross-contaminated PromQL results. Isolate environments via datasources, labels, or explicit rule filters.

### 6.3. Transient Errors and Retry Storms

A partner API returning 503 where every operation eventually succeeds before its deadline may preserve the SLO while its retry storm overloads the DB, thread pools, and partner. Keep separate metrics for **attempt error rate**, retries per job, `429` responses, and open circuit breakers; emit warnings on prolonged dependency errors or falling throughput before terminal failures erupt.

Invalid messages landing repeatedly on a Dead Letter Topic require triage scaled to severity. Track `integration_dead_letter_events_total` and unresolved DLQ counts; never endlessly retry malformed schemas with zero chance of recovery.

## 7. Alerting on Latency

### 7.1. Per-Hop vs. End-to-End Latency

In an `HTTP → DB → outbox → Kafka → consumer → external HTTP` chain, measure:

| Latency Segment | Measured From → To | Diagnostic Clue |
|---|---|---|
| HTTP server | Request arrival to response | CPU/thread pools, auth, DB, timeouts |
| JDBC/R2DBC | Query start to result/commit per instrumentation | Locks, connection pools, slow queries |
| Outbox waiting | `created_at` to relay claim | Relay down or under-provisioned workers |
| Kafka produce | Send call to broker ack | Broker, batching, quotas, network, timeouts |
| Consumer processing | Record receipt to processed/committed state | Serialization, DB, partner API, retries |
| End-to-end | Durable acceptance to final business state | Sum of queue waits, processing, retries, and hops |

Never add per-hop `p95` percentiles together and call it end-to-end `p95`; percentiles do not sum linearly. Measure end-to-end directly and use per-hop spans/metrics to isolate root causes.

### 7.2. Example p95 Latency Alert

~~~yaml
groups:
  - name: integration-latency
    rules:
      - alert: IntegrationEndToEndP95High
        expr: |
          histogram_quantile(
            0.95,
            sum by (le, integration) (
              rate(integration_operation_duration_seconds_bucket[10m])
            )
          ) > 120
          and on (integration)
          sum by (integration) (
            increase(integration_operation_duration_seconds_count[10m])
          ) >= 50
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "High p95 latency: {{ $labels.integration }}"
          description: "Check queue wait times, retries, and slow dependencies."
~~~

Illustrative condition: **p95 over 120 seconds**, sufficient sample size, sustained for 10 minutes. `histogram_quantile` sums histogram buckets **by `le` and `integration`**. Preserve `le` when aggregating classic histograms; native histograms use different query syntax.

Two caveats:

1. The histogram from section 5 records **successfully completed operations**. If all work stalls, samples vanish—rely on oldest pending age and overdue counts. Never interpret low p95 as proof all work is finishing on time.
2. Bucket boundaries and `rate` windows must match deadlines and traffic; on low-volume flows, percentiles fluctuate wildly. For hard deadlines, the **overdue operations ratio** often aligns better with SLOs than percentiles.

### 7.3. Deadline-Based SLO Alerting

Suppose the business rule is completion within 5 minutes. If every job persists `accepted_at`, `deadline_at`, and durable state, count **currently overdue items**:

~~~sql
SELECT COUNT(*) AS overdue_items
FROM integration_jobs
WHERE state IN ('PENDING', 'RUNNING', 'RETRY')
  AND deadline_at < CURRENT_TIMESTAMP;
~~~

Export `integration_overdue_items{integration}` and alert when it exceeds thresholds across multiple scrapes. This tracks SLO risk directly because it captures **unfinished work**. To compute a deadline-compliance percentage over a window, build the denominator from the cohort of jobs whose **`deadline_at` has arrived**, rather than marking brand-new jobs under 5 minutes old as failures.

## 8. Alerting on Backlogs, Work Age, and Stalled Progress

### 8.1. Queue Depth Alone Is Insufficient

Compare two snapshots:

~~~text
12:00  pending = 600, oldest_age = 20 seconds
12:05  pending = 700, oldest_age = 8 minutes
12:10  pending = 850, oldest_age = 13 minutes
~~~

Rising queue depth is one signal, while **steadily climbing oldest age** proves work is sitting unserved for long periods. Conversely, 600 items arriving in a sharp burst might clear in seconds without threatening SLOs.

A rule can alert when the oldest pending item exceeds 10 minutes:

~~~yaml
groups:
  - name: integration-backlog
    rules:
      - alert: IntegrationPendingWorkTooOld
        expr: |
          (integration_oldest_pending_age_seconds > 600)
          and on (integration)
          (integration_pending_items > 0)
        for: 5m
        labels:
          severity: page
        annotations:
          summary: "Pending work too old: {{ $labels.integration }}"
          description: "Inspect outbox/job store, retries, and worker progress."

      - alert: IntegrationBacklogGrowing
        expr: |
          (delta(integration_pending_items[15m]) > 300)
          and on (integration)
          (integration_pending_items > 500)
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Backlog growing steadily: {{ $labels.integration }}"
          description: "Compare ingress rate against processing throughput."
~~~

`delta` applies only to **gauges**, never monotonic counters. Thresholds of 600 seconds, 300 items/15m, and 500 items are illustrative only. `for:` filters short bursts. If scraping fails or gauges stop updating, expressions may stop evaluating; monitor **telemetry freshness** and metric source availability.

### 8.2. Zero Progress Despite Remaining Backlog

A worker process may stay alive and emit heartbeats while failing to commit results. Track the last timestamp when **a real business operation completed**:

~~~yaml
groups:
  - name: integration-progress
    rules:
      - alert: IntegrationNoProgressWithBacklog
        expr: |
          (integration_pending_items > 0)
          and on (integration)
          (integration_oldest_pending_age_seconds > 900)
          and on (integration)
          (time() - integration_last_progress_timestamp_seconds > 900)
        for: 5m
        labels:
          severity: page
        annotations:
          summary: "Worker making no progress: {{ $labels.integration }}"
~~~

**Precondition:** `integration_last_progress_timestamp_seconds` must be initialized and updated from the **same durable state source**; if missing, `and` evaluates to empty. Handle cold-start states cleanly or pair with overdue/missing-telemetry alerts. Never update `last_progress` merely when `@Scheduled` wakes up—schedulers keep ticking even when actual work is completely deadlocked.

### 8.3. Kafka Lag, Consumer Groups, and Partitions

Inspect Kafka consumer lag per **consumer group + topic + partition**. Aggregate lag hides a single stuck partition while other partitions stay caught up. For any consumer group:

- **Lag count:** gap between committed offsets and partition head per exporter semantics; measured in offsets, not seconds.
- **Ingress rate vs. processing rate:** backlog grows when arrivals outpace completions.
- **Oldest unprocessed age:** useful when record timestamps and pending offsets are tracked; never infer time directly from offset count.
- **Last committed progress:** whether offsets/business outputs advance while the partition has data.
- **Consumer group state/rebalances:** explains transient stalls or broken partition assignments.

Use separate thresholds for real-time topics, batch topics, and low-volume topics. Partition counts, producer rates, and message sizes make a single universal lag number meaningless across integrations.

### 8.4. Outbox, DLQ, and Retry Backlogs

One flow can span **multiple chained queues**: SQL outbox, Kafka topic, retry table, dead-letter queue, and reconciliation queue. Watching only Kafka lag when the outbox relay stopped publishing shows Kafka lag near **0** while business work is completely stuck in the database.

Watch every boundary:

| Boundary | Backlog/Age to Monitor | Related Failures |
|---|---|---|
| Database outbox → broker | `PENDING` count, oldest age, last relay publish time | Broker down, retry loop, lock/lease bugs |
| Broker → consumer | Per-group/partition lag, time without progress | Rebalances, deserialization failures, uncommitted offsets |
| Consumer → partner HTTP | Retry job count, oldest retry age, 429/5xx/timeouts | Rate limits, open circuit breakers, credential errors |
| Consumer → database | In-flight, retries, DB connection pool waits | Locks, deadlocks, incompatible migrations |
| Consumer → DLQ | Total DLQ entries, unresolved items, record age | Poison messages, contract version mismatches |
| Scheduler → job store | Missed slots, overdue `READY/RUNNING` jobs | Scheduler down, stuck claim leases, multi-replica races |

Evaluate the **entire end-to-end path**, not a single infrastructure number.

## 9. SLO and Error-Budget Alerting

Static thresholds like "HTTP 5xx > 5% over 10 minutes" are easy to read yet miss real SLO impact. With a 99.5% on-time completion SLO, the **error budget** is 0.5% allowed violations over the evaluation window.

**Burn rate** compares current budget consumption speed to the sustainable rate:

\[
\text{burn rate} =
\frac{\text{observed SLO violation rate}}
     {\text{allowed SLO violation rate}}
\]

Illustrative example: a 99.5% SLO permits 0.5% failures; observing a 5% violation rate means burn rate = 10. This gauges urgency: rapid budget burn over a short window warrants immediate paging, whereas low sustained burn over hours warrants a lower-urgency ticket.

In asynchronous pipelines, counting only "terminal failures" **underestimates** SLO breaches because stuck overdue pending jobs haven't terminated yet. To implement burn-rate alerts accurately, define a **proper cohort SLI**: each operation enters the denominator once its deadline passes, evaluated as `within_deadline` or `violated`—retries and duplicates never inflate the denominator. Then layer fast/slow alert windows.

Typical multi-window alerting has two tiers:

- **Page tier:** budget burning fast across **both short and long windows**, indicating active major impact requiring immediate response.
- **Ticket/warning tier:** slower sustained burn manageable during business hours before exhausting the monthly budget.

Never deploy arbitrary burn-rate formulas to production without verifying SLI definitions, evaluation windows, and alert fatigue. Backtest on historical metrics and verify behavior under low traffic, outages, retries, and missing telemetry.

## 10. Alert Tiers and Noise Reduction

| Tier | When to Use | Examples |
|---|---|---|
| **Page / critical** | Customers face active or imminent severe impact; immediate intervention needed | Sustained deadline breaches, very old queues, zero progress, high terminal failures |
| **Warning / ticket** | Early degradation requiring monitoring or planned action | Backlog growing but not yet near deadline, rising attempt errors, small new DLQ entries |
| **Dashboard / info** | Diagnostics and trend analysis; no standalone alert needed | Occasional retries, minor p50 shifts, normal brief CPU spikes |

To keep alerts actionable:

1. **Appropriate `for` durations:** never wake on-call for spikes lasting just a couple of scrape cycles.
2. **Traffic conditions:** require minimum sample thresholds or use deadline-based checks for low-volume flows.
3. **Grouping and deduplication:** group alerts by `environment`, `integration`, and failure class rather than paging per pod.
4. **Inhibition/dependencies:** when the entire broker is down, suppress redundant downstream consumer pages while preserving business-impact visibility.
5. **Approved maintenance silences:** scope tightly with explicit end times so real new incidents aren't hidden forever.
6. **Linked runbooks:** state what the alert means, key dashboards/traces, safe recovery steps, and owning team.
7. **End-to-end delivery checks:** perfect rules are useless if Alertmanager/PagerDuty/Slack delivery fails.

Distinguish **alert resolved** from **business incident recovered**: error rates drop to zero if traffic stops completely while old jobs remain stuck. Runbooks must verify overdue job counts and real progress before closing incidents.

## 11. Investigation Runbook When an Alert Fires

A runbook should quickly answer three questions for on-call: **who is impacted, where is it stuck, and what recovery step is safe**.

### 11.1. Investigation Workflow

1. **Confirm impact:** which integration, environment, overdue operation count, impacted customers/systems, and breached SLO.
2. **Inspect trends:** terminal and attempt error charts, p95, pending counts, oldest age, and ingress/egress rates before/after recent deploys.
3. **Isolate the hop:** is SQL outbox growing, what does per-partition Kafka lag show, are consumers committing offsets, what codes is the partner HTTP returning, and are DB pools/locks anomalous?
4. **Correlate samples:** follow `traceId`, `eventId`, or `businessOperationId` through logs/traces from enqueue to final step rather than guessing from one isolated stack trace.
5. **Check recent changes:** releases, schema migrations, credentials/tokens, broker ACLs, retry/timeout configs, worker scaling, and scheduled jobs.
6. **Recover within safe boundaries:** fix credentials/routes, tune capacity, temporarily throttle ingress, restore dependencies, or replay verified idempotent work.
7. **Verify recovery:** oldest age drops, backlog drains, terminal successes climb, SLO recovers, and affected jobs reconcile cleanly.

### 11.2. Symptom Differentiation Table

| Symptom | Common Cause | Priority Checks | Controlled Mitigation |
|---|---|---|---|
| Attempt errors up, terminal errors flat | Partner 429/503; retries partly succeeding | HTTP status, retry counts, breaker state, deadlines | Backoff/jitter, cap concurrency, contact partner if prolonged |
| Pending up, oldest age up | Relay/worker slowed or stalled | Worker progress, locks, broker acks, DB queries | Restore workers/dependencies; scale after identifying bottleneck |
| Kafka lag up, outbox low | Consumers slow or failing | Group/partition lag, rebalances, deserialization, downstream DB/HTTP | Fix consumer/dependency; tune partitions/concurrency carefully |
| Kafka lag low, outbox up | Messages not publishing from DB | Relay state, retries, producer errors | Restore relay; replay with stable outbox keys |
| p95 up, queues steady | Slow processing/DB/HTTP | Per-hop spans, connection pools, locks, timeouts | Optimize bottleneck; maintain load caps |
| p95 looks good, old backlog grows | Fast jobs finish; hard jobs stall | Oldest pending items, failed keys, poison messages | Isolate poison jobs into proper quarantine/DLQ |
| Missing metrics or zero traffic | App down, exporter/scrape broken, scheduler stopped creating work | `up`, scrape targets, source heartbeats, ingest rates | Restore telemetry; verify business systems separately |
| DLQ growing steadily | Schema contract mismatch, bad data, permissions | Exception types, schema versions, masked payloads | Stop bad source, fix converters/contracts, replay safely |

### 11.3. Retries and Replays Require Idempotency

If a consumer dies after writing the DB but before committing its offset, Kafka redelivers. If an outbox relay dies after broker ack before marking `SENT`, it republishes. **Backlog alerts routinely lead to replay actions**, so runbooks must verify duplicate protection:

- Keep `eventId`/`operationId` immutable across retries; never mint fresh UUIDs for the same business intent.
- Persist processing markers in the same DB transaction as business updates using unique constraints or conditional upserts.
- For partner HTTP calls, send idempotency keys if supported; distinguish pre-send timeouts from post-processing response timeouts.
- Never purge/replay entire DLQs or uncap concurrency solely to make backlog metrics drop—doing so risks duplicate side effects, cascading load, and lost root causes.

## 12. Dashboards and Cross-Adapter Tracing

An operations dashboard organized **by integration**—not only by pod—should present:

| Panel Group | Contents |
|---|---|
| SLO health | Due operations, on-time ratio, error budget burn, terminal failures |
| Throughput | Ingress/s, completed/s, retry rate, rejection rate |
| Timing | End-to-end p50/p95/p99, HTTP/DB/Kafka hop durations, oldest pending age |
| Backlogs | Outbox pending, retry backlog, per-group/partition Kafka lag, DLQ |
| Dependencies | Partner HTTP status/timeouts, DB pool waits/locks, broker ack latency |
| Workers | In-flight, throughput, last committed progress, restarts/rebalances, lease expiries |
| Diagnostics | Recent deploys/config changes, sample traces, runbook links, active alerts |

A clean trace links milestones:

~~~text
HTTP request
  traceId = a1...
  businessOperationId = order-42
    -> DB transaction commits order + outbox(eventId=e-42)
    -> Relay sends Kafka record(key=order-42, eventId=e-42)
    -> Consumer records processing state
    -> External HTTP call / final DB commit
    -> business completion / SLO outcome
~~~

Propagate correlation IDs across message headers where appropriate and store business IDs in tables and logs, **never placing high-cardinality IDs in metric labels**. Never log tokens, credentials, emails, sensitive payloads, or PII. For distributed tracing, account for gaps when consumers process messages minutes later; use span links or business correlation IDs to stitch async stages.

## 13. Testing Alert Rules Before Production

For alerts to catch real failures, validating PromQL syntax is not enough. Test with synthetic time-series simulations or fault-injecting integration tests emitting real metrics.

### 13.1. Scenarios to Cover

| Test Case | Injected Condition | Expected Alert Behavior |
|---|---|---|
| Brief blip | HTTP 503 for a few seconds then healthy | Does not page; diagnostic data captured |
| Sustained errors | Terminal failure ratio > threshold across windows | Fires after `for` duration |
| Very low traffic | 1 of 1 request fails | Minimum-sample ratio rule stays silent; deadline alert handles separately |
| Retry eventually succeeds | 4 attempts, 3 errors, 1 success | Attempt failures rise; terminal success increments once |
| All work stalled | Zero completions, pending age climbs | Backlog/overdue alerts fire even though completed error rate is 0 |
| Big burst cleared fast | Pending spikes for 1–2 minutes then drains | `for` window prevents false pages |
| Poison message | One schema-invalid event repeating | Bounded retries, DLQ rises, triage signal emitted |
| Stuck Kafka partition | One partition fails to commit while others progress | Partitioned dashboard exposes the bottleneck |
| Broken scrape/metrics | Exporter disappears or gauge freezes | Separate `up`/metric-freshness alert fires |
| Downstream recovery | Partner HTTP recovers, workers catch up | Errors drop, oldest age and backlog drain before resolving incident |
| Duplicate delivery | Replays with same event ID | Terminal completion counter does not double-count; data stays intact |
| Rolling deployment | Mixed versions running during deploy | Stable labels, alerts do not reset unexpectedly, runbooks track releases |

With Prometheus, run **unit tests for alert rules** using `promtool test rules` against mock time series, paired with real Micrometer exporter tests. This lesson outlines the testing approach; do not assume the illustrative YAML rules above are active in any specific cluster.

### 13.2. `for` Semantics, Missing Data, and Scrape Intervals

`for: 10m` means the expression must remain firing across evaluation ticks for 10 minutes; it **cannot** invent metrics if the exporter goes silent. When an integration generates no work, `rate` can return no samples. Distinguish:

- **Zero:** metric is scraped and genuinely equals 0.
- **No data:** metric missing—uninstrumented, target down, or zero samples in window.
- **Stale:** metric exists yet carries an old snapshot because the sampler stalled while the exporter lived.

Monitor scrape target `up`, backlog snapshot timestamps, and job-creation heartbeats for continuous flows. An alert relying solely on `rate(success)` stays silent when traffic vanishes, masking broken schedulers that stopped emitting work.

## 14. Illustrative Threshold Set for Outbox → Kafka → Consumer

Suppose a flow targets 5-minute completion, receives steady peak work, and has active on-call support:

| Signal | Illustrative Starting Threshold | Tier | Post-Fire Verification |
|---|---|---|---|
| Terminal failure ratio | > 5% over 10m, ≥50 completed, sustained 5m | Page | Failures by integration, dependency, and overdue count |
| End-to-end p95 success | > 120s over 10m with sufficient samples, sustained 10m | Warning | Queue wait vs. processing and pending backlog |
| Oldest pending | > 600s sustained 5m | Page | Oldest slot/event; is relay/consumer making progress? |
| Backlog growing | +300 items/15m and depth > 500, sustained 10m | Warning | Ingress vs. throughput, scaling/partner limits |
| No progress | Pending > 0, oldest > 900s, zero successes > 900s | Page | Worker state, DB locks, retries, poison messages |
| DLQ newly added | New DLQ arrivals within 15m | Ticket/Warning | Schema contracts, deserialization errors, poison events |
| Telemetry missing | Target down or snapshot age past limit | Infra alert | Scraping, collectors, and business system health |

**Never copy these numbers verbatim.** With a 5-minute SLO, waiting until oldest pending reaches 10 minutes to page is already too late; calibrate thresholds from **remaining intervention window**, dependency recovery time, and error budgets. Use p95 latency as an early warning ahead of deadline breaches, while overdue counts and oldest age confirm actual customer impact.

## 15. Common Operational Mistakes

1. **"Health UP means integrations are healthy."** Apps can stay UP while consumers stall, schedulers stop, or outboxes freeze.
2. **"Alert only on HTTP 5xx."** Many flows return 202 and fail asynchronously; HTTP status misses final outcomes.
3. **"Kafka lag = 0 means no backlog."** Work can stall upstream in the DB outbox or downstream in retry tables.
4. **"Low p95 proves every request finishes on time."** Completion percentiles omit pending items and stuck partitions.
5. **"100% error rate must always page."** A single failed request on low traffic needs different handling than 10,000 failures.
6. **"Adding `for: 5m` fixes all noisy alerts."** Missing metrics or zero traffic can silence rules during real outages.
7. **"A counter incremented per retry equals failed customers."** Attempts and business operations are different counting units.
8. **"Increasing concurrency always clears backlogs."** Under downstream 429s, DB locks, or broker overload, adding workers worsens outages.
9. **"Replaying to clear a backlog is harmless."** HTTP, DB, and Kafka create duplicate side effects without idempotency.
10. **"Alert stopped firing means the incident is over."** Verify overdue jobs have recovered or reconciled first.

## 16. Self-Check Questions

1. An HTTP endpoint returns 202 fast, yet 20 minutes later consumers haven't updated orders: which signals catch this accurately?
2. Why can attempt error rates and terminal error rates diverge sharply? Which decisions does each drive?
3. Pending count rises from 600 to 900 while oldest age stays under 10 seconds—do you page immediately? What extra facts do you check?
4. If `histogram_quantile` looks healthy while one Kafka partition is stuck, what metrics and traces are missing?
5. With `for: 10m` in Prometheus, what happens if the exporter crashes midway through a breach?
6. How do you compute accurate deadline compliance for async jobs without ignoring still-pending jobs?
7. When an outbox relay publishes to Kafka and crashes before marking complete, what deduplication guarantees must replay enforce?
8. Should `eventId` live in metric labels or logs/traces? Why?
9. Why must Kafka consumer lag thresholds factor in partition count, ingress rate, and business deadlines?
10. What must a solid runbook verify before closing an incident once the broker comes back online?

**Technical conclusion:** Effective alerting for Spring Boot Integration must detect **sustained impact on business progress**, not merely log exceptions. Combining **terminal failures**, **end-to-end latency**, **oldest pending age**, **backlog growth**, and **last committed progress** catches both overt crashes and silent stalls. Rules require accurate counting semantics, proper time windows, noise controls, reliable telemetry freshness, safe recovery runbooks, and testing across real failure and replay scenarios.

### References

- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Actuator, Micrometer, meter registries, and exporters.
- [Spring Boot — Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): health/metrics endpoints and exposure config.
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): measuring durations and histograms.
- [Prometheus — Alerting Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/): expressions and `for`.
- [Prometheus — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/): `histogram_quantile`, buckets, and histogram aggregation.
- [Google SRE Workbook — Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/): burn rates and multi-window alerting.
- [Apache Kafka — Monitoring](https://kafka.apache.org/documentation/#monitoring): Kafka consumer and producer metrics.
