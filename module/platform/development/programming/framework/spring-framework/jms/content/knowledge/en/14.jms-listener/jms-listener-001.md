# Enabling Endpoint Infrastructure with @EnableJms

**Topic:** Spring Framework - jms → @JmsListener

## 1. Why Writing @JmsListener Alone Is Not Enough

In Spring JMS, a method annotated with `@JmsListener` can act as an asynchronous consumer:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class OrderConsumer {

    @JmsListener(destination = "orders.incoming")
    public void consume(String orderId) {
        System.out.println("RECEIVED=" + orderId);
    }
}
~~~

However, an annotation on a method **does not automatically connect to a broker**, does not automatically create message-receiving threads, and does not automatically register a consumer if the application lacks annotation-driven JMS infrastructure. Spring needs components that detect methods, build endpoints, create message listener containers, and manage the container lifecycle.

For **plain Spring Framework**, the way to enable that mechanism is to place `@EnableJms` on a configuration class:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;

@Configuration
@EnableJms
public class JmsInfrastructureConfig {
    // Required JMS beans are provided here or elsewhere.
}
~~~

This is a **configuration snippet**; for the listener to actually run, you still need a `ConnectionFactory`, at least one suitable `JmsListenerContainerFactory`, a bean containing the `@JmsListener` method, and an available JMS provider/broker.

**Important distinction with Spring Boot:** When using Spring Boot 3.x with a JMS starter and matching auto-configuration conditions, Boot **automatically enables/registers support for `@JmsListener`**, so normally **you do not need to write `@EnableJms` yourself**. Adding `@EnableJms` to illustrate the Framework mechanism is valid, but it does not mean every Boot application lacking this annotation will fail to receive messages.

This lesson uses Java 17+, Spring Framework 6.x / Spring Boot 3.x, and the Jakarta Messaging `jakarta.jms.*` namespace. Older Spring 5/JMS projects may still use `javax.jms.*`; you must use compatible APIs and provider clients and never mix the two generations.

## 2. Which Components Does @EnableJms Actually Activate?

`org.springframework.jms.annotation.EnableJms` is a Spring configuration annotation. It imports internal infrastructure through `JmsBootstrapConfiguration`, registering the components needed to discover listener endpoints.

Conceptual flow:

~~~text
         @Configuration + @EnableJms
                       |
                       v
             JmsBootstrapConfiguration
                       |
             +---------+----------+
             |                    |
             v                    v
  JmsListenerAnnotation      JmsListenerEndpointRegistry
  BeanPostProcessor
             |
     finds @JmsListener on
      Spring-managed beans
             |
             v
      JmsListenerEndpoint
             |
      JmsListenerEndpointRegistrar
             |
             v
     JmsListenerContainerFactory
             |
             v
      MessageListenerContainer
             |
             v
        JMS ConnectionFactory
             |
             v
       Queue / Topic on broker
             |
             v
      @JmsListener method
~~~

Each component has a distinct responsibility:

| Component | Role |
| --- | --- |
| `@EnableJms` | Enables processing of JMS listener annotations in Spring Framework |
| `JmsListenerAnnotationBeanPostProcessor` | Detects methods annotated with `@JmsListener` on Spring-managed beans |
| `JmsListenerEndpoint` | Describes the discovered listener endpoint (destination, ID, selector...) |
| `JmsListenerEndpointRegistrar` | Registers the endpoint with the appropriate factory/registry |
| `JmsListenerContainerFactory` | Creates a message listener container according to configuration |
| `DefaultJmsListenerContainerFactory` | Common factory that creates containers for asynchronous JMS receiving |
| `JmsListenerEndpointRegistry` | Stores and manages the lifecycle of containers attached to annotated endpoints |
| `ConnectionFactory` | Provides JMS connections/sessions to the provider |
| `MessageListenerContainer` | Performs the work of receiving messages and invoking the listener method |

**@EnableJms is not a broker launcher.** It does not replace `ConnectionFactory`, does not supply credentials, does not provision queues/topics, and does not guarantee messages are available. It only makes Spring understand and register properly annotated endpoints.

### 2.1. Why Is the Endpoint Registry Needed?

Containers created for `@JmsListener` are usually **not registered as ordinary individual beans in the ApplicationContext**. Instead, `JmsListenerEndpointRegistry` manages those containers, providing lookup by endpoint ID and lifecycle control.

Therefore, not finding a bean named `ordersListener` of type `DefaultMessageListenerContainer` **does not prove** that the listener is not working. Check `JmsListenerEndpointRegistry` or the metrics/logs of the listener container.

### 2.2. What Happens When the Application Starts?

A typical sequence:

1. Spring loads `@Configuration` and bean definitions.
2. `@EnableJms` registers the JMS annotation infrastructure.
3. Spring instantiates beans from component scan; the post-processor searches for `@JmsListener` on eligible beans.
4. For each annotation, Spring creates an endpoint definition.
5. The registrar finds a matching `JmsListenerContainerFactory`, creates the listener container, and places it in the registry.
6. When the context finishes starting and the container is started according to lifecycle, the container opens JMS resources to consume messages.
7. Each message matching the destination/selector is dispatched to the handler method.

Steps 4–6 may differ in initialization/lifecycle ordering details depending on the Spring version and factory. Do not rely on a fixed log order to claim a method has received a message without verifying the actual broker/consumer.

## 3. How to Enable It in Plain Spring Framework (Without Boot)

For a Spring Framework application using Java Config, the clearest way is:

~~~java
package com.example.config;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
@ComponentScan(basePackages = "com.example")
public class JmsInfrastructureConfig {

    @Bean
    public DefaultJmsListenerContainerFactory
            jmsListenerContainerFactory(
                    ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1-3");
        return factory;
    }
}
~~~

This is **compilable Java Config** when Spring Framework 6.x + Spring JMS/Jakarta Messaging dependencies are present, but it is **not yet a standalone runnable application**: it needs a `jakarta.jms.ConnectionFactory` bean from the JMS provider and a properly configured broker. `@ComponentScan` must point to the package containing the listener beans.

Notice the bean name created from the method:

~~~java
@Bean
public DefaultJmsListenerContainerFactory
        jmsListenerContainerFactory(ConnectionFactory factory) {
    // ...
}
~~~

The bean has the default name **`jmsListenerContainerFactory`**. That is the default name the infrastructure looks for when a `@JmsListener` does not explicitly specify `containerFactory`.

### 3.1. Why Must There Be a JmsListenerContainerFactory?

A `@JmsListener(destination = "orders.incoming")` only provides the endpoint description. The factory decides **how to create the consumer**, including the ConnectionFactory, queue/topic domain, concurrency, transaction, converter, error handling, and appropriate recovery policy.

If a plain Spring Framework configuration only has `@EnableJms` and `@JmsListener`, but **has no default factory** or corresponding custom factory, Spring may fail during endpoint initialization because it cannot find the `jmsListenerContainerFactory` bean.

Solution: declare the default factory with the exact name, or select a custom factory via the annotation or `JmsListenerConfigurer`.

### 3.2. @EnableJms Is Not the Same as @ComponentScan

The two annotations do two different things:

- `@ComponentScan` finds classes such as `@Component` and registers them as **Spring beans**.
- `@EnableJms` enables the processor that detects `@JmsListener` **on beans already managed by Spring**.

If an object is created with `new OrderConsumer()` without becoming a Spring bean, Spring does not automatically process `@JmsListener` on that instance, even if `@EnableJms` is enabled.

A listener can be declared via `@Component`, `@Service`, or through a `@Bean` method; the decisive point is that **the bean exists in the context** and the processor can see the annotation on the appropriate method.

## 4. Spring Boot 3.x: When You Do Not Need to Add @EnableJms Yourself

Spring Boot provides auto-configuration for JMS when the appropriate dependency/provider is present, including `ConnectionFactory`, `JmsTemplate`, and listener infrastructure. According to official Spring documentation, Boot **automatically detects `@JmsListener` methods** when valid JMS infrastructure is present: adding `@EnableJms` is not required in a typical Boot configuration.

Comparison:

| Aspect | Plain Spring Framework | Spring Boot with JMS starter |
| --- | --- | --- |
| Enabling `@JmsListener` | Usually must add `@EnableJms` | Boot usually enables it automatically |
| `ConnectionFactory` | Provided by application/container | Boot can auto-configure if conditions are met |
| `jmsListenerContainerFactory` | Usually declared explicitly | Boot can auto-configure |
| Bean scan | Must be configured | `@SpringBootApplication` includes component scan |
| Connection to broker | Configured manually | Uses provider properties/autoconfig |
| Auto-creates physical queue? | Not by default | Boot properties also do not guarantee broker auto-provisioning |

Therefore, in a Boot application, both of the following forms are valid:

~~~java
@SpringBootApplication
public class BootJmsApplication {
    public static void main(String[] args) {
        SpringApplication.run(BootJmsApplication.class, args);
    }
}
~~~

and:

~~~java
@SpringBootApplication
@EnableJms
public class BootJmsApplication {
    public static void main(String[] args) {
        SpringApplication.run(BootJmsApplication.class, args);
    }
}
~~~

**These are two alternative options**, not two classes with the same name placed together in one source file. In normal Boot, the first approach is sufficient if JMS support is auto-configured. The second approach explicitly shows the intent to enable Framework JMS annotation support and is suitable for learning the mechanism. There is no need to place duplicate `@EnableJms` annotations in multiple places just because there are many listeners.

### 4.1. Boot Dependencies and Configuration to Check

With Artemis, the typical dependency is:

~~~text
org.springframework.boot:spring-boot-starter-artemis
~~~

In addition to the Spring JMS dependency, the runtime needs the provider client, valid broker URL/credentials, and permissions to access the queue/topic. You can use Spring Initializr to generate a Maven project with aligned Spring Boot versions instead of randomly mixing versions of Spring JMS, Artemis, and Jakarta JMS.

Example connection configuration:

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=${ARTEMIS_USER}
spring.artemis.password=${ARTEMIS_PASSWORD}
spring.jms.pub-sub-domain=false
~~~

`mode=native` connects to an **external Artemis broker running outside the application**; it does not start an embedded broker. `spring.jms.pub-sub-domain=false` uses queue semantics in the example. If the application needs topics, the producer and listener container must share matching domain/destination configuration.

## 5. Runnable Example: Spring Boot + @EnableJms + @JmsListener

This example intentionally places `@EnableJms` to demonstrate the exact focus of the lesson, even though a Boot application with full auto-configuration usually works without that annotation.

### 5.1. Preparation

Create a project on [Spring Initializr](https://start.spring.io/):

- Java **17+**, Spring Boot **3.x**, Maven build system.
- Group `com.example`, artifact `jms-enable-demo`.
- Dependency **Spring for Apache ActiveMQ Artemis** (Maven `org.springframework.boot:spring-boot-starter-artemis`).
- An Artemis broker running at `tcp://localhost:61616`.
- A broker account permitted to connect, send to, and consume from queue `demo.jms.orders`.
- Queue `demo.jms.orders` already provisioned or the broker allows appropriate auto-creation.

Provide the environment variables `ARTEMIS_USER` and `ARTEMIS_PASSWORD` according to your broker. Do not commit real credentials to source control.

Create `src/main/resources/application.properties`:

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=${ARTEMIS_USER}
spring.artemis.password=${ARTEMIS_PASSWORD}

spring.jms.pub-sub-domain=false
~~~

With a native broker, Spring Boot **does not create** the Artemis server. Starting the broker, creating addresses/queues, and configuring security lie outside the Spring code of this example.

Create `src/main/java/com/example/EnableJmsDemoApplication.java`:

~~~java
package com.example;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableJms
public class EnableJmsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(EnableJmsDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner publish(
            JmsTemplate template,
            JmsListenerEndpointRegistry registry) {

        return args -> {
            boolean registered =
                    registry.getListenerContainer("ordersEndpoint") != null;
            System.out.println("ENDPOINT_REGISTERED=" + registered);

            if (!registered) {
                throw new IllegalStateException(
                        "JMS listener endpoint not registered");
            }

            // Producer adds a property so the listener selector matches.
            template.convertAndSend(
                    "demo.jms.orders",
                    "order-42",
                    message -> {
                        message.setStringProperty(
                                "eventType", "ORDER_CREATED");
                        return message;
                    });

            System.out.println("SENT=order-42");
        };
    }
}

@Component
class OrderEndpoint {

    @JmsListener(
            id = "ordersEndpoint",
            destination = "demo.jms.orders",
            selector = "eventType = 'ORDER_CREATED'")
    public void onOrder(Message message) throws JMSException {
        if (!(message instanceof TextMessage textMessage)) {
            throw new IllegalArgumentException(
                    "Expected TextMessage");
        }

        System.out.println("RECEIVED=" + textMessage.getText());
        System.out.println("EVENT_TYPE="
                + message.getStringProperty("eventType"));
    }
}
~~~

**Reasons the code compiles:**

1. The file has only one public class `EnableJmsDemoApplication`, matching the filename. `OrderEndpoint` is package-private but is a Spring-managed component within the same package scan.
2. `@SpringBootApplication` registers configuration, component scanning, and auto-configuration.
3. `@EnableJms` enables detection of `@JmsListener` methods.
4. Spring Boot creates `ConnectionFactory`/`JmsTemplate`/default listener factory if the starter and configuration satisfy the conditions; there is no need to add a factory manually in this example.
5. `@JmsListener(id = "ordersEndpoint", ...)` creates an endpoint with an ID used for lookup from `JmsListenerEndpointRegistry`.
6. The producer sets the property `eventType = ORDER_CREATED` so the selector matches. The listener reads a raw `jakarta.jms.Message`, so it can access both body and properties.
7. The AppRunner starts after the context is initialized; the registry already has the registered endpoint metadata. The container must start and connect successfully to actually receive messages.

### 5.2. Running the Program

In the root directory of the Maven project:

~~~bash
mvn spring-boot:run
~~~

With Maven Wrapper on Windows:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

If the broker, credentials, queue, listener factory, and permissions are all valid, the expected business output lines are:

~~~text
ENDPOINT_REGISTERED=true
SENT=order-42
RECEIVED=order-42
EVENT_TYPE=ORDER_CREATED
~~~

**This is a representative expected stdout presentation, not an immutable chronological order.** Spring Boot also emits startup logs; the two listener lines `RECEIVED`/`EVENT_TYPE` may appear **before or after** `SENT=order-42` because the listener runs asynchronously. The `ENDPOINT_REGISTERED=true` line is printed before the send operation by AppRunner itself.

If the queue already contains older messages, the listener may print extra data, or receive older messages before AppRunner sends. If the broker cannot be reached, the application may fail on startup or send; merely having an entry in the endpoint registry does not prove the broker is running.

### 5.3. Proof That an Endpoint Exists Differs from a Message Being Processed

The output `ENDPOINT_REGISTERED=true` proves **the endpoint has been registered** with the registry. It does not guarantee:

- That the listener container is `running`; it could be stopped/disabled.
- That the broker is online or the queue exists.
- That the selector has any matching messages.
- That the handler ran successfully, the transaction committed, or business data was saved.

To check whether the container has started, you can inspect `registry.getListenerContainer("ordersEndpoint").isRunning()` once lifecycle has started. When monitoring production, also check logs, broker metrics, JMS consumer count, and actual business processing.

### 5.4. Try Removing @EnableJms

In the Spring Boot demo with normal JMS auto-configuration, remove `@EnableJms` and run again: the annotation-driven listener **is still usually detected** by Boot. This is a useful verification of the difference **between Spring Framework requiring explicit activation and Boot proactively auto-configuring**.

If you move the demo to a **plain Spring Framework project without Boot auto-configuration**, you must provide `@EnableJms`, the factory bean, and ConnectionFactory as shown in section 3.

## 6. Default Factory and Choosing a Dedicated Factory per Endpoint

### 6.1. The Default Bean Name Is jmsListenerContainerFactory

When the annotation does not specify `containerFactory`:

~~~java
@JmsListener(destination = "orders.incoming")
public void receive(String body) {
    System.out.println(body);
}
~~~

the infrastructure looks for the **default factory**, typically a bean named:

~~~text
jmsListenerContainerFactory
~~~

This is different from the name `ConnectionFactory` and different from `JmsTemplate`. `JmsListenerContainerFactory` is **not** a `ConnectionFactory` object; it receives the JMS ConnectionFactory as a dependency to create listener containers.

### 6.2. Configuring a Specific Factory

Example Spring Java Config used when you want to control transaction/concurrency:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
class OrdersListenerConfig {

    @Bean("ordersListenerFactory")
    DefaultJmsListenerContainerFactory ordersListenerFactory(
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

This is **a configuration dependent on a ConnectionFactory bean**, not a standalone program. When multiple listeners have different requirements, specify the factory on the annotation:

~~~java
@JmsListener(
        destination = "orders.incoming",
        containerFactory = "ordersListenerFactory")
public void onOrder(String body) {
    System.out.println(body);
}
~~~

The exact annotation attribute name is **`containerFactory`**, not `factory` or `connectionFactory`. The value is the **bean name** of type `JmsListenerContainerFactory`; the bean must exist and be compatible with the destination/provider.

If an annotation does **not** specify a factory and there is no default factory, you must either define `jmsListenerContainerFactory` or configure a default via `JmsListenerConfigurer`. Having a custom bean named `ordersListenerFactory` does not automatically make all listeners use that bean.

### 6.3. Settings Worth Defining on the Factory

| Setting | Effect | Notes |
| --- | --- | --- |
| `setConnectionFactory(...)` | Selects JMS provider/connection | Correct URL, credentials, JMS namespace |
| `setConcurrency("2-5")` | Allows multiple consumers/threads depending on container implementation | Broker load, ordering, competing consumers |
| `setSessionTransacted(true)` | Uses local JMS session transaction | Rollback/redelivery; does not automatically cover the database |
| `setPubSubDomain(true/false)` | Selects Topic or Queue when resolving names | Consumer needs the matching domain |
| `setDestinationResolver(...)` | How destination names are resolved to objects | Dynamic resolver/JNDI depending on provider |
| `setMessageConverter(...)` | Maps JMS Message to method payload | May differ from `JmsTemplate` converter |
| `setErrorHandler(...)` | Handles errors outside the receiving flow depending on container | Does not replace transaction/redelivery policy |
| `setAutoStartup(false)` | Does not automatically start the listener container | Must start explicitly via lifecycle/registry |

Some settings depend on the type of listener container created by the factory; check the Javadoc of the version in use, especially when tuning recovery, caching, and transaction managers. Do not copy all tuning settings from one broker/provider to another environment without verification.

## 7. JmsListenerEndpointRegistry: Observing and Controlling Listeners

The registry is a component registered by the annotation-driven infrastructure. You can inject it into a Spring bean:

~~~java
import org.springframework.jms.config.JmsListenerEndpointRegistry;

class RegistryInspector {

    private final JmsListenerEndpointRegistry registry;

    RegistryInspector(JmsListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    void inspect() {
        var container =
                registry.getListenerContainer("ordersEndpoint");
        if (container == null) {
            System.out.println("NOT_REGISTERED");
            return;
        }
        System.out.println("REGISTERED");
        System.out.println("RUNNING=" + container.isRunning());
    }
}
~~~

This is an **illustrative class**: for Spring to perform constructor injection, you must register the class as a bean via `@Component` or `@Bean`. The ID `ordersEndpoint` must match `@JmsListener(id = "ordersEndpoint", ...)`.

Typical capabilities:

- `getListenerContainer(String id)` — retrieves the container by endpoint ID, or `null` if it does not exist.
- `getListenerContainers()` — iterates over the listener containers managed by the registry.
- `isRunning()` — checks whether the registry/container is active according to lifecycle.
- `start()`, `stop()` — lifecycle operations at the registry or corresponding container level.

### 7.1. Stopping/Starting the Right Endpoint Without Stopping Everything by Mistake

Example when you intentionally implement a pause/resume feature:

~~~java
var container = registry.getListenerContainer("ordersEndpoint");
if (container == null) {
    throw new IllegalArgumentException("Unknown endpoint id");
}

// Pause only the listener corresponding to this id.
container.stop();

// After a valid resume decision:
container.start();
~~~

This is an **illustrative administrative service snippet**, requiring the `registry` bean and authorization/operational controls if exposed over HTTP. Do not call stop/start arbitrarily in business code for every message: listener lifecycle belongs to operations and can affect in-flight messages.

When a container has `isRunning() == true`, it has been started according to the Spring lifecycle; that still does not guarantee the broker is delivering messages, credentials remain valid, or listener processing succeeds.

### 7.2. Avoid Bypassing Infrastructure by Calling new Directly on a @JmsListener Class

~~~java
OrderEndpoint endpoint = new OrderEndpoint();
~~~

The snippet above is valid Java code **but does not register a JMS listener**: Spring does not manage that object at all. The registry has no knowledge of the `@JmsListener` method on a manually instantiated object. You must register the bean via component scanning/`@Bean` so the post-processor processes it.

## 8. @JmsListener Can Describe More Than Just Destination

`@EnableJms` enables the infrastructure. Each `@JmsListener` defines a specific endpoint. Commonly used attributes:

| Attribute | Example | Meaning |
| --- | --- | --- |
| `destination` | `"orders.incoming"` | Name of queue/topic to receive from |
| `id` | `"ordersEndpoint"` | Unique ID for lookup in the registry |
| `containerFactory` | `"ordersListenerFactory"` | Factory bean that creates the container |
| `selector` | `"eventType = 'ORDER_CREATED'"` | JMS selector filtering headers/properties |
| `concurrency` | `"2-5"` | Overrides concurrency if the factory/container supports it |
| `subscription` | `"billingService"` | Subscription name for a topic according to relevant semantics |

You do not need to set every attribute. A simple method:

~~~java
@JmsListener(destination = "orders.incoming")
public void handle(String text) {
    System.out.println(text);
}
~~~

can already be processed by the infrastructure if Spring manages the bean and the factory/connection work. With a `String` payload, Spring's handler adapter converts the JMS message into the parameter using the appropriate converter. If receiving a raw JMS message:

~~~java
@JmsListener(destination = "orders.incoming")
public void handleRaw(jakarta.jms.Message message)
        throws jakarta.jms.JMSException {
    System.out.println(message.getJMSMessageID());
}
~~~

you can read headers/properties directly. Both are **method snippets inside a Spring-managed bean**, not standalone code. Do not declare two listener methods consuming the same queue expecting **each message to be processed twice**: on a queue they can act as competing consumers.

### 8.1. When Is an Endpoint Invoked?

Not when the Java method is declared or the class is loaded into the JVM. It is invoked when:

1. The Spring bean has been discovered.
2. `@JmsListener` has been detected by the processor and the endpoint is registered.
3. The container has started and connected to the destination.
4. The broker delivers an eligible message.
5. The container/adapter converts the message into method arguments and calls the handler.

If the method signature requires a DTO but the converter does not know how to deserialize the payload, the message may reach the container and then fail before entering the method body. That differs from the situation where the endpoint was never registered at all.

### 8.2. Repeatable @JmsListener

Spring allows repeating `@JmsListener` on the same method to describe multiple endpoints:

~~~java
@JmsListener(
        id = "ordersAEndpoint",
        destination = "orders.a")
@JmsListener(
        id = "ordersBEndpoint",
        destination = "orders.b")
public void handleMany(String payload) {
    System.out.println(payload);
}
~~~

This is a **snippet inside a bean**, requiring Java imports and JMS infrastructure. Each annotation describes an endpoint/container corresponding to a separate destination. IDs should be distinct so the registry manages them clearly. Do not treat repeatable annotations as a mechanism to merge two JMS queues into one queue.

## 9. Customizing the Default Factory with JmsListenerConfigurer

When the default factory is not named `jmsListenerContainerFactory`, or when you want to register endpoints programmatically, Spring provides the `JmsListenerConfigurer` interface and the `configureJmsListeners(JmsListenerEndpointRegistrar)` callback.

Concise example:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListenerConfigurer;
import org.springframework.jms.config.JmsListenerContainerFactory;
import org.springframework.jms.config.JmsListenerEndpointRegistrar;

@Configuration
@EnableJms
class RegistrarConfig implements JmsListenerConfigurer {

    private final JmsListenerContainerFactory<?> factory;

    RegistrarConfig(
            @Qualifier("ordersListenerFactory")
            JmsListenerContainerFactory<?> factory) {
        this.factory = factory;
    }

    @Override
    public void configureJmsListeners(
            JmsListenerEndpointRegistrar registrar) {
        registrar.setContainerFactory(factory);
    }
}
~~~

This is an **illustrative configuration**, assuming a valid `ordersListenerFactory` bean already exists. The registrar will use this factory as the default for endpoints that do not specify `containerFactory`. Name beans consistently to avoid injection errors or selecting the wrong factory.

An advanced scenario is registering a `SimpleJmsListenerEndpoint` programmatically instead of via annotation, for instance when endpoint definitions are built from configuration. However, this still requires the registrar, registry, factory, and ConnectionFactory to be properly configured; it does not alter JMS queue/topic rules.

### 9.1. When Do You NOT Need JmsListenerConfigurer?

If the project only has one factory named `jmsListenerContainerFactory`, and every method uses the shared configuration, you do not need the advanced interface. With Spring Boot, in many cases you also do not need to declare the factory yourself. Start with the minimal working configuration and only customize when you truly need distinct transactions, concurrency, message conversion, or separate factories.

## 10. @EnableJms, @JmsListener, and JmsTemplate Are Not the Same

| Component | Layer | Responsibility |
| --- | --- | --- |
| `@EnableJms` | Spring configuration | Enables annotation-driven JMS endpoint processing |
| `@JmsListener` | Method endpoint | Declares a consumer method to invoke when a message arrives |
| `JmsListenerContainerFactory` | Infrastructure configuration | Creates and configures listener containers |
| `JmsListenerEndpointRegistry` | Lifecycle/registry | Looks up/manages containers of annotated endpoints |
| `JmsTemplate` | Client operations | Sends messages; or receives synchronously when called |
| `ConnectionFactory` | JMS provider | Provides connections/sessions/contexts |
| JMS broker | Messaging infrastructure | Stores/routes messages by queue/topic and provider policies |

An application can **only send messages** using `JmsTemplate.convertAndSend(...)` **without needing `@EnableJms`**, because it does not use annotation-driven listeners. Conversely, a consumer application with `@JmsListener` may never directly call `JmsTemplate.receive()` anywhere.

Do not confuse with:

- `@EnableScheduling`: enables processing of Spring scheduled methods (not JMS).
- `@EnableAsync`: enables processing of `@Async` methods (not listener containers).
- `@EnableRabbit`: listener infrastructure for RabbitMQ via Spring AMQP (not JMS API).
- `@EnableKafka`: listener infrastructure for Kafka (not JMS).
- `@EnableJms`: dedicated solely to annotation-driven **JMS** endpoints.

If an application uses multiple messaging technologies, each has its own configuration, factories, and lifecycle rules. Do not apply RabbitMQ or Kafka property/factory names to `@JmsListener`.

## 11. Transactions, Concurrency, and Lifecycle After Activation

Enabling `@EnableJms` only provides **the capability to register endpoints**. The reliability of message processing depends on the listener container configuration.

### 11.1. Concurrency

For a queue, `factory.setConcurrency("2-5")` typically allows the container to manage the number of concurrent consumers depending on the implementation. That increases throughput for certain workloads but has consequences:

- Messages may be processed concurrently; completion order is not necessarily send order.
- Database/HTTP dependencies experience higher concurrency.
- If multiple instances consume the same queue, they compete for message delivery.
- Special ordering behaviors such as JMS message groups require configuration/verification on the provider.
- `@JmsListener(concurrency="...")` can override the factory setting for an endpoint if the container supports it.

Do not increase concurrency just to "turn on @JmsListener". Check handler idempotency, thread-safety, and broker quotas.

### 11.2. Transactions and Acknowledgment

When a listener method throws an exception, whether the broker redelivers or not **depends on the ack/transaction configuration**. Having `@EnableJms` does not mean automatic rollback.

For example:

~~~java
factory.setSessionTransacted(true);
~~~

This is a **JMS local session transaction** setting commonly used when you want the container to roll back the JMS session if processing fails. However:

- A JMS transaction does not automatically include the application's database commit.
- The listener may be invoked again upon redelivery; business logic should be idempotent.
- The provider has its own retry/DLQ policy; monitor poison messages.
- If using an external transaction manager/JTA, configure it accordingly rather than only setting `sessionTransacted=true`.

With `AUTO_ACKNOWLEDGE` and certain listener container types, acknowledgment may happen before the business method completes; therefore, never promise that every method error will be redelivered without testing the actual configuration.

### 11.3. Auto-Startup and Explicit Start

A factory can be configured with:

~~~java
factory.setAutoStartup(false);
~~~

In that case the endpoint can still **be registered** while the container has not started; `registry.getListenerContainer("ordersEndpoint")` can return a valid object even though `isRunning() == false`.

Once the environment/broker is ready and the application has lifecycle control permissions, you can call `container.start()`. Do not put start/stop controls arbitrarily into every business event. For production systems, you need graceful shutdown/drain mechanisms and consumer health monitoring.

### 11.4. Queue vs. Topic Differences

In Spring, a factory/container can configure `pubSubDomain`:

~~~java
factory.setPubSubDomain(false); // queue
factory.setPubSubDomain(true);  // topic
~~~

The two lines are **two alternative options**, not a configuration run simultaneously. With a Topic, you must consider subscription (durable/shared), client identity, and lifecycle; a consumer is only present when the corresponding subscription is established. Do not infer that putting `"topic"` in the destination name automatically changes the JMS domain.

## 12. Common Errors When Enabling @EnableJms

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Plain Spring Framework does not recognize `@JmsListener` | `@EnableJms` not enabled | Place it on a `@Configuration` imported/scanned by the context |
| Boot lacks `@EnableJms` yet listener still works | Boot JMS auto-configuration enabled the infrastructure | This can be normal behavior |
| Has `@EnableJms` but receives no messages | Missing factory, ConnectionFactory, broker, or endpoint bean | Check all layers; the annotation does not connect to the broker itself |
| Error that `jmsListenerContainerFactory` is not found | Endpoint specifies no factory, default factory does not exist | Define the bean with the exact name or use `JmsListenerConfigurer` |
| `@JmsListener(containerFactory="ordersFactory")` fails | Bean name does not exist or bean has wrong type | Verify exact bean name and `JmsListenerContainerFactory` type |
| `registry.getListenerContainer("ordersEndpoint")` returns `null` | Wrong ID, listener bean not scanned/registered | Check component scan, ID, processor, context |
| Registry shows endpoint but `isRunning=false` | Factory disabled autoStartup or container was stopped | Check lifecycle, start the right container when appropriate |
| Endpoint is running but queue receives nothing | Wrong destination, unprovisioned queue, ACL, broker offline, unmatched selector | Check broker/queue metrics, network, and selector |
| Using `javax.jms.Message` with Spring Boot 3 | Namespace mismatch with Jakarta JMS | Use `jakarta.jms.Message`/compatible client |
| Listener fails converting body | Converter does not match message type or DTO | Check listener converter and actual JMS Message |
| Listener class not picked up by component scan | Class not managed by Spring or outside base package | Register bean/adjust component scan |
| Message processed multiple times | Rollback/redelivery/consumer restart or ack error | Design idempotency, inspect transactions/DLQ |
| Consumer overloaded at high concurrency | Too many consumers/threads | Measure throughput, lower concurrency, apply backpressure |
| Messages published to Topic not seen | Wrong domain/subscription lifecycle | Check `pubSubDomain` and durable/shared subscription |
| Changing annotation at runtime does not change container | Endpoint is registered at startup | Reload config/restart container properly, avoid mutating annotations |

### 12.1. Layer-by-Layer Investigation Workflow

~~~text
Is the @JmsListener method in a Spring-managed bean?
     |
     +-- No --> check @ComponentScan/@Bean
     |
     v
Does Spring Framework have @EnableJms or valid Boot auto-configuration?
     |
     +-- No --> enable annotation infrastructure
     |
     v
Is there a suitable JmsListenerContainerFactory?
     |
     +-- No --> declare jmsListenerContainerFactory/custom bean
     |
     v
Does the Registry have the endpoint ID?
     |
     +-- No --> check annotation processing, bean scan, ID
     |
     v
Has the container started and connected to the broker?
     |
     +-- No --> connection/ACL/autostart/recovery
     |
     v
Is the queue/topic right and has matching messages?
     |
     +-- No --> destination, pubSubDomain, selector, TTL, competing consumers
     |
     v
Do method argument conversion and business processing succeed?
     |
     +-- No --> converter, exception, transaction, redelivery, DLQ
     |
     v
Working
~~~

This diagnostic path separates **annotation infrastructure not enabled** errors from **broker/message delivery** errors and **business method** errors. That is the main purpose of understanding `@EnableJms`, rather than just adding annotations until warnings disappear.

## 13. Production Deployment Checklist

1. **Correct namespace:** Spring Framework 6/Boot 3 uses `jakarta.jms.*`, not mixed with legacy `javax.jms.*`.
2. **Correct activation mechanism:** Plain Spring uses `@EnableJms`; Spring Boot verifies auto-configuration instead of adding annotations out of habit.
3. **Spring-managed bean:** `@JmsListener` is on a scanned class or registered via `@Bean`.
4. **Explicit factory:** Have default `jmsListenerContainerFactory` or a custom factory specified with `containerFactory`.
5. **ConnectionFactory:** Correct broker URL, credentials, TLS, provider client, connect/send/consume permissions.
6. **Destination:** Correct name, Queue/Topic domain; provisioned/auto-created per broker policy.
7. **Endpoint ID:** Assign a unique ID if operating through the registry.
8. **Selector:** Use properly typed properties; type mismatches can prevent the listener from receiving messages.
9. **Concurrency:** Choose a level suited to workload and ordering/idempotency.
10. **Transactions:** Verify actual ack/commit/rollback/redelivery; design DLQ and retries.
11. **Converter:** String/DTO/raw Message handlers have valid conversion paths and compatible schemas.
12. **Lifecycle:** Know when containers start/stop, support graceful shutdown.
13. **Observability:** Measure consumer count, queue depth, message age, conversion errors, and handler failures.
14. **Security:** Avoid logging secrets/sensitive payloads; apply ACLs and authorization beyond selectors.
15. **Integration testing:** Do not only unit-test annotations; run against a test broker or JMS test infrastructure to verify registration/sending/receiving.

## 14. Self-Check Questions

**Question 1.** In plain Spring Framework, which annotation enables discovery of `@JmsListener` methods?

**Answer:** `@EnableJms` on a `@Configuration` class loaded by Spring; the required JMS/factory beans must also be present.

**Question 2.** Why can a Spring Boot 3 app with `@JmsListener` still run without writing `@EnableJms`?

**Answer:** Spring Boot with a JMS starter and valid auto-configuration can automatically enable the JMS listener annotation infrastructure.

**Question 3.** Does `@EnableJms` create a `ConnectionFactory` or run a broker?

**Answer:** No. It only enables processing of annotated endpoints. ConnectionFactory/provider and the broker must be configured independently.

**Question 4.** Which factory does the infrastructure look for if `@JmsListener` has no `containerFactory` attribute?

**Answer:** Usually the bean named `jmsListenerContainerFactory`, unless a default is configured separately via `JmsListenerConfigurer`.

**Question 5.** Does `@EnableJms` make Spring recognize a listener object created manually with `new`?

**Answer:** No. The bean must be managed by Spring for the post-processor to detect method annotations.

**Question 6.** To use a factory with bean name `ordersListenerFactory` for a listener, how is the annotation written?

**Answer:** `@JmsListener(destination="...", containerFactory="ordersListenerFactory")`.

**Question 7.** What is `JmsListenerEndpointRegistry.getListenerContainer("id")` used for?

**Answer:** Looking up the container of an endpoint ID to observe and manage its lifecycle; not for directly fetching a JMS Message.

**Question 8.** Does `registry.getListenerContainer(id) != null` guarantee messages will reach the method?

**Answer:** No. It only confirms registration. The container must be running, the broker/queue/permissions must be valid, and matching messages must exist.

**Question 9.** Do two `@JmsListener` methods consuming the same queue cause every message to be processed twice?

**Answer:** No. Queues typically use competing consumers; each delivery goes to only one eligible consumer. Topics/subscriptions provide fan-out.

**Question 10.** Why does enabling `setSessionTransacted(true)` on a factory not automatically guarantee atomic database and JMS commits?

**Answer:** That is a JMS session transaction, which does not automatically open a global transaction across the database; an appropriate transaction/outbox or JTA/XA design is required.

**Question 11.** If a listener is registered but not running due to `setAutoStartup(false)`, should you fix the `@EnableJms` annotation?

**Answer:** No. That is a container lifecycle/startup issue; use the registry or factory configuration to start at the right time.

**Question 12.** Why should you separate bean discovery, JMS connection, and handler conversion errors when debugging?

**Answer:** Because the three errors occur at three different layers: endpoint not registered, container unable to connect/receive messages, or message arrives but conversion/business method fails.

## Official References

- [Spring Framework 6.2 — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html): `@EnableJms`, default factory, JMS endpoint registration, registry lifecycle, and listener parameters.
- [Spring Framework 6.2 Javadoc — EnableJms](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/annotation/EnableJms.html): annotation, `JmsBootstrapConfiguration`, `@JmsListener` detection mechanism, `JmsListenerConfigurer`.
- [Spring Framework 6.2 Javadoc — JmsListener](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/annotation/JmsListener.html): `id`, `destination`, `selector`, `containerFactory`, `concurrency`, `subscription`.
- [Spring Framework 6.2 Javadoc — JmsListenerEndpointRegistry](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistry.html): managing containers by endpoint ID and lifecycle.
- [Spring Framework 6.2 Javadoc — DefaultJmsListenerContainerFactory](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html): factory configuration for listeners.
- [Spring Boot 3.5 — JMS](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html): Artemis, auto-configured JMS resources, and listeners.
- [Spring Guide — Messaging with JMS](https://spring.io/guides/gs/messaging-jms/): Spring Boot example auto-discovering `@JmsListener` without requiring `@EnableJms`.
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): queue/topic semantics, consumers, connection/session, and acknowledgments.
