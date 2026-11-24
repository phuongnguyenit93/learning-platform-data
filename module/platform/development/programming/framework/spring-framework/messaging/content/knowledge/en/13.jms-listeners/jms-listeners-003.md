# Enabling @EnableJms and Declaring @JmsListener in Spring JMS

## 1. What Is an Annotation-Driven Listener?

Spring JMS lets you declare a Java method as a message listener using the `@JmsListener` annotation. When the application starts, Spring detects the annotated methods, creates listener endpoints, and manages listener containers to receive messages from the JMS destination.

Two central annotations:

- **@EnableJms:** enables the mechanism that detects and registers `@JmsListener` methods in the Spring ApplicationContext.
- **@JmsListener:** declares the destination and the message-handling method.

This mechanism separates the business logic from the code that manages the JMS lifecycle. Instead of writing your own message-receiving loop, creating consumers, and handling recovery, the application declares a listener; Spring creates and manages the container based on configuration.

~~~text
JMS Provider / Broker
        |
        v
Queue or Topic
        |
        v
JmsListenerContainerFactory
        |
        v
MessageListenerContainer
        |
        v
@JmsListener method
        |
        v
Business service
~~~

`@EnableJms` does not create a broker, a queue, or a connection to the JMS provider. The application must still configure a valid `jakarta.jms.ConnectionFactory` and a listener container factory.

## 2. Enabling @EnableJms

Place `@EnableJms` on a Spring-managed configuration class:

~~~java
@Configuration
@EnableJms
public class JmsConfiguration {
    // JMS beans are declared here.
}
~~~

When the ApplicationContext starts, Spring registers the annotation-driven JMS infrastructure. The main components:

- `JmsListenerAnnotationBeanPostProcessor`: detects the `@JmsListener` annotation on beans and registers the corresponding endpoints.
- `JmsListenerEndpointRegistry`: manages the listener containers created for those endpoints.
- `JmsListenerContainerFactory`: creates the container that runs each endpoint.

The listener class must be a Spring bean. Usually you use `@Component` with component scanning, or declare it with `@Bean`.

~~~java
@Component
public class OrderListener {

    @JmsListener(destination = "orders.queue")
    public void receive(String payload) {
        System.out.println("Received: " + payload);
    }
}
~~~

If the class is not a Spring bean, the annotation on the method will not create a listener by itself. Creating the object with `new OrderListener()` outside the container also does not trigger the annotation-detection mechanism.

`@JmsListener` is a repeatable annotation: a method can carry multiple declarations to receive from multiple destinations.

## 3. Declaring a JmsListenerContainerFactory

Each `@JmsListener` needs a listener container factory to create the container. By default, Spring looks for a bean named:

`jmsListenerContainerFactory`

If you use a different name, declare that name in the `containerFactory` attribute of `@JmsListener`. The default factory is only needed when at least one endpoint does not specify its own factory.

### 3.1. Configuring DefaultJmsListenerContainerFactory

A common configuration example:

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
        factory.setConcurrency("3-10");
        factory.setSessionTransacted(true);

        return factory;
    }
}
~~~

Important settings:

| Setting | Meaning |
|---|---|
| `setConnectionFactory(...)` | The ConnectionFactory the listener container uses to connect to the broker |
| `setConcurrency("3-10")` | The minimum and maximum number of consumers for a container that supports concurrency |
| `setSessionTransacted(true)` | Uses a local JMS transaction for the message-processing session |
| `setTransactionManager(...)` | Participates in a transaction managed by an external transaction manager |
| `setMessageConverter(...)` | Converts a JMS Message into a Java payload and vice versa |
| `setDestinationResolver(...)` | Resolves a destination name into a JMS Destination object |
| `setPubSubDomain(true)` | Configures the destination as a Topic rather than a Queue |
| `setErrorHandler(...)` | Receives errors that are not handled while the listener executes |
| `setAutoStartup(false)` | Does not automatically start the container when the ApplicationContext refreshes |

`DefaultJmsListenerContainerFactory` creates a `DefaultMessageListenerContainer`. This is the commonly used choice for applications that need transaction management, recovery, and concurrency.

### 3.2. Using a Factory with Its Own Name

An application can have multiple groups of listeners with different configurations:

~~~java
@Bean
DefaultJmsListenerContainerFactory ordersListenerFactory(
        ConnectionFactory connectionFactory) {

    DefaultJmsListenerContainerFactory factory =
        new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setConcurrency("2-6");
    factory.setSessionTransacted(true);
    return factory;
}

@Bean
DefaultJmsListenerContainerFactory auditListenerFactory(
        ConnectionFactory connectionFactory) {

    DefaultJmsListenerContainerFactory factory =
        new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setConcurrency("1");
    factory.setSessionTransacted(true);
    return factory;
}
~~~

Choosing the factory for each listener:

~~~java
@JmsListener(
    id = "ordersListener",
    destination = "orders.queue",
    containerFactory = "ordersListenerFactory"
)
public void receiveOrder(String payload) {
    // Process the order.
}

@JmsListener(
    id = "auditListener",
    destination = "audit.queue",
    containerFactory = "auditListenerFactory"
)
public void receiveAudit(String payload) {
    // Process the audit.
}
~~~

A separate factory is useful when listeners differ in concurrency, transaction, converter, destination type, or error handling.

## 4. Declaring @JmsListener

The simplest way is to specify only the destination:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(String payload) {
    orderService.process(payload);
}
~~~

`destination` can be a Queue or Topic name depending on the listener container factory configuration. With the default configuration `pubSubDomain=false`, Spring treats the destination as a Queue.

Commonly used attributes:

| Attribute | Role |
|---|---|
| `id` | The identifier of the endpoint/container for management and observation |
| `destination` | The name of the Queue or Topic to listen on |
| `containerFactory` | The name of the factory bean that creates the listener container |
| `selector` | A JMS message selector to filter messages by header/property |
| `subscription` | The durable subscription name when listening to a Topic |
| `concurrency` | Overrides the factory's concurrency for the endpoint |
| `autoStartup` | Determines whether the container starts automatically with the context |

Example combining the attributes:

~~~java
@JmsListener(
    id = "priorityOrders",
    destination = "orders.queue",
    selector = "priority >= 5",
    concurrency = "2-4",
    containerFactory = "jmsListenerContainerFactory"
)
public void receivePriorityOrder(String payload) {
    orderService.processPriority(payload);
}
~~~

The selector is a JMS message selector expression applied to JMS headers and properties. It does not query the body content of a TextMessage or a JSON payload. If you need to filter by a field inside the body, receive the message and then check in the business code.

### 4.1. Using a Property Placeholder for the Destination

There is no need to hard-code the destination name in the source. You can take the name from the application configuration:

~~~java
@JmsListener(destination = "${app.jms.orders-destination}")
public void receiveOrder(String payload) {
    orderService.process(payload);
}
~~~

In the configuration file, declare the corresponding destination:

~~~properties
app.jms.orders-destination=orders.queue
~~~

Spring resolves the placeholder when registering the endpoint. You can use SpEL if you need to reference a bean or a dynamic configuration expression, but keep the destination easy to control and verifiable at startup.

## 5. Queue, Topic, and Durable Subscription

JMS has two main destination models:

- **Queue (point-to-point):** a message is delivered to one consumer in a group of competing consumers.
- **Topic (publish-subscribe):** a message is broadcast to the registered subscribers; a durable subscription lets the broker retain messages according to its policy while the subscriber is offline.

### 5.1. Listening to a Topic

With `DefaultJmsListenerContainerFactory`, enable the pub/sub domain:

~~~java
@Bean
DefaultJmsListenerContainerFactory topicListenerFactory(
        ConnectionFactory connectionFactory) {

    DefaultJmsListenerContainerFactory factory =
        new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setPubSubDomain(true);
    return factory;
}
~~~

Declare a listener that uses this factory:

~~~java
@JmsListener(
    id = "newsSubscriber",
    destination = "news.topic",
    containerFactory = "topicListenerFactory"
)
public void receiveNews(String news) {
    newsService.handle(news);
}
~~~

If the factory is not configured with the appropriate pubSubDomain, the container may interpret the destination name as the wrong type or not receive messages as expected.

### 5.2. Durable Topic Subscription

The `subscription` attribute of `@JmsListener` sets the subscription name. Setting only this name is not enough to enable a durable subscription; the container factory also needs to configure durable mode and client identity according to the provider's requirements.

~~~java
@Bean
DefaultJmsListenerContainerFactory durableTopicListenerFactory(
        ConnectionFactory connectionFactory) {

    DefaultJmsListenerContainerFactory factory =
        new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setPubSubDomain(true);
    factory.setSubscriptionDurable(true);
    factory.setClientId("billing-service-client");
    return factory;
}
~~~

A listener using a durable subscription:

~~~java
@JmsListener(
    id = "billingEvents",
    destination = "billing.topic",
    subscription = "billing-service-subscription",
    containerFactory = "durableTopicListenerFactory"
)
public void receiveBillingEvent(String payload) {
    billingService.process(payload);
}
~~~

Points to remember:

- A durable subscription applies only to a Topic.
- The client ID must be stable and unique within the scope the broker specifies.
- The subscription name must be stable and unique within that client ID.
- A regular durable subscription normally has only one active consumer at a time. To let multiple consumers share a subscription, you need a shared subscription and a JMS provider supporting JMS 2.0 or later; configure `setSubscriptionShared(true)` on the factory.
- The listener's concurrency must be compatible with the subscription type in use.

Do not use the same durable subscription identity for multiple independent applications unless they are designed to share the subscription.

## 6. Listener Method Parameter Types

Spring converts the JMS message into the method parameters based on the `MessageConverter` and argument resolvers.

Commonly used parameter types:

- **Java payload:** String, a DTO, or a domain type if the converter supports it.
- **jakarta.jms.Message:** the original JMS message when you need access to properties, delivery mode, reply-to, or provider metadata.
- **jakarta.jms.Session:** the current JMS Session when you need low-level JMS operations.
- **org.springframework.messaging.Message<?>:** a Spring message with the payload and headers already mapped.
- **@Header:** gets a specific header.
- **@Headers:** gets the set of headers into a Map.
- **@Payload:** explicitly marks the parameter as the payload.
- **@Valid:** requires payload validation if an appropriate validator has been configured.

Example:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(
        @Payload OrderCreated event,
        @Header(JmsHeaders.MESSAGE_ID) String messageId,
        @Header(name = "correlationId", required = false)
        String correlationId) {

    orderService.process(event, messageId, correlationId);
}
~~~

`JmsHeaders.MESSAGE_ID` is the Spring header mapped from the JMS message ID. For an optional header, set `required=false` to avoid an error when the message does not have that value.

If you need full control over the message:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(
        jakarta.jms.Message jmsMessage,
        jakarta.jms.Session session) throws JMSException {

    String messageId = jmsMessage.getJMSMessageID();
    String correlationId = jmsMessage.getJMSCorrelationID();

    // Process according to the application's requirements.
}
~~~

Avoid passing the whole JMS Message or Session into the domain layer. Keep the JMS API in the adapter/listener layer and convert the needed data into business objects.

## 7. MessageConverter and Payload Conversion

JMS carries message types such as TextMessage, BytesMessage, MapMessage, ObjectMessage, and Message. A listener usually wants to receive a DTO or String rather than reading each JMS message type itself.

Spring JMS uses a `MessageConverter` to convert between JMS messages and Java objects.

### 7.1. The Default SimpleMessageConverter

If no other converter is configured, Spring uses `SimpleMessageConverter`. Common mappings:

| JMS message | Java object |
|---|---|
| TextMessage | String |
| BytesMessage | byte[] |
| MapMessage | Map |
| ObjectMessage | Serializable object |

Therefore, the following example directly receives a String from a TextMessage:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(String payload) {
    System.out.println(payload);
}
~~~

SimpleMessageConverter is convenient for simple data types. For complex DTOs, you should configure a converter with a clear schema/format.

### 7.2. JSON Converter for DTOs

You can use `MappingJackson2MessageConverter`:

~~~java
@Bean
MappingJackson2MessageConverter jacksonJmsMessageConverter() {
    MappingJackson2MessageConverter converter =
        new MappingJackson2MessageConverter();

    converter.setTargetType(MessageType.TEXT);
    converter.setTypeIdPropertyName("_type");
    return converter;
}

@Bean
DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory,
        MappingJackson2MessageConverter converter) {

    DefaultJmsListenerContainerFactory factory =
        new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setMessageConverter(converter);
    factory.setSessionTransacted(true);
    return factory;
}
~~~

When a converter is configured for the factory, the listener can receive a DTO:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(OrderCreated event) {
    orderService.process(event);
}
~~~

The producer must also use a compatible converter. Agree on the JSON format, type mapping, schema version, and the rules for handling invalid payloads between the producer and the consumer.

Do not enable arbitrary Java object deserialization from untrusted sources. For messages via a broker or from external systems, JSON/Bytes with a clear schema is usually easier to control than an ObjectMessage containing a Java serialized object.

## 8. Concurrency and Processing Order

A listener container can run multiple consumers to increase throughput. With DefaultJmsListenerContainerFactory:

~~~java
factory.setConcurrency("3-10");
~~~

The string `3-10` means the container starts with at least 3 consumers and can grow to 10 as needed. A single value such as `4` sets the upper limit to 4, with the minimum defaulting to 1. To fix exactly 4 consumers, use `4-4`.

You can override concurrency for a single endpoint:

~~~java
@JmsListener(
    destination = "orders.queue",
    concurrency = "2-6"
)
public void receive(String payload) {
    orderService.process(payload);
}
~~~

When concurrency is greater than one:

- Multiple listener invocations can run at the same time.
- The listener bean and the services it calls must be thread-safe.
- The order in which processing completes may differ from the order in which the broker delivers messages.
- Throughput may increase, but the load on the database and downstream services also increases.
- If you need to serialize by orderId or an aggregate key, you must design partitioning/ordering separately.

A single consumer usually keeps processing order more easily, but limits throughput. Do not increase concurrency based only on the number of messages; measure the processing time, the broker capacity, and downstream resources.

## 9. Acknowledgment, Transactions, and Redelivery

A listener's reliability depends on the acknowledgment mode and the transaction.

### 9.1. AUTO_ACKNOWLEDGE and sessionTransacted

With `DefaultMessageListenerContainer`, the default `AUTO_ACKNOWLEDGE` mode acknowledges the message before the listener method runs. Therefore, if the listener throws an exception, the message is not redelivered automatically in this default mode.

To have the listener process within a local JMS transaction, configure:

~~~java
factory.setSessionTransacted(true);
~~~

When the listener completes normally, the session commits. If the listener throws an exception out of the invocation, the transaction may roll back and the broker may redeliver the message according to the provider's policy.

For this mechanism to work correctly:

- Do not swallow exceptions if you want the container to know processing has failed.
- Understand the broker's redelivery limit and dead-letter policy.
- Ensure the business logic is idempotent because messages may be redelivered.
- Do not assume a JMS rollback automatically rolls back an independent database transaction.

### 9.2. External Transaction Manager

If you need to coordinate JMS with the application's transaction manager, you can configure `setTransactionManager(...)` on the factory with an appropriate transaction manager. A JTA/XA environment can coordinate multiple resources if the provider and datasource support XA.

`setSessionTransacted(true)` creates a local JMS transaction. It does not turn database and JMS operations into a single distributed atomic transaction by itself.

If you do not use XA, consider the Outbox pattern, idempotency keys, or eventual consistency to handle the situation where the database commit succeeds but sending the message fails, or vice versa.

### 9.3. Redelivery and Dead-Letter

The Spring listener container does not fully define the policy for storing failed messages for every broker. Redelivery delay, maximum delivery attempts, dead-letter address/queue, and message expiry are usually configured by the JMS provider.

Define clearly:

1. Which errors are retried?
2. What is the maximum number of retries?
3. When the retries are exhausted, where is the message sent?
4. Who monitors and handles the dead-letter?
5. Can the consumer safely process a message repeatedly?

Do not endlessly retry a message with a permanent data error, because it can cause a loop and occupy queue resources.

## 10. Error Handling and Listener Monitoring

You can configure an ErrorHandler for the listener container:

~~~java
factory.setErrorHandler(exception -> {
    // Log/metric safely; do not log tokens or sensitive payloads.
});
~~~

The ErrorHandler is where you observe errors that arise while the listener executes. It does not replace transaction rollback, provider redelivery, or dead-letter policy.

Some points to monitor:

- The number of messages received and successfully processed.
- The number of listener exceptions and the number of redeliveries.
- The consumer count and the state of the listener container.
- Queue depth, message age, and dead-letter count.
- Processing time and downstream errors.
- Connection recovery and the time the container stops receiving messages.

Use a correlation ID or message ID to link logs. Avoid logging the whole payload, credentials, or sensitive headers.

## 11. Replying from a Listener with @SendTo

A listener method can return a value. Spring converts that value into a JMS message and sends the reply:

- If the request has a JMSReplyTo, the reply is sent to that destination.
- If there is no JMSReplyTo, you can declare a default destination with `@SendTo`.

Example:

~~~java
@JmsListener(destination = "orders.request")
@SendTo("orders.reply")
public OrderStatus process(OrderCommand command) {
    return orderService.process(command);
}
~~~

You can return a Spring `Message<?>` if you need to add headers to the reply. If the reply destination needs to be computed at runtime, use `JmsResponse` to wrap the response together with a specific destination.

Only use the reply pattern when the producer actually waits for a reply. For one-way events, the listener should usually return void to avoid creating unnecessary messages.

## 12. Managing Listener Containers

The listener containers created by `@JmsListener` are managed in the `JmsListenerEndpointRegistry`.

If you assign an ID to the endpoint:

~~~java
@JmsListener(id = "ordersListener", destination = "orders.queue")
public void receive(String payload) {
    orderService.process(payload);
}
~~~

You can access the container by ID:

~~~java
@Autowired
private JmsListenerEndpointRegistry registry;

public void stopOrdersListener() {
    MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");

    if (container != null) {
        container.stop();
    }
}
~~~

The registry allows retrieving and managing the lifecycle of the listener containers. You can use it to start/stop listeners according to the application state, a feature flag, or an operational procedure.

If the annotation sets `autoStartup=false`, the container does not run automatically when the context starts; the application can start it proactively once the necessary conditions are ready.

## 13. Runnable Java 17+ Example with an Embedded Artemis Broker

The following example starts an embedded Artemis broker, configures Spring with `@EnableJms`, registers a `@JmsListener`, sends three messages using JmsTemplate, and waits for the listener to process them.

**Project structure**

~~~text
jms-listener-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          JmsListenerDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>jms-listener-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
            <version>6.2.18</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.18</version>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-server</artifactId>
            <version>2.37.0</version>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-client</artifactId>
            <version>2.37.0</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/JmsListenerDemo.java**

~~~java
package demo;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.Session;
import org.apache.activemq.artemis.core.config.impl.ConfigurationImpl;
import org.apache.activemq.artemis.core.server.embedded.EmbeddedActiveMQ;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

public class JmsListenerDemo {

    public static void main(String[] args) throws Exception {
        EmbeddedActiveMQ broker = new EmbeddedActiveMQ();
        broker.setConfiguration(new ConfigurationImpl()
            .setPersistenceEnabled(false)
            .setSecurityEnabled(false)
            .addAcceptorConfiguration("netty", "tcp://127.0.0.1:61616"));
        broker.start();

        ActiveMQConnectionFactory nativeFactory =
            new ActiveMQConnectionFactory("tcp://127.0.0.1:61616");

        try {
            try (Connection connection = nativeFactory.createConnection();
                 Session session = connection.createSession(
                     false, Session.AUTO_ACKNOWLEDGE)) {
                session.createQueue("orders.queue");
            }

            OrderListener listener = new OrderListener(3);

            try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

                context.registerBean(
                    "nativeConnectionFactory",
                    ConnectionFactory.class,
                    () -> nativeFactory
                );
                context.registerBean(
                    "orderListener",
                    OrderListener.class,
                    () -> listener
                );
                context.register(JmsConfiguration.class);
                context.refresh();

                JmsTemplate template = context.getBean(JmsTemplate.class);
                template.convertAndSend("orders.queue", "order-1");
                template.convertAndSend("orders.queue", "order-2");
                template.convertAndSend("orders.queue", "order-3");

                if (!listener.await(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                        "Timed out waiting for JMS messages"
                    );
                }

                List<String> received = new ArrayList<>(listener.messages());
                Collections.sort(received);
                System.out.println("receivedCount=" + received.size());
                System.out.println("messages=" + received);
            }
        }
        finally {
            nativeFactory.close();
            broker.stop();
        }
    }

    @Configuration
    @EnableJms
    static class JmsConfiguration {

        @Bean
        DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
                ConnectionFactory nativeConnectionFactory) {

            DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
            factory.setConnectionFactory(nativeConnectionFactory);
            factory.setConcurrency("1-2");
            factory.setSessionTransacted(true);
            return factory;
        }

        @Bean
        JmsTemplate jmsTemplate(ConnectionFactory nativeConnectionFactory) {
            return new JmsTemplate(nativeConnectionFactory);
        }
    }

    @Component
    static class OrderListener {
        private final CountDownLatch latch;
        private final List<String> messages =
            Collections.synchronizedList(new ArrayList<>());

        OrderListener(int expectedMessages) {
            this.latch = new CountDownLatch(expectedMessages);
        }

        @JmsListener(destination = "orders.queue")
        public void receive(String payload) {
            messages.add(payload);
            latch.countDown();
        }

        boolean await(long timeout, TimeUnit unit) throws InterruptedException {
            return latch.await(timeout, unit);
        }

        List<String> messages() {
            synchronized (messages) {
                return List.copyOf(messages);
            }
        }
    }
}
~~~

Run from the `jms-listener-demo` directory:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.JmsListenerDemo
~~~

**Output from the program**

~~~text
receivedCount=3
messages=[order-1, order-2, order-3]
~~~

Explanation:

1. The embedded Artemis broker opens a TCP acceptor on port 61616.
2. Artemis's ConnectionFactory is registered as a Spring bean.
3. `@EnableJms` enables annotation processing and registers the listener container.
4. The OrderListener bean with the `@JmsListener` method is detected and listens on `orders.queue`.
5. JmsTemplate sends three TextMessages.
6. The listener receives the payload as a String thanks to the default SimpleMessageConverter.
7. The CountDownLatch waits for all three messages; the list is sorted before printing so the result is stable.

The example uses an embedded broker for learning and testing. Production needs a standalone broker and appropriate configuration for credentials, TLS, destination provisioning, monitoring, transactions, and redelivery policy.

## 14. Common Mistakes

1. **Forgetting @EnableJms:** Spring does not enable the annotation-driven listener infrastructure; the @JmsListener method is not registered.
2. **The listener is not a Spring bean:** the annotation is only detected on beans in the ApplicationContext.
3. **Missing the default factory:** if `containerFactory` is not specified, Spring looks for the bean `jmsListenerContainerFactory`.
4. **Wrong factory name:** the `containerFactory` attribute must match the actual bean name.
5. **Confusing Queue and Topic:** check the factory's `pubSubDomain` and the destination configuration at the broker.
6. **A selector filtering by body:** the JMS selector only examines headers/properties and does not query the JSON or TextMessage body.
7. **A DTO is not converted:** configure a compatible MessageConverter at the producer and the listener factory.
8. **Concurrency too high:** can place heavy load on the broker, database, and downstream; the listener bean must be thread-safe.
9. **Using AUTO_ACKNOWLEDGE but expecting rollback:** DefaultMessageListenerContainer acknowledges before the listener; use a transaction if you need rollback/redelivery.
10. **Swallowing exceptions in the listener:** the container may consider the invocation complete and not roll back as expected.
11. **Confusing ErrorHandler with dead-letter:** the ErrorHandler observes errors; the broker policy decides redelivery and dead-letter.
12. **Using a durable subscription without a client identity:** configure the durable mode, client ID, and subscription name correctly for the provider.
13. **Increasing concurrency on a non-shared durable subscription:** a regular durable subscription allows only one consumer; you need a shared subscription and broker support if you want to scale horizontally on the same subscription.
14. **Not closing self-created producer/consumer resources:** prefer JmsTemplate and the listener container; if using the JMS API directly, manage the Session and resources according to their lifecycle.
15. **Not monitoring the container:** use a stable ID and JmsListenerEndpointRegistry to observe, start, or stop endpoints.

## 15. Deployment Checklist

Before putting a listener into production, check:

1. Is the ConnectionFactory connected to the correct broker and is its lifecycle managed by Spring?
2. Does the Configuration have `@EnableJms`?
3. Is the listener class a Spring bean?
4. Is there a `jmsListenerContainerFactory` factory bean or a separate factory specified correctly?
5. Do the Queue/Topic, selector, and durable subscription match the broker configuration?
6. Is the MessageConverter compatible with the producer and the payload schema?
7. Is the concurrency suitable for the business ordering and downstream capacity?
8. Does the acknowledgment/transaction meet the redelivery requirement?
9. Is the listener idempotent and does it handle duplicates safely?
10. Have the ErrorHandler, retry, backoff, and dead-letter policy been defined?
11. Do the logs/metrics carry the correlation ID and avoid sensitive data?
12. Is there an integration test with a JMS provider to confirm the annotation is registered and messages are actually received?

## 16. Conclusion

`@EnableJms` enables the annotation-driven JMS infrastructure; `@JmsListener` declares the destination and the processing method. The listener container factory determines the ConnectionFactory, concurrency, converter, transaction, error handling, and destination type. Spring manages the lifecycle of the containers through the JmsListenerEndpointRegistry.

A reliable listener needs more than an annotation: you must correctly configure the Queue/Topic, converter, transaction, concurrency, retry/redelivery, and observability. Start with a simple listener, test it with a JMS provider, then expand concurrency and transactions according to load and business requirements.

## 17. References

- [Spring Framework 6.2 — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html)
- [EnableJms — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/jms/annotation/EnableJms.html)
- [JmsListener — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/jms/annotation/JmsListener.html)
- [DefaultJmsListenerContainerFactory — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html)
- [JmsListenerEndpointRegistry — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistry.html)
- [DefaultMessageListenerContainer — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)
- [JmsTemplate — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)