# JmsTemplate and Send/Receive Resource Management

## Objectives

After this lesson, you will be able to:

- Explain the role of `JmsTemplate` and `ConnectionFactory` in Spring JMS.
- Use `send`, `convertAndSend`, `receive`, and `receiveAndConvert` appropriately.
- Understand how Spring creates, uses, and releases `Connection`, `Session`, `MessageProducer`, and `MessageConsumer`.
- Distinguish between `SingleConnectionFactory`, `CachingConnectionFactory`, and a JMS provider's connection pool.
- Choose between synchronous receiving with a template and asynchronous receiving with a listener container.
- Configure appropriate transactions, acknowledgement, timeout, and QoS.
- Avoid resource leaks, improper thread usage, unbounded message receiving, and inconsistent transaction handling.

## 1. What is JmsTemplate?

JMS (Jakarta Messaging) defines an API for sending and receiving messages through a message provider. Applications typically have to interact with several objects:

~~~text
ConnectionFactory
       |
       v
   Connection
       |
       v
    Session
       |
       +---- MessageProducer ---- send(...)
       |
       +---- MessageConsumer ---- receive(...)
~~~

When using the JMS API directly, code must create and close intermediate objects, handle `JMSException`, manage transactions, and ensure resources are released even when errors occur.

`org.springframework.jms.core.JmsTemplate` is the central class of Spring JMS, providing high-level operations for synchronous sending or receiving. The template handles acquiring and releasing JMS resources for each operation, while translating JMS errors into Spring's unchecked exception hierarchy.

Key benefits:

- Reduces boilerplate code for creating and closing connections, sessions, producers, or consumers.
- Integrates with JMS resources managed by a Spring transaction manager.
- Supports destinations by name or `Destination` object.
- Supports payload conversion via `MessageConverter`.
- Provides callbacks when access to a Session or MessageProducer is needed.
- Safely shared across multiple collaborators once configured.

**A configured JmsTemplate instance is thread-safe.** You can declare a singleton bean and inject it into multiple services. You should not modify the template's configuration while threads are using it.

## 2. ConnectionFactory and JMS Resources

### ConnectionFactory

`jakarta.jms.ConnectionFactory` is the entry point to a JMS provider. It creates connections and holds provider-specific connection information, for example:

- Broker URL or JNDI resource.
- Authentication.
- TLS/SSL.
- Network failover.
- Connection pooling or resource-management adapters.

In applications running on an application server, prefer a server-managed `ConnectionFactory` via JNDI if server pooling and transaction integration are required. For standalone applications, you can use a provider connection factory such as ActiveMQ or Artemis.

### Connection

`Connection` represents a connection to the provider. Connections are typically reused rather than created anew for every message. Opening a connection may involve sockets, threads, and broker-side resources.

### Session

`Session` is the context for creating messages, producers, and consumers. It also determines the transaction and acknowledgement mode. A JMS `Session` is not an object meant for arbitrary concurrent use from multiple threads; avoid sharing a single session across multiple parallel processing threads.

### MessageProducer and MessageConsumer

- `MessageProducer` sends messages to a queue or topic.
- `MessageConsumer` receives messages from a destination and can use a selector for filtering.

Each send/receive operation may require a producer or consumer. Repeatedly creating and closing these objects can be costly, so Spring provides connection factory wrappers to reuse resources.

## 3. How Does JmsTemplate Manage Resources?

A simple send typically goes through the following sequence:

~~~text
JmsTemplate.convertAndSend(...)
          |
          v
Obtain ConnectionFactory
          |
          v
Obtain Connection and Session
          |
          v
Create MessageProducer
          |
          v
MessageConverter creates JMS Message
          |
          v
Producer sends message
          |
          v
Release producer / session / connection
~~~

When the operation is not part of an active transaction, the template creates or obtains the necessary resources, performs the operation, and then releases them in the proper order.

When a JMS resource is bound to the thread by a Spring transaction manager, the template detects and uses that transactional resource. The template does not close transaction-bound resources mid-operation; the transaction manager is responsible for completing and releasing them when the transaction ends.

This means:

- There is no need to manually call `createConnection()`, `createSession()`, or `close()` when using standard `JmsTemplate` methods.
- Do not store a `Session`, `MessageProducer`, or `MessageConsumer` in a service field for long-term reuse.
- Do not manually close resources managed by the template or transaction manager.
- If you truly use the JMS API directly, you must follow the ownership and release rules of `ConnectionFactoryUtils` or `JmsUtils`.

### Resource lifecycle and transaction-bound resources

~~~text
Without transaction:
JmsTemplate
  -> obtain resources
  -> send/receive
  -> close or return resources to wrapper/cache

With Spring transaction:
TransactionManager
  -> bind Connection/Session to thread
  -> JmsTemplate retrieves bound Session
  -> send/receive within transaction
  -> commit or rollback
  -> unbind and release resources
~~~

Spring provides `ConnectionFactoryUtils` to look up or obtain a session bound to the current transaction. This is primarily an internal utility used by `JmsTemplate` and listener containers; typical application code should call the template rather than managing this utility directly.

## 4. Sending Messages with JmsTemplate

### send and MessageCreator

Use `send` when you want to create a JMS Message directly from a `Session`:

~~~java
jmsTemplate.send("orders.queue", session ->
        session.createTextMessage("ORD-1001")
);
~~~

The `MessageCreator` callback receives a `Session` provided by the template. You can use the session to create a `TextMessage`, `BytesMessage`, `MapMessage`, `ObjectMessage`, or set JMS properties and headers as required.

This is the right choice when you need exact control over the JMS message type or native attributes.

### convertAndSend

If you only need to send an object and let Spring convert it into a JMS message, use `convertAndSend`:

~~~java
jmsTemplate.convertAndSend("orders.queue", "ORD-1001");
~~~

By default, `SimpleMessageConverter` supports common types:

| Java payload | JMS message |
|---|---|
| `String` | `TextMessage` |
| `byte[]` | `BytesMessage` |
| `Map` | `MapMessage` |
| `Serializable` | `ObjectMessage` |

You can replace the converter with `setMessageConverter(...)` if the contract requires JSON, XML, or another format. When sending `ObjectMessage`, you must control which classes are deserialized and only use it with trusted sources; do not enable arbitrary deserialization for external messages.

### MessagePostProcessor

After the converter creates the JMS message but before sending, you can add properties or headers using a `MessagePostProcessor`:

~~~java
jmsTemplate.convertAndSend(
        "orders.queue",
        "ORD-1001",
        message -> {
            message.setStringProperty("eventType", "OrderCreated");
            message.setJMSCorrelationID("checkout-9001");
            return message;
        }
);
~~~

Use JMS properties for data that selectors may inspect. Standard JMS headers such as correlation ID have dedicated APIs. Do not use arbitrary properties to replace standard headers if the application needs interoperability with other systems.

### QoS: delivery mode, priority, and time-to-live

JMS allows tuning Quality of Service:

- **Delivery mode:** persistent or non-persistent.
- **Priority:** priority level from 0 to 9 according to JMS.
- **Time-to-live (TTL):** how long a message remains valid before expiring.

These can be configured on the template:

~~~java
jmsTemplate.setDeliveryPersistent(true);
jmsTemplate.setPriority(4);
jmsTemplate.setTimeToLive(60_000);
jmsTemplate.setExplicitQosEnabled(true);
~~~

`setExplicitQosEnabled(true)` instructs the template to apply the configured QoS values. If not enabled, some providers may apply default values configured on the connection factory or broker. Verify the actual provider policy.

Persistent delivery can increase durability but also affects performance. TTL is suitable for data that loses value after a period of time; do not use TTL if the message must be retained until business processing completes.

### Sending multiple messages on one Session

When multiple JMS operations need to share a Session or MessageProducer, you can use:

- `SessionCallback<T>`: receives a Session.
- `ProducerCallback<T>`: receives a Session and a MessageProducer.

Conceptual example:

~~~java
jmsTemplate.execute((SessionCallback<Void>) session -> {
    Queue queue = session.createQueue("orders.queue");
    MessageProducer producer = session.createProducer(queue);
    try {
        producer.send(session.createTextMessage("ORD-1001"));
        producer.send(session.createTextMessage("ORD-1002"));
    }
    finally {
        producer.close();
    }
    return null;
});
~~~

Inside the callback, the session is provided by the template and must not be closed manually. Any producer created directly by your code must be closed. If a transaction is active, operations in the callback follow the session's transaction.

## 5. Synchronous Receiving with JmsTemplate

JMS is commonly used for asynchronous processing, but the template also supports synchronous receiving.

Common methods:

- `receive(destination)`: receives a JMS `Message`.
- `receiveSelected(destination, selector)`: receives a message matching the selector.
- `receiveAndConvert(destination)`: receives a message and converts its payload into an object.
- Overloads can accept a destination object, a destination name, or use the default destination.

Example:

~~~java
Message message = jmsTemplate.receive("orders.queue");
~~~

Or receive a converted object:

~~~java
Object payload = jmsTemplate.receiveAndConvert("orders.queue");
~~~

If no message arrives within the wait time, the method returns `null`. Therefore, always check for null before using the payload.

### receiveTimeout

Synchronous receiving blocks the calling thread until a message arrives or a timeout expires. Without a reasonable limit configured, a thread can be held for too long.

~~~java
jmsTemplate.setReceiveTimeout(2_000);

Object payload = jmsTemplate.receiveAndConvert("orders.queue");

if (payload == null) {
    System.out.println("No message before timeout");
}
else {
    System.out.println("Received: " + payload);
}
~~~

Choose the timeout according to application requirements. No-wait receiving, bounded-wait receiving, and indefinite-wait receiving are distinct policies; do not let a synchronous receive API block a request thread indefinitely.

### Message selector

A selector is a JMS expression used to filter messages by headers or properties:

~~~java
Message message = jmsTemplate.receiveSelected(
        "orders.queue",
        "eventType = 'OrderCreated'"
);
~~~

Selectors do not filter by arbitrary payloads; they operate on supported JMS headers and properties. Use a selector when a consumer needs to receive a specific subset of messages from the same destination.

### Request-reply

`JmsTemplate` provides a basic request-reply operation: send a request and wait for a response on a temporary queue created for that call. This is a synchronous model over messaging and can hold the thread while waiting.

Use request-reply when the contract genuinely requires an immediate result. For long or multi-step workflows, prefer correlation IDs and an asynchronous workflow to avoid blocking request threads.

## 6. Asynchronous Receiving with a Listener Container

`JmsTemplate.receive(...)` fits polling or a short synchronous receive operation. For continuously running consumers, Spring recommends using a listener container.

There are two common approaches:

- `@JmsListener`: declare a message-handling method; Spring registers the endpoint and manages the listener container.
- `DefaultMessageListenerContainer`: configure the container directly when deeper control is needed.

Annotation example:

~~~java
@Configuration
@EnableJms
public class JmsListenerConfiguration {
}

@Component
public class OrderListener {

    @JmsListener(destination = "orders.queue", concurrency = "2-5")
    public void receive(String orderId) {
        System.out.println("Processing order: " + orderId);
    }
}
~~~

The listener container manages receiving threads, consumer registration, resource acquisition/release, transactions, and error propagation. If concurrency is greater than one, the listener can be invoked on multiple threads; the listener bean must be thread-safe.

### DefaultMessageListenerContainer

You can declare the container with Java Configuration:

~~~java
@Bean
public DefaultMessageListenerContainer orderListenerContainer(
        ConnectionFactory connectionFactory,
        OrderListener orderListener) {

    DefaultMessageListenerContainer container =
            new DefaultMessageListenerContainer();

    container.setConnectionFactory(connectionFactory);
    container.setDestinationName("orders.queue");
    container.setMessageListener((MessageListener) message ->
            orderListener.handle(message)
    );
    container.setConcurrentConsumers(2);
    container.setMaxConcurrentConsumers(5);
    container.setSessionTransacted(true);

    return container;
}
~~~

This is an example of manual container configuration. In real applications, you can use `@JmsListener` and `DefaultJmsListenerContainerFactory` for centralized configuration. Do not create an extra manual container for the same endpoint already registered by `@JmsListener`.

## 7. Connection Reuse, Caching, and Pooling

JMS creates multiple intermediate objects during sending or receiving. Appropriate reuse helps reduce resource creation overhead.

### SingleConnectionFactory

`SingleConnectionFactory` returns the same JMS Connection across `createConnection()` calls and ignores close calls on the shared connection. It is useful in certain standalone or testing environments when you want to reuse a connection.

It does not cache Sessions, Producers, and Consumers the way `CachingConnectionFactory` does, nor is it a multi-connection pool.

### CachingConnectionFactory

`CachingConnectionFactory` extends `SingleConnectionFactory` and adds caching for:

- JMS `Session`.
- `MessageProducer`.
- `MessageConsumer`.

It can be configured as follows:

~~~java
CachingConnectionFactory cachingFactory =
        new CachingConnectionFactory(targetConnectionFactory);

cachingFactory.setSessionCacheSize(10);
cachingFactory.setCacheProducers(true);
cachingFactory.setCacheConsumers(false);
~~~

Session caching is bounded per acknowledgement mode; the actual number of sessions may exceed the configured limit when multiple acknowledgement modes are used. Unused sessions are returned to the cache when closed via their proxy.

Notes:

- You must close a Session obtained from CachingConnectionFactory so it is returned to the cache.
- Cached consumers can have different semantics from creating a new consumer and closing it immediately; be especially careful with selectors and durable subscriptions.
- Producers/consumers for temporary destinations are not cached.
- CachingConnectionFactory shares one connection and caches resources; it does not replace a true connection pool when multiple independent connections are needed.

### When is a provider connection pool needed?

Under heavy load or with many concurrent consumers/producers, consider a pool provided by the provider or deployment environment. A connection pool can manage multiple connections, sessions, and resource limits better than sharing a single connection.

Do not stack multiple caching/pooling layers arbitrarily. Understand which layer owns the connection, session, transaction, and shutdown lifecycle to avoid double-close, resource starvation, or unexpected behavior.

## 8. Transactions and Acknowledgement

### JmsTemplate defaults

By default, a Session created by `JmsTemplate` is:

- Non-transacted.
- `AUTO_ACKNOWLEDGE`.

This can be changed with `sessionTransacted` and `sessionAcknowledgeMode`, or by using a Spring transaction manager. If a Session is created within an active transaction, the transaction/acknowledgement parameters of the Session creation method are governed by the transaction infrastructure.

### JmsTransactionManager

`JmsTransactionManager` manages local transactions for a single `ConnectionFactory`. It binds the Connection/Session pair to the thread. `JmsTemplate` automatically detects the bound resource and participates in that transaction.

~~~java
@Bean
public JmsTransactionManager jmsTransactionManager(
        ConnectionFactory connectionFactory) {
    return new JmsTransactionManager(connectionFactory);
}
~~~

When combined with declarative transactions, template send or receive operations can participate in a managed JMS transaction. This transaction manager only manages a single JMS ConnectionFactory; it does not automatically create an atomic transaction across JMS and a database.

### Listener transactions

For a listener container, you can enable local JMS transactions:

~~~java
container.setSessionTransacted(true);
~~~

When the listener fails and an exception propagates out of the listener, message reception can roll back in the JMS transaction and the message may be redelivered according to provider policy.

If the listener both updates a database and receives a JMS message, a local JMS transaction does not automatically roll back the database transaction. A situation can arise where the database commits while JMS rolls back and redelivers the message. Consumers require idempotency or duplicate detection.

If a distributed transaction covering both database and JMS is truly required, you need a JTA transaction manager with a properly configured XA-capable ConnectionFactory. XA carries high overhead and operational requirements; many systems choose the Transactional Outbox or inbox/idempotency patterns to manage consistency at the application architecture level.

## 9. Complete Java 17 Example with Embedded ActiveMQ Classic

The example below uses Spring Framework 6.2.19, ActiveMQ Classic 6.2.6, and Java 17. The broker runs embedded in the same JVM via the VM transport, so no external broker installation is required. The program sends a String, receives the String back, and verifies that a subsequent receive times out.

Directory structure:

~~~text
jms-template-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── JmsTemplateDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>jms-template-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>activemq-broker</artifactId>
            <version>6.2.6</version>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>activemq-client</artifactId>
            <version>6.2.6</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

File `src/main/java/demo/JmsTemplateDemo.java`:

~~~java
package demo;

import org.apache.activemq.ActiveMQConnectionFactory;
import org.apache.activemq.broker.BrokerService;
import org.springframework.jms.connection.CachingConnectionFactory;
import org.springframework.jms.core.JmsTemplate;

public class JmsTemplateDemo {

    public static void main(String[] args) throws Exception {
        BrokerService broker = new BrokerService();
        broker.setBrokerName("jms-template-demo");
        broker.setPersistent(false);
        broker.setUseJmx(false);
        broker.start();
        broker.waitUntilStarted();

        ActiveMQConnectionFactory providerFactory =
                new ActiveMQConnectionFactory("vm://jms-template-demo");

        CachingConnectionFactory connectionFactory =
                new CachingConnectionFactory(providerFactory);
        connectionFactory.setSessionCacheSize(2);

        try {
            JmsTemplate jmsTemplate = new JmsTemplate(connectionFactory);
            jmsTemplate.setReceiveTimeout(500);

            jmsTemplate.convertAndSend("orders.demo", "ORD-1001");
            System.out.println("sent=ORD-1001");

            Object received =
                    jmsTemplate.receiveAndConvert("orders.demo");
            System.out.println("received=" + received);

            Object secondReceive =
                    jmsTemplate.receiveAndConvert("orders.demo");
            System.out.println(
                    "secondReceiveTimedOut=" + (secondReceive == null)
            );
        }
        finally {
            connectionFactory.destroy();
            broker.stop();
            broker.waitUntilStopped();
        }
    }
}
~~~

Run from the directory containing `pom.xml`:

~~~bash
mvn -q compile org.codehaus.mojo:exec-maven-plugin:3.5.0:java -Dexec.mainClass=demo.JmsTemplateDemo
~~~

Program stdout output:

~~~text
sent=ORD-1001
received=ORD-1001
secondReceiveTimedOut=true
~~~

Explanation:

1. The embedded broker is started before creating the client connection factory.
2. `CachingConnectionFactory` wraps the provider factory and reuses connections/sessions as configured.
3. `JmsTemplate.convertAndSend` uses the default converter to turn the String into a `TextMessage`.
4. `receiveAndConvert` retrieves the message and converts it back into a String.
5. The second receive finds no message and returns `null` after the 500 ms timeout.
6. `CachingConnectionFactory.destroy()` closes the shared connection and cache; the broker is stopped in the finally block.

This example uses a non-persistent broker for learning purposes. It does not represent a production durability configuration. In a real environment, use an appropriate broker, authentication, TLS, persistence, destination policies, and transactions.

## 10. When to Use JmsTemplate vs. Listener?

| Need | Choice |
|---|---|
| Send a message to a queue/topic | `JmsTemplate.send` or `convertAndSend` |
| Send a Java payload with a converter | `convertAndSend` |
| Create a custom JMS Message from Session | `send` with `MessageCreator` |
| Receive one message on demand with timeout | `receive` or `receiveAndConvert` |
| Scheduled or selector-based polling | `receiveSelected` or a dedicated poller |
| Continuously running, asynchronous consumer | `@JmsListener` or `DefaultMessageListenerContainer` |
| Multiple operations on one Session/Producer | `SessionCallback` or `ProducerCallback` |
| Local JMS transaction needed | `JmsTransactionManager` or transacted session |
| Distributed JMS + database transaction needed | JTA/XA if truly necessary; consider Outbox/inbox |

## 11. Common Pitfalls and How to Avoid Them

1. **Manually creating and closing Connection/Session in every service.** Use `JmsTemplate` so the template manages the lifecycle; only use the JMS API directly when specifically needed.
2. **Storing a Session or Producer in a shared field.** Session is not a thread-safe object for concurrent operations across threads.
3. **Creating a new JmsTemplate per message.** Configure one shared template after initialization completes.
4. **Using receive without timeout on a request thread.** Synchronous receive can block indefinitely; set an explicit timeout or switch to a listener container.
5. **Using JmsTemplate as a continuously running consumer.** Each synchronous receive is a separate operation; use a listener container for long-running asynchronous consumption.
6. **Failing to check null from receive.** Timeouts or empty queues can return null.
7. **Confusing CachingConnectionFactory with a multi-connection pool.** CachingConnectionFactory shares a single connection and caches resources; use a provider pool or managed factory when real pooling is needed.
8. **Failing to close a Session when using CachingConnectionFactory directly.** The session must be closed to be returned to the cache.
9. **Caching MessageConsumer without considering durable subscriptions.** Consumer caching can affect subscription lifecycles; verify provider semantics and cache settings.
10. **Assuming send() means the consumer has finished processing.** Send is only a producer operation with the provider; downstream processing is a separate step.
11. **Assuming a JMS transaction covers the database.** JmsTransactionManager only manages one ConnectionFactory; XA or Outbox/idempotency architecture is needed for multi-resource consistency.
12. **Catching and swallowing exceptions inside a listener.** If the listener container uses a transacted session, failing to propagate the exception can cause the transaction to commit and the message to be acknowledged. Only swallow errors after handling or forwarding them according to a clear policy.
13. **Lacking a retry or DLQ policy.** Configure redelivery limits, backoff, and dead-letter destinations on the broker/provider; avoid infinite retries.
14. **Using ObjectMessage with untrusted data.** Prefer JSON or a clearly defined schema format and restrict type deserialization.
15. **Neglecting shutdown management.** Close the cache/connection factory and stop listener containers according to the Spring context lifecycle.

## 12. Operations Checklist

- [ ] Use a ConnectionFactory managed by the provider or container.
- [ ] Configure a single shared JmsTemplate after initialization.
- [ ] Identify queue vs. topic and an appropriate destination resolver.
- [ ] Choose send/convertAndSend based on payload conversion needs.
- [ ] Set receiveTimeout for synchronous receive operations.
- [ ] Use a listener container for continuously running consumers.
- [ ] Choose caching or pooling based on concurrency and provider characteristics.
- [ ] Do not share unsafe Session/Producer/Consumer instances across threads.
- [ ] Configure transactions and acknowledgement according to message loss/redelivery requirements.
- [ ] Review retry, redelivery, TTL, delivery mode, and dead-letter policies.
- [ ] Design idempotent consumers if redelivery is possible.
- [ ] Monitor connections, sessions, consumer count, queue depth, delivery latency, and provider errors.
- [ ] Close resource wrappers and listener containers cleanly on lifecycle shutdown.

## 13. Conclusion

`JmsTemplate` provides a synchronous send and receive API while managing the acquisition and release of Connection, Session, Producer, and Consumer. `ConnectionFactory` determines how connections are made and resources reused; `SingleConnectionFactory` shares a connection, while `CachingConnectionFactory` adds session/producer/consumer caching. Use `receiveTimeout` for synchronous receiving, listener containers for asynchronous consumers, and choose transactions aligned with resource boundaries. By understanding lifecycle, caching, transactions, and timeouts, applications avoid resource leaks and process messages more reliably.

## Official References

- [Spring Framework 6.2 Reference: Using Spring JMS](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html) — JmsTemplate, ConnectionFactory, resource caching, and listener containers.
- [Spring Framework 6.2 Reference: Sending a Message](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/sending.html) — send, convertAndSend, MessageConverter, MessagePostProcessor, and callbacks.
- [Spring Framework 6.2 Reference: Receiving a Message](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html) — synchronous receive, timeout, listener containers, and transactions.
- [Spring Framework 6.2.19 Javadoc: JmsTemplate](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/core/JmsTemplate.html) — send/receive API, default session settings, and resource lifecycle.
- [Spring Framework 6.2.19 Javadoc: CachingConnectionFactory](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/connection/CachingConnectionFactory.html) — Session, MessageProducer, MessageConsumer caching, and lifecycle.
- [Spring Framework 6.2.19 Javadoc: ConnectionFactoryUtils](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/connection/ConnectionFactoryUtils.html) — obtaining transactional Session and releasing Connection.
- [Spring Framework 6.2.19 Javadoc: JmsTransactionManager](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/connection/JmsTransactionManager.html) — local transactions for a single ConnectionFactory.
- [ActiveMQ Classic: JMS and Jakarta Messaging support](https://activemq.apache.org/components/classic/documentation/jms2) — Jakarta JMS compatibility and client.
