# KafkaTemplate and Messaging Abstraction Layer

## 1. Where does KafkaTemplate sit in the messaging architecture?

In Spring Kafka, `KafkaTemplate` is the high-level API for an application to send records to Kafka. Instead of manually creating and managing a Kafka producer for every send, the application injects a `KafkaTemplate<K, V>` bean and calls its send methods.

`KafkaTemplate` works with `ProducerFactory`. The producer factory creates and manages Kafka producers based on bootstrap server configuration, serializers, security, and other producer properties. As a result, business code focuses on the event to be sent; communication with Kafka is handled by Spring Kafka.

The sending flow typically looks like this:

~~~mermaid
flowchart LR
    A["Application service"] --> B["Event publisher port"]
    B --> C["Kafka adapter"]
    C --> D["KafkaTemplate"]
    D --> E["ProducerFactory"]
    E --> F["Kafka broker"]
    F --> G["Broker acknowledgement"]
    G --> D
    D --> C
    C --> B
~~~

In this architecture, the application service issues a request to publish an event through an application interface. The adapter implements that interface using `KafkaTemplate`. When Kafka needs to be swapped for another messaging mechanism, the business layer keeps the same interface and event contract.

`KafkaTemplate` is suitable for both simple send operations and cases requiring control over key, partition, timestamp, headers, callbacks, or Kafka transactions.

## 2. Configuring KafkaTemplate and Serializers

With Spring Boot, when the Spring Kafka dependency and valid producer configuration are present, the application typically auto-configures `ProducerFactory` and `KafkaTemplate`. Basic properties can be declared in `application.yml`:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      acks: all

app:
  kafka:
    topics:
      orders: orders
~~~

In the example:

- `bootstrap-servers` specifies the Kafka broker addresses.
- `key-serializer` converts `String` keys into bytes for the producer to write to Kafka.
- `value-serializer` converts event objects into bytes. Spring Kafka's `JsonSerializer` supports serializing Java objects into JSON.
- `acks: all` requires the producer to wait for acknowledgement from replicas currently in the ISR set according to Kafka's rules. Actual durability also depends on the replication factor and the topic/broker `min.insync.replicas` configuration.
- `app.kafka.topics.orders` is an application property so the adapter knows which business topic to send to.

The generic types of the template must match the serializers. For example, `KafkaTemplate<String, OrderCreatedEvent>` uses key `String` and value `OrderCreatedEvent`; if the configured serializers cannot convert those types, the send operation will fail.

Do not create a new `KafkaTemplate` for each record. Use the bean configured and managed by Spring to reuse the producer factory, configuration, and connection resources.

## 3. Common Ways to Send Records

`KafkaTemplate` provides multiple overloads to choose the appropriate level of control.

| Call | Meaning |
|---|---|
| `send(topic, value)` | Sends value to topic without specifying a key |
| `send(topic, key, value)` | Sends a record with a key so the partitioner selects a partition |
| `send(topic, partition, key, value)` | Specifies the target partition |
| `send(topic, partition, timestamp, key, value)` | Specifies both partition and timestamp |
| `send(ProducerRecord)` | Constructs a record manually for fuller control |
| `send(Message<?>)` | Sends a Spring Message and maps payload/headers to a Kafka record |
| `sendDefault(...)` | Sends to the default topic configured for the template |

Example of sending a simple object:

~~~java
OrderCreatedEvent event = new OrderCreatedEvent(
    "ORD-1001",
    "CUS-42",
    System.currentTimeMillis()
);

kafkaTemplate.send("orders", event);
~~~

If you want events for the same order to be routed consistently, use the order ID as the key:

~~~java
kafkaTemplate.send("orders", event.orderId(), event);
~~~

When no partition is specified, the partitioner uses the key and related configuration to select a partition. When a partition is explicitly specified, the record goes to that partition instead of letting the partitioner choose. Only pin a partition when there is a clear routing requirement.

### Using ProducerRecord for Header Control

`ProducerRecord<K, V>` represents a record sent to Kafka, containing topic, optional partition, optional timestamp, key, value, and headers. When you need to attach a correlation ID or application metadata, you can construct the record directly:

~~~java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.clients.producer.ProducerRecord;

ProducerRecord<String, OrderCreatedEvent> record =
    new ProducerRecord<>("orders", event.orderId(), event);

record.headers().add(
    "correlation-id",
    correlationId.getBytes(StandardCharsets.UTF_8)
);

kafkaTemplate.send(record);
~~~

Headers are suitable for passing metadata for tracing, correlation, or event classification. Avoid putting core business data into headers if consumers need it as part of the payload.

### Using Spring Message

If the application already uses Spring Messaging, you can use `MessageBuilder` and Kafka headers:

~~~java
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<OrderCreatedEvent> message = MessageBuilder
    .withPayload(event)
    .setHeader(KafkaHeaders.TOPIC, "orders")
    .setHeader(KafkaHeaders.MESSAGE_KEY, event.orderId())
    .setHeader("correlation-id", correlationId)
    .build();

kafkaTemplate.send(message);
~~~

This approach is useful when leveraging the Spring message model. For simple sending flows, the `send(topic, key, value)` overload is usually more readable.

## 4. Asynchronous Sending and Result Handling

Sending records to Kafka is normally an asynchronous operation. In Spring Kafka 3.x, `send(...)` methods return `CompletableFuture<SendResult<K, V>>`. The future completes when the producer receives the send result according to the configured acknowledgement policy, or when the operation fails.

You can register a callback using `whenComplete`:

~~~java
import org.apache.kafka.clients.producer.RecordMetadata;
import org.springframework.kafka.support.SendResult;

kafkaTemplate.send("orders", event.orderId(), event)
    .whenComplete((result, error) -> {
        if (error != null) {
            log.error("Failed to send order event", error);
            return;
        }

        RecordMetadata metadata = result.getRecordMetadata();
        log.info(
            "Sent topic={}, partition={}, offset={}",
            metadata.topic(),
            metadata.partition(),
            metadata.offset()
        );
    });
~~~

`SendResult` provides the sent record and `RecordMetadata` returned by Kafka. The metadata identifies which topic, partition, and offset the record was written to.

Three milestones should be distinguished:

1. The application calls `send(...)`: the send request has been created.
2. The future completes successfully: the producer has received acknowledgement according to the `acks` configuration.
3. The consumer finishes processing the event: this is a separate progress of the consumer group, not guaranteed merely because the producer received an acknowledgement.

Therefore, do not treat `send(...)` returning immediately as proof that the event reached the broker. Nor should you treat a successful future as proof that the receiving service has completed business processing.

### When is synchronous waiting needed?

In some flows, the application needs to know the send result before continuing. You can wait on the future with a timeout:

~~~java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import org.springframework.kafka.support.SendResult;

try {
    SendResult<String, OrderCreatedEvent> result =
        kafkaTemplate.send("orders", event.orderId(), event)
            .get(5, TimeUnit.SECONDS);

    // Metadata can be read once the send result is received.
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Kafka send thread was interrupted", ex);
} catch (ExecutionException | TimeoutException ex) {
    throw new IllegalStateException("Failed to confirm event send", ex);
}
~~~

Waiting with `get()` blocks the current thread. Use it only when the business flow truly needs the result immediately and an appropriate timeout has been chosen. Do not block every request thread just to log or retrieve an offset. If a timeout occurs, the final outcome may still be uncertain to the application; design retries and idempotency to avoid creating duplicate side effects.

Version note: Spring Kafka 3.x uses `CompletableFuture` for the send API; older Spring Kafka 2.x projects may use `ListenableFuture`. When applying examples to an existing project, check the actual dependency version.

## 5. Creating an Event Publishing Abstraction Layer

If controllers or application services call `KafkaTemplate` directly, business code becomes coupled to Spring Kafka, topic names, serializers, and infrastructure error handling. A messaging abstraction layer helps keep boundaries clear:

- The application service decides when to emit an event and what its contents are.
- An application interface defines the event publishing contract.
- A Kafka adapter translates that contract into a record and sends it using `KafkaTemplate`.
- The adapter translates technical metadata into the result the application layer needs, and propagates send errors back to the caller.

For example, define an event publishing contract independent of Spring Kafka. Place the interface and result record in separate files:

~~~java
import java.util.concurrent.CompletionStage;

public interface EventPublisher<T> {
    CompletionStage<PublishReceipt> publish(String key, T event);
}
~~~

~~~java
public record PublishReceipt(
    String topic,
    int partition,
    long offset
) {}
~~~

`CompletionStage` lets the application layer observe the asynchronous outcome without directly depending on `KafkaTemplate` or `SendResult`. `PublishReceipt` contains only the metadata the application wants to expose.

Define the event in a separate file:

~~~java
public record OrderCreatedEvent(
    String orderId,
    String customerId,
    long createdAtEpochMillis
) {}
~~~

Implement the adapter using KafkaTemplate:

~~~java
import java.util.concurrent.CompletionStage;

import org.apache.kafka.clients.producer.RecordMetadata;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
public class KafkaOrderEventPublisher
        implements EventPublisher<OrderCreatedEvent> {

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;
    private final String topic;

    public KafkaOrderEventPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate,
            @Value("${app.kafka.topics.orders}") String topic) {
        this.kafkaTemplate = kafkaTemplate;
        this.topic = topic;
    }

    @Override
    public CompletionStage<PublishReceipt> publish(
            String key,
            OrderCreatedEvent event) {

        return kafkaTemplate.send(topic, key, event)
            .thenApply(result -> {
                RecordMetadata metadata = result.getRecordMetadata();

                return new PublishReceipt(
                    metadata.topic(),
                    metadata.partition(),
                    metadata.offset()
                );
            });
    }
}
~~~

The adapter is responsible for converting `OrderCreatedEvent` into a Kafka record, selecting the topic, passing the key, and mapping the send result. If sending fails, the future returned from `KafkaTemplate` completes exceptionally; the error propagates through the `thenApply` chain to the caller.

The application service only needs to depend on the interface:

~~~java
import java.util.concurrent.CompletionStage;
import org.springframework.stereotype.Service;

@Service
public class OrderApplicationService {

    private final EventPublisher<OrderCreatedEvent> eventPublisher;

    public OrderApplicationService(
            EventPublisher<OrderCreatedEvent> eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    public CompletionStage<PublishReceipt> publishCreated(
            OrderCreatedEvent event) {
        return eventPublisher.publish(event.orderId(), event);
    }
}
~~~

This structure enables testing the application service with a fake implementation of `EventPublisher`. Test the adapter separately to verify the topic, key, payload, headers, and how metadata is mapped to the result.

In an application with many event types, you can use a generic interface as in the example above or define domain-specific ports, such as `OrderEventPublisher`. Domain-specific ports often express rules more clearly and prevent the application service from choosing topic names itself. Which approach to choose depends on the number of events and module boundaries; do not create extra wrapper layers if they add no meaningful value.

## 6. Error Handling and Limitations to Understand

Send errors can occur for many reasons: broker unavailability, connection errors, timeouts, authentication failures, invalid topics, or serializer failures when converting the payload. Because the operation is asynchronous, errors are typically observed through the future. The caller should handle errors instead of ignoring the future.

Example of handling the result at the call site:

~~~java
eventPublisher.publish(event.orderId(), event)
    .whenComplete((receipt, error) -> {
        if (error != null) {
            log.error("Failed to publish OrderCreated", error);
            return;
        }

        log.info(
            "OrderCreated acknowledged at {}-{}",
            receipt.topic(),
            receipt.partition()
        );
    });
~~~

Some practical principles:

- **Do not ignore errors:** if the future is not observed, the application may miss asynchronous send failures.
- **Do not retry indefinitely at the application layer:** the producer already has configured retries; additional retries at the business layer need bounded attempt counts, backoff, and an exhaustion policy.
- **Design for idempotency:** a retry can produce duplicate records or duplicate business effects. Consumers should have a way to detect already-processed events, such as using an event ID or business key.
- **Monitor outcomes:** log with correlation IDs and measure successful sends, failures, send latency, and timeouts.
- **Do not confuse acknowledgement with business processing:** the producer acknowledges writing the record; the consumer must track its own processing progress.

Producer idempotence and `acks` support sending reliability from the producer within Kafka's guarantee scope. They do not automatically turn an entire business workflow, such as writing to a database and sending an event, into an atomic transaction.

If the application needs to guarantee that database changes and Kafka events do not diverge when either operation fails, explore the Transactional Outbox pattern. If Kafka transactions across multiple Kafka records are needed, Spring Kafka provides transactional producer configuration and appropriate transaction APIs. These are separate topics; merely adding transactions to `KafkaTemplate` does not automatically create a distributed transaction with a standard database.

## 7. Testing the Messaging Layer

Two different boundaries should be tested:

| Component to test | Approach | What to verify |
|---|---|---|
| Application service | Fake or mock `EventPublisher` | Business logic emits the right event, right key, and reacts properly when the future succeeds/fails |
| Kafka adapter | Kafka test broker, Embedded Kafka, or Testcontainers | Record is actually sent with the expected topic, key, payload, and headers |

For adapter tests, read records from the topic using a consumer in a separate test group. Wait with a bounded timeout instead of a fixed sleep so tests remain more stable. If you only mock `KafkaTemplate`, the test verifies how the adapter calls the API but does not verify serializers, connectivity, or the broker.

For error testing, you can simulate an exceptionally completed future to verify the application service does not swallow errors. For integration testing, test both successful sends and scenarios where the broker is unavailable or serialization is misconfigured.

## 8. Checklist When Designing the Messaging API

Before putting the messaging layer into production, check:

- [ ] `KafkaTemplate<K, V>` has generic types matching the actual serializers and payloads.
- [ ] Topics are configured centrally, not scattered throughout business code.
- [ ] Keys are chosen according to partitioning and ordering requirements of the business entity.
- [ ] Necessary metadata such as correlation ID is intentionally placed in headers or payload.
- [ ] Futures are observed and errors are propagated to where they can be handled.
- [ ] Synchronous flows have explicit timeouts; asynchronous flows do not block threads unnecessarily.
- [ ] Retries, idempotency, and duplicate handling are designed according to business requirements.
- [ ] Tests separate application contract testing from Kafka adapter integration testing.

`KafkaTemplate` provides a consistent messaging API for Spring Kafka applications. When placed behind a domain-oriented abstraction layer, applications can keep business code clean, test independently, and clearly control send results. The key is understanding exactly what the future confirms, how to manage send errors, and not confusing broker receipt of a record with consumer completion of processing.
