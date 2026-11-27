# Dead-Letter Exchange and Requeue

## Learning Objectives

After this lesson, you will be able to:

- Explain what **dead-lettering** is and the distinct roles of **dead-letter exchange (DLX)**, **dead-letter queue (DLQ)**, bindings, and routing keys.
- Distinguish **`basicAck`**, **`basicReject`**, **`basicNack`**, the **`requeue=true/false`** flags, broker redelivery, and **republishing** a new message.
- Describe the scenarios in which a message is dead-lettered: rejected without requeue, TTL expiration, max queue length exceeded, or reaching a delivery limit on supported queue types.
- Design **bounded retry and backoff** flows, avoiding hot requeue loops, dead-letter cycles, and indefinite storage of failed messages.
- Configure RabbitMQ topology with **Spring AMQP**, then integrate Spring Integration's **AMQP inbound channel adapter**, **MessageChannel**, service activator, and error handling.
- Analyze the effects of **AUTO/MANUAL ACK**, MessageConverters, listener containers, prefetch, database transactions, idempotency, and shutdown.
- Test rejections, missing DLX bindings, slow retries, connection loss, consumer crashes, and redelivery against a real RabbitMQ broker.

## 1. Problem: Where Does a Repeatedly Failing Message Go?

Suppose queue **`orders.created.q`** holds many **OrderCreated** events. Most messages are valid, yet one message contains schema-invalid JSON that makes WarehouseService fail every time. If the consumer keeps calling **NACK with `requeue=true`**, RabbitMQ redelivers it rapidly in a loop. The consumer hits the same error repeatedly, the queue makes no business progress, logs grow nonstop, and valid messages are impacted.

Conversely, if the consumer calls **NACK with `requeue=false`** without dead-letter configuration on the queue, the message can be discarded instead of resting somewhere it can be investigated and replayed.

A common design:

~~~mermaid
flowchart LR
    P["Order publisher"] --> X["orders.events<br/>exchange"]
    X --> Q["orders.created.q<br/>main queue"]
    Q --> L["AMQP inbound adapter<br/>listener container"]
    L --> H{"Warehouse handler"}
    H -->|"Success"| A["Consumer ACK"]
    H -->|"Permanent error / retries exhausted"| N["Reject or NACK<br/>requeue=false"]
    N --> D["orders.dead.exchange<br/>DLX"]
    D --> DQ["orders.created.dlq"]
    H -->|"NACK requeue=true"| Q
~~~

**A DLX is an exchange, not a queue.** RabbitMQ publishes dead-lettered messages to **that exchange**, and the exchange uses routing keys and bindings to determine which queue receives them. Without a matching route, **merely setting a DLX name does not guarantee messages land in a DLQ**.

In **SPRING_INTEGRATION_ADAPTERS**, this lesson belongs to the **AMQP Adapter** chapter. It focuses on error boundaries when connecting RabbitMQ to inbound/outbound adapters, gateways, and MessageChannels. The discipline of separating source errors, routing errors, processing errors, and durable storage points is equally critical when building File, SFTP, HTTP, JMS, Kafka, or database flows.

## 2. Concepts to Distinguish

| Concept | Meaning | Important Note |
| --- | --- | --- |
| **Main queue** | Queue where consumers receive business deliveries | Holds ready/unacked messages per broker state |
| **Dead-letter exchange (DLX)** | RabbitMQ exchange receiving dead-lettered messages from source queues | Does not store messages like a queue |
| **Dead-letter queue (DLQ)** | Queue bound to a DLX to hold failed messages | Requires matching bindings, permissions, and retention policy |
| **Dead-letter routing key** | Routing key used when publishing to the DLX | Can be configured on the queue via `x-dead-letter-routing-key` |
| **Requeue** | Returns a delivery to the queue's deliverable state | Does not add delay or cap retry counts automatically |
| **Redelivery** | Delivery sent again by the broker after NACK/requeue or consumer loss | Does not mean the producer republished |
| **Republish** | Application publishes a new AMQP message to an exchange/queue | Requires publisher confirms, idempotency, and coordinated source ACK |
| **Retry queue** | Queue that holds messages temporarily before retrying | Distinct from a final DLQ for unprocessable messages |

### 2.1. DLX Is a Second Routing Step

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant E as orders.events
    participant Q as orders.created.q
    participant C as Consumer
    participant D as orders.dead.exchange
    participant F as orders.created.dlq
    P->>E: Publish orders.created
    E->>Q: Route message
    Q-->>C: Delivery
    C-->>Q: basicReject(tag, requeue=false)
    Q->>D: Dead-letter message
    D->>F: Route by dead routing key
~~~

Key point: consumers **do not send messages directly to a DLQ** via `basicReject`. Consumers reject the delivery; RabbitMQ inspects the source queue's dead-letter configuration and publishes the message to the DLX. If the DLX or binding is missing, the message will not be retained as expected.

### 2.2. Consumer ACK, Publisher Confirm, and Publisher Return Differ

| Mechanism | Timing | Responsibility |
| --- | --- | --- |
| **Publisher confirm** | Publisher sends message to exchange | Broker confirms publish handling under confirms |
| **Publisher return** | Publish cannot be routed under mandatory | Notifies publisher of an unroutable message |
| **Consumer ACK/NACK/reject** | After broker delivers message to consumer | Tells broker whether consumer settled or rejected delivery |
| **Dead-lettering** | Message is already in queue and meets a dead-letter trigger | Broker publishes to the DLX |

If a producer publishes to an exchange **with no matching binding**, the message may trigger a **publisher return**; that is not a consumer rejection, nor does it automatically appear in a DLQ. **DLX does not replace publisher returns.**

## 3. How RabbitMQ Handles `basicAck`, `basicReject`, and `basicNack`

For deliveries received under explicit acknowledgment mode, consumers can use the RabbitMQ Java client API:

~~~java
import com.rabbitmq.client.Channel;

// Call ONLY ONE of the following for a single delivery.
channel.basicAck(deliveryTag, false);
channel.basicReject(deliveryTag, true);
channel.basicReject(deliveryTag, false);
channel.basicNack(deliveryTag, false, true);
channel.basicNack(deliveryTag, false, false);
~~~

| Command | Primary Meaning | Broker Effect |
| --- | --- | --- |
| **`basicAck(tag, false)`** | Consumer confirms delivery completed | Broker stops waiting for ACK on that delivery |
| **`basicReject(tag, true)`** | Rejects one delivery, requests requeue | Can be redelivered per broker policy |
| **`basicReject(tag, false)`** | Rejects one delivery, no requeue | Can dead-letter via DLX or be discarded |
| **`basicNack(tag, false, true)`** | NACKs one delivery, requeue | Can redeliver immediately without automatic backoff |
| **`basicNack(tag, false, false)`** | NACKs one delivery, no requeue | Can dead-letter via DLX |
| **`basicNack(tag, true, ...)`** | NACKs multiple unacked deliveries up to tag on same channel | Requires extreme care when tasks run in parallel |

**A delivery tag is scoped strictly to the channel that received the delivery.** Never ACK/NACK on another channel, persist tags across reconnects, or use them as `eventId`. In our examples, **`multiple=false`** is used so other messages are never settled accidentally.

### 3.1. `requeue=true`: Back to Queue, Not Delayed Retry

When a consumer executes **`basicNack(tag, false, true)`**, the broker returns the delivery to the queue, keeping its position near the front depending on concurrency and concurrent operations. While consumers are free, the message can be redelivered **immediately**.

~~~mermaid
flowchart TD
    Q["Queue"] --> C["Consumer"]
    C --> H{"Business handler"}
    H -->|"Error"| N["basicNack(requeue=true)"]
    N --> Q
    H -->|"Success"| A["basicAck"]
~~~

For messages with permanent schema errors, this loop spins very rapidly. RabbitMQ **does not automatically add exponential backoff, cap retries, or route to a DLQ merely because a message was requeued many times**. Certain **quorum queues** support a configured delivery limit, yet never generalize that rule to every queue type and version.

### 3.2. `requeue=false`: Not Necessarily Lost, Provided a DLX Exists

**`basicReject(tag, false)`** and **`basicNack(tag, false, false)`** do not name a DLQ themselves. If the source queue has a valid DLX, the broker uses that configuration to dead-letter. Without a valid DLX, a message rejected without requeue is discarded.

### 3.3. `basicNack` vs. `basicReject` Differ on `multiple`

**`basicReject`** targets a single delivery. **`basicNack`** supports the **`multiple`** flag to NACK a batch of unacked deliveries on the same channel. Never pass **`multiple=true`** if earlier deliveries might still be running in parallel tasks.

### 3.4. ACK Does Not Guarantee Exactly-Once

If a handler commits the database and the connection drops before the broker receives ACK, the delivery can be redelivered. If a handler ACKs before durable business persistence and the process crashes, the work may never be redelivered. Therefore:

1. Place the **ACK point after processing/durable persistence**.
2. Keep **business `eventId`s stable**.
3. Use an **idempotent consumer** or unique constraint/inbox to prevent duplicate side effects.
4. Never treat ACK as part of an atomic transaction with the database.

## 4. Reasons RabbitMQ Dead-Letters a Message

Dead-lettering does not occur only on consumer rejection. Common triggers include:

| Cause | Situation | Things to Watch |
| --- | --- | --- |
| **Reject/NACK with `requeue=false`** | Handler cannot process payload or retries exhausted | Requires valid DLX, binding, and DLQ |
| **TTL expiration** | Message waited longer than configured lifetime | Routed to DLX per queue settings, not consumer action |
| **Queue exceeds `max-length` / `max-length-bytes`** | Broker drops messages due to queue bounds | Behavior follows overflow/policy; may dead-letter |
| **Quorum queue delivery limit** | Message redelivered past threshold supported by quorum queues | Depends on version, policy, settings, and queue type |

### 4.1. Do Not Confuse Queue TTL with Message TTL

RabbitMQ can apply **message TTL** via queue policy/arguments or per-message expiration properties. Expired messages can be dead-lettered if the queue has a DLX. **Queue expiration (`x-expires`)** governs the lifetime of **the queue itself** and does not mean all messages move to a DLX when the queue expires.

TTL also does not promise a Java callback fires at the exact expiration millisecond. Expiration rate—especially with varying per-message TTLs—depends on queue position and broker mechanics.

### 4.2. Overflow Policies Behave Differently

When a queue fills up, RabbitMQ supports policies such as `drop-head` or `reject-publish`, depending on queue type and configuration. Some `max-length` overflows dead-letter dropped messages, whereas `reject-publish` at ingress rejects publishes via error/confirm signals instead.

Never oversimplify as "whenever a queue is full, all messages automatically go to DLQ." Verify queue type, overflow policy, limits, publisher confirms/returns, and broker version.

### 4.3. Quorum Queues Have Specific Delivery-Limit Mechanics

Quorum queues can support a **delivery limit** and handle messages exceeding it per policy. However, do not assume a **classic queue** shares the same default or that application republishes increment the same broker counter. Check queue type, broker version, and how messages are redelivered/republished.

## 5. Configuring DLX: Exchange, Routing Key, Binding, and Queue

Suppose an application uses:

~~~text
Main exchange  : orders.events
Routing key    : orders.created
Main queue     : orders.created.q
DLX            : orders.dead.exchange
DL routing key : orders.failed
DLQ            : orders.created.dlq
~~~

For dead-lettering to work:

1. The main queue configures a **dead-letter exchange** and optionally a **dead-letter routing key**.
2. **`orders.dead.exchange`** exists with an appropriate exchange type.
3. **`orders.created.dlq`** exists.
4. The DLQ is **bound** to the DLX with key **`orders.failed`** if the DLX is a direct exchange.
5. Connection/vhost, permissions, and broker policies allow the dead-letter path.

~~~mermaid
flowchart TD
    P["Publisher"] --> X["Direct exchange<br/>orders.events"]
    X -->|"orders.created"| Q["orders.created.q"]
    Q --> C["Consumer"]
    C -->|"Reject / NACK<br/>requeue=false"| D["DLX<br/>orders.dead.exchange"]
    D -->|"orders.failed"| F["DLQ<br/>orders.created.dlq"]
~~~

### 5.1. `x-dead-letter-exchange` and `x-dead-letter-routing-key`

Two common arguments/policies:

- **`x-dead-letter-exchange`:** exchange name receiving dead-lettered messages.
- **`x-dead-letter-routing-key`:** routing key the broker uses when publishing to the DLX.

If **`x-dead-letter-routing-key` is omitted**, RabbitMQ normally retains the original routing key during dead-lettering per broker rules, with subtleties when multiple routes/bindings exist. If you have a dedicated DLQ and want a simple, predictable key, configure an explicit dead-letter routing key.

### 5.2. DLX Does Not Create the DLQ Automatically

A DLX is **an exchange** and obeys the same binding rules as any direct/topic/fanout exchange. Without a receiving queue or with a mismatched binding key, messages will not land in the DLQ as expected.

### 5.3. DLX Routing and Business Routing Are Separate

**`orders.created`** describes the business event type; **`orders.failed`** is technical routing to the DLQ. Events must still preserve **`eventId`**, **`eventType`**, and **`schemaVersion`** in their payload/properties. Never mutate `eventId` when dead-lettered just because the routing key changed.

## 6. Policy or Hardcoded `x-arguments` on the Queue?

RabbitMQ supports configuring DLX via broker **policies** or **`x-arguments`** in queue declarations. This is an architectural choice, not mere syntax.

| Criterion | RabbitMQ Policy | `x-arguments` in Queue Declaration |
| --- | --- | --- |
| Ownership | Usually managed by ops/platform teams | Usually declared by apps via Queue beans |
| Changing an existing queue | Many settings can change via policy depending on parameter | Many arguments are immutable; changes may require migration |
| Consistency | Applied via pattern/scope across queues | Attached individually per queue |
| Precedence | Broker precedence rules between arguments and policies apply | Explicit `x-arguments` can override policy depending on parameter |
| Risk | Overbroad policy affects many queues | Mismatched argument causes `PRECONDITION_FAILED` on redeclare |

**Operational recommendation:** When platform teams manage production topology, coordinate with the RabbitMQ team on policies rather than hardcoding immutable attributes. In labs or isolated tests, `x-arguments` keep setups self-contained and easy to read.

### 6.1. Why Check Existing Queues Before Changing DLX?

A queue named **`orders.created.q`** already declared on the broker with `x-arguments` will not necessarily accept a redeclaration with different attributes. RabbitMQ can return **`PRECONDITION_FAILED`** and close the declaring channel. Never assume editing a Java bean and restarting the app migrates an existing queue cleanly.

### 6.2. Policies Do Not Replace Access Permissions

In multi-virtual-host environments, the DLX, main queue, and DLQ must live and route inside the same **vhost**. Accounts need appropriate permissions for declarations and dead-letter paths per RabbitMQ rules. Also restrict read access to the DLQ since it can hold sensitive payloads.

## 7. Retry Mechanisms Easily Confused with Dead-Lettering

| Mechanism | When to Use? | Strength | Risk |
| --- | --- | --- | --- |
| **Immediate requeue** | Very brief glitches with strict controls | Creates no new messages | Can spin into an infinite hot loop |
| **In-process retry** | Short transient errors, a few attempts inside listener | Easy backoff/classifier | Keeps delivery unacked, ties up worker |
| **DLX + TTL retry queue** | Broker-mediated delayed redelivery | Avoids sleeping workers for long waits | Loops forever without attempt caps |
| **Republish to retry exchange** | Need fine control over count/destination/payload | Flexible routing | Must confirm new publish before ACKing original |
| **Durable inbox/job + scheduler** | Prolonged retries needing state tracking | Clear attempt/`nextRetryAt` tracking | Adds DB tables, workers, and recovery logic |
| **Final DLQ** | Bad data or exhausted retries needing investigation | Isolates from main stream | Needs owner, retention, and controlled replay |

### 7.1. In-Listener Retry Does Not Use DLX

With **Spring Retry/`RetryTemplate`**, a listener can retry transient infrastructure errors before returning from the callback. Deliveries stay **unacked** during backoff. If an attempt succeeds, the consumer ACKs; if attempts exhaust, policy rejects without requeue to route to the DLX.

### 7.2. A Retry Queue Is Not a Final DLQ

A **retry queue** **temporarily holds** messages before returning them to the main queue when due. A **final DLQ** isolates messages **excluded from further automatic processing**. Use distinct names and exchanges so operators never confuse the two destinations.

### 7.3. One Queue with Multiple Consumers Is Still One Queue

Adding consumers to the main queue increases throughput, yet does not give each system its own copy. If both Warehouse and Analytics need OrderCreated, declare **two separate queues** bound to the exchange; design retries and DLQs per consumer group so ownership stays clear.

## 8. Hands-On Example: Failed OrderCreated Routed to DLQ

Let's build a minimal yet extensible flow:

~~~text
Producer
   -> orders.events (direct exchange)
   -> orders.created (routing key)
   -> orders.created.q (main queue)
   -> SimpleMessageListenerContainer (AUTO ACK)
   -> AMQP inbound adapter
   -> DirectChannel
   -> RetryTemplate (3 attempts for transient errors)
   -> OrderProcessingService

On success:
   container ACK

On data error or exhausted retries:
   container rejects/NACKs without requeue
   -> orders.dead.exchange
   -> orders.failed (dead-letter routing key)
   -> orders.created.dlq
~~~

**Design decision for this example:** we use **`AcknowledgeMode.AUTO`** and keep the handler synchronous so the listener container owns settlement. The handler throws an exception when processing fails. **Do not** also call `basicAck`/`basicNack` manually in this AUTO example.

In the dedicated lesson on manual acknowledgment, the application calls ACK/NACK itself using channel and delivery tag. Both models aim to control delivery settlement, yet **settlement ownership must never be mixed**.

### 8.1. Dependencies

With Spring Boot, illustrative dependencies:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-amqp</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
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

Use compatible versions from **Spring Boot dependency management/BOM**, and Java 17 or newer for the record example below. The environment needs a test RabbitMQ broker, an appropriate ConnectionFactory, and permissions to create or use topology. **Never hardcode real credentials.**

### 8.2. Java Configuration: Main and Dead-Letter Topologies

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersDlxTopology {

    public static final String EVENTS_EXCHANGE = "orders.events";
    public static final String EVENTS_KEY = "orders.created";
    public static final String MAIN_QUEUE = "orders.created.q";

    public static final String DEAD_EXCHANGE = "orders.dead.exchange";
    public static final String DEAD_KEY = "orders.failed";
    public static final String DEAD_QUEUE = "orders.created.dlq";

    @Bean
    public DirectExchange ordersEventsExchange() {
        return new DirectExchange(EVENTS_EXCHANGE, true, false);
    }

    @Bean
    public Queue ordersQueue() {
        return QueueBuilder.durable(MAIN_QUEUE)
            .deadLetterExchange(DEAD_EXCHANGE)
            .deadLetterRoutingKey(DEAD_KEY)
            .build();
    }

    @Bean
    public Binding ordersEventsBinding(
            @Qualifier("ordersQueue") Queue queue,
            @Qualifier("ordersEventsExchange") DirectExchange exchange) {

        return BindingBuilder.bind(queue)
            .to(exchange)
            .with(EVENTS_KEY);
    }

    @Bean
    public DirectExchange ordersDeadExchange() {
        return new DirectExchange(DEAD_EXCHANGE, true, false);
    }

    @Bean
    public Queue ordersDeadQueue() {
        return QueueBuilder.durable(DEAD_QUEUE).build();
    }

    @Bean
    public Binding ordersDeadBinding(
            @Qualifier("ordersDeadQueue") Queue queue,
            @Qualifier("ordersDeadExchange") DirectExchange exchange) {

        return BindingBuilder.bind(queue)
            .to(exchange)
            .with(DEAD_KEY);
    }
}
~~~

Two **Queue beans** and two **DirectExchange beans** exist in the same ApplicationContext, so the example uses **`@Qualifier`** at injection points instead of relying on parameter-name inference or picking the wrong bean.

**Scope:** This topology targets a test broker or brand-new queues. If the main queue already exists without DLX arguments, changing the declaration may fail. In production, coordinate with operations and evaluate broker policies or migrations.

### 8.3. Topology Alone Does Not Guarantee Once-Only Processing

- **Durable exchange** and **durable queue** describe resource survivability.
- **Message persistence**, publisher confirms, queue type, and broker policies govern message durability guarantees.
- **Consumer ACK** confirms delivery; it does not prove a business side effect executed exactly once.
- **DLX/DLQ** isolates failures when properly configured; it does not replace business transactions or idempotency.

If applications span multiple virtual hosts, exchanges and queues with identical names in two different vhosts **are not a shared topology**.

## 9. Listener Container and ACK/NACK in Spring Integration

For message-driven AMQP inbound, the Spring AMQP listener container receives RabbitMQ deliveries, and the Spring Integration inbound adapter wraps them into Spring Messages sent to a MessageChannel.

~~~mermaid
flowchart LR
    MQ["orders.created.q"] --> LC["SimpleMessageListenerContainer"]
    LC --> IA["Amqp.inboundAdapter"]
    IA --> CH["ordersInput<br/>DirectChannel"]
    CH --> H["Service activator"]
    H --> DB[("Warehouse DB")]
    LC -. "ACK or reject" .-> MQ
~~~

### 9.1. Configuring SimpleMessageListenerContainer

~~~java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.listener.SimpleMessageListenerContainer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersListenerConfig {

    @Bean("ordersListenerContainer")
    public SimpleMessageListenerContainer ordersListenerContainer(
            ConnectionFactory connectionFactory) {

        SimpleMessageListenerContainer container =
            new SimpleMessageListenerContainer(connectionFactory);

        container.setQueueNames(OrdersDlxTopology.MAIN_QUEUE);
        container.setConcurrentConsumers(2);
        container.setMaxConcurrentConsumers(4);
        container.setPrefetchCount(10);
        container.setAcknowledgeMode(AcknowledgeMode.AUTO);

        // Note: fallback requeue policy; does NOT create DLX/DLQ on its own.
        container.setDefaultRequeueRejected(false);

        return container;
    }
}
~~~

**`AcknowledgeMode.AUTO`** in Spring AMQP means the container actively ACKs when the listener callback succeeds, or rejects/NACKs per policy when it fails. It is **not** RabbitMQ's no-acknowledgment mode.

**`defaultRequeueRejected(false)`** prevents errors handled by the container's default mechanism from requeuing endlessly. Still verify the **listener error handler**, special exceptions, `errorChannel`, and exception propagation back to the container; never conclude every failure lands in the DLQ solely because this setter is `false`.

### 9.2. Prefetch and Concurrency Affect Requeues

With two consumers and prefetch 10, the in-flight window is roughly **20 unacked deliveries** under standard per-consumer QoS. If the container scales up to four consumers, the theoretical window rises to **40**.

When a consumer crashes or a connection closes, unacked deliveries are eligible for redelivery. High prefetch increases the batch that must be redelivered. Never raise prefetch solely to drain ready counts while handlers cannot keep pace.

### 9.3. SMLC vs. DMLC

**SimpleMessageListenerContainer** uses **`concurrentConsumers`/`maxConcurrentConsumers`** and its own consumer scaling mechanism. **DirectMessageListenerContainer** uses a different listener/thread model and **`consumersPerQueue`**. Both receive deliveries and apply prefetch and ACK policies, yet never copy parameters blindly from one container type to the other without checking.

**DirectMessageListenerContainer is not DirectChannel.** One belongs to the RabbitMQ consumer/client layer; the other is a synchronous Spring Integration MessageChannel.

## 10. Classifying Business Errors Before Retrying

Instead of retrying every `RuntimeException`, classify errors:

- **`InvalidOrderEventException`:** contract-violating payload that will not heal across retries.
- **`TransientOrderException`:** transient outage such as a DB timeout that can recover.
- **Configuration/permission errors:** must not loop forever; alert and fix root cause.
- **Uncertain transaction outcomes:** reconcile by `eventId` and idempotency before retrying.

### 10.1. Exception Classes

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
public class TransientOrderException extends RuntimeException {

    public TransientOrderException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

### 10.2. `RetryTemplate` Retries Only Transient Exceptions

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.retry.support.RetryTemplate;
import org.springframework.retry.support.RetryTemplateBuilder;

@Configuration
public class OrdersRetryConfig {

    @Bean
    public RetryTemplate ordersRetryTemplate() {
        return new RetryTemplateBuilder()
            .maxAttempts(3)
            .exponentialBackoff(200L, 2.0, 1200L)
            .retryOn(TransientOrderException.class)
            .build();
    }
}
~~~

**`maxAttempts(3)`** typically covers **the first execution plus up to two retries**. If a delivery is redelivered after a crash, a fresh retry cycle starts; in-process `RetryTemplate` is not a durable lifetime counter for the event.

While `RetryTemplate` sleeps in backoff, the delivery remains **unacked**, occupying a prefetch slot. If infrastructure outages last minutes, prefer a delayed retry queue or durable job store over sleeping listener threads.

### 10.3. Why Classify Errors?

| Handler Outcome | Error Category | Appropriate Action in Example |
| --- | --- | --- |
| Valid parse, business success | Success | AUTO ACK |
| Malformed JSON/text | Permanent data error | Do not retry; reject without requeue |
| Unsupported `schemaVersion` | Contract error | Do not hot-requeue; isolate and alert |
| DB temporarily unavailable | Transient | Bounded retry with backoff; dead-letter if exhausted |
| Invalid DB permissions | Permanent configuration | Alert/fix infra; avoid infinite retry |
| `eventId` already processed | Valid duplicate | Skip repeated side effect; return normally for ACK |
| Broker connection drops near ACK | Uncertain outcome | May redeliver; idempotency protects state |

**Dead-lettering should not be the sole reflex for every error.** For brief DB outages, controlled **delayed retries** cut down manual triage volume. For permanent schema errors, retrying the same bad payload accomplishes nothing.

## 11. Business Service: Validation, Transaction, and Idempotency

To demonstrate real persistence rather than logging, we process an `OrderCreated` event and update a Warehouse projection. The goal is **applying side effects once per `eventId`**, even when the broker redelivers.

### 11.1. Record and Parser

~~~java
public record OrderCreatedEvent(
    String eventId,
    String orderId,
    long totalVnd
) {}
~~~

~~~java
public final class OrderEventParser {

    private OrderEventParser() {}

    public static OrderCreatedEvent parse(String payload) {
        if (payload == null || payload.length() > 1024) {
            throw new InvalidOrderEventException(
                "Payload empty or too large");
        }

        String[] fields = payload.split("\\|", -1);
        if (fields.length != 3
                || !fields[0].matches("[A-Za-z0-9_-]{1,80}")
                || !fields[1].matches("[A-Za-z0-9_-]{1,80}")) {
            throw new InvalidOrderEventException(
                "Expected eventId|orderId|totalVnd");
        }

        final long total;
        try {
            total = Long.parseLong(fields[2]);
        } catch (NumberFormatException ex) {
            throw new InvalidOrderEventException(
                "totalVnd is not an integer", ex);
        }

        if (total <= 0) {
            throw new InvalidOrderEventException(
                "totalVnd must be positive");
        }
        return new OrderCreatedEvent(fields[0], fields[1], total);
    }
}
~~~

This is a **sample text payload** to keep focus on requeue mechanics. Production should use JSON/Avro/Protobuf with `schemaVersion`, validation, and size bounds. Never assume every AMQP inbound message is a pipe-delimited String.

### 11.2. Repository Contract

~~~java
public interface WarehouseProjectionRepository {

    // Atomic insert with UNIQUE(consumer_name, event_id).
    // Returns false when the event was already processed.
    boolean insertInboxIfAbsent(String consumerName, String eventId);

    // Must participate in the same database transaction.
    void updateOrderProjection(String orderId, long totalVnd);
}
~~~

This interface **must be implemented** with JDBC/JPA and an appropriate driver. You need an inbox table, unique constraint, and transaction manager; Spring does not auto-generate implementations merely from these method names.

### 11.3. Synchronous Business Service

~~~java
import org.springframework.dao.TransientDataAccessException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderProcessingService {

    private final WarehouseProjectionRepository repository;

    public OrderProcessingService(
            WarehouseProjectionRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void process(String payload) {
        OrderCreatedEvent event = OrderEventParser.parse(payload);

        try {
            boolean firstTime = repository.insertInboxIfAbsent(
                "warehouse", event.eventId());

            if (!firstTime) {
                return; // Duplicate: no repeated side effect.
            }
            repository.updateOrderProjection(
                event.orderId(), event.totalVnd());
        } catch (TransientDataAccessException ex) {
            throw new TransientOrderException(
                "Temporary database failure", ex);
        }
    }
}
~~~

Key conditions:

- `OrderProcessingService` is called through a **Spring bean/proxy** so transaction advice takes effect.
- Inbox insertion and projection update share the same transaction in the same database.
- The unique constraint prevents races across concurrent consumers; naive **check-then-insert** is insufficient.
- When updating fails, the transaction rolls back the inbox insert too, allowing clean retries.
- When the DB commits and ACK fails, redelivery sees `eventId` already exists and skips side effects.

**`@Transactional` does not create an atomic transaction spanning database and RabbitMQ ACK.** If a handler calls external APIs or publishes to Kafka/JMS mid-transaction, those external side effects need dedicated idempotency and reconciliation.

## 12. Spring Integration Java DSL: Inbound → Retry → DLX

The flow wires **`ordersListenerContainer`** to **`Amqp.inboundAdapter`**. The handler runs synchronously in the listener callback; the container AUTO ACKs on success or rejects per policy on failure.

~~~java
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.rabbit.listener.SimpleMessageListenerContainer;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.amqp.dsl.Amqp;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.retry.support.RetryTemplate;

@Configuration
@EnableIntegration
public class OrdersInboundFlowConfig {

    @Bean
    public MessageChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow ordersInboundFlow(
            @Qualifier("ordersListenerContainer")
            SimpleMessageListenerContainer container,
            RetryTemplate ordersRetryTemplate,
            OrderProcessingService orderProcessingService) {

        return IntegrationFlow
            .from(Amqp.inboundAdapter(container))
            .channel("ordersInput")
            .handle(String.class, (payload, headers) -> {
                try {
                    ordersRetryTemplate.execute(context -> {
                        orderProcessingService.process(payload);
                        return null;
                    });
                } catch (RuntimeException ex) {
                    // Permanent error OR transient retries exhausted.
                    throw new AmqpRejectAndDontRequeueException(
                        "OrderCreated cannot be processed", ex);
                }
                return null;
            })
            .get();
    }
}
~~~

### 12.1. Note on Exception Translation

Exceptions from a Spring Integration handler may be wrapped inside **`MessagingException`** before returning to the Spring AMQP listener container. The container evaluates requeue rules, though exact behavior depends on version and error handler.

In this sample, **`setDefaultRequeueRejected(false)`** provides fallback protection against infinite requeues, and **`AmqpRejectAndDontRequeueException`** explicitly signals no requeue. **Test against real RabbitMQ** to verify exceptions propagate through the adapter and the container actually rejects/NACKs as intended.

**Do not call `basicNack` manually in this handler:** the container is in **AUTO** mode. If switching to MANUAL, redesign settlement ownership and verify zero double settlement.

### 12.2. Expected Behavior by Failure Type

| Outcome | RetryTemplate | Handler | RabbitMQ |
| --- | --- | --- | --- |
| Business succeeds | Completes | Returns normally | Container AUTO ACKs |
| `eventId` already processed | No repeated side effect | Returns normally | Container AUTO ACKs |
| `InvalidOrderEventException` | Does not retry | Throws reject-not-requeue | Dead-lettered if topology valid |
| `TransientOrderException` recovers within 3 attempts | Bounded retry | Eventually returns normally | Container AUTO ACKs |
| `TransientOrderException` exhausts attempts | Fails | Throws reject-not-requeue | Dead-lettered if topology valid |
| Converter fails before flow | Handler may never run | Container error handler | Verify reject/requeue/DLQ separately |

### 12.3. Why Use DirectChannel?

**DirectChannel** invokes the handler synchronously inside the listener's execution path. Once `OrderProcessingService` finishes its transaction and the handler returns, the container has a valid basis to ACK on listener outcome.

If replaced by **ExecutorChannel**, the listener may return right after queuing the task on the executor **before the business worker finishes**. If the container AUTO ACKs then, the broker loses redelivery protection for downstream async failures.

Default **`QueueChannel`** is also not durable. If long processing must be decoupled, persist to a **durable inbox/job** inside a transaction before ACKing, then let workers process durably and idempotently.

### 12.4. Converters and Payload Contracts

The flow assumes `SimpleMessageConverter` emits a `text/plain` `String`. If producers send JSON or binary payloads, the inbound adapter may emit `byte[]` or a DTO, breaking a handler expecting `String`.

Verify `contentType`, `charset`, `schemaVersion`, header mappers, and `MessageConverter` at the **AMQP boundary**. When a converter throws before building a Spring Message, the exception may bypass the handler above; test the container error handler directly.

## 13. Test Publishing and Observing the Dead-Letter Path

With a `RabbitTemplate` configured on the same broker/vhost:

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;

public class OrdersTestPublisher {

    private final RabbitTemplate rabbitTemplate;

    public OrdersTestPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void sendValid() {
        rabbitTemplate.convertAndSend(
            OrdersDlxTopology.EVENTS_EXCHANGE,
            OrdersDlxTopology.EVENTS_KEY,
            "evt-1001|O-1001|150000");
    }

    public void sendInvalid() {
        rabbitTemplate.convertAndSend(
            OrdersDlxTopology.EVENTS_EXCHANGE,
            OrdersDlxTopology.EVENTS_KEY,
            "event-without-required-fields");
    }
}
~~~

For a valid event, expect: broker routes to main queue, inbound flow parses and updates projection, transaction commits, container AUTO ACKs, and the DLQ receives nothing.

For an invalid payload: parser throws `InvalidOrderEventException`, `RetryTemplate` skips retries, handler throws reject-not-requeue, container rejects delivery, and broker routes via DLX/DLQ **if** dead-letter settings are working.

### 13.1. Read the DLQ Only in an Isolated Environment

In an integration test, `RabbitTemplate.receiveAndConvert` can pull the message from the DLQ to assert its arrival:

~~~java
Object dead = rabbitTemplate.receiveAndConvert(
    OrdersDlxTopology.DEAD_QUEUE, 2000L);

// Expected: String "event-without-required-fields",
// when a matching text converter is used and no other consumer is active.
~~~

**`receive` is not `peek`:** it consumes the message. Run this only on a test broker/queue; never run it to inspect a production DLQ unless you intend to remove messages awaiting investigation.

### 13.2. Testing Retries Before Dead-Lettering

Using a stub test repository:

- Attempt 1 throws `TransientOrderException`.
- Attempt 2 succeeds.
- Verify the handler returns normally and the container ACKs; the DLQ receives nothing.

When all three attempts fail:

- Handler throws reject-not-requeue.
- Broker dead-letters to the DLQ per topology.
- Logs/metrics record **retry exhausted** to distinguish from payload errors.

**One delivery can be retried multiple times inside the listener**, so RabbitMQ callback counts do not prove `RetryTemplate` ran only once.

### 13.3. Use Isolated Topology for Tests

If another application consumes the same queue, competing consumers can steal messages before your test sees them. Use a separate queue, vhost, or test broker. If old messages remain in the queue, isolate test data and use unique `eventId`s for deterministic results.

## 14. Retry Queues with TTL: Delaying Without Infinite Loops

When a downstream outage lasts minutes, holding unacked deliveries in listeners while `RetryTemplate` sleeps is impractical. A common design is a **TTL retry queue**:

~~~mermaid
flowchart TD
    MQ["orders.created.q<br/>main queue"] --> C["Consumer"]
    C -->|"Success"| ACK["ACK"]
    C -->|"Transient error needing delay"| RX["orders.retry.exchange"]
    RX --> RQ["orders.retry.q<br/>message TTL"]
    RQ -->|"TTL expired, dead-letter"| EX["orders.events"]
    EX --> MQ
    C -->|"Permanent error / retries exhausted"| DX["orders.dead.exchange"]
    DX --> DQ["orders.created.dlq"]
~~~

**Two separate branches:** permanent errors and exhausted retries must route to the **final DLQ**; transient errors can route to the **retry queue** for delayed reprocessing. Branching can be driven by application republishing, broker policies, or intermediate queues. If every non-requeued NACK from the main queue went straight to the retry queue, a permanently malformed message would cycle back to the main queue forever.

### 14.1. Configuring a Dedicated Retry Queue

The following Java configuration is an **optional add-on**: declaring an exchange/queue/binding for a simple delay.

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersDelayedRetryTopology {

    public static final String RETRY_EXCHANGE = "orders.retry.exchange";
    public static final String RETRY_QUEUE = "orders.retry.q";
    public static final String RETRY_KEY = "orders.retry";

    @Bean
    public DirectExchange ordersRetryExchange() {
        return new DirectExchange(RETRY_EXCHANGE, true, false);
    }

    @Bean
    public Queue ordersRetryQueue() {
        return QueueBuilder.durable(RETRY_QUEUE)
            .ttl(30_000)
            .deadLetterExchange(OrdersDlxTopology.EVENTS_EXCHANGE)
            .deadLetterRoutingKey(OrdersDlxTopology.EVENTS_KEY)
            .build();
    }

    @Bean
    public Binding ordersRetryBinding(
            @Qualifier("ordersRetryQueue") Queue queue,
            @Qualifier("ordersRetryExchange") DirectExchange exchange) {
        return BindingBuilder.bind(queue)
            .to(exchange)
            .with(RETRY_KEY);
    }
}
~~~

**Meaning:** Messages entering the retry queue wait for a duration governed by TTL and the broker. When TTL expires, the broker dead-letters them back to the main exchange under key `orders.created`. **TTL is not a millisecond-accurate delivery timer**; it depends on broker scheduling, queue state, load, and expiration mechanics.

### 14.2. How Do Messages Enter the Retry Queue?

The snippet above **does not automatically route messages from the main queue into the retry queue**. Choose one of these designs:

**Option A — Main queue DLX points to retry exchange:** the broker moves rejected-without-requeue messages into the retry queue. However, all eligible dead-lettered messages take this path; without classification and attempt limits, schema-invalid messages will loop infinitely. If you choose this option, **intentionally update the main queue topology** rather than keeping two conflicting Queue beans with the same name.

**Option B — Application republishes to retry exchange:** the handler classifies transient errors, publishes **a new message** to the retry exchange under the retry key, and ACKs the original only after reaching a durable acceptance milestone per contract. When republish outcomes are uncertain, handle `UNKNOWN`, idempotency, and potential duplicates.

**Option C — Durable inbox/job scheduler:** the handler persists a job in the database inside a transaction, ACKs after durable persistence, and a dedicated worker retries at `nextRetryAt`. Suits scenarios needing explicit attempt tracking, custom delays, and long-term state.

**Do not** keep the main queue declaring `deadLetterExchange = orders.dead.exchange` and expect a single NACK to jump to `orders.retry.exchange`. A queue has one active dead-letter target; splitting paths requires explicit routing or republishing logic.

### 14.3. TTL, Head-of-Line Blocking, and Ordering

Message TTL can be affected by how the broker detects expired messages at the head of a queue. When messages with different TTLs share one queue, expiration order does not behave like an exact per-message timer in all situations.

For staged backoff tiers, use separate retry queues per interval (e.g., 10 seconds, 1 minute, 5 minutes) or a durable scheduler. Evaluate memory/disk footprint, queue count, throughput, and bulk failure handling for each option.

### 14.4. Avoiding Dead-Letter Cycles

~~~text
main queue
  -> DLX
  -> TTL retry queue
  -> DLX
  -> main queue
  -> ...
~~~

Without an **attempt limit**, a **final DLQ**, and clear ownership to break the loop, a permanently broken message can cycle through this loop repeatedly. RabbitMQ has cycle-detection behaviors depending on cycle shape, dead-letter trigger, and broker version; **never rely on the broker to break every cycle automatically** in place of an application retry policy.

### 14.5. A Retry Queue Does Not Guarantee Republishing to the Target Broker

If a worker actively republishes from queue A to a retry exchange, at least two actions occur: **publishing the new message** and **ACKing the original**. They are not part of an atomic transaction with your database/business logic. A careful approach:

1. Keep **`eventId`** stable, optionally generating a separate `attemptId`.
2. Publish to the retry exchange with **publisher confirms** and **returns** handling to detect unroutable publishes.
3. ACK the original delivery only after reaching the design's accepted handoff milestone.
4. If the new publish becomes **`UNKNOWN`**, never assume it was not sent; support reconciliation and idempotent retries.
5. Downstream consumers must deduplicate because the same event can appear twice during connection failures.

Never treat a publisher confirm ACK as proof the retry consumer finished processing; it only confirms broker-level publishing.

## 15. `x-death` and Dead-Letter History Metadata

RabbitMQ can attach or update dead-letter metadata, typically including **`x-death`** or **`x-first-death`** / **`x-last-death`** headers depending on version and policy. These aid diagnostics:

- Which queue dead-lettered the message.
- Reason, such as **`rejected`**, **`expired`**, **`maxlen`**, or **`delivery_limit`** where supported.
- Associated exchange and routing details.
- Broker-maintained counts/history in that version's format.

Logical example:

~~~text
eventId = evt-1001
dead-letter history:
  queue = orders.created.q
  reason = rejected
  count = ... (per broker representation)
~~~

**Never fabricate `x-death` inside payloads or treat it as infallible proof.** Metadata format and updates are managed by RabbitMQ; application-level republishing can alter or strip prior headers. Newer broker versions may also restrict accepting client-supplied `x-death` headers.

### 15.1. Why `x-death` Count Is Not Always Total Business Attempts

- A message may be retried **three times inside one listener callback** yet dead-lettered **once**.
- A message may be republished as a new body carrying the same `eventId`.
- A message may be dead-lettered across multiple queues for different reasons.
- The broker may aggregate history by queue/reason rather than logging a separate line per business attempt.

Thus never equate **total business attempts = an arbitrary count field**. To cap total attempts across restarts and requeues, use a controlled **durable attempt counter** or a verified queue-type delivery limit.

### 15.2. Header Metadata Is Not Authorization

Never trust a producer-supplied **`retryCount=0`** header to reset attempt budgets. If your application supports replay, enforce replay authorization and `eventId`/schema integrity rather than letting external clients trigger unbounded retries.

### 15.3. Dead-Letter Routing Key Differs from Original Business Key

A message initially arrived on **`orders.created`** and was dead-lettered via **`orders.failed`**. DLQ consumers need **`eventType=ORDER_CREATED`** and `eventId` from business payload/headers rather than inspecting the DLX routing key and assuming the business event type became "FAILED."

## 16. Reliability Limits of Dead-Lettering

DLX/DLQ is essential, yet **should not be described as an always-atomic, zero-loss transfer**. Broker dead-letter publishing uses guarantees that depend on **queue type, broker version, and configuration**.

### 16.1. What Can Go Wrong?

- The DLX does not exist or was deleted after queue declaration.
- The DLX exists, yet **no binding matches** the dead-letter routing key.
- The target DLQ becomes unavailable or applies aggressive overflow/TTL policies.
- Internal permission/connection errors or severe broker resource saturation occur.
- In some dead-letter setups, the transfer does not offer the same confirmation/durability guarantees as an application publisher using confirms.

**Conclusion:** calling `basicReject` without requeue and seeing the Java call succeed **does not prove the DLQ stored the message**. Test and monitor routing results, broker logs, queue metrics, and the exact guarantees of your queue type.

### 16.2. Quorum Queues and At-Least-Once Dead-Lettering

Certain RabbitMQ versions support **at-least-once dead-lettering** for **quorum queues** when required settings are enabled. This differs from standard dead-letter behavior and imposes queue, policy, and resource constraints.

If your SLA requires zero loss of dead-lettered messages, **evaluate the feature on your target RabbitMQ version**, design permissions, policies, monitoring, and failover tests. Never claim every classic queue or every quorum queue provides at-least-once dead-letter delivery by default.

### 16.3. DLQs Also Need Retention and Capacity Limits

A DLQ can fill up, store sensitive payloads, hit TTL/overflow limits, or lose messages to accidental replay. Never treat a DLQ as infinite zero-loss storage. Enforce:

- Explicit operational ownership.
- Read/write access controls and audit logging.
- Capacity and retention caps.
- Alerts on message count and oldest message age.
- Backup/export policies if compliance requires.
- Controlled replay tested for duplicate safety.

### 16.4. Rule: Never Fix Errors by Raising Prefetch

When messages repeatedly reject and return to the queue, raising prefetch/concurrency simply **accelerates error throughput and retry volume** without fixing schemas or databases. Tune throughput only after error classification, retry budgets, and DLQ correctness are solid.

## 17. AUTO ACK, MANUAL ACK, and `errorChannel`

In Spring AMQP + Spring Integration, failure handling can cross multiple layers:

~~~mermaid
flowchart TD
    B["RabbitMQ delivery"] --> C["MessageConverter"]
    C -->|"Decode OK"| A["AMQP inbound adapter"]
    C -->|"Decode error"| CE["Listener error handler"]
    A --> CH["MessageChannel"]
    CH --> H["Handler / RetryTemplate"]
    H -->|"Success"| ACK["AUTO ACK"]
    H -->|"Exception reaches container"| REJ["Reject / NACK per policy"]
    CH -. "ErrorMessage if configured" .-> EC["Integration errorChannel"]
    EC --> P["Error flow / logging"]
~~~

### 17.1. MessageConverter Errors Happen Before the Handler

If the AMQP body has invalid JSON or fails type mapping, the converter throws before Spring Integration constructs a Message for the flow. Then **the service activator and `RetryTemplate` in Section 12 never execute**.

Verify the **listener error handler**, fatal exception classification, and `AcknowledgeMode`. In some versions/configurations, fatal conversion errors reject without requeue. Yet **never promise every converter failure lands in the DLQ automatically**, as DLX topology and exception policies still apply.

### 17.2. `errorChannel` Can Absorb Exceptions

When handler exceptions route to an `ErrorMessage` on `errorChannel` and the error flow finishes normally, the listener container may not see an exception the way it would if the handler threw directly.

**Possible consequences:**

- With **AUTO**, the container may treat the callback as complete and ACK.
- With **MANUAL**, if the error flow fails to settle the delivery, the message stays unacked.
- If both the error flow and another code path call ACK/NACK, a **double acknowledgment** occurs.

Always establish **one final settlement owner** per branch and test every error path. Never log an exception and return normally without verifying whether ACK or NACK actually happened.

### 17.3. Example: Debugging Messages Missing the DLQ

Suppose an application has:

~~~text
Listener AUTO
  -> inbound adapter
  -> DirectChannel
  -> handler throws IllegalArgumentException
  -> custom errorChannel
  -> error handler logs and returns
~~~

If the custom `errorChannel` handler swallows the exception propagation path back to the container, the broker receives an ACK instead of a reject. To route **data errors to the DLQ**, inspect the error flow contract: does it return normally, rethrow, and what ACK/NACK does the container actually send?

### 17.4. MANUAL ACK Requires a Single Owner

When choosing MANUAL, handlers can retrieve channel/delivery tag via **AMQP headers** exposed by compatible endpoints and execute:

~~~java
// Illustrates settlement commands under MANUAL ACK only.
// Channel and tag must belong to THIS exact delivery.
channel.basicAck(deliveryTag, false);           // Success
channel.basicNack(deliveryTag, false, true);    // Requeue
channel.basicReject(deliveryTag, false);        // Dead-letter if DLX
~~~

**Use only one of these commands per delivery.** Delivery tags belong to their channel and cannot be reused across channels. Never pass raw `Channel` or tags casually across async threads/JSON/HTTP expecting ACKs to remain valid after reconnects.

Do not combine this MANUAL snippet with the AUTO container from Sections 9–12. It is an **alternative approach** requiring `AcknowledgeMode.MANUAL`, header-mapping tests, and rewritten settlement paths.

### 17.5. ExecutorChannel Shifts the ACK Boundary

With DirectChannel, handlers run synchronously so errors propagate back to the listener before AUTO ACK. With ExecutorChannel:

~~~mermaid
sequenceDiagram
    participant B as RabbitMQ
    participant L as Listener AUTO
    participant E as ExecutorChannel
    participant W as Async worker
    L->>E: Send Spring Message
    E-->>L: Executor accepts task
    L-->>B: ACK on listener outcome
    E->>W: Task runs later
    W--xW: Business processing fails
    Note over B,W: Delivery may have ACKed before business failure occurred
~~~

If business logic takes long and must be asynchronous, consider **persisting to a durable inbox/job before ACK**, letting workers execute afterward with independent state and retries. An in-memory default `QueueChannel` **is not a durable inbox**.

## 18. Redelivery, Idempotency, and Transactions

**Dead-lettering does not fix duplicate processing.** Deliveries can repeat when:

- Consumer NACKs with `requeue=true`.
- Consumer crashes before ACK.
- Connection/channel closes with unacked deliveries outstanding.
- Producer resends after losing publisher confirms.
- An operator replays messages from a DLQ or retry queue.

### 18.1. Two Critical Crash Windows

~~~text
Case A:
  Delivery received -> ACK -> process crashes -> DB not committed
  => Risk of losing business side effect.

Case B:
  Delivery received -> DB commits -> process crashes before ACK
  => Broker may redeliver and side effects risk being duplicated.
~~~

Keep the ACK point **after processing/durable persistence** to prevent Case A, and enforce a **unique `eventId`/inbox** to block duplicate side effects in Case B.

### 18.2. `eventId` Differs from Routing Key, Delivery Tag, and `x-death`

| Data | Function | Safe as Idempotency Key? |
| --- | --- | --- |
| **`eventId`** | Stable business event identifier | Yes, when contract guarantees uniqueness/scope |
| **`routingKey`** | Routes via exchange to queues | No; many events share one key |
| **`deliveryTag`** | ACK/NACK on one AMQP channel | No; valid only within that channel |
| **`redelivered` flag** | Hints broker delivered earlier | No; does not prove business commit |
| **`x-death` metadata** | Describes dead-letter history | No; not a business identity |
| **`CorrelationData` ID** | Pairs publisher confirm with attempt | Not by default; retries may create new attemptIds |

### 18.3. Unique Constraints Must Be Designed Properly

An inbox table can enforce:

~~~text
processed_events
  consumer_name VARCHAR
  event_id      VARCHAR
  payload_hash  VARCHAR
  processed_at  TIMESTAMP

UNIQUE (consumer_name, event_id)
~~~

If `eventId` already exists, the consumer skips repeating side effects. If `eventId` matches while `payload_hash` differs, raise a conflict/investigation alert rather than silently ignoring it as a valid duplicate.

**Avoid:** checking whether `eventId` exists and then updating the DB without a transaction and unique constraint. When two consumers run concurrently, both can see it absent and both execute side effects.

### 18.4. Pairing Retries with Non-Database Side Effects

If the consumer calls a payment HTTP API or publishes to Kafka/JMS, a local JDBC inbox transaction does not cover external side effects. You may need API idempotency keys, transactional outbox, workflow state tracking, and reconciliation when timeouts hit near external commits.

Never claim end-to-end exactly-once solely because DLX, durable queues, or AUTO/MANUAL ACK are enabled.

## 19. Common Operational Issues and Diagnostics

| Symptom | Likely Cause | What to Check |
| --- | --- | --- |
| Bad message loops rapidly | `NACK requeue=true`; missing retry limit/backoff | Requeue logs, error classification, broker redelivery |
| Messages rejected yet DLQ empty | Missing DLX, wrong binding, missing permissions, target queue issue | Live topology, broker logs, routing key |
| Messages hit DLQ too fast | `defaultRequeueRejected=false` without transient retries | Exception classes, retry advice, downstream health |
| Ready queue growing steadily | Slow/offline consumers; downstream bottleneck | Consumer count, ACK rate, handler latency |
| High unacked count | Slow handlers, sleeping `RetryTemplate`, missing ACKs | Prefetch, thread dumps, DB latency, MANUAL ACK |
| DLQ spikes after deploy | Schema/`MessageConverter` mismatch | `contentType`, `schemaVersion`, DTO compatibility |
| DLQ messages cycle back to main | TTL/DLX retry loop missing termination | Retry topology, `x-death`, attempt budget |
| Publish confirms OK yet consumer silent | Misrouted or consumer failing | Returns, queue ready/unacked, consumer DLQ |
| Duplicates after restart | Redelivery/producer retry | Inbox unique constraint, transaction order |
| Retry queue returns messages late | TTL semantics, queue load, mixed TTLs | Queue policy, expiration, broker metrics |
| `PRECONDITION_FAILED` on startup | Queue bean `x-arguments` differ from existing queue | Policy, queue type, DLX arguments, migration |

### 19.1. How to Diagnose a Disappearing Message

Ask in sequence:

1. Which **exchange and routing key** did the producer publish to?
2. Were there matching **publisher confirms/returns**?
3. Did the broker have a **binding** to the main queue at that moment?
4. Did the delivery reach a consumer, and was there an **ACK/NACK/reject**?
5. If rejected without requeue, which DLX was active on the main queue?
6. Did the DLX route to the DLQ, and does the DLQ have TTL/overflow policies?
7. If replayed, what was the `eventId`, and did the consumer skip it as a duplicate?

Never start by "adding more consumers" before knowing whether the message was lost **pre-route**, **at consumer ACK**, or **during dead-lettering**.

### 19.2. Confirming Business State

A message sitting in a DLQ usually means **main-path processing did not succeed**, though you must verify against policy—it does not automatically prove business data rolled back. If a handler committed the DB and failed before ACK, the broker can redeliver and later dead-letter it on a secondary error. Reconcile using **`eventId`/business state**, not just where the message currently sits.

## 20. Observability, Alerting, and DLQ Ownership

A system with a DLQ that nobody watches, with no retention policy and no replay process, still drifts into business inaccuracy over time.

| Layer | Metrics to Monitor | Question Answered |
| --- | --- | --- |
| Producer | Publish attempts, confirms, returns, unknown outcomes | Did messages enter the broker and route? |
| Main queue | Ready, unacked, oldest age, consumer count | Are consumers keeping pace? |
| Consumer | ACK/NACK/reject/requeue, handler latency, error classes | Why are messages failing? |
| Retry | Attempt count, retries exhausted, backoff duration, delayed queue depth | Too many retries or excessive waits? |
| DLX/DLQ | Dead-letter ingress, DLQ depth/age, DLQ replay rate | How many messages need investigation? |
| Database/inbox | Commits, rollbacks, duplicates ignored, payload conflicts | Are business side effects accurate? |
| Runtime | Connections/channels, threads, memory, GC, reconnects | Resource saturation or connectivity issues? |

**Exact metric names** depend on RabbitMQ management, Spring AMQP, Micrometer, and application instrumentation. The table lists observability requirements, not a promise that frameworks emit those exact metric names automatically.

### 20.1. Safe Logging for Failed Messages

~~~text
queue=orders.created.q
eventId=evt-1001
eventType=ORDER_CREATED
schemaVersion=1
errorCategory=INVALID_SCHEMA
retryable=false
disposition=REJECT_NO_REQUEUE
deadLetterTarget=orders.created.dlq
~~~

**`disposition=REJECT_NO_REQUEUE`** only says code chose to reject. It **does not prove the DLQ retained the message**. Verify delivery via broker metrics/topology and end-to-end tests. Never log full payloads containing PII, payment details, tokens, or credentials.

### 20.2. DLQ Triage and Replay Procedure

1. Identify the queue owner, response SLA, and stored data classification.
2. Categorize root causes: schema, business rules, downstream outages, permissions, topology.
3. Check whether `eventId` already completed business side effects partially or fully.
4. Fix the root cause before replaying.
5. Replay test messages or a small controlled batch while keeping `eventId` intact.
6. Monitor duplicate skips, business successes, retries, and new DLQ arrivals.
7. Audit who replayed, when, why, and the outcome.

**Never auto-replay the entire DLQ back to the main queue every minute** while data remains invalid; that turns the DLQ into an uncontrolled infinite retry loop.

### 20.3. DLQ Security

Dead-letter messages usually retain business bodies. Protect:

- DLQ read permissions by vhost/ACL.
- TLS on transport connections.
- Retention, backup, and sensitive-data deletion policies.
- Authorization to replay or export messages.
- Masking when displaying payloads in dashboards and logs.

A DLQ holding failed payloads for days can retain sensitive data that primary consumers only touch briefly. Include DLQs in security and compliance reviews.

## 21. Pre-Production Integration Test Matrix

You cannot prove DLX/requeue behavior solely with a unit test mocking a service activator. You need a **real RabbitMQ broker in a test environment** (such as a dedicated test broker or Testcontainers), properly provisioned topology, and realistic broker/consumer failure tests.

| Test Case | Action to Inject | Outcome to Verify |
| --- | --- | --- |
| **Normal success** | Publish valid event | Business transaction commits, ACKed, absent from DLQ |
| **Invalid payload** | Publish contract-violating text | No hot retry; rejected without requeue and lands in DLQ when routed |
| **Transient recovers on attempt 2** | Repository fails attempt 1, succeeds attempt 2 | `RetryTemplate` retries, listener ACKs, absent from DLQ |
| **Transient exhausts retries** | Repository fails all 3 attempts | Rejected without requeue, lands in DLQ, `retry exhausted` metric recorded |
| **Missing DLX** | Declare source queue pointing to nonexistent DLX in test | Message fails to reach DLQ; topology error surfaced |
| **DLX exists, wrong binding** | Dead routing key matches no binding | Message misses target queue; do not assume DLX alone suffices |
| **Hot requeue** | `NACK requeue=true` with failing handler in short test | Rapid redeliveries demonstrating need for bounded retries |
| **Forgotten Manual ACK** | MANUAL consumer skips settlement in isolated test | Unacked rises toward prefetch; new deliveries throttled |
| **Consumer crash before DB commit** | Kill process mid-transaction | DB rolls back; broker can redeliver |
| **Consumer crash after DB commit** | Kill before ACK | Redelivery occurs; inbox blocks duplicate side effects |
| **Producer sends duplicate `eventId`** | Publish same `eventId` twice | Business side effect runs once |
| **Converter error before handler** | Unparseable JSON, handler never invoked | Listener error handler handles cleanly without hanging forever |
| **`errorChannel` absorbs exception** | Error flow logs and returns | Detects unintended ACK/missing NACK if present |
| **`ExecutorChannel`** | Offload work to another thread | Verify ACK boundary; no lost work after premature ACK |
| **TTL retry queue** | Publish to retry queue | Message returns to main after delay without requiring millisecond precision |
| **Retry cycle** | Route permanently failing event through retry topology | Terminates in final DLQ |
| **Multi-tier retry** | Test 2 or 3 backoff tiers | Attempts counted accurately across restarts and republishes |
| **DLQ overflow/TTL** | Configure limiting policy on test broker | Observe conditions where DLQ keeps vs. drops messages |
| **Multiple consumers** | Run 2–4 consumers on same queue | Competing consumers, not broadcast |
| **Graceful shutdown** | Stop app with unacked deliveries | Recovers cleanly without falsely reporting business completion |
| **Quorum queue delivery limit** | Configure compatible queue type/version | Dead-lettered once limit exceeded per live policy |
| **Security** | Connect with under-privileged account | ACL/configure/read/write error surfaced without leaking data |
| **DLQ replay** | Replay partially processed event | `eventId` preserved; idempotency guards side effects |

### 21.1. Unit Testing Service and Retry

A unit test can stub the repository:

~~~text
Given: valid event evt-1001
When : repository throws TransientOrderException on attempt 1
       and succeeds on attempt 2
Then : RetryTemplate returns success
       OrderProcessingService completes transaction
       handler does not request reject-not-requeue
~~~

Another test:

~~~text
Given: event missing orderId
When : parser throws InvalidOrderEventException
Then : RetryTemplate does not retry further
       handler requests reject-not-requeue
~~~

This only tests **application logic**. It does not prove the broker has a DLX, `x-death`, or bindings. Run integration tests against RabbitMQ to verify messages actually arrive in **`orders.created.dlq`**.

### 21.2. Post-DB-Commit Crash Scenario

~~~mermaid
sequenceDiagram
    participant Q as RabbitMQ queue
    participant L as Warehouse listener
    participant S as Business service
    participant DB as Warehouse DB
    Q->>L: Delivery eventId=evt-1001
    L->>S: process(evt-1001)
    S->>DB: Insert inbox + update order
    DB-->>S: Commit
    Note over L: Process crash before broker receives ACK
    Q-->>L: Redelivery after consumer recovery
    L->>S: process(evt-1001) again
    S->>DB: Inbox detects duplicate
    DB-->>S: No repeated business mutation
    L-->>Q: ACK
~~~

This test proves **business recoverability**, rather than merely checking Java method invocation counts in a single JVM. Control the exact crash/connection-close moment and inspect DB state after restart.

### 21.3. Publisher-Side Unroutable Failures

Do not place a test that **publishes to an exchange with no matching binding** under "consumer DLQ." Messages that never enter the main queue are never rejected by consumers. In tests, verify **publisher returns/mandatory** or alternate exchanges as configured rather than expecting them in the consumer's DLQ.

### 21.4. Isolate Test Data

Never publish malformed payloads into production queues. When running integration tests, use test queues/vhosts, prevent stray consumers from stealing messages, avoid deleting production queues, and ensure tests do not use overly broad administrative credentials.

## 22. Design Scenario: Combining DLQ and Bounded Retries

An e-commerce platform processes `OrderCreated`, while downstream Warehouse faces two failure modes:

- **Invalid `schemaVersion` or invalid `totalVnd`:** requires investigation, no retries.
- **Database timeouts lasting a few minutes:** should retry slowly without causing a requeue loop.

A viable design:

~~~mermaid
flowchart TD
    MQ["orders.created.q"] --> C["Warehouse consumer"]
    C --> V{"Validate payload"}
    V -->|"Permanent error"| FD["Final DLQ<br/>orders.created.dlq"]
    V -->|"Valid"| DB{"DB transaction"}
    DB -->|"Commit succeeds"| ACK["ACK"]
    DB -->|"Transient error"| SHORT["Short local retry"]
    SHORT -->|"Recovers"| ACK
    SHORT -->|"Not yet recovered"| B{"Retry budget left?"}
    B -->|"Yes"| RQ["Durable retry queue/job<br/>delay + nextAttempt"]
    RQ --> MQ
    B -->|"Exhausted"| FD
~~~

### 22.1. Decisions to Lock Down

| Question | Recommended Choice to Verify |
| --- | --- |
| Condition to consider processed? | DB transaction commits with consistent inbox state |
| Where do permanent errors go? | Final DLQ with ownership, alerts, manual replay |
| How do transient errors retry? | Brief local retries, then bounded delayed retries |
| Where are total attempts stored? | Durable inbox/job store or verified broker mechanism |
| Required before ACKing original? | Business commit or durable handoff of retry copy |
| When republish is `UNKNOWN`? | Preserve state; retry idempotently with original `eventId` |
| If retry queue fills up? | Alert/backpressure; never silently mark complete |
| When consumer crashes? | Redelivery with same `eventId`, duplicate-safe |
| When DLQ fills or retention ends? | Monitor capacity and data-handling policy |
| Who has permission to replay? | Authorized operator/service with audit trail |

### 22.2. Do Not Apply One DLX Pattern to Every Problem

A message may traverse:

~~~text
RabbitMQ exchange
  -> main queue
  -> listener
  -> service activator
  -> downstream database
~~~

**Failures at each boundary require distinct policies:**

- Exchange cannot route: publisher returns / alternate exchange.
- Consumer receives but converter fails: listener error handler, reject, and DLQ.
- Transient DB failure: bounded retry/backoff.
- Business rule rejection: final error state or DLQ if contract dictates.
- Network drop near ACK: redelivery/idempotency.
- Republish to retry exchange fails: confirms/returns/outbox or durable state.

A single DLX cannot solve all of these failure modes by itself.

### 22.3. One Event for Multiple Services

If both Warehouse and Analytics need `OrderCreated`, give them **two separate queues** bound to `orders.events`. Each consumer group should maintain its own retry/DLQ policies. A Warehouse DB outage should not halt Analytics consumption, and an Analytics DLQ replay must not touch Warehouse's inbox.

## 23. Common Mistakes

**"DLX and DLQ are the same resource."** DLX is the routing exchange; DLQ is the queue receiving messages via a binding.

**"Setting `x-dead-letter-exchange` is enough to save failed messages."** You also need an existing DLX, matching routing key/binding/target queue, and proper durability guarantees.

**"`NACK requeue=true` routes to the DLQ."** No; requeue can redeliver rapidly with no built-in backoff.

**"`NACK requeue=false` guarantees zero message loss."** Without an existing DLX and valid route, messages are discarded instead of entering a DLQ.

**"Publisher return is dead-lettering."** Returns report unroutable publishes at the exchange; dead-lettering occurs later inside a queue when conditions match.

**"Every error should requeue to avoid data loss."** Permanent schema errors cause infinite hot loops; classify errors.

**"`RetryTemplate maxAttempts=3` caps total executions across every redelivery."** It only bounds one in-process pass; restarts or republishes start fresh passes.

**"A TTL retry queue guarantees delivery after exactly 30 seconds."** TTL/dead-letter timing depends on broker/queue mechanics, not exact per-message timers.

**"A retry queue automatically separates transient from permanent errors."** Classification belongs in the listener/application or intentionally designed topology.

**"RabbitMQ always breaks dead-letter cycles at the exact desired attempt count."** Never rely on that; enforce retry budgets and a final DLQ.

**"`x-death` count equals total service executions."** In-listener retries, republishes, and mixed dead-letter reasons make `x-death` counts differ from business attempts.

**"Consumer ACK proves the database transaction committed."** Early ACKs can happen before DB commits; align the ACK boundary explicitly.

**"Having a DLQ removes the need for idempotency."** Crashes between DB commit and ACK, as well as DLQ replays, can still produce duplicates.

**"Setting `defaultRequeueRejected(false)` creates a DLQ automatically."** It only alters requeue behavior in certain container error paths; topology must be provisioned separately.

**"JSON errors always reach the service activator."** Converters can fail before Spring Messages are ever constructed.

**"`errorChannel` logging and returning still triggers NACK."** Error flows can swallow exceptions, making the listener appear successful; verify actual ACK/NACK.

**"Switching DirectChannel to ExecutorChannel does not affect ACK."** Async handlers can fail after the container already ACKed.

**"An in-memory `QueueChannel` is a durable retry queue."** Without a durable `MessageStore`, it lacks the durability of broker queues or database inboxes.

**"Changing `QueueBuilder` arguments and restarting updates an existing main queue."** Expect `PRECONDITION_FAILED`; plan compatible migrations or policies.

**"Quorum queues automatically provide full at-least-once dead-letter guarantees."** Specific queue type, broker version, and feature configuration are required.

**"DLQs need no monitoring because messages are safe."** DLQs can overflow, expire via TTL, get replayed recklessly, or retain sensitive data.

**"All consumers on the main queue receive every event."** They normally compete for deliveries; cross-system broadcast needs separate queues.

**"Calling `basicAck` on another channel works if you know the delivery tag."** Tags are scoped strictly to their origin channel; ACKing on the wrong channel causes protocol errors.

**"You can ACK the original as soon as republishing to the retry queue begins."** If the retry publish fails or goes `UNKNOWN`, the event can be lost; establish a durable handoff milestone first.

## 24. Self-Check Questions

1. How do a dead-letter exchange and a dead-letter queue differ? Why must the DLX have a binding to the DLQ?
2. What happens to a message from `orders.created.q` after `basicReject(tag, false)` when a valid DLX exists? What happens when the DLX does not exist?
3. How do `basicNack(tag, false, true)` and `basicNack(tag, false, false)` differ?
4. Why should `requeue=true` not be treated as a backoff retry mechanism?
5. At which stage of the message path does a publisher return differ from consumer reject/dead-lettering?
6. Besides consumer rejection, what are the common reasons RabbitMQ dead-letters a message?
7. How does message TTL differ from expiration of the queue itself?
8. Can the dead-letter routing key differ from the original business routing key? Why preserve `eventType`/`eventId`?
9. In `OrdersDlxTopology`, which exchanges, routing keys, and queues does a failed message traverse?
10. Why does a Queue bean declaring a DLX not prove the broker already has the bound destination queue?
11. When should you prefer RabbitMQ policies over hardcoded `x-arguments` on `QueueBuilder`?
12. If the broker reports `PRECONDITION_FAILED` while declaring a queue, which settings do you inspect first?
13. Under Spring AMQP `AcknowledgeMode.AUTO`, who owns ACK, and when can a handler exception trigger rejection?
14. Does `setDefaultRequeueRejected(false)` create a DLQ on its own? What must it pair with?
15. How many processing invocations does `RetryTemplate.maxAttempts(3)` cover in one retry loop?
16. If the DB fails twice and succeeds on attempt 3, should the delivery be ACKed or routed to the DLQ?
17. For permanent schema errors, why avoid retrying three times and then requeuing indefinitely?
18. In Spring Integration, is a `MessageConverter` error occurring before Spring Message creation guaranteed to enter the flow handler?
19. If `errorChannel` absorbs an exception and returns normally, how can ACK/NACK outcomes change?
20. How do DirectChannel and ExecutorChannel differ regarding listener completion timing and AUTO ACK?
21. Why can a delivery tag not serve as an `eventId`, and why can it not be ACKed on another channel?
22. How is a TTL retry queue wired so messages return to the main queue?
23. Does configuring a TTL retry queue automatically separate transient errors from errors destined for the final DLQ?
24. Why must a **main queue → retry queue → main queue** loop have a termination condition?
25. What diagnostics does `x-death` provide? Why not use one count field as total business attempts?
26. If the process crashes after DB commit but before ACK, what happens and how does an idempotent consumer protect state?
27. Why does a transactional inbox need a unique constraint when multiple consumers share a queue?
28. When a consumer republishes to a retry exchange, why wait for publisher confirms/returns before ACKing the original delivery?
29. Which conditions can prevent a dead-lettered message from showing up in the DLQ as expected?
30. When can a quorum queue offer different dead-letter guarantees than a classic queue? What must be checked?
31. Which metrics distinguish a requeue loop, slow downstream services, and DLQ growth from schema mismatches?
32. Why does a message appearing in the DLQ not prove database side effects definitely never occurred?
33. If both Warehouse and Analytics need `OrderCreated`, how should queues and DLQs be designed per system?
34. When replaying from a DLQ, should you keep `eventId` or generate a new one? Should payload conflicts be checked?
35. Which tests prove manual/auto ACK, dead-letter routing, and DB commits truly work under connection failures?

## Summary

A **dead-letter exchange (DLX)** is a **RabbitMQ exchange** that routes dead-lettered messages from source queues; a **dead-letter queue (DLQ)** is a queue bound to receive those messages. Common triggers include **consumer reject/NACK with `requeue=false`**, **message TTL expiration**, certain queue overflow limits, and **delivery limits** on supported queue types. A DLX does not create destination queues automatically, does not replace publisher returns, and does not guarantee zero message loss across every configuration.

**`requeue=true`** can make the broker redeliver immediately rather than adding delay or attempt limits. Reliable retries require **error classification, backoff, retry budgets**, and a termination point such as a **final DLQ**. When using **TTL retry queues**, design ingress to the retry queue, return paths to the main queue, and loop prevention; when republishing to another queue, distinguish confirmation of the new publish from ACKing the original delivery.

In **Spring Integration**, the AMQP inbound channel adapter passes deliveries from a Spring AMQP listener container into a **MessageChannel**; service activators execute business logic, while **`AcknowledgeMode.AUTO/MANUAL`**, error handlers, and exception propagation govern ACK/NACK. Choices around **DirectChannel vs. ExecutorChannel, MessageConverters, prefetch, transactions, lifecycle, and `errorChannel`** shift processing boundaries and must be verified against a real broker.

Ultimately, a reliable design needs more than a DLQ: it requires **stable `eventId`s, idempotent consumers, unique constraints/inboxes, reconciliation for uncertain states, ready/unacked/retry/DLQ monitoring, security, and owned replay procedures**. Following these principles enables isolating malformed data, retrying safely, and recovering when RabbitMQ or downstream services fail—without confusing **message delivered**, **message dead-lettered**, and **business logic completed**.
