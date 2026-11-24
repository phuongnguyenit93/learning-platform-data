# Reset State When Recovery Fails

## 1. Recovery failure in Spring Kafka

In Spring Kafka, `DefaultErrorHandler` handles exceptions thrown when a listener receives and processes a record. An error-handling flow typically has two phases:

1. **Retry delivery**: the listener is invoked again according to the `BackOff` policy when record processing fails.
2. **Recovery**: after retry attempts are exhausted, the error handler invokes a recoverer to handle the uncompleted record—for example, logging, storing it in an error system, or publishing it to a dead-letter topic (DLT).

Recovery itself can also fail. For instance, the listener fails to process an event after multiple attempts and `DeadLetterPublishingRecoverer` attempts to publish the record to the DLT, yet the target broker is unavailable or the producer fails to receive a send acknowledgment. When the recoverer throws an exception, the record has not been recovered under the configured policy.

`resetStateOnRecoveryFailure` controls how `DefaultErrorHandler` handles `BackOff` state after a recoverer fails:

- Default is `true`: resets `BackOff` state. When the record is redelivered, it starts a fresh retry cycle from the beginning before the recoverer is invoked again.
- Set to `false`: does not reset `BackOff` state. The next redelivery skips the exhausted retry cycle and immediately retries recovery, following the exhausted `BackOff` behavior.

This setting determines the retry cadence after a recovery failure. It does not reset committed offsets, does not rewind the consumer group to the beginning of the topic, and does not delete business data.

## 2. Distinguishing listener failure and recovery failure

The two failures happen in different phases and must be diagnosed separately.

### 2.1. Listener failure

Listener failure occurs when the listener method throws an exception while processing a record.

~~~java
@KafkaListener(topics = "orders", groupId = "billing-service")
public void onOrder(OrderCreated event) {
    billingService.process(event); // Can throw an exception
}
~~~

If `billingService.process()` throws an exception, `DefaultErrorHandler` catches the error and applies `BackOff`. While retry attempts remain, the record is redelivered according to the error handler's mechanism.

### 2.2. Recovery failure

Recovery failure occurs after the error handler has decided to recover the record, yet the recoverer itself cannot complete its recovery work.

Example of a DLT publishing recoverer:

~~~java
DeadLetterPublishingRecoverer recoverer =
    new DeadLetterPublishingRecoverer(kafkaTemplate);
~~~

If the DLT publish operation fails and the recoverer throws an exception, the error handler cannot treat the record as successfully moved to the DLT. The record must return to the redelivery flow for another chance at recovery.

### 2.3. Overall flow

~~~mermaid
flowchart TD
    A[Consumer receives record] --> B[Listener processes]
    B -->|Success| C[Container commits per AckMode]
    B -->|Exception| D[DefaultErrorHandler applies BackOff]
    D --> E{Retries remaining?}
    E -->|Yes| F[Redeliver to listener]
    F --> B
    E -->|No| G[Invoke recoverer]
    G --> H{Recovery succeeds?}
    H -->|Yes| I[Mark recovered and advance offset per policy]
    H -->|No| J[Recovery failure]
    J --> K{resetStateOnRecoveryFailure}
    K -->|true| L[Reset BackOff state]
    K -->|false| M[Keep exhausted BackOff state]
    L --> N[Redelivery: retry cycle restarts]
    M --> O[Redelivery: retry recovery without starting a new retry cycle]
    N --> B
    O --> G
~~~

The diagram illustrates the meaning of both reset branches. Actual commit timing still depends on the acknowledgment mode, error handler, recoverer, and consumer group state.

## 3. Why reset BackOff when recovery fails?

Suppose the configuration allows two retries after the initial invocation, with a one-second wait interval:

~~~java
BackOff backOff = new FixedBackOff(1_000L, 2L);
DefaultErrorHandler handler =
    new DefaultErrorHandler(recoverer, backOff);
~~~

A record can go through the following sequence:

1. Listener receives the record and fails.
2. Error handler waits one second, then retries.
3. Listener fails again.
4. Error handler waits another second for the final retry.
5. Listener still fails.
6. Error handler invokes the recoverer.
7. The recoverer also fails—for example, DLT publishing fails.

At this point, two sensible policies exist.

**Reset state (`true`)**: when the record is redelivered, `BackOff` starts from the beginning. The listener gets another chance to be retried under the initial cycle. If the downstream dependency has recovered, the listener can succeed and recovery is no longer needed. If the listener still fails, the recoverer is invoked again once retries are exhausted.

**Keep state (`false`)**: `BackOff` stays in its exhausted state. When the record is redelivered, the error handler does not run a new listener retry cycle and instead tries invoking the recoverer again. This is useful when the main failure lies in the recovery system and re-running the listener adds no value or risks extra side effects.

## 4. Default values and version differences

Since Spring Kafka 2.5.5, when a recoverer fails, `BackOff` is reset by default. You can set `resetStateOnRecoveryFailure=false` to revert to prior behavior, where `BackOff` is not reset and recovery is retried on the next delivery without running a new retry cycle.

| Version / configuration | Behavior when recoverer throws an exception |
|---|---|
| Before Spring Kafka 2.5.5 | `BackOff` did not reset under the older default behavior |
| Spring Kafka 2.5.5 and later, default | `BackOff` resets; redelivery goes through the retry sequence from the start |
| Spring Kafka 2.5.5 and later, `resetStateOnRecoveryFailure=false` | Keeps exhausted `BackOff`; next delivery retries recovery without a new retry cycle |

Do not confuse this setting with `resetStateOnExceptionChange`. The two properties handle different events:

- `resetStateOnRecoveryFailure` handles the case where the recoverer throws an exception.
- `resetStateOnExceptionChange` controls restarting the retry sequence when the listener's exception type changes across deliveries.

Since Spring Kafka 2.9, `resetStateOnExceptionChange` defaults to `true`. When upgrading, review both properties rather than assuming they have the same effect.

## 5. Configuring state reset in DefaultErrorHandler

### 5.1. Keeping default behavior

If no setter is called, `DefaultErrorHandler` resets `BackOff` when recovery fails in Spring Kafka versions supporting this default behavior (from 2.5.5 onward).

~~~java
@Bean
public DefaultErrorHandler orderErrorHandler(
    KafkaTemplate<Object, Object> kafkaTemplate
) {
    DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(kafkaTemplate);

    FixedBackOff backOff = new FixedBackOff(1_000L, 2L);

    return new DefaultErrorHandler(recoverer, backOff);
}
~~~

In this case, if the recoverer throws an exception, the record re-enters the processing flow and `BackOff` is reset. The next delivery can go through listener invocations and wait intervals just like the initial cycle.

This is typically appropriate when the downstream system can recover over time and the listener has a chance of succeeding on the next attempt.

### 5.2. Disabling state reset when recovery fails

If you want to skip listener retries after the recoverer fails, set the property to `false`:

~~~java
@Bean
public DefaultErrorHandler orderErrorHandler(
    KafkaTemplate<Object, Object> kafkaTemplate
) {
    DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(kafkaTemplate);

    FixedBackOff backOff = new FixedBackOff(1_000L, 2L);

    DefaultErrorHandler handler =
        new DefaultErrorHandler(recoverer, backOff);

    handler.setResetStateOnRecoveryFailure(false);

    return handler;
}
~~~

After recovery fails, the next redelivery does not start a new listener retry cycle. The handler remains in the exhausted `BackOff` state and retries recovery.

Use this option only when re-running the listener is unnecessary or unsafe. For instance, the listener already failed due to an invalid payload and the recovery service is temporarily unavailable; calling the listener repeatedly will not help, whereas retrying the DLT publish is the primary goal.

### 5.3. Attaching the handler to the right listener container factory

Declaring a bean is insufficient if the listener uses a different factory. Attach the handler to the factory actually used by the endpoint:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        orderKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory,
            DefaultErrorHandler orderErrorHandler
        ) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(orderErrorHandler);

    return factory;
}
~~~

If an application has multiple factories, each factory may need its own policy. Never assume every `@KafkaListener` automatically uses the same handler when the application defines custom factories.

## 6. DeadLetterPublishingRecoverer and DLT send errors

A common recovery failure scenario is failing to publish to the DLT. Configure the recoverer so send errors are detected and thrown instead of silently treating the send as complete.

### 6.1. Enabling send result checking

Since Spring Kafka 2.7, `DeadLetterPublishingRecoverer` supports `setFailIfSendResultIsError(true)` to throw an exception when the DLT send result reports an error.

~~~java
@Bean
public DefaultErrorHandler orderErrorHandler(
    KafkaTemplate<Object, Object> kafkaTemplate
) {
    DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(kafkaTemplate);

    recoverer.setFailIfSendResultIsError(true);
    recoverer.setWaitForSendResultTimeout(Duration.ofSeconds(10));

    DefaultErrorHandler handler =
        new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L)
        );

    handler.setResetStateOnRecoveryFailure(true);
    return handler;
}
~~~

The send confirmation timeout must match producer timeouts and SLAs. If the confirmation timeout is too short, the recoverer may report an error even though the broker already wrote the record and the response simply arrived late. That can cause duplicate DLT publishing on the next recovery attempt; therefore, design the DLT pipeline to tolerate duplicates.

### 6.2. Why confirm DLT publishing?

If the application treats recovery as successful as soon as `send` is called, the source record can be marked recovered before knowing whether the DLT actually received it. With asynchronous sends, checking the send result catches producer/broker errors and keeps the source record in the recovery flow when DLT publishing fails.

Verify clearly:

- Whether the producer receives broker acknowledgments.
- Whether the DLT topic exists and has enough partitions.
- Whether the serializer can serialize both normal payloads and failed payloads.
- Whether the producer has write permissions on the DLT.
- Whether the confirmation timeout fits actual latency.

### 6.3. Checking DLT topic configuration

Under the default resolver, records are typically sent to a topic with a `-dlt` suffix and the partition matching the source partition. When using default routing, the DLT topic needs at least as many partitions as the source topic.

If using a custom resolver, you can route to another topic or partition:

~~~java
DeadLetterPublishingRecoverer recoverer =
    new DeadLetterPublishingRecoverer(
        kafkaTemplate,
        (record, exception) ->
            new TopicPartition(record.topic() + "-dlt", record.partition())
    );
~~~

Ensure the destination actually exists, the partition is valid, and ACLs permit producer writes. If DLT publishing fails due to a misconfigured destination, resetting `BackOff` simply repeats the exact same error until the configuration is fixed.

## 7. Choosing true or false by scenario

No single value fits every application. The decision depends on whether the listener should rerun after recovery fails.

| Scenario | Usually appropriate choice | Reason |
|---|---|---|
| DLT broker temporarily unavailable, listener may succeed on retry | `true` | Allows the entire processing cycle to restart |
| Listener downstream temporarily failing, DLT also unavailable | `true` | Gives the listener another chance to succeed after waiting |
| Invalid payload, listener retries cannot fix the data | `false` may fit | Avoids futile repeated processing; retries recovery instead |
| Recovery service can recover, but listener has hard-to-repeat side effects | Consider `false` | Avoids re-invoking the listener when recovery is the failing part |
| Misconfigured DLT destination | Neither value fixes the error on its own | Fix the topic, partition, ACL, or serializer first |
| Must rerun full business logic after every recovery failure | `true` | Resets `BackOff` so the listener gets a fresh retry cycle |

Notably, `false` does not mean dropping the record or committing the offset immediately. It merely keeps `BackOff` in its exhausted state so the next delivery retries recovery without running a new listener retry cycle. The record must still be successfully recovered or handled by another governance policy before advancing the offset.

## 8. RetryListener for observing recovery failures

Spring Kafka provides `RetryListener` to receive notifications about retries and recovery. Since Spring Kafka 2.8.10, callbacks for batch listeners were also added.

Key record callbacks:

- `failedDelivery(record, exception, deliveryAttempt)`: listener delivery failed.
- `recovered(record, exception)`: record was recovered successfully.
- `recoveryFailed(record, original, failure)`: recoverer failed; the first exception parameter is the listener's original exception and the last is the exception thrown during recovery.

Example:

~~~java
public class OrderRetryListener implements RetryListener {

    private static final Logger log =
        LoggerFactory.getLogger(OrderRetryListener.class);

    @Override
    public void failedDelivery(
        ConsumerRecord<?, ?> record,
        Exception exception,
        int deliveryAttempt
    ) {
        log.warn(
            "Listener delivery failed: topic={}, partition={}, offset={}, attempt={}",
            record.topic(),
            record.partition(),
            record.offset(),
            deliveryAttempt,
            exception
        );
    }

    @Override
    public void recovered(
        ConsumerRecord<?, ?> record,
        Exception exception
    ) {
        log.info(
            "Record recovered: topic={}, partition={}, offset={}",
            record.topic(),
            record.partition(),
            record.offset()
        );
    }

    @Override
    public void recoveryFailed(
        ConsumerRecord<?, ?> record,
        Exception original,
        Exception failure
    ) {
        log.error(
            "Recovery failed: topic={}, partition={}, offset={}",
            record.topic(),
            record.partition(),
            record.offset(),
            failure
        );
        log.error("Original listener failure", original);
    }
}
~~~

Register the listener with the error handler:

~~~java
DefaultErrorHandler handler =
    new DefaultErrorHandler(recoverer, new FixedBackOff(1_000L, 2L));

handler.setResetStateOnRecoveryFailure(true);
handler.setRetryListeners(new OrderRetryListener());
~~~

Callback signatures and registration APIs must match the Spring Kafka version in use. If processing batches, check the Javadoc overloads accepting `ConsumerRecords`.

`recoveryFailed` is a crucial signal for separating listener errors from DLT/recoverer errors. If operations only monitors listener failure counts, they can miss that the DLT is failing to write.

## 9. Resetting state is not resetting offsets

The name `resetStateOnRecoveryFailure` is easily mistaken for meaning the consumer resets offsets. In reality, it only controls the error handler's `BackOff` state.

| Component | Changed by resetStateOnRecoveryFailure? |
|---|---|
| `BackOff` retry state of the failing record | Yes |
| Consumer group's committed offset | Not directly |
| Partition log start/end offset | No |
| Record contents in Kafka | No |
| Consumer group ID | No |
| Business state in the database | No |
| Listener payload | No |
| DLT destination | No |

If you need to replay already-committed records, use a deliberate offset reset procedure or a new group. Never use `resetStateOnRecoveryFailure` for that purpose.

Similarly, if database state needs restoring, use transactions, compensation, or a separate business workflow. The error handler does not automatically roll back side effects already committed in systems outside Kafka.

## 10. Recovery failure and offset acknowledgments/commits

When the recoverer throws an exception, the record is not considered successfully recovered. Under standard behavior, the record re-enters the redelivery flow (via seek in standard seek mode, or retained/resubmitted if `seekAfterError=false` is configured).

This ensures the record is not skipped just because DLT publishing failed. However, exact commit progress also depends on:

- Whether the listener uses `AckMode.RECORD` or `AckMode.BATCH`.
- Whether the listener is record-based or batch-based.
- Whether the error handler has already committed offsets for records preceding the failed record.
- Whether the recoverer succeeds on the next attempt.
- Properties such as `ackAfterHandle` and `commitRecovered`.
- Whether the consumer rebalances or restarts during recovery.

Do not assume an exception from the recoverer always leads to the exact same offset commit across all ack modes. During deployment, inspect actual committed offsets per partition.

If the recoverer succeeds, the handler can treat the record as handled under the recovery policy and advance the offset accordingly. If the recoverer fails, the record must continue being retried—never commit past it in a way that loses the record.

## 11. Interaction with seekAfterError=false

Since Spring Kafka 2.9, `DefaultErrorHandler` can retain unprocessed records in the listener container and resubmit them instead of seeking the partition to refetch. This can be enabled with:

~~~java
handler.setSeekAfterError(false);
~~~

This setting changes how the container re-acquires unprocessed records, without changing the meaning of `resetStateOnRecoveryFailure`.

When recovery fails:

- The failed record still returns to the delivery/recovery flow.
- `BackOff` state is reset or kept per `resetStateOnRecoveryFailure`.
- If records are retained/resubmitted, retained state lives in memory and does not survive a process restart.
- If the consumer stops, Kafka recovers from the committed offset and uncommitted records may be redelivered.

The two settings answer two separate questions:

| Property | Question |
|---|---|
| `seekAfterError` | Are unprocessed records re-acquired via seek/fetch or retain/resubmit? |
| `resetStateOnRecoveryFailure` | After the recoverer fails, is `BackOff` state reset or kept in its exhausted state? |

Avoid changing both properties simultaneously without understanding the individual impact of each.

## 12. Common causes of recovery failure

### 12.1. DLT broker or partition unavailable

The target broker may lose connectivity, the partition leader may be undergoing election, or the DLT topic has not been created yet. The producer cannot write the record, so the recoverer throws an exception.

Check broker availability, partition leaders, replication, and topic metadata. If using the default partition resolver, verify the DLT has enough matching partitions.

### 12.2. Authorization

The producer/app may have permission to read the source topic yet lack write permission on the DLT topic. Then the listener fails and recovery also fails due to ACLs.

Check the producer's principal, `WRITE`/`DESCRIBE` permissions on the DLT topic, and security settings of the producer factory used by the recoverer.

### 12.3. Serialization

The payload may be a business object, a byte array, or another type after a deserialization failure. If the `KafkaTemplate` uses a serializer that does not support the type being recovered, DLT publishing fails.

You may need multiple serializers or a template capable of handling both normal payloads and failed payloads. Check key, value, and headers.

### 12.4. Record size

The source record may be close to the broker's size limit. Once exception headers or metadata are added, the DLT record can become larger and get rejected by the broker.

Check record size after adding headers, producer/broker/topic limits, and payload design. Do not raise limits arbitrarily if payloads are too large; you may need to trim data stored in error records or store payloads in external storage.

### 12.5. Timeout and ambiguous results

The producer might send the record successfully yet fail to receive a response within the timeout. The recoverer treats the send as failed and retries on the next delivery. If the DLT record was already written, subsequent recovery may produce a duplicate DLT entry.

Therefore, DLT consumers should have an event ID or idempotency key to detect duplicate records. A timeout does not prove the broker failed to write the record.

## 13. Investigation runbook for recovery failures

When seeing `recoveryFailed` callbacks or recoverer exception logs, proceed in order:

1. Record the source record's topic, partition, offset, key, and event ID.
2. Record the listener's original exception and the new exception from the recoverer.
3. Identify which recoverer was invoked—e.g., DLT publisher or custom recoverer.
4. Check the DLT destination, partition, leader, and ACLs.
5. Check serializers, record size, and headers.
6. Check producer send results, retries, request timeouts, and delivery timeouts.
7. Verify `setFailIfSendResultIsError(true)` is enabled if the recoverer needs to detect DLT send errors.
8. Check `resetStateOnRecoveryFailure` to know whether the next redelivery reruns the listener retry cycle or retries recovery immediately.
9. Compare committed offsets before and after recovery failure.
10. After fixing the root cause, verify the record is successfully published to the DLT or processed by the listener.
11. Check for DLT duplicates if the previous send timed out yet may have been written by the broker.

Do not look solely at the final exception. The original exception explains why the listener failed; the recovery exception explains why the record did not enter the expected recovery stream.

## 14. Testing state reset on recovery failure

Test against a Kafka test broker or dedicated integration environment with a source topic, DLT topic, and test consumer group.

### 14.1. Testing default state reset

1. Configure `DefaultErrorHandler` with a `FixedBackOff` having a small retry count.
2. Make the listener always throw an exception.
3. Make the recoverer throw an exception on its first invocation.
4. Verify the `recoveryFailed` callback is invoked.
5. Make the recoverer succeed on the next invocation.
6. Observe that the listener is invoked again under a fresh `BackOff` cycle when `resetStateOnRecoveryFailure` is `true`.
7. Verify the record is marked recovered only when the recoverer completes successfully.
8. Verify the committed offset of the source partition.

### 14.2. Testing disabled state reset

1. Use the same `BackOff` and listener.
2. Configure `setResetStateOnRecoveryFailure(false)`.
3. Let the listener fail until `BackOff` is exhausted.
4. Make the recoverer fail.
5. Trigger the next delivery.
6. Verify the handler retries recovery without running a new listener retry cycle.
7. Let the recoverer succeed and verify offset progression per ack mode.

### 14.3. Testing DLT publish timeout

1. Simulate a case where the producer does not receive a DLT send confirmation within the deadline.
2. Enable `setFailIfSendResultIsError(true)`.
3. Record the recovery failure.
4. Verify whether the DLT record already exists using the event ID.
5. Let the next recovery attempt run and check for duplicates.
6. Verify the DLT consumer handles it idempotently.

### 14.4. Testing restart and rebalance

1. Make the recoverer fail while the record is still uncommitted.
2. Stop the consumer or trigger a controlled rebalance.
3. Restart with the same group ID.
4. Verify the record is redelivered from the committed offset.
5. Verify in-memory `BackOff` state can reinitialize after restart.
6. Verify recovery does not skip the record and duplicate side effects are controlled.

Tests must observe listener invocations, recoverer invocations, DLT contents, and committed offsets. Checking only exception log counts is insufficient to prove state resets properly.

## 15. Metrics and alerting

Separate listener failure metrics from recovery failure metrics because the two error types have different causes and owners.

| Metric | Purpose |
|---|---|
| Listener delivery failure count | Track business or downstream errors in the listener |
| Retry attempt count | Track delivery retries |
| Recovery attempt count | Track recoverer invocations |
| Recovery failure count | Detect non-functioning DLT/custom recoverer |
| DLT send success/error | Verify the dead-letter publishing stream |
| Time from first failure to recovery | Measure how long a record stays in the error flow |
| Consumer lag | Monitor impact of retries/recovery on group progress |
| DLT topic lag | Detect unprocessed records in the DLT |
| Duplicate DLT event count | Detect resends after ambiguous timeouts |

`RetryListener` can be used to record logs and metrics per record. Metric labels should have low cardinality, such as topic, exception class, or outcome. Do not use event IDs, order IDs, or keys as metric labels because value counts can grow unboundedly.

Alerts should distinguish:

- Listener failures rising while recovery still succeeds.
- Recovery failures rising due to DLT broker/ACL/serializer issues.
- Prolonged recovery failures causing consumer lag to grow.
- DLT publishing succeeding while the DLT consumer is not processing.
- A single record repeating recovery failures multiple times.

## 16. Common design mistakes

**Confusing resetting BackOff with resetting offsets:** `resetStateOnRecoveryFailure` does not rewind the consumer group to the start of the topic.

**Not checking DLT publish results:** the recoverer may fail to detect send errors without proper confirmation settings.

**Setting `false` solely to reduce retries:** the next delivery will retry recovery without running a new listener retry cycle. If the listener needs time to recover, this setting may be inappropriate.

**Setting `true` when the listener has non-idempotent side effects:** a recovery failure can cause the listener to rerun and create duplicate side effects.

**Not separating original exceptions from recovery exceptions:** logging only the recoverer's exception hides the original reason the listener failed.

**Not checking DLT partition counts:** the default resolver may send to the same partition index as the source record, so the DLT needs enough partitions.

**Assuming a timeout means never sent:** the DLT may have already been written while the response was lost; subsequent recovery can create duplicates.

**Not tracking the `recoveryFailed` callback:** dashboards showing only listener failures will miss incidents in the DLT or recovery system.

**Using a custom recoverer that only logs:** if logging is the entire recovery action, the record can be considered recovered and offsets advance without any durable copy saved.

**Not testing process restarts:** the `BackOff` tracker is not a durable state store; restarts can restart delivery cycles based on consumer state and offsets.

## 17. Production operating principles

- Understand clearly the difference between listener failure and recovery failure.
- Use the default `resetStateOnRecoveryFailure=true` when you want a record to get another listener retry cycle after a recoverer failure.
- Choose `false` when you want the next redelivery to retry recovery immediately without re-running an exhausted retry cycle.
- Check your Spring Kafka version; default reset behavior changed starting in 2.5.5.
- Configure the DLT publisher to detect send failures and set an appropriate confirmation timeout.
- Ensure the DLT topic, partitions, ACLs, and serializers are ready.
- Use `RetryListener` to distinguish `failedDelivery`, `recovered`, and `recoveryFailed`.
- Keep event IDs stable and make DLT consumers idempotent to tolerate duplicate publishes.
- Monitor committed offsets, consumer lag, and DLT lag alongside recovery failure counts.
- Never use state reset to alter offsets or roll back databases.
- Test both `true`/`false` values, DLT publish failures, timeouts, and process restarts before broad rollout.

`resetStateOnRecoveryFailure` decides how `BackOff` proceeds after a recoverer fails. The default resets the cycle so the record is retried under the initial policy; `false` skips a new retry cycle and retries recovery on the next delivery. Choose based on whether the listener should run again or recovery itself is what needs retrying, while protecting side effects and confirming DLT publishes truly succeed.
