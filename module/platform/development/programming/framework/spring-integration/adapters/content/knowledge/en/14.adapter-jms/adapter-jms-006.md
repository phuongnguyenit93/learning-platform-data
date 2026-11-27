# JmsTemplate and ConnectionFactory

## 1. Why understand both components?

An order-management service uses Spring Integration to send events to the JMS queue `orders.events` and synchronously receive commands from the `orders.import` queue. To talk to the broker, the application needs a way to **obtain JMS connections** and a component to **send/receive JMS messages** without manually opening and closing `Connection`, `Session`, `MessageProducer`, or `MessageConsumer` for every operation.

In the Spring ecosystem, the two core concepts are:

- **`jakarta.jms.ConnectionFactory`:** the standard JMS interface implemented by the provider. It creates connections to the broker; Spring classes can wrap (decorate) it to cache or pool resources.
- **`org.springframework.jms.core.JmsTemplate`:** Spring JMS's helper class for **synchronous** message sending, receiving, and conversion using the supplied `ConnectionFactory`. It handles most open/close resource boilerplate and translates `JMSException` into Spring's consistent exception hierarchy.

In the **SPRING_INTEGRATION_ADAPTERS** module, outbound adapters, inbound adapters, gateways, pollers, and `MessageChannel`s work together to connect external systems with integration flows. The **JMS** layer builds on Spring JMS infrastructure underneath; understanding `JmsTemplate` and `ConnectionFactory` explains why JMS inbound polling fetches messages on a schedule, why outbound adapters send when messages enter a channel, and why message-driven endpoints use a listener container instead.

**Learning outcomes:** after this lesson, you can configure `ConnectionFactory` and `JmsTemplate`, send/receive a JMS message, choose receive timeouts, understand converters/headers, distinguish queues/topics, choose caching/pooling appropriately, and set proper transaction boundaries for a Spring Integration flow.

## 2. Relationship between ConnectionFactory, JmsTemplate, and the broker

~~~mermaid
flowchart LR
    A["Service / Spring Integration flow"] --> B["JmsTemplate"]
    B --> C["ConnectionFactory"]
    C --> D["JMS Connection + Session"]
    D --> E["MessageProducer / MessageConsumer"]
    E <--> F[("JMS Broker")]
    B -. "MessageConverter + DestinationResolver" .-> G["Payload / Destination"]
~~~

Using the raw JMS API directly, a basic send requires acquiring a connection from the factory, creating a session, creating a producer, building a `TextMessage`, sending the message, and closing resources properly. `JmsTemplate` encapsulates these steps inside `send(...)` and `convertAndSend(...)`.

| Component | API/concept | Primary responsibility | What it does **not** do on its own |
|---|---|---|---|
| `ConnectionFactory` | Jakarta JMS | Creates connections to provider/broker | Does not define JSON contracts or business routing |
| `CachingConnectionFactory` | Spring JMS | Wraps a factory and caches connections, sessions, producers/consumers as configured | Is not a broker; does not replace every dedicated connection pool |
| `JmsTemplate` | Spring JMS | Synchronous send/receive, destination resolution, JMS message conversion | Does not run a JMS listener container for message-driven flows |
| `MessageConverter` | Spring JMS | Converts Java object ↔ JMS body | Does not automatically validate JSON schemas or business rules |
| `DestinationResolver` | Spring JMS | Resolves a destination name into a queue/topic object | Does not guarantee the destination exists or ACLs are valid |
| `DefaultMessageListenerContainer` | Spring JMS | Manages listener-style consumers, recovery, and concurrency | Does not replace `JmsTemplate` across all endpoints |
| `JmsTransactionManager` | Spring | Coordinates local JMS transactions on a `ConnectionFactory` | Does not automatically create an atomic transaction with a database |

A single `JmsTemplate` can serve multiple destinations; it does **not** own a single queue. A default queue name is merely a fallback when a call omits an explicit destination.

## 3. Environment setup and API versions

Examples use **Spring Framework 6+, Spring Integration 6+, and Java 17+**, with the JMS API in `jakarta.jms`. Spring 5 projects may use `javax.jms`; do not mix both packages in the same configuration.

In a Spring Boot project with BOM version management, application dependencies typically include:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-jms</artifactId>
</dependency>
<!-- Add the provider-specific JMS starter/client, e.g., Artemis or IBM MQ. -->
~~~

The JMS API/driver is usually supplied by the JMS provider dependency. `spring-integration-jms` **does not run a broker on its own**. You need a real broker or test container, connection address, credentials, TLS/ACL settings if required, and the corresponding queues/topics. No single set of connection parameters applies to every JMS provider.

With Spring Boot, a compatible JMS starter may auto-create `ConnectionFactory` and `JmsTemplate` beans. Before defining manual beans, check auto-configuration to avoid unintentionally creating duplicate templates/factories. The examples below illustrate manual bean creation when the app needs custom options.

### 3.1. Creating a JmsTemplate from a ConnectionFactory

Assume Spring already has a single `ConnectionFactory` bean configured to connect to the broker:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
public class OrderJmsTemplateConfiguration {

    @Bean("orderJmsTemplate")
    public JmsTemplate orderJmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setDefaultDestinationName("orders.events");
        template.setPubSubDomain(false); // false: queue; true: topic when resolving by name
        template.setReceiveTimeout(500); // ms; affects receive() operations only
        return template;
    }
}
~~~

Here:

- `new JmsTemplate(connectionFactory)` creates a template bound to the same JMS provider supplied by the factory.
- `setDefaultDestinationName(...)` sets the default destination, though `send("queue.name", ...)` or `convertAndSend("queue.name", ...)` can specify another destination.
- `setPubSubDomain(false)` resolves names using **queue** semantics. Switching to topics requires aligning publish-subscribe semantics with consumers, not merely changing string names.
- `setReceiveTimeout(500)` caps **a single synchronous receive** at 500 milliseconds when no message is available; it does not control the polling interval of a Spring Integration endpoint.

Do not set `setSessionTransacted(true)` just to "be safer" without defining transaction boundaries. Section 8 explains why commit timing matters more than a configuration flag.

## 4. Sending JMS messages with JmsTemplate

`JmsTemplate` offers two common approaches:

1. **`send(...)`:** manually create a JMS `Message` via `MessageCreator`, giving direct control over `TextMessage`, `BytesMessage`, and headers/properties.
2. **`convertAndSend(...)`:** pass a Java object/payload and let `MessageConverter` build the JMS Message; a `MessagePostProcessor` can add metadata after conversion.

### 4.1. Example sending JSON with convertAndSend

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final JmsTemplate jmsTemplate;

    public OrderEventPublisher(
            @Qualifier("orderJmsTemplate") JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void publishOrderPaid(String jsonBody, String eventId) {
        jmsTemplate.convertAndSend("orders.events", jsonBody, message -> {
            message.setStringProperty("eventId", eventId);
            message.setStringProperty("eventType", "OrderPaid");
            message.setIntProperty("schemaVersion", 1);
            return message;
        });
    }
}
~~~

JSON payload:

~~~json
{
  "eventId": "evt-6001",
  "schemaVersion": 1,
  "eventType": "OrderPaid",
  "orderId": "ORD-600",
  "amount": 320000
}
~~~

With the default `SimpleMessageConverter`, a `String` normally produces a JMS `TextMessage`. `MessagePostProcessor` adds **JMS properties**; values must use JMS-supported types. The event ID in the payload should be a stable business key; the provider-generated `JMSMessageID` per send can differ when the app retries.

**Do not confuse "method returned without exception" with "consumer processed successfully".** `convertAndSend` completes when the provider accepts the send under the active session, transaction, and QoS settings. The consumer may not have received or committed business state yet.

### 4.2. Example manually creating a TextMessage with send

~~~java
// jmsTemplate is an injected bean; this snippet runs inside a service method.
jmsTemplate.send("orders.events", session -> {
    jakarta.jms.TextMessage message =
            session.createTextMessage("{\"eventId\":\"evt-6002\"}");
    message.setStringProperty("eventType", "OrderPaid");
    return message;
});
~~~

`send` fits when you need a specific JMS message type or metadata that a converter cannot infer automatically. For most simple JSON contracts, `convertAndSend` keeps code shorter.

### 4.3. QoS when sending: persistence, priority, TTL

JMS supports delivery properties such as delivery mode, priority (0–9), and time-to-live (TTL). `JmsTemplate` can configure QoS:

~~~java
JmsTemplate notificationTemplate = new JmsTemplate(connectionFactory);
notificationTemplate.setExplicitQosEnabled(true);
notificationTemplate.setDeliveryPersistent(false);
notificationTemplate.setPriority(3);
notificationTemplate.setTimeToLive(60_000L); // 60 seconds
~~~

This is an **example for expirable notifications**, not a recommendation for payment events or data requiring durable storage. JMS defaults typically send persistent messages at priority 4 with unlimited TTL, though providers and app settings can alter defaults. `setExplicitQosEnabled(true)` instructs the template to actually apply the configured QoS values on send.

Never mutate configuration properties of a singleton `JmsTemplate` on each service call from multiple threads. If different message types require different QoS, define separate template beans or use dynamic QoS mechanisms supported by the endpoint.

## 5. Receiving JMS messages with JmsTemplate

`JmsTemplate.receive(...)` performs a **synchronous receive**: the calling thread waits until the broker returns a message or the timeout expires. In Spring Integration applications, this mechanism underpins the **JMS polling inbound channel adapter**.

~~~java
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

// Single receive call, not a continuous listener.
Message message = orderJmsTemplate.receive("orders.import");

if (message == null) {
    // No JMS message arrived before receiveTimeout expired.
} else if (message instanceof TextMessage textMessage) {
    String json = textMessage.getText();
    // Parse JSON and process per business contract.
} else {
    throw new IllegalArgumentException("Unsupported JMS message type");
}
~~~

`receiveAndConvert("orders.import")` is a more concise option when you want the converter to return a Java payload:

~~~java
Object payload = orderJmsTemplate.receiveAndConvert("orders.import");
if (payload instanceof String json) {
    // TextMessage -> String with default SimpleMessageConverter.
}
~~~

The returned value may be `null` if no message arrives within the wait period; the Java object type depends on `MessageConverter`.

### 5.1. `receiveTimeout` values

| `receiveTimeout` | `JmsTemplate` behavior | Use case |
|---|---|---|
| `-1` | Does not wait; uses JMS `receiveNoWait()` | Poller needs to finish quickly when the queue is empty |
| `0` | Waits indefinitely until a message arrives (plain `JmsTemplate` default) | Only when intentionally accepting long thread blocking |
| `500` | Waits at most 500 ms per receive attempt | Synchronous workers/tools needing an explicit timeout |

**Distinguish timeout from poll schedule:** `receiveTimeout` is the maximum wait for **each JMS receive call**. Spring Integration poller's `fixedDelay(5000)` is the interval between **poll attempts**. If receive timeout is 10 seconds, one poll can take up to 10 seconds before returning empty-handed, even if fixed delay is only 5 seconds.

When the broker continuously has messages, multiple `receive()` calls and handler executions can stretch a single poll if `maxMessagesPerPoll` is large. Therefore, account for total timeout, batch size, and scheduler thread count together.

### 5.2. Using JmsTemplate in Spring Integration inbound polling

In Java DSL, you can configure a polling inbound adapter from `ConnectionFactory` and tune its internal template:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;

@Bean
public IntegrationFlow inboundOrdersPolling(ConnectionFactory connectionFactory) {
    return IntegrationFlow.from(
            Jms.inboundAdapter(connectionFactory)
                    .destination("orders.import")
                    .configureJmsTemplate(template ->
                            template.receiveTimeout(-1)),
            endpoint -> endpoint.poller(poller ->
                    poller.fixedDelay(5000)
                          .maxMessagesPerPoll(10)))
            .handle(String.class, (json, headers) -> {
                // Illustration: replace with idempotent validation + import service.
                System.out.println("JMS incoming: " + json);
                return null;
            })
            .get();
}
~~~

In this example, `.configureJmsTemplate(...)` configures the template for **this adapter** without altering the `orderJmsTemplate` bean defined in section 3. `receiveTimeout(-1)` lets empty-queue polls return quickly. Since Spring Integration 5.0.8, certain defaults involving `CachingConnectionFactory` and `cacheConsumers` may already use no-wait; setting it explicitly avoids ambiguity when switching providers or configs.

The `maxMessagesPerPoll(10)` limit is at most 10 messages per poll, **not** a throughput guarantee of 10 messages every 5 seconds; handler duration, network, and transactions all affect cadence. The polling adapter is **one-way**: it sends no JMS reply to the producer.

## 6. MessageConverter, DestinationResolver, and queue/topic

`JmsTemplate` defaults to `SimpleMessageConverter` and `DynamicDestinationResolver`, though applications can substitute implementations matching partner contracts.

### 6.1. MessageConverter

| Java data when sending | JMS body typically created | Typical type when received |
|---|---|---|
| `String` | `TextMessage` | `String` |
| `byte[]` | `BytesMessage` | `byte[]` |
| `Map` with JMS-compatible types | `MapMessage` | `Map` |
| `Serializable` | `ObjectMessage` | Java object |

**Do not assume a DTO turns into JSON automatically.** When producers and consumers communicate across Java, .NET, or Node.js, use a `TextMessage` carrying JSON with `schemaVersion` or a schema-governed binary format, and serialize/deserialize explicitly with validation. `ObjectMessage` carries class-compatibility and deserialization risks and is usually a poor choice for cross-service contracts.

Example building a JSON payload before `convertAndSend`:

~~~java
// orderPaid is a business DTO; objectMapper is a Jackson ObjectMapper.
try {
    String json = objectMapper.writeValueAsString(orderPaid);
    jmsTemplate.convertAndSend("orders.events", json);
} catch (com.fasterxml.jackson.core.JsonProcessingException ex) {
    throw new IllegalStateException("Cannot serialize OrderPaid", ex);
}
~~~

On the receiving side, parse and validate the schema before persisting data. When contracts evolve, include `schemaVersion` and a backward-compatibility strategy.

### 6.2. Queue, topic, and DestinationResolver

| JMS destination | Model | What to focus on |
|---|---|---|
| **Queue** (`pubSubDomain=false`) | Competing consumers; each JMS message is processed by one queue consumer | Work distribution, business processing, retries, and DLQ |
| **Topic** (`pubSubDomain=true`) | Publish-subscribe; multiple subscriptions can receive copies | Durable/shared subscriptions and behavior when subscribers are offline |

`setPubSubDomain(true)` affects how `DynamicDestinationResolver` creates/looks up destinations **by name**; if you pass a concrete `Destination` object, that object itself determines destination type. Never assume naming a destination differently automatically turns a queue like `orders.events` into a topic.

Production environments may require a specialized `DestinationResolver` or JNDI lookup. Destination creation permissions and naming policies belong to the broker; never pass unvalidated user input directly as a destination name.

## 7. ConnectionFactory: caching, pooling, and lifecycle management

`ConnectionFactory` is the entry point for opening JMS connections. Some JMS providers supply factories with built-in connection pooling; Spring provides decorators to reuse resources and reduce setup overhead.

### 7.1. Common options

| Factory type | Behavior | Suitable scenario |
|---|---|---|
| JMS provider factory | Creates connections/sessions per provider behavior | Every app needing a driver to reach the broker |
| `SingleConnectionFactory` | Shares one `Connection` and suppresses logical close calls | Standalone/tests or when only connection reuse is needed |
| `CachingConnectionFactory` | Extends `SingleConnectionFactory`, adds session, producer, and optional consumer caching | Repeated `JmsTemplate` calls needing lower overhead |
| Provider pooled factory / JNDI-managed factory | Pool/lifecycle managed by provider or app server | High load or centrally managed environments |

Illustrative cache configuration when the **target ConnectionFactory is not yet pooled/cached**:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.jms.connection.CachingConnectionFactory;

// vendorConnectionFactory is the factory provided by the JMS vendor.
CachingConnectionFactory caching =
        new CachingConnectionFactory(vendorConnectionFactory);
caching.setSessionCacheSize(10);
caching.setCacheProducers(true);
caching.setCacheConsumers(true);
~~~

This is a **configuration fragment**; do not create duplicate beans in an app already auto-configured by Spring Boot. `sessionCacheSize` sets cached sessions per acknowledge/session mode; total open sessions can exceed that number when multiple modes are used. Appropriate sizing depends on actual concurrency rather than one universal number.

`CachingConnectionFactory` can automatically reconnect after an exception. However, **reconnection does not prove whether a prior send succeeded or failed**, nor does it solve replay, transactions, or business-layer idempotency.

### 7.2. Special note for listener containers

`DefaultMessageListenerContainer` typically maintains **its own caching/recovery mechanism**. Spring Framework notes that wrapping a container with an external `CachingConnectionFactory` can cause issues with stop/start, consumer scaling, or durable subscriptions. For message-driven inbound adapters or inbound gateways, check the listener container configuration before sharing one caching factory across every component.

Avoid "double caching" when the provider already pools connections and Spring Boot also wraps with `CachingConnectionFactory`. Signs of misconfiguration include excessive JMS sessions, consumers unintentionally holding messages, slow recovery, broker connection-quota errors, or unexpected listener shutdown behavior.

### 7.3. Singleton beans and thread safety

`JmsTemplate` is designed for reuse as a singleton bean once configured. Multiple services can invoke `convertAndSend` concurrently on one instance; each call obtains appropriate JMS resources from the factory. **Never mutate `defaultDestination`, `receiveTimeout`, QoS, converter, or transaction flags on a shared template while multiple threads are using it.**

Do not store a `Session` or `MessageProducer` from a `JmsTemplate` call to reuse directly across threads. A JMS `Session` is not designed for concurrent multi-threaded access; let Spring/the provider manage its lifecycle.

## 8. Transactions, acknowledgement, and commit timing

### 8.1. JmsTemplate defaults

A plain `JmsTemplate` defaults to **non-transacted** sessions and **AUTO_ACKNOWLEDGE**. If you execute `receive()` and then a database write fails, the broker may already treat the JMS message as received. That is why receipt/transaction configuration must consider the **entire flow**, not just one template call.

| Scenario | What is protected by a transaction? | Consequence |
|---|---|---|
| Plain `convertAndSend` | Sends under default session/QoS; does not cover the database | Send success does not prove DB and consumer are in sync |
| `receive` without a transaction | Receive/ack according to session mode | Downstream handler errors may not trigger broker redelivery |
| `JmsTemplate.sessionTransacted=true` on a receive call | Local JMS transaction scoped to the template call | Commit usually completes before the downstream flow runs |
| `JmsTransactionManager` wrapping a synchronous chain | JMS receive/send participate in a transaction on the same resource | Errors escaping the boundary can roll back JMS |
| Separate DB transaction + separate JMS transaction | Each resource commits independently | Not atomic between DB and JMS without coordination |

### 8.2. JmsTransactionManager

Spring provides `JmsTransactionManager` to bind a JMS session to the thread executing a transaction. Bean example:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.connection.JmsTransactionManager;

@Bean("orderJmsTransactionManager")
public JmsTransactionManager orderJmsTransactionManager(
        ConnectionFactory connectionFactory) {
    return new JmsTransactionManager(connectionFactory);
}
~~~

When an active matching transaction exists, `JmsTemplate` obtains the Spring thread-bound session and participates in that transaction. If the application has both `DataSourceTransactionManager` and `JmsTransactionManager`, specify the intended manager where the transaction starts; never assume a default `@Transactional` annotation covers both resources.

### 8.3. Transactions in Spring Integration polling

Setting `sessionTransacted=true` on the receiving template is **not enough** to roll back when a downstream handler fails: if the transaction only wraps `receive()`, commit completes before the Spring Message is sent onto `MessageChannel`.

For a **JMS polling inbound channel adapter**, place transaction advice on the **poller**, for example in the endpoint configuration:

~~~java
endpoint -> endpoint.poller(poller ->
        poller.fixedDelay(5000)
              .maxMessagesPerPoll(10)
              .transactional(orderJmsTransactionManager))
~~~

This fragment replaces the poller in section 5; `orderJmsTransactionManager` is injected into the flow definition method. The handler and channel chain must stay **synchronous** (typically using `DirectChannel`) so exceptions propagate to the transaction advice. Routing through an `ExecutorChannel` or `QueueChannel` allows downstream work to run after the JMS transaction has already committed.

For a **message-driven inbound adapter**, configure transactions on the `MessageListenerContainer`; it receives messages and controls transactions around the listener callback. `JmsTemplate` remains used for appropriate send operations, not as a substitute for the listener container.

### 8.4. Why is idempotency still required?

Suppose a service receives a JMS request, commits order status to PostgreSQL, and then the JMS transaction rolls back due to a network error before acknowledging receipt. The broker may redeliver the same message; if the handler writes again, data is duplicated.

A resilient workflow typically:

1. Includes a stable `eventId` or `requestId` in the payload.
2. In the same DB transaction, inserts an idempotency key with a unique constraint and applies the business change.
3. When the same ID arrives again, returns the stored result or skips safely.
4. Lets transient errors propagate to the transaction boundary so the broker redelivers per policy.
5. Uses an outbox when **writing DB state and emitting JMS events** must survive crashes reliably.

`JmsTransactionManager` does **not** automatically provide atomic commits between JMS and a DB. XA/distributed transactions make sense only when supported by the broker, database, and transaction manager, and when operational complexity is justified.

## 9. Where does Spring Integration use JmsTemplate?

This mapping is worth remembering in the `SPRING_INTEGRATION_ADAPTERS` module:

| Spring Integration endpoint | How JMS works underneath | Uses a poller? |
|---|---|---|
| JMS **polling inbound channel adapter** | `JmsTemplate.receive()` via `JmsDestinationPollingSource` | **Yes**, configured on the adapter |
| JMS **message-driven inbound channel adapter** | JMS `MessageListenerContainer` callback on incoming message | **No** |
| JMS **outbound channel adapter** | `JmsTemplate` converts and sends messages on demand | **No** |
| JMS **inbound gateway** | Listener container receives request, processes Spring reply, sends JMS reply | No poller at the receive point |
| JMS **outbound gateway** | Sends JMS request and waits for JMS reply, managing reply destination/correlation | No poller needed for Spring request source |

Example outbound adapter using `ConnectionFactory`:

~~~java
@Bean
public IntegrationFlow orderEventsOutbound(ConnectionFactory connectionFactory) {
    return IntegrationFlow.from("orderEventsOutput")
            .handle(Jms.outboundAdapter(connectionFactory)
                    .destination("orders.events"))
            .get();
}
~~~

In Java DSL, the outbound adapter creates or uses an appropriate JMS template to send; this handler is triggered by Spring Messages entering `orderEventsOutput`. While you can call `JmsTemplate` directly in a service, the adapter integrates naturally with Spring Integration's `MessageChannel`, transformers, filters, routers, and error handling.

If the application already defines a custom `JmsTemplate` bean with custom converter, caching, or QoS settings, check whether the adapter uses that bean or creates a new template from `ConnectionFactory`. **Sharing the same factory does not mean sharing all template settings.** Configure the adapter directly via its supported API or pass the intended template into the endpoint when needed.

## 10. Error handling and troubleshooting

Provider-originated JMS errors are typically translated by `JmsTemplate` into unchecked `org.springframework.jms.JmsException` subclasses, making classification easier for callers. However, a network error during a send **can leave an uncertain outcome**: the broker may have received the message even though the client never saw confirmation. Retries must account for duplicates.

| Symptom | Common cause | How to investigate |
|---|---|---|
| Cannot create `ConnectionFactory` | Missing starter/driver, invalid URL/credentials | Check beans, classpath, broker URL, auth/TLS |
| Send reports destination does not exist | Queue/topic not created or lacking auto-create permission | Check name, `pubSubDomain`, and broker policy |
| `receive()` hangs for a very long time | `receiveTimeout=0` (infinite wait) | Set positive timeout or `-1` as needed |
| Poller runs but receives no messages | Wrong destination, converter error, broker offline, another consumer took them | Check queue depth, listeners/consumers, logs, and timeouts |
| Sending JSON but consumer gets Java `ObjectMessage` | Object payload not serialized to JSON | Serialize explicitly or configure matching converter |
| Message processed twice | Redelivery/retry after error, producer resend | Use `eventId` + unique constraint/idempotent handler |
| Broker runs out of connections/sessions | Misconfigured factory/pool/cache or resource leak | Check connection/session metrics, pool size, concurrency |
| DMLC fails to stop/start cleanly | External consumer caching or bad session lifecycle | Review `CachingConnectionFactory` usage with listeners |
| Messages lost on DB failure | JMS receive acknowledged before DB failure | Align transaction boundaries and idempotency |
| Producer send succeeds with no downstream result | Slow consumer, queued messages, or DLQ | Inspect queue depth, message age, consumer health, and DLQ |

**Three distinct time settings:**

- `JmsTemplate.receiveTimeout`: wait time for **a single receive**.
- Poller `fixedDelay`/`fixedRate`: trigger cadence in Spring Integration.
- Broker/provider connect/send timeouts or JMS `timeToLive`: control separate aspects; TTL is not how long a caller waits for a reply.

In production, monitor successful/failed send and receive counts, operation latency, queue depth, oldest message age, consumer counts, session pools/caches, reconnect counts, redeliveries, and DLQs. Logs should include `eventId`, JMS message ID, correlation ID, destination, and error type when available; avoid logging sensitive payload contents.

## 11. Hands-on exercise: building the JMS foundation for order import/export flows

**Context:** a test broker has queues `orders.events` (emitting events) and `orders.import` (receiving import commands). Configure the provider factory; initialize `orderJmsTemplate` as in section 3, and register only one test consumer per queue so results are easy to observe.

1. **Initialization:** verify the app creates `ConnectionFactory` and `orderJmsTemplate`; log the factory class name without logging credentials.
2. **Sending JSON:** call `OrderEventPublisher.publishOrderPaid(...)`; verify with a test consumer that a `TextMessage` arrives with the expected `eventId` and properties.
3. **Manual message sending:** call `JmsTemplate.send(...)` to compare with `convertAndSend(...)`; pinpoint where the converter runs.
4. **Synchronous receive:** push a `TextMessage` onto `orders.import`; call `receiveAndConvert(...)` and verify a `String` payload.
5. **Empty queue:** test `receiveTimeout(-1)` and `receiveTimeout(500)`; record return times and `null` results.
6. **Polling:** run the flow from section 5 with `fixedDelay(5000)` and `maxMessagesPerPoll(10)`; push 25 messages to the queue and verify each poll stays within the cap (with no competing consumers).
7. **Converter:** send a `String`, `byte[]`, and an unserialized DTO; explain why a DTO requires an explicit contract format.
8. **Broker offline:** cut connectivity before and during a send; inspect exceptions, reconnection, and how retries can produce duplicates.
9. **Transactions:** simulate a failure after receive but before DB write; compare non-transacted receive with a transactional poller and observe redelivery.
10. **Caching:** measure connection/session counts with an uncached factory vs. a cached factory in a test environment; avoid double caching and observe listener behavior on restart.
11. **Business integrity:** use `eventId` as a unique key on the receiving side; resend the same event to prove the DB creates no duplicate records.

For testing transactions, acknowledgement, redelivery, and recovery, **you must use a real broker/provider or matching container environment**. Mocking `JmsTemplate` cannot prove the broker persisted, redelivered, or rolled back a message.

### Self-check questions

1. How do `ConnectionFactory` and `JmsTemplate` differ in responsibility? Why does a template need a factory?
2. At which conversion step does `convertAndSend` differ from `send`?
3. Why does `receiveTimeout(-1)` fit a polling inbound adapter when the queue is empty?
4. Does `fixedDelay(5000)` mean each `receive()` waits only 5 seconds?
5. Why should `CachingConnectionFactory` not be layered blindly on top of every provider pool or listener container?
6. Does `sessionTransacted=true` on a single `receive()` operation protect downstream handlers? Why or why not?
7. What happens when a producer resends the same event after an uncertain timeout? Which key prevents duplicates?
8. When should you use a JMS message-driven inbound adapter instead of a polling adapter?
9. Why does `JmsTransactionManager` not guarantee that a DB transaction and a JMS send commit together?
10. When the contract expects JSON but the Java payload is a DTO, what additional step must be configured/implemented?

## 12. References

- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): how Spring Integration endpoints depend on `JmsTemplate` and listener containers; polling, transaction, and gateway configuration.
- [Spring Framework Reference — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): `JmsTemplate`, converters, `ConnectionFactory`, and resource caching.
- [Spring Framework API — JmsTemplate](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/core/JmsTemplate.html): `send`, `convertAndSend`, `receive`, `receiveAndConvert`, timeouts, QoS, and transactions.
- [Spring Framework API — CachingConnectionFactory](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/connection/CachingConnectionFactory.html): session/producer/consumer caching, `sessionCacheSize`, and connection lifecycle.
- [Spring Framework API — DefaultMessageListenerContainer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html): concurrency, recovery, acknowledgement/transactions, and notes on external caching.

**Remember:** `ConnectionFactory` supplies JMS connection resources; `JmsTemplate` executes synchronous send/receive operations on those resources. In Spring Integration, pick the right endpoint (polling, message-driven, outbound adapter, or gateway), configure caching/timeouts for your context, and wrap transactions around **the entire processing path that needs protection**. Business data still requires explicit message contracts and idempotency to remain safe under retries or redelivery.
