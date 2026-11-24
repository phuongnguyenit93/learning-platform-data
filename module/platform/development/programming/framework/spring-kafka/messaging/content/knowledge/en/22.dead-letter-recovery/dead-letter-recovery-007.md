# ConsumerRecordRecoverer

When a record has exhausted its retry attempts or falls under an exception category that should not be retried, the consumer needs a recovery step to decide where the data goes next. Spring Kafka provides `ConsumerRecordRecoverer` as a container-level callback for this step. The recoverer receives the original Kafka record along with the exception that caused the failure, allowing the application to persist the record to an error store, write an audit log, or move the record to a dead-letter topic (DLT).

`ConsumerRecordRecoverer` is typically passed to `DefaultErrorHandler`. The error handler decides whether a record should be retried; the recoverer is invoked only when the error handler reaches the recovery stage. Separating these two responsibilities lets retry policy and failed-record storage be configured independently.

## 1. The ConsumerRecordRecoverer Contract

`ConsumerRecordRecoverer` is a functional interface in the `org.springframework.kafka.listener` package. It has a single method:

```java
void accept(ConsumerRecord<?, ?> record, Exception exception);
```

The two parameters carry distinct meanings:

- `record`: the original `ConsumerRecord` received by the Kafka consumer, including topic, partition, offset, timestamp, key, value, and headers.
- `exception`: the error that prevented the listener from processing the record. Use this exception to classify the failure, record the cause, and aid investigation.

Because it receives `ConsumerRecord` rather than a converted `Message<?>` object, the recoverer can preserve the record together with its original Kafka metadata prior to business processing by the listener. If deserialization failed and the application uses `ErrorHandlingDeserializer`, `value()` may not contain a converted payload; deserialization error details and raw data are kept in headers by the deserializer mechanism. The recoverer or DLT must preserve those headers if the recovery process needs to inspect the original data.

For example, a record can be identified by the triplet of topic, partition, and offset. The key and an event ID inside the payload are also useful for business tracing. Do not merely log `exception.getMessage()` and drop the original record, as that information is rarely sufficient for investigation or recovery.

## 2. When Is the Recoverer Invoked?

For a record listener using `DefaultErrorHandler`, the high-level processing flow is:

1. The consumer polls a record and the container invokes the listener.
2. If the listener throws a retryable exception, `DefaultErrorHandler` waits according to `BackOff` and retries the record.
3. If the exception is classified as non-retryable, the error handler skips retries.
4. Once retries are exhausted or the exception is non-retryable, the error handler invokes the configured `ConsumerRecordRecoverer`.
5. If recovery succeeds, the container proceeds according to its configured commit/acknowledgment policy. If recovery fails, the exception from the recoverer is handled as a recovery error and the record may be redelivered.

Thus, the recoverer is neither a callback invoked for every record nor the place for retry logic. It handles records that the error handler has decided require recovery.

## 3. Creating a Custom Recoverer

A custom recoverer can save the record and exception into a durable failure store. The example below assumes the application has a `FailureArchive` to persist data into a database or dedicated repository:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.listener.ConsumerRecordRecoverer;

@Bean
ConsumerRecordRecoverer orderRecordRecoverer(FailureArchive failureArchive) {
    return (record, exception) -> {
        failureArchive.persist(
                record.topic(),
                record.partition(),
                record.offset(),
                record.key(),
                record.value(),
                record.headers(),
                exception);
    };
}
```

`FailureArchive` is an illustrative business component; the method signature should be adapted to your actual storage schema. The crucial point is that `persist` must finish successfully before the recoverer returns. If it merely launches an asynchronous task and returns immediately, the container may consider recovery complete before the data is durably persisted.

When writing to a failure archive, record at a minimum:

- Record identity: topic, partition, offset, and timestamp.
- Key, original payload, and headers needed for investigation or replay.
- Exception type, error message, and useful root-cause details.
- Recovery timestamp, delivery count if tracked by the application, and handling status.

Payloads can contain sensitive data. Restrict access permissions, retention periods, and log contents according to your application's data policies.

## 4. Combining ConsumerRecordRecoverer with DefaultErrorHandler

Pass the recoverer into `DefaultErrorHandler`'s constructor, then attach the error handler to the listener container factory:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.ConsumerRecordRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Bean
DefaultErrorHandler orderErrorHandler(
        ConsumerRecordRecoverer orderRecordRecoverer) {

    return new DefaultErrorHandler(
            orderRecordRecoverer,
            new FixedBackOff(1_000L, 2L));
}

@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
orderKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        DefaultErrorHandler orderErrorHandler) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(orderErrorHandler);
    return factory;
}
```

In this example, `FixedBackOff(1_000L, 2L)` sets a one-second interval and at most two retries after the initial processing attempt. When retries fail, `orderRecordRecoverer` is called. Exceptions classified as non-retryable also go straight to the recoverer without waiting through those retries.

The listener uses the factory by bean name via the `containerFactory` attribute of `@KafkaListener`. If the application has multiple listener groups with different policies, you can create separate factories and recoverers for each group.

## 5. Using DeadLetterPublishingRecoverer to Send to a DLT

If you want to store failed records in Kafka so operations teams can inspect and replay them, Spring Kafka already includes `DeadLetterPublishingRecoverer`. This class implements `ConsumerRecordRecoverer` and uses `KafkaTemplate` to publish failed records to a DLT.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Bean
DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    var recoverer = new DeadLetterPublishingRecoverer(kafkaTemplate);
    return new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L));
}
```

With the common default routing, a record from the source topic is sent to a topic with the `.DLT` suffix and its corresponding partition preserved. Create the target topic with a compatible partition count, grant write permissions to the producer, and check broker configuration before operating. You can provide a custom destination resolver if you want different DLT naming or partitioning rules.

`DeadLetterPublishingRecoverer` can add headers containing exception details and the original record's location. When you need to ensure the send succeeded before considering recovery complete, configure and verify the recoverer's send-result waiting behavior for your Spring Kafka version. Do not replace it with a fire-and-forget asynchronous `KafkaTemplate.send()` that returns immediately without observing the result.

## 6. Recovery Failure and Idempotency

A recoverer can also fail: the failure archive database is unavailable, the DLT does not exist, the producer lacks write permission, or the broker loses connectivity. In such cases, recovery is not complete. Let the error propagate out of the recoverer so the error handler knows recovery failed; do not catch and swallow the exception.

When recovery fails, `DefaultErrorHandler` can put the record back into delivery. Whether `BackOff` state is reset after a recovery failure can be tuned with `resetStateOnRecoveryFailure`; verify the value and behavior against your project's Spring Kafka version. Whichever policy you choose, the application must monitor recovery failures so records do not get stuck unnoticed.

A record may be redelivered after the listener ran partially or after the recoverer performed a side effect without completing. Therefore, persisting to a failure archive or sending to another system should be idempotent. You can use topic-partition-offset as a unique key for the source record, or use a stable event ID if the domain already defines event identifiers.

## 7. Distinguishing ConsumerRecordRecoverer from Other Handlers

Error-handling components in Spring Kafka operate at different layers:

| Component | Primary input | Responsibility |
| --- | --- | --- |
| `KafkaListenerErrorHandler` | Converted message and `ListenerExecutionFailedException` | Handles errors bound to a `@KafkaListener`; may rethrow to the container |
| `CommonErrorHandler` / `DefaultErrorHandler` | Exception and consumer/container context | Classifies retries, BackOff, seek, commit, and decides when to recover |
| `ConsumerRecordRecoverer` | `ConsumerRecord<?, ?>` and `Exception` | Performs the final action on a record that has reached recovery |
| `DeadLetterPublishingRecoverer` | Record and exception | An implementation that sends failed records to a DLT via `KafkaTemplate` |

The recoverer does not receive a `Consumer` or `Acknowledgment`, so do not use it to manually seek or commit offsets. Offset control belongs to the error handler and container. Likewise, a recoverer does not replace `KafkaListenerErrorHandler`: one handles records at the container's recovery step, while the other wraps the listener invocation.

## 8. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Logging only the exception without saving the record | Insufficient data to investigate or replay | Store the record and metadata in a DLT or durable error store |
| Swallowing exceptions when failure storage fails | Container may unintentionally treat recovery as successful | Let recovery errors propagate to the error handler |
| Firing an async DLT send and returning immediately | Offset may advance before publishing completes | Verify the send result before finishing recovery |
| Not making recovery idempotent | Redelivered records can create duplicate error records | Use a unique key derived from Kafka coordinates or event ID |
| Not checking DLT partition count | Publishing can fail when the target partition does not exist | Create matching partition counts or use an appropriate resolver |
| Logging full payloads uncontrolled | Exposes sensitive data and bloats log volume | Restrict stored fields, access permissions, and retention |

## 9. Testing ConsumerRecordRecoverer

Tests should verify both the data received by the recoverer and the storage outcome after the error handler completes:

1. Create a listener that intentionally throws a retryable exception; verify the listener retries according to BackOff and the recoverer is called only after retries are exhausted.
2. Create a non-retryable exception; verify the recoverer is invoked immediately without waiting for retries.
3. Verify the recoverer receives the right topic, partition, offset, key, value, headers, and exception.
4. Make the failure store or DLT unavailable; verify the recovery exception is observed and the record can be redelivered per configuration.
5. Re-deliver the same record; verify the idempotency key prevents duplicate failure entries.
6. If using `DeadLetterPublishingRecoverer`, read the record from the DLT and inspect payload, partition, and source headers.

## 10. Implementation Checklist

- [ ] `ConsumerRecordRecoverer` is registered as a bean or explicitly created and passed to `DefaultErrorHandler`.
- [ ] The recoverer persists the original record along with required metadata and failure cause.
- [ ] Recovery completes synchronously or uses a result-confirmation mechanism before returning.
- [ ] Exceptions from failed recovery operations propagate to the error handler.
- [ ] Recovery is idempotent to tolerate record redelivery.
- [ ] If using a DLT, topics, partitions, ACLs, and publish settings are verified.
- [ ] BackOff policy, non-retryable exceptions, and recovery are designed cohesively.
- [ ] Metrics/logs exist for recovered record count, recovery failures, and DLT record count.
- [ ] Both successful recovery and failed recovery paths are tested.

`ConsumerRecordRecoverer` is the bridge between deciding to stop retrying and preserving failed data. When the recoverer reliably persists the original record, the application can continue processing the event stream while retaining enough information for investigation, bug fixing, or later replay.
