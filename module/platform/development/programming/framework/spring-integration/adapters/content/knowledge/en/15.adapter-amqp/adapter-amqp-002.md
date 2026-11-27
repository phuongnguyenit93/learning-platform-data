# AMQP outbound channel adapter

## Learning Objectives

After this lesson, you will be able to:

- Describe the path **MessageChannel → AMQP outbound channel adapter → RabbitTemplate → RabbitMQ exchange → queue**.
- Distinguish a one-way outbound adapter from a **request–reply** outbound gateway.
- Design payloads, AMQP message properties, headers, routing keys, bindings, and MessageConverters for business events.
- Write a Spring Integration Java DSL flow to publish messages to RabbitMQ and verify the actual outcome.
- Distinguish **publisher confirms**, **publisher returns**, and **consumer ACK**, and use them to decide on retries, progress tracking, idempotency, and outbox patterns.
- Evaluate performance, security, connection lifecycle, and recovery strategies when downstream systems fail.

## 1. Why Do We Need an AMQP Outbound Channel Adapter?

Suppose an ordering application emits an **OrderCreated** event after recording an order. The warehouse system, notification service, and analytics system all need this event, but they do not need to be invoked synchronously within the same HTTP request. RabbitMQ can sit in between: the producer publishes the event to an **exchange**, the broker routes the message to the appropriate **queues**, and consumers pick it up when ready.

Spring Integration's **AMQP outbound channel adapter** is the endpoint at the **sending boundary**. It receives a Spring Message from a MessageChannel, translates its content via Spring AMQP infrastructure, and publishes it to RabbitMQ. Upstream business logic does not have to manage RabbitMQ client channels directly.

~~~mermaid
flowchart LR
    S["OrderService<br/>OrderCreated"] --> M["Spring Message<br/>payload + headers"]
    M --> C["MessageChannel<br/>ordersToAmqp"]
    C --> A["AMQP outbound<br/>channel adapter"]
    A --> T["RabbitTemplate<br/>MessageConverter"]
    T --> X["RabbitMQ direct exchange<br/>orders.events"]
    X -->|"orders.created"| Q["Queue<br/>orders.created.q"]
    Q --> H["Receiving consumer"]
~~~

Key points to remember:

- **Spring MessageChannel** is internal application messaging infrastructure; it is not a RabbitMQ queue.
- **Outbound adapter** consumes a message and performs a one-way publish action; it does not automatically return a consumer's business response.
- **RabbitTemplate** and **ConnectionFactory** manage the AMQP client side, whereas **exchange/binding/queue** form the topology on the broker.
- **Consumers** decide how to process deliveries and ACK/NACK once messages reach a queue. The producer must not infer consumer business outcomes on its own.

## 2. The Publishing Journey and Different Completion Milestones

| Stage | Component | What Happened |
| --- | --- | --- |
| 1. Event preparation | Business service / transformer | Creates payload and business identification details |
| 2. Internal handoff | MessageChannel | Accepts the message according to channel semantics |
| 3. Boundary handling | AMQP outbound adapter | Receives message, determines exchange/routing key and conversion strategy |
| 4. AMQP message creation | MessageConverter | Maps payload and properties to body bytes + metadata |
| 5. Sending request | RabbitTemplate | Publishes via ConnectionFactory per configuration |
| 6. Broker reception | RabbitMQ exchange | Evaluates routing, may emit publisher confirm |
| 7. Message reaches queue | Binding/queue | Queue holds the delivery per topology and broker policies |
| 8. Receiving business logic | Consumer | Reads delivery, processes, and ACKs/NACKs per contract |

**Step 2 does not prove step 6; step 6 does not prove step 7; step 7 does not prove step 8.** Each step has its own observability and recovery mechanisms.

### 2.1. Exchange and Routing Key Determine the Destination

RabbitMQ does not require every producer to send directly to a queue. The producer publishes to an exchange with a routing key; the exchange uses bindings and its exchange type to route:

~~~mermaid
flowchart TD
    P["Publisher"] --> E["Direct exchange<br/>orders.events"]
    E -->|"Binding key: orders.created"| Q1["orders.created.q"]
    E -. "No matching binding" .-> U["Unroutable<br/>must be handled per policy"]
    Q1 --> C["AMQP inbound consumer"]
~~~

| Concept | Responsibility |
| --- | --- |
| **Exchange** | Reception point for publishes and routing decision-maker |
| **Routing key** | Information supplied by the producer for the exchange to select routes |
| **Binding** | Links an exchange to a queue under routing criteria |
| **Queue** | Holds routed messages according to broker policies |
| **Consumer acknowledgment** | Confirms or rejects a delivery on the consumer side |

A **direct exchange** typically matches the routing key against the binding key; a **topic exchange** uses patterns; a **fanout exchange** uses bindings to broadcast to multiple queues. The **default exchange** has an empty name and routes by queue name, which is a special case. This lesson uses a named exchange to make the model clear.

### 2.2. A One-Way Endpoint Has No Business Reply

The outbound channel adapter receives a message and executes a publish operation; it does not emit a reply message carrying a business result from the receiving system. An adapter invocation may fail synchronously or trigger producer callbacks, but **a broker ACK does not become a business response from the order processor**.

If you need to send a request over AMQP and receive a business response so the flow can continue, use an **AMQP outbound gateway** or design an asynchronous reply workflow with a correlation ID and a dedicated reply destination.

## 3. Adapters, Gateways, and AMQP Communication Directions

| Endpoint | Data Direction | Contract | Example |
| --- | --- | --- | --- |
| **AMQP outbound channel adapter** | Spring MessageChannel → RabbitMQ | One-way | Publish OrderCreated |
| **AMQP inbound channel adapter** | RabbitMQ queue → Spring MessageChannel | One-way | Receive OrderCreated |
| **AMQP outbound gateway** | Flow → RabbitMQ → reply to flow | Request–reply | Query processing status over AMQP |
| **AMQP inbound gateway** | RabbitMQ request → flow → AMQP reply | Request–reply | Receive command, execute, and return result |

An AMQP gateway can use a reply-to destination, correlation ID, and timeout. Those details are different from **publisher confirm** and **consumer ACK**. Do not choose a gateway just to "know whether the broker received the message"; use publisher confirms/returns for technical delivery confirmation.

## 4. Payload, MessageConverter, and AMQP Properties

A Spring Message consists of a **payload** and **MessageHeaders**. An AMQP message on the wire has **body bytes** and **message properties**. Each part should be mapped explicitly:

~~~text
Spring Message
├── payload: String / byte[] / DTO / ...
└── headers
    ├── eventId (if added)
    ├── correlation ID
    └── flow metadata
           |
           v
AMQP outbound adapter + MessageConverter
           |
           v
AMQP message
├── body: byte[]
└── properties
    ├── contentType / contentEncoding
    ├── deliveryMode
    ├── messageId / correlationId
    └── mapped application headers
           |
           v
RabbitMQ exchange + routing key
~~~

Do not assume every Spring header is automatically transferred to AMQP properties. Mapping depends on the module, adapter configuration, RabbitTemplate, and converter.

| Payload | Conversion Approach | Notes |
| --- | --- | --- |
| **String** | Encodes bytes using a charset, typically text format | Producer and consumer must agree on charset |
| **byte[]** | Sends binary body | Consumer must understand the wire format |
| **DTO or Java record** | Converter/serializer produces JSON, Avro, Protobuf, or another schema | Do not emit arbitrary Java objects when multiple languages consume |
| **Large file** | Read/stream or pass a file reference depending on design | Avoid loading entire large payloads into a single message by default |

### 4.1. Metadata to Design Intentionally

| Field | Purpose | What to Avoid |
| --- | --- | --- |
| **contentType** | Declares the body format | Declaring JSON while sending non-JSON bytes |
| **contentEncoding** | Charset/compression per contract | Decoding with the wrong charset |
| **deliveryMode** | Specifies persistent mode when needed | Assuming a durable queue alone is enough |
| **messageId** | Traces the message | Treating it as a business deduplication key |
| **correlationId** | Pairs request/reply or tracing | Using it in place of eventId when purposes differ |
| **eventId** | Stable business key across retries | Generating a new eventId on each retry |
| **replyTo** | Used in request–reply | Adding arbitrarily to one-way events |
| **routing key** | Routing at the exchange | Confusing with Spring MessageChannel name |

Spring Integration headers such as **replyChannel** and **errorChannel** can hold internal references to MessageChannels and **should not be serialized as-is to RabbitMQ**. Allow only metadata that truly needs to cross the boundary, and validate header types and values.

### 4.2. Converter and Transformer Have Two Distinct Roles

- A **Transformer** in the flow standardizes the business event, for example converting an OrderCreated DTO into a JSON String with schemaVersion.
- **RabbitTemplate's MessageConverter** converts the payload into AMQP body/properties for publishing.

If a JSON converter already serializes the DTO into JSON, do not stack another JSON transformer before it and double-encode the body. For real events, specify schema, charset, required fields, version, and payload size limits.

## 5. Spring Integration Java DSL Example: Sending OrderCreated to RabbitMQ

This example creates the following topology and flow:

~~~mermaid
flowchart LR
    P["OrderEventPublisher"] --> CH["ordersToAmqp<br/>DirectChannel"]
    CH --> AD["Amqp.outboundAdapter"]
    AD --> R["RabbitTemplate"]
    R --> EX["orders.events"]
    EX -->|"orders.created"| Q["orders.created.q"]
~~~

**Illustrative contract:** the event is represented as a String **eventId|orderId|totalVnd**. This is a minimal pattern for the lesson; production systems should use JSON/Avro/Protobuf with explicit parsers/serializers and schemas.

### 5.1. Dependencies and Connectivity

With Spring Boot, use appropriate dependency management to manage Spring Integration/Spring AMQP versions:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-amqp</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-amqp</artifactId>
    </dependency>
</dependencies>
~~~

The application needs an available RabbitMQ broker and a RabbitTemplate/ConnectionFactory configured with host, port, virtual host, authentication, and TLS per environment. Real credentials must be supplied via a secret manager or environment variables, never committed to source control.

### 5.2. Topology and Outbound IntegrationFlow

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.amqp.dsl.Amqp;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class OrdersAmqpOutboundConfiguration {

    public static final String EXCHANGE = "orders.events";
    public static final String ROUTING_KEY = "orders.created";
    public static final String QUEUE = "orders.created.q";

    @Bean
    public DirectExchange ordersExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    public Queue createdOrdersQueue() {
        return new Queue(QUEUE, true);
    }

    @Bean
    public Binding createdOrdersBinding(
            Queue createdOrdersQueue,
            DirectExchange ordersExchange) {
        return BindingBuilder.bind(createdOrdersQueue)
            .to(ordersExchange)
            .with(ROUTING_KEY);
    }

    @Bean
    public MessageChannel ordersToAmqp() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow publishOrdersFlow(RabbitTemplate rabbitTemplate) {
        return IntegrationFlow.from("ordersToAmqp")
            .handle(Amqp.outboundAdapter(rabbitTemplate)
                .exchangeName(EXCHANGE)
                .routingKey(ROUTING_KEY))
            .get();
    }
}
~~~

**Explanation:**

1. **DirectExchange** receives published messages and routes using the routing key.
2. **Queue** is created durable to illustrate topology that should survive broker restarts; a durable queue alone does not guarantee messages will not be lost.
3. **Binding** connects the exchange to the queue using **orders.created**.
4. **ordersToAmqp** is the DirectChannel into which the internal producer sends Spring Messages.
5. **Amqp.outboundAdapter(rabbitTemplate)** creates the outbound endpoint; exchangeName and routingKey specify the destination properties for each publish.

Exchange, queue, and binding beans can be declared automatically by RabbitAdmin when properly configured, connected, and authorized. If your organization manages topology through separate infrastructure tooling, do not assume bean declarations mean the broker topology already exists; verify it in practice.

### 5.3. Producer Sending to MessageChannel

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final MessageChannel ordersToAmqp;

    public OrderEventPublisher(
            @Qualifier("ordersToAmqp") MessageChannel ordersToAmqp) {
        this.ordersToAmqp = ordersToAmqp;
    }

    public void publish(
            String eventId, String orderId, long totalVnd) {
        if (eventId == null
                || !eventId.matches("[A-Za-z0-9_-]{1,80}")
                || orderId == null
                || !orderId.matches("[A-Za-z0-9_-]{1,80}")
                || totalVnd <= 0) {
            throw new IllegalArgumentException(
                "Invalid order event");
        }

        String body = eventId + "|" + orderId + "|" + totalVnd;
        Message<String> message = MessageBuilder.withPayload(body)
            .setHeader("eventId", eventId)
            .build();

        boolean accepted = ordersToAmqp.send(message);
        if (!accepted) {
            throw new IllegalStateException(
                "Failed to send message to channel");
        }
    }
}
~~~

Example:

~~~java
publisher.publish("evt-1001", "O-1001", 150000L);
~~~

Illustrative body:

~~~text
evt-1001|O-1001|150000
~~~

**eventId is placed in the payload** so the consumer can read it even if the application header eventId is not mapped into AMQP properties by a header mapper. If a partner requires eventId in an AMQP header, configure and test header mapping explicitly.

**DirectChannel** invokes the outbound handler synchronously in the same execution chain. Synchronous send errors can propagate back to the caller; however, **a successful send() does not prove publisher confirm was received, the message was routed to a queue, or the consumer processed it**.

### 5.4. Testing Across Each Boundary

1. Run RabbitMQ in a test environment and configure ConnectionFactory.
2. Start the application; verify that the exchange, queue, and binding were actually declared.
3. Call publish with evt-1001, O-1001, and 150000.
4. Use RabbitMQ management or a test consumer to inspect the message in orders.created.q, its body, and its properties.
5. Send another eventId and verify stable routing.
6. In a separate test, try an unbound routing key to observe publisher returns when mandatory is enabled.
7. Pause the consumer to observe backlog; resume it to verify the consumer reads messages according to the ACK policy.

If the consumer processes very quickly, the queue may be empty by the time you look; **a queue depth of 0 does not prove publishing failed**. Use publish/deliver/ack metrics or a consumer to verify the content.

**Example limitations:** The pipe-delimited format only suits validated IDs as shown above. The code does not yet handle confirms/returns, outbox, retries, transactions, or schema versioning. For production, add these before using it to emit critical events.

## 6. Three Confirmation Mechanisms to Distinguish

~~~mermaid
sequenceDiagram
    participant A as Outbound adapter
    participant T as RabbitTemplate
    participant X as RabbitMQ exchange
    participant Q as Queue
    participant C as Consumer
    A->>T: Publish AMQP message
    T->>X: basic.publish
    alt Matching route exists
        X->>Q: Route to queue
    else Unroutable with mandatory
        X-->>T: basic.return
    end
    X-->>T: Publisher confirm ACK/NACK
    Q-->>C: Delivery
    C-->>Q: Consumer ACK/NACK (separate)
~~~

| Signal | Sender | Meaning | Does Not Prove |
| --- | --- | --- | --- |
| **Publisher confirm** | RabbitMQ → publisher | Broker acknowledges publish under the confirms mechanism | Consumer completed business logic |
| **Publisher return** | RabbitMQ → publisher | Publish could not be routed with mandatory and no matching route | Consumer parse/write error |
| **Consumer ACK/NACK** | Consumer → RabbitMQ | Consumer confirms/rejects a delivery | Producer received a business reply |

### 6.1. Publisher Confirms

Publisher confirms are enabled at the RabbitMQ client layer. Spring Boot configuration example:

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
~~~

With correlated confirms, the application can use **CorrelationData** and callbacks/futures per Spring AMQP's API to correlate ACK/NACK results with each publish attempt. **Enabling confirms does not automatically turn an outbound adapter into a gateway**, does not persist outbox state on its own, and does not implicitly return a business reply to the caller.

If business logic needs confirmation that an event reached the broker milestone, you must collect confirms, handle NACKs/timeouts, and update state according to the contract. Do not rely solely on the boolean return of MessageChannel.send().

### 6.2. Mandatory and Publisher Returns

If the exchange exists but no binding matches, a message can be **unroutable**. To observe this case, enable returns and mandatory:

~~~yaml
spring:
  rabbitmq:
    publisher-returns: true
    template:
      mandatory: true
~~~

With RabbitTemplate, returned messages can be handled via **ReturnsCallback** or an appropriate tracking mechanism. RabbitMQ can send a **publisher confirm ACK** for an **unroutable** publish, so **confirm ACK does not replace checking returns**.

If multiple parts of the application share a RabbitTemplate, manage callbacks centrally; do not overwrite callbacks used by other components. In critical flows, maintain a unified publish tracker to correlate eventId, confirm, return, and timeout.

### 6.3. Consumer ACK Is Not Directly Tied to Producer Confirm

Consumer ACK occurs after RabbitMQ delivers the message to the consumer according to the receiving side's mode and policy. A message can already be producer-confirmed before the consumer begins processing it.

Therefore, if you need to know that "the warehouse system finished updating", the producer needs a **business response or reconciliation mechanism**—looking at publisher confirm ACK alone is not enough.

## 7. Durable Queues, Persistent Messages, and Delivery Guarantees

Reliability depends on topology, message properties, broker, producer, and consumer alike:

- Do the exchange, queue, and binding exist correctly?
- Are the queue durability and queue type/broker policy aligned with fault-tolerance goals?
- Does the message have **persistent delivery mode** when durable storage is required?
- Does the publisher track confirms and returns?
- Does the consumer ACK at the right moment, and can it handle redelivery?
- Are idempotency and recovery checkpoints in place after a restart?

A **durable queue** does not automatically make every message persistent, does not prevent a producer from publishing with the wrong routing key, and does not guarantee end-to-end exactly-once delivery. Check the delivery mode configuration of your converter/template rather than inferring it from whether the payload is a String or DTO.

For quorum queues or other durability policies, evaluate RabbitMQ cluster requirements, throughput, recovery behavior, and deployment topology. A solid queue choice still does not replace guarding against duplicate business side effects.

## 8. Outbound Failures, Retries, and Unknown Send States

A publish attempt can fail or have an uncertain outcome for different reasons. Do not retry all errors with the same policy:

| Stage | Example Error | Recommended Response |
| --- | --- | --- |
| **Pre-send** | DTO serialization failure, invalid schema, message too large | Isolate, fix data/contract; simple retries will not cure it |
| **Connection** | RabbitMQ unavailable, DNS/TLS error, insufficient permissions | Bounded retry with backoff; alert on configuration issues |
| **Routing** | Missing exchange, routing key matches no binding | Check topology; use publisher returns for unroutable messages |
| **Broker publish handling** | Publisher confirm NACK or closed channel | Record failed send state; consider policy-driven retry |
| **Missing confirm** | Broker may have received before network timeout | Record UNKNOWN state, reconcile, and retry with stable eventId |
| **Receiving-side failure** | Consumer parse error, DB deadlock | Retry/requeue/DLQ on the consumer; producer cannot fix that by itself |

### 8.1. Retries Do Not Guarantee At-Most-Once Delivery

Suppose a producer publishes event **evt-1001** successfully, but the connection drops before receiving the publisher confirm. The application sees a timeout, retries immediately, and the broker may receive the same event a second time.

The key solution is keeping a **stable eventId**, such as evt-1001, and using an **idempotent consumer**: persist processed eventIds alongside business outcomes, or use a unique constraint/inbox table. Do not generate a new eventId on each retry, and do not use a newly generated MessageHeaders.ID as the sole deduplication key.

**Retry** means re-attempting an operation that can fail. **Idempotency** means retrying does not create duplicate business side effects. The two mechanisms must complement each other.

### 8.2. The UNKNOWN State Must Be Recognized

When it is uncertain whether the broker received the message, do not force events into only two states: SUCCESS/FAILED. An outbox design can use application-level states such as:

~~~text
NEW -> SENDING -> CONFIRMED
           |       |
           |       +-- (awaiting separate business processing)
           |
           +--> RETRYABLE_ERROR
           +--> PERMANENT_ERROR
           +--> UNKNOWN -> reconcile or idempotent resend
~~~

These are **application-designed labels**, not default Spring Integration enums. Depending on SLA, you can store last send timestamp, retry count, last error, eventId, exchange, and routing key for investigation.

### 8.3. Bounded Retries and Backoff

- Retry only when recovery is plausible, such as temporary broker unavailability.
- Use backoff and optionally jitter to avoid thundering-herd retries after an outage.
- For schema errors, missing permissions, or non-existent routing, raise alerts and fix the root cause.
- After retries are exhausted, keep the event in durable state storage so operations can follow up.
- Ensure publisher confirms/returns and asynchronous errors have dedicated handling paths instead of only catching exceptions inside the send() caller.

### 8.4. DLQ Does Not Automatically Catch Every Publish Error

A RabbitMQ **dead-letter exchange/queue** primarily serves messages that already entered a queue and were then rejected/nacked without requeue, exceeded TTL, or were dead-lettered by another policy. If the outbound adapter **cannot publish to the exchange**, or the message is **unroutable**, the message may never enter a queue for that DLQ mechanism to process.

Therefore, separate two questions:

1. **Producer cannot publish:** store in an outbox/error store, and retry/alert per producer policy.
2. **Consumer cannot process delivery:** use retry, requeue, DLX/DLQ, and idempotency per consumer policy.

~~~mermaid
flowchart TD
    E["Event pending publish"] --> V{"Valid payload/route?"}
    V -- "No" --> BAD["Isolate and fix contract"]
    V -- "Yes" --> PUB["AMQP outbound publish"]
    PUB --> C{"Confirm / return / timeout"}
    C -- "ACK and no return" --> OK["Reached broker milestone per config"]
    C -- "Returned unroutable" --> RT["Fix binding or routing"]
    C -- "NACK or transient error" --> RET["Bounded retry"]
    C -- "UNKNOWN" --> UN["Reconcile + stable eventId"]
    RET --> PUB
~~~

Even the **ACK and no return** branch still does not prove the consumer has finished business processing.

## 9. Database Transactions and Transactional Outbox

A common problem: an application saves an order to the database and then emits an AMQP event. These are two independent resources, leading to several scenarios:

1. Database commits successfully, but the application crashes **before publishing**: downstream systems never hear about the new order.
2. Publish succeeds, but the producer crashes **before recording sent status**: the next run may publish the event again.
3. Broker receives the event, but the publisher **never receives the confirm**: send status is uncertain.

**Transactional outbox** is the right pattern when events must stay tied to business state changes:

~~~mermaid
flowchart LR
    S["OrderService"] --> TX["Database transaction"]
    TX --> O["Orders table"]
    TX --> OB["Outbox events"]
    OB --> W["Outbox worker<br/>retry + status"]
    W --> C["MessageChannel"]
    C --> A["AMQP outbound adapter"]
    A --> MQ["RabbitMQ"]
    MQ --> I["Idempotent consumer"]
~~~

Within the same database transaction, the system writes both the Order and an OutboxEvent record (e.g., eventId, payload, event type, schemaVersion). A worker reads the outbox, sends it to the MessageChannel, and publishes via the outbound adapter. The worker records publish progress against the committed confirmation milestone; on failure, it can retry.

**Outbox does not create an atomic transaction between the database and RabbitMQ.** It closes the gap where "DB committed but the event was never recorded for publishing", while providing a basis for recovery. The receiving consumer **must still be idempotent** because publishes can repeat after crashes or timeouts.

### 9.1. When Is Outbox Unnecessary?

Not every flow needs this pattern. If an event is best-effort and losing occasional notifications is acceptable, a simpler direct-send approach can suffice. However, for financial, inventory, order, or audit workflows with data integrity constraints, explicitly document **no lost events**, **no duplicate side effects**, and how they are verified before omitting an outbox.

### 9.2. Do RabbitTemplate Transactions Replace Outbox?

Spring AMQP and RabbitMQ support their own transaction/confirmation mechanisms, but a broker transaction **does not automatically** span database, HTTP, SFTP, or Kafka transactions. Define the exact boundary of each resource and commit order. Never claim end-to-end exactly-once just because a transaction flag is turned on.

## 10. MessageChannel Determines How the Adapter Is Triggered

The AMQP outbound adapter is a **consumer of a MessageChannel**. The channel type affects latency, backpressure handling, and error paths:

| Channel | Mechanism | Considerations with AMQP Outbound |
| --- | --- | --- |
| **DirectChannel** | Subscriber runs synchronously on the sender's thread | Synchronous RabbitTemplate errors propagate back; slow publishes block the caller |
| **ExecutorChannel** | Dispatches work to a thread pool | Producer may return early; publish errors surface on another thread |
| **QueueChannel** | Buffers messages for a polling consumer | Requires poller, capacity planning, queue-full handling, and restart durability |
| **PublishSubscribeChannel** | Broadcasts to multiple subscribers | One outbound branch may succeed while another fails |

### 10.1. DirectChannel in the Example

When OrderEventPublisher calls send(), DirectChannel typically invokes the AMQP outbound handler on the same thread. If conversion or publishing throws an exception immediately, the caller observes the error. However, **publisher confirms or returns may arrive later** and are not reflected in send()'s boolean return value.

### 10.2. QueueChannel and Poller on the Outbound Side

If you want to pace outgoing publishes, you can place a **QueueChannel** ahead of the outbound endpoint and use a **polling consumer** to pull messages for publishing:

~~~mermaid
flowchart LR
    P["Producer"] --> Q["QueueChannel"]
    POL["Consumer poller"] -.-> Q
    Q --> A["AMQP outbound adapter"]
    A --> R["RabbitMQ"]
~~~

This poller **pulls messages already in the internal channel**; it is not AMQP inbound polling. The RabbitMQ producer is invoked when the consumer endpoint receives a message.

**QueueChannel uses in-memory storage by default**, not durable persistence. If the process crashes before publishing, buffered messages can be lost. Use a persistent MessageStore, outbox, or external broker when high durability is required.

### 10.3. Do Not Use Concurrency to Hide Load Bottlenecks

If a business flow produces 1,000 events/second while RabbitMQ or the network can only handle 100 events/second, scaling an executor indefinitely only grows backlog, memory usage, and timeouts. Enforce limits on:

- Concurrent publishes, queue capacity, and timeouts.
- Payload size, serializer cost, and connection/channel limits.
- Retry/backoff cadence when the broker is unavailable.
- Consumer capacity to drain backlog once the publisher recovers.

RabbitMQ can preserve message order within a queue under certain conditions, but **business processing order** can change with multiple publishers/consumers, retries, priorities, or requeues. If per-orderId ordering is required, use version/sequence numbers and appropriate processing rules rather than relying solely on a single queue.

## 11. Routing to One or Multiple Systems

### 11.1. One Queue, Multiple Competing Consumers

When multiple consumers consume **one queue**, the broker typically distributes deliveries to share load. They **do not automatically each receive a copy**. This pattern fits scaling out multiple instances of the same worker.

### 11.2. One Event, Multiple Independent Systems

If both warehouse and notifications need every OrderCreated, create two queues and bind both to the exchange using appropriate rules:

~~~mermaid
flowchart TD
    P["AMQP outbound adapter"] --> X["orders.events"]
    X -->|"orders.created"| WQ["warehouse.orders.q"]
    X -->|"orders.created"| NQ["notifications.orders.q"]
    WQ --> W["Warehouse inbound consumer"]
    NQ --> N["Notifications inbound consumer"]
~~~

Each queue has its own backlog, retries, consumer ACKs, and DLQ. The producer only needs to publish one event with the contract's exchange/routing key.

### 11.3. Static or Dynamic Routing Keys?

**Static routing keys** such as orders.created are easy to test and manage when each flow publishes a single event type. Dynamic routing keys may be needed for multiple eventTypes, tenants, or regions, but valid values, corresponding topics/bindings, and handling for unroutable messages must be defined. Never construct routing keys arbitrarily from untrusted input.

## 12. Connection Lifecycle, Security, and Monitoring

The AMQP outbound adapter typically depends on RabbitTemplate, ConnectionFactory, and RabbitMQ client connections/channels. Many Spring Integration endpoints participate in **Lifecycle/SmartLifecycle**, yet **an endpoint being running** does not mean the broker is healthy or all publishes are confirmed.

### 12.1. Key Operational Concerns

| Group | What to Design or Monitor |
| --- | --- |
| **Connectivity** | Host, port, virtual host, timeouts, reconnects, pooled channels |
| **Security** | TLS, certificate verification, least-privilege accounts, secret rotation |
| **Topology** | Provisioned exchanges/queues/bindings; declare/publish permissions |
| **Producer** | Publish attempts, exceptions, confirm ACKs/NACKs, returned messages |
| **Broker** | Publish rate, route rate, queue ready/unacked counts, connection/channel count |
| **Business** | Emitted eventIds, outbox states, events actually processed by consumers |
| **Performance** | Publish latency, confirm latency, retries, backlog age |
| **Errors** | Unroutable, timeouts, converter errors, permission errors, UNKNOWN |

Do not log credentials or raw sensitive payloads. Use eventId/correlationId, endpoint name, controlled exchange/routing key values, and error codes for tracing.

### 12.2. Start, Stop, and Graceful Shutdown

Safe application shutdown typically requires:

1. Stop generating new publish work.
2. Record or preserve pending event state in an outbox or durable queue.
3. Monitor in-flight publishes and confirm outcomes within SLA.
4. Stop the outbound consumer and shared resources in the proper order.
5. Resume from persisted state on restart rather than relying on process memory.

**stop() does not mean all outgoing messages have drained successfully**, and stopping one endpoint does not automatically close a ConnectionFactory shared across other flows. If upstream endpoints such as HTTP/JMS/Kafka/SFTP or a database precede AMQP outbound, analyze their ACK/commit timing before letting callers assume publishing is complete.

## 13. Integration Scenario: OrderService → RabbitMQ → Two Consumers

An application needs to emit OrderCreated to the warehouse and notification services. Requirements:

- Every successfully saved order must have a corresponding event to publish.
- RabbitMQ may be temporarily unavailable; the application must resend safely.
- Both systems receive every event independently.
- Consumers do not execute business logic twice when an event is redelivered.

Reference design:

~~~mermaid
flowchart TD
    S["OrderService"] --> TX["Database transaction"]
    TX --> O["Orders"]
    TX --> OB["OutboxEvent: evt-1001"]
    OB --> W["Outbox publishing worker"]
    W --> C["ordersToAmqp"]
    C --> A["AMQP outbound adapter"]
    A --> X["orders.events exchange"]
    X --> WQ["warehouse.orders.q"]
    X --> NQ["notifications.orders.q"]
    WQ --> WC["Warehouse idempotent consumer"]
    NQ --> NC["Notification idempotent consumer"]
    A -. "Confirm/return/status" .-> W
~~~

Decisions that must be documented in the design:

1. **Event identity:** stable eventId across retries, explicit schemaVersion.
2. **Routing topology:** two queues and bindings, publish/consume permissions per service.
3. **Producer tracking:** ACK/NACK, returns, timeouts, UNKNOWN, and how the outbox is updated.
4. **Consumer processing:** inbox/unique constraint to prevent duplicate side effects.
5. **Failure policy:** schema errors quarantined; connection errors retried with limits.
6. **Observability:** reconcile confirmed outbox entries with business outcomes in warehouse and notifications.

Thus, a **successful AMQP outbound publish** does not mean both consumers have finished. Each system has its own progress and failure paths.

## 14. Test Suite Required Before Production

| Scenario | Outcome to Verify |
| --- | --- |
| Valid exchange/binding | Message reaches target queue through AMQP outbound adapter |
| Wrong routing key | Mandatory/returns mechanism detects unroutable message |
| Broker unavailable | Event is not falsely marked complete; retry/alert occurs |
| Publisher confirm | ACK/NACK is correlated with the exact publish attempt and eventId |
| Broker receives but slow consumer | Confirm ACK is not confused with business completion |
| Invalid payload | Converter/validator detects and isolates it |
| Duplicate eventId | Consumer produces no duplicate side effects |
| Multiple queues on one exchange | Both systems receive the event when bindings match |
| Multiple workers on one queue | Competing consumers, not broadcast by default |
| Producer restart | Unconfirmed events recover from outbox |
| Network timeout near confirm | UNKNOWN state handled and retried idempotently |
| Peak load | Monitor confirm latency, rate, backlog, timeouts, and memory |
| Mid-publish shutdown | Do not rely on in-memory QueueChannel for data requiring durability |

### 14.1. Three Especially Important Tests

**Unroutable:** In testing, publish to a valid exchange with a routing key that matches no binding. Observe the **return** when mandatory is enabled. Do not conclude routing succeeded solely from a confirm ACK.

**Unknown state:** Drop the connection after the broker may have received the publish but before the producer receives the confirm. Verify the worker records UNKNOWN or unconfirmed status and retries with a stable eventId.

**Restart and duplicate handling:** Resend an eventId already persisted by the consumer. Verify the inbox or unique constraint protects against duplicate side effects.

## 15. Common Mistakes

**Confusing a RabbitMQ queue with a Spring MessageChannel.** The channel lives in the application; the queue lives in the broker, with different persistence guarantees and delivery mechanisms.

**Assuming producers always send directly to a queue.** RabbitMQ publishes to an exchange. With the default exchange, the routing key can be a queue name, but do not generalize that to all topologies.

**Confusing publisher confirm ACK with consumer ACK.** The two mechanisms belong to opposite sides of communication; neither acts as a business reply on its own.

**Ignoring returned messages.** A publish can be confirmed by the exchange yet reach no queue because routing did not match.

**Using send() to mark an event as processed by all consumers.** Channel acceptance and broker confirmation are only intermediate milestones.

**Treating a durable queue as an exactly-once guarantee.** Consider persistence, broker policies, producer confirms, consumer ACKs, and idempotency.

**Retrying infinitely on invalid schema, missing exchange, or insufficient permissions.** These errors usually require fixing the contract or configuration before resending.

**Using MessageHeaders.ID as the business eventId.** A reconstructed message can get a new ID even for the same event; use a stable eventId.

**Pushing Java DTOs without a serializer contract.** Consumers in other languages or versions may fail to decode them; define the wire format and version.

**Assuming a consumer DLQ captures all publish errors.** Producer errors, unroutable messages, and messages that reached a queue are different cases.

**Treating an in-memory QueueChannel as an outbox.** Buffered messages can be lost if the process crashes; choose durable storage when required.

**Assuming multiple consumers on one queue all receive every event.** They typically split deliveries for parallel processing; fan-out requires a multi-queue topology.

## 16. Self-Check Questions

1. Through what steps does an event travel from OrderService via MessageChannel, AMQP outbound adapter, and RabbitTemplate to RabbitMQ?
2. How do exchange, routing key, binding, and queue differ?
3. How does an AMQP outbound channel adapter differ from an outbound gateway? When is a gateway needed?
4. What is actually proven when MessageChannel.send() returns true?
5. Why does publisher confirm ACK not guarantee a message routed into the right queue? When are mandatory and returns used?
6. Which parties emit producer confirm, publisher return, and consumer ACK?
7. How is a String payload converted into an AMQP body? What contract is needed when sending JSON DTOs?
8. Why must eventId remain stable across retries and differ from MessageHeaders.ID?
9. If the broker may have received a message but the application timed out before confirm, what state and recovery approach are needed?
10. Does a durable queue remove the need for an idempotent consumer? Why?
11. If both warehouse and notifications need OrderCreated, how must exchanges/queues/bindings be designed?
12. How does switching from DirectChannel to ExecutorChannel change error reporting paths and when the producer returns?
13. Why does a consumer dead-letter queue not automatically rescue all producer publish failures?
14. Why is transactional outbox commonly considered when saving to a database and publishing to AMQP?
15. Which metrics indicate producer routing errors, broker congestion, or a slow consumer?

## Summary

The **AMQP outbound channel adapter** is a one-way bridge from a **Spring Integration MessageChannel** to **RabbitTemplate**, through a **RabbitMQ exchange** to route into appropriate queues. A sound design explicitly defines payload, MessageConverter, properties, routing key, and message durability, and distinguishes **sending to the channel**, **publisher confirm**, **publisher return**, **message queued**, and **consumer ACK**. These milestones cannot substitute for final business outcomes. In systems integrating File, SFTP, HTTP, JMS, AMQP, Kafka, and databases, use bounded retries, stable eventIds, idempotent consumers, outbox when needed, end-to-end observability, and connection lifecycle management to publish events safely.
