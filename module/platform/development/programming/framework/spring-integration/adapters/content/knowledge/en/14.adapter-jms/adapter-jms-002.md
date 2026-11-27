# JMS message-driven channel adapter

## 1. The problem solved by the message-driven adapter

Suppose a sales system sends order events to the JMS queue `orders.in`. The receiving service needs to start processing almost immediately after a message arrives, without writing a custom loop to check the queue periodically. Spring Integration's **JMS message-driven inbound channel adapter** is the right entry point: a **JMS listener container** listens on the destination, receives messages delivered by the broker, and pushes them onto a Spring Integration `MessageChannel`.

In the **SPRING_INTEGRATION_ADAPTERS** module, adapters serve to connect external systems to the integration flow. An inbound adapter brings data into Spring Integration; an outbound adapter sends data out; a gateway supports two-way exchange; `MessageChannel` connects processing steps; and a poller actively invokes a data source on a schedule. This lesson focuses on the **JMS message-driven channel adapter**, i.e., the listener-based JMS inbound style, and connects it to the message contracts, error handling, and connection lifecycle required by the module.

**Learning objectives:** you will be able to configure a listener for a JMS queue, understand where `jakarta.jms.Message` is converted into a Spring Message, choose appropriate concurrency, explain when the broker acknowledges a message, and design an error-handling/redelivery strategy that avoids duplicate data writes.

### Core difference compared to polling

- **Polling inbound adapter:** a scheduler triggers a `JmsTemplate.receive()` call on `fixedDelay`, `fixedRate`, or cron; message-pickup latency depends on the poll schedule and receive timeout.
- **Message-driven inbound adapter:** `MessageListenerContainer` actively manages the consumer and receive loop; when the broker has a message, the listener callback immediately forwards the message into the integration flow. **No poller is configured** on this endpoint.

Message-driven is usually the first choice for continuous JMS event streams or low-latency requirements. Polling remains useful when business requirements must restrict reception times, such as syncing only during specific processing windows.

## 2. Architecture and path of a message

~~~mermaid
flowchart LR
    A["Sender app / ERP"] -->|"JMS TextMessage"| B[("JMS broker: orders.in")]
    B -->|"Broker delivers to consumer"| C["Listener container"]
    C -->|"MessageListener callback"| D["JMS message-driven inbound adapter"]
    D -->|"Convert / map headers"| E["Spring Message"]
    E --> F["MessageChannel"]
    F --> G["Validate + business processing"]
    G --> H[("Database")]
~~~

Layers of responsibility:

| Component | Responsibility | Key points to remember |
|---|---|---|
| JMS broker | Stores and distributes messages with queue/topic semantics | Retry and dead-letter policies must be configured at the broker/provider when needed |
| `ConnectionFactory` | Provides JMS connections/sessions | Can be created by Spring Boot from the JMS provider's starter |
| `DefaultMessageListenerContainer` | Maintains JMS consumers, receive loop, concurrent consumers, recovery, and listener transactions | Provided by Spring JMS; Spring Integration uses this or another suitable container |
| JMS message-driven inbound adapter | Receives callbacks from the container, converts the JMS message to a Spring Message, and sends it to the channel | This is the start of the integration flow; there is no poller |
| `MessageConverter` and header mapper | Converts payload, copies supported metadata | The message contract must be agreed upon with the producer |
| `MessageChannel` | Delivers Spring Messages to the next consumer | Synchronous vs. asynchronous channels strongly affect JMS acknowledgement |
| Message handler | Validates, persists data, calls external systems | Must handle duplicates and throw errors appropriately if rollback is desired |

Typical sequence for a **queue**:

1. When the endpoint starts, the listener container creates a JMS consumer on `orders.in` and manages the connection lifecycle.
2. The broker delivers a message to the consumer. The listener container invokes the registered handler code on the same receive thread.
3. The adapter reads the content, converts it into a Spring Message (payload and headers), and sends it to the `MessageChannel`.
4. One or more handlers process the message. On a synchronous processing path, errors can propagate back to the listener container.
5. The JMS session acknowledges or rolls back the receive according to the acknowledge mode and transaction configuration. Broker policy decides what happens to the message after rollback.

**Scope:** this is a **one-way inbound channel adapter**. It does not automatically generate a JMS response for the producer. If the task requires **request/reply** with `JMSReplyTo`, use a JMS inbound gateway; if writing messages to a destination is needed, use an outbound adapter.

## 3. Creating a message-driven integration flow with Java DSL

The example uses Spring Integration 6+ (the JMS API uses the `jakarta.jms` package); for older projects, some imports may belong to `javax.jms`. Add Spring Integration JMS and the JMS client matching the broker. Below is the minimal Maven dependency snippet on the Spring Integration side in a Spring Boot project with a BOM managing versions:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-jms</artifactId>
</dependency>
<!-- Add the JMS provider or JMS starter matching the broker in use. -->
~~~

Prerequisites: the application has a `ConnectionFactory` bean able to connect to the broker, and the broker has the `orders.in` queue. Do not assume the broker auto-creates queues or has default addresses or passwords.

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;

@Configuration
@EnableIntegration
public class OrderJmsInboundConfiguration {

    @Bean
    public IntegrationFlow orderJmsInboundFlow(
            ConnectionFactory connectionFactory,
            OrderImportService orderImportService) {

        return IntegrationFlow
                .from(Jms.messageDrivenChannelAdapter(connectionFactory)
                        .destination("orders.in"))
                .handle(String.class, (jsonBody, headers) -> {
                    // This function processes synchronously; on failure, the service must signal an error.
                    orderImportService.importOrder(jsonBody);
                    return null; // One-way adapter, produces no reply message.
                })
                .get();
    }
}
~~~

In the example, `OrderImportService` is a business bean built by the application; a minimal interface might be:

~~~java
public interface OrderImportService {
    void importOrder(String jsonBody);
}
~~~

This flow does not use `@Scheduled`, `PollerMetadata`, or `maxMessagesPerPoll`. `Jms.messageDrivenChannelAdapter(connectionFactory)` creates an entry point backed by a JMS listener container; `.destination("orders.in")` selects the destination. `.handle(String.class, ...)` assumes the producer sends a `TextMessage` converted into a `String` by the converter. The handler returns `null` because importing an order is a one-way task.

**Runtime note:** `OrderImportService` must have an implementation, `ConnectionFactory` must be configured with a real provider, and the queue must be ready. If receiving `BytesMessage`, the payload type or converter must change; if an error happens in the converter before the handler, error-handling policy must account for that stage.

### Illustrating a producer sending an event

~~~java
import org.springframework.jms.core.JmsTemplate;

// Another service injected with JmsTemplate.
jmsTemplate.convertAndSend(
        "orders.in",
        "{\"eventId\":\"evt-2001\",\"schemaVersion\":1,"
        + "\"orderId\":\"ORD-82\",\"amount\":250000}");
~~~

When both the broker and consumer are active, the listener receives the message without waiting for a 5- or 10-second cycle. **There is no absolute latency guarantee**: network, broker, listener concurrency, handler duration, and system load can all affect it.

### XML namespace for XML-configured projects

~~~xml
<int:channel id="ordersInput"/>

<int-jms:message-driven-channel-adapter
        id="ordersInbound"
        connection-factory="jmsConnectionFactory"
        destination-name="orders.in"
        channel="ordersInput"/>

<int:service-activator
        input-channel="ordersInput"
        ref="orderMessageHandler"
        method="handle"/>
~~~

This is an XML fragment: the application needs the `int` and `int-jms` namespace declarations, the `jmsConnectionFactory` bean, and the `orderMessageHandler` bean. The XML difference from polling inbound is that **`message-driven-channel-adapter` has no `<int:poller>`**.

## 4. Listener container, consumer count, and connection lifecycle

Spring Integration uses Spring JMS's listener mechanism; `DefaultMessageListenerContainer` (DMLC) is commonly used because it supports flexible concurrency, reconnect/recovery, and transaction configuration. Under higher traffic, you do not need to create multiple identical flows just to open more consumers: adjust the listener container configuration appropriately.

| Listener container setting | Effect | Operational notes |
|---|---|---|
| `destinationName` or `destination` | Specifies the receiving queue/topic | Distinguish queue vs. topic; name must match the broker |
| `concurrentConsumers` | Minimum number of consumers maintained | Increasing consumers generally raises queue throughput if downstream can process in parallel |
| `maxConcurrentConsumers` | Maximum concurrency when the container supports dynamic scaling | Size based on broker, CPU, DB pool, and ordering requirements |
| `sessionTransacted` | Requests a transacted JMS session | Enables rollback/redelivery when errors propagate out of the listener |
| `transactionManager` | Attaches a manager when transactions are managed outside the container | Clarify whether using standalone JMS transaction or multi-resource coordination |
| `recoveryInterval` / `BackOff` | Controls when connection recovery is retried after failure | Requires monitoring and proper backoff when the broker disconnects |
| `pubSubDomain` | Selects topic semantics instead of queue | For topics, decide durable/shared subscriptions as required |

Example design progression for an order-import app: start with **one consumer** to keep ordering easy to trace, then raise to 2–4 consumers if orders are independent and the DB can handle the load. With multiple consumers, **completion ordering is not guaranteed as with a single consumer**; if the system must process events for the same order in strict sequence, use broker-supported ordering/partitioning or grouping strategies.

Do not confuse three distinct concepts:

- **Consumer concurrency:** the number of JMS consumers the listener container uses to receive messages in parallel.
- **Channel executor:** the number of downstream processing threads behind an `ExecutorChannel`; this can decouple JMS acknowledgement time from business processing time.
- **Deployed instance count:** total consumers across instances reading the same queue. Adding instances increases throughput but also makes preserving order harder.

### Queues and topics do not share the same semantics

With a **queue**, each message is normally delivered to **one** of the competing consumers, suitable for distributing work. With a **topic**, a message can be distributed across different subscriptions; non-durable subscribers may miss messages while offline, whereas durable subscriptions preserve delivery rights subject to broker/provider configuration. Configure `pubSubDomain` and the corresponding client/subscription properties rather than only changing the destination name.

### Startup, shutdown, and recovery

When the application starts, Spring manages startup of the endpoint and listener container; during shutdown, the container stops accepting new messages and handles stopping active consumers as configured. If the application crashes mid-flight, whether the broker redelivers the message depends on transactions, acknowledgement, and broker policy. Do not treat a restart as a guarantee that every message is automatically processed exactly once.

When the broker temporarily disconnects, DMLC has a recovery retry mechanism, but you should still inspect actual state, queue depth, and recovery failure counts. Enable health checks/metrics alongside error logs; avoid relying solely on the Java process being alive to conclude that the listener is still receiving messages.

## 5. Message contract: payload and JMS headers

JMS defines message types such as `TextMessage`, `BytesMessage`, `MapMessage`, and `ObjectMessage`. Spring JMS `MessageConverter` converts the body into a Java object; Spring Integration creates a Spring Message for the handler. With the common default converter:

| JMS message | Typical received payload | Recommendation |
|---|---|---|
| `TextMessage` | `String` | Agree on encoding and JSON schema/version |
| `BytesMessage` | `byte[]` | Document binary format and size limits |
| `MapMessage` | `Map` or converter-appropriate representation | Keep key/value conventions consistent, limit provider coupling |
| `ObjectMessage` | Serialized Java object | Be cautious of class compatibility and deserialization; prefer language-neutral contracts |

Example event:

~~~json
{
  "eventId": "evt-2001",
  "schemaVersion": 1,
  "orderId": "ORD-82",
  "amount": 250000
}
~~~

The fields `eventId`, `schemaVersion`, and `orderId` are **business contract fields in the payload**; they are not auto-generated by JMS. `eventId` must remain stable when the same event is resent. The handler validates required fields, checks the version, and uses `eventId` as the idempotency key to prevent duplicate writes on redelivery.

Standard JMS metadata includes `JMSMessageID`, `JMSCorrelationID`, `JMSType`, `JMSRedelivered`, `JMSPriority`, `JMSExpiration`, etc. Spring Integration uses a header mapper to map a subset of this metadata into Spring Message headers. Do not assume the names or presence of **all** headers are identical across versions, converters, and configurations; test the headers actually used in your flow.

**Two different types of ID:** JMS message ID describes a provider-assigned delivery/record; `eventId` describes the business event. A producer might replay the same event as a new JMS message carrying a different ID, so deduplication should rely on `eventId` or a meaningful business key.

If direct interaction with the JMS API is needed, the adapter has an option to preserve the raw JMS message instead of extracting only the payload. This increases coupling to the broker/JMS session and is usually unnecessary in domain handlers; prefer converting early into a validated business data type.

## 6. Acknowledgement, transactions, and redelivery

A common mistake is assuming that **the listener received the message** equals **the order was written successfully**. When the broker considers a message acknowledged depends on how the Spring JMS listener container is configured.

### Key modes to understand

| Mode | What to understand |
|---|---|
| `AUTO_ACKNOWLEDGE` | With `DefaultMessageListenerContainer`, acknowledgement can occur before the listener runs; an exception in the handler does not guarantee broker redelivery |
| `CLIENT_ACKNOWLEDGE` | Depends on the container and how acknowledge is invoked; do not assume business errors always lead to redelivery |
| JMS session `transacted` | The container commits after a successful callback and rolls back when an error escapes within the transaction boundary |
| External transaction manager | Can manage transactions per configuration; distinguish local JMS transactions from DB transactions |

To give the broker a chance to redeliver when a synchronous handler fails, configuring **`sessionTransacted = true`** on the listener container is a common starting point. In Java, `DefaultMessageListenerContainer` exposes `setSessionTransacted(true)`; when configuring via DSL/XML, map the corresponding transaction option onto the adapter's listener container.

Do not put retry logic in an infinite loop inside the listener. A permanently broken message (e.g., invalid schema) could be redelivered endlessly, clogging the queue. Choose a broker retry policy with bounded attempts, backoff, and a dead-letter queue (DLQ), and distinguish permanent business/data errors from transient dependency errors like DB timeouts.

### Decision diagram for error handling

~~~mermaid
flowchart TD
    A["Listener receives JMS message"] --> B["Convert and validate"]
    B --> C{"Processing succeeded?"}
    C -->|Yes| D["Commit / acknowledge per config"]
    C -->|No| E{"Does exception reach listener container?"}
    E -->|Yes, session transacted| F["Rollback JMS session"]
    F --> G["Broker redelivery / DLQ per policy"]
    E -->|No, already handled| H["Container may see callback as succeeded"]
    H --> I["Risk of committing despite business failure"]
~~~

**The synchronous boundary matters greatly.** If the adapter sends to a `DirectChannel` and the next handler runs on the same thread, exceptions have a chance to propagate back to the listener container. If you insert an `ExecutorChannel`, `QueueChannel`, or an async call, the listener may finish and acknowledge JMS before work on the other thread/consumer completes. At that point, a JMS rollback of the original message no longer covers the final outcome of the downstream handler.

### Why a JMS transaction is not a DB transaction

Suppose a service writes an order to PostgreSQL and then the listener tries to commit the JMS transaction. If the database commit succeeds but the JMS commit fails, the broker may redeliver the same message. Conversely, if the listener already acknowledged and async downstream processing fails, the order may be lost from the processing flow. `JmsTransactionManager` manages local JMS transactions; by itself it **does not guarantee atomic commits between JMS and DB**.

In most integration applications, the pragmatic approach is **at-least-once + idempotency**:

1. The producer supplies a stable `eventId`.
2. The handler opens a DB transaction and inserts `eventId` into an inbox/`processed_event` table with a unique constraint.
3. Within the **same DB transaction**, it updates the order and marks the event processed.
4. If `eventId` already exists, the handler treats the event as already processed and returns success without duplicate writes.
5. On transient errors, it throws an exception so the listener container/JMS transaction handles rollback per policy.

For systems requiring atomic guarantees across multiple resources, evaluate outbox/inbox architectures, distributed transactions if genuinely supported, and operational trade-offs. Do not claim `exactly-once` just because `sessionTransacted` is enabled.

## 7. `errorChannel` and preserving proper error semantics

The JMS message-driven inbound adapter can route errors through Spring Integration's `ErrorMessage`/`errorChannel` mechanism as configured. Sending exceptions to an error channel is useful for logging, alerting, and error classification. However, **an error flow that absorbs the exception can make the JMS listener container view the callback as successful**. In transacted mode, this can lead to a commit instead of a rollback.

Therefore, explicitly choose one of these policies:

- **Transient error, want broker redelivery:** the exception must reach the listener's transaction boundary. If an error handler processes the error, ensure it **rethrows** the exception when rollback is desired.
- **Permanent error, acceptable to drop after quarantine:** write safely to an error store/DLQ per the designed strategy, then finish the callback; make clear when acknowledgement is allowed.
- **Asynchronous downstream error:** place into a work queue with independent acknowledgement or a dedicated retry mechanism; do not expect the inbound JMS transaction to protect work that has crossed onto another thread.

Sending an `ErrorMessage` to `errorChannel` **does not automatically** perform retries, rollbacks, or DLQ routing. To determine exact behavior, inspect the adapter config, error handler, whether exceptions propagate, the listener container's transaction mode, and broker policy.

### Common operational failures

| Symptom | Possible cause | How to verify |
|---|---|---|
| Queue has messages but handler does not run | Connection failure, wrong destination, listener not started, converter throwing exception | Check container status, destination, logs, metrics, and error channel |
| Messages disappear despite handler errors | AUTO_ACK, error handler swallowing exception, or async processing | Check transaction/acknowledge settings and synchronous boundaries |
| Duplicate message processing | Redelivery after rollback, producer resend, or crash between DB/JMS commits | Track `eventId` and JMS redelivered flag if available |
| One bad message clogs the queue | Unbounded redelivery | Establish retry/DLQ policy and handle poison messages |
| Orders processed out of order | Multiple consumers or async downstream | Check concurrency, ordering, and partitioning/grouping |
| Broker recovers but consumption is slow | Repeated recovery failures, container limits, or downstream bottleneck | Monitor active consumers, backlog, thread pool, and DB pool |

Log at minimum: destination name, `eventId`, JMS message ID/correlation ID (if available), error type, retry count, or redelivery indicator. Avoid logging full payloads containing sensitive data. Metrics to observe include **queue depth**, oldest message age, active consumer count, processing throughput, error rate, redelivery/DLQ count, and processing latency.

## 8. When to use an adapter, gateway, or polling?

| Need | Suitable component | Reason |
|---|---|---|
| Receive continuous JMS events with low latency | **JMS message-driven inbound adapter** | Listener is always ready to receive; no poll schedule needed |
| Check a queue only at predetermined times/batches | JMS polling inbound adapter | Poller controls receive cycles |
| Receive a JMS request and send a correlated JMS reply | JMS inbound gateway | Supports request/reply |
| Push Spring Messages onto a JMS queue/topic | JMS outbound channel adapter | Data flows from Spring Integration to the broker |
| Process the same event across multiple independent services | Topic with appropriate subscriptions | Each subscription receives topic distributions per configuration |

An application can use **multiple adapters** in the same system: receiving orders via message-driven JMS inbound, saving to DB, sending notifications to Kafka/AMQP via outbound adapters, updating files, or calling HTTP gateways. However, each connection boundary has its own timeouts, transactions, retries, and message contracts; no single JMS transaction automatically protects every step across external systems.

## 9. Hands-on exercise: ingesting orders from a queue

**Context:** the broker has the `orders.in` queue, and the app receives order JSON; each order must be stored only once by `eventId`. You can work through these steps in order:

1. **Setup:** configure a provider for `ConnectionFactory`, create the `orders.in` queue, register the message-driven flow, and implement `OrderImportService`.
2. **Happy path:** have the producer send valid payload `evt-2001`; observe the listener invoking the handler without waiting for a poll, and verify one order record appears in the DB.
3. **Idempotency:** resend the same `eventId` in another JMS message; verify the DB still shows only one business effect.
4. **Schema error:** send JSON missing `orderId`; verify the flow records the error and applies the designed retry/quarantine/DLQ policy.
5. **DB error:** simulate the service throwing an exception on DB timeout; verify redelivery with a transacted listener and exception propagation to the container.
6. **Async path:** replace the synchronous channel with an `ExecutorChannel` in a test environment, repeat the DB error, and explain why the original JMS rollback is no longer guaranteed.
7. **Concurrency:** send 100 messages across independent orders; change consumer concurrency from 1 to 3, measure throughput, and inspect completion ordering.
8. **Recovery:** temporarily stop the broker and restart it; observe listener status and backlog, without concluding success solely because the app process is still running.

To test the flow from broker to Spring Integration, use a real broker/provider or a matching container environment. Unit tests that only mock the handler will not prove acknowledgement, rollback, redelivery, durable subscription, or recovery behavior.

### Self-check questions

1. In a JMS message-driven inbound adapter, who triggers message reception? Why is `PollerMetadata` not needed?
2. What resources does `DefaultMessageListenerContainer` manage, and why can increasing `concurrentConsumers` change processing order?
3. Why is `AUTO_ACKNOWLEDGE` on DMLC not enough to guarantee redelivery when a handler throws an exception?
4. What happens to the JMS transaction if `errorChannel` handles and swallows the exception?
5. Why is an `eventId` key still needed even when the listener is configured with `sessionTransacted`?
6. Should you choose a JMS inbound gateway or an inbound channel adapter if the producer expects a JMS reply?

## 10. References

- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): message-driven channel adapter, gateway, converter, and transaction usage.
- [Spring Framework Reference — JMS Message Listener Containers](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): lifecycle, acknowledgement, transactions, and listener containers.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): `DirectChannel`, `ExecutorChannel`, `QueueChannel`, and their impact on synchronous/asynchronous processing.

**Remember:** a message-driven inbound adapter lets the broker actively push JMS messages into Spring Integration via a listener container. For safe production operation, explicitly define destination type, payload contract, concurrency, synchronous boundaries, acknowledgement/transactions, error propagation, and business-layer idempotency.
