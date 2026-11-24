# Choosing Blocking vs. Non-Blocking Retry

## Lesson Objectives

In the **Non-blocking retry** chapter, this lesson helps you decide how to handle a failed Kafka record: keep the record in the consumer flow to retry (blocking retry), or forward the record to a retry topic for later reprocessing (non-blocking retry).

**SPRING_KAFKA_MESSAGING** focuses on building applications that produce and consume Kafka events using Spring Kafka, `KafkaTemplate`, and `@KafkaListener`; it also helps learners understand topics, partitions, offsets, consumer groups, serialization, retry, dead-lettering, transactions, exactly-once semantics, concurrency, and testing. Retry selection must match event characteristics and how the application operates consumer groups.

After this lesson, you will be able to:

- Describe the mechanisms of blocking retry and non-blocking retry.
- Choose a strategy based on wait duration, ordering, throughput, and business requirements.
- Configure blocking retry using `DefaultErrorHandler` and `DeadLetterPublishingRecoverer`.
- Configure non-blocking retry using `RetryableTopic`, `Backoff`, and `DltHandler`.
- Design retry topics, DLTs, partitions, and retention.
- Classify retryable and non-retryable exceptions.
- Ensure idempotency when records are redelivered.
- Understand retry topic limitations with batch listeners and transactions.
- Test retries, DLTs, ordering, and behavior during prolonged downstream outages.

## 1. Two Retry Approaches in Spring Kafka

When a listener throws an exception, Spring Kafka must decide how to bring the failed record back for reprocessing.

**Blocking retry** keeps retrying inside the listener container's processing flow. The error handler waits through backoff and redelivers the record. While the record is being retried, subsequent records on the same partition may be delayed.

**Non-blocking retry** forwards the failed record to a retry topic. Another listener container reads the retry topic and processes the record when the scheduled time arrives. The main topic consumer can move on to subsequent records.

~~~mermaid
flowchart TD
    A["Record from main topic"] --> B["Listener processes"]
    B --> C{"Succeeded?"}
    C -->|Yes| D["Commit offset"]
    C -->|No| E{"Retry strategy"}
    E --> F["Blocking retry"]
    F --> G["Backoff in consumer flow"]
    G --> B
    E --> H["Non-blocking retry"]
    H --> I["Publish to retry topic"]
    I --> J["Wait for retry time"]
    J --> K["Retry listener"]
    K --> L{"Succeeded?"}
    L -->|Yes| M["Complete"]
    L -->|No| I
    I --> N["Attempts exhausted"]
    N --> O["Dead-letter topic"]
~~~

Both mechanisms share the goal of handling transient errors, but involve different trade-offs. No single option fits every event stream.

## 2. How Does Blocking Retry Work?

Blocking retry is commonly configured with `DefaultErrorHandler`. When a listener throws an exception:

1. The container passes the exception to the error handler.
2. The error handler classifies the exception.
3. If the exception is retryable, the handler waits according to backoff.
4. The record is redelivered via the container's seek/redelivery mechanism.
5. If retries reach their limit, the recoverer is invoked.
6. The recoverer can publish the record to a DLT.

Example configuring two retries, waiting one second each:

~~~java
@Bean
public DefaultErrorHandler kafkaErrorHandler() {
    FixedBackOff backOff = new FixedBackOff(1_000L, 2L);
    return new DefaultErrorHandler(backOff);
}
~~~

In this example, `FixedBackOff(1_000L, 2L)` means two retries after the initial processing attempt. If the initial attempt and both retries fail, the listener has been invoked three times in total before final recovery.

Attach the handler to the listener container factory:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        kafkaListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory,
                DefaultErrorHandler kafkaErrorHandler) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(kafkaErrorHandler);
    return factory;
}
~~~

Listeners using this factory will apply the configured retry policy.

## 3. When Is Blocking Retry Suitable?

Blocking retry is typically suitable when:

- Errors are likely to resolve within a short time.
- Total retry duration is small and predictable.
- Subsequent events must wait for prior events to finish.
- Preserving processing order within a partition matters.
- The application uses batch listeners.
- The listener requires container transactions in a compatible configuration.
- You want to avoid creating additional retry topics and consumer groups.

For example, a database connection was just reset. Retrying after one second may succeed once the connection pool recovers.

Blocking retry also fits when events for the same aggregate have ordering dependencies. If `OrderCreated` has not finished processing, `PaymentCaptured` may need to wait to avoid creating an invalid state.

## 4. Limitations of Blocking Retry

Blocking retry consumes consumer thread time. When backoff is long or records fail continuously:

- The consumer thread spends time waiting instead of processing new records.
- Subsequent records on the same partition may be delayed.
- Consumer lag increases.
- Processing time may approach or exceed `max.poll.interval.ms`.
- Multiple consumers retrying simultaneously can place heavy load on downstream systems.
- A poison message can slow down the stream if exceptions are misclassified.

Do not configure blocking retry with unlimited attempts. Cap the number of attempts and total retry duration, then route records to a DLT or an appropriate quarantine mechanism.

For long backoffs, examine how Spring Kafka manages container pause/resume. Depending on the version, `ContainerPausingBackOffHandler` can be configured to avoid holding the consumer thread in a long sleep; you must still check poll intervals and actual pause durations.

## 5. How Does Non-Blocking Retry Work?

Non-blocking retry uses retry topics. When a listener fails:

1. The retry infrastructure catches the exception.
2. The record is published to the retry topic corresponding to the next retry attempt.
3. The record carries the metadata needed to identify the original topic and retry state.
4. The retry topic is consumed by its corresponding listener container.
5. If it continues to fail, the record advances to the next retry topic or to the DLT when attempts are exhausted.
6. The main topic consumer can continue receiving new records.

Spring Kafka supports this pattern through `@RetryableTopic`.

~~~mermaid
flowchart TD
    A["orders topic"] --> B["Main listener"]
    B -->|Failure| C["orders-retry-1000"]
    C --> D["Retry listener"]
    D -->|Failure| E["orders-retry-2000"]
    E --> F["Retry listener"]
    F -->|Failure| G["orders-retry-4000"]
    G --> H["Retry listener"]
    H -->|Attempts exhausted| I["orders.DLT"]
    B -->|Success| J["Complete"]
    D -->|Success| J
    F -->|Success| J
    H -->|Success| J
~~~

Actual retry topic names depend on the naming strategy and application configuration. The diagram merely illustrates retry tiers by wait time.

## 6. When Is Non-Blocking Retry Suitable?

Non-blocking retry is typically suitable when:

- Retry wait times exceed what is reasonable for blocking.
- Downstream systems may take several minutes or longer to recover.
- Subsequent events can continue processing independently.
- Business rules accept delayed record processing and potential reordering.
- You want to isolate retry load from the main topic consumer.
- Multiple time-based backoff tiers are needed.

For instance, an event needs to wait for a partner service to finish syncing data. Retrying after 1 minute, 5 minutes, and 15 minutes makes more sense than keeping a consumer thread waiting continuously.

Non-blocking retry is not an automatic choice for every long error. If later events depend on earlier ones, diverting an old record to a retry topic can violate business ordering.

## 7. Configuring @RetryableTopic

Example listener retrying up to four times with exponential backoff:

~~~java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(
        delay = 1_000,
        multiplier = 2.0,
        maxDelay = 10_000
    ),
    dltTopicSuffix = ".DLT"
)
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service"
)
public void listen(OrderCreated event) {
    billingService.createInvoice(event);
}
~~~

In this example:

- `attempts = "4"` is a maximum of four processing attempts, normally including the initial delivery.
- `delay = 1_000` is the initial wait interval of one second.
- `multiplier = 2.0` doubles the wait interval each step.
- `maxDelay = 10_000` caps the wait interval at ten seconds.
- `dltTopicSuffix = ".DLT"` specifies the DLT name suffix.

Verify annotation semantics against your project's Spring Kafka version when upgrading dependencies. Actual timing also depends on the scheduler, consumer polls, and broker load, rather than an absolute real-time schedule.

### 7.1. Handling the DLT with @DltHandler

You can place a DLT handler in the same class as the listener:

~~~java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(delay = 1_000, multiplier = 2.0)
)
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service"
)
public void listen(OrderCreated event) {
    billingService.createInvoice(event);
}

@DltHandler
public void handleDlt(OrderCreated event) {
    dltService.storeForInvestigation(event);
}
~~~

`@DltHandler` receives records that have exhausted retries per configuration. The DLT handler must capture enough information for investigation and replay; for undeserializable data, configure the consumer/DLT appropriately to retain and read raw bytes.

Do not automatically republish records from the DLT back to the main topic in a continuous loop. Follow a controlled workflow to fix the root cause, inspect the data, and replay deliberately.

### 7.2. Classifying Exceptions for Retry Topics

You can restrict which exception types are retried:

~~~java
@RetryableTopic(
    attempts = "4",
    include = {
        TransientDataAccessException.class,
        TimeoutException.class
    },
    exclude = {
        IllegalArgumentException.class,
        UnsupportedOperationException.class
    },
    backoff = @Backoff(delay = 1_000, multiplier = 2.0)
)
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service"
)
public void listen(OrderCreated event) {
    billingService.createInvoice(event);
}
~~~

Validation errors generally do not resolve with waiting, so they do not need retries. Timeouts or transient database errors can be retried if the operation can be safely re-executed.

If an exception wraps another exception, verify the cause-traversal configuration and classify based on the root cause. Avoid overly broad classification that causes configuration or data errors to retry pointlessly.

## 8. Comparing Blocking and Non-Blocking Retry

| Criterion | Blocking retry | Non-blocking retry |
|---|---|---|
| Mechanism | Error handler redelivers record within container flow | Publishes record to a retry topic |
| Consumer thread | Spends time waiting/retrying | Main topic consumer can move on |
| Wait duration | Good for short delays | Good for long delays |
| Ordering | Preserves partition order better | Can alter ordering |
| Subsequent partitions/records | Subsequent records on partition may be delayed | Can continue processing |
| Infrastructure | Fewer topics | Requires retry topics and a DLT |
| Batch listener | Supported via error handler | Not supported by the retry-topic feature |
| Container transaction | Can be configured compatibly | Incompatible with container transactions |
| Operations | Monitor error handler and retry counts | Monitor multiple topics, lag, and retry schedules |
| Best suited for | Short retries, ordering matters | Long retries, independent events |

## 9. Ordering Is the Deciding Criterion

Kafka guarantees ordering only within each partition of a topic. Blocking retry holds the failed record in the partition's processing stream, so subsequent records are delayed until the failed record succeeds or is recovered.

Example:

~~~text
orders partition 0:
offset 10 -> OrderCreated(order-01)  [failed]
offset 11 -> PaymentCaptured(order-01)
offset 12 -> OrderCompleted(order-01)
~~~

With blocking retry, offsets 11 and 12 must wait for offset 10.

With non-blocking retry, `OrderCreated` is forwarded to a retry topic. The `orders` topic consumer can continue processing `PaymentCaptured` and `OrderCompleted` before `OrderCreated` finishes retrying.

This is only safe if events are independent or business logic can handle late-arriving events. Otherwise, you must:

- Keep blocking retry.
- Use a state machine to validate allowed state transitions.
- Carry sequence/version numbers in events.
- Defer dependent events when prerequisites are incomplete.
- Design consumers capable of detecting and handling out-of-order events.

Using the same key so events land in the same partition does not by itself resolve the reordering introduced by non-blocking retry between the main topic and retry topics.

## 10. Batch Listeners and Transactions

Non-blocking retry topics carry critical limitations: Spring Kafka's retry-topic feature does not support batch listeners and cannot be combined with container transactions as specified by Spring Kafka documentation.

If an endpoint needs to receive `List<ConsumerRecord<K,V>>` or requires listener-container-managed transactions, consider blocking retry with `DefaultErrorHandler`.

If migrating to non-blocking retry, re-evaluate the listener method, transaction boundaries, and ordering requirements. Do not simply add `@RetryableTopic` to an existing batch listener assuming it will work.

Regarding transactions, distinguish between:

- Database transactions protecting database updates.
- Kafka transactions coordinating record publishing and offsets per configuration.
- Non-blocking retry forwarding records across topics, whose semantics are not a single transaction spanning the entire retry chain.

## 11. Configuring a DLT for Blocking Retry

With blocking retry, you can use `DeadLetterPublishingRecoverer`:

~~~java
@Bean
public DeadLetterPublishingRecoverer deadLetterPublishingRecoverer(
        KafkaTemplate<Object, Object> kafkaTemplate) {
    return new DeadLetterPublishingRecoverer(kafkaTemplate);
}

@Bean
public DefaultErrorHandler kafkaErrorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    DefaultErrorHandler handler = new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 2L)
    );

    handler.addNotRetryableExceptions(
        IllegalArgumentException.class
    );

    return handler;
}
~~~

Once retries reach their limit, the recoverer publishes the record to the DLT. The default resolver commonly uses the `.DLT` suffix and preserves the source partition. Therefore, ensure the DLT has enough partitions or configure an appropriate destination resolver.

DLT publishing can fail due to ACLs, missing topics, insufficient partitions, serializer errors, or broker/network issues. Monitor the recoverer and consider a record recovered only when the DLT publish succeeds according to the handler's semantics.

## 12. Retry Topic Topology and Topic Management

Non-blocking retry creates extra topics for wait tiers plus a DLT. With a main topic `commerce.order.created`, the topology may look like:

~~~text
commerce.order.created
commerce.order.created-retry-1000
commerce.order.created-retry-2000
commerce.order.created-retry-4000
commerce.order.created.DLT
~~~

Actual topic names depend on the naming strategy, suffixes, and Spring Kafka version.

When designing the topology, determine:

- Which topics are auto-created and which are platform-managed.
- Partition counts for retry topics and the DLT.
- Replication factor.
- Retention for each retry topic.
- ACLs for producers and consumers.
- Cleanup policy.
- Naming strategy to avoid collisions.
- How to handle increasing the main topic's partition count.

If the resolver preserves source partitions, retry/DLT topics must have matching partitions. Verify the actual configuration and pre-create topics in production when auto-creation is disallowed.

Retry topics need retention long enough for the retry schedule and operational response. Never set retention shorter than the time a record might sit waiting in the retry topology.

## 13. Throughput, Lag, and System Load

Blocking retry reduces consumer time spent on new records while waiting. Non-blocking retry frees the main flow but adds publish/consume traffic on retry topics.

| Metric | Blocking retry | Non-blocking retry |
|---|---|---|
| Main topic consumer lag | May grow when records retry for long durations | Usually lower because failed records are offloaded |
| Broker I/O | Fewer topics and extra publishes | Higher due to retry topic publishes/consumes |
| Consumer thread | May be held during backoff | Dedicated retry consumers process on schedule |
| Downstream load | Retries paced by consumer backoff | Multiple retry consumers can add load if unthrottled |
| Operations | Relatively simple | Requires monitoring a multi-topic topology |

Non-blocking retry does not make errors disappear. It moves the work to another topic stream. If the downstream system remains in an outage, retry topics will accumulate records and require alerting.

Monitor:

- Lag on the main topic and every retry topic.
- Record count in the DLT.
- Age of the oldest record.
- Retry attempt counts.
- Error rates by exception type.
- Processing time per attempt.
- Retry/DLT publish failures.
- Downstream throughput and latency.

## 14. Idempotency During Retries

Both mechanisms can cause a business operation to execute multiple times. A Kafka consumer may redeliver records after failures, rebalances, or before offsets are committed.

Never assume a record is processed strictly once. Design idempotency using an event ID and a unique constraint or inbox table.

Example table:

~~~sql
CREATE TABLE processed_event (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Within the same database transaction:

1. Insert the event ID.
2. If it already exists, skip side effects per policy.
3. If the insert succeeds, execute the business logic.
4. Commit the marker and business changes together.

With non-blocking retry, a record may be processed on the main topic, retry topics, and during DLT replay. The original event ID must be preserved so idempotency works end to end.

## 15. Choosing a Strategy by Scenario

| Scenario | Recommended choice | Reason |
|---|---|---|
| Database timeout for a few seconds | Blocking retry | Short backoff, simple |
| API 503 outage lasting several minutes | Non-blocking retry | Avoids holding the main consumer for long periods |
| Later event depends on earlier event | Blocking retry | Preserves partition stream |
| Events can be processed independently | Non-blocking retry | Main flow continues |
| Listener uses batch mode | Blocking retry | Retry topics do not support batch listeners |
| Listener uses container transactions | Blocking retry | Retry topics are incompatible with container transactions |
| Payload violates schema | DLT/quarantine | Waiting will not fix corrupted bytes or schema |
| HTTP 429 with long Retry-After | Non-blocking or scheduled retry | Avoids blocking consumer threads |
| Widespread invalid credentials/ACL | Stop/alert and fix config | Continuous retries will not fix root config issues |
| Short retries while needing high throughput | Measure load and consider partitioning streams | Blocking may bottleneck partitions |

Do not choose non-blocking solely for higher throughput. If ordering is a business invariant, unblocking the partition can cause data corruption that is much harder to detect than consumer lag.

## 16. Testing Blocking Retry

For blocking retry, tests should confirm:

- The listener is invoked the expected number of times.
- Backoff and retry limits are enforced.
- Non-retryable exceptions are not retried.
- The recoverer runs only after retries are exhausted or the error is classified as non-retryable.
- The DLT receives the expected key/value and metadata.
- Offsets are committed per policy only after successful processing or recovery.

Use `EmbeddedKafka` or Testcontainers to start a real container. Do not invoke the listener method directly and conclude retries work, because retries are coordinated by the listener container and error handler.

## 17. Testing Non-Blocking Retry

For retry topics, test the full topology:

1. Send a record to the main topic.
2. Make the listener intentionally fail.
3. Verify the record is published to the retry topic.
4. Wait until the retry time arrives.
5. Have the listener either succeed or continue failing.
6. Verify the record traverses retry stages per configuration.
7. When attempts are exhausted, verify the record appears in the DLT.
8. Inspect origin, attempt, and exception headers.
9. Verify subsequent events on the main topic can be processed while the earlier record awaits retry.
10. Test duplicates and idempotency.

Retry durations in tests should be short enough to keep test runs fast, while still verifying the wait schedule. Use Awaitility or latches rather than fixed sleeps.

## 18. Common Pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| Record retried too many times | Misunderstood attempts/backoff | Verify attempt count includes the initial attempt |
| Partition stalled | Prolonged blocking retry | Shorten backoff or consider retry topics if ordering allows |
| Events processed out of order | Non-blocking retry let dependent events proceed | Use blocking retry or sequence/state validation |
| Retry topic receives no records | Misconfigured topic/ACL/serializer/destination resolver | Check producer and topic topology |
| DLT publish fails | Missing partitions, ACLs, or topic | Provision topic and configure permissions |
| Retry topic accumulates records | Downstream still failing or retry consumer lacks capacity | Monitor lag, scale carefully, fix root cause |
| Batch listener fails with @RetryableTopic | Retry-topic feature does not support batches | Use blocking retry or redesign listener |
| Transactional listener incompatible | Retry topics do not support container transactions | Use blocking retry matching the transaction model |
| Duplicate side effects | Retries/replays and consumer redelivery | Enforce idempotency with event IDs |
| Tests observe no retries | Calling method directly instead of via container | Use integration tests with listener containers |

## 19. Retry Selection Implementation Workflow

Before implementing, follow these steps in order:

1. Classify errors: transient, validation, serialization, or configuration.
2. Determine maximum retry duration per SLA.
3. Determine whether events have ordering dependencies with subsequent records.
4. Check whether the listener uses batch mode or container transactions.
5. Choose blocking or non-blocking retry.
6. Configure exception classification and attempt counts.
7. Configure the DLT, partitions, retention, and ACLs.
8. Design idempotency for side effects.
9. Test retries, DLT publish failures, replays, and duplicates.
10. Set up alerts for lag, retry rate, and DLT rate.

~~~mermaid
flowchart TD
    A["Record fails processing"] --> B{"Need partition ordering?"}
    B -->|Yes| C["Blocking retry"]
    B -->|No| D{"Need long wait?"}
    D -->|No| C
    D -->|Yes| E{"Batch listener or container transaction?"}
    E -->|Yes| C
    E -->|No| F["Non-blocking retry"]
    C --> G["Bounded retries + backoff"]
    F --> H["Retry topics + backoff"]
    G --> I{"Retries exhausted?"}
    H --> I
    I -->|No| J["Retry"]
    I -->|Yes| K["DLT and replay workflow"]
~~~

## 20. Production Readiness Checklist

- [ ] Classified retryable and non-retryable exceptions?
- [ ] Chosen blocking or non-blocking based on ordering and wait times?
- [ ] Attempt count includes the initial processing attempt?
- [ ] Backoff caps total duration?
- [ ] Listener is idempotent?
- [ ] Are batch listeners or container transactions required?
- [ ] Retry topics have sufficient partitions and retention?
- [ ] DLT has sufficient partitions, ACLs, and replication?
- [ ] Serializers handle failed records and raw bytes?
- [ ] DLT preserves headers for source traceability?
- [ ] Replay has a defined workflow and audit trail?
- [ ] Alerts exist for retry rate, DLT rate, and retry topic lag?
- [ ] Tested ordering when a record is retried?
- [ ] Tested DLT publish failure?
- [ ] Tested duplicate delivery and idempotency?
- [ ] Verified compatibility with the running Spring Kafka version?

## 21. Conclusion

Blocking retry suits transient errors needing quick retries, especially when in-partition ordering matters or listeners use batch mode or container transactions. Non-blocking retry suits longer waits when subsequent events can continue processing independently; Spring Kafka implements this via retry topics and `@RetryableTopic`.

Non-blocking retry unblocks the main topic flow, but changes observable ordering and adds operational complexity due to extra retry topics. Blocking retry is simpler, yet can hold consumer threads and stall partitions. Decide based on ordering, SLAs, wait durations, listener type, transactions, broker load, and idempotency capabilities; then test the entire path from initial receipt through DLT and replay.

