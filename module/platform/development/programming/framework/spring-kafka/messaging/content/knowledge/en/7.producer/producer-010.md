# Send Errors and Retry Capability

## 1. Why can a Kafka send operation fail?

When an application calls `KafkaTemplate.send(...)`, the producer must convert the key and value into bytes, fetch topic metadata, place the record into its buffer, send a request to the broker, and await acknowledgement according to the `acks` setting. Any of these steps can fail.

Some common causes:

| Cause category | Example | Resolution |
|---|---|---|
| Connectivity and broker | Broker connection lost, partition leader changing, request timeout | Check cluster and network, and let the producer retry within configured limits |
| Configuration and permissions | Wrong broker address, missing topic write permission, authentication error | Fix configuration or permissions; continuous retries will not resolve permanent errors |
| Data and serialization | Serializer does not support object type, malformed payload | Fix serializer or data before sending |
| Resource limits | Record exceeds size limit, producer buffer full | Check record size, broker limits, and producer load |
| Record acknowledgement | Insufficient replicas in ISR to satisfy `acks=all` | Check replication factor, ISR, and `min.insync.replicas` |

Not every error can be resolved by resending. Transient connectivity errors may disappear after a short wait; serializer, permission, or wrong-topic errors will continue failing until configuration or data is fixed.

## 2. Distinguishing synchronous and asynchronous errors

In Spring Kafka 3.x, `KafkaTemplate.send(...)` returns `CompletableFuture<SendResult<K, V>>`. However, calling `send` can still throw an error immediately on the current thread, such as when metadata cannot be fetched in time or the producer cannot accept the record. Once the call returns a future, errors from the send process are usually reported via the future's exceptional state.

Therefore, observe both error paths:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.kafka.support.SendResult;

public void publish(OrderCreatedEvent event) {
    CompletableFuture<SendResult<String, OrderCreatedEvent>> future;

    try {
        future = kafkaTemplate.send("orders", event.orderId(), event);
    } catch (RuntimeException ex) {
        // Error occurred immediately when calling send().
        log.error("Cannot initiate Kafka send operation", ex);
        throw ex;
    }

    future.whenComplete((result, error) -> {
        if (error != null) {
            log.error("Failed to send event", error);
            return;
        }

        var metadata = result.getRecordMetadata();
        log.info(
            "Successfully sent topic={}, partition={}, offset={}",
            metadata.topic(),
            metadata.partition(),
            metadata.offset()
        );
    });
}
~~~

A future completing successfully means the producer received an acknowledgement according to the `acks` configuration. It does not mean a consumer has received or finished processing the event. Sending and consuming are two separate processes with their own confirmation mechanisms.

If you merely call `send(...)` and ignore the future, the application may fail to observe errors that occur afterward. For important events, there must be a place that records the outcome, measures metrics, and decides how to handle send failures.

## 3. Producer automatic retries at the Kafka client layer

The Kafka producer has a retry mechanism for errors the client considers retriable, such as certain network errors, transient leader errors, or replica acknowledgement failures. The producer can resend the request within the allowed time window without the application calling `KafkaTemplate.send(...)` again.

Commonly used properties:

| Property | Meaning |
|---|---|
| `retries` | Limits how many times the producer retries retriable errors; the effective limit is also bounded by delivery timeout |
| `delivery.timeout.ms` | Maximum total time for the producer to complete sending, including metadata wait, send time, and retries |
| `request.timeout.ms` | Time to wait for a response to a request sent to a broker |
| `retry.backoff.ms` | Initial wait interval between retry attempts |
| `retry.backoff.max.ms` | Upper bound for the retry wait interval when the client supports exponential backoff |
| `acks` | Acknowledgement level the producer requires from the broker |
| `enable.idempotence` | Enables producer idempotence to prevent duplicate writes from internal producer retries |

Can be configured in `application.yml`:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      acks: all
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000
        request.timeout.ms: 30000
        retry.backoff.ms: 500
        retry.backoff.max.ms: 10000
        linger.ms: 5
~~~

`delivery.timeout.ms` must be greater than or equal to the sum of `request.timeout.ms` and `linger.ms`. If the delivery timeout is set too short, the producer may expire before retry attempts have enough time to recover the connection or wait for the broker to stabilize.

With modern Kafka clients, `enable.idempotence` is typically enabled by default when related settings are compatible. Declaring it explicitly makes configuration intent clearer. When idempotence is enabled, the producer requires compatible conditions such as `acks=all`, `retries` greater than 0, and `max.in.flight.requests.per.connection` not exceeding Kafka's supported limit (currently 5). Modern Kafka clients validate or adjust these constraints automatically depending on the version.

`acks=all` instructs the leader to wait for replicas currently in the ISR to acknowledge. It does not mean every replica of the topic must respond. Data durability protection also depends on replication factor and `min.insync.replicas`.

### Internal retries do not mean infinite retries

The producer only retries within the bounds of `delivery.timeout.ms` and request conditions. When time runs out, the future completes with a failure. A large retry configuration does not bring a down broker back online; it only gives the producer more opportunity to ride out transient failures.

Do not set arbitrarily huge timeouts. Long timeouts increase how long applications wait for results and can hold records in the buffer longer. Choose timeouts based on delivery SLAs, cluster recovery capability, and the latency your business logic tolerates.

## 4. How does producer idempotence make retries safer?

When the broker has written a record but the acknowledgement is lost on the return path, the producer may not know for certain whether the record was written. If it resends, the same record risks appearing twice.

Producer idempotence uses a producer ID and sequence numbers so the broker can recognize resends belonging to the same producer session. When configured properly, Kafka can deduplicate records arising from those internal retries within the guarantees of producer idempotence.

However, idempotence does not automatically deduplicate records caused by the application calling `send(...)` a second time. Two separate send calls are treated as two distinct send operations, even if their payloads are identical.

Distinguish clearly:

| Situation | How does producer idempotence handle it? |
|---|---|
| Producer internally resends a request due to network error within the same producer session | Can prevent duplicate writes via sequence numbers |
| Application calls `send` a second time after the first future fails or times out | Does not automatically recognize it as the same business event |
| Application restarts and replays events from the database | Does not automatically deduplicate by business event ID |
| Consumer processes a record, fails to commit offset, and receives the record again | Outside the guarantee scope of producer idempotence |

For critical business events, assign a unique `eventId` and design an idempotent consumer. The consumer can persist the processed `eventId` together with the business outcome in an appropriate transaction to skip redeliveries.

## 5. When are application-layer retries needed?

Internal producer retries are usually the first line of defense because they operate within a single send attempt. Application-layer retries should only be added when business logic requires a dedicated policy, for example:

- Wanting a retry limit different from the producer's global policy.
- Needing custom backoff, jitter, or wait times per event type.
- Needing to record failed send state for operations or reprocessing.
- Needing to route the event to a separate recovery flow after exhausting attempts.

Before retrying, classify the error:

| Error type | Example | Should you resend automatically? |
|---|---|---|
| Transient, recoverable error | Certain network errors or leader changes | Possibly, with bounds and backoff |
| Uncertain outcome | Timeout where the broker may have written the record but acknowledgement did not arrive | Only if duplicates are acceptable and an idempotent mechanism is in place |
| Data error | Serialization failure, record too large | No; fix data or configuration first |
| Permission or static configuration error | Authentication/authorization failure, wrong topic | No; fix root cause first |
| Business error | Data invalid per business rules | No; fix data or route to a dedicated business workflow |

A timeout must be examined carefully: the producer may have written the record even though the application did not receive an acknowledgement. If the application resends immediately, the event may be written twice. Do not treat every failed future as proof that the broker did not receive the record.

### Example of bounded retries with Spring Retry

When business rules tolerate potential duplicate sends and the consumer already has an idempotent mechanism, you can use Spring Retry's `RetryTemplate` to add application-layer retries. The following example only retries errors explicitly classified as transient; timeout errors with unknown outcomes are thrown separately to follow a different policy.

Requires the `org.springframework.retry:spring-retry` dependency:

~~~java
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.support.RetryTemplate;

@Configuration
public class ProducerRetryConfiguration {

    @Bean
    RetryTemplate producerRetryTemplate() {
        var retryPolicy = new SimpleRetryPolicy(
            3,
            Map.of(TransientPublishException.class, true),
            false
        );

        var backOffPolicy = new ExponentialBackOffPolicy();
        backOffPolicy.setInitialInterval(200);
        backOffPolicy.setMultiplier(2.0);
        backOffPolicy.setMaxInterval(2000);

        var template = new RetryTemplate();
        template.setRetryPolicy(retryPolicy);
        template.setBackOffPolicy(backOffPolicy);
        return template;
    }
}
~~~

In this configuration, `maxAttempts = 3` includes the initial call, meaning at most two additional retries. `SimpleRetryPolicy` only accepts `TransientPublishException`, so other errors are not retried automatically.

Dedicated exceptions to represent errors permitted by the retry policy:

~~~java
public class TransientPublishException extends RuntimeException {

    public TransientPublishException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class PublishOutcomeUnknownException extends RuntimeException {

    public PublishOutcomeUnknownException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

The synchronous send method below illustrates waiting for the result and translating errors into the appropriate exception types. Place this method on a worker thread or background processing thread because `get()` blocks the current thread:

~~~java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.apache.kafka.common.errors.RetriableException;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.retry.support.RetryTemplate;
import org.springframework.stereotype.Component;

@Component
public class RetryingOrderPublisher {

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;
    private final RetryTemplate producerRetryTemplate;

    public RetryingOrderPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate,
            RetryTemplate producerRetryTemplate) {
        this.kafkaTemplate = kafkaTemplate;
        this.producerRetryTemplate = producerRetryTemplate;
    }

    public SendResult<String, OrderCreatedEvent> publish(
            String topic,
            OrderCreatedEvent event) {

        return producerRetryTemplate.execute(context -> {
            try {
                return kafkaTemplate.send(
                    topic,
                    event.orderId(),
                    event
                ).get(15, TimeUnit.SECONDS);

            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                    "Kafka send thread interrupted", ex
                );

            } catch (TimeoutException ex) {
                throw new PublishOutcomeUnknownException(
                    "Timed out waiting; unknown whether broker wrote the record",
                    ex
                );

            } catch (ExecutionException ex) {
                Throwable cause = ex.getCause();

                if (cause instanceof org.apache.kafka.common.errors.TimeoutException) {
                    throw new PublishOutcomeUnknownException(
                        "Producer timeout; check for duplicate write risk before resending",
                        cause
                    );
                }

                if (cause instanceof RetriableException) {
                    throw new TransientPublishException(
                        "Encountered retriable Kafka error", cause
                    );
                }

                throw new IllegalStateException(
                    "Kafka send error cannot be retried automatically", cause
                );
            }
        });
    }
}
~~~

This example has an important design intent: only `TransientPublishException` is retried by `RetryTemplate`. `PublishOutcomeUnknownException` is excluded from the retry policy. In practice, check the exact error type, Kafka client version, and broker situation to decide whether an error is safe to resend. Even a retriable error may have an uncertain write outcome; therefore, only enable application retries when business logic tolerates duplicates or has deduplication by `eventId`.

`RetryTemplate` runs synchronously and holds the thread while waiting. Under high traffic, consider a worker queue, scheduler, or stateful background sender instead of blocking request threads.

## 6. Backoff and retry limits

If retries fire continuously right as errors happen, multiple producers can flood an already overloaded broker with requests. This phenomenon increases pressure and prolongs recovery time.

Exponential backoff progressively increases the wait interval between attempts:

| Attempt | Illustrative wait interval |
|---:|---:|
| 1 | 200 ms |
| 2 | 400 ms |
| 3 | 800 ms |
| 4 | 1,600 ms |

You can add jitter (a small random offset) so instances do not all retry at the exact same moment. Set limits on attempt count, total retry duration, and the policy once attempts are exhausted.

A retry policy must answer:

- Which errors are retried?
- What is the maximum number of attempts?
- How does the wait interval grow?
- What is the maximum total duration?
- How are uncertain timeout outcomes handled?
- Once attempts are exhausted, where is the event stored so it is not lost?
- Who or which component is responsible for reprocessing?

Do not retry infinitely on a request thread. That can exhaust thread pools, tie up resources, and prevent the system from recovering smoothly during prolonged broker outages.

## 7. What to do when retries are exhausted?

When a producer cannot send an event after all attempts, the application needs a final fallback policy. For non-critical events, logging and returning an error to the calling flow may suffice. For critical business events, merely logging is usually not enough because the application may lose the opportunity to resend once the process terminates.

Several handling approaches:

| Handling approach | Suitable when |
|---|---|
| Return error to caller | The caller can hold the request and decide to retry |
| Persist failure state in the database | Lookup, operational support, and reprocessing are needed |
| Transactional Outbox | The intent to publish the event must be persisted alongside the database update transaction |
| Dedicated recovery queue | The system has durable storage for a worker to reprocess later |
| Drop event after recording | Only suitable for events that can be lost under agreed business requirements |

### Transactional Outbox for critical events

A common scenario is an application updating an order in the database and emitting `OrderCreated` to Kafka. If the database commits successfully but the Kafka send fails, the order state and event stream diverge.

Transactional Outbox solves this by writing business data and an outbox record within the same database transaction. A separate worker reads the outbox, sends the event to Kafka, and marks the record as published. If Kafka is temporarily down, the worker can keep retrying once the system recovers.

~~~mermaid
flowchart TD
    A["Application service"] --> B["Database transaction"]
    B --> C["Update order"]
    B --> D["Insert outbox event"]
    C --> E["Commit"]
    D --> E
    E --> F["Outbox publisher"]
    F --> G["KafkaTemplate"]
    G --> H["Kafka topic"]
    H --> I["Mark outbox as published"]
~~~

An Outbox does not completely eliminate duplicate sends: the worker could send successfully and crash before marking the outbox record. Therefore, an outbox publisher usually delivers with at-least-once semantics and consumers still need idempotency by `eventId`.

## 8. Producer failures vs. consumer failures and dead-letter topics

Distinguish where the failure occurs:

- **Producer failure:** the application has not confirmed that the record was written by Kafka. There is no input record in Kafka for the framework to automatically route to a dead-letter topic.
- **Consumer failure:** the record is already in a topic, but the listener fails to process it. Spring Kafka can use an error handler, retry topic, or dead-letter publishing to handle failed records per configuration.
- **Business rejection:** the data was read, yet it is invalid according to business rules. This may be a business outcome to record separately, not necessarily a Kafka send failure.

Consequently, do not use `DeadLetterPublishingRecoverer` or `@RetryableTopic` as the default mechanism to retry a failed producer send. For producer failures, use producer retries, application-layer retry policies, and durable storage like an outbox when needed.

## 9. Observing send failures in Spring Kafka

In addition to future callbacks, Spring Kafka provides `ProducerListener` to receive notifications when sends succeed or fail. You can use this listener for centralized logging or metrics updates:

~~~java
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.clients.producer.RecordMetadata;
import org.springframework.kafka.core.ProducerListener;

public class LoggingProducerListener
        implements ProducerListener<String, OrderCreatedEvent> {

    @Override
    public void onSuccess(
            ProducerRecord<String, OrderCreatedEvent> record,
            RecordMetadata metadata) {
        log.info(
            "Kafka send success topic={}, partition={}, offset={}",
            metadata.topic(),
            metadata.partition(),
            metadata.offset()
        );
    }

    @Override
    public void onError(
            ProducerRecord<String, OrderCreatedEvent> record,
            RecordMetadata metadata,
            Exception exception) {
        log.error(
            "Kafka send failed topic={}, key={}",
            record.topic(),
            record.key(),
            exception
        );
    }
}
~~~

Register the listener on the template via Spring configuration or by calling `kafkaTemplate.setProducerListener(...)` when creating the template. `ProducerListener` works well for general logging and metrics. If a business flow needs to decide whether to return an error to the caller, save to an outbox, or mark status, observe the future at the call site and pass the result back to the proper application service.

At minimum, monitor:

- Count of records sent successfully and failed.
- Retry count and post-retry failure rate.
- Latency from calling send to receiving acknowledgement.
- Timeouts, serialization errors, authentication errors, and broker errors.
- Count of pending outbox records and age of the oldest pending record.
- Duplicate rate detected by consumers if deduplication is in place.

Do not log sensitive payloads merely to investigate errors. Prefer `eventId`, correlation ID, topic, permitted keys, partition, and error codes.

## 10. Producer retry design checklist

- [ ] Both synchronous errors on calling `send()` and asynchronous errors from the future are observed.
- [ ] `acks`, idempotence, and delivery timeouts are configured to match requirements.
- [ ] The bounds of `delivery.timeout.ms` and `request.timeout.ms` are understood.
- [ ] Errors are classified into transient, permanent, and uncertain timeout outcomes.
- [ ] Internal producer retries are used before adding application-layer retries.
- [ ] Application retries are bounded, use backoff, and apply only to selected errors.
- [ ] Consumers have idempotency mechanisms when business flows may receive duplicate events.
- [ ] Critical events have durable persistence, such as a Transactional Outbox.
- [ ] Producer failures are not confused with consumer failures and dead-letter topics.
- [ ] Logs, metrics, and alerts are in place when send errors or outbox backlog rise.

Retry capability helps a producer ride out transient failures, but it cannot replace durable storage design and duplicate handling. In Spring Kafka, start with the Kafka producer's internal retries, observe outcomes via futures, add application-layer retries only when governed by a clear policy, and use a Transactional Outbox for events that must never be lost.
