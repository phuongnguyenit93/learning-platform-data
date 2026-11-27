# Queue destinations, topics, and destination names in JMS

## 1. Problem: sending to the right place, receiving the right way

Suppose a sales platform emits two kinds of messages:

- A `ReserveInventory` command requiring **one** warehouse worker to reserve stock for order `ORD-701`.
- An `OrderPaid` event that must reach **multiple** independent services: warehouse, accounting, and analytics.

If both are sent to the same destination and consumed the same way, things easily go wrong: commands may be executed multiple times, or some services may miss their required copy of the event. A **JMS Destination** is the logical address for sending/receiving messages, yet **Queue** and **Topic** have very different delivery contracts.

In the **SPRING_INTEGRATION_ADAPTERS** module, Spring Integration connects external systems via inbound/outbound adapters, gateways, pollers, and `MessageChannel`s. For JMS, choosing the right destination is the first step toward keeping message contracts, error handling, retries, and connection lifecycles sound. This lesson focuses on **queue destinations, topics, and destination names**: their semantics, how Spring JMS resolves names, how to configure adapters/gateways, how to use subscriptions, and how to verify behavior against a broker.

**After this lesson, you will be able to:**

1. Explain the differences among `jakarta.jms.Destination`, `Queue`, `Topic`, and the `destinationName` string.
2. Choose a queue for competing consumers or a topic for publish-subscribe.
3. Configure `pubSubDomain`, `DestinationResolver`, and JMS adapters using Java DSL/XML.
4. Design durable/shared subscriptions, temporary destinations for request-reply, and consistent destination naming.
5. Spot issues such as queue/topic mismatches, offline subscriptions losing messages, multiple consumers altering ordering, and sending to unintended destinations.

## 2. What is a JMS Destination?

`jakarta.jms.Destination` is the interface representing **a JMS target that producers send to and consumers receive from**. Two primary types:

- `jakarta.jms.Queue`: **point-to-point** model. A message on a queue is normally delivered to one of the queue's competing consumers. When a consumer rolls back, the broker can redeliver the message per policy.
- `jakarta.jms.Topic`: **publish-subscribe** model. A message is delivered to matching subscriptions; each independent subscription can receive a copy of the same event.

A `Destination` is **not** a Spring Integration `MessageChannel`. Inside the application, a `MessageChannel` transports Spring Messages between endpoints and handlers; a `Destination` belongs to the broker/provider and transports JMS Messages outside the JVM.

~~~mermaid
flowchart LR
    A["Service creates Spring Message"] --> B["Spring Integration outbound adapter"]
    B -->|"JmsTemplate / JMS send"| C{"Destination"}
    C --> D[("Queue: inventory.commands")]
    C --> E[("Topic: orders.events")]
    D --> F["One consumer in the warehouse worker group"]
    E --> G["Warehouse: subscription"]
    E --> H["Accounting: subscription"]
    E --> I["Analytics: subscription"]
~~~

The branches from `Destination` to Queue or Topic in the diagram illustrate **two configuration options for two use cases**, not that a single JMS send automatically delivers to both destination types. To emit both commands and events, the application must publish separate corresponding messages.

### Commonly confused terms

| Term | Meaning | Example |
|---|---|---|
| `Destination` | Target JMS object for sending/receiving | A `Queue` or `Topic` |
| `destinationName` / `destination-name` | **Name string** used by a Spring/JMS resolver to look up a `Destination` | `inventory.commands` |
| `DestinationResolver` | Strategy converting a name into a `Destination` | `DynamicDestinationResolver`, `JndiDestinationResolver` |
| `pubSubDomain` | Flag selecting **topic** when resolving a destination by name; `false` typically means queue | `true` when publishing to a topic |
| Subscription | A subscriber's relationship to a topic, optionally durable/shared | `accounting-service-v1` |
| `JMSReplyTo` | A JMS `Destination` where a request receiver should send the reply | Temporary queue or fixed reply queue |
| `MessageChannel` | Internal Spring Integration abstraction | `ordersInput`, `commandsOutput` |

Key takeaway: **a destination name is just a string**, whereas how the broker/provider interprets that string depends on **destination type, resolver, broker configuration, and access permissions**.

## 3. Queue: assigning one task to one consumer

A queue is typically used when a message represents a **task that should be executed once in business terms**: importing an order, reserving stock, processing a payment, generating a shipping label. Multiple workers listening to the same queue are **competing consumers**.

~~~mermaid
flowchart LR
    P["Order Service"] --> Q[("Queue: inventory.commands")]
    Q --> W1["Warehouse Worker 1"]
    Q --> W2["Warehouse Worker 2"]
    Q --> W3["Warehouse Worker 3"]
    W1 --> DB[("Warehouse")]
    W2 --> DB
    W3 --> DB
~~~

The diagram shows that **multiple consumers can receive different messages from the same queue**. A specific message is normally delivered to **one** consumer at a processing attempt, though if the consumer/transaction fails, the message may be redelivered to another consumer. JMS does not by itself guarantee that a handler produces a business side effect only once.

### Key characteristics of a Queue

1. **Work distribution:** a queue can have multiple consumers; the broker decides which consumer receives each message.
2. **Backlog:** messages can wait in the queue when no consumer is ready; retention depends on persistence, expiry, quotas, and broker policy.
3. **Redelivery:** if a transacted session rolls back or a consumer fails at the right boundary, the broker can resend the message; usually paired with retry and dead-letter queue (DLQ) policies.
4. **Ordering:** never assume multiple consumers finish work in send order. If strict ordering per `orderId` is required, use serialization, grouping, or partitioning supported by the broker.
5. **Idempotency:** consumers must recognize duplicate `eventId`/`commandId` values on retries, producer resends, or message redeliveries.

Example: the application sends three consecutive commands for `ORD-701`: `CREATE`, `UPDATE`, and `CANCEL`. With three parallel consumers, `CANCEL` might finish before `UPDATE` even if the broker delivered them in order. The contract should include versions/states or key-based command grouping.

### When is a Queue unsuitable?

If an `OrderPaid` message must reach **both warehouse and accounting**, two consumers reading the **same queue** will compete for messages. Each message is not automatically duplicated for every service. The right approach is usually a **topic with two separate subscriptions**, or having a producer/router publish two copies to two separate business queues when strict isolation is needed.

## 4. Topic: broadcasting the same event to multiple subscriptions

Topics serve **publish-subscribe**. A producer publishes one event; the broker distributes the event to matching subscriptions.

~~~mermaid
flowchart LR
    P["Order Service"] --> T[("Topic: orders.events")]
    T --> S1["Warehouse subscription"]
    T --> S2["Accounting subscription"]
    T --> S3["Analytics subscription"]
    S1 --> W["Warehouse"]
    S2 --> A["Accounting"]
    S3 --> X["Analytics"]
~~~

Here, warehouse and accounting **do not compete on the same subscription**: each subscription receives its own event stream. Both subscriptions can process the same `evt-701` independently. However, **two consumers sharing the same shared subscription** split the messages of that subscription among themselves, much like scaling workers on a queue. That is the difference between **subscription count** and **consumers within a subscription**.

### Non-durable vs. durable subscriptions

| Subscription type | While subscriber is online | While subscriber is offline | Typical use |
|---|---|---|---|
| **Non-durable** | Receives messages published while the subscription is active | Normally misses messages published while inactive | Live dashboards, non-critical notifications |
| **Durable (unshared)** | Receives messages under a persistent subscription | Broker can retain eligible messages for the subscription until the subscriber returns, subject to expiry/quota/retention | Accounting, critical event reconciliation |
| **Shared subscription** | Multiple consumers split processing within one subscription | Offline behavior depends on shared non-durable vs. durable | Scaling a single application's subscriber |
| **Shared durable** | Multiple consumers share one durable subscription | Can retain messages when no consumer is connected, per config and policy | Services needing both cross-system fan-out and intra-service scaling |

A durable subscription does **not** automatically mean infinite retention: messages are still subject to `timeToLive`/expiry, broker quotas, security policies, and retention limits. Monitor backlog per durable subscription.

With unshared durable subscriptions, client ID and subscription name usually form the subscription identity. With JMS 2.0+ shared/durable subscriptions, naming and concurrency rules differ; check your JMS provider and Spring listener container options. Avoid letting multiple instances accidentally register distinct durable subscriptions when the goal is to share processing of one copy per event.

### One topic for three services

Suppose we publish:

~~~json
{
  "eventId": "evt-701",
  "schemaVersion": 1,
  "eventType": "OrderPaid",
  "orderId": "ORD-701",
  "paidAmount": 480000
}
~~~

With three independent subscriptions for warehouse, accounting, and analytics, the broker can deliver three logical copies to the three subscriptions. Each service **independently governs its own retries, acks, error handling, and deduplication**; success on the warehouse subscription does not prove accounting has finished processing.

## 5. Queue vs. Topic: quick selection table

| Criterion | Queue | Topic |
|---|---|---|
| Purpose | Assign a task to one member of a worker pool | Broadcast events to one or more independent subscriptions |
| Relationship among consumers | Competing consumers on the queue | Each subscription gets its own stream; multiple consumers can share a shared subscription |
| Delivery while offline | Eligible messages can wait in the queue | Non-durable typically loses events while offline; durable retains per policy |
| Retry and DLQ | Typically configured per queue/consumer/broker policy | Configured per subscription/provider; retries can be isolated across services |
| Ordering | Depends on broker, concurrency, grouping | Depends on subscription, concurrency, partitioning/grouping |
| Examples | `inventory.commands`, `invoice.jobs` | `orders.events`, `catalog.events` |
| When to choose | Only one worker should execute a command | Multiple systems need a copy of the event |

Do not choose queue vs. topic solely from suffixes like `.commands` or `.events`; the **delivery contract** is the primary criterion. In a large system, an event may arrive via a topic and each service may then forward its own work onto an internal queue processed by a worker pool.

## 6. How does `destinationName` differ from a `Destination` object?

A JMS adapter can be supplied with either:

1. An existing **`jakarta.jms.Destination` object**, such as a `Queue`/`Topic` bean provided by JNDI or the JMS provider; or
2. A **name string** `destinationName`, such as `orders.events`, for Spring to resolve upon connection/use.

Java example using `JmsTemplate`:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.jms.core.JmsTemplate;

JmsTemplate queueTemplate = new JmsTemplate(connectionFactory);
queueTemplate.setPubSubDomain(false); // String name resolves to a queue.
queueTemplate.convertAndSend("inventory.commands",
        "{\"commandId\":\"cmd-701\",\"orderId\":\"ORD-701\"}");

JmsTemplate topicTemplate = new JmsTemplate(connectionFactory);
topicTemplate.setPubSubDomain(true); // String name resolves to a topic.
topicTemplate.convertAndSend("orders.events",
        "{\"eventId\":\"evt-701\",\"eventType\":\"OrderPaid\"}");
~~~

This snippet illustrates code inside a method with an already-configured `connectionFactory`; it is not a standalone Java app. Using two distinct templates makes the **queue domain** and **topic domain** explicit. `setPubSubDomain(true)` controls how the resolver creates/looks up destinations **by name**; with a concrete `Destination` object, its `Queue` or `Topic` type already determines its domain.

### 6.1. `DynamicDestinationResolver`

`JmsTemplate` uses `DynamicDestinationResolver` by default. When calling:

~~~java
topicTemplate.convertAndSend("orders.events", payload);
~~~

Spring asks the resolver to map the string `orders.events` to an appropriate JMS `Destination`. With `pubSubDomain=true`, the resolver resolves a topic; with `false`, a queue.

**A string name does not guarantee the broker physically auto-creates a queue/topic.** The provider may auto-create when permitted, or require pre-provisioned destinations. `DynamicDestinationResolver` handles **destination resolution**, while physical creation and ACLs belong to provider/broker behavior and security.

A common pitfall: both producer and consumer use the string `orders.events`, yet the producer sends to a **queue** while the consumer subscribes to a **topic**. The two sides never meet despite having identical names.

### 6.2. `JndiDestinationResolver` and administrator-provisioned destinations

In some enterprise environments, destinations are managed via JNDI or an application server. In that case, the app can configure `JndiDestinationResolver` to look up logical names as registered `Destination` objects:

~~~java
import org.springframework.jms.support.destination.JndiDestinationResolver;

JndiDestinationResolver resolver = new JndiDestinationResolver();
resolver.setCache(true);

JmsTemplate jmsTemplate = new JmsTemplate(connectionFactory);
jmsTemplate.setDestinationResolver(resolver);
jmsTemplate.convertAndSend("jms/OrderEvents", jsonBody);
~~~

This example assumes the JNDI context already has a `jms/OrderEvents` binding and `jsonBody` is a JSON `String`. `JndiDestinationResolver` can be configured to fall back to dynamic resolution when lookup fails; in strictly governed destination environments, consider **disabling fallback** so a JNDI error does not accidentally send to a different destination.

Do not assume `jms/OrderEvents` is the physical broker name unless the admin/provider states so. **JNDI name** and **physical broker address** can be two different values.

### 6.3. Destination bean vs. string name: when to use each?

| Reference style | Example | Advantages | What to check |
|---|---|---|---|
| String destination name | `"orders.events"` | Concise, easy to configure per environment | Resolver, queue/topic domain, auto-create, ACLs |
| `Destination` object | `Topic` bean from provider/JNDI | Explicit destination type, no string resolution at call site | Bean lifecycle, permissions, broker mapping |
| JNDI logical name | `"jms/OrderEvents"` | Separates app administration from broker details | Naming context, fallback, lookup cache |
| Dynamic destination from message | `headers['targetDestination']` | Flexible routing | Allowlist, validation, observability, send permissions |

## 7. Configuring queues/topics in Spring Integration Java DSL

Examples use Spring Integration 6+ and `jakarta.jms.ConnectionFactory`. The project needs `spring-integration-jms` plus the provider's JMS client and a matching broker/queue/topic. The Java snippets below show **independent flows** that can be placed as separate beans in a Spring application.

### 7.1. Sending commands to a Queue with an outbound adapter

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;

@Configuration
@EnableIntegration
public class InventoryCommandFlows {

    @Bean
    public IntegrationFlow inventoryCommandOutbound(
            ConnectionFactory connectionFactory) {
        return IntegrationFlow.from("inventoryCommandOutput")
                .handle(Jms.outboundAdapter(connectionFactory)
                        .destination("inventory.commands"))
                .get();
    }
}
~~~

In this configuration, `Jms.outboundAdapter(connectionFactory)` uses a `JmsTemplate` with standard name resolution (queue by default) when uncustomized. Sending a Spring Message with a JSON `String` to `inventoryCommandOutput` triggers the outbound adapter, converts it to a JMS `TextMessage`, and sends it to the `inventory.commands` queue.

If the app has a Spring Boot auto-configured `ConnectionFactory`, you can inject that bean. The example does not create the broker or destination itself and does not wait for a reply; if a result from the warehouse system is needed, use a JMS outbound gateway.

### 7.2. Publishing events to a Topic via a domain-configured JmsTemplate

To guarantee topic domain resolution when passing a string name, configure a dedicated topic `JmsTemplate` and pass it to the JMS outbound adapter:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;
import org.springframework.jms.core.JmsTemplate;

@Bean("orderEventsTopicTemplate")
public JmsTemplate orderEventsTopicTemplate(ConnectionFactory connectionFactory) {
    JmsTemplate template = new JmsTemplate(connectionFactory);
    template.setPubSubDomain(true);
    return template;
}

@Bean
public IntegrationFlow orderEventTopicOutbound(
        @org.springframework.beans.factory.annotation.Qualifier("orderEventsTopicTemplate")
        JmsTemplate topicTemplate) {
    return IntegrationFlow.from("orderEventsOutput")
            .handle(Jms.outboundAdapter(topicTemplate)
                    .destination("orders.events"))
            .get();
}
~~~

These beans/methods should reside in a class annotated with `@Configuration` and `@EnableIntegration` (or equivalent Spring Integration setup). If the producer sends a `String`, the common default converter produces a JMS `TextMessage`. This configuration only publishes to **topic `orders.events`**; subscriptions are created/managed by the **receiving side**.

Because `JmsTemplate` is typically a singleton, **never** toggle `setPubSubDomain(true/false)` back and forth while multiple threads are sending. Use dedicated templates/adapters with fixed configuration, or route across separate endpoints.

### 7.3. Receiving commands from a Queue with a message-driven adapter

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;

@Bean
public IntegrationFlow inventoryCommandInbound(
        ConnectionFactory connectionFactory) {
    return IntegrationFlow
            .from(Jms.messageDrivenChannelAdapter(connectionFactory)
                    .destination("inventory.commands"))
            .handle(String.class, (commandJson, headers) -> {
                // Process synchronously, validate commandId and idempotency in a real service.
                System.out.println("Inventory command: " + commandJson);
                return null;
            })
            .get();
}
~~~

The listener container created by the adapter receives messages as soon as the broker delivers them; **do not add a poller**. Queues and competing consumers follow broker policies. In production, the handler needs transaction, redelivery, and idempotency strategies.

### 7.4. Receiving from a Topic with a durable subscription

For subscribers that must receive events even after temporary downtime, configure a listener container for the topic and subscription identity and pass that container into the adapter.

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;
import org.springframework.jms.listener.DefaultMessageListenerContainer;

@Bean
public DefaultMessageListenerContainer accountingTopicListener(
        ConnectionFactory connectionFactory) {
    DefaultMessageListenerContainer container =
            new DefaultMessageListenerContainer();
    container.setConnectionFactory(connectionFactory);
    container.setDestinationName("orders.events");
    container.setPubSubDomain(true);
    container.setSubscriptionDurable(true);
    container.setSubscriptionName("accounting-service");
    container.setClientId("accounting-client-01");
    container.setSessionTransacted(true);
    // Container has no listener yet: the Spring Integration adapter will register the listener.
    return container;
}

@Bean
public IntegrationFlow accountingOrderEvents(
        DefaultMessageListenerContainer accountingTopicListener) {
    return IntegrationFlow
            .from(Jms.messageDrivenChannelAdapter(accountingTopicListener))
            .handle(String.class, (json, headers) -> {
                System.out.println("Accounting received: " + json);
                return null;
            })
            .get();
}
~~~

Note: this snippet illustrates attaching a subscription to a listener. For production use, verify Spring Integration/JMS provider versions, bean lifecycle, listener registration timing, and unique client IDs per broker rules. **An unshared durable subscription cannot arbitrarily share the same identity across multiple active consumers**; to distribute load within the same subscription, configure a **shared durable subscription** as supported by the broker and container API.

When declaring the container as a standalone bean, Spring manages its start/stop lifecycle; test how its lifecycle coordinates with the endpoint. Configure the listener container under a unified management approach to avoid starting it prematurely before the adapter registers its listener.

## 8. XML namespace examples: destination-name and pub-sub-domain

In Spring Integration XML configuration, many JMS adapters/gateways support specifying:

- `destination`: reference to a `Destination` bean.
- `destination-name`: string name to be resolved by the resolver.
- `pub-sub-domain`: select topic instead of queue when appropriate.

### Queue inbound and outbound

~~~xml
<int:channel id="inventoryCommands"/>

<int-jms:message-driven-channel-adapter
        id="inventoryCommandsInbound"
        connection-factory="jmsConnectionFactory"
        destination-name="inventory.commands"
        channel="inventoryCommands"/>

<int-jms:outbound-channel-adapter
        id="inventoryCommandsOutbound"
        connection-factory="jmsConnectionFactory"
        destination-name="inventory.commands"
        channel="inventoryCommandOutput"/>
~~~

These are XML fragments; full `int` and `int-jms` namespaces, the `jmsConnectionFactory` bean, and channels/handlers are required. If the same application both sends to and receives from `inventory.commands`, both endpoints can run; during testing, keep roles separate or control the flow to avoid accidentally creating an infinite resend loop.

### Topic message-driven inbound with durable subscription

~~~xml
<int:channel id="accountingEvents"/>

<int-jms:message-driven-channel-adapter
        id="accountingTopicInbound"
        connection-factory="jmsConnectionFactory"
        destination-name="orders.events"
        pub-sub-domain="true"
        subscription-durable="true"
        subscription-name="accounting-service"
        channel="accountingEvents"/>
~~~

With an unshared durable subscription, configure an appropriate **client ID** on the listener container/connection factory and follow broker rules. Never assign the same durable subscription identity to two independent services if both need **one copy each**; give them distinct subscription names/client IDs.

When deploying with XML, the `accountingEvents` bean must have a consumer such as a service activator or receiving flow. Subscription settings must align with the JMS provider, Spring Integration version, and deployment lifecycle.

### Comparison with JMS-backed Spring Integration channels

Spring Integration also provides **JMS-backed channels**, which differ from inbound/outbound channel adapters: `<int-jms:channel>` uses a queue, while `<int-jms:publish-subscribe-channel>` uses a topic. When messages need to traverse JMS directly between Spring Integration endpoints, these channel types can also fit.

~~~xml
<int-jms:channel
        id="jmsWorkQueueChannel"
        connection-factory="jmsConnectionFactory"
        queue-name="inventory.commands"/>

<int-jms:publish-subscribe-channel
        id="jmsEventTopicChannel"
        connection-factory="jmsConnectionFactory"
        topic-name="orders.events"/>
~~~

Do not confuse `queue-name`/`topic-name` on a **JMS-backed channel** with `destination-name` on an **adapter**: they are different configuration elements even though both point to broker destinations. Decide whether you want an **endpoint bridging a Spring `MessageChannel` to the broker** or a **`MessageChannel` itself with JMS-backed semantics**.

## 9. Dynamic destinations: flexible but must be bounded

Some applications need to route commands by business type:

~~~text
inventory.reserve  -> queue inventory.reserve.commands
inventory.release  -> queue inventory.release.commands
~~~

The Spring Integration outbound adapter can resolve a destination via an expression instead of a fixed name. For example:

~~~java
IntegrationFlow.from("inventoryRoutedCommands")
        .handle(Jms.outboundAdapter(connectionFactory)
                .destinationExpression("headers['targetQueue']"))
        .get();
~~~

This is a flow fragment; `targetQueue` must be a **server-validated** header. Never allow client APIs to pass uncontrolled destination strings directly, as that could allow writing to internal queues, broadcasting sensitive data, or spawning unintended destinations.

### Using an allowlist instead of arbitrary string concatenation

Example of normalizing the header from `commandType`:

~~~java
.enrichHeaders(headers -> headers.headerFunction(
        "targetQueue",
        message -> {
            String type = (String) message.getHeaders().get("commandType");
            return switch (type) {
                case "RESERVE" -> "inventory.reserve.commands";
                case "RELEASE" -> "inventory.release.commands";
                default -> throw new IllegalArgumentException(
                        "Unsupported commandType: " + type);
            };
        }))
.handle(Jms.outboundAdapter(connectionFactory)
        .destinationExpression("headers['targetQueue']"))
~~~

This is a **snippet to embed inside an `IntegrationFlow`**, omitting the full `IntegrationFlow.from(...)` wrapper. The application should check `commandType` for `null`, bound header lengths/values, and handle exceptions. Destination lists should live in governed environment configuration rather than building `"inventory." + userInput`.

**Note on dynamic queue/topic selection:** if a flow must switch between **queue** and **topic** per message, **route across two outbound endpoints** with matching templates/domains, or return an allowlisted `Destination` object. Never toggle `pubSubDomain` on a singleton `JmsTemplate` between sends.

## 10. Naming conventions: naming for operability

JMS **does not enforce** one universal queue/topic naming convention across all brokers. Still, consistent names help production teams identify purpose, access permissions, ownership, and alerts.

An illustrative convention:

~~~text
inventory.reserve.commands
inventory.release.commands
orders.events
payments.events
orders.status.requests
orders.status.replies
orders.events.dlq
~~~

| Name segment | Meaning | Example |
|---|---|---|
| Domain | Business context | `orders`, `inventory` |
| Action/aggregate | Subject or operation | `reserve`, `status` |
| Message kind | Distinguishes commands, requests, events, replies | `.commands`, `.events` |
| Operational suffix when needed | DLQ, retry, version | `.dlq`, `.retry`, `.v2` |

Do not assume longer names are automatically better; pick a convention aligned with broker tooling and operational policies. A broker may separate **address** and **queue** concepts (for example, some JMS providers map JMS topics/queues onto an address model), so document both the **JMS name seen by the app** and the **physical resource name** in the environment.

### Separating configuration by environment

Do not hard-code broker URLs, credentials, or sensitive addresses in lessons or applications. Place destination names in configuration and set send/receive permissions accordingly. Example:

~~~yaml
app:
  messaging:
    inventory-commands: inventory.reserve.commands
    order-events: orders.events
~~~

This is an **application configuration example**, not lesson YAML metadata. You can use `@ConfigurationProperties` to bind destination names into a config class and pass them into flows. Across environments, physical names can be mapped from logical keys while keeping contracts consistent.

## 11. How do message selectors, TTL, and subscriptions interact?

### 11.1. Selectors do not turn a queue into a topic

A JMS **message selector** filters messages by JMS properties, for example:

~~~text
eventType = 'OrderPaid' AND region = 'VN'
~~~

A listener only receives messages whose properties satisfy the expression. On a **queue**, two consumers with different selectors still read the same queue under broker delivery rules; selectors do not duplicate messages for each consumer. On a **topic**, each subscription with its own selector can receive matching events.

Do not write selectors against JSON payload bodies directly: JMS selectors operate on broker-supported **headers/properties**, not by parsing JSON strings. Producers must set valid JMS properties like `eventType` and `region` if selectors rely on them.

### 11.2. TTL and durability

- **Persistent delivery** asks the JMS provider to apply appropriate durable storage guarantees; actual durability also depends on broker configuration.
- **Time-to-live** limits how long a message remains valid. Upon expiration, the broker may discard it or route it per expiry policy.
- **Durable topic subscriptions** retain eligible messages while a subscriber is offline, **but TTL and quotas still apply**.
- **DLQ** is a broker error-handling destination/strategy; the JMS specification does not guarantee every failed message automatically lands in a queue named `.dlq`.

Example: an `OrderPaid` event must still be processed if the accounting system is down for 4 hours. If the producer sets a 60-second TTL, even a durable subscription may miss the event after 4 hours. Align TTL, broker retention, backlog capacity, and consumer SLAs before claiming "zero lost events".

### 11.3. Ordering and idempotency

Adding consumers to a queue or using a shared topic subscription can raise throughput while breaking strict ordering assumptions. An event may also reappear after redelivery, or a producer may resend after an uncertain send outcome.

The JSON contract should carry keys such as:

~~~json
{
  "eventId": "evt-701",
  "aggregateId": "ORD-701",
  "aggregateVersion": 3,
  "eventType": "OrderPaid",
  "schemaVersion": 1
}
~~~

Consumers use `eventId` for deduplication and `aggregateVersion` to validate sequence order when business rules require it. A database unique constraint or inbox table helps prevent duplicate side effects. `JMSMessageID` only identifies a single JMS send and does not fully replace a stable event ID.

## 12. Request-reply: request destination and reply destination

A JMS gateway uses **at least two destination directions**:

~~~mermaid
sequenceDiagram
    participant Client as Spring Integration outbound gateway
    participant Broker as Broker
    participant Server as JMS inbound gateway / consumer
    Client->>Broker: Request -> orders.status.requests
    Note over Client,Broker: Request JMSReplyTo = temporary/fixed reply queue
    Broker->>Server: Receive request
    Server->>Broker: Reply -> JMSReplyTo
    Broker-->>Client: Receive reply via correlation
~~~

- **Request destination:** typically a queue so one server/consumer processes each request.
- **Reply destination:** `JMSReplyTo` points to a temporary queue or fixed queue where the client listens for replies.
- **Correlation:** the reply needs `JMSCorrelationID` per contract so the client matches it to the right request, especially with a shared reply queue.

Do not use a topic as a default reply destination just so "all clients can receive it", because a reply must be routed to the **request of that specific client**. JMS supports temporary topics/custom subscriptions in some setups, but choosing one must be intentional and supported by both gateway and provider.

A common bug: the client sends a request to `orders.status.requests`, the server replies to `orders.status.replies`, while the client is actually listening on a temporary destination created by the outbound gateway. Both sides may log "send succeeded" while the client still times out. Inspect the actual **`JMSReplyTo` on the request** and the server's default reply destination config.

## 13. Common troubleshooting scenarios

| Symptom | Possible cause | How to verify |
|---|---|---|
| Producer sends without error, consumer receives nothing | One side uses queue, other uses topic; wrong broker/address; selector mismatch | Log resolved destination type and name; inspect broker console |
| Queue depth grows continuously | No active consumers, failing or slow consumers | Check active consumers, retries, transactions, and backlog |
| Only one of two services receives events | Both services are competing on the same queue | Switch to a topic with separate subscriptions or explicit fan-out |
| Subscriber misses events after restart | Non-durable subscription or short TTL | Check durable setting, identity, expiry, and backlog |
| One service receives events multiple times | Redelivery or accidentally duplicated durable subscriptions | Inspect subscription list, `eventId`, and retries |
| Same name yet no messages delivered | Wrong resolver/JNDI mapping or queue/topic mismatch | Inspect resolved `Destination`, `pubSubDomain`, and physical broker name |
| Destination creation rejected | Broker disables auto-create or missing ACL | Provision destination and grant appropriate permissions |
| Two instances fight over a durable subscription | Sharing an unshared durable identity | Configure shared durable per version/provider or separate identities |
| Reply gateway times out | Wrong `JMSReplyTo`, correlation mismatch, missing reply queue | Inspect request/reply headers, listeners, and destinations |
| Renaming breaks delivery | Producer/consumer deployed at different versions | Use a migration plan, controlled dual-publish, and monitor backlog |

**Production observability checklist:** sent/received message counts, queue depth, oldest message age, active consumers/subscriptions, durable backlog, expiry count, redelivery/DLQ count, destination resolution errors, reconnect counts, JMS correlation, and `eventId` for tracing. Log only essential metadata; avoid logging full sensitive payloads.

## 14. Hands-on lab with a broker

Prepare a test JMS broker with two destinations:

- **Queue:** `inventory.commands`.
- **Topic:** `orders.events`.

Create two subscriber apps (or two independently configured consumers) to compare semantics. Use a real JMS broker or a provider-compatible test container; mocking `JmsTemplate` cannot prove subscriptions, redelivery, selectors, or retention.

### Lab A — Competing consumers on a Queue

1. Create a producer sending 20 commands with distinct `commandId` values to `inventory.commands`.
2. Run two consumers listening on that same queue.
3. Log each `commandId` and which consumer handled it; verify the total succeeded count is complete without assuming each consumer receives all 20.
4. Intentionally have one handler throw an exception inside a transacted session; observe redelivery and deduplication by `commandId`.
5. Start three consumers, measure throughput, and observe whether completion order still matches send order.

### Lab B — Two independent subscriptions on a Topic

1. Create two subscriptions on `orders.events`: `warehouse-service` and `accounting-service`.
2. Publish 10 `OrderPaid` events; verify each subscription receives all events matching its selector/policy.
3. Stop the accounting subscriber, then publish 5 more events.
4. Test both **non-durable** and **durable** subscriptions. Compare which events arrive after restart; inspect TTL, broker policies, and prior subscription registration.
5. Create two consumers sharing the same shared durable subscription (if supported by the broker) and confirm they split the work of **one** subscription.

### Lab C — Same name, different destination type

1. Have the producer send with `JmsTemplate.setPubSubDomain(false)` to the name `orders.events`.
2. Have the consumer subscribe to `orders.events` with `pubSubDomain=true`.
3. Confirm the queue/topic mismatch via broker console/logs (some brokers allow the same physical name with different routing types).
4. Switch the producer to the topic template and verify the subscriber receives messages.
5. Switch to JNDI lookup and observe when logical name `jms/OrderEvents` maps to physical topic `orders.events`.

### Lab D — Routing and security

1. Use header `commandType=RESERVE` or `RELEASE`; map to two allowlisted queues.
2. Test an unexpected value like `commandType=ADMIN`; verify the flow rejects it before sending.
3. Verify broker ACLs so the producer can only publish to the two valid destinations.
4. Measure destination resolution error counts and tag metrics by destination name/domain type.

### Lab E — Contract changes and operations

1. Rename a topic in one deployment while keeping an old consumer running; observe missing events.
2. Design a migration plan with a dual-publish phase, verify duplicate `eventId` handling, and decommission the old destination once backlog reaches 0.
3. Test a subscriber offline longer than TTL, and adjust retention to match real SLAs.
4. Restart the broker and both producer/consumer; verify connection recovery and intact subscription identities.

### Self-check questions

1. Why do two consumers on the same queue not guarantee each receives a copy of the same event?
2. What is the difference between **two independent subscriptions** and **two consumers on a shared subscription**?
3. If `destinationName="orders.events"` is configured on both producer and consumer, what else must be checked?
4. How does `pubSubDomain=true` affect string name resolution?
5. When should you use a `Destination` bean instead of `destinationName`?
6. Does a durable subscription retain messages forever regardless of TTL?
7. Why must producer and consumer agree on `JMSReplyTo` when using a JMS request-reply gateway?
8. Why do dynamic destinations require an allowlist?
9. If an `OrderPaid` message must reach three independent services, would you choose a Queue or a Topic, and how would you configure subscriptions?
10. How can you rename a destination while minimizing the risk of lost events or duplicate processing?

## 15. References

- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): queues/topics for inbound/outbound adapters, `destination`, `destinationName`, `pub-sub-domain`, durable/shared subscriptions, and request-reply.
- [Spring Framework Reference — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): `DestinationResolver`, `DynamicDestinationResolver`, `JndiDestinationResolver`, JNDI, and `JmsTemplate.pubSubDomain`.
- [Spring Integration API — Jms](https://docs.spring.io/spring-integration/api/org/springframework/integration/jms/dsl/Jms.html): Java DSL factory methods for adapters/gateways and JMS-backed channels.
- [Spring Integration API — JmsOutboundChannelAdapterSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jms/dsl/JmsOutboundChannelAdapterSpec.html): destination objects, destination names, and expression/function routing.
- [Spring Framework API — DefaultMessageListenerContainer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html): listener destinations, concurrency, and topic subscriptions.

**Remember:** `Destination` is the actual JMS target, while `destinationName` is a name resolved by `DestinationResolver`. A **Queue** distributes work to one consumer in a pool, whereas a **Topic** delivers events to independent subscriptions. In Spring Integration, configure `pubSubDomain`, subscription identity, reply destination, and access permissions accurately, and design idempotency, TTL, retries, and monitoring so the flow stays reliable under load or failure.
