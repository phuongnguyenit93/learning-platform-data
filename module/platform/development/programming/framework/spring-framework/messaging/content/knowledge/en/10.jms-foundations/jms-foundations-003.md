# ConnectionFactory, Connection, Session, Producer, and Consumer

> Objective: understand the role and lifecycle of the core resources in Jakarta Messaging (JMS), know how producers send messages and consumers receive messages, grasp transactions/acknowledgement, and understand how Spring JMS manages these resources via `JmsTemplate` and listener containers.

## 1. The Big Picture of JMS

JMS (Jakarta Messaging; formerly Java Message Service) is the standard API for Java applications to send and receive messages through a messaging provider such as ActiveMQ Artemis, IBM MQ, or another JMS-compatible product. The provider manages connections to the broker, destinations, storage, and message distribution according to product capabilities.

A typical send/receive flow has these components:

```text
Application
    |
    v
ConnectionFactory
    | createConnection()
    v
Connection
    | createSession()
    v
Session
    |                         |
    v                         v
MessageProducer           MessageConsumer
    |                         ^
    v                         |
Destination (Queue / Topic) --+
```

These components answer different questions:

- `ConnectionFactory`: creates connections to the JMS provider.
- `Connection`: represents the client's connection to the provider.
- `Session`: context for creating messages, creating producers/consumers, and managing transactions or acknowledgement.
- `MessageProducer`: sends messages to a destination.
- `MessageConsumer`: receives messages from a destination synchronously or asynchronously.
- `Destination`: send/receive target, usually a queue or topic.

In Spring, applications typically inject `ConnectionFactory` and then use `JmsTemplate` to send or a listener container to receive. Spring manages most of the creation, usage, and closing of resources for each operation.

## 2. ConnectionFactory: The Starting Point for Connections

`jakarta.jms.ConnectionFactory` is an interface provided by the JMS provider. Concrete implementations know how to connect to the broker using server addresses, authentication credentials, TLS, and provider-specific options.

Applications typically obtain a `ConnectionFactory` through dependency injection or JNDI configuration. Do not instantiate provider implementations directly in business logic.

Example creating a connection via the JMS API:

```java
import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;

Connection createConnection(ConnectionFactory connectionFactory)
        throws JMSException {
    return connectionFactory.createConnection();
}
```

`ConnectionFactory` is the factory used to create connections. In production environments, it is typically configured with endpoints, credentials, TLS, timeouts, and provider-specific reconnect mechanisms. Credentials should come from a secret manager or environment security configuration, never hardcoded in source code.

The connection factory is also where connection pooling or caching can be integrated. Which pool/cache to use should be based on the provider and deployment model; do not create a new connection for every message in business code.

## 3. Connection: Client Connection to the Provider

`Connection` represents an open connection between the application and the JMS provider. From a connection, the application creates one or more `Session` instances.

Key operations:

- `createSession(...)`: creates a session for working with messages.
- `start()`: starts message delivery to consumers. For consumers receiving asynchronously, the connection must be started before the provider delivers messages to listeners.
- `stop()`: temporarily pauses message delivery to consumers.
- `close()`: closes the connection and releases associated sessions, producers, and consumers.

A connection can serve multiple sessions. However, creating a connection and maintaining sockets usually costs more resources than creating a message; therefore Spring listener containers typically keep long-lived consumers and reuse resources per configuration.

For producers that only send messages, the application usually does not need to call `start()` to begin receiving messages. `start()` is especially important when a connection has consumers that need to receive messages.

## 4. Session: Context for Creating and Processing Messages

`Session` is the primary working context between the application and the provider. A session is created from a `Connection` and used to:

- Create `Queue`, `Topic`, or other destination objects.
- Create `MessageProducer` and `MessageConsumer`.
- Create message types such as `TextMessage`, `BytesMessage`, or `MapMessage`.
- Manage transactions and acknowledgement within the session scope.

A critical rule of JMS is that **a Session is not designed for concurrent use by multiple threads**. Use a session on one processing thread at a time. If concurrency is needed, create multiple sessions/consumers in the manner supported by the provider and listener container rather than sharing the same session across multiple threads.

### Creating a session and choosing an acknowledgement mode

The classic API for creating a session looks like this:

```java
Session session = connection.createSession(
        false,
        Session.AUTO_ACKNOWLEDGE
);
```

The first parameter indicates whether the session uses a local transaction. The second parameter is the acknowledgement mode when the session is non-transacted. If the session is transacted, message confirmation is governed by `commit()` or `rollback()`; the individual acknowledgement mode does not control that transaction.

Standard acknowledgement modes:

| Mode | Meaning | Note |
|---|---|---|
| `AUTO_ACKNOWLEDGE` | Provider automatically acknowledges per JMS rules after message is received/processed depending on receive style | Easy to use, though you must understand the acknowledgement timing of receive vs. listener |
| `CLIENT_ACKNOWLEDGE` | Client explicitly calls `Message.acknowledge()` | In JMS, acknowledging one message can acknowledge messages previously consumed by the same session |
| `DUPS_OK_ACKNOWLEDGE` | Allows provider to acknowledge lazily/in batches | Duplicates can occur; consumers must be idempotent |
| `SESSION_TRANSACTED` | Not an acknowledgement mode passed when creating a non-transacted session; transaction is enabled via `transacted=true` | Use `commit()` or `rollback()` on the session |

Choose the mode based on delivery requirements, transactions, and duplicate-handling capability. Do not treat acknowledgement as proof that all business logic in downstream systems has completed.

## 5. Destination: Queue and Topic

Producers send messages to a `Destination`; consumers subscribe to receive from that destination. Two common destination types:

- **Queue:** point-to-point model. A message is distributed to one consumer in a competing consumer group per provider policy.
- **Topic:** publish–subscribe model. Matching subscribers can receive a copy of the message according to subscriptions and provider retention policy.

Example creating destinations using a session:

```java
Queue ordersQueue = session.createQueue("orders.incoming");
Topic orderEvents = session.createTopic("orders.events");
```

Queue/topic names are logical names per the provider's contract. Calling `createQueue` or `createTopic` creates a destination object in the client; it does not necessarily create the physical resource on the broker. Some providers support auto-creation, but production typically manages destinations, access permissions, and policies via administration tools or Infrastructure as Code.

## 6. MessageProducer: Sending Messages

`MessageProducer` is created from a session and a destination. The producer creates or receives a message and sends it to the queue/topic.

JMS defines several message types:

- `TextMessage`: text content, commonly used for JSON/XML or plain text.
- `BytesMessage`: binary data.
- `MapMessage`: collection of name/value pairs of JMS-supported types.
- `ObjectMessage`: serializable Java object; requires special care regarding deserialization and untrusted data sources.
- `StreamMessage`: ordered sequence of typed values read sequentially.
- `Message`: message with only headers and properties, no application body.

Example sending a `TextMessage` using the JMS API:

```java
import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

Connection connection = connectionFactory.createConnection();
Session session = null;
MessageProducer producer = null;
try {
    session = connection.createSession(false, Session.AUTO_ACKNOWLEDGE);
    Queue queue = session.createQueue("orders.incoming");
    producer = session.createProducer(queue);

    TextMessage message = session.createTextMessage(
            "{\"orderId\":\"ORD-100\",\"itemCount\":2}"
    );
    producer.send(message);
} finally {
    if (producer != null) producer.close();
    if (session != null) session.close();
    connection.close();
}
```

This snippet illustrates the resource lifecycle; a complete program must handle `JMSException` and ensure closing resources does not mask the original exception. `connection.start()` is unnecessary for a pure send operation since the example does not receive messages.

The producer can set send options such as delivery mode, priority, and time-to-live. For example, a message can be sent in persistent mode so the provider stores it durably per configuration, or non-persistent to prioritize performance. Actual durability still depends on the broker, storage, and provider configuration.

## 7. MessageConsumer: Receiving Messages

`MessageConsumer` is created from a session and a destination. There are two common ways to receive:

- **Synchronous:** call `receive()`, `receive(timeout)`, or `receiveNoWait()` to actively pull messages.
- **Asynchronous:** register a `MessageListener`; the provider invokes `onMessage` when a message arrives.

With a synchronous consumer, the connection must be started before waiting to receive messages:

```java
import jakarta.jms.Connection;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

Connection connection = connectionFactory.createConnection();
Session session = null;
MessageConsumer consumer = null;
try {
    session = connection.createSession(false, Session.AUTO_ACKNOWLEDGE);
    Queue queue = session.createQueue("orders.incoming");
    consumer = session.createConsumer(queue);

    connection.start();
    Message received = consumer.receive(3000);
    if (received instanceof TextMessage textMessage) {
        System.out.println(textMessage.getText());
    }
} finally {
    if (consumer != null) consumer.close();
    if (session != null) session.close();
    connection.close();
}
```

If the sample message above is received, the output is:

```text
{"orderId":"ORD-100","itemCount":2}
```

If no message arrives within three seconds, `receive(3000)` returns `null`. This is an illustrative example; real applications need proper exception handling and lifecycle management. Do not block a thread waiting indefinitely on `receive()` inside a normal web request.

### Asynchronous receiving with MessageListener

A consumer can register a listener:

```java
consumer.setMessageListener(message -> {
    try {
        if (message instanceof TextMessage textMessage) {
            process(textMessage.getText());
        }
    } catch (JMSException ex) {
        throw new IllegalStateException("Cannot read JMS message", ex);
    }
});
connection.start();
```

The provider invokes the listener when a message is delivered. Listener processing duration affects throughput and acknowledgement. Keep the callback concise or delegate work to an appropriate service, while understanding transaction/session boundaries and never using a session concurrently from multiple threads.

## 8. Headers, Properties, and Correlation

A JMS message has standard header fields such as:

- `JMSMessageID`: message identifier assigned by the provider.
- `JMSCorrelationID`: links a message to a request or another message.
- `JMSReplyTo`: destination used to send replies in a request–reply model.
- `JMSType`: message type information per application contract; it is not synonymous with MIME `Content-Type`.
- `JMSDestination`: destination to which the message was sent.
- `JMSDeliveryMode`, `JMSPriority`, `JMSExpiration`, and `JMSRedelivered`: delivery metadata.

Besides standard headers, producers can add application properties for consumers to route or process per contract. Do not use properties as a substitute for validation; consumers must still validate values and sender identity.

Example setting a correlation ID:

```java
TextMessage message = session.createTextMessage(json);
message.setJMSCorrelationID("corr-ORD-100");
message.setStringProperty("eventType", "OrderCreated");
producer.send(message);
```

Correlation IDs help match requests and replies or trace a flow across multiple components. They do not replace message IDs: one request can produce multiple distinct messages that share the same correlation ID.

## 9. Transactions and Acknowledgement

JMS supports session-level transactions. When creating a session with `transacted=true`, producer sends and consumer receives within the session can be committed or rolled back along the session's transaction boundary.

```java
Session session = connection.createSession(true, Session.SESSION_TRANSACTED);
try {
    // Receive message, update data, or send the next message.
    session.commit();
} catch (JMSException | RuntimeException ex) {
    session.rollback();
    throw ex;
}
```

This snippet outlines a JMS transaction; production code must manage exceptions, session lifecycle, and the proper transaction manager. `commit()` confirms the JMS operations in the transacted session; `rollback()` cancels uncommitted JMS operations and can cause received messages to be redelivered according to the provider.

A local JMS transaction does not automatically cover a database transaction. If a handler writes to the database and then commits JMS, or commits the database and then acknowledges JMS, a failure between the two operations can leave an inconsistent state. For atomicity across multiple resources, use XA/JTA if supported by both provider and database, or design an appropriate transactional outbox/inbox.

Redelivery can occur after a rollback or consumer failure. Consumers should be idempotent and have policies for handling failing messages, bounded retries, and dead-letter queues.

## 10. How Does Spring JMS Manage Resources?

Spring JMS provides abstractions so applications do not have to manually create and close connections, sessions, and producers for every operation:

- `JmsTemplate`: sends messages, performs synchronous receives, and manages acquiring/releasing JMS resources during operations.
- `DefaultMessageListenerContainer`: manages background consumers, sessions, listener threads, concurrency, and connection recovery per configuration.
- `@JmsListener`: declares a message-receiving method; Spring creates a listener endpoint and attaches it to a container.
- `JmsTransactionManager`: manages local JMS transactions for a `ConnectionFactory`.
- `CachingConnectionFactory`: can cache JMS resources to reduce repeated creation overhead, depending on configuration and usage.

In a Spring application, you typically inject a `ConnectionFactory` configured by the provider or Spring Boot. `JmsTemplate` and listener containers use the same factory to communicate with the broker.

### Sending with JmsTemplate

```java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
class OrderPublisher {
    private final JmsTemplate jmsTemplate;

    OrderPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    void publish(String json) {
        jmsTemplate.convertAndSend("orders.incoming", json);
    }
}
```

With a `String`, the default `SimpleMessageConverter` converts the content into a `TextMessage`. When sending DTOs or complex formats, configure an explicit `MessageConverter` and serialization contract; do not assume every Java object is automatically converted to JSON.

### Receiving with @JmsListener

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class OrderListener {
    @JmsListener(destination = "orders.incoming")
    public void receive(String json) {
        processOrder(json);
    }
}
```

Spring creates the listener container and converts the message to the appropriate parameter type using the configured converter. `@JmsListener` does not itself define the broker, credentials, or destination provisioning; the application still needs a valid `ConnectionFactory` and JMS infrastructure.

### Configuring the listener container

```java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
class JmsConfiguration {
    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrency("2-8");
        factory.setSessionTransacted(true);
        return factory;
    }
}
```

This example sets concurrency between 2 and 8 consumers and uses a transacted session for the listener. Choose the consumer count based on broker capacity, database pool size, and downstream services. When a listener throws an exception, rollback/redelivery depends on container configuration, transaction manager, and provider policies.

The examples above use `jakarta.jms`, matching the Spring Framework 6+ ecosystem. Spring Framework 5 and older JMS applications typically use the `javax.jms` package; do not mix the two namespaces in the same application.

## 11. Lifecycle Management and Performance

Repeatedly creating and closing connections/sessions/producers/consumers can introduce overhead. Some operational principles:

- Use `JmsTemplate` for synchronous send/receive operations so Spring manages resources.
- Use listener containers for long-running consumers instead of manually creating consumers per request.
- Consider connection pooling or caching appropriate to the provider and Spring; measure effectiveness before increasing cache size.
- Size concurrency according to CPU limits, database connection pools, and broker processing capacity.
- Close consumers, producers, sessions, and connections in manual JMS code; do not leak resources.
- Monitor connection/session counts, consumer counts, queue depth, message age, throughput, and redelivery.

Do not share a single `Session`, `MessageProducer`, or `MessageConsumer` across multiple threads simultaneously. To increase parallelism, use multiple sessions/consumers managed by the container or pool.

## 12. Common Pitfalls

- **Confusing ConnectionFactory with Connection:** the factory creates connections; the connection represents an open connection.
- **Using one Session from multiple threads:** sessions are not designed for concurrent use; create separate sessions per thread/container.
- **Forgetting to call `Connection.start()` when receiving messages:** consumers may not receive asynchronous messages until the connection is started.
- **Not closing resources when using the JMS API directly:** connections/sessions/producers/consumers leak and exhaust resources.
- **Treating `createQueue()` as guaranteed to create a physical queue:** it may only create a destination object; provisioning depends on the provider.
- **Confusing Queue and Topic:** queues distribute using point-to-point; topics use publish–subscribe.
- **Using ObjectMessage with untrusted data:** object deserialization carries security risks and class/version coupling; prefer explicit schemas like JSON or controlled formats.
- **Treating AUTO_ACKNOWLEDGE as a database transaction:** JMS acknowledgement does not automatically synchronize with database commits.
- **Not designing for redelivery/idempotency:** rollbacks or lost connections can cause messages to be redelivered.
- **Assuming @JmsListener provisions all infrastructure:** listeners require a valid ConnectionFactory, broker, and destination.
- **Confusing JMSType with Content-Type:** these two metadata fields serve different purposes.

## 13. JMS Resource Selection and Implementation Process

1. Choose a provider and configure `ConnectionFactory` with endpoints, credentials, TLS, and timeouts.
2. Determine whether the destination is a queue or topic, along with provisioning policies and access permissions.
3. Choose the sending model: `JmsTemplate` or direct JMS `MessageProducer`.
4. Choose the receiving model: synchronous `receive` or asynchronous `MessageListener`/`@JmsListener`.
5. Determine whether a transacted session or an appropriate acknowledgement mode is needed.
6. Design message format, converter, correlation ID, and properties.
7. Set concurrency, pooling/caching, and timeouts according to resource capacity.
8. Design retry, redelivery, dead-letter handling, and idempotency.
9. Test send/receive, commit/rollback, broker failures, reconnects, and resource closing.

## 14. Conclusion

`ConnectionFactory` creates `Connection`; `Connection` creates `Session`; `Session` creates messages, destinations, `MessageProducer`, and `MessageConsumer`. Producers send messages to queues/topics, while consumers receive synchronously with `receive` or asynchronously with `MessageListener`. `Session` is where transactions and acknowledgements are managed, and it must not be shared across multiple threads.

In Spring applications, prefer `JmsTemplate` for synchronous send/receive and listener containers/`@JmsListener` for background consumers. A solid grasp of resource lifecycles, transactions, acknowledgement, concurrency, and redelivery helps applications communicate reliably with the JMS provider, avoid resource leaks, and handle duplicate messages safely.