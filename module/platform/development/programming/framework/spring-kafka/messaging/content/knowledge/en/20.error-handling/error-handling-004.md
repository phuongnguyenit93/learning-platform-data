# CommonErrorHandler

When a `@KafkaListener` method throws an exception, Spring Kafka must decide whether the record should be retried, recovered, routed to a dead-letter topic, or stop the listener container. `CommonErrorHandler` is the unified abstraction for the listener container to handle errors arising while receiving and processing records, applying to both record listeners and batch listeners.

In most applications, you do not need to implement this interface yourself. `DefaultErrorHandler` is the general-purpose choice for backoff-based retries and recovery. You can attach the handler to `ConcurrentKafkaListenerContainerFactory`, configure which exceptions are retried, and use `DeadLetterPublishingRecoverer` to route unprocessable records to a DLT.

## 1. What Problem Does CommonErrorHandler Solve?

A listener can fail for many reasons:

- Invalid data or missing required fields.
- Database temporarily unreachable.
- Downstream service timing out or rate-limiting requests.
- Payload conversion or deserialization failure.
- Programming bug or invalid business state.

Without a clear error-handling policy, a consumer may repeatedly re-read a failing record, stall partition progress, or commit offsets at the wrong moment. `CommonErrorHandler` lets the container apply a consistent strategy whenever the listener or polling encounters an exception.

High-level processing flow:

```text
Kafka poll
    |
    v
Listener processes record/batch
    |
    +---- Success ----------------------> Commit per AckMode
    |
    +---- Throws exception
              |
              v
       CommonErrorHandler
              |
       +------+-------------------+
       |                          |
       v                          v
   Retry/backoff              Recovery
       |                          |
       |                          +--> Write DLT
       |                          +--> Skip intentionally
       |                          +--> Stop container
       |
       +--> Invoke listener again
```

The handler decides retry/recovery; the listener container remains responsible for polling, seeking, acknowledgment, and offset commits per configuration.

## 2. CommonErrorHandler and Legacy Error-Handling APIs

Since Spring Kafka 2.8, `CommonErrorHandler` unifies error handling for record listeners and batch listeners. It replaces the legacy `ErrorHandler` and `BatchErrorHandler` abstractions.

| API | Role |
| --- | --- |
| `CommonErrorHandler` | Unified interface for listener container errors |
| `DefaultErrorHandler` | Retries per `BackOff`, classifies exceptions, and recovers records after retries are exhausted |
| `CommonLoggingErrorHandler` | Logs exceptions using a simple logging strategy |
| `CommonContainerStoppingErrorHandler` | Stops the container on error so unfinished records can be reprocessed later |
| `CommonDelegatingErrorHandler` | Selects different handlers based on exception type |
| `CommonMixedErrorHandler` | Uses separate handlers for record listeners and batch listeners |

Specialized classes suit specific operational policies. If you need bounded retries and routing failed records to a DLT, `DefaultErrorHandler` is usually the right starting point.

Avoid building new code on `SeekToCurrentErrorHandler` or `RecoveringBatchErrorHandler` in modern codebases; their common use cases have been replaced by `DefaultErrorHandler`.

The `CommonErrorHandler` interface provides extension points for different scenarios: handling a single record (`handleOne`), handling remaining records when seeks are needed (`handleRemaining`), handling a batch (`handleBatch`), and handling exceptions not tied to a specific record such as poll errors (`handleOtherException`). `seeksAfterHandling()` indicates whether the handler manages seeks itself; `isAckAfterHandle()` determines whether the container commits after the handler finishes normally. Implement the interface directly only when built-in handlers cannot satisfy the required policy.

## 3. Attaching CommonErrorHandler to the Listener Container Factory

`CommonErrorHandler` is configured on `ConcurrentKafkaListenerContainerFactory`. Every listener using that factory inherits the same error policy unless the application defines a separate factory.

Minimal example with `DefaultErrorHandler`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
public class KafkaListenerConfiguration {

    @Bean
    public DefaultErrorHandler commonErrorHandler() {
        // Wait 1 second between retries, up to 2 retry attempts.
        return new DefaultErrorHandler(new FixedBackOff(1_000L, 2L));
    }

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, String>
            kafkaListenerContainerFactory(
                    ConsumerFactory<String, String> consumerFactory,
                    DefaultErrorHandler commonErrorHandler) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, String>();
        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(commonErrorHandler);
        return factory;
    }
}
```

`FixedBackOff(1_000L, 2L)` means waiting one second between retries and allowing two retries after the initial processing attempt. In total, the listener can be invoked up to three times for a single record delivery if both retries fail.

The `DefaultErrorHandler` bean methods in the subsequent examples represent alternative configurations illustrating individual options. Within a single listener factory, register only the handler matching your actual policy; do not create multiple beans of the same type and inject by type without `@Qualifier`.

Attach the factory to a listener:

```java
@KafkaListener(
        topics = "orders.created",
        groupId = "order-projection",
        containerFactory = "kafkaListenerContainerFactory")
public void onMessage(OrderCreatedEvent event) {
    orderService.process(event);
}
```

When using Spring Boot auto-configuration, you can define a `CommonErrorHandler` bean and customize the factory per your Boot version's conventions. When declaring `ConcurrentKafkaListenerContainerFactory` manually, call `setCommonErrorHandler(...)` explicitly to avoid ambiguity over which factory uses which handler.

## 4. DefaultErrorHandler and Retry/Backoff

`DefaultErrorHandler` handles errors by retrying the record according to a `BackOff`. Once retries are exhausted, it invokes a recoverer to recover the record. If no recoverer is supplied, the handler defaults to logging the failed record after retries run out.

Commonly used backoff types:

| BackOff | Behavior |
| --- | --- |
| `FixedBackOff` | Waits a fixed duration between retry attempts |
| `ExponentialBackOff` | Gradually increases wait time by a multiplier |
| `ExponentialBackOffWithMaxRetries` | Exponential backoff with an explicit maximum retry count |

Exponential backoff example:

```java
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.ExponentialBackOff;

@Bean
public DefaultErrorHandler retryErrorHandler() {
    ExponentialBackOff backOff = new ExponentialBackOff(500L, 2.0);
    backOff.setMaxInterval(5_000L);
    backOff.setMaxElapsedTime(20_000L);

    return new DefaultErrorHandler(backOff);
}
```

Wait time starts at 500 ms, doubles after each retry, and is capped at 5 seconds. `maxElapsedTime` bounds the total backoff duration per `ExponentialBackOff` mechanics; if you want an exact, easy-to-read attempt count, `FixedBackOff` or `ExponentialBackOffWithMaxRetries` is usually clearer.

Retries are blocking retries: the consumer thread remains occupied with the record during retry/backoff. This can temporarily stall partition progress and affect consumer lag. Choose retry counts and wait intervals based on downstream timeouts, `max.poll.interval.ms`, and latency requirements.

## 5. Exception Classification: Which Errors Should Be Retried?

Not every error goes away on retry. For example, a database timeout may be transient; however, a payload with an invalid schema or missing required field typically cannot be fixed by retrying.

`DefaultErrorHandler` provides default exception classifications. Several conversion/deserialization and data-type errors such as `DeserializationException`, `MessageConversionException`, `ConversionException`, `MethodArgumentResolutionException`, `NoSuchMethodException`, and `ClassCastException` are treated as non-retryable by default because retrying the same record usually will not solve the issue.

You can add non-retryable or retryable exceptions:

```java
import org.springframework.dao.TransientDataAccessException;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Bean
public DefaultErrorHandler classifiedErrorHandler() {
    DefaultErrorHandler handler = new DefaultErrorHandler(
            new FixedBackOff(1_000L, 3L));

    handler.addNotRetryableExceptions(
            IllegalArgumentException.class,
            UnsupportedOperationException.class);

    handler.addRetryableExceptions(
            TransientDataAccessException.class);

    return handler;
}
```

In this example, the specified data/logic errors go straight to recovery; transient database errors are retried. Unclassified exceptions continue to follow `DefaultErrorHandler`'s default classification.

When a listener wraps the original exception inside another exception, inspect the cause chain. `DefaultErrorHandler` supports cause-chain exception classification by default; avoid wrapping errors in a way that discards the root cause or collapses all failures into a single generic type.

## 6. Recoverer and DeadLetterPublishingRecoverer

Once retries are exhausted, the recoverer decides what to do with the failed record. A common choice is `DeadLetterPublishingRecoverer`, which uses `KafkaTemplate` to publish the record to a dead-letter topic (DLT).

Example:

```java
import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Bean
public DefaultErrorHandler dltErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(
                    kafkaTemplate,
                    (record, exception) -> new TopicPartition(
                            record.topic() + ".DLT",
                            record.partition()));

    return new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L));
}
```

This example routes a record from `orders.created` partition 1 to `orders.created.DLT` partition 1. The target DLT must exist or be created according to the application's topic management policy, and must have enough matching partitions if preserving the partition index.

With `DeadLetterPublishingRecoverer`'s default constructor, Spring Kafka routes by appending the `.DLT` suffix to the original topic and preserving the original partition. You can replace the resolver to route by exception, tenant, or error category. Decide explicitly when to preserve partitions versus routing to a shared DLT.

The recoverer can add headers describing the exception, stack trace, original topic/partition/offset, and delivery details. Do not log or expose sensitive data in payloads/headers if the DLT is accessible to multiple teams.

If publishing to the DLT fails, the recoverer can throw an exception. In that case, the container must not treat the original record as successfully recovered and silently commit its offset. Monitor DLT publish failures and ensure the DLT producer has serializers compatible with both normal payloads and raw data in case deserialization failed.

## 7. Error Handling in Record Listeners

For a record listener, `DefaultErrorHandler` can retry the failing record and then recover it. Other records in the poll are handled via the container's seek/commit mechanisms.

Listener example:

```java
@KafkaListener(topics = "orders.created", groupId = "order-projection")
public void onMessage(OrderCreatedEvent event) {
    orderService.process(event);
}
```

If `orderService.process` throws an exception, the handler retries according to backoff. If a retry succeeds, the container continues processing. If retries are exhausted, the recoverer publishes the record to the DLT; once recovery completes, the offset can be committed according to the acknowledgment configuration.

Do not catch exceptions and merely log them if you want `CommonErrorHandler` to perform retries. The listener must let the exception propagate or actively use appropriate recovery/acknowledgment APIs.

## 8. Error Handling in Batch Listeners

With a batch listener, one listener invocation receives multiple records. If it simply throws a generic exception, the handler may not know which record in the batch failed and may have to retry the entire batch.

To pinpoint the failing record, throw `BatchListenerFailedException` with the corresponding index:

```java
import java.util.List;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.listener.BatchListenerFailedException;

@KafkaListener(
        topics = "orders.created",
        groupId = "order-batch-projection",
        containerFactory = "batchKafkaListenerContainerFactory")
public void onMessages(List<ConsumerRecord<String, OrderCreatedEvent>> records) {
    for (int index = 0; index < records.size(); index++) {
        try {
            orderService.process(records.get(index).value());
        }
        catch (Exception exception) {
            throw new BatchListenerFailedException(
                    "Cannot process order event",
                    exception,
                    index);
        }
    }
}
```

With `DefaultErrorHandler`, the index lets the container identify records before the failing record that were already processed successfully, commit the appropriate portion, and retry/recover the failing record along with the remaining records. If the failure position cannot be determined, the entire batch may have to be reprocessed.

Batch listeners must design operations to be idempotent because part of a batch may be redelivered after an error. Also verify the transaction and acknowledgment modes in use before combining them with partial batch recovery.

## 9. Seek and Retained Records After an Error

By default, `DefaultErrorHandler` uses seek to return the consumer to the offset that needs reprocessing after an error. Unprocessed records are re-fetched from the broker on the next poll.

Since Spring Kafka 2.9, you can configure `seekAfterError=false` so the container retains unprocessed records in memory and redelivers them after a paused poll to keep the consumer group alive. This avoids manual seeks for the remaining offsets, though records can still be redelivered and must follow the same error policy.

Example:

```java
DefaultErrorHandler handler = new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 2L));
handler.setSeekAfterError(false);
```

Choose between seeking and retaining records based on listener characteristics, batch sizes, and memory management capacity. With large batches or prolonged retries, monitor the volume of records held in the container.

## 10. AckAfterHandle and Committing Offsets After Recovery

`CommonErrorHandler` can finish handling an error and return control to the container. `isAckAfterHandle()` determines whether the container commits the offset when the handler processes an exception without rethrowing it.

`DefaultErrorHandler` enables `ackAfterHandle` by default. When a record is successfully recovered—for instance, successfully published to the DLT—the container can commit the original offset according to AckMode. This allows the group to move forward instead of infinitely re-reading a record already routed to the DLT.

You can change this setting:

```java
handler.setAckAfterHandle(false);
```

Disable this option only when you intentionally want to keep the offset uncommitted after recovery. If you do not understand the consequences, a record already sent to a DLT without advancing the original offset may continue to be re-read. Check the interaction among `AckMode`, manual acknowledgment, transactions, and recovery before changing it.

## 11. Deserialization Errors Occur Before the Listener Is Invoked

Not every exception originates inside a `@KafkaListener` method. If JSON is malformed or the deserializer cannot construct an object, the error happens while the Kafka consumer converts bytes into key/value, before the listener receives a payload.

For these errors, configure `ErrorHandlingDeserializer` wrapping the real deserializer:

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.key.delegate.class]": org.apache.kafka.common.serialization.StringDeserializer
        "[spring.deserializer.value.delegate.class]": org.springframework.kafka.support.serializer.JsonDeserializer
        "[spring.json.value.default.type]": com.example.messaging.OrderCreatedEvent
        "[spring.json.trusted.packages]": com.example.messaging
```

`ErrorHandlingDeserializer` stores the error details so the container/error handler can handle the corrupted record. If you want to publish raw bytes to the DLT, the DLT producer must support both byte arrays and normal payload types, such as by configuring a type-based delegating serializer. Never assume `CommonErrorHandler` can receive a valid DTO when deserialization has failed.

## 12. Retries in CommonErrorHandler vs. Retry Topics

`DefaultErrorHandler` normally performs blocking retries: the failing record is retried on the consumer thread, and the partition may have to wait until retry/recovery finishes.

Spring Kafka also provides a non-blocking retry topic mechanism, typically configured via `@RetryableTopic`. This mechanism forwards failed records to retry topics with dedicated wait intervals, allowing the consumer to continue processing other records on the partition. This is a different retry model from in-place retries in `CommonErrorHandler`.

Avoid configuring both mechanisms to handle the same error without a clear design. Choose:

- Blocking retries via `DefaultErrorHandler` when you want to preserve partition processing flow and offset-based recovery.
- Non-blocking retry topics when you want to decouple wait times from the original partition and accept the corresponding topic and ordering model.

Non-blocking retry topics do not integrate with container transactions. If a flow requires EOS read-process-write semantics, design retries/rollbacks to align with transactions instead of adding `@RetryableTopic` by default.

For a listener container using Kafka transactions, an exception escaping the listener rolls back the transaction. Retrying after a rollback is typically controlled by `DefaultAfterRollbackProcessor`; do not configure an error handler to swallow exceptions and return normally, because the container may commit the transaction instead of rolling back. Design recovery/DLT handling for transactional listeners specifically according to Spring Kafka's transaction guidelines.

## 13. Tracking Delivery Attempts and Retries

`DefaultErrorHandler` supports `RetryListener` to observe each delivery attempt, retry outcome, and recovery. You can use callbacks to emit metrics, log correlation IDs, or send alerts.

Example:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.listener.RetryListener;

handler.setRetryListeners(new RetryListener() {
    @Override
    public void failedDelivery(
            ConsumerRecord<?, ?> record,
            Exception exception,
            int deliveryAttempt) {
        log.warn(
                "Kafka delivery failed: topic={}, partition={}, offset={}, attempt={}",
                record.topic(), record.partition(), record.offset(),
                deliveryAttempt, exception);
    }

    @Override
    public void recovered(
            ConsumerRecord<?, ?> record,
            Exception exception) {
        log.error("Kafka record recovered: topic={}, partition={}, offset={}",
                record.topic(), record.partition(), record.offset(), exception);
    }
});
```

This example assumes the configuration class has a `log` logger. Do not log full payloads if they contain sensitive data. Log the topic, partition, offset, permitted event ID/correlation ID, exception type, and delivery attempt.

Useful operational metrics:

- Retry counts by exception and topic.
- Records recovered or published to the DLT.
- DLT publish failure rate.
- Listener processing time and backoff duration.
- Consumer lag during retries.
- Container stop counts caused by errors.

## 14. When Do You Need CommonDelegatingErrorHandler?

Some applications require different policies per exception. For example, transient database errors are retried, data errors go straight to a DLT, and critical infrastructure errors stop the container.

`CommonDelegatingErrorHandler` lets you choose a handler by exception type. Delegated handlers must share compatible settings for common properties such as `ackAfterHandle` and `seekAfterError`; do not combine handlers with conflicting container behaviors.

For simple classification policies, `DefaultErrorHandler.addRetryableExceptions(...)` and `addNotRetryableExceptions(...)` are usually sufficient. Use a delegating handler only when each error group genuinely needs a different handling strategy.

## 15. Testing CommonErrorHandler

Tests must verify listener retries, recovery, and offset behavior—not merely assert that an exception was logged.

A typical integration test:

1. Create input and DLT topics in the test broker.
2. Configure the listener with `DefaultErrorHandler`, a short backoff, and `DeadLetterPublishingRecoverer`.
3. Send a record for which the listener fails on the first two attempts and succeeds on the next attempt.
4. Assert the listener was invoked the expected number of times and the record did not land in the DLT.
5. Send a permanently failing record and verify that after retries are exhausted, the record appears in the DLT.
6. Verify the consumer group advances past the recovered offset.

Additional cases worth testing:

- Retryable and non-retryable exceptions.
- Batch listener throwing `BatchListenerFailedException` at a specific index.
- Deserialization errors wrapped by `ErrorHandlingDeserializer`.
- DLT producer failure or missing DLT topic.
- `ackAfterHandle` enabled/disabled and `seekAfterError` behavior per configuration.
- Container-stopping handler and behavior after restart.

Use `CountDownLatch`, `BlockingQueue`, or Awaitility to wait for events with a timeout. Avoid short fixed `Thread.sleep` calls because poll, retry, and rebalance timings can vary across runs.

## 16. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Listener retries indefinitely | Unbounded backoff used or no recovery configured | Set explicit retry limits and a recoverer |
| Invalid payload still retried repeatedly | Non-retryable exceptions not classified | Use `addNotRetryableExceptions` or classification |
| Record reprocessed after entering DLT | Offset not committed after recovery or DLT publish did not succeed | Check `ackAfterHandle`, AckMode, and recoverer outcome |
| DLT publish serialization error | DLT producer does not support original payload type or raw bytes | Configure a serializer compatible with all payload types |
| Entire batch retried | Listener did not identify the failing record/index | Throw `BatchListenerFailedException` with the appropriate index |
| Listener not called on malformed JSON | Deserialization failed before listener invocation | Use `ErrorHandlingDeserializer` |
| Partition slows down during retries | Blocking backoff holds consumer thread | Reduce retries/backoff or consider retry topics |
| Handler not applied | Listener factory does not have `setCommonErrorHandler` attached | Check `containerFactory` and bean wiring |
| Error ignored and offset still advances | Listener swallows exception or recovery is treated as successful | Define explicit commit and recovery semantics |

## 17. Conclusion

`CommonErrorHandler` is the unified abstraction for a Spring Kafka listener container to handle exceptions from record listeners and batch listeners. In most cases, `DefaultErrorHandler` provides all necessary features for backoff retries, exception classification, and recovery. It can be paired with `DeadLetterPublishingRecoverer` to forward unprocessable records to a DLT.

Attach the handler to the right listener container factory, distinguish transient errors from permanent data errors, set clear retry limits, and understand how recovery affects seeks and offset commits. For deserialization errors, configure `ErrorHandlingDeserializer`; for batch listeners, identify failing records with `BatchListenerFailedException` whenever possible. A sound error policy keeps the system moving forward while preserving traceability and the ability to replay failed data.

## References

- [Spring for Apache Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring for Apache Kafka — DefaultErrorHandler](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html#default-eh)
- [Spring for Apache Kafka — Dead-Letter Publishing](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html#dead-letters)
- [Spring for Apache Kafka — ErrorHandlingDeserializer](https://docs.spring.io/spring-kafka/reference/kafka/serdes.html#error-handling-deserializer)
