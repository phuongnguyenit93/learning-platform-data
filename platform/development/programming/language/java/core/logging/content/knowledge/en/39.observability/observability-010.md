# SLOs for Log Pipelines in Java: Measuring Reliability from Event to Storage

## 1. What Is a Log Pipeline SLO and Why Do We Need It?

A **Service Level Objective (SLO)** is a quantitative target for the quality of a service over a defined time window. For a logging pipeline, an SLO helps answer a practical question: **“Among the log events the system commits to collecting, how many reach the required destination, on time, and with enough information to be usable?”**

A Java statement like `logger.info("Order {}", orderId)` completing **does not mean** the log has been written to a file, sent by an agent, received by a collector, indexed for querying, or durably stored. When using an asynchronous appender, there is a queue between the application thread and the sink. When the collector is slow or disconnected, operators may still see the application serving requests successfully while the information needed for investigation has been lost.

Example pipeline:

```text
Java service -> SLF4J/JUL -> logger level/filter -> appender
                                              |
                                              v
                                  async queue / stdout / file
                                              |
                                              v
                                      log agent / forwarder
                                              |
                                              v
                                     transport + retry
                                              |
                                              v
                                       collector/ingest
                                              |
                                              v
                                  durable storage + index
                                              |
                                              v
                                     dashboard / alert
```

Every stage can become a point of log loss or delay:

- Events are filtered or sampled right inside the JVM.
- The async queue fills up and drops events according to its policy.
- Writing to stdout/file fails, or the volume/pipe is congested.
- The agent loses connectivity, builds a backlog, or runs out of disk spool space.
- The collector returns 429/5xx or acknowledges receipt while indexing lags.
- Events are stored but cannot be queried due to schema/parser issues, retention, access permissions, or an incorrect time range.

**An SLO is not an application CPU/heap dashboard.** It measures a useful outcome of the logging path, with a predefined target group, start point, end point, deadline, and counting method.

This article distinguishes **SLI**, **SLO**, **SLA**, and **error budget**, explains how to measure end-to-end, and shows how to implement verification in Java 17. The percentages and thresholds below are **illustrative values for learning and design**, not mandatory defaults for every system.

## 2. SLI, SLO, SLA, and Error Budget

| Term | Meaning | Example for Logging |
| --- | --- | --- |
| **SLI (Service Level Indicator)** | Ratio/metric measuring actual quality | Percentage of events queryable within 30 seconds |
| **SLO (Service Level Objective)** | Target set on an SLI over a measurement window | At least 99.95% of critical events meet the deadline over 30 days |
| **SLA (Service Level Agreement)** | Commitment/contract with consequences when violated | Legal/commercial commitment if applicable, not synonymous with internal SLO |
| **Error budget** | Allowed proportion/number of events that may miss the SLO | At 99.95%, an error budget of 0.05% of eligible samples |
| **Burn rate** | Rate of budget consumption relative to the allowed rate | A 2x burn rate means errors are arriving at twice the budget rate as defined |

A good SLO does not just state `99.9% uptime`; it specifies **what counts as a successful delivery**. An agent that is “UP” but unable to ship logs can still render the pipeline useless.

**Distinguish component availability from pipeline outcome:** A Kafka broker, Logback appender, Fluent Bit/Vector, collector, and dashboard may all be individually “healthy” while events are being discarded between stages. An end-to-end SLI must include at least one method that observes the final outcome at the destination.

## 3. Choosing What to Measure: Which Events Are Truly “Eligible”?

Not every `TRACE`/`DEBUG` log should be expected to be stored 100%. Some applications intentionally sample or drop low-priority logs to save resources. Therefore, define **eligible events** before calculating an SLI.

Example classes:

| Class | Typical Policy | SLO Suggestion |
| --- | --- | --- |
| **Mandatory audit** | Never intentionally discarded; has storage/reconciliation contract | Dedicated, very strict SLO with durability verification |
| **Critical security events** | Needed for investigation; preserve event ID/actor/action safely | Dedicated completeness and latency targets |
| **Critical operational logs** | `ERROR`, critical service state events | End-to-end and freshness targets |
| **Standard INFO** | May be rate-limited by design | SLO over a defined sample |
| **Sampled DEBUG/TRACE** | Only a portion of eligible events proceed | Do not count intentionally sampled-out events as “lost” |

Example contract:

> All events in the `critical` class **accepted by the application for pipeline delivery per policy** must have a valid record and be queryable within at most 30 seconds, at a rate of at least 99.95% over a 30-day window.

However, the example above carries a risk: if the logger/filter itself is disabled before the “accepted” marker, the denominator may **omit all events lost right at the source**. For critical audit logs, count **business events that must emit logs from a trusted data source**, such as a committed event/outbox, not just from an appender counter.

### A Verifiable Eligibility Definition

```text
Eligible(event) =
    belongs to a group required to be retained by policy
    AND the defined business emission point has occurred
    AND does not fall under an approved exemption
```

All exemptions such as maintenance, sampling, or test data must be clearly described, measurable, and pre-approved. **Do not exclude lost events from the denominator simply because they were “not seen at the collector”**; doing so makes the SLI look artificially good.

### Tracking Policy Changes

When deploying new filters, adjusting log levels, changing sampling, or altering retention, the eligible set may change. Record the policy version and effective date so SLIs can be compared across periods. Do not directly compare this month with last month if the measurement sample changed without explanation in the report.

## 4. Defining Start Point, End Point, and Deadline

On-time log delivery rate is only meaningful when **where measurement starts and where delivery ends** are clearly defined.

An example:

- **`t0`**: timestamp when the source event is created/committed per contract.
- **`t1`**: timestamp when the collector writes the event to queryable storage and acknowledges per contract.
- **Deadline**: `t1 - t0 <= 30 seconds`.
- **Good event**: matching ID, matching class, valid schema, queryable before the deadline.
- **Bad event**: no record by the deadline, record arrives late, or record fails agreed validity conditions.

If you only measure when the agent calls `send()`, the event may not have reached the collector yet. If you only measure when the collector returns HTTP 200, indexing or durable storage may still happen afterward. If you only measure when a dashboard renders it, the result is affected by the query engine. **Choose an end milestone that directly matches what users or operators need.**

### Table of Different “End Points”

| Destination Milestone | What Can Be Asserted | What Is Not Yet Guaranteed |
| --- | --- | --- |
| Java logger call returned | Logging API call completed | Event was not filtered, reached file or collector |
| Appender accepted | Appender accepted the event | May only reside in RAM |
| Async queue enqueued | Worker can consume it later | Survives a JVM crash |
| Agent sent bytes | Transmission attempted | Collector stored or indexed it |
| Collector ack | Protocol acknowledgment scope reached | Whether that ack guarantees durability or queryability |
| Durable/indexed/queryable | Event exists per storage/query contract | Will remain forever after retention expires |

For audit events, if the requirement is “evidence must survive a crash,” an in-memory queue acceptance ACK is far too weak a milestone. If the requirement is “visible on the dashboard within 30 seconds,” an `appender_writes_total` metric is also insufficient.

### Watch Out for Time

To compare timestamps across two hosts, you need clock synchronization and an understanding of clock skew. A `t1 < t0` caused by clock skew **must not be counted as negative latency (i.e., ultra-fast)**. You can classify it as `INVALID_TIMESTAMP` and report measurement quality; in a strict SLI, treat it as non-compliant until verified otherwise. Within the same process, use a monotonic clock to measure elapsed time when possible; for multi-host end-to-end measurement, use reliable timestamps with a shared definition.

## 5. SLIs to Consider for a Log Pipeline

Do not lump every requirement into a vague “logging healthy” ratio. You can start with the following SLIs.

### 5.1. Completeness / Delivery Success

```text
delivery_success_rate =
    number of eligible events validly present at destination as required
    --------------------------------------------------------------------
                        total eligible events
```

Choose the **outcome milestone**: stored, indexed, or queryable. If the target does not require a deadline, this is the final rate within a specified finalization/reconciliation bound. When delayed events have not yet reached the finalization point, do not keep them “pending” indefinitely to flatter the denominator.

### 5.2. Timely Delivery / Freshness

```text
on_time_delivery_rate =
    number of valid eligible events reaching destination before deadline
    --------------------------------------------------------------------
                        total eligible events
```

This is usually the most practical SLI: it penalizes both **lost logs** and **logs arriving too late**. If you only compute p99 latency over delivered events, 20% completely lost events will never appear in the percentile—because lost events have no observable latency.

You can set a separate SLO for `p99 ingest latency` as a diagnostic signal, but **do not replace the completeness/on-time SLO** with a percentile computed only over successful events.

### 5.3. Parseability / Schema Correctness

```text
parse_success_rate =
    number of events reaching sink and parsed with required schema
    ---------------------------------------------------------------
                  total inspected events reaching sink
```

This ratio indicates the format quality of events that arrived; **it cannot measure events that never arrived at all**. If the product goal is “99.95% of eligible events are queryable by `reasonCode`,” include both lost events and schema failures in the end-to-end numerator/denominator rather than using `parse_success_rate` alone to claim compliance.

### 5.4. Duplicate Rate / Integrity

```text
duplicate_delivery_rate =
    number of extra duplicate copies of identified event IDs
    --------------------------------------------------------
                  total received event copies
```

Duplicate rate can be measured separately. Retries with at-least-once delivery may produce valid duplicates per delivery semantics; the system should deduplicate at query time or at the consumer, and understand that one `eventId` may appear multiple times. **Do not treat each duplicate as a new source event** when computing completeness. At the same time, do not ignore duplicates if they inflate costs or cause audit results to double-count.

### 5.5. End-to-End Canary Success

Emit a **synthetic event with a unique ID** from a chosen source point, then verify query/ack at the end of the pipeline. For example, a canary every minute with a 30-second timeout:

```text
canary_success_rate =
    number of canaries found within deadline
    ----------------------------------------
             total canaries emitted
```

Canaries are very useful for detecting outages **even when real traffic is low**, but they only reflect the exact path the canary takes. If the canary originates from the agent instead of the JVM, it will not detect a broken application logger/filter/async queue. If the canary is prioritized differently from real events, it may look healthy while real data is being dropped. **A canary is a complementary SLI, not sole proof of full log completeness.**

## 6. Example SLOs by Log Group

Suppose a company defines experimental targets as follows:

| Group | SLI | Illustrative Target | Window |
| --- | --- | --- | --- |
| Critical operational logs | Valid event, queryable within 30 seconds | ≥ 99.95% | Rolling 30 days |
| Security events | Schema-valid event, queryable within 60 seconds | ≥ 99.99% | Rolling 30 days |
| Log pipeline canary | Canary from JVM queryable within 30 seconds | ≥ 99.90% | Rolling 7 days |
| General INFO | Policy-retained event found within 2 minutes | ≥ 99.0% | Rolling 30 days |

**These are not default recommended targets.** Targets must be based on criticality, investigation needs, retention obligations, load, traffic volume, cost, infrastructure design, and measurability. Mandatory audit events may require **stronger functional guarantees than a percentage SLO**, such as transactions/outbox that do not tolerate loss even with low probability.

An SLO can include **multiple simultaneous conditions**:

- `eventId` is not semantically duplicated.
- Queryable within the specified time.
- Critical fields `service`, `action`, `outcome`, and `reasonCode` are not missing.
- No secrets appear in broadly accessible data (security requirements must be checked separately, not collapsed into a single ratio).

Avoid averaging across multiple classes and masking failures in a small but critical class. For example, 1 million well-delivered INFO logs do not compensate for 10 lost audit events.

## 7. Error Budget: Calculate It Properly, Not Just on Paper

Suppose the SLO is **99.95% on-time events** over the chosen window.

```text
error_budget_fraction = 1 - 0.9995 = 0.0005 = 0.05%
```

If the window has **10,000 eligible events** that have had enough time to be classified:

- At most **5 non-compliant events** correspond to 0.05%.
- If **9,990 events are on time**, **7 events arrive late**, and **3 events are not found**, total non-compliant events are **10**.
- The on-time SLI is `9990 / 10000 = 99.90%`.
- The allowed error budget is 5 events, but 10 failed → **200% of the budget has been consumed**, exceeding the target.
- The burn rate over the observed window is `(10/10000) / (1-0.9995) = 2x`.

When volume is not evenly divisible or the sample is too small, “allowed error count” requires clear rounding rules and ratio evaluation policies. **Prefer evaluating the SLI ratio directly against the target** rather than applying an unexplained `floor` that alters SLO semantics. A window with 0 eligible events must be classified as **no data**, not automatically reported as 100% success.

### Burn Rate Is Not a Fixed Number of Remaining Hours

`burn_rate = observed_bad_fraction / allowed_bad_fraction`.

- `burn=1x`: error rate equals the allowed budget rate in the measured window.
- `burn=2x`: error rate is twice the allowed rate.
- `burn≫1x`: errors are consuming budget rapidly, potentially requiring urgent action if sample size is sufficient and impact is high.

Burn rate depends on the **measurement window**. A 5-minute window with 1 error out of 10 events produces a high ratio from a tiny sample; evaluate it alongside longer windows, volume, and log group significance. Do not infer “X hours remaining” without knowing budget history, traffic patterns, and window duration.

## 8. End-to-End Measurement Cannot Count Only at the Collector

A common logical flaw:

```text
collector_received_total / collector_received_total = 100%
```

or using “all logs seen by the collector” as the denominator. This approach **cannot detect events lost before the collector**, because both the numerator and denominator miss them.

A viable measurement architecture requires an **independent data source**:

```text
Business source / outbox
     |
     +-- source event ID + expected timestamp --> SLI reconciler
     |
     v
Application logger / agent / collector
                                    |
                                    v
                         indexed event IDs
                                    |
                                    v
                    reconciliation + deadline
                                    |
                                    v
                  metrics / SLO / alert
```

For events with IDs and full retention, the reconciler checks whether each ID committed at the source exists validly at the sink and arrived by the deadline. If an event is lost before the appender, the reconciler still knows it should have appeared.

**Limitation:** not every debug log has a durable source event. For log classes that cannot be reconciled per event, you can combine end-to-end canaries, emitter-side counters, agent and sink counters, controlled sampling, and operational indicators. In that case, explicitly document **SLI coverage** and do not claim absolute loss measurement.

### Event ID Sources and Independence

- `eventId` must be stable and unique enough to join source and sink; if retries resend the same event, preserve the ID for deduplication.
- A business message's `messageId` is not necessarily the `eventId` of each log record; one message may emit multiple logs.
- Source milestones can be drawn from an audit outbox or transaction commit rather than only in-JVM metrics, since a JVM crash can also wipe out those metrics.
- The SLI reconciler needs reliable state/timestamps and must report itself if it breaks.
- If the source event count comes from the very logging pipeline being measured, a full pipeline outage can make the source metric disappear too. Monitor it via a relatively independent metrics/health path.

## 9. Cohorts, Deadlines, and Classifying Unfinished Events

This is where time-window calculations commonly go wrong.

Suppose the deadline is 30 seconds. If you measure at exactly 10:00:05, an event created at 10:00:00 that is not yet visible at the sink is **not overdue yet**. Treating it as lost immediately is wrong; dropping it from the denominator indefinitely is also wrong.

One design approach:

1. An eligible event has an `eventId` and `t0`.
2. At `t0 + 30s`, the reconciler concludes **ON_TIME** if a valid destination outcome was observed before or at the deadline.
3. If not, after the deadline it is counted as **BAD / DEADLINE_MISSED** for the SLO, even if the event arrives later.
4. Afterward, `LATE` or `MISSING` details can be added to eventual-delivery reports; **do not erase the deadline violation** when an event arrives late.
5. When reconciliation itself is not functioning, mark **measurement unavailable** rather than reporting green.

For aggregation, you can use **emission-time cohorts** (events whose `t0` falls in the same source window, once the window has “matured” past the deadline) or **finalization-time windows** (all events whose final state was finalized within the window). The two can differ at window boundaries. Choose **one** and apply it consistently across SLOs, dashboards, and alerts.

### Avoid Mixing Cohorts When Dividing Two Independent Counters

Do not arbitrarily compute:

```text
events_arrived_in_last_5m / events_created_in_last_5m
```

because logs created near the end of a window may arrive at the start of the next window, while logs created before the window may just be arriving now. The ratio can temporarily exceed 100% or appear artificially low. Instead, reconcile by matching cohort/event ID, or count a **finalized outcome** counter at a consistent finalization milestone.

## 10. Standalone Java 17: Computing SLI, Error Budget, and Burn Rate

The following example uses **pure Java 17, with no external broker or logger dependencies**. It generates a set of 10,000 simulated events that have had enough time to be finalized, where:

- 9,990 events are persisted after 10 seconds (within the 30-second deadline).
- 7 events are persisted after 45 seconds (arriving late).
- 3 events have no persistence evidence (missing).
- No out-of-order timestamps occur.

Each record has an ID, a source timestamp, and a persisted timestamp or `null`. The classification logic **does not treat missing-event latency as 0**, and does not treat negative latency as good.

### 10.1. File `LogPipelineSloDemo.java`

```java
import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.util.Locale;

public class LogPipelineSloDemo {
    enum Result {
        ON_TIME, LATE, MISSING, INVALID_TIMESTAMP
    }

    record Event(
            String eventId,
            Instant createdAt,
            Instant persistedAt
    ) {}

    static Result classify(Event event, Duration deadline) {
        if (event.persistedAt() == null) {
            return Result.MISSING;
        }

        Duration elapsed = Duration.between(
                event.createdAt(), event.persistedAt());

        if (elapsed.isNegative()) {
            return Result.INVALID_TIMESTAMP;
        }

        if (elapsed.compareTo(deadline) <= 0) {
            return Result.ON_TIME;
        }

        return Result.LATE;
    }

    public static void main(String[] args) {
        int eligible = 10_000;
        int onTime = 0;
        int late = 0;
        int missing = 0;
        int invalid = 0;

        Instant produced =
                Instant.parse("2026-01-01T10:00:00Z");
        Duration deadline = Duration.ofSeconds(30);

        for (int i = 0; i < eligible; i++) {
            Instant persisted;

            if (i < 9_990) {
                persisted = produced.plusSeconds(10);
            } else if (i < 9_997) {
                persisted = produced.plusSeconds(45);
            } else {
                persisted = null;
            }

            Event event = new Event(
                    "event-" + i, produced, persisted);

            switch (classify(event, deadline)) {
                case ON_TIME -> onTime++;
                case LATE -> late++;
                case MISSING -> missing++;
                case INVALID_TIMESTAMP -> invalid++;
            }
        }

        int bad = eligible - onTime;
        BigDecimal target = new BigDecimal("0.9995");
        BigDecimal allowedFraction =
                BigDecimal.ONE.subtract(target);

        long allowedBad = BigDecimal.valueOf(eligible)
                .multiply(allowedFraction)
                .longValueExact();

        double achievedRate = 100.0 * onTime / eligible;
        double budgetUsed = 100.0 * bad / allowedBad;
        double burnRate =
                ((double) bad / eligible)
                    / allowedFraction.doubleValue();

        System.out.println("eligible=" + eligible);
        System.out.println("onTime=" + onTime);
        System.out.println("late=" + late);
        System.out.println("missing=" + missing);
        System.out.println("invalidTimestamp=" + invalid);
        System.out.printf(
                Locale.ROOT,
                "onTimeRate=%.3f%%%n", achievedRate);
        System.out.printf(
                Locale.ROOT,
                "target=%.3f%%%n", target.doubleValue() * 100.0);
        System.out.println("allowedBad=" + allowedBad);
        System.out.println("observedBad=" + bad);
        System.out.printf(
                Locale.ROOT,
                "budgetUsed=%.1f%%%n", budgetUsed);
        System.out.printf(
                Locale.ROOT,
                "burnRate=%.2fx%n", burnRate);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac LogPipelineSloDemo.java
java LogPipelineSloDemo
```

**Deterministic stdout of the program:**

```text
eligible=10000
onTime=9990
late=7
missing=3
invalidTimestamp=0
onTimeRate=99.900%
target=99.950%
allowedBad=5
observedBad=10
budgetUsed=200.0%
burnRate=2.00x
```

### 10.2. Interpretation

- `ON_TIME` when the persisted timestamp is non-negative and **≤30 seconds** after the source timestamp.
- `LATE` even if the event eventually arrives: it violated the on-time SLO.
- `MISSING` only because the model assumes **the window has lasted long enough to finalize** and no persistence evidence was found; in a real system, a responsible reconciler/timeout is required.
- `INVALID_TIMESTAMP` is counted separately when destination time precedes source time; it is not added to good events. Clock skew or corrupted data must be investigated.
- `allowedBad=5` is computed with `BigDecimal("0.9995")` to avoid binary floating-point inaccuracy in the illustrative integer calculation.
- `budgetUsed=200%` reflects 10 bad events against an allowed budget of 5; `burnRate=2x` reflects an error rate twice the allowed rate.

**Demo limitations:** all events are generated in memory, timestamps are fixed, there is no collector, no real network observation, no duplicate handling, and persisted results are fabricated in code. This is a calculator for understanding the formulas, **not a production end-to-end measurement system**. For different windows, non-integer targets, or `allowedBad=0`, use a direct SLI evaluation policy and safe division; do not blindly copy the demo's `budgetUsed` into every scenario.

### 10.3. Adapting the Example to a Real Application

Replace the synthetic generator with:
- an `eventId`/`t0` source from an audit outbox, event emitter, or canary;
- a sink lookup confirming the ID in storage/query;
- a classifier triggered when the deadline expires;
- counters/metrics emitted only upon finalization, with replay/deduplication support for results.

Never let a reconciler failure be interpreted as “zero bad events.” Instrument **unclassified event count, reconciler lag, and disconnected sources** as well.

## 11. Designing Metrics and Using Prometheus/PromQL

A metric set might include:

| Illustrative Metric | Role | Notes |
| --- | --- | --- |
| `log_eligible_events_total` | Number of eligible source events | Needs a source close to the business event, not just the collector |
| `log_delivery_finalized_total{result}` | Number of events classified when deadline matures | `result` values are **mutually exclusive** and share the same denominator |
| `log_delivery_latency_seconds` | Latency of received events | Diagnostic histogram; does not replace loss SLI |
| `log_pipeline_dropped_total{stage}` | Drops detected at JVM/agent/sink | May not cover silent loss |
| `log_pipeline_queue_depth` | Async appender/agent backlog | Gauge, not a delivery rate |
| `log_pipeline_spool_bytes` | Disk spool used | Alert when nearing capacity |
| `log_pipeline_retry_total` | Transport retries | Does not equal unique event count |
| `log_pipeline_last_delivery_timestamp_seconds` | Most recent success timestamp | Detects stalled pipeline during normal traffic |
| `log_pipeline_canary_total{result}` | Canary good/bad by probe ID | Must verify from source to storage |
| `log_sli_reconciler_lag_seconds` | Reconciler finalization lag | Detects broken measurement system |

The metric names above are **suggested names**, not built-in defaults of JUL, Logback, agents, or collectors. Instrumentation techniques depend on your stack.

**Important:** `log_delivery_finalized_total` must be incremented **only once per eligible event** when finalization occurs. Labels `result="on_time"`, `result="late"`, `result="missing"`, and `result="invalid_timestamp"` must never double-count; if an event arrives late after already being marked missed, track late arrivals with a separate metric or supplementary state that does not increment the finalized denominator a second time.

### PromQL Examples

Assuming the counter is accurately instrumented for events **finalized within the window**:

```promql
sum(increase(log_delivery_finalized_total{
  class="critical",result="on_time"
}[1h]))
/
sum(increase(log_delivery_finalized_total{
  class="critical"
}[1h]))
```

This illustrative query calculates the ratio of events **finalized within one hour**. It is **not equivalent** to an SLI for the cohort “events created within one hour” if deadlines and late classifications fall in a different window; keep the definition consistent in your SLO. If the denominator is 0 or the metric has no data, report no-data/unknown status rather than plotting 100%.

Corresponding burn rate when the target is `0.9995`:

```promql
(
  1 -
  (
    sum(increase(log_delivery_finalized_total{
      class="critical",result="on_time"
    }[1h]))
    /
    sum(increase(log_delivery_finalized_total{
      class="critical"
    }[1h]))
  )
) / (1 - 0.9995)
```

**Warning on measurement independence:** the query only reflects the true SLO when the reconciler also classifies **events lost before the collector**. A counter incremented solely from events seen at the collector will undercount failures. Add checks for volume, `reconciler lag`, and source health.

### Avoiding High Cardinality

Metric labels should use bounded sets such as `service`, `environment`, `class`, `result`, and `stage`. **Do not use `eventId`, `requestId`, `userId`, `messageId`, or raw exception strings as labels**. Detailed IDs belong in an event store or reconciliation DB, not as separate time series.

## 12. End-to-End Canaries and Sink Presence Checks

A **synthetic canary** is a test event containing a non-sensitive ID, sent periodically through the exact application path being monitored.

Conceptual workflow:

1. A scheduler emits a canary through the same logger/appender/profile as real `critical` events, or from a representative service.
2. Record `canaryId`, emission timestamp, and target storage class.
3. An independent monitoring system queries the collector/index by `canaryId`, within the deadline and with proper read permissions.
4. Mark `ON_TIME` only if the matching record with valid fields/schema is found before the deadline.
5. If not found, alert on the logging path; continue checking for late arrival to distinguish latency from loss.
6. Alerting must still work when the main collector/logging system is down—for example, metrics/alerting hosted in a separate failure domain.

Example test event:

```json
{
  "eventType": "LOG_PIPELINE_CANARY",
  "canaryId": "canary-test-0007",
  "service": "order-service",
  "class": "critical",
  "schemaVersion": 1
}
```

Do not put real secrets, tokens, or user data into canaries. If the canary does not share the same load/format characteristics as real events, it may travel through a different path. Supplement it with **checks on real traffic** when completeness is required.

### How to Prevent Canaries from Producing False Results

- Do not emit the canary directly into the collector and claim the Java application was tested; the emission point must match the SLO scope.
- Do not check only for HTTP 200 on send; verify the storage/query milestone per contract.
- Do not let canaries bypass a filter that discards real events while the dashboard stays green.
- Do not use an overly narrow current-time query window that hides events affected by time skew; prefer unique ID lookup.
- When the collector is down, the canary probe may also fail to read; that is a measurement-path failure/unknown, not a pass.
- Canary data must be identifiable and bounded in retention/volume to avoid skewing audit reports or ingest costs.

## 13. How to Build a Completeness Reconciler

For critical events with a durable `eventId`, reconciliation is more reliable than checking each component's health alone.

A conceptual table:

| `eventId` | `t0` | `tPersisted` | Conclusion at Deadline | Eventual Outcome |
| --- | --- | --- | --- | --- |
| ev-1 | 10:00:00 | 10:00:05 | ON_TIME | DELIVERED |
| ev-2 | 10:00:00 | 10:00:42 | MISSED_DEADLINE | LATE |
| ev-3 | 10:00:00 | Not yet | MISSED_DEADLINE | MISSING |
| ev-4 | 10:00:00 | 09:59:59 | INVALID_TIMESTAMP | CLOCK_SKEW/INVESTIGATE |

A reconciliation pipeline can:

- Read the source outbox/event table using a reliable checkpoint, recording watermarks and event IDs.
- Query the sink by batched IDs or query the event database rather than issuing one network call per ID at high volume.
- Lock/mark state once when the deadline expires; prevent two workers from finalizing the same event.
- Persist `state` and `finalizedAt` so restarts/replays do not double-increment `log_delivery_finalized_total`.
- Record late arrivals after a deadline miss, but **do not rewrite past violation history** in SLO reports.
- Track data gaps, clock skew, and the backlog of the reconciler itself.

**Guard against measurement data bias:** If the source database is missing events, you cannot assume every business action was captured. If the sink index is purged by retention before reconciliation runs, conclusions must account for the retention contract. If event IDs collide, joins may report false success.

### When Is Absolute Measurement Impossible?

For ad hoc text logs without a source event ID, without an outbox, and with a logger that can be disabled, it is very hard to measure “the exact ratio of every log line that should have existed.” In that case, **do not set a fake completeness SLO with two decimal places of precision**. Choose measurable SLIs (canaries, rate-limit/drop metrics, queue health, sampling coverage) or add instrumentation to move toward true end-to-end measurement.

## 14. Alerting on Error Budget and Multi-Window Burn Rate

SLOs help separate alerts requiring immediate action from trend warnings.

Implementation examples:

- **Fast burn:** errors spike across both short and corresponding longer windows; requires immediate incident triage.
- **Slow burn:** mild but sustained violation rate; create a ticket/prioritize remediation before the budget runs out.
- **No data:** source traffic disappears or the reconciler breaks; never treat as healthy.
- **Silent loss:** canaries stop arriving while application queues/CPU look normal; inspect end-to-end milestones.

### Why Use Multiple Windows?

A 5-minute window reacts fast but is noisy at low volume. A 1-hour window is steadier but slower to detect. You can require conditions on **both 5 minutes and 1 hour** for fast burn, plus a **6-hour and 24-hour** pair for slow burn. Specific burn thresholds must be calibrated to the target, budget period, volume, and alert fatigue; **there is no single number that fits every system**.

An implementation policy might state:

```text
PAGE: both 5m and 1h exceed calibrated fast-burn thresholds,
      with a minimum number of eligible events for a reliable signal.

TICKET: 6h and 24h exceed calibrated slow-burn thresholds.

PAGE/DASHBOARD UNAVAILABLE:
      source/reconciler/canary no-data exceeds threshold
      or measurement component reports an independent error.
```

Not every budget burn requires paging. If the event class is mandatory audit, even a single lost event may require policy-driven action; if traffic is low and a few logs arrived late due to valid maintenance, handle it under the approved exemption scope rather than artificially turning metrics green after an incident.

## 15. Impact of AsyncAppender, Buffers, and Backpressure on SLOs

With Logback `AsyncAppender`, producers enqueue events and a worker thread sends them to the target appender. Depending on configuration and load:

- `queueSize` bounds the in-RAM queue.
- `discardingThreshold` can cause lower-priority log levels to be dropped as the queue nears capacity, unless the policy is changed.
- `neverBlock=true` avoids blocking producers when enqueueing fails, but may drop events.
- `neverBlock=false` can block producers when the queue is full, increasing business request latency.
- `maxFlushTime` affects shutdown wait time, without guaranteeing that events reached the final collector.

These options are specific to **Logback AsyncAppender**; do not copy these names to every backend. For Log4j2 AsyncLogger, JUL async bridges, or collector agents, check the actual implementation and version behavior.

**SLOs must measure from the eligible source point**, not from “events that passed through the AsyncAppender queue.” If an event is dropped in the async queue and the source committed to storing it, that is an SLO violation. If sampling/dropping is a documented policy for the DEBUG class, those events may be excluded from the eligible set; never silently alter the critical class policy under overload.

### Bounded Buffers Always Need a Full-Queue Plan

| Handling Strategy | Trade-off | Impact to Measure |
| --- | --- | --- |
| Block producer | May prevent short-term drops, increases latency | p95/p99 request latency, block duration |
| Drop low-priority logs | Preserves business throughput | Drop count by class, risk of losing signal |
| Disk spool | Extends outage tolerance | Spool size, replay delay, quota |
| Retry with backoff | Can recover transient transport issues | Oldest backlog age, retry success |
| Secondary sink | Reduces single-destination dependency | Duplicates, shared failure domain, access control |

An in-RAM queue is **not durable across a process crash**. Disk spooling can survive longer outages, but still faces quota exhaustion, disk loss, or crashes before fsync. An SLO must not treat “the queue is currently empty” as proof that records are safely in required storage.

## 16. SLOs When Logging via Files, Stdout, and Collectors

Containerized Java applications commonly write to stdout/stderr, which a platform log agent collects. This simplifies application code, but does not mean end-to-end delivery is guaranteed.

**Stdout path:**
- `println` or ConsoleAppender returning does not prove the central system indexed the event.
- The runtime logging driver/agent can lag, hit size limits, or be configured to discard.
- If stdout is redirected, the actual sink may differ from local environments.

**File path:**
- FileAppender open/write operations can fail due to permissions, full volumes, rotation, or read-only mounts.
- Writing to OS buffers does not guarantee fsync/durability across a host crash.
- If an agent tails files, you must understand rotation, inode/offset checkpoints, and retention.

**Remote collector path:**
- Batches may be partially accepted; HTTP 200/202 and transport ACKs have distinct semantics.
- Retries can create duplicates; preserve event IDs and deduplicate if the SLI counts unique events.
- The indexer can lag while ingest remains healthy; freshness SLOs must measure at the queryable milestone.
- Auth/TLS failures or schema changes can cause some events to be rejected.

With multiple parallel sinks, specify whether the SLO means **reaching at least one sink**, **reaching the primary sink**, or **reaching both sinks**. Do not sum event counts across two sinks and call it completeness: one event could be counted twice and mask another lost event.

## 17. Should Audit Logging Share the Same SLO as Operational Logs?

Usually **no**, if audit logs serve compliance, traceability, or mandatory business evidence. Principles to separate:

- **Best-effort observability logs** for operations may tolerate some level of discard/sampling.
- **Audit events** may require a contract forbidding arbitrary drops, restricted access, retention, immutable storage, and evidence preservation.
- If an audit record must be saved before a business action completes, establish a clear commit/ack boundary—not just `logger.info("AUDIT ...")`.
- A transactional outbox can bind a state mutation and a pending event in the same database transaction; a dispatcher retries/deduplicates after commit. It reduces event-loss gaps, **without automatically providing pipeline-wide exactly-once delivery**.
- `DENIED/REJECTED` events without a state mutation may also need to be stored; placing them in a business transaction that rolls back would falsely make you think the audit record survived.
- If the audit sink fails, policy may require failing closed for specific actions or using an approved durable buffer. Align this with business, legal, and security teams.

An SLO of “99.95% of audit logs arrive within 30 seconds” **does not replace** a mandatory requirement that all evidence be captured. It can serve as an alerting indicator, while durability, integrity, and access control are separate requirements that must be verified.

### Distinguishing “Arrived on Time” from “Still Retained”

An event that arrived on time but is deleted after 1 hour—when policy requires 90 days—still violates the **retention/durability requirement**. Separate SLIs or compliance checks are needed for survival across restarts/crashes, data immutability, retention, and audit access.

## 18. Testing SLOs: Unit, Integration, and Fault Injection

### 18.1. Unit Testing the Classification Function

Section 10 includes `classify(Event, Duration)`. In a JUnit 5 project in the same package, you can test it as follows:

```java
// Test snippet: requires JUnit Jupiter on the classpath.
import static org.junit.jupiter.api.Assertions.*;
import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class LogPipelineSloTest {
    @Test
    void deadlineBoundaryCountsAsOnTime() {
        Instant start = Instant.parse("2026-01-01T10:00:00Z");
        var event = new LogPipelineSloDemo.Event(
                "e-1", start, start.plusSeconds(30));

        assertEquals(
                LogPipelineSloDemo.Result.ON_TIME,
                LogPipelineSloDemo.classify(
                        event, Duration.ofSeconds(30)));
    }

    @Test
    void lateAndMissingAreNotGood() {
        Instant start = Instant.parse("2026-01-01T10:00:00Z");

        assertEquals(
                LogPipelineSloDemo.Result.LATE,
                LogPipelineSloDemo.classify(
                    new LogPipelineSloDemo.Event(
                        "e-2", start, start.plusSeconds(31)),
                    Duration.ofSeconds(30)));

        assertEquals(
                LogPipelineSloDemo.Result.MISSING,
                LogPipelineSloDemo.classify(
                    new LogPipelineSloDemo.Event(
                        "e-3", start, null),
                    Duration.ofSeconds(30)));
    }
}
```

This is a **test snippet usable after adding the JUnit 5 dependency and placing it in the right package**, not a standalone file runnable with plain `javac`. It tests boundary thresholds, not end-to-end SLIs. You should also test `persistedAt` before `createdAt`, negative/invalid deadlines, duplicate events, and counter behavior when finalization is replayed.

### 18.2. Pipeline Integration Tests

- Start the logging backend with the appropriate profile and a test sink (isolated collector/proxy, file, or agent).
- Emit events with unique `eventId`s from the exact entry point defined by the SLO.
- Use controlled/contracted timestamps and measure latency at the chosen sink milestone.
- Wait for the sink via acknowledgment or timeout-bounded polling; do not use `Thread.sleep(500)` and treat it as confirmation.
- Count unique IDs at source and sink, distinguishing lost, late, duplicate, and schema-invalid events.
- Clean up appenders, agents, queues, files, and test collectors after the test; never interfere with production.

### 18.3. Intentional Fault Injection

| Scenario | What to Observe |
| --- | --- |
| Logger level/filter blocks critical events | SLI detects missing events if source truth is independent |
| Async queue fills and discards | Drop metrics, rising bad events, does not report green |
| Sink file lacks permissions / disk full | Backend status, backlog, fallback, loss rate |
| Agent restart | Spool/offset, duplicates or gaps, eventual delivery |
| Collector returns 429/503 | Retry with backoff, deadline misses, queue growth |
| Collector accepts but indexing lags | Ingest ACK looks good while queryable freshness degrades |
| Network timeout after collector receipt | Retry duplicates, deduplication by event ID |
| JVM/process crash with queued events | Verify in-RAM queue is not durable |
| Reconciler stops or source metric disappears | No-data/measurement alert, no false SLO pass |
| Multiple services/partitions | Ordering, class-level degradation, and grouped SLIs |

In long-running fault tests, bound event rates, spool capacity, and test duration so CI runners do not run out of disk. For mandatory audit logs, test fail-closed behavior or outbox recovery too, not just the SLO dashboard.

## 19. Runbook When the Logging SLO Is Breached

When an SLO or canary alerts, a useful response workflow is:

1. **Validate the signal:** Which SLI failed? Completeness, freshness, schema, canary, or measurement unavailable? Which window and which log class?
2. **Check the source:** Were eligible events created/committed? Did log levels, filters, sampling, or schemas change? Are source IDs still being emitted?
3. **Isolate the stage:** logger → async queue → stdout/file → agent → transport → collector → index/query. Compare counts and event IDs at each trustworthy milestone.
4. **Inspect resources:** queue depth, drops, spool bytes, disk quota, memory, CPU, retries, 429/5xx responses, rate limits, and index lag.
5. **Distinguish lost from late:** events arriving after the deadline still violate the timely SLO; their late arrival helps localize the fault without erasing the violation.
6. **Mitigate impact:** restore the sink, adjust quotas/transport, activate fallback paths per runbook; avoid aggressive retry storms that cause overload.
7. **Preserve evidence:** for security/audit events, retain the source outbox, spool, independent records, and access metadata; do not rush to delete raw logs.
8. **Recover:** drain the backlog, replay unacknowledged events, deduplicate re-received records; measure queue age and confirm the sink milestone.
9. **Recalculate impact:** affected time range, event classes, finalized bad count, unreconciled events, and error budget consumption.
10. **Prevent recurrence:** re-test the failure scenario, add independent alerts, and monitor the post-deployment window.

Incident reports must distinguish **“confirmed lost”**, **“missed deadline but arrived late”**, **“insufficient data to determine”**, and **“excluded from eligible group by policy”**. Never report “0 logs lost” based solely on collector metrics when the source lacks independent truth.

## 20. Common Mistakes When Building Log Pipeline SLOs

| Mistake | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| Treating collector availability as an end-to-end SLO | Collector can be up while events are lost upstream | Measure by event IDs from source to sink |
| Using only received logs as the denominator | Silent loss never enters the denominator | Use source eligible count / reconciliation |
| Using p99 latency of arrived events | Lost events have no latency | On-time success / total eligible |
| Marking events as missing before deadline matures | Creates false failures | Matured cohorts and clear deadlines |
| Removing late events from bad once they arrive | Erases freshness violations | Keep deadline-miss, track late separately |
| Counting retried duplicates as new source messages | Completeness can exceed 100% | Deduplicate by stable event ID |
| Merging audit and debug into one ratio | High INFO volume hides small, critical audit losses | Define SLOs by event class and obligation |
| Treating a collector-originated canary as end-to-end | Bypasses the JVM/appender | Emit canary from the true start point |
| Treating an empty queue as durable | Worker may have dequeued and failed to write | Check ACK/index/query at the destination milestone |
| Querying only latency histograms | Does not measure silent drops | Loss/completeness SLI + drop metrics |
| Not monitoring the SLI reconciler | Dead instrumentation makes dashboards falsely green | No-data alerts, lag, independent health |
| Mixing emission and ingest windows | Skewed ratios, can exceed 100% | Consistent cohorts or finalized windows |
| Using eventId as a metric label | Cardinality explosion, potential data leak | Keep IDs in an event store, use bounded labels |
| Alerting only on transport errors | Parse/index failures still make events unusable | Schema/queryability SLI |
| Defaulting to 99.95% for every system | Ignores policy, cost, and risk | Agree on targets by class and need |
| Retrying infinitely during outages | Causes overload, prolongs incidents | Backoff, budgets, bounded spool/buffer |

## 21. Log Pipeline SLO Implementation Checklist

- [ ] Identify which event classes need an SLO, the source milestone `t0`, and why events are eligible.
- [ ] Define the destination milestone: accepted, durable, indexed, or queryable—never vaguely “delivered.”
- [ ] Define the deadline, SLO window, target, and handling of immature events.
- [ ] Choose an on-time/completeness SLI with an appropriate source denominator that detects silent loss.
- [ ] Establish a stable `eventId`, deduplication, and reconciliation for retries or lost collector ACKs.
- [ ] Properly classify good, late, missing, invalid-timestamp, and schema-invalid events.
- [ ] Synchronize clocks or use reliable latency measurement; never treat negative durations as good.
- [ ] Track p95/p99 latency, queue depth, drops/retries, spool usage, and collector/index lag for diagnostics.
- [ ] Run canaries through the real path with dedicated IDs and independent outcome verification.
- [ ] Build the reconciler with watermarks, no-data alerts, safe restart/replay, and no double-counting.
- [ ] Use error budgets and burn rates with appropriate windows, volumes, and alerts.
- [ ] Scope SLOs by class; give mandatory audit logs dedicated durability/security contracts where needed.
- [ ] Test fault injection across logger, queue, agent, collector, indexing, and measurement.
- [ ] Keep sensitive data out of metric labels, canaries, and broadly accessible dashboards.
- [ ] Maintain a runbook for impact calculation, backlog recovery, replay, and reporting measurement uncertainty.
- [ ] Review SLOs after changes to log levels, filters, appenders, sampling, retention, or backends.

**Takeaway:** A logging SLO is valuable when it measures **whether events that should arrive actually reach the right place, on time, and in a usable state**. Achieving this requires source-side eligibility definitions, clear deadlines and destination milestones, ID reconciliation, and independent measurement. Queues, collector health, canaries, and latency histograms are useful signals, but none of them can replace end-to-end event-loss measurement.
