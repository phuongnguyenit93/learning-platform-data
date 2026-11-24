# Retaining and Resubmitting Records

## 1. Meaning of Retain and Resubmit in DefaultErrorHandler

In Spring Kafka, `DefaultErrorHandler` handles exceptions thrown by record listeners. After a failed processing attempt, the error handler decides which records need retrying, when to retry them, and when to transition to recovery, such as publishing to a dead-letter topic (DLT).

The traditional approach is to seek the consumer back to the failed record's offset so Kafka re-fetches that record along with subsequent unprocessed records. Starting in Spring Kafka 2.9, you can configure `DefaultErrorHandler` to use retain-and-resubmit mode via `setSeekAfterError(false)`.

With this mode:

- The container holds unprocessed records in memory.
- The error handler executes retries per the configured backoff.
- Once the error handler finishes, the container re-delivers the unprocessed records to the listener.
- The container performs one poll while the consumer is paused to maintain group activity and heartbeats per Kafka client mechanics.
- The container does not seek the partition back to the failed offset to re-fetch those records during this retry cycle.

Distinguish two concepts:

- **Retain**: holding unprocessed records in the listener container's memory.
- **Resubmit**: passing the retained records back to the listener for continued processing.

Resubmitting here does not mean a producer re-publishes records to Kafka, nor does the broker create new copies. It is a container mechanism for re-delivering records that were already fetched but not yet successfully processed.

This mode is useful when you want to reduce seek operations and keep the already-fetched record set intact during retries. However, because records stay in memory, pay attention to batch size, retry duration, memory usage, and behavior when consumers stop or rebalance.

## 2. Two Ways of Handling Records After an Error

### 2.1. Seek and Re-Fetch (Default)

By default, when a listener fails, the container/error handler seeks partitions back to the offset that needs reprocessing. On the next poll, the Kafka consumer re-fetches the failed record and unprocessed records after it.

For example, one poll returns records at offsets 20, 21, and 22 on the same partition. The listener processes 20 successfully but fails on 21:

~~~text
Poll:
  offset 20
  offset 21  <-- listener throws exception
  offset 22

Error handling:
  commit processed progress before failed record (if appropriate for ack mode)
  seek partition to offset 21

Next poll:
  re-fetch 21, 22
~~~

This approach relies on Kafka offsets to re-read data. Unprocessed records are served again from the broker's log, provided they are still within retention and the partition remains readable.

### 2.2. Retain and Resubmit

When `seekAfterError=false` is configured, the container does not seek the partition to re-fetch the remainder. Instead, it retains the unprocessed records and resubmits them after the error handler completes.

~~~text
Poll:
  offset 20
  offset 21  <-- listener throws exception
  offset 22

Retain:
  retain records 21 and 22 in container

Retry/backoff:
  error handler processes error for 21

Resubmit:
  listener receives 21 again and unprocessed record 22
~~~

Record 20, already processed successfully, can be committed per the acknowledgment mode. The unprocessed portion is held to continue rather than forcing the consumer to seek and re-fetch from the broker.

Within a batch, the retained records list may include the failed record and subsequent unprocessed records. With a record listener, the container can hold the record needing retry along with the remaining unprocessed records from that poll.

### 2.3. Quick Comparison

| Criterion | Seek and Re-Fetch | Retain and Resubmit |
|---|---|---|
| How records are re-acquired | Seek partition and poll/fetch from broker | Keep fetched records in container memory |
| Seek operation | Yes | No seek to reprocess retained portion |
| Record source on next attempt | Kafka log | Record list held by the container |
| Container memory | Does not need to retain the full remainder beyond current processing | Must retain unprocessed records |
| Broker fetch impact | Re-fetches after seek | Avoids re-fetching retained portion during retry |
| Behavior after process restart | Re-fetches from committed offset | Retained records in RAM are lost; Kafka may redeliver from committed offset |
| Version | Traditional default behavior | Supported since Spring Kafka 2.9 |

Both modes share the same goal: continue processing incomplete records without committing past unprocessed progress. The main difference is how the container obtains records for the next attempt.

## 3. Configuring DefaultErrorHandler for Retain and Resubmit

### 3.1. Java Configuration

You can create a `DefaultErrorHandler`, configure backoff, and disable seek-after-error:

~~~java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    public DefaultErrorHandler defaultErrorHandler() {
        BackOff backOff = new FixedBackOff(1_000L, 2L);

        DefaultErrorHandler errorHandler =
            new DefaultErrorHandler(backOff);

        errorHandler.setSeekAfterError(false);

        return errorHandler;
    }

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            kafkaListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory,
                DefaultErrorHandler defaultErrorHandler
            ) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(defaultErrorHandler);

        return factory;
    }
}
~~~

In this example:

- `FixedBackOff(1_000L, 2L)` waits one second between retries and allows two retries after the initial invocation.
- `setSeekAfterError(false)` instructs the container to retain unprocessed records and resubmit them.
- `setCommonErrorHandler(...)` attaches the handler to the listener container factory.

Attempt counts and backoff values are illustrative only. Choose them based on error type, SLAs, and downstream recovery times.

### 3.2. Sharing the Error Handler Bean Across Multiple Factories

If an application has multiple listener container factories, attach the error handler to each factory that should use retain mode. Declaring a `DefaultErrorHandler` bean does not automatically ensure every custom factory uses it.

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, PaymentEvent>
        paymentKafkaListenerContainerFactory(
            ConsumerFactory<String, PaymentEvent> paymentConsumerFactory,
            DefaultErrorHandler defaultErrorHandler
        ) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, PaymentEvent>();

    factory.setConsumerFactory(paymentConsumerFactory);
    factory.setCommonErrorHandler(defaultErrorHandler);

    return factory;
}
~~~

If each factory needs a different retry policy, create a dedicated handler for each workload type. For example, a payment listener may need a longer backoff than a telemetry listener; sharing a single handler can make independent policy tuning difficult.

### 3.3. Checking Version Support

`setSeekAfterError(false)` is supported from Spring Kafka 2.9 onward. If the application uses an older version, this API may not exist. Check the actual Spring Kafka version in your dependency tree and its corresponding Javadoc.

Spring Boot manages Spring Kafka and Kafka client versions according to each release's dependency management. Do not upgrade a single library independently while ignoring Boot's compatibility matrix.

## 4. Retry Flow During Retain and Resubmit

### 4.1. A Record Listener Encounters an Error

Suppose a consumer polls several records and the listener processes them one by one. Record at offset 31 hits a transient exception:

~~~mermaid
sequenceDiagram
    participant K as Kafka broker
    participant C as Listener container
    participant L as Listener
    participant E as DefaultErrorHandler

    K-->>C: Poll records 30, 31, 32
    C->>L: Process record 30
    L-->>C: Success
    C->>L: Process record 31
    L-->>C: Exception
    C->>E: Handle failure at offset 31
    E->>E: Apply BackOff and retry policy
    E-->>C: Return with unprocessed records retained
    C->>K: Paused poll to maintain group activity
    C->>L: Resubmit record 31
    L-->>C: Success
    C->>L: Process record 32
    L-->>C: Success
    C->>K: Commit eligible offsets
~~~

The diagram shows the high-level flow. Exact listener invocation counts, commit timing, and how the handler executes recovery depend on ack mode, listener type, BackOff, and container configuration.

### 4.2. Records Before the Failed Record

If record 30 finished processing successfully before record 31 failed, the container can commit the offset representing progress past record 30, per the active acknowledgment mode and commit mechanism.

Do not commit an offset past record 31 while that record has not been processed or recovered per policy. Committing past a failed record can cause the consumer to skip it after a restart.

### 4.3. Records After the Failed Record

Record 32 was not yet passed to the listener in the example above. It belongs to the unprocessed portion and is retained alongside record 31 for resubmission via container mechanics.

This matters for per-partition ordering. The container must continue from the failed record and the remainder in the order received by the consumer, rather than processing later records and committing offsets past incomplete ones.

With multiple partitions, each partition tracks its own progress. Never infer one partition's offset from another partition's offset.

## 5. BackOff Determines the Retry Wait Interval

Retain and resubmit only decides how records are held and redelivered. BackOff determines when retries occur.

### 5.1. FixedBackOff

`FixedBackOff` uses a constant wait between attempts:

~~~java
BackOff backOff = new FixedBackOff(2_000L, 3L);

DefaultErrorHandler handler =
    new DefaultErrorHandler(backOff);

handler.setSeekAfterError(false);
~~~

In this example, retries are spaced two seconds apart, with three retries after the initial invocation. Once retries are exhausted, the handler moves to recovery using the configured recoverer or default behavior.

Do not interpret the retry count as total listener invocations. Distinguish the initial invocation from additional retries per BackOff semantics.

### 5.2. ExponentialBackOff

For downstreams with variable recovery times, exponential backoff gradually increases the wait interval:

~~~java
ExponentialBackOff backOff = new ExponentialBackOff(
    1_000L,
    2.0
);

backOff.setMaxInterval(10_000L);
backOff.setMaxElapsedTime(60_000L);

DefaultErrorHandler handler =
    new DefaultErrorHandler(backOff);

handler.setSeekAfterError(false);
~~~

The example starts with a one-second wait, multiplies by 2, caps each wait at ten seconds, and bounds total elapsed time per configuration. Verify `ExponentialBackOff` APIs and defaults against the Spring Framework version used in your project.

Backoff prevents bursting retries into a failing service. However, long waits also keep records in flight longer and can increase consumer lag.

### 5.3. BackOff Is Not a Listener Timeout

BackOff only controls wait time between attempts. It does not limit how long a listener takes to process a single record.

If a listener calls a database or HTTP service that can hang indefinitely, set a dedicated timeout for that call. If the listener takes too long between polls, the consumer can also breach `max.poll.interval.ms` and trigger a rebalance.

## 6. Recovery After Retries Are Exhausted

When BackOff signals that attempts are exhausted, `DefaultErrorHandler` can invoke a recoverer to handle the unrecoverable record. A common choice is publishing the record to a DLT.

### 6.1. DeadLetterPublishingRecoverer

~~~java
@Bean
public DefaultErrorHandler defaultErrorHandler(
    KafkaTemplate<Object, Object> kafkaTemplate
) {
    DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(kafkaTemplate);

    FixedBackOff backOff = new FixedBackOff(1_000L, 3L);

    DefaultErrorHandler handler =
        new DefaultErrorHandler(recoverer, backOff);

    handler.setSeekAfterError(false);

    return handler;
}
~~~

The default recoverer can route records to a DLT based on topic naming conventions, typically appending a `-dlt` suffix, and use the corresponding partition when default configuration applies. Ensure the DLT topic exists, has matching partitions, and that the producer's serializer can handle the payload.

When a record is recovered successfully, the handler can finish error processing and the container proceeds to the next record per commit policy. If DLT publishing fails, inspect handler/recoverer behavior to avoid treating a record as recovered when the DLT write did not succeed.

### 6.2. Custom Recoverer

You can create a recoverer to log failures or route records according to business rules:

~~~java
ConsumerRecordRecoverer recoverer = (record, exception) -> {
    log.error(
        "Recovering record topic={}, partition={}, offset={}",
        record.topic(),
        record.partition(),
        record.offset(),
        exception
    );

    // Can publish to DLT or persist metadata in recovery system.
};

DefaultErrorHandler handler =
    new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 2L)
    );

handler.setSeekAfterError(false);
~~~

A recoverer needs clear semantics: when a record counts as recovered, when to throw an exception to force recovery retry, and when to let the container advance offsets. Do not merely log an error and treat the record as safely stored if the business requires a DLT or replay pipeline.

### 6.3. Classifying Retryable and Non-Retryable Errors

Not every error should be retried. For example:

- Database timeouts or transient connection errors can be retried.
- HTTP 503 can be retried with backoff.
- Malformed payloads or missing required fields generally cannot be fixed by retrying.
- Authorization errors typically require fixing configuration or credentials.
- Unique-constraint violations might be legitimate duplicates or business errors, requiring use-case-specific classification.

`DefaultErrorHandler` lets you mark non-retryable exceptions using classification APIs such as `addNotRetryableExceptions(...)` or corresponding retryable-exception settings.

~~~java
DefaultErrorHandler handler =
    new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 2L)
    );

handler.addNotRetryableExceptions(
    IllegalArgumentException.class,
    DeserializationException.class
);

handler.setSeekAfterError(false);
~~~

The exception list is only an example. Ensure the actual exception wrapped or thrown by Spring matches the types classified by the handler; otherwise, an error meant to skip retries might still enter the retry path.

## 7. Retain and Resubmit with Record Listeners

A record listener receives each record from a poll individually. When a record fails, the error handler processes that error. With `seekAfterError=false`, the container retains the failed record and unprocessed records from the poll for redelivery.

Example:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "billing-service"
)
public void onOrder(OrderCreated event) {
    billingService.process(event);
}
~~~

If the listener processes offset 40 successfully and fails on offset 41:

- Offset 40 can be committed per `AckMode.RECORD`.
- Offset 41 is retained for retry.
- Unprocessed records after 41 are also retained.
- Once retry succeeds or recovery finishes, the container resumes processing the remainder.

If errors persist on a single record, that record can slow down subsequent records on the same partition. Backoff and recovery policies must be bounded so one poison record does not stall the stream for too long.

## 8. Retain and Resubmit with Batch Listeners

### 8.1. Batch Listeners Receive Multiple Records

A batch listener receives a list of records from a poll:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "billing-service"
)
public void onOrders(List<OrderCreated> events) {
    billingService.processBatch(events);
}
~~~

If the batch listener throws an exception, the handler needs to know which record caused the error to distinguish the processed portion from the portion needing retry. With Spring Kafka, you can throw `BatchListenerFailedException` specifying the failed record/index.

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "billing-service"
)
public void onOrders(
    List<OrderCreated> events,
    Acknowledgment acknowledgment
) {
    for (int i = 0; i < events.size(); i++) {
        try {
            billingService.process(events.get(i));
        } catch (Exception ex) {
            throw new BatchListenerFailedException(
                "Cannot process batch record at index " + i,
                ex,
                i
            );
        }
    }

    acknowledgment.acknowledge();
}
~~~

This snippet illustrates the concept of identifying the failed record; the `BatchListenerFailedException` constructor signature must match your Spring Kafka version. For batch listeners, how the handler determines committed offsets and the retained slice depends on the failure metadata provided by the listener.

### 8.2. If the Failed Record Is Not Identified

If a batch listener throws a generic exception without specifying the failed record, the handler may have to reprocess the entire batch using fallback behavior. This can cause previously processed records to be invoked again.

Therefore, when iterating item-by-item in a batch, clearly pinpoint the failing record/index. If the batch is processed atomically at the database layer, throwing a batch-wide exception can be reasonable, provided the database transaction rolls back all corresponding side effects.

### 8.3. Retained Batches and Memory

In retain mode, the container must hold unprocessed records. With large batches or large payloads, memory usage can climb significantly during retries.

Control:

- `max.poll.records`.
- Record and batch sizes.
- Number of partitions assigned to a consumer.
- Backoff duration and retry count.
- Number of concurrent consumers encountering errors simultaneously.
- Heap and garbage collection.

Do not set `max.poll.records` too high when payloads are large and downstreams experience prolonged outages. Retaining reduces re-fetches, at the cost of holding records in memory until retry/recovery finishes.

## 9. Paused Poll and Maintaining Group Membership

When using retain and resubmit, the container may need to keep records in memory during backoff. Meanwhile, it pauses the consumer and executes a poll so the consumer stays active in the group.

Goals of a paused poll:

- Continue driving Kafka client group coordination/heartbeat activity.
- Reduce the risk of the consumer being evicted from the group merely for waiting on retries.
- Keep partition assignments while the container finishes error handling.
- Avoid fetching unnecessary new data while retained records remain unprocessed.

A paused poll does not mean the listener continues processing new records while paused. It serves the consumer lifecycle and group membership.

If retry and listener processing times are excessive, you still must check `max.poll.interval.ms`, session/heartbeat settings, and group protocol version. A paused poll helps the container keep consumer activity alive as designed, but is not a license for a listener to block indefinitely.

## 10. Relationship to Acknowledgment Modes and Commits

Retain/resubmit does not replace acknowledgment modes. Ack mode still decides when the container commits offsets after records are processed or recovered.

Common modes:

| AckMode | General Effect |
|---|---|
| `RECORD` | Commits after each listener record succeeds |
| `BATCH` | Commits after a polled batch finishes successfully |
| `MANUAL` | Listener marks acknowledgment; container commits per manual semantics |
| `MANUAL_IMMEDIATE` | Can commit immediately when acknowledged on the consumer thread |

When a record fails, the container should not commit past that record until it is processed or recovered successfully. If an earlier record on the same partition already completed, corresponding progress can be committed per ack mode.

When a recoverer handles a record successfully, commit behavior also depends on error handler properties such as `ackAfterHandle`, `commitRecovered`, and ack mode. In particular, `commitRecovered` has specific requirements around manual immediate acknowledgment in supported versions. Check the Javadoc for your running version before enabling it.

Never assume `setSeekAfterError(false)` decides offset commits by itself. That property only chooses how unprocessed records are held and redelivered.

## 11. Retain/Resubmit and Rebalances

### 11.1. Consumer Rebalanced During Retry

While records sit in memory and the handler waits on backoff, the group may rebalance due to other consumers joining/leaving, partition changes, or consumer disconnects.

When partitions are revoked, the container must follow rebalance procedures and partition ownership rules. Uncommitted retained records may need to be reprocessed from Kafka when the partition moves to another consumer or when the consumer restarts.

Never treat in-memory records as durable storage. If a process crashes, memory is lost; the committed offset is the basis for a consumer to resume progress.

### 11.2. Do Not Process Side Effects on Background Threads After Partition Transfer

If a listener offloads tasks to an executor, a task may still be running when a partition is revoked. A new consumer may receive the same record while the old task is still writing to the database.

You must:

- Track tasks per topic-partition.
- Stop accepting new tasks when a partition is revoked.
- Wait for or cancel in-flight tasks within a deadline.
- Avoid committing offsets past incomplete tasks.
- Use idempotency for side effects to withstand redelivery.

Retain/resubmit only manages records inside the listener container; it does not automatically manage application-created executors or tasks.

## 12. Retries, Delivery Attempts, and Observability

To track how many times a record has been attempted, Spring Kafka provides a delivery-attempt header in supported versions. You can enable the delivery-attempt header on container properties and read it in the listener or DLT.

Configuration example:

~~~java
factory.getContainerProperties()
    .setDeliveryAttemptHeader(true);
~~~

You can then read the corresponding header from the message or record using your version's API. Delivery attempt aids diagnostics, but should not be used as an event ID or idempotency key. A redelivery after a process restart may have a different attempt history than in-memory retries.

Recommended details to record:

- Topic, partition, offset.
- Key and event ID.
- Consumer group and client/member ID if available.
- Exception class and root cause.
- Delivery attempt.
- Processing time and backoff time.
- Recovery/DLT outcome.
- Committed offset after handling.

Useful metrics:

| Metric | Meaning |
|---|---|
| Listener failure count | Number of times the listener threw an exception |
| Retry attempt count | Number of retries |
| Recovery count | Number of records processed by the recoverer |
| DLT publish success/error | Outcome of sending failed records to the DLT |
| Retained record count/age | Count and wait time of retained records if instrumented by the application |
| Consumer lag | Group lag |
| Listener duration | Processing time for a record/batch |
| Heap/GC | Memory pressure from retaining records |

Exact metric names depend on Spring Kafka, the Kafka client, and your metrics system. Not every version exposes a built-in metric for retained record count; custom instrumentation may be needed.

## 13. Scenarios Where Retain and Resubmit Makes Sense

### 13.1. Reducing Seeks in the Retry Flow

When a consumer has already fetched a batch and only one record fails, retaining lets the container hold the unprocessed slice and redeliver it without seeking partitions. This helps when you want to continue from already-fetched data and cut down re-fetch operations for the remaining records.

### 13.2. Batch Processing with Expensive Fetches

If records carry large payloads or re-fetching batches creates significant load, retaining can avoid an extra fetch round-trip during retries. However, weigh that benefit against heap usage for holding payloads and how long records sit in memory.

### 13.3. Keeping Retry Control Inside the Container

Retain/resubmit keeps retry execution inside the listener container with BackOff and the error handler. It avoids needing a producer to re-publish records or a separate retry topic just to immediately retry already-fetched records.

If you need long delays, multi-hour retries, or separation of retry workloads from the main partition, retry topics may fit better. Retain is not a durable long-term retry store.

## 14. When to Consider Seek or Retry Topics Instead?

Retain/resubmit is not the best choice for every scenario.

| Scenario | Direction to Consider |
|---|---|
| Short retries, records already fetched and want to keep remainder | Retain/resubmit |
| Want default behavior, re-fetch from Kafka | Seek and re-fetch |
| Retries need long delays, avoid holding records in heap | Retry topic or a persistent retry mechanism |
| Need to isolate error stream from main partition | DLT or retry topic |
| Large payloads, many records failing simultaneously | Evaluate memory before retaining |
| Listener processes batches atomically | Transactional batch retry/recovery |
| Consumers rebalance or restart frequently | Investigate group instability and replayability from committed offsets |

Retry topics allow the main partition to continue with later records, though processing order can shift. Retain generally keeps the poll's unprocessed records and continues on the current stream; it does not create a durable retry schedule outside Kafka.

## 15. Common Pitfalls with Retain and Resubmit

**Assuming records are re-published:** resubmitting means the container re-delivers records held in memory, not a producer sending a new record to Kafka.

**Forgetting `setSeekAfterError(false)`:** the handler keeps default seek behavior. Merely declaring `DefaultErrorHandler` does not turn on retain mode.

**Using too old a Spring Kafka version:** retain/resubmit APIs do not exist in versions prior to 2.9.

**Ignoring memory:** payloads and batches stay in the container during retries, which can cause heap pressure with large batches or multiple failing listeners.

**Infinite retries:** a poison record stalls the partition, driving up consumer lag and delaying subsequent records.

**Not classifying exceptions:** schema or unrecoverable data errors get retried like transient errors.

**Assuming restarts preserve retained records:** retained records live in memory and are lost when the process stops. Kafka recovers from committed offsets, so uncommitted records may be redelivered.

**Committing offsets before processing/recovery:** loses the chance to process records if the process fails after committing.

**Letting background tasks run after revocation:** can cause concurrent side effects when a partition moves to another consumer.

**Treating recovery logging as durable recovery:** merely logging errors is insufficient when the business requires a DLT, archival, or replay.

## 16. Investigation Procedure When a Record Is Resubmitted Repeatedly

When a record fails repeatedly and keeps getting redelivered:

1. Record topic, partition, offset, key, and event ID.
2. Identify when the listener first received the record and the exception/root cause.
3. Check whether `seekAfterError` is set to false on the right container factory.
4. Determine whether the record is retained in memory or re-fetched after a seek.
5. Check BackOff, retry count, and exception classification.
6. Check whether the error handler routes the record to the recoverer/DLT after exhausting retries.
7. Check committed offsets to see whether the group advanced past the failed record.
8. Monitor consumer lag, heap, GC, and listener execution time.
9. Check whether rebalances or restarts occurred during retries.
10. If side effects could have succeeded before the exception, verify listener idempotency to avoid duplicates.

When a record is resubmitted, logs can show the same topic/partition/offset multiple times. That is a sign of retrying the same record, not proof by itself that the producer published duplicates.

## 17. Testing Retain and Resubmit

Test using a Kafka test broker or dedicated integration environment with test topics and group IDs.

### 17.1. Testing a Record Listener

1. Create a single-partition topic and send three records with consecutive offsets.
2. Configure `DefaultErrorHandler` with a short `FixedBackOff` and `setSeekAfterError(false)`.
3. Have the listener process the first record successfully.
4. Have the second record throw an exception on the first attempt and succeed on retry.
5. Record the sequence of topic/partition/offset received by the listener.
6. Verify the failed record is redelivered and subsequent unprocessed records proceed.
7. Check committed offsets after all records complete.

### 17.2. Comparing with Seek Mode

Run the same scenario with `seekAfterError(true)` or the default:

1. Record poll/fetch counts and record ordering.
2. Observe partition seeks in logs/debug output.
3. Compare container record retention against re-fetching from the broker.
4. Keep backoff, batch size, concurrency, and load identical for a meaningful comparison.

### 17.3. Testing a Batch Listener

1. Send a multi-record batch.
2. Have the listener throw `BatchListenerFailedException` at a specific index.
3. Verify records before that index are processed/committed per policy.
4. Verify the failed record and unprocessed portion are retried/resubmitted.
5. Verify recovery when retries are exhausted.
6. Verify a recovered record does not advance offsets past other unprocessed records.

### 17.4. Testing Restart While Retained

1. Produce a failing record and configure a sufficiently long backoff.
2. While the container is waiting to retry, stop the process in a controlled way.
3. Restart with the same group ID.
4. Verify the uncommitted record is re-fetched from Kafka.
5. Verify idempotent side effects are not duplicated.

This test demonstrates that retained records are purely in-memory state. Committed offsets remain the durable progress stored by Kafka for the group.

## 18. Production Deployment Principles

- Use Spring Kafka 2.9 or later if `setSeekAfterError(false)` is needed.
- Attach the right `DefaultErrorHandler` to the listener container factory actually used by the listener.
- Choose a bounded BackOff and classify retryable/non-retryable exceptions.
- Use retain/resubmit when you want to keep fetched records in memory and redeliver via the container.
- Keep `max.poll.records` and payload sizes compatible with heap capacity.
- Monitor retries, recovery, DLT, consumer lag, listener duration, and memory.
- Never treat retained records as durable storage; process restarts wipe in-memory retained state.
- Let the container commit offsets after listener/recovery completion per acknowledgment mode.
- Protect side effects with event IDs, an inbox table, or idempotent operations.
- Use retry topics or DLTs when long retry schedules, workload isolation, or independent replay pipelines are needed.
- Test listener failures, recoverer failures, rebalances, and restarts before broad rollout.

Retain and resubmit lets `DefaultErrorHandler` keep unprocessed records inside the listener container and redeliver them after retries without seeking partitions to re-fetch that slice. This mechanism keeps retry control directly in the container, though it depends on memory and consumer lifecycle. Coordinate BackOff, recovery, acknowledgment modes, idempotency, and monitoring so failing records do not stall partitions or cause duplicate side effects.
