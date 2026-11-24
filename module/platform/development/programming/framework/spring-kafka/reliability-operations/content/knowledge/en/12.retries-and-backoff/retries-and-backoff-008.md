# Reset State When Exception Changes

In Spring Kafka, retrying is not just invoking a listener a few more times. `DefaultErrorHandler` also tracks **the retry state of a failing record**: which error occurred, which `BackOff` step is active, when to stop retrying, and when to hand the record to the recoverer. When the exception changes across attempts for the same record, continuing to use the previous retry state can cause the application to miss a chance to recover or apply the wrong error-classification policy.

`resetStateOnExceptionChange` is an option that allows **reinitializing `BackOff` state when the exception type changes between failures**. In modern Spring Kafka versions, `DefaultErrorHandler` supports this option via `setResetStateOnExceptionChange(boolean)`. Spring Kafka 2.9 and later default to `true`; you can set it explicitly to express application intent. For older versions, verify the actual API and default value.

This feature belongs to the listener container's retry layer. It does not delete the consumer group's committed offsets, does not call `seekToBeginning()`, does not reset the topic, and does not turn an existing record into a new Kafka record. What gets reset is **the error-tracking state and `BackOff` schedule for that record inside the error handler**.

## 1. What is retry state in `DefaultErrorHandler`?

When a listener encounters an error, Spring Kafka must remember prior failed attempts to decide whether to retry. For a record listener, failure tracking is tied to the record being processed and its topic, partition, and offset context. `BackOff` determines wait intervals between attempts and when retries have expired.

Example:

```java
BackOff backOff = new FixedBackOff(1_000L, 2L);

DefaultErrorHandler errorHandler =
        new DefaultErrorHandler(recoverer, backOff);
```

`FixedBackOff(1_000L, 2L)` means **at most two retries after the first delivery**, each separated by a 1,000-millisecond wait. If the error persists and nothing resets the state, the recoverer is invoked after retries are exhausted. The `recoverer` is the action that handles the record when the listener cannot complete it, such as moving it to a Dead Letter Topic (DLT).

```text
Delivery 1: error A
              |
              v
        wait 1,000 ms
              |
              v
Delivery 2: error A
              |
              v
        wait 1,000 ms
              |
              v
Delivery 3: error A
              |
              v
          recoverer
```

Retries here are listener re-invocations managed by the error handler, not the producer resending the record to Kafka. Distinguish listener delivery counts from producer broker-write retry counts.

Retry tracking state lives on the application/container side, not as durable metadata persisted by Kafka alongside committed offsets. If the process stops, uncommitted records can be redelivered by the consumer group after restart and start a fresh retry cycle. Therefore, an in-memory retry budget is not a global limit persisting across restarts.

## 2. When the exception type changes, what should happen?

A single record can fail for different reasons across different deliveries. For example, on the first call the database times out; on the next attempt the database responds, yet the service discovers the event violates a business invariant. A new cause requires a new decision.

| Attempt | Exception | Interpretation |
|---:|---|---|
| 1 | `InventoryTimeoutException` | Inventory service temporarily unresponsive |
| 2 | `InventoryTimeoutException` | Previous error persists |
| 3 | `InvalidReservationException` | Connection recovered, but reservation data is invalid |

If the state from `InventoryTimeoutException` is kept, the error handler might already be at the end of its retry budget when `InvalidReservationException` arrives. Yet the two errors have different natures: one is retryable, while the other may need to go straight to the DLT.

When `resetStateOnExceptionChange` is enabled, a change in exception type **restarts the `BackOff` sequence for the new error type**. Combined with exception classification, the error handler can apply the retry/recover decision appropriate for the new exception. If the new exception is classified as not-retryable, the application should not delay with pointless retries.

Conceptual diagram:

```text
Record orders-0, offset 205
           |
           v
Listener fails: exception A
           |
           v
BackOff is tracking error A
           |
           v
Listener fails next time
           |
           v
Is current exception same type A?
           |
     +-----+------+
     |            |
    Yes           No
     |            |
     v            v
Continue     Reset BackOff
BackOff      state for new error
     |            |
     +-----+------+
           |
           v
    Retry or recover
   per classification
```

"Exception change" here refers to the **exception type** used by the error-tracking mechanism—not merely changing the wording in `getMessage()` or creating a new instance of the same class. When errors are wrapped through multiple exception layers, verify the cause-extraction mechanism of your Spring Kafka version so the critical exception type is actually recognized.

## 3. Enabling `resetStateOnExceptionChange` with Java configuration

Consider an order-event processing application with two error groups: retryable transient dependency errors and deterministic non-retryable data errors. The error handler uses finite retries, sends failed records to a DLT, and resets state when the exception type changes.

```java
@Bean
DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> dltKafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(
                    dltKafkaTemplate,
                    (record, exception) -> new TopicPartition(
                            record.topic() + ".DLT",
                            record.partition()));

    // Recovery must report an error if DLT publishing fails.
    recoverer.setFailIfSendResultIsError(true);

    // Initial invocation + at most 2 retries, 1 second apart.
    FixedBackOff backOff = new FixedBackOff(1_000L, 2L);

    DefaultErrorHandler handler =
            new DefaultErrorHandler(recoverer, backOff);

    handler.addNotRetryableExceptions(
            InvalidOrderPayloadException.class,
            UnsupportedEventVersionException.class);

    handler.setResetStateOnExceptionChange(true);

    return handler;
}
```

The configuration uses custom-defined domain exceptions. Those exception classes must exist in the application. `DeadLetterPublishingRecoverer` uses a template with serializers matching key/value, the DLT topic must have the partition pointed to by the resolver, and the producer needs write permissions. `setFailIfSendResultIsError(true)` surfaces DLT publish failures back to the error handler in versions supporting this API.

Register the error handler with the container factory actually used by the listener:

```java
@Bean(name = "orderKafkaListenerContainerFactory")
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
orderKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        DefaultErrorHandler orderErrorHandler) {

    ConcurrentKafkaListenerContainerFactory<String, OrderCreated> factory =
            new ConcurrentKafkaListenerContainerFactory<>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(orderErrorHandler);
    factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.RECORD);

    return factory;
}
```

Listener:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-processing-service",
        containerFactory = "orderKafkaListenerContainerFactory")
public void handle(OrderCreated event) {
    orderService.processIdempotently(event);
}
```

In this example, `AckMode.RECORD` commits the offset after the listener finishes each record successfully per container mechanics. When the listener throws an exception, `DefaultErrorHandler` manages retries and recovery. Resetting `BackOff` when the exception type changes **does not change the ack mode** or when offsets are committed.

If the application has multiple factories, verify the right `containerFactory` on each `@KafkaListener`. Declaring an error handler bean is not enough to guarantee every listener uses it.

## 4. Progression example: both exception types are retryable

Suppose a record initially fails to reach the inventory system. After one retry, inventory responds, but the database connection times out. Both exceptions are treated as transient and retryable.

With `FixedBackOff(1_000L, 2L)` and `resetStateOnExceptionChange=true`, illustrative progression:

| Delivery | Exception | Decision |
|---:|---|---|
| 1 | `InventoryTimeoutException` | Start retry state for this error type, wait 1 second |
| 2 | `InventoryTimeoutException` | Consume next retry for the same error type |
| 3 | `DatabaseTimeoutException` | Exception type changed; reset `BackOff` to start a retry chain for the new error |
| 4 | `DatabaseTimeoutException` | Next retry for the database error |
| 5 | `DatabaseTimeoutException` | Budget exhausted for current error; invoke recoverer if still failing |

Delivery counts in the table illustrate the reset sequence when exceptions change. Exact behavior also depends on the `BackOff` type, how exceptions are classified, and whether prior attempts succeeded.

Key takeaway: **a record's retry count can exceed the retry limit set for a single `BackOff` sequence if the exception type keeps changing**. This helps when errors transition from one transient state to another transient state, but it can also prolong record processing time.

### Risk when exceptions alternate

If the same record continuously alternates between `InventoryTimeoutException` and `DatabaseTimeoutException`, `BackOff` state can be reset repeatedly. The record will be held longer than expected compared to a single fixed retry sequence.

```text
A -> B -> A -> B -> A -> B -> ...
     ^     ^     ^
     |     |     |
  exception type changes, may reset BackOff
```

If the application needs to cap total processing attempts or total elapsed time from the first delivery, add an independent business/operational policy, such as an event deadline, durably recorded delivery counts, or a threshold to route to quarantine. Do not rely on an in-memory `FixedBackOff` as a global guardrail when reset-on-exception-change is enabled.

## 5. Progression example: the new exception is not-retryable

Another scenario is that after the dependency recovers, the listener detects permanently invalid data.

```text
Delivery 1:
  InventoryTimeoutException   -> retry

Delivery 2:
  InventoryTimeoutException   -> retry

Delivery 3:
  InvalidOrderPayloadException -> error type changed
                                -> do not retry per classification
                                -> recoverer / DLT
```

In the configuration from the previous section, `InvalidOrderPayloadException` is in `addNotRetryableExceptions(...)`. It must be handled under the non-retryable policy, even if the record previously experienced a transient failure.

When the exception changes type, evaluating classification against the new error type is critical. Verify behavior in your exact Spring Kafka version, especially if the application wraps exceptions or customizes the classifier. If you want to route the record straight to the DLT, ensure the actual exception received by the handler can be classified as not-retryable.

Do not mark a broad exception like `RuntimeException` as not-retryable just because some data errors are wrapped in it. Overly broad classification can send temporary database failures straight to the DLT. Keep domain exceptions specific and preserve the cause chain.

## 6. Distinguishing reset on exception change from reset after recovery failure

`DefaultErrorHandler` has two related reset options with different meanings:

| Property | Trigger condition | Effect |
|---|---|---|
| `resetStateOnExceptionChange` | The exception type across attempts for the same record changes | Recreates the `BackOff` sequence for the new error type |
| `resetStateOnRecoveryFailure` | The recoverer was called, yet recovery itself failed | Decides whether to restart the `BackOff` sequence when the record must continue being handled |

Two completely different scenarios:

**Scenario A — Exception changes:** the listener fails first with a timeout, next with a validation error. The handler tracks changes in listener exception types and resets state as configured.

**Scenario B — Recovery fails:** the listener keeps throwing the same exception, retries are exhausted, yet `DeadLetterPublishingRecoverer` cannot write to the DLT due to missing ACLs. The error occurs inside the recoverer; `resetStateOnRecoveryFailure` controls resetting `BackOff` in this branch.

Example configuring both explicitly:

```java
DefaultErrorHandler handler =
        new DefaultErrorHandler(recoverer, new FixedBackOff(1_000L, 2L));

handler.setResetStateOnExceptionChange(true);
handler.setResetStateOnRecoveryFailure(true);
```

The two properties do not replace each other. You can enable one, both, or adjust per requirements. When recovery keeps failing, monitor DLT publish errors, backoff, and consumer lag; resetting state does not fix missing ACLs, broken serializers, or disconnected brokers.

## 7. Exception wrappers and cause chains

In Spring applications, the root exception is not always the outermost object. A listener method might throw `InvalidOrderPayloadException`, yet Spring Kafka or an application layer wraps it in another exception:

```text
ListenerExecutionFailedException
       |
       +-- cause: OrderProcessingException
                       |
                       +-- cause: InvalidOrderPayloadException
```

If failures all surface under the same wrapper while the root cause changes, how "exception type change" is evaluated depends on the unwrapping and cause-traversal mechanism of your Spring Kafka version. Configure, test with the actual wrappers present in your application, and observe the exception received by the recoverer.

Preserve the original cause when wrapping exceptions:

```java
try {
    reservationService.reserve(order);
}
catch (InvalidOrderPayloadException ex) {
    throw new OrderProcessingException("Invalid order event", ex);
}
```

Do not construct a new exception and discard the cause:

```java
catch (InvalidOrderPayloadException ex) {
    throw new OrderProcessingException("Cannot process event");
}
```

In the second case, the error handler no longer has enough information to identify the original error. For accurate classification, let domain exceptions propagate directly or configure the classifier for exception wrappers and appropriate cause traversal.

Do not use changes in exception messages as a signal to reset retries. Two `TimeoutException`s with different messages can still represent the same transient error; conversely, two different exception classes can represent two distinct causes requiring different policies.

## 8. Impact on ordering, lag, and throughput

When a record is retried continuously, the container may hold off moving to subsequent records in the partition, depending on error-handler strategy and listener mode. Enabling reset on exception change can increase processing attempts before recovery, raising consumer lag and unprocessed record age.

For example, the `payment-events` topic needs to complete one record before processing the next record with the same key. A record hitting error A, then B, then A can stall the processing stream longer than a plain retry configuration. Valid records arriving later in the same partition can be delayed.

In operations, balance:

- The benefit of granting a fresh retry budget when a new cause might self-recover.
- Requirements on maximum event processing time.
- Cost of re-calling databases and downstream APIs.
- Increased latency for trailing records.
- The option to move failing records to the DLT early to isolate and handle them later.

If per-key ordering is mandatory, weigh the impact of DLTs and retry topics on whether one record is processed before or after another. `resetStateOnExceptionChange` only controls retry state; it does not solve the broader ordering problem across multiple topics or partitions.

## 9. Relationship to `seekAfterError` and ack mode

Several configurations are easily confused with resetting retry state:

| Configuration | Responsibility |
|---|---|
| `setResetStateOnExceptionChange(true)` | Resets the `BackOff` schedule when exception type changes |
| `setSeekAfterError(false)` | Lets the container retain and resubmit unprocessed records rather than seeking the partition to refetch |
| `setCommitRecovered(true)` | Instructs committing the record's offset after the recoverer finishes, per applicable ack mode rules |
| `AckMode.RECORD` | Commits progress after the listener processes each record successfully |
| `AckMode.MANUAL_IMMEDIATE` | Enables direct acknowledgment under the container's manual-immediate mechanism |

`seekAfterError=false` decides how records are redelivered, whereas `resetStateOnExceptionChange=true` decides how retry budgets are tracked when error types change. Both settings can coexist without directly depending on each other.

`commitRecovered` is a different concern: whether the consumer group marks the offset as processed after successful recovery. Resetting state **does not** commit offsets automatically, and a successful listener retry **does not** make side effects outside Kafka exactly-once. For side effects like database updates or payment requests, design idempotency.

## 10. Container transactions and `DefaultAfterRollbackProcessor`

When a listener container runs with Kafka transactions, an exception can roll back the current transaction. Spring Kafka uses `DefaultAfterRollbackProcessor` to handle retrying or recovering records after rollback in the transactional model.

`DefaultAfterRollbackProcessor` also supports resetting state on exception type changes in compatible Spring Kafka versions. When this behavior is needed, configure the processor on the transactional listener container rather than only setting it on a `DefaultErrorHandler` meant for non-transactional flows.

Illustrative example:

```java
DefaultAfterRollbackProcessor<String, OrderCreated> processor =
        new DefaultAfterRollbackProcessor<>(
                recoverer,
                new FixedBackOff(1_000L, 2L));

processor.setResetStateOnExceptionChange(true);
```

This snippet assumes `recoverer` is a compatible `ConsumerRecordRecoverer` and the Spring Kafka version supports this setter. Wiring the processor into the container factory, configuring the Kafka transaction manager, and setting up a transactional DLT publisher must still follow the application's transaction design.

In transactional recovery, committing the recovered record's offset may use a new transaction depending on processor configuration. Resetting retry state does not automatically enable transactional recovery. Separate retry, rollback, recovery, and commit clearly so you do not mistakenly assume an exception change automatically starts or commits a Kafka transaction.

## 11. Observing retries when exceptions change

For diagnostics, logs and metrics must show **which record**, **which exception**, **which delivery number**, and **whether the handler retried or recovered**. Useful fields include:

| Field | Purpose |
|---|---|
| Topic, partition, offset | Identify the record being retried |
| Group ID and listener/container ID | Distinguish the executing consumer |
| Exception class and root cause class | Detect error-type transitions |
| Delivery attempt | Observe listener invocation counts within the current processing cycle |
| Retry/recovery outcome | Know whether the record was retried or moved to DLT |
| Duration since first error | Detect records held too long due to repeated retry resets |

Spring Kafka provides `RetryListener` to receive callbacks on failed deliveries, recovered records, and failed recoveries in supported versions. An observation listener can be registered on `DefaultErrorHandler`:

```java
handler.setRetryListeners(new RetryListener() {
    @Override
    public void failedDelivery(
            ConsumerRecord<?, ?> record,
            Exception ex,
            int deliveryAttempt) {
        // Record lightweight metric/log by topic, exception class, and attempt.
    }
});
```

This is an observation callback, not a place to re-invoke the listener or update business databases. Do not perform blocking I/O on the consumption thread inside the callback. When tracking exception transitions, you can increment a counter when the new error's class differs from the previously seen class for the same record within a bounded processing window.

Do not use event IDs, offsets, or exception messages as metric labels because cardinality can explode. Keep detailed identifiers in logs/tracing; use bounded labels on metrics such as service, topic, exception class, and outcome.

## 12. Common failure scenarios

| Symptom | Possible cause | Remediation |
|---|---|---|
| Record retried more times than expected `maxAttempts` | Exception type changed consecutively, resetting `BackOff` | Inspect exception sequence; add a deadline or total processing time limit |
| Not-retryable exception still retried | Exception wrapped; classifier did not recognize new type; listener uses a different handler | Inspect cause chain, classification, and actual container factory |
| Setter configured with no effect | Listener uses another factory/error handler or version lacks the API | Verify dependency version and the bean attached via `setCommonErrorHandler` |
| Recoverer invoked too early | No reset on exception change or new exception is fatal | Inspect per-delivery exception types, backoff state, and classifier |
| Record already sent to DLT reappears | DLT publish and source offset commit non-atomic; restart/commit failure | Check offsets, DLT/replay idempotency, and transactional design if needed |
| Consumer lag climbs continuously | Retry budget reset multiple times; downstream failing continuously | Bound retries, set deadlines, and monitor throughput/record age |
| Error handler misclassifies error type | Multiple errors wrapped into one generic `RuntimeException` or cause lost | Use specific domain exceptions and preserve original causes |

During investigation, prioritize reconstructing the exception sequence for the same topic-partition-offset. Looking only at the last exception can mislead: the record may have already burned through the retry budget of an earlier error type before switching types.

## 13. Test scenarios to include when adopting

An integration test for retry state should control the exception thrown on each delivery and observe retries/recovery. Valuable test cases include:

1. **Same error type continuously:** listener throws exception A on every attempt; verify retry count per `FixedBackOff` and recovery after exhaustion.
2. **Error type changes:** throws A first, then B; verify `BackOff` resets and the retry schedule applies to B.
3. **Error changes to not-retryable:** A is retryable, then B is not-retryable; verify the handler routes to the recoverer per the new classification.
4. **Same class with changing message:** verify this is not treated as an exception-type change.
5. **Multi-layer wrapped exceptions:** verify the classifier detects the right root cause/wrapper per configuration.
6. **Recovery fails:** simulate DLT publish failure to distinguish `resetStateOnRecoveryFailure` from resets caused by exception changes.
7. **Restart mid-retry:** verify committed offsets and idempotency; do not expect in-memory `BackOff` state to survive restarts.
8. **Alternating error types:** A/B/A/B; verify application-level time or attempt caps if the business enforces them.

For each case, record listener invocation counts, exception classes per attempt, recoverer call counts, actual records in the DLT, and committed offsets. Do not claim reset works based solely on the listener being invoked multiple times: increased invocation counts can also come from restarts, rebalances, or retries at another layer.

## 14. Configuration choices for production

Before enabling `resetStateOnExceptionChange` in production, define the desired behavioral goal first:

- If a new exception type typically represents a new transient condition, resetting retry state gives that error type a chance to recover within its own budget.
- If the stream has strict processing deadlines, repeated resets can let a record hold a partition too long; add independent time guardrails.
- If the new exception is a deterministic data error, classify it as not-retryable and design a resilient recoverer.
- If using wrappers heavily, preserve causes and confirm the classifier matches the listener's actual exceptions.
- If DLT publishing can fail, the recoverer must report errors and recovery failures must be monitored.
- If using Kafka transactions, confirm retry state resides in the processor matching the active rollback flow.

Key points to keep in operational runbooks: locate the right group/partition/offset, read the exception sequence by attempt, determine how long the record has been held, inspect DLT and offsets, and then decide whether to fix the downstream failure, update exception classification, or tune the retry budget. Never manually reset consumer offsets just to hide repeated retries; advancing offsets can drop records, while rewinding offsets can create duplicate side effects.

`resetStateOnExceptionChange` solves a specific retry scenario: **a record transitions from one error type to another while being reprocessed**. When understood as a mechanism for resetting `BackOff` state and combined with exception classification, recovery, idempotency, and per-record observability, operations teams can avoid futile retries while still giving newly emerging transient errors a fair chance to recover.
