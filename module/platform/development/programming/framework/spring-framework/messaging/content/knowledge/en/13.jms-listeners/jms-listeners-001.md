# Asynchronous Receiving with MessageListener and Message-Driven POJO

## Learning Objectives

After this lesson, you can:

- Explain how JMS delivers a message to a listener without the producer calling the consumer directly.
- Distinguish between the Jakarta JMS MessageListener and the Message-Driven POJO (MDP) in Spring.
- Configure a listener container to manage the Connection, Session, Consumer, threads, and the message-receiving lifecycle.
- Choose between a directly implemented listener, MessageListenerAdapter, and the @JmsListener annotation.
- Understand how a JMS Message is converted into a Java payload and how replies are sent.
- Configure concurrency, selectors, Queue/Topic, and durable subscriptions.
- Choose the appropriate acknowledgement or transaction, and handle errors, redelivery, and duplicates.
- Write a thread-safe consumer and shut the container down properly.

## 1. What Is Asynchronous JMS Receiving?

In the JMS model, a producer sends a Message to a Queue or Topic. A consumer can actively call receive to wait for a Message, or register a listener to be called when the provider delivers a Message.

**Asynchronous receiving** means the application registers its processing logic first; when a Message arrives, the listener container or the JMS provider invokes the callback on the receiving thread. The producer does not need to wait for the consumer to finish processing within the send call.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant B as JMS Broker
    participant C as Spring Listener Container
    participant L as MessageListener / POJO

    P->>B: Send Message
    Note over P: Producer continues its work
    B-->>C: Message arrives at the consumer
    C->>L: Invoke the listener on the receiving thread
    L->>L: Process business logic
    L-->>C: Callback finishes
    C->>B: Commit or acknowledge according to configuration
~~~

JMS provides the standard callback jakarta.jms.MessageListener with the method onMessage(Message). Spring adds infrastructure that turns an ordinary Java object into a message receiver, while also managing connections, sessions, consumers, threads, transactions, and recovery.

A listener does not create its own threads or poll on its own. In a Spring application, the listener container is responsible for registering and coordinating the receiving. The container receives a Message from the provider and then invokes the configured listener.

## 2. Jakarta JMS MessageListener

The standard interface lives in the jakarta.jms package:

~~~java
public interface MessageListener {
    void onMessage(Message message);
}
~~~

A class implementing MessageListener can receive many kinds of JMS Message. The listener needs to check the type of the Message and read the corresponding payload.

Example of receiving a TextMessage:

~~~java
public final class RawOrderListener implements MessageListener {

    @Override
    public void onMessage(Message message) {
        if (!(message instanceof TextMessage textMessage)) {
            throw new IllegalArgumentException(
                    "Expected a TextMessage"
            );
        }

        try {
            System.out.println("orderId=" + textMessage.getText());
        }
        catch (JMSException ex) {
            throw new IllegalStateException(
                    "Cannot read order message", ex
            );
        }
    }
}
~~~

The onMessage method does not declare throws JMSException. If reading the Message raises a JMSException, the application needs to handle it or convert it into an unchecked exception according to the listener container's policy.

A listener should process quickly and in a bounded way. If the work is time-consuming, consider moving the heavy processing to a controlled worker pool, but you must design acknowledgement and transactions so that the Message is acknowledged only when the work has actually reached the desired state.

## 3. Message-Driven POJO in Spring

A Message-Driven POJO (MDP) is an ordinary Java object used as the place that handles JMS Messages. The idea is similar to the Message-Driven Bean in EJB, but the business class does not need to depend on the EJB container.

Spring supports MDPs in three common ways:

1. A POJO that directly implements jakarta.jms.MessageListener.
2. A POJO that does not depend on the JMS API and is wrapped by a MessageListenerAdapter.
3. A POJO that declares a receiving method with @JmsListener; Spring registers the endpoint and creates the listener container.

What they have in common is that the business logic is invoked when a Message arrives. The differences lie in the degree of dependency on the JMS API, how the payload is converted, and how the endpoint is configured.

### 3.1. A POJO Implementing MessageListener

This approach is suitable when you need to work directly with the JMS Message, properties, headers, or specific message types:

~~~java
public class OrderMessageListener implements MessageListener {

    @Override
    public void onMessage(Message message) {
        // Read the JMS Message and call the business logic.
    }
}
~~~

The advantage is full access to the JMS Message object. In exchange, the class depends on Jakarta JMS and must handle type checking, payload reading, and any resulting JMSException on its own.

### 3.2. A POJO Using MessageListenerAdapter

MessageListenerAdapter lets you wrap a POJO that does not implement MessageListener. The adapter converts the content of the JMS Message into a suitable Java type and then invokes a method on the delegate.

Example POJO:

~~~java
public class OrderDelegate {

    public void handleMessage(String orderId) {
        System.out.println("orderId=" + orderId);
    }
}
~~~

Adapter configuration:

~~~java
MessageListenerAdapter adapter =
        new MessageListenerAdapter(new OrderDelegate());

adapter.setDefaultListenerMethod("handleMessage");
~~~

The default method name is already handleMessage, so the setDefaultListenerMethod line is only needed when you want to make it explicit or replace it with another name, for example processOrder.

By default, the adapter uses SimpleMessageConverter to extract the payload from the JMS Message. Common mappings include:

| JMS Message | Java payload typically received |
|---|---|
| TextMessage | String |
| BytesMessage | byte[] |
| MapMessage | Map |
| ObjectMessage | Serializable object |

If you want the POJO to receive the whole JMS Message, you can set the adapter's MessageConverter to null and declare the method parameter as the appropriate Message type.

The adapter also supports responses: if the delegate method returns a non-null object, the adapter can convert that object into a JMS Message and send it to the request's JMSReplyTo or to the configured default response destination. This mechanism uses the SessionAwareMessageListener entry point, which the adapter implements when called by the listener container. If the method returns void, there is no automatic response.

## 4. What Does the Listener Container Manage?

The MessageListenerContainer is the intermediary component between the JMS provider and the listener. It manages:

- Creating and registering the JMS Connection, Session, and MessageConsumer.
- Receiving Messages and then invoking the listener on a suitable thread.
- The number of concurrent consumers and the lifecycle of the consumers.
- Acknowledgement or transaction for each processing run.
- Releasing resources when the application stops.
- Recovering when the broker or connection fails, depending on the implementation and configuration.

Applications should generally not create a single Session shared across multiple threads. A JMS Session is not designed for concurrent operation by multiple threads. The listener container manages a separate session for each consumer/invoker depending on the implementation.

When concurrency is increased, the same listener or POJO instance may be invoked concurrently from multiple threads. Therefore, mutable fields in the listener must be protected by a thread-safe mechanism, or better, keep the listener stateless and put the state specific to each processing run into local variables.

## 5. Spring's Two Standard Listener Containers

Spring Framework provides two common implementations.

### 5.1. SimpleMessageListenerContainer

SimpleMessageListenerContainer creates a fixed number of Sessions and Consumers at startup, then registers the listener through the JMS MessageConsumer.setMessageListener. The JMS provider performs the listener callback.

Characteristics:

- Simple configuration, close to JMS's standard listener mechanism.
- The number of consumers is fixed at startup.
- Does not automatically adjust concurrency according to runtime demand.
- Supports internal JMS transactions when sessionTransacted is enabled.
- Does not support participating in an externally managed transaction the way DefaultMessageListenerContainer does.
- Has compatibility limitations in some Jakarta EE environments.

### 5.2. DefaultMessageListenerContainer

DefaultMessageListenerContainer is usually more suitable for Spring applications that need recoverability and load adaptation.

Characteristics:

- Manages the container's threads and message-receiving loop.
- Supports concurrency and dynamic scaling.
- Supports internal JMS transactions and externally managed transactions.
- Has a recovery mechanism when the broker or connection is interrupted.
- Can be configured with a BackOff to adjust the wait between reconnection attempts.
- Can cache the Connection, Session, and Consumer according to the cache level.

Although the two containers have different names, both deliver Messages to the listener asynchronously relative to the producer. The difference lies in how the container registers/receives Messages and in its operational capabilities.

In most cases, DefaultMessageListenerContainer is the more flexible choice. SimpleMessageListenerContainer is suitable when you want a fixed configuration and accept its transaction/concurrency limitations.

## 6. Configuring DefaultMessageListenerContainer in Java

Example of configuring a listener for a Queue:

~~~java
@Bean
DefaultMessageListenerContainer orderListenerContainer(
        ConnectionFactory connectionFactory,
        OrderMessageListener listener) {

    DefaultMessageListenerContainer container =
            new DefaultMessageListenerContainer();

    container.setConnectionFactory(connectionFactory);
    container.setDestinationName("orders.in");
    container.setMessageListener(listener);
    container.setSessionTransacted(true);
    container.setConcurrentConsumers(1);

    return container;
}
~~~

Spring manages the container bean and calls the lifecycle callbacks itself. The container starts with the application context and stops when the context is closed.

setDestinationName uses the container's DestinationResolver to resolve the destination name. By default, the name is dynamically resolved to a Queue when pubSubDomain=false. If you need a Topic, configure pubSubDomain=true or pass an appropriate Destination object.

You can use setDestination(destination) when you already have a Queue or Topic object.

## 7. Using @JmsListener

The @JmsListener annotation is a convenient way to declare a JMS receiving endpoint. Spring creates and manages a listener container for each endpoint.

Enable annotation support with @EnableJms:

~~~java
@Configuration
@EnableJms
public class JmsConfiguration {

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("3-10");

        return factory;
    }
}
~~~

A POJO that receives messages:

~~~java
@Component
public class OrderListener {

    @JmsListener(
            destination = "orders.in",
            containerFactory = "jmsListenerContainerFactory"
    )
    public void handleOrder(String orderId) {
        System.out.println("orderId=" + orderId);
    }
}
~~~

If containerFactory is not specified, Spring by default looks for a bean named jmsListenerContainerFactory. Concurrency can be configured right on the annotation; the value at the endpoint overrides the corresponding configuration of the factory.

A listener method can receive the converted payload, the raw jakarta.jms.Message, or parameters supported by Spring such as headers and JMS information. The conversion depends on the MessageConverter configured for the listener container.

### 7.1. Choosing Destination, Selector, and Subscription

@JmsListener supports these commonly used attributes:

- destination: the name of the Queue or Topic.
- selector: a JMS message selector expression for filtering Messages.
- concurrency: limits the concurrent consumers/sessions.
- subscription: the durable subscription name for a Topic.
- containerFactory: the factory bean that creates the listener container.

Example:

~~~java
@JmsListener(
        destination = "orders.events",
        selector = "eventType = 'order.created'",
        subscription = "order-projection",
        containerFactory = "topicListenerContainerFactory"
)
public void onOrderCreated(String payload) {
    // Update the projection.
}
~~~

For a durable Topic subscription, you need to configure the correct pubSubDomain, client ID, subscription name, and the subscription type the provider supports. A durable subscription stores messages for the subscriber according to the broker's policy while the subscriber is temporarily offline; it does not by itself guarantee exactly-once business processing.

## 8. How Do MessageListener, MessageListenerAdapter, and @JmsListener Differ?

| Implementation approach | Does the listener depend on the JMS API? | How data is received | When suitable |
|---|---|---|---|
| MessageListener | Yes | Receives the raw Message in onMessage | Need control over the JMS Message and properties |
| MessageListenerAdapter + POJO | The POJO does not need to depend on JMS | The adapter converts the Message into a Java payload | Want to separate business logic from the JMS API |
| @JmsListener | The POJO method is registered by Spring | Spring converts and binds the parameters | Want a concise endpoint declaration managed by a container factory |

All three approaches need receiving infrastructure. MessageListenerAdapter does not connect to the broker by itself; @JmsListener does not create a ConnectionFactory by itself either. The listener container and the JMS provider must still be configured correctly.

## 9. Concurrency and Thread Safety

Concurrency determines how many consumers/sessions can receive Messages at the same time.

With DefaultMessageListenerContainer:

~~~java
container.setConcurrentConsumers(3);
container.setMaxConcurrentConsumers(10);
~~~

Or through the factory:

~~~java
factory.setConcurrency("3-10");
~~~

With a Queue, multiple consumers typically compete to take different Messages from the same queue. Adding consumers can increase throughput if the handler and downstream systems have sufficient capacity.

However, when there are multiple consumers:

- The order in which processing completes is no longer guaranteed to match the send order.
- Two Messages for the same order may be processed concurrently.
- The database or downstream service may become a bottleneck.
- A listener object may be invoked concurrently, so it is unsafe if it holds unsynchronized mutable state.

With a Topic, you should not increase consumers mechanically. Depending on the subscription type and provider, multiple consumers may cause a single publication to be delivered to multiple consumers. Only configure concurrency for a Topic once you understand shared subscriptions and the specific semantics of the broker.

If ordering by business key matters, partition or serialize the processing by that key instead of relying on the number of consumers.

## 10. Acknowledgement and Transactions

After the listener processes a Message, the JMS provider needs to know whether the Message has been acknowledged or needs to be redelivered. This behavior depends on the acknowledgement mode and the transaction.

### 10.1. AUTO_ACKNOWLEDGE

This is the commonly used default mode. With a listener container, AUTO_ACKNOWLEDGE is not a reliable choice for every situation. If the listener fails, the provider may already have acknowledged the Message according to the callback behavior, and the Message risks being lost instead of redelivered.

If the business needs reliability, configure an appropriate transaction or acknowledgement.

### 10.2. sessionTransacted=true

Configuration:

~~~java
container.setSessionTransacted(true);
~~~

Each time the listener processes a Message, it runs within a JMS local transaction. When the listener completes normally, the container commits. When the listener throws an exception, the transaction rolls back and the provider may redeliver the Message according to the redelivery policy.

This is the choice usually suited to queue consumers that need reliable processing. Define the number of redeliveries, the backoff, and the dead-letter policy at the broker.

### 10.3. A JMS Transaction Does Not Automatically Include the Database

If the listener updates the database and then the JMS transaction rolls back, the database transaction may already have committed while the Message is redelivered. This creates the possibility of duplicate processing.

You need to design idempotency or duplicate detection, for example by storing the processed message ID/event ID in the same database transaction as the business update.

If you must commit JMS and the database as a single distributed transaction, you can use JTA/XA with an XA-capable ConnectionFactory and a suitable transaction coordinator. XA has higher cost and operational requirements; use it only when the business semantics truly require it.

## 11. Error Handling, Redelivery, and Poison Messages

A listener can fail because of an invalid payload, an interrupted external dependency, a database timeout, or a business bug.

You need to classify the errors:

- **Transient errors:** can be retried after a wait.
- **Data errors:** retrying does not help; send them to a dead-letter queue or an error-handling flow.
- **Infrastructure errors:** the container needs recovery/reconnect and broker state monitoring.
- **Programming errors:** need full logging of the message ID, destination, exception, and correlation ID.

Do not retry endlessly a Message that certainly cannot be processed. The broker typically provides a redelivery counter, delay, maximum attempts, and a dead-letter address/queue; the specific configuration depends on the provider.

A listener should log enough context but must not log secrets or the entire sensitive payload. When catching an exception, do not swallow the error if you need the transaction to roll back and the message to be redelivered.

DefaultMessageListenerContainer has a recovery mechanism for when the broker goes down. You can customize the BackOff to avoid retrying too aggressively when the broker is not yet ready.

## 12. Message Conversion and Responses

A JMS listener can receive a raw Message or a converted Java payload.

The default SimpleMessageConverter supports common JMS types such as TextMessage, BytesMessage, MapMessage, and ObjectMessage. If the application exchanges complex DTOs, configure an appropriate MessageConverter, typically a JSON converter with a clear schema and type mapping.

Do not enable arbitrary Java deserialization for ObjectMessage from untrusted sources. Control the allowed types and prefer data formats with a clear schema.

### 12.1. Replying to a Request via MessageListenerAdapter

If the delegate returns a non-null value, MessageListenerAdapter can convert that value into a JMS Message and send it to:

1. The destination specified in the request's JMSReplyTo.
2. The default response destination configured on the adapter if the request has no JMSReplyTo.

Example:

~~~java
public class InventoryDelegate {

    public String handleMessage(String sku) {
        return "available:" + sku;
    }
}
~~~

When the adapter receives a request and the delegate returns a String, the adapter can send a reply TextMessage. A valid reply destination is required; if there is nowhere to send the reply, the reply operation may fail.

This mechanism suits request-reply. For one-way events, the delegate should return void and the producer does not wait for a reply.

## 13. Lifecycle and Shutdown

A listener container is usually managed by Spring according to its lifecycle. When the application context starts, the container registers its consumers. When the application stops, the container stops receiving Messages and releases the resources it owns.

For a container created outside the Spring context, the application must proactively:

1. Initialize the container.
2. Start the container after it is fully configured.
3. Stop the container in the shutdown path.
4. Destroy the container to release the connection/session/consumer.

Do not close a Connection or Session that is being used by another listener. Let the container manage the resources it created.

If shutdown occurs while a listener is processing, determine the graceful shutdown wait time and the policy for uncommitted Messages. With a transacted session, closing or rolling back may cause the Message to be redelivered.

## 14. Runnable Java 17 Example: MessageListenerAdapter and DefaultMessageListenerContainer

The example below uses Apache ActiveMQ Classic 6.1.6 as the JMS provider, Spring Framework 6.2.19, and Java 17. An ActiveMQ Classic broker must be running at tcp://localhost:61616, and the queue orders.in must already exist or the broker must allow auto-creating queues.

The program uses MessageListenerAdapter to invoke a POJO that receives a String. DefaultMessageListenerContainer manages the receiving thread and the transacted session.

### 14.1. Maven Configuration

Create the pom.xml file:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>jms-message-listener-demo</artifactId>
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
            <artifactId>activemq-client</artifactId>
            <version>6.1.6</version>
        </dependency>
        <dependency>
            <groupId>jakarta.jms</groupId>
            <artifactId>jakarta.jms-api</artifactId>
            <version>3.1.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
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

ActiveMQ Classic 6.x uses the jakarta.jms namespace, which is compatible with Spring Framework 6. Do not mix a JMS client that uses javax.jms with Spring 6.

### 14.2. Complete Program

Create the file src/main/java/demo/JmsMessageListenerDemo.java:

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import jakarta.jms.ConnectionFactory;

import org.apache.activemq.ActiveMQConnectionFactory;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.listener.DefaultMessageListenerContainer;
import org.springframework.jms.listener.adapter.MessageListenerAdapter;

public class JmsMessageListenerDemo {

    public static final class OrderDelegate {
        private final CountDownLatch received;

        public OrderDelegate(CountDownLatch received) {
            this.received = received;
        }

        public void handleMessage(String orderId) {
            System.out.println("listener.payload=" + orderId);
            received.countDown();
        }
    }

    public static void main(String[] args) throws Exception {
        ConnectionFactory connectionFactory =
                new ActiveMQConnectionFactory("tcp://localhost:61616");

        CountDownLatch received = new CountDownLatch(1);
        OrderDelegate delegate = new OrderDelegate(received);

        MessageListenerAdapter adapter =
                new MessageListenerAdapter(delegate);
        adapter.setDefaultListenerMethod("handleMessage");

        DefaultMessageListenerContainer container =
                new DefaultMessageListenerContainer();

        container.setConnectionFactory(connectionFactory);
        container.setDestinationName("orders.in");
        container.setMessageListener(adapter);
        container.setSessionTransacted(true);
        container.setConcurrentConsumers(1);
        container.afterPropertiesSet();

        JmsTemplate producer = new JmsTemplate(connectionFactory);

        try {
            container.start();

            producer.convertAndSend("orders.in", "ORD-150");

            if (!received.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Listener did not receive the message in time"
                );
            }

            System.out.println("producer.completed=true");
        }
        finally {
            container.stop();
            container.destroy();
        }
    }
}
~~~

Run from the directory containing pom.xml once the broker is ready:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=demo.JmsMessageListenerDemo
~~~

The lines printed by the program:

~~~text
listener.payload=ORD-150
producer.completed=true
~~~

The JMS provider's internal logs may appear depending on the logging configuration. The order of the program's two lines is guaranteed by the CountDownLatch: the listener prints the payload before decrementing the latch; the producer prints completed only after the latch is released.

### 14.3. Program Analysis

The producer uses JmsTemplate to send the String ORD-150 to the queue orders.in. SimpleMessageConverter converts the String into a TextMessage.

DefaultMessageListenerContainer registered the consumer before the producer sent. When the Message arrives, the container invokes MessageListenerAdapter. The adapter converts the TextMessage into a String and then invokes OrderDelegate.handleMessage.

The listener runs on a receiving thread managed by the container. The producer does not call the delegate directly. The CountDownLatch is used only in the example to wait for the test result; in a real application, the producer usually continues its work right after sending and does not wait for the listener.

setSessionTransacted(true) places each listener processing run in a JMS local transaction. When the listener completes normally, the transaction is committed. If the listener throws an exception, the transaction may roll back and the broker redelivers the Message according to the redelivery policy.

The example uses a single consumer to keep the output order easy to observe. You can increase concurrency when you need throughput, but you must check ordering, thread safety, and the load on downstream systems.

## 15. Choosing the Appropriate Receiving Approach

| Need | Appropriate implementation |
|---|---|
| Need to read the raw JMS Message and check properties/headers | MessageListener |
| Want a POJO that does not depend on the JMS API | MessageListenerAdapter |
| Want to declare a listener with an annotation | @JmsListener |
| Need explicit configuration of threads, transactions, recovery, and concurrency | DefaultMessageListenerContainer or the corresponding factory |
| Need a simple container with a fixed number of consumers | SimpleMessageListenerContainer |
| Need to send a reply from the POJO's result | MessageListenerAdapter with JMSReplyTo or a response destination |
| Need reliable processing and redelivery when the listener fails | Container with sessionTransacted and the broker's redelivery policy |

There is no single choice that suits every system. Start from the Message type, the desired level of JMS dependency, transactions, concurrency, and the broker's operability.

## 16. Common Mistakes

1. **Assuming MessageListener creates threads itself:** a listener only defines the callback; it is the listener container or the JMS provider that coordinates the receiving threads.
2. **Sharing a single JMS Session across multiple threads yourself:** a Session is not designed for concurrent access; let the container manage separate sessions.
3. **Using a listener with mutable fields when increasing concurrency:** multiple consumers may invoke the same instance and cause race conditions.
4. **Forgetting to convert the payload:** if receiving a raw Message, you must check the type TextMessage, BytesMessage, MapMessage, or ObjectMessage before reading.
5. **Confusing MessageListenerAdapter with the broker:** the adapter only converts the Message and calls the POJO; the container must still connect to the provider.
6. **Not configuring a transaction when reliability is needed:** AUTO_ACKNOWLEDGE may not meet the redelivery requirement when the listener fails.
7. **Assuming sessionTransacted includes the database:** a local JMS transaction does not automatically commit/roll back the database.
8. **Adding consumers and expecting to keep ordering:** multiple consumers may complete Messages in an order different from the send order.
9. **Increasing concurrency for a Topic without understanding the subscription:** it may cause each publication to be processed by multiple consumers.
10. **Retrying a poison message endlessly:** configure maximum redelivery and a dead-letter policy at the broker.
11. **Not managing the lifecycle:** the listener container must be stopped/destroyed when the application stops.
12. **Confusing javax.jms and jakarta.jms:** Spring Framework 6 uses jakarta.jms; the client/provider must be namespace-compatible.
13. **Not specifying a Reply-To:** a delegate method that returns an object may trigger sending a reply; a valid destination is needed.
14. **Assuming a completed listener means exactly-once:** transactions and redelivery can still create duplicates in failure or restart scenarios.

## 17. Self-Check Questions

1. What callback method does the Jakarta JMS MessageListener have?
2. Why does asynchronous receiving not require the producer to call the consumer directly?
3. How does a Message-Driven POJO differ from a directly implemented MessageListener?
4. What is the name of the default delegate method that MessageListenerAdapter uses?
5. What Java types does SimpleMessageConverter map TextMessage and BytesMessage to?
6. What resources does the listener container manage?
7. How does SimpleMessageListenerContainer differ from DefaultMessageListenerContainer in capability?
8. How do @EnableJms and @JmsListener work together?
9. What does concurrency 3-10 mean?
10. Why can multiple consumers cause processing to lose its order?
11. What does sessionTransacted=true change when the listener throws an exception?
12. Why does a JMS local transaction not automatically include the database?
13. Where does MessageListenerAdapter send the reply when the delegate returns a non-null value?
14. Why must the listener be thread-safe when the container runs multiple consumers?
15. What needs to be done to avoid endlessly retrying a poison message?

## 18. Conclusion

Asynchronous receiving with MessageListener lets the JMS provider and the Spring listener container deliver Messages to processing logic on a receiving thread. MessageListener provides the standard callback; MessageListenerAdapter allows using a POJO that does not depend on the JMS API; @JmsListener helps declare the endpoint with an annotation.

The listener container manages the Connection, Session, Consumer, threads, transactions, acknowledgement, recovery, and lifecycle. When deploying, you need to choose a suitable container, configure concurrency according to load, keep the listener thread-safe, enable transactions when redelivery is needed, and coordinate idempotency with the database. Being able to deliver a Message to a Queue or Topic does not mean the business processing has happened exactly once.

## Official References

- Spring Framework 6.2 — Receiving a Message: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html
- Spring Framework 6.2 — Using Spring JMS: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html
- Spring Framework 6.2 — Annotation-driven Listener Endpoints: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html
- MessageListenerAdapter API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/adapter/MessageListenerAdapter.html
- DefaultMessageListenerContainer API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html
- SimpleMessageListenerContainer API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/SimpleMessageListenerContainer.html
- Jakarta Messaging specification: https://jakarta.ee/specifications/messaging/
- Apache ActiveMQ Classic 6.1.6 release: https://activemq.apache.org/components/classic/download/classic-06-01-06
