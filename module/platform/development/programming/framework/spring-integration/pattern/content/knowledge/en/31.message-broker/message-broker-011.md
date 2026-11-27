# Differences Between Broker Semantics and Spring Integration Channels

**Chapter:** Message broker  
**Lesson:** Differences between broker semantics and Spring Integration channels  
**Scope:** `SPRING_INTEGRATION_PATTERN` — learning to implement Enterprise Integration Patterns (EIP) with Spring Integration, from Router, Filter, Transformer, Splitter, Aggregator, and Gateway to retry, error channel, correlation, testing, and observing message flows.

## Objectives

After this lesson, you will be able to:

1. Distinguish **message channels** (logical paths between integration components) from **message brokers** (intermediary infrastructure that transmits/stores messages between producers and consumers).
2. Accurately interpret `send()`, `receive()`, ACK, offset commit, durability, redelivery, ordering, and consumer groups at each layer.
3. Choose among `DirectChannel`, `ExecutorChannel`, `QueueChannel`, `PublishSubscribeChannel`, and external brokers based on process isolation, reliability, and throughput needs.
4. Design Spring Integration flows over RabbitMQ, JMS, or Kafka without confusing application-level errors, retries, or correlation with transport guarantees.
5. Test crash points, duplicate messages, consumer failures, and queue backpressure before moving systems into production.

## 1. Two concepts at two different layers

A **Spring Integration channel** is an **in-application abstraction**. The sending component knows a `MessageChannel` and pushes a `Message<?>` into it; the receiving component connects to the channel via an endpoint. Channels decouple EIP processing responsibilities, yet **an ordinary channel does not automatically equal a durable broker queue**.

A **Message broker** is a communication service or infrastructure such as RabbitMQ or a JMS provider. The broker receives messages, manages queues/subscriptions, distributes them to consumers, and applies storage, confirmation, redelivery, or quota policies per configuration. Kafka provides a **distributed log** model with topics, partitions, and offsets; never interpret Kafka as a queue that deletes messages immediately upon reading.

The two concepts can cooperate in the same flow. A Spring Integration adapter connects to a broker; inside each application, channels continue wiring Router, Filter, Transformer, Service Activator, and handlers.

~~~mermaid
flowchart LR
  subgraph A["Application A — Spring Integration"]
    G["Gateway"] --> T["Transformer"]
    T --> C1["DirectChannel"]
    C1 --> OUT["Outbound adapter"]
  end
  OUT -->|Publish| B[("Broker: queue / topic / log")]
  B -->|Deliver / consume| IN["Inbound adapter"]
  subgraph W["Application B — Spring Integration"]
    IN --> C2["Internal channel"]
    C2 --> R["Router / Filter"]
    R --> H["Service Activator"]
  end
~~~

The adapter is the **protocol boundary**. Channels before/after the adapter belong to the application, whereas queues/topics, ACK mechanics, and storage reside in the corresponding transport/broker.

## 2. What are semantics and why must we state them clearly?

*Semantics* are the observable rules governing what happens when a message is sent, received, fails, or when an application stops: who receives it, when it is received, whether the message persists or is lost, whether processing is complete, whether it gets redelivered, and what ordering is guaranteed.

For example, the statement “sending the message succeeded” can have at least four different meanings:

1. The message was **accepted** by a `MessageChannel`.
2. The message reached an **outbound adapter** and the adapter called the client API without throwing.
3. The broker confirmed receipt or **durably persisted** it per producer/broker configuration.
4. The consumer **committed business effects** and acknowledged processing.

These four milestones are not identical. In reliable system design, always state precisely which confirmation level an API or log refers to.

### 2.1 Spring Integration channel API

- `MessageChannel.send(message)` sends a message to the channel and returns a result per the channel's contract. Returning `true` is not a certificate that “business logic in another service has finished”.
- `SubscribableChannel` provides handler subscription so the channel pushes messages to recipients, e.g., `DirectChannel`.
- `PollableChannel` lets consumers call `receive()` or pollers fetch messages, e.g., `QueueChannel`.
- A flow can use channels even with **no network, broker, or out-of-process storage**.

### 2.2 Broker API

- **Publish/send:** producer sends to an exchange, destination, topic, or queue per protocol.
- **Delivery/fetch:** broker pushes messages to a consumer, or the consumer reads records by position.
- **ACK/negative ACK/transaction/offset commit:** mechanism recording whether a delivery was processed or how far consumption has progressed.
- **Retention, persistence, replication:** mechanisms governing how messages survive and recover; these differ between queue brokers and distributed logs.

A successful `send()` in Spring Integration does not automatically issue a RabbitMQ ACK, commit a JMS session, or commit a Kafka offset.

## 3. Four common channels and their practical meaning

| Channel | How messages move | Synchronicity and scope | Default durability/redelivery |
|---|---|---|---|
| `DirectChannel` | Invokes handler/subscriber directly per channel dispatch strategy. | Typically runs **directly on the thread calling `send`**; creates no process boundary. | No durable storage; synchronous exceptions can propagate back to the sender. |
| `ExecutorChannel` | Hands execution to a `TaskExecutor`. | Switches threads; subject to scheduling rules and executor bounds. | No built-in durable queue or broker ACK; must configure appropriate error handling. |
| `QueueChannel` | Buffers messages for a poller/consumer to pull. | Decouples enqueue and dequeue timing; still typically inside one application. | In-memory by default; needs a compatible persistent `MessageStore` to survive restarts. |
| `PublishSubscribeChannel` | Broadcasts to registered subscribers. | Synchronous by default; asynchronous if configured with an executor. | Does not create durable cross-app subscriptions like a broker; per-subscriber errors depend on config. |

**Key point:** the name `QueueChannel` does not mean it is a “mini RabbitMQ queue” with all broker-like ACK, TTL, DLQ, or recovery guarantees. Likewise, `PublishSubscribeChannel` does not inherently provide durable fan-out to other applications.

### 3.1 Synchronous does not mean durable

For instance, suppose `DirectChannel` passes `OrderCreated` to a Service Activator. When the handler throws an exception during the synchronous call, the sender can receive the error immediately. However, if the process crashes before business logic commits, the channel retains no copy to automatically resume after restart.

When replaced by `ExecutorChannel`, execution moves onto another thread. `send()` accepting the task **does not guarantee** the worker will succeed; subsequent failures may route to `errorChannel` or the executor's error handler, depending on configuration.

### 3.2 `QueueChannel` can persist durably, but must be configured

`QueueChannel` can use a persistent store, such as `JdbcChannelMessageStore`, instead of an in-memory queue. Messages stored in the database can then recover after a restart if transactions and storage are configured properly. However:

- **Taking the message** and **executing business logic** require clear transaction boundaries.
- Durable message storage **does not automatically prevent duplicate business effects**.
- If the store is a shared database, throughput, lock contention, schema, serialization, and backups become the system's operational responsibility.
- A persistent channel remains a Spring Integration application component; it does not create the topology, consumer groups, or protocol of an external broker.

## 4. Comparison table: channel semantics vs. external broker semantics

| Design question | Spring Integration channel | External broker |
|---|---|---|
| **Routing** | `Router` and internal channels choose handlers/branches. | Exchange, binding, destination, topic, subscription, or partition selects delivery targets. |
| **Scope** | Within one Spring `ApplicationContext`/process by default. | Applications, hosts, or consumer groups can connect remotely. |
| **Storage** | Depends on channel type and `MessageStore`; many channels store nothing at all. | Depends on broker, queue/topic policies, message type, replication, and durability settings. |
| **Receiving messages** | Direct handler call, executor dispatch, or polling `QueueChannel`. | Broker push delivery/listener or log reading by consumer. |
| **Completion confirmation** | No unified broker ACK across all channels. | RabbitMQ ACK/NACK, JMS session acknowledgment/transaction, Kafka offset commit: distinct models. |
| **Retry/redelivery** | Advice, retry interceptor, poller transaction, error flow configured by the app. | Broker- and client-dependent: requeue/redelivery/seek/offset or retry topic; not fully automatic. |
| **Ordering** | Depends on channel type, threads, pollers, and handler count. | Depends on queue/consumer, partitions, prefetch, redelivery, and concurrency config. |
| **Fan-out** | `PublishSubscribeChannel` broadcasts to subscribers within the app. | Independent subscriptions/queues or consumer groups per receiving group. |
| **Backpressure** | Queue capacity, executor rejection, poller rate. | Queue depth/retention, consumer lag, prefetch, flow control, quotas. |
| **Error tracking** | `ErrorMessage`, `errorChannel`, logging/Micrometer/tracing. | DLQ, broker metrics, consumer lag, unacked count, failed publishes; must link with app tracing. |
| **Transactions** | Can wrap internal steps/transaction-capable resources. | Has per-broker transactions/sessions/offsets/ACKs, not a shared transaction across arbitrary DBs/APIs. |
| **Request–reply** | Gateway can use internal reply channels. | Requires reply destination, correlation, timeouts, and late/duplicate reply handling when crossing a broker. |

The table compares **typical** contracts, without claiming every channel or every broker shares identical configurations. When choosing, verify exact behavior for your adapter and library versions.

## 5. Clearly distinguish RabbitMQ, JMS, and Kafka

**RabbitMQ** commonly implements work queues or publish/subscribe through exchanges and bindings. For push consumers, the application selects an acknowledgment mode; if a consumer stops before ACK, messages may be redelivered per broker rules. Durable queue declarations and persistent messages are two separate requirements; when sender-side reliability is needed, also consider publisher confirms and matching broker settings.

**JMS** is an API/specification, while providers supply the implementation. Persistent delivery mode, acknowledgment mode, and transacted sessions govern recoverability and redelivery. Never deduce an exact guarantee solely from the presence of `Jms.messageDrivenChannelAdapter` in a flow.

**Kafka** appends records to a partitioned log; consumer groups coordinate partition assignments and each group tracks its own offsets. Committing an offset records read progress—it **does not delete** records from the topic. Retention policies determine how long data stays stored. Ordering is guaranteed **within one partition**, not globally across a multi-partition topic.

| Technology | Distribution unit | When consumer finishes | Semantics notes |
|---|---|---|---|
| RabbitMQ | Queue/exchange and consumer | ACK or confirmation per listener mode | NACK/requeue, prefetch, DLX/DLQ, and durability must be verified in config. |
| JMS | Destination (queue/topic) and subscription | Acknowledge/commit session per mode | Redelivery and durable subscription behavior depend on provider/config. |
| Kafka | Topic partition and consumer group | Offset commit or transaction within supported scope | Records remain per retention; replayable; must prevent duplicate business effects. |

Never say “Spring Integration guarantees exactly once” across all three transports. Spring Integration orchestrates endpoints and flows, whereas delivery guarantees come from the combination of broker, client, transactions, business storage, and consumer design.

## 6. Typical scenario: order processing

Requirement: when an order succeeds, emit `OrderPlaced(eventId, orderId)`; a worker generates an invoice. The order service and invoice service deploy independently and can restart at any time.

### 6.1 Wiring internal channels only

~~~mermaid
flowchart LR
  P["Order handler"] --> D["DirectChannel"]
  D --> T["Transformer"]
  T --> H["Invoice handler"]
~~~

This structure is simple, low-latency, and suitable when all three steps live in the **same application**. If `Invoice handler` throws an exception on the same call, the error can propagate back to the caller. However, the entire flow shares a single process lifecycle; a worker on another host cannot subscribe directly to `DirectChannel`.

### 6.2 Using an internal `QueueChannel`

~~~mermaid
flowchart LR
  P["Order handler"] --> Q[["QueueChannel"]]
  Q --> POL["Poller"]
  POL --> H["Invoice handler"]
~~~

A poller decouples producer and consumer rates. You must decide capacity, message storage, retry policy, and transactions. By default `QueueChannel` buffers only in memory; if using `JdbcChannelMessageStore`, re-read behavior on failure must be tested with the actual transaction manager.

### 6.3 Using a broker between two applications

~~~mermaid
flowchart LR
  subgraph S["Order service"]
    A["Business transaction"] --> O["Outbox / event publisher"]
    O --> SA["Outbound adapter"]
  end
  SA --> B[("Broker queue / topic")]
  B --> IA["Inbound adapter"]
  subgraph I["Invoice service"]
    IA --> F["Filter / Transformer"]
    F --> H["Idempotent invoice handler"]
    H --> D[("Invoice DB")]
  end
~~~

With this design, the broker decouples **deployment, lifecycle, and pace** between the two services. The producer needs to know when a publish is confirmed. The consumer needs to decide when to ACK/commit after business logic. When order data and messages are written to two separate systems, a transactional outbox typically prevents “DB succeeded while message emit failed”.

In practice, Spring Integration adapters connecting to a broker can use channels both before and after the adapter; the adapter does not turn a local channel into a broker.

## 7. Java DSL example: an internal queue is not equivalent to a broker

The following example illustrates an in-application queue. Imports are omitted; compatible Spring Integration Java DSL and Spring configuration are required.

~~~java
@Configuration
@EnableIntegration
class LocalOrderFlow {

    @Bean
    MessageChannel orderBuffer() {
        // Caps at 100 pending messages; this is an in-memory queue.
        return new QueueChannel(100);
    }

    @Bean
    IntegrationFlow invoiceFlow(InvoiceService invoiceService) {
        return IntegrationFlow
                .from("orderBuffer", endpoint -> endpoint.poller(
                        Pollers.fixedDelay(250).maxMessagesPerPoll(10)))
                .handle(OrderPlaced.class, (event, headers) -> {
                    invoiceService.applyOnce(event.eventId(), event.orderId());
                    return null; // Terminates one-way flow.
                })
                .get();
    }
}

record OrderPlaced(String eventId, String orderId) {}

interface InvoiceService {
    void applyOnce(String eventId, String orderId);
}
~~~

With this configuration:

- `orderBuffer().send(message)` performs an **in-memory enqueue**; there is no broker publisher confirm.
- `invoiceFlow` uses a poller to pull messages; if the handler throws after dequeueing, an in-memory queue has no RabbitMQ-style ACK/rollback/redelivery mechanism out of the box.
- You can add retry advice and an error channel, yet you must specify whether exceptions propagate back to the poller and whether the message still exists.
- Capacity `100` is an internal queue bound; understand the blocking or failure behavior of `send(message, timeout)` when full.

Replacing the queue with a persistent `JdbcChannelMessageStore` and configuring transactions gives the system message persistence across restarts. Even then, it **still does not create** out-of-process consumer groups or RabbitMQ publisher confirms.

### 7.1 Broker boundary example via AMQP adapter

One way to connect RabbitMQ in Spring Integration is using an inbound adapter, then continuing the flow with in-application endpoints:

~~~java
@Configuration
@EnableIntegration
class BrokerInboundFlow {

    @Bean
    IntegrationFlow invoicesFromRabbit(
            org.springframework.amqp.rabbit.connection.ConnectionFactory connectionFactory,
            InvoiceService invoiceService) {

        return IntegrationFlow
                .from(Amqp.inboundAdapter(connectionFactory, "orders.invoice"))
                .handle(OrderPlaced.class, (event, headers) -> {
                    invoiceService.applyOnce(event.eventId(), event.orderId());
                    return null;
                })
                .get();
    }
}
~~~

This snippet **illustrates where the adapter and handler connect**; running it in practice requires declaring the queue on RabbitMQ, configuring a message converter to turn payloads into `OrderPlaced`, configuring the listener container, ACK mode, error/requeue policy, and appropriate transactions or idempotency. Notably, reliability cannot be inferred from the `Amqp.inboundAdapter(...)` call alone.

For Kafka and JMS, swap the adapter per transport; downstream EIP components remain usable, while confirmation/retention/redelivery semantics must be evaluated separately.

## 8. Failure table to avoid confusing ACK and `send()`

| Failure timing | With an in-memory channel | With a broker and appropriate ACK/offset mechanism |
|---|---|---|
| Producer crashes before sending | No message to process. | Also no message if unpublished; needs producer retry/outbox. |
| Producer sees `send() == true` then app crashes | Message can be lost if only in an in-memory queue. | If a valid durable confirm was received from the broker, the message can recover per broker guarantee. |
| Consumer takes message then crashes before business commit | In-memory queue may have already removed the message; no automatic redelivery. | Broker can redeliver or retain uncommitted position, depending on protocol/config. |
| Business logic committed, consumer crashes before ACK/offset commit | No shared broker ACK protocol. | Same event may be redelivered; requires idempotency. |
| Handler throws exception | `DirectChannel` can propagate synchronously; async flows need an error channel. | Listener/container decides rollback/requeue/seek/DLQ; error flow config can affect ACK. |
| History replay needed | In-memory queues offer no replay capability. | Kafka typically permits re-reading within retention; queue brokers need DLQ/archiving or saved copies. |

**Design principle:** message existence, message delivery, message confirmation, and business commit are **distinct events**. Every integration diagram should depict at least the storage boundary and the confirmation boundary of critical flows.

## 9. At-most-once, at-least-once, and exactly-once effect

- **At-most-once:** messages may be lost on failure, with no redelivery attempt within the guarantee scope; fits non-critical signals.
- **At-least-once:** redelivery occurs when unconfirmed; processing may happen **more than once**, so consumers must tolerate duplicates.
- **Exactly-once effect:** final business state equals processing once. Scope must be defined explicitly, since a broker cannot make an external REST API or database execute exactly once merely via an ACK setting.

Consider an invoice-creating consumer. If DB write succeeds yet the process dies before ACK, the broker can redeliver `eventId=evt-246`. The handler must then check `eventId` in a unique-keyed deduplication table and place **recording completion in the same transaction** as updating the invoice.

~~~sql
-- PostgreSQL illustration schema:
-- processed_event(event_id PRIMARY KEY, processed_at, ...)
BEGIN;

INSERT INTO processed_event(event_id, processed_at)
VALUES (:eventId, CURRENT_TIMESTAMP)
ON CONFLICT (event_id) DO NOTHING;

-- Create/update the invoice only if the INSERT above
-- actually added a row (check affected row count in the app).
-- INSERT INTO invoices(...) VALUES (...);

COMMIT;
~~~

If sending emails, charging payments, or calling HTTP APIs outside the database transaction, use an idempotency key on the target system or a dedicated outbox to manage side effects. Never conflate “internal message deduplication” with “preventing duplicate external business effects”.

## 10. Do Router, Filter, Transformer, and Splitter/Aggregator alter broker semantics?

EIP components structure processing inside Spring Integration, yet do not change the transport contract merely by appearing in a flow.

### Router and Filter

`Router` selects branches by header, payload, or expression; `Filter` accepts/drops messages by application rules. If the broker delivered a message and the handler finishes by ignoring it under a valid rule, the system may ACK the message per policy. If the filter rejects due to data errors needing investigation, route to quarantine or an error flow and specify clearly whether to ACK or requeue.

### Transformer

`Transformer` transforms payloads or headers for processing; by itself it does not persist messages in a broker. If transformation strips `eventId`, `correlationId`, or trace context, deduplication and tracing become difficult. Actively preserve business-meaningful identifiers.

### Splitter and Aggregator

`Splitter` produces multiple child messages; `Aggregator` groups messages by correlation, release strategy, and timeout. The broker storing **one** parent message does not mean the broker manages **all group state** inside the application. For long-running aggregations across restarts, evaluate persistent `MessageGroupStore`, correlation strategy, release strategy, timeouts, and duplicate child messages.

### Gateway and request–reply

`Messaging Gateway` lets business code call a familiar API to enter a flow and optionally await a reply. With internal channels, `replyChannel` can be an object tied to a single process. For request–reply across a broker, you need an appropriate reply destination, `correlationId`, timeouts, and late/duplicate reply handling; never assume internal reply channels stay valid across restarts.

## 11. Error channel, retry advice, and broker redelivery are separate mechanisms

Three layers to distinguish:

1. **In-handler retry:** an interceptor/advice or application logic re-invokes the operation within the same delivery. Requires backoff and attempt limits.
2. **Broker redelivery:** when a consumer fails to ACK, rolls back, loses connection, or leaves offsets uncommitted, the broker/client redelivers records/messages under its own mechanism.
3. **Error channel:** Spring Integration routes an `ErrorMessage` onto an error-handling path to log, notify, or route; it does not create transport redelivery guarantees.

An error handler that **catches and swallows exceptions** can cause the listener to treat the attempt as successful and ACK/commit, depending on configuration. To roll back or route to a DLQ, configure the interaction among flow errors, advice, listener container, and ACK/transactions explicitly.

~~~mermaid
flowchart TD
  IN["Broker delivers"] --> HD{"Handler result"}
  HD -->|Success| ACK["ACK / commit per transport"]
  HD -->|Transient failure| RET["Retry with backoff"]
  RET --> HD
  HD -->|Retries exhausted| POLICY{"Error policy"}
  POLICY -->|Reject / DLQ| DLQ["Dead-letter / quarantine"]
  POLICY -->|Rollback / requeue| BACK["Broker redelivery"]
  POLICY -->|Handler swallows error| ACK
~~~

The diagram depicts policy options, not a mandatory default across every adapter. With Kafka, “rollback/requeue” usually maps to read-position management, seeking, or retry topics rather than NACKing a queue item.

## 12. Ordering, fan-out, and consumer groups

Processing order is another area easily confused between the two layers:

- On a synchronous `DirectChannel`, a `send()` call traverses handlers on the current thread; if multiple producers send concurrently, concurrency still applies.
- With `ExecutorChannel`, `QueueChannel` with multiple pollers, or multiple workers, **completion order** can differ from send order.
- RabbitMQ uses one queue with multiple consumers to share work, where prefetch, unacked messages, and redeliveries can affect observed order.
- Kafka preserves record order within each partition; multiple partitions have no global order. Choose a partition key like `orderId` when per-order sequencing is needed.
- A typical `PublishSubscribeChannel` broadcasts to subscribers in the current application. On a broker, separate groups/subscriptions receive independent consumption streams per transport rules; consumers **within the same group/work queue** typically share the workload.

To fan out to `Billing`, `Shipping`, and `Analytics` while processing each event once per group, declare appropriate broker/subscription topologies and correlation keys; never put three competing workers on a single work queue expecting all three to see every event.

## 13. Backpressure and monitoring at each layer

Publishing faster than processing builds a backlog. Channel and broker layers require different metrics.

| Location | Metrics to track | Operational decisions |
|---|---|---|
| `QueueChannel` | Queue depth, poll latency, message age, handler exceptions. | Tune capacity, pollers, transactions, and processing speed. |
| `ExecutorChannel` | Active threads, queued tasks, rejected tasks, handler latency. | Adjust bounds or handle rejections cleanly; avoid unbounded executors. |
| RabbitMQ/JMS | Ready/in-flight/unacked counts, queue depth, consumer count, redeliveries, and DLQ. | Evaluate prefetch, retries, broker capacity, ACK rules. |
| Kafka | Consumer lag per group/partition, processing latency, rebalances, offset commit failures. | Tune partitions, workers, batching, retention, and error handling. |
| Business DB/API | Idempotency hits, commit counts, failed transactions, duplicate side-effect attempts. | Verify **business effectiveness**, beyond mere message transport. |

Propagate `eventId`, business keys (`orderId`), `correlationId`, and trace context across inbound/outbound adapters. Never rely solely on broker message IDs to recognize the same **business event** republished after failure. Alert on **oldest message age / consumer lag and sustained processing errors**, in addition to queue length.

## 14. Choosing architecture by requirement

| Requirement | Initial choice | What else to verify |
|---|---|---|
| Very fast steps, same thread/process. | `DirectChannel`. | Exception propagation, caller blocking time, internal transactions. |
| Heavy processing needing thread offloading, no restart durability needed. | `ExecutorChannel`. | Executor capacity/rejection, async error flow. |
| Buffering between steps inside one application. | `QueueChannel` + poller. | Capacity, data loss on restart, dequeue semantics. |
| Persisting messages within an app across restarts. | `QueueChannel` + persistent store. | Schema, serializer, transactions/rollbacks, lock contention. |
| Two independent services needing work queues and ACK/redelivery. | RabbitMQ or JMS provider + SI adapter. | Durability, publisher confirms, listener ACK, retry/DLQ. |
| Need retained history stream, multiple reader groups, and replay. | Kafka + SI adapter. | Retention, partition keys, consumer lag, offset semantics. |
| One event has multiple independent business branches. | Broker fan-out/subscription or matching topology. | Each group needs its own subscription/queue and idempotency. |

There is no one-size-fits-all solution. Start from the **failure model**: which message loss is acceptable, recovery time objective, duplicate impact, required ordering scope, and how decoupled consumers must be from producers.

## 15. Practice exercise: verify through fault injection

Create an `OrderPlaced(eventId="evt-246", orderId="order-42")` event and test two setups: an in-memory `QueueChannel`, then an adapter crossing a broker. Record behavior and DB state across these scenarios:

1. **No consumer:** emit 100 events; measure backlog and buffer-limit effects.
2. **Application restart:** enqueue and restart before processing; verify differences among memory queue, persistent store, and broker.
3. **Failure after dequeue:** make the handler throw an exception; check whether the message is reprocessed or lost under the current config.
4. **Failure after business commit:** intentionally redeliver the same `eventId`; verify the invoice is created only once.
5. **Two competing consumers:** emit multiple messages with the same `orderId`; measure receipt order, completion order, and guard against out-of-order updates.
6. **Poison message:** send an invalid payload; observe retries, error channel, DLQ, and alerts.
7. **Publisher disconnect:** disconnect the broker mid-publish; distinguish outbound call return from broker confirmation per configuration.
8. **Replay or late reply:** replay a Kafka record if applicable, or send a late reply to a gateway; verify deduplication, correlation, and timeouts.

Each test must answer: **does the message exist, who received it, when is it considered done, can it be redelivered, and do business results duplicate?** Never check only how many times `send()` returned `true`.

## 16. Pre-production checklist

- [ ] Clearly distinguish in-app channels, transport adapters, and broker queues/topics in deployment diagrams.
- [ ] Document the ACK/offset/transaction contract at each inbound adapter and producer confirms at outbound adapters if required.
- [ ] Identify where messages survive crashes and each component's recovery responsibility.
- [ ] Configure bounded retries/backoff, error flows, DLQ/quarantine, and replay procedures.
- [ ] Use stable `eventId`, idempotency, and end-to-end correlation/trace context.
- [ ] Test duplicate deliveries, crashes before/after commit, restarts, and order-sensitive concurrency.
- [ ] Monitor channel backlogs, broker queue/consumer lag, idempotency, and business outcomes.
- [ ] Set capacity limits, TTL/retention, and full-queue policies to prevent cascading congestion.
- [ ] Verify exact behavior of your provider, listener container, converters, and Spring Integration version in deployment.

**Key takeaway:** Spring Integration channels express **how components inside a flow exchange messages**; broker semantics express **how infrastructure transports, stores, distributes, and confirms messages**. Adapters bridge the two layers, while durability, redelivery, and business-effect accuracy must be defined, configured, and tested right at their boundaries.
