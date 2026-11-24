# SLOs, SLAs, and Operational Metrics

## 1. Why Measure Kafka Reliability?

In a Spring Kafka system, the fact that brokers are running is not enough to conclude the service is healthy. The application may publish records successfully while consumers process slowly; consumers may read data yet fail when writing to the database; or the cluster may still have active brokers while several critical partitions lack a leader.

Therefore, operations must measure event flow quality from the perspective of the application and users. SLO targets help teams align on the quality level to maintain. SLAs turn part of that commitment into customer obligations. Operational metrics provide the data to detect, explain, and resolve issues.

An event flow typically has these stages:

1. The Spring application publishes an event via the Kafka producer.
2. The producer sends the record to the partition leader.
3. The broker acknowledges the record according to acknowledgement and replication configurations.
4. The consumer receives the record, executes business logic, and persists results to the target system.
5. The consumer commits the offset after processing according to the application's delivery semantics.

Each stage can fail independently. For example, a producer receiving an acknowledgement only indicates Kafka confirmed the record under current settings; it does not prove the consumer finished business processing. When designing SLIs and SLOs, clearly state which stage is being measured and what is guaranteed.

## 2. Distinguishing Metric, SLI, SLO, SLA, and Error Budget

These concepts are related yet serve different roles.

| Concept | Meaning | Example in Spring Kafka |
|---|---|---|
| Metric | Measured value over time or per event | Consumer lag, producer request latency, failed record count |
| SLI (Service Level Indicator) | Indicator representing service quality experienced by users | Percentage of events processed successfully within 60 seconds |
| SLO (Service Level Objective) | Quantitative target for an SLI over a time window | 99% of events processed within 60 seconds over a 7-day window |
| SLA (Service Level Agreement) | Agreed quality commitment with customers, typically with measurement rules, exclusions, and remedies | Monthly availability commitment with service credits if missed |
| Error budget | Allowable level of errors or disruption under an SLO | For a 99.9% SLO, the error budget is 0.1% within the measurement window |

A technical metric is not automatically an SLI. For instance, broker CPU is a useful metric for diagnosing load, but users do not directly perceive CPU. The rate of successful publish requests or the time for an event to reach the target system usually reflects user experience more clearly.

Business KPIs also differ from SLIs. Daily order count may be a KPI; the percentage of order events processed on time may be an SLI for the event platform supporting that KPI.

### Relationships Between the Concepts

- Metrics are the raw input data.
- SLIs turn that data into a clearly defined quality measurement.
- SLOs set targets for SLIs and establish the basis for managing error budgets.
- SLAs select specific commitments to formalize with customers.
- Dashboards, alerts, and incident workflows use SLIs alongside supporting metrics to operate the service.

Internal SLOs usually need to be tight enough for teams to act before breaching an SLA. The exact margin depends on the service and agreement; no single ratio applies to every system.

## 3. Choosing Kafka-Appropriate SLIs

Start from critical application journeys: which events must be published, where they must arrive, within what time, and what counts as successful processing. Only then choose technical metrics to explain outcomes.

### 3.1. Producer Availability and Publish Success

A common SLI is the proportion of valid publish operations successfully acknowledged by Kafka:

[
SLI_{publish} =
\frac{\text{good publish operations}}
{\text{total valid publish operations}}
\times 100%
]

You must define "good publish operation." One definition could be a record successfully acknowledged with latency not exceeding a chosen threshold. The denominator must include valid operations that failed due to timeouts, broker errors, or network errors; counting only successful requests makes the SLI look artificially good.

For producers with retries, distinguish one logical business operation from client-layer resend attempts. Counting every retry as an independent operation inflates the denominator. Pick a consistent measurement point, such as treating each application input event as one logical publish operation.

Supporting metrics typically include:

- Successful and failed record send counts.
- Producer error rate and retry rate.
- Request latency, record queue time, and batch size.
- Buffer available bytes and buffer exhaustion count.
- Timeouts, metadata errors, or authentication failures.

### 3.2. Publish Latency

Latency should be measured with histograms to observe distributions and tail values. p50 indicates typical experience; p95 and p99 reveal slow request tails that averages can hide.

Distinguish latency types:

- Producer request latency: time the client waits for a response from the broker.
- Publish completion latency: time from when the application initiates sending an event until receiving the send result.
- End-to-end latency: time from when an event is created or broker-received until consumer business logic completes.

These measurements answer different questions. Do not substitute producer request latency for end-to-end latency if the service commitment covers complete event processing.

### 3.3. Consumer Lag and Event Freshness

Consumer lag is typically calculated by offset count:

[
Lag_{records} = LogEndOffset - CommittedOffset
]

Rising lag indicates the consumer is falling behind new data on the partition. However, the count of delayed records does not directly reveal how long events have been waiting. One partition may have thousands of records of lag yet drain quickly at high throughput; another partition may have small lag yet old events sitting idle for a long time.

Therefore, monitor all of the following:

- Lag by consumer group, topic, and partition.
- Age of the oldest unprocessed record, if measurable.
- Event freshness: time from when an event is accepted or written to Kafka until consumer processing completes.
- Event ingress rate and processing egress rate.
- Rebalance count, rebalance duration, and offset commit errors.

Event freshness usually aligns closer with user experience than offset lag. When measuring durations across multiple machines, synchronize clocks and standardize timestamp sources; skewed clocks can make measurements negative or significantly inaccurate.

### 3.4. Processing Success and Error Handling

For business flows, an SLI can be the percentage of events processed successfully within deadline:

[
SLI_{processing} =
\frac{\text{events completed successfully within deadline}}
{\text{valid events received}}
\times 100%
]

Explicitly state what "completed" means: business logic finished, data committed to the target system, or the consumer merely received the record. If an event is routed to a dead-letter topic (DLT/DLQ), it should normally not count as successful business processing. A DLQ is an error-isolation and investigation mechanism; it is not equivalent to fulfilling the original request.

Also track:

- Processing duration and error rate by error category.
- Retry counts, records sent to retry topics, and retry wait durations.
- DLQ ingress rate, backlog count, and age of the oldest record.
- Duplicate processing and idempotency conflicts.
- Commit failures and records processed but uncommitted.

If business rules permit compensating actions or accept an alternative terminal state, document that state explicitly in the SLI definition. Never alter the definition of "success" merely to make dashboards look better.

### 3.5. Broker, Partition, and Replication Health

These metrics help detect root causes affecting availability or durability:

| Metric | Operational Meaning |
|---|---|
| Offline partitions | Partitions with no available leader; investigate immediately for critical topics |
| Under-replicated partitions (URP) | Number of replicas not keeping up with the leader |
| ISR shrink/expand rate | Frequency at which replicas leave or rejoin the ISR |
| Leader election rate | Frequency of leader changes; spikes can cause disruptions |
| Active controller | Cluster controller status |
| Request handler/network processor idle | Idle capacity of request-handling and network pools |
| Bytes/messages in and out | Broker inbound/outbound throughput |
| Disk usage, disk latency, and network utilization | Resource pressure that can cause slow replication or requests |

Zero URP is a positive signal, yet it does not prove the entire business flow is healthy. Conversely, high CPU on a broker does not necessarily mean an SLO has been breached. Correlate infrastructure metrics with service SLIs.

### 3.6. Durability and Recoverability

Durability concerns the ability to retain acknowledged records. Settings commonly reviewed together include replication factor, `acks`, `min.insync.replicas`, producer idempotence, and leader election policies.

For example, with replication factor 3, producer `acks=all` and broker `min.insync.replicas=2` require at least two replicas in the ISR to acknowledge before a request succeeds. Here "all" refers to replicas currently in the ISR, not necessarily every originally configured replica. This configuration balances data durability and write availability when one replica fails, though it is not an absolute guarantee against data loss in every scenario.

Metrics and targets to consider:

- Confirmed acknowledged-record loss count.
- Recovery Point Objective (RPO): maximum committed data loss tolerance.
- Recovery Time Objective (RTO): target duration to restore service.
- Replica and partition recovery time after an incident.
- Results from recovery, failover, and disaster recovery tests.

Never claim an RPO of 0 based solely on `acks=all`. Evaluate topology, replication, leader election, storage, backups, operational procedures, and recovery test outcomes together.

## 4. Writing Measurable and Operable SLOs

A useful SLO must answer five questions:

1. **What is measured?** Choose an SLI tied to a journey or outcome users care about.
2. **What unit is counted?** Define events, requests, partitions, or time intervals.
3. **What counts as good?** Set explicit latency thresholds, success states, or deadlines.
4. **Where and over what window?** Choose data sources, topic/group scope, and measurement window.
5. **Who is accountable?** Assign an owner and response process when the SLO is at risk of breach.

Examples of starting SLOs for a critical event flow:

| SLI | Example Target | Interpretation |
|---|---|---|
| Publish success | At least 99.95% of valid logical publishes acknowledged within 250 ms, over a 30-day rolling window | Measures publish operations on the application side |
| Event freshness | At least 99% of events fully processed within 60 seconds, over a 7-day rolling window | Measures from an agreed event receipt timestamp until processing completion |
| Processing success | At least 99.9% of valid events complete business processing within 5 minutes | DLQ and terminal errors do not count as successes |
| Write availability | At least 99.9% of one-minute intervals where critical partitions accept writes | Fits when a time-based SLI is needed |
| Durability | Zero confirmed loss of acknowledged records; every incident recorded and investigated | Tracked as a data-protection goal alongside RPO/RTO if applicable |

The numbers above are illustrative examples showing how to write targets. They are not default commitments for every cluster. Use actual baselines, flow criticality, recovery capability, and customer requirements to set targets.

### 4.1. Defining Good Events and Bad Events

Example publish SLO: "99.95% of valid publish operations acknowledged within 250 ms."

- Good event: valid logical publish receiving a successful acknowledgement within at most 250 ms.
- Bad event: failed publish or completion taking longer than 250 ms.
- Denominator: all valid logical publish operations within the measurement scope.
- Exclusion: exclude only cases explicitly defined in the SLO or SLA policy; never exclude system failures merely because they are hard to measure.

Defining the denominator matters as much as picking the target. Omitting timed-out requests, retried records, or failed events from the denominator without clear justification skews the SLI away from real quality.

### 4.2. Choosing the Measurement Window

The measurement window must fit its purpose:

- Short windows like 5 minutes or 1 hour aid rapid incident detection and burn-rate alerting.
- A 7-day window helps observe weekly trends.
- A 28- or 30-day window typically fits monthly target reporting.

Rolling windows prevent waiting until month-end to realize an SLO is at risk. If an SLA specifies calendar months, SLA reports must still follow the exact contractual window and rules.

### 4.3. Event-Based vs. Time-Based SLIs

Event-based SLIs divide good events by total events. This directly reflects request or message quality, though denominators and retries must be handled accurately.

Time-based SLIs divide compliant time intervals by total time intervals—for example, the percentage of minutes where critical partitions can still accept writes. This suits uptime-style availability, though a one-minute outage may impact very few or very many events depending on traffic. Do not mix both calculation styles in one SLO without stating it explicitly.

## 5. Error Budgets and Operational Usage

An error budget is the permissible quality degradation when an SLO does not require 100%.

With a 99.9% SLO:

[
ErrorBudget = 100% - 99.9% = 0.1%
]

If there are 1,000,000 logical events in the measurement window, the corresponding budget is 1,000 bad events. For a time-based 99.9% SLO over a 30-day month, the equivalent time budget is:

[
30 \times 24 \times 60 \times 0.001 = 43.2 \text{ minutes}
]

These two calculations apply to two different SLI types: one counts events, the other counts time.

### 5.1. Burn Rate

Burn rate indicates how fast the error budget is being consumed relative to the allowed rate:

[
BurnRate =
\frac{\text{observed error rate}}
{\text{SLO-allowed error rate}}
]

Suppose an SLO allows 0.1% errors. If a recent window observes 0.5% errors, the burn rate is 5x. If this rate persists, the budget will exhaust much sooner than expected.

Multiple windows can distinguish severe incidents from brief fluctuations:

- A short window detects fast burns requiring paging on-call.
- A longer window confirms whether the issue is sustained and large enough to threaten targets.
- Specific thresholds should be tuned based on traffic volume, measurement lag, and service severity.

### 5.2. Policies When the Error Budget Shrinks

Teams should agree beforehand on corresponding actions:

- When burn rate spikes: confirm impact, declare an incident if needed, find root cause, and mitigate blast radius.
- When budget drops significantly: review recent changes, prioritize reliability work, and evaluate release risk.
- When budget is exhausted: apply an internally agreed freeze on risky changes until a reliability recovery plan is in place.
- Post-incident: update timeline, root cause, mitigations, and lessons for SLOs or runbooks.

Error budgets bring release and reliability decisions onto a shared scale. They do not replace incident severity judgment; a rare bug causing data loss may demand immediate action even when plenty of total budget remains.

## 6. SLAs: Turning Targets into Customer Commitments

SLAs usually specify which services are covered, commitment levels, calculation methods, measurement windows, exclusions, notification duties, and remedies if missed. Remedies may be service credits or agreed support procedures.

When establishing an SLA for a Kafka platform or Spring Kafka service, clarify:

- **Service scope:** which clusters, topics, tenants, regions, and business flows are covered.
- **Availability definition:** based on publish requests, writable partitions, or fully processed events.
- **Thresholds and windows:** percentage targets, measurement periods, and aggregation rules.
- **Data sources:** which telemetry is authoritative and how data gaps are handled.
- **Exclusions:** announced maintenance, customer-side faults, or external dependencies, if specified by contract.
- **Notification and remedies:** reporting deadlines, service credit claim procedures, and support contacts.

A platform availability SLA does not automatically include a support team response-time SLA. Those are two separate commitments requiring separate definitions.

Internal SLOs can cover more dimensions than SLAs: publish success, event freshness, processing success, durability, and recovery time. SLAs should rely on metrics that are explainable, verifiable, and agreed upon with customers. Contractual terms must be reviewed by service owners and authorized teams before publication.

## 7. Designing Dashboards and Alerts

Dashboards must help on-call engineers quickly answer three questions: are users impacted, which flow is failing, and which metrics explain the cause.

### 7.1. Suggested Dashboard Layout

| Section | Content to Display |
|---|---|
| SLO overview | Current SLI, target, remaining error budget, and burn rate |
| Producer | Publish success, p95/p99 latency, retry/error rates, buffer availability |
| Broker | Offline partitions, URP, ISR changes, leader elections, request latency |
| Consumer | Lag by group/topic, event freshness, processing rate, rebalances, and commit errors |
| Failure handling | Retry topic ingress, DLQ ingress, DLQ backlog, and oldest record age |
| Capacity | Disk, network, CPU, request handler idle, throughput, and quota throttling |
| Incidents | Active incidents, start time, impacted flows, and runbook links |

Support filtering by environment, cluster, topic, and consumer group. Keep label sets controlled; never put event IDs, order IDs, customer IDs, or continuously varying values into metric labels, as doing so creates extreme cardinality.

### 7.2. Symptom- and Impact-Based Alerting

Prioritize alerting based on SLIs or burn rate. Use technical metrics to provide diagnostic context and guidance.

Examples:

- Dropping publish success or p99 latency breaching SLO: alert producer and broker owners.
- Worsening event freshness alongside rising consumer lag: inspect processing speed, downstream dependencies, and rebalances.
- Offline partitions appearing on critical topics: high-severity alert.
- Sustained rise in URP or ISR shrinks: inspect brokers, network, disks, and replication.
- DLQ ingress spike or aging backlog: investigate data errors, schemas, or processing logic.
- Disk filling up or sustained quota throttling: capacity warning before SLIs are directly hit.

Do not page on-call for every minor metric fluctuation. Alerts need thresholds, sustained durations, severity levels, owners, and runbooks. An alert without a clear action usually creates only noise.

## 8. Collecting and Computing Metrics

A Kafka observability stack typically combines multiple sources:

- **Broker JMX:** request, throughput, partition, replication, and broker resource data.
- **Producer/consumer client metrics:** latency, retries, errors, buffers, lag, and rebalances.
- **Application metrics:** business processing outcomes, event freshness, completed event counts, and DLQ.
- **Distributed tracing:** connecting producers, consumers, and downstream calls via trace or correlation IDs.
- **Logs:** error details for investigation; avoid logging sensitive payloads or secrets.

Exact metric names depend on Kafka version, Spring Kafka client version, exporters, and JMX mapping rules. Inspect actual scraped metrics before building dashboards on top of them.

### 8.1. Example Application-Emitted Metrics

Applications can define counters and histograms with low-cardinality labels:

| Example Metric | Type | Purpose |
|---|---|---|
| `kafka_publish_total` | Counter | Total valid logical publish operations |
| `kafka_publish_duration_seconds` | Histogram | Time to complete publish |
| `event_processing_total` | Counter | Events processed by outcome |
| `event_processing_duration_seconds` | Histogram | Event processing duration |
| `event_freshness_seconds` | Histogram | Latency from event receipt milestone to completion |

Labels like `topic`, `consumer_group`, `environment`, and `outcome` are usually controllable. Never use per-message unique IDs as labels. Place IDs in traces or controlled logs for investigation.

### 8.2. PromQL Examples

The queries below illustrate calculations. Assume the application emits a `kafka_publish_duration_seconds` histogram recording only successful publishes, while the `kafka_publish_total` counter counts all valid logical publish operations.

Publish success rate within at most 250 ms, over a 30-day window:

```promql
sum(increase(kafka_publish_duration_seconds_bucket{le="0.25"}[30d]))
/
sum(increase(kafka_publish_total[30d]))
```

p99 publish latency over 5 minutes:

```promql
histogram_quantile(
  0.99,
  sum by (le) (
    rate(kafka_publish_duration_seconds_bucket[5m])
  )
)
```

Consumer lag by group and topic, if the exporter provides metrics with matching names and labels:

```promql
max by (consumer_group, topic) (
  kafka_consumergroup_lag
)
```

Under-replicated partition count, if the exporter maps JMX to this metric:

```promql
max(kafka_server_replicamanager_underreplicatedpartitions)
```

These are exporter-schema-dependent examples, not mandatory metric names. For long windows like 30 days, Prometheus needs adequate retention or recording rules/long-term storage. Also verify how histograms handle errors, counter resets, and labels before using results for official SLO reports.

### 8.3. Instrumentation in Spring Kafka

At the application layer, place instrumentation around both send operations and business processing:

- Record publish start time and callback success/failure outcome.
- Measure duration from when the listener receives a record until business logic finishes.
- Record retries, terminal errors, and routing to a DLT.
- Mark processing success only after completion conditions are met.
- Use trace/correlation IDs to connect stages; keep metric labels aggregated.

If a consumer commits offsets before business logic completes, a "records read" metric will overstate quality. For asynchronous processing, explicitly define the completion milestone and corresponding commit mechanism.

## 9. Using Metrics to Diagnose Incidents

| Symptom | Check Next | Investigation Direction |
|---|---|---|
| Rising publish errors | Producer errors/retries, request latency, broker request queue, network | Determine whether the fault is client-side, broker-side, quota, or connectivity |
| Rising publish p99 | Broker request latency, batching, buffers, network, and partition load | Find bottlenecks by topic/partition and timestamp |
| Continuously rising consumer lag | Event ingress rate vs. processing rate, consumer instances, rebalances, downstream latency | Determine whether consumers lack capacity or downstream is slow |
| Poor event freshness despite small lag | Record age, processing duration, retry delays, and clock synchronization | Find events stalled for long periods or slow at a specific step |
| Rising URP or ISR shrinks | Broker health, disk/network, replication traffic, and broker logs | Identify replicas falling behind the leader |
| DLQ spike | Schema/version, payload validation, exception types, and retry policies | Identify poison messages or compatibility errors |
| Continuous rebalancing | Consumer logs, per-poll processing time, heartbeats, and membership | Find disconnected consumers or processing exceeding limits |
| Rapid disk growth | Retention, segment growth, throughput, and per-broker capacity | Forecast disk exhaustion and inspect partition balance |

Do not change timeouts, replication, or consumer concurrency wholesale based on a single chart. First identify which metrics changed, when it started, blast radius, and recent system changes. After recovery, document root cause and update runbooks.

## 10. Common Mistakes When Setting Goals

**Measuring only broker uptime.** Broker processes may be up while critical partitions cannot accept writes or consumers cannot process. Measure both requests and end-to-end outcomes.

**Using average latency as the sole standard.** Averages hide slow event tails. Use histograms and track p95/p99 alongside deadline compliance rates.

**Treating offset lag as delay time.** Lag is a record count, not seconds. Combine lag with event age/freshness and throughput.

**Leaving the denominator undefined.** Excluding failed requests, retries, or DLQ events from the denominator distorts SLIs. Explicitly specify logical operations, validity criteria, and exclusion rules.

**Counting retries as new events.** One event resent multiple times can skew success rates and traffic counts. Distinguish logical events from transport-layer attempts.

**Treating DLQ as success.** A DLQ isolates errors, yet usually represents incomplete business processing. Count a terminal state as success only when the business contract defines it as such.

**Setting 100% targets for every metric.** Absolute targets rarely yield useful operational decisions and can push teams to optimize the wrong things. Choose targets based on risk, baselines, and real needs; data-protection requirements specifically may be tracked as zero-incident goals.

**Alerting on every metric.** Too many alerts dull recognition of critical incidents. Tie alerts to impact, burn rate, owners, and next actions.

**Not validating measurement data quality.** Clock skew, dropped samples, label changes, counter resets, or insufficient retention can corrupt SLO reports. Add checks for the telemetry pipeline itself.

## 11. Periodic SLO Operations Process

A practical operational cycle can follow these steps:

1. Select critical Kafka flows and describe the outcomes the application must achieve.
2. Agree on SLI definitions, good/bad events, denominators, scope, and measurement windows.
3. Collect baselines across normal and peak traffic periods.
4. Choose appropriate SLOs, explicitly recording owners and authoritative data sources.
5. Build dashboards around SLIs; supplement with broker, producer, consumer, and downstream metrics for diagnostics.
6. Set up alerts on burn rates and severe symptoms.
7. During incidents, prioritize restoring service and reducing impact; then investigate root cause.
8. Periodically review SLIs, error budgets, incidents, architecture changes, and customer needs.

SLOs are not write-once-and-forget documents. When traffic, topology, business requirements, or dependencies change, measurement methods and targets must be revisited too. Version every definition change so reports remain comparable across periods.

## 12. Consolidated Example: Order Flow

Suppose a Spring Boot application publishes `OrderCreated` events to the `orders.created` topic. A consumer processes events to update the fulfillment system.

A measurement suite can be designed as follows:

| Stage | SLI | Supporting Metrics |
|---|---|---|
| Producer publishes event | Percentage of logical publishes acknowledged within 250 ms | Publish success, p99 latency, retry rate |
| Kafka stores and distributes | Percentage of time critical partitions are writable | Offline partitions, URP, ISR changes, leader elections |
| Consumer receives event | Percentage of events with freshness under 60 seconds | Consumer lag, oldest record age, records consumed rate |
| Fulfillment processing | Percentage of events completing business processing within 5 minutes | Processing success, processing duration, downstream errors |
| Exception handling | DLQ backlog detected and handled within operational deadline | DLQ ingress, backlog age, retry count |

Suppose over 30 days there are 2,000,000 valid logical publish operations. The publish SLO requires 99.95% success within 250 ms. The error budget is:

[
2,000,000 \times (1 - 0.9995) = 1,000 \text{ operations}
]

If 700 bad-event operations have occurred, the system has consumed 70% of its budget. Teams should examine burn-rate trends, failure timestamps, involved topics/partitions, and recent changes. If errors concentrate in the fulfillment consumer, the publish SLO may still pass while the processing SLO degrades. Two separate SLIs pinpoint the exact affected stage.

When reporting to customers, use only the measurements and rules documented in the SLA. Internal dashboards can provide additional metrics to help operations understand root causes and proactively maintain service quality.

## 13. Checklist for Putting an SLO into Production

- [ ] The SLI represents a meaningful outcome for the application or users.
- [ ] Good events, bad events, and the denominator are concretely defined.
- [ ] Logical events are distinguished from retry/transport attempts.
- [ ] Scope of topics, consumer groups, environments, and tenants is clear.
- [ ] Latency thresholds or deadlines specify units and start/end milestones.
- [ ] Measurement windows and data sources are agreed upon.
- [ ] Dashboards display SLIs, targets, error budgets, and trends.
- [ ] Alerts specify owners, severity, and runbooks.
- [ ] DLQ, retries, duplicates, and event freshness are accounted for in definitions.
- [ ] External SLAs align with agreed measurements and exclusions.
- [ ] A review cadence is scheduled after incidents or architecture changes.

When these points are clear, operations teams can use SLOs to prioritize reliability work, SLAs to manage service commitments, and Kafka/Spring Kafka metrics to detect and resolve root causes of quality degradation.

