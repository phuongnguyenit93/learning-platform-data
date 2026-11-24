# Confirming That a Record Was Recovered

## 1. Why must recovery be confirmed?

In a Spring Kafka system, when a record enters the error-handling path, the goal is not merely **stopping retries**, but ensuring the record has reached a controllable state: processed successfully, durably written to a dead-letter topic (DLT), or saved in a recovery store that can be queried and replayed.

A failing record can pass through multiple steps:

1. The listener receives the record from the source topic.
2. Listener processing fails; the error handler retries per policy.
3. Once retries are exhausted, the error handler invokes a `ConsumerRecordRecoverer`.
4. The recoverer performs a recovery action, such as sending the record to a DLT.
5. The error handler and container handle the recovery outcome and decide whether to advance the source offset per acknowledgement mode.
6. A system or operator may inspect the DLT, reprocess the record, and verify the business result later.

Each step has its own success criteria. Specifically:

- **Recoverer was invoked** does not mean recovery succeeded.
- **Producer was called to send to the DLT** does not mean the broker confirmed receiving the DLT record.
- **Record was written to the DLT** does not mean the source offset was committed.
- **Source offset was committed** does not mean the DLT record has been resolved by an operator or DLT consumer.

That is why **recovery confirmation** must be designed across multiple layers, preventing the system from silently skipping records whenever the recovery path fails.

## 2. Precisely defining the recovered state

At the `DefaultErrorHandler` layer, a record is considered **recovered** when the recoverer completes normally under the error handler's contract. If the recoverer throws an exception, recovery is not considered complete; the error handler continues handling the failure on subsequent deliveries.

However, **the recoverer returning normally** is only as trustworthy as the recoverer implementation itself. For example:

~~~java
ConsumerRecordRecoverer unsafeRecoverer = (record, error) -> {
    kafkaTemplate.send(
        "orders.DLT",
        record.key(),
        record.value()
    );
    // Returns immediately without observing the async send result.
};
~~~

This snippet illustrates a pitfall: the `KafkaTemplate.send()` callback can fail **after** the recoverer has already returned. Without proper confirmation, the container may treat the record as recovered even though DLT publishing failed.

A reliable recovery contract generally requires:

- The destination is accurately determined and writable.
- Data, headers, and metadata needed for investigation are preserved.
- The recovery action is **confirmed** per chosen guarantees, such as broker acknowledgement or durable database commit.
- If recovery fails, the recoverer must throw an exception so the error handler does not mark the record handled.
- After recovery succeeds, the source offset is handled per the matching ack mode and commit policy.
- Observability exists to distinguish recovered records, commit failures, and subsequent DLT processing.

## 3. Outcome milestones to distinguish

| Milestone | Observable signal | Can conclude | Cannot yet conclude |
|---|---|---|---|
| Listener throws exception | Exception from `@KafkaListener` | This attempt failed | Record will be lost or received by DLT |
| Retries exhausted | `BackOff` attempts finished | Reached recoverer step | Recoverer completed |
| Recoverer returns normally | Error handler treats recoverer as handled | Recovery completed per recoverer contract | Destination is durable if recoverer did not verify I/O |
| DLT send future succeeds | `RecordMetadata` from broker | Producer got send confirmation per `acks` | DLT consumer processed it |
| Source offset commit succeeds | Group's committed offset | Consumer group saved next read position | Business issue is fixed |
| DLT consumer processing succeeds | Business status log/DB | DLT handling step completed per contract | External side effects outside transaction are definitely exactly-once |

A well-run system should emit separate metrics or logs for at least three milestones: **recovery attempt**, **recovery success/failure**, and **source offset advancement**. If a DLT consumer exists, also track **DLT processing success/failure**.

## 4. Flow from DefaultErrorHandler to the recoverer

In a standard record-listener flow, `DefaultErrorHandler` coordinates retries and recovery. A general overview:

~~~mermaid
sequenceDiagram
    participant K as Kafka source topic
    participant C as Listener container
    participant L as Application listener
    participant E as DefaultErrorHandler
    participant R as Recoverer
    participant D as DLT broker

    K-->>C: Poll record offset 42
    C->>L: Process record
    L-->>C: Exception
    C->>E: Handle failed record
    E->>E: BackOff, retry until exhausted
    E->>R: Recover(record, exception)
    R->>D: Publish DLT record
    D-->>R: Ack or send error
    alt DLT publish confirmed
        R-->>E: Return normally
        E-->>C: Record handled
        C->>K: Offset commit per AckMode and policy
    else Recovery failed
        R-->>E: Throw exception
        E-->>C: Not recovered
        C->>C: Redelivery or continue error handling
    end
~~~

Details of offset commits, seek/retain, and transactions depend on Spring Kafka version, listener type, and container setup. The diagram emphasizes the boundary between **recoverer completion** and **source offset commit**.

A business example:

- Source topic: `orders`.
- Group: `billing-service`.
- Failed record: partition 2, offset 42, event ID `evt-93`.
- Listener retried three times without success.
- Recoverer sends the record to topic `orders.DLT`.
- Once the producer confirms send success and the recoverer returns normally, the record can be treated as recovered.
- Container continues processing offset 43 onward per commit policy.
- DLT consumer or operator handles `evt-93` later.

If DLT publishing is not confirmed, the system must preserve the ability to redeliver `orders-2@42` or continue recovery per policy rather than automatically treating the event as safely handed off.

## 5. Default recoverer vs. custom recoverers

### 5.1. ConsumerRecordRecoverer

`ConsumerRecordRecoverer` is the abstraction receiving the record and exception so the application can execute a recovery action:

~~~java
ConsumerRecordRecoverer recoverer = (record, exception) -> {
    log.error(
        "Record failed: topic={}, partition={}, offset={}",
        record.topic(),
        record.partition(),
        record.offset(),
        exception
    );
};
~~~

A logging-only recoverer like this **returns normally** if logging succeeds. Hence the error handler can treat the record as recovered even though no durable copy exists elsewhere. That is only appropriate if business policy allows skipping records after logging.

If records must be preserved for replay, the recoverer needs to write to a DLT, database, object storage, or durable queue and confirm the outcome before returning.

### 5.2. DeadLetterPublishingRecoverer

`DeadLetterPublishingRecoverer` is the dedicated implementation for publishing failed records to a DLT using `KafkaTemplate`. It can attach headers supporting root-cause investigation and source record metadata.

An explicit destination resolver avoids relying on environment naming assumptions:

~~~java
DeadLetterPublishingRecoverer recoverer =
    new DeadLetterPublishingRecoverer(
        kafkaTemplate,
        (record, exception) -> new TopicPartition(
            record.topic() + ".DLT",
            record.partition()
        )
    );
~~~

With that resolver, create the DLT topic with at least enough partitions to map the same partition index as the source topic. That is an **example** convention; applications can choose other topics/partitions using a custom resolver.

## 6. Confirming the DLT send result

### 6.1. Why just calling send is not enough

`KafkaTemplate.send()` is an asynchronous API. Calling send can return a future before the broker has confirmed the record. The actual outcome arrives later, or may fail due to unavailable brokers, authorization, serializers, or timeouts.

If the recoverer marks completion immediately after initiating send, an error window opens:

~~~text
Listener fails -> recoverer calls send(DLT)
                    |
                    v
Recoverer returns normally
                    |
                    v
Container advances source offset
                    |
                    +-- DLT send fails later
                        => Risk of losing the record's replay path.
~~~

Therefore, recovery requiring durability must await results under an appropriate contract or use properly coordinated transactions.

### 6.2. DeadLetterPublishingRecoverer checking the send result

`DeadLetterPublishingRecoverer` supports configuring send-result checks so a failed DLT publish is not treated as successful recovery:

~~~java
DeadLetterPublishingRecoverer recoverer =
    new DeadLetterPublishingRecoverer(
        kafkaTemplate,
        (record, exception) -> new TopicPartition(
            record.topic() + ".DLT",
            record.partition()
        )
    );

recoverer.setFailIfSendResultIsError(true);
recoverer.setWaitForSendResultTimeout(Duration.ofSeconds(10));
~~~

Meaning:

- `setFailIfSendResultIsError(true)` instructs the recoverer to throw an error when the DLT send result indicates failure.
- `setWaitForSendResultTimeout(...)` bounds how long to wait for the send result in versions exposing this API.
- When the recoverer throws an exception, the error handler must not treat the record as successfully recovered.

Timeout details and waiting on futures depend on Spring Kafka version and producer configuration. Wait durations should not be too short relative to `delivery.timeout.ms`, network latency, and normal broker behavior. Even with timeouts, keep a careful distinction: a timeout does not prove the record was never written by the broker.

### 6.3. Broker acknowledgements and producer configuration

To make DLT publish confirmation meaningful for durability, understand Kafka producer `acks`:

| Setting | Meaning of success |
|---|---|
| `acks=0` | Producer does not wait for broker ack; unsuitable when proof of DLT persistence is required |
| `acks=1` | Leader confirmed write per protocol; does not mean other replicas have caught up |
| `acks=all` | Broker confirms per in-sync replicas (ISR), paired with `min.insync.replicas` and replication factor |

Example producer configuration for the recovery path:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000
        request.timeout.ms: 30000
~~~

This is an illustrative configuration. Ensure the DLT topic has matching replication factor and `min.insync.replicas`. `acks=all` does not guarantee end-to-end exactly-once on its own; it raises confirmation guarantees at the producer/broker boundary.

## 7. Example DefaultErrorHandler setup with recovery confirmation

A configuration attaching `DeadLetterPublishingRecoverer` to `DefaultErrorHandler`:

~~~java
@Configuration
public class OrderKafkaRecoveryConfiguration {

    @Bean
    public DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> recoveryKafkaTemplate
    ) {
        DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(
                recoveryKafkaTemplate,
                (record, exception) -> new TopicPartition(
                    record.topic() + ".DLT",
                    record.partition()
                )
            );

        recoverer.setFailIfSendResultIsError(true);
        recoverer.setWaitForSendResultTimeout(Duration.ofSeconds(10));

        FixedBackOff backOff = new FixedBackOff(1_000L, 2L);

        DefaultErrorHandler handler =
            new DefaultErrorHandler(recoverer, backOff);

        handler.setAckAfterHandle(true);
        handler.setResetStateOnRecoveryFailure(true);

        return handler;
    }

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
}
~~~

Key points:

- `FixedBackOff(1_000L, 2L)` allows two retry attempts after the initial attempt, spaced one second apart.
- `DeadLetterPublishingRecoverer` routes failed records to the DLT.
- Send-result verification detects failed DLT publishes.
- `setAckAfterHandle(true)` allows the container to commit offsets for errors handled by the handler in applicable modes. This does not force immediate synchronous commits in every ack mode.
- `setResetStateOnRecoveryFailure(true)` resets BackOff state when the recoverer fails, letting the record go through a fresh retry cycle on the next redelivery.
- The factory must actually be used by the listener; declaring a handler bean without attaching it to the right factory will not change error handling.

Example listener:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "billing-service",
    containerFactory = "orderKafkaListenerContainerFactory"
)
public void onOrder(OrderCreated event) {
    billingService.applyIdempotently(event);
}
~~~

A failing record passes through `DefaultErrorHandler` and the recovery policy. If the DLT publisher fails, the recoverer throws an exception and the record is not considered recovered.

## 8. Confirming recovered is different from committing offsets

### 8.1. Offsets track consumer group progress

Kafka stores committed offsets by group ID, topic, and partition. The committed value is the **next offset to read**.

If `orders-2@42` was processed or recovered, progress might look like:

~~~text
Topic orders, partition 2

...  40  41  42  43  44 ...
            ^
            record 42 failed

After recovery and committing offset 43:
next consumer read continues from position 43
~~~

Committing offset 43 proves the group recorded progress past record 42 for normal subsequent reads. If DLT publishing was not truly durable before commit, the system can lose automatic reprocessing of record 42.

### 8.2. AckMode.RECORD

With a record listener and `AckMode.RECORD`, the container normally commits offsets after the listener completes each record successfully. When a record fails and the error handler recovers it successfully, commit behavior depends on the handler finishing, `ackAfterHandle`, and container mechanics.

Do not conclude "the recoverer returned, so the offset commit definitely succeeded." Offset commits can still fail due to rebalances, unavailable brokers/coordinators, or network errors after recovery finishes.

### 8.3. AckMode.BATCH

With `AckMode.BATCH`, the container normally commits progress after processing records from a poll per policy. When a record fails in the middle of a batch, the error handler can separate already-processed records prior to the failure from those needing retry/recovery.

Never use a single offset across the whole batch. Each topic-partition has its own committed offset and must not advance past unfinished records.

### 8.4. Manual acknowledgement

If the listener uses `AckMode.MANUAL` or `MANUAL_IMMEDIATE`, the application can call `Acknowledgment.acknowledge()` once work completes. However, a record entering the error handler does not automatically become "acknowledged" just because the listener threw an exception.

Understand the container's ack mode policy and how the error handler commits recovered records. Avoid calling acknowledge yourself before the recoverer durably stores the failed record.

## 9. commitRecovered and MANUAL_IMMEDIATE

`DefaultErrorHandler` provides `commitRecovered` to request committing the offset of recovered records in applicable situations. Spring Kafka documentation requires the container to use `AckMode.MANUAL_IMMEDIATE` for this feature.

Example:

~~~java
DefaultErrorHandler handler =
    new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 2L)
    );

handler.setCommitRecovered(true);
~~~

Matching container setup:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        manualRecoveryContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory,
            DefaultErrorHandler errorHandler
        ) {
    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setAckMode(
        ContainerProperties.AckMode.MANUAL_IMMEDIATE
    );
    factory.setCommonErrorHandler(errorHandler);

    return factory;
}
~~~

The listener can acknowledge records normally after successful processing:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "billing-service",
    containerFactory = "manualRecoveryContainerFactory"
)
public void onOrder(
    OrderCreated event,
    Acknowledgment acknowledgment
) {
    billingService.applyIdempotently(event);
    acknowledgment.acknowledge();
}
~~~

When an error causes the listener to throw an exception, `DefaultErrorHandler` coordinates retry/recovery; if the recoverer succeeds and `commitRecovered=true` is properly configured, the handler can commit the recovered record's offset per its semantics. Do not call acknowledge in the listener's error branch before the error handler runs.

Distinguish the two properties:

| Property | Role |
|---|---|
| `ackAfterHandle` | Controls whether the container commits offsets for errors handled by the error handler per container mechanics |
| `commitRecovered` | Instructs the handler to commit the offset of recovered records in supported modes, notably MANUAL_IMMEDIATE |

These two properties do not replace each other. Check Javadoc for your deployed Spring Kafka version, especially with batch listeners, transactions, and async commits.

## 10. Using RetryListener to receive recovered signals

Spring Kafka provides `RetryListener` to observe retry and recovery progress. Common record callbacks:

- `failedDelivery(...)`: a delivery attempt to the listener failed.
- `recovered(...)`: the error handler confirms the recoverer completed per contract.
- `recoveryFailed(...)`: the recoverer threw an exception.

Example:

~~~java
public class RecoveryMetricsListener implements RetryListener {

    private final MeterRegistry meterRegistry;

    public RecoveryMetricsListener(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    @Override
    public void failedDelivery(
        ConsumerRecord<?, ?> record,
        Exception exception,
        int deliveryAttempt
    ) {
        meterRegistry.counter(
            "app.kafka.listener.delivery.failed",
            "topic", record.topic()
        ).increment();
    }

    @Override
    public void recovered(
        ConsumerRecord<?, ?> record,
        Exception exception
    ) {
        meterRegistry.counter(
            "app.kafka.record.recovered",
            "topic", record.topic()
        ).increment();
    }

    @Override
    public void recoveryFailed(
        ConsumerRecord<?, ?> record,
        Exception original,
        Exception failure
    ) {
        meterRegistry.counter(
            "app.kafka.record.recovery.failed",
            "topic", record.topic()
        ).increment();
    }
}
~~~

Registering on the handler:

~~~java
handler.setRetryListeners(
    new RecoveryMetricsListener(meterRegistry)
);
~~~

The `recovered` callback is a recovery signal at the error-handler level. If the recoverer does not check DLT send results, this callback is still not proof the broker wrote the DLT record. Therefore, configure the recoverer so its completion contract reflects durability before relying on the callback.

If the application observes the callback and wants to know whether the source offset actually committed, verify committed offsets or consumer commit callbacks/monitoring. `RetryListener.recovered` does not replace offset commit signals.

## 11. Where does a record go if recovery fails?

When the recoverer throws an exception, `DefaultErrorHandler` does not treat the record as successfully recovered. Under standard setups, the record is returned to the error-handling path on the next delivery, via seek/re-fetch or retain/resubmit.

Example:

~~~text
Listener fails
      |
      v
BackOff exhausted
      |
      v
Recoverer publishes to DLT
      |
      +-- Success -> recovered -> commit per policy
      |
      +-- Failure -> exception -> record not yet recovered
                                         |
                                         v
                                 Redelivery/re-recovery
~~~

In Spring Kafka, `resetStateOnRecoveryFailure` affects the BackOff tracker when the recoverer fails:

- `true` (default behavior in supported versions): resets BackOff; the next delivery can pass through the listener retry cycle again.
- `false`: keeps BackOff exhausted; the next delivery can proceed quickly to the recoverer instead of repeating the whole retry cycle.

Example:

~~~java
handler.setResetStateOnRecoveryFailure(false);
~~~

Choose `false` when the error cannot self-resolve by re-running the listener, whereas the DLT/recovery system may recover after a while. Choose `true` when you want the listener to have another chance to finish business logic in the next cycle.

Do not choose based on "reducing error logs"; choose based on retry cost, side effects, and recoverability. If the listener already produced side effects outside Kafka before failing, re-running requires idempotency.

## 12. DLT timeouts and ambiguous state

A timeout while awaiting the DLT send result can happen after the broker already wrote the record yet the response was lost or arrived too late. Thus, after a timeout there are two possibilities:

1. The DLT record was not written by the broker.
2. The DLT record was written, yet the producer/recoverer did not receive the acknowledgement.

If the error handler retries recovery, the DLT may contain **duplicates**. Do not treat DLT duplicates automatically as a Spring Kafka bug; this is a distributed-systems scenario that must be designed for.

Solutions:

- Keep a stable **event ID** across source topic, retry topics, and DLT.
- Preserve source metadata including original topic, partition, offset, and consumer group if available.
- DLT consumers use unique constraints, inbox tables, or idempotent operations.
- When manual replay is needed, record both origin and attempt history.
- Track DLT publish failures/timeouts separately from source listener failures.

Never use the DLT offset alone as a business event idempotency key. A record republished to the DLT receives a new offset even though its payload and event ID represent the same failure.

## 13. Confirming record origin in the DLT

When a record is sent to the DLT, operators need to know **where it came from and why it failed**. `DeadLetterPublishingRecoverer` can attach headers such as:

- Original topic.
- Original partition.
- Original offset.
- Original consumer group, when corresponding info is available.
- Exception class and message.
- Stack trace or error info per configuration.
- Retry/delivery attempt metadata depending on retry mechanism.

Corresponding constants in Spring Kafka typically reside in `KafkaHeaders`, such as the `DLT_ORIGINAL_*` and `DLT_EXCEPTION_*` groups. Available headers can vary by version; verify against your running dependency.

Example business storage schema for DLT tracking:

~~~json
{
  "eventId": "evt-93",
  "sourceTopic": "orders",
  "sourcePartition": 2,
  "sourceOffset": 42,
  "recoveryDestination": "orders.DLT",
  "status": "PENDING_REVIEW",
  "reason": "DatabaseTimeoutException"
}
~~~

This is merely an example of out-of-band metadata; not a mandatory format emitted by Spring Kafka.

When logging, do not dump full payloads or stack traces containing sensitive data uncontrollably. Event ID, topic/partition/offset, and exception category are usually enough to correlate with a tracing system guarded by proper access control.

## 14. Confirming recovery via logs and metrics

A helpful recovery log should record the **outcome** rather than just "sending to DLT".

Example:

~~~text
RECOVERY_ATTEMPT eventId=evt-93 source=orders-2@42 destination=orders.DLT
RECOVERY_CONFIRMED eventId=evt-93 destination=orders.DLT partition=2 offset=105
SOURCE_OFFSET_COMMITTED group=billing-service source=orders-2 nextOffset=43
~~~

In failure cases:

~~~text
RECOVERY_FAILED eventId=evt-93 source=orders-2@42
failure=TimeoutException result=UNKNOWN
SOURCE_OFFSET_NOT_CONFIRMED group=billing-service source=orders-2
~~~

Do not log `RECOVERY_CONFIRMED` before the recoverer's confirmation mechanism reports success. Do not log `SOURCE_OFFSET_COMMITTED` merely because the handler returned; capture actual commit signals or explicitly note that commit is pending.

Operational metrics table:

| Metric / indicator | Role |
|---|---|
| Listener failed deliveries | How often listener processing failed |
| Retry attempts | Retry volume before recovery |
| Recovery attempts | How often the recoverer was invoked |
| Recovered count | How often the recoverer confirmed completion |
| Recovery failure count | How often the recoverer failed |
| DLT publish latency/error | Latency and reliability of DLT producer sends |
| Consumer committed offset | Durable progress of source group |
| Source consumer lag | Assesses whether failing records stall the group |
| DLT consumer lag | Number of failed records waiting to be handled |
| DLT oldest age | Maximum age of unresolved records |
| DLT replay success/failure | Outcome of subsequent business recovery |

Metric labels should have low cardinality: topic, outcome, and exception category. Do not attach event ID, order ID, or offset to metric labels because time series can grow unboundedly. Detailed identifiers belong in logs or traces.

## 15. Recovery in non-blocking retries

With `@RetryableTopic`, failed records move across retry topics and can reach the DLT when attempts are exhausted. The path differs from `DefaultErrorHandler` handling blocking retries on the source topic.

~~~java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(delay = 2_000L)
)
@KafkaListener(
    topics = "orders",
    groupId = "billing-service"
)
public void onOrder(OrderCreated event) {
    billingService.applyIdempotently(event);
}

@DltHandler
public void onDlt(OrderCreated event) {
    dltReviewService.recordForReview(event);
}
~~~

This example conveys the concept; exact routing and DLT/retry topic settings depend on Spring Kafka version. `@RetryableTopic` is for record listeners and is not directly supported by Spring Kafka for batch listeners.

At least two milestones must be distinguished:

1. **Moving the record into the DLT**: retry infrastructure published the record after exhausting attempts or per policy.
2. **Processing the record from the DLT**: `@DltHandler` or a DLT consumer executed subsequent work.

If `@DltHandler` only logs and returns, the system should not call the business state "resolved". If controlled reprocessing is needed, store state and build an appropriate replay/approval workflow.

In non-blocking retries, also monitor publishing between topics. Timeouts can produce duplicates; retry topic/DLT retention must be long enough for operations and investigation.

## 16. Recovery using a database or system outside Kafka

Not every application uses a DLT. A custom recoverer can persist failed records into a table for operators to reprocess.

General example:

~~~java
public class DatabaseRecoverer implements ConsumerRecordRecoverer {

    private final FailedEventRepository failedEventRepository;

    public DatabaseRecoverer(
        FailedEventRepository failedEventRepository
    ) {
        this.failedEventRepository = failedEventRepository;
    }

    @Override
    public void accept(
        ConsumerRecord<?, ?> record,
        Exception exception
    ) {
        failedEventRepository.saveAndFlush(
            FailedEvent.from(record, exception)
        );
    }
}
~~~

In practice, `saveAndFlush` alone does not guarantee the database transaction committed durably. If the method participates in an outer open transaction, the recoverer can return before commit and roll back later.

Therefore, define transaction boundaries and the point at which recovery counts as durable:

- Write the failed record in an independent transaction that commits successfully before the recoverer returns, or
- Use an explicitly coordinated transaction/outbox mechanism, or
- Accept at-least-once policy and handle duplicates safely if the write and offset commit are not atomic.

If the recoverer cannot write durably, it must signal failure so the source offset does not advance past an unhandled record in a data-losing way.

## 17. Kafka transactions and recovery

In Kafka-to-Kafka flows, Spring Kafka can combine producer transactions with consumer offsets so output records and source offsets participate in a single Kafka transaction. This is another way to bind publishing outputs (including DLTs in some designs) with offset advancement.

With transactional listener containers, error handling typically works with `DefaultAfterRollbackProcessor` or transaction-aware recovery, rather than simply copying a non-transactional `DefaultErrorHandler` setup.

Key points to understand:

- Only Kafka records/offsets participating in the same Kafka transaction commit/abort together.
- Downstream consumers use `isolation.level=read_committed` to avoid reading records from aborted transactions.
- Kafka transactions do not automatically include databases, emails, or REST requests.
- DLT publisher and offset commit must participate in the right transaction if the design requires Kafka-to-Kafka atomicity.
- APIs and transactional recovery constraints differ by version; consult Spring Kafka documentation for your exact version before applying.

Never assume enabling `spring.kafka.producer.transaction-id-prefix` suffices for every recoverer to use an appropriate transaction automatically. Verify producer factories, container transaction managers, recovery processors, and real commit/abort outcomes.

## 18. Recovery succeeded yet offset commit failed

This is a very important scenario:

~~~text
Record orders-2@42 fails
    |
    v
Publish orders.DLT -> broker confirms success
    |
    v
Recoverer returns normally
    |
    v
Commit offset 43 -> FAILED (rebalance/network)
    |
    v
Consumer restarts, re-reads orders-2@42
    |
    v
May publish orders.DLT again
~~~

Although initial recovery succeeded, source progress was never saved. Subsequent redelivery is expected under at-least-once semantics.

Mitigations include:

- Idempotent DLT consumers keyed by event ID or source identifier.
- Saving recovery records under an appropriate unique key.
- Tracking offset commit errors separately from recoverer errors.
- If Kafka-to-Kafka atomicity is required, evaluate transactional recovery.
- Never delete the initial DLT record merely because a duplicate appeared before verifying business completion.

Recovery confirmation and source commit confirmation must remain two separate signals in dashboards and reports.

## 19. Recovery failed yet the DLT already received the record

The reverse scenario can also occur:

~~~text
Recoverer publishes to DLT
    |
    v
Broker writes record
    |
    X  response lost or timed out
    |
    v
Recoverer reports error / unknown status
    |
    v
Retry recovery
    |
    v
DLT may receive duplicate record
~~~

Do not assert a record was lost simply because a future timed out. At the moment of failure, the send status may be **ambiguous**.

When investigating, search by:

- Event ID.
- Original topic/partition/offset.
- Correlation ID.
- Recovery destination.
- Expected send time window.

If the DLT already had the record prior to retry, detect duplicates and handle them idempotently. If the DLT did not have it, retrying supplies the recovery record. Neither path should produce wrong side effects.

## 20. Batch listeners and recovered records

When using a batch listener, an error can sit at a specific index or across the entire batch. Spring Kafka supports `BatchListenerFailedException` to pinpoint the failing element and corresponding `DefaultErrorHandler`/batch retries.

~~~java
@KafkaListener(
    topics = "orders",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void onOrders(
    List<ConsumerRecord<String, OrderCreated>> records
) {
    for (int i = 0; i < records.size(); i++) {
        try {
            billingService.applyIdempotently(records.get(i).value());
        } catch (Exception ex) {
            throw new BatchListenerFailedException(
                "Failed record in batch",
                ex,
                i
            );
        }
    }
}
~~~

When recovering a record inside a batch, know:

- Which elements already succeeded.
- Which element failed and was recovered.
- Which elements remain unprocessed.
- The valid progress offset per topic-partition.
- Whether the batch has atomic side effects or wrote incrementally.

If the failing record is unknown, fallback batch recovery may have to retry the whole batch; records that already applied side effects may be redelivered. Idempotency is crucial.

Non-blocking retry via `@RetryableTopic` does not support batch listeners. Do not use that annotation expecting automatic per-element recovery confirmation in a batch.

## 21. Common mistakes

**Assuming calling the recoverer means success:** the recoverer may throw an exception or launch async I/O that fails later.

**Logging failed records and treating that as safe recovery:** if business requires replay, logs do not replace a DLT or durable failure store.

**Not checking DLT send results:** source offsets can advance before knowing DLT publishing failed.

**Treating the `recovered` callback as offset commit success:** the callback reports recoverer completion, not that the group coordinator saved the offset.

**Acknowledging before durable recovery:** if the process crashes or DLT publish fails, the record may be skipped.

**Not handling ambiguous timeouts:** duplicates can appear when recovery is retried.

**Not distinguishing DLT enqueue from DLT processing:** a record entering the DLT does not mean the business error is fixed.

**Forgetting `commitRecovered`'s `MANUAL_IMMEDIATE` requirement:** the handler may not commit recovered records as expected if ack mode is incompatible.

**Not monitoring `recoveryFailed`:** dashboards counting only listener failures will miss a broken DLT publisher.

**Emitting metrics tagged by event ID:** huge cardinality raises cost and can destabilize metrics backends.

**Not ensuring the DLT has enough partitions:** if the resolver picks the same source partition index, the DLT needs matching partitions.

**Retrying endlessly when the DLT continuously fails:** poison records can stall partitions, inflate lag, and block progress. Fix root causes, classify exceptions, and configure alerts.

## 22. Procedure to investigate a record with uncertain recovery status

When logs say "Recovery started" yet the record is absent from the DLT or source lag rises, trace milestone by milestone:

1. Verify the exact group ID, source topic, partition, offset, and event ID.
2. Check the original listener exception and retry count.
3. Identify the error handler/recoverer actually attached to the listener container.
4. Confirm the recoverer was invoked; record any exception if the recoverer failed.
5. If using a DLT publisher, check destination topic/partition, ACLs, serializers, and producer settings.
6. Inspect the future/send result or confirmation the recoverer waited on.
7. On timeout, search the DLT by source metadata/event ID before concluding it was not written.
8. Check whether the `recovered` or `recoveryFailed` callback fired.
9. Check the committed source offset; distinguish recovery success from commit failure.
10. Check DLT consumer lag and DLT processing status.
11. Check for duplicates and idempotency if recovery was retried.
12. After fixing the error, confirm recovery, offset progress, and downstream DLT processing work properly.

Example investigation output:

~~~text
Source record: orders-2@42
Listener result: exhausted after configured retries
Recovery attempt: orders.DLT
DLT producer result: success at orders.DLT-2@105
Recoverer result: success
Source group committed offset: 43
DLT processing: pending manual review
~~~

This is a case where the record was recovered **to the DLT**, the source offset was recorded, yet the business failure still awaits resolution.

## 23. Test scenarios for recovery confirmation

To prove the design works properly, use an isolated test Kafka cluster, provisioned source topic and DLT, and a test consumer group.

### 23.1. Successful recovery

1. Send a record with a specific event ID.
2. Have the listener always throw a retryable exception.
3. Wait through the configured retry count.
4. Confirm the recoverer publishes the record to the DLT.
5. Confirm the producer receives a successful send result.
6. Confirm `RetryListener.recovered` is called.
7. Confirm the source committed offset advances past the failing record per ack mode.
8. Confirm the DLT record preserves required source metadata.

### 23.2. Recovery publisher failure

1. Configure an unwritable DLT topic in the test environment or use a controlled failing producer.
2. Enable `setFailIfSendResultIsError(true)`.
3. Have the listener fail into the recovery phase.
4. Confirm the recoverer reports an error.
5. Confirm the `recoveryFailed` callback is called.
6. Confirm the source record is not skipped via an improper commit.
7. Restore producer/DLT, let the system retry recovery, and observe the outcome.

### 23.3. DLT publish succeeds yet source commit fails

1. Have the recoverer publish to the DLT successfully.
2. Induce a controlled source offset commit failure.
3. Restart the consumer with the same group ID.
4. Confirm the source record can be redelivered.
5. Confirm idempotency handles the DLT record if published a second time.
6. Confirm metrics/logs distinguish recovered from offset commit failed.

### 23.4. Timeouts and duplicates

1. Simulate a case where the producer misses confirmation before timeout while the broker may still have written.
2. Let recovery retry.
3. Locate DLT records sharing the same event ID and original topic/partition/offset.
4. Confirm the DLT consumer/inbox does not duplicate side effects.
5. Reconcile recovery attempt counts against actual DLT records present.

Do not merely assert listener invocation counts. Recovery tests must observe actual records in the DLT, source commit state, recoverer exceptions, and deduplication behavior.

## 24. Production operating principles

- Define "recovered" strictly around the **recovery destination**, not merely invoking the recoverer.
- For DLTs, configure the recoverer to check send results and use producer `acks` matching durability requirements.
- Ensure DLT topics, partitions, replication, ACLs, and serializers are provisioned.
- Separate metrics/logs for recovery attempts, recovery success, recovery failure, and source offset commits.
- Never treat timeouts as proof a record was not written; design idempotent DLT consumers.
- Use `RetryListener` to observe `recovered` and `recoveryFailed`.
- Understand `ackAfterHandle`, `commitRecovered`, and acknowledgement mode before changing commit behavior.
- With `commitRecovered=true`, verify the `MANUAL_IMMEDIATE` requirement in your Spring Kafka version.
- Preserve event IDs and original metadata for lookup, replay, and deduplication.
- Distinguish DLT publish success from a DLT handler having resolved the business error.
- If using Kafka transactions, ensure recovery records and source offsets truly participate in the transaction per design.
- For batch listeners, manage partial success, per-partition offsets, and recovery via supported batch mechanisms.
- Test failures at boundaries between the listener, recoverer, Kafka producer, and source offset commits.

**Confirming that a record was recovered** means having evidence that the recovery action completed under a reliable contract while knowing clearly whether source offset progress has been persisted. Recovery into a DLT can succeed while the business issue remains unresolved; offset commits can also fail even after the DLT received the record. By separating these milestones and designing idempotency for ambiguous outcomes, a Spring Kafka system avoids dropping events and retains sufficient data for controlled recovery.
