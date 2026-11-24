# ACK, Receipts, Transactions, and Durability by Actual Broker in Spring STOMP

## Objectives

STOMP provides frames for clients to send messages, receive messages, and control processing acknowledgments. Four commonly confused concepts are:

- **ACK/NACK**: the consumer confirms it processed or rejects a received message.
- **Receipt**: the client asks the server to confirm that a sent frame has been processed by the server.
- **Transaction**: grouping SEND and ACK/NACK operations so the broker processes them as a single transactional unit.
- **Durability/persistence**: the ability to retain messages or subscriptions while no consumer is present or across a broker restart.

Spring WebSocket STOMP can use the built-in simple broker or relay to an external broker. ACK, receipt, transaction, and persistence capabilities depend on the actual STOMP broker. You cannot infer delivery guarantees solely from whether a destination is named **/queue** or **/topic**.

The Java snippets in this article are illustrative configuration or logic excerpts. Imports, DTOs, services, authentication setup, and broker initialization are omitted when not directly related to the concept being explained. The consumer snippet in the idempotency section is marked as pseudocode, not a complete STOMP listener.

## 1. Identify Which Layer Provides the Feature

A Spring STOMP application typically has three layers:

1. **STOMP client** sends frames such as SEND, SUBSCRIBE, ACK, NACK, BEGIN, COMMIT, and DISCONNECT.
2. **Spring WebSocket messaging** receives frames over WebSocket, authenticates, applies interceptors, and routes by destination.
3. **Broker** manages subscriptions, queues, delivery, acknowledgments, and message storage.

Simple broker configuration:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Spring's simple broker stores subscription information in memory and broadcasts messages to connected clients. It only supports a subset of STOMP; features such as ACK and receipts are not supported. Nor is it a durable broker or a distributed broker for clustering deployments.

When fuller capabilities are needed, Spring can relay STOMP to an external broker:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableStompBrokerRelay("/topic", "/queue")
            .setRelayHost("localhost")
            .setRelayPort(61613);
}
~~~

In a relay configuration, Spring forwards STOMP frames between WebSocket clients and the external broker. The external broker determines how ACK, NACK, receipts, transactions, durable queues, durable subscriptions, retries, dead-lettering, and replication are supported. The relay does not create those guarantees itself if the broker does not provide them.

## 2. ACK and NACK: Confirming Message Consumption

### ACK Modes on SUBSCRIBE

Clients select the acknowledgment mode using the **ack** header in the SUBSCRIBE frame. STOMP 1.2 defines three values:

| Mode | Meaning |
|---|---|
| **auto** | The server/broker considers the message acknowledged upon sending MESSAGE to the client; the client does not need to send ACK. |
| **client** | The client must send ACK/NACK. ACK is cumulative: it acknowledges the specified message and any earlier unacknowledged messages on the subscription. |
| **client-individual** | The client acknowledges each message individually; ACKing one message does not automatically acknowledge earlier messages. |

If **ack** is omitted, STOMP defaults to **auto**. For flows requiring confirmation after the application finishes processing, **client-individual** is typically chosen so each message has an independent decision.

Manual subscription example:

~~~text
SUBSCRIBE
id:orders-sub
destination:/queue/orders
ack:client-individual

^@
~~~

The **^@** symbol in the examples is a visual notation for the NUL byte terminating a STOMP frame. When actually sending, the STOMP library encodes the frame terminator automatically.

### ACK Must Use the Right Id

With manual ACK modes, the broker sends a MESSAGE frame containing an **ack** header. The client must use the value of this **ack** header in the ACK frame, and must not substitute **message-id** in its place.

Example MESSAGE:

~~~text
MESSAGE
subscription:orders-sub
message-id:msg-901
ack:ack-901
destination:/queue/orders
content-type:application/json

{"orderId":"ORD-901"}
^@
~~~

After the application finishes processing successfully:

~~~text
ACK
id:ack-901

^@
~~~

The **id** header in ACK matches the **ack** value on MESSAGE. This is a notable change in STOMP 1.2: ACK uses a dedicated id header corresponding to the message's ack token.

### NACK and Failure Handling

NACK informs the broker that the consumer could not process the message. The broker may redeliver the message, route it to another consumer, discard it, or move it to a dead-letter queue. Exact behavior depends on the broker and its configuration.

~~~text
NACK
id:ack-902

^@
~~~

Do not assume NACK always means immediate retry. For example, the RabbitMQ STOMP plugin supports a **requeue** header on NACK to control whether the message is returned to the queue or discarded/dead-lettered per configuration. Other brokers may have different policies.

### When to Send ACK in the Application

A consumer should send ACK after completing the processing step that the application considers successful:

1. Receive MESSAGE.
2. Validate the payload and processing permissions.
3. Execute business logic, write data, or save results.
4. Only after the step requiring guarantees completes, send ACK.
5. If processing fails, apply the appropriate retry/NACK policy.

If you ACK before writing data, the application can lose the message if the process crashes after ACK but before completing business logic. If you write data and lose connectivity before ACK, the broker may redeliver the message and business logic risks running twice. Therefore, consumers need safe duplicate handling using an idempotency key, unique constraint, inbox table, or deduplication mechanism.

ACK only confirms delivery state with the broker. It does not by itself prove that the application's database transaction committed, that an email was sent, or that an external system completed its work.

## 3. Receipt: Confirming a Frame Was Processed by the Server

Receipt is a mechanism for the client to request confirmation for a frame sent to the server. The client adds a **receipt** header with a unique value to a frame, such as SEND:

~~~text
SEND
destination:/queue/orders
receipt:send-901
content-type:application/json

{"orderId":"ORD-901"}
^@
~~~

When the server processes a frame requesting a receipt, the server responds with:

~~~text
RECEIPT
receipt-id:send-901

^@
~~~

The **receipt-id** value must match the **receipt** value the client sent. Client applications should maintain a map of pending receipt requests to match the right frame, set timeouts, and handle receiving ERROR or receiving no receipt.

### What Does a Receipt Confirm?

Per STOMP 1.2, RECEIPT confirms the server has processed the corresponding frame. Because STOMP transmits data sequentially over a stream, a receipt is also a cumulative confirmation that earlier frames were received by the server. However, those earlier frames might not have finished processing yet.

Therefore, a receipt for SEND does not by itself prove that:

- A consumer has received MESSAGE.
- A consumer has processed the business logic successfully.
- Business data has committed to the application's database.
- The message is guaranteed to survive every hardware failure or broker configuration.
- All subscribers have received a copy.

A receipt is confirmation at the protocol/broker boundary. To know that business work is complete, the application needs a business-layer response, such as an OrderProcessed event or a separate request-response result.

### Receipt and DISCONNECT

To disconnect cleanly, a client can send DISCONNECT with a receipt, wait for the corresponding RECEIPT, and only then close the socket:

~~~text
DISCONNECT
receipt:disconnect-17

^@
~~~

Server response:

~~~text
RECEIPT
receipt-id:disconnect-17

^@
~~~

This lets the client know the server received and processed the DISCONNECT frame and prior frames according to receipt semantics. Closing the socket immediately after DISCONNECT without waiting for a receipt may prevent the client from receiving final confirmation.

Spring's built-in simple broker does not support receipts. When using the broker relay, receipt capability depends on the external STOMP broker and whether the frames are processed successfully by the broker.

## 4. STOMP Transactions

STOMP 1.2 defines the following frames:

- **BEGIN**: starts a transaction.
- **COMMIT**: commits a transaction.
- **ABORT**: aborts a transaction.
- **SEND**, **ACK**, **NACK**: can include a **transaction** header to participate in an open transaction.

A transaction ID must be unique within the scope of a connection. Participating operations must use that exact ID.

Example sending multiple messages in one transaction:

~~~text
BEGIN
transaction:batch-01

^@

SEND
destination:/queue/a
transaction:batch-01

message A
^@

SEND
destination:/queue/b
transaction:batch-01

message B
^@

COMMIT
transaction:batch-01

^@
~~~

If the client sends ABORT instead of COMMIT, the broker cancels the operations in the transaction according to the broker's implementation. Uncommitted transactions are implicitly aborted when the client DISCONNECTs or the TCP connection drops per the STOMP specification.

### Transactions Can Include ACK

STOMP allows ACK/NACK to participate in a transaction as well. This is useful when a consumer simultaneously acknowledges an input message and sends one or more output messages within the same broker transaction:

~~~text
BEGIN
transaction:process-901

^@

ACK
id:ack-901
transaction:process-901

^@

SEND
destination:/queue/order-events
transaction:process-901
content-type:application/json

{"orderId":"ORD-901","status":"PROCESSED"}
^@

COMMIT
transaction:process-901

^@
~~~

The intent is for the broker to handle acknowledging the input message and emitting the output message as a single transactional unit. If the broker provides full support, a successful commit applies the participating operations; abort cancels them per broker semantics.

### Important Limitations

A STOMP transaction is a broker-managed transaction. It does not automatically include:

- The application's JDBC/JPA database transaction.
- HTTP calls to other services.
- Sending emails, writing files, or calling external APIs.
- Multiple independent brokers simultaneously.
- All operations inside a Spring **@Transactional** method.

For example, **@Transactional** on a service can commit the database, yet it does not automatically enroll a STOMP SEND frame from a client into that same transaction. Conversely, a STOMP broker COMMIT does not automatically commit data in the application's database.

If you need to coordinate database writes and event emission without losing events, consider the **Transactional Outbox**: write the business change and an outbox record in the same database transaction, then have a publisher read the outbox and send to the broker; the publisher marks items sent in a retryable workflow. Consumers still need idempotency because redelivery is a normal possibility in distributed systems.

Do not assume the simple broker supports BEGIN/COMMIT/ABORT with full transaction semantics. Spring's simple broker is only a partial STOMP implementation; if transactions are required, explicitly verify external broker support and test against the exact running version.

## 5. Message Durability and Subscription Durability

There are two distinct concepts:

- **Message persistence**: the message itself is stored durably by the broker so it can recover after a broker restart or failure according to configuration.
- **Durable subscription/queue**: the place holding messages destined for subscribers can continue to exist when a subscriber disconnects.

A persistent message sent to a temporary queue does not automatically create a durable subscription. Nor does a durable queue mean every message sent to it is persisted durably if the message is sent non-persistently or the broker lacks an appropriate storage mechanism enabled.

### STOMP Does Not Define Semantics for Destination Names

STOMP treats the **destination** header value as an opaque string interpreted by the broker. The name **/queue/orders** does not automatically guarantee a durable queue; nor does **/topic/news** automatically guarantee retaining messages when no subscriber is present.

A broker can define:

- Which destinations are queues, topics, exchanges, or streams.
- Whether queues are auto-created or must be pre-created.
- Whether queues are durable, exclusive, or auto-delete.
- Whether topic subscriptions are transient or durable.
- Whether messages have persistence, TTL, priority, or dead-lettering.
- When consumers are offline, whether messages are kept, dropped, or routed elsewhere.
- When a broker restarts or loses a node, what data is recovered.

Therefore, you must read the documentation for the exact broker, exact STOMP plugin, and exact version. Do not take RabbitMQ conventions and apply them to ActiveMQ or another broker.

## 6. Concrete Example with the RabbitMQ STOMP Plugin

RabbitMQ provides a STOMP plugin and supports destinations such as **/queue**, **/amq/queue**, **/topic**, and **/exchange**. These are semantics of the RabbitMQ STOMP adapter, not universal STOMP rules.

### Queue Destinations

With **/queue/orders**, RabbitMQ creates a queue managed via the STOMP gateway. Without extra queue parameters, the queue defaults to durable, non-exclusive, and non-auto-delete. Messages sent to the queue can be retained when no subscriber is present, depending on queue and message configuration.

Persistent SEND example:

~~~text
SEND
destination:/queue/orders
persistent:true
receipt:order-send-901
content-type:application/json

{"orderId":"ORD-901"}
^@
~~~

The **persistent:true** header is supported by the RabbitMQ STOMP plugin. With a persistent SEND, RabbitMQ only sends RECEIPT after receiving the corresponding publisher confirm from the broker. This is stronger than merely receiving the frame on the socket, yet still does not mean a consumer has processed the message.

### Topics and Durable Subscriptions

With **/topic/orders**, a regular RabbitMQ subscription uses a temporary, non-durable, auto-delete queue. Messages sent when no matching subscriber exists may be dropped.

To create a durable topic subscription, the RabbitMQ STOMP plugin supports the **durable:true** header (with **persistent:true** as an alias for legacy compatibility) and requires **auto-delete:false** so the queue backing the subscription is not deleted when the last subscriber disconnects. The subscription also requires an ID.

~~~text
SUBSCRIBE
id:orders-durable
destination:/topic/orders
ack:client-individual
durable:true
auto-delete:false

^@
~~~

A durable subscription lets a subscriber disconnect and reconnect while still receiving messages routed into the subscription's durable queue. Configure appropriate message persistence and queue durability if data must survive broker restarts. Also verify publisher confirms, queue types, replication, disk alarms, and retention policies in the deployment environment.

### ACK and NACK in RabbitMQ

The RabbitMQ STOMP plugin supports **auto**, **client**, and **client-individual**. NACK can use the **requeue** header to control whether the message is placed back into the queue; the plugin default is requeue. If using a dead-letter exchange, configure the corresponding queues and routing. Do not NACK endlessly without a retry limit or dead-letter policy, as that can create a processing loop.

RabbitMQ also supports **prefetch-count** on SUBSCRIBE to limit how many unacknowledged messages a consumer receives at once. This is a RabbitMQ-specific header, not a required STOMP header.

## 7. Example with ActiveMQ Classic and Broker Differences

ActiveMQ Classic supports STOMP and has its own destination conventions. Per ActiveMQ Classic documentation, STOMP messages are non-persistent by default; clients must add the **persistent:true** header on SEND if persistent delivery is desired.

~~~text
SEND
destination:/queue/ORDERS
persistent:true
receipt:orders-001
content-type:application/json

{"orderId":"ORD-001"}
^@
~~~

With ActiveMQ Classic, the **/queue/** or **/topic/** prefix maps to the corresponding JMS destination. However, semantics for queues, topics, persistence, transactions, prefetch, redelivery, and dead-lettering must be verified in the documentation for the specific ActiveMQ version.

One point requiring particular care: do not treat example headers or behaviors from ActiveMQ Apollo, ActiveMQ Classic, and ActiveMQ Artemis as interchangeable. These are different broker products/lines and can differ in STOMP support, mapping, and configuration.

## 8. Comparison Table of Confirmation Mechanisms

| Mechanism | Who Sends It? | What Does It Confirm? | What Does It Not Confirm? |
|---|---|---|---|
| ACK | Consumer client | Consumer informs broker the message was processed per subscription ack mode | Does not prove the database or external API committed |
| NACK | Consumer client | Consumer reports it could not process the message; broker applies its policy | Does not guarantee identical retry behavior across brokers |
| RECEIPT | Server/broker returns when a frame requesting receipt is processed | The frame was processed by the server; receipt also confirms earlier frames were received | Does not guarantee subscribers received it or business logic finished |
| COMMIT | Client sends to broker | Completes operations participating in the STOMP transaction per broker | Does not commit the application's database transaction |
| Persistence confirm | Broker-specific | Per broker mechanism, confirms persistent SEND was acknowledged/stored per its semantics | Does not replace consumer ACK or business confirmation |

These mechanisms address different boundaries. A reliable flow typically combines publisher confirms/receipts, persistent messages, durable queues or subscriptions, manual ACK, bounded retries, dead-lettering, and idempotent consumer processing. No single header provides end-to-end guarantees.

## 9. Designing Safe Consumers Under Retries and Redelivery

When a consumer disconnects, the broker may redeliver unacknowledged messages if the broker and ack mode support that behavior. This can cause messages to be processed multiple times. Applications should be designed for **at-least-once delivery** when a broker can redeliver, rather than assuming every message is processed strictly once.

A processing pattern:

~~~java
public void handle(OrderEvent event) {
    transactionTemplate.executeWithoutResult(status -> {
        if (inboxRepository.existsByEventId(event.eventId())) {
            return;
        }

        inboxRepository.save(new InboxRecord(event.eventId()));
        orderService.apply(event);
    });

    // Send ACK after the business transaction has committed successfully.
}
~~~

This is pseudocode illustrating processing boundaries, not a complete STOMP consumer. How you obtain the ACK token and send the ACK frame depends on the STOMP client library in use. Place a unique constraint on event ID in the inbox table and ensure checking the inbox, writing the inbox, and updating business data occur within the same database transaction. If two concurrent deliveries both pass the exists check, the unique constraint prevents duplicate recording; the consumer must handle duplicate errors per application policy and then ACK once it has confirmed that the event was processed now or previously.

Implementation principles:

- Each event has a stable, unique ID from the producer.
- The consumer records processed IDs within the same transaction as business changes.
- Only ACK after the business transaction succeeds.
- For transient errors, use retries with backoff and a maximum attempt limit.
- For unrecoverable errors, move messages to a dead-letter queue or log error records for manual handling.
- Monitor redelivery counts, queue depth, unacknowledged message counts, and oldest message age.
- Do not assume reconnect automatically restores a response sent when the previous session no longer exists.

## 10. Checks When Deploying Spring with a Broker Relay

When enabling the broker relay, verify the following settings and states:

1. The broker has enabled its STOMP listener on the right host/port and allows connections from Spring.
2. Credentials for the system connection and client connections are configured per environment; default guest accounts are not used in production.
3. Relay prefixes in Spring match destinations understood by the broker.
4. The broker has persistence, queue durability, durable subscriptions, and replication enabled per business requirements.
5. ACK/NACK, receipts, transactions, and extended headers are tested directly through a real STOMP client.
6. Broker restarts, network interruptions, client disconnects, consumer crashes, and redelivery are simulated in a test environment.
7. The application monitors broker relay status. Spring publishes **BrokerAvailabilityEvent** when the broker becomes available or loses connectivity; message-sending components should be ready to handle **MessageDeliveryException** when the broker is unavailable.
8. Timeouts exist for receipts and missing-receipt cases are handled; never wait indefinitely.
9. Business data has a reconciliation or replay mechanism if recovery after an outage is required.

Do not test only the happy path by sending one message and seeing the client receive it. Also test stopping the broker mid-send, stopping the consumer before ACK, stopping the consumer after database write but before ACK, and publishers not receiving receipts.

## 11. Checklist for Choosing Mechanisms by Requirement

| Requirement | Mechanism to Evaluate |
|---|---|
| Client needs to know the broker processed the SEND frame | **receipt** header and RECEIPT from broker |
| Consumer confirms only after finishing processing | SUBSCRIBE with **ack:client-individual** or an appropriate mode |
| Consumer wants to report processing failure | **NACK**, combined with retry/requeue/dead-letter per broker |
| Multiple SENDs and ACKs must commit together on the broker | **BEGIN/COMMIT/ABORT**, if the broker supports transactions |
| Retain messages while consumer is offline | Durable queue or durable subscription |
| Retain messages across broker restarts | Persistent messages with durable storage/queues and proper broker configuration |
| Avoid losing events when DB commits but broker send fails | Transactional Outbox or an equivalent transactional integration mechanism |
| Tolerate redelivery and duplicates | Idempotency, inbox/deduplication, and retry policy |
| Using Spring simple broker | Use only for basic messaging flows; do not rely on ACK/receipt or durable storage |

Before finalizing the architecture, explicitly write down what needs to be guaranteed: whether the frame reached the broker, the message was stored, the consumer received it, the consumer processed it, or the database and message broker committed together. Each requirement sits at a different boundary and may require a separate mechanism.

## References

- STOMP Protocol Specification 1.2 — ACK, NACK, RECEIPT, and transaction frames: https://stomp.github.io/stomp-specification-1.2.html
- Spring Framework — External Broker and simple broker limitations: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html
- Spring Framework — Broker Availability Events: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html
- RabbitMQ — STOMP Plugin, destinations, persistence, durable subscriptions, ACK/NACK: https://www.rabbitmq.com/docs/stomp
- ActiveMQ Classic — STOMP protocol and persistent messages: https://activemq.apache.org/components/classic/documentation/stomp
