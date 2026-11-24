# Multiple @JmsListener Annotations on One Method and the @JmsListeners Annotation

## Learning Objectives

After this lesson, you can:

- Explain why a single Java method can carry multiple @JmsListener annotations.
- Understand that @JmsListener is a repeatable annotation and @JmsListeners is the container annotation.
- Distinguish direct repeated declaration from explicitly writing @JmsListeners.
- Know that each listener declaration creates a separate endpoint managed by a listener container.
- Configure a separate destination, id, selector, concurrency, and containerFactory for each endpoint.
- Understand how a shared method receives Messages from multiple Queues or Topics.
- Avoid errors involving thread safety, durable subscriptions, processing order, and payload conversion.
- Monitor, stop, and start endpoints through the JmsListenerEndpointRegistry.

## 1. The Problem: Multiple Destinations, One Handling Method

An application may receive the same kind of business message from multiple JMS destinations. For example:

- The Queue orders.priority receives priority orders.
- The Queue orders.standard receives regular orders.
- The Topic orders.events broadcasts order events.
- Another destination is used in a separate environment or tenant.

If the business logic is the same, we may want multiple destinations to call the same method. Spring supports this by allowing @JmsListener to be declared multiple times on the same method.

~~~java
@JmsListener(destination = "orders.priority")
@JmsListener(destination = "orders.standard")
public void handleOrder(String orderId) {
    process(orderId);
}
~~~

The two annotations describe two different listener endpoints. Each endpoint has its own destination and configuration, but both call the handleOrder method when a matching Message is received.

~~~mermaid
flowchart TB
    A["Queue orders.priority"]
    B["Queue orders.standard"]
    C["Listener endpoint 1"]
    D["Listener endpoint 2"]
    E["Same method handleOrder(String)"]
    F["Business logic process(orderId)"]

    A --> C --> E
    B --> D --> E
    E --> F
~~~

This approach helps reuse the processing logic. It does not merge multiple destinations into one Queue, and it does not turn multiple endpoints into a single subscription.

## 2. @JmsListener Is a Repeatable Annotation

In Java 8 and later, an annotation can be marked as repeatable using the @Repeatable meta-annotation. Spring declares @JmsListener this way:

~~~java
@Repeatable(JmsListeners.class)
public @interface JmsListener {
    // The endpoint configuration attributes
}
~~~

Therefore, a method can declare multiple @JmsListener annotations directly:

~~~java
@JmsListener(destination = "orders.priority")
@JmsListener(destination = "orders.standard")
public void handleOrder(String orderId) {
    // Process the order
}
~~~

At compile time, Java uses a container annotation to hold multiple annotations of the same type. In this case, the container is @JmsListeners.

Spring reads the repeated declarations and registers each listener endpoint. Each declaration can represent its own destination and configuration.

Packages to know:

- @JmsListener: org.springframework.jms.annotation.JmsListener.
- @JmsListeners: org.springframework.jms.annotation.JmsListeners.
- @EnableJms: org.springframework.jms.annotation.EnableJms.

This is a Spring JMS API, not an annotation of Spring Messaging in general.

## 3. @JmsListeners Is the Container Annotation

@JmsListeners is the container annotation used to group multiple @JmsListener annotations. It has a value element containing an array of @JmsListener annotations.

It can be written explicitly as follows:

~~~java
@JmsListeners({
    @JmsListener(
            id = "priorityOrders",
            destination = "orders.priority"
    ),
    @JmsListener(
            id = "standardOrders",
            destination = "orders.standard"
    )
})
public void handleOrder(String orderId) {
    process(orderId);
}
~~~

This form is equivalent in meaning to placing two @JmsListener annotations directly on the method:

~~~java
@JmsListener(
        id = "priorityOrders",
        destination = "orders.priority"
)
@JmsListener(
        id = "standardOrders",
        destination = "orders.standard"
)
public void handleOrder(String orderId) {
    process(orderId);
}
~~~

In modern Java code, direct repeated declaration is usually easier to read. Writing @JmsListeners explicitly is useful when you want to show the container annotation clearly or when creating a composed annotation.

**Point to remember:** @JmsListeners only groups the annotation declarations. It is not a shared listener container for all the destinations. Spring still processes each @JmsListener inside it to register the corresponding endpoints.

There is no need to place both declaration styles on the same method. Choose one of the two approaches to avoid duplicate declarations.

## 4. How Does Spring Register Endpoints?

@JmsListener does not directly open a Connection or receive Messages by itself. Spring uses an annotation processor and a listener container factory to create the receiving infrastructure.

Conceptual initialization flow:

~~~mermaid
flowchart TD
    A["Application context starts"]
    B["@EnableJms enables annotation support"]
    C["JmsListenerAnnotationBeanPostProcessor"]
    D["Detects the @JmsListener annotations"]
    E["Creates an endpoint for each annotation"]
    F["Selects the JmsListenerContainerFactory"]
    G["Creates the listener container"]
    H["The container registers a consumer with the JMS provider"]

    A --> B --> C --> D --> E --> F --> G --> H
~~~

An endpoint describes how to receive Messages from a destination. The listener container is responsible for connecting to the JMS provider, creating the Session and Consumer, managing threads and transactions, and calling the annotated method.

Spring provides the JmsListenerEndpointRegistry to manage the listener containers created by the annotation infrastructure. These containers are not registered as ordinary independent beans, but can be retrieved through the registry by endpoint ID.

### 4.1. Enabling Annotation Support

Add @EnableJms to a configuration class:

~~~java
@Configuration
@EnableJms
public class JmsConfiguration {
}
~~~

If annotation support is not enabled, Spring does not register methods with @JmsListener as endpoints.

### 4.2. The Default Listener Container Factory

By default, Spring looks for a bean named jmsListenerContainerFactory to create the listener container:

~~~java
@Bean
public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory) {

    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setSessionTransacted(true);
    factory.setConcurrency("2-5");

    return factory;
}
~~~

If containerFactory is not specified on the annotation, the endpoint uses this default factory. You can declare another factory and choose it separately for each @JmsListener.

## 5. Each @JmsListener Has Its Own Configuration

An important advantage of the repeatable annotation is that each declaration can carry different configuration.

Commonly used attributes:

| Attribute | Meaning |
|---|---|
| destination | The name of the Queue or Topic the endpoint receives from |
| id | The unique ID of the listener container in the registry |
| containerFactory | The name of the JmsListenerContainerFactory bean used for the endpoint |
| selector | A JMS message selector to filter Messages |
| concurrency | Limits the number of concurrent consumers of the endpoint |
| subscription | The durable subscription name when receiving from a Topic |

Example:

~~~java
@JmsListener(
        id = "priorityOrders",
        destination = "orders.in",
        selector = "priority >= 5",
        concurrency = "2-4",
        containerFactory = "fastListenerFactory"
)
@JmsListener(
        id = "standardOrders",
        destination = "orders.in",
        selector = "priority < 5",
        concurrency = "1",
        containerFactory = "standardListenerFactory"
)
public void handleOrder(String orderId) {
    process(orderId);
}
~~~

The two endpoints read the same orders.in but apply different selectors and concurrency. Messages are classified by the JMS properties matching the selector.

If multiple selectors can match at the same time, understand the semantics of the consumers and destination. With a Queue, consumers compete to receive Messages; a Message is not broadcast to all consumers of the Queue. With a Topic, subscriptions have their own publish-subscribe semantics.

### 5.1. The ID Must Be Clear and Unique

The ID identifies the endpoint's container. If left blank, Spring generates an ID. With multiple @JmsListener annotations on the same method, you should declare a separate ID to make management easier:

~~~java
@JmsListener(id = "priorityOrders", destination = "orders.priority")
@JmsListener(id = "standardOrders", destination = "orders.standard")
public void handleOrder(String orderId) {
    process(orderId);
}
~~~

You can retrieve the container:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("priorityOrders");
~~~

Then call start(), stop(), or check the state as operational needs require. The registry is also useful when you need to observe the registered endpoints.

Do not use the same ID for multiple annotations. A duplicate ID makes registering and managing containers ambiguous or causes failure.

### 5.2. Choosing the containerFactory per Endpoint

Each annotation can specify a different containerFactory:

~~~java
@JmsListener(
        id = "queueOrders",
        destination = "orders.in",
        containerFactory = "queueListenerFactory"
)
@JmsListener(
        id = "topicEvents",
        destination = "orders.events",
        containerFactory = "topicListenerFactory"
)
public void handle(String payload) {
    process(payload);
}
~~~

This approach is useful when the Queue and Topic need different pubSubDomain configuration, or when endpoints have different requirements for transaction, concurrency, error handler, converter, and recovery.

A factory can be shared by multiple endpoints if they have the same policy. There is no need to create a new factory for each annotation if the configuration does not differ.

## 6. How Does a Shared Method Receive the Payload?

The endpoints on the same method all use the same method signature. Spring converts the JMS Message into the Java parameters according to the converter and the listener adapter's argument resolution mechanism.

Example:

~~~java
@JmsListener(destination = "orders.priority")
@JmsListener(destination = "orders.standard")
public void handleOrder(String orderId) {
    process(orderId);
}
~~~

With the default converter configuration, a TextMessage is usually converted into a String. If the two destinations send different Message types, you need to ensure the method signature and converter can handle both.

Commonly supported parameter types include:

- A Java payload such as String or a DTO.
- jakarta.jms.Message or a subclass such as TextMessage.
- jakarta.jms.Session when you need access to the JMS API.
- org.springframework.messaging.Message to receive the payload along with the headers.
- A parameter with @Header to get a specific header.
- A Map parameter with @Headers to receive the set of headers.

Example of reading additional metadata:

~~~java
@JmsListener(destination = "orders.priority")
@JmsListener(destination = "orders.standard")
public void handleOrder(
        String orderId,
        @Header("eventType") String eventType) {

    process(orderId, eventType);
}
~~~

Both destinations must send compatible eventType metadata. If a destination lacks a required header, binding the parameter may fail; you can use required=false or a default value if the business logic allows.

### 6.1. Using the Raw JMS Message When the Structure Is Not Uniform

If the destinations send multiple kinds of JMS Message or you need to check properties, you can receive the raw Message:

~~~java
@JmsListener(destination = "orders.priority")
@JmsListener(destination = "orders.standard")
public void handleMessage(jakarta.jms.Message message) {
    // Check the Message type and read the corresponding data.
}
~~~

This approach allows different handling depending on TextMessage, BytesMessage, MapMessage, or JMS metadata. In exchange, the method must check the type and handle JMSException itself.

If you only share a single DTO, keep the payload signature explicit to avoid manual type conversion and checking.

## 7. Queue and Topic When There Are Multiple Listener Endpoints

The meaning of repeating @JmsListener depends on the destination type.

### 7.1. Multiple Endpoints Reading the Same Queue

Example:

~~~java
@JmsListener(destination = "orders.in")
@JmsListener(destination = "orders.in")
public void handleOrder(String orderId) {
    process(orderId);
}
~~~

Each annotation creates a separate endpoint. If both endpoints read the same Queue, they create competing consumers on that Queue. Under the point-to-point model, a Message is delivered to one consumer that receives it; it does not automatically call the method twice for the same Message.

However, if both endpoints have matching selectors, both may compete to receive the Messages that satisfy the condition. Avoid duplicate declarations unless you intend to increase the number of consumers.

### 7.2. Multiple Endpoints Receiving the Same Topic

A Topic uses the publish-subscribe model. Independent subscriptions can receive copies of the same publication.

If multiple @JmsListener annotations register on the same Topic with separate subscriptions, a publication can be delivered to each subscription. This is different behavior from a Queue and can cause the same method logic to be called multiple times for the same event.

Do not increase a Topic's concurrency mechanically. Configuring multiple consumers on the same Topic can lead to the same publication being processed multiple times concurrently, depending on the subscription type and the JMS provider.

### 7.3. Durable Subscription and Subscription Name

The subscription attribute is used to set the durable subscription name. A durable subscription lets the broker retain Messages according to the subscription policy while the subscriber is temporarily offline.

The Spring Javadoc notes that the default subscription name can be generated from the fully qualified name of the listener method. When multiple @JmsListener annotations on the same method use a durable Topic, declare a separate subscription name for each endpoint to avoid duplicate subscription identities.

Besides the subscription name, a durable subscriber also depends on the client ID, the container configuration, and the capabilities of the JMS provider. Check the client identity and durable/shared subscription configuration of the broker in use.

## 8. Concurrency and Thread Safety of a Shared Method

A method with multiple @JmsListener annotations can be called from multiple listener containers. Each endpoint can have its own concurrency.

Example:

~~~java
@JmsListener(
        destination = "orders.priority",
        concurrency = "3"
)
@JmsListener(
        destination = "orders.standard",
        concurrency = "2"
)
public void handleOrder(String orderId) {
    process(orderId);
}
~~~

The total number of consumers can be larger than the concurrency of a single endpoint. In the example, each endpoint has its own number of consumers per configuration, and both call the same method on the same listener bean.

This is an easily overlooked point: setting concurrency=1 for each endpoint does not mean the whole method runs on only one thread at a time. Two different endpoints can still call the method concurrently.

Therefore:

- Prefer a stateless listener.
- Use local variables for the data of each processing run.
- If you need to share a counter or cache, use a thread-safe structure.
- Do not hold a JMS Session or MessageConsumer in a field for multiple calls to use.
- Protect operations that update the same business entity with a transaction or an appropriate synchronization mechanism.
- Do not assume a global processing order among destinations.

If the business requires serializing all orders from multiple destinations, use an explicit coordination mechanism, such as a sequential worker, partitioning by key, or a merged queue. Multiple @JmsListener annotations do not by themselves create a common ordering guarantee.

## 9. Transactions and Error Handling

Each endpoint has its own listener container and session per configuration. Transactions, acknowledgement, and redelivery are applied according to that endpoint's container factory.

Example:

~~~java
factory.setSessionTransacted(true);
~~~

When using sessionTransacted=true, the listener processes the Message in a JMS local transaction. If the method completes normally, the container commits. If the method throws an exception, the transaction may roll back and the broker redelivers the Message according to the redelivery policy.

If a method is called from multiple endpoints, each call still belongs to the transaction of the endpoint that received the Message. A successful processing run on the first destination does not commit or roll back the transaction of the second endpoint.

Points to note:

- The default AUTO_ACKNOWLEDGE does not provide a reliable redelivery guarantee for every failure case.
- Configure the transaction for each factory to suit the business requirements.
- A JMS local transaction does not automatically include the database transaction.
- If there are side effects in the database or external APIs, you need idempotency and duplicate detection.
- Configure maximum redelivery and dead-letter policy at the broker to avoid a poison message repeating endlessly.

When multiple endpoints call the same method, the log should include the destination, message ID, correlation ID, or event type to identify which endpoint triggered the processing run.

## 10. Replying from a Shared Method

A listener method can return a non-void value. Spring can convert that value into a JMS response and send it to the destination specified in the request's JMSReplyTo. If the request has no JMSReplyTo, you can configure a default destination with @SendTo.

Example:

~~~java
@JmsListener(destination = "orders.priority")
@JmsListener(destination = "orders.standard")
@SendTo("orders.status")
public OrderStatus handleOrder(Order order) {
    return process(order);
}
~~~

In the example, the two endpoints share the reply destination policy orders.status.

If each endpoint needs to send its reply to a different destination, a fixed @SendTo on the method may not be enough. Use JmsResponse to choose the destination per request, or split into separate methods when the reply logic differs.

Not every one-way event needs a return value. If the producer does not wait for a response, using a void method makes the intent clearer.

## 11. When to Use an Explicit @JmsListeners?

Direct repeated declaration is the common approach:

~~~java
@JmsListener(destination = "orders.priority")
@JmsListener(destination = "orders.standard")
public void handleOrder(String orderId) {
    process(orderId);
}
~~~

The container annotation can be written explicitly:

~~~java
@JmsListeners({
    @JmsListener(destination = "orders.priority"),
    @JmsListener(destination = "orders.standard")
})
public void handleOrder(String orderId) {
    process(orderId);
}
~~~

You should use direct repeated declaration when:

- The code runs on Java 8 or later.
- You want to quickly read the destinations that call the same method.
- Each annotation has simple configuration.

You can use an explicit @JmsListeners when:

- You want to show the container annotation clearly in code or documentation.
- You are creating a composed annotation reused in many places.
- You need to group the child annotations into a single declaration per the codebase's convention.

Both approaches rely on the same Java repeatable annotation mechanism and are processed by Spring into separate listener endpoints.

## 12. When the Destination List Is Only Known at Runtime

A repeatable annotation suits cases where the destination list can be declared statically in the source code. If the destination list is loaded from a database, tenant configuration, or a registry at application startup, you cannot write an arbitrary number of annotations at compile time.

In that case, you can register endpoints using JmsListenerConfigurer and JmsListenerEndpointRegistrar:

~~~java
@Configuration
@EnableJms
public class DynamicJmsConfiguration implements JmsListenerConfigurer {

    @Override
    public void configureJmsListeners(
            JmsListenerEndpointRegistrar registrar) {

        SimpleJmsListenerEndpoint endpoint =
                new SimpleJmsListenerEndpoint();

        endpoint.setId("dynamicOrders");
        endpoint.setDestination("orders.dynamic");
        endpoint.setMessageListener(message -> {
            // Process the JMS Message
        });

        registrar.registerEndpoint(endpoint);
    }
}
~~~

You can loop over a configuration list to register multiple endpoints. This is the more suitable approach for a number of destinations that changes according to runtime configuration.

Do not try to create annotations via reflection after the application context has finished initializing and expect Spring to automatically re-register endpoints. Use the official endpoint registration API.

## 13. Runnable Java 17 Example with Two @JmsListener Annotations on One Method

The following example uses Spring Framework 6.2.19 and Apache ActiveMQ Classic 6.1.6. The broker runs embedded in the same JVM via BrokerService and the VM transport. Two Queues are routed to the same listener method.

### 13.1. Maven Configuration

Create the pom.xml file:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>repeatable-jms-listener-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework</groupId>
                <artifactId>spring-framework-bom</artifactId>
                <version>6.2.19</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>activemq-broker</artifactId>
            <version>6.1.6</version>
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

### 13.2. Spring JMS Configuration

Create the file src/main/java/demo/JmsDemoConfiguration.java:

~~~java
package demo;

import jakarta.jms.ConnectionFactory;

import org.apache.activemq.ActiveMQConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;

@Configuration
@EnableJms
public class JmsDemoConfiguration {

    @Bean
    public ConnectionFactory connectionFactory() {
        return new ActiveMQConnectionFactory(
                "vm://repeatable-listener-demo?create=false"
        );
    }

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1");

        return factory;
    }

    @Bean
    public JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        return new JmsTemplate(connectionFactory);
    }

    @Bean
    public SharedOrderListener sharedOrderListener() {
        return new SharedOrderListener();
    }
}
~~~

### 13.3. The Shared Listener

Create the file src/main/java/demo/SharedOrderListener.java:

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.jms.annotation.JmsListener;

public class SharedOrderListener {

    private final AtomicInteger priorityCount = new AtomicInteger();
    private final AtomicInteger standardCount = new AtomicInteger();
    private final CountDownLatch received = new CountDownLatch(2);

    @JmsListener(
            id = "priorityOrders",
            destination = "orders.priority",
            containerFactory = "jmsListenerContainerFactory",
            concurrency = "1"
    )
    @JmsListener(
            id = "standardOrders",
            destination = "orders.standard",
            containerFactory = "jmsListenerContainerFactory",
            concurrency = "1"
    )
    public void handleOrder(String payload) {
        if (payload.startsWith("priority:")) {
            priorityCount.incrementAndGet();
        }
        else if (payload.startsWith("standard:")) {
            standardCount.incrementAndGet();
        }
        else {
            throw new IllegalArgumentException(
                    "Unsupported order payload: " + payload
            );
        }

        received.countDown();
    }

    public boolean awaitMessages(long timeout, TimeUnit unit)
            throws InterruptedException {
        return received.await(timeout, unit);
    }

    public int getPriorityCount() {
        return priorityCount.get();
    }

    public int getStandardCount() {
        return standardCount.get();
    }
}
~~~

### 13.4. Starting the Broker and Sending Two Messages

Create the file src/main/java/demo/RepeatableJmsListenerDemo.java:

~~~java
package demo;

import java.util.concurrent.TimeUnit;

import org.apache.activemq.broker.BrokerService;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.jms.core.JmsTemplate;

public class RepeatableJmsListenerDemo {

    public static void main(String[] args) throws Exception {
        BrokerService broker = new BrokerService();
        broker.setBrokerName("repeatable-listener-demo");
        broker.setPersistent(false);
        broker.setUseJmx(false);

        broker.start();
        broker.waitUntilStarted();

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             JmsDemoConfiguration.class
                     )) {

            JmsTemplate template = context.getBean(JmsTemplate.class);
            SharedOrderListener listener =
                    context.getBean(SharedOrderListener.class);

            template.convertAndSend(
                    "orders.priority",
                    "priority:PO-158"
            );

            template.convertAndSend(
                    "orders.standard",
                    "standard:SO-158"
            );

            if (!listener.awaitMessages(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Listener did not receive both messages"
                );
            }

            System.out.println(
                    "priority.received=" + listener.getPriorityCount()
            );
            System.out.println(
                    "standard.received=" + listener.getStandardCount()
            );
        }
        finally {
            broker.stop();
            broker.waitUntilStopped();
        }
    }
}
~~~

Run from the directory containing pom.xml:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=demo.RepeatableJmsListenerDemo
~~~

The lines printed by the program, not counting the internal logs of the broker or framework:

~~~text
priority.received=1
standard.received=1
~~~

### 13.5. Analysis of the Result

JmsDemoConfiguration enables @EnableJms and provides a DefaultJmsListenerContainerFactory. Spring detects the two @JmsListener annotations on the same handleOrder method and registers two endpoints:

- priorityOrders receives from the Queue orders.priority.
- standardOrders receives from the Queue orders.standard.

The two endpoints share the listener bean SharedOrderListener but have separate containers. JmsTemplate sends two TextMessages with different payloads. The corresponding container receives each Message and calls the same handleOrder method.

The method distinguishes the payload type by the prefix priority: or standard:. AtomicInteger helps update the counters safely when the two endpoints call the method from different threads. CountDownLatch lets the main program wait until both Messages have been processed before printing the result.

The example demonstrates that two destinations can share one method. It does not mean the two Messages are processed on the same thread or in a global order.

## 14. Testing and Observing Multiple Endpoints

When there are multiple @JmsListener annotations on a method, you should test each endpoint independently and test the case where they run concurrently.

Points to confirm:

1. Each destination is registered correctly.
2. Each endpoint has a unique ID.
3. Messages from the first and second destinations both call the correct method.
4. Each endpoint's selector filters Messages correctly.
5. The converter can handle the payload of all destinations.
6. Concurrency does not cause a race condition in the listener bean.
7. Transactions and redelivery work correctly for each endpoint.
8. Durable subscriptions do not duplicate names or client identity.
9. The reply is sent to the expected destination if the method has a return value.
10. The registry can retrieve and manage each container by ID.

You can use the JmsListenerEndpointRegistry to check the state:

~~~java
MessageListenerContainer priorityContainer =
        registry.getListenerContainer("priorityOrders");

MessageListenerContainer standardContainer =
        registry.getListenerContainer("standardOrders");
~~~

The two containers can be started or stopped separately. This is useful when you need to pause one receiving flow while maintaining a destination or changing configuration.

You should log the endpoint ID or destination together with the message ID/correlation ID for tracing. If you only log the method name, it will be hard to tell which endpoint a Message came from when multiple annotations call the same method.

## 15. Common Mistakes

1. **Thinking @JmsListeners is a shared listener container:** it is a container annotation; Spring processes each @JmsListener inside it into a separate endpoint.
2. **Using @JmsListener multiple times but forgetting @EnableJms:** the annotation infrastructure is not enabled.
3. **No default container factory:** if the annotation does not specify containerFactory, Spring needs a default factory named jmsListenerContainerFactory or another default configuration.
4. **Using duplicate IDs:** each endpoint needs a unique ID so the registry manages them accurately.
5. **Believing concurrency=1 guarantees the method does not run in parallel:** multiple endpoints can still call the same method concurrently.
6. **Using non-thread-safe mutable fields:** a shared listener bean can be called from multiple containers and consumer threads.
7. **Assuming a Queue broadcasts to every listener:** a Queue uses the competing consumers model; a Message is received by one consumer.
8. **Assuming a Topic is like a Queue:** independent subscriptions can receive copies of the same publication.
9. **Sharing a durable subscription name:** durable endpoints need appropriate, non-conflicting subscription identities.
10. **Using the same method for incompatible payloads:** the converter or argument binding may fail when a destination sends a different Message type.
11. **Not distinguishing containerFactory:** Queue and Topic endpoints may need factories with different pubSubDomain or transaction settings.
12. **Setting a fixed @SendTo but expecting different reply destinations:** use JmsResponse or split the method when the reply destination depends on the endpoint.
13. **Expecting a common processing order across multiple destinations:** each endpoint and consumer has its own execution schedule.
14. **Using annotations for a destination list only known at runtime:** use JmsListenerConfigurer and JmsListenerEndpointRegistrar.
15. **Not monitoring individual endpoints:** when an error occurs, you need the ID/destination to identify which container has the problem.

## 16. Self-Check Questions

1. Why can @JmsListener appear multiple times on the same method?
2. What does @Repeatable(JmsListeners.class) mean?
3. Which container annotation does Java use to handle repeated annotations?
4. Does @JmsListeners directly create a single listener container?
5. What individual attributes can each @JmsListener declaration configure?
6. What is the role of @EnableJms?
7. If containerFactory is not specified, what default bean name does Spring look for?
8. Which component does the JmsListenerEndpointRegistry manage?
9. Why should each endpoint have its own ID?
10. Do two @JmsListener annotations reading the same Queue create a broadcast?
11. What is different when multiple endpoints register on the same Topic?
12. Why does a durable subscription need a separate name when multiple annotations share a method?
13. Does Concurrency=1 on each endpoint guarantee the method runs on only one thread?
14. When should you use an explicit @JmsListeners instead of direct repeated annotations?
15. When the destination list is only known at runtime, which API is more suitable?
16. If a method returns an object, where can Spring send the reply?
17. How do you test that both endpoints call the correct method?

## 17. Conclusion

@JmsListener is a repeatable annotation, allowing one method to receive Messages from multiple JMS destinations. Java stores the repeated declarations through the container annotation @JmsListeners; an application can also declare this container explicitly.

Spring processes each @JmsListener into a separate listener endpoint and creates a corresponding listener container. Each endpoint can have its own destination, ID, selector, concurrency, subscription, and containerFactory, while calling the same business method.

When designing, you need to distinguish Queue from Topic, manage IDs and durable subscriptions, ensure the method is thread-safe, and configure the transaction appropriately. If the destination list is only known at runtime, use the endpoint registration API instead of trying to create annotations dynamically.

## Official References

- Spring Framework 6.2 — Annotation-driven Listener Endpoints: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html
- Spring Framework 6.2 — Receiving a Message: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html
- Spring Framework 6.2 — Using Spring JMS: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html
- JmsListener API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/annotation/JmsListener.html
- JmsListeners API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/annotation/JmsListeners.html
- EnableJms API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/annotation/EnableJms.html
- JmsListenerEndpointRegistry API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistry.html
- Jakarta Messaging specification: https://jakarta.ee/specifications/messaging/
- Apache ActiveMQ Classic: https://activemq.apache.org/components/classic/
