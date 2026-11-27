# Event-driven Consumer Pattern in Spring Integration Adapters

> **Chapter:** Design patterns  
> **Topic:** Event-driven consumer pattern  
> **Scope:** Connecting external systems using **Spring Integration** inbound/outbound adapters, gateways, pollers, and MessageChannels; understanding message flows across HTTP, JMS, AMQP, Kafka, files, SFTP, and databases. Focuses on message contracts, consumer invocation, error handling, reliability, load throttling, and connection lifecycle.

## 1. Learning Objectives and Problem Statement

An integration application must react when new data arrives: an order is created, a transaction is approved, a file completes, or a message arrives from a broker. Instead of repeatedly asking “is there anything new yet?”, an **Event-driven Consumer** lets a source or intermediary **trigger processing when a message is delivered to the consumer**.

After this lesson, you can:

1. Explain the Event-driven Consumer in Enterprise Integration Patterns (EIP) and distinguish it from the Polling Consumer.
2. Identify **who proactively emits events, who holds messages before reception, and who decides acknowledgment** in each integration flow.
3. Correctly use Spring Integration's **SubscribableChannel**, **DirectChannel**, **ExecutorChannel**, **PublishSubscribeChannel**, and service activators.
4. Distinguish between a **message-driven inbound adapter** (e.g., JMS, AMQP, Kafka) and an **inbound gateway** (e.g., HTTP request/reply).
5. Design payload/header contracts, correlation, ordering, retries, dead-lettering, idempotency, and input validation.
6. Understand the difference between **message accepted by a channel**, **handler executed**, and **business transaction committed**.
7. Recognize cases where files/SFTP/DB still require polling or where changes are emitted as events via an intermediary layer.
8. Design labs with Java DSL, failure testing, and production operational checklists.

**Core question:** How do you react quickly to new data **while remaining business-correct when messages arrive duplicated, out of order, fail processing, or when the consumer temporarily stops**?

## 2. What is an Event-driven Consumer?

An **Event-driven Consumer** is a pattern where a consuming component is invoked or notified **when a message becomes available** according to the source, broker, or channel mechanism. On the application side, the handler is typically registered as a subscriber/listener rather than invoking a schedule to query business data itself.

For example, an ordering system emits an OrderCreated event; the message enters a broker, and then a listener/container delivers it to a handler to update inventory:

~~~text
10:00:00  Order Service creates order ORD-1007 and records event
10:00:00  Broker receives message, stores/dispatches per configured contract
10:00:00  Listener receives a message ready for processing
10:00:00  Spring Integration converts it into Message<OrderCreated>
10:00:00  Handler validates schema, business key, writes inventory state
10:00:00  Consumer/broker records ack/commit per policy
~~~

Not every system completes within the same millisecond. **Event-driven does not mean zero latency**, “never polling at the transport layer,” or “end-to-end exactly-once.”

### 2.1. Event, command, and message

| Term | Meaning | Example |
| --- | --- | --- |
| **Event** | Event describing something that happened | OrderCreated, PaymentApproved |
| **Command** | Request for another component to perform an action | ReserveInventory, GenerateInvoice |
| **Message** | Unit of data transported by the integration system | Payload OrderCreated with headers |
| **Consumer** | Component that receives and processes messages | Handler updating order status |
| **Producer** | Component that creates/sends messages | Order Service or inbound adapter |
| **Broker** | Intermediary holding/distributing messages if present | JMS broker, RabbitMQ, Kafka |
| **MessageChannel** | Abstraction routing messages inside Spring Integration | DirectChannel, ExecutorChannel |

An **event** is described at the business level; a **message** is the technical envelope. A message can carry a command, an event, or a request/reply. Thus, a handler invoked when a message reaches a channel can be technically event-driven even when the payload is a command.

### 2.2. Strengths and trade-offs

**Pros:**

- Reacts when messages arrive without needing frequent scheduled scans of business data.
- Can reduce empty queries and data-detection latency compared to sparse polling.
- Easily integrates with brokers, listeners, or HTTP inbound requests that already have dispatch mechanisms.
- Allows decoupling producers and consumers, deploying multiple handlers, and changing integration flows via channels.

**Trade-offs:**

- Requires understanding the broker/transport **delivery and ack mechanisms**; there is no universal guarantee across all adapters.
- Events can repeat, arrive late, or arrive out of desired order.
- A slow consumer can build up backlog, grow memory, or degrade upstream responsiveness.
- When an event has multiple subscribers, each subscriber must own its own error handling and idempotency logic.
- Adding asynchrony requires redesigning tracing, transactions, and completion checkpoints.

### 2.3. Example of when NOT to choose this pattern mechanically

If a partner only drops files onto SFTP every hour and **provides no file-completion event**, Spring Integration usually needs an **SFTP inbound polling adapter** to detect files first. You can turn the file into a message and **process it in an event-driven manner on downstream channels**; however, the SFTP data-fetching leg is still triggered by a poller.

Similarly, calling a REST API via an HTTP outbound gateway upon receiving an event **does not turn the REST server into a message broker**. Each layer must be described accurately by source, target, and contract.

## 3. Comparing Event-driven Consumer and Polling Consumer

| Criterion | Event-driven Consumer | Polling Consumer |
| --- | --- | --- |
| Trigger signal | Message/notification dispatched when data arrives | Scheduler/trigger invokes a receive operation |
| Common Spring Integration endpoints | Consumer on SubscribableChannel; message-driven inbound adapter | PollingConsumer on PollableChannel; SourcePollingChannelAdapter on MessageSource |
| Internal channels | DirectChannel, ExecutorChannel, PublishSubscribeChannel | QueueChannel, PriorityChannel |
| Source examples | HTTP requests, JMS/AMQP listeners, Kafka listeners | File/SFTP polling, database queries, HTTP changes API |
| Latency | Depends on transport, listener, queues, and processing | Adds wait time until the next poll cycle |
| Errors and redelivery | Depends on broker/container/transaction and channel | Depends on source, filter, poller, ack, and retry |
| Load throttling | Prefetch, consumer concurrency, executor queue, broker lag | Poll interval, maxMessagesPerPoll, receiveTimeout |
| Ordering | Per producer contract, broker partition/queue, concurrency | Per source ordering, claims, batching, and concurrency |
| Scalability | Listeners/consumer groups, partitions, subscribers | Multiple pollers, locks/leases/metadata stores |

**Common pitfall:** The Kafka Java consumer client has an **internal poll() loop**, but in Spring Integration, the **message-driven Kafka inbound adapter** uses a listener container to push records into the flow. Do not infer from the client method name that the Spring Integration endpoint is using a **PollingConsumer**.

### 3.1. When do you have to use both?

Suppose SFTP ingests data into an application that uses a broker:

~~~mermaid
flowchart LR
    SFTP["SFTP: files have no push mechanism"] --> POLL["SFTP SourcePollingChannelAdapter"]
    POLL --> VAL["Validate / Transform"]
    VAL --> BROKER["Outbound Adapter: publish event"]
    BROKER --> IN["Message-driven inbound adapter"]
    IN --> CH["SubscribableChannel"]
    CH --> BIZ["Business update handler"]
~~~

**The SFTP ingress uses polling**, while **the broker reception uses an event-driven consumer**. Both patterns complement each other; there is no need to force the entire system into a single pattern.

## 4. Position in Spring Integration

Spring Integration organizes systems around messages, channels, and endpoints. A consumer does not necessarily need to know directly whether the producer used Kafka, HTTP, or the filesystem; adapters translate external protocols into appropriate Spring **Messages**.

~~~mermaid
flowchart TD
    A["JMS/AMQP/Kafka listener or HTTP inbound gateway"] --> ADAPTER["Inbound Adapter / Gateway"]
    ADAPTER --> CHANNEL["MessageChannel"]
    CHANNEL --> HANDLER["Service Activator / Filter / Router / Transformer"]
    HANDLER --> NEXT["Outbound Adapter / Gateway"]
    NEXT --> DEST["Database / API / Broker / File"]
    HANDLER --> AUDIT["Observability + error handling"]
    ADAPTER --> AUDIT
~~~

### 4.1. Five components to distinguish

1. **Inbound channel adapter:** receives external data and emits messages into a channel. Can be message-driven or polling depending on the source and implementation.
2. **Inbound gateway:** receives an external request, sends it into the flow, and typically waits for a **reply** to return to the caller.
3. **MessageChannel:** defines how a Spring Message moves from one endpoint to another.
4. **MessageHandler/Service Activator:** processes messages, potentially transforming data or causing side effects.
5. **Outbound adapter/gateway:** sends messages to external systems; adapters are typically one-way, gateways handle request/reply.

Do not call **event-driven** a specific protocol. HTTP requests, JMS listeners, RabbitMQ listeners, and Kafka listeners have very different delivery characteristics even though all can trigger handlers when messages arrive.

### 4.2. Relevant channel types

| Channel | Dispatch model | Consequence |
| --- | --- | --- |
| **DirectChannel** | Sends message to a selected subscriber handler, typically on the sender's thread | Easy synchronous exception and transaction propagation; slow handlers slow down the sender |
| **ExecutorChannel** | Dispatches to a TaskExecutor | Decouples threads, increases concurrency; a successful `send()` does not mean business work finished |
| **PublishSubscribeChannel** | Broadcasts to multiple subscribers | Each subscriber has its own side effects/errors; must understand ordering, executors, and failure semantics |
| **QueueChannel** | Buffers messages for a consumer actively calling `receive()` | **PollableChannel**, usually needs a polling consumer; not direct event-driven dispatch |
| **PriorityChannel** | PollableChannel prioritizing messages on receive | Priority does not equal chronological ordering |
| **RendezvousChannel** | Exchange channel with rendezvous/synchronous handoff | Backpressure and blocking design differ from a simple queue |

By default, **DirectChannel** dispatches directly to a handler on the same thread; however, if the flow has an asynchronous channel downstream, a successful upstream send does not guarantee the entire pipeline has completed. **PublishSubscribeChannel** broadcasts to multiple subscribers, whereas DirectChannel does not broadcast.

### 4.3. Thread and completion-timing diagram

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant D as DirectChannel
    participant H as Handler
    participant DB as Database
    P->>D: send(message)
    D->>H: handle(message) on same call stack
    H->>DB: Persist business state
    DB-->>H: Commit succeeded
    H-->>D: Return
    D-->>P: send completes
    Note over P,DB: Illustrates synchronous flow only, not a multi-system transaction guarantee.
~~~

If you swap DirectChannel for ExecutorChannel, the **sender** can return as soon as the executor accepts the message, before the handler has run. You must monitor downstream results and handle errors along an asynchronous path.

## 5. Event-driven Does Not Mean “Never Polling”

Each layer can use its own technique:

- JMS/AMQP listeners can have a container and consumer callbacks from the broker; the app flow receives in a message-driven fashion.
- The Kafka consumer client must poll the broker to maintain groups/offsets; the **listener container** manages the poll loop and dispatches messages to Spring Integration.
- An HTTP server listens for requests on a socket; when a request arrives, the inbound gateway starts the flow on demand without polling a business data source.
- File/SFTP/JDBC usually require a polling schedule unless reliable change notifications/CDC/event sources are deployed.
- An internal QueueChannel buffers messages and requires a consumer to actively call `receive()`.

**Mini-exercise:** label these three statements separately: “Kafka client polls the broker,” “Spring Integration Kafka adapter is message-driven,” “handler on DirectChannel is invoked on send.” All three can be true simultaneously; they describe **three different layers**.

## 6. Designing Message Contracts for Consumers

An event-driven system is only maintainable when producers and consumers agree on **which event occurred**, **what data is inside the message**, **contract versions**, and **how processing status is confirmed**.

### 6.1. Payload, headers, and metadata

Spring Integration uses **Message<T>** (from Spring Messaging) to combine a payload with headers. Example business JSON payload:

~~~json
{
  "eventId": "EVT-LAB-1042",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "occurredAt": "2026-11-23T10:01:23+07:00",
  "aggregateId": "ORD-LAB-0501",
  "aggregateVersion": 3,
  "tenantId": "TENANT-LAB-01",
  "data": {
    "customerId": "CUST-LAB-032",
    "currency": "VND",
    "amount": 250000
  }
}
~~~

These values are illustrative data, not a default schema of Spring Integration or any broker. Transport headers may include **message ID, timestamp, trace ID, correlation ID, content type, routing key, partition key, retry count** depending on the adapter and mapping. Never assume headers from an external source are always trustworthy or always present.

### 6.2. Contract checklist

- [ ] Every event has a stable **eventId/business key**, not just a newly generated message ID on retry.
- [ ] Has an **event type** and **schema version** or an equivalent schema identification mechanism.
- [ ] Includes resource/aggregate keys and tenant ID if the application requires data isolation.
- [ ] Event occurrence time, reception time, and processing time are distinguished.
- [ ] Payload defines validation rules, data types, units, encoding, and size limits.
- [ ] Specifies which sources are authorized to emit this event type and enforces appropriate authentication/authorization.
- [ ] Never places credentials, passwords, private keys, or raw tokens in payloads/headers/logs.
- [ ] Consumer tolerates optional fields and known versions or rejects incompatible schemas in a controlled way.
- [ ] Defines rules for late, duplicate, and out-of-order events.
- [ ] Has criteria distinguishing **received**, **validated**, **processed**, **committed**, and **acknowledged**.

**EventId is not synonymous with MessageHeaders.ID.** A re-sent event may get a new technical message ID; the business event ID must remain stable for idempotency to work across retries, restarts, and redeliveries.

### 6.3. Consumers must not trust all headers

For example, if an HTTP message carries `X-Tenant-Id: TENANT-B`, the backend must not blindly let a user from TENANT-A update TENANT-B data. Tenant or permissions must be verified against trusted identity and sources. Similarly, if a broker only restricts which producer can publish to a topic, the consumer still must validate schemas and business rules before writing sensitive data.

### 6.4. Versioning and compatibility

Suppose OrderCreated v1 has `customerId` and `amount`, while v2 adds `currency` and `discount`. Compatibility can be preserved by adding optional fields with sensible defaults; however, changing the semantics of `amount` from minor currency units to major currency units is a **breaking change** even if the JSON still parses.

Recorded decisions:

| Scenario | Suggested handling |
| --- | --- |
| Supported schemaVersion received | Parse/validate and process |
| Unsupported version received | Quarantine/DLQ, alert schema mismatch; do not silently drop |
| Missing required field | Reject with reason or route to error store |
| New field without business impact | Allow per compatibility policy |
| Stale event for the same aggregate | Compare version/state before writing; ignore or reconcile |

## 7. Java DSL: Simple Event-driven Consumer with DirectChannel

We start without a broker to isolate the exact roles of channels and handlers. **A producer calls `send(message)`**, and Spring Integration routes the message to the service activator subscribed to `DirectChannel`. There is no poller in this example.

### 7.1. Spring Integration flow configuration

The code illustrates Spring Integration 6.x style and Java 17, using **spring-integration-core** and the Spring context. When adopting into a real project, verify your exact dependencies and versions.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;

@Configuration
@EnableIntegration
public class OrderEventIntegration {

    @Bean
    public MessageChannel orderEvents() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow orderEventFlow() {
        return IntegrationFlow
                .from("orderEvents")
                .handle((MessageHandler) message -> {
                    Object payload = message.getPayload();
                    System.out.println("Received event: " + payload);
                    // In practice: validate -> idempotency -> business transaction.
                })
                .get();
    }
}
~~~

The handler subscribes to messages sent to the channel named **orderEvents**. With a synchronous DirectChannel and a handler that only logs, the send call waits until the handler returns; however, **printing a log is not a durable processing guarantee**.

### 7.2. Application-side producer

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {
    private final MessageChannel channel;

    public OrderEventPublisher(
            @Qualifier("orderEvents") MessageChannel channel) {
        this.channel = channel;
    }

    public void publish(String eventId, String orderId) {
        String event = "OrderCreated:" + orderId;
        boolean accepted = channel.send(
                MessageBuilder.withPayload(event)
                        .setHeader("businessEventId", eventId)
                        .build()
        );
        if (!accepted) {
            throw new IllegalStateException("Message not accepted");
        }
    }
}
~~~

**Key point to understand:** the Java producer is sending to an in-application channel, **not to a durable broker**. If invoking the handler throws an exception, a synchronous sender may receive that exception; with an asynchronous channel, the return value of `send()` typically only means the message was accepted for dispatch.

### 7.3. MessageHandler, Service Activator, and transformer

A flow can consist of multiple steps:

~~~text
OrderEventPublisher
  -> DirectChannel
  -> Filter (only valid OrderCreated)
  -> Transformer (JSON -> OrderEvent DTO)
  -> Service Activator (businessService.accept)
  -> Outbound Adapter or Gateway (when needed)
~~~

A transformer should not declare business commit solely because parsing succeeded. The service activator must check **the business key, order status, tenant permissions, and data validity**, and only acknowledge success at the point where results are persisted per contract.

### 7.4. Java annotations instead of Java DSL

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class AuditEventHandler {

    @ServiceActivator(inputChannel = "orderEvents")
    public void onEvent(String payload) {
        System.out.println("Processed: " + payload);
    }
}
~~~

Note that this example is **an alternative** to the handler declared in the DSL; do not attach both to the same DirectChannel expecting both to always receive every message. **DirectChannel selects one subscriber handler per dispatch**, it does not broadcast; if fan-out is needed, choose an appropriate channel structure such as PublishSubscribeChannel.

## 8. Asynchronous Dispatch with ExecutorChannel and Fan-Out

A handler calling a slow external API can hold the source thread for too long. You can **offload dispatch via an executor**, but in return you must manage queues, errors, and ordering.

### 8.1. ExecutorChannel

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.messaging.MessageChannel;

@Configuration
public class AsyncEventChannels {

    @Bean
    public ThreadPoolTaskExecutor orderEventExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("order-events-");
        return executor;
    }

    @Bean
    public MessageChannel asynchronousOrderEvents(
            ThreadPoolTaskExecutor orderEventExecutor) {
        return new ExecutorChannel(orderEventExecutor);
    }
}
~~~

**What must be designed next:**

- When the executor queue is full, `send()` may be rejected or subject to the executor's rejection policy. Never silently drop messages.
- The handler runs on a different thread; the sender thread's transaction context **does not automatically propagate**.
- Handlers can run concurrently and finish out of send order.
- Exceptions in the handler do not necessarily return to the producer; asynchronous error handling and monitoring are required.
- The executor queue is not a **durable store** across JVM crashes by default.
- If messages come from JMS/AMQP/Kafka, re-verify **ack timing**; pushing quickly into an executor and acking the broker too early can lose data if the JVM crashes.

### 8.2. PublishSubscribeChannel for multi-branch broadcasting

~~~mermaid
flowchart LR
    EVENT["OrderCreated"] --> PUB["PublishSubscribeChannel"]
    PUB --> INVOICE["Invoice handler"]
    PUB --> INVENTORY["Inventory handler"]
    PUB --> ANALYTICS["Analytics handler"]
~~~

**Fan-out** is useful when multiple independent components care about one event. However, how a failure in the invoice handler affects the inventory handler depends on **channel dispatch, executor, transactions, and error strategy**. Do not assume all three receive and commit under a single cross-system transaction.

If you require **every subscriber to receive the message again after a crash**, an in-memory PublishSubscribeChannel is insufficient; consider **broker topics/exchanges, durable subscriptions, consumer groups, or an outbox/inbox mechanism**.

### 8.3. DirectChannel is not a broadcast channel

If you attach two service activators to the same DirectChannel, the channel selects one subscriber per message according to its dispatch strategy. Under default configuration, do not expect both handlers to run for every message. Choose **PublishSubscribeChannel** when the goal is replicating messages to multiple subscribers.

## 9. Message-driven Inbound Adapter and Inbound Gateway

In Spring Integration, event-driven flows often begin with an **adapter or gateway** receiving an external signal. These two endpoint types must not be confused because they have different **reply/ack contracts**.

| Inbound endpoint | Input | Application-side outcome | Scenario |
| --- | --- | --- | --- |
| **Message-driven inbound channel adapter** | Broker/container listener receives message | Emits message to channel, typically one-way in the flow | JMS, AMQP, Kafka events |
| **Inbound gateway** | Incoming request from another system | Sends request into the flow and waits for or maps a reply | HTTP requests, JMS/AMQP request-reply |
| **Polling inbound channel adapter** | MessageSource triggered on a schedule | Sends newly fetched message to channel | File, SFTP, JDBC polling |
| **Application channel producer** | Internal code calls MessageChannel.send | Flow processes message immediately or asynchronously | Business service emitting internal events |

### 9.1. One-way vs. request/reply

When a client calls HTTP **POST /orders**, the server usually must return an HTTP response. Using an **HTTP inbound gateway**, the request becomes a Spring Message; the flow processes it and returns a reply as an HTTP response. This is *request/reply* even though the handler is triggered per request.

Conversely, when a RabbitMQ queue holds **OrderCreated**, a message-driven inbound adapter delivers the message to the handler, and broker acknowledgment is handled per container configuration. Do not assume every event requires a reply message back to the producer.

### 9.2. Turning an HTTP request into a business event

~~~mermaid
sequenceDiagram
    participant C as HTTP Client
    participant H as HTTP Inbound Gateway
    participant V as Validate + Business Service
    participant O as Outbox
    participant B as Broker
    participant L as Message-driven Inbound Adapter
    participant S as Subscriber
    C->>H: POST /orders
    H->>V: Spring Message request
    V->>O: Commit order + outbox event
    V-->>H: Order creation result
    H-->>C: HTTP response
    O->>B: Publish (via relay)
    B->>L: Deliver event
    L->>S: Process OrderCreated
~~~

This design illustrates the **transactional outbox**: saving business changes and an outbox record in the same DB transaction, followed by a relay publishing the event. If the relay crashes after publishing but before marking as published, the broker may receive the event again; subscribers must be idempotent.

### 9.3. Do not treat HTTP 200 as whole-system completion

When a gateway returns HTTP 200/201, it usually confirms the **request handler** conditions under the API contract. It does not prove all asynchronous consumers have finished. If the API accepts work asynchronously, you can use 202 Accepted and a status resource; exact policy depends on the system.

## 10. Event-driven Consumers with JMS, AMQP, and Kafka

What these three systems share is transport infrastructure for messages, yet **acknowledgment, ordering units, and redelivery mechanics** differ. When connecting Spring Integration, choose an inbound adapter or gateway suited to the **protocol and purpose**, not merely to make all configurations look identical.

### 10.1. JMS: listeners and transactions

**JMS** defines a Java messaging API with destinations such as Queues and Topics. A message listener container receives messages and dispatches them to consumers. Spring Integration provides JMS adapters/gateways, including **message-driven** reception.

Typical flow:

~~~text
JMS Queue "orders.events"
    -> JMS listener container
    -> Spring Integration JMS message-driven inbound adapter
    -> MessageChannel
    -> validate + service activator
    -> database/outbound adapter
~~~

An *illustrative* Java DSL example for the listener branch:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;
import org.springframework.messaging.MessageHandler;

@Configuration
@EnableIntegration
public class JmsInboundFlow {

    @Bean
    public IntegrationFlow orderJmsFlow(ConnectionFactory connectionFactory) {
        return IntegrationFlow.from(
                    Jms.messageDrivenChannelAdapter(connectionFactory)
                       .destination("orders.events")
                )
                .handle((MessageHandler) message -> {
                    Object event = message.getPayload();
                    System.out.println("JMS message: " + event);
                    // Business processing + idempotent persistence.
                })
                .get();
    }
}
~~~

This example follows modern Spring Integration JMS/Java DSL API families; exact overloads, container factories, `jakarta.jms` packages, and dependencies must match your target version. The snippet **does not configure durability, a transaction manager, or a DLQ**, so it must not be used verbatim as a production standard.

**Decisions to make before deployment:**

- A JMS Queue typically delivers messages to one consumer in a competing-consumers group; a Topic has publish-subscribe semantics, with durability depending on subscription and broker settings.
- Acknowledge modes such as AUTO_ACKNOWLEDGE, CLIENT_ACKNOWLEDGE, or transacted sessions behave differently; the Spring listener container and adapter also influence actual ack timing.
- If the handler fails, is the message redelivered, after how many attempts, and where is the DLQ located?
- If the handler immediately hands off to an **ExecutorChannel** and returns, the listener may finish before async work actually commits. Never assume exceptions on downstream threads roll back broker consumption.
- A JMS transaction does not automatically span an HTTP request or a separate DB transaction; use outbox/idempotency when no coordinated transaction mechanism is available.

### 10.2. AMQP/RabbitMQ: ack, nack, prefetch, and dead-letter

AMQP brokers such as RabbitMQ manage queues, exchanges, and routing. Spring Integration provides an AMQP inbound adapter backed by a listener container, forwarding broker-delivered messages to a channel.

| Component | Meaning to check |
| --- | --- |
| **Exchange/routing key** | Which queue the producer routes messages to via bindings |
| **Queue** | Whether it is durable, messages are persistent, and TTL/quorum/policies apply |
| **Consumer listener** | How many consumers, which connections/channels receive messages |
| **Prefetch** | How many unacked messages the broker delivers to a consumer |
| **Ack / nack / reject** | Behavior upon completion, error, or requeue intent |
| **Dead-letter** | Where failed/TTL-expired/policy-exceeded messages go |
| **Ordering** | How concurrency, requeueing, and redelivery alter observed order |

Architectural pseudocode:

~~~text
RabbitMQ orders.exchange
  -> orders.created.queue
  -> AMQP listener container
  -> AMQP message-driven inbound adapter
  -> DirectChannel
  -> validate + idempotent order handler
  -> ack per listener configuration and processing result
~~~

**Ack note:** do not ack immediately after merely enqueuing into an in-memory executor if the business criterion is DB commit. If an async channel is mandatory, use a durable design with explicit acknowledgement coordination. With redelivery, the same message can be processed again; business idempotency is required.

**A DLQ is not an automatic trash bin:** it needs retention, reading/quarantine mechanisms, error classification, access controls, alerts, and a controlled replay procedure.

### 10.3. Kafka: listener container, partitions, and offsets

Kafka stores records in partitioned topics. Consumer groups assign partitions across consumer instances; the listener container invokes handlers when records/batches are polled.

~~~mermaid
flowchart LR
    PRODUCER["Order Service"] --> TOPIC["Kafka topic: orders.events"]
    TOPIC --> P0["Partition 0"]
    TOPIC --> P1["Partition 1"]
    P0 --> C0["Consumer group: instance A"]
    P1 --> C1["Consumer group: instance B"]
    C0 --> SI0["Spring Integration Kafka inbound adapter"]
    C1 --> SI1["Spring Integration Kafka inbound adapter"]
    SI0 --> H["Handler + idempotency"]
    SI1 --> H
~~~

**What you must know precisely:**

1. **Offsets:** which offsets are committed and when relative to handler/transaction completion?
2. **Groups:** consumers in the same group divide partitions; each consumer does not receive a full copy of every message.
3. **Partition key:** if per-aggregate event ordering is required, select an appropriate key/partitioning; Kafka preserves order within a partition under broker/producer conditions, not globally across all partitions.
4. **Rebalance:** partition ownership shifts when instances join/leave; records can be reprocessed if commits/processing did not finish.
5. **Retry and DLT:** failing records are retried, skipped, or sent to a dead-letter topic per configuration; do not let one bad record stall an entire partition indefinitely.
6. **Async handoff:** if the listener returns before downstream handlers commit, offset/ack and failure paths must be redesigned.

Kafka supports options like record/batch listeners, transactions, and error handlers; actual configuration depends on the versions of **Spring for Apache Kafka and Spring Integration Kafka** in use. Never treat one auto-commit or manual-ack configuration as a universal rule for all adapters.

### 10.4. Comparison table for design decisions

| Question | JMS | AMQP/RabbitMQ | Kafka |
| --- | --- | --- | --- |
| Consumption unit | Message in Queue/Topic | Message from queue | Record/batch in partition |
| Spring Integration interface | JMS listener adapter/gateway | AMQP listener adapter/gateway | Kafka listener adapter |
| Progress confirmation | Ack/transaction per session/container | Ack/nack and broker delivery | Offset/transaction commit per container |
| Redelivery | Redelivery per broker/session | Requeue/redelivery/DLQ | Reprocess from offset, retry/DLT |
| Ordering | Depends on destination and concurrency | Depends on queue, concurrency, requeue | Within partition, under relevant conditions |
| Fan-out | Topic/subscription | Exchange → multiple queues | Multiple consumer groups |
| Backpressure | Consumer concurrency/prefetch if supported | Prefetch + concurrency + queue depth | Lag + partitions + concurrency |

No row guarantees **exactly-once across all external targets**. When a consumer updates a DB and then sends HTTP to another service, you still need idempotency and failure handling between the two operations.

## 11. HTTP, Files, SFTP, and Databases in Event-driven Architecture

Not every protocol provides native “push events” in the way an application needs. You can combine adapters to convert **the appearance of data** into event-driven messages for downstream processing.

### 11.1. HTTP inbound gateway

An HTTP server receives requests when clients connect; Spring Integration's **HTTP inbound gateway** converts the request into a Message, routes it into the flow, and awaits a reply per the request/reply contract. You must:

- Authenticate callers and check authorization against the actual target resource.
- Bound payload sizes, validate schemas, content types, and tenants.
- Set reasonable timeouts; for long-running work, consider asynchronous broker handoff and 202 Accepted / a status endpoint.
- Ensure client HTTP retries do not cause duplicate side effects; use a business idempotency key where appropriate.
- Never treat arbitrary HTTP request headers as a trusted source of access rights.

An HTTP outbound gateway calling an external system upon receiving an event can also time out after the target already processed the request. Consumers must **read back state or perform idempotent retries** rather than assuming a timeout means the remote side did nothing.

### 11.2. Files and SFTP: event-driven downstream, polling at the source

In many designs, file or SFTP inbound adapters must **poll to detect new files**. Once the adapter creates a Spring Message and sends it to a DirectChannel, handlers are **dispatched per message**. This is a hybrid flow:

~~~text
File/SFTP (scheduled poll)
    -> Message<File> / Message<InputStream>
    -> DirectChannel
    -> Validate file completion
    -> Transform CSV/JSON
    -> Handler -> DB / outbound broker adapter
~~~

With files/SFTP, data may still be uploading, so you need temp-name/rename conventions, markers, accepted-file filters, and persistent metadata stores. Never delete/move files solely because a message was sent if downstream business logic has not yet committed. When streaming, manage stream/session resources and corresponding retry strategies.

### 11.3. Databases: polling, CDC, and outbox

Databases can surface changes in three ways:

| Approach | Nature | When appropriate |
| --- | --- | --- |
| **JDBC polling** | Runs scheduled queries to find READY rows | Small apps or DBs without change streams |
| **CDC connector** | Reads changes from transaction logs, emits messages | Need DB-sourced change event streams with suitable tooling |
| **Transactional outbox** | Business logic writes an outbox record in the same transaction; relay emits events | Want to bind business commits reliably to event record creation |

**CDC** can be event-driven from the perspective of a broker consumer, even though the underlying connector reads the transaction log. An **outbox relay** may also use polling while the downstream Kafka/JMS listener remains event-driven. Clearly document the source of truth and where an event is considered emitted/received.

### 11.4. When is a gateway better than an adapter?

| Need | Suggested choice |
| --- | --- |
| Receive a webhook and return processing status to the caller | HTTP inbound gateway |
| One-way reception from event queues | Message-driven inbound adapter |
| Call an API needing a response to continue the flow | Outbound gateway |
| Send notifications/fire-and-forget to a target system | Outbound channel adapter |
| Send a message and wait for a reply over JMS/AMQP | Inbound/outbound gateway with correlation and timeouts |

Do not use request/reply gateways for event broadcasts if no reply is required. Every synchronous wait for a reply increases coupling, timeout risk, and correlation state management.

## 12. Delivery Semantics: Receiving a Message is Not Exactly-Once Processing

Event-driven systems typically operate under one or more guarantee levels:

| Target level | Description | Consequence |
| --- | --- | --- |
| **At-most-once** | A message is never redelivered once the system considers it received | Business effects may be lost if failures happen after ack |
| **At-least-once** | A message may be redelivered if not confirmed successful | Requires idempotency to avoid duplicate side effects |
| **Effectively-once** | Final business side effects are protected from duplicates | Requires business keys, proper transactions, and reconciliation |
| **Scoped exactly-once** | Some brokers/streams offer transaction semantics within a narrow boundary | Does not automatically cover HTTP, files, external DBs, and the whole system together |

### 12.1. Classic failure window

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant L as Listener
    participant DB as Business DB
    B->>L: Deliver OrderCreated(eventId=E1)
    L->>DB: Insert order using E1
    DB-->>L: Commit success
    Note over L: JVM crash before ack/offset commit
    B->>L: Redeliver E1
    L->>DB: Repeat operation
    Note over DB: If not idempotent, side effects may repeat
~~~

**Principle:** design for receiving the same event again without corrupting data, and never acknowledge prematurely before business actions meet completion criteria.

### 12.2. Layered controls that must work together

1. **Broker delivery/ack policy:** defines when messages are redelivered or offsets committed.
2. **Consumer transactions:** executes DB work with proper unique constraints/optimistic concurrency.
3. **Inbox/idempotent repository:** records processed events by trusted business eventId.
4. **Outbox for downstream events:** ties downstream event creation to the business transaction.
5. **Reconciliation:** resolves lost ACKs, timeouts, and cross-system gaps.
6. **Dead-letter/quarantine:** stores unprocessable events with reasons, owners, and replay support.

## 13. Idempotent Consumer and Business Keys

In EIP, **Idempotent Consumer** is closely paired with Event-driven Consumer: when the same event arrives again, side effects must not be unintentionally duplicated.

### 13.1. Choosing a stable key

Several options:

- **eventId** generated by the producer and preserved across retries.
- **aggregateId + aggregateVersion** when each business change version must be applied once.
- **sourceSystem + businessKey + operationVersion** when integrating multiple sources.

Do not rely solely on runtime message IDs or reception timestamps; they can change on redelivery. In multi-tenant systems, the business key often must include tenant/source so valid events from separate scopes do not collide.

### 13.2. Sample inbox table

~~~sql
CREATE TABLE consumer_inbox (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(180) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

If the handler updates a business DB, it can insert into the inbox **within the same DB transaction** as the business state change. When a duplicate violates the unique constraint, the consumer recognizes it as already processed. Ensure the inbox row reflects **completed processing**, not merely “started.”

### 13.3. Pseudocode for an idempotent event handler

~~~text
consume(message):
  event = validateSchemaAndSource(message)
  with transaction:
      if inbox.exists(consumerName, event.eventId):
          return ALREADY_PROCESSED

      current = loadAggregateForUpdate(event.aggregateId)
      if event.aggregateVersion <= current.lastAppliedVersion:
          inbox.recordProcessed(event.eventId)
          return STALE_OR_DUPLICATE

      applyBusinessChange(current, event)
      inbox.recordProcessed(event.eventId)
      commit

  acknowledgeByTransportContract()
~~~

This is a logic model, not complete Java. Concurrency must be handled via unique constraints and proper transaction isolation; a non-atomic “check then insert” can let two consumers pass simultaneously. If a message jumps ahead in event version, policy must decide whether to wait for missing events or fetch a snapshot from the source.

### 13.4. Side effects outside the DB

If a consumer sends an email or calls an HTTP payment API, the DB inbox transaction **does not roll back** an already-executed email or payment. You need:

- Target APIs supporting idempotency keys or status queries by business key.
- Outbox/workers for post-commit side effects with controlled retries.
- Reconciliation when a response is lost even though the side effect may have occurred.
- Avoid “catch exception and return success,” which tricks the broker into acking before processing.

### 13.5. Multiple subscribers must dedupe per consumer

On a topic, both Billing and Analytics need to process E1 once **for their own domain**. The inbox key should include **consumer name or handler identity**. Using a global dedupe store shared across subscribers would cause Billing processing E1 to make Analytics wrongly skip E1.

## 14. Ordering, Concurrency, and Preserving Business State

Event-driven systems often emphasize speed, yet **concurrent events must never allow stale state to overwrite newer state**.

### 14.1. Three different kinds of ordering

| Order type | Example | Condition |
| --- | --- | --- |
| **Transport order** | Kafka within a single partition | Producer, partition key, retries, and consumer must satisfy constraints |
| **Processing start order** | Handler starts E1 before E2 | Executor concurrency and scheduling can alter this |
| **Commit order** | E2 commits before E1 | Handler latency, DB locks, API calls, and retries affect this |

A queue delivering E1 before E2 **does not guarantee E1 commits before E2** if the app dispatches across multiple threads. When account, order, or inventory state has sequential dependencies, use **aggregate versions** or per-key serialization to prevent stale updates.

### 14.2. Out-of-order event example

~~~text
E1: AccountStatusChanged(user=U7, version=5, status=ACTIVE)
E2: AccountStatusChanged(user=U7, version=6, status=DISABLED)

Consumer receives E2 first and saves DISABLED.
E1 arrives late.

Wrong: overwrite with ACTIVE because it was the most recently received message.
Right: check version 5 < version 6, ignore or reconcile against the source.
~~~

This is a **state versioning** problem; it cannot be solved merely by raising message priority. When a version is missing, policy may require reading authoritative state from the source or waiting for missing data.

### 14.3. Strategies for choosing concurrency levels

- **Serial consumer:** fits simple ordering needs with bounded throughput.
- **Partition by business key:** preserves ordering within the same customer/order while processing different keys in parallel.
- **Optimistic concurrency:** writes conditionally on unchanged version; handles conflicts with controlled retries/skips.
- **Pessimistic lock/claim:** protects DB rows within transactions; avoid holding locks too long.
- **Compensation:** if irreversible side effects already occurred, provide an approved business compensation workflow.

### 14.4. Fan-out and success ownership

Suppose OrderCreated goes to three handlers: **Inventory**, **Invoice**, and **Analytics**:

~~~mermaid
flowchart TD
    E["OrderCreated E1"] --> TOPIC["Broker topic or fan-out"]
    TOPIC --> A["Inventory: commit OK"]
    TOPIC --> B["Invoice: transient error"]
    TOPIC --> C["Analytics: processed OK"]
    B --> RETRY["Retry / DLT / Escalation"]
~~~

This is not a distributed transaction by default. **Inventory succeeding does not mean Invoice succeeded**, and retrying Invoice should not force Inventory to rerun its entire business logic if each subscriber has independent delivery/idempotency.

With an **in-JVM PublishSubscribeChannel**, consider specific failure propagation and how one failing handler can affect other subscribers under synchronous dispatch. With multi-queue/group brokers, each subscription tracks progress independently per broker semantics.

## 15. Error Flows, Retries, and Dead-Lettering

A consumer can fail during **reception/deserialization**, **validation**, **business logic**, **DB commit**, **external calls**, or **broker ack**. Do not push all failures into the same unbounded retry loop.

### 15.1. Error classification

| Category | Example | Handling direction |
| --- | --- | --- |
| **Schema/deserialize** | JSON missing required field, unsupported version | Quarantine/DLT, record reason and owner; no infinite retries |
| **Authorization/source trust** | Spoofed event source, invalid tenant | Reject, security alert, create no side effects |
| **Business validation** | Order violates defined business rules | Business rejection, audit, likely no redelivery |
| **Transient infrastructure** | DB timeout, temporary broker disconnect, HTTP 503 | Bounded retry with backoff |
| **Rate limit** | HTTP 429, target service quota | Respect Retry-After and reduce concurrency |
| **Concurrency conflict** | Optimistic locking / unique constraint | Distinguish valid duplicates from conflicts needing resolution |
| **Poison message** | An event that consistently throws exceptions | DLT/quarantine after retry cap |
| **Ack failure/rebalance** | Business committed before offset committed | May redeliver; requires idempotency |

### 15.2. Synchronous vs. asynchronous exception handling

**DirectChannel + synchronous handler:** exceptions from the handler can unwind the call stack back to the inbound endpoint. Broker listeners/containers can use exceptions to trigger rollback/redelivery when configured appropriately.

**ExecutorChannel:** the handler runs on another thread; producers or listeners typically **cannot catch exceptions like a normal synchronous call**. You need asynchronous error paths, retries, and durable handoffs to avoid losing messages.

**Gateway:** exceptions or timeouts must map to appropriate responses/handlers. Never return HTTP 200 success when downstream failed and the flow swallowed the error, unless the contract explicitly only acknowledges “accepted.”

### 15.3. ErrorChannel and ErrorMessage

Spring Integration supports routing many asynchronous errors to an **error channel** wrapped as **ErrorMessages**. However, the error source, ErrorMessage construction, and actual path depend on adapters, endpoints, ErrorHandler configuration, and async boundaries.

**Checklist for building error flows:**

- [ ] Separate message reception, data transformation, handler, and outbound adapter errors.
- [ ] Safely log source, business eventId, target, attempt, exception class, and trace ID.
- [ ] Never log plaintext credentials or unnecessary sensitive payload data.
- [ ] For transient errors, define retry/backoff and maximum attempts.
- [ ] For unrecoverable errors, provide a DLT/quarantine and an owner able to replay.
- [ ] Verify whether the error handler **rethrows**, **acks**, **nacks**, or **swallows** per protocol.
- [ ] Never route messages to an **in-memory-only** error queue and claim crash durability.
- [ ] Track repeated failures on the same key to prevent poison events from causing congestion.

### 15.4. Turning retries and dead-lettering into an operational workflow

~~~mermaid
flowchart TD
    M["Inbound event"] --> V{"Validate schema/source"}
    V -->|Invalid| Q["Quarantine/DLT: reason + owner"]
    V -->|Valid| H["Idempotent business handler"]
    H --> C{"Business commit?"}
    C -->|Succeeded| ACK["Ack/offset per transport"]
    C -->|Transient error| RT{"Retry budget left?"}
    RT -->|Yes| BACK["Backoff / redelivery"]
    BACK --> H
    RT -->|Exhausted| Q
    C -->|Permanent failure| Q
    Q --> OPS["Review + repair + controlled replay"]
~~~

**Replay must be controlled:** when replaying messages from a DLT into the main flow, never bypass validation, idempotency, or version checks; if the root cause was a schema mismatch, deploy a compatible consumer before replaying.

### 15.5. When automatic acknowledgment is unsuitable

If a listener container acknowledges a message immediately after the adapter **successfully sends to an ExecutorChannel**, the message can be lost if the process crashes before business commit. Options include:

1. Keep the acknowledgment-covered processing **synchronous within the listener/transaction** when load permits.
2. Persist messages to a **durable inbox/queue** before acking the broker, then process asynchronously with retries.
3. Use supported manual ack/container modes and manage lifecycles/contexts properly; verify broker thread, ack, and timeout constraints.
4. Design at-least-once consumers with idempotency and test kill-process scenarios.

Do not apply manual acknowledgment uniformly across JMS, AMQP, and Kafka; each has its own contract and API.

### 15.6. Difference between DLT and business failures

A **PaymentDeclined** event is a valid business event, not an infrastructure failure for a DLT. Conversely, a consumer failing to parse PaymentApproved due to schema incompatibility is an integration failure. DLTs hold messages **not processed cleanly under the contract**, whereas business states like “payment declined” belong in the domain model.

## 16. Backpressure and Processing Capacity

An event-driven consumer lacks a simple business polling schedule to speed up or slow down; yet it must still **bound concurrent message processing** and react when sinks slow down.

### 16.1. Why fast-arriving events cause overload

Suppose a producer emits 500 events/second while the consumer writes to the DB at most 300 events/second. The ~**200 events/second** excess accumulates in the broker, executor queue, an intermediate queue, or causes transport-level rejections. Merely “adding more threads” solves nothing if the final bottleneck is the DB connection pool.

### 16.2. Throttling mechanisms by layer

| Layer | Load signal | Measure |
| --- | --- | --- |
| Broker queue | Queue depth, unacked messages | Prefetch, concurrency, bounded consumer autoscaling |
| Kafka topic | Per-partition consumer lag, processing duration | Consumer group/partition count, batching, processing limits |
| DirectChannel | Sender/handler latency, held threads | Optimize handlers, consider durable async handoff |
| ExecutorChannel | Active threads, queue depth, rejected tasks | Bounded queue, rejection policy, upstream backpressure |
| HTTP inbound | Request latency, timeouts, 429/503, thread utilization | Rate limits, timeouts, 202 + durable queue when appropriate |
| Database sink | Pool saturation, lock waits, commit latency | Batching, indexing, short transactions, shed input load |
| External REST sink | Latency, 429, circuit open | Rate limits, bulkheads, retry/backoff, idempotency |

**Never use an unbounded JVM queue** as a “solution” when producer speed exceeds consumer speed. It merely moves backlog into the heap and can cause OOM crashes, losing queued messages.

### 16.3. Choosing subscriber concurrency

If a handler averages 100 ms latency in steady state, one worker theoretically handles ~10 tasks/second before overhead. That is not guaranteed throughput: I/O, contention, GC, DB locks, message sizes, and retries create wide variance.

Measure:

- Actual throughput after **business commit**, not just messages received.
- P50/P95/P99 latency for handlers and targets.
- Backlog/lag and age of the oldest unprocessed message.
- Connection counts, pool saturation, CPU, heap, and rejected tasks.
- Retry rates, DLT counts, and duplicate rates.

### 16.4. Watch out for fan-out

One OrderCreated sent to three subscribers can trigger **three side effects**. Total load is not just incoming event volume, but fan-out multiplied by each branch's outbound calls. If the Analytics subscriber is slow, decide whether to isolate its backlog from Inventory/Billing; independent broker topics/subscription groups clarify pressure isolation points.

## 17. Connection Lifecycle, Startup, Shutdown, and Multi-Instance Deployment

### 17.1. Startup

On startup, listeners/adapters typically participate in the Spring ApplicationContext lifecycle. Each connector needs explicit authentication, timeout, and recovery configuration.

- [ ] Verify brokers/topics/queues/destinations actually exist and the app has subscribe/consume permissions.
- [ ] Verify schemas/serializers/deserializers, content types, and version compatibility.
- [ ] Configure consumer groups, client IDs, prefetch, and concurrency per product semantics.
- [ ] Do not automatically overwrite offsets or skip backlogs outside policy.
- [ ] Initialize idempotent repositories/inboxes, DB migrations, and dependent services before taking heavy load.
- [ ] Health endpoints distinguish **app alive** from **consumer connected, assigned, and making progress**.

### 17.2. Graceful shutdown

When receiving a shutdown or rolling deployment signal:

1. Stop accepting new messages or pause listeners via supported lifecycle controls.
2. Allow in-flight handlers to finish within the shutdown grace window, or roll back/requeue per transport.
3. Never ack/commit offsets for messages whose business transaction has not committed.
4. Ensure unprocessed messages in in-memory queues are not treated as durably persisted.
5. Monitor offsets/queue depth and transaction states before terminating the instance.

If a shutdown timeout forces a process kill, **redelivery** can occur; that is why idempotency must exist before enabling rolling deployments.

### 17.3. Connection recovery

| Technology | Common risk | What to verify |
| --- | --- | --- |
| JMS | Broker restarts, dropped sessions/consumers | Listener container reconnect, ack/transaction, redelivery |
| RabbitMQ | Connection/channel closures, network partitions | Reconnect, queue topology, prefetch, ack state |
| Kafka | Rebalances, broker leader changes, max poll interval | Partition assignment, offsets, retries, and heartbeats |
| HTTP | TLS, request timeouts, client retries | Idempotency keys, status responses, connection pools |
| Database | Pool exhaustion, deadlocks, transaction timeouts | Error-specific retries, commits, and inbox state |
| SFTP/File bridge | Incomplete files, stale sessions, renames | Polling/ready markers, metadata, reconnect |

Not every connector should auto-reconnect infinitely. For credential/permission errors, rapid retries only add load and mask configuration issues. Separate transient failures from failures requiring operator intervention.

### 17.4. Multi-instance and scaling

- **JMS Queue/RabbitMQ queue:** multiple competing consumers divide messages; measure ordering and redelivery behavior.
- **JMS Topic/RabbitMQ fan-out:** when multiple business domains need every event, use appropriate subscriptions/queues rather than just adding consumers in one competing group.
- **Kafka:** active consumers receiving partition assignments are bounded by partition count and group assignment; launching more replicas than partitions does not linearly increase throughput.
- **HTTP:** multiple inbound gateway instances behind a load balancer receive different requests; client retries may hit another instance, requiring shared idempotency state.
- **ExecutorChannel:** multiple threads only manage concurrency within one JVM, not distributed deduplication.

### 17.5. Event-driven does not eliminate reconciliation

If a producer fails to publish an event, a broker expires retention, a consumer is mis-subscribed, or schemas drift incompatibly, events can be missed across integration boundaries. For critical domains, run periodic **source–target state reconciliation** to detect drift and resync safely.

## 18. Observability, Auditing, and Runbooks

**Consumer alive** and **consumer processing properly** are two different things. A listener can stay connected to a broker while endlessly retrying the same poison message with zero business progress.

### 18.1. Metrics to monitor

| Metric | Purpose | Warning sign |
| --- | --- | --- |
| **messages received** | Reception rate from adapter | Sudden drop while source is still publishing |
| **processed/committed** | Business completion rate | Flat despite high incoming message volume |
| **processing duration** | Handler and downstream latency | Sustained rise in P95/P99 |
| **queue depth / Kafka lag** | Backlog and consumption delay | Continuous growth or message age exceeding SLA |
| **ack/offset commit lag** | Processed messages whose progress isn't recorded | Long lag, high redelivery risk |
| **redelivery/retry** | Repeat load and transient errors | Same eventId exceeding retry thresholds |
| **DLT/quarantine count** | Unrecoverable errors | Rapid spike or missing owner |
| **duplicate suppressed** | Frequency of repeated business events | Spikes after restarts/rebalances |
| **consumer connected/assigned** | Broker connection, Kafka partition assignment | No active consumers despite app alive |
| **executor queue/rejections** | Async overload | Full queue, rejected tasks |
| **last successful commit** | Actual business progress | Too stale while source emits events |

Metrics should define **denominators, message types, sources, consumer groups, and environment scopes**. Never attach individual eventIds or payloads as metric labels due to extreme cardinality and potential data leaks.

### 18.2. Illustrative logging

~~~json
{
  "flow": "order-created-consumer",
  "eventId": "EVT-LAB-1042",
  "schemaVersion": 1,
  "consumer": "inventory-projection",
  "source": "orders.events",
  "stage": "BUSINESS_COMMIT",
  "attempt": 2,
  "result": "RETRYABLE_ERROR",
  "traceId": "TRACE-LAB-081",
  "durationMs": 145
}
~~~

This log is a simulated example, not Spring Integration's default format. Never log raw tokens, passwords, session cookies, private keys, or unnecessary personal data. Log access and retention must follow policy.

### 18.3. Three essential runbooks

**Runbook A — Rising consumer lag:** check if new messages are arriving, partition/queue counts, listener connectivity, handler latency, DB pools, retries, and concurrency; do not blindly increase threads if targets are already overloaded.

**Runbook B — One event failing repeatedly:** extract eventId/schemaVersion, distinguish transient vs. permanent failure, cap retries, move to DLT, notify owner, fix root cause before replay; never log secrets.

**Runbook C — Consumer restart causing duplicates:** check checkpoints/offsets/acks, transactions, and inbox business keys; verify business effects were not duplicated, fix the redelivery path if needed; never disable idempotency to hide symptoms.

### 18.4. Evidence checklist

- [ ] Correlation exists from producer eventId through inbound adapter to handler.
- [ ] Timestamps exist for when an event was received, validated, processed, committed, and acked.
- [ ] On failure, attempt number, cause, message source, and owner are identifiable.
- [ ] DLT/quarantine items can be listed, inspected, and replayed within authorized bounds.
- [ ] Tests verify process restarts/redeliveries produce no duplicate side effects.
- [ ] Logs and metrics do not leak sensitive data.
- [ ] Operators can distinguish a backlogged consumer from one that lost its subscription or partition assignment.

## 19. Lab: Processing OrderCreated with an Event-driven Flow

The lab is designed for practice using **Java 17 and Spring Integration in an authorized environment**. You can start with just a DirectChannel and an in-memory repository, then swap in a JMS/AMQP/Kafka test broker and test DB to observe real delivery semantics.

### 19.1. Context

**Order Service** emits OrderCreated. **Inventory Consumer** updates inventory projections or pending orders; **Analytics Consumer** updates metrics. Each consumer must independently prevent duplicate events and preserve correct state when events arrive late.

Mock data:

~~~json
{
  "eventId": "EVT-LAB-2001",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "aggregateId": "ORDER-LAB-1001",
  "aggregateVersion": 1,
  "tenantId": "TENANT-LAB-01",
  "data": {
    "sku": "SKU-LAB-A",
    "quantity": 2
  }
}
~~~

### 19.2. Minimal design

~~~mermaid
flowchart TD
    P["Producer: OrderCreated"] --> B["Test broker or DirectChannel"]
    B --> IA["Inbound Adapter / Channel"]
    IA --> V["Validate schema and tenant"]
    V --> IDEMP["Inbox: check business eventId"]
    IDEMP --> H["Business handler"]
    H --> DB["Persist/commit"]
    DB --> ACK["Ack/offset per contract"]
    V -->|Invalid| Q["Quarantine/DLT"]
    H -->|Transient failure| RET["Retry + backoff"]
    RET --> H
~~~

For an **in-memory-only DirectChannel**, there is no broker ack. Thus the ACK step in the diagram applies only when switching to a broker; the internal lab uses **recording completion status** to illustrate the equivalent business-level result.

### 19.3. Implementation steps

**Step 1 — Build channel and service activator.** Use the DirectChannel flow from section 7; create a handler that parses `OrderCreated`, validating `eventId`, `aggregateId`, tenant, and version. Reject missing fields or invalid data.

**Step 2 — Store business idempotency keys.** Create an inbox table or mock repository with a unique constraint on `consumerName + eventId`. Do not use just a HashSet if testing durable restarts.

**Step 3 — Process business state.** Update order or inventory state using `aggregateVersion`. Prevent older event versions from overwriting newer versions.

**Step 4 — Send the same event twice.** The business outcome should reflect only one valid effect per design; logs should record duplicate detection instead of repeating side effects.

**Step 5 — Inject failure after commit before ack.** With a test broker, simulate a crash/offset reset or lost ack after DB commit; restart and verify redelivery does not repeat side effects. With mocks, invoke the handler a second time after successful state persistence.

**Step 6 — Trigger schema errors.** Send JSON missing eventId or with an unsupported version; the message must be rejected/quarantined per policy without infinite retries.

**Step 7 — Trigger transient infrastructure errors.** Make the test DB fail once; the consumer retries with backoff and never writes an inbox “done” record before business commit.

**Step 8 — Enable fan-out.** Register Inventory and Analytics independently. Both process the same event using **consumer-specific idempotency**, never sharing one inbox row that causes the second subscriber to skip it.

**Step 9 — Test concurrency.** Emit two events for the same aggregate with version 2 then version 1; stale writes must be prevented via version checks or per-key serialization.

**Step 10 — Write the report.** Record Expected/Actual, eventId, attempt, commit status, retry/DLT, and verified evidence. Explicitly note differences between DirectChannel tests and broker tests.

### 19.4. Test matrix

| ID | Scenario | Expected outcome |
| --- | --- | --- |
| **ED-01** | Producer sends event to DirectChannel with one handler | Handler is triggered on send without needing a poller |
| **ED-02** | No new messages | No handler invocations from a polling schedule |
| **ED-03** | Event missing required fields | No business write; error recorded |
| **ED-04** | Unsupported schemaVersion received | Quarantined/DLT or rejected with owner |
| **ED-05** | Same eventId received twice | No repeated business side effects |
| **ED-06** | Retry with a new technical message ID but identical eventId | Inbox still detects duplicate |
| **ED-07** | Event version 2 arrives before version 1 | Stale event does not overwrite newer state |
| **ED-08** | Handler DB fails before commit | Retries/redelivers per contract; no false success ack |
| **ED-09** | Commit succeeds then broker ack is lost | Safe redelivery via idempotency |
| **ED-10** | Consumer stops mid-processing | After restart, no unintended lost or doubled side effects |
| **ED-11** | One poison event fails repeatedly | Moved to DLT/quarantine after bounded retries |
| **ED-12** | Transient 503/timeout from HTTP outbound gateway | Retries with backoff, no busy loop |
| **ED-13** | Valid event fanned out | Every valid subscriber gets a chance to process per contract |
| **ED-14** | Inventory succeeds, Invoice fails | Retrying Invoice does not rerun Inventory if subscriptions are independent |
| **ED-15** | Two handlers attached to same DirectChannel | Do not assume both receive broadcast for every message |
| **ED-16** | Switch to ExecutorChannel | Async errors do not automatically propagate synchronously to producer |
| **ED-17** | Executor queue full | Recorded rejection/backpressure, no silent drops |
| **ED-18** | Multi-instance Kafka consumer group | Partitions distributed across group, lag measurable |
| **ED-19** | Kafka rebalance with uncommitted record | Record may be re-read; valid state not lost |
| **ED-20** | RabbitMQ redelivery/requeue | Idempotency prevents duplicates, DLQ follows policy |
| **ED-21** | JMS listener rollback on handler error | Verifies redelivery/ack per container setup |
| **ED-22** | HTTP client retries with same idempotency key | Does not create two orders if contract requires one |
| **ED-23** | SFTP bridge polls file then sends broker event | Separates source polling from downstream event-driven flow |
| **ED-24** | Outbox relay republishes after restart | Consumer tolerates duplicate event delivery |
| **ED-25** | Backlog grows due to DB bottleneck | Metrics/alerts identify bottleneck instead of blindly adding threads |
| **ED-26** | Audit log contains sensitive info | Credentials redacted, data/labels minimized |

### 19.5. Sample lab result template

~~~yaml
testCase: ED-09
eventId: EVT-LAB-2001
consumer: inventory-projection
input: "Broker redelivers after business commit but before ack"
expected: "One business effect; duplicate detected"
actual: "Expected value from the experiment"
result: PENDING
evidenceRef: "lab://tests/ED-09"
verifiedAt: null
~~~

This is an **unexecuted test report template**; do not treat `result: PENDING` as PASS. When running for real, fill in actuals, adapter output, redacted logs/screenshots, and readback verification.

### 19.6. Increasing difficulty

1. Replace the DirectChannel producer with a **JMS listener adapter** and configure real transactions/acks in a test environment.
2. Use a **RabbitMQ fan-out exchange** with two queues so each domain manages its own retries/DLQ.
3. Use a **Kafka topic** keyed by aggregateId to study ordering, offsets, and rebalancing.
4. Offload heavy processing via ExecutorChannel and design how to prevent premature broker acks.
5. Add an **HTTP inbound gateway** receiving commands, persisting order + outbox in the same DB transaction, with a relay publishing events.
6. Add a processed/received/lag/DLT dashboard and conduct a crash-recovery drill.

## 20. Anti-Patterns and Implementation Checklist

### 20.1. Common anti-patterns

| Mistake | Risk | Better approach |
| --- | --- | --- |
| **“Kafka polls, so it's a PollingConsumer”** | Confuses Spring Integration abstractions | Distinguish client polling inside a listener from SI PollingConsumer endpoints |
| **Attaching two subscribers to DirectChannel to broadcast** | Only one handler is chosen per message | Use PublishSubscribeChannel or broker fan-out |
| **Acking immediately after enqueuing to ExecutorChannel** | Crashes before business commit lose messages | Process synchronously or use durable handoff/coordinated ack |
| **Treating successful send as business success** | Masks downstream handler/transaction failures | Track commit points and readback |
| **Missing business eventId** | Retries/redeliveries cause duplicate side effects | Stable idempotency keys |
| **Writing inbox before business commit** | Crashes may drop events | Same transaction as business state changes |
| **Infinitely retrying malformed events** | Poison events block consumers and flood logs | DLT/quarantine with an owner |
| **Swallowing all exceptions in the handler** | Broker may ack even though processing failed | Classify errors and let contract failure paths run |
| **Enabling unbounded executor queues** | OOM, missing backpressure, lost work on crash | Bounded executors and durable brokers where appropriate |
| **Increasing concurrency while DB is overloaded** | Increases locks, retries, and latency | Measure bottlenecks and bound load |
| **Assuming message order equals commit order** | Stale state versions overwrite newer ones | Version checks or per-aggregate serialization |
| **Sharing one inbox across all subscribers** | Other subscribers skip valid events | Scope idempotency per consumer |
| **Forgetting stop/rebalance during deploys** | Duplicates, lag, timeouts | Graceful lifecycle and restart testing |
| **Skipping source–target reconciliation** | Silent drift after lost events or schema changes | Business-level reconciliation/repair |
| **Logging full payloads/tokens** | Credential and customer data leaks | Redaction, data minimization, retention |

### 20.2. Pre-production design checklist

- [ ] Event source, transport, and inbound adapter/gateway types are accurately identified.
- [ ] Clear rationale exists for event-driven over polling, or hybrid flows are explicitly documented.
- [ ] Message contract defines eventId, schemaVersion, aggregateId, tenant, and validation policies.
- [ ] Threading semantics of DirectChannel/ExecutorChannel/PublishSubscribeChannel are understood.
- [ ] In-memory channels are never treated as durable brokers without persistent storage.
- [ ] Specific business commit point exists before acknowledgment/offset commit per contract.
- [ ] Idempotency strategy covers retries and restarts.
- [ ] Ordering and concurrency are bounded by key/partition or version.
- [ ] DLT/quarantine paths, retry/backoff policies, ownership, and replay exist.
- [ ] Fan-out defines which subscribers receive events and who owns branch failures.
- [ ] Backpressure, concurrency limits, and capacity match target systems.
- [ ] Startup/shutdown, reconnect, and rolling deploys have been tested.
- [ ] Consumer lag/queue depth, processed commits, errors, duplicates, and DLTs are monitored.
- [ ] Events are not treated as trusted authorization sources without proper authentication and authorization.
- [ ] Tests cover post-commit redelivery, schema mismatches, poison messages, and stale events.
- [ ] Runbooks, audit trails, and state reconciliation exist if required by the domain.

## 21. Summary and Self-Check Questions

### 21.1. Key knowledge to remember

The **Event-driven Consumer Pattern** enables a handler to react when a message is dispatched to the consumer instead of scheduling scans of business data. In **Spring Integration**, you commonly encounter this pattern in:

- **Message-driven inbound adapters** from JMS, AMQP, or Kafka listener containers.
- **Inbound gateways** when HTTP/JMS/AMQP requests arrive and require a reply.
- **Service activators** subscribed to a **SubscribableChannel** like DirectChannel or ExecutorChannel.
- **PublishSubscribeChannel** when a single message must reach multiple subscribers inside the application.

Meanwhile, **PollingConsumer** pulls from a **PollableChannel** such as QueueChannel, and **SourcePollingChannelAdapter** pulls from a **MessageSource** such as File/SFTP/JDBC. These mechanisms can coexist in the same system; choose based on the data source and delivery contract.

### 21.2. Self-check

1. What is the biggest difference between an event-driven consumer and a polling consumer at the **trigger point**?
2. Why is the Spring Integration Kafka inbound adapter still called message-driven even though the Kafka client polls?
3. When two service activators share the same DirectChannel, do both receive the same message?
4. Does ExecutorChannel preserve the sender thread's transaction context and guarantee the handler has committed when `send()` returns?
5. How does an HTTP inbound gateway differ in role from an HTTP outbound gateway and a message-driven inbound adapter?
6. Why can a JMS/AMQP/Kafka message be redelivered after a DB commit succeeds?
7. When fanning out to Inventory and Analytics, why should inbox idempotency include consumer identity?
8. If OrderUpdated v8 commits before v7, how does the consumer prevent stale updates?
9. How should a poison event that repeatedly fails parsing be handled once the retry limit is reached?
10. A consumer remains connected yet lag is not decreasing: which metrics/error paths do you check first?

**Short reference answers:** (1) message dispatch vs. scheduled receive; (2) transport client poll is container-managed while SI's abstraction is a listener; (3) no broadcast by default; (4) no; (5) inbound request-reply, outbound request-reply, and one-way listener; (6) ack/offset not yet recorded; (7) each subscriber has independent side effects; (8) version checks/partitioning; (9) quarantine/DLT with an owner; (10) business commits, handler latency, retries, DB, and backlog.

### 21.3. Closing principle

A reliable event-driven flow does not stop at **“the handler was invoked.”** You must prove **messages are valid, come from trusted sources, are processed idempotently, respect business ordering, and persist successfully at the target system**, alongside mechanisms for retries, redelivery, and recovery whenever any step fails.

**Remember:** *Event-driven decides when to react; message contracts, transactions, acknowledgments, idempotency, backpressure, and observability decide whether that reaction is actually correct and durable.*
