# Queue, Exchange, Binding, and Routing Key

## Learning Objectives

After this lesson, you will be able to:

- Explain the exact roles of **queue**, **exchange**, **binding**, and **routing key** in RabbitMQ/AMQP 0-9-1.
- Distinguish **direct**, **topic**, **fanout**, **headers**, and **default exchange** types, and predict which queues receive a publish.
- Design topology for cases where multiple systems need the same event or multiple workers share work from one queue.
- Declare exchanges, queues, and bindings via **Spring AMQP**, then connect them to **Spring Integration AMQP inbound/outbound adapters** and **MessageChannels**.
- Analyze **unroutable** messages, publisher confirms/returns, mandatory, alternate exchanges, dead-letter exchanges, and consumer acknowledgment.
- Evaluate durability, security, permissions, connection lifecycle, retries, idempotency, and observability for production deployment.

## 1. Why Understand Topology Before Using AMQP Adapters?

Suppose the ordering system emits an **OrderCreated** event. The warehouse service needs to update inventory; the analytics service needs to record statistics; meanwhile, a pool of payment workers has its own job queue. If the producer only knows a queue name and does not understand exchanges/bindings, it is very easy to misconfigure **consumers competing on the same queue** instead of **each service receiving a copy**.

RabbitMQ uses this routing model:

~~~mermaid
flowchart LR
    P["Producer / RabbitTemplate"] -->|"basic.publish<br/>exchange + routing key"| X["RabbitMQ exchange"]
    X -->|"Binding A"| Q1["Queue: warehouse"]
    X -->|"Binding B"| Q2["Queue: analytics"]
    Q1 --> C1["Warehouse consumer"]
    Q2 --> C2["Analytics consumer"]
~~~

In a Spring Integration application, the flow typically runs as follows:

~~~text
Service activator / Transformer
  -> Spring MessageChannel
  -> AMQP outbound channel adapter
  -> RabbitTemplate / ConnectionFactory
  -> RabbitMQ exchange
  -> matching binding
  -> RabbitMQ queue
  -> Spring AMQP listener container
  -> AMQP inbound channel adapter
  -> Receiving Spring MessageChannel
~~~

Key distinctions:

- **MessageChannel** is a message delivery channel **inside the Spring application**.
- **RabbitMQ queue** is a resource **on the broker** holding messages routed to it.
- **Exchange** makes routing decisions, not where normal consumers pull messages from.
- **Binding** describes the relationship between an exchange and a queue.
- **Routing key** is the value attached by the publisher to each publish so the exchange can apply routing rules.

A flow may use HTTP, SFTP, JMS, Kafka, files, or databases at other boundaries; however, when crossing AMQP, RabbitMQ's rules for exchanges, queues, and routing keys still apply.

## 2. Four Core Concepts

| Concept | Where It Lives | Primary Role | What It Does **Not** Do Automatically |
| --- | --- | --- | --- |
| **Queue** | RabbitMQ broker | Holds routed messages awaiting delivery to consumers | Automatically copy every message to every consumer |
| **Exchange** | RabbitMQ broker | Receives publishes and selects destinations by exchange type and bindings | Store messages by default like a queue |
| **Binding** | RabbitMQ broker | Connects an exchange to a queue under routing conditions | Create a business ACK or transaction |
| **Routing key** | Attribute of a publish operation | Supplies the value evaluated by the exchange for routing | Create queues or replace a business event ID |

### 2.1. Producers Publish to an Exchange

In AMQP 0-9-1, producers publish with key parameters:

~~~text
basic.publish(
  exchange = "commerce.events",
  routingKey = "orders.created",
  properties = ...,
  body = bytes
)
~~~

**Exchange name** names a broker resource; **routing key** is the string evaluated during routing. **Body** and **message properties** have their own serialization contract, such as contentType, correlationId, and messageId.

When using Spring AMQP:

~~~java
rabbitTemplate.convertAndSend(
    "commerce.events",
    "orders.created",
    "evt-1001|O-1001|150000");
~~~

RabbitTemplate converts the payload into an AMQP message using its MessageConverter and publishes to the named exchange. This call does not automatically prove the message reached any queue or that a consumer processed it.

### 2.2. Queues Are Where Consumers Receive Deliveries

Consumers normally subscribe to a **queue**, not directly to an exchange. When multiple consumers consume from the same queue, they typically **split deliveries** among themselves; the broker can redeliver unacked messages if a consumer fails.

If two independent systems both need OrderCreated, create **two queues** and bind both to the exchange. If one system wants multiple worker instances to share load, run **multiple consumers on the same queue**.

### 2.3. One Exchange Can Route to Multiple Queues

A single publish can match multiple bindings and reach multiple distinct queues. For a single queue with multiple matching bindings, RabbitMQ does not necessarily create multiple copies of the message in that same queue just because multiple bindings matched.

The exchange–queue relationship **is not necessarily 1-to-1**:

- One exchange can bind to many queues.
- One queue can bind to many exchanges.
- One exchange can have many bindings with different binding keys.
- Deleting a binding does not delete the queue; deleting a queue stops related bindings from routing to that queue.

## 3. Exchange Types and Routing Rules

RabbitMQ supports these common exchange types:

| Exchange Type | How Route Is Decided | Appropriate Example |
| --- | --- | --- |
| **Direct** | Routing key must exactly match the binding key | Dispatching commands by type or logical queue name |
| **Topic** | Routing key is matched against dot-separated binding patterns | Domain events: orders.created, orders.cancelled |
| **Fanout** | Broadcasts to all bound queues, ignoring routing key | Broadcasting notifications to multiple subscriber groups |
| **Headers** | Matches on message headers and binding criteria instead of routing key patterns | Routing based on metadata attributes |
| **Default exchange** | Predefined nameless direct exchange where every queue is auto-bound by queue name | Simple send to a named queue |

### 3.1. Direct Exchange: Exact Match

Suppose direct exchange **operations.direct** has two bindings:

~~~text
operations.direct -- key = "payments.charge" --> payments.charge.q
operations.direct -- key = "payments.refund" --> payments.refund.q
~~~

Publishing with routing key **payments.charge** reaches the charge queue; **payments.refund** reaches the refund queue. Routing key **payments.charge.priority** does not match binding **payments.charge**, because a direct exchange does not interpret topic wildcards.

~~~mermaid
flowchart LR
    P["Publisher"] --> X["Direct exchange<br/>operations.direct"]
    X -->|"payments.charge"| A["payments.charge.q"]
    X -->|"payments.refund"| B["payments.refund.q"]
~~~

If two queues bind to a direct exchange with the **same binding key**, a matching publish can route to both queues. Direct exchange **does not mean** only one queue may receive.

### 3.2. Topic Exchange: Pattern-Based Routing

A topic exchange is useful for events with multiple subtypes. **Routing keys** typically consist of dot-separated words:

~~~text
orders.created
orders.cancelled
orders.created.priority
payments.refunded
~~~

In a **topic exchange binding key**:

- **\*** matches **exactly one word**.
- **#** matches **zero or more words**.
- **.** separates words.

Examples:

| Binding key | orders.created | orders.cancelled | orders.created.priority | payments.refunded |
| --- | :---: | :---: | :---: | :---: |
| **orders.created** | Yes | No | No | No |
| **orders.\*** | Yes | Yes | No | No |
| **orders.#** | Yes | Yes | Yes | No |
| **#.created** | Yes | No | No | No |
| **payments.#** | No | No | No | Yes |
| **#** | Yes | Yes | Yes | Yes |

Note: binding **orders.\*** does not match **orders.created.priority** because it has three words. By contrast, **orders.#** matches both **orders.created** and **orders.created.priority**.

Architecture example:

~~~mermaid
flowchart TD
    P["Publisher"] --> X["Topic exchange<br/>commerce.events"]
    X -->|"orders.created"| W["warehouse.orders.q"]
    X -->|"orders.#"| A["analytics.orders.q"]
    X -->|"payments.#"| F["finance.payments.q"]
~~~

An **orders.created** event reaches both warehouse and analytics. **orders.cancelled** reaches only analytics under these three bindings; **payments.refunded** reaches only finance.

**\*** and **#** have special meaning in **topic exchange binding patterns**, not expressions to put into a producer's routing key. On a direct exchange, these characters do not create wildcard matching.

### 3.3. Fanout Exchange: Ignores Routing Key

A fanout exchange forwards publishes to all bound queues regardless of routing key:

~~~mermaid
flowchart TD
    P["Publisher"] --> X["Fanout exchange<br/>system.notifications"]
    X --> Q1["email.notifications.q"]
    X --> Q2["mobile.notifications.q"]
    X --> Q3["audit.notifications.q"]
~~~

Suitable when **every subscribed system** must receive the same notification type. It does not mean every user or every running consumer receives a copy: messages still go to **queues**, and multiple consumers on the same queue share deliveries.

### 3.4. Headers Exchange: Routing by Properties

A headers exchange inspects a set of message headers and binding criteria, typically with **x-match = all** or **x-match = any**:

- **all:** requires all specified header conditions to match.
- **any:** requires at least one specified header condition to match.

Illustrative example: an invoice-processing queue bound with **documentType=invoice** and **region=apac**. To use this properly, define how producers map headers to AMQP properties, header data types, and permissions. Do not pick a headers exchange just because Spring Messages have many headers: most internal headers are not automatically sent to the broker.

### 3.5. Default Exchange: Special Case

RabbitMQ has a **default direct exchange** whose exchange name is the **empty string**. Every ordinary queue is automatically bound by RabbitMQ to the default exchange with a routing key equal to the **queue name**.

~~~java
rabbitTemplate.convertAndSend(
    "", "orders.created.q", "evt-1001|O-1001");
~~~

This call publishes through the default exchange and routes by queue name. That is why code sometimes appears to pass only a queue name and still succeeds. However:

- This is still **publishing to an exchange** (empty name), not an API sending directly into a Queue object.
- Do not generalize the default-exchange pattern to named exchanges.
- When routing to multiple destinations, prefer named direct/topic/fanout exchanges with explicit bindings.
- Do not try to alter default bindings by treating the default exchange as an application-owned named exchange.

## 4. Queue Properties and Topology Durability

Queue creation determines many characteristics of the receiving path:

| Property | Meaning | Considerations |
| --- | --- | --- |
| **name** | Queue identifier within a virtual host | Keep stable; do not confuse with routing key |
| **durable** | Queue survives broker restarts per supported mechanism | Does not guarantee individual messages are persistent |
| **exclusive** | Queue tied to its owning connection, inaccessible to other connections per broker rules | Useful for temporary client queues, unsuitable for shared queues |
| **autoDelete** | Queue is deleted when broker auto-delete conditions are met | Do not use arbitrarily for queues that must retain backlog |
| **arguments/policy** | TTL, DLX, max length, queue type, and special behaviors | Coordinate with operations team |
| **queue type** | Classic/quorum or other broker-supported type | Affects availability, durability, and cost |

**A durable queue does not automatically make messages persistent.** Reliability also depends on message delivery mode, queue type, broker policies, publisher confirms, consumer acknowledgment, and business-layer deduplication.

### 4.1. Quorum Queue or Classic Queue?

RabbitMQ provides multiple queue types with different guarantees, performance, and trade-offs. **Quorum queues** use quorum-based replication and are commonly considered when appropriate node fault tolerance is needed; classic queues have different management and load characteristics. Choose based on infrastructure, cluster size, SLA, retention, throughput, and recommendations for your deployed RabbitMQ version. Never infer "quorum queues can never lose data" or "all classic queues are unsafe."

### 4.2. Durable Queue, Durable Exchange, and Persistent Message

Consider three independent choices:

1. **Durable exchange**: persistence configuration of the routing resource.
2. **Durable queue**: persistence configuration of the storage resource.
3. **Persistent delivery mode**: message property supporting durable storage per broker/queue-type policy.

Even when all three are configured, you still need publisher confirms and recovery strategies for network timeouts, publisher crashes, and duplicate consumer side effects. Never promise **end-to-end exactly-once** based on a single queue attribute.

## 5. Bindings, Topology, and Multiple Consumer Groups

### 5.1. Competing Consumers on One Queue

~~~text
orders.created.q
  ├── warehouse-worker-1
  └── warehouse-worker-2
~~~

Two workers typically share load: each delivery goes to one consumer at a time per protocol and can be redelivered if unacked. This suits **scaling out one processing group**, not cases where each worker represents a distinct system that must receive every event.

### 5.2. One Queue per System

~~~text
commerce.events (topic)
  ├── key orders.# --> analytics.orders.q --> Analytics
  └── key orders.created --> warehouse.orders.q --> Warehouse
~~~

One OrderCreated is routed by the broker into **both queues**. Each queue has its own backlog, consumer count, retries, and ACK policy. When warehouse goes down, analytics can continue receiving and processing messages from its own queue.

### 5.3. One Queue Can Receive from Multiple Exchanges

A queue can bind to exchanges from multiple event sources. If you design it this way, standardize payload/schemaVersion and metadata so consumers know which event type arrived. Do not mix incompatible formats assuming a single handler can parse everything.

### 5.4. Naming and Ownership

Follow a consistent convention:

- Exchange names reflect a domain or routing group, e.g., **commerce.events**.
- Routing keys reflect the event type, e.g., **orders.created**.
- Queue names reflect the **consumer/receiving group**, e.g., **warehouse.orders.q**.
- Dead-letter queues reflect source and policy, e.g., **warehouse.orders.dlq**.

These are suggested conventions, not RabbitMQ rules. What matters is clear ownership so producers do not accidentally delete or alter queues owned by another service.

## 6. Journey of a Message and Four Types of Outcomes

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant X as RabbitMQ exchange
    participant Q as Queue
    participant C as Consumer
    P->>X: publish(exchange, routing key, body)
    alt Binding matches
      X->>Q: Route message
    else No matching route
      X-->>P: Return if mandatory and conditions met
    end
    X-->>P: Publisher confirm ACK/NACK if enabled
    Q-->>C: Delivery when consumer receives
    C-->>Q: Consumer ACK/NACK depending on mode
~~~

| Signal | Emitter | What It Tells You | What Cannot Be Concluded |
| --- | --- | --- | --- |
| **Publisher confirm** | Broker → publisher | Broker confirms publish status under confirms mechanism | Consumer completed business processing |
| **Publisher return** | Broker → publisher | Message was unroutable while mandatory/returns were active | Consumer handler threw an error |
| **Consumer ACK/NACK** | Consumer → broker | Confirmation status of a delivery | Caller received a business reply |
| **Business reply/event** | Receiving app → calling app | Business outcome per separate contract | Broker will never redeliver |

An **unroutable publish** can still receive a publisher confirm ACK because the broker processed the publish, even though no queue matched. To detect this, configure **mandatory** and **publisher returns**, or an alternative mechanism such as an alternate exchange per design.

### 6.1. Missing Exchange vs. Missing Binding

- **Missing exchange:** publishing to a nonexistent exchange can trigger protocol/channel errors or exceptions, not necessarily a returned message.
- **Exchange exists but no route:** the message can be **unroutable**; use mandatory/returns or an alternate exchange to avoid silent drops.
- **Queue exists but listener is stopped:** messages wait in the queue; this is not a routing error.
- **Listener runs but handler fails:** that is a post-delivery consumer failure requiring ACK/NACK/retry/DLQ, distinct from a producer publish error.

### 6.2. Routing Key Is Not an Idempotency Key

**orders.created** describes the event routing category; thousands of messages can share the same routing key. To prevent duplicate processing, use a stable **eventId** or business key. Never use a routing key, delivery tag, Kafka offset (in another system), or Spring MessageHeaders.ID instead of a business key.

## 7. Cross-System Scenario: OrderCreated, OrderCancelled, and PaymentRefunded

Requirements:

- Warehouse receives only **orders.created**.
- Analytics receives **all events in the orders domain**.
- Finance receives **all events in the payments domain**.
- The system can scale out workers per queue without sacrificing independence across groups.

Choose a topic exchange **commerce.events** with bindings:

| Queue | Binding pattern | Messages Received |
| --- | --- | --- |
| warehouse.orders.q | orders.created | Only orders.created |
| analytics.orders.q | orders.# | orders.created, orders.cancelled, orders.created.priority, ... |
| finance.payments.q | payments.# | payments.received, payments.refunded, ... |

**Expected routing matrix:**

| Published Routing Key | Warehouse | Analytics | Finance |
| --- | :---: | :---: | :---: |
| orders.created | Yes | Yes | No |
| orders.cancelled | No | Yes | No |
| orders.created.priority | No | Yes | No |
| payments.refunded | No | No | Yes |
| customers.created | No | No | No |

For **customers.created**, with no other binding and no alternate exchange, the message is **unroutable**; if mandatory is disabled, the publisher may not receive a returned message for it.

## 8. Declaring Topology with Spring AMQP

With Spring Boot, the AMQP stack typically uses:

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
</dependencies>
~~~

Use versions managed by a compatible **Spring Boot dependency management/BOM** rather than mixing arbitrary Spring Integration and Spring AMQP versions.

### 8.1. Java Configuration: Topic Exchange and Three Queues

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CommerceAmqpTopology {

    public static final String EXCHANGE = "commerce.events";
    public static final String WAREHOUSE = "warehouse.orders.q";
    public static final String ANALYTICS = "analytics.orders.q";
    public static final String FINANCE = "finance.payments.q";

    @Bean
    public TopicExchange commerceExchange() {
        return new TopicExchange(EXCHANGE, true, false);
    }

    @Bean
    public Queue warehouseOrdersQueue() {
        return QueueBuilder.durable(WAREHOUSE).build();
    }

    @Bean
    public Queue analyticsOrdersQueue() {
        return QueueBuilder.durable(ANALYTICS).build();
    }

    @Bean
    public Queue financePaymentsQueue() {
        return QueueBuilder.durable(FINANCE).build();
    }

    @Bean
    public Binding warehouseBinding(
            Queue warehouseOrdersQueue,
            TopicExchange commerceExchange) {
        return BindingBuilder.bind(warehouseOrdersQueue)
            .to(commerceExchange)
            .with("orders.created");
    }

    @Bean
    public Binding analyticsBinding(
            Queue analyticsOrdersQueue,
            TopicExchange commerceExchange) {
        return BindingBuilder.bind(analyticsOrdersQueue)
            .to(commerceExchange)
            .with("orders.#");
    }

    @Bean
    public Binding financeBinding(
            Queue financePaymentsQueue,
            TopicExchange commerceExchange) {
        return BindingBuilder.bind(financePaymentsQueue)
            .to(commerceExchange)
            .with("payments.#");
    }
}
~~~

The code creates **Spring beans describing topology**. Whether they are declared on the RabbitMQ broker depends on **RabbitAdmin/AmqpAdmin**, connectivity, permissions, and auto-declaration, or on prior provisioning by operations tooling.

### 8.2. Are Exchanges, Queues, and Bindings Created Automatically?

With Spring Boot/Spring AMQP, **RabbitAdmin** can declare exchange/queue/binding beans on the broker if enabled and the account has sufficient permissions. However:

- Creating Spring beans **does not guarantee** the topology already exists on the broker.
- The application may lack configure permissions because infrastructure manages topology externally.
- If the broker already has a queue/exchange with the same name but incompatible attributes, RabbitMQ may reject the declaration (e.g., **PRECONDITION_FAILED**, closing the channel).
- Changing durable, type, or arguments of an existing queue should not be treated as a simple app restart; it may require migration.
- Binding declarations require the exchange and queue to live in the same **virtual host**; topology is scoped per virtual host.

In production, decide explicitly **who owns topology**: self-declaration by the application when allowed, or management by a platform team via IaC/scripts. Avoid having both sides accidentally apply conflicting definitions.

### 8.3. Why Verify the Actual Broker Topology?

Proper tests do not merely check that Spring beans were created. Verify on the broker:

1. An exchange named **commerce.events**, type **topic**, durable per contract exists.
2. All three queues exist with the expected properties.
3. All three bindings have exact patterns.
4. The producer user has permission to publish to the exchange.
5. Consumer users have permission to read their respective queues.
6. All resources live in the virtual host the application actually connects to.

## 9. Publishing with RabbitTemplate: Where Is the Routing Key Chosen?

**RabbitTemplate** provides publish operations via Spring AMQP. In this example, one producer can emit different event types to the topic exchange:

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class CommerceEventPublisher {

    private final RabbitTemplate rabbitTemplate;

    public CommerceEventPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void orderCreated(String eventId, String orderId) {
        String payload = eventId + "|" + orderId + "|CREATED";
        rabbitTemplate.convertAndSend(
            CommerceAmqpTopology.EXCHANGE,
            "orders.created",
            payload);
    }

    public void orderCancelled(String eventId, String orderId) {
        String payload = eventId + "|" + orderId + "|CANCELLED";
        rabbitTemplate.convertAndSend(
            CommerceAmqpTopology.EXCHANGE,
            "orders.cancelled",
            payload);
    }

    public void paymentRefunded(String eventId, String paymentId) {
        String payload = eventId + "|" + paymentId + "|REFUNDED";
        rabbitTemplate.convertAndSend(
            CommerceAmqpTopology.EXCHANGE,
            "payments.refunded",
            payload);
    }
}
~~~

**Predicted routes:**

- **orderCreated:** warehouse and analytics.
- **orderCancelled:** analytics.
- **paymentRefunded:** finance.

In the example, payloads are simple strings to keep focus on routing. Production needs dedicated schemas for OrderCreated, OrderCancelled, and PaymentRefunded. Avoid sending sensitive data or concatenating delimited strings when values might contain delimiter characters.

### 9.1. Routing Key in Header or Configuration?

RabbitTemplate allows passing the routing key directly via **convertAndSend(exchange, routingKey, payload)**. With a Spring Integration outbound adapter, you can configure a **static** routing key or compute it per message using routing expression/header options supported by your DSL version.

Choose **static routing** if a flow serves a single event type. If **dynamic routing** is needed:

1. Standardize **eventType → routing key** through a controlled lookup table.
2. Never accept an arbitrary routing key directly from untrusted external client input.
3. Validate that allowed keys have corresponding bindings and consumers.
4. Carry event ID/schema version in the data contract; do not use routing key as event identity.
5. Test missing routing keys or keys that no longer have matching bindings.

### 9.2. MessageConverter Does Not Decide the Route

MessageConverter decides how payloads become AMQP body/properties. Exchange and routing key decide **where it goes**. For instance, the same JSON body could be published with **orders.created** or **orders.cancelled** and reach different queues. Consumers must validate both payload content and event semantics rather than trusting the routing key alone to skip validation.

## 10. Connecting Topology to Spring Integration Java DSL

A clean integration flow separates **business data creation** from **AMQP destinations**. MessageChannels transfer internal messages, and AMQP outbound adapters publish via RabbitTemplate. On the receiving side, AMQP inbound adapters use listener containers to consume from queues and push messages into MessageChannels.

~~~mermaid
flowchart LR
    P["OrderCreated producer"] --> OC["ordersToAmqp<br/>DirectChannel"]
    OC --> OA["AMQP outbound adapter"]
    OA --> EX["Topic exchange<br/>commerce.events"]
    EX --> WQ["warehouse.orders.q"]
    WQ --> IA["AMQP inbound adapter"]
    IA --> IC["warehouseOrders<br/>MessageChannel"]
    IC --> S["Warehouse service activator"]
~~~

### 10.1. Outbound Adapter with Static Routing Key

~~~java
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
public class CommerceAmqpOutboundFlow {

    @Bean
    public MessageChannel ordersToAmqp() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow publishOrderCreated(RabbitTemplate rabbitTemplate) {
        return IntegrationFlow.from("ordersToAmqp")
            .handle(Amqp.outboundAdapter(rabbitTemplate)
                .exchangeName(CommerceAmqpTopology.EXCHANGE)
                .routingKey("orders.created"))
            .get();
    }
}
~~~

Here, **ordersToAmqp** is the MessageChannel name, not a queue name. **Amqp.outboundAdapter(...)** receives the message and publishes it to the exchange with key orders.created. RabbitMQ decides to route the message to warehouse and analytics according to the two configured bindings.

### 10.2. Internal Producer Only Sends a Spring Message

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class OrderCreatedFlowPublisher {

    private final MessageChannel ordersToAmqp;

    public OrderCreatedFlowPublisher(
            @Qualifier("ordersToAmqp") MessageChannel ordersToAmqp) {
        this.ordersToAmqp = ordersToAmqp;
    }

    public void publish(String eventId, String orderId) {
        if (eventId == null
                || !eventId.matches("[A-Za-z0-9_-]{1,80}")
                || orderId == null
                || !orderId.matches("[A-Za-z0-9_-]{1,80}")) {
            throw new IllegalArgumentException(
                "Invalid eventId or orderId");
        }

        String payload = eventId + "|" + orderId + "|CREATED";
        boolean sent = ordersToAmqp.send(
            MessageBuilder.withPayload(payload)
                .setHeader("businessEventId", eventId)
                .build());

        if (!sent) {
            throw new IllegalStateException(
                "Failed to send message to channel");
        }
    }
}
~~~

Use **only one publishing path** per event: either CommerceEventPublisher calling RabbitTemplate directly, or OrderCreatedFlowPublisher sending into the Spring Integration outbound flow. **Do not call both** for the same event unless you intend duplicate publishes.

In this example, **businessEventId** sits in a Spring header for illustration; do not assume it is propagated into AMQP properties without configuring a header mapper. The business ID is also embedded in the payload for reliable reading by receivers.

**A successful DirectChannel.send() return does not guarantee the broker routed to every queue**, does not mean a publisher confirm arrived, and certainly is not a business ACK. Handle those requirements via producer tracking, confirms/returns, and reconciliation for critical events.

### 10.3. Inbound Adapter on the Warehouse Side

When the Warehouse system uses an AMQP inbound adapter, it consumes **warehouse.orders.q**, not directly from the topic exchange:

~~~java
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.amqp.dsl.Amqp;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class WarehouseAmqpInboundFlow {

    @Bean
    public MessageChannel warehouseOrders() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow warehouseInbound(ConnectionFactory connectionFactory) {
        return IntegrationFlow
            .from(Amqp.inboundAdapter(
                connectionFactory, CommerceAmqpTopology.WAREHOUSE))
            .channel("warehouseOrders")
            .get();
    }

    @Bean
    public IntegrationFlow inspectWarehouseOrders() {
        return IntegrationFlow.from("warehouseOrders")
            .handle(String.class, (payload, headers) -> {
                System.out.println("Warehouse received: " + payload);
                return null;
            })
            .get();
    }
}
~~~

**The outbound and inbound configurations can live in two separate applications.** This illustrates the cross-system contract rather than requiring a single JVM. If you are inspecting queue message counts with a pull tool, do not simultaneously run an inbound consumer reading that same queue; the consumer may drain messages before your inspection.

The inbound code assumes the converter produces a **String** payload because the sample producer sends a String. With JSON/bytes from another producer, verify the MessageConverter and actual body contract before expecting a String in the handler.

### 10.4. When to Use a Gateway?

The flows above are one-way. If the producer must receive a computed result from the receiving service to continue within the same interaction, you need an **AMQP outbound gateway** on the caller side and an **AMQP inbound gateway** on the provider side, or a dedicated request/reply workflow.

**Routing key** still determines the path of the AMQP request, while **reply-to/correlation** defines how the response returns to the caller. Producer confirms only acknowledge at the broker level; they cannot replace a gateway's business response.

## 11. Verifying Routing on RabbitMQ

To prove routing works, do not look only at a "sent" log line. Test against RabbitMQ in a test environment, verify actual topology, publish per routing key, and inspect the resulting queues.

### 11.1. Recommended Test Matrix

| Test | Exchange/Routing Key | Expected Queue(s) |
| --- | --- | --- |
| OrderCreated | commerce.events / orders.created | warehouse.orders.q, analytics.orders.q |
| OrderCancelled | commerce.events / orders.cancelled | analytics.orders.q |
| Urgent OrderCreated | commerce.events / orders.created.priority | analytics.orders.q |
| PaymentRefunded | commerce.events / payments.refunded | finance.payments.q |
| Unknown event | commerce.events / customers.created | None of the three queues; check unroutable handling |
| Wrong exchange name | commerce.missing / orders.created | Exchange-not-found error per broker/client behavior |
| Deleted binding | commerce.events / orders.created | Only queues with remaining matching bindings receive message |

### 11.2. A Verification Check Using RabbitTemplate in an Isolated Environment

Once topology is provisioned, you can use RabbitTemplate to publish and then pull from queues in **an integration test with no listener consuming those queues**:

~~~java
// Illustrative test; requires an injected rabbitTemplate and a test broker.
rabbitTemplate.convertAndSend(
    "commerce.events", "orders.created", "evt-1001|O-1001|CREATED");

Object warehouse = rabbitTemplate.receiveAndConvert(
    "warehouse.orders.q", 2000L);
Object analytics = rabbitTemplate.receiveAndConvert(
    "analytics.orders.q", 2000L);
Object finance = rabbitTemplate.receiveAndConvert(
    "finance.payments.q", 100L);

// warehouse and analytics expect the event string.
// finance expects null if the queue was empty before the test.
~~~

**receiveAndConvert** actually **removes the message from the queue** per RabbitTemplate semantics; it is not a non-destructive peek API. Run this check only on dedicated test queues, isolated data, or specifically named test topologies. In production, use management tools/metrics and properly authorized test consumers instead of pulling and consuming live business messages just to inspect.

### 11.3. Testing Multiple Consumers on One Queue

If two warehouse workers consume **warehouse.orders.q**, each worker receives a portion of deliveries under competing-consumer semantics, with possible redelivery if one fails to ACK. Do not write tests asserting **both workers receive every message**.

Conversely, if Analytics and Warehouse must both receive every OrderCreated, test by publishing one event and verifying the content appears in **two separate queues**, not by checking two consumers on the same queue.

### 11.4. Misconfigurations to Simulate

1. **Wrong routing key:** publisher finds no route; enable returns/mandatory to observe clearly.
2. **Wrong exchange type:** topic bean declared when broker already has a direct exchange of the same name; check declare/precondition errors.
3. **Wrong virtual host:** topology exists in vhost A while the application connects to vhost B.
4. **Missing configure/write/read permissions:** RabbitAdmin or producer/consumer fails accordingly.
5. **Binding deleted mid-flight:** publish may still be accepted by broker yet fail to reach the expected queue.
6. **Consumer stopped:** queue retains ready messages; do not confuse with a routing error.

## 12. Unroutable, Mandatory, Alternate Exchange, and Dead-Letter Exchange

These three mechanisms are frequently confused even though they handle different stages:

| Mechanism | When It Applies | Main Effect |
| --- | --- | --- |
| **mandatory + publisher returns** | A publish is not routed to any matching queue while return conditions apply | Notifies the producer that the message was unroutable |
| **Alternate exchange (AE)** | Primary exchange cannot route and has an alternate exchange configured | Reroutes unrouted publishes |
| **Dead-letter exchange (DLX)** | Message already entered a queue and was dead-lettered per broker policy | Moves messages from a queue to an error/secondary path |

### 12.1. Mandatory and Publisher Returns

Spring Boot configuration example for a publisher app:

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
~~~

With proper configuration, RabbitTemplate can handle returned messages via **ReturnsCallback** or integrated mechanisms, and confirms via **CorrelationData** callbacks/futures when correlated confirms are active.

Do not catch only synchronous exceptions from convertAndSend and assume that suffices: **unroutable returns and publisher confirms can arrive asynchronously**. Maintain publish tracking state and inspect confirm, return, and timeout results together.

**Important:** a publisher confirm ACK can arrive even when a message is unroutable. That ACK means the broker processed the publish under confirms, not that a target queue received it.

### 12.2. Alternate Exchange

An **alternate exchange** configured on a primary exchange can receive messages that the primary exchange could not route. For example:

~~~text
commerce.events  -- no matching binding -->
commerce.unrouted (alternate exchange)
                         |
                         v
                commerce.unrouted.q
~~~

For this design to be effective:

- The alternate exchange must exist and have appropriate bindings to a fallback queue.
- Producers and operators must know where messages go; never equate landing in the alternate queue with successful delivery to the intended target consumer.
- If the alternate exchange also cannot route, you still need a policy for unrouted/uncertain outcomes.
- Configure AE via exchange arguments/policies per broker rules; do not add it mistakenly as a per-message business field.

When using an alternate exchange, understand how it affects **unroutable** reporting back to the publisher. Do not assume a message successfully routed to an alternate queue will still trigger a mandatory return as if the broker had nowhere to route it.

### 12.3. Dead-Letter Exchange Belongs to the Queue Message Lifecycle

DLX applies when a message inside a queue is dead-lettered, for example:

- Consumer rejects/NACKs with **requeue=false**.
- Message expires due to TTL policy.
- Queue exceeds max length per broker settings.
- Certain delivery-limit conditions on quorum queues per configuration.

~~~mermaid
flowchart LR
    P["Publisher"] --> X["commerce.events"]
    X --> Q["warehouse.orders.q"]
    Q --> C["Warehouse consumer"]
    C -->|"Reject / NACK<br/>no requeue"| D["warehouse.dlx"]
    D --> DQ["warehouse.orders.dlq"]
~~~

**DLX does not automatically catch every failed producer publish.** If the publisher cannot connect, the exchange does not exist, or the message never reached a queue, the consumer's DLX cannot rescue that publish. Producer failures require separate outbox/retry/alert handling.

### 12.4. Illustrating DLX Configuration for a Queue

The following example is an **alternative** defining the Warehouse queue with DLX; do not add two Queue beans with the same name and conflicting attributes to the same application:

~~~java
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;

// Example declaration for a test environment / new queue.
Queue warehouseWithDlx = QueueBuilder.durable("warehouse.orders.q")
    .deadLetterExchange("warehouse.dlx")
    .deadLetterRoutingKey("warehouse.failed")
    .build();
~~~

You must also declare **warehouse.dlx**, **warehouse.orders.dlq**, the binding with key **warehouse.failed**, and corresponding permissions. For existing production topologies, RabbitMQ policies are often more flexible than hardcoded immutable x-arguments; coordinate changes with operations.

Avoid a **dead-letter cycle**: a failing message routed back to the original queue without a termination condition can loop indefinitely, generating load and making reconciliation difficult.

## 13. Reliability: Correct Routing Is Not Enough for Correct Processing

Suppose the producer publishes OrderCreated to two queues. Warehouse succeeds, while Analytics times out and redelivers. Both queues received the right message, yet their **business state differs** at that point in time.

Distinguish:

1. **Routing success:** broker placed the message into matching queues.
2. **Transport acknowledgment:** publish confirm or consumer ACK at the protocol layer.
3. **Business completion:** service committed data / finished the operation.
4. **End-to-end outcome:** all involved systems reached the expected business state.

### 13.1. Idempotency When Consumers Receive Duplicates

Consumers can receive duplicates due to:

- Broker redelivery when an ACK was not sent/recorded.
- Producer retry after losing a publisher confirm.
- The same event being re-emitted from an outbox.
- A partner intentionally republishing the same event.

Therefore, attach a stable **eventId** (e.g., **evt-1001**) and handle idempotency with a unique constraint/inbox table or equivalent mechanism. **Routing key orders.created** can be identical across millions of events and cannot uniquely identify a business operation.

### 13.2. Transactional Outbox

When writing an Order to a database and publishing over AMQP, the two resources typically do not share an atomic transaction. If the database commits and the process crashes before publishing, the event is lost. If publishing succeeds before marking it sent, the event can be re-emitted.

A **transactional outbox** pattern:

~~~mermaid
flowchart LR
    S["OrderService"] --> TX["Database transaction"]
    TX --> O["Orders"]
    TX --> OB["OutboxEvent(eventId, routingKey)"]
    OB --> W["Outbox publisher worker"]
    W --> RT["RabbitTemplate / outbound adapter"]
    RT --> EX["commerce.events"]
    EX --> Q["Target queue per binding"]
    Q --> ID["Idempotent consumer"]
~~~

Inside the database transaction, write both Order and OutboxEvent. A worker publishes events using the agreed exchange/routing key, tracks confirms/returns/timeouts, and marks them sent upon reaching the designed confirmation milestone. Consumers must still be idempotent. **Outbox does not create end-to-end exactly-once by itself**; it improves recoverability across independent resources.

### 13.3. Preserving Ordering

RabbitMQ queues follow delivery ordering rules, but concurrency, prefetch, multiple consumers, retries, priorities, and requeues can make **business processing order** diverge from publish order. If OrderCreated must precede OrderCancelled per order ID, check domain event versions or sequence numbers and coordinate consumer handling rather than assuming a topic exchange preserves all ordering.

## 14. Operations: Security, Lifecycle, Load, and Observability

### 14.1. RabbitMQ Permissions by Virtual Host

RabbitMQ scopes resources inside a **virtual host**. An exchange or queue with the same name in two different vhosts is not the same resource.

Permissions to distinguish:

- **Configure:** declare/modify exchanges or queues and related configuration operations.
- **Write:** publish to exchanges or perform write operations.
- **Read:** consume from queues as authorized.

Grant least-privilege permissions to producers, consumers, and topology admin accounts. Use TLS and certificate verification where security requires; never put passwords into code, logs, or event messages.

### 14.2. ConnectionFactory and Endpoint Lifecycle

Spring AMQP uses **ConnectionFactory**—commonly **CachingConnectionFactory** in Spring Boot apps—to supply connections/channels. RabbitTemplate uses it to publish; inbound adapters use listener containers to consume queues.

- An **outbound adapter** may stop while RabbitTemplate/ConnectionFactory remain in use by other flows.
- An **inbound adapter** is typically message-driven and does not use a Spring Integration Poller like File/SFTP.
- Many endpoints implement **Lifecycle/SmartLifecycle**; **isRunning()** does not prove the broker is healthy or all messages are processed.
- On shutdown, stop accepting new work, finish or durably persist in-flight work, and then close connections and shared resources per lifecycle order.

### 14.3. Load and Backlog

| Symptom | What to Inspect |
| --- | --- |
| Growing ready queue | Consumer throughput lower than publish rate, consumers down |
| Growing unacked count | Slow handlers, large prefetch, incomplete manual ACK |
| Slow publish confirms | Overloaded broker/network, connection/channel contention |
| Increasing unroutable rate | Incorrect routing key/binding/topology or changed targets |
| High requeue/redelivery | Poison messages, transient errors, crashes before ACK |
| Growing DLQ | Data errors, exhausted retries, TTL/delivery-limit, or broker policy |
| Queues receiving different counts | Different bindings, DLX/TTL, already-consumed messages, unisolated tests |

Do not treat **queue depth = 0** as proof that the producer failed to send: consumers may have drained it very fast. Likewise, do not treat **queue depth > 0** as a routing error if backlog is caused by slow consumers.

### 14.4. Metrics to Monitor

- **Publisher:** publish count, confirm ACKs/NACKs, returns, timeouts/UNKNOWN.
- **Broker:** connection/channel counts, exchange publish/route rates, ready/unacked counts, consumer count.
- **Consumer:** delivery rate, ACK/NACK/requeue counts, processing latency, and business errors.
- **Business:** processed eventIds, pending outbox events, duplicates rejected, final states in Warehouse/Analytics.
- **Security:** authentication/authorization failures, TLS errors, and unexpected permission usage.

Logs should record exchange, routing key, contract queue, eventId/correlation, and error category; avoid printing credentials or sensitive payloads.

## 15. Common Confusions

**"Producers publish directly to a queue."** In AMQP 0-9-1, publishing goes through an exchange; the default exchange is just a special case whose routing key matches the queue name.

**"A direct exchange can only send to one queue."** Multiple queues can bind the same key; a matching publish can go to multiple queues.

**"Topic exchanges use asterisks in the routing key to pick queues."** Wildcards belong in **binding patterns**, not in a producer declaring a wildcard routing key to the broker.

**"orders.\* matches orders.created.priority."** False: `*` matches exactly one word; **orders.#** matches multiple levels.

**"Multiple consumers on one queue means broadcast."** Competing consumers typically share deliveries. Cross-system fan-out requires separate queues.

**"A durable exchange makes all messages safe."** You must account for queues, delivery mode, queue type, confirms, and consumer ACK/idempotency.

**"Publisher confirm ACK means the consumer finished processing."** Confirm belongs to broker/publisher; consumers have separate ACKs and business outcomes.

**"An unrouted message always makes convertAndSend throw an exception."** Unroutable messages may not throw directly; configure mandatory/returns or an alternate exchange.

**"DLX handles all producer errors."** DLX primarily handles messages already in a queue that are dead-lettered by policy; producer errors need separate retry/outbox/alert handling.

**"Routing key is the event ID."** Routing key directs delivery; eventId handles deduplication and business tracing.

**"Declaring a Queue bean automatically creates it on the broker."** You need RabbitAdmin/AmqpAdmin enabled with permissions, or external infrastructure provisioning.

**"QueueChannel and a RabbitMQ queue have the same durability."** Internal QueueChannels default to in-memory; RabbitMQ queues offer guarantees based on broker config and queue type.

**"Stopping a consumer deletes unprocessed messages."** Ready messages can remain queued; in-flight/unacked messages depend on ACK, connection, and recovery policies.

## 16. Self-Check Questions

1. Where do queue, exchange, binding, and routing key live in AMQP architecture, and how do they differ?
2. Why can a producer publish successfully to an exchange yet no queue receives the message?
3. When can a direct exchange deliver one publish to two queues?
4. Does topic binding **orders.\*** match **orders.created.priority**? What about **orders.#**?
5. What is the name of the default exchange? Why can the routing key be a queue name?
6. How does a fanout exchange treat routing keys? Does broadcasting to multiple systems still require one queue per system?
7. What information does a headers exchange use to route? Why should AMQP headers not be confused with all Spring MessageHeaders?
8. Why is a durable queue insufficient to claim all messages are persistent and exactly-once?
9. In the CommerceAmqpTopology example, which queues receive **orders.created**? What about **orders.cancelled**?
10. If the application has a Queue bean yet RabbitMQ reports the queue does not exist, what should be checked?
11. How do publisher confirm, publisher return, consumer ACK, and business reply differ?
12. When should an alternate exchange be used vs. a dead-letter exchange?
13. Why must retrying an event keep eventId unchanged rather than using a different routing key or generating a new ID?
14. If both Warehouse and Analytics must receive every OrderCreated, why does a single shared queue fail the requirement?
15. Which metrics distinguish routing errors, slow-consumer backlog, and poison-message loops?
16. When changing a MessageChannel from DirectChannel to QueueChannel, what changes regarding pollers, persistence, and when success is reported?
17. If an exchange is already declared as direct on the broker but code changes it to topic with the same name, what can happen?
18. How do you ensure an Order saved in the database does not lose its event if the process crashes before publishing?

## Summary

**Queue, exchange, binding, and routing key** are the four core pieces of RabbitMQ routing. Producers publish **to an exchange**; the exchange uses its **exchange type and bindings** to determine which **queues** receive the message; consumers read from queues. Direct exchanges perform exact matching, topic exchanges use wildcards in binding patterns, fanout ignores routing keys, and headers exchanges evaluate metadata. The **default exchange** enables routing by queue name while still following the publish-to-exchange model.

In Spring Integration, **AMQP outbound adapters/RabbitTemplate** connect a MessageChannel to an exchange, while **AMQP inbound adapters/listener containers** bring deliveries from queues back into a MessageChannel. For a system to work reliably, verify not only routing but also **actual broker topology, permissions, message converters, publisher confirms/returns, ACK/retry/DLX, idempotency, transactions/outbox, and connection lifecycle**. A clear topology design ensures warehouse, analytics, and other services receive the right events, process independently, and recover cleanly from failures.
