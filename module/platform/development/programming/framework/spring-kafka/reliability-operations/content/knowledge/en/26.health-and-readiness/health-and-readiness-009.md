# Lag Exceeding Threshold

Increasing consumer group lag is a signal that consumers are falling behind data written to Kafka. However, a large lag number does not automatically mean the service is broken: a topic may have just experienced a traffic burst, the consumer may be intentionally paused for maintenance, or a retry workflow may be moving records to another topic. Conversely, a lag of only a few hundred records can still be severe if each record is a critical transaction that has already waited beyond SLA.

In the **Health and readiness** chapter, "lag exceeding threshold" is an operational condition used to evaluate whether a consumer group can still process work within the service's objectives. To incorporate this condition reliably into health/readiness, you must clearly define **which lag is being measured, which group/topic/partition the threshold applies to, how long the breach persists, whether metrics data is fresh, and how health status impacts the instance**.

This lesson explains how to design a threshold policy, distinguish lag count from lag age, use sustained breaches and hysteresis, integrate a lag health indicator with Spring Boot Actuator, separate readiness from liveness, monitor metrics, avoid false positives in retry/transaction/pause flows, and build recovery runbooks.

## 1. What does lag exceeding threshold mean?

Kafka stores records per partition with monotonically increasing offsets. A consumer group stores committed offsets per topic-partition. A commonly used lag calculation:

~~~text
committed-offset lag
    = log-end-offset
      - committed-offset
~~~

Example:

~~~text
Topic: orders.events
Group: orders-worker
Partition: 0

Committed offset = 8,000
Log end offset   = 8,750

Lag = 8,750 - 8,000 = 750
~~~

In this example, the group is 750 offset positions behind the end of the log. This is a backlog signal, though it is not enough on its own to conclude 750 business events are waiting: compaction, transaction markers, aborted records, offset gaps, and how the exporter fetches end offsets can affect interpretation.

A "lag exceeding threshold" policy typically consists of multiple conditions:

- Lag exceeds a threshold for the group total or a single partition.
- The condition persists long enough, not just a single scrape.
- The consumer group has a genuine backlog and input continues arriving.
- Record age or business freshness exceeds the allowed budget.
- Pause/maintenance states are accounted for.
- Lag measurement data is fresh enough to act on.

### 1.1. Thresholds are a business policy

A threshold of 1,000 records may suit a pipeline processing thousands of records per second, yet be severe for a pipeline processing only a few records per minute.

Thresholds must be chosen based on:

1. Normal and peak producer rates.
2. Consumer capacity measured under production-like conditions.
3. Event processing latency SLAs.
4. Size and processing cost of each record.
5. Partition count and load skew across partitions.
6. Permitted pause/maintenance windows.
7. Topic retention and maximum time available to drain a backlog.

Do not copy a threshold number from another service merely because it also uses Kafka.

## 2. Identify the lag type before setting thresholds

Dashboards can display several metrics all called "lag." You must know which position each metric measures from.

| Metric | Interpretation | Question Answered |
|---|---|---|
| Committed group lag | End offset minus committed offset | How far has the group confirmed progress? |
| Fetch/consumer position lag | End offset minus consumer fetch position | How far has the consumer read? |
| LSO lag | Last stable offset minus committed offset | How far is a `read_committed` consumer behind readable data? |
| Partition lag | Distance for each individual topic-partition | Which partition is falling behind? |
| Lag age / oldest record age | Age of the oldest waiting data | How long must users wait? |
| Business completion backlog | Unfinished business items per application state | How much real work remains? |

### 2.1. Committed lag and fetch lag differ

A consumer may have polled a batch of records without committing the offset yet:

~~~text
Log end offset        = 1,100
Consumer position     = 1,050
Committed offset      = 1,000

Fetch-position lag    = 50
Committed-offset lag  = 100
~~~

This is normal when a listener is processing a batch or committing per batch. Do not use fetch lag and committed lag interchangeably in the same threshold policy.

### 2.2. Transactions and last stable offset

With `isolation.level=read_committed`, consumers do not read records from aborted transactions, and reads can be bounded by the last stable offset (LSO) while open transactions remain unfinished.

Example:

~~~text
Log end offset       = 5,500
Last stable offset   = 5,400
Committed offset     = 5,350

LEO lag              = 150
LSO lag              = 50
~~~

An exporter using LEO and an exporter using LSO can show different lag while transactions are open. When defining thresholds, document the lag source and calculation explicitly; otherwise operations teams may compare numbers with incompatible definitions.

### 2.3. Negative lag, missing offsets, or stale series

A new group may have no committed offset yet; partitions may be unassigned; an exporter may scrape end offsets and committed offsets at different instants. Never treat missing values as 0, and never interpret negative lag as "consumer faster than broker."

Policies need an **unknown** state when data is insufficient to conclude. If an exporter stops updating, some gauges retain old values and create the illusion that lag is stable.

## 3. Total lag does not replace partition lag

Suppose a topic has four partitions:

| Partition | Lag |
|---|---:|
| 0 | 20 |
| 1 | 30 |
| 2 | 1,800 |
| 3 | 25 |
| **Total** | **1,875** |

Total lag of 1,875 may sit below a warning threshold of 2,000, yet partition 2 has accumulated 1,800 records. If this partition carries a hot key or a critical business flow, looking only at total lag hides the problem.

Monitor at least:

- **Total lag** of the consumer group per topic.
- **Maximum partition lag**.
- Number of partitions with continuously growing lag.
- Partition lag growth rate.
- Current partition assignment/member if ownership investigation is needed.

### 3.1. Do not sum per-consumer max lag to compute total

One consumer can be assigned multiple partitions. The `records-lag-max` metric is typically the largest lag observed by that client, not the group's total committed lag.

To compute total group lag, collect committed offsets and end offsets per partition and aggregate using the same definition. Use client-level max lag to find consumers holding hot partitions or fetching slowly.

### 3.2. Consumer count exceeding partition count

Within a consumer group, each partition is assigned to only one consumer at a time. If a topic has three partitions while the group has six consumer instances, not all six process data from that topic.

An unassigned consumer is not necessarily a liveness fault. Health policies should consider assignment and group state rather than marking `DOWN` solely because one member has no records.

## 4. Lag count and lag age answer two different questions

Lag count measures offset distance. Lag age measures how long a record has waited.

Example:

- Pipeline A has 20,000 records of lag while processing 10,000 records/s.
- Pipeline B has 200 records of lag while processing only 1 record/s.

Pipeline B can experience much higher latency despite a tiny lag count.

A sound health policy should combine:

| Signal | Used When |
|---|---|
| Total lag | Measuring backlog scale |
| Max partition lag | Detecting hot partitions |
| Lag growth rate | Distinguishing growing vs. draining backlogs |
| Oldest unprocessed record age | Protecting freshness/SLAs |
| Business completion age | Measuring delay until side effects actually finish |
| Consumer success rate | Confirming business throughput |

### 4.1. Kafka record timestamps are not always business event time

Kafka timestamps can be producer-set `CreateTime` or broker-assigned `LogAppendTime`, depending on topic config. Payloads may contain a source-system event time that differs from both.

When computing lag age, choose a reliable timestamp. Clock skew between producer and broker can produce negative or inflated ages. If a business SLA is required, instrument event creation time and processing completion time in application state.

### 4.2. Low lag yet stale events

An event sitting in an upstream outbox for 30 minutes before being published to Kafka may be consumed immediately. Kafka lag is near 0, yet end-to-end latency is still 30 minutes.

For pipelines with outboxes, retry topics, or worker queues, measure data age across the whole workflow. Do not declare the service healthy simply because main-topic lag is 0.

## 5. Thresholds should have warning and critical levels

One approach is defining multiple tiers:

| Level | Meaning | Suggested Action |
|---|---|---|
| Normal | Lag is within baseline/SLO | Continue monitoring |
| Warning | Backlog is growing or exceeds warning threshold | Raise alert, investigate capacity |
| Critical | Lag/age breaches SLO-impacting threshold | Mark readiness failing if required by policy, page owner |
| Unknown | Metrics missing, stale, or insufficient data | Alert on observability; do not assume lag = 0 |

Illustrative example:

~~~text
orders-worker:
  warning total lag  = 2,000 records
  critical total lag = 10,000 records
  critical oldest age = 60 seconds

  warning max partition lag  = 1,000
  critical max partition lag = 5,000
~~~

These values only illustrate policy structure, not recommendations for every workload.

### 5.1. Absolute thresholds

Absolute thresholds are easy to explain and implement, such as total lag exceeding 10,000 records. However, they do not adapt to hourly producer rates, topics with widely varying record sizes, batch workloads, partition counts, or per-event processing costs.

Use absolute thresholds as guardrails combined with age and trend.

### 5.2. Ratio or capacity-based thresholds

Backlog can be compared against expected processing capacity:

~~~text
backlog_ratio = current_lag / expected_processing_capacity_per_window
~~~

For example, a consumer normally processes 5,000 records in 5 minutes; a lag of 10,000 equals roughly two capacity windows. This measure is more useful than a static number when throughput varies.

However, capacity must be measured from sustainable business success throughput, not just polled record count.

## 6. Sustained breach: do not react to a single scrape

Lag can spike briefly due to producer bursts, consumer rebalances, rolling deployments, batch commits, GC pauses, or brief backpressure pauses.

If a health indicator flips `DOWN` the instant one sample exceeds a threshold, readiness can flap and cause orchestration to thrash states.

A common policy requires the breach condition to persist continuously over a duration:

~~~text
Critical breach:
  total lag > 10,000
  continuously for 2 minutes

or

oldest record age > 60 seconds
  continuously for 30 seconds
~~~

Exact durations must fit SLOs and scrape intervals. You can use a rolling window or require N consecutive samples; handle missing samples explicitly.

### 6.1. Hysteresis to prevent flapping

Use two different thresholds for entering and clearing a state:

~~~text
Enter WARNING: lag >= 2,000
Clear WARNING: lag <= 1,000

Enter CRITICAL: lag >= 10,000
Clear CRITICAL: lag <= 5,000
~~~

These are high/low watermarks. When lag hovers around 2,000, warning state does not toggle on and off repeatedly.

### 6.2. Clear conditions must be defined

Do not clear an incident just because a single lag sample dips below the threshold. Require:

- Lag below the clear threshold for a stable window.
- Oldest record age back within SLA.
- Normal business success rate.
- Stable consumer poll progress and group assignment.

Readiness may recover faster or slower than alerts depending on service policy; define the two states separately.

## 7. Computing lag growth and catch-up time

Simple record-based model:

~~~text
backlog(t + Δt)
  ≈ max(0, backlog(t) + incoming(Δt) - completed(Δt))
~~~

Net backlog growth rate:

~~~text
growth_rate ≈ producer_arrival_rate - consumer_completion_rate
~~~

If producers emit 500 records/s and consumers complete 400 records/s, backlog grows by roughly 100 records/s. Over 5 minutes, backlog grows by 30,000 records at steady rates.

### 7.1. Estimating time to catch up

When consumer capacity exceeds the input rate:

~~~text
time_to_catch_up
  ≈ current_backlog
    / (consumer_capacity - producer_arrival_rate)
~~~

Example:

- Backlog: 12,000 records.
- Producer rate: 200 records/s.
- Consumer completion capacity: 260 records/s.
- Net drain rate: 60 records/s.

Estimated catch-up time is 12,000 / 60 = 200 seconds.

If consumer capacity is less than or equal to the producer rate, backlog cannot drain steadily. Increasing timeouts, restarting, or lowering thresholds will not fix a capacity deficit.

### 7.2. Limits of estimation

This calculation assumes relatively steady producer rates and consumer capacity, no hot partition bottlenecking the group, no retry/DLT workflows shifting backlog elsewhere, and capacity measured in business completions matching how backlog is counted.

In production, use forecasts as an operational signal, not an exact time guarantee.

## 8. Where does lag data come from?

Several collection sources exist:

| Source | Data | Notes |
|---|---|---|
| Kafka consumer group exporter | Lag by group/topic/partition | Offset definition must be verified |
| Kafka `AdminClient` | Group committed offsets, group state, end offsets via Admin APIs | Requires permissions and timeout handling |
| Kafka client metrics | Fetch lag, consumed rate, fetch behavior | Not necessarily committed group lag |
| JMX exporter | Exposes Kafka client/broker metrics | MBean names depend on version |
| Spring/Micrometer instrumentation | Listener processing and application metrics | Often requires custom business metrics |
| Observability platform | Aggregates lag, age, throughput, health | Check freshness and label cardinality |

### 8.1. AdminClient and committed offsets

Kafka `AdminClient` can query a consumer group's committed offsets, group description/state, and end offsets through the corresponding APIs. Conceptually:

1. Fetch committed offsets for the group.
2. Identify the topic-partitions to monitor.
3. Fetch end offsets using the chosen definition.
4. Calculate lag per partition.
5. Aggregate total/max and snapshot timestamp.

Fetching end offsets and committed offsets is not a single atomic snapshot. Producers and consumers can advance during the query. Results can therefore fluctuate slightly; threshold policies must tolerate minor measurement skew.

### 8.2. Do not query AdminClient directly on every health request

An `/actuator/health` endpoint can be called frequently by kubelet, load balancers, and monitoring. If every request queries multiple consumer groups/partitions against brokers:

- The health endpoint can become slow.
- Brokers receive unnecessary extra load.
- Administrative Kafka errors can make the health endpoint time out.
- Concurrent probes can trigger a query storm.

Use a **lag sampler** running periodically with timeouts, storing the latest snapshot in a thread-safe cache. The `HealthIndicator` simply reads the snapshot and evaluates policy quickly.

### 8.3. Stale metrics are a distinct state

An old lag snapshot must not be treated as stable lag. Store the timestamp of the last collection:

~~~text
Lag snapshot:
  value = 8,500
  observedAt = 12:00:00
  now = 12:05:00
  maxAge = 30 seconds

Result = STALE / UNKNOWN
~~~

Do not return `UP` merely because an old snapshot is still below threshold. Nor should you default the consumer group to `DOWN` if the fault lies only in the metrics exporter; distinguish **consumer health unknown** from **consumer lag critical**.

## 9. Designing LagSnapshot and policy

A snapshot can contain:

~~~text
groupId
topic
observedAt
totalLag
maxPartitionLag
partitionLagMap
oldestRecordAge
activeMemberCount
assignedPartitionCount
sourceDefinition (committed/LSO/...)
collectionStatus
~~~

Not every field comes from the same API. Store only fields backed by reliable data sources and clear definitions.

### 9.1. Essential policy fields

~~~text
LagPolicy:
  warningTotalLag
  criticalTotalLag
  warningPartitionLag
  criticalPartitionLag
  criticalOldestAge
  sustainedBreachDuration
  clearThreshold
  clearDuration
  maxSnapshotAge
  startupGracePeriod
  maintenancePolicy
~~~

### 9.2. Policy per group/topic

An application may consume multiple topics:

| Group/Topic | Characteristics | Health Policy |
|---|---|---|
| `orders-worker / orders.events` | Critical, requires fast processing | Age + total + partition thresholds |
| `audit-worker / audit.events` | Can process more slowly | Thresholds aligned with retention/SLA |
| `notifications / email.events` | Prone to traffic bursts | Lag trend and oldest age |
| `orders-dlt-review / orders.events.dlt` | Awaits manual review | DLT age/ownership; do not apply main-pipeline thresholds |

Do not sum lags across multiple consumer groups to invent a meaningless "total application lag." A single record can be read by multiple independent groups; summing group lags double-counts the same data.

## 10. Hysteresis and sustained breach in code

A policy evaluator can be built independently of Spring `HealthIndicator`:

~~~java
public enum LagState {
    NORMAL,
    WARNING,
    CRITICAL,
    UNKNOWN
}

public record LagSnapshot(
        long totalLag,
        long maxPartitionLag,
        Duration oldestRecordAge,
        Instant observedAt) {
}
~~~

An evaluator tracks current state and breach start timestamps to check sustained conditions:

~~~text
on each new snapshot:
  if snapshot missing or stale:
      state = UNKNOWN
  else if critical condition starts:
      record criticalSince
  else if critical condition persists:
      after sustained duration -> CRITICAL
  else if warning condition starts:
      record warningSince
  else if warning condition persists:
      after warning duration -> WARNING
  else if below clear threshold long enough:
      state = NORMAL
~~~

This is illustrative logic. A production implementation must handle process restarts, duplicate snapshot timestamps, clock shifts, stale data, and concurrent state updates across threads.

### 10.1. Breach state should not be just a boolean

A useful state holds severity, `since` timestamp, last observed lag, trigger reason, related group/topic/partition, last successful collection timestamp, and last clear timestamp.

This lets health endpoints and incident logs explain **why** the service is degraded.

## 11. Integrating with Spring Boot Actuator

Spring Boot Actuator provides health infrastructure. Applications can create a custom `HealthIndicator` to expose lag policy status on the health endpoint.

Example:

~~~java
@Component("kafkaConsumerLag")
public class KafkaConsumerLagHealthIndicator
        implements HealthIndicator {

    private final LagSnapshotProvider snapshots;
    private final LagPolicyEvaluator evaluator;

    public KafkaConsumerLagHealthIndicator(
            LagSnapshotProvider snapshots,
            LagPolicyEvaluator evaluator) {
        this.snapshots = snapshots;
        this.evaluator = evaluator;
    }

    @Override
    public Health health() {
        LagSnapshot snapshot = snapshots.latest();
        LagEvaluation evaluation = evaluator.evaluate(snapshot);

        if (evaluation.state() == LagState.UNKNOWN) {
            return Health.unknown()
                    .withDetail("reason", evaluation.reason())
                    .build();
        }

        if (evaluation.state() == LagState.CRITICAL) {
            return Health.outOfService()
                    .withDetail("reason", evaluation.reason())
                    .withDetail("totalLag", snapshot.totalLag())
                    .withDetail(
                            "maxPartitionLag",
                            snapshot.maxPartitionLag())
                    .build();
        }

        return Health.up()
                .withDetail("lagState", evaluation.state().name())
                .withDetail("totalLag", snapshot.totalLag())
                .withDetail(
                        "maxPartitionLag",
                        snapshot.maxPartitionLag())
                .build();
    }
}
~~~

`LagSnapshotProvider` and `LagPolicyEvaluator` are application-defined abstractions. The snippet uses `Health.unknown()`, `Health.outOfService()`, and `Health.up()`; verify the exact API and health status mapping of your Spring Boot version.

### 11.1. HealthIndicator must be fast

`health()` should only read a previously collected snapshot. Never run `AdminClient` network calls, database queries, or synchronous partition scans inside a health request.

If a health check is slow, the probe itself can time out and make orchestration mark the instance unhealthy even when the only issue is a blocked health endpoint.

### 11.2. Warning does not have to return DOWN

In the example, `WARNING` still returns `UP` with detail `lagState=WARNING`. You can substitute a custom status or separate health group if needed. What matters is that the policy distinguishes:

- Warning: investigate, but the instance can still process.
- Critical: readiness fails if the service should stop receiving more traffic/work.
- Unknown: insufficient data to conclude.

Do not turn every warning into `DOWN` if doing so triggers scaling/restart storms.

## 12. Including lag health in the readiness group

With Spring Boot Actuator supporting health groups/probes, a custom indicator can be added to readiness:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,kafkaConsumerLag
        liveness:
          exclude: kafkaConsumerLag
~~~

Example configuration for Spring Boot versions supporting health probes/groups. Verify exact property names and default groups for your project version.

When the lag indicator returns `OUT_OF_SERVICE`, the readiness group can mark the instance unready per status mapping. This only has effect if the orchestrator actually calls the corresponding readiness probe.

### 12.1. Readiness DOWN does not automatically pause Kafka listeners

Readiness typically governs whether a pod receives traffic via a Kubernetes Service. It **does not automatically stop Kafka consumers**. If critical lag requires stopping new record intake, a separate pause/backpressure mechanism is needed, keeping in mind that pausing can cause lag to keep growing.

Within a consumer group, removing a pod from an HTTP Service does not automatically change Kafka partition assignments either.

### 12.2. Lag exceeding threshold should not always mark readiness DOWN

For example, a service may be draining a large backlog while sustaining strong throughput. If every pod transitions to NotReady together, the system might strip consumers from service/orchestration policies, shrinking capacity and worsening lag.

Before wiring lag into readiness, answer:

- Does a NotReady pod stop its consumer?
- Does the deployment autoscaler scale based on readiness?
- If all pods go NotReady, can the system self-recover?
- Could lag drain faster by keeping consumers running?

For many worker services, it is better to base process readiness on ability to serve while paging/alerting when consumer lag breaches SLO. Readiness should fail only when an instance genuinely should not receive more work or cannot fulfill its role.

## 13. Do not use consumer lag directly as a liveness probe

**Liveness** determines whether a process should be restarted. Lag is a group backlog that can rise due to producer bursts or low downstream capacity. Restarting a pod does not make backlog vanish and can trigger rebalances.

Do not do:

~~~text
if consumerLag > threshold:
    liveness = DOWN
    restart pod
~~~

If all replicas experience high lag simultaneously, coordinated restarts destabilize the consumer group and lengthen processing delays.

### 13.1. Liveness should reflect whether the process can continue on its own

Better signals for liveness:

- JVM deadlocks / unrecoverable internal states.
- Main application process unresponsive.
- A verified, unrecoverable critical internal loop.

Consumer thread liveness can have its own health component. However, a consumer made non-responsive by a transient dependency does not necessarily require immediate restart; timeouts, circuit breakers, and recovery can be more effective.

### 13.2. Readiness, liveness, and alerts are not the same

| Mechanism | Goal | How should a lag breach affect it? |
|---|---|---|
| Alert | Notify operators | Can trigger `WARNING`/`CRITICAL` per SLO |
| Readiness | Decide if the instance accepts more traffic/work | Fail only if policy says the instance is unready |
| Liveness | Decide whether to restart the process | Never fail solely for a large backlog |
| Autoscaling | Adjust capacity | Can use lag trend/age and throughput, with cooldowns |
| Backpressure | Throttle input/delivery | Pause/resume by resource state, not lag alone |

## 14. Lag thresholds with multiple consumer instances

A consumer group can span multiple pods. Lag is group/partition state, not owned by a single pod.

~~~text
                    orders-worker group
                           |
          +----------------+----------------+
          |                |                |
          v                v                v
        pod A            pod B            pod C
      partitions 0      partitions 1      partitions 2
      and 3
~~~

If every pod queries total group lag and feeds it into readiness, one breach forces all pods NotReady simultaneously. If orchestration or deployment policies evict them, consumer capacity drops right when it is needed most.

### 14.1. Local health and group health

Distinguish:

- **Local health:** are the consumer threads/containers inside this pod running properly?
- **Group health:** is the whole group keeping up with data and meeting SLOs?

Lag thresholds are normally **group health**. Consumer thread liveness and listener runtime are **local health**.

Do not mechanically feed group-level backlog into every pod's local liveness.

### 14.2. A central signal can be a better fit

For large groups, compute group lag centrally in a monitoring/health service to emit alerts or autoscaling signals. Each pod still tracks local container state. This avoids every pod repeating identical group offset queries and making conflicting decisions.

## 15. Health during startup grace periods

Immediately after deployment:

- Consumers may not have finished assignment.
- Exporters may not have their first sample.
- Group offsets may not be created yet.
- Producers may not have emitted data yet.
- New consumers may lack committed offsets.

Do not treat missing snapshots at startup as `lag = 0` or `critical`. Policies need a startup grace period:

~~~text
container starts
      |
      v
startup grace period
      |
      +--> lag sample not ready: STARTING / UNKNOWN
      |
      v
valid snapshots available
      |
      v
evaluate warning/critical thresholds
~~~

The grace period must be long enough for normal startup, yet short enough not to mask misconfigurations that prevent consumers from ever receiving partitions.

### 15.1. New consumer groups

A group with no committed offset yet can be initialized via `auto.offset.reset` when reading starts. Exporter lag calculations may show missing/unknown until offsets are established.

Never default a new group to lag 0. Distinguish:

- No offsets and no assignment yet.
- Group starting from `earliest` with existing backlog.
- Group starting from `latest` with no new records yet.
- Exporter not yet collecting data.

## 16. Retries, DLTs, and shifted lag

When a listener fails to process:

~~~text
orders.events
     |
     | retry/recover
     v
orders.events-retry
     |
     | retries exhausted
     v
orders.events-dlt
~~~

Main-topic lag can drop as records move to a retry topic, yet the business event has still not completed.

If only `orders.events` is wired into the health indicator, the service can report `UP` while retry-topic backlog grows huge.

### 16.1. Track all stages

For workflows with retries/DLTs, health policies should explicitly account for:

- Main consumer group lag.
- Retry consumer group lag.
- Oldest retry event age.
- DLT count/age and manual handling time.
- Business event completion age.

Do not sum lags across multiple topics/groups as unique event counts if the same event can appear in multiple stages.

### 16.2. DLT lag is not always a critical backlog

A DLT may be designed to wait for operator review. Zero records in a DLT is a healthy sign; if records exist, severity depends on business type and SLA. A rule like `DLT lag > 0 => DOWN` usually misfires for intentional quarantine workflows.

## 17. Lag thresholds while a consumer is paused

Spring Kafka pause/resume can protect downstream when queues or databases overload. While a container is paused:

- Producers keep writing to Kafka.
- Consumers stop delivering new records to listeners per pause mechanics.
- Lag can increase.
- This may be an intentionally controlled state.

If a health indicator marks `DOWN` merely because lag rises during maintenance, readiness/alerts misrepresent policy.

### 17.1. Include pause reason in evaluation

Snapshots or policy context should know:

- Whether the container is paused.
- Pause reason (maintenance, queue full, dependency unhealthy).
- When the pause started.
- Maximum permitted pause duration.
- Whether backlog remains within retention/freshness budgets.

Intentional pause does not mean ignoring every threshold. If a pause extends beyond the maintenance window or oldest record age breaches SLA, alerting is still required.

### 17.2. High lag after resume

Right after resuming, backlog can remain large while the consumer catches up. Do not immediately flip critical just because the first snapshot is still high; watch lag growth rate and drain rate.

If lag drops steadily and oldest age is draining, status can be `warning` rather than `critical` depending on SLA. If lag keeps climbing despite resuming, capacity or downstream is still insufficient.

## 18. Prometheus and Grafana: example threshold queries

Metric names depend on the exporter. The queries below apply only if your metrics endpoint actually exports series with matching names and labels.

### 18.1. Total lag by group/topic

Assuming the exporter exposes `kafka_consumergroup_lag`:

~~~promql
sum by (consumergroup, topic) (
  kafka_consumergroup_lag{
    consumergroup="orders-worker",
    topic="orders.events"
  }
)
~~~

### 18.2. Maximum partition lag

~~~promql
max by (consumergroup, topic) (
  kafka_consumergroup_lag{
    consumergroup="orders-worker",
    topic="orders.events"
  }
)
~~~

### 18.3. Lag growth over a window

Lag is a gauge, not a counter. You can use `delta` over a window to evaluate change:

~~~promql
delta(
  kafka_consumergroup_lag{
    consumergroup="orders-worker",
    topic="orders.events"
  }[5m]
)
~~~

A positive delta indicates lag at the end of the window is higher than at the start across available samples; account for rebalances, offset resets, missing samples, and exporter restarts.

### 18.4. Sustained alert condition

Example alert structure:

~~~yaml
groups:
  - name: kafka-consumer-health
    rules:
      - alert: KafkaConsumerLagCritical
        expr: |
          sum by (consumergroup, topic) (
            kafka_consumergroup_lag{
              consumergroup="orders-worker"
            }
          ) > 10000
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Kafka consumer lag is above the critical threshold"
          description: "Check partition lag, input rate and processing throughput."
~~~

Metric names, labels, and group syntax are examples; verify against your actual exporter before deploying. The 10,000 threshold and 2-minute duration are illustrative only.

### 18.5. Alert separately when metrics are stale

A lag threshold alert cannot be trusted if the exporter stopped scraping. Create separate alerts for target down, stale sample timestamps, disappearing metric series, and `AdminClient` collection failures.

Never interpret "no lag metric" as "lag = 0."

## 19. HealthIndicator reads snapshots instead of querying Kafka

A suitable architecture:

~~~text
Scheduled lag sampler
        |
        v
Kafka AdminClient / exporter metrics
        |
        v
LagSnapshotProvider (cache)
        |
        +--> lag policy evaluator
        |
        v
HealthIndicator
        |
        v
Actuator readiness group
~~~

The sampler can run every few seconds or at a cadence suited to volume and partition count. The health endpoint simply reads the latest snapshot and evaluates state rapidly.

### 19.1. Separate collection from evaluation

Two distinct responsibilities:

- **Collection:** call `AdminClient`/metrics source, compute lag, attach timestamp, handle timeouts.
- **Evaluation:** apply thresholds, sustained breach, hysteresis, startup grace, and maintenance policies.

This lets you unit-test threshold logic without a broker and test the collector separately with Kafka integration tests.

### 19.2. Snapshots must be consistent from a single collection

Do not mutate individual partitions inside a shared map piecemeal while health checks read half old and half new data. Build a complete immutable snapshot and atomically replace the reference after collection succeeds.

If collection succeeds only partially, mark the snapshot partial/unknown or record the error per policy; never assume missing partitions have lag 0.

## 20. Example LagSnapshotProvider and HealthIndicator

An application-defined interface:

~~~java
public interface LagSnapshotProvider {
    LagSnapshot latest();
}
~~~

Snapshot:

~~~java
public record LagSnapshot(
        String groupId,
        String topic,
        long totalLag,
        long maxPartitionLag,
        Duration oldestRecordAge,
        Instant observedAt,
        boolean complete) {
}
~~~

The health indicator can check freshness and critical breaches:

~~~java
@Component("kafkaConsumerLag")
public class KafkaLagHealthIndicator implements HealthIndicator {

    private final LagSnapshotProvider snapshots;
    private final Duration maxSnapshotAge = Duration.ofSeconds(30);
    private final long criticalLag = 10_000;
    private final Duration criticalAge = Duration.ofSeconds(60);

    public KafkaLagHealthIndicator(LagSnapshotProvider snapshots) {
        this.snapshots = snapshots;
    }

    @Override
    public Health health() {
        LagSnapshot snapshot = snapshots.latest();

        if (snapshot == null || !snapshot.complete()) {
            return Health.unknown()
                    .withDetail("reason", "lag_snapshot_unavailable")
                    .build();
        }

        Duration snapshotAge =
                Duration.between(snapshot.observedAt(), Instant.now());

        if (snapshotAge.isNegative()
                || snapshotAge.compareTo(maxSnapshotAge) > 0) {
            return Health.unknown()
                    .withDetail("reason", "lag_snapshot_stale")
                    .withDetail("snapshotAge", snapshotAge.toString())
                    .build();
        }

        boolean critical =
                snapshot.totalLag() >= criticalLag
                || snapshot.oldestRecordAge()
                        .compareTo(criticalAge) >= 0;

        if (critical) {
            return Health.outOfService()
                    .withDetail("group", snapshot.groupId())
                    .withDetail("topic", snapshot.topic())
                    .withDetail("totalLag", snapshot.totalLag())
                    .withDetail(
                            "maxPartitionLag",
                            snapshot.maxPartitionLag())
                    .withDetail(
                            "oldestRecordAge",
                            snapshot.oldestRecordAge().toString())
                    .build();
        }

        return Health.up()
                .withDetail("totalLag", snapshot.totalLag())
                .withDetail(
                        "maxPartitionLag",
                        snapshot.maxPartitionLag())
                .build();
    }
}
~~~

This is a structural example omitting sustained breach/hysteresis and using illustrative thresholds. In production, values should live in validated configuration; `Instant.now()` can be abstracted with `Clock` for deterministic testing. Handle future timestamps caused by clock skew.

### 20.1. Do not use this sample code as a complete threshold policy

A health check comparing an instantaneous snapshot against a threshold can flap. For production readiness, add:

- Sustained breach duration.
- Clear threshold lower than enter threshold.
- Startup grace.
- Maintenance/pause reasons.
- Stale/partial snapshots.
- Partition-specific thresholds.
- Distinction between warning and critical.

## 21. Customizing status mapping

Spring Boot Health includes standard statuses such as `UP`, `DOWN`, `OUT_OF_SERVICE`, and `UNKNOWN`. When a health group drives readiness, verify which statuses map to HTTP 200/503 under your configuration/version.

If defining a custom status like `DEGRADED`, configure status ordering and mappings appropriately. Otherwise Actuator may handle the custom status unexpectedly.

A simple choice:

- `UP`: within limits.
- `OUT_OF_SERVICE`: critical; the instance should not receive more traffic per readiness policy.
- `UNKNOWN`: insufficient data.

However, `UNKNOWN` does not automatically carry the same meaning as `DOWN` in every probe. Confirm orchestrator behavior with integration tests or by inspecting live endpoints.

## 22. Lag-based autoscaling differs from health readiness

Lag can serve as a scaling signal for consumer groups:

- Lag grows continuously.
- Producer rate exceeds consumer success rate.
- Unassigned capacity exists across partitions.
- Downstream has headroom for extra load.

Yet scaling does not always help:

- Consumer count already equals or exceeds partition count.
- The database connection pool is already full.
- Downstream is rate-limiting.
- A hot partition limits parallelism.
- Consumer tasks are blocked on the same dependency.

### 22.1. Scale on lag and throughput

A better autoscaling policy combines:

~~~text
scale_out when:
  lag growth is sustained
  AND oldest record age is rising
  AND downstream has capacity
  AND additional partitions can be assigned
~~~

Scale in when backlog stabilizes below the clear threshold, consumers hold no critical in-flight tasks, and sufficient headroom remains for traffic bursts.

### 22.2. Cooldowns and rebalance cost

Every scale event can trigger a rebalance, disrupting processing and briefly raising lag. Use cooldowns, stabilization windows, and bounded scale steps to prevent oscillation.

Never use readiness `DOWN` as the sole autoscaler signal if all pods get marked unready simultaneously from group lag.

## 23. Lag exceeding threshold during deployments

Rolling deployments can stop old consumer instances and yield partitions, start new consumers awaiting assignment, briefly pause some processing during rebalances, raise lag temporarily, and shift metric exporter series across instances.

Health policies should recognize deployment/rollout state or use sustained windows sensible enough not to page on every brief rebalance.

However, if lag keeps rising after the group stabilizes, investigate regressions in startup, concurrency, deserializers, databases, or processing times.

### 23.1. Do not ignore all lag during rollouts

A prolonged deployment can push backlog past freshness SLAs. Startup grace is not an excuse to ignore lag forever. Set a maximum rollout duration and maximum allowable lag age in maintenance policies.

## 24. Lag thresholds and retention

Kafka retention limits how long or how much data is kept. If a backlog sits too long, older data can be deleted before consumers process it.

When evaluating critical lag, consider:

- Topic retention time/size.
- Oldest record age relative to retention.
- Expected drain speed.
- Ability to add capacity.
- Replay from archive/object storage if available.

A lag of 100,000 records may be acceptable if consumers catch up in 2 minutes and retention is long; a lag of 5,000 records can be critical if the oldest record is minutes away from expiration.

### 24.1. Lag does not prove data still exists

If the log start offset has moved past the committed offset, consumers can no longer read some older records. Detect retention gaps and never report "backlog is 0" if group offsets were reset or data expired.

Never automatically reset group offsets just to turn health status green. Skipping records requires an explicit business decision and audit trail.

## 25. Observability: dashboards and alerts

A lag health dashboard should include:

| Panel | Purpose |
|---|---|
| Total committed lag by group/topic | Total backlog |
| Max lag by partition | Detect hot partitions |
| Lag growth rate | Show whether backlog is growing or draining |
| Oldest record age | Measure freshness/SLA |
| Producer arrival rate | Input pressure |
| Business success throughput | Real processing capacity |
| Consumer active members/assignments | Group membership |
| Retry topic lag / DLT count | Backlog on recovery paths |
| Pause state and duration | Backpressure/maintenance |
| Snapshot age / collection errors | Metric reliability |
| Readiness status | Impact on orchestration |

### 25.1. Alert on combined conditions

A critical alert may require lag above the critical threshold, persisting for at least a duration, oldest age breaching freshness SLA or continuously positive lag growth, absence of approved planned maintenance, and a fresh snapshot.

Do not alert solely on an instantaneous lag number.

### 25.2. Alert separately on stale metrics

If the lag collector stops working, lag threshold alerts may stay silent even as backlog grows. Maintain separate alerts for excessive snapshot age, `AdminClient` collection failures, exporter scrape failures, and missing group/topic series.

Observability failures must be detected as their own incidents.

## 26. Runbook: lag exceeds warning threshold

1. Identify the exact consumer group and topic.
2. Check total lag, max partition lag, and trends over a time window.
3. Confirm the lag snapshot is fresh.
4. Compare producer arrival rate with business completion throughput.
5. Check oldest record age and freshness SLO.
6. Check consumer group state, active members, and partition assignments.
7. Check pause/maintenance state.
8. Check retry topics/DLTs if main-topic lag is dropping unusually fast.
9. Check DB/HTTP latency and consumer errors.
10. Monitor drain rate; escalate severity if backlog keeps growing or age exceeds SLA.

A warning may simply reflect a normal traffic burst. Do not scale or restart before identifying the bottleneck.

## 27. Runbook: lag exceeds critical threshold

1. Confirm the threshold breach across multiple samples or an independent metric source.
2. Identify which partitions contribute most to the backlog.
3. Verify whether the consumer group has active members and assignments.
4. Check records consumed rate and business success rate.
5. Check listener exceptions, retries, DLTs, and transaction aborts.
6. Check consumer thread liveness and thread dumps if poll progress stopped.
7. Check downstream capacity, connection pools, and timeouts.
8. Estimate catch-up time from net drain rate.
9. Choose action: restore dependencies, add capacity, throttle input, or pause per policy.
10. Monitor lag age and completion throughput until below the clear threshold.

Never reset offsets to make a dashboard green and never restart the whole group before identifying the root cause.

## 28. Runbook: lag is high yet decreasing

1. Confirm lag growth rate is steadily negative.
2. Confirm oldest record age is decreasing or no longer rising.
3. Check business success rate.
4. Confirm the consumer group is not rebalancing continuously.
5. Check whether estimated catch-up time fits the recovery objective.
6. Keep warnings/incidents open until clear conditions are satisfied.
7. Avoid scaling in before backlog recovers.

High yet draining lag can be normal recovery. Severity should reflect both backlog level and trend.

## 29. Runbook: readiness DOWN due to lag

1. Identify which indicator caused the readiness group to fail.
2. Check health details: group, topic, total lag, max partition lag, oldest age.
3. Confirm the lag snapshot is not stale.
4. Confirm readiness `DOWN` is truly required for this service.
5. Check whether NotReady reduces consumer capacity or impacts orchestration.
6. If the consumer can still drain backlog, consider a more suitable readiness/alert policy.
7. If the instance genuinely cannot take work, fix the root cause and confirm clear thresholds before returning readiness `UP`.

Readiness is a decision about accepting work, not a mirror of the lag dashboard.

## 30. Runbook: lag collector or health indicator returns UNKNOWN

1. Check the timestamp of the last snapshot.
2. Check `AdminClient`/exporter availability.
3. Check timeouts, ACLs, and permissions to read group offsets.
4. Check whether the group/topic exists and has committed offsets yet.
5. Check for partial partition results.
6. Check clock skew or future timestamps.
7. Confirm the health endpoint reads cache rather than calling brokers synchronously.
8. Restore metrics collection.
9. Cross-check with Kafka CLI/Admin tools if needed.

`UNKNOWN` does not mean lag is 0. In critical services, unavailable observability may warrant its own alert without necessarily restarting consumer processes.

## 31. Runbook: lag concentrated on one partition

1. Find the top lagging partition.
2. Compare input rates per partition.
3. Identify the consumer member assigned to that partition.
4. Inspect hot keys and key distribution.
5. Measure processing time/error rate for the associated events.
6. Check for a poison pill or blocking retry at the head of the partition.
7. Identify ordering requirements before altering partition strategy.
8. If adding partitions, assess key remapping and ordering for future events.
9. Monitor max partition lag after changes.

Adding replicas will not help a hot partition if downstream or ordering only permits sequential processing.

## 32. Testing lag thresholds and readiness

Do not test only arithmetic comparisons. Also test missing data, stale snapshots, hysteresis, and health endpoint behavior.

### 32.1. Unit-testing the policy evaluator

Cases:

1. Lag below warning: `NORMAL`.
2. Lag exceeds warning for one sample: no transition yet if sustained breach is required.
3. Lag exceeds warning long enough: `WARNING`.
4. Lag exceeds critical long enough: `CRITICAL`.
5. Lag drops below clear threshold for one sample: retain state if clear duration is unmet.
6. Lag stays steadily below clear threshold: `NORMAL`.
7. Stale/partial snapshot: `UNKNOWN`.
8. Oldest age breaches SLO even with low total lag: `CRITICAL` if specified by policy.
9. Partition lag breaches threshold even before total breaches: state per partition policy.
10. Valid pause/maintenance: state per maintenance policy.

### 32.2. Testing HealthIndicator

1. Inject a `NORMAL` snapshot and verify `UP`.
2. Inject a `WARNING` snapshot and verify health details reflect warning per policy.
3. Inject `CRITICAL` and verify the corresponding status.
4. Inject `UNKNOWN`/stale and verify it is not interpreted as lag 0.
5. Verify the `health()` method makes no network/`AdminClient` calls.
6. Measure indicator response time against the snapshot cache.

### 32.3. Testing the readiness group

1. Enable Actuator health probes.
2. Include `kafkaConsumerLag` in the readiness group per config.
3. Verify `UP`/`OUT_OF_SERVICE`/`UNKNOWN` map as expected.
4. Verify the liveness group is not pulled `DOWN` by the lag indicator.
5. Test the exact endpoint path the orchestrator calls.

### 32.4. Integration-testing the collector

1. Create a test topic and consumer group.
2. Send records to create a controlled backlog.
3. Collect committed offsets and end offsets.
4. Verify lag snapshot per partition.
5. Consume records and verify lag decreases.
6. Simulate `AdminClient` timeout or missing offsets.
7. Verify snapshots are marked stale/unknown, never 0.

### 32.5. Testing bursts and recovery

1. Send a burst exceeding consumer capacity.
2. Verify warning/critical transitions over the sustained window.
3. Add capacity or reduce producer input.
4. Verify positive net drain rate.
5. Verify state clears only after the hysteresis duration.

## 33. Common mistakes

**Using one fixed threshold for all topics.** Workloads, SLAs, and record costs differ.

**Looking only at total lag.** A hot partition can be hidden inside the sum.

**Marking DOWN on a single sample exceeding threshold.** Rebalances, batch commits, and brief bursts cause flapping.

**Omitting a clear threshold.** Health status flickers repeatedly around the same boundary.

**Treating low lag as business completion.** Backlog may reside in retry topics or worker queues.

**Using lag as a liveness probe.** Restarts do not erase backlogs and can trigger group rebalances.

**Adding group lag to every pod's readiness without evaluating impact.** All replicas can go NotReady together and shrink capacity.

**Calling AdminClient on every health request.** The health endpoint slows down and creates query storms.

**Treating missing metrics as lag 0.** Hides observability failures.

**Ignoring startup grace and new groups.** Offsets/assignments may not be ready yet.

**Treating DLT lag = 0 as a mandatory target.** A DLT may be an intentional review queue.

**Ignoring retry lag.** The main topic may look clear while events remain unfinished.

**Scaling consumers without checking downstream.** Can overload databases/HTTP services further.

**Resetting offsets to turn health green.** Can silently skip unprocessed data.

## 34. Implementation checklist

### Lag definition and thresholds

- [ ] Clearly documented committed lag, fetch lag, or LSO lag.
- [ ] Both total lag and max partition lag are tracked.
- [ ] Lag growth rate and oldest record age are tracked.
- [ ] Thresholds are based on arrival rate, capacity, and SLOs.
- [ ] Warning/critical and enter/clear thresholds exist.
- [ ] Sustained breach duration and hysteresis are configured.
- [ ] Startup grace and maintenance policies exist.

### Data collection

- [ ] Lag source has timeouts and proper permissions to read offsets.
- [ ] Snapshots include observed timestamp and completeness flag.
- [ ] Missing/stale data becomes `UNKNOWN`, never 0.
- [ ] Health endpoint reads cache instead of querying brokers synchronously.
- [ ] Total lag is aggregated consistently across group/topic/partitions.

### Health and orchestration

- [ ] `HealthIndicator` evaluates only the defined policy.
- [ ] Readiness group includes lag only when justified by business logic.
- [ ] Liveness does not fail solely due to high lag.
- [ ] Spring Boot status mapping has been verified.
- [ ] Impact of NotReady on consumer capacity has been evaluated.
- [ ] Separate alert exists for stale metrics collectors.

### Recovery and testing

- [ ] Dashboards cover lag, age, input rate, and business success rate.
- [ ] Retry/DLT and pause states are visible in observability.
- [ ] Runbooks exist for warning, critical, stale metrics, and hot partitions.
- [ ] Tested sustained breach, hysteresis, and clearing.
- [ ] Tested readiness and liveness independently.
- [ ] Tested `AdminClient`/exporter failures.
- [ ] Offsets are never reset outside approved replay workflows.

## Conclusion

**Lag exceeding threshold** is a signal about a consumer group's ability to keep pace with data processing rate and latency goals. Turning it into a useful health/readiness policy requires defining the exact lag type, measuring at group and partition levels, and pairing total/max lag with lag age and backlog growth rate. Thresholds must reflect real SLOs and capacity; sustained breaches, hysteresis, startup grace, and snapshot freshness reduce false alarms.

In Spring Boot, you can wire the policy into a custom `HealthIndicator`, provided the indicator reads periodically collected snapshots rather than querying Kafka on every health request. Readiness should fail only when an instance truly should not accept more work; high lag is not a reason to automatically restart processes or mark every pod NotReady. Finally, monitor retry/DLT topics, pauses, transactions, and business completions too, because backlog can shift off the main topic while business work remains unfinished. **A good threshold drives the right recovery action; a single lag number alone cannot determine the health of an entire pipeline.**
