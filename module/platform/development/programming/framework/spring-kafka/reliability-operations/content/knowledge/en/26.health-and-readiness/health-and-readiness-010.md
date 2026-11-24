# DLT Producer Fails to Send

In Spring Kafka, a Dead Letter Topic (DLT) stores records that a consumer cannot process under the configured policy. An error handler can retry a record multiple times and then invoke `DeadLetterPublishingRecoverer` to publish the record to a DLT. However, **calling the recoverer does not mean the record was safely stored in the DLT**: the producer can encounter serialization errors, missing write permissions, invalid topic/partition, an unavailable broker, timeouts, or transaction rollbacks.

If the DLT producer fails to send yet the application still treats the source record as successfully recovered, the record can be skipped on the source topic while no DLT copy exists. This is a dangerous failure mode because consumer lag on dashboards may keep dropping while data needed for investigation or replay has vanished from the main flow.

This lesson explains how Spring Kafka handles DLT publish failures, how to configure recovery so DLT send errors propagate back to the error handler, how to include DLT producer status in health/readiness, and how to operate when the DLT path becomes unreliable.

## 1. Where does the DLT producer sit in the error-handling flow?

A consumer listener can throw an exception while processing a record. The Spring Kafka error handler applies retry/backoff; once retries are exhausted or the exception is classified as non-retryable, the recoverer is invoked.

~~~mermaid
flowchart TD
    A["ConsumerRecord from source topic"] --> B["Listener processes"]
    B -->|Success| C["Ack / commit per container"]
    B -->|Exception| D["DefaultErrorHandler"]
    D --> E{"Retries left?"}
    E -->|Yes| F["Backoff then retry record"]
    F --> B
    E -->|No| G["DeadLetterPublishingRecoverer"]
    G --> H["KafkaTemplate / DLT producer"]
    H --> I{"Broker acknowledged?"}
    I -->|Yes| J["Recovery complete"]
    J --> K["Source offset confirmed per policy"]
    I -->|No| L["Recovery failure"]
    L --> M["Exception returns to error-handling flow"]
    M --> N["Record is not considered recovered"]
~~~

Crucially, DLT publishing is **an independent I/O operation**. The listener already failed; the recoverer must write the record to the recovery destination. Only when the publish outcome is confirmed per configuration and the recovery handler returns normally can the container proceed to commit source progress per policy.

If a send runs asynchronously without checking its outcome, the application can confuse "submitted a publish request" with "broker acknowledged the record."

## 2. Why are DLT publish failures especially dangerous?

Suppose the record at `orders-3@1842` hits a business processing error. The error handler has exhausted retries and invokes the DLT recoverer.

~~~text
Source record: orders partition 3 offset 1842
       |
       v
Listener throws InvalidOrderException
       |
       v
Retry exhausted
       |
       v
DLT producer sends to orders.DLT
       |
       +-- Send succeeds -> record can be recovered
       |
       +-- Send fails but failure is ignored
              |
              v
          Recoverer returns normally
              |
              v
          Source offset may advance
              |
              v
          Original record is no longer redelivered
          and no DLT copy exists
~~~

If recovery is treated as successful while the DLT send failed, the system can lose the ability to recover the record. Consequences:

- The business event is never processed.
- The DLT has no record for operators to investigate.
- The source consumer group may commit offsets past the record.
- Consumer lag drops, creating the illusion of a healthy pipeline.
- Replay via the DLT workflow is impossible because the record does not exist.
- Audit trails and incident reconstruction lack data.

Therefore, **the DLT producer is part of the reliability path**, not an auxiliary logging utility.

## 3. DeadLetterPublishingRecoverer uses KafkaTemplate

Spring Kafka provides `DeadLetterPublishingRecoverer` to publish failed records to a destination topic. The recoverer uses the `KafkaTemplate`/`KafkaOperations` supplied to its constructor or resolver.

Basic example:

~~~java
@Bean
DeadLetterPublishingRecoverer deadLetterPublishingRecoverer(
        KafkaTemplate<Object, Object> dltTemplate) {

    return new DeadLetterPublishingRecoverer(dltTemplate);
}
~~~

When using the default recoverer, Spring Kafka typically builds the destination topic by appending the `.DLT` suffix to the source topic and preserving the source record's partition number. Example:

~~~text
source: orders partition 3 offset 1842
destination: orders.DLT partition 3
~~~

This is the common default convention; an application can configure a destination resolver to use a different topic/partition.

**Ensure the destination exists and has compatible partitions.** If the source topic has 12 partitions while the DLT has only 3 partitions, trying to send a record from source partition 8 to DLT partition 8 can fail. Topic creation, ACLs, and partition counts must be verified before putting listeners into production.

## 4. Do not confuse a send request with a send acknowledgement

`KafkaTemplate.send()` is asynchronous. It returns a future indicating the send result after the producer receives a broker response or encounters an error.

~~~java
CompletableFuture<SendResult<Object, Object>> future =
        kafkaTemplate.send("orders.DLT", key, value);
~~~

Merely calling `send()` successfully does not prove the broker persisted the record. Failures that can happen after the method returns:

- Broker fails to acknowledge before timeout.
- Network connection is reset.
- Topic or partition does not exist.
- Authorization is denied.
- Serializer throws an exception.
- Record exceeds size limits.
- Producer is fenced or transaction aborts.
- Broker lacks sufficient replicas under `acks` and `min.insync.replicas`.

Therefore, when DLT publishing is required to mark a source record recovered, there must be a mechanism to **observe the future result and turn send failures into recovery failures**.

## 5. Configuring the recoverer so send failures are not ignored

`DeadLetterPublishingRecoverer` has the `failIfSendResultIsError` setting to control whether to throw an exception when a send result fails. When you need to guarantee that a DLT send succeeded before recovery is treated as complete, enable fail-on-send-error behavior per the API of your Spring Kafka version.

Example:

~~~java
@Bean
DeadLetterPublishingRecoverer deadLetterPublishingRecoverer(
        KafkaTemplate<Object, Object> dltTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(dltTemplate);

    recoverer.setFailIfSendResultIsError(true);

    return recoverer;
}
~~~

When enabled, send failures are surfaced by an exception from the recoverer instead of logging and treating recovery as complete. The error handler can then detect recovery failure and apply the appropriate policy.

Verify the default of the exact Spring Kafka version you are running; do not rely on a memorized default from another version. In critical systems, explicit configuration plus an integration test for DLT broker unavailability is far safer to control.

## 6. Waiting for send results

The recoverer may need to wait for the send result for a finite duration. Spring Kafka provides send-result wait timeout configuration on `DeadLetterPublishingRecoverer` in supported versions, including `setWaitForSendResultTimeout` and `setTimeoutBuffer`.

Illustrative example:

~~~java
recoverer.setFailIfSendResultIsError(true);
recoverer.setWaitForSendResultTimeout(Duration.ofSeconds(20));
~~~

API names and overloads can differ across versions; verify against your pinned dependency.

A timeout that is too short can treat recovery as failed even while the broker might still acknowledge slightly later. A timeout that is too long blocks the consumer/error-handling thread, extending processing and raising lag. Choose the timeout based on producer `delivery.timeout.ms`, network latency, broker SLA, and total retry budget.

Never set an infinite timeout. If producer sends hang, the system needs a bound so it can detect and escalate to incident handling.

## 7. Destination resolvers and partition mapping

The recoverer can customize a destination resolver to choose the DLT topic and partition:

~~~java
@Bean
DeadLetterPublishingRecoverer recoverer(
        KafkaTemplate<Object, Object> dltTemplate) {

    BiFunction<ConsumerRecord<?, ?>, Exception, TopicPartition> resolver =
            (record, exception) -> {
                String dltTopic = record.topic() + ".DLT";
                return new TopicPartition(
                    dltTopic,
                    record.partition()
                );
            };

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(dltTemplate, resolver);

    recoverer.setFailIfSendResultIsError(true);
    return recoverer;
}
~~~

This snippet preserves the source partition. Routing can be customized by exception type or business domain, but avoid nondeterministic destination logic or routing records to non-existent partitions.

If a resolver returns `null`, behavior depends on recoverer config/API; explicitly decide whether the record should be skipped, handled via fallback, or treated as a recovery failure. For critical data, never let a buggy resolver silently turn into "recovery succeeded."

## 8. DLT topics need enough partitions

If preserving source partitions, the DLT needs matching partitions. A simple approach is keeping the same partition count:

~~~text
orders topic:      12 partitions
orders.DLT topic:  12 partitions
~~~

Reasons:

- Default partition mapping stays predictable.
- Original partition can be preserved in metadata.
- DLT replay can retain partial ordering per source partition.
- Operators can locate records by source coordinates.

If intentionally routing all records into a single DLT partition, understand that ordering across multiple source partitions cannot be restored from offset alone. DLT partition count and partition resolvers are architectural decisions.

Create DLTs via infrastructure-as-code or topic provisioning jobs. Do not rely on broker automatic topic creation in production when you need controlled replication factor, retention, ACLs, and partition counts.

## 9. Configuring DefaultErrorHandler

An example non-transactional listener container:

~~~java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    FixedBackOff backOff = new FixedBackOff(1_000L, 2L);

    DefaultErrorHandler handler =
            new DefaultErrorHandler(recoverer, backOff);

    return handler;
}
~~~

`FixedBackOff(1_000L, 2L)` illustrates two retries after the initial attempt, with a one-second pause between attempts. Real configuration must match exception types and dependency behavior.

Attach the handler to the factory:

~~~java
factory.setCommonErrorHandler(kafkaErrorHandler);
~~~

Once retries are exhausted, the handler calls the recoverer. If the recoverer returns normally, the record is treated as recovered per handler policy. If the recoverer throws an exception because the DLT send failed, the record is **not considered successfully sent to the DLT**; the error handler can continue handling recovery failure according to version/configuration semantics.

Never catch exceptions from the recoverer and return normally inside a custom error handler. Doing so turns a failure into a false success and lets the source offset advance.

## 10. Recovery failure differs from listener failure

There are two separate failures:

1. **Listener failure:** the business method failed to process the record.
2. **Recovery failure:** after retries, the system failed to publish the failed record to the DLT.

Example:

~~~text
Record A
  |
  +-- Listener attempt 1 -> DB timeout
  +-- Listener attempt 2 -> DB timeout
  +-- Listener attempt 3 -> DB timeout
  |
  +-- DLT publish -> authorization failure
~~~

The final failure is not another business listener failure. It is a failure of the record-preservation mechanism after the listener already failed.

Logs and metrics must distinguish:

~~~text
event=listener_processing_failed
event=dlt_publish_attempted
event=dlt_publish_failed
event=recovery_failed
~~~

If everything is logged under a single "consumer error" label, operators will struggle to know whether to fix business logic, DLT ACLs, or broker connectivity.

## 11. What happens to the source offset when DLT publishing fails?

In a non-transactional flow, when the recoverer throws instead of returning normally, the error handler must not treat the record as recovered. Depending on ack mode, seek/retry, and recovery policy, the record can be redelivered or reprocessed later.

Desired model:

~~~text
Listener fails
    |
Retry exhausted
    |
DLT send fails
    |
Recoverer throws
    |
Recovery not completed
    |
Source record remains eligible for retry/redelivery
~~~

Do not state simplistically that "offsets will never commit" without examining container config, ack mode, error handler, transactional mode, and version. What must be guaranteed is that **recovery failure propagates back into control flow** so source records are never marked recovered just because a send request was issued.

Test your application's exact behavior: briefly disconnect the DLT broker, make the listener throw, let the recoverer fail, restore the broker, and verify the source record is reprocessed or recovery continues per policy.

## 12. DLT send can succeed while its acknowledgement is lost

A harder failure: the producer sends the record, the broker appends it, yet the response is lost due to a network timeout. The producer/future reports an error even though the record may already exist in the DLT.

~~~text
Attempt 1:
  Broker appends DLT record
  Ack response lost
  Producer reports timeout

Attempt 2:
  Source record is retried
  DLT record is sent again
  Broker acknowledges
~~~

When the source record is redelivered and the recoverer sends again, the DLT may contain **two copies** of the same business event.

This is why DLT consumers should have idempotency based on business event IDs or original source coordinates. DLT producer idempotence can reduce duplicates from internal producer retries within a session, but it does not replace deduplication when the application issues a new send after redelivery/restart.

If you need exactly-once atomicity between source offsets and DLT output, design appropriate transactional recovery. Never assume a non-transactional send and a source offset commit are automatically atomic.

## 13. DLT producer serialization failures

The DLT may hold a deserialized record value or raw bytes if the error occurred before payload deserialization. This makes the DLT producer's serializer a critical part of recovery.

For example, the source listener uses a JSON deserializer, while the DLT producer is configured only with a DTO serializer. If the record value is `byte[]` due to a deserialization failure, the producer serializer may fail to handle that type.

With multiple payload types, you can configure multiple `KafkaTemplate` instances or suitable serializers. Spring Kafka supports recoverers using a template resolver keyed by key/value types in corresponding versions.

Design must account for:

- Payloads deserialized into DTOs.
- Payloads as raw `byte[]` on deserialization failure.
- Keys with different types from values.
- Tombstone records with `value=null`.
- Header and exception metadata serializer/size constraints.
- DLT consumers needing to understand payload schemas/versions.

Never discard the original payload just because deserialization failed. If the DLT serves forensic/replay purposes, raw bytes and original metadata may need to be preserved.

## 14. Example selecting KafkaTemplate by payload type

One idea is providing a template for DTOs and a template for raw bytes:

~~~java
Map<Class<?>, KafkaOperations<?, ?>> templates = new LinkedHashMap<>();
templates.put(OrderCreated.class, orderTemplate);
templates.put(byte[].class, bytesTemplate);
templates.put(Object.class, fallbackTemplate);

DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(
            record -> selectTemplate(record, templates)
        );
~~~

This is pseudocode illustrating template selection; check exact constructors and resolver overloads against your Spring Kafka version. Do not copy this snippet verbatim if type inference/constructors in your dependency differ.

What matters is that the chosen template has key/value serializers compatible with the actual record. Run integration tests for valid payloads, raw bytes, tombstones, and header metadata.

## 15. Broker, topic, and ACL failures

Common causes preventing DLT producers from sending:

| Failure | Possible Symptoms | Check |
|---|---|---|
| Broker unavailable | Timeout, disconnect | Cluster health, bootstrap, network |
| Topic does not exist | Metadata/unknown topic error | Topic provisioning, auto-create policy |
| Invalid partition | Invalid partition | DLT partition count, resolver |
| Missing `WRITE` ACL | Authorization exception | Principal, topic ACLs |
| Missing `DESCRIBE` ACL | Metadata/authorization issue | Topic and cluster ACLs per policy |
| Leader unavailable | Not leader/leader unavailable | Partition leader, broker state |
| Insufficient ISR | Not enough replicas | Replication, `min.insync.replicas` |
| Message too large | `RecordTooLarge` | Broker/topic/producer max message size |
| Serializer error | `SerializationException` | Serializer config and runtime types |
| Network/TLS/auth error | SSL/SASL/timeout | Certificates, credentials, truststore |
| Quota/throttling | Request delay/throttling | Client/broker quotas |
| Transaction fencing | `ProducerFencedException` | Transactional ID ownership/lifecycle |
| Buffer pressure | `BufferExhausted`/timeout | Producer buffers, downstream broker health |

Do not treat every failure by increasing timeouts. Authorization, serialization, and invalid partition errors are configuration/data bugs that must be fixed; infinite retries only pin the source partition and grow backlog.

## 16. Does the DLT producer need idempotence?

Producer idempotence helps Kafka producers guard against duplicates from internal producer retries per protocol within a single producer session and under qualifying settings. It helps, yet does not eliminate all DLT duplicates.

Duplicates can still occur when:

- The source record is redelivered and the recoverer issues a new send.
- The application restarts after the broker appends but before the source offset commits.
- A send acknowledgement is lost.
- DLT replay or an operator republishes the same event.
- Two consumer instances process the same logical operation due to coordination faults.

Therefore, DLT records should carry a stable business event ID or source identity. DLT consumers and replay tools should support deduplication or require operator confirmation before replaying.

Never use the current DLT offset as an idempotency key for a logical source event, because each republish receives a new offset.

## 17. Transactional recovery

If the listener container uses Kafka transactions, recovery can be configured to send the DLT record and commit the source offset within an appropriate transaction boundary, typically via an after-rollback processor and a transactional `KafkaTemplate`.

The goal is:

~~~text
Kafka transaction
   |
   +-- Send record to DLT
   |
   +-- Send source consumer offset to transaction
   |
   +-- Commit both
~~~

If the transaction commit fails, both the DLT output and the source offset inside the transaction roll back per Kafka transaction semantics. This narrows the window where one side succeeds and the other fails.

However, transactional recovery requires:

- A producer factory with matching transaction configuration.
- Unique transactional IDs that do not collide across instances.
- Properly configured container transaction manager and error recovery.
- DLT publishing using a transaction-compatible template.
- Downstream consumers using an appropriate isolation level if they must see only committed records.
- Retry/recovery processors set up properly for your Spring Kafka version.

Never mix a transactional recoverer with a non-transactional template and assume source offsets and DLT output are atomic. Nor do Kafka transactions protect external database side effects outside Kafka.

## 18. DLT publish failures and Health

A service may process normal records fine yet fail to send to the DLT when encountering an invalid record. This is **degraded recovery capability**.

Health must answer distinct questions:

- Is the process alive?
- Is the listener container running?
- Is the consumer group polling and assigned?
- Do business dependencies have enough capacity?
- Can the DLT producer publish to the DLT topic?
- Can the error handler preserve records when recovery is needed?

A `HealthIndicator` that only checks whether the `KafkaTemplate` bean exists is not enough. The producer object can exist while brokers are unreachable or the principal lacks ACLs.

Health states can be modeled as:

| State | Meaning |
|---|---|
| `UP` | DLT path is verified healthy per policy |
| `UNKNOWN` | No sufficiently fresh evidence yet, or probe has not run |
| `DEGRADED` | Send failures occurred or DLT path is impaired |
| `DOWN` | Recovery path cannot meet requirements and the service must not accept more workload |

This is an application-level classification; Spring Boot Health APIs can use `UP`/`DOWN`/`OUT_OF_SERVICE`/`UNKNOWN` or custom statuses per configuration. Map statuses clearly to HTTP status codes.

## 19. Health checks should not arbitrarily send real DLT records

A health check running every few seconds and sending test records to a production DLT creates noise, feeds fake events to DLT consumers, or triggers alerts.

Safer observation methods:

1. Track producer send success/failure metrics.
2. Track recoverer exceptions and DLT send results.
3. Check cluster metadata and topic descriptions with appropriate permissions.
4. Validate ACLs during provisioning/deployment.
5. Use a dedicated synthetic probe topic if end-to-end send/consume testing is needed.
6. Run probes in a controlled manner with dedicated markers and clear cleanup/retention.
7. Never let the health endpoint execute long-blocking synchronous sends.

A metadata check does not prove write ACLs or serializer paths work. Conversely, an actual send to a DLT topic is stronger evidence but causes side effects. Choose probes according to the assurance level needed.

## 20. Readiness differs from liveness

If the DLT producer fails, should the pod be restarted? Normally **liveness must not fail solely because the DLT broker is temporarily unavailable**. Repeated restarts cannot fix ACLs, broker outages, or serializer config; they can trigger rebalances and worsen the system.

Readiness may fit better if the application cannot safely continue consuming new records while the recovery path is unavailable. When a pod is marked not-ready, remember that Kubernetes readiness primarily affects Service routing; it **does not automatically stop Kafka listener containers**. Stopping intake requires a dedicated pause/stop mechanism.

| Probe | Role | Typically Appropriate DLT Failure Policy |
|---|---|---|
| Liveness | Is the process deadlocked/crashed? | Do not fail solely for a temporary DLT broker outage |
| Readiness | Can the pod accept workload per contract? | Can be `DEGRADED`/`OUT_OF_SERVICE` if recovery cannot be preserved |
| Startup | Has the app finished initializing? | Used for startup dependencies/time budgets |
| Business health | Is the workflow meeting SLOs? | Track DLT failure rate, backlog, error handler |

If the source listener can still process normally and the DLT is only needed for rare errors, readiness policy may differ from a consumer where every failing record must be guaranteed DLT storage. This is a business-risk decision.

## 21. Readiness does not automatically pause consumers

A common deployment mistake is marking a pod not-ready and assuming the Kafka consumer will stop. Kafka consumers do not depend on Kubernetes Service routing; they join consumer groups and poll brokers directly.

Therefore, if policy requires halting record intake when the DLT recovery path is down:

~~~text
DLT send failures detected
       |
       v
Set application recovery state = DEGRADED
       |
       v
Backpressure controller requests listener pause
       |
       v
Wait for pause effective / drain in-flight work
       |
       v
Keep consumer group polling while paused
       |
       v
DLT path restored and verified
       |
       v
Resume under controlled policy
~~~

Pausing the container suspends record dispatch while keeping the poll loop alive per Spring Kafka mechanics. It does not abort an already-executing record and does not replace retry/error handling for the current record.

If you only mark readiness false without pausing/stopping the listener, the consumer can keep receiving and processing records.

## 22. Avoid auto-pausing on a single transient send error

A single timeout can stem from network jitter or a brief broker failover. If every failure immediately pauses all consumers, the system can flap and build huge backlogs.

A control policy can use:

- Count of DLT send failures within a window.
- Consecutive failures or failure ratio.
- Duration the dependency has been degraded.
- Circuit breaker state.
- Minimum pause duration and recovery stability window.
- Manual override for maintenance.

Example:

~~~text
Pause intake when:
  DLT send failures >= 3 consecutive
  OR failure ratio > 20% over 1 minute

Resume when:
  DLT probe succeeds
  AND producer send failures = 0 for 2 minutes
  AND operator maintenance lock is cleared
~~~

This is illustrative logic, not a Spring Kafka default. Thresholds must match volume and SLOs. At low traffic, ratios can be noisy; at high traffic, even a small failure rate can represent many records.

## 23. Observing DLT producer metrics

Track metrics for both the Kafka producer and the application recovery flow:

| Metric / Signal | Question |
|---|---|
| DLT send attempts | How many times did the recoverer attempt to publish? |
| DLT send successes | How many records did the broker acknowledge? |
| DLT send failures | How many sends failed? |
| DLT send latency | How long does broker acknowledgement take? |
| Producer `record-error-rate` | At what rate is the producer hitting send errors? |
| Request latency/throttling | Are brokers/networks responding slowly? |
| Buffer available / queue time | Is the producer under buffer pressure? |
| Recoverer exceptions | How often did recovery fail? |
| Source lag | Are source records being held back? |
| DLT topic ingress/lag | Is the DLT consumer keeping up? |
| DLT retention age | Are failed records risking retention expiration? |

Exact Kafka client metric names depend on Kafka client version and metrics binder. Inspect the actual registry instead of hardcoding metric names from another cluster.

Never put event IDs or offsets into metric labels. Use logs/traces for per-record tracing; metrics only need listener/topic/result/exception class or other low-cardinality dimensions.

## 24. Structured logs for DLT send outcomes

Log attempts and outcomes separately:

~~~text
event=dlt_publish_attempted
source_topic=orders
source_partition=3
source_offset=1842
destination_topic=orders.DLT
destination_partition=3
event_id=evt-91fe

event=dlt_publish_acknowledged
source_topic=orders
source_partition=3
source_offset=1842
destination_topic=orders.DLT
destination_partition=3
destination_offset=91
event_id=evt-91fe
~~~

On failure:

~~~text
event=dlt_publish_failed
source_topic=orders
source_partition=3
source_offset=1842
destination_topic=orders.DLT
error_type=TopicAuthorizationException
recovery_result=not_recovered
~~~

Key fields:

- Source coordinates.
- Destination topic/partition.
- Permitted event ID or operation ID.
- Recoverer attempt/result.
- Exception type.
- Consumer group/listener/instance.
- Retry count or recovery stage if metadata is available.

Never log raw payloads or headers containing tokens. For serializer failures, log the expected type and actual type; do not dump full objects if they contain sensitive data.

## 25. DLT producer serialization and multiple KafkaTemplates

If an application handles multiple payload types, a single `KafkaTemplate` with one serializer may not fit every record. In particular, when a listener hits a deserialization exception, the recoverer may need to publish raw bytes.

Design options:

- Template dedicated to JSON DTOs.
- Template supporting `byte[]` for raw payloads.
- Template supporting the matching key serializer.
- Resolver selecting templates by runtime key/value types.
- Controlled fallback template for nulls/tombstones.

If the template resolver picks the wrong serializer, the DLT send fails before the broker ever receives the record. That is why DLTs must be tested with both cleanly deserialized records and malformed records.

Tombstone records have a null value; templates/serializers must support null values following compacted-topic semantics. Never convert null into the string `"null"` if preserving tombstones is the goal.

## 26. Header metadata and DLT record size

The recoverer can add headers describing original topic, partition, offset, consumer group, and exceptions. These headers aid forensics and replay, yet also enlarge records.

Potential errors:

- Exception messages/stack traces that are too long.
- Repeated headers accumulating after multiple retry/DLT forwards.
- Total record size exceeding broker/topic/producer limits.
- Serializers not supporting the expected header value encoding.
- Headers containing internal details or sensitive data.

Inspect header functions/retention settings for your version. If truncating stack traces, retain the exception class, original coordinates, and a reference to accessible logs/traces. Never strip original coordinates if they are needed for auditing.

## 27. DLT publishing and source offsets in non-transactional flows

In a non-transactional flow, DLT publishing and source offset commits are two independent operations. There are two failure windows:

~~~text
A. DLT send fails
   -> recoverer throws
   -> source record must be retried/recovered again per policy

B. DLT send succeeds
   -> process crashes before source offset commit
   -> source record is redelivered
   -> DLT may receive a second copy
~~~

Consequently, a non-transactional DLT flow requires:

- Send failures must propagate.
- DLT consumers must support idempotency/deduplication.
- Original source coordinates and event IDs are preserved.
- Source offset commit semantics are tested.
- Operators can distinguish retry sends from duplicate DLT records.

Transactional recovery can shrink the failure window between DLT output and input offset, but requires properly configuring transaction manager, template, and processor, and does not extend guarantees to databases.

## 28. Retrying when the DLT producer itself fails

An operational question: if the listener exhausted retries yet the DLT send fails, what retries?

There are two retry layers:

1. **Business listener retry:** retrying the record due to a business processing failure.
2. **Recovery/DLT publish retry:** retrying the operation of publishing the failed record to the DLT.

Not every error handler configuration automatically retries recovery infinitely. Behavior after the recoverer throws depends on the handler, retry state, backoff, and version. Define an explicit policy:

- Retry DLT publishing with finite backoff.
- Keep the source record eligible for redelivery on recovery failure.
- Pause intake during prolonged DLT path outages.
- Alert operators if recovery fails after the budget is spent.
- Never discard records or commit source offsets merely because the retry budget ran out.

If sharing retry state between listener and recovery, check `resetStateOnRecoveryFailure` and the exact behavior of your running version. Never design policy on assumptions alone.

## 29. DLT publish failures should not cause an infinite retry storm

If a DLT topic lacks an ACL, every failing record fails to publish. Retrying DLT sends infinitely on the same partition can tie up the consumer thread and cause unbounded backlog growth.

A recovery budget is needed:

- Bounded backoff or exponential backoff.
- Distinguishing transient failures from permanent configuration errors.
- A circuit breaker for the DLT producer path.
- Pausing intake when record preservation can no longer be guaranteed.
- Alerting DLT/topic ACL owners immediately.
- Keeping records on the source until recovery can continue.
- Never diverting records to an untested fallback DLT.

A fallback topic can reduce reliance on the primary DLT, but only helps if the fallback cluster/topic/ACLs/serializers/retention are provisioned and tested in advance. If the fallback shares the same broker/ACL failure domain, it adds no reliability.

## 30. Checking the DLT path before deployment

A pre-deployment checklist should verify:

1. DLT topics are created.
2. Partition counts match source/resolver expectations.
3. Replication factor and min ISR meet requirements.
4. The producer principal has `WRITE`/appropriate ACLs.
5. Consumer/operator principals have `READ`/`DESCRIBE` if needed.
6. Serializers support payload types and raw bytes.
7. Message size limits accommodate DLT headers and payloads.
8. TLS/SASL credentials and trust chains are valid.
9. Producer delivery timeouts and recoverer wait timeouts are sensibly aligned.
10. Metrics/logs are exported and alerts have owners.
11. DLT retention is long enough for incident response.
12. Replay procedures are controlled and idempotent.

Provisioning alone only verifies config; an integration test sending a representative record verifies the end-to-end write path in a test environment.

## 31. Testing DLT producer failures

An integration test suite should verify:

| Scenario | Expected Outcome |
|---|---|
| DLT send succeeds | Recoverer completes and source progresses per policy |
| DLT broker unavailable | Recoverer reports error; record is not marked recovered |
| Missing `WRITE` ACL | Failure is surfaced with alerts/logs |
| DLT topic does not exist | Explicit recovery failure |
| DLT partition does not exist | No silent drop |
| Serializer unsupported for DTO | Recovery failure |
| Raw `byte[]` after deserialization failure | DLT preserves original payload |
| Broker ack timeout | System handles uncertain send outcome |
| DLT send succeeds but source offset commit fails | Duplicate DLT is deduplicated/investigated |
| DLT publish transaction rollback | DLT record and offset obey transaction semantics |
| DLT consumer replay | Business idempotency is preserved |

The most important test: cause the DLT send to fail in a controlled way, then verify the error handler **does not mark recovery successful**. Do not assert only that an error was logged; inspect source offset/redelivery behavior and DLT record counts.

This is a testing design for learners, not test results from an application in this article.

## 32. Runbook: DLT producer cannot send

When receiving a `dlt_publish_failed` alert:

1. Identify source topic, partition, offset, event ID, and consumer group.
2. Identify the destination DLT topic/partition chosen by the resolver.
3. Read the exception root cause: authorization, metadata, serialization, timeout, broker, message size, or transaction.
4. Check Kafka cluster/broker availability and the destination partition's leader.
5. Check topic existence, partition count, and replication/ISR.
6. Check producer principal, `WRITE` ACLs, and TLS/SASL credentials.
7. Check serializers for runtime payload types and raw bytes/tombstones.
8. Check producer delivery timeout, buffer pressure, and recoverer wait timeout.
9. Confirm `failIfSendResultIsError` is enabled per policy.
10. Check whether the source record remains eligible for retry/redelivery.
11. Fix the DLT path and run a controlled test publish.
12. Let recovery resume per error-handler policy; never reset offsets indiscriminately.
13. Monitor DLT success, source lag, retry counts, and duplicate records.
14. Document the incident with original source coordinates.

If the error is an ACL issue, raising retries/backoff will not fix the root cause. If the broker is unavailable, restarting consumer pods one by one will not restore the broker.

## 33. Runbook: readiness turns DEGRADED due to the DLT path

1. Identify which health component reported degraded and which evidence triggered it.
2. Check whether this is an actual send failure or a failed probe/metadata check.
3. Determine whether the service can still process records that do not require recovery.
4. Check how many records are awaiting recovery and which source partitions are affected.
5. If policy requires preserving every failed record, request intake pause via the control plane.
6. Wait for pause to take effect and inspect in-flight listener operations.
7. Fix DLT topic, ACLs, serializers, or broker connectivity.
8. Confirm DLT send succeeds on a safe test path.
9. Clear the degraded reason per control policy.
10. Resume intake in a controlled way.
11. Monitor source lag and DLT throughput until caught up.
12. Keep liveness stable; never enter a restart loop solely for a temporary DLT dependency loss.

Readiness false does not automatically stop Kafka consumers. To stop receiving records, control the listener container explicitly.

## 34. Runbook: source offset advanced yet no DLT record exists

Treat this situation as a data incident:

1. Confirm source topic/partition/offset and consumer group.
2. Inspect committed offsets and commit timestamps.
3. Search recoverer logs around processing time.
4. Check `failIfSendResultIsError` and send-result wait configuration.
5. Inspect DLT topic, partitions, retention, and compaction.
6. Check whether the destination resolver routed to a different topic.
7. Check broker transaction commits/rollbacks if transactional recovery is used.
8. Search for the DLT record by event ID and original coordinates across all DLT partitions.
9. Check for duplicates/replays or manual forwarding.
10. If the record is truly lost, determine whether it can be recovered from source retention, archives, or producer outboxes.
11. Replay via an idempotent, audited workflow.
12. Fix configuration/tests so recovery failures are never treated as success.

Never delete idempotency markers or mass-reset group offsets before verifying whether business side effects already ran.

## 35. Common mistakes

### Logging send failure while still returning success

If the recoverer does not propagate send errors, the error handler may treat the record as recovered and advance the source offset. Logging an error is not enough to protect the record.

### Assuming KafkaTemplate.send() returning means the broker persisted it

Send is asynchronous; observe future outcomes or use recoverer settings that wait and fail properly.

### DLT topic having fewer partitions than source

The default resolver preserves source partitions and can send to a non-existent partition. Provision partition counts and resolvers together.

### Configuring only a JSON serializer

Deserialization failures can leave raw bytes. DLT producers must support actual runtime payload types.

### Retrying DLT publishing infinitely

Can hold the consumer thread, raise lag, and cause storms. Use retry budgets, alerts, and backpressure.

### Marking liveness DOWN when the DLT broker is temporarily unavailable

Kubernetes can enter a restart loop without fixing the dependency failure. Liveness and readiness serve different goals.

### Assuming readiness false stops Kafka listeners

Consumer groups operate independently of Service routing. Stopping intake requires pause/stop controls.

### Failing to handle ambiguous send outcomes

Brokers can append a record while the ack is lost; retries can create duplicates. Preserve event IDs/original coordinates and deduplicate.

### Assuming Kafka transactions protect databases

Kafka transactions only make Kafka records/offsets within the transaction atomic. DB side effects require separate transactions/idempotency.

## 36. DLT producer reliability implementation checklist

- [ ] Use `DeadLetterPublishingRecoverer` with a `KafkaTemplate` configured with the right serializers.
- [ ] Configure destination topic/partition mapping explicitly.
- [ ] DLT partitions are compatible with source partition mapping.
- [ ] `failIfSendResultIsError` is enabled per record-preservation policy.
- [ ] Send-result timeout aligns with producer delivery timeout and broker SLA.
- [ ] Recoverer send exceptions propagate back to the error handler.
- [ ] Recovery failures are never turned into false successes.
- [ ] Source offset behavior is tested for actual `AckMode` and transactions.
- [ ] DTOs, raw `byte[]`, keys, and tombstones are supported as needed.
- [ ] DLT topics/ACLs/replication/retention are provisioned before deployment.
- [ ] Separate metrics/logs track DLT attempts, successes, failures, and latency.
- [ ] Readiness reflects recovery capability per business policy.
- [ ] Liveness does not fail solely for a temporary DLT broker outage.
- [ ] If intake is paused, clear control-plane and resume policies exist.
- [ ] DLT consumers implement idempotency for duplicates/replays.
- [ ] Integration tests cover DLT send failures, ack timeouts, and transaction rollbacks.
- [ ] Runbooks cover ACL, broker, topic, partition, serializer, and source-offset anomalies.

## 37. References

- [Spring Kafka Reference — Dead Letter Publishing Recoverer](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring Kafka API — DeadLetterPublishingRecoverer](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/listener/DeadLetterPublishingRecoverer.html)
- [Spring Kafka Reference — Listener Container Properties](https://docs.spring.io/spring-kafka/reference/kafka/container-props.html)
- [Spring Kafka Reference — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Spring Boot Reference — Actuator Health](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Apache Kafka — Producer Configuration](https://kafka.apache.org/documentation/#producerconfigs)

**Conclusion:** A DLT producer failing to send is a failure of the recovery path and must be treated as a data-preservation issue. Configure `DeadLetterPublishingRecoverer` so send failures propagate as recovery failures, verify publish outcomes before treating source records as recovered, and control topics/partitions/serializers/ACLs/timeouts. Surface DLT path state in readiness when business policy requires it, without using liveness to restart-loop on broker outages; remember also that readiness false does not automatically stop Kafka consumers. Finally, preserve source coordinates and event IDs, test failure windows, and maintain runbooks to recover without losing records or creating uncontrolled duplicates.
