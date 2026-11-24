# Recovery Records and logRecoveryRecord

In a Spring Kafka consumer with retries, not every failed record will succeed on the next attempt. After exhausting the allowed retry attempts, or when an exception is classified as non-retryable, the application needs a **recovery step**: log the failed record, send it to a dead-letter topic (DLT), or route it to another handling workflow. This step prevents the consumer from getting stuck indefinitely on the same record while still preserving information for investigation.

`DeadLetterPublishingRecoverer` is the recoverer commonly used to publish failed records to a DLT. Starting in **Spring Kafka 3.1**, this class provides `setLogRecoveryRecord(boolean)`; setting it to `true` logs the **recovery record and exception**. The `logRecoveryRecord` feature aids visibility into events entering the recovery workflow, yet it **does not guarantee DLT publishing succeeds, does not alter retry counts, and does not replace deduplication mechanisms**.

## 1. What is a recovery record?

A *recovery record* is a record that has reached the recovery branch according to the error-handling policy. Within this lesson's scope, it is typically a `ConsumerRecord<?, ?>` that the listener failed to process and the error handler decided to pass to a `ConsumerRecordRecoverer`.

Example of a record from topic `orders`, partition 2, offset 150:

```text
orders-2, offset=150
          |
          v
@KafkaListener processes OrderCreated
          |
          v
HTTP timeout / ValidationException / business error
          |
          v
DefaultErrorHandler decides to retry?
          |
     +----+----+
     |         |
    Yes       No / retries exhausted
     |         |
     v         v
   Retry  ConsumerRecordRecoverer
               |
               v
      Log or publish to DLT
```

Recovery does not mean business processing succeeded. If an `OrderCreated` cannot be processed and is successfully moved into `orders.DLT`, consumption progress can continue per configuration, yet that order still requires investigation or reprocessing. Therefore, distinguish two concepts:

| Concept | What happened | What is NOT guaranteed |
|---|---|---|
| Listener success | The listener method completed normally. | All systems outside Kafka are durable, unless the logic ensures it. |
| Recovery success | The recoverer completed per its contract and error policy. | The main business action succeeded or someone has already resolved the DLT. |

When an error occurs, a record may retry multiple times before entering recovery. For errors classified as non-retryable, the record can enter recovery immediately after the first failure.

## 2. Relationship between DefaultErrorHandler and the recoverer

`DefaultErrorHandler` coordinates error handling for the Kafka listener container. For a record listener, the handler uses `BackOff` to decide whether to retry processing the record or move to recovery. Once backoff is exhausted, the handler invokes the corresponding recoverer.

Example using `FixedBackOff`:

```java
FixedBackOff backOff = new FixedBackOff(1_000L, 2L);

DefaultErrorHandler errorHandler =
        new DefaultErrorHandler(backOff);
```

`2L` means **two retry attempts after the initial delivery**, i.e., up to three listener invocations in a normal retry cycle. If all attempts fail, the handler invokes its default recovery mechanism. By default, `DefaultErrorHandler`'s recoverer logs the failed record; to send records to a DLT, supply a dedicated recoverer.

```java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(kafkaTemplate);

DefaultErrorHandler errorHandler =
        new DefaultErrorHandler(
                recoverer,
                new FixedBackOff(1_000L, 2L));
```

In the second example, `DefaultErrorHandler` remains the component coordinating retries. `DeadLetterPublishingRecoverer` only receives the record once the handler decides to enter recovery. Do not assume declaring a recoverer makes the listener send every record straight to the DLT.

## 3. Where does DeadLetterPublishingRecoverer send records?

With a `DeadLetterPublishingRecoverer` built from a `KafkaTemplate` without a custom resolver, the default rule normally sends to the source topic plus the `.DLT` suffix and the same partition number as the source record.

Example:

```text
Source: orders-2, offset=150
        |
        v
DeadLetterPublishingRecoverer
        |
        v
Destination: orders.DLT, partition=2
```

Kafka offsets on the DLT topic are assigned independently. The source record at offset 150 **does not** mean its copy in the DLT is also at offset 150. When tracing, use source info in headers and a stable event ID.

If you want to route by exception or business logic, pass a destination resolver:

```java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(
                kafkaTemplate,
                (record, exception) -> {
                    String destination =
                            exception instanceof IllegalArgumentException
                                    ? "orders-invalid.DLT"
                                    : "orders.DLT";

                    return new TopicPartition(destination, record.partition());
                });
```

This example requires the DLT topics to exist with corresponding partitions, along with compatible producer serializers and write permissions. If the destination topic lacks the requested partition, how the framework checks and selects partitions depends on version/configuration; do not treat a returned destination as proof that publishing will certainly succeed.

## 4. What is logRecoveryRecord, and since which version?

`setLogRecoveryRecord(boolean)` is a method on **`org.springframework.kafka.listener.DeadLetterPublishingRecoverer`**, introduced in **Spring Kafka 3.1**. The method enables or disables logging the record being recovered and the corresponding exception.

```java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(kafkaTemplate);

recoverer.setLogRecoveryRecord(true);
```

When enabled, the recoverer logs record and exception details during recovery. This helps operators know which records reached the recovery branch without relying solely on initial listener logs.

Distinguish three different things:

| Mechanism | Purpose |
|---|---|
| `setLogRecoveryRecord(true)` | Logs the recovery record and exception inside `DeadLetterPublishingRecoverer`. |
| `DefaultErrorHandler` + `BackOff` | Decides when to retry and when to hand off to the recoverer. |
| `setFailIfSendResultIsError(true)` | Instructs the recoverer to detect and report errors from asynchronous publish results when supported. |

**`logRecoveryRecord` is not a Kafka broker property** and not a Kafka client `spring.kafka.consumer.logRecoveryRecord` syntax. It is a setting on the Java recoverer object. If the application runs Spring Kafka earlier than 3.1, this method is unavailable; upgrade appropriately or implement recovery-layer logging with available APIs.

Do not enable `logRecoveryRecord` merely to know a record failed. Your system may already log in the error handler, retry listener, and DLT consumer; enabling this feature on top can create duplicate logs, inflate storage, or expose payloads. Decide based on monitoring goals and data policy.

## 5. Complete configuration example with Spring Kafka

The following configuration uses `DefaultErrorHandler`, `FixedBackOff`, and `DeadLetterPublishingRecoverer`. The listener retries up to two times after the initial attempt; once retries are exhausted, the recoverer sends the record to the DLT and logs the recovery record.

```java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
public class OrderKafkaErrorConfig {

    @Bean
    public DefaultErrorHandler orderErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(kafkaTemplate);

        recoverer.setLogRecoveryRecord(true);
        recoverer.setFailIfSendResultIsError(true);
        recoverer.setWaitForSendResultTimeout(Duration.ofSeconds(10));

        FixedBackOff backOff = new FixedBackOff(1_000L, 2L);
        return new DefaultErrorHandler(recoverer, backOff);
    }

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            orderKafkaListenerContainerFactory(
                    ConsumerFactory<String, OrderCreated> consumerFactory,
                    DefaultErrorHandler orderErrorHandler) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(orderErrorHandler);
        return factory;
    }
}
```

The listener just runs business logic and throws an exception on failure:

```java
@KafkaListener(
    topics = "orders",
    groupId = "order-service",
    containerFactory = "orderKafkaListenerContainerFactory"
)
public void handle(OrderCreated event) {
    orderService.process(event);
}
```

This example assumes the application already configured `ConsumerFactory`, `KafkaTemplate`, serializers/deserializers, and a logging framework. `OrderCreated` is an application-defined business data type. `KafkaTemplate<Object, Object>` needs a producer factory compatible with key/value types in both normal and recovery paths; do not assume one serializer handles every failing payload type.

With Spring Boot, foundational consumer properties can be configured as:

```yaml
spring:
  kafka:
    consumer:
      group-id: order-service
      enable-auto-commit: false
      auto-offset-reset: earliest
    producer:
      acks: all
```

Do not confuse `enable-auto-commit: false` with guaranteed safe commits. The listener container still needs appropriate acknowledgement, commit, and recovery policies. Setting `acks: all` makes the producer request broker acknowledgements per replication config, yet alone it does not create an atomic transaction with consumer committed offsets.

## 6. When is the recovery log emitted?

Typical processing flow:

```text
Consumer polls record
        |
        v
Listener processes and throws exception
        |
        v
DefaultErrorHandler performs allowed retries
        |
        v
BackOff exhausted or non-retryable exception
        |
        v
DeadLetterPublishingRecoverer.accept(record, exception)
        |
        +--> logRecoveryRecord = true:
        |      log record and exception info
        |
        +--> build ProducerRecord for DLT
        |      + add source/error headers
        |
        +--> publish via KafkaTemplate
        |
        v
Publish result and recovery handling per configuration
```

This is a logical diagram. The exact ordering between the logging call, record creation, and receiving producer acknowledgements depends on implementation/version. **A recovery log line is not proof the record is durably stored in the DLT**. To verify, monitor send results, actual DLT record counts, and producer errors.

At least three log types must be distinguished:

1. **Listener failure:** records a failed record processing attempt.
2. **Retry exhausted or recovery attempt:** records that the record entered the recovery branch.
3. **DLT publishing outcome:** records whether publishing actually succeeded or failed per wait/send-result policy.

Enabling `logRecoveryRecord` only improves visibility of the second type; it does not replace the other two.

## 7. Distinguishing default recoverer logging from logRecoveryRecord

If you do not pass a custom recoverer to `DefaultErrorHandler`, when retries are exhausted Spring Kafka can by default **log the failed record**. That is the error handler's recovery behavior. It differs from enabling `setLogRecoveryRecord(true)` on a specific `DeadLetterPublishingRecoverer`.

Example:

```java
// Use DefaultErrorHandler's default recoverer.
DefaultErrorHandler handler =
        new DefaultErrorHandler(new FixedBackOff(1_000L, 2L));

// Use DLT-publishing recoverer and request logging the recovered record.
DeadLetterPublishingRecoverer publishingRecoverer =
        new DeadLetterPublishingRecoverer(kafkaTemplate);
publishingRecoverer.setLogRecoveryRecord(true);

DefaultErrorHandler publishingHandler =
        new DefaultErrorHandler(
                publishingRecoverer,
                new FixedBackOff(1_000L, 2L));
```

In the first configuration, `DefaultErrorHandler` does not automatically introduce a DLT publish step. In the second configuration, the record passes through the publishing recoverer; `logRecoveryRecord` only adds logging inside this component.

Also distinguish `setLogRecoveryRecord` from the error handler's exception log level (`setLogLevel(...)` in relevant APIs). The log level for exceptions thrown by the handler and the record log emitted as the recoverer forwards it can belong to different branches, so changing one does not silence all error logs.

## 8. Controlling sensitive data in recovery logs

`ConsumerRecord` can contain message keys, values, and headers. Exceptions can contain business messages, URLs, input data, or stack traces. Therefore, when enabling `setLogRecoveryRecord(true)`, review log security policies:

- Do not put passwords, tokens, payment card numbers, or personal data into logged payloads.
- Avoid logging full payloads verbatim when records contain sensitive or oversized data.
- Review how `toString()` is implemented on business payloads; it can expose fields the application does not want published.
- Grant recovery-log read permissions strictly to teams that need them for operations.
- Set appropriate retention periods for both logs and the DLT; each has independent protection policies.
- Use correlation/event IDs for tracing instead of relying on payload contents.

When the application needs controlled logging, use `RetryListener.recovered(...)` to log selected metadata rather than logging the whole record. Example:

```java
DefaultErrorHandler handler =
        new DefaultErrorHandler(
                publishingRecoverer,
                new FixedBackOff(1_000L, 2L));

handler.setRetryListeners(new RetryListener() {
    @Override
    public void failedDelivery(
            ConsumerRecord<?, ?> record,
            Exception exception,
            int deliveryAttempt) {
        // Avoid printing the payload on every retry.
    }

    @Override
    public void recovered(
            ConsumerRecord<?, ?> record,
            Exception exception) {
        log.warn(
            "Kafka record recovered: topic={}, partition={}, offset={}, exception={}",
            record.topic(),
            record.partition(),
            record.offset(),
            exception.getClass().getSimpleName());
    }
});
```

`recovered()` is a signal from the error handler when the recoverer did not throw an error at call time. If DLT sending can still fail asynchronously without the recoverer verifying it, this callback alone does not guarantee the copy was persisted by the broker. For systems requiring publish confirmation, also configure the recoverer's send-result observation.

## 9. DLT publish errors and recovery status

A record can fail both in the listener and when publishing to the DLT. For instance, the DLT topic does not exist yet, the producer lacks ACLs, the serializer does not support the value type, or brokers are unresponsive.

```text
orders-2, offset 150
         |
         v
Listener fails and retries exhausted
         |
         v
DeadLetterPublishingRecoverer
         |
         +--> DLT publish succeeded
         |       |
         |       v
         |   Can complete recovery per configuration
         |
         +--> DLT publish failed
                 |
                 v
             Recovery failure
                 |
                 v
        Needs reprocessing / investigate publish error
```

Spring Kafka offers settings like `setFailIfSendResultIsError(true)` and `setWaitForSendResultTimeout(...)` so the recoverer detects send errors and bounds how long it waits for results. When the recoverer throws an exception due to recovery failure, `DefaultErrorHandler` can put the failed record back into a retry cycle; by default, backoff state may be reset after a recovery error.

Example:

```java
publishingRecoverer.setLogRecoveryRecord(true);
publishingRecoverer.setFailIfSendResultIsError(true);
publishingRecoverer.setWaitForSendResultTimeout(Duration.ofSeconds(10));

DefaultErrorHandler handler = new DefaultErrorHandler(
        publishingRecoverer,
        new FixedBackOff(2_000L, 3L));
```

In practice, align producer, broker, and application timeouts properly. Waiting too long for send results on the consumer thread can push processing time close to `max.poll.interval.ms`. Not waiting or not catching publish errors risks declaring recovery successful prematurely. Balance both risks according to reliability requirements.

**Do not use `logRecoveryRecord` logs as the sole criterion for deleting or skipping failed records.** To confirm handoff, rely on publish results, offsets, actual DLT record counts, and corresponding metrics.

## 10. Recovery and committed offsets are not a default transaction

When a record is recovered, the consumer can move on to the next record depending on acknowledgement mode and error handler policy. However, offset commit behavior depends on container configuration, not solely on `logRecoveryRecord`.

For example, record `orders-2@150` fails and is sent to the DLT:

```text
Consumer fails to process orders-2@150
          |
          v
Recoverer publishes a copy to orders.DLT
          |
          v
Container is allowed to advance past failed record per config
          |
          v
Consumer group may commit next offset = 151
```

In manual modes, understand acknowledgement and committing recovered offsets clearly. With `AckMode.MANUAL_IMMEDIATE`, `DefaultErrorHandler` supports `setCommitRecovered(true)` to commit the offset of recovered records; this setting has conditions and is not always needed for other ack modes.

```java
DefaultErrorHandler handler = new DefaultErrorHandler(
        publishingRecoverer,
        new FixedBackOff(1_000L, 2L));

handler.setCommitRecovered(true);

// The corresponding container requires AckMode.MANUAL_IMMEDIATE.
factory.getContainerProperties()
       .setAckMode(ContainerProperties.AckMode.MANUAL_IMMEDIATE);
```

This is a configuration example, not advice to enable `commitRecovered` on every listener. Weigh DLT write timing, recovery failure states, and business guarantees. Source offset commit and DLT publish do not automatically form an atomic transaction in every setup; crashing between the two actions can lead to reprocessing. Replay design and idempotency remain necessary.

## 11. RetryListener for tracking three states

`DefaultErrorHandler`'s `RetryListener` provides useful callbacks to separate three stages: a failed delivery, a completed recovery, and a failed recovery.

```java
handler.setRetryListeners(new RetryListener() {
    @Override
    public void failedDelivery(
            ConsumerRecord<?, ?> record,
            Exception exception,
            int deliveryAttempt) {
        log.warn("Delivery failed: topic={}, partition={}, offset={}, attempt={}",
                record.topic(), record.partition(), record.offset(),
                deliveryAttempt, exception);
    }

    @Override
    public void recovered(
            ConsumerRecord<?, ?> record,
            Exception exception) {
        log.info("Recovery completed: topic={}, partition={}, offset={}",
                record.topic(), record.partition(), record.offset());
    }

    @Override
    public void recoveryFailed(
            ConsumerRecord<?, ?> record,
            Exception original,
            Exception failure) {
        log.error("Recovery failed: topic={}, partition={}, offset={}",
                record.topic(), record.partition(), record.offset(), failure);
    }
});
```

Exact callback APIs can differ across Spring Kafka versions, especially for batch listeners; use signatures matching your project's dependency. A `RetryListener` can increment metrics and log metadata without logging entire payloads.

Example metric separation:

| Metric | When incremented? | Meaning |
|---|---|---|
| `kafka_listener_failure_total` | Listener processing fails. | Business/technical error in listener. |
| `kafka_record_recovered_total` | Recovery callback invoked. | Handler completed recovery step per recoverer contract. |
| `kafka_record_recovery_failed_total` | Recoverer throws error. | Recovery, DLT, or producer issue needs attention. |
| `kafka_dlt_publish_failure_total` | System records DLT publish error. | Delivering failed record to DLT has problems. |

The metric names above are illustrative names an application can define, not mandatory Spring Kafka defaults.

## 12. logRecoveryRecord in non-blocking retries

With `@RetryableTopic`, Spring Kafka can use a `DeadLetterPublishingRecoverer` created by the retry-topic infrastructure to **route records through retry topics or to the DLT**. In that case, recovery logs may reflect **forwarding to the next topic**, not necessarily just entering the final DLT.

```text
orders
  |
  +--> retry-1000ms
           |
           +--> retry-2000ms
                    |
                    +--> orders-dlt
```

When inspecting logs, examine `current topic`, `destination topic`, `attempt`, and the exception. A recoverer log line can appear before the record finishes the entire retry-topic chain.

If you want to customize the recoverer created by the retry-topic infrastructure, Spring Kafka provides version-dependent configuration hooks/customizers. For instance, in versions supporting `RetryTopicConfigurationSupport`, you can customize the recoverer instead of attaching a separate DLT handler to every container. Ensure the extension point is actually invoked in your version and avoid conflicts across ways of enabling retry-topic infrastructure.

Do not configure a separate `DefaultErrorHandler` with a DLT-publishing recoverer on the main listener if the goal is using the full `@RetryableTopic` path, unless intentionally coordinating retry layers. Otherwise, records may jump to the DLT early or undergo a different retry count than expected.

## 13. Observing records from source to DLT

A well-operated system needs a stable correlation ID across topics. For example, an event may appear sequentially in `orders`, `orders-retry-1000`, and `orders.DLT`, with a different offset in each topic.

Recommended log at the business or recovery monitoring layer:

```text
event_id=order-4821-created
original_topic=orders
original_partition=2
original_offset=150
current_topic=orders-retry-1000
destination_topic=orders.DLT
attempt=3
exception_type=DownstreamTimeoutException
recovery_result=PUBLISH_ATTEMPTED
```

This is an illustrative example; `PUBLISH_ATTEMPTED` is intentionally distinct from `PUBLISH_CONFIRMED`. To record `PUBLISH_CONFIRMED`, you need evidence the producer received an appropriate broker acknowledgement under the send policy.

Signals to monitor include retry rate, recovery success/failure, DLT records received, consumer lag for both the main group and retry groups, DLT publish latency, serialization errors, timeouts, and ACL errors. Watching only main-topic lag drop can mask many unfinished business records waiting in retry topics or DLTs.

## 14. Easily misunderstood scenarios

| Symptom | Misconception | Correct understanding / action |
|---|---|---|
| Recovery log exists but DLT has no record | Thinking the log means the broker stored the DLT record. | Verify producer send result, destination, serializer, ACL, and DLT record count. |
| No recovery log appears | Thinking no records were recovered. | Check `setLogRecoveryRecord`, log level, active handler/recoverer, and DLT metrics. |
| Record entered DLT yet business is incomplete | Thinking recovery equals business success. | DLT only stores failed records for follow-up; investigation/replay workflow is needed. |
| Same record appears multiple times in logs | Thinking they are independent events. | Could be retries, rebalances, replays, or logs from multiple layers; match event ID and source offset. |
| Recovery log contains sensitive payloads | Enabling logging for easy debug without data controls. | Reduce raw record logging, use RetryListener with metadata, and control retention/read permissions. |
| `setLogRecoveryRecord` fails to compile | Using Spring Kafka prior to 3.1 or wrong recoverer class. | Check version and import `org.springframework.kafka.listener.DeadLetterPublishingRecoverer`. |
| Listener retries endlessly after DLT failure | Recoverer failure resets backoff / redelivers record. | Check producer failures, backoff reset behavior, and recovery state. |
| logRecoveryRecord enabled but offset does not advance | Confusing logging with commit or recovery success. | Investigate exceptions, send results, ack mode, `commitRecovered`, and rebalances. |

## 15. Practical implementation workflow

To introduce recovery logging into a production listener, follow this sequence:

1. Identify retryable exceptions and exceptions that should go straight to recovery.
2. Choose the recoverer: logging, DLT publishing, or another recovery workflow; define what counts as success.
3. Configure `DefaultErrorHandler` and `BackOff` with a bounded time budget.
4. If using `DeadLetterPublishingRecoverer` on Spring Kafka 3.1+, consider enabling `setLogRecoveryRecord(true)` if log policy allows.
5. Ensure the DLT producer has compatible serializers, topics/partitions, ACLs, and timeouts.
6. Configure publish failure detection and separate logs/metrics for recovery failures; never treat recovery logs as sole proof of handoff.
7. Check impacts on `AckMode`, committed offsets, and business idempotency.
8. Monitor logs/metrics for retries, recovery, DLT publishing, and consumer lag across all related topics.
9. Prepare workflows to intake, classify, and perform controlled replay of DLT records.

`logRecoveryRecord` is an observability option in `DeadLetterPublishingRecoverer`, not a tool that guarantees delivery semantics. By clearly understanding the boundaries between **listener failure**, **recovery attempt**, **DLT publish outcome**, and **offset commit**, operations teams can investigate failed records more reliably without mistaking logging for business processing success.
