# commitRecovered After Recovery

In Spring Kafka, `commitRecovered` is an option that lets the listener container **commit the offset of a record that has been successfully recovered by the error handler**. This mechanism is typically used with `DefaultErrorHandler` and a recoverer such as `DeadLetterPublishingRecoverer` to route unprocessable records to a Dead Letter Topic (DLT) and then advance the consumer group's committed offset past that record.

A key point is that the commit happens only after the recovery callback finishes successfully. If publishing the record to the DLT fails and the recoverer reports an error, the offset is not advanced as though the record had finished processing. That allows the record to be retried once the cause of recovery failure is resolved.

`commitRecovered` solves one step in the error-handling lifecycle: after the application decides a record has been recovered by an alternative action, Kafka needs to record progress so the consumer does not remain stuck on that record. It does not publish to the DLT itself, does not fix corrupted data, and does not replace the retry policy. Those actions belong to the recoverer and error handler configured together.

## 1. Why Commit After Recovery?

For a consumer group, Kafka delivers records based on the committed offset of each topic-partition. When a listener fails to process a record, Spring Kafka can retry according to backoff. If all retries fail, the application must decide how the record is handled:

- Route the record to a DLT for investigation and later replay.
- Write the record to a recoverable error store.
- Skip the record after explicitly recording the business decision.
- Perform an application-defined alternative action.

Once the recovery action succeeds, the consumer group needs to move forward to process subsequent records. Without committing the recovered record's offset, the next poll or restart can put that record back into the processing flow. The application could repeatedly send the same record to the DLT or repeat the recovery action.

Suppose partition `orders-0` has consecutive offsets:

| Offset | Processing Outcome |
|---:|---|
| 40 | Processed successfully |
| 41 | Listener failed, retries exhausted, routed to DLT successfully |
| 42 | Pending next processing |

If record 41 was recovered successfully yet the committed offset remains at 41, the consumer may receive record 41 again after a restart or rebalance. When `commitRecovered` works properly, the container commits the next position, 42. The consumer group can continue with record 42.

```text
Poll record 41
      |
      v
Listener throws exception
      |
      v
Retry per BackOff
      |
      +---- retries remaining ----> invoke listener again
      |
      v retries exhausted
Recoverer handles record 41
      |
      +---- recovery fails ----> do not commit recovered offset
      |
      v recovery succeeds
commitRecovered
      |
      v
Committed offset advances to 42
      |
      v
Consumer continues with record 42
```

In this example, the committed offset is the next position to read. Committing offset 42 means the group has completed handling record 41 under the application's policy, even when handled by moving it to a DLT rather than completing the normal business listener.

## 2. `commitRecovered` in DefaultErrorHandler

For listener containers that do not use a Kafka transaction per processing cycle, `DefaultErrorHandler` is the standard mechanism for exception handling, retries, and recovery. A `ConsumerRecordRecoverer` can be passed to the handler. Once retries are exhausted, the handler invokes the recoverer for the failed record.

`DefaultErrorHandler.setCommitRecovered(true)` instructs the container to commit the record's offset after the recoverer completes successfully. With `DefaultErrorHandler`, the container must use acknowledgment mode `MANUAL_IMMEDIATE` to support this feature.

This prerequisite must be configured explicitly. `MANUAL` and `MANUAL_IMMEDIATE` are not identical: `MANUAL` has the container coordinate commits per batch rules, whereas `MANUAL_IMMEDIATE` allows immediate commits when acknowledge is called on the consumer thread. `commitRecovered` requires `MANUAL_IMMEDIATE` so the recovered record's offset is committed at the right moment.

### 2.1. Configuring the Listener Container

Java configuration example for a record listener:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
orderKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        DefaultErrorHandler orderErrorHandler) {

    ConcurrentKafkaListenerContainerFactory<String, OrderCreated> factory =
            new ConcurrentKafkaListenerContainerFactory<>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.MANUAL_IMMEDIATE);
    factory.setCommonErrorHandler(orderErrorHandler);

    return factory;
}
```

With this factory, the listener must accept `Acknowledgment` and acknowledge after business processing succeeds. When the listener throws an exception, acknowledge is not called; the error handler performs retries and recovery per configuration. When the recoverer completes, `commitRecovered` handles the failed record's offset.

If using Spring Boot auto-configuration, you can set the acknowledgment mode in the corresponding listener configuration, though you must confirm which factory the listener actually uses. If the application has multiple `ConcurrentKafkaListenerContainerFactory` beans, setting `MANUAL_IMMEDIATE` on one factory does not automatically apply to the others.

### 2.2. Configuring DefaultErrorHandler and the DLT Recoverer

The example below routes failed records to a DLT named `<topic>.DLT` while preserving the source partition:

```java
@Bean
DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(
                    kafkaTemplate,
                    (record, exception) -> new TopicPartition(
                            record.topic() + ".DLT",
                            record.partition()));

    // Fail if DLT publishing fails.
    recoverer.setFailIfSendResultIsError(true);

    // 2 retries after the initial delivery.
    FixedBackOff backOff = new FixedBackOff(1_000L, 2L);

    DefaultErrorHandler handler =
            new DefaultErrorHandler(recoverer, backOff);

    handler.setCommitRecovered(true);
    return handler;
}
```

In this example, the record is delivered once, followed by up to two retries spaced one second apart. If it still fails, `DeadLetterPublishingRecoverer` sends the record to the DLT. `setFailIfSendResultIsError(true)` turns DLT publish failures into recovery failures; otherwise, the application might fail to notice a failed send before recovery proceeds. Verify this API against your running Spring Kafka version and configure an appropriate send timeout.

`handler.setCommitRecovered(true)` enables offset commits after recovery. This configuration must pair with a factory using `AckMode.MANUAL_IMMEDIATE`. Without that acknowledgment mode prerequisite, the application cannot rely on `commitRecovered` to commit offsets as intended.

### 2.3. Listener Acknowledging on Successful Processing

Example listener using manual acknowledgment:

```java
@KafkaListener(
        topics = "orders",
        groupId = "billing-service",
        containerFactory = "orderKafkaListenerContainerFactory")
public void consume(
        OrderCreated event,
        Acknowledgment acknowledgment) {

    billingService.applyIdempotently(event);
    acknowledgment.acknowledge();
}
```

Once `applyIdempotently()` completes, the listener acknowledges so the container commits the successful record. If the business method throws an exception, the acknowledge line does not run. The error handler catches the error, performs retries, and finally invokes the recoverer if needed. Once the recoverer succeeds, `commitRecovered` commits the recovered record's offset.

Do not call `acknowledgment.acknowledge()` inside `finally` or before side effects complete. Doing so can commit the offset of a record whose business processing did not succeed, preventing Kafka from redelivering the record after an incident.

## 3. Commit Sequence After Recovery

To understand commit timing precisely, separate three outcomes:

1. **Listener succeeds:** business processing finishes and the listener acknowledges. The container commits the offset per the acknowledgment mode.
2. **Listener fails with retries remaining:** the error handler waits for backoff and redelivers the record per the retry policy. The offset is not yet treated as successfully processed.
3. **Retries exhausted and recovery succeeds:** the recoverer finishes the alternative action; `commitRecovered` instructs the container to commit that record's offset.

If the recoverer throws an exception, the handler must not treat the record as recovered. With `DeadLetterPublishingRecoverer`, configure it so publish errors surface back to the caller, monitor timeouts, and ensure serializers/destination topics are ready. When recovery fails, the record must be retried or handled per error-handler policy; the offset must not be committed as a successfully recovered record.

Example with offset `41`:

| Step | Action | Committed Offset |
|---|---|---:|
| Before processing | Group starts at offset 41 | 41 |
| Listener fails | Exception passed to error handler | 41 |
| Retries | Retry attempts fail | 41 |
| Publish DLT | Recoverer publishes record 41 successfully | Not yet committed while recoverer runs |
| Commit recovered | Container commits next position | 42 |
| Next poll | Consumer reads next record | 42 |

Committing the offset after recovery does not mean the failed record was fixed or succeeded in the original business service. It means the application finished the designed recovery action and can continue the main stream.

## 4. What Happens When DLT Publishing Fails?

A critical failure to handle is when the DLT cannot accept the record. Causes can include unavailable brokers, missing topics, missing ACL permissions, exhausted quotas, unsupported serializer types, or network timeouts.

If the recoverer does not report publish errors, the error handler may continue as though recovery finished and risk committing the offset. Therefore, with `DeadLetterPublishingRecoverer`, enable failure reporting on send-result errors via `setFailIfSendResultIsError(true)` in supported versions, set timeouts, and monitor send outcomes.

When DLT publishing fails and the recoverer throws an exception:

- Do not treat the record as successfully recovered.
- Do not commit the recovered offset for that record.
- Log the DLT publish error separately to distinguish it from the original listener exception.
- Check DLT brokers, write permissions, topic, partitions, and serializers.
- Let the error handler retry recovery according to an appropriate retry policy.

Do not let a DLT outage turn into a retry storm. Bound backoff, alert when recovery continuously fails, and define how to pause or throttle consumers if the DLT cannot serve writes. When the DLT recovers, monitor recovered record counts and consumer group lag.

## 5. DLT Topics and Record Metadata

A DLT should retain enough information for investigation and replay. By default, `DeadLetterPublishingRecoverer` attaches headers describing the source and exception, such as topic, partition, offset, timestamp, and error details. Exact header names depend on the Spring Kafka version.

In the example using resolver `record.topic() + ".DLT"` while preserving the source partition, the DLT must have enough partitions to accept every partition of the source topic. If the source topic has partitions 0 through 11, the DLT needs at least 12 partitions when the resolver routes records to the same partition index. If the DLT has fewer partitions, use a different resolver to map to valid target partitions.

The DLT must be operated as a critical topic:

- Have appropriate replication factor, `min.insync.replicas`, and placement.
- Have retention long enough for investigation and remediation.
- Have ACLs granting read/write access only to required services and operations teams.
- Have dashboards tracking DLT ingress rate and backlog count.
- Have a controlled replay procedure preserving event IDs and preventing duplicates.
- Have alerts when DLT publishing fails or recovery rates spike abnormally.

The serializer of the `KafkaTemplate` used for DLT publishing must handle actual key/value types. When errors occur during deserialization, values may be `byte[]` instead of domain objects. If the application uses multiple value types, configure suitable serializers—such as type-routing serializers or a dedicated DLT template.

## 6. Successful Recovery Does Not Equal Successful Business Processing

Suppose a listener processes a payment event whose payload lacks a required field. After permitted retries, the recoverer routes the record to the DLT. Once the DLT accepts the record and the offset commits, the group can keep processing subsequent payments.

That does not mean the payment was executed. The operations team must monitor the DLT, identify data or code defects, fix the root cause, and decide whether to replay the record. If the record is fixed and replayed, the consumer needs idempotency to avoid applying side effects twice if the earlier attempt partially succeeded.

Therefore, distinguish these states:

| State | Meaning |
|---|---|
| Processed | Listener completed business processing per application contract |
| Retried | Listener re-invoked due to transient errors or errors undergoing retry |
| Recovered | Recoverer finished the alternative action, such as publishing to DLT |
| Committed | Consumer group persisted read progress past the corresponding record |
| Replayed | Record re-entered the processing flow after root cause remediation |

A record can be in recovered and committed state while still needing business investigation. Dashboards must not fold recovered record counts into successfully business-processed counts.

## 7. Gap Between DLT Publish and Offset Commit

In configurations without Kafka transactions, publishing a record to the DLT and committing the source offset are normally two separate operations. The following can occur:

1. The DLT receives the record successfully.
2. The application or broker stops before the source offset is committed.
3. The consumer restarts and re-reads the source record.
4. The recoverer publishes the same record to the DLT a second time.

This is duplicate exposure in the DLT. `commitRecovered` reduces re-reads once the commit finishes, but does not merge publish and commit into an atomic transaction in non-transactional mode.

To handle duplicates:

- Preserve event IDs and source metadata in the DLT.
- Use a deduplication key such as `originalTopic + originalPartition + originalOffset` when identifying the same source record.
- Make the replay procedure idempotent.
- Monitor duplicate records in the DLT and maintain a reconciliation procedure.

If atomicity between DLT publishing and offset commits is required, consider transactional recovery with a transactional container and `DefaultAfterRollbackProcessor`. In that model, DLT publishing and the recovered offset can execute inside a new Kafka transaction if the producer factory, transaction manager, and processor are configured properly.

## 8. `commitRecovered` with Transactional Containers

When the listener container uses Kafka transactions, an exception in the listener normally causes the active transaction to roll back. Post-rollback handling uses `DefaultAfterRollbackProcessor`, rather than relying solely on `DefaultErrorHandler` for non-transactional commit paths.

`DefaultAfterRollbackProcessor` provides a `commitRecovered` option. When enabled alongside a transactional `KafkaTemplate`, the processor can perform recovery and commit the recovered record's offset inside a new transaction. This records both the DLT record and consumer group progress atomically within the Kafka transaction scope.

Illustrative processor configuration:

```java
@Bean
DefaultAfterRollbackProcessor<String, OrderCreated>
orderAfterRollbackProcessor(
        KafkaTemplate<String, OrderCreated> transactionalTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(
                    transactionalTemplate,
                    (record, exception) -> new TopicPartition(
                            record.topic() + ".DLT",
                            record.partition()));

    recoverer.setFailIfSendResultIsError(true);

    DefaultAfterRollbackProcessor<String, OrderCreated> processor =
            new DefaultAfterRollbackProcessor<>(
                    recoverer,
                    new FixedBackOff(1_000L, 2L));

    processor.setCommitRecovered(true);
    processor.setKafkaTemplate(transactionalTemplate);
    return processor;
}
```

Attach the processor to the transactional listener container factory:

```java
factory.setAfterRollbackProcessor(orderAfterRollbackProcessor);
```

This is an illustrative configuration for Spring Kafka versions supporting these APIs. `transactionalTemplate` must use a `ProducerFactory` with a transaction ID prefix and a transaction manager matching the container. Do not use a non-transactional template and expect DLT publishing and offset commits to become an atomic transaction automatically.

With transactional recovery, check transaction timeouts, DLT permissions, serializers, and behavior when the recovery transaction aborts. If the new transaction fails, neither the DLT publish nor the offset commit inside that transaction is treated as complete; the record must be rehandled per recovery policy.

## 9. Common Configuration Mistakes

| Symptom | Common Cause | Resolution |
|---|---|---|
| `commitRecovered` does not commit offsets | Container does not use `MANUAL_IMMEDIATE` in `DefaultErrorHandler` setup | Check `ContainerProperties.AckMode` on the exact listener factory |
| Record still redelivered after DLT publish | DLT publish succeeded yet offset did not commit; commit failed or process stopped in between | Check commit result, enable `commitRecovered`, evaluate DLT duplicates and transactional recovery |
| Record skipped despite DLT publish failure | Recoverer did not report send-result errors; error handler assumed recovery finished | Configure `setFailIfSendResultIsError(true)` on supported versions and monitor publish failures |
| Listener succeeds yet offset does not advance | `MANUAL_IMMEDIATE` enabled without listener calling acknowledge | Call `acknowledge()` after successful processing or pick a suitable acknowledgment mode |
| Record routed to wrong DLT partition | DLT lacks matching partition or resolver maps incorrectly | Create DLT with sufficient partitions or configure an appropriate destination resolver |
| DLT has records yet source cannot be traced | Missing event ID or source metadata in headers/logs | Preserve source metadata and establish correlation/deduplication keys |
| Recovery errors repeat endlessly | Broken DLT broker/ACL/serializer or improper backoff | Fix root cause, cap retries, alert, and throttle consumer if needed |
| DLT spikes sharply after a release | New version introduces schema, mapping, or dependency bugs | Halt rollout/rollback, classify exceptions, and identify records needing replay |

A common mistake is enabling `commitRecovered` while forgetting `MANUAL_IMMEDIATE`. Another is configuring manual immediate while the listener fails to acknowledge successfully processed records. Both conditions must be verified together in real configuration.

## 10. Observing Recovery and Committed Offsets

To confirm `commitRecovered` works properly, monitor metrics across the listener, recoverer, and consumer group:

- Listener failure counts and retry counts by exception type.
- Successful recovery counts and failed recovery counts.
- DLT publish success, failure, and timeout rates.
- Consumer lag and committed offsets per partition.
- Number of times source records are redelivered after recovery.
- Number of DLT records awaiting investigation or replay.
- Duration from initial processing attempt until recovery and commit complete.

Recovery logs should include source topic, partition, offset, event ID, DLT topic, exception class, and commit result where observable. Never log sensitive payloads. Avoid using individual event IDs or offsets as high-cardinality metric labels; keep them in logs or traces.

A validation workflow after enabling configuration:

1. Send a valid record and verify the listener processes, acknowledges, and committed offset advances.
2. Send a record triggering a retryable listener error; verify listener invocation count matches `BackOff`.
3. Let retries exhaust; verify the recoverer sends the record to the right DLT and preserves source metadata.
4. Verify the committed offset advances past the recovered record.
5. Restart the consumer or trigger a controlled rebalance; verify the recovered record is not reprocessed from the source topic.
6. Simulate DLT publish failure; verify recovery reports an error and the offset is not committed as recovered.
7. With transactional recovery, simulate transaction abort to verify DLT publish and offset commit roll back together.

## 11. Operational Runbook When Recovery Fails to Advance

When records keep returning despite being routed to the DLT, investigate in sequence:

1. Identify the source record's group ID, topic, partition, and offset.
2. Check `DefaultErrorHandler` or `DefaultAfterRollbackProcessor` logs to see whether the recoverer was invoked.
3. Check whether the DLT received the record, send-future outcomes, and publish errors.
4. Verify the exact listener container factory has `MANUAL_IMMEDIATE` if using `DefaultErrorHandler.setCommitRecovered(true)`.
5. Check transaction configuration if using `DefaultAfterRollbackProcessor`.
6. Compare committed offsets before and after recovery against the log end offset.
7. Check process restarts, rebalances, and commit exceptions at recovery time.
8. After fixing, resend a test record and confirm unexpected duplicates no longer occur.

Do not manually reset offsets just to hide commit failures. Resetting forward can skip records; resetting backward can cause replays and duplicate side effects. If a reset is unavoidable, record old offset, new offset, and the reconciliation plan.

## 12. Production Deployment Principles

When deploying `commitRecovered`, operations teams should confirm the following:

1. Clearly determine whether the listener uses non-transactional `DefaultErrorHandler` or `DefaultAfterRollbackProcessor` in a transactional container.
2. For `DefaultErrorHandler`, configure `AckMode.MANUAL_IMMEDIATE` on the exact listener container factory.
3. With manual acknowledgment, the listener acknowledges only after business side effects complete.
4. Enable `setCommitRecovered(true)` on the right error handler/processor.
5. Configure the recoverer for reliable send outcomes; for DLT publishing, send errors must propagate back to recovery.
6. Ensure the DLT has enough partitions, replication, retention, ACLs, and suitable serializers.
7. Clearly separate counts of business-processed records from recovered records.
8. Maintain idempotency/deduplication for potential duplicates from crashes between DLT publishing and offset commits in non-transactional flows.
9. If atomicity is required, use transactional recovery with the matching transaction manager and `KafkaTemplate`.
10. Test successful recovery, DLT publish failures, commit failures, restarts, rebalances, and transaction aborts.

`commitRecovered` helps a consumer group advance past a record after a recovery action completes. Combined with the right acknowledgment mode, recoverer, DLT, and observability, applications can isolate failing records while keeping the main stream moving. The reliability of this mechanism depends on accurately confirming successful recovery and controlling the gap between publishing the failed record and committing the offset.
