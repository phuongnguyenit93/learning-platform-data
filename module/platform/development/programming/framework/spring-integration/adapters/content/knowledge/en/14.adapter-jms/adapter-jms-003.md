# JMS outbound channel adapter

## 1. What problem does the JMS outbound channel adapter solve?

Suppose an enterprise's order-management service needs to notify the warehouse system whenever an order is paid. Internal business logic has produced an `OrderPaid` event as a Spring Message; however, the warehouse system only accepts messages via the JMS queue `warehouse.orders`. The **JMS outbound channel adapter** is the endpoint at the end of a Spring Integration flow that receives a Spring Message and sends a JMS message to a queue/topic on the broker.

Within the **SPRING_INTEGRATION_ADAPTERS** module, an outbound adapter bridges a `MessageChannel` to an external system. An inbound adapter brings data into Spring Integration; a gateway supports request/reply exchange; a poller orchestrates data sources that must be polled on a schedule. This lesson focuses on the **Spring Integration → JMS broker** direction, while clarifying message contracts, error handling, transactions, and connection lifecycle.

Most important point: **the outbound channel adapter is a one-way endpoint**. It sends the message to a JMS destination and finishes the send; it does not wait to receive a business-processing result from a JMS consumer. If the receiver must reply to a request via a JMS reply destination, look at the **JMS outbound gateway**.

### Exchange diagram

~~~mermaid
flowchart LR
    A["Order Service"] -->|"Spring Message<OrderPaid JSON>"| B["MessageChannel"]
    B --> C["JMS outbound channel adapter"]
    C -->|"JmsTemplate.convertAndSend"| D[("JMS broker: warehouse.orders")]
    D -->|"Broker delivery"| E["Warehouse consumer"]
    E --> F[("Warehouse system")]
~~~

From the sending application's perspective:

1. A component builds a Spring Message containing the appropriate payload and headers.
2. `MessageChannel` delivers the message to the outbound adapter's `JmsSendingMessageHandler`.
3. The handler selects the JMS destination, converts the Spring Message body via `MessageConverter`, and maps metadata using `JmsHeaderMapper`.
4. `JmsTemplate` uses `ConnectionFactory` to send the JMS message through the provider to the broker.
5. The send call returns or throws an exception; **success at the send step does not prove that a consumer has processed the message**.

The outbound adapter **does not poll on its own** and does not need a JMS `MessageListenerContainer`: it is invoked whenever a Spring Message enters the endpoint.

## 2. Components and boundaries of responsibility

| Component | Role | Design considerations |
|---|---|---|
| `MessageChannel` | Receives Spring Messages from the previous step | `DirectChannel` invokes the handler synchronously; async channels decouple processing timing |
| `JmsSendingMessageHandler` | Spring Integration endpoint performing JMS send | Has no reply message unlike a gateway |
| `JmsTemplate` | Creates session/producer and sends to destination | Configure session transaction, QoS, converter, and exception translation |
| `ConnectionFactory` | Opens and manages JMS connections via provider | Configure URL, authentication, TLS, recovery/caching per broker |
| `MessageConverter` | Turns a Java payload into JMS `TextMessage`, `BytesMessage`, etc. | Must be compatible with the external system's consumption contract |
| `JmsHeaderMapper` | Maps Spring headers to supported JMS headers/properties | Watch for valid data types and special header names |
| `Destination` / `DestinationResolver` | Identifies the target queue/topic | Can be static or computed dynamically from validated messages |
| JMS broker | Receives, stores/distributes messages | Manages durability, quotas, expiry, ACLs, DLQ, and consumers |

Do not confuse a **Spring Message** (`org.springframework.messaging.Message`) with a **JMS Message** (`jakarta.jms.Message`). The two objects have different bodies, headers/properties, and lifecycles; the outbound adapter performs the conversion at the integration boundary.

## 3. Java DSL configuration: pushing order notifications to a queue

The examples target Spring Integration 6+ with Jakarta JMS. A Spring Boot project can declare dependencies as follows when versions are managed by the Spring Boot BOM:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-jms</artifactId>
</dependency>
<!-- Add the JMS starter/client appropriate for the deployed broker. -->
~~~

The application needs a `ConnectionFactory` bean already connected to the broker, the `warehouse.orders` destination, and corresponding send permissions. Connection configuration and queue creation depend on ActiveMQ Artemis, IBM MQ, or the actual JMS provider in use.

### 3.1. Declaring the channel and outbound flow

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class WarehouseJmsOutboundConfig {

    @Bean
    public MessageChannel warehouseOutboundChannel() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow warehouseOutboundFlow(
            ConnectionFactory connectionFactory,
            @Qualifier("warehouseOutboundChannel") MessageChannel warehouseOutboundChannel) {

        return IntegrationFlow.from(warehouseOutboundChannel)
                .handle(Jms.outboundAdapter(connectionFactory)
                        .destination("warehouse.orders"))
                .get();
    }
}
~~~

Explanation:

- `IntegrationFlow.from(warehouseOutboundChannel)` uses a channel as the starting point of the flow segment; the message producer may be a service, another integration flow, or a gateway.
- `.handle(Jms.outboundAdapter(connectionFactory).destination("warehouse.orders"))` registers the JMS-sending handler. When a message arrives, the handler invokes `JmsTemplate` without using a poller.
- `DirectChannel` keeps the handler call on the sender's execution thread. If a synchronous send error occurs, the caller has a chance to receive the exception immediately. Using an asynchronous channel changes the error and acknowledgement boundary.
- The example uses a fixed queue name; it does not auto-generate queue names or change the broker address.

### 3.2. Sending a message from a service

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class WarehouseNotificationService {
    private final MessageChannel outboundChannel;

    public WarehouseNotificationService(
            @Qualifier("warehouseOutboundChannel") MessageChannel outboundChannel) {
        this.outboundChannel = outboundChannel;
    }

    public void notifyPaidOrder(String jsonPayload, String eventId) {
        boolean accepted = outboundChannel.send(
                MessageBuilder.withPayload(jsonPayload)
                        .setHeader("eventId", eventId)
                        .setHeader("schemaVersion", 1)
                        .setHeader("sourceSystem", "order-service")
                        .build());

        if (!accepted) {
            throw new IllegalStateException("Spring MessageChannel rejected the message");
        }
    }
}
~~~

Suppose `jsonPayload` has the following content:

~~~json
{
  "eventId": "evt-3010",
  "schemaVersion": 1,
  "eventType": "OrderPaid",
  "orderId": "ORD-301",
  "paidAt": "2026-11-23T01:00:00Z"
}
~~~

With the common default converter, a `String` payload produces a JMS `TextMessage`. Custom string/integer headers can be mapped into JMS properties if the header mapper allows them. The sender should agree on field names and JSON format with the consumer; do not assume the receiving app understands internal Java objects.

**Meaning of `send()`:** returning `true` indicates the message was accepted by the Spring `MessageChannel` according to channel semantics. With `DirectChannel`, the adapter is invoked synchronously before returning; with queue/executor channels, `true` may only mean the message was placed onto the channel, **not yet a successful JMS send**. Even after the JMS send completes, the downstream consumer and database may not have processed it yet.

### 3.3. Equivalent XML configuration

~~~xml
<int:channel id="warehouseOutboundChannel"/>

<int-jms:outbound-channel-adapter
        id="warehouseJmsSender"
        channel="warehouseOutboundChannel"
        connection-factory="jmsConnectionFactory"
        destination-name="warehouse.orders"/>
~~~

The XML fragment requires the Spring Integration `int` and `int-jms` namespaces, the `jmsConnectionFactory` bean, and a component sending messages to the channel. If you already use Java DSL, do not register an additional XML adapter on the same channel unless intentionally sending multiple copies, because multiple subscribers on a `DirectChannel` does not mean every subscriber receives every message.

## 4. Payload contract and header mapping

By default, the `extractPayload` property of the outbound channel adapter is `true`. This means the adapter takes the **Spring Message payload** as the JMS body, while Spring headers are handled separately via the header mapper.

| Spring payload | JMS message typically created by `SimpleMessageConverter` | Points to note |
|---|---|---|
| `String` | `TextMessage` | Suitable for JSON/XML/strings with a clear schema |
| `byte[]` | `BytesMessage` | Agree on encoding, format, and size limits |
| `Map` with valid values | `MapMessage` | Verify JMS-supported value types |
| `Serializable` | `ObjectMessage` | Depends on Java class, serialVersionUID, and data trust; avoid as a cross-service contract |

With `extractPayload(false)`, the adapter can convert the **entire Spring Message** into a JMS body using an appropriate converter. This mode fits very few scenarios because the consumer must decode the Spring Message structure and internal data. For cross-service integration, prefer `extractPayload(true)` with a platform-independent message format such as JSON or schema-governed Avro/Protobuf.

### Standard JMS headers and JMS properties

JMS distinguishes between:

1. **Standard headers** such as `JMSCorrelationID`, `JMSReplyTo`, `JMSType`, `JMSPriority`, `JMSExpiration`.
2. **Application properties**, which are primitive/`String` values defined by the application.

`DefaultJmsHeaderMapper` can map supported Spring headers to corresponding fields, but not every Spring header is valid as a JMS property. Headers that are arbitrary objects, unsupported JMS types, or invalid names may be ignored/not mapped. For example, `String` headers like `eventId` and `sourceSystem` are simple choices for tracing.

Important fields should live in the **payload contract** or an agreed header; do not rely on every internal Spring header being preserved automatically across the broker. `JMSMessageID` is typically generated by the JMS provider per send, whereas `eventId` is the business event identifier that must remain stable so the receiver can detect duplicate messages.

Spring Integration's `correlationId` and `jms_correlationId` mapped to `JMSCorrelationID` are not completely identical. When using request/reply or tracing a processing chain, verify which field the consumer expects. The outbound channel adapter only **sends**, so having `JMSCorrelationID` does not turn it into a reply-receiving gateway.

### Choosing an appropriate converter

Do not assume every domain object converts automatically to JSON. If the payload is `OrderPaid` (a Java object), `SimpleMessageConverter` may handle it with Java serialization or fail to match a consumer expecting JSON. To transmit JSON, you can:

- Serialize the domain object to JSON in a `.transform(...)` step before the outbound adapter, with controlled schema and version.
- Configure a suitable JMS `MessageConverter` and align mapping with the receiving side.

Example of a transform step when the source already has an `OrderPaid` object:

~~~java
// Illustrative flow snippet; objectMapper is a Jackson ObjectMapper.
.transform(OrderPaid.class, event -> {
    try {
        return objectMapper.writeValueAsString(event);
    } catch (com.fasterxml.jackson.core.JsonProcessingException ex) {
        throw new IllegalStateException("Cannot serialize OrderPaid", ex);
    }
})
.handle(Jms.outboundAdapter(connectionFactory)
        .destination("warehouse.orders"))
~~~

This snippet belongs inside an appropriate `IntegrationFlow` with an injected `objectMapper` variable. Serialization failures are converted into an unchecked exception so the flow handles them before JMS sending.

## 5. Choosing a static or dynamic destination

Most business use cases should use a static destination and distinguish event types via `eventType`/`schemaVersion`, keeping ACLs, monitoring, and consumer deployment straightforward.

When routing to multiple queues is required, Java DSL supports an expression/function to resolve the destination from the Spring Message. For example:

~~~java
.handle(Jms.outboundAdapter(connectionFactory)
        .destinationExpression("headers['targetQueue']"))
~~~

`targetQueue` must be produced by a **validation and allowlist-mapping** step; never use a raw value supplied by an untrusted client directly. If the app only permits `warehouse.orders` and `warehouse.returns`, validate that value before sending. When destinations vary by payload, monitor metrics/ACLs per queue and handle missing-header cases.

**Queues and topics differ in delivery:** queues typically serve competing consumers where one message is processed by one consumer; topics can fan out to multiple subscriptions. Configure JMS `pubSubDomain` or the corresponding `Destination` in `JmsTemplate`/provider; simply renaming a queue to a topic name does not automatically give publish-subscribe semantics. For topics, consider subscription types (durable/non-durable) on the consumer side if offline subscribers must receive messages.

## 6. QoS: persistent delivery, priority, and time-to-live

JMS provides several Quality of Service (QoS) properties:

| Property | Meaning | Risk if misconfigured |
|---|---|---|
| `DeliveryMode.PERSISTENT` | Requests the provider to persist messages with appropriate durability | Has I/O overhead; actual durability also depends on broker and config |
| `DeliveryMode.NON_PERSISTENT` | Allows sending with lower durability | Messages may be lost if the broker fails |
| `priority` (0–9) | Hints delivery priority to the broker | Should not be relied upon to guarantee business ordering |
| `timeToLive` (milliseconds) | Message lifetime from send time; expired messages may be discarded or handled per policy | Setting TTL too short may prevent consumers from ever seeing the message |

JMS send defaults are typically persistent, priority 4, and unlimited TTL, though you should verify the final provider settings. For certain dynamic QoS settings on `JmsSendingMessageHandler` to take effect, `JmsTemplate` must enable **`explicitQosEnabled`**; Spring Integration Java DSL uses `DynamicJmsTemplate` when configuring the adapter from `ConnectionFactory`.

Example intended only for **expirable notifications**:

~~~java
.handle(Jms.outboundAdapter(connectionFactory)
        .destination("warehouse.notifications")
        .timeToLiveExpression("60000")
        .configureJmsTemplate(template -> template.explicitQosEnabled(true)))
~~~

Here TTL is set to 60,000 ms. This is a snippet to place in a flow; do not add a second adapter on the same message path if you only want to send one copy. Financial events, order status transitions, or messages requiring audit trails generally **should not have a short TTL**. `JMSExpiration` is the expiration timestamp after a message is sent; `timeToLive` is the duration passed to the send operation—the two values are not identical.

## 7. Transactions: send success and data consistency

The outbound adapter uses `JmsTemplate`. When `sessionTransacted=true` is set on the template, if there is **no external JMS transaction**, the template can create a local JMS transaction for the send operation and commit upon success. If an active JMS transaction exists on the same resource and execution thread, the send can participate in that transaction. The XML `session-transacted` attribute on the outbound adapter serves this same purpose.

### Receiving from one JMS queue and forwarding to another

A flow may read `orders.in` via a JMS message-driven inbound adapter, process synchronously, and send to `orders.out` via an outbound adapter. When both steps use the **same `ConnectionFactory`**, JMS transactions are properly configured, and the processing path stays synchronous, receiving and sending can share the same JMS transaction. If a handler throws an error before commit, the broker has a chance to roll back both the receive and the send. Still, verify actual reuse of the same JMS session/transaction, listener container configuration, and provider behavior; do not assume any two JMS endpoints automatically merge transactions.

### Writing to a database and then sending JMS

Suppose the system performs:

1. Write order status `PAID` to the database.
2. Send `OrderPaid` to `warehouse.orders`.

Two resources—**database and JMS broker**—do not automatically belong to a single atomic transaction. If the DB commits and the JVM crashes before step 2, the order is paid without an event. If the JMS send commits before the DB transaction fails, the consumer may receive an event for state that does not exist in the DB. Merely adding `@Transactional` with `DataSourceTransactionManager` does not make the JMS send part of the DB transaction.

~~~mermaid
flowchart TD
    A["Begin DB transaction"] --> B["Write Order=PAID"]
    B --> C["Write event to outbox in same DB transaction"]
    C --> D["Commit DB"]
    D --> E["Outbox publisher reads unsent records"]
    E --> F["JMS outbound adapter sends event"]
    F --> G{"Send succeeded?"}
    G -->|Yes| H["Mark outbox as sent"]
    G -->|Failed| I["Keep outbox for controlled retry"]
~~~

**Transactional outbox** is a pragmatic pattern for critical events: write the business change and an outbox record in the **same DB transaction**; another worker/integration flow reads the outbox and sends via JMS, then marks the result. Because a failure window still exists between the JMS send and the status update, events **may be delivered more than once**; the consumer needs idempotency keyed by `eventId`.

If publishing an event originating from a transacted JMS inbound adapter, keep `DirectChannel`/synchronous execution when exceptions should affect the upstream transaction. Inserting an `ExecutorChannel` or `QueueChannel` can split the transaction and allow the inbound to commit before the outbound send fails.

**Do not promise `exactly-once` solely from JMS transaction configuration.** Cross-system correctness generally requires outbox/inbox, idempotent consumers, retries, and monitoring; distributed/XA transactions are appropriate only when genuinely supported by the provider and infrastructure and their operational overhead is acceptable.

## 8. Send errors, retries, and dead-letter handling

### Where do errors occur?

- **Before sending:** missing destination, JSON serialization error, invalid property value, converter failure.
- **During sending:** JMS connection closed, broker overloaded, missing send permissions, network timeout, or provider error.
- **After sending with uncertain outcome:** the app loses connectivity right after the broker accepts the message before the client receives acknowledgement; retrying may create duplicates.
- **After broker acceptance:** the downstream consumer may fail or be stopped; the outbound adapter has no visibility into that outcome.

With `DirectChannel`, exceptions from `JmsSendingMessageHandler` usually propagate back to the caller invoking `send()` (possibly wrapped in a messaging exception). The caller or upstream advice must decide whether to roll back, retry, or log the failure. With `ExecutorChannel`, the original sending thread may already have returned; errors go through async error handling, so observe `errorChannel` and configure the executor appropriately.

**`errorChannel` does not automatically retry JMS sends or move messages to a DLQ.** JMS dead-letter queues are primarily part of broker/consumer redelivery; for **producer send failures**, use producer-side retry/outbox/quarantine or an application-designed error channel.

### Responsible retry policy

| Error type | Auto-retry? | Handling approach |
|---|---|---|
| Broker temporarily disconnected | Yes, bounded attempts/intervals | Backoff, retry via outbox, alert on backlog |
| Broker overloaded / rate-limited | Yes, respecting resources | Throttle emission rate, avoid hot spin loops |
| Non-existent destination or ACL denied | Usually do not retry infinitely immediately | Fix configuration or permissions, surface clear error state |
| Payload fails schema | Do not resend unmodified indefinitely | Validate before sending, quarantine invalid records |
| Uncertain send result | Can retry, must tolerate duplicates | Stable `eventId`, receiver-side idempotency |

Example pseudo-flow for an outbox-backed application:

~~~text
DB outbox PENDING
    -> read batch with lock/lease
    -> send via JMS outbound adapter
        -> success: mark SENT
        -> transient error: record attempts, next_retry_at, last_error
        -> permanent error: move to FAILED/quarantine, alert
~~~

Spacing out retries with backoff and capping attempts avoids keeping a publisher spinning continuously during a broker outage. Use consumer-side idempotency because the publisher can crash after the broker receives the message but before marking `SENT`.

### Stopping/restarting the application

The outbound adapter does not run a continuous listener to consume messages on its own. It uses `ConnectionFactory`/`JmsTemplate` when the handler is called. When the broker is unavailable, sending can fail; if the app only keeps notifications in RAM, a restart risks losing unsent data. For safe replay, persist events to an outbox or equivalent durable store and control send ordering.

Monitor at minimum: successful/failed message send counts, send latency, retry counts, outbox depth, oldest `PENDING` record age, broker connection state, destination quotas, expired message counts, and downstream consumer success rates if cross-service metrics exist.

## 9. Comparing the outbound adapter with other options

| Need | Suitable endpoint | Why |
|---|---|---|
| Push an event to a JMS queue without waiting for a reply | **JMS outbound channel adapter** | One-way, converts Spring Message to JMS Message |
| Send a JMS request and wait for a JMS reply | JMS outbound gateway | Supports reply destination, correlation, and timeout |
| Pull messages from a JMS queue on a schedule | JMS polling inbound adapter | Poller-driven `JmsTemplate.receive()` |
| Receive JMS immediately when delivered by the broker | JMS message-driven inbound adapter | JMS listener container |
| Publish to HTTP/Kafka/AMQP | Protocol-specific adapter/gateway | Each protocol has its own contracts and retry semantics |

Having a `JMSReplyTo` header on a message **does not make the outbound adapter automatically receive responses**. If a result from the consumer is needed, choose a gateway from contract design onward: request destination, reply destination, correlation ID, timeout, and late-reply handling.

## 10. Hands-on exercise: publishing payment events to the warehouse system

**Context:** the application sends `OrderPaid` JSON to queue `warehouse.orders`, and the warehouse system has a consumer reading and confirming event ingestion. Use a real test broker or properly configured container.

1. **Happy path:** configure `ConnectionFactory`, queue, and Java DSL as in section 3; send `evt-3010`; verify the queue/consumer receives a `TextMessage` with valid JSON.
2. **Header contract:** inspect properties mapped by the mapper, verify `eventId`/`schemaVersion`, JMS message ID, and destination name. Do not assume every Spring header reaches the consumer.
3. **Converter:** test both a `String` payload and a Java domain object; explain why an appropriate serializer/converter is needed for the consumer to receive JSON.
4. **Broker offline:** shut down the broker and invoke the flow over `DirectChannel`; inspect the exception, retry/outbox behavior, and remaining pending events.
5. **Timeout/uncertain outcome:** simulate a connection drop after sending and retry with the same `eventId`; verify the consumer does not create duplicate business effects.
6. **QoS:** send a test notification with a short TTL and observe the expiry policy. Do not use real orders for TTL testing.
7. **Dynamic destination:** test valid and invalid `targetQueue` values; verify the allowlist blocks arbitrary destinations.
8. **Transactions:** write to DB and intentionally fail the JMS send; observe the inconsistency and implement an outbox so retries work.
9. **Stop/restart:** restart the publisher while outbox rows are still `PENDING`; verify the publisher resumes sending and receiver-side business records do not duplicate.

When verifying transactions and durability, use a real JMS broker/provider; unit tests mocking `JmsTemplate` cannot prove the broker persisted the message, handled reconnection, or behaved properly on a crash between commits.

### Self-check questions

1. When `warehouseOutboundChannel.send(...)` returns `true`, which steps have been confirmed and which have not?
2. Why does an outbound adapter not need a poller? How does its trigger differ from message-driven inbound?
3. What difference do `extractPayload(true)` and `extractPayload(false)` make to the JMS body?
4. Why is `JMSMessageID` insufficient to prevent duplicate processing of a resent business event?
5. If a DB write succeeds but the JMS send fails, how does the outbox pattern help recover?
6. Why is `explicitQosEnabled` required when configuring dynamic QoS through the outbound adapter?
7. When the producer must receive a processing status back from the warehouse, which endpoint should replace the adapter?

## 11. References

- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): `JmsSendingMessageHandler`, outbound adapter, `extractPayload`, mapping, QoS, and transactions.
- [Spring Integration Java DSL API — JmsOutboundChannelAdapterSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jms/dsl/JmsOutboundChannelAdapterSpec.html): static/dynamic destination selection, header mapper, and QoS expressions.
- [Spring Framework Reference — JMS](https://docs.spring.io/spring-framework/reference/integration/jms.html): `JmsTemplate`, converters, transactions, and JMS infrastructure.

**Remember:** the JMS outbound channel adapter sends Spring Messages from an integration flow to a JMS broker. Reliable design requires clarifying payload/header contracts, destinations and QoS, exception handling, transaction boundaries with databases, outbox/retry, and consumer idempotency. Successful broker acceptance is one step in the workflow, not proof that downstream business processing has completed.
