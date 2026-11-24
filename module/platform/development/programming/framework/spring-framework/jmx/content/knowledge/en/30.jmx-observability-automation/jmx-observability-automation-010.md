# Designing Threshold- and Trend-Based Alerts in Spring Framework JMX

## 1. Overview

In Java/Spring applications, JMX (Java Management Extensions) lets operational tools read the state of MBeans such as queues, memory, thread pools, caches, connection pools, and application-published counters. When combined with a metrics collection and rule evaluation system, that data can be used to design **threshold- and trend-based alerts**.

A good alert does not merely say that a value is greater than a number. It must answer:

- Does this signal reflect a real problem?
- What is the impact on users and business operations?
- Is the trend worsening, or is the system recovering on its own?
- Is immediate action required, or only monitoring?
- What should the alert recipient inspect next?
- Can duplicate or noisy alerts be reduced without missing critical incidents?

In Spring Framework JMX, MBeans typically only **expose data and operations**. Retaining history, computing trends, evaluating thresholds, dispatching notifications, and managing incidents usually belong to an external monitoring/alerting system. JMX notifications can also signal state transitions, but they do not replace an alerting system with storage, time-window evaluation, and history.

### Objectives

After this lesson, you will be able to:

1. Select useful JMX attributes to serve as alert signals.
2. Distinguish absolute threshold, ratio, trend, and forecasting alerts.
3. Design \`for\`/duration conditions, hysteresis, and cooldowns to prevent flapping.
4. Use counters, gauges, rates, and rolling windows with accurate semantics.
5. Design warning/critical severity levels based on impact and actionability.
6. Combine JMX metrics with monitoring systems such as Micrometer/Prometheus when appropriate.
7. Test alerts against normal data, load spikes, errors, missing data, and recovery.
8. Craft alert messages with ownership, context, runbooks, and resolution conditions.

## 2. Data and Alerting Model

\`\`\`text
Spring application
  |
  +-- MBeans / @ManagedResource
  |       |
  |       +-- QueueDepth
  |       +-- ActiveThreads
  |       +-- FailedJobsTotal
  |       +-- LastSuccessEpochMs
  |
  +-- JVM platform MXBeans
          |
          +-- HeapMemoryUsage
          +-- ThreadCount
          +-- GarbageCollector counts/times
          |
          v
   JMX collector / metrics bridge
          |
          v
   Time-series database
          |
          v
   Rule evaluation / alert manager
          |
          +-- Threshold checks
          +-- Trend / rate analysis
          +-- Missing-data handling
          +-- Dedup, grouping and routing
          |
          v
    Warning / Critical alerts
          |
          v
    Operator / incident response
\`\`\`

Distinguish:

- **MBean:** an observable data source inside a JVM.
- **JMX attribute:** current state or counter exposed by an MBean.
- **JMX notification:** an event signal at the moment the producer emits it.
- **Collector:** actively gathers data via JMX or reads from an instrumentation system.
- **Time-series store:** persists samples over time.
- **Alert rule:** defines the condition that requires alerting.
- **Alert manager:** dispatches, groups, deduplicates, throttles, and routes alerts.
- **Runbook:** guides the recipient on how to assess and remediate.

Do not assume \`MBeanServer\` keeps enough history to calculate trends or sends email/Slack/PagerDuty notifications on its own. Those capabilities must be implemented at the appropriate layer.

## 3. Start from the Symptom to Detect

Do not start by asking “which MBeans are available?” and creating alerts on every attribute. Identify the symptom that affects operations.

| Symptom | Appropriate Signal | What to Check |
|---|---|---|
| Work piling up | QueueDepth, enqueue/dequeue rate | Is backlog growing steadily or just a spike |
| Worker stopped progressing | LastSuccessTime, ProcessedTotal | Is there incoming work |
| Pool near exhaustion | ActiveConnections / MaxConnections | Does it stay elevated for long |
| JVM memory pressure | HeapUsed / HeapMax, GC pauses | Is max heap defined; is GC increasing |
| Processing errors rising | Failure counter rate / total rate | Is there traffic; is denominator large enough |
| Scheduler delayed | LastExecutionAgeSeconds | What is the expected schedule cadence |
| Cache performing poorly | Hit/Miss rate, latency | Did traffic or workload pattern change |
| Thread pool saturated | ActiveThreadCount, QueueSize, rejected count | Is the queue bounded and do tasks have timeouts |

Select an attribute only when it has clear semantics, reasonable read cost, and drives a concrete operational decision.

## 4. Choosing the Right Data Type

### Gauge

A Gauge represents a measurement at read time:
- \`QueueDepth\`.
- \`ActiveConnections\`.
- \`HeapUsedBytes\`.
- \`CurrentWorkers\`.

It can go up or down and is not necessarily monotonic.

### Counter

A Counter represents a cumulative total within a scope:
- \`ProcessedJobsTotal\`.
- \`FailedJobsTotal\`.
- \`RejectedRequestsTotal\`.

If a counter resets on restart, the rate calculation system must detect counter resets properly. Never use “counter increased by 100” without specifying the time interval.

### Timestamp

For example, \`LastSuccessfulRunEpochMillis\`. When alerting on a stalled worker, you can compute:

\`\`\`text
lastSuccessAgeSeconds = (nowMillis - lastSuccessEpochMillis) / 1000
\`\`\`

Handle the case where no successful run has occurred yet, clock skew, and whether the schedule is fixed.

### Ratio

Example:

\`\`\`text
PoolUtilization = ActiveConnections / MaxConnections
\`\`\`

Apply only when \`MaxConnections > 0\`; account for dynamic max sizes and measure both values near the same instant.

### Rate

Example:
\`\`\`text
ErrorRatePerSecond = increase(FailedJobsTotal in window) / windowSeconds
\`\`\`

Distinguish absolute error rate from error ratio over total requests. When traffic is near zero, a single failure can produce a 100% ratio that is not worth paging for.

## 5. Absolute Thresholds

Absolute thresholds are simple when the value domain and system capacity are stable.

Examples:
- QueueDepth greater than 500 jobs.
- Worker paused during processing hours.
- Active connections exceeding 90 in a pool with capacity 100.
- TimeSinceLastSuccess exceeding 10 minutes when the expected schedule is 1 minute.

A simple rule:

\`\`\`text
if QueueDepth > 500:
    warning
\`\`\`

However, if the queue normally jumps to 600 for 15 seconds after a batch and drains on its own, this rule easily generates noisy alerts.

Add a sustained duration:

\`\`\`text
if QueueDepth > 500 for 5 minutes:
    warning
\`\`\`

The 5-minute window is only an example, not a universal standard. Choose it based on workload characteristics, consumption rate, and user impact.

### When Are Absolute Thresholds Appropriate?

- Capacity limits are clearly defined.
- The value carries absolute meaning.
- The threshold is validated against operational data.
- Breaching the threshold requires consistent action.

### When Are They Insufficient?

- Traffic follows hourly/daily cycles.
- Different clusters have different capacities.
- Queues grow in bursts and drain rapidly.
- Systems auto-scale, making fixed thresholds obsolete quickly.

## 6. Capacity-Relative Thresholds

A pool with 20 connections and a pool with 200 connections should not share the same “18 active connections” threshold.

Compute:
\`\`\`text
utilization = active / maximum
\`\`\`

Example:
- Warning if utilization exceeds 0.80 sustained for 10 minutes.
- Critical if utilization exceeds 0.95 sustained for 3 minutes.

These are illustrative conditions, not a standard for every pool. For pools with legitimate bursts, include waiters, timeout counts, or queue depth to assess whether users are actually impacted.

A high ratio does not always mean the service is broken. If a pool has low headroom without waiters or timeouts, capacity planning may be needed rather than paging.

## 7. Trend-Based Alerting

Trends answer “how fast is the value rising or falling?”, not just “has the value crossed a mark?”.

Example:
\`\`\`text
Time       QueueDepth
10:00      100
10:05      180
10:10      280
10:15      400
10:20      560
\`\`\`

A value of 400 at 10:15 has not yet crossed a 500 threshold, but the backlog is growing. If the growth rate is steep with no sign of recovery, an early trend alert is valuable.

### Simple Linear Slope

\`\`\`text
slope = (value_now - value_10min_ago) / 10
\`\`\`

The unit is jobs/minute when sampled every minute.

In practice, a slope from just two points is sensitive to spikes or missing data. You can use:
- Linear regression over a window.
- Rolling median/mean.
- EWMA to smooth noise.
- Change-point/anomaly detection once baseline data exists.

Each method must be validated against workload behavior. Do not alert on a minor trend in a short window with high random variance.

## 8. Combining Thresholds and Trends

A useful alert can require both:

\`\`\`text
Warning if:
  QueueDepth > 300
  AND slope over 10 minutes > 20 jobs/minute
  AND condition persists for 5 minutes
\`\`\`

Benefits:
- Avoids alerting on a high queue that is draining quickly.
- Can warn before hitting a severe limit.
- Filters out brief spikes.

However, if QueueDepth has already crossed a truly critical threshold, do not require a positive slope: a very high, stagnant queue is still an incident.

A strategy:
- Warning: backlog is both elevated and growing.
- Critical: backlog exceeds the user-impact threshold, or time-to-exhaustion is very short.
- Recovery: backlog drops and remains in the safe zone.

## 9. Time-to-Exhaustion Forecasting

When a queue has bounded capacity, you can estimate:

\`\`\`text
remainingCapacity = queueCapacity - currentDepth
netGrowthRate = enqueueRate - dequeueRate

if netGrowthRate > 0:
    timeToFull = remainingCapacity / netGrowthRate
\`\`\`

Example:
- Capacity: 10,000 jobs.
- Current depth: 8,000 jobs.
- Net growth: 100 jobs/minute.
- Time-to-full: 20 minutes.

This is an **estimate** assuming the growth rate continues similarly. If auto-scaling kicks in or rates shift sharply, the forecast can be wrong.

Recommendations:
- Use a sufficiently long window.
- Verify netGrowthRate is steadily positive.
- Attach confidence/freshness indicators.
- Do not present false precision when data is noisy.
- Combine with an absolute critical threshold.

## 10. Hysteresis to Prevent Flapping

Flapping occurs when a signal oscillates around a threshold, causing the alert to fire and clear repeatedly.

Example:
\`\`\`text
QueueDepth: 490 -> 510 -> 495 -> 520 -> 480 -> 505
threshold: 500
\`\`\`

A single threshold makes the system flip states continuously.

**Hysteresis** uses two thresholds:
- Enter alert when \`QueueDepth >= 500\`.
- Clear alert when \`QueueDepth <= 350\`.

\`\`\`text
             QueueDepth
                 |
   Alert ON  >= 500
                 |
        350 .. 500   Keep previous alert state
                 |
   Alert OFF <= 350
\`\`\`

This is a state machine. Between the two thresholds, the previous state is retained. You can also combine durations before entering/clearing.

### Logic Example

\`\`\`java
public final class QueueAlertState {
    private boolean active;

    public boolean update(int queueDepth) {
        if (!active && queueDepth >= 500) {
            active = true;
        } else if (active && queueDepth <= 350) {
            active = false;
        }
        return active;
    }
}
\`\`\`

This is a simple hysteresis simulation. Real alerting systems must manage state across multiple samples and may require \`for\` durations as well as missing-data semantics.

## 11. Time Windows and Sustained Conditions

A condition like “CPU > 90%” is usually insufficient for paging. A brief spike may be normal.

Approaches:
- **Instantaneous:** evaluate every sample.
- **Rolling average:** mean over a window.
- **Percentile:** captures tail latency or pause durations.
- **Sustained duration:** require the condition to hold continuously for N minutes.
- **Count of violations:** at least K out of N samples breach the threshold.

Example:
\`\`\`text
Critical if:
  error_ratio_5min > 5%
  AND requests_5min >= 100
  sustained for 3 minutes
\`\`\`

The request-count condition prevents alerting on a 100% error rate when only one request failed.

Be careful not to pick an overly long window: it reduces noise but delays incident detection. Choose based on SLOs and required response time.

## 12. Warning and Critical

A two-tier model:

| Level | Purpose | Action |
|---|---|---|
| Warning | Early degradation forming | Investigate during business hours, prepare to add capacity |
| Critical | Likely severe impact or active SLO breach | On-call paging or incident response |

Avoid:
- Warning when a metric is “somewhat high” with unknown impact.
- Critical for every internal glitch that does not affect users.
- Multiple separate alerts paging for the same root cause.

A good system ties thresholds to capacity, SLOs, tolerance windows, and concrete actions.

## 13. JMX Signals for Queues and Workers

A Spring MBean can expose:

\`\`\`java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.jobs:type=Worker,name=Import",
    description = "Import worker monitoring"
)
public class ImportWorkerMonitor {

    private final AtomicInteger pending = new AtomicInteger();
    private final AtomicInteger active = new AtomicInteger();
    private final AtomicLong completed = new AtomicLong();
    private final AtomicLong failed = new AtomicLong();

    @ManagedAttribute(description = "Current pending job count")
    public int getPendingCount() {
        return pending.get();
    }

    @ManagedAttribute(description = "Current active job count")
    public int getActiveCount() {
        return active.get();
    }

    @ManagedAttribute(description = "Completed jobs since restart")
    public long getCompletedTotal() {
        return completed.get();
    }

    @ManagedAttribute(description = "Failed jobs since restart")
    public long getFailedTotal() {
        return failed.get();
    }
}
\`\`\`

This is an example management interface. In a real application, data must be updated by actual workers/services rather than an isolated set of counters disconnected from business processing.

### Alerts You Can Design

- PendingCount is high and steadily rising.
- PendingCount is high while ActiveCount is 0 when workers should be running.
- FailedTotal rate increases over a time window.
- CompletedTotal does not increase while PendingCount is non-zero.
- Queue capacity is nearly exhausted.

Reading a single snapshot is insufficient for computing rates/trends. The collector must store multiple samples over time.

## 14. JMX Platform MXBeans and JVM Alerts

Java provides platform MBeans such as:
- \`java.lang:type=Memory\`.
- \`java.lang:type=Threading\`.
- \`java.lang:type=GarbageCollector,name=...\`.
- \`java.lang:type=MemoryPool,name=...\`.

Heap can be read via:

\`\`\`java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;

MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
MemoryUsage heap = memory.getHeapMemoryUsage();

long used = heap.getUsed();
long max = heap.getMax();

if (max > 0) {
    double utilization = (double) used / max;
    System.out.printf("Heap utilization: %.2f%n", utilization);
}
\`\`\`

When \`max\` is undefined (e.g., -1 per some APIs), do not divide to compute a ratio. Handle unbounded cases explicitly.

### Do Not Alert Solely on “heap > 80%”

A JVM may naturally use high heap before GC and then drop, so a single 80% snapshot does not prove a memory leak. You may need:
- Post-GC heap usage trend.
- GC pause duration and frequency.
- Allocation rate.
- OutOfMemoryError indicators.
- JVM version, collector type, and heap sizing.
- Application latency/error rates.

Reliable alerts combine user impact with resource signals rather than relying solely on one generic threshold.

## 15. Counter Resets After Restart

A \`FailedTotal\` counter can grow like:

\`\`\`text
100 -> 110 -> 130 -> process restart -> 0 -> 5
\`\`\`

If a collector naively computes \`new - old\`, the delta becomes negative and breaks rate calculations.

Requirements:
- Know when counters reset.
- Use reset-aware increase/rate functions in the metrics engine.
- Attach appropriate instance identities.
- Account for missing samples during restarts.
- Avoid summing two process instances together when one pod replaces another.

Never alert directly on \`FailedTotal > 1000\` for long-lived counters, because they will inevitably cross the threshold over time. Alerts should generally use **error rate** or error ratio over a window.

## 16. Missing Data: Absent Data Is Also a State

If a collector fails to read JMX, the system might be experiencing:
- Dead JVM.
- Disconnected JMX connector.
- Firewall change.
- Expired credentials.
- Unregistered MBean.
- ObjectName changed during deployment.
- Scraper/collector failure.

Never default missing data to zero. Zero means the system reported a measured value of 0; missing means no valid sample exists.

A policy might:
- Fire a dedicated “JMX target unavailable” alert after an appropriate delay.
- Mark metric-dependent alerts as unknown rather than falsely auto-clearing them.
- Distinguish telemetry loss from healthy idle workers.
- Provide a runbook to inspect connector and service health.

Example:
\`\`\`text
QueueDepth = 0: measured backlog is 0
QueueDepth = missing: backlog is unknown
\`\`\`

These two states are not equivalent.

## 17. Notifications and Rule-Based Alerting

JMX notifications can signal events when:
- A worker transitions to FAILED.
- A resource enters DEGRADED state.
- Configuration reload fails.
- A queue stops unexpectedly.

However, JMX notifications do not durably persist or fully replay when clients are offline. High-reliability alerting systems should use **metrics polling + rule evaluation**, optionally supplemented by notifications for early signals.

Coordination example:
1. Notification reports \`worker.failed\`.
2. Collector/alert engine re-reads \`WorkerState\`.
3. Alert engine verifies the condition persists.
4. Alert routes to the right owner.
5. When state returns to RUNNING and stabilizes, the alert clears.

This avoids reacting to stale single notifications and supports recovery after disconnects.

## 18. Avoiding Alert Storms and Duplicate Alerts

A database outage can cause:
- Connection pool saturation.
- Growing queue depth.
- Rising error rates.
- Rising latency.
- Failed workers.

If five separate alerts page independently for the same root cause, on-call responders get overwhelmed.

Best practices:
- Group alerts by service, environment, cluster, or incident.
- Use intentional inhibition/suppression.
- Designate a primary symptom alert.
- Attach secondary signals as context.
- Use a stable deduplication key.
- Never use request IDs or session IDs as alert identity.
- Rate-limit notifications during flapping.

Do not suppress so broadly that independent incidents get hidden. Grouping rules should reflect real ownership and failure domains.

## 19. Do Not Base Alerts Solely on Technical Metrics

A JVM may show normal CPU/heap while business work has stalled. For example:
- High QueueDepth.
- CompletedTotal is not increasing.
- LastSuccessAt is too old.

A “worker stalled” alert can be more actionable than “high CPU” because it ties directly to user-facing trouble.

Illustrative condition:

\`\`\`text
WorkerStalled if:
  PendingCount > 0
  AND increase(CompletedTotal over 10m) == 0
  AND WorkerState == RUNNING
\`\`\`

Considerations:
- Can legitimate batches take longer than 10 minutes?
- Are there scheduled pickup delays?
- How does CompletedTotal reset/restart?
- Are long retries occurring?
- Is WorkerState stale or fresh?

If expected throughput and standard processing times are unknown, consider alerting on the age of the oldest pending job instead of relying solely on CompletedTotal.

## 20. Setting Thresholds from Real Data

A threshold selection workflow:
1. Collect a sufficiently long baseline (peak/off-peak hours, weekdays/weekends).
2. Identify capacity, service SLOs, and where user impact begins.
3. Label historical incidents and normal patterns.
4. Backtest candidate rules offline against historical data.
5. Measure false positives, false negatives, and detection delay.
6. Choose warning/critical thresholds.
7. Configure sustained duration, hysteresis, and cooldowns.
8. Review after major changes in workload or capacity.

There is no universal “standard JMX threshold” for every application. Good thresholds are grounded in impact, real capacity, and clear actions.

### Historical Distribution Thresholds

If queue depth is cyclical, you can use time-of-day or percentile baselines. However, anomaly detection requires managing:
- Seasonality.
- Cold starts and sparse data.
- Load shifts or deployments.
- Avoiding treating a prolonged outage as the new normal baseline.
- Limiting how fast adaptive thresholds can drift.

An overly adaptive dynamic threshold can fail to trigger when a system degrades gradually.

## 21. Example Alerts with PromQL

Once JMX data is exported as time series with appropriate names/labels, rules can be written. Metric names here **are collector examples**, not default standardized Spring/JMX names.

### Queue Backlog

\`\`\`promql
job_queue_pending{app="orders",env="prod"} > 500
\`\`\`

The alert rule can set \`for: 5m\` to fire only when the condition holds continuously. This requires the collector to actually export the \`job_queue_pending\` metric.

### Error Rate

\`\`\`promql
rate(job_failed_total{app="orders",env="prod"}[5m]) > 2
\`\`\`

This measures failures/second (5-minute average), not 2%. To compute a percentage ratio, you need a matching denominator such as processed/attempted request rate.

### Error Ratio

\`\`\`promql
sum(rate(job_failed_total{app="orders",env="prod"}[5m]))
/
clamp_min(
  sum(rate(job_attempted_total{app="orders",env="prod"}[5m])),
  0.001
)
> 0.05
\`\`\`

Add a minimum traffic volume condition to avoid false alerts during low traffic. \`clamp_min\` only prevents division by zero; it does not prove the denominator is large enough.

### Backlog Trend

\`\`\`promql
deriv(job_queue_pending{app="orders",env="prod"}[15m]) > 0.5
\`\`\`

\`deriv()\` estimates the slope in **units per second**. 0.5 jobs/second is roughly 30 jobs/minute. Combine with absolute backlog to avoid alerting when a tiny queue grows slightly.

## 22. Illustrative Alert Rule YAML

A Prometheus-style rules example:

\`\`\`yaml
groups:
  - name: orders-jobs
    rules:
      - alert: OrdersQueueBacklogHigh
        expr: job_queue_pending{app="orders",env="prod"} > 500
        for: 5m
        labels:
          severity: warning
          team: orders
        annotations:
          summary: "Orders queue backlog high"
          description: "Queue {{ $labels.queue }} has exceeded 500 pending jobs for 5m"
          runbook_url: "https://intranet.example/runbooks/orders-queue"
\`\`\`

The runbook URL above is a **placeholder**. Replace it with a real internal URL if deployed. This condition only works if the collector exports metrics and labels matching the query.

In real projects, version-control alert rules, review them via pull requests, and validate them using your alerting stack's tooling.

## 23. Designing Alert Messages

A message needs enough information to investigate:

\`\`\`text
[CRITICAL] Orders worker backlog may exhaust capacity

Environment: production
Service: orders
Instance: worker-03
Resource: ImportQueue
Current queue depth: 8,600 / 10,000
15m trend: +95 jobs/min
Estimated time to capacity: ~15 min
Started at: 2026-11-11 08:30 UTC
Suggested checks:
  - Verify dequeue rate and worker health
  - Inspect downstream database latency
  - Check recent deployment and rejection counts
Runbook: <internal URL>
\`\`\`

A good alert should include:
- Severity.
- Service/environment/instance.
- Signal and threshold.
- Time duration/window.
- Trend or rate of change when relevant.
- Current state and timestamp.
- Owning team.
- Runbook and diagnostic steps.
- Clear/recovery condition.

Do not present exact forecasts when data is missing or slopes are unstable.

## 24. Preventing Flapping with a State Machine

A rule can be modeled as:

\`\`\`text
NORMAL
  |
  | QueueDepth >= 500 for 5m
  v
WARNING
  |
  | QueueDepth >= 800 for 3m
  v
CRITICAL
  |
  | QueueDepth <= 600 for 5m
  v
WARNING
  |
  | QueueDepth <= 350 for 10m
  v
NORMAL
\`\`\`

Separate enter/clear thresholds provide hysteresis; durations prevent transitions on brief fluctuations. When critical conditions ease, state can step down to warning before returning to normal.

State-machine design must answer:
- Should an alert fire on severity escalation?
- Should recovery notifications be sent?
- If data is missing, hold state or transition to unknown?
- If the collector restarts, how is state recovered?
- If an instance disappears due to valid scale-down, should it alert?

Do not embed a standalone static state machine inside each MBean to replace the alerting system unless specifically justified; alert state is generally best managed by the monitoring system over historical data.

## 25. Testing Alert Rules

Do not test a condition on a single sample alone. Test time series.

### Case A — Brief Spike

\`\`\`text
0m: 200
1m: 650
2m: 250
3m: 210
\`\`\`

If the rule requires >500 for 5 minutes, it should not alert.

### Case B — Steady Growth

\`\`\`text
0m: 200
5m: 360
10m: 540
15m: 700
\`\`\`

A backlog + trend rule can alert once the duration requirement is met.

### Case C — High but Draining

\`\`\`text
0m: 900
5m: 820
10m: 720
15m: 580
\`\`\`

A positive-trend rule should not fire, though an absolute critical threshold may still apply while the queue causes impact.

### Case D — Flapping

\`\`\`text
490, 510, 495, 520, 485, 515
\`\`\`

Hysteresis/duration prevents repeated alert firing.

### Case E — Counter Reset

\`\`\`text
FailedTotal: 100 -> 110 -> restart -> 0 -> 2
\`\`\`

Rate logic must handle resets rather than inferring negative rates.

### Case F — Missing Samples

\`\`\`text
QueueDepth: 500 -> missing -> missing
\`\`\`

Detect telemetry loss or apply an appropriate unknown state instead of defaulting queue=0 and falsely clearing the alert.

### Case G — Low Volume

One failure in one request yields a 100% error ratio; require a minimum volume to prevent false paging.

## 26. Testing the JMX Source and Collection

A great rule is useless if JMX source data is wrong.

You can check the MBean:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.jobs:type=Worker,name=Import"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException("MBean not registered");
}

Object pending = server.getAttribute(name, "PendingCount");
System.out.println("PendingCount=" + pending);
\`\`\`

Use the platform server only if the exporter actually registers there. In multi-MBeanServer environments, obtain the right server reference.

End-to-end verification:
1. Generate simulated backlog data.
2. Verify the MBean attribute changes.
3. Verify the collector reads the value.
4. Verify metric label mapping.
5. Test the alert rule with test time series.
6. Verify Alertmanager routing to the right team.
7. Verify recovery when values return to normal.

Never invoke destructive operations or generate excessive production load to test alerts.

## 27. Metrics vs. JMX Notifications

| Criterion | JMX attribute polling | JMX notification |
|---|---|---|
| Current state | Yes | Usually requires re-reading a snapshot |
| History storage | Requires collector/time-series store | Not by default |
| Trends/rates | Yes if samples are stored | Not directly |
| Fast change detection | Depends on polling interval | Can be near emission time |
| Connection loss | Collector can recover via new samples | Events may be missed |
| Reconnect | Re-read snapshot | Re-register listener |
| Alert thresholds | Well suited for rule engines | Often used as supplementary signals |
| Durable exactly-once | Not guaranteed automatically | Not guaranteed automatically |

Combine both approaches when needed:
- Notifications report anomalies immediately.
- Attribute polling confirms state and tracks recovery.
- The alerting engine evaluates sustained duration and trends.
- A log/event store retains history when business requirements demand it.

## 28. Production Alert Deployment Process

1. **Define the goal:** detect impacted users or imminent risk of impact.
2. **Select source metrics:** JMX attributes with clear semantics.
3. **Apply labels:** app, env, instance, resource, owner.
4. **Gather baseline:** understand normal variation.
5. **Choose thresholds:** absolute/ratio/trend.
6. **Set temporal logic:** window, duration, hysteresis.
7. **Handle missing data:** include rules for lost telemetry.
8. **Define severity and routing:** target the right on-call team.
9. **Write a runbook:** diagnostic steps and safe remediation.
10. **Test history and simulations:** false positives/negatives, resets, reconnects.
11. **Roll out in phases:** initially non-paging warnings to evaluate.
12. **Review periodically:** whenever capacity, workload, or architecture changes.

A well-maintained alert has an owner, documentation, test coverage, and a review schedule. Rules that are no longer meaningful should be removed rather than left to accumulate.

## 29. Anti-Patterns

**1. Alerting on every attribute.**  
Creates noise and is disconnected from concrete action.

**2. Using only an instantaneous threshold.**  
Reacts too easily to brief spikes.

**3. Failing to distinguish counters and gauges.**  
Produces wrong rates or permanently firing alerts on cumulative totals.

**4. Ignoring missing data.**  
Can mistake lost telemetry for a healthy system.

**5. Applying generic CPU/heap thresholds across all JVMs.**  
Ignores GC behavior, SLOs, workload, and memory sizing.

**6. Omitting minimum traffic conditions.**  
A single error causes a 100% error ratio.

**7. Alerting solely on trends.**  
Can miss a state that is already severely degraded but no longer climbing.

**8. Alert storms from a single root cause.**  
Lacks proper grouping and inhibition.

**9. Missing owner or runbook.**  
Responders do not know what action to take.

**10. Using JMX notifications as an event history.**  
No built-in durable replay.

**11. High-cardinality labels.**  
Request IDs/session IDs do not belong in alert identity.

**12. Unbounded auto-remediation.**  
Automated restarts or scaling can worsen incidents on bad signals.

## 30. Automating Responses to Alerts

Not every alert should automatically invoke a JMX operation.

A workflow might look like:

\`\`\`text
Alert condition
      |
      v
Validate health + recent change + current state
      |
      v
Choose action
      |
      +-- Notify only
      +-- Create incident
      +-- Restart worker (under strict policy)
      +-- Scale capacity (with guardrails)
      +-- Pause intake (when safe)
\`\`\`

When auto-remediation is used, ensure:
- Execution count limits.
- Action only after verifying state.
- Cooldowns.
- Auditing and rollback.
- Race prevention across multiple alert processors.
- Access control over operation invocation.
- Ability to disable automation during an incident.
- No blind retries of non-idempotent operations on remote JMX timeouts.

An alerting rule must not be allowed to mutate production by default merely because it detected a threshold breach.

## 31. Hands-On Exercises

### Exercise A — Designing a Backlog Alert

1. Create an MBean with PendingCount and CompletedTotal.
2. Simulate the queue rising and draining.
3. Design a warning threshold + slope rule.
4. Design a critical threshold independent of slope.
5. Add duration and hysteresis.
6. Write the clear condition.

### Exercise B — Counter Rate

1. Create FailedTotal and AttemptedTotal.
2. Store per-minute samples.
3. Compute the error rate over a 5-minute window.
4. Handle counter resets.
5. Add a minimum traffic volume guard.
6. Compare absolute failures/second against percentage ratio.

### Exercise C — Missing JMX Connection

1. Stop the collector in a test environment.
2. Observe missing data.
3. Configure a target-unavailable rule.
4. Verify dependent alerts do not falsely auto-clear.
5. Restart the collector and verify recovery.

### Exercise D — Hysteresis

1. Generate a value series oscillating around 500.
2. Compare against a single-threshold 500 alert.
3. Add enter 500, clear 350.
4. Count state transitions.
5. Add duration to reduce flapping.

### Exercise E — Capacity-Based Thresholds

1. Create pools of size 20 and size 200.
2. Compare an absolute threshold of 18.
3. Switch to utilization ratio.
4. Add waiters/timeouts.
5. Propose warning/critical levels aligned with SLOs.

### Exercise F — Runbook

1. Pick a critical alert.
2. Document owner, scope, and impact.
3. Define the first three diagnostic steps.
4. Specify safe, non-repeating actions.
5. Define the recovery condition.

## 32. Self-Check Questions

**Question 1.** Does JMX compute trends and send alerts automatically?  
**Answer:** Not by default. You need a collector, history store, and alert evaluator or custom implementation.

**Question 2.** Why is an instantaneous >500 threshold noisy?  
**Answer:** It may simply be a brief, self-recovering burst.

**Question 3.** What is hysteresis?  
**Answer:** Using separate enter and clear thresholds to prevent flapping.

**Question 4.** Why should alerts use rate instead of total FailedTotal?  
**Answer:** Long-lived cumulative counters eventually stay above static limits; rate reflects error velocity over a window.

**Question 5.** Is missing data equal to zero?  
**Answer:** No. Missing means no valid measurement is available.

**Question 6.** Is a positive trend always critical?  
**Answer:** No. Consider absolute value, capacity, growth rate, and impact.

**Question 7.** Do notifications guarantee replay after reconnect?  
**Answer:** There is no built-in durable replay; re-read snapshots and rely on monitoring history.

**Question 8.** Why is minimum volume needed for error ratios?  
**Answer:** To avoid false alerts when the denominator is tiny.

**Question 9.** What does a good alert need besides an expression?  
**Answer:** Owner, severity, context, runbook, routing, temporal logic, and a recovery condition.

**Question 10.** Should every JMX gauge breaching a threshold trigger an automatic restart?  
**Answer:** No. Auto-remediation needs guardrails, validation, cooldowns, auditing, and risk controls.

## 33. Key Takeaways

- JMX data is an observation source, not a complete alerting system.
- Start from operational impact and the questions you need to answer.
- Distinguish gauges, counters, rates, ratios, and timestamps.
- Absolute thresholds work well when capacity is fixed; ratio thresholds work better across varying scales.
- Trends help detect incidents early, but must be paired with absolute values and data quality checks.
- Durations, rolling windows, hysteresis, and cooldowns reduce noisy alerts.
- Missing data needs its own policy; never treat it as zero.
- JVM metrics such as heap/GC must be interpreted in workload and performance context.
- Group alerts and attach clear owners/runbooks.
- Notifications aid immediate detection but do not replace metric history or event stores.
- All auto-remediation must enforce authorization, idempotency/guardrails, and proper rollback.
- Test rules with normal, anomalous, reset, missing, and recovery time series.

### References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Reference — JMX Notifications: https://docs.spring.io/spring-framework/reference/integration/jmx/notifications.html
- Spring Framework Javadoc — \`@ManagedAttribute\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedAttribute.html
- Java SE 21 API — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 API — Platform MXBeans: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/package-summary.html
- Prometheus Documentation — Alerting Rules: https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/
- Prometheus Documentation — Query Functions: https://prometheus.io/docs/prometheus/latest/querying/functions/
