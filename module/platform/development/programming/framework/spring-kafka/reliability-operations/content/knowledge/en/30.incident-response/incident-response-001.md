# Runbook for Increasing Consumer Lag

## Objective and Scope

This runbook guides incident response when a Kafka consumer group processes records slower than the rate at which data is produced, causing the backlog of unprocessed records to grow. The objective during an incident is to identify the exact affected consumer group, topic, and partitions; determine whether the root cause lies in the consumer, application, dependency, or Kafka cluster; safely restore processing throughput; and confirm that the backlog is decreasing and data continues to be processed according to system commitments.

This runbook applies to applications using Spring for Apache Kafka, including single-record listeners, batch listeners, and listeners with retry or a dead-letter topic (DLT). Metric names, Actuator endpoints, and certain configuration options may vary depending on the Spring Boot, Spring Kafka, Kafka client, and observability stack versions in use. Always use the service's actual configuration when operating.

Throughout the incident:

- Record the start time, alert, group ID, topic, partitions, environment, application version, and the most recent deployments or configuration changes.
- Prioritize restoring processing capacity and preserving data. Do not reset offsets, skip records, or delete retry/DLT data just to make the lag metric drop.
- Make one controlled change at a time, record the before-and-after values, and observe the impact before proceeding.
- If there are signs of data loss due to retention, offset errors, or broker failures, switch to the system's data/incident response procedure and notify the Kafka owner.

## 1. Understanding Consumer Lag Properly

For a partition, consumer lag is typically approximated as:

~~~text
lag = log end offset - committed offset
~~~

The committed offset is the next position the consumer group will read. The log end offset (LEO) is the end position of the log as measured by the observability tool. Therefore, lag usually represents the number of offsets behind, which is not always equal to the exact number of readable messages.

Several edge cases should be kept in mind:

- Compacted topics may have offset gaps because old records have been compacted. The offset difference in that case does not equal the actual number of remaining records.
- For consumers using the `read_committed` isolation level, the consumer can only read up to the Last Stable Offset (LSO). If the topic has open transactions, measurements based on LEO may show lag that the consumer cannot yet read.
- When the log start offset has surpassed the committed offset, old data may have already expired due to retention. This is a sign that requires immediate investigation, not a situation to automatically reset offsets.
- Different tools use the high watermark, LEO, or LSO as the baseline; metrics may therefore differ. When comparing trends, use the same metric source.

Do not assess an incident using total lag alone. Review the following together:

| Metric | Meaning during investigation |
|---|---|
| Lag by group/topic/partition | Identify the scope and bottlenecked partitions |
| Producer rate (records in/sec) | Amount of new work arriving |
| Consumer rate (records consumed/sec) | Current processing capacity |
| Age of the oldest unprocessed record | Actual delay experienced by the business flow |
| Number of active consumer members | Check whether the group has consumers assigned to partitions |
| Rebalance count and group state | Detect consumers repeatedly leaving/joining the group |
| Listener processing duration and error rate | Locate slow listeners or dependencies |
| Retry, DLT, and commit rate | Detect failing records or non-advancing offsets |

Continuously rising lag is usually more concerning than a high lag value that is decreasing. Record age can reflect business impact better than offset count, especially when the data ingestion rate fluctuates sharply.

Given a backlog (B), an incoming rate (I) records/sec, and a processing rate (C) records/sec, the estimated catch-up time is:

~~~text
catch-up time = B / (C - I), when C > I
~~~

If C <= I, the consumer cannot reduce the backlog at its current capacity. This is only an estimate for the whole group; hot partitions, uneven processing times, and retries can make the actual time longer.

## 2. Rapid Response Procedure

### Step 1 — Confirm the Alert and Impact Scope

1. Confirm whether the alert reflects fresh data or stale metrics, missed scrapes, or a broken exporter.
2. Retrieve the group ID, topic, environment, and the time range when lag started increasing from dashboards, logs, or service configuration.
3. Identify which business flow the consumer group serves, the maximum acceptable latency, and whether any downstream flows are waiting for results.
4. Check whether the producer recently increased traffic, replayed data, ran a backfill, or re-emitted events.
5. Record the total lag, max partition lag, oldest record age, ingress/egress rates, and current consumer count as a baseline for comparison.

Do not infer the group ID solely from the deployment name. Verify the effective group ID in the Spring Kafka configuration or in Kafka group metadata; multiple listeners may use separate group IDs.

### Step 2 — Check Consumer Group Status

Run commands from a machine or pod that has Kafka CLI and permission to read cluster metadata. Replace the placeholders in angle brackets with environment details:

~~~bash
BOOTSTRAP_SERVERS="<broker-1:9092,broker-2:9092>"
GROUP_ID="<consumer-group-id>"
TOPIC="<topic-name>"

# Overview of committed offset, log end offset, and lag by partition
kafka-consumer-groups.sh \
  --bootstrap-server "$BOOTSTRAP_SERVERS" \
  --describe \
  --group "$GROUP_ID"

# Group state
kafka-consumer-groups.sh \
  --bootstrap-server "$BOOTSTRAP_SERVERS" \
  --describe \
  --group "$GROUP_ID" \
  --state

# Members and partition assignment (if supported by Kafka CLI)
kafka-consumer-groups.sh \
  --bootstrap-server "$BOOTSTRAP_SERVERS" \
  --describe \
  --group "$GROUP_ID" \
  --members --verbose
~~~

If the cluster requires authentication, add `--command-config <client.properties>` to each command. Do not include passwords, tokens, or authentication config file contents in tickets or incident logs.

Interpreting the output:

- `CURRENT-OFFSET`: the group's committed offset on the partition.
- `LOG-END-OFFSET`: the end of log position reported by the CLI.
- `LAG`: the difference calculated by the CLI for the partition.
- `CONSUMER-ID`, `HOST`, `CLIENT-ID`: help identify the member and instance holding the assignment.
- Group states such as `Stable`, `PreparingRebalance`, `CompletingRebalance`, or `Empty` indicate whether the group is stable, rebalancing, or has no members. State names may vary across Kafka versions.

If the command does not return the expected group or partitions, double-check the cluster bootstrap, ACL permissions, group ID, topic, and environment. Do not conclude the group is gone from a single CLI connection error.

### Step 3 — Quick Triage by Symptom

| Symptom | First direction of investigation |
|---|---|
| Group has no members or is in Empty state | Pods not running, listener not initialized, wrong group ID, connection error, or ACL issue |
| Group repeatedly in Preparing/Completing Rebalance | Pod restarts, deployments, heartbeat, poll interval, single poll taking too long, or member disconnects |
| Lag rising across almost all partitions | Producer load spike, insufficient total consumer capacity, or a shared dependency slowing down |
| Only a few partitions have high lag | Hot partition, skewed key distribution, a poison/failing record, or unbalanced assignment |
| Consumer has members but committed offset is stuck | Blocked listener, prolonged retries, incomplete processing, or commit/ack issue |
| High consumer rate but lag still increases | Ingress rate exceeds processing rate |
| Listener processes quickly but lag does not drop | Check commits, the group ID/metric being observed, rebalances, and the tool's offset baseline |
| Lag suddenly drops to 0 after an action | Verify offsets and business data; zero lag does not prove records were processed correctly |
| Logs show OffsetOutOfRange or log start exceeds committed offset | Check retention and whether data has been purged from the log; escalate to the owner |

### Step 4 — Determine Severity Level

Evaluate based on business impact, record age, and catch-up capability; do not apply a single lag threshold to every topic.

- **High severity:** payment, order, or SLA-bound data flows are delayed; record age exceeds SLA; lag continues to grow; group has no members; signs of data loss or commit failures.
- **Action needed:** lag is steadily rising, estimated catch-up time exceeds target, some partitions have low processing throughput, or retries are increasing.
- **Monitor:** lag fluctuates briefly after a traffic burst, consumer rate has exceeded producer rate, and record age is decreasing.

If the system already defines its own severity levels and SLAs, use those definitions to open the incident and escalate.

## 3. Gather Evidence Before Making Changes

### 3.1. Inspect Topic and Partitions

~~~bash
kafka-topics.sh \
  --bootstrap-server "$BOOTSTRAP_SERVERS" \
  --describe \
  --topic "$TOPIC"
~~~

Record the partition count, leader, replicas, and ISR. Compare high-lag partitions against the remaining partitions. If a partition has no leader, an abnormal ISR, or metadata changes continuously, shift investigation to the Kafka broker/cluster.

Check the log start offset using an offset tool appropriate for the running Kafka version, if permitted. If the log start offset has passed the committed offset, retention may have already removed data the consumer has not processed. Do not set offsets to earliest/latest to mask this condition.

### 3.2. Check Kafka Consumer Metrics

If JMX is enabled, useful Kafka consumer metric groups include:

| JMX Group | Metrics to inspect | Meaning |
|---|---|---|
| `kafka.consumer:type=consumer-fetch-manager-metrics,client-id=...` | `records-lag-max` | Maximum lag observed by the member |
| Same fetch manager group | `records-consumed-rate`, `bytes-consumed-rate` | Data consumption rate |
| Same fetch manager group | `fetch-rate`, `fetch-latency-avg`, `fetch-latency-max` | Fetch frequency and latency |
| `kafka.consumer:type=consumer-coordinator-metrics,client-id=...` | `commit-rate`, `commit-latency-avg` | Commit frequency and latency |
| Same coordinator group | `heartbeat-rate`, `join-rate`, `sync-rate` | Heartbeat and group coordination activity |

Per-member JMX metrics do not replace group- and partition-level lag dashboards. `records-lag-max` is the maximum value for a member, not the total group backlog.

Metric names exposed via Micrometer/Prometheus depend on versions and configuration. Use the `/actuator/metrics` endpoint to discover registered metrics, or `/actuator/prometheus` if the application has enabled the Prometheus registry. Do not assume endpoints are public; access them only through authorized management paths.

### 3.3. Check Spring Kafka Application Metrics

Correlate the following groups of information across dashboards and logs:

- Processing duration per listener invocation, records per batch, and listener completion rate.
- Exception counts by type, retry counts, backoff duration, and number of records routed to DLT.
- Active listener thread count, thread wait time, and CPU utilization.
- Heap, GC pauses, memory pressure, thread count, and connection pool status.
- Latency, timeouts, error rate, and throughput limits of databases or HTTP services called by the listener.
- Rebalance count, consumer member count, partition assignments, and time spent without polling.
- Producer rate, request/fetch latency, quota throttling, and Kafka connection errors.

When searching logs, correlate by group ID, listener ID, topic, partition, and offset. If the application does not log all of these fields, use Kafka client logs and assignment metrics to narrow down the scope. Avoid logging payloads containing personal data, tokens, or secrets.

### 3.4. Check Changes Near the Start Time

Correlate the time lag began increasing with:

- Deployments, restarts, autoscaling, or replica count changes.
- Changes to `group.id`, topic subscription, concurrency, partition count, or assignor.
- Changes to `max.poll.records`, `max.poll.interval.ms`, ack mode, or retry/backoff.
- Producer starting a replay/backfill or experiencing a sudden traffic spike.
- Database migrations, connection pool exhaustion, downstream rate limits, or network issues.
- Kafka broker rolling restarts, partition leader elections, ISR shrinks, or quota changes.

Coinciding timestamps are a clue, not sufficient proof of root cause. Verify with metrics and logs.

## 4. Remediation by Root Cause

### 4.1. No Consumer Members

Check the deployment, pods/containers, readiness/liveness probes, startup logs, and Kafka connectivity. Verify:

1. The application started the listener container successfully.
2. Broker bootstrap addresses and DNS/network are reachable from the runtime.
3. ACLs allow reading the topic and joining the group.
4. Group ID and topic subscription match the environment.
5. No deserialization or configuration errors cause the listener to stop immediately on startup.
6. No change caused instances to accidentally use different group IDs.

Restore the failed instances or configuration. After members join the group, monitor assignments and committed offsets. If the group ID changes, the new group may start from an offset determined by `auto.offset.reset`; this can create a separate read stream and will not automatically resume the old group's position. Do not change the group ID during an incident without fully understanding the impact.

### 4.2. Consumer Continuously Rebalancing

Common causes include pod restarts, intermittent network issues, a listener taking too long to process one poll, a consumer failing to call poll within the allowed window, or membership/assignment changes.

Check:

- Rebalance counts over time and join/sync/heartbeat logs.
- Maximum batch processing time, not just average duration.
- Effective values of `max.poll.interval.ms` and `max.poll.records`.
- Pod restarts/OOMs, CPU throttling, GC pauses, and network timeouts.
- Whether deployments or an autoscaler are continuously adding/removing instances.
- Whether partition assignments are changing abnormally.

For Kafka consumers, `max.poll.interval.ms` limits the maximum time between poll calls in standard group management mode. If a listener takes too long to process the records returned from a single poll, the consumer may be considered no longer making progress and the group triggers a rebalance. `session.timeout.ms` and heartbeats relate to detecting disconnected members; they do not replace completing processing within the poll interval.

Actions:

1. Fix the cause of the listener or JVM hanging/slowing down.
2. Reduce `max.poll.records` if the current batch takes too long to process; re-measure throughput and processing duration.
3. If the workload genuinely requires longer processing time, recalculate `max.poll.interval.ms` based on controlled maximum processing time plus a safety margin. Do not increase this value merely to mask a hung listener.
4. Stabilize replica counts and freeze deployments/autoscaling during the incident.
5. Consider static membership or changing the partition assignor only after understanding their impact on failed-member detection time and deployment procedures.

### 4.3. Ingress Rate Exceeds Consumer Capacity

If the producer rate exceeds the consumer rate across most partitions, the group needs more processing capacity or ingress load must be reduced per business agreement.

Check before scaling:

- Topic partition count and number of consumers actually holding assignments.
- Total listener consumers across all pods. Within a group, a partition can be assigned to at most one consumer member at a time.
- CPU, memory, threads, connection pools, and downstream limits.
- Processing time per record/batch and number of synchronous I/O calls inside the listener.
- Whether the producer rate is a temporary spike or a sustained traffic change.

**Scale Replicas or Concurrency in a Controlled Manner**

Spring Kafka allows configuring concurrency on the listener container. Example Spring Boot configuration:

~~~yaml
spring:
  kafka:
    listener:
      concurrency: 3
~~~

Or container factory configuration:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent> kafkaListenerContainerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {
    var factory = new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);
    return factory;
}
~~~

Values in the examples are illustrative only. Total consumer members for a listener group is approximately the number of pods multiplied by concurrency per pod. The number of consumers that actually receive partition assignments cannot exceed the topic's partition count. If there are 6 partitions and total concurrency is 10, at least 4 consumers will remain idle without partitions; adding more consumers will not make that flow process faster.

Increase replicas/concurrency incrementally while monitoring rebalances, throughput, CPU, and dependencies. Stop scaling if databases or downstream services begin to overload. If pods do not share the same group ID, each group will receive its own copy of the data instead of sharing partitions; verify the group ID before scaling.

**Optimize Processing**

- Reduce synchronous calls or repeated queries inside the listener; use bulk operations if the dependency supports them.
- Consider batch listeners when business logic permits batch processing and per-record errors can be handled cleanly.
- Increase `max.poll.records` only when processing time, memory, and poll interval have sufficient headroom. Larger batches can increase throughput but also lengthen the interval before the next poll and increase in-memory work in flight.
- If processing concurrently inside a listener, bound the concurrency and preserve ordering/idempotency as required by business rules. Do not push records into an unbounded queue and commit offsets before the actual work completes.
- Inspect serialization/deserialization, record size, and payload conversion overhead.

**When Considering Increasing Partitions**

Increasing partitions can raise future maximum parallelism, but it is not an instant lag fix. Adding partitions does not automatically redistribute the existing backlog in a balanced way. With key-based partitioning, increasing the partition count can change which partition a key maps to, affecting ordering across old and new records with the same key. Only increase partitions after evaluating ordering guarantees, consumer assignments, broker capacity, and a migration plan.

### 4.4. Downstream Dependency Slow or Failing

For example: the listener reads from Kafka normally, but each record must write to a database, call an HTTP service, or wait on another system. When the dependency slows down, the consumer holds partitions longer and committed offsets stop advancing.

Check dependency dashboards and logs for the same timeframe:

- Database: connection pool exhaustion, lock contention, slow queries, deadlocks, long transactions, or storage latency.
- HTTP/gRPC: timeouts, rate limits, retry storms, DNS, or network errors.
- Cache: elevated misses, high latency, or connection limits.
- Object storage/search service: throttling, quotas, or request timeouts.

Actions:

1. Restore the dependency following its own runbook; coordinate with its owner if this is a cross-service incident.
2. Limit concurrency on the consumer or client to avoid overloading the dependency further.
3. Use bounded timeouts and retries with backoff/jitter according to application policy; avoid tight retry loops.
4. If you need to temporarily pause consuming new records while the dependency recovers, pause the listener container in a controlled manner. For example:

~~~java
@Autowired
private KafkaListenerEndpointRegistry registry;

public void pauseListener() {
    MessageListenerContainer container =
            registry.getListenerContainer("ordersListener");
    if (container != null) {
        container.pause();
    }
}

public void resumeListener() {
    MessageListenerContainer container =
            registry.getListenerContainer("ordersListener");
    if (container != null) {
        container.resume();
    }
}
~~~

Replace `ordersListener` with the actual listener ID. Pausing may only take effect on the next poll cycle and does not cancel in-flight work. The container still maintains poll/coordination activity per Spring Kafka's mechanism. Monitor the paused state and resume only when the dependency is sufficiently healthy.
5. Do not build an unbounded in-memory queue to absorb the backlog. That shifts pressure from Kafka onto the heap, risking OOMs and losing in-progress work state.

### 4.5. Single Partition Bottleneck or Skewed Key Distribution

If one partition has high lag while the others look nearly normal, investigate localized causes:

- A single key generates high volume and routes to the same partition.
- A record has an abnormal payload or causes deserialization/validation failures.
- A specific operation for that key is slow.
- The partition leader or a broker holding its replica has an issue.
- The assignment or consumer instance holding that partition has abnormal resource usage.

Correlate the partition, consumer ID, offset, and listener logs. If the same offset appears repeatedly with the same exception, that record may be blocking partition progress due to the retry/error handler.

Do not manually skip the record. Identify the error category:

- **Transient error:** dependency timeout or throttling. Restore the dependency and retry with bounded backoff.
- **Data error:** incompatible schema, malformed payload, or invalid business data. Collect the necessary metadata, route via the application's error/DLT flow, and ensure an owner is assigned to handle the record.
- **Application bug:** consistently reproducible exception. Consider rolling back or patching the application per deployment procedures; define how to replay after the fix.

If using `DefaultErrorHandler`, `DeadLetterPublishingRecoverer`, or `@RetryableTopic`, inspect retry attempts, backoff, retryable vs. recoverable exceptions, DLT destination, and post-recovery commit policy. Retry topics can alter processing order relative to the original topic; understand ordering guarantees before changing retry policy.

### 4.6. Committed Offset Not Advancing

If the listener appears active but `CURRENT-OFFSET` remains stationary, inspect the ack/commit mechanism:

- Whether `enable.auto.commit` is enabled or disabled.
- The actual ack mode of the listener container: RECORD, BATCH, TIME, COUNT, COUNT_TIME, MANUAL, or MANUAL_IMMEDIATE.
- With MANUAL, whether the application invokes acknowledge after successful processing.
- Whether exceptions prevent the listener from completing or the error handler has not recovered.
- Whether transactions are committing successfully or repeatedly rolling back.
- Whether async processing causes offsets to be acked before actual work finishes.
- Whether the dashboard is observing the correct group ID and cluster.

Spring Kafka listener containers typically manage commits according to the container's ack mode; actual behavior can vary across versions and applications. Inspect the running configuration rather than assuming from sample configs. With asynchronous processing, design ack/commit handling so offsets advance only once the corresponding work completes under the desired semantics. Committing prematurely can forfeit the ability to replay records after a failure.

### 4.7. Kafka Broker, Network, or Quota Issues

If multiple consumer groups are affected simultaneously, or consumer fetch latency and connection errors spike together, inspect the cluster:

- Offline brokers, leaderless partitions, or continuous leader elections.
- Under-replicated partitions, ISR shrinks, and controller instability.
- Disk utilization/latency, network saturation, and request queue time.
- Fetch request latency, request handler idle percent, and quota throttling.
- ACL/authentication, DNS, TLS, firewall, or connectivity from the application subnet.
- Unusual producer ingress spike placing heavy load on the cluster.

Use `kafka-topics.sh --describe` to check topic leaders/replicas/ISR. Broker metrics and cluster logs must be verified by the Kafka operator/platform team. Do not restart brokers, alter replication factors, or change quotas during an incident without coordination from the cluster owner.

## 5. Relevant Spring Kafka Configurations to Review

The configurations below are checkpoints to review once supporting evidence is available. Do not apply them indiscriminately during an incident:

| Configuration | Effect | Considerations |
|---|---|---|
| `spring.kafka.listener.concurrency` or container `setConcurrency` | Number of consumer threads for the listener container per instance | Total group consumers vs. partition count; dependency load |
| `max.poll.records` | Maximum records returned in a single poll | Batch processing duration, memory, and poll interval |
| `max.poll.interval.ms` | Maximum interval between polls in group management | Longest poll processing time; do not use to mask hung listeners |
| `session.timeout.ms` | Time to detect missed member heartbeats per protocol config | Failure detection sensitivity and network jitter |
| `heartbeat.interval.ms` | Heartbeat cadence in configs using client-side heartbeat intervals | Must align with session timeout and protocol |
| `fetch.min.bytes`, `fetch.max.wait.ms` | Conditions for batching fetch responses | Latency vs. throughput; tune only with measurements |
| `max.partition.fetch.bytes`, `fetch.max.bytes` | Fetch data size limits | Record/batch size, memory, and broker response |
| `auto.offset.reset` | Behavior when the group has no valid offset | Not a recovery mechanism for lost offsets; may start at earliest/latest per config |
| Ack mode and `enable.auto.commit` | When offsets are committed | At-least-once/exactly-once semantics and replay capability |

Example consumer configuration in Spring Boot:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
      max-poll-records: 100
      properties:
        "[max.poll.interval.ms]": 300000
    listener:
      concurrency: 3
~~~

This is an illustrative configuration, not a universal recommendation. Verify your Spring Boot version and how the binder handles dotted properties before applying. `max.poll.interval.ms` must exceed the longest poll processing time with a safety margin; `max.poll.records` must align with processing time and resources. After each change, deploy via standard procedures and monitor rebalances, throughput, errors, and dependencies.

## 6. Confirming Recovery

Close the incident only when there is evidence that both processing capacity and business outcomes have recovered. Minimum checks:

1. The consumer group has stable members and proper partition assignments.
2. Lag per partition is decreasing over a sustained period; not merely total lag dropping due to missing metrics or offset changes.
3. Consumer rate exceeds producer rate long enough for the backlog to continue shrinking.
4. The age of the oldest unprocessed record is returning within SLA.
5. Committed offsets are advancing normally with no persistent commit/transaction errors.
6. Listener errors, retries, DLT volume, and rebalance rates have returned to acceptable levels.
7. CPU, heap, GC, connection pools, and dependencies are not overloaded after increasing concurrency.
8. Downstream business flows have received and processed the data; verify using business metrics or appropriate reconciliation.

Continue monitoring after lag returns to normal thresholds to ensure the issue does not recur when load returns. Record the recovery start time, SLA recovery time, and the changes that resolved the incident.

## 7. High-Risk Operations Requiring Control

### Do Not Reset Offsets to Make Dashboards Look Good

Offset reset commands can skip unprocessed data or replay already-processed data. For example, `--to-earliest`, `--to-latest`, `--to-offset`, and `--shift-by` have different effects; `--execute` persists actual changes to the group. Never run these commands as a routine lag mitigation step.

If a business-driven offset reset is required:

1. Identify the exact cluster, group, topic, and partitions.
2. Record the current offsets, target offsets, and affected data range.
3. Determine whether replaying will cause duplicate side effects; verify idempotency and deduplication mechanisms.
4. Obtain approval from the business owner and Kafka owner per organizational process.
5. Execute within a controlled window, save before/after output, and prepare a rollback or reconciliation plan.

### Do Not Scale Concurrency Beyond Downstream Capacity

Adding consumers can increase concurrent requests to databases/APIs and worsen the incident. Before each scale-up, verify dependency headroom, connection pools, and rate limits. If the dependency is saturated, limiting concurrency or pausing the listener may be safer.

### Do Not Arbitrarily Increase Partitions or Change Group IDs

Increasing partitions can alter key-to-partition mapping and ordering. Changing the group ID can create a new group with different offset selection behavior. Both require dedicated data evaluation and a rollout plan.

### Do Not Commit Before Processing Completes

Do not ack/commit offsets merely because a record has been placed into an asynchronous queue. If the process dies before the queue finishes processing, Kafka may consider the record completed and not redeliver it. Use durable state persistence, transactions, or post-processing acks according to application design.

## 8. Incident Action Checklist

### Within the First 5 Minutes

- [ ] Confirm the alert, timestamp, and environment.
- [ ] Identify the group ID, topic, partitions, and business owner.
- [ ] Check whether metrics are updating; record lag, record age, and producer/consumer rates.
- [ ] Run `kafka-consumer-groups --describe` and check group state/members.
- [ ] Determine whether the group has no members, is rebalancing, has lag across all partitions, or only specific partitions.
- [ ] Check recent deployments, restarts, traffic spikes, and dependency changes.

### Before Mitigation

- [ ] Collect relevant logs/metrics and record baseline values.
- [ ] Identify whether the bottleneck is the consumer, listener, dependency, or broker.
- [ ] Estimate the impact of increasing consumers/concurrency.
- [ ] Choose a small, observable, and reversible change.
- [ ] Assign someone to monitor lag, dependencies, and business impact after the change.

### Before Closing the Incident

- [ ] Lag is decreasing across affected partitions.
- [ ] Record age and business SLAs have recovered.
- [ ] Group is stable, offsets are advancing, and there are no abnormal commit errors.
- [ ] Retry/DLT and error rates have been reviewed, and failed records have an assigned owner.
- [ ] Dependencies are not overloaded by the mitigation.
- [ ] Document root cause, timeline, mitigation, and follow-ups.

## 9. Incident Record Template

Use the template below in the ticket or incident channel:

~~~text
Incident:
Environment:
Service / listener ID:
Consumer group:
Topic:
Affected partitions:
First observed at:
Business impact / SLA:

Initial state:
- Total lag:
- Max partition lag:
- Oldest unprocessed event age:
- Producer rate:
- Consumer rate:
- Active members:
- Group state:
- Retry / DLT rate:

Evidence:
- Relevant dashboard links:
- Log time range / correlation:
- Recent deploy or config change:
- Dependency / broker health:

Root cause:
Mitigation and timestamps:
Observed result after each change:
Recovery confirmed at:
Remaining backlog / follow-up owner:
~~~

## 10. Post-Incident

During the post-incident review, determine why alerts detected the issue early enough or why the system failed to detect it before the SLA was impacted. Add or adjust:

- Alerts by group/topic/partition combining lag, lag slope, and record age.
- Dashboards for producer rate, consumer rate, estimated catch-up time, and member count.
- Metrics for listener processing duration, retries, DLT, rebalances, and commits.
- Load testing to determine safe throughput by partition count and concurrency.
- Concurrency limits, timeouts, retry/backoff, and connection pools for downstream calls.
- Testing for bad records, poison messages, broker restarts, and slow dependencies.
- Replay/DLT procedures with idempotency, auditing, and clear ownership.
- Runbooks for consumer scaling, pause/resume, and escalation aligned with operational permissions.

Every follow-up item needs an owner, due date, and verification criteria. If the root cause is sustained traffic growth, update the capacity plan rather than leaving temporary scaling configs in place.

## 11. When to Escalate

Escalate immediately to the Kafka/platform owner when brokers are offline, partitions lose leaders, ISR is widely abnormal, unexplained authentication/ACL failures occur, quota throttling affects multiple groups, or retention is suspected of purging unprocessed data.

Escalate to the application owner when listeners fail repeatedly, deserialization/schema incompatibilities occur, commits do not advance, or retry/ack semantics need changes.

Escalate to the downstream owner when a database/API/cache is the bottleneck or when rate limits, capacity, or data adjustments are needed.

Escalate to the business owner when record age breaches SLA, data needs to be skipped or replayed, duplicate side effects occur, or backlog processing prioritization is needed.

When handing off, provide the group ID, topic/partitions, start time, lag and record age, group state, relevant logs/metrics, changes already made, and observed impact. Do not share credentials or sensitive payloads.
