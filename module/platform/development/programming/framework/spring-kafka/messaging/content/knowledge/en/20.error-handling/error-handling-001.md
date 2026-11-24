# Classifying Producer and Consumer Errors

## 1. Why Classify Errors by Where They Occur?

In a Spring Kafka pipeline, the producer and consumer perform two distinct jobs. The producer converts data into a Kafka record and sends the record to the broker. The consumer reads the record, converts the data, and invokes business logic inside the listener. Therefore, errors on the two sides have different causes, retry capabilities, and recovery strategies.

Consider an order creation flow as an example:

- `order-service` sends `OrderCreatedEvent` to the `orders` topic.
- The Kafka broker stores the record and returns the send result to the producer.
- `order-projection` reads the record and updates query-serving data.
- `fraud-monitor` reads the same event in a separate consumer group to assess risk.

If `order-service` fails to send the record, `order-projection`'s listener does not have a record to process yet. The consumer's `DefaultErrorHandler` cannot fix a send error on the producer. Conversely, if the record is already in Kafka but `order-projection` fails to write to its database, the producer should not resend just because one consumer encountered an error.

The first principle is to identify which stage the error occurred in:

~~~mermaid
flowchart TD
    A["Producer application"] --> B["Serialize key/value"]
    B --> C["Send record"]
    C --> D["Kafka broker"]
    D --> E["Consumer poll"]
    E --> F["Deserialize / convert"]
    F --> G["Listener and business logic"]
    G --> H["Commit offset"]

    B --> P1["Producer serialization/config error"]
    C --> P2["Producer send / broker / network error"]
    E --> C1["Consumer fetch / group error"]
    F --> C2["Deserialization / conversion error"]
    G --> C3["Listener / business error"]
    H --> C4["Commit / offset error"]
~~~

Misclassification often leads to futile retries, duplicate event publishing, or lost data.

## 2. Map of Error Categories

| Stage | Error Category | Examples | Primary Handling Location |
|---|---|---|---|
| Producer before sending | Data or configuration | Wrong value type, serializer failure, invalid topic | Publisher, serializer, producer configuration |
| Producer while sending | Transient error | Connection lost, leader change, broker temporarily unavailable | Kafka producer retries and publisher observing the result |
| Producer while sending | Non-retryable error | Missing write permission, record exceeds size limit, misconfiguration | Fix configuration/data or handle operationally |
| Producer awaiting result | Timeout with unknown outcome | Broker may have persisted the record, but acknowledgment did not arrive in time | Publisher, idempotency, and reconciliation |
| Consumer reading data | Infrastructure/group error | Broker disconnection, rebalance, commit failure | Kafka client and listener container |
| Consumer converting | Deserialization/conversion error | Malformed bytes, invalid JSON, incompatible schema | Deserializer, converter, error handler |
| Consumer running listener | Business error | Database temporarily down, API call failure, data rule violation | Listener, retry, recoverer, DLT |
| Consumer confirming | Offset commit error | Commit failure, consumer no longer owns the partition | Listener container and consumer group |

The table classifies errors by the stage where they arise. When troubleshooting an incident, inspect the root cause exception and record context rather than relying solely on the outermost exception class name.

## 3. Producer-Side Errors

The producer can fail before the record leaves the application, during the send process, or while waiting for broker acknowledgment.

### Data and Serialization Errors

Common errors include:

- The publisher passes an object incompatible with the configured serializer.
- The serializer cannot convert the object into bytes.
- Input data is missing a required field or contains an invalid value.
- Record size exceeds the producer, broker, or topic limit.
- Topic name, partition, or security configuration is invalid.

For example, the producer is configured with `StringSerializer`, yet the publisher sends an `OrderCreatedEvent` object directly. This type error will not resolve itself after a few seconds. Retrying the same object with the same configuration will continue to fail.

The proper fix is to verify the generic types of `KafkaTemplate<K, V>`, serializer, payload, record size, topic, and ACLs. Record the error along with the event ID so it can be corrected and replayed in a controlled manner. Do not use retries to mask programming bugs or static misconfigurations.

### Transient Errors While Sending

Some errors can recover on their own:

- Broker temporarily loses connectivity.
- Partition leader is undergoing election.
- Request is interrupted due to network issues.
- Broker temporarily lacks resources or cannot fulfill the request yet.
- Replicas have not yet satisfied the acknowledgment condition configured via `acks`.

The Kafka producer has an internal retry mechanism. Key properties include:

| Property | Role |
|---|---|
| `retries` | Number of times the producer retries certain retryable errors |
| `retry.backoff.ms` | Base wait interval between retry attempts |
| `delivery.timeout.ms` | Maximum total time the producer attempts to complete a send, including queuing and retries |
| `request.timeout.ms` | Time to wait for a response to a single request |
| `acks` | Acknowledgment level the broker must return for a send request |
| `enable.idempotence` | Limits duplicates caused by internal producer retries within Kafka's guarantees |

Spring Boot configuration example:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000
        request.timeout.ms: 30000
        retry.backoff.ms: 1000
~~~

The values above are illustrative only. Choose timeouts based on latency, SLA, broker configuration, and how long the publisher can wait. When idempotence is enabled, the Kafka producer enforces compatibility constraints among `acks`, `retries`, and `max.in.flight.requests.per.connection`; verify the effective configuration of the Kafka client version in use.

Normally, you should let the producer handle retries for transient network/broker errors. Do not wrap every `KafkaTemplate.send()` call in an application-level retry loop without understanding what the producer already retries.

## 4. Producer Timeouts Can Have Unknown Outcomes

A tricky situation occurs when the publisher sends a record but does not receive an acknowledgment before the timeout expires.

There are two possibilities:

1. The broker did not persist the record. Resending may be necessary.
2. The broker persisted the record, but the response was lost or arrived after the producer timed out. Resending at the application layer may create a second record.

Therefore, a timeout does not always mean the record was definitely not written. Treat this as an unknown outcome until a reconciliation mechanism resolves it.

`enable.idempotence=true` protects internal retries within a single producer session using the idempotent producer mechanism. It does not automatically deduplicate every application-level `send()` retry after a timeout, restart, or a new producer request created for the same business event.

To handle this safely:

- Assign a stable `eventId` to the event before the first send attempt.
- Keep this same `eventId` when retrying the same business event.
- Have the consumer use `eventId` to deduplicate when applying side effects.
- For events originating from a database transaction, consider Transactional Outbox to store the intent to publish alongside the business transaction.
- Log the topic, key, event ID, exception, and future result; avoid logging sensitive payloads.

## 5. Observing Send Results with KafkaTemplate

In Spring Kafka 3.x, `KafkaTemplate.send()` returns a `CompletableFuture<SendResult<K, V>>`. The publisher must observe both errors thrown immediately during the call and asynchronous completion errors.

~~~java
import java.util.concurrent.CompletableFuture;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Component;

@Component
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreatedEvent>> publish(
            OrderCreatedEvent event) {

        try {
            return kafkaTemplate.send(
                "orders",
                event.orderId(),
                event
            );
        } catch (RuntimeException ex) {
            // Synchronous error: e.g., configuration or serialization.
            log.error(
                "Failed to initiate send for eventId={}",
                event.eventId(),
                ex
            );
            throw ex;
        }
    }
}
~~~

Observing the asynchronous result:

~~~java
publisher.publish(event)
    .whenComplete((result, error) -> {
        if (error != null) {
            log.error(
                "Failed to send event eventId={}",
                event.eventId(),
                error
            );
            return;
        }

        var metadata = result.getRecordMetadata();
        log.info(
            "Successfully sent event eventId={} topic={} partition={} offset={}",
            event.eventId(),
            metadata.topic(),
            metadata.partition(),
            metadata.offset()
        );
    });
~~~

When the future completes successfully, the producer has received acknowledgment according to the configured `acks`. This does not mean every consumer has processed the record.

Do not swallow exceptions in the callback and treat the send as successful. If the publisher must track delivery state, persist success/failure outcomes to an appropriate store or outbox so it can retry and reconcile after a process restart.

## 6. Consumer-Side Errors

The consumer can fail at multiple stages after a record already exists in Kafka.

### Fetch, Connection, and Consumer Group Errors

Examples:

- The consumer temporarily loses connectivity to the broker.
- The partition leader changes.
- The consumer undergoes a rebalance when group members join or leave.
- Processing a single poll takes too long, exceeding `max.poll.interval.ms`.
- Offset commit fails because the consumer no longer owns the partition or the group is rebalancing.

These are primarily client, connection, and group-coordination errors. The Kafka consumer and listener container have mechanisms to manage polling, heartbeats, assignments, and commits. Do not catch all infrastructure exceptions and send the record to a DLT as if the payload were invalid.

When investigating, check consumer lag, partition assignment, rebalances, listener execution time, `max.poll.interval.ms`, broker health, and consumer logs.

### Deserialization Errors

These occur when the Kafka client cannot convert bytes into the key/value types requested by the consumer. Examples:

- The producer sends JSON, but the consumer uses `IntegerDeserializer`.
- Bytes are corrupted or the payload is malformed.
- The consumer uses the wrong schema or type mapping configuration.
- A tombstone record has a `null` value, while the application assumes a payload is always present.

Deserialization errors can occur right inside `poll()`, before the listener is invoked. Therefore, if you want a Spring Kafka error handler to handle this type of error, you typically need to wrap the delegate with `ErrorHandlingDeserializer`.

Example of a consumer using `JsonDeserializer` as the delegate:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.events.OrderCreatedEvent
        spring.json.trusted.packages: com.example.events
~~~

`ErrorHandlingDeserializer` preserves the deserialization error details so Spring Kafka can route the error to the container's appropriate handling mechanism. Configure the delegate, type mapping, and trusted packages strictly according to the contract. Do not widen trusted packages for data from untrusted sources just to make errors go away.

If the consumer uses `StringDeserializer` together with `StringJsonMessageConverter`, JSON parsing errors happen during message conversion, after the Kafka client has already produced a `String`. Distinguish client-level deserialization errors from listener-adapter JSON-to-object conversion errors.

### Message Conversion and Validation Errors

Some records deserialize successfully but still cannot be converted into listener parameters:

- Syntactically valid JSON cannot be mapped into the Java type.
- Required headers or type metadata are missing.
- Field types are incompatible with the event class.
- Validation detects missing data or rule violations.

Conversion errors typically occur along the listener adapter invocation path. Validation errors may originate in the listener or a business service. Record the error type and event ID to determine whether the record can be repaired, needs to go to a DLT, or requires a contract change.

### Business Errors in the Listener

Examples:

- The database is temporarily unreachable.
- A downstream API returns HTTP 503.
- A dependent service is rate-limiting requests.
- Data is valid, but the business state does not yet allow processing at this moment.
- The record cannot be processed due to missing data or a permanent rule violation.

Not all listener errors share the same retry policy. A temporary database outage can be retried after a backoff; a schema-invalid payload may never succeed without changing the data or code. Distinguish transient errors from errors that cannot be recovered via retry.

## 7. Classifying Consumer Errors by Recoverability

| Error Type | Examples | Retry? | Action After Retries Exhausted |
|---|---|---|---|
| Transient infrastructure error | Database timeout, HTTP 503 | Yes, with backoff and limit | DLT or recovery workflow / wait for dependency |
| Rate-limiting error | HTTP 429 | Yes, honoring `Retry-After` if present | DLT or delayed retry topic |
| Invalid payload error | Malformed JSON, missing required field | Usually no blind retry | DLT for investigation |
| Contract/schema error | Unsupported version | Only retry after compatible code/schema is deployed | DLT or pause per policy |
| Authentication/authorization error | Invalid credentials, missing ACL | Do not retry continuously | Fix secret/ACL, then recover |
| Programming error | `NullPointerException`, mapping bug | Do not retry indefinitely | DLT/pause, fix code, and replay |
| Commit/rebalance error | Commit failed when group changed assignment | Let container/client manage; assess redelivery | Monitor rebalances and offsets |

This table is a guideline only. A single exception class can represent multiple causes; for example, `DataAccessException` could be a transient connection error or a permanent constraint violation. Classify based on the root cause and operation type, not merely on a broad exception class.

## 8. Retry and Dead Letter on the Consumer Side

For a record listener, Spring Kafka can use `DefaultErrorHandler` to retry failed records with a backoff. Once retries are exhausted, a recoverer can forward the record to a dead-letter topic (DLT).

The error handler bean must be attached to the container factory used by the listener. Factory example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.DefaultErrorHandler;

@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>
        orderKafkaListenerContainerFactory(
                ConsumerFactory<String, OrderCreatedEvent> consumerFactory,
                DefaultErrorHandler kafkaErrorHandler) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(kafkaErrorHandler);
    return factory;
}
~~~

The listener must specify `containerFactory = "orderKafkaListenerContainerFactory"`, or configure the error handler on the default factory the listener uses. Ensure the factory and the DLT template use serializers compatible with the actual key/value types.

~~~java
import org.apache.kafka.common.TopicPartition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
public class KafkaConsumerErrorConfiguration {

    @Bean
    DefaultErrorHandler kafkaErrorHandler(
            KafkaTemplate<Object, Object> dltKafkaTemplate) {

        var recoverer = new DeadLetterPublishingRecoverer(
            dltKafkaTemplate,
            (record, exception) ->
                new TopicPartition(
                    record.topic() + ".DLT",
                    record.partition()
                )
        );

        var handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1000L, 2L)
        );

        // Data errors where retrying is futile are marked as non-retryable.
        handler.addNotRetryableExceptions(
            IllegalArgumentException.class
        );

        return handler;
    }
}
~~~

`FixedBackOff(1000L, 2L)` means waiting one second between retries, up to two additional retry attempts after the initial processing attempt. `IllegalArgumentException` in the example is treated as a non-retryable error; only apply this classification if the application guarantees that the exception truly denotes unprocessable data.

For the recoverer to send the record to the same partition number, the DLT topic must have enough corresponding partitions and be created/configured beforehand. If partition mapping cannot be guaranteed, choose the target partition with an appropriate strategy rather than assuming the DLT always has a matching partition.

The producer used to publish to the DLT must be able to serialize failed records as well. In particular, a deserialization error can leave the original value as a byte array while normal records are Java objects. When a single DLT template must accept multiple value types, configure a compatible serializer, such as a type-delegating serializer; do not assume `KafkaTemplate<Object, Object>` automatically handles every data type.

For deserialization errors, verify that the DLT actually preserves the raw key/value and exception metadata. If DLT publishing fails, the error handler must not silently treat the record as recovered. Configure and test commit/recovery behavior according to the Spring Kafka version in use.

## 9. Why Producer Retries and Consumer Retries Do Not Replace Each Other

| Criterion | Producer Retry | Consumer Retry |
|---|---|---|
| Goal | Persist the record into Kafka according to producer policy | Process a record that has already been read successfully |
| Execution location | Kafka producer client | Spring Kafka listener container/error handler or retry topic |
| Typical errors | Network, leader unavailable, transient broker errors | Database errors, downstream API errors, listener exceptions |
| Retry unit | A single record send | Processing a single record or batch |
| Final outcome | Send future succeeds or fails | Listener succeeds, record is recovered/DLT'd, or continues failing |
| Does not solve | Consumer-side business errors | Records never written to Kafka by the producer |

For example, the producer sends `OrderCreatedEvent` successfully, and later the consumer fails to update its database. The producer does not need to resend the event just because the consumer's database is down. The consumer error handler must retry processing that record.

Conversely, if the producer cannot send the record due to a serialization error, the consumer cannot retry because the record was never written to the topic.

If the publisher receives a timeout with an unknown outcome and decides to resend, it may create a duplicate. The consumer still needs idempotency via `eventId` even when producer idempotence is enabled.

## 10. Logs and Metadata Needed for Error Investigation

Kafka error logs need sufficient context to locate the record and identify the responsible component.

| Field | Meaning |
|---|---|
| `event-id` | Business event identifier |
| `topic` | Related topic |
| `partition` | Record partition |
| `offset` | Record position |
| `key` | Key if non-sensitive |
| `consumer-group` | Group currently processing |
| `exception-class` | Exception type |
| `root-cause` | Safely truncated root cause |
| `attempt` | Retry count or attempt number |
| `correlation-id` / `traceparent` | Correlates logs and distributed traces |

Do not log full payloads, tokens, personal data, or binary document contents. For a producer that has no Kafka offset because the send failed, log the event ID, target topic, key, future status, and exception. Never fabricate an offset when the broker has not acknowledged the write.

Use metrics to monitor:

- Producer send success/failure counts.
- Timeout, retry, and rejected-record rates.
- Consumer lag by group and partition.
- Listener exception counts by type.
- Retry counts and records sent to the DLT.
- DLT ingress and processing rates.
- End-to-end latency from event creation until each consumer completes.

## 11. Testing Error Classification

Tests should verify that errors are handled on the right side and under the right policy, rather than only checking that an exception was thrown.

| Scenario | What to Verify |
|---|---|
| Producer passes wrong type to serializer | Send fails; consumer listener is not invoked |
| Broker temporarily unavailable | Producer retries per configuration and future reflects final outcome |
| Producer times out after sending | Application recognizes the unknown outcome and does not auto-generate a new event ID |
| Consumer deserialization fails | Listener does not receive an invalid object; error handling preserves error details |
| Listener encounters database timeout | Retries with finite backoff |
| Listener encounters malformed payload | Does not retry indefinitely; record is recovered per policy |
| DLT publish fails | Recovery is not inadvertently recorded as successful |
| Consumer finishes processing but stops before commit | Record may be redelivered and side effects must be idempotent |

You can use Embedded Kafka or Testcontainers to test paths through the broker. Use distinct topics and group IDs per test, and wait using Awaitility or polling with a timeout instead of fixed `Thread.sleep()`.

For the producer, check the `CompletableFuture` and returned metadata. For the consumer, check listener invocation counts, committed offsets, DLT records, and database effects. Do not conclude the producer succeeded simply because `KafkaTemplate.send()` returned a future; wait for the future to complete in tests.

## 12. Practical Incident Investigation Workflow

When the system reports a Kafka error, you can follow this sequence:

1. **Determine whether the record was sent by the producer.** Check the send future, producer logs, topic, and event ID.
2. **If the producer failed, distinguish permanent from transient errors.** Check serializer, ACLs, topic, record size, broker/network, and timeouts.
3. **If the record is already in the topic, inspect the consumer group.** Check assignment, lag, polls, rebalances, and committed offsets.
4. **Determine whether the error occurred before or inside the listener.** Check deserializer, converter, argument binding, and stack trace.
5. **Classify the listener error.** Determine whether it is a transient dependency error, invalid data, or a code bug.
6. **Verify retry/recovery.** Confirm backoff, attempt count, DLT routing, and whether DLT publishing succeeded.
7. **Reconcile business impact.** Check event IDs, database state, and duplicate-handling capability before replaying.
8. **Monitor post-recovery.** Confirm lag decreases, the DLT is processed, and producer/consumer operate normally.

Do not delete or reset offsets just to clear a lag alert without identifying which records have not been processed. Resetting offsets can skip data or trigger reprocessing of a large volume of records.

## 13. Producer and Consumer Error Classification Checklist

- [ ] Identify whether the error occurs before send, during send, on poll, during deserialization, inside the listener, or during commit.
- [ ] Distinguish static configuration/data errors from transient infrastructure errors.
- [ ] Let the Kafka producer handle internal retries for retryable send errors.
- [ ] Observe the `CompletableFuture` returned by `KafkaTemplate.send()`.
- [ ] Treat producer timeouts as potentially unknown outcomes; never assume the record was not written.
- [ ] Keep `eventId` stable when retrying the same event.
- [ ] Use `ErrorHandlingDeserializer` when deserialization errors must enter Spring Kafka's error handling flow.
- [ ] Configure `DefaultErrorHandler`, backoff, and recoverer according to listener error types.
- [ ] Ensure the DLT has appropriate partitions and a serializer compatible with failed records.
- [ ] Do not use producer retries to solve consumer business errors, or vice versa.
- [ ] Design idempotent consumers to tolerate redelivered records.
- [ ] Track event ID, topic, partition, offset, group, retries, and DLT.

Properly classifying producer and consumer errors helps you choose the right place to retry and recover. The producer is responsible for getting records into Kafka and reporting send outcomes; the consumer is responsible for reading, converting, executing business logic, and acknowledging offsets. Separating these responsibilities—combined with timeout awareness, bounded retries, DLTs, and idempotency—makes Spring Kafka pipelines much easier to investigate and recover.
