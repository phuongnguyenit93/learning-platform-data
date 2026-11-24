# Isolating Incidents by Topic and Partition

When a Spring Kafka system runs into an incident, asking "does the consumer have lag?" is usually not enough to pinpoint the root cause. A consumer group may lag on only a single partition, all partitions of one topic may climb together, or multiple consumer groups may be impacted by a single topic. Each pattern points to a different fault domain.

Isolating by topic and partition helps operations teams narrow an incident from a broad symptom down to a specific combination of cluster, topic, consumer group, partition, offset, and processing instance. This is the core unit of investigation in Kafka because a partition is where message ordering is stored, what gets assigned to consumers, and what has a leader serving reads and writes.

The goal of incident response is to define the blast radius, gather evidence before mutating state, locate the bottleneck, and then recover in a controlled manner while confirming that data has been processed accurately.

## 1. Core Concepts Needed During Investigation

A topic is divided into multiple partitions. Each partition is an independently ordered log that can reside on different brokers. Kafka does not provide a global ordering across partitions of the same topic. When a producer sends records with a key, Kafka typically uses the key to select a partition, keeping records with the same key in the same partition and preserving order within that partition.

The following concepts appear frequently during isolation:

| Component | Meaning during investigation |
|---|---|
| Topic | Logical data stream, e.g. `orders.created` or `payments.completed` |
| Partition | An independently ordered log; the unit of work distribution and offset tracking |
| Offset | Position of a record within a single partition; not a global sequence number across the topic |
| Leader | Replica currently serving reads/writes for the partition per metadata state |
| Follower | Replica replicating data from the leader |
| ISR | Set of replicas currently considered in sync with the leader per Kafka rules |
| Consumer group | Group of consumers sharing the reading of a topic; each partition is assigned to at most one consumer in the same group at a time |
| Committed offset | Progress position the consumer group has committed for a partition |
| Log end offset | End of log position reported by the broker for the partition; lag measurement also depends on log state and isolation level |
| Consumer lag | Difference between available data position and the group's committed progress on each partition |

Kafka guarantees ordering only within a single partition. When a topic has multiple partitions, never compare offsets between partition 0 and partition 1 as if they belonged to the same sequence. When reading lag numbers, always preserve the full tuple `(cluster, topic, group, partition)`.

Lag is commonly approximated by:

```text
lag(topic, group, partition)
    = end offset used for monitoring
      - committed offset of the consumer group
```

The end offset used to compute lag can depend on the monitoring tool, transaction state, and `isolation.level` configuration. With consumers using `read_committed`, data from open transactions may not be readable yet even though the log end offset has advanced. Therefore, compare figures from the same tool and understand the metric definition before drawing conclusions.

## 2. Start by Defining the Exact Scope

Before restarting pods or scaling up consumers, identify which cluster and flow the incident belongs to. Some environments have multiple stages, multiple Kafka clusters, similarly named topics, and multiple consumer groups sharing one topic. Running commands against the wrong cluster can yield false conclusions or modify the wrong data.

Record initial details:

- Environment and Kafka cluster being inspected.
- Affected topic and dependent topics in the same business flow.
- Consumer group of the Spring Kafka application.
- Start time, alert time, and most recent deployment time.
- User-visible symptoms: delayed data, missing data, duplicate processing, listener errors, or publish errors.
- Whether one or multiple partitions have lag, and whether lag is rising, falling, or flat.

Obtain topic names and group IDs from runtime configuration or the running deployment's config. Never infer the group ID solely from a listener class name: `groupId`, `id`, `idIsGroup`, and default configs can make the actual group differ from what a code reader expects.

With Spring Kafka, cross-check settings such as `spring.kafka.consumer.group-id`, the `groupId` attribute on `@KafkaListener`, topics declared on the listener, and environment-specific overrides. If the listener uses a topic pattern, identify the actual set of topics matched by that pattern.

## 3. Read Lag Per Partition

Total lag for a group is useful for alerting, but it can hide a single troubled partition. Inspect lag per partition and observe trends across multiple timestamps.

Hypothetical example output:

| Topic | Partition | Committed offset | End offset | Lag |
|---|---:|---:|---:|---:|
| `orders.created` | 0 | 12,400 | 12,510 | 110 |
| `orders.created` | 1 | 8,100 | 8,220 | 120 |
| `orders.created` | 2 | 18,000 | 24,500 | 6,500 |
| `orders.created` | 3 | 9,700 | 9,820 | 120 |

In this example, total lag is 6,850, yet almost all of it sits in partition 2. Adding more consumers may not solve the problem if partition 2 is blocked by a hot key, a failing record, or a dependency affecting only one data slice.

Never conclude from a single metric snapshot. Record lag and its rate of change over time:

- Steadily rising lag: incoming data rate exceeds processing rate, or the consumer is not advancing offsets.
- Falling lag: the consumer is catching up.
- Flat lag at a high level: the consumer may be stopped, stuck, unassigned to partitions, or blocked waiting on a dependency.
- Low lag while listener errors climb: likely per-record failures or business errors that have not yet built a large backlog.
- Lag rising and falling in waves: likely bursty traffic, retries, rebalances, or flaky dependencies.

Correlate lag with throughput. If the end offset climbs rapidly while the committed offset stays nearly flat, the consumer cannot keep up or is failing to commit progress. If both remain static, producers may not be sending data, the topic may be idle, or consumers are not receiving new records. If committed offset advances while lag still rises, the consumer is doing work, but its capacity is below the ingress rate.

## 4. Use Kafka CLI to Inspect Topics, Groups, and Partitions

The commands below illustrate checks using scripts bundled with Kafka distributions. Script names may end in `.sh` or `.bat` depending on OS; exact flags vary across Kafka versions. Replace bootstrap servers, groups, and topics with values from the environment under investigation.

### Inspect Consumer Group Status

```bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --group order-projection-v1
```

Output typically includes group, topic, partition, current offset, log end offset, lag, and consumer ID/host/client ID depending on version. Look for partitions with large lag, partitions with no consumer ID, or consumer IDs changing continuously.

Inspect group members and assignments if your Kafka version supports it:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --group order-projection-v1 \
  --members \
  --verbose
```

This identifies which consumer instance owns which partition. If the group state is `Empty`, there are no active members. If the group repeatedly changes state or assignments shift, inspect rebalances, heartbeats, session timeouts, and connectivity errors.

### Inspect Topic Metadata

```bash
kafka-topics.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --topic orders.created
```

Output shows partition count, replication factor, leader, replicas, and ISR for each partition. Watch for:

- Leader `-1` or missing leader: the partition has no available leader at inspection time.
- ISR smaller than expected replica count: the partition has lagging replicas.
- One broker repeatedly appearing as leader of troubled partitions: check that broker's health.
- Partitions with unexpected replica or leader changes: correlate with broker restarts, rolling upgrades, or reassignments.

### Check Topic-Level Offsets

Some Kafka distributions include `kafka-get-offsets.sh` to retrieve offsets by partition:

```bash
kafka-get-offsets.sh \
  --bootstrap-server kafka-1:9092 \
  --topic orders.created \
  --time -1
```

The value `-1` typically requests the log end offset. Check `--help` for your version to get earliest offsets or filter specific partitions. To calculate lag, match offsets of the same partition against committed offsets of the exact consumer group. Never mix offsets from another group or cluster.

The commands above are read-only state checks. They do not replace time-series metrics, application logs, and broker telemetry. Save outputs with timestamps so you can compare before and after recovery.

## 5. Identify Incident Patterns from Partition Distribution

How errors distribute across partitions and consumer groups is a strong directional signal.

| Observed pattern | Priority investigation path |
|---|---|
| One partition's lag rises while others are normal | Hot key, failing record, partition leader/replicas, assignment, or a dependency tied to that record slice |
| All partitions of one topic rise together in one group | Insufficient consumer group capacity, slow listener, shared dependency, retries, or rebalancing |
| Multiple groups lag together on one topic | Producer burst, broker/topic health, anomalous data, or shared infrastructure issue |
| Only one group is affected while other groups read the same topic normally | Application logic, group config, database, or service-specific dependency |
| Different topics slow down together on one cluster | Brokers, network, storage, controller, or cluster resources |
| One consumer instance is slow across multiple partitions | That instance may lack CPU, memory, threads, network, or is blocked |
| Low lag yet some records repeatedly fail | Poison message, schema incompatibility, validation error, or business error |

These patterns are initial hypotheses, not final conclusions. For instance, multiple groups slowing down together could stem from an external dependency shared by all those services. Verify with metrics and logs.

### Only One Partition Has High Lag

Check in order:

1. Does the partition have a healthy leader and ISR?
2. Is the partition assigned to an active consumer?
3. Does the assigned consumer show similar lag or errors on other partitions?
4. Is the record arrival rate on this partition unusually high?
5. Does a single key account for most records?
6. Do listener logs repeat the same event ID, offset, or exception?
7. Does a dependency or business state appear uniquely in this partition?

If only one partition has high lag and the consumer repeatedly retries the same record, investigate poison messages before scaling the group. If that record always fails due to invalid schema or data, adding consumers only leaves extra resources waiting around the same partition or adds load to dependencies.

### All Partitions of One Topic Lag Together

If leaders and ISRs are healthy, inspect listener processing speed, database query duration, connection pools, thread pools, CPU, garbage collection, and network across all instances. Correlate deployment timestamps for changes to concurrency, batch size, retry/backoff, serialization, or processing logic.

If multiple groups are affected together, inspect brokers and producers. A producer may have suddenly increased throughput, sent larger records, changed key distribution, or replayed historical data.

## 6. Check Leaders, Replicas, and Broker Health

A partition can serve normal traffic only when it has an available leader. Follower replicas copy data from the leader, and the ISR reflects replicas meeting Kafka's synchronization rules. When a broker slows down, disconnects, or suffers storage issues, some partitions may be affected far more visibly than others.

When seeing abnormal partition leaders or shrinking ISRs:

- Identify which brokers hold the partition's leader and replicas.
- Inspect broker logs, restart timestamps, network, disk latency, disk space, and file descriptors.
- Check metrics for request latency, produce/fetch request rates, under-replicated partitions, and offline partitions.
- Correlate controller logs or cluster events if multiple leaders changed simultaneously.
- Determine whether the issue lies in brokers, inter-broker networking, or client load.

Rising `UnderReplicatedPartitions` indicates replicas are falling behind the leader. `OfflinePartitionsCount` greater than 0 indicates partitions with no available leader. Exact metric names and exposure depend on Kafka version and monitoring stack, but these two signals should always be reviewed alongside per-partition ISR and leader state.

Never enable unclean leader election merely to restore a partition leader without understanding the risk of data loss. Unclean election can promote an out-of-sync replica and lose records it had not yet received. If reassignments or replication changes are needed, follow cluster operations procedures and assess impact first.

## 7. Check Consumer Assignment, Rebalancing, and Processing Capacity

Within a consumer group, a partition can be assigned to at most one consumer at a time. A group with 12 partitions and 20 consumer instances can assign partitions to at most 12 instances; the remaining instances stay idle for that group. Conversely, if there are fewer consumers than partitions, each consumer may handle multiple partitions.

Check:

- Topic partition count and number of active consumer members.
- Which partitions are assigned to each consumer ID/host.
- Whether consumer instances are restarting, missing heartbeats, or repeatedly leaving the group.
- Per-record processing time and records processed per second.
- Whether listeners are blocked by synchronous I/O, database locks, or exhausted thread pools.
- Whether repeated exceptions cause retry/backoff to hold partitions without advancing offsets.

Continuous rebalancing can pause record consumption while partitions are revoked and reassigned. Check logs for `Revoking`, `Assigned`, heartbeat/session timeouts, long processing durations, and member count changes. In Spring Kafka, review listener concurrency, `max.poll.interval.ms`, `session.timeout.ms`, `heartbeat.interval.ms`, and related poll settings. Do not mechanically increase timeouts: first determine whether the listener is slow due to business work or hung.

`@KafkaListener` `concurrency` creates the configured number of consumer containers/threads. It does not allow a single partition to be processed concurrently by multiple consumers in the same group. If a topic has 4 partitions, raising concurrency from 4 to 12 creates no additional parallelism for a hot partition; concurrency exceeding partition count may sit unused.

## 8. Finding Hot Partitions and Key Skew

Producers typically choose partitions based on key to preserve order for the same business entity, such as `orderId` or `accountId`. If one key appears with dominant frequency, most records funnel into one partition. Other partitions stay light while the hot partition accumulates lag.

Compare per partition:

- Record rate and byte rate.
- Average record size and size distribution.
- Key repetition ratio or top keys over a time window.
- Processing time by event type or key group.
- Producer instances and partitioner/configuration changes near the incident time.

Do not log full payloads to hunt for hot keys if payloads contain sensitive data. Use cardinality-bounded metrics, sampling, or approved data analysis tools. Avoid creating metric labels per event ID or arbitrary key because high cardinality can overload the monitoring system.

If a hot key represents an entity requiring strict ordering, you cannot simply spread that key's records across multiple partitions while keeping the same ordering guarantee. Revisit the business model: serialize that hot entity separately, coalesce updates, batch changes, use a dedicated processing lane, or adjust sharding if business rules allow.

Increasing partition counts can improve parallelism for well-distributed keys, but does not guarantee splitting a single hot key. When partition counts change, key-to-partition mapping can shift for new records while old records remain in previous partitions. This can alter observed ordering between records of the same key during the transition window. Only add partitions after evaluating semantics, consumer groups, retention, quotas, and a migration plan.

## 9. Isolating Poison Messages and Processing Errors in Spring Kafka

A repeatedly failing record can stall offset progress on a partition if the error handler retries that record under the current policy. Other partitions continue working normally, making the incident resemble a hot partition.

In application logs, correlate:

- Topic, partition, and offset of the failing record.
- Event ID or business key if safely loggable.
- Exception class, root cause, and initial stack trace.
- Delivery/retry attempt count and backoff duration.
- When errors began relative to deployments, schema changes, or data changes.
- Consumer instance and listener ID processing the record.

Spring Kafka may use `DefaultErrorHandler` with `BackOff` for retries; the exact configuration determines which exceptions are retried, attempt counts, and behavior after retries exhaust. When using `DeadLetterPublishingRecoverer`, records can be routed to a dead-letter topic once recovery fails. Inspect actual configuration rather than assuming every exception goes to the DLT.

Illustrative configuration example:

```java
@Configuration
public class KafkaErrorHandlingConfig {

    @Bean
    DefaultErrorHandler kafkaErrorHandler(
            DeadLetterPublishingRecoverer recoverer) {

        var backOff = new FixedBackOff(1_000L, 2L);
        var handler = new DefaultErrorHandler(recoverer, backOff);

        // Only mark identified data errors as non-retryable.
        handler.addNotRetryableExceptions(InvalidOrderEventException.class);
        return handler;
    }
}
```

The example above illustrates structure only; the recoverer bean, serializers, DLT topic, write permissions, and retry policy must be configured for your application. Do not place transient infrastructure errors like database unavailable into the non-retryable list if the system expects recovery via retries.

When routing records to a DLT, preserve sufficient metadata for investigation, including source topic, partition, offset, exception, and timestamp per recoverer config. A DLT is itself a topic with its own partitions and consumers; monitor its lag, retention, and replay workflow.

Do not arbitrarily skip a record simply because it blocks a partition. Skipping can lose a business state change. Before skipping or replaying, determine the impact, fix data or code, and preserve the event/offset needing handling.

## 10. Observing with Spring Kafka Metrics and Logs

Effective investigation combines three data layers: Kafka client/broker metrics, application listener metrics, and message-identified logs.

### Kafka Consumer Metrics

Commonly useful metrics include:

- `records-lag-max` and per-partition lag metrics if exposed: maximum lag observed by the consumer.
- `records-consumed-rate`: rate at which the consumer reads records.
- `bytes-consumed-rate`: byte consumption rate.
- `fetch-latency-avg` and `fetch-rate`: fetch latency and frequency.
- `commit-latency-avg` and `commit-rate`: offset commit latency and frequency.
- `assigned-partitions`: number of partitions currently held by the consumer, if provided by the metric system.

Exact metric names, tags, and per-partition granularity depend on Kafka client version, Micrometer registry, and export config. Verify live metrics before building dashboards or alerts. Do not rely solely on one consumer's `records-lag-max` to represent the entire group when multiple members exist.

### Application and Dependency Metrics

Correlate listener processing duration against:

- Database connection pool: active, idle, pending, and timeouts.
- Database query latency, lock waits, and transaction rollbacks.
- HTTP client latency, timeouts, and error rates.
- Thread pool queues, CPU, heap, garbage collection, and container throttling.
- Retry counts, DLT publish failures, and listener exceptions.

If lag climbs at the same time the database connection pool hits its limit, the bottleneck may be the database or consumer count issuing too many concurrent queries. If listener duration rises while dependencies look normal, review code, internal locks, serialization, and batch processing.

### Logs with Sufficient Context

Message processing logs should include `topic`, `partition`, `offset`, `consumer group` or listener ID, `clientId`/instance, and event ID when available. Putting these fields into MDC or structured log fields enables tracing a partition across multiple instances.

Do not use unbounded event IDs, order IDs, or keys as metric labels. High-cardinality values belong in logs or controlled traces. In logs, avoid recording unnecessary payloads, tokens, personal information, or payment data.

## 11. Controlled Partition Isolation in Spring Kafka

In some situations, it is necessary to pause reading further records from one partition to protect a dependency or handle a failing record. Spring Kafka provides listener container pause/resume APIs in supported versions.

Illustrative example:

```java
@Component
@RequiredArgsConstructor
public class PartitionControl {

    private final KafkaListenerEndpointRegistry registry;

    public void pauseOrdersPartition(int partition) {
        MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

        if (container == null) {
            throw new IllegalStateException("Listener container not found");
        }

        container.pausePartition(
            new TopicPartition("orders.created", partition)
        );
    }

    public void resumeOrdersPartition(int partition) {
        MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

        if (container == null) {
            throw new IllegalStateException("Listener container not found");
        }

        container.resumePartition(
            new TopicPartition("orders.created", partition)
        );
    }
}
```

The listener must have a matching ID, e.g. `@KafkaListener(id = "orders-listener", topics = "orders.created")`. Check the exact API and partition pause behavior for your running Spring Kafka version. Pausing is a container control request; it does not delete records, commit offsets on the application's behalf, or fix bad data. The partition may continue accumulating lag while paused.

Before pausing, identify which partitions the container currently manages, the objective, and the pause duration. After fixing the root cause, resume and watch the catch-up rate. With high listener concurrency, verify which container holds the partition and confirm the control API targets the active assignment.

Do not use pausing as a default knee-jerk fix for all lag. If the entire group is slow due to the database, pausing one partition can concentrate backlog elsewhere and prolong recovery.

## 12. Step-by-Step Incident Response Procedure

A consistent procedure lets multiple responders investigate together without accidentally altering evidence or introducing new risk.

### Step 1: Confirm Cluster, Topic, and Group

Obtain the cluster name, topic, consumer group, environment, and start time. Verify the application connects to the right bootstrap servers with the right runtime configuration. Record Kafka client, broker, and Spring Kafka versions if the incident relates to a version upgrade.

### Step 2: Capture Initial Baseline

Save outputs of `kafka-consumer-groups --describe`, `kafka-topics --describe`, per-partition lag metrics, member lists, and error logs. Record timestamps, deployed version, and application replica count. This serves as the baseline for post-mitigation comparison.

### Step 3: Classify the Shape of Impact

Categorize the incident: single partition, single topic, single group, multiple groups, or cluster-wide. Compare lag, end offsets, committed offsets, record rates, and consumer assignments. Never collapse metrics from different partitions into a single conclusion.

### Step 4: Choose the Investigation Branch

- Single partition: check leader/ISR, key skew, poison messages, and assigned consumer.
- All partitions of one topic: check group capacity, shared dependencies, and producer throughput.
- Multiple groups on the same topic: check producer, brokers, schemas, and source data.
- Multiple topics on the same cluster: check brokers, controller, network, disks, and cluster capacity.

### Step 5: Propose the Smallest Verifiable Change

For example: roll back a faulty release, restore a database dependency, fix schema mapping, route invalid records to the DLT per procedure, or adjust consumer capacity once under-provisioning is proven. Explicitly state which topic, group, and partitions the change affects.

### Step 6: Monitor Recovery

After the change, watch per-partition lag, end offset/committed offset rates, retries, DLT, listener errors, rebalances, and business latency. Confirm lag is shrinking and no new partitions start climbing abnormally. A drop in total lag on a dashboard is insufficient if a critical partition remains stuck.

### Step 7: Document Findings

Record the root cause, affected partitions, time window, relevant events/offsets, changes applied, before/after measurements, and preventive follow-ups. If root cause remains unconfirmed, state open hypotheses and missing evidence explicitly.

## 13. Operations Requiring Careful Evaluation Before Execution

Certain actions alter reading progress or data stream semantics. Execute them only with a plan, an owner, and the ability to verify results.

### Resetting Consumer Offsets

`kafka-consumer-groups --reset-offsets` can move a group to earliest, latest, a timestamp, or a specific offset depending on version. This operation can cause the application to skip data or reprocess historical data. Typically, the group must have no active consumers when resetting.

Before resetting:

1. Save current committed offsets for every partition.
2. Identify the exact partitions to modify and target offsets.
3. Estimate how many records will be skipped or replayed.
4. Check consumer idempotency and impact on side effects.
5. Use dry-run mode if supported by your version, then review the output.
6. Execute within an agreed window and verify offsets afterward.

Never use `--to-latest` simply to clear red dashboards. It can skip an entire unprocessed backlog. Resetting to earliest can replay huge event volumes, overloading databases or repeating side effects if consumers are not idempotent.

### Adding Partitions or Changing Keys

Adding partitions can spread more keys, but alters key mapping and can affect ordering during the transition window. Evaluate consumer groups, downstream systems, retention, quotas, replication, and how in-flight records will be handled before making the change.

### Increasing Consumer Concurrency or Pod Count

Scaling helps only when unassigned/underutilized partitions exist and dependencies have headroom. If a single hot partition is the bottleneck, adding pods will not let multiple consumers in the same group process that partition concurrently. Over-scaling can overload databases and widen the incident.

### Reassigning Replicas or Changing Broker Configs

Reassignment can consume heavy network and disk I/O for extended periods. Replication changes, leader elections, or broker configuration changes must follow Kafka cluster administration procedures. Never use unclean election or log deletion as an experimental fix during an incident.

## 14. Example Investigation of a Bottlenecked Partition

Suppose an alert reports rising lag on consumer group `order-projection-v1`. Describing the group shows partitions 0, 1, and 3 have low lag, while partition 2 grows from a few hundred to tens of thousands of records. The group has enough members and partition 2 is assigned to an active consumer.

Next, topic metadata shows partition 2 has a healthy leader and ISR. Brokers have no offline or under-replicated partitions. Consumer logs show the same offset on partition 2 repeatedly throwing `InvalidOrderEventException`; other partitions process normally.

The operations team determines this is a single-event data error, not insufficient consumer capacity. They inspect the payload in an approved tool, confirm a required field is missing due to a newly deployed producer schema, and coordinate fixing the data contract. Per agreed policy, the failing record is routed to the DLT with source metadata and offset; the consumer resumes processing remaining records. Once the producer is fixed, the team replays the corrected record following the idempotent replay procedure.

Recovery is confirmed by partition 2 lag dropping, committed offsets advancing steadily, the DLT record tracked, and zero business duplicates. Had they scaled out pods from the start, partition 2 would still only be handled by one consumer in the group and the data error would remain.

## 15. Handover Checklist When an Incident Continues

When handing off a shift or escalating to the Kafka/platform team, record enough context so the next responder does not start from scratch:

- Exact cluster, environment, topic, and consumer group.
- Affected partitions and currently assigned consumer instances.
- Committed offsets, end offsets, and lag at handover time.
- Lag and throughput trends during the observation window.
- Leader, replicas, and ISR for relevant partitions.
- Consumer members, rebalances, and recent restarts.
- Exceptions, event IDs/offsets, and retry/DLT status if applicable.
- Dependency metrics such as database, HTTP clients, thread pools, and pod resources.
- Changes already applied, who performed them, and measured outcomes.
- Open hypotheses, risks, and next steps with assigned owners.

Isolating by topic and partition creates a verifiable investigation path: start from cluster and business flow scope, examine per-partition progress, cross-check assignments and broker health, and tie lag to listener errors, key distribution, and dependencies. When every conclusion anchors to a concrete topic, partition, offset, and timestamp, operations teams recover more accurately and avoid actions that lose data or alter processing order unexpectedly.
