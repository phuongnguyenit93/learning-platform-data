# Spring AMQP and RabbitMQ in AMQP Use Cases

## Objectives

After this lesson, you will be able to choose the right protocol and Spring integration for RabbitMQ; design exchanges, queues, and bindings; send/receive messages with `RabbitTemplate` and `@RabbitListener`; configure JSON, publisher confirms, consumer acknowledgements, retries, and dead-letter exchanges; and recognize the limits of message delivery in distributed systems.

## 1. AMQP, RabbitMQ, and Spring AMQP

**AMQP (Advanced Message Queuing Protocol)** is an application-layer protocol for message-oriented middleware systems. An application that sends messages is called a producer/publisher; an application that processes messages is a consumer; a broker receives, stores, and routes messages between the two sides.

**RabbitMQ** is a message broker that supports multiple protocols, including AMQP 0-9-1 and AMQP 1.0. The broker and applications can run on different machines. Producers do not need to know where consumers are running; producers only need to send messages to the broker according to the declared topology.

**Spring AMQP** brings Spring abstractions into AMQP programming: dependency injection, send/receive templates, listener containers, message converters, bean-based topology declarations, and connection recovery mechanisms. The project has the core `spring-amqp` module and protocol-implementing client modules.

Distinguish three components:

- **Protocol:** the wire format and communication rules, such as AMQP 0-9-1 or AMQP 1.0.
- **Broker:** RabbitMQ, which receives, stores, and routes messages.
- **Spring abstraction:** Java APIs helping applications use the broker via templates, admin, and listener containers.

Spring AMQP is not a message broker. It is an application-side library for working with a broker.

## 2. Distinguishing AMQP 0-9-1 and AMQP 1.0

The two protocols have similar names but are two different wire protocols, not two versions you can swap back and forth merely by configuring a port.

| Protocol | Model | Common Spring integration |
|---|---|---|
| AMQP 0-9-1 | Exchange, routing key, binding, queue; RabbitMQ-style consumer acknowledgement and publisher confirms | `spring-rabbit`, `RabbitTemplate`, `RabbitAdmin`, `@RabbitListener` |
| AMQP 1.0 | Message, sender/receiver link, address, settlement, and flow control per the AMQP 1.0 model | `spring-amqp-client` or `spring-rabbitmq-client` depending on broker and goal |

RabbitMQ 4.0 supports both AMQP 0-9-1 and AMQP 1.0. Both protocols can share the default listener port 5672; the client sends a protocol header so the broker identifies which protocol it wants to use. Having two clients connect to the same broker does not make their client libraries interchangeable.

Current Spring options:

- **AMQP 0-9-1:** use `spring-rabbit`. This is the common path of the Spring Boot RabbitMQ starter, with `RabbitTemplate` and `@RabbitListener`.
- **AMQP 1.0 on RabbitMQ:** Spring AMQP 4.0 added `spring-rabbitmq-client`, based on the RabbitMQ AMQP 1.0 Java client. Representative APIs are `RabbitAmqpTemplate`, `RabbitAmqpAdmin`, and `RabbitAmqpListenerContainer`. This module is specific to RabbitMQ, not a general client for every AMQP 1.0 broker.
- **Multi-broker AMQP 1.0:** Spring AMQP 4.1 added `spring-amqp-client`, based on Qpid ProtonJ2. This module can work with AMQP 1.0 peers, including RabbitMQ, ActiveMQ, and other compatible services. Representative APIs are `AmqpClient`, `AmqpMessageListenerContainer`, and `@AmqpListener`.

If the project uses Spring AMQP 3.x, check the dependency and documentation for the right branch before copying 4.x examples. Spring AMQP 4.x requires Spring Framework 7; do not upgrade a single module while ignoring Spring Boot, Spring Framework, and Java compatibility.

## 3. AMQP 0-9-1 model: exchange, routing key, binding, and queue

In AMQP 0-9-1, a producer publishes messages to an **exchange**. The exchange uses the exchange type and **bindings** to decide which queues a message will be routed to. Consumers subscribe to receive messages from a queue.

<escape>Producer → Exchange → Binding → Queue → Consumer</escape>

Components:

- **Exchange:** entry point receiving messages from producers and performing routing.
- **Routing key:** string sent by the producer for the exchange to match against bindings.
- **Binding:** rule connecting an exchange to a queue, optionally with a routing key or headers.
- **Queue:** where the broker stores messages for consumers to receive.
- **Virtual host (vhost):** separate namespace and permission boundary for exchanges, queues, bindings, and users.

### Four basic exchange types

| Exchange | Routing behavior | Usage example |
|---|---|---|
| Direct | Routing key must exactly match the binding key | Route `invoice.create` commands to the invoice processing queue |
| Topic | Routing key matches a pattern; `*` is exactly one word, `#` is zero or more words | Select event groups like `order.created`, `order.cancelled` |
| Fanout | Sends copies to every bound queue; ignores routing key | Broadcast cache invalidation or configuration updates |
| Headers | Matches message headers against binding arguments | Route by multiple metadata attributes instead of routing key |

Topic exchange example:
- Binding `order.*` matches `order.created` or `order.cancelled`.
- Binding `order.#` matches `order.created`, `order.payment.failed`, or `order.item.added`.
- `*` matches exactly one segment between dots; `#` matches zero or more segments.

RabbitMQ has a **default exchange**, which is an unnamed direct exchange (empty name). Every queue is automatically bound to the default exchange with a routing key equal to the queue name. Therefore, calling `convertAndSend("billing.orders", event)` actually uses the default exchange and the queue name as the routing key.

### Durable, exclusive, and auto-delete

Queues and exchanges have lifecycle attributes:

- **Durable:** topology survives broker restarts.
- **Exclusive:** queue is tied only to the owning connection and deleted when that connection closes.
- **Auto-delete:** queue can be deleted when the last consumer unsubscribes after the queue has had at least one consumer.

Durable queues and persistent messages are two different things. A durable queue does not automatically make every message persistent; the producer must set the appropriate delivery mode. For critical workloads, you also need to choose queue type, replication, broker storage, and publisher confirms.

## 4. Spring AMQP 0-9-1: core abstractions

With Spring AMQP and RabbitMQ 0-9-1, the key classes include:

| Component | Role |
|---|---|
| `ConnectionFactory` / `CachingConnectionFactory` | Manages connections and reuses channels |
| `AmqpTemplate` | Interface for sending/receiving messages |
| `RabbitTemplate` | Implementation using the RabbitMQ Java client |
| `AmqpAdmin` | Interface for declaring/deleting exchanges, queues, and bindings |
| `RabbitAdmin` | Manages topology on RabbitMQ |
| `@RabbitListener` | Marks a method for asynchronous message processing |
| `RabbitListenerContainerFactory` | Creates and configures listener containers |
| `MessageConverter` | Converts between Java objects and AMQP messages |

`RabbitTemplate` is the standard API for publishing messages. `@RabbitListener` is the standard API for consuming messages. The listener container manages consumers, concurrency, acknowledgement, and connection lifecycle underneath.

With Spring Boot, the common dependency for AMQP 0-9-1 is:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
~~~

Let Boot manage dependency versions via its BOM; do not manually pick Spring AMQP and RabbitMQ client versions unless there is a specific compatibility reason.

## 5. Connecting to RabbitMQ with Spring Boot

Example `application.yml` configuration:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: app
    password: ${RABBITMQ_PASSWORD}
    virtual-host: /orders
    connection-timeout: 5s
~~~

Values must match the broker:
- Host/port is the broker address.
- Username/password must have access rights to the vhost.
- Virtual host isolates topology and access permissions.
- Connection timeout limits wait time when establishing a connection.

Do not commit real passwords into the repository. Production should use a secret manager or secret injection. When using TLS, configure SSL according to Spring Boot/RabbitMQ and verify the broker certificate; do not disable certificate verification to bypass connection errors.

Spring Boot typically auto-configures:
- RabbitMQ `ConnectionFactory`.
- `RabbitTemplate` / `AmqpTemplate`.
- `AmqpAdmin` / `RabbitAdmin`.
- Default listener container factory for `@RabbitListener`.

If `Queue`, `Exchange`, and `Binding` beans are declared, RabbitAdmin can automatically declare the topology on the broker. If the application creates a listener for a non-existent queue, the listener may fail to start or receive no messages until the queue is properly declared.

## 6. Declaring topology with Java configuration

Example of a simple event flow: a producer publishes `order.created` to a Topic exchange; the billing department's queue receives this event.

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderAmqpTopology {

    @Bean
    TopicExchange ordersExchange() {
        return new TopicExchange("orders.events", true, false);
    }

    @Bean
    Queue billingQueue() {
        return QueueBuilder.durable("billing.orders").build();
    }

    @Bean
    Binding billingBinding(
            Queue billingQueue,
            TopicExchange ordersExchange) {

        return BindingBuilder.bind(billingQueue)
            .to(ordersExchange)
            .with("order.created");
    }
}
~~~

This is a minimal topology. The application needs a connection to RabbitMQ and a RabbitAdmin for topology beans to be declared. When an exchange or queue already exists with mismatched attributes, RabbitMQ may return a `PRECONDITION_FAILED` error; do not change attributes of an active queue simply by editing the bean and restarting the application.

When changing queue type, durability, TTL, or dead-letter arguments, have a migration plan: create a new queue, move bindings/consumers, drain the backlog, and only then retire the old queue.

## 7. Sending messages with RabbitTemplate

Suppose the event is a Java record:

~~~java
import java.time.Instant;

public record OrderCreated(
    String eventId,
    String orderId,
    Instant occurredAt
) {}
~~~

The producer uses `RabbitTemplate`:

~~~java
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
class OrderPublisher {

    private final RabbitTemplate rabbitTemplate;

    OrderPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    void publish(OrderCreated event) {
        rabbitTemplate.convertAndSend(
            "orders.events",
            "order.created",
            event,
            message -> {
                message.getMessageProperties()
                    .setMessageId(event.eventId());
                message.getMessageProperties()
                    .setDeliveryMode(MessageDeliveryMode.PERSISTENT);
                return message;
            }
        );
    }
}
~~~

Parameters of `convertAndSend`:
1. Exchange: `orders.events`.
2. Routing key: `order.created`.
3. Payload: `OrderCreated` object.
4. MessagePostProcessor: adds metadata before publishing.

If no exchange is specified, the template uses the default exchange. If only a queue name is passed, the queue name is used as the routing key via the default exchange.

### Message properties and headers

An AMQP message has a body and metadata. Common metadata fields:

- `messageId`: message identifier.
- `correlationId`: correlates request and response or messages within the same business flow.
- `contentType`: content type, e.g., `application/json`.
- `deliveryMode`: persistent or non-persistent.
- `timestamp`: message creation time.
- `replyTo`: address to receive responses in request/reply.
- Headers: additional information such as tenant, event type, or trace context.

Include a stable event ID in the payload or header so consumers can deduplicate processing. Do not put entire complex domain objects, JPA entities, or sensitive data into a message just because a converter can serialize them.

## 8. MessageConverter: JSON instead of Java serialization

Spring AMQP uses `MessageConverter` to convert objects into byte arrays and restore payloads when consumers receive messages.

The default converter is `SimpleMessageConverter`, which supports text, byte arrays, and Java serialized objects. Java native serialization tightly couples producers and consumers to Java classes, breaks easily when classes change, and carries deserialization risks. For multi-service or polyglot systems, JSON or schema-based formats are usually more suitable.

With Spring AMQP 4.x, you can use the Jackson 3 converter:

~~~java
import org.springframework.amqp.support.converter.JacksonJsonMessageConverter;
import org.springframework.amqp.support.converter.MessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class AmqpConverterConfiguration {

    @Bean
    MessageConverter amqpMessageConverter() {
        return new JacksonJsonMessageConverter();
    }
}
~~~

Spring Boot will attach the `MessageConverter` bean to the auto-configured template and listener factory. If you create a custom `RabbitTemplate` or listener factory, you must configure the corresponding converter on that instance.

Version notes:
- Spring AMQP 4.x uses Jackson 3-based converters, notably `JacksonJsonMessageConverter`.
- Spring AMQP 3.x commonly uses `Jackson2JsonMessageConverter` based on Jackson 2.
- Do not copy 4.x converter imports into a 3.x project without checking dependencies and Javadoc.

Type headers can be used to map payloads back to Java classes. With cross-language producers/consumers, agree on a JSON schema and stable event types; do not depend on the producer's Java package/class names. Configure trusted packages/type mappings using an allowlist rather than trusting arbitrary class names arriving in messages.

## 9. Receiving messages with @RabbitListener

A listener declares the queue to consume from:

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
class BillingOrderListener {

    @RabbitListener(queues = "billing.orders")
    public void handle(OrderCreated event) {
        // Validate and process billing business logic.
    }
}
~~~

When a message arrives at the queue, the listener container converts the payload via MessageConverter and invokes the method. The method can accept the converted payload, the Spring AMQP `Message`, headers, or other supported parameters.

Listeners are asynchronous: the producer does not wait for the `handle` method to finish. If an immediate response is needed, request/reply can be used; if only emitting an event is needed, let consumers process independently.

### Queue binding directly on the annotation

For simple topologies, `@RabbitListener` can declare the queue, exchange, and binding:

~~~java
@RabbitListener(bindings = @QueueBinding(
    value = @Queue(value = "inventory.orders", durable = "true"),
    exchange = @Exchange(value = "orders.events", type = "topic"),
    key = "order.created"
))
public void updateInventory(OrderCreated event) {
    // Update inventory.
}
~~~

For topologies with many queues, DLX, TTL, or queue types, Java bean configuration is usually clearer. Ensure queues/exchanges already exist or that RabbitAdmin declares them.

## 10. Choosing a routing topology for the use case

| Use case | Suitable topology | Explanation |
|---|---|---|
| A group of workers sharing task processing | Direct exchange or default exchange + queue | Each message in the queue is received successfully by one consumer |
| One event needed by multiple services | Fanout or Topic exchange with a separate queue per service | Each queue has an independent backlog and consumers |
| Routing by event type | Topic exchange | Routing keys like `order.created`, `order.cancelled` |
| Routing by exact command | Direct exchange | Keys like `invoice.generate` |
| Routing by multiple metadata attributes | Headers exchange | Bindings match header values |
| Calling a service and waiting for a result | Request/reply | Uses correlation ID and reply address, with timeout |
| Storing logs/events for long-term replay | RabbitMQ Streams or an appropriate event store | Streams have a different storage and replay model from traditional queues |

An important point: if two services share the same queue, they compete for messages. If both services need to receive a copy of an event, each service needs its own queue bound to the exchange.

## 11. Publisher confirms and returned messages

Publishing is an asynchronous operation. `RabbitTemplate.convertAndSend(...)` returning does not mean the broker has persisted the message or routed it to a queue.

There are two distinct mechanisms:

- **Publisher confirm:** the broker confirms that the publish was accepted or rejected by the broker.
- **Publisher return:** the broker returns the message when published with `mandatory=true` but it could not be routed to any queue.

These two mechanisms are independent of consumer acknowledgement. A confirm does not state that a consumer has processed the message; it only reflects the publish status on the broker side.

Example configuration in Spring Boot:

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
~~~

When using correlated confirms, `CorrelationData` helps correlate confirms with outgoing messages:

~~~java
import org.springframework.amqp.rabbit.connection.CorrelationData;

CorrelationData correlation = new CorrelationData(event.eventId());

rabbitTemplate.convertAndSend(
    "orders.events",
    "order.created",
    event,
    correlation
);

correlation.getFuture().whenComplete((confirm, error) -> {
    if (error != null) {
        // Error while waiting for confirm result.
    }
    else if (!confirm.isAck()) {
        // Broker nack: handle unaccepted publish.
    }
    else if (correlation.getReturn() != null) {
        // Broker returned message because it could not be routed.
    }
});
~~~

In production, record publish failures and decide to retry or save to an outbox for redelivery. Do not blindly retry when publish outcome is unknown: the broker may have received the message while the connection dropped before the client received the confirm, causing a resend to create a duplicate.

## 12. Consumer acknowledgement, prefetch, and reliability

When RabbitMQ delivers a message to a consumer, the broker needs to know when the message is considered processed. With AMQP 0-9-1, there are three common modes in Spring AMQP:

| Spring AcknowledgeMode | Behavior |
|---|---|
| `AUTO` | The listener container acks after the listener finishes successfully; exceptions may result in reject/nack depending on configuration |
| `MANUAL` | Application code explicitly acks/nacks after processing |
| `NONE` | The broker considers the message acknowledged immediately upon delivery; high throughput but messages may be lost if the consumer dies |

Note: `AUTO` in the Spring listener container is not the same as RabbitMQ's protocol-level `autoAck=true`. Spring AUTO generally waits until the listener finishes successfully before acknowledging.

For consumers needing reliability, AUTO or MANUAL is usually used instead of NONE. If the process dies before acking, unacknowledged messages can be redelivered by the broker. Therefore, consumers must be idempotent.

**Prefetch** limits the number of unacknowledged messages the broker can pre-deliver to a consumer/channel. Low prefetch helps limit messages sitting in memory and distributes load more evenly; high prefetch can increase throughput but increases in-flight messages and the risk of overloading one consumer.

## 13. Retry, requeue, and Dead Letter Exchange

When a listener throws an exception, the application must decide whether to retry:

- Transient errors (database timeout, temporary outage of a downstream service) can be retried with backoff.
- Invalid data or unrecoverable errors should not be requeued indefinitely.
- Once retry attempts are exhausted, the message should be rejected and routed to a dead-letter exchange (DLX) if configured.
- The DLQ stores failed messages for investigation, data repair, or controlled replay.

Spring Boot can enable listener retries:

~~~yaml
spring:
  rabbitmq:
    listener:
      simple:
        retry:
          enabled: true
          initial-interval: 1s
          multiplier: 2.0
          max-interval: 10s
          max-attempts: 3
~~~

Listener retry is different from retry when publishing from `RabbitTemplate`. Boot disables listener retry by default. Once retries are exhausted, the default recoverer may reject without requeuing; the message only goes to a DLQ if the broker has a dead-letter exchange configured. If a listener throws an exception while retry is disabled and configuration still requeues rejected messages, delivery can loop infinitely.

DLX topology example:

~~~java
@Bean
DirectExchange ordersDlx() {
    return new DirectExchange("orders.dlx");
}

@Bean
Queue billingDlq() {
    return QueueBuilder.durable("billing.orders.dlq").build();
}

@Bean
Binding billingDlqBinding(
        @org.springframework.beans.factory.annotation.Qualifier("billingDlq")
        Queue billingDlq,
        DirectExchange ordersDlx) {

    return BindingBuilder.bind(billingDlq)
        .to(ordersDlx)
        .with("billing.orders.failed");
}
~~~

The main queue must declare the dead-letter exchange and routing key:

~~~java
@Bean
Queue billingQueue() {
    return QueueBuilder.durable("billing.orders")
        .deadLetterExchange("orders.dlx")
        .deadLetterRoutingKey("billing.orders.failed")
        .build();
}
~~~

This is broker topology configuration; check whether the existing queue has the same arguments before deploying. If the queue already exists with different arguments, RabbitMQ may reject redeclaration. A DLQ should not be a place where messages sit indefinitely with no one handling them: alerts, dashboards, inspection procedures, and replay policies are needed.

Immediate requeuing when all consumers are hitting the same error can create a CPU/network-burning loop. Use backoff, bounded retries, and a DLQ.

## 14. Durable queues, persistent messages, and queue types

Three concepts to separate:

1. **Durable exchange:** exchange topology survives broker restarts.
2. **Durable queue:** queue survives broker restarts.
3. **Persistent message:** message sent with persistent delivery mode.

To improve data durability, both durable queues and persistent messages are typically needed, along with publisher confirms. However, ultimate durability still depends on queue type, replicas, broker storage, and cluster configuration.

RabbitMQ has multiple queue types:
- **Classic queue:** traditional queue, suitable for many simple workloads.
- **Quorum queue:** Raft-based replicated queue, aimed at higher safety and availability in a cluster; has its own resource overhead and operational characteristics.
- **Stream:** persistent log structure supporting offset-based replay and multiple independent consumers; different from traditional message-consuming queues.

Do not pick a queue type solely by its name. Base the choice on maximum acceptable data loss, replica count, throughput, latency, replay needs, and broker operational capacity.

## 15. Retries and duplicate handling: do not assume exactly-once

AMQP acknowledgements and publisher confirms tell the application about certain delivery states, but they do not create end-to-end business exactly-once processing.

Example:
1. Consumer receives `order.created`.
2. Consumer writes the order to the database successfully.
3. Process stops before sending ack.
4. Broker redelivers the message.
5. Consumer runs a second time and may write a duplicate order.

Protection methods:
- Every event has a stable `eventId`.
- Consumer maintains an inbox/processed-event table with a unique constraint.
- Marking the event processed and updating business data happen within the same database transaction.
- If the event was already processed, the consumer returns success to ack without repeating side effects.
- Producer uses a transactional outbox to store the event in the same business transaction, and a separate publisher sends the message to RabbitMQ.

Do not rely solely on broker-generated message IDs for business deduplication. Producer-generated IDs must remain stable across retries and replays.

## 16. Transactions between database and RabbitMQ

Spring AMQP supports channel transactions, but a RabbitMQ channel transaction and a JDBC/JPA transaction are two separate resources.

- `RabbitTemplate.setChannelTransacted(true)` uses channel transactions for publishing.
- Listener containers can run with transacted channels so ack/reject ties to commit/rollback.
- A database transaction manager does not automatically make RabbitMQ operations atomic with it.
- Distributed transactions require XA/JTA and supporting resources; this model has operational costs and limitations.

For many business systems, transactional outbox/inbox is easier to operate: commit the database first, then publish outbox events; consumers deduplicate using an inbox. This remains an at-least-once model, but with controlled duplicate handling.

## 17. Request/reply and RPC

RabbitMQ can support request/reply via reply queues, correlation IDs, and reply-to addresses. Spring AMQP provides `RabbitTemplate.convertSendAndReceive(...)` to implement request/reply.

This pattern is useful when:
- The client truly needs the result of an operation from another service.
- There is a clear timeout.
- Request and response share a correlation ID.
- The server can process the request and send a reply within the expected timeframe.

Do not use RPC over a message broker for every internal call. Request/reply still creates temporal coupling: the caller must wait for a response and handle timeouts, lost responses, retries, and duplicates. If the use case is event notification or background work, publishing events and processing asynchronously is usually more suitable.

## 18. AMQP 1.0 in Spring AMQP 4.x

When a system requires AMQP 1.0, choose the right module rather than using AMQP 0-9-1's `RabbitTemplate` and assuming the protocol will switch automatically.

### Generic AMQP 1.0: spring-amqp-client

Spring AMQP 4.1 adds the dependency:

~~~xml
<dependency>
    <groupId>org.springframework.amqp</groupId>
    <artifactId>spring-amqp-client</artifactId>
</dependency>
~~~

This module is based on Qpid ProtonJ2 and supports AMQP 1.0 peers in general. APIs include `AmqpConnectionFactory`, `SingleAmqpConnectionFactory`, `AmqpClient`, `AmqpMessageListenerContainer`, and the `@AmqpListener` annotation.

Example of initializing the client via the fluent API:

~~~java
@Bean
AmqpConnectionFactory amqpConnectionFactory() {
    return new SingleAmqpConnectionFactory();
}

@Bean
AmqpClient amqpClient(AmqpConnectionFactory connectionFactory) {
    return AmqpClient.builder(connectionFactory)
        .defaultToAddress("/queues/orders.in")
        .messageConverter(new JacksonJsonMessageConverter())
        .build();
}
~~~

Example of sending a message:

~~~java
amqpClient.to("/queues/orders.in")
    .body(orderCreated)
    .messageId(orderCreated.eventId())
    .send();
~~~

Send/receive operations return a `CompletableFuture`, so asynchronous completion/errors must be handled. The address `/queues/orders.in` is an example of RabbitMQ destination conventions; other AMQP 1.0 brokers may use different address conventions.

### RabbitMQ-specific AMQP 1.0: spring-rabbitmq-client

Spring AMQP 4.0 added `spring-rabbitmq-client`, based on the RabbitMQ AMQP 1.0 Java client. APIs include `RabbitAmqpTemplate`, `RabbitAmqpAdmin`, and `RabbitAmqpListenerContainer`. This module is for RabbitMQ, not a general client for every AMQP 1.0 broker.

If the project uses AMQP 0-9-1, continue using `spring-rabbit`, `RabbitTemplate`, and `@RabbitListener`. If the project needs AMQP 1.0 interoperability across multiple brokers, consider `spring-amqp-client`. If you need AMQP 1.0 with RabbitMQ-specific APIs, consider `spring-rabbitmq-client`.

## 19. Choosing RabbitMQ queue or Stream?

Queues and RabbitMQ Streams solve different needs.

| Need | Queue | Stream |
|---|---|---|
| Worker receives a task and processes it once | Suitable | Usable but usually unnecessary |
| Multiple consumers independently reading one event log | Requires a separate queue per consumer | Suitable |
| Delete message after consumer ack | Queue model | Stream retains logs according to retention |
| Re-reading data from an older offset | Not the primary model | Supports replay |
| Long-term event storage by retention | Requires additional storage system | More suitable |

RabbitMQ Streams use a separate protocol/client, not identical to AMQP queues. Spring Boot has `RabbitStreamTemplate` and dedicated configuration for RabbitMQ Streams. Do not use the term "AMQP stream" to refer to every queue or every stream.

## 20. Testing Spring AMQP applications

Unit tests can verify business handler logic by calling the service directly. However, verifying routing, exchanges, queues, acks, retries, and DLQs requires integration tests with a real RabbitMQ broker.

Recommended tests:

1. **Topology:** verify exchanges, queues, and bindings are declared with the right name, type, durability, and routing keys.
2. **Publish/consume:** send an event via `RabbitTemplate` and verify the listener receives the right payload.
3. **Routing:** publish multiple routing keys and verify each queue only receives matching event types.
4. **Publisher confirm:** verify broker ack/nack and handling of returned messages when no binding exists.
5. **Acknowledgement:** when the listener succeeds, the message is acked; when the listener fails, the message is requeued or rejected according to configuration.
6. **Retry/DLQ:** induce a deliberate error, verify retry count, and verify the message appears in the DLQ once attempts are exhausted.
7. **Idempotency:** send the same event ID multiple times and verify side effects happen only once.
8. **Broker restart:** verify durable queues/persistent messages according to queue type and storage config.
9. **Protocol compatibility:** if using AMQP 1.0, test with a client and broker using that protocol; do not substitute AMQP 0-9-1 tests.

Testcontainers can spin up a RabbitMQ container for integration tests. Use separate queues/exchanges per test or controlled cleanup so messages from earlier tests do not affect results. Do not just mock `RabbitTemplate` and conclude that broker routing is correct.

## 21. Observability and operations

Monitor both the application and the broker:

- Publish rate, publish confirm latency, nack/return count.
- Queue depth, messages ready, messages unacknowledged.
- Consumer count, consumer utilization, and prefetch.
- Redelivery count, DLQ depth, and age of messages in the DLQ.
- Connection/channel count, reconnects, broker alarms, and disk/memory watermarks.
- Listener processing latency and errors by destination/event type.

Spring AMQP integrates Micrometer metrics/Observation for templates and listener containers. The RabbitMQ Management plugin provides a dashboard/API for queues, exchanges, connections, channels, and consumers. Queue depth and broker health should come from broker metrics, not solely from application logs.

When running in production:
- Use separate vhosts and users per application or business domain.
- Grant least-privilege configure/write/read permissions.
- Use TLS for connections over untrusted networks.
- Set easily identifiable connection names.
- Monitor channel cache, consumer concurrency, and prefetch.
- Set alerts for DLQ, queue backlog, inactive consumers, and broker resource alarms.

## 22. Common mistakes

- **Confusing AMQP 0-9-1 with AMQP 1.0:** two different protocols; must choose the right client/module.
- **Assuming RabbitTemplate routes directly to a queue by name:** templates publish to an exchange; queues receive messages through bindings. The default exchange is a special case.
- **Creating a queue without binding an exchange:** messages may fail to route to the intended queue.
- **Assuming a durable queue makes all messages persistent:** queue durability and delivery mode are two separate properties.
- **Not enabling publisher confirms:** producers do not know whether the broker accepted the message.
- **Not enabling mandatory/returns:** unroutable messages can be dropped without the producer receiving a return.
- **Confusing publisher confirms with consumer acks:** one confirms the broker accepted the publish, the other confirms the consumer processed the delivery.
- **Using AUTOACK/NONE for critical workloads:** the broker may consider the message finished before the consumer processes it successfully.
- **Infinite retries:** poison messages can cause requeue loops and clog queues.
- **Not handling duplicates:** broker redelivery can cause side effects to execute multiple times.
- **Changing queue arguments directly:** topology mismatch can cause the broker to return `PRECONDITION_FAILED`.
- **Using Java serialization across services:** creates coupling to Java classes and deserialization risks.
- **Putting unique IDs into metric tags:** cardinality explodes rapidly; use traces/logs for message identifiers.
- **Using a queue as a replayable event log:** if offset-based reading and retention are needed, look at RabbitMQ Streams or an event store.

## 23. Pre-deployment checklist

- [ ] Determined whether the protocol is AMQP 0-9-1 or AMQP 1.0.
- [ ] Selected the right module: `spring-rabbit`, `spring-rabbitmq-client`, or `spring-amqp-client`.
- [ ] Spring Boot, Spring Framework, Spring AMQP, and Java versions are compatible.
- [ ] Defined exchange types, routing keys, bindings, and queues for each consumer.
- [ ] Queue/exchange durability, message persistence, and queue types match requirements.
- [ ] Message schema has version, event ID, and necessary metadata.
- [ ] JSON converter matches Jackson 2/3 for the Spring AMQP version.
- [ ] Publisher confirms and returned messages are handled when reliability is required.
- [ ] Consumer acknowledgement, prefetch, retries, and DLQ are clearly configured.
- [ ] Consumers have idempotency/inbox handling for duplicates.
- [ ] Database + publish is designed with outbox or appropriate transactions.
- [ ] Integration tests exist against a real broker and broker restart tests when needed.
- [ ] Metrics/alerts exist for backlog, DLQ, confirms, consumers, and broker health.
- [ ] Credentials, vhosts, permissions, and TLS are securely managed.

## References

- [Spring AMQP Reference](https://docs.spring.io/spring-amqp/reference/amqp.html): abstractions, templates, connections, converters, transactions, and recovery.
- [Spring Boot — AMQP](https://docs.spring.io/spring-boot/reference/messaging/amqp.html): starter, connection properties, RabbitTemplate, listeners, retries, and auto-configuration.
- [Spring AMQP — AMQP Abstractions](https://docs.spring.io/spring-amqp/reference/amqp/abstractions.html): Message, Exchange, Queue, and Binding.
- [Spring AMQP — Message Converters](https://docs.spring.io/spring-amqp/reference/amqp/message-converters.html): SimpleMessageConverter and Jackson JSON converters.
- [Spring AMQP — Sending Messages](https://docs.spring.io/spring-amqp/reference/amqp/sending-messages.html): RabbitTemplate, publisher confirms, and returns.
- [Spring AMQP — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven.html): `@RabbitListener` and listener containers.
- [Spring AMQP — Generic AMQP 1.0 Support](https://docs.spring.io/spring-amqp/reference/amqp10-client.html): `spring-amqp-client`, ProtonJ2, `AmqpClient`, and `@AmqpListener`.
- [Spring AMQP — RabbitMQ AMQP 1.0 Support](https://docs.spring.io/spring-amqp/reference/rabbitmq-amqp-client.html): `spring-rabbitmq-client`, `RabbitAmqpTemplate`, and listener containers.
- [RabbitMQ — AMQP 0-9-1 Model Explained](https://www.rabbitmq.com/tutorials/amqp-concepts): exchanges, queues, bindings, routing, and acknowledgements.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): delivery acknowledgements, publisher confirms, nacks, and prefetch.
- [RabbitMQ — Exchanges](https://www.rabbitmq.com/docs/exchanges): exchange types and routing.
- [RabbitMQ — Spring AMQP Tutorial](https://www.rabbitmq.com/tutorials/tutorial-one-spring-amqp): producer/consumer example with Spring AMQP and AMQP 0-9-1.
