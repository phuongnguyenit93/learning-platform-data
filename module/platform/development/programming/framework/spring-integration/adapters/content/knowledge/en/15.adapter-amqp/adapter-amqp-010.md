# Manual Acknowledgment and Retry

## Learning Objectives

After this lesson, you will be able to:

- Distinguish **manual acknowledgment (MANUAL ACK)** from **AUTO ACK** and **NONE** on a Spring AMQP listener container, and identify who is responsible for confirming deliveries.
- Correctly use **delivery tag**, **AMQP channel**, **basicAck**, **basicNack**, **basicReject**, and the **multiple** and **requeue** flags.
- Explain the exact relationship between **ACK**, **redelivery**, **prefetch**, **consumer transactions**, business errors, and end-to-end reliability.
- Design **bounded** retries, distinguish transient errors from permanent errors, avoid hot requeue loops, and coordinate **DLX/DLQ**.
- Build a **Spring Integration Java DSL** example: RabbitMQ → MANUAL listener container → AMQP inbound channel adapter → DirectChannel → service activator → ACK/NACK.
- Understand why **ExecutorChannel**, **QueueChannel**, listener error handlers, MessageConverters, and shutdown can alter the acknowledgment boundary.
- Apply **idempotent consumers**, inbox/unique constraints, ready/unacked monitoring, crash/restart handling, and pre-production failure testing.

## 1. Problem: When Can We Say Processing Is Complete?

Suppose the **Warehouse** service receives an **OrderCreated** event from RabbitMQ and must update the inventory database. A delivery passes through multiple stages:

~~~mermaid
flowchart LR
    P["OrderService"] --> X["RabbitMQ exchange"]
    X --> Q["orders.created.q"]
    Q --> L["Spring AMQP<br/>listener container"]
    L --> A["AMQP inbound<br/>channel adapter"]
    A --> C["DirectChannel"]
    C --> H["Service activator<br/>WarehouseService"]
    H --> DB[("Warehouse DB")]
    L -. "basicAck / basicNack / basicReject" .-> Q
~~~

If the application **ACKs before the database transaction commits** and then the process crashes, RabbitMQ clears its responsibility to redeliver even though the business work never finished. Conversely, if the database commits and the application crashes **before RabbitMQ receives the ACK**, the broker can redeliver the same event after the connection closes. The consumer can then execute the side effect twice unless deduplication is in place.

**Manual acknowledgment** lets the application choose exactly when to confirm a delivery. However, calling ACK manually **does not create end-to-end exactly-once** and **does not make RabbitMQ part of the database transaction**.

This lesson belongs to the **AMQP Adapter** chapter of **SPRING_INTEGRATION_ADAPTERS**. The universal rule when connecting external systems via File, SFTP, HTTP, JMS, AMQP, Kafka, or databases is: **identify the reception point, durable persistence point, processing point, and retryable point**. Never equate them with a successful `MessageChannel.send()` call.

## 2. Four Signals Not to Confuse

| Signal | Direction | What Does It Confirm? | What Does It Not Prove |
| --- | --- | --- | --- |
| **Publisher confirm** | RabbitMQ broker → publisher | Broker confirmed the status of a publish under confirms | Consumer committed business logic |
| **Publisher return** | RabbitMQ broker → publisher | Message could not be routed under mandatory/returns conditions | Consumer rejected a delivery |
| **Consumer ACK/NACK** | Consumer/listener → RabbitMQ broker | Consumer confirmed or rejected a **delivery** | Producer received a business reply |
| **Business reply/event** | Consumer service → caller/other system | Business outcome per separate contract | Broker will definitely not redeliver |

In this lesson, **ACK** (unless stated otherwise) refers to **consumer acknowledgment**: the signal sent after RabbitMQ delivers a message to a consumer.

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant B as RabbitMQ
    participant L as Listener container
    participant H as WarehouseService
    P->>B: Publish OrderCreated
    B-->>P: Publisher confirm (if enabled)
    B->>L: Delivery from queue
    L->>H: Spring Message through flow
    H->>H: Database transaction
    H-->>L: Success or error
    L-->>B: Consumer ACK/NACK
~~~

An **AMQP inbound channel adapter** receives messages one-way and does not send a business reply back to the producer. If an external caller needs request–reply, consider **AMQP inbound/outbound gateways** and a reply-to/correlation contract; consumer ACKs do not substitute for that reply.

## 3. AcknowledgeMode.AUTO, MANUAL, and NONE

Spring AMQP listener containers offer three common acknowledgment modes:

| Mode | Who Decides ACK? | Characteristics | Common Risks |
| --- | --- | --- | --- |
| **AUTO** | Container ACKs/NACKs based on listener outcome, error handler, and configuration | Fits synchronous handlers where the container should manage ACK | Swallowed exceptions or async work running after callback returns can cause early ACK |
| **MANUAL** | Application explicitly ACKs/NACKs/rejects using AMQP channel and delivery tag | Explicitly places confirmation after commit or durable storage | Forgotten ACK, double ACK, wrong channel/tag, requeue loops |
| **NONE** | Consumer runs without explicit acknowledgments | Simple, yet broker does not wait for processing outcomes like AUTO/MANUAL | Crash after delivery can lose redelivery opportunity |

### 3.1. AUTO Does Not Mean the Broker ACKs Upon Sending

In Spring AMQP, **AUTO** means the **container** manages ACK after the listener finishes according to policy. For a synchronous handler running through a DirectChannel, exceptions can propagate back to the container and trigger reject/requeue depending on error type and configuration. AUTO does not mean every error retries, nor does it make DB transactions atomic with ACK.

### 3.2. MANUAL Does Not Automatically Mean Safer

When choosing MANUAL, the application must handle every path:

1. Success, DB committed → **`basicAck`**.
2. Invalid data that retries cannot fix → **`basicReject`** or **`basicNack`** with **`requeue=false`**.
3. Transient error → retry per policy, then ACK on success; if retries exhaust, route to durable error storage.
4. Process crash, dropped connection, or failed ACK → tolerate **redelivery** and deduplicate.
5. Shutdown/cancellation and unexpected exceptions → never leave deliveries hanging indefinitely due to a missing branch.

With MANUAL, there is no universal **`finally { basicAck(...); }`** that is safe in all cases: ACKing in `finally` can acknowledge a message that failed processing.

### 3.3. Is NONE Suitable for Critical Business Logic?

When explicit ACKs are disabled, the broker cannot rely on post-processing ACKs to decide whether to redeliver if a process crashes. Use it only for explicitly best-effort workloads—never rely on it to prevent lost orders, payments, or mandatory audit records.

## 4. Delivery Tag and AMQP Channel: Foundations of Manual ACK

When RabbitMQ delivers a message, it attaches a **delivery tag**. That tag is used in acknowledgment operations on the **channel that received the delivery**.

**Critical rules:**

- Delivery tags are scoped **per AMQP channel**, not as global broker IDs.
- You must ACK/NACK on the **exact channel** that received the delivery.
- A delivery may only be settled validly once: ACK, NACK, or reject per protocol semantics.
- Never use delivery tags as **business eventIds**, correlation IDs across services, or tracking IDs across connection restarts.
- Once a channel disconnects, delivery tags from the old channel are no longer valid keys to settle on a new channel.

### 4.1. RabbitMQ Java Client-Level Commands

~~~java
import com.rabbitmq.client.Channel;

// tag: delivery tag on the channel that received the message
channel.basicAck(tag, false);          // Acknowledge one delivery
channel.basicReject(tag, false);       // Reject without requeue
channel.basicNack(tag, false, true);   // Reject one delivery, requeue
channel.basicNack(tag, false, false);  // Reject one delivery, no requeue
~~~

These illustrate **mutually exclusive decisions**. Never execute all four calls sequentially for the same delivery tag.

### 4.2. `basicAck(deliveryTag, multiple)`

**`basicAck(tag, false)`** confirms **one specific delivery**. **`basicAck(tag, true)`** confirms **multiple unacked deliveries whose tags are less than or equal to the supplied tag on the same channel**, per AMQP semantics.

**Never set `multiple=true` casually** in concurrent processing systems: deliveries with lower tags may not have finished business processing yet. Accidental batch ACKs can strip redelivery protection from unprocessed messages.

In our learning examples, always use **`multiple=false`** to avoid ACKing other messages by mistake.

### 4.3. `basicNack(deliveryTag, multiple, requeue)`

- **`multiple=false`:** NACK only the target delivery.
- **`multiple=true`:** batch-NACK unconfirmed deliveries within the tag/channel scope per AMQP rules.
- **`requeue=true`:** asks the broker to return the message to a redeliverable state.
- **`requeue=false`:** do not return to the original queue; the broker may dead-letter it if a DLX is configured, or drop it per policy.

**`basicReject(tag, requeue)`** rejects **a single delivery** and has no `multiple` flag. For rejecting one message, **`basicNack(tag, false, false)`** and **`basicReject(tag, false)`** are often used for similar goals, though you should not assume zero protocol or implementation differences exist.

### 4.4. ACK Matters Only If the Broker Receives It

Suppose the application calls **`basicAck`** after committing the DB, yet the connection drops right before the broker receives the ACK frame. The application cannot conclude "I called the method, so the broker definitely will not redeliver."

Therefore, even with manual ACK, consumers still need **idempotency** whenever a side effect must execute at most once per `eventId`.

## 5. Redelivery, Requeue, and Processing Order

A delivery can be redelivered by the broker when:

- Consumer NACKs/rejects with **`requeue=true`**.
- Connection/channel closes with unacked deliveries outstanding.
- Process is killed or the broker detects the consumer disconnected.
- A retry/republish mechanism puts an event with the same content back into the queue.

### 5.1. Requeue Does Not Mean "Wait a Few Seconds and Try Again"

**`basicNack(tag, false, true)`** requests returning the delivery to the queue per RabbitMQ semantics. While consumers remain active, the broker can redeliver **almost immediately**, possibly to the **same consumer** or another one. Never assume `requeue=true` provides delayed retry or exponential backoff.

~~~mermaid
flowchart TD
    Q["Queue"] --> C["Consumer"]
    C --> H{"Process"}
    H -- "Transient error" --> N["basicNack(requeue=true)"]
    N --> Q
    H -- "Success" --> A["basicAck"]
~~~

If the payload consistently fails schema validation, this requeue loop can spin continuously, creating a **poison message loop** that spikes CPU, network, and logs while delaying valid messages.

### 5.2. What Is the `redelivered` Flag Good For?

RabbitMQ can mark a delivery as **redelivered** to indicate the message may have been delivered previously. This is a helpful operational signal, yet:

- It is not a **business eventId**.
- It does not prove whether a prior delivery committed or not.
- It is not a sufficient criterion on its own to skip side effects.
- An event republished by the producer arrives as a new message whose `redelivered` flag differs from a broker requeue.

Deduplication must rely on a stable application-defined **eventId/idempotency key** paired with durable state storage.

### 5.3. Delivery Order Differs from Business Completion Order

Even when a queue generally stores messages in order, processing can diverge from publish order due to:

- Competing consumers.
- Large prefetch with concurrent callbacks/handlers.
- NACK/requeue pushing messages back.
- Retry queues, delayed retries, priorities, or offloading to ExecutorChannel.

If **OrderCreated** must be applied before **OrderCancelled** for the same `orderId`, enforce domain versions/sequence numbers or ordered partitioning mechanisms. **`Prefetch=1` does not guarantee global business ordering when multiple consumers are active.**

## 6. Prefetch Caps Unacknowledged Deliveries

RabbitMQ's **`basic.qos(prefetch)`** caps how many unacked deliveries can be pushed ahead under active QoS. In standard RabbitMQ configurations, prefetch applies **per consumer**, though global QoS settings or other limits must be checked if used.

Suppose:

~~~text
concurrentConsumers = 3
prefetchCount     = 10
~~~

With three active consumers, potentially in-flight unacked deliveries are roughly:

~~~text
3 consumers × 10 deliveries/consumer = 30 unacked deliveries
~~~

This is only an **estimated maximum window**, not throughput, business thread count, guaranteed available messages, or total messages in the queue.

| Value/Parameter | Effect | Considerations with MANUAL |
| --- | --- | --- |
| **Low `prefetchCount`** | Fewer pre-fetched messages per consumer | Improves fairness; may lower throughput if ACK/network RTT is noticeable |
| **High `prefetchCount`** | More unacked deliveries pushed ahead | Forgotten ACKs saturate quota quickly; raises memory and post-crash redeliveries |
| **`concurrentConsumers`** | Parallel active consumers in SMLC | Total in-flight scales by `N × P` |
| **`maxConcurrentConsumers`** | Upper scaling limit in SMLC | Actual consumer count still depends on triggers and load |
| **`consumersPerQueue`** | Per-queue consumer count in DMLC | Total calculation differs when one container watches multiple queues |

### 6.1. What Happens When ACK Is Forgotten?

With MANUAL, if a handler fails to ACK/NACK/reject, the broker keeps deliveries in **unacked** state. Once prefetch is reached, the broker may stop delivering more messages to that consumer even as **ready** messages pile up in the queue.

A classic signature:

~~~text
Queue ready   : rising
Queue unacked : near consumers × prefetch
Consumer ACK  : very low or 0
~~~

Inspect ACK code paths, exceptions before ACK, blocked threads, and connections/channels rather than raising prefetch to mask the issue.

### 6.2. Manual ACK Does Not Increase Processing Capacity on Its Own

If a handler takes **200 ms/message** with one sequential consumer, ideal throughput is around **5 messages/second**, ignoring overhead. Raising prefetch from 10 to 100 **does not make DB transactions 10x faster**; it only allows holding more deliveries ahead.

Increasing concurrency can help if the database and downstream systems have headroom, though it can also introduce lock contention or reorder events.

## 7. Classify Errors Before Designing Retries

No retry policy is safe without knowing **which errors are recoverable**.

| Error Type | Example | Typically Appropriate Policy |
| --- | --- | --- |
| **Permanent data error** | Malformed JSON, missing `orderId`, unsupported `schemaVersion` | Reject/quarantine; never requeue infinitely |
| **Business rule rejection** | Order ineligible per contract | Return business result or record rejected state; avoid repeating side effects |
| **Transient infrastructure** | DB connection timeout, HTTP 503, transient lock | Bounded retry with backoff/jitter |
| **Permanent infra/config** | Missing DB permissions, bad credentials, nonexistent resource | Alert and fix configuration; do not hot-retry |
| **Uncertain transaction outcome** | Network dropped near commit | Reconcile by business key; idempotent retry |
| **Already-processed message** | `eventId` already present in inbox | Do not repeat side effects; ACK after safe check |
| **ACK call failure** | Closed channel / `IOException` | May redeliver; do not emit another ACK/NACK on a new channel |

### 7.1. Retry Inside the Listener or Retry Through the Broker?

**In-listener retry (in-process):**

- Keeps the delivery unacked during retry attempts.
- Can use Spring Retry to bound attempts and backoff.
- Fits brief transient errors when keeping a worker busy briefly is acceptable.
- Not durable if the process crashes mid-retry; the broker may redeliver after connection close.

**Retry via broker or durable store:**

- After failure, move the message to a delayed/TTL retry queue or a durable outbox/inbox.
- Workers can resume processing after restarts.
- Requires topology, attempt caps, correlation/`eventId`, and failure handling if republishing fails.
- When **republishing** to a retry queue, ensure you do not **ACK the original before the retry copy is durably accepted**.

No single strategy fits every error category. Choose based on SLA, throughput, expected outage duration, and duplicate tolerance.

### 7.2. "Retry Until It Succeeds" Is Dangerous

A poison message can pin a consumer for a long time, grow the ready queue, trigger log storms, hammer downstream systems, and starve valid messages. Define:

- Maximum attempt count.
- Appropriate backoff, plus jitter across multiple instances.
- Overall time limit.
- Transition point to DLQ or an investigable error state.
- Controlled replay tooling rather than unbounded automatic loops.

## 8. Dead-Letter Exchanges and Queues Differ from NACK Requeue

When a consumer calls **`basicReject(tag, false)`** or **`basicNack(tag, false, false)`**, RabbitMQ can **dead-letter** the message if the queue has a dead-letter exchange configured. Without matching configuration and bindings, do not expect messages to appear automatically in a DLQ.

~~~mermaid
flowchart LR
    X["orders.events exchange"] --> Q["orders.created.q"]
    Q --> C["Consumer MANUAL ACK"]
    C -->|"ACK"| DONE["Delivery settled"]
    C -->|"NACK, requeue=true"| Q
    C -->|"Reject/NACK, requeue=false"| DLX["orders.dead.exchange"]
    DLX --> DLQ["orders.created.dlq"]
~~~

**DLX handles messages already inside a queue**, triggered by reject/NACK without requeue, TTL expiration, max queue length, or delivery limits depending on queue type and policy. **Publisher returns** happen when an exchange cannot route a publish; they do not place data into a consumer's DLQ.

### 8.1. `requeue=true` Does Not Send to DLQ

A **`basicNack(tag, false, true)`** call normally returns the delivery to be processed again, which is not equivalent to "move to DLQ." To quarantine after exhausting attempts, use **`requeue=false`** or a retry/delivery-limit mechanism with a defined termination condition and proper topology.

### 8.2. A DLQ Also Needs an Owner and Handling Process

A DLQ is not an "infinite safe trash bin." Define:

1. Who monitors alerts and triages messages in the DLQ?
2. Who is authorized to view sensitive payloads?
3. What retention, TTL, size caps, or policies apply to the DLQ?
4. Do repairs and replays preserve `eventId`, `schemaVersion`, and ordering?
5. Could replaying trigger duplicate side effects?
6. Can you tell whether a message landed in the DLQ due to bad data, exhausted retries, or queue policy?

### 8.3. Retrying with DLX/TTL Can Create Loops

An optional pattern dead-letters from the main queue to a TTL retry queue that dead-letters back to the main queue. Without an explicit **attempt cap** and sensible dead-letter routing, messages can cycle forever. Certain quorum queue configurations support delivery limits, though you should never assume every queue type shares the exact same behavior.

**Headers like `x-death` reflect broker dead-letter history**; they do not replace a durable business attempt counter if the system republishes and alters headers. Never trust producer-controlled fields blindly to decide how many retries occurred.

## 9. Spring Integration Example: Topology with DLX/DLQ

Let's build a concrete hands-on example:

~~~text
Main exchange   : orders.events
Routing key     : orders.created
Main queue      : orders.created.q          (durable)
Dead exchange   : orders.dead.exchange
Dead routing key: orders.failed
Dead queue      : orders.created.dlq        (durable)
Sample payload  : evt-1001|O-1001|150000

Consumer:
  SimpleMessageListenerContainer
  acknowledgeMode = MANUAL
  concurrentConsumers = 2
  maxConcurrentConsumers = 4
  prefetchCount = 8
  -> AMQP inbound channel adapter
  -> DirectChannel
  -> retry (3 attempts inside listener)
  -> business service
  -> ACK or reject without requeue
~~~

### 9.1. Dependencies

With Spring Boot dependency management supplying compatible versions:

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
    <dependency>
        <groupId>org.springframework.retry</groupId>
        <artifactId>spring-retry</artifactId>
    </dependency>
</dependencies>
~~~

**spring-retry** is needed for `RetryTemplate` in the example below. To run the database example with `JdbcTemplate`, the application also needs the JDBC starter, JDBC driver, and pre-created tables; the tutorial code does not create DB schemas automatically.

The application needs a test RabbitMQ broker and a ConnectionFactory configured with host/port/vhost and environment-appropriate credentials/TLS. Never put real passwords in source code.

### 9.2. Declaring Exchanges, Queues, and Bindings

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersManualAckTopology {

    public static final String EVENTS_EXCHANGE = "orders.events";
    public static final String ROUTING_KEY = "orders.created";
    public static final String QUEUE = "orders.created.q";

    public static final String DEAD_EXCHANGE = "orders.dead.exchange";
    public static final String DEAD_KEY = "orders.failed";
    public static final String DLQ = "orders.created.dlq";

    @Bean
    public DirectExchange ordersEventsExchange() {
        return new DirectExchange(EVENTS_EXCHANGE, true, false);
    }

    @Bean
    public Queue ordersCreatedQueue() {
        return QueueBuilder.durable(QUEUE)
            .deadLetterExchange(DEAD_EXCHANGE)
            .deadLetterRoutingKey(DEAD_KEY)
            .build();
    }

    @Bean
    public Binding ordersCreatedBinding(
            Queue ordersCreatedQueue,
            DirectExchange ordersEventsExchange) {
        return BindingBuilder.bind(ordersCreatedQueue)
            .to(ordersEventsExchange)
            .with(ROUTING_KEY);
    }

    @Bean
    public DirectExchange ordersDeadExchange() {
        return new DirectExchange(DEAD_EXCHANGE, true, false);
    }

    @Bean
    public Queue ordersCreatedDeadQueue() {
        return QueueBuilder.durable(DLQ).build();
    }

    @Bean
    public Binding ordersCreatedDeadBinding(
            Queue ordersCreatedDeadQueue,
            DirectExchange ordersDeadExchange) {
        return BindingBuilder.bind(ordersCreatedDeadQueue)
            .to(ordersDeadExchange)
            .with(DEAD_KEY);
    }
}
~~~

**Deployment note:** Beans only describe topology. RabbitAdmin/AmqpAdmin must be enabled with declaration permissions, or topology must be provisioned externally. If a queue with the same name already exists without DLX arguments or with incompatible attributes, RabbitMQ will reject redeclaration. For production, plan migrations or use RabbitMQ broker policies instead of casually altering arguments on a live queue.

### 9.3. Why Does the DLQ Need Its Own Binding?

**`basicReject(tag, false)`** only requests no requeue. RabbitMQ forwards the message to the dead-letter exchange configured on the **source queue**. The dead-letter exchange then needs a binding to route into **`orders.created.dlq`**.

Without the exchange, queue, and binding in place, **failed messages are not guaranteed to be retained**. Verify this independently from checking that Java code called `reject` successfully.

## 10. MANUAL Listener Container + Prefetch

For a message-driven **AMQP inbound channel adapter**, the Spring AMQP listener container manages consumers, concurrency, and acknowledgment. Example using **SimpleMessageListenerContainer (SMLC)**:

~~~java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.listener.SimpleMessageListenerContainer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersManualListenerConfiguration {

    @Bean("ordersManualContainer")
    public SimpleMessageListenerContainer ordersManualContainer(
            ConnectionFactory connectionFactory) {

        SimpleMessageListenerContainer container =
            new SimpleMessageListenerContainer(connectionFactory);

        container.setQueueNames(OrdersManualAckTopology.QUEUE);
        container.setConcurrentConsumers(2);
        container.setMaxConcurrentConsumers(4);
        container.setPrefetchCount(8);
        container.setAcknowledgeMode(AcknowledgeMode.MANUAL);

        // Fallback for listener errors not yet settled.
        // Does not replace the application's ACK/NACK decision.
        container.setDefaultRequeueRejected(false);

        return container;
    }
}
~~~

**Why `setDefaultRequeueRejected(false)`?** This acts as the container's fallback policy for errors the container handles via rejection; in MANUAL mode, the handler itself must still actively ACK/NACK deliveries it owns. **Do not assume this setter guarantees every exception goes to the DLQ**: inspect error handlers, exception types, whether channel/tag exist, and connection state.

**Illustrative in-flight count:** 2 consumers × prefetch 8 ≈ **16 unacked deliveries** that can be delivered ahead. If SMLC scales up to 4 consumers, the estimated window grows to **32**. That does not mean there are 32 parallel business workers or DB transactions.

### 10.1. SMLC and DMLC Are Two Distinct Options

**SimpleMessageListenerContainer** typically tunes concurrency via **`concurrentConsumers`/`maxConcurrentConsumers`**. **DirectMessageListenerContainer** uses **`consumersPerQueue`** and a different dispatch/thread model. Both support manual acknowledgment and prefetch, provided you apply the settings belonging to the chosen container.

Do not confuse **DirectMessageListenerContainer** with Spring Integration's **DirectChannel**: one is an AMQP container, the other is a synchronous internal channel.

### 10.2. Message-Driven Needs No Spring Integration Poller

RabbitMQ pushes deliveries to consumers registered by the listener container. The **AMQP inbound adapter** receives via message-driven mechanics; do not add **`Pollers.fixedDelay`** like a File/SFTP inbound adapter merely to throttle throughput. For AMQP, tune **prefetch, concurrency, ACK, handler latency, and backpressure**.

## 11. RetryTemplate: Retry Only Recoverable Errors

To avoid hammering NACK requeue during brief database outages, we configure **in-listener retries** of up to three attempts with short exponential backoff, retrying only **`TransientOrderProcessingException`**.

~~~java
public class InvalidOrderEventException extends RuntimeException {
    public InvalidOrderEventException(String message) {
        super(message);
    }

    public InvalidOrderEventException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

~~~java
public class TransientOrderProcessingException
        extends RuntimeException {

    public TransientOrderProcessingException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

### 11.1. Bounded Retry Configuration Bean

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.retry.support.RetryTemplate;
import org.springframework.retry.support.RetryTemplateBuilder;

@Configuration
public class OrdersRetryConfiguration {

    @Bean
    public RetryTemplate ordersRetryTemplate() {
        return new RetryTemplateBuilder()
            .maxAttempts(3)
            .exponentialBackoff(200L, 2.0, 1500L)
            .retryOn(TransientOrderProcessingException.class)
            .build();
    }
}
~~~

**`maxAttempts(3)`** normally means **the initial execution plus up to two retries**, not three retries on top of the first attempt. With this backoff, retries do not spin in a tight loop; however, the worker/listener still holds the delivery unacked while waiting.

**Configuration note:** Spring Retry APIs evolve across versions; the sample uses `RetryTemplateBuilder` on versions supporting this builder. For database failures, the service layer must translate recoverable exceptions into `TransientOrderProcessingException`; **never retry every `RuntimeException`**.

### 11.2. Where Does Retry Fit?

~~~mermaid
flowchart TD
    D["Delivery from broker"] --> P["Parse and validate"]
    P -->|"Invalid"| BAD["Reject requeue=false"]
    P -->|"Valid"| T["RetryTemplate"]
    T --> S["BusinessService<br/>DB transaction"]
    S -->|"Success"| A["basicAck"]
    S -->|"Transient failure"| R{"Retries left?"}
    R -->|"Yes"| WAIT["Backoff"] --> T
    R -->|"No"| DLQ["basicNack requeue=false"]
    S -->|"Non-retryable failure"| DLQ
~~~

In this example, **all three attempts occur on the same unacked delivery**. If the process dies after two attempts, `RetryTemplate`'s in-memory counter disappears; RabbitMQ can redeliver and the fresh processing pass gets up to three attempts again. Therefore **`maxAttempts(3)` is not a durable cap on total attempts for an event across all redeliveries**.

### 11.3. Should You Call `basicNack(requeue=true)` After Three Failures?

Without delayed retry, calling `NACK requeue=true` can cause the message to be redelivered immediately and restart another three attempts, forming an infinite loop at the broker level. Thus our baseline example **NACKs with `requeue=false` once attempts are exhausted** to route the message into a monitored DLQ.

In workflows tolerating prolonged transient outages, you can add a **delayed retry queue**, job scheduler, or durable inbox; be sure to bound total attempts and manage handoffs between queues.

## 12. Business Service and Transaction Boundary

We separate business processing from ACK calls for clear ownership:

- **OrderBusinessService** parses, validates, and runs the business transaction.
- **OrderManualAckHandler** chooses ACK/NACK/reject **after the business method returns**.
- The listener container and inbound adapter handle only delivery reception and message forwarding.

### 12.1. Illustrative Model and Parser

~~~java
public record OrderCreatedEvent(
        String eventId,
        String orderId,
        long totalVnd) {
}
~~~

~~~java
public final class OrderEventParser {

    private OrderEventParser() {}

    public static OrderCreatedEvent parse(String body) {
        if (body == null || body.length() > 1024) {
            throw new InvalidOrderEventException(
                "Payload missing or too large");
        }

        String[] fields = body.split("\\|", -1);
        if (fields.length != 3
                || !fields[0].matches("[A-Za-z0-9_-]{1,80}")
                || !fields[1].matches("[A-Za-z0-9_-]{1,80}")) {
            throw new InvalidOrderEventException(
                "Expected eventId|orderId|totalVnd");
        }

        long total;
        try {
            total = Long.parseLong(fields[2]);
        } catch (NumberFormatException ex) {
            throw new InvalidOrderEventException(
                "totalVnd is not a valid integer", ex);
        }

        if (total <= 0) {
            throw new InvalidOrderEventException(
                "totalVnd must be positive");
        }
        return new OrderCreatedEvent(
            fields[0], fields[1], total);
    }
}
~~~

This parser is strictly for the lesson. Production systems should use JSON/Avro/Protobuf with **`schemaVersion`** and validation, avoiding delimited strings unless characters are strictly constrained.

### 12.2. BusinessService with an Independent Transaction Boundary

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderBusinessService {

    private final WarehouseProjectionRepository repository;

    public OrderBusinessService(
            WarehouseProjectionRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void process(String body) {
        OrderCreatedEvent event = OrderEventParser.parse(body);

        // insertInboxIfAbsent MUST be protected by UNIQUE
        // on (consumerName, eventId) inside the same DB transaction.
        boolean firstTime = repository.insertInboxIfAbsent(
            "warehouse", event.eventId());

        if (!firstTime) {
            return; // Event was already processed previously.
        }

        repository.upsertOrderProjection(
            event.orderId(), event.totalVnd());
    }
}
~~~

~~~java
public interface WarehouseProjectionRepository {

    // Atomic insert; returns false on duplicate unique key.
    boolean insertInboxIfAbsent(
        String consumerName, String eventId);

    // Updates projection in the SAME database transaction.
    void upsertOrderProjection(
        String orderId, long totalVnd);
}
~~~

**The interfaces in this example are contracts you must implement**, not repositories automatically generated by Spring Data/JDBC just by naming them. In real applications, implement atomic insertion (e.g., unique constraint / `INSERT ... ON CONFLICT` per database), a transaction manager, database schema, and migrations.

**Key insight:** Because the inbox insert and projection update share one database transaction, rolling back on failure reverts both. Never use a non-atomic **`exists(eventId) → insert`** sequence lacking a unique constraint, because two concurrent consumers can race and both apply side effects.

### 12.3. Scope of `@Transactional`

**`OrderBusinessService.process()`** is invoked through a Spring bean/proxy from another handler bean so transaction advice applies as configured. **A database transaction does not automatically encompass RabbitMQ `basicAck`.**

Two failure windows must be accepted:

1. DB commits, ACK fails → broker may redeliver; the inbox makes reprocessing safe.
2. DB has not committed, app ACKs early → delivery may never be redelivered even though business logic did not finish. Therefore **ACK must happen only after the transactional method completes successfully**.

If the method calls an HTTP endpoint or external resource outside the DB transaction, design compensation/idempotency for that resource; `@Transactional` does not turn external systems into a distributed transaction.

### 12.4. Translating Transient Exceptions into the Retryable Type

This lesson's RetryTemplate only retries **`TransientOrderProcessingException`**. If the repository throws another exception type directly, classify it explicitly. For instance, inside **`process`** you can wrap the DB call:

~~~java
import org.springframework.dao.TransientDataAccessException;

// Illustrative snippet inside OrderBusinessService.process(...):
try {
    repository.upsertOrderProjection(
        event.orderId(), event.totalVnd());
} catch (TransientDataAccessException ex) {
    throw new TransientOrderProcessingException(
        "Temporary database failure", ex);
}
~~~

This **replaces** the corresponding repository call in Section 12.2 rather than calling **`upsertOrderProjection`** a second time. The transaction rolls back when the runtime exception escapes. Inspect exception translation in your driver/framework as well as transaction commit failures; do not assume every DB error belongs in the retryable group.

## 13. Manual ACK Handler: Process First, Confirm Afterward

A Spring Integration AMQP inbound adapter can expose AMQP delivery metadata via headers, typically including **`AmqpHeaders.CHANNEL`** and **`AmqpHeaders.DELIVERY_TAG`** when using manual acknowledgment mode and a supporting endpoint configuration.

**Version note:** Header names and availability depend on how the endpoint is constructed and the Spring AMQP/Spring Integration version. Before relying on this pattern, verify **`channel` and `deliveryTag` are actually present** on the Spring Message emitted by your running inbound adapter; if missing, never fabricate a new tag or ACK using a different connection/channel.

### 13.1. Service Owning Settlement

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.Map;

import com.rabbitmq.client.Channel;
import org.springframework.amqp.support.AmqpHeaders;
import org.springframework.retry.support.RetryTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderManualAckHandler {

    private final RetryTemplate ordersRetryTemplate;
    private final OrderBusinessService businessService;

    public OrderManualAckHandler(
            RetryTemplate ordersRetryTemplate,
            OrderBusinessService businessService) {
        this.ordersRetryTemplate = ordersRetryTemplate;
        this.businessService = businessService;
    }

    public void handle(
            String payload, Map<String, Object> headers) {

        Object rawChannel = headers.get(AmqpHeaders.CHANNEL);
        Object rawTag = headers.get(AmqpHeaders.DELIVERY_TAG);

        if (!(rawChannel instanceof Channel)
                || !(rawTag instanceof Number)) {
            throw new IllegalStateException(
                "MANUAL ACK requires channel and delivery tag headers");
        }

        Channel channel = (Channel) rawChannel;
        long deliveryTag = ((Number) rawTag).longValue();

        try {
            ordersRetryTemplate.execute(context -> {
                businessService.process(payload);
                return null;
            });
        } catch (InvalidOrderEventException ex) {
            // Permanent payload error: do not requeue.
            reject(channel, deliveryTag);
            return;
        } catch (RuntimeException ex) {
            // Retries exhausted, or a non-retryable technical error.
            // Route to DLQ according to the queue topology.
            nackWithoutRequeue(channel, deliveryTag);
            return;
        }

        // Called only AFTER businessService.process returned,
        // including completion of its database transaction.
        ack(channel, deliveryTag);
    }

    private void ack(Channel channel, long deliveryTag) {
        try {
            channel.basicAck(deliveryTag, false);
        } catch (IOException ex) {
            // Do not issue a second ACK/NACK on an unknown channel state.
            throw new UncheckedIOException("ACK failed", ex);
        }
    }

    private void reject(Channel channel, long deliveryTag) {
        try {
            channel.basicReject(deliveryTag, false);
        } catch (IOException ex) {
            throw new UncheckedIOException("Reject failed", ex);
        }
    }

    private void nackWithoutRequeue(
            Channel channel, long deliveryTag) {
        try {
            channel.basicNack(deliveryTag, false, false);
        } catch (IOException ex) {
            throw new UncheckedIOException("NACK failed", ex);
        }
    }
}
~~~

**Branch analysis:**

1. **`businessService.process` succeeds:** transactional method completes, then **`basicAck(tag, false)`**.
2. **`InvalidOrderEventException`:** invalid data, **`basicReject(tag, false)`**; if DLX/DLQ are properly configured, the message is dead-lettered.
3. **`TransientOrderProcessingException`:** RetryTemplate tries up to three attempts; if all fail, **`basicNack(tag, false, false)`** isolates it.
4. **Other `RuntimeException`:** not retried by the sample policy; NACK without requeue avoids a hot loop. Real systems should expand error classification rather than sending every unexpected failure straight to the DLQ.
5. **`IOException` during ACK/NACK/reject:** handler propagates the failure to the container and **does not send another settlement** for the same tag. Broker state is uncertain; expect possible redelivery and rely on idempotency.

**Do not wrap ACK/NACK and all processing inside one `try/catch` that NACKs on any caught error.** If `basicAck` already ran and a later failure triggers a NACK on the same delivery tag, RabbitMQ raises a protocol error and closes the channel for double acknowledgment.

### 13.2. How Should This Example Handle Missing Headers?

Missing **`AmqpHeaders.CHANNEL`** or **`DELIVERY_TAG`** is an **integration-boundary configuration error**, not a business error fixable by retries. The sample fails fast before running business logic. Check:

- Whether `AcknowledgeMode.MANUAL` is actually applied on the running container.
- Adapter/header mapper versions, filtered headers, or transformers stripping metadata.
- The listener's error handler when failures occur **before settlement is possible**.
- Halt deployment if no valid ACK/NACK path exists; never let the system commit DB changes when it cannot acknowledge deliveries.

Never fabricate a fresh channel and synthetic delivery tag just to pass validation.

### 13.3. Never Send Channel/Tag to External Systems

An **AMQP Channel** is a client resource bound to a connection, thread, and delivery lifecycle. Do not:

- Serialize `Channel` into JSON.
- Save `Channel` or `deliveryTag` into a database to ACK after restart.
- Pass them to Kafka/HTTP/SFTP as business headers.
- Store `Channel` in a singleton field to ACK multiple deliveries.

To track state across prolonged asynchronous workflows, use **`eventId`/`jobId` and durable state storage**, not channel/tag as long-lived business references.

## 14. Wiring the Handler into an AMQP Inbound IntegrationFlow

We connect the **`ordersManualContainer`** from Section 10 to Spring Integration: inbound adapter → DirectChannel → manual ACK handler.

### 14.1. Spring Integration Java DSL

~~~java
import org.springframework.amqp.rabbit.listener.SimpleMessageListenerContainer;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.amqp.dsl.Amqp;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class OrdersManualAckIntegrationConfiguration {

    @Bean
    public MessageChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow ordersInboundFlow(
            @Qualifier("ordersManualContainer")
            SimpleMessageListenerContainer container,
            OrderManualAckHandler manualAckHandler) {

        return IntegrationFlow
            .from(Amqp.inboundAdapter(container))
            .channel("ordersInput")
            .handle(String.class, (payload, headers) -> {
                manualAckHandler.handle(payload, headers);
                return null;
            })
            .get();
    }
}
~~~

**These configuration classes are separate Java files**; they illustrate the overall architecture rather than requiring everything in one file. Producer and consumer can be deployed in separate applications; the lesson places them together for ease of observation.

### 14.2. Why Use DirectChannel?

With **DirectChannel**, the service activator runs inside the listener's synchronous call chain:

~~~mermaid
sequenceDiagram
    participant Q as RabbitMQ queue
    participant L as SMLC MANUAL
    participant A as AMQP inbound adapter
    participant C as DirectChannel
    participant H as OrderManualAckHandler
    participant DB as Warehouse DB
    Q->>L: Delivery + tag + channel
    L->>A: Listener callback
    A->>C: Spring Message
    C->>H: handle(payload, headers)
    H->>DB: Business transaction
    DB-->>H: Commit success
    H-->>Q: basicAck(tag, false)
    H-->>C: Handler returns
    C-->>A: Flow completes
~~~

The flow does not automatically ACK at `MessageChannel.send()`; the handler explicitly ACKs after the transactional service finishes. However, if the processor invokes an external system asynchronously inside and returns before the external work finishes, **ACK can still occur before real business completion**. Success boundaries must match the actual contract.

### 14.3. What If the Adapter Emits a Non-String Payload?

The example assumes the inbound adapter's AMQP converter turns **`text/plain`** messages into **`String`**. If the producer sends JSON/binary, the inbound converter may emit **`byte[]`** or a DTO, and a handler expecting `String` will no longer match the contract.

Test **body/properties**, `contentType`, `charset`, converters, and whether **`AmqpHeaders.CHANNEL`/`DELIVERY_TAG`** survive any transformers ahead of the handler. Never alter schemas or header mappers casually while live traffic flows.

### 14.4. When to Use `@RabbitListener` Instead of an Inbound Adapter?

If an application only needs a lightweight RabbitMQ consumer without MessageChannels or IntegrationFlows, Spring AMQP's **`@RabbitListener`** can also perform MANUAL ACK with `Channel` and `deliveryTag`. When you need to connect to routers, filters, transformers, service activators, or other adapters, the **AMQP inbound channel adapter** brings the data cleanly into Spring Integration architecture.

Do not register **both `@RabbitListener` and an inbound adapter** on the same queue during a test if you want every test message delivered exclusively to the flow under test; those two consumers will compete for deliveries.

## 15. ErrorChannel, Converters, and Listener Error Handlers

Errors inside Spring Integration and errors in the Spring AMQP listener container sit at different layers:

| Error Boundary | Example | Typically Handles It |
| --- | --- | --- |
| **AMQP delivery / MessageConverter** | Malformed JSON, wrong `contentType`, disallowed object type | Spring AMQP converter + listener error handler |
| **Spring Integration transformer/filter** | Wrong `schemaVersion`, missing header | IntegrationFlow / `errorChannel` if configured |
| **Service activator** | DB timeout, business validation | Business service, `RetryTemplate`/advice, error flow |
| **Manual settlement** | Closed channel, `basicAck` `IOException` | RabbitMQ channel/connection and listener container |
| **Dead-letter routing** | Missing DLQ or binding | RabbitMQ topology, broker logs/management |

### 15.1. Errors Occurring Before `OrderManualAckHandler`

If **`MessageConverter`** fails to build a Spring Message from the AMQP body, code inside **`OrderManualAckHandler`** may never run; consequently the handler cannot use `channel`/`tag` to reject the delivery. Configure and test a **Spring AMQP listener error handler** and exception classification for conversion errors.

Some Spring AMQP versions recognize certain conversion failures as **fatal** and reject without requeue under default error handlers. Yet never assume every MANUAL configuration or every exception automatically lands in a DLQ; it depends on **acknowledge mode, error handler, listener container, queue topology, and exception type**.

### 15.2. Errors Swallowed by `errorChannel`

If an IntegrationFlow routes exceptions to an **ErrorMessage** on `errorChannel` and the error flow completes normally, the container may not see an exception the way it would when the handler throws directly.

- With **AUTO**, the listener may look successful and the container ACKs per policy.
- With **MANUAL**, if settlement code does not run or the error flow fails to settle the delivery, it can **hang unacked**.
- If the error flow ACKs and another branch also ACKs, it causes a **double ACK**.

Thus, under manual ACK, assign **one final settlement owner** per delivery and test every error branch. Never simply log an exception and return without knowing whether ACK/NACK occurred.

### 15.3. Do Not Turn Arbitrary Runtime Exceptions into `requeue=true`

Specialized Spring AMQP exceptions can influence requeue/reject behavior in certain setups. However, **MANUAL ACK** is an application-controlled settlement model; never assume throwing an exception from a Spring Integration handler automatically triggers the desired `basicNack`.

To retry via classifiers, trace the exact path:

~~~text
AMQP delivery
  -> converter
  -> Spring Message
  -> transformer
  -> service activator
  -> RetryTemplate
  -> MANUAL ACK/NACK
~~~

For errors **before** or **after** the handler owning settlement, configure dedicated handling at the container or topology level.

## 16. Asynchronous Processing and Premature ACKs

In Spring Integration, switching from DirectChannel to **ExecutorChannel** or **QueueChannel** can alter when the listener callback returns.

### 16.1. Risk with AUTO ACK

~~~mermaid
sequenceDiagram
    participant B as RabbitMQ
    participant L as Listener AUTO
    participant E as ExecutorChannel
    participant H as Async worker
    L->>E: Send Spring Message
    E-->>L: Executor accepts task
    L-->>B: ACK on callback completion
    E->>H: Executes business logic later
    H--xH: Database error
    Note over B,H: Broker may have ACKed before business failure
~~~

With an asynchronous channel, the caller may only know that the executor accepted the task. If ACK happens before side effects finish, RabbitMQ can no longer redeliver that delivery upon downstream failure.

### 16.2. MANUAL ACK Can Help, Provided Channel Ownership Is Controlled

Manual ACK **can** defer confirmation until async work finishes, yet you cannot casually hand **`com.rabbitmq.client.Channel`** and `deliveryTag` off to an arbitrary thread:

- Channels tie to connection/consumer lifecycles; connections may close while tasks are still running.
- Channels/consumers are not meant for arbitrary concurrent use across threads.
- **`multiple=true`** ACKs can accidentally settle other pending deliveries.
- Out-of-order ACKs can occur; some container versions offer specific async-ACK features that must be configured and tested against that version's docs.
- If the executor queue fills, tasks are rejected, or shutdown starts, messages still need a settlement/recovery policy.

A safer approach in many cases is **keeping the handler synchronous until DB commit** and then ACKing, while scaling consumer count within downstream limits. If asynchronous execution is mandatory, consider **persisting durably to an inbox/job table before ACK**, letting background workers read jobs and process idempotently.

### 16.3. Persist Before ACK: The Inbox Pattern

~~~mermaid
flowchart LR
    MQ["RabbitMQ delivery"] --> IA["AMQP inbound adapter"]
    IA --> DB["DB transaction:<br/>insert inbox eventId + body"]
    DB --> ACK["basicAck after commit"]
    DB --> W["Async inbox worker"]
    W --> H["Business processing"]
    H --> DONE["Update job status"]
~~~

In this model, ACK means **the event was durably saved to the inbox**, not that business processing finished. SLAs must reflect that meaning clearly. Internal workers need retries, concurrency limits, error states, and idempotency protection. **An in-memory `QueueChannel` does not replace a durable inbox.**

### 16.4. Do Not Use "Async" to Hide Upstream Errors

If an HTTP inbound gateway hands work to an ExecutorChannel and immediately returns HTTP 200 while downstream AMQP consumers or DB workers have not processed it yet, the HTTP response must not imply completion. Return **`202 Accepted` + `jobId`** with a status endpoint when the contract permits.

## 17. Delayed Retry and Restart Recoverability

The example's `RetryTemplate` suits brief transient errors. When targets can stay down for minutes, keeping listener threads sleeping on backoff wastes resources. You need a **durable retry** model.

### 17.1. Retry Queue with TTL/DLX

A common topology:

~~~mermaid
flowchart TD
    MQ["orders.created.q"] --> C["Consumer"]
    C -->|"Success"| A["ACK"]
    C -->|"Retry later"| RX["Retry exchange"]
    RX --> RQ["Retry queue<br/>controlled TTL"]
    RQ -->|"TTL expired / DLX"| EX["orders.events"]
    EX --> MQ
    C -->|"Retries exhausted / invalid data"| D["Final DLQ"]
~~~

You can configure the main queue to dead-letter into a retry queue that dead-letters back to the main queue, or have the consumer **republish** messages to a retry exchange. These differ in how well they control **attempt counts**, delays, and when the original delivery is ACKed.

### 17.2. Do Not ACK the Original Before Safely Persisting the Retry

If a consumer republishes to a retry exchange and **ACKs the original before the broker confirms the new copy**, events can be lost if the new publish fails.

A safer workflow:

1. Maintain a stable business `eventId`.
2. Record retry intent in durable storage or publish to the retry exchange with proper confirms/returns.
3. ACK the original delivery only after the new handoff milestone succeeds.
4. If republish outcome is **`UNKNOWN`**, never assume it was not sent.
5. Tolerate **two copies with the same `eventId`**, relying on idempotent consumers to guard side effects.

**It is not trivial to create an atomic transaction spanning original delivery ACK and publishing a new message**, even when both use RabbitMQ. Strict guarantees require analyzing broker transactions/confirms and durable checkpoints rather than adding two API calls.

### 17.3. Bounded Attempts Across Multiple Redeliveries

**`RetryTemplate.maxAttempts(3)`** only bounds one in-process execution pass. After a crash or connection reset, the broker can redeliver and start another three-attempt pass.

To bound total executions per `eventId`:

- Persist a **durable attempt counter** in an inbox/job table or state store.
- Or rely on a supported broker policy, such as **delivery limit** on applicable queue types, verified for your version and setup.
- Never rely solely on an in-memory Java counter.
- If using **`x-death`**, check how the broker updates it and how republishing/headers affect values; never rely on producer-modifiable headers for retry enforcement.

### 17.4. When Retries Fail Repeatedly

Route messages to a **final DLQ or durable error state** with an owner and triage process. A retry queue without a stop condition can spin for hours or days, burning resources without fixing the root cause.

## 18. Idempotency and the Limits of "Exactly Once"

Manual ACK governs **when to tell the broker a delivery was handled under the consumer contract**. It does not guarantee every business side effect executes only once.

### 18.1. Two Fundamental Crash Windows

~~~text
Case A:
  Message received
  -> ACK
  -> process crashes
  -> DB not committed
  => Risk of losing business side effect

Case B:
  Message received
  -> DB commits
  -> process crashes before ACK
  -> broker redelivery
  => Risk of duplicating business side effect
~~~

Choose **DB commit then ACK** to prevent Case A, and use an **idempotent consumer** to handle Case B.

### 18.2. Inbox with Unique Constraint

~~~text
processed_events
  consumer_name   VARCHAR
  event_id        VARCHAR
  processed_at    TIMESTAMP

UNIQUE(consumer_name, event_id)
~~~

During processing:

1. Parse/validate `eventId`.
2. Inside the database transaction, **insert if absent** backed by the unique constraint.
3. On a valid duplicate, skip repeating side effects.
4. When new, apply business logic and commit together with the processed marker.
5. Only after the transactional method succeeds, send ACK.

If `eventId` matches yet the payload differs, enforce a **collision/conflict** policy rather than silently treating every duplicate ID as valid. Store a payload checksum or source identifier in the inbox if required.

### 18.3. When Side Effects Span External Systems

If the consumer calls an external ordering HTTP API, payment gateway, or emits to JMS/Kafka outside the DB transaction, a local unique constraint alone cannot stop external duplicates. You need:

- To pass an **idempotency key** to the external API if supported.
- Durable request/response state tracking inside your workflow.
- Reconciliation when timeouts happen near external commits.
- Compensating actions where the contract allows.

Never claim end-to-end exactly-once solely because MANUAL ACK or a durable queue is enabled.

## 19. Listener Lifecycle, Shutdown, and Permissions

Spring AMQP listener containers and Spring Integration endpoints participate in **Lifecycle/SmartLifecycle**: `start`, `stop`, `autoStartup`, and `phase` per configuration. ConnectionFactory manages connections/channels shared with RabbitTemplate and other listeners.

### 19.1. Shutdown Order Affects ACK

Suppose a handler is mid-transaction when shutdown starts:

1. Stop accepting new work per application/listener container controls.
2. Give handlers with active deliveries a bounded window to finish.
3. If the transaction commits and the channel remains open, ACK the right tag.
4. If the channel/connection closed, do not try to ACK on a new channel; let the broker recover unsettled deliveries per policy.
5. On restart, consumers reprocess unsettled events while inbox/idempotency blocks duplicate side effects.

**`stop()` does not mean every unacked delivery was ACKed.** Shutdown timeouts, container semantics, and connection state determine what happens to in-flight deliveries.

### 19.2. Manual ACK with Multiple Consumers

When SMLC runs multiple consumers on the same queue, each consumer receives deliveries on its own channel. **Tag 1** on channel A is not the same delivery as **tag 1** on channel B.

Never store `Channel` and `deliveryTag` in a shared singleton `"lastDelivery"` field across handlers. Read metadata from the **exact Spring Message** of the current delivery, and settle using its exact channel/tag without accidentally sweeping other deliveries via `multiple=true`.

### 19.3. Thread Model and AMQP Channel Safety

The RabbitMQ Java client `Channel` should not be treated as a thread-safe data object to pass arbitrarily across tasks. If using async ACK models, check async/out-of-order ACK features supported by your Spring AMQP version and minimize thread handoffs.

A simple, easily verifiable approach is a **synchronous handler on DirectChannel** with one clear settlement point. For long-running work, a **durable inbox** pattern is usually better than keeping an AMQP channel open for minutes.

### 19.4. Security and RabbitMQ Permissions

- Consumers need **read** permission on their queues and relevant broker/vhost rights.
- Use an account with configure permission for declaring exchanges/queues/bindings if the app manages topology; do not over-privilege accounts.
- Enable TLS and certificate verification where required; load credentials from a secret manager or environment variables.
- Never log full payloads, sensitive headers, or RabbitMQ connection URIs containing passwords.
- DLQs can also hold personal or sensitive business data; apply proper read ACLs, retention, and deletion workflows.

### 19.5. Difference Between MANUAL ACK and Producer Confirm in Operations

If a flow bridges both an AMQP inbound adapter and an outbound adapter:

~~~text
RabbitMQ queue A
  -> consumer MANUAL ACK
  -> transform
  -> AMQP outbound adapter
  -> RabbitMQ queue B
~~~

You cannot claim that once **`MessageChannel.send` to the outbound adapter succeeds**, queue B has received a publisher confirm/return. If consumer A **ACKs before the publish to B is confirmed**, messages can be lost between the two queues.

For critical bridges, define a durable checkpoint/transaction between source and destination, or use outbox/inbox plus producer confirms for recoverability. **MANUAL ACK on queue A does not replace publisher confirms for publishing to queue B.**

## 20. Observability and Incident Investigation

Manual ACK is only trustworthy when you know how many deliveries are pending, settled, and failing unhandled.

| Layer | Metrics to Monitor | Abnormalities May Indicate |
| --- | --- | --- |
| **RabbitMQ queue** | ready, unacked, total, message age | Backlog or deliveries held too long |
| **RabbitMQ consumer** | consumer count, delivery rate, ACK/NACK/reject/requeue rate | Whether listeners run or hit poison loops |
| **Spring AMQP container** | Active consumer count, reconnects, listener exceptions, shutdown | Connection or error-handler issues |
| **Spring Integration flow** | Input count, handler latency/errors, `errorChannel` | Failures before or after service activator |
| **Retry** | attempts, exhausted count, backoff duration | Transient downstream outage vs. permanent failures |
| **DLQ** | Entry count, oldest age, error category | Unprocessable messages and triage backlog |
| **Database** | Transaction latency, rollbacks, unique violations | Bottlenecks or idempotency contention |
| **Business** | Unique `eventId` processed, duplicates ignored, business success | Whether ACKs match real business completion |

### 20.1. Common Diagnostic Patterns

**Ready rising, Unacked near `consumers × prefetch`, low ACK rate:** likely slow handler, in-listener retries holding deliveries, or forgotten ACKs. Do not reflexively raise prefetch; inspect what workers are doing.

**Unacked near 0, high ACK rate, low business success:** likely ACKing before side effects, `errorFlow` swallowing exceptions, or miscounted business metrics. Reconcile database transactions against settlement timing.

**Requeue/redelivery spiking rapidly:** suspect infinite `basicNack(requeue=true)` loops, missing backoff, or permanently failing downstream dependencies.

**DLQ spiking after deploy:** check JSON schema/version, converters, `eventType`, DB permissions, and topology changes—do not just add consumers.

**Consumer count drops to 0 while ready stays non-zero:** listener stopped, RabbitMQ connection/credentials failed, or container stuck reconnecting.

**Duplicate `eventId` spikes after restart:** redelivery or producer retries can be normal; ensure **duplicate business side effects** remain zero.

### 20.2. Safe Logging and Tracing

Useful metadata example:

~~~text
consumer=warehouse
eventId=evt-1001
queue=orders.created.q
deliveryTag=42
redelivered=true
retryAttempt=3
outcome=REJECT_TO_DLQ
errorCategory=TRANSIENT_EXHAUSTED
processingMillis=1850
~~~

**`deliveryTag=42`** only has meaning within that channel at delivery time; logging it helps debugging, but never store tags as persistent business keys. Never dump `Channel` objects, credentials, tokens, or sensitive payloads.

### 20.3. SLA Alerting

Alert when:

- Message age exceeds allowed processing windows.
- Ready/unacked counts breach benchmarked load thresholds.
- Exhausted retries or DLQ ingress spike unexpectedly.
- Consumer count stays at 0 longer than recovery thresholds.
- p95/p99 processing latency or DB rollbacks rise.
- ACKs stall despite high delivery rates.

Base thresholds on real workloads and SLAs rather than copying sample numbers from a lesson into production.

## 21. MANUAL ACK and Retry Test Matrix

Test against **real RabbitMQ in an isolated environment** (such as a dedicated test broker or Testcontainers), not merely by mocking `OrderManualAckHandler`.

| Scenario | Test Action | What to Verify |
| --- | --- | --- |
| **Success** | Send valid event, DB healthy | Transaction commits, ACK sent once, message leaves unacked |
| **Duplicate `eventId`** | Resend same `eventId` | No duplicate side effect; delivery ACKed cleanly |
| **Malformed payload** | Send String violating contract | Rejected without requeue; lands in DLQ when topology matches |
| **Unsupported schema** | Send new version unknown to consumer | No hot retry; logged/quarantined per policy |
| **DB fails once, succeeds second time** | Mock/stub transient exception once | Bounded retry, eventually ACKs |
| **DB continuously fails transiently** | Fail all attempts | After 3 attempts, NACK `requeue=false`, lands in DLQ |
| **Non-retryable technical error** | Throw non-retryable exception | No infinite retry; takes appropriate error path |
| **Forgotten ACK** | Test handler that skips settlement | Unacked saturates prefetch quota; ready queue can grow |
| **Double ACK** | Intentionally settle same tag twice on isolated broker | Channel/protocol error caught; no accidental `multiple` misuse |
| **Wrong channel/tag** | Intentionally ACK on another channel | Delivery tag/channel error detected, never treated as success |
| **`basicAck` `IOException`** | Drop connection near ACK | Redelivery possible; idempotency guards side effects |
| **Crash after DB commit** | Kill consumer before ACK | Delivery can redeliver; no duplicate side effects |
| **Crash before DB commit** | Kill consumer mid-transaction | Rolls back and reprocesses cleanly |
| **Converter error before handler** | Send malformed JSON | Container error handler processes cleanly without hanging unacked |
| **`errorChannel` absorbs error** | Flow catches exception without settling | Test catches missing ACK/NACK |
| **`ExecutorChannel`** | Offload work to another thread in test | Verify no premature ACK, or replace with durable inbox |
| **DLX missing binding** | Reject bad message on test broker | Topology gap detected instead of silently dropping failed message |
| **`NACK requeue=true`** | Force handler failures in short test | Observe hot redelivery proving need for bounded retries |
| **Prefetch = 1 vs. 16** | Slow handler, multiple consumers | Measure unacked, fairness, throughput, latency |
| **Graceful shutdown** | Stop app with unacked deliveries | No lost side effects; recovers per policy |
| **Multiple instances** | Run two JVMs on same queue | Competing consumers sharing inbox/unique key deduplication |

### 21.1. Unit Testing the Business Handler Is Not Enough

A unit test can mock **`Channel`** to assert:

~~~text
success         -> basicAck(tag, false)
invalid         -> basicReject(tag, false)
exhausted       -> basicNack(tag, false, false)
ack IOException -> exception propagated, no second settlement
~~~

Yet mocks do not prove:

- Listener container actually runs in MANUAL mode.
- `AmqpHeaders.CHANNEL` and `DELIVERY_TAG` are preserved by mappers.
- DLX/DLQ exist and the broker routes rejected messages there.
- Broker redelivers after connection close.
- Transaction actually commits before ACK.

Therefore, write **integration tests** against real RabbitMQ and a test database enforcing unique constraints.

### 21.2. Test Message Publishing

With RabbitTemplate and the example topology:

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;

public class OrdersTestPublisher {

    private final RabbitTemplate rabbitTemplate;

    public OrdersTestPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void sendValid() {
        rabbitTemplate.convertAndSend(
            OrdersManualAckTopology.EVENTS_EXCHANGE,
            OrdersManualAckTopology.ROUTING_KEY,
            "evt-1001|O-1001|150000");
    }

    public void sendMalformed() {
        rabbitTemplate.convertAndSend(
            OrdersManualAckTopology.EVENTS_EXCHANGE,
            OrdersManualAckTopology.ROUTING_KEY,
            "not-a-valid-event");
    }
}
~~~

**Warning:** These two methods are only for producing test messages. Use a dedicated test queue or virtual host; never push malformed messages to a production queue. When listeners are running, messages may be consumed immediately, so **a queue depth of 0 does not prove publishing failed**.

### 21.3. Testing the Exact Transaction Boundary

An important test uses a **fake repository/test DB** to exercise these exact points:

~~~mermaid
sequenceDiagram
    participant B as RabbitMQ
    participant L as Listener
    participant S as Business Service
    participant DB as Test DB
    B->>L: Delivery evt-1001
    L->>S: process(evt-1001)
    S->>DB: Insert inbox + update projection
    DB-->>S: Commit
    S-->>L: Return success
    L-->>B: basicAck
    Note over B,DB: Kill before ACK to test redelivery
~~~

When killed after commit but before ACK, a new consumer receives **`evt-1001`** again, hits the inbox check, and ACKs without updating the projection a second time. That is a meaningful idempotency test—far stronger than checking method call counts in a single process.

### 21.4. Testing Retry Counts

Configure the database stub so that:

- Attempt 1 throws `TransientOrderProcessingException`.
- Attempt 2 succeeds.
- Verify the handler calls ACK **once** after attempt 2, never after attempt 1.

In another test, have the database always throw the transient exception:

- Verify a total of **three attempts within the local retry loop**.
- Zero ACKs on failed attempts.
- Finally one NACK with `requeue=false`.
- Broker stores the message in the DLQ when topology is declared properly.

Do not confuse broker delivery counts with `RetryTemplate` attempt counts: one delivery can be attempted multiple times inside the listener before NACK/ACK.

## 22. When Should You Choose MANUAL Instead of AUTO?

**MANUAL ACK** is valuable when you need exact control over confirming deliveries after a processing or durable persistence milestone, or a structured settlement workflow. However, it adds responsibility for channel/tag handling, exceptions, thread models, and operations.

| Situation | Option to Consider | Reason |
| --- | --- | --- |
| Synchronous handler, clean exception propagation, no custom ACK point | **AUTO** with tested retry/error policy | Lower risk of missed/double ACKs; container owns settlement |
| Must explicitly decide ACK after DB commit and classify per message | **MANUAL** with a single settlement owner | Explicit choice among ACK/reject/NACK |
| Ultra-fast, best-effort work tolerating lost deliveries | **NONE** only when contract permits | No redelivery guarantee on processing crash |
| Long async handler needing restart recovery | **Durable inbox/job + ACK after durable save** | Avoids holding channels/tags open across long tasks |
| Critical RabbitMQ A → RabbitMQ B bridge | **Publisher confirms + durable state + controlled source ACK** | Never treat source ACK as target broker confirmation |
| Infrastructure outages lasting minutes/hours | **Durable delayed retry** | Avoids sleeping listener threads inside retries |
| Must apply side effect once per `eventId` | **Idempotent consumer + transaction** | Manual ACK alone does not guarantee exactly-once |

### 22.1. Recommended ACK Placement

For a consumer updating a single database, a clean, defensible sequence is:

~~~text
Receive delivery
  -> validate
  -> begin DB transaction
  -> atomic inbox uniqueness + business change
  -> DB commit
  -> basicAck(tag, false)
~~~

For a consumer handing work off to an async worker:

~~~text
Receive delivery
  -> validate
  -> begin DB transaction
  -> save durable inbox/job
  -> DB commit
  -> basicAck(tag, false)
  -> background worker later handles job
~~~

Both patterns are valid, yet **the meaning of ACK differs**. The second pattern ACKs **durable storage for later processing**, not **completed business processing**. Document that clearly in designs and SLAs.

## 23. Common Mistakes

**"Manual ACK guarantees exactly-once."** False. If DB commits and ACK is lost, the message can still redeliver. You still need **stable `eventId`, unique constraint/inbox, and transactions**.

**"You can ACK before calling the DB and retry if the DB fails."** Once the broker accepts an ACK, it stops tracking that delivery for automatic redelivery. Without durable alternate retry storage, work can be lost.

**"`basicAck(tag, true)` confirms only one message."** `multiple=true` can ACK **multiple unconfirmed deliveries** on the same channel. With concurrent in-flight messages, misusing it settles unprocessed deliveries early.

**"Delivery tag is a global ID."** Tags are scoped strictly to their channel. Never ACK a channel A delivery on channel B, or persist tags for use after reconnect.

**"Calling `basicAck` successfully guarantees the broker processed the ACK."** If the connection drops near frame transmission, status may be uncertain; consumers must handle redelivery.

**"`basicNack(requeue=true)` includes exponential backoff automatically."** Requeue can happen immediately. For permanently invalid data, it creates an endless hot loop.

**"`basicNack(requeue=false)` guarantees landing in a DLQ."** You need working DLX, DLQ, and bindings; without matching topology/policy, messages may not be retained.

**"A DLQ fixes messages automatically."** A DLQ only isolates/holds messages per policy; you still need owners, retention limits, and safe repair/replay tools.

**"Spring Retry `maxAttempts=3` means the event only runs three times in its entire lifetime."** `RetryTemplate` bounds one in-process pass; broker redelivery or post-restart republishing starts a new pass. Total bounds require durable state or supported broker policies.

**"Every `RuntimeException` should be retried."** Schema, permission, configuration, and business validation errors do not self-heal. Retry only genuinely recoverable error classes.

**"MANUAL is AUTO where you also call `basicAck` to be extra safe."** Both modes have distinct settlement owners. Never manually ACK a delivery managed by AUTO.

**"Putting ACK in `finally` is always safe."** `finally` still runs on DB rollbacks or handler failures, destroying broker redelivery protection.

**"If a handler throws, it definitely goes to `errorChannel` and then DLQ."** Converter errors can happen before Spring Messages exist; `errorChannel` can swallow errors; reject/NACK paths depend on container and topology.

**"DirectMessageListenerContainer is DirectChannel."** One is an AMQP listener container; the other is a synchronous Spring Integration channel.

**"`ExecutorChannel` is always safe for MANUAL consumers."** Passing channels/tags across threads risks closed connections, out-of-order ACKs, and lost work in non-durable internal queues.

**"An in-memory `QueueChannel` is a durable inbox."** Default `QueueChannel` lacks database inbox durability; crashes lose work already ACKed at the broker.

**"Prefetch=100 means 100 parallel business executions."** Prefetch caps unacked deliveries, not workers. It can simply bloat unacked counts and memory.

**"Prefetch=1 guarantees strict ordering and zero duplicates."** Multiple consumers, crashes, requeues, and producer retries still exist. Ordering and deduplication need domain controls.

**"Adding `@Transactional` makes ACK and DB commit atomic."** `@Transactional` manages specific resource transactions; RabbitMQ ACK does not automatically join that transaction.

**"After NACKing, the handler can call ACK to change its mind."** A delivery cannot be settled twice; treat settlement decisions as final for that tag.

**"Multiple consumers on one queue all receive every event."** They normally compete for deliveries. If two services both need the same events, use separate queues and bindings.

**"Publisher confirm replaces consumer ACK."** Confirm belongs to producer/broker; consumer ACK settles post-delivery. A RabbitMQ A → B bridge must distinguish source confirmation from target confirmation.

**"`redelivered=true` means business logic already ran once."** It is not proof of a committed transaction, only a delivery hint.

**"Storing the delivery tag in the database allows ACKing after app restart."** Old channels/tags become invalid across connection restarts; store **`eventId` and business state**, not tags as durable references.

## 24. Self-Check Questions

1. What control does manual acknowledgment give the application that AUTO ACK typically delegates to the container?
2. In Spring AMQP, does AUTO mean the broker ACKs as soon as the message is delivered?
3. What is the identifier scope of a delivery tag? Why not use it as `eventId`?
4. What is the difference between **`basicAck(tag, false)`** and **`basicAck(tag, true)`**?
5. When are **`basicReject(tag, false)`** and **`basicNack(tag, false, false)`** used?
6. When calling **`basicNack(tag, false, true)`**, does the broker wait a few seconds before redelivering?
7. Why can a message be reprocessed even after a DB transaction committed successfully?
8. If code ACKs before DB commit and the process crashes, what can happen?
9. Why does MANUAL ACK still require an idempotent consumer and unique constraints?
10. How do in-listener retry and broker-based retry differ regarding unacked counts, backoff, and post-restart recovery?
11. How many execution passes in a single call does `RetryTemplate` with `maxAttempts(3)` run?
12. If RabbitMQ redelivers an event after a process crash, does the in-process `RetryTemplate` counter persist?
13. When should you reject without requeue immediately instead of retrying?
14. If a queue lacks a DLX/binding, what can happen after `basicReject(tag, false)`?
15. Why does using a DLQ not mean business work completed or bad data was fixed?
16. With 4 consumers and prefetch 8 per consumer, roughly how large is the theoretical unacked window?
17. If unacked hits the cap while ACK rate stays 0, what should you inspect?
18. When an inbound adapter uses MANUAL, where do you obtain **`Channel`** and **delivery tag**, and what must you check before ACKing?
19. If a Spring Integration Message lacks `AmqpHeaders.CHANNEL`, can you open a new channel and use the old delivery tag to ACK?
20. If `MessageConverter` fails before constructing a Spring Message, is the manual ACK handler guaranteed to run?
21. How does switching from DirectChannel to ExecutorChannel alter error and ACK boundaries?
22. When should you ACK after saving to a **durable inbox** yet before background business workers finish?
23. If a consumer bridges queue A to queue B, why does ACKing A not replace publisher confirm for B?
24. Which tests prove that DB commit actually happened **before** ACK?
25. When ACK throws an `IOException` after DB commit, how should the consumer handle redelivery risk?
26. Why configure attempt limits, backoff, and DLQ for transient DB errors instead of infinite requeue?
27. If `eventId` repeats with a different payload, how should an idempotent consumer react?
28. When graceful shutdown leaves unacked deliveries, what must be monitored?
29. When can tested AUTO ACK be simpler and more appropriate than MANUAL ACK?
30. Distinguish consumer ACK, publisher confirm, and business reply in a system using both AMQP inbound and outbound gateways.

## Summary

**Manual acknowledgment** grants control over **when to confirm or reject a RabbitMQ delivery**. In Spring Integration, it is configured on the **AMQP inbound channel adapter**'s **Spring AMQP listener container**, while handlers retrieve the matching **channel and delivery tag** to call **`basicAck`**, **`basicNack`**, or **`basicReject`**. Always settle with the **exact tag on the exact channel**, avoid unintended **multiple ACKs**, and never settle twice.

Reliable retries begin with **error classification**: isolate malformed data, bound retries with backoff for transient failures, and reject/NACK without requeue upon exhaustion to feed a configured and tested **DLX/DLQ**. **`basicNack(requeue=true)`** is not a delayed retry and can trigger hot loops; in-memory **`RetryTemplate`** does not cap total executions across broker redeliveries.

Place ACKs at a **committed boundary**: DB transaction commit or persistence in a **durable inbox**. Because the broker can still redeliver after crashes or lost connections near ACK, consumers need **stable `eventId`s, idempotency, unique constraints, and recovery strategies**. Finally, operating reliably requires managing **prefetch/concurrency, thread models, `errorChannel`, converters, lifecycle, queue ready/unacked counts, DLQ, and business outcomes**. These principles allow integrating AMQP alongside File, SFTP, HTTP, JMS, Kafka, and database flows without mistaking a successful send call for completed business work.
