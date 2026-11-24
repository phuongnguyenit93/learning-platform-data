# Package Organization for Producers and Consumers

When bootstrapping a Spring Kafka application, organize packages so readers can quickly locate where events are published, where events are received, where data contracts are defined, and where Kafka is configured. Good structure also prevents business logic from depending directly on `KafkaTemplate`, `@KafkaListener`, or Kafka client types.

In the `SPRING_KAFKA_MESSAGING` module, producers send events using Spring Kafka and `KafkaTemplate`; consumers receive events using `@KafkaListener`. An application may take on both roles, or each service may take on only one role. Package structure should clearly reflect that boundary while remaining appropriate for the project's scale.

## 1. Define Responsibilities Before Creating Packages

Producers and consumers are the two ends of a messaging flow, each with distinct responsibilities:

| Component | Primary Responsibility | Should Not Be Responsible For |
|---|---|---|
| Producer adapter | Choose topic, key, and headers; convert events into records; send via `KafkaTemplate`; observe send results | Containing full order-creation business rules or computing domain state |
| Consumer adapter | Declare `@KafkaListener`; receive payloads; pass needed data to application use cases; coordinate error handling at the messaging boundary | Containing complex business logic or accessing every repository directly inside the listener |
| Event contract | Define the data structure exchanged over Kafka, field names, and their meanings | Reusing JPA entities or internal domain objects directly as integration schemas |
| Kafka configuration | Configure bootstrap servers, serializers/deserializers, consumer groups, listener factories, and topics when needed | Mixing infrastructure configuration into the domain model |
| Application/domain | Enforce business rules, orchestrate use cases, and manage state | Depending on `KafkaTemplate`, `ConsumerRecord`, or broker APIs |

A useful principle is that **listeners receive data and delegate processing to a use case; publishers translate event-publishing requests into Kafka records**. These two adapters form the boundary between the application and Kafka.

## 2. Choosing an Appropriate Package Structure

There are two common approaches.

### 2.1. Organizing by Technical Role

For a small application with only a few producers and consumers, you can start with a simple structure:

```text
com.example.messaging
├── MessagingApplication.java
├── config/
│   ├── KafkaProducerConfiguration.java
│   ├── KafkaConsumerConfiguration.java
│   └── KafkaTopicConfiguration.java
├── contract/
│   ├── OrderCreatedEvent.java
│   └── PaymentReceivedEvent.java
├── producer/
│   ├── OrderEventPublisher.java
│   └── PaymentEventPublisher.java
└── consumer/
    ├── OrderEventListener.java
    └── PaymentEventListener.java
```

The advantage of this approach is that it is easy to understand, has few directories, and is convenient when learning Spring Kafka APIs. However, as business capabilities grow, the `producer` or `consumer` package can accumulate many classes from unrelated features. Readers must navigate multiple directories to understand a single business flow end-to-end.

### 2.2. Organizing by Feature, Separating Adapters Inside the Feature

For applications with multiple business capabilities, group code by feature or bounded context first, then separate producers and consumers inside that feature:

```text
com.acme.orders
├── OrdersApplication.java
├── order/
│   ├── domain/
│   │   ├── Order.java
│   │   └── OrderRepository.java
│   ├── application/
│   │   ├── port/
│   │   │   └── out/
│   │   │       └── OrderEventPublisher.java
│   │   └── usecase/
│   │       ├── CreateOrderUseCase.java
│   │       └── HandleOrderCreatedUseCase.java
│   ├── messaging/
│   │   └── contract/
│   │       └── OrderCreatedEvent.java
│   └── adapter/
│       └── kafka/
│           ├── producer/
│           │   └── KafkaOrderEventPublisher.java
│           └── consumer/
│               └── OrderCreatedListener.java
├── infrastructure/
│   └── kafka/
│       ├── KafkaProducerConfiguration.java
│       ├── KafkaConsumerConfiguration.java
│       └── KafkaTopicConfiguration.java
└── support/
```

In this structure:

- `domain` contains entities, value objects, and domain rules.
- `application` contains use cases and the ports those use cases need.
- `adapter.kafka.producer` implements the event-publishing port using Kafka.
- `adapter.kafka.consumer` receives records and invokes the corresponding use case.
- `messaging.contract` contains DTOs representing schemas exchanged over Kafka, independent of any specific adapter.
- `infrastructure.kafka` contains shared infrastructure configuration for the application.

This is a reference structure following the ports-and-adapters style. A project is not required to use all of these layers. For small applications, `port` or `support` can be omitted if they do not yet add value. What matters is maintaining the boundary between business logic and messaging technology.

## 3. Dependency Flow Between Producer, Consumer, and Business Logic

A producer is typically called from an application use case after business logic determines an event needs to be published. A consumer receives a record from Kafka and invokes a use case to process the incoming data. Both pass through adapters at the system boundary:

```mermaid
flowchart LR
    A[Application use case] --> B[OrderEventPublisher port]
    B --> C[KafkaOrderEventPublisher]
    C --> D[KafkaTemplate]
    D --> E[(Kafka topic)]
    E --> F[@KafkaListener]
    F --> G[HandleOrderCreatedUseCase]
    G --> H[Domain / Repository]
```

The sending and receiving sides may reside in the same service, but that does not mean they should depend directly on each other. The producer only needs to know the event contract and target topic; the consumer only needs to know the event contract it handles. Both sides communicate through Kafka.

Do not let domain entities call `KafkaTemplate.send(...)`. The domain model does not need to know about brokers, topics, or serializers. If an event must be published after persisting data, coordinate that at the application layer. When consistency between the database and Kafka is required, a transactional outbox may be needed; do not assume calling `send()` right after `repository.save()` automatically creates an atomic transaction across both systems.

## 4. Where Should Event Contracts Live?

An event contract is the schema understood by both producer and consumer. For example:

```java
package com.acme.orders.order.messaging.contract;

import java.math.BigDecimal;
import java.time.Instant;

public record OrderCreatedEvent(
        String eventId,
        String orderId,
        BigDecimal total,
        Instant occurredAt
) {}
```

A contract should describe the public data to be exchanged, with clear field names and a compatibility strategy when schemas evolve. Do not put internal details such as entities with lazy relationships, ORM state, or service beans into the payload.

If the producer and consumer belong to the same application, the contract can live in the feature's messaging package. If they belong to independent services, consider a versioned contract library module or a schema registry/schema repository. In that case:

- Do not share JPA entities or internal domain models across services.
- Only share explicitly published contract data types.
- Field changes must consider compatibility with producers/consumers deployed at different versions.
- Do not let consumers depend on the producer's implementation packages.

For example, the `orders` service can publish `OrderCreatedEvent`; the `billing` service only needs the event contract to process invoices. `billing` does not need to import the `Order` entity or `OrderRepository` from the `orders` service.

## 5. Producer Organization Example

The application layer defines the port needed by the use case:

```java
package com.acme.orders.order.application.port.out;

import com.acme.orders.order.messaging.contract.OrderCreatedEvent;

public interface OrderEventPublisher {
    void publish(OrderCreatedEvent event);
}
```

The adapter implements the port using `KafkaTemplate`:

```java
package com.acme.orders.order.adapter.kafka.producer;

import com.acme.orders.order.messaging.contract.OrderCreatedEvent;
import com.acme.orders.order.application.port.out.OrderEventPublisher;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
public class KafkaOrderEventPublisher implements OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;
    private final String topic;

    public KafkaOrderEventPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate,
            @Value("${app.kafka.topics.order-created}") String topic) {
        this.kafkaTemplate = kafkaTemplate;
        this.topic = topic;
    }

    @Override
    public void publish(OrderCreatedEvent event) {
        kafkaTemplate.send(topic, event.orderId(), event);
    }
}
```

In this example, `orderId` is the key so events for the same order can be routed to the same partition by the default partitioner when the partition count remains stable. The publisher does not decide order-creation rules; it only translates the event into a Kafka message.

The snippet keeps the example short and therefore does not handle the asynchronous result from `KafkaTemplate.send(...)`. In a real application, observe send results/failures and determine error reporting appropriate for the use case. If the port needs to represent the send outcome, use an application-layer return type such as `CompletionStage` or a custom result type, avoiding direct dependence of the application layer on Spring Kafka's `SendResult`.

## 6. Consumer Organization Example

The consumer adapter simply receives the event and forwards it to the use case:

```java
package com.acme.orders.order.adapter.kafka.consumer;

import com.acme.orders.order.messaging.contract.OrderCreatedEvent;
import com.acme.orders.order.application.usecase.HandleOrderCreatedUseCase;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    private final HandleOrderCreatedUseCase useCase;

    public OrderCreatedListener(HandleOrderCreatedUseCase useCase) {
        this.useCase = useCase;
    }

    @KafkaListener(topics = "${app.kafka.topics.order-created}")
    public void onMessage(OrderCreatedEvent event) {
        useCase.handle(event);
    }
}
```

The business-processing use case resides in the application layer:

```java
package com.acme.orders.order.application.usecase;

import com.acme.orders.order.messaging.contract.OrderCreatedEvent;

public interface HandleOrderCreatedUseCase {
    void handle(OrderCreatedEvent event);
}
```

In a real project, the use case implementation validates data, applies business rules, and calls repositories or domain services. Listeners should not become the place where all order-processing logic lives.

If the consumer needs metadata such as key, partition, offset, or timestamp, it can accept `ConsumerRecord<String, OrderCreatedEvent>` or appropriate header parameters. Pass only the metadata that business logic genuinely needs into the application layer; avoid making the domain depend on the Kafka client's `ConsumerRecord` type.

## 7. Where Should Kafka Configuration Live?

With Spring Boot, many basic configurations can be declared in `application.yml`; Spring Boot automatically creates the required beans such as `KafkaTemplate` and the listener container factory according to the configuration. There is no need to create a `@Configuration` class just to wrap every default value.

Example configuration for a producer and consumer using JSON:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
    consumer:
      group-id: orders-projection
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        "[spring.json.value.default.type]": com.acme.orders.order.messaging.contract.OrderCreatedEvent
        "[spring.json.trusted.packages]": com.acme.orders.order.messaging.contract
        "[spring.json.use.type.headers]": false

app:
  kafka:
    topics:
      order-created: orders.created
```

This is an illustrative configuration for a consumer that knows the payload type in advance. When type header reading is disabled, the consumer uses the declared default type; this is useful when producer and consumer do not use the same Java package. In a real environment, configure serializers/deserializers and schemas according to managed contracts, and do not widen trusted packages unnecessarily. Also establish how invalid data and deserialization errors are handled.

When deep customization is needed, place configuration classes in `infrastructure.kafka` or a dedicated configuration package:

| Class or File | Content That Belongs Here |
|---|---|
| `application.yml` | Bootstrap servers, serializers/deserializers, consumer groups, timeouts, and environment-specific properties |
| `KafkaProducerConfiguration` | Custom `ProducerFactory` or `KafkaTemplate` when multiple producer configurations are needed |
| `KafkaConsumerConfiguration` | Custom `ConsumerFactory`/listener container factory, concurrency, or custom error handlers |
| `KafkaTopicConfiguration` | Declaring `NewTopic` beans if the application is responsible for creating topics |

If a service has multiple producers/consumers with different configurations, name beans and factories by purpose, such as `orderKafkaTemplate` or `billingListenerContainerFactory`. Do not lump every case into a single shared factory and add hard-to-follow conditional branches.

## 8. Package Organization for Tests

Test packages should mirror the main source code's core boundaries:

```text
src/test/java/com/acme/orders
├── order/
│   ├── application/
│   │   └── HandleOrderCreatedUseCaseTest.java
│   └── adapter/kafka/
│       ├── producer/
│       │   └── KafkaOrderEventPublisherTest.java
│       └── consumer/
│           └── OrderCreatedListenerTest.java
└── infrastructure/kafka/
    └── KafkaConfigurationTest.java

src/test/resources
└── application-test.yml
```

- Unit tests for use cases verify business rules without needing a Kafka broker.
- Producer tests verify topic, key, payload, and how the adapter handles send results.
- Consumer tests verify the listener forwards the right event to the use case and handles required metadata.
- Integration tests use Embedded Kafka or Testcontainers to verify serialization, deserialization, topics, consumer groups, and real send/receive flows.

There is no need to put all tests into one massive test class for both producer and consumer. Separating tests by responsibility helps quickly pinpoint whether a failure lies in business logic, an adapter, or infrastructure configuration.

## 9. Organizational Practices to Avoid

- **One `kafka` package containing everything:** as the project grows, publishers, listeners, events, configs, and handlers from many features get mixed together.
- **Putting business logic inside listeners:** listeners become hard to test in isolation, hard to reuse, and prone to slowing down the poll loop if they do too much work.
- **Letting the domain depend on Kafka:** the domain should not import `KafkaTemplate`, `@KafkaListener`, `ConsumerRecord`, or serializers.
- **Using entities as event contracts:** database mapping changes can accidentally break schemas consumed by other services.
- **Sharing implementations across services:** services should only share managed contracts, not repositories, entities, or internal logic.
- **Creating too many packages prematurely:** a small application does not need empty layers or interfaces that merely forward a single call.
- **Merging all listener configurations into one giant class:** when different concurrency, retry, or deserialization settings are needed, separate purpose-built configurations are easier to follow.

## 10. Checklist Before Starting Development

- [ ] Determine whether the service acts as a producer, a consumer, or both.
- [ ] Choose an organization by technical role or by feature appropriate for the scale.
- [ ] Define event contracts independent of entities and database schemas.
- [ ] Place producer adapters at the outbound boundary and consumer adapters at the inbound boundary.
- [ ] Have consumers delegate to application use cases.
- [ ] Have the application layer invoke an event-publishing port, with an adapter implementing the port via `KafkaTemplate`.
- [ ] Place serializer, deserializer, group ID, and topic configurations where they can be managed per environment.
- [ ] Separate unit tests, adapter tests, and integration tests.
- [ ] Establish versioning and schema compatibility conventions when multiple services share events.
- [ ] Define how send failures, deserialization errors, and consumer processing errors are observed.

A clear package structure allows producers and consumers to evolve independently, keeps event contracts maintainable long-term, and minimizes business-logic coupling to Kafka. As the project grows, features can be split or contracts extracted into separate modules without rewriting the entire messaging flow.
