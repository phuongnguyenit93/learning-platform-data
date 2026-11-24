# Reliability Operations in Spring Kafka

Reliability Operations is the set of designs, configurations, monitoring processes, and operational procedures that help a Spring Kafka system continue processing events correctly during application errors, network failures, broker disconnects, consumer restarts, or sudden traffic spikes. The goal is not only to keep the application running, but also to control three critical outcomes: preventing the loss of accepted events, limiting duplicate processing that causes data inconsistencies, and recovering events that cannot be processed immediately.

Spring Kafka provides components such as `KafkaTemplate`, listener containers, `CommonErrorHandler`, `DefaultErrorHandler`, `DeadLetterPublishingRecoverer`, retry topics, and transaction support. These components form the foundation for reliable operations, but ultimate reliability also depends on Kafka cluster configuration, offset management, business idempotency, retry strategies, observability, and incident response procedures.

## 1. Defining Reliability Goals

Before configuring Spring Kafka, you need to define what counts as an accepted event, when a processing attempt is considered complete, and how the system must respond when an event cannot be processed.

| Concern | Operational Question | Commonly Used Mechanism |
|---|---|---|
| Producer publishing events | When the broker acknowledges, does the data have enough replicas to tolerate faults? | `acks=all`, replication, `min.insync.replicas`, producer idempotence |
| Consumer processing events | After what point is the offset committed/acknowledged? | Container-managed acknowledgement, `enable.auto.commit=false`, appropriate ack mode |
| Duplicate processing | If a record is redelivered, does the business logic produce duplicate side effects? | Idempotency key, unique constraint, inbox/deduplication |
| Transient errors | Should it be retried, and for how long? | Backoff, bounded retry, retry topics |
| Unrecoverable errors | How do we retain the record and continue processing other records? | Dead-letter topic (DLT), investigation and replay process |
| Widespread incidents | How do we detect issues before users are impacted? | Metrics, logs, tracing, alerts, and runbooks |

Goals should be expressed as measurable SLOs, such as the maximum time an event is allowed to stay in a queue, processing success rate, incident recovery time, and failed record backlog count. Alert thresholds should be based on baseline load, business characteristics, and system recovery capacity; no single number fits every Kafka cluster.

## 2. Understanding Delivery Semantics Accurately

Kafka and Spring Kafka can support multiple levels of delivery guarantees. You must distinguish between a producer sending successfully, a broker storing the data, and a consumer completing the business logic. These are different milestones.

| Semantics | Behavior | Trade-off |
|---|---|---|
| At-most-once | The offset or completion status is acknowledged before processing finishes | Records may be lost if the application stops after acknowledgement but before business logic completes |
| At-least-once | Records are only acknowledged after processing; records may be redelivered | Minimizes record loss, but business logic must tolerate duplicate processing |
| Exactly-once in Kafka | Reading, processing, and writing to Kafka within a transaction can be committed atomically | The guarantee scope primarily lies within the Kafka flow; it does not automatically cover databases, HTTP APIs, or external systems |

For most business consumers, at-least-once combined with idempotent processing is the practical choice. If a consumer completes a database update but crashes before the offset is committed, Kafka may redeliver the record. That is not necessarily a Kafka bug; it is a normal consequence of at-least-once. The application needs to recognize the same event and avoid applying the business side effect a second time.

You should not advertise a system as exactly-once merely because the producer enables idempotence or the application uses transactions. Producer idempotence helps prevent duplicate records caused by retries at the producer layer. Kafka transactions can coordinate reading offsets and writing Kafka records. Neither automatically makes a database balance deduction or an HTTP request exactly-once.

## 3. Configuring the Producer for Reliable Delivery

The producer needs to know to what level the broker has received the data, how long to retry, and what to do when sending fails. A baseline configuration for a critical producer can be declared in Spring Boot as follows:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      retries: 2147483647
      properties:
        "[enable.idempotence]": true
        "[max.in.flight.requests.per.connection]": 5
        "[delivery.timeout.ms]": 120000
        "[request.timeout.ms]": 30000
~~~

This is an illustrative configuration that must be tuned according to the Kafka client version, Spring Boot version, SLA, and actual traffic characteristics.

- `acks=all` requires the partition leader broker to wait for acknowledgement from replicas currently in the in-sync replica set (ISR) according to the Kafka protocol. Actual protection also depends on the topic or broker `min.insync.replicas`.
- `enable.idempotence=true` helps the producer avoid creating duplicate records due to retries within a producer session and supports ordering under compatible configuration constraints.
- `retries` allows the producer to retry recoverable errors. Do not treat a large retry count as an infinite delivery guarantee; `delivery.timeout.ms` still caps the total delivery time for a record.
- `max.in.flight.requests.per.connection` must satisfy compatibility constraints with idempotence. A value of at most 5 is a common configuration for modern Kafka producers.
- `request.timeout.ms` limits the wait time for a single request; `delivery.timeout.ms` covers queuing, retries, and record delivery. Set a sensible relationship between the two values while accounting for network latency and broker processing time.

`acks=all` is only meaningful when the topic has an appropriate replication factor and the ISR does not shrink below the safe threshold. For example, a topic with replication factor 3 and `min.insync.replicas=2` typically tolerates one replica failure while still requiring at least two synchronized replicas to acknowledge. If the ISR drops below the minimum, the producer may receive an error rather than accepting a write with lower durability. This is necessary behavior to protect data, but the application must have alerts and handling procedures.

### 3.1. Handling Send Results from KafkaTemplate

Do not treat calling `KafkaTemplate.send()` as proof that the broker has accepted the record. Observe the asynchronous result and handle send failures:

~~~java
CompletableFuture<SendResult<String, OrderCreated>> send =
        kafkaTemplate.send("orders", orderId, event);

send.whenComplete((result, error) -> {
    if (error != null) {
        // Record the send failure, correlation id, and information needed for investigation.
        // Only retry at the business layer when a duplicate-send prevention policy is in place.
        log.error("Cannot publish order event, orderId={}", orderId, error);
        return;
    }

    RecordMetadata metadata = result.getRecordMetadata();
    log.debug("Published order event: topic={}, partition={}, offset={}",
            metadata.topic(), metadata.partition(), metadata.offset());
});
~~~

In Spring Kafka 3.x, the send method returns a `CompletableFuture`. Older versions may use a different future type; verify the API against your project's dependency version.

If the business operation may only be confirmed to the caller after Kafka has received the record, wait on or coordinate the send result in a manner appropriate for the request flow. Avoid arbitrarily blocking threads on the request path or inside a listener. If sending fails after the business operation has already returned success, there must be a recovery mechanism such as a transactional outbox or a stateful resend queue.

### 3.2. Choosing Keys and Partitions Deliberately

Kafka guarantees ordering only within a single partition. Events that require ordering, such as state transitions for the same order, should use the same stable key such as `orderId`. The producer uses the key to select a partition via the partitioner.

Unevenly distributed keys can create a hot partition: one partition receives most of the traffic, causing its consumer to lag while other partitions remain idle. Monitor traffic and lag per partition. Increasing the partition count can change the key-to-partition mapping, so evaluate the impact on the ordering of existing events before making changes.

## 4. Configuring the Consumer and Managing Offsets

The consumer must determine when to commit offsets so that a record is considered complete only after the business state is durably persisted. A baseline configuration typically disables auto commit so the listener container manages acknowledgements:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
      auto-offset-reset: earliest
      properties:
        "[max.poll.records]": 100
        "[max.poll.interval.ms]": 300000
    listener:
      ack-mode: record
~~~

`auto-offset-reset` is only used when the group has no valid committed offset yet or the current offset is no longer within the log range. `earliest` allows reading retained data on the topic; `latest` starts from new data. This is not a substitute for managing committed offsets.

### 4.1. Choosing an Acknowledgement Mode

With `AckMode.RECORD`, the container commits the record's offset after the listener finishes processing that record successfully. This is a straightforward starting point for record-by-record listeners.

With `AckMode.BATCH`, offsets are committed per batch returned by a single poll. If an error occurs within a batch, the error handler and container must coordinate seeking or redelivering the incomplete records.

With `MANUAL` or `MANUAL_IMMEDIATE`, the application explicitly invokes acknowledgement. Only acknowledge after the business effect has been durably persisted. Acknowledging too early can forfeit the ability to reprocess the record if the application crashes.

Example of a listener processing a single record:

~~~java
@KafkaListener(topics = "orders", groupId = "billing-service")
public void consume(OrderCreated event) {
    billingService.createInvoiceIdempotently(event);
}
~~~

If `createInvoiceIdempotently` throws an exception, the container can apply retry or an error handler. Only when the method returns normally does the container consider the record successfully processed according to the configured ack mode.

### 4.2. Tuning Poll and Processing Time

A Kafka consumer must call `poll()` frequently enough. If the time between polls exceeds `max.poll.interval.ms`, the consumer may be considered dead and its partitions rebalanced to other members.

- `max.poll.records` limits the number of records returned in a single poll. Lowering this value can reduce per-batch processing time while increasing poll frequency.
- `max.poll.interval.ms` must be larger than the batch processing time under foreseeable slow conditions, plus a safety margin.
- `session.timeout.ms` and heartbeats relate to detecting consumer disconnects. Do not change them independently without understanding group coordination mechanics.
- Spring listener container `concurrency` creates consumers running in parallel. Within a consumer group, the number of usefully active consumers typically does not exceed the topic's partition count.

If a listener performs long-running work such as calling external APIs, generating large reports, or processing files, consider offloading the work to an internal worker and explicitly designing the acknowledgement point. Do not submit records to an unbounded executor and acknowledge immediately; if the application stops, acknowledged but unfinished tasks will not be redelivered by Kafka.

### 4.3. Designing Idempotent Business Logic

An at-least-once consumer must tolerate the same event being processed multiple times. A common approach is storing `eventId` in an inbox table with a unique constraint inside the same database transaction as the business update:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

The processing flow can execute in the following order:

1. Start the database transaction.
2. Attempt to insert `eventId` into the `processed_events` table.
3. If a unique constraint violation occurs, the event has already been processed; end the transaction without repeating the side effect.
4. If the insert succeeds, perform the business update.
5. Commit the database transaction, then let the listener complete and commit the offset.

Recording the event marker and updating business state must occur within the same database transaction. If you record the marker first and update business state in a separate transaction, a failure between the two steps can leave the event marked as processed even though the business effect never happened.

## 5. Retries and Error Handling in Spring Kafka

Not every error should be retried. A brief network glitch may self-recover; malformed data or business rule violations usually cannot be fixed by redelivering the same record.

| Error Category | Examples | Handling Strategy |
|---|---|---|
| Transient | Database timeout, downstream service connection error, recent broker leader election | Retry with backoff and a cap |
| Invalid data | Missing required fields, out-of-domain values | Do not retry, or retry only after data correction |
| Configuration/deployment errors | Schema mismatch, missing permissions, non-existent topic | Alert and fix the root cause; avoid tight retries |
| Unknown errors | Unclassified exceptions | Finite retries, then route to DLT for investigation |

Unbounded retries can keep a partition occupied, increasing consumer lag and stalling subsequent records. Backoff reduces pressure on a failing service. The retry count and total wait duration should be based on the dependency's recovery characteristics and the business processing deadline.

### 5.1. Blocking Retry with DefaultErrorHandler

Spring Kafka provides `DefaultErrorHandler` to retry records inside the listener container and forward them to a recoverer once retries are exhausted. The following example uses exponential backoff:

~~~java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);

    ExponentialBackOffWithMaxRetries backOff =
            new ExponentialBackOffWithMaxRetries(4);
    backOff.setInitialInterval(1_000L);
    backOff.setMultiplier(2.0);
    backOff.setMaxInterval(10_000L);

    DefaultErrorHandler handler =
            new DefaultErrorHandler(recoverer, backOff);
    handler.addNotRetryableExceptions(
            IllegalArgumentException.class);

    return handler;
}
~~~

Attach the error handler to the listener container factory used by the application:

~~~java
factory.setCommonErrorHandler(kafkaErrorHandler);
~~~

This example illustrates how to wire the components together; the generic types of `KafkaTemplate`, the factory, and serializer configurations must match the actual application. In older Spring Kafka versions, the error handler API may differ.

`ExponentialBackOffWithMaxRetries(4)` specifies the number of retries after the initial processing attempt according to the Spring Kafka API. Verify how attempts are counted in your specific version and its corresponding documentation to avoid misunderstanding the total number of listener invocations.

Blocking retry is suitable when partition-level ordering must be preserved and errors are likely to recover quickly. During the retry wait, the consumer thread's processing capacity is reduced; if errors persist, lag can grow rapidly.

### 5.2. Non-blocking Retry with Retry Topics

Retry topics move failed records to a delayed retry topic, allowing the main topic consumer to continue processing other records. Spring Kafka supports this approach via `@RetryableTopic`:

~~~java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(
                delay = 1_000,
                multiplier = 2.0,
                maxDelay = 10_000),
        dltTopicSuffix = ".DLT")
@KafkaListener(topics = "orders", groupId = "billing-service")
public void consume(OrderCreated event) {
    billingService.createInvoiceIdempotently(event);
}

@DltHandler
public void handleDlt(OrderCreated event) {
    dltOperations.recordForInvestigation(event);
}
~~~

In this configuration, `attempts` is the total number of attempts per the annotation's convention, including the initial processing attempt. Check your Spring Kafka version and configured exception types to know exactly which topics a record will traverse.

Retry topics are useful when you do not want a failing record to block the entire main partition's progress. On the other hand, a retried record may arrive after newer records, so business ordering across events with the same key can change. If ordering is strictly required, consider blocking retry or redesigning the business flow.

Avoid inadvertently stacking multiple independent retry layers—such as listener retries, service-layer retries, HTTP client retries, and retry topics—without calculating the total number of calls. A single record could generate far more dependency calls than intended. Designate one primary layer responsible for retries, cap total elapsed time, and propagate correlation/event IDs across attempts.

## 6. Dead-Letter Topics and Recovery Procedures

A DLT retains records that cannot be processed after retries so the system can keep moving forward. A DLT is an operational queue that requires management, not an indefinite error dumping ground.

When configuring `DeadLetterPublishingRecoverer`, Spring Kafka typically derives the destination topic name by appending `.DLT` to the source topic and preserves the corresponding partition by default. Therefore, the DLT must have at least as many partitions as the source topic when using default mapping. If a different mapping is desired, provide an appropriate resolver.

When a record enters the DLT, preserve information needed for investigation:

- Original topic, partition, and offset.
- Key and event id to locate related events.
- Exception class, error message, and failure timestamp.
- Attempt count and any retry topics traversed.
- Correlation id or trace id to link logs across services.

Do not log sensitive payloads or full stack traces indiscriminately in application logs. Restrict read permissions on the DLT, apply appropriate retention policies, and comply with system data regulations.

### 6.1. DLT Handling Procedure

A DLT operational procedure can include the following steps:

1. Alert when the rate of new records entering the DLT spikes abnormally or the age of the oldest record exceeds a threshold.
2. Operations identifies the cause by exception, schema version, topic, partition, and deployment timestamp.
3. Classify records: data needing repair, code bugs needing a patch release, dependency outages, or events no longer valid for business processing.
4. Fix the root cause and verify with a few representative records in an appropriate environment.
5. Replay in a controlled manner, rate-limit the replay, and monitor results.
6. Reconcile replayed record counts, succeeded counts, and still-failing counts; retain an audit trail.

Replay must be designed to be idempotent because a record may have already produced partial side effects before failing. Do not replay the entire DLT immediately after fixing code without assessing the impact of duplicate processing. For ordered events, consider replaying by key or in original order.

### 6.2. Ensuring DLT Publishing Succeeds

Do not treat calling the recoverer as proof that the DLT has persisted the record. Check the configuration and API of your Spring Kafka version to ensure DLT send failures are propagated back to the container rather than committing the source offset while the record has not been saved to the DLT. On supported versions, you can configure the recoverer to wait for the send result and treat send failures as recoverable/failing errors. Test the scenario where the DLT broker is unavailable before deploying.

## 7. Serialization and Schema Compatibility

A record may fail to be processed because the consumer cannot deserialize the key or value. This error occurs before the listener receives the business object, so deserialization error handling must be designed separately.

Spring Kafka provides `ErrorHandlingDeserializer`, which wraps the actual deserializer and forwards error metadata for the error handler/recoverer to handle. Delegate configuration must match the producer's serializer and the data format on the topic. If using JSON, manage type headers, trusted packages, and schema evolution explicitly.

Key operational principles:

- Evolve schemas compatibly with producers and consumers running concurrently.
- Deploy consumers capable of reading the old schema before producers begin emitting the new schema.
- Do not use arbitrary class names from message headers as a trust boundary.
- Route records that fail deserialization into an appropriate investigation flow, retaining the raw payload where security policies allow.
- Maintain schema version control and a rollback procedure when a release causes widespread failures.

If a deployment causes a sudden spike in deserialization failures, treat it as a schema compatibility or serializer/deserializer configuration incident. Retrying the same payload with the same binary usually will not resolve the root cause.

## 8. Transactions, Exactly-Once, and Outbox/Inbox

### 8.1. Kafka Transactions

Kafka transactions allow a producer to write multiple records to Kafka as an atomic unit. For consume-transform-produce flows, Spring Kafka can coordinate producing output records and committing input offsets within a transaction. If the transaction is aborted, outputs are not treated as committed and input offsets do not advance as a successful transaction.

When enabling transactions for a producer, configure a unique transaction id prefix across concurrently running application instances. Do not reuse the same prefix in a way that causes transactional id collisions across instances. Consumers reading transactional data should set `isolation.level=read_committed` if they should only receive records from committed transactions.

Kafka transactions are suitable when both inputs and outputs reside in Kafka. They do not turn a database transaction and a Kafka transaction into a single atomic distributed transaction.

### 8.2. Transactional Outbox

A common scenario is an application both updating a database and publishing a Kafka event. If the database write succeeds but the Kafka send fails, the two systems fall out of sync. If Kafka is sent to first and the database rolls back, consumers may receive an event that does not correspond to database state.

Transactional outbox solves this by writing the business change and an outbox record within the same database transaction. A separate publisher reads the outbox and publishes events to Kafka; after a successful send, it marks the record or saves a published checkpoint. The publisher can still produce duplicates if a failure occurs between broker acknowledgement and recording the sent status in the database, so consumers still require idempotency.

~~~sql
CREATE TABLE outbox_events (
    event_id VARCHAR(100) PRIMARY KEY,
    aggregate_id VARCHAR(100) NOT NULL,
    event_type VARCHAR(200) NOT NULL,
    payload TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP NULL
);
~~~

The outbox needs its own operational process: monitoring unpublished record counts, age of the oldest unpublished record, publisher throughput, send errors, and replay capability. Establish a cleanup policy for published records after an appropriate retention period.

### 8.3. Consumer-Side Inbox

An inbox or processed-events table prevents consumers from duplicate processing when Kafka redelivers a record. The event id must remain stable across the producer, retry topics, and DLT. If a new event id is generated on each retry, deduplication will fail to recognize the same event.

When calling external services such as payments or notifications, use a business-defined idempotency key and leverage the target API's idempotency support if available. If the target API does not support idempotency, maintain intermediate processing states and a reconciliation process to handle ambiguous timeout outcomes.

## 9. Durability of Kafka Clusters and Topics

Producer configuration cannot compensate for a topic with weak replication and ISR policies. For critical data, coordinate topic, broker, and producer configurations.

| Setting | Operational Meaning |
|---|---|
| `replication.factor` | Number of copies of a partition across brokers |
| `min.insync.replicas` | Minimum number of synchronized replicas required to accept writes when the producer uses `acks=all` |
| `unclean.leader.election.enable` | Whether out-of-ISR replicas are allowed to become leader; enabling may increase availability at the risk of data loss |
| `retention.ms` / `retention.bytes` | Duration or size of data retained on the topic |
| `cleanup.policy` | How Kafka cleans up data, such as delete or compact |

A common configuration for critical topics is replication factor 3, `min.insync.replicas=2`, producer `acks=all`, and unclean leader election disabled. This is a common design example, not a mandatory default; consider broker count, failure domains, capacity, and cluster availability requirements.

Monitor cluster metrics such as offline partitions, under-replicated partitions, ISR shrink/expand events, broker disk usage, request latency, and controller health. A partition that loses a replica may still serve requests, but its fault tolerance is reduced. Alerts should fire before the next broker fails.

Retention must be long enough for consumers to recover after an outage or lag spike. If a consumer is stopped longer than the retention period, its offset may fall outside the retained log; `auto.offset.reset` may then cause the consumer to start at a different position, requiring data reconciliation. DLTs also need sufficiently long retention for investigation and replay per SLA.

## 10. Rebalance, Scaling, and Application Deployment

A rebalance occurs when consumers join or leave a group, heartbeats are missed, polling is too slow, or subscriptions change. Frequent rebalances reduce useful processing time and can increase duplicate deliveries as unfinished work is reassigned.

To minimize impact:

- Keep batch processing time within `max.poll.interval.ms`.
- Choose `max.poll.records` to match processing duration and memory capacity.
- Avoid cycling consumer instances continuously due to flaky health checks or oscillating autoscaling.
- Perform rolling updates with a shutdown grace period long enough for listeners to stop accepting new work and finish in-flight processing.
- Monitor rebalance frequency, partition revoke/assign duration, and reasons consumers leave the group.
- Increase concurrency only when sufficient partitions and downstream capacity exist.

If a topic has 6 partitions and a group has 10 consumer instances, at most 6 consumers can be assigned partitions at one time; the remaining instances add no throughput to that group. Increasing partitions can increase parallelism, but it also changes key-to-partition mapping and increases management overhead.

When deploying a new version, account for compatibility between producers and consumers running concurrently during rollout. Avoid changing message formats in ways older consumers cannot read. For major changes, use an expand-and-contract strategy: deploy compatible consumers first, then switch producers, and remove legacy support in a subsequent release.

## 11. Observability: Metrics, Logs, and Tracing

A reliable Kafka system must tell you where records are, which step is slow, and whether errors are trending upward. Monitoring only whether the process is running is not enough.

| Area | Metrics to Track | Signals Requiring Investigation |
|---|---|---|
| Producer | Send rate, error rate, retry rate, request latency, record size, buffer availability | Rising send errors, prolonged retries, buffer exhaustion |
| Consumer | Consumer lag by group/topic/partition, records consumed rate, poll interval, commit failures | Continuously rising lag, dropping throughput, commit errors |
| Listener | Processing duration, exception rate, retry count, records recovered | Rising processing duration, recurring exception type |
| Retry/DLT | Records entering retry topics and DLT, age of oldest record | Rapid DLT growth or records stuck for a long time |
| Cluster | Offline/under-replicated partitions, ISR, broker disk, request latency | Lost replicas, disk nearly full, slow broker responses |
| Business | Events accepted, completed, failed, and reconciled | Discrepancy between source emissions and business outcomes |

Spring Kafka integrates with Micrometer in supported versions to export listener and Kafka client metrics. Metric names and tags can vary by version; inspect the actual metrics endpoint after enabling instrumentation. Avoid creating high-cardinality tags such as event id, order id, or customer id.

Logs should include event id, topic, partition, offset, consumer group, correlation id, and handler name when available. Do not log full payloads by default because payloads may contain personal or confidential data. Trace context should be propagated via message headers and restored on the consumer side to link producers with downstream processing steps.

Useful alerts generally focus on trends and backlog age rather than a single instantaneous value:

- Lag rising continuously over a sustained period.
- Age of the oldest record exceeding the business deadline.
- Producer error rate or send latency exceeding baseline.
- New records appearing in the DLT or rapid DLT growth.
- Offline or under-replicated partitions appearing.
- A spike in rebalances following a deployment.
- Outbox backlog remaining unpublished longer than the event-publishing SLA.

## 12. Health Checks and Resilience

Health checks must accurately reflect serving readiness. If Kafka temporarily loses connectivity, a liveness probe should not immediately trigger continuous container restarts; a restart storm can amplify rebalances and add load to the cluster.

You can distinguish between:

- **Liveness:** the process and main threads are running and not deadlocked.
- **Readiness:** whether the instance is eligible to receive more work, factoring in dependency state and processing capacity.
- **Business health:** whether event flows are completing within business deadlines; usually tracked through dedicated metrics and alerts.

Whether to include Kafka in readiness depends on architecture. If all instances are marked not-ready simultaneously when a broker has an issue, the orchestrator may remove every instance from service even though they could recover once the broker returns. Define the desired behavior when Kafka is unavailable and test that scenario.

During shutdown, listener containers should be stopped gracefully so in-flight records complete within the grace period. If the timeout expires, accept the possibility of record redelivery and ensure consumers are idempotent.

## 13. Runbooks for Common Incidents

### 13.1. Producer Unable to Send Records

1. Identify the specific error: timeout, authorization, serialization, unknown topic, or ISR error.
2. Check broker connectivity, ACLs, metadata, and partition leader status.
3. Review producer retry rate, request latency, and buffer availability.
4. If the error is caused by ISR or brokers, remediate the cluster per operational procedures; do not lower `acks` just to silence alerts.
5. Identify business requests that received a send failure or ambiguous outcome; reconcile and retry using a stable event id.

### 13.2. Increasing Consumer Lag

1. Determine whether lag affects the entire group or only specific partitions.
2. Compare incoming rate against consumed rate to distinguish producer traffic spikes from degraded consumer capacity.
3. Check processing duration, exception/retry rates, downstream latency, and rebalances.
4. Inspect key distribution to identify hot partitions.
5. Increase consumer concurrency only if partition count and downstream systems permit; otherwise optimize processing or increase partitions after assessing ordering impact.
6. Monitor the age of the oldest record until it returns within SLO.

### 13.3. DLT Spike

1. Group records by exception class, source topic, schema version, and timestamp of occurrence.
2. Check recent code/config changes and dependency health.
3. Pause or throttle automated replay if it is generating load or repeatedly failing.
4. Fix the root cause and verify with representative records.
5. Replay in rate-limited batches, preserving event ids and recording an audit log.
6. Reconcile business outcomes to confirm no lost or duplicated side effects.

### 13.4. Continuous Rebalancing

1. Check group coordinator logs and reasons for members leaving the group.
2. Measure processing time between polls relative to `max.poll.interval.ms`.
3. Check for GC pauses, CPU throttling, network interruptions, and hung downstream calls.
4. Adjust batch size or processing duration; modify timeouts only after understanding the root cause.
5. After deployment, compare rebalance frequency and lag against the pre-deployment baseline.

### 13.5. Broker or Availability Zone Outage

1. Identify the scope of affected brokers/zones and partitions.
2. Check leader election, ISR, and offline partitions.
3. Confirm whether producers are rejecting writes due to `min.insync.replicas`.
4. Recover brokers per cluster procedures, monitoring replica catch-up and disk usage.
5. Once the cluster stabilizes, monitor producer retries, consumer lag, and DLT for residual errors.

## 14. Pre-Release Reliability Testing

Happy-path testing is insufficient to prove a reliable Kafka configuration. Integration tests should simulate potential failure points:

- Broker temporarily unavailable while the producer sends.
- Consumer stops after database commit but before offset commit.
- Listener throws exceptions multiple times and then recovers.
- DLT unavailable when the recoverer attempts to publish.
- Malformed or schema-incompatible payloads.
- Consumer restarted or rebalanced mid-processing.
- A downstream dependency slower than normal latency.
- Retries and replays not producing duplicate business side effects.

Kafka Testcontainers or an embedded broker matching your Spring Kafka version can be used for integration tests. Tests should verify both business outcomes and Kafka state: whether records are preserved, retried the expected number of times, routed to the DLT, and whether offsets advance only after successful recovery.

Beyond integration tests, run operational game-day exercises in a production-like environment: ramp load, stop a broker, induce consumer lag, recover a DLT, and execute rolling deployments. Record time to detect, time to recover, and runbook updates needed.

## 15. Production Operations Checklist

### Before Deployment

- [ ] Critical topics have appropriate replication factor, `min.insync.replicas`, and retention.
- [ ] Producer uses `acks=all` and idempotence when business requirements demand that level of protection.
- [ ] Consumer disables auto commit and selects an intentional ack mode.
- [ ] Listener is idempotent or uses an inbox/deduplication mechanism with a stable event id.
- [ ] Retries are bounded, use backoff, and classify exceptions.
- [ ] DLT has partitions, ACLs, retention, alerts, and a replay procedure.
- [ ] Producer/consumer schemas are compatible across the rollout window.
- [ ] Metrics, logs, tracing, and dashboards have been verified.
- [ ] Shutdown grace period and health checks accurately reflect behavior when Kafka is unavailable.

### During Operations

- [ ] Monitor consumer lag and age of the oldest record.
- [ ] Monitor producer error/retry rates and ISR health.
- [ ] Monitor DLT, retry topics, and outbox backlog.
- [ ] Investigate abnormal rebalances and hot partitions.
- [ ] Replay failed records in controlled, audited batches.
- [ ] Reconcile event counts against business outcomes after incidents.

### After an Incident

- [ ] Identify root cause and the scope of affected records.
- [ ] Check for duplicates, missing events, and inconsistent business state.
- [ ] Confirm all backlogs have returned to normal levels.
- [ ] Update alerts, runbooks, retry policies, or idempotency as needed.
- [ ] Document lessons learned and preventive actions with assigned owners.

## Conclusion

Reliable Spring Kafka operations require coordinating producer acknowledgements, cluster replication, offset management, consumer idempotency, bounded retries, DLTs with recovery procedures, and deep observability. Design for record redelivery, temporary dependency unavailability, and consumer rebalances, then test those scenarios before going to production. When these mechanisms operate together, the system can continue processing the vast majority of events under failure conditions and provide enough evidence to recover the remainder in a controlled manner.
