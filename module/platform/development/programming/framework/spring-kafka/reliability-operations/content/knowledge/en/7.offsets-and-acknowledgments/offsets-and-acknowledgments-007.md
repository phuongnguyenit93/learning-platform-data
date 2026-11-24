# AckMode MANUAL_IMMEDIATE

In Spring Kafka, `AckMode` determines how the listener container acknowledges offsets after processing records. With `MANUAL_IMMEDIATE`, the listener explicitly calls `Acknowledgment.acknowledge()` to ask the container to commit the offset immediately at the call site. When the call executes on the listener's consumer thread, the container commits right away instead of waiting for the rest of the `poll()` batch as some other modes do.

This mode is useful when an application needs explicit control over when a record is considered finished. For example, a consumer acknowledges only after validating data and persisting business results successfully. However, `MANUAL_IMMEDIATE` does not automatically create exactly-once semantics, does not automatically retry, and does not merge a database and Kafka into one shared transaction. Reliability still depends on acknowledgment timing, error handling, and whether offset commits are coordinated with side effects.

## 1. What Does AckMode Control?

A Kafka consumer reads records per partition and maintains its current read position. The committed offset is the next position the consumer group will read upon startup or when re-assigned a partition. If a consumer processes the record at offset `41`, the committed offset is normally `42`.

The Spring Kafka listener container manages polling, invoking the listener, and committing offsets. `AckMode` specifies when the container confirms successfully processed records:

| AckMode | Typical Commit Timing | Characteristics |
|---|---|---|
| `RECORD` | After each record the listener processes successfully | Per-record commit boundary. |
| `BATCH` | After finishing records received from a single poll | Batch-level commit; common default if not configured otherwise. |
| `TIME` | When the configured commit time interval is reached | Can group multiple records between commits. |
| `COUNT` | When the configured record count is reached | Commits by count threshold. |
| `COUNT_TIME` | When either the count or time threshold is reached | Combines both thresholds. |
| `MANUAL` | Listener calls `acknowledge()`; container applies poll-batch commit semantics | Application decides which records are complete. |
| `MANUAL_IMMEDIATE` | Listener calls `acknowledge()` on the consumer thread | Commits immediately when acknowledge is called on the right thread. |

Both `MANUAL` and `MANUAL_IMMEDIATE` require the listener to acknowledge explicitly. The key difference is commit timing. With `MANUAL`, the container normally waits until the poll's records finish processing before committing acknowledged offsets. With `MANUAL_IMMEDIATE`, a call on the consumer thread requests an immediate commit.

## 2. Basic Example with a Record Listener

The listener receives `Acknowledgment` alongside the payload or `ConsumerRecord`. After processing succeeds, the listener calls `acknowledge()`:

```java
@Component
public class PaymentListener {

    private final PaymentService paymentService;

    public PaymentListener(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    @KafkaListener(
            topics = "${app.topics.payments-in}",
            groupId = "payment-worker",
            containerFactory = "manualImmediateFactory")
    public void onPayment(
            ConsumerRecord<String, PaymentRequested> record,
            Acknowledgment acknowledgment) {

        paymentService.process(record.value());
        acknowledgment.acknowledge();
    }
}
```

In this example, `PaymentService.process()` must finish the work the application considers successful before calling `acknowledge()`. If the service throws an exception, the listener does not acknowledge the record; the container can pass the error to the error handler for retry or recovery per configuration.

Do not call `acknowledge()` at the beginning of the listener before running business logic. Once the offset has been committed, a later error cannot make Kafka automatically return the record to an unprocessed state. The record can be lost from the consumer group's processing flow even though business work never finished.

## 3. Configuring MANUAL_IMMEDIATE

You can create a dedicated listener container factory and set `AckMode.MANUAL_IMMEDIATE` on `ContainerProperties`:

```java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, PaymentRequested>
    manualImmediateFactory(
            ConsumerFactory<String, PaymentRequested> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, PaymentRequested>();
        factory.setConsumerFactory(consumerFactory);
        factory.getContainerProperties()
                .setAckMode(ContainerProperties.AckMode.MANUAL_IMMEDIATE);
        return factory;
    }
}
```

A listener selects the factory via the `containerFactory` attribute on `@KafkaListener`. The bean name must match the referenced name exactly. If an application has multiple listener groups with different acknowledgment policies, dedicated factories keep each group's configuration explicit.

In Spring Boot, you can configure the default listener via YAML:

```yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: manual_immediate
```

When individual listeners need distinct settings, using a custom factory is clearer than changing the application-wide default ack mode. `enable-auto-commit: false` ensures the Spring Kafka container controls commits according to ack mode. Do not enable Kafka consumer auto-commit if the goal is for `Acknowledgment` to decide when offsets are confirmed.

## 4. What Happens When acknowledge Is Called?

With a record listener running on the consumer thread, the basic sequence is:

```text
Kafka consumer poll()
        |
        v
Listener receives record offset 41
        |
        v
Execute business logic
        |
        +---- fails ----> throw exception -> error handler
        |
        v
Business logic succeeds
        |
        v
acknowledgment.acknowledge()
        |
        v
Container commits offset 42 immediately
```

The committed offset is the next offset to read, not the offset of the record just processed. Once the commit succeeds, if the consumer restarts or the partition is assigned to another consumer, the group can resume from the position after the acknowledged record.

`MANUAL_IMMEDIATE` only controls when the container executes the commit. It does not prove that a database wrote durably, an external API completed, or an output event was processed by a downstream consumer. The listener must clearly define what counts as "processed successfully" before acknowledging.

## 5. Consumer Thread vs. Calls from Other Threads

The name `MANUAL_IMMEDIATE` is strictly accurate when `acknowledge()` is called on the consumer thread running the listener. In that case, the container can commit immediately at the call site.

If `acknowledge()` is called from another thread, the commit request is queued and processed after records from the previous poll are handled. In that situation, behavior is no longer an immediate synchronous commit at the call site on the consumer thread.

Do not mix acknowledge calls on the consumer thread and on other threads within the same listener container. Spring Kafka warns that mixing both call styles can produce undefined results regarding commit timing. Choose one consistent processing model.

### 5.1 Asynchronous Processing

Some applications receive a record and hand work off to an executor for background processing. In this model, the listener may return before work finishes. If you want to acknowledge after asynchronous processing, configure and understand the semantics of your running Spring Kafka version.

Spring Kafka supports `asyncAcks` for `MANUAL` and `MANUAL_IMMEDIATE` in compatible versions. This feature permits acknowledging records from a single poll out of order. The container keeps the consumer paused until all missing acknowledgments from that poll arrive, and only then resumes committing/reading. This supports parallel processing, though it can increase latency and create extra redelivery exposure if the application stops before all acknowledgments arrive.

Example configuration on the listener container:

```java
factory.getContainerProperties().setAckMode(
        ContainerProperties.AckMode.MANUAL_IMMEDIATE);
factory.getContainerProperties().setAsyncAcks(true);
```

Enable `asyncAcks` only when parallel processing is genuinely needed and asynchronous outcome management has been designed. Do not hold onto `Acknowledgment` and call it arbitrarily from multiple threads. Each record must have one clear processing outcome; once work finishes, acknowledge the exact instance and avoid accidental double acknowledgments.

## 6. MANUAL_IMMEDIATE and Sync/Async Commits

`MANUAL_IMMEDIATE` governs when the container requests a commit after an acknowledge call. How the Kafka client sends the commit can be configured separately:

- `syncCommits` enables synchronous commits (`commitSync`); this is the common default for Spring Kafka containers.
- When `syncCommits` is disabled, the container uses asynchronous commits (`commitAsync`) and the corresponding callback if configured.

Example enabling synchronous commits:

```java
factory.getContainerProperties().setSyncCommits(true);
```

Synchronous commits wait for the broker's commit response within a timeout, so the listener thread can spend extra time waiting. Asynchronous commits reduce inline waiting, though the application must monitor errors in the callback and clearly understand commit-failure possibilities.

Do not confuse `MANUAL_IMMEDIATE` with a guarantee that the broker has confirmed success the moment `acknowledge()` returns under all configurations. Check `syncCommits`, timeouts, callbacks, and commit logs to understand how your application observes failures. With synchronous commits, the container waits for the commit result; with asynchronous commits, results are handled through the callback.

## 7. Combining with Spring Kafka Transactions

When a listener container runs inside a Kafka transaction, offsets are enlisted in the transaction and committed alongside output records when the transaction completes. `acknowledge()` still indicates the record has been processed, while the actual offset commit is coordinated by the transaction manager/container. Do not view calling `MANUAL_IMMEDIATE` inside a transactional listener as a way to detach offsets from the transaction.

For example, a listener can send an output and then acknowledge:

```java
@KafkaListener(
        topics = "${app.topics.orders-in}",
        containerFactory = "transactionalManualFactory")
public void onOrder(
        ConsumerRecord<String, Order> record,
        Acknowledgment acknowledgment) {

    EnrichedOrder output = processor.enrich(record.value());
    kafkaTemplate.send("orders.enriched", record.key(), output);
    acknowledgment.acknowledge();
}
```

With a properly configured transactional container, output and input offset are committed in the same Kafka transaction. If the transaction rolls back, the uncommitted output is hidden from committed readers and the offset is not committed either. `KafkaTemplate` must participate in the same transaction managed by the container, typically via the same `ProducerFactory` and corresponding transaction manager.

Without transactions, acknowledging the offset and sending output are two separate operations. Sending output successfully and then failing to commit the offset can cause the input record to be re-read and the output to be emitted twice. Committing the offset before output is durably written risks losing output if sending fails. Choose transactions when atomicity within Kafka's scope is needed; use idempotency or outbox when side effects live outside Kafka.

## 8. Retries and Error Handling

If the listener throws an exception before acknowledging, the container passes the error to the error handler. Depending on configuration, Spring Kafka can retry the record, seek back to the read position, or invoke a recovery handler to route the record to a Dead Letter Topic (DLT).

A `DefaultErrorHandler` configuration can bound retry attempts and apply backoff:

```java
@Bean
DefaultErrorHandler kafkaErrorHandler(KafkaTemplate<Object, Object> template) {
    var recoverer = new DeadLetterPublishingRecoverer(template);
    var backOff = new FixedBackOff(1_000L, 2L);
    return new DefaultErrorHandler(recoverer, backOff);
}
```

This snippet illustrates creating a recoverer and backoff; the application must configure serializers, destination resolvers, and error-handler beans matching key/value types, topic topology, and Spring Kafka version. For transactional listeners, use error-handling configuration compatible with transactions and rollback processors; do not blindly apply a non-transactional error handler to a transactional container.

If the listener already acknowledged and then threw an exception, the offset may already have been committed (in the non-transactional case when acknowledged on the consumer thread). The error handler cannot undo that commit to guarantee the record is redelivered. Therefore, place `acknowledge()` after all mandatory steps of the processing attempt.

Classify errors to choose policies:

| Error Type | Example | Handling Approach |
|---|---|---|
| Transient error | Dependency service timeout, temporary broker disruption | Bounded retries with backoff. |
| Permanent data error | Payload missing required field, invalid schema | Isolate or DLT, with metadata for investigation. |
| Business error | Order state does not allow transition | Apply business policy; avoid infinite retries. |
| Unrecoverable after retries | Prolonged dependency outage, record still fails | Pause/throttle processing or recover per operational policy. |

## 9. Rebalances, Redelivery, and Acknowledgment Timing

A consumer group can rebalance when an instance leaves the group, misses heartbeats, changes replica count, or exceeds processing time limits. If a partition is revoked before the record's offset is committed, the record may be redelivered to another consumer.

`MANUAL_IMMEDIATE` does not prevent rebalances and does not guarantee the listener is invoked only once per record. It only lets the application explicitly request a commit at acknowledgment time. If a commit fails because partition ownership already changed, the record can be redelivered. Consequently, business logic should be idempotent even when using manual immediate.

Pay special attention to `max.poll.interval.ms`. If the listener takes too long without polling again, the consumer may be treated as inactive and leave the group. For long-running work, consider reducing `max.poll.records`, optimizing work, raising limits appropriately, or splitting tasks using an asynchronous model with explicitly managed acknowledgments.

## 10. Record Listeners vs. Batch Listeners

The typical example for `MANUAL_IMMEDIATE` is a record listener: each listener invocation receives one record and can acknowledge that record after completion.

With a batch listener, a single listener invocation receives multiple records from a poll. Acknowledgments in batch listeners have batch semantics. Some Spring Kafka versions provide APIs to partially acknowledge a batch, subject to specific conditions such as listener thread and `MANUAL_IMMEDIATE`. If partial batch acknowledgment is needed, verify documentation for your exact running version before designing; do not assume a record-listener example carries over unchanged to a batch listener.

Basic batch listener example:

```java
@KafkaListener(
        topics = "${app.topics.events-in}",
        containerFactory = "manualImmediateBatchFactory")
public void onEvents(
        List<ConsumerRecord<String, Event>> records,
        Acknowledgment acknowledgment) {

    for (ConsumerRecord<String, Event> record : records) {
        processor.process(record.value());
    }

    acknowledgment.acknowledge();
}
```

In this example, acknowledge only after the entire batch succeeds. If a record throws an exception prior to acknowledgment, error handling decides how the batch is retried or recovered.

## 11. Common Mistakes

- **Acknowledging before processing finishes:** the offset can commit while business logic is incomplete, leading to lost processing.
- **Assuming MANUAL_IMMEDIATE retries automatically:** retries are governed by the error handler and container policy; ack mode only controls commits.
- **Calling acknowledge from a background thread and expecting an instant commit:** off-consumer-thread calls are queued and handled under different semantics.
- **Mixing consumer-thread and off-thread acknowledgments:** can yield undefined commit timing.
- **Enabling auto-commit:** the Kafka client can commit offsets outside acknowledgment control.
- **Ignoring asynchronous commit failures:** the application may believe an offset was confirmed while the callback reported a commit failure.
- **Assuming committing an offset makes a database and Kafka atomic:** offset commits cannot roll back side effects outside Kafka.
- **Failing to design idempotency:** records can be redelivered after a crash or rebalance even when the listener uses `MANUAL_IMMEDIATE`.
- **Applying record-listener semantics to batch listeners:** a batch contains multiple offsets and acknowledgment behavior must match the listener type.

## 12. Testing MANUAL_IMMEDIATE

Integration tests should verify both processing timing and committed offset positions. Embedded Kafka or Kafka Testcontainers can be used to run a broker in tests.

Key scenarios:

1. Send a valid record; listener processes and acknowledges; verify group offset advances to the next offset.
2. Have business logic throw an exception before acknowledge; verify the record is retried or handled per the error handler.
3. Send a record where the listener intentionally acknowledges before processing; use the test to demonstrate that an error after acknowledge does not automatically roll back the offset.
4. Compare `MANUAL` and `MANUAL_IMMEDIATE` with multiple records in one poll to observe differences in commit timing.
5. If `asyncAcks` is enabled, complete records out of receive order; verify the container waits for missing acknowledgments before resuming.
6. Simulate a rebalance or restart before commit; verify records can be redelivered and business logic is idempotent.
7. With a transactional container, verify offsets and outputs commit together or roll back together.

Do not rely on fixed `Thread.sleep()` calls to check offsets. Wait on concrete conditions such as the consumer group reaching the expected offset, output appearing, or the listener receiving the record. Use bounded timeouts so tests fail clearly when the condition does not happen.

## 13. When Should You Use MANUAL_IMMEDIATE?

`MANUAL_IMMEDIATE` fits when the listener needs to explicitly decide when each record is acknowledged and can acknowledge on the consumer thread immediately after finishing work. It is also useful when you want to avoid waiting for the remaining records in a poll before committing an already-processed record.

Consider `MANUAL` if you want the listener to mark acknowledgments while still letting the container commit under batch semantics. Use `RECORD` if all records are processed synchronously and manual acknowledgment decisions are unnecessary. Use Kafka transactions if Kafka outputs must be committed atomically with input offsets. If processing asynchronously, design completion order explicitly, configure `asyncAcks` when appropriate, and accept pause/redelivery impacts.

Before choosing this mode, answer three questions: at which step does the listener acknowledge, on which thread does the call execute, and what happens if the application stops right before or right after commit? The answers define the actual processing boundary and the required retry/idempotency policy.
