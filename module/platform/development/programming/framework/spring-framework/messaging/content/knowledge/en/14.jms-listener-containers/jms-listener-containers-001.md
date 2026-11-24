# The Role of the Container in Registering, Receiving, and Invoking Listeners

In a JMS application, a listener is the component that performs business logic when a message arrives. A listener usually only needs to know how to process the payload, validate the data, and call business services. Connecting to the broker, registering the consumer, waiting for messages, managing the Session, acknowledgment, transactions, concurrency, and connection recovery belong to a different component: the **message listener container**.

Spring JMS provides a listener container that sits between the JMS provider and the application's listener. The container manages the message-receiving lifecycle, then invokes the listener in the exact context it has been configured with. When using annotations, the application declares an endpoint with @JmsListener; Spring creates a container from a JmsListenerContainerFactory and manages the container through the JmsListenerEndpointRegistry.

This lesson follows the entire path from listener registration to the moment a message is received and the business method is invoked. We will also distinguish the two main Spring implementations, understand transactions and acknowledgment, configure concurrency, handle errors, and build a runnable Java application with an Artemis broker.

## 1. What problem does the listener container solve?

If you write JMS yourself with the low-level API, the application has to perform many steps:

1. Obtain the ConnectionFactory.
2. Create the Connection and Session.
3. Look up or create the Queue/Topic.
4. Create the MessageConsumer.
5. Register a MessageListener or call receive() yourself.
6. Pass the message to the business code.
7. Manage acknowledgment or transactions.
8. Close the consumer, session, and connection when stopping.
9. Handle connection loss, restarts, and errors while receiving.

If every service performs these steps itself, business code gets mixed with infrastructure code. Changing concurrency, transactions, or the provider also becomes difficult.

The Spring listener container gathers that infrastructure into one place. The listener focuses only on the message it receives.

~~~text
                 Spring Application
                         |
              @EnableJms / endpoint scan
                         |
                    @JmsListener
                         |
              JmsListenerEndpointFactory
                         |
             JmsListenerContainerFactory
                         |
                         v
              MessageListenerContainer
                         |
              +----------+-----------+
              |                      |
         JMS Connection          JMS Destination
              |                  Queue / Topic
           Session                    ^
              |                      |
         MessageConsumer -------------+
              |
          Receive JMS Message
              |
       Message conversion
              |
        Listener adapter
              |
        Listener method
              |
        Business processing
~~~

The container is the component that coordinates message receiving. It is responsible for registering to receive messages, allocating and releasing resources, managing threads, participating in transactions, and routing errors to the corresponding handling mechanism.

## 2. Distinguishing the listener, endpoint, factory, and container

These names often appear together but have different roles:

| Component | Role |
|---|---|
| Listener method | The business method invoked when a message arrives |
| Listener endpoint | Describes where to receive from, which listener to invoke, and the properties of the receiving point |
| JmsListenerContainerFactory | Creates a container from an endpoint and applies the configuration |
| MessageListenerContainer | Manages consumers, receives messages, and invokes the listener |
| JmsListenerEndpointRegistry | Stores and manages the lifecycle of containers created from annotation endpoints |
| ConnectionFactory | Creates the JMS Connection to the provider |
| MessageConverter | Converts a JMS Message into a Java payload and vice versa |

Example:

~~~java
@JmsListener(destination = "orders.queue")
public void handleOrder(String payload) {
    // Handle the order's business logic.
}
~~~

The handleOrder method is the listener. The annotation describes an endpoint that receives from the orders.queue destination. The factory provides the container configuration. The container creates a consumer on the destination, receives the message, and then invokes this method through the listener adapter.

Do not treat JmsListenerContainerFactory as the running container. The factory is the object that creates containers; each registered endpoint gets its own container created from the factory.

## 3. How Spring registers listeners with annotations

To enable annotation-driven listeners, declare @EnableJms on a Spring configuration class:

~~~java
@Configuration
@EnableJms
public class JmsConfiguration {
}
~~~

Spring registers the infrastructure that detects @JmsListener methods on beans managed in the ApplicationContext.

A listener:

~~~java
@Component
public class OrderListener {

    @JmsListener(destination = "orders.queue")
    public void receive(String payload) {
        System.out.println("Received: " + payload);
    }
}
~~~

When the ApplicationContext initializes:

1. Spring detects the OrderListener bean.
2. The JMS infrastructure finds the method annotated with @JmsListener.
3. Spring creates metadata for the endpoint, including the destination, the listener method, and the annotation's properties.
4. The endpoint is registered with the JmsListenerEndpointRegistrar.
5. The registrar asks the JmsListenerContainerFactory to create a container for the endpoint.
6. The JmsListenerEndpointRegistry manages the created container.
7. The container starts according to the application's lifecycle and begins receiving messages.

Each @JmsListener method is an endpoint. If a class has three listener methods, Spring usually creates three independent containers, each receiving the configuration and destination of the corresponding endpoint.

You can specify a dedicated factory on the annotation:

~~~java
@JmsListener(
        destination = "orders.queue",
        containerFactory = "ordersListenerFactory"
)
public void receiveOrder(String payload) {
    // Handle the order.
}
~~~

If containerFactory is not specified, Spring looks for the bean with the default name jmsListenerContainerFactory. Therefore, the factory bean's name must be consistent with the annotation or the default configuration.

## 4. JmsListenerContainerFactory and container configuration

The factory is where you configure properties shared by endpoints:

- The ConnectionFactory used to connect to the provider.
- The type of container to create.
- The destination resolver.
- Transactions and acknowledgment.
- The number of concurrent consumers.
- The ErrorHandler.
- The recovery interval and lifecycle settings.
- The MessageConverter and related adapters.

Example DefaultJmsListenerContainerFactory configuration:

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
        factory.setConcurrency("2-5");

        return factory;
    }
}
~~~

In this example:

- The ConnectionFactory provides the connection to the JMS provider.
- sessionTransacted enables a local transaction on the JMS Session.
- concurrency sets the minimum number of consumers to 2 and the maximum to 5 for the DefaultMessageListenerContainer.

A factory can be used by multiple endpoints. Each endpoint still has its own container, but the containers can share configuration such as the ConnectionFactory, transactions, and concurrency.

If two groups of listeners need different policies, create two factories with distinct names:

~~~java
@Bean
public DefaultJmsListenerContainerFactory auditListenerFactory(
        ConnectionFactory connectionFactory) {

    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setSessionTransacted(true);
    factory.setConcurrency("1");

    return factory;
}

@Bean
public DefaultJmsListenerContainerFactory workerListenerFactory(
        ConnectionFactory connectionFactory) {

    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setSessionTransacted(true);
    factory.setConcurrency("3-8");

    return factory;
}
~~~

The audit listener has one consumer to keep the processing order predictable. The worker listener can increase the number of consumers as load grows if it uses the DefaultMessageListenerContainer and receives from a queue.

## 5. The two main container implementations

Spring provides two standard implementations:

- SimpleMessageListenerContainer (SMLC).
- DefaultMessageListenerContainer (DMLC).

Both receive messages and invoke the listener, but they differ in how they receive messages and in their ability to manage load.

| Characteristic | SimpleMessageListenerContainer | DefaultMessageListenerContainer |
|---|---|---|
| Receiving method | Registers a callback with MessageConsumer.setMessageListener() | A loop calling MessageConsumer.receive() |
| Number of consumers | Fixed at initialization | Can be fixed or dynamically increased/decreased |
| Broker recovery | Has an error-handling mechanism but is less flexible | Recovers automatically when the broker is temporarily unavailable |
| External transaction manager | Not fully supported | Supported |
| Native JMS transaction | Yes | Yes |
| Concurrency configuration | Fixed number of consumers | Supports min/max |
| Goal | Simple configuration, few runtime requirements | Applications that need recovery and flexible control |

### 5.1. SimpleMessageListenerContainer

SMLC creates a fixed number of Sessions and MessageConsumers at startup. It registers the listener through the JMS API:

~~~java
consumer.setMessageListener(messageListener);
~~~

After that, the JMS provider invokes the callback when a message arrives.

Characteristics:

- Relatively simple configuration.
- The number of consumers created is fixed.
- Does not automatically increase or decrease the number of consumers according to load.
- Supports native JMS transactions through sessionTransacted.
- Does not support participating in an external transaction manager the way DMLC does.
- Message-receiving behavior depends on the provider's callback.

SMLC suits cases that need a simple listener container and where the provider has a stable callback capability. You need to check compatibility with the limits of the application server and the Jakarta EE runtime.

Do not enable a TaskExecutor to run listeners concurrently without understanding the impact on acknowledgment. With SMLC, if the listener is executed on a different executor, the message may be acknowledged before the listener runs and the Session may be reused. That combination is not suitable with sessionTransacted or CLIENT_ACKNOWLEDGE.

### 5.2. DefaultMessageListenerContainer

DMLC uses a loop that calls MessageConsumer.receive() to fetch messages. Spring manages the asynchronous receiving tasks through a TaskExecutor.

Characteristics:

- Can start a fixed number of consumers.
- Can be configured with min/max consumers to scale up and down automatically according to load.
- Has a self-recovery mechanism when the broker is temporarily unavailable.
- Supports native JMS transactions.
- Supports an external transaction manager such as JTA.
- Manages re-acquiring the Connection, Session, and MessageConsumer when needed.
- Allows stopping, restarting, and changing configuration while the application is running.

DMLC is usually the appropriate default choice for Spring JMS applications that need recoverability and concurrency management.

Example of setting concurrency limits:

~~~java
factory.setConcurrency("2-8");
~~~

The container maintains at least two consumers and can grow to at most eight consumers as load increases. When load decreases, it can shrink back to the base level.

With a queue, multiple consumers can share the messages. When you increase consumers, the overall processing order may change because multiple messages are processed at the same time.

With a Topic, do not increase consumers casually. In a typical configuration, multiple consumers on the same node may receive copies of the same message. If you need to share load on a Topic, design a shared subscription and check provider support.

## 6. The path of a message from the broker to the listener

Once the container is running, the process of receiving a message usually goes as follows:

**Step 1 — Open JMS resources**

The container uses the ConnectionFactory to obtain a Connection, create a Session, and register a MessageConsumer with the destination. Depending on the container and the cache level, resources may be reused throughout the consumer's lifecycle.

**Step 2 — Wait for a message**

DMLC calls receive() in invoker tasks. SMLC registers a callback for the provider to invoke when a message arrives.

**Step 3 — Receive the JMS Message**

The provider delivers a JMS Message to the container. The message can be a TextMessage, BytesMessage, MapMessage, ObjectMessage, or another message type.

**Step 4 — Convert the message**

If the endpoint is a @JmsListener method that accepts a String or DTO, Spring uses a MessageConverter to convert the payload to a Java type. If the listener directly accepts jakarta.jms.Message, it can access the original JMS properties.

**Step 5 — Invoke the listener**

The Spring adapter prepares the method arguments, maps the payload, headers, and annotated parameters, and then invokes the listener method.

**Step 6 — Complete the transaction/acknowledgment**

After the listener finishes running, the container performs a commit or acknowledgment according to the configuration. If the listener throws an exception within a JMS transaction, the container may roll back so that the provider redelivers the message.

**Step 7 — Continue receiving**

The consumer continues waiting for the next message until the container stops or needs to recreate resources.

~~~text
Broker
  |
  | JMS Message
  v
MessageConsumer
  |
  v
Listener Container
  |
  | receive the message via receive() or callback
  v
Message conversion / listener adapter
  |
  v
@JmsListener method
  |
  | business processing
  v
Transaction / acknowledgment
  |
  +---- commit ----> Broker acknowledges
  |
  +---- rollback --> Broker may redeliver
~~~

The container performs the coordination. The listener method is still where the application decides whether the business operation succeeded or failed.

## 7. How the listener receives data and headers

Spring supports many parameter types for @JmsListener methods.

Receiving a String payload:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(String payload) {
    System.out.println(payload);
}
~~~

Receiving a DTO:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(OrderCreated event) {
    System.out.println(event.orderId());
}
~~~

Receiving a Spring Message:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(
        org.springframework.messaging.Message<OrderCreated> message) {

    System.out.println(message.getPayload().orderId());
    System.out.println(message.getHeaders());
}
~~~

Receiving the original JMS Message:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(jakarta.jms.Message message) throws JMSException {
    System.out.println(message.getJMSMessageID());
    System.out.println(message.getJMSRedelivered());
}
~~~

Getting a header or property:

~~~java
@JmsListener(destination = "orders.queue")
public void receive(
        String payload,
        @Header("eventType") String eventType,
        @Header(name = "priority", required = false) Integer priority) {

    System.out.println(eventType + ": " + payload);
    System.out.println("priority = " + priority);
}
~~~

Spring can map JMS properties and headers to listener parameters. The conversion type depends on the MessageConverter and the configured converters. If a property does not exist, a required parameter may by default cause a mapping error; use required=false or an appropriate default value when the property is optional.

For a DTO payload, you need to configure a corresponding converter, such as a JSON MessageConverter. Do not assume that every JMS provider understands an arbitrary Java object on its own.

## 8. MessageListener, MessageListenerAdapter, and @JmsListener

There are three common ways to connect messages to application code.

### Implementing MessageListener directly

~~~java
public class OrderMessageListener implements MessageListener {

    @Override
    public void onMessage(Message message) {
        System.out.println("Received a JMS message");
    }
}
~~~

Then attach the listener to the container using setMessageListener(). This approach is close to the JMS API and suits cases where you need to work directly with the Message.

### Using MessageListenerAdapter

MessageListenerAdapter lets you delegate processing to a POJO method. It converts the payload and invokes the delegate method according to the configuration.

~~~java
@Bean
public MessageListenerAdapter orderAdapter(OrderDelegate delegate) {
    MessageListenerAdapter adapter =
            new MessageListenerAdapter(delegate);

    adapter.setDefaultListenerMethod("handleOrder");
    return adapter;
}
~~~

~~~java
public class OrderDelegate {

    public void handleOrder(String payload) {
        System.out.println("Order: " + payload);
    }
}
~~~

This approach is useful when you want to reuse a POJO and decouple it from the JMS API.

### Using @JmsListener

~~~java
@Component
public class OrderListener {

    @JmsListener(destination = "orders.queue")
    public void handleOrder(String payload) {
        System.out.println("Order: " + payload);
    }
}
~~~

The annotation is the most concise way to declare an endpoint. Spring automatically registers the endpoint, creates the container, and connects the listener method to the message adapter.

## 9. Transactions and acknowledgment in the listener container

Receiving a message does not mean the business operation has completed. The container needs to determine when the provider is allowed to consider the message processed.

Common modes:

| Configuration | Meaning |
|---|---|
| AUTO_ACKNOWLEDGE | The provider/container acknowledges automatically according to the container's semantics |
| CLIENT_ACKNOWLEDGE | Acknowledgment is controlled by the client/container side |
| DUPS_OK_ACKNOWLEDGE | Allows batched acknowledgment and duplicates may occur |
| sessionTransacted=true | Receives messages within a JMS Session transaction |

Pay special attention: AUTO_ACKNOWLEDGE has different semantics between DMLC and SMLC. With DMLC, acknowledgment by default happens before the listener executes, so an exception from the listener does not cause the message to be redelivered. With SMLC, acknowledgment happens after the listener invocation, but a business exception still does not guarantee redelivery in every situation.

If you need reliability and want a listener exception to cause the message to be redelivered, Spring recommends using sessionTransacted=true or an appropriate external transaction manager.

Example:

~~~java
factory.setSessionTransacted(true);
~~~

When the listener completes normally, the container commits the transaction. If the listener throws an exception, the container rolls back; the provider may redeliver the message according to the broker's redelivery policy.

### JMS and database transactions

If the listener both updates a database and processes a JMS message, a local JMS transaction does not automatically include the database transaction.

An example of what can happen:

1. The database commit succeeds.
2. The JMS commit fails.
3. The broker redelivers the message.
4. The listener updates the database again.

Therefore, idempotency or duplicate detection is needed. If you need an atomic transaction across multiple resources, you can use XA/JTA when the provider, database, and transaction manager support it. XA has higher cost and operational requirements, so choose it according to the consistency requirements.

## 10. Exception handling and ErrorHandler

By default, the listener container usually catches exceptions from the listener and logs them at WARN level. The exception is not necessarily propagated back to the JMS provider as a signal that the listener failed.

You can configure an ErrorHandler to write structured logs, emit metrics, or forward errors to a monitoring system:

~~~java
factory.setErrorHandler(error ->
        System.err.println("[listener-error] " + error.getMessage()));
~~~

The ErrorHandler observes errors that occur in the listener container. It does not replace transaction rollback, acknowledgment, or the broker's dead-letter policy.

It is important to distinguish:

- Business errors: for example, an invalid order. These can be a legitimate rejection result and do not necessarily need a retry.
- Transient errors: for example, the database being temporarily unreachable. You can roll back to retry according to the policy.
- Configuration errors: for example, a nonexistent destination or wrong credentials. Continuous retries may only generate logs and unnecessary load.
- JMS connection errors: the container can recover through its own recovery mechanism.

Determine which errors need a rollback, which need to be routed to a dead-letter queue, and which need the listener to be stopped so the configuration can be fixed.

## 11. Concurrency and processing order

Concurrency is the number of consumers active at the same time on an endpoint.

With DMLC:

~~~java
factory.setConcurrency("2-8");
~~~

- 2 is the minimum number of consumers.
- 8 is the maximum number of consumers.
- The container can increase consumers when load increases and decrease them when load decreases.

With SMLC, the number of consumers is fixed:

~~~java
factory.setConcurrency("3");
~~~

Although the configuration API may accept a lower-upper string for compatibility, SMLC keeps the number of consumers fixed and does not scale dynamically. It is usually better to use setConcurrentConsumers() when configuring SMLC directly.

Increasing consumers can increase queue throughput, but it has these effects:

- The overall processing order is no longer guaranteed when multiple messages run in parallel.
- The downstream database/API must be able to handle many concurrent tasks.
- The number of Sessions and consumers increases, which increases broker resource usage.
- Retries may cause a message to be reprocessed in parallel with other messages.
- With a Topic, multiple independent consumers may receive copies of the same message.

If you need ordering by a business key, you can partition the destination or design a mechanism that serializes by key. Setting concurrency to 1 alone does not solve ordering across multiple producers or multiple destinations, but it helps simplify ordering within a single consumer.

## 12. Container lifecycle management and monitoring

Containers created by @JmsListener are managed by the JmsListenerEndpointRegistry. The registry implements the Spring lifecycle, so it can start and stop containers according to the ApplicationContext lifecycle.

You can access the registry to manage them:

~~~java
@Component
public class ListenerLifecycleManager {

    private final JmsListenerEndpointRegistry registry;

    public ListenerLifecycleManager(JmsListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void stopOrderListener() {
        MessageListenerContainer container =
                registry.getListenerContainer("orderListener");

        if (container != null) {
            container.stop();
        }
    }

    public void startOrderListener() {
        MessageListenerContainer container =
                registry.getListenerContainer("orderListener");

        if (container != null) {
            container.start();
        }
    }
}
~~~

To find a container by ID, declare an id on the annotation:

~~~java
@JmsListener(
        id = "orderListener",
        destination = "orders.queue"
)
public void handle(String payload) {
    // processing
}
~~~

Containers managed by the registry are not separate beans in the ApplicationContext and cannot be autowired directly like an ordinary bean. Use the registry to find and control them.

Useful properties:

- autoStartup: whether to automatically start the endpoint when the context starts.
- phase: the relative lifecycle order when starting and stopping.
- concurrency: the number of consumers.
- recoveryInterval: the interval for attempting recovery when the connection fails.
- shutdownTimeout: the wait time when stopping the container in configurations that support it.

In operations, you should monitor the number of active consumers, queue depth, message age, processing time, number of redeliveries, listener errors, connection errors, and recovery time.

## 13. Manual configuration without @JmsListener

You can create the container directly with Java config:

~~~java
@Bean
public DefaultMessageListenerContainer orderContainer(
        ConnectionFactory connectionFactory,
        OrderMessageListener listener) {

    DefaultMessageListenerContainer container =
            new DefaultMessageListenerContainer();

    container.setConnectionFactory(connectionFactory);
    container.setDestinationName("orders.queue");
    container.setMessageListener(listener);
    container.setSessionTransacted(true);
    container.setConcurrentConsumers(2);

    return container;
}
~~~

This approach suits cases where you need to create endpoints dynamically, need special configuration, or want to declare the container explicitly. Spring manages the lifecycle of the container bean and calls start/stop according to the configuration.

If you only need an ordinary listener method, @JmsListener usually has less boilerplate. Both approaches rely on the same MessageListenerContainer abstraction.

## 14. Complete example: @JmsListener with Artemis and DMLC

The example below creates a Spring ApplicationContext, registers a listener with @JmsListener, sends a message through JmsTemplate, and waits for the listener to process it. Spring uses DefaultJmsListenerContainerFactory to create the DMLC.

The program uses Java 17, Spring Framework 6.2.19, and the Artemis Jakarta JMS client 2.40.0. It needs a running Artemis broker with a queue named orders.queue and appropriate credentials. The example does not start the broker itself.

Project structure:

~~~text
listener-container-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                ├── JmsConfiguration.java
                ├── OrderListener.java
                └── ListenerContainerDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>listener-container-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>jakarta.jms</groupId>
            <artifactId>jakarta.jms-api</artifactId>
            <version>3.1.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-client</artifactId>
            <version>2.40.0</version>
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

### src/main/java/demo/JmsConfiguration.java

~~~java
package demo;

import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;

@Configuration
@EnableJms
public class JmsConfiguration {

    @Bean(destroyMethod = "close")
    public ActiveMQConnectionFactory connectionFactory() {
        String url = System.getenv().getOrDefault(
                "JMS_BROKER_URL", "tcp://localhost:61616");

        String user = System.getenv("JMS_BROKER_USER");
        String password = System.getenv("JMS_BROKER_PASSWORD");

        if (user != null && password != null) {
            return new ActiveMQConnectionFactory(url, user, password);
        }

        return new ActiveMQConnectionFactory(url);
    }

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ActiveMQConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1-3");

        return factory;
    }

    @Bean
    public JmsTemplate jmsTemplate(
            ActiveMQConnectionFactory connectionFactory) {

        return new JmsTemplate(connectionFactory);
    }

    @Bean
    public OrderListener orderListener() {
        return new OrderListener();
    }
}
~~~

### src/main/java/demo/OrderListener.java

~~~java
package demo;

import org.springframework.jms.annotation.JmsListener;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class OrderListener {

    private final CountDownLatch received = new CountDownLatch(1);

    @JmsListener(
            id = "ordersListener",
            destination = "orders.queue"
    )
    public void handle(String payload) {
        System.out.println("[listener] received = " + payload);
        received.countDown();
    }

    public boolean awaitMessage(long timeout, TimeUnit unit)
            throws InterruptedException {
        return received.await(timeout, unit);
    }
}
~~~

### src/main/java/demo/ListenerContainerDemo.java

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.jms.core.JmsTemplate;

import java.util.concurrent.TimeUnit;

public class ListenerContainerDemo {

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             JmsConfiguration.class)) {

            JmsTemplate jmsTemplate = context.getBean(JmsTemplate.class);
            OrderListener listener = context.getBean(OrderListener.class);

            jmsTemplate.convertAndSend(
                    "orders.queue",
                    "Order #1024 created"
            );

            if (!listener.awaitMessage(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Timed out waiting for the listener");
            }

            System.out.println("[main] listener completed");
        }
    }
}
~~~

Run in the directory containing pom.xml:

~~~shell
mvn -q compile exec:java -Dexec.mainClass=demo.ListenerContainerDemo
~~~

If the broker is running at localhost:61616, the queue already exists, and no separate credentials are required, the expected output is:

~~~text
[listener] received = Order #1024 created
[main] listener completed
~~~

If the broker requires login, set the environment variables before running. Example in PowerShell:

~~~powershell
$env:JMS_BROKER_URL = "tcp://localhost:61616"
$env:JMS_BROKER_USER = "your-user"
$env:JMS_BROKER_PASSWORD = "your-password"
mvn -q compile exec:java -Dexec.mainClass=demo.ListenerContainerDemo
~~~

### Analysis of the example

1. JmsConfiguration enables @EnableJms so that Spring detects listener endpoints.
2. The ConnectionFactory creates the connection to the Artemis broker.
3. jmsListenerContainerFactory provides the configuration for the DMLC: a JMS transaction and concurrency from 1 to 3.
4. OrderListener has @JmsListener, so it is registered as an endpoint.
5. The JmsListenerEndpointRegistry creates and manages the container for this endpoint.
6. The container creates a consumer on orders.queue and waits for messages.
7. JmsTemplate sends a string to the queue.
8. The container receives a JMS TextMessage, converts the payload to a String, and invokes OrderListener.handle().
9. The listener prints the payload and then decrements the CountDownLatch.
10. The main thread receives the signal and prints the completion message.
11. When the ApplicationContext closes, the registry stops the listener containers and Spring closes the beans according to the lifecycle.

The example uses sessionTransacted=true. If the listener throws an exception, the container rolls back the JMS transaction and the broker may redeliver the message. In the success case, the transaction is committed after the listener completes.

The example requires a real broker to verify the transport path. If you only run Maven compile, you have only confirmed that the dependencies and source code compile; an integration test with the broker is needed to confirm the connection, access permissions, queue, and transactions.

## 15. Common mistakes

**Forgetting @EnableJms:** Spring does not activate the infrastructure that detects @JmsListener, so the listener method is not registered.

**The listener bean is not in the ApplicationContext:** the annotation is only detected on Spring-managed beans. Creating the listener with new in code does not register the endpoint automatically.

**Missing container factory:** if you do not declare containerFactory on the annotation, Spring looks for the default bean jmsListenerContainerFactory. A wrong bean name can cause the ApplicationContext to fail to initialize.

**Wrong or nonexistent destination:** the provider may refuse to create the consumer or to send messages. Check the queue/topic and the broker's auto-create policy.

**Confusing queue and topic:** the default factory uses the queue domain. If you receive from a Topic, configure pubSubDomain=true or an appropriate dedicated factory.

**Increasing concurrency without considering ordering:** multiple consumers can process in parallel and finish in an order different from the sending order.

**Increasing consumers on a Topic without a shared subscription:** each consumer may receive its own copy. Check the subscription mode and the provider's capabilities before increasing concurrency.

**Relying on AUTO_ACKNOWLEDGE to guarantee redelivery:** the semantics differ between DMLC and SMLC. Use sessionTransacted=true or an external transaction manager when you need consistent rollback behavior.

**Assuming a listener exception always makes the broker resend the message:** the exception may only be logged or forwarded to the ErrorHandler. Redelivery depends on the transaction, acknowledgment, and broker policy.

**Confusing the listener container with JmsTemplate:** JmsTemplate serves synchronous send/receive operations; the listener container manages asynchronous message receiving and invokes the listener.

**Not stopping the container in line with the lifecycle:** the container holds the Connection, Session, and consumers. Let Spring manage the lifecycle, or call stop/destroy if you create it manually.

**Ignoring duplicate processing:** a message may be redelivered after a rollback, a connection loss, or an error at commit time. The listener should be idempotent or have a mechanism to detect duplicate processing.

## 16. Listener design and operations checklist

- The ConnectionFactory points to the correct JMS provider and broker.
- The Queue/Topic and destination resolver are configured.
- @EnableJms is enabled and the listener is a Spring-managed bean.
- Each endpoint uses the correct container factory.
- The container type is chosen according to recovery, transaction, and concurrency requirements.
- The number of consumers fits the load and the broker's limits.
- The MessageConverter converts the payload and headers correctly.
- Transactions and acknowledgment have a clear policy.
- The ErrorHandler, retry, redelivery, and dead-letter policy have been tested.
- The listener handles messages idempotently if a message may be redelivered.
- The registry and containers are stopped in line with the lifecycle.
- Metrics track consumer count, queue depth, message age, processing time, and recovery.
- Integration tests run with a provider/broker compatible with the deployment environment.

## 17. Key takeaways

- The listener is business code; the listener container manages connecting, registering consumers, receiving messages, and invoking the listener.
- @JmsListener declares an endpoint on a Spring-managed bean; @EnableJms enables the infrastructure that detects annotations.
- JmsListenerContainerFactory creates containers according to the configuration for each endpoint.
- JmsListenerEndpointRegistry manages the lifecycle and allows finding a container by endpoint ID.
- SimpleMessageListenerContainer uses the JMS provider's callback and keeps the number of consumers fixed.
- DefaultMessageListenerContainer uses a receive() loop, has recovery, and supports dynamic concurrency together with an external transaction manager.
- Messages are converted through the MessageConverter before entering the listener method if the method accepts a Java payload.
- sessionTransacted=true enables rollback when the listener fails and supports redelivery according to the broker policy.
- Increasing concurrency can increase queue throughput but affects ordering; with a Topic, you must consider the subscription and the ability to receive copies.
- The container does not guarantee business-level exactly-once; the listener must tolerate redelivery and handle duplicates.

## References

- [Spring Framework 6.2 — Annotation-driven JMS listener endpoints](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html)
- [Spring Framework 6.2 — Receiving a Message](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html)
- [Spring Framework 6.2 — Using Spring JMS and listener containers](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html)
- [DefaultMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)
- [SimpleMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/SimpleMessageListenerContainer.html)
- [JmsListenerEndpointRegistry Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistry.html)
- [AbstractMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html)
