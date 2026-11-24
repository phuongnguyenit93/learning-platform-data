# JMS and the Role of Spring JMS for Broker-Based Systems

## Objectives

JMS (Java Message Service, now standardized as Jakarta Messaging) provides a standard API for Java applications to send, receive, and process messages through a messaging provider. Spring JMS builds a support layer on top of that API so Spring applications can work with a broker more easily: managing resources, sending messages, receiving messages asynchronously, converting payloads, and participating in transactions.

After this lesson, you will be able to:

- Distinguish between the JMS API, JMS provider, and broker.
- Understand queue, topic, producer, consumer, destination, session, and connection.
- Explain where Spring JMS fits in the architecture.
- Use `JmsTemplate` for synchronous sending and receiving.
- Use `@JmsListener` and listener containers for asynchronous message receiving.
- Understand acknowledgement, redelivery, persistence, and transactions.
- Choose the appropriate converter, destination, and connection factory.
- Recognize new APIs in Spring Framework 7 such as `JmsClient`.
- Build a Spring Boot application that sends and receives messages via ActiveMQ Artemis.

## 1. JMS, Provider, and Broker Are Three Different Concepts

JMS is an **API specification**, not a message broker. The specification defines interfaces and semantics so Java programs can send/receive messages under a common contract.

A JMS system typically has three parts:

1. **Java application:** creates messages, sends them to a destination, and processes received messages.
2. **JMS provider/client library:** implements the `jakarta.jms` interfaces and lets the application connect to the messaging system.
3. **Broker/server:** receives, routes, stores, and distributes messages according to queues, topics, subscriptions, policies, and product configuration.

Examples of products commonly used with JMS include Apache ActiveMQ Artemis and IBM MQ. A product must provide a compatible JMS provider for the application to use the JMS API. A broker can run separately as a standalone service, or run embedded in the application process for development and testing.

~~~text
Producer application
        |
        | jakarta.jms API
        v
JMS ConnectionFactory / provider client
        |
        | protocol / network connection
        v
Message broker
        |
        | queue, topic, subscription
        v
JMS provider client
        |
        | jakarta.jms API
        v
Consumer application
~~~

JMS standardizes how Java applications interact with a messaging provider. It does not require every broker to share the same administration model, network protocol, HA mechanism, dead-letter queue, or security configuration. Those parts remain product-dependent.

Spring JMS is also not a broker and does not replace the provider. Spring provides convenient APIs and infrastructure for applications to use the provider through `ConnectionFactory`.

## 2. Core Components in Jakarta Messaging

| Component | Role |
|---|---|
| `ConnectionFactory` | Entry point to create connections to the JMS provider; holds endpoint configuration, credentials, TLS, and vendor-specific properties. |
| `Connection` | Logical connection between the application and the provider. |
| `Session` | Context for creating producers/consumers/messages; manages processing order, acknowledgement, and transactions for a sequence of operations. |
| `Destination` | Logical address that receives messages, usually a `Queue` or `Topic`. |
| `MessageProducer` | Sends messages to a destination. |
| `MessageConsumer` | Receives messages from a destination or subscription. |
| `MessageListener` | Callback invoked when a consumer receives a message asynchronously. |
| `Message` | JMS message object, consisting of headers, properties, and body. |

The low-level API send flow typically looks like this:

~~~text
ConnectionFactory
    -> Connection
        -> Session
            -> MessageProducer
                -> send(Destination, Message)
~~~

The application also needs to close resources properly according to their lifecycle. Spring JMS reduces this boilerplate via templates and listener containers; the provider remains responsible for connection and transport.

### Session Has a Special Role

`Session` is not just where messages are created. It also:

- Creates producers, consumers, and messages.
- Determines the acknowledgement mode when the session is non-transacted.
- Groups send/receive operations within the session into a local transaction if the session is configured as transacted.
- Defines message operation ordering within the session scope.
- Manages retaining unacknowledged messages and redelivery when the session is recovered.

Do not share a JMS `Session` arbitrarily across multiple threads. Let Spring manage sessions via `JmsTemplate` or a listener container, or follow the JMS API thread-safety rules if using the low-level API directly.

## 3. Queue and Topic: Two Messaging Domains

Jakarta Messaging defines two primary models.

### Queue — point-to-point

Producers send messages to a queue. One or more consumers can listen to the same queue, but each message is delivered to one consumer in the competing consumers group.

~~~text
Producer A ----                                 > Queue: orders.queue ---> Consumer 1
                /                    ----> Consumer 2
Producer B ----/
~~~

Queues fit work that needs to be distributed to workers:

- Order processing.
- Invoice generation.
- Sending emails.
- Running background tasks.
- Decoupling the producer from when the consumer processes the work.

When multiple consumers listen on the same queue, the provider decides how to distribute messages according to product rules and message selectors. Do not assume all consumers receive a copy.

### Topic — publish/subscribe

Producers publish messages to a topic. Each matching subscription receives its own copy of the message. Multiple independent subscribers can be interested in the same event.

~~~text
                    +---- Subscription A ---> Consumer A
Producer ---> Topic |
                    +---- Subscription B ---> Consumer B
                    |
                    +---- Subscription C ---> Consumer C
~~~

Topics fit event notifications:

- `OrderCreated` sent to inventory, analytics, and notification.
- A state-change event that multiple systems care about.
- Subscribers with independent lifecycles.

Distinguish between a **subscription** and a **consumer**: a subscription is an entity managed by the provider; a consumer is the object in the application used to receive messages from the subscription.

### Durable and non-durable subscriptions

- **Non-durable subscription:** typically only receives messages while the subscription is active. Offline subscribers can miss messages.
- **Durable subscription:** the provider retains matching messages for the subscription while the consumer is temporarily offline, according to broker configuration and storage policy.

A durable subscription does not mean every message is retained indefinitely. Retention duration, quota, expiry, policy, and subscription deletion depend on the provider.

Queue/topic are JMS abstractions; destination names and physical broker configuration must be administered consistently. JMS does not standardize all long-lived queue/topic administration operations.

## 4. What Does a JMS Message Contain?

A JMS message has three groups of data:

1. **Headers:** standard metadata defined by JMS, such as `JMSMessageID`, `JMSCorrelationID`, `JMSReplyTo`, `JMSDestination`, `JMSExpiration`, `JMSRedelivered`.
2. **Properties:** name–value pairs added by the application or provider, which can be used in message selectors.
3. **Body:** the main content of the message.

Common standard body types:

| Message type | Content |
|---|---|
| `TextMessage` | Text, commonly used for JSON/XML/plain text. |
| `BytesMessage` | Binary data. |
| `MapMessage` | Set of name–value pairs with JMS-supported data types. |
| `ObjectMessage` | A Java Serializable object. |
| `StreamMessage` | Sequence of typed values read sequentially. |
| `Message` | Message with no body, using only headers/properties. |

For new systems, `TextMessage` containing JSON or `BytesMessage` containing a schema-defined binary format is usually easier for polyglot integration than `ObjectMessage`. Do not deserialize Java objects from untrusted sources; use a schema-backed serializer and explicitly restrict allowed types.

### Headers, properties, and selectors

For example, a message has:

- `JMSCorrelationID = "REQ-2026-17"`
- Property `tenantId = "tenant-a"`
- Property `eventType = "OrderCreated"`
- Body as JSON containing order details.

Consumers can use a message selector to receive only messages matching conditions on JMS headers/properties, for example:

~~~sql
eventType = 'OrderCreated' AND tenantId = 'tenant-a'
~~~

Selectors do not query the JSON body. Only valid JMS headers/properties can be used in a selector. Producers and consumers must agree on property data types.

## 5. Durability, Delivery Mode, and Acknowledgement

JMS provides mechanisms for the provider to manage delivery. Each concept should be understood clearly because they do not automatically guarantee "exactly once" for the entire business operation.

### Persistent and non-persistent

| Delivery mode | Meaning |
|---|---|
| `PERSISTENT` | Requests the provider to store the message under a durable policy to survive provider/server failures according to JMS semantics. |
| `NON_PERSISTENT` | Allows the provider to optimize performance; messages may be lost if the provider fails. |

A persistent message can still be redelivered if a consumer fails or a transaction rolls back. Therefore, consumers should be idempotent and have a mechanism to detect already-processed messages.

### Acknowledgement modes

For non-transacted sessions, JMS defines the main modes:

- **AUTO_ACKNOWLEDGE:** the provider automatically acknowledges after the consumer receives a message according to API semantics.
- **CLIENT_ACKNOWLEDGE:** the application calls acknowledge; acknowledgement can apply to messages already delivered by the same session rather than only a single message.
- **DUPS_OK_ACKNOWLEDGE:** the provider may acknowledge lazily to reduce overhead; the consumer must tolerate duplicate deliveries.
- **Transacted session:** acknowledgement is managed through session commit/rollback rather than a separate acknowledgement mode.

Once a listener finishes processing and acknowledges, the provider can remove the message from the delivery flow. If processing fails and the message has not been committed/acknowledged, the provider can redeliver it depending on mode and policy.

### Redelivery and duplicates

When a message is redelivered, the provider may set `JMSRedelivered` and update `JMSXDeliveryCount`. Retry counts, retry intervals, backoff, expiry, and dead-letter policies depend on the provider.

Never assume a message appears strictly once. This scenario can occur:

1. The consumer updates the database successfully.
2. The process crashes before JMS acknowledge/commit.
3. The provider redelivers the message.
4. The consumer runs the business logic again.

A common solution is idempotency: use an event ID/business key to check whether the message has already been applied before executing side effects again.

## 6. Where Does Spring JMS Fit?

Spring JMS belongs to the `spring-jms` module of Spring Framework. It works with the Jakarta Messaging API and provider client, providing utility classes:

| Spring component | Role |
|---|---|
| `JmsTemplate` | Synchronous message sending and receiving; manages Connection/Session/Producer/Consumer and releases resources. |
| `@JmsListener` | Declares a message-handling method. |
| `DefaultMessageListenerContainer` | Listener container supporting thread management, consumers, transactions, recovery, and scaling. |
| `SimpleMessageListenerContainer` | Simple listener container with a fixed number of consumers and provider-driven callbacks. |
| `JmsListenerContainerFactory` | Creates and configures listener containers for endpoints. |
| `JmsMessagingTemplate` | Bridge between Spring `Message<?>` and JMS. |
| `JmsClient` | New fluent API in Spring Framework 7.0 for JMS operations. |
| `JmsTransactionManager` | Manages local transactions for a JMS ConnectionFactory. |
| `DestinationResolver` | Resolves destination names into JMS `Destination` objects. |
| `MessageConverter` | Converts application objects to JMS Messages and vice versa. |

Spring JMS helps applications focus on business logic. It does not provide a broker itself; the application still needs an appropriate JMS provider and broker/server.

## 7. Sending Messages with JmsTemplate

`JmsTemplate` is the central class of Spring JMS. It manages the JMS resource lifecycle during synchronous sends or receives.

Common operations:

~~~java
jmsTemplate.send("orders.queue", session -> {
    TextMessage message = session.createTextMessage("order-42");
    message.setStringProperty("eventType", "OrderCreated");
    return message;
});

jmsTemplate.convertAndSend("orders.queue", "order-42");

jmsTemplate.convertAndSend("orders.queue", orderCreated);
~~~

Differences:

- `send` takes a `MessageCreator`, allowing direct creation of a JMS Message using the JMS Session.
- `convertAndSend` takes an object; a JMS `MessageConverter` converts the object into a JMS Message.
- `receive` receives a JMS Message synchronously and can block the thread.
- `receiveAndConvert` receives and converts the payload into an object.
- `sendAndReceive` supports basic request/reply, typically using a temporary queue for replies when appropriate.

QoS settings such as delivery mode, priority, and time-to-live can be configured. When you want `JmsTemplate` to actively apply configured QoS values instead of provider defaults, enable `explicitQosEnabled`.

`JmsTemplate` is thread-safe once configured. A single shared instance can be injected into multiple services; there is no need to create a new template per request.

### Synchronous receiving

`JmsTemplate.receive(...)` waits for a message on the calling thread. Configure `receiveTimeout` to avoid blocking indefinitely:

~~~java
jmsTemplate.setReceiveTimeout(2_000);
Message message = jmsTemplate.receive("orders.reply");
~~~

For applications that process continuously, a listener container is usually better suited than synchronous receive because it receives messages asynchronously and manages consumers/threads.

## 8. Asynchronous Receiving with @JmsListener

Spring lets you write Message-Driven POJOs (MDPs) without implementing `jakarta.jms.MessageListener` directly.

~~~java
@Component
public class OrderListener {

    @JmsListener(destination = "orders.queue")
    public void receive(String orderId) {
        System.out.println("received=" + orderId);
    }
}
~~~

`@JmsListener` declares the destination and handler method. The listener container registers the consumer, receives messages, and invokes the method.

You can receive the payload, the JMS Message, or metadata parameters supported by Spring. For example:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(
        String payload,
        @Header(JmsHeaders.MESSAGE_ID) String messageId) {
    // Process payload and metadata.
}
~~~

The snippet above illustrates Spring JMS header binding; when using header parameters, import the proper Spring JMS annotations and constants.

In plain Spring Framework applications, enable listener endpoints with `@EnableJms` and configure a `JmsListenerContainerFactory`. With Spring Boot when JMS auto-configuration is active, listener infrastructure is auto-configured and declaring `@EnableJms` separately is usually unnecessary.

If the container runs multiple consumers concurrently, the listener bean must be thread-safe. Avoid storing per-message mutable state in shared fields; prefer local variables, stateless services, and proper synchronization mechanisms.

## 9. SimpleMessageListenerContainer and DefaultMessageListenerContainer

Spring provides two standard listener containers:

| Feature | SimpleMessageListenerContainer | DefaultMessageListenerContainer |
|---|---|---|
| Receiving mechanism | Registers listener via `MessageConsumer.setMessageListener`; provider invokes callback | Container actively pulls messages and dispatches listener via tasks |
| Consumers | Fixed count at startup | Configurable concurrency and dynamic scaling with load |
| External transactions | Does not participate in external transactions the way DMLC does | Can participate in external transactions, such as JTA/XA |
| Recovery | Close to provider callbacks | Supports self-recovery/reconnect on broker interruptions |
| Use case | Simple setup, minimal requirements | Most applications requiring concurrency, recovery, and transaction management |

`DefaultMessageListenerContainer` is usually the right choice for production applications. It supports local JMS transactions and external transactions when properly configured.

### Note on AUTO_ACKNOWLEDGE

Spring documentation warns against assuming `AUTO_ACKNOWLEDGE` is reliable enough by default for listener processing. With certain ways of running listeners, a message can be acknowledged even if the listener business logic fails or the container is shutting down.

If reliable processing is required, consider transacted sessions. When a listener throws an exception inside a local transaction, the container can roll back the session and the provider redelivers the message.

Redelivery can create duplicates. Combine transactions with an idempotent consumer and an appropriate dead-letter/retry policy. Do not expect changing the acknowledgement mode alone to automatically give exactly-once business processing.

## 10. Transactions in Spring JMS

There are two transaction levels to distinguish.

### Local JMS transactions

`JmsTransactionManager` manages transactions for a single `ConnectionFactory`. It binds the JMS Connection/Session pair to the thread; `JmsTemplate` automatically detects and uses that transactional resource.

A local JMS transaction can group multiple JMS operations in the same session into a single commit/rollback. It does not automatically create a distributed transaction with a database.

Example:

~~~java
@Transactional(transactionManager = "jmsTransactionManager")
public void publishOrderEvents(Order order) {
    jmsTemplate.convertAndSend("orders.created", order.getId());
    jmsTemplate.convertAndSend("audit.events", "created:" + order.getId());
}
~~~

This example requires configuring `JmsTransactionManager` and the destinations. When the transaction rolls back, JMS operations in that session can be rolled back together.

### XA/JTA transactions

If JMS and a database need to be coordinated in the same distributed transaction, you need:

- A JTA transaction manager.
- An XA-capable JMS ConnectionFactory.
- An XA-configured DataSource/provider.
- A transaction coordinator and corresponding deployment configuration.

XA carries high overhead and complexity. For many systems, the transactional outbox and idempotent consumer pattern is a more practical choice: write business data and an outbox record in a single database transaction, then have a publisher forward outbox events to the broker.

### Do not conflate these three events

- `send` returns successfully: the send operation via the API/provider was accepted under the contract.
- Broker stores the message: depends on delivery mode, persistence, and broker configuration.
- Consumer completes business processing: must be confirmed separately via reply/status/event or business data.

Do not infer that the consumer has committed to the database merely because `JmsTemplate.convertAndSend` did not throw an exception.

## 11. Destination and DestinationResolver

A JMS destination can be a queue or a topic. In an application, a destination can be referenced by a `Destination` object or by name.

Spring uses `DestinationResolver` to resolve destination names into JMS objects:

- Can look up pre-administered destinations via JNDI.
- Can resolve destinations by name via a resolver.
- Some providers support dynamic destination creation, though the physical queue/topic creation mechanism is vendor-specific.

`pubSubDomain` determines the default domain for name-based destination resolution. By default Spring JMS uses queues (point-to-point). If using topics, sender and listener container configurations must agree on the pub/sub domain.

In Spring Framework 7, the default resolver was changed to `SimpleDestinationResolver`, which can cache Queues/Topics resolved from a Session. If dynamic resolution on every call is needed, an appropriate resolver such as `DynamicDestinationResolver` can be configured.

Destination names must match the broker configuration. A queue name in code does not guarantee the queue has been created or that the application has send/receive permissions.

## 12. Message Conversion: Java Objects and JMS Messages

The JMS API has specific message types such as `TextMessage`, `BytesMessage`, `MapMessage`, and `ObjectMessage`. Spring JMS `MessageConverter` helps convert business objects into one of those forms.

The default `SimpleMessageConverter` supports basic types like String, byte array, Map, and Serializable. For non-Serializable POJOs, a custom converter is needed, such as a Jackson JSON converter to produce a `TextMessage`.

Distinguish between two interfaces with the same name:

- `org.springframework.jms.support.converter.MessageConverter`: converts objects to/from JMS `Message`.
- `org.springframework.messaging.converter.MessageConverter`: converts payloads to/from Spring `Message<?>`.

`JmsMessagingTemplate` and `JmsClient` integrate with Spring's common messaging abstraction; `JmsTemplate` operates at the JMS layer. Use the converter from the exact package required by the API.

When passing objects through a broker, use an explicit format such as JSON/bytes and manage schemas. Avoid relying on Java native serialization and avoid accepting `ObjectMessage` from untrusted sources.

## 13. JmsMessagingTemplate and JmsClient in Spring Framework 7

### JmsMessagingTemplate

`JmsMessagingTemplate` builds on `JmsTemplate`, but works with Spring `Message<?>` and `spring-messaging` abstractions. It is useful when an application already uses `MessageHeaders`, `MessageChannel`, or Spring Messaging converters and wants to connect that flow to JMS.

### JmsClient

Spring Framework 7.0 introduces `JmsClient`, a fluent API for JMS operations. Built on top of `JmsTemplate`, it provides operation handles configurable per send/receive and can be created from a `ConnectionFactory` or a preconfigured `JmsTemplate`.

Example:

~~~java
JmsClient jmsClient = JmsClient.create(connectionFactory);

jmsClient.destination("orders.queue")
        .withTimeToLive(30_000)
        .send("order-42");
~~~

You can use its builder to configure `MessageConverter` and `MessagePostProcessor`. If you already have a `JmsTemplate` with shared settings, creating `JmsClient` from that template reuses that configuration.

`JmsClient` is a new API in Framework 7; projects on Framework 6.x continue using `JmsTemplate` and `JmsMessagingTemplate` according to their respective version.

## 14. Connections, Caching, and Pooling

A JMS operation may require a Connection, Session, Producer, and Consumer. Creating/destroying these objects for every message can cause overhead.

Spring provides:

- `SingleConnectionFactory`: reuses a single JMS Connection, suitable for certain standalone/test use cases.
- `CachingConnectionFactory`: extends this to cache sessions, producers, and consumers.
- Provider-specific pools: such as a vendor's pooled connection factory or pooled-jms.

In Jakarta EE/application servers, use a container-managed ConnectionFactory to participate in transactions and pooling according to the environment configuration. In standalone applications, use caching or a pool suited to the provider.

Do not share a JMS Session manually across multiple threads. Let the template/container manage sessions according to the proper lifecycle and threading model.

## 15. Spring Boot and Broker Configuration

Spring Boot auto-configures JMS infrastructure when it detects a suitable starter/provider on the classpath.

With ActiveMQ Artemis:

- `spring-boot-starter-artemis` provides the client and Spring infrastructure to connect to Artemis.
- Add `artemis-jakarta-server` if you want to run an embedded broker.
- `spring.artemis.mode=embedded` requests an embedded broker.
- `spring.artemis.mode=native` connects to a separately running broker.
- `spring.artemis.embedded.queues` and `spring.artemis.embedded.topics` declare destinations to create for the embedded broker.
- `spring.jms.cache.session-cache-size` configures the session cache.
- `spring.jms.pub-sub-domain` controls the default queue/topic domain.

Example connecting to a standalone broker:

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://broker.example:61616
spring.artemis.user=${JMS_USER}
spring.artemis.password=${JMS_PASSWORD}
spring.jms.pub-sub-domain=false
~~~

Credentials should be loaded from a secret manager or environment variables. Do not commit real passwords to source control.

## 16. Runnable Java 17+ Example: Sending and Receiving via Embedded Artemis

This example uses Spring Boot 4.1.2, Spring JMS, and embedded ActiveMQ Artemis. The producer sends a String to a queue; the `@JmsListener` method receives the message asynchronously. Since the example only demonstrates a queue and String payload, no JSON converter is needed.

Project structure:

~~~text
spring-jms-artemis-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          JmsBrokerDemoApplication.java
          OrderListener.java
      resources/
        application.properties
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>spring-jms-artemis-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
        </dependency>

        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-server</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### application.properties

~~~properties
spring.artemis.mode=embedded
spring.artemis.embedded.queues=orders.queue
spring.artemis.embedded.persistent=false
spring.jms.pub-sub-domain=false
~~~

The embedded broker here uses in-memory storage for demo purposes. Do not use this configuration to assume data is durably persisted when the process or server stops.

### JmsBrokerDemoApplication.java

~~~java
package demo;

import java.util.concurrent.TimeUnit;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class JmsBrokerDemoApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(JmsBrokerDemoApplication.class, args)) {
            // ApplicationRunner waits for the asynchronous listener before shutdown.
        }
    }

    @Bean
    ApplicationRunner sendOrder(JmsTemplate jmsTemplate, OrderListener listener) {
        return args -> {
            String orderId = "ORD-42";
            System.out.println("sending=" + orderId);

            jmsTemplate.convertAndSend("orders.queue", orderId);

            if (!listener.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Timed out waiting for the JMS listener");
            }
        };
    }
}
~~~

### OrderListener.java

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    private final CountDownLatch received = new CountDownLatch(1);

    @JmsListener(destination = "orders.queue")
    public void receive(String orderId) {
        System.out.println("received=" + orderId);
        received.countDown();
    }

    public boolean await(long timeout, TimeUnit unit) throws InterruptedException {
        return received.await(timeout, unit);
    }
}
~~~

Run from the project directory with Java 17+ and Maven:

~~~bash
mvn spring-boot:run
~~~

Stdout lines printed by the application (ignoring Spring Boot startup logs):

~~~text
sending=ORD-42
received=ORD-42
~~~

How to read the example:

1. Spring Boot detects Artemis and configures `ConnectionFactory`, `JmsTemplate`, and the listener infrastructure.
2. Embedded Artemis creates the `orders.queue` queue.
3. `ApplicationRunner` calls `JmsTemplate.convertAndSend` to send a String; the default converter maps the String to a JMS `TextMessage`.
4. The listener container registers a consumer and invokes `OrderListener.receive` when a message arrives.
5. `CountDownLatch` is only used in the example to wait for the listener to finish before closing the application context.
6. This is an embedded example in a single JVM; for real deployments, switch the configuration to `native` and connect to an external broker.

## 17. Spring Integration and JMS

If the application uses Spring Integration, the `spring-integration-jms` module provides:

- Inbound channel adapter to receive messages from JMS and send them into a Spring Integration channel.
- Outbound channel adapter to send messages from a channel to a JMS destination.
- Inbound/outbound gateways for request/reply.
- Configuration based on Spring JMS's `JmsTemplate` and message listener containers.

Adapters are appropriate when connecting JMS to endpoints, transformers, routers, filters, and channels in an integration flow. If you only need to send/receive in regular Spring services, `JmsTemplate` and `@JmsListener` are usually simpler.

A JMS adapter does not turn a queue/topic into a Spring `MessageChannel`; the adapter is a bridge between the two abstractions.

## 18. Security and Operations

When connecting to a broker in production, pay attention to:

- Use TLS and proper authentication; do not transmit credentials in cleartext over untrusted networks.
- Grant least privilege: services should only send/receive on the destinations they need.
- Manage destinations, expiry, max size, redelivery, and dead-letter policies on the broker.
- Limit concurrency and consumer counts so you do not overload databases or downstream services.
- Monitor queue depth, enqueue/dequeue rate, consumer count, redelivery, DLQ, connection recovery, and processing latency.
- Use persistent delivery when durability is needed and configure the broker accordingly.
- Design idempotent consumers to handle duplicates/redelivery.
- Avoid Java native deserialization from untrusted sources; prefer JSON/bytes with controlled schemas.
- Do not log full message bodies if they contain personal information, tokens, or secrets.
- Test broker restarts, listener exceptions, transaction rollbacks, full queues, expired messages, and abrupt consumer shutdowns.

## 19. Common Errors

| Symptom | Common cause | What to check |
|---|---|---|
| Cannot connect to broker | Wrong URL, port, credentials, TLS, or broker not running | ConnectionFactory, broker logs, network, and TLS truststore |
| Destination not found | Queue/topic not created or name mismatch | Broker configuration, JNDI, or DestinationResolver |
| Listener does not receive messages | Wrong destination/domain, listener not started, or selector mismatch | `@JmsListener`, container factory, queue/topic, and selector |
| Consumer receives duplicates | Redelivery after rollback/crash or multiple publishes | JMSRedelivered, delivery count, idempotency key |
| Messages lost on listener failure | Inappropriate acknowledge mode/transaction | `sessionTransacted`, acknowledgement mode, and container behavior |
| Listener blocked | Calling synchronous receive or overly long business processing | Receive timeout, listener concurrency, downstream latency |
| Low throughput | Creating too many connections/sessions or missing cache/pool | CachingConnectionFactory, provider pool, and consumer count |
| Conversion exception | Payload type, charset, converter, or schema mismatch | MessageConverter, raw message type, content, and headers |
| Queue keeps growing | Insufficient consumer capacity or continuous processing failures | Queue depth, concurrency, DLQ, retry, and downstream |
| Send succeeds but consumer does not process | Broker receives message but route/selector/subscription does not match | Destination, selector, permissions, and consumer state |

## 20. Distinguishing JMS from Kafka and Other Broker APIs

JMS is a standard Java API. It fits when integrating with providers that implement Jakarta Messaging.

Kafka has its own protocol, client API, topic/partition model, offsets, and consumer groups. Kafka does not automatically become a JMS provider just because it is a messaging system. Connecting JMS with Kafka requires a specific bridge/connector or integration layer.

Similarly, Spring AMQP uses its own AMQP/RabbitMQ API; Spring JMS uses Jakarta Messaging. A broker may support multiple protocols, but the semantics of those protocols still differ. You cannot swap `JmsTemplate` for `RabbitTemplate` or `KafkaTemplate` merely by changing the destination name.

## 21. Spring JMS Selection Checklist

- [ ] Broker/provider implements Jakarta Messaging and has a compatible client.
- [ ] Application uses the `jakarta.jms` namespace (Spring 6/7); do not mix with legacy `javax.jms`.
- [ ] Choose queue or topic according to the distribution model.
- [ ] Destinations are created/administered and the service has access permissions.
- [ ] Producers/consumers agree on message type, converter, schema, and headers.
- [ ] Use `JmsTemplate` for synchronous send/receive; use listener containers for asynchronous receiving.
- [ ] Choose `DefaultMessageListenerContainer` or `SimpleMessageListenerContainer` based on transaction and concurrency requirements.
- [ ] Acknowledgement, session transaction, redelivery, and DLQ are defined.
- [ ] Consumers are idempotent to handle duplicates.
- [ ] ConnectionFactory has appropriate caching/pooling.
- [ ] TLS, authentication, authorization, and secret management are configured.
- [ ] Tests cover broker restarts, listener failures, and transaction rollbacks.

## Key Takeaways

- **JMS/Jakarta Messaging is a standard API; the provider implements the API and the broker performs storage, routing, and distribution.**
- A queue is point-to-point: each message is delivered to one consumer; a topic is publish/subscribe: each subscription receives a copy.
- `JmsTemplate` is the synchronous send/receive API; `@JmsListener` uses a listener container for asynchronous receiving.
- `DefaultMessageListenerContainer` fits most use cases needing concurrency, recovery, and transactions.
- Acknowledgement, persistent delivery, and transactions determine how messages are retained or redelivered; they do not automatically guarantee exactly-once business processing.
- `JmsTransactionManager` manages local JMS transactions for a single ConnectionFactory; XA/JTA requires provider and transaction coordinator configuration.
- Spring Framework 7 adds `JmsClient`; `JmsMessagingTemplate` connects JMS with Spring `Message<?>`.
- Spring JMS is not a broker and does not automatically make Kafka/AMQP into JMS.
- Production requires idempotency, observability, security, retry policies, and dead-letter handling.

## Official Documentation

- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
- [Spring Framework 7.0.10 Reference: Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Spring Framework Reference: Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html)
- [Spring Framework Reference: Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
- [Spring Framework Reference: JMS Namespace and Listener Containers](https://docs.spring.io/spring-framework/reference/integration/jms/namespace.html)
- [Spring Boot 4.1.2 Reference: JMS](https://docs.spring.io/spring-boot/4.1/reference/messaging/jms.html)
- [Spring Boot Getting Started: Messaging with JMS](https://spring.io/guides/gs/messaging-jms/)
- [Spring Integration Reference: JMS Support](https://docs.spring.io/spring-integration/reference/jms.html)
