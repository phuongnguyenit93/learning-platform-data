# JmsListenerConfigurer and Programmatic Endpoint Registration

## Objectives

Spring JMS can register listeners using the `@JmsListener` annotation or Java configuration. `JmsListenerConfigurer` is a callback that lets an application customize the listener infrastructure and register `JmsListenerEndpoint` instances directly through `JmsListenerEndpointRegistrar`.

Programmatic registration is useful when the list of destinations comes from configuration, when each endpoint needs its own listener or container factory, or when the application wants to create endpoints according to a configuration rule at startup time.

After this lesson, you can:

- Explain the roles of `@EnableJms`, `JmsListenerConfigurer`, and `JmsListenerEndpointRegistrar`.
- Create a `SimpleJmsListenerEndpoint` and attach a `MessageListener`.
- Distinguish `SimpleJmsListenerEndpoint` from `MethodJmsListenerEndpoint`.
- Configure the ID, destination, selector, subscription, and concurrency.
- Choose the default `JmsListenerContainerFactory` or a separate factory for each endpoint.
- Understand how `JmsListenerEndpointRegistry` creates and manages listener containers.
- Combine programmatically registered endpoints with `@JmsListener` endpoints.
- Customize argument binding, conversion, and validation for method endpoints.
- Monitor the lifecycle, transactions, and errors of endpoints.
- Run a Spring Boot example with embedded ActiveMQ Artemis.

## 1. What Is a Listener Endpoint?

In Spring JMS, a listener endpoint describes a place where messages are received and how Spring processes messages there. The endpoint is configuration metadata; the listener container is the component that connects to the JMS provider, creates consumers, and invokes the listener.

Main parts:

| Component | Role |
|---|---|
| `JmsListenerEndpoint` | Describes a JMS endpoint and how to configure the listener container for that endpoint. |
| `JmsListenerContainerFactory` | Creates the listener container from the endpoint. |
| `MessageListenerContainer` | Manages the consumer, session, threads, transactions, recovery, and message dispatching. |
| `JmsListenerEndpointRegistrar` | Receives endpoints and factories during the configuration phase. |
| `JmsListenerEndpointRegistry` | Creates, stores, and manages the lifecycle of the registered listener containers. |
| `JmsListenerConfigurer` | Callback for a Spring bean to customize the registrar and register endpoints programmatically. |

General flow:

~~~mermaid
flowchart TD
    A["Spring Application Context"] --> B["@EnableJms"]
    B --> C["JmsListenerAnnotationBeanPostProcessor"]
    C --> D["JmsListenerConfigurer callback"]
    D --> E["JmsListenerEndpointRegistrar"]
    E --> F["JmsListenerEndpoint"]
    E --> G["JmsListenerContainerFactory"]
    F --> H["JmsListenerEndpointRegistry"]
    G --> H
    H --> I["MessageListenerContainer"]
    I --> J["JMS Provider / Broker"]
    J --> I
    I --> K["MessageListener / POJO method"]
~~~

The endpoint specifies the destination and the listener. The factory provides how to create the container. The registry holds the container and manages its lifecycle along with the application context.

## 2. JmsListenerConfigurer and @EnableJms

`JmsListenerConfigurer` lives in the package:

~~~java
org.springframework.jms.annotation.JmsListenerConfigurer
~~~

It is a functional interface with a single callback:

~~~java
void configureJmsListeners(JmsListenerEndpointRegistrar registrar);
~~~

Spring calls this callback while initializing the listener infrastructure. The application uses the registrar to:

- Set the default listener container factory.
- Choose the default factory by bean name.
- Register one or more endpoints.
- Configure `MessageHandlerMethodFactory` for endpoints that use method invocation.

Configuration skeleton example:

~~~java
@Configuration
@EnableJms
public class JmsConfiguration implements JmsListenerConfigurer {

    @Override
    public void configureJmsListeners(JmsListenerEndpointRegistrar registrar) {
        // Register endpoints here.
    }
}
~~~

`@EnableJms` enables the annotation-driven listener infrastructure. It registers the processor that handles `@JmsListener` and a default `JmsListenerEndpointRegistry`.

Even when not using the `@JmsListener` annotation, you can still use `@EnableJms` together with `JmsListenerConfigurer` to register endpoints purely programmatically.

### Do Not Confuse the Configurer with the Container

`JmsListenerConfigurer` does not receive messages directly. It only declares endpoints and how to create containers during the configuration phase.

`JmsListenerEndpointRegistrar` is also not a running listener. It is a helper that accepts endpoints and passes them to the registry.

Actual messages are received by the consumers managed by the listener container.

## 3. JmsListenerEndpointRegistrar

The registrar is a helper for registering endpoints with the registry and choosing the factory that creates containers.

Commonly used APIs:

| Method | Purpose |
|---|---|
| `registerEndpoint(endpoint)` | Registers an endpoint using the default factory. |
| `registerEndpoint(endpoint, factory)` | Registers an endpoint with the specified factory. |
| `setContainerFactory(factory)` | Sets the default factory for endpoints that do not specify a factory. |
| `setContainerFactoryBeanName(name)` | Sets the bean name of the default factory; looked up via BeanFactory. |
| `setEndpointRegistry(registry)` | Specifies the registry that manages endpoints. |
| `setMessageHandlerMethodFactory(factory)` | Configures method argument binding/invocation for method endpoints. |

Example of choosing the default factory by bean name:

~~~java
@Override
public void configureJmsListeners(JmsListenerEndpointRegistrar registrar) {
    registrar.setContainerFactoryBeanName("jmsListenerContainerFactory");

    SimpleJmsListenerEndpoint endpoint = new SimpleJmsListenerEndpoint();
    endpoint.setId("ordersEndpoint");
    endpoint.setDestination("orders.queue");
    endpoint.setMessageListener(message -> {
        // Process the message.
    });

    registrar.registerEndpoint(endpoint);
}
~~~

In the example, `jmsListenerContainerFactory` must be a `JmsListenerContainerFactory` bean with the corresponding name. If an endpoint does not specify its own factory, the registrar uses the default factory.

You can pass a factory directly:

~~~java
registrar.registerEndpoint(endpoint, ordersListenerFactory);
~~~

This approach is useful when a Queue and a Topic need different configurations, or when groups of listeners have separate transaction, concurrency, converter, or acknowledgement policies.

### Default Factory for @JmsListener

If the application has `@JmsListener` endpoints that do not declare `containerFactory`, Spring needs a default factory. By convention, the infrastructure looks for a bean named `jmsListenerContainerFactory`.

You can set the default factory through the registrar inside `JmsListenerConfigurer`. An endpoint that has its own factory passed will use that factory.

## 4. SimpleJmsListenerEndpoint

`SimpleJmsListenerEndpoint` is a simple implementation of `JmsListenerEndpoint`. It directly takes a `jakarta.jms.MessageListener` object.

Example:

~~~java
SimpleJmsListenerEndpoint endpoint = new SimpleJmsListenerEndpoint();
endpoint.setId("auditEndpoint");
endpoint.setDestination("audit.queue");
endpoint.setMessageListener(message -> {
    System.out.println("received JMS message");
});
registrar.registerEndpoint(endpoint);
~~~

Properties inherited from `AbstractJmsListenerEndpoint`:

| Setter | Meaning |
|---|---|
| `setId(id)` | Sets a stable ID for the registry to manage and retrieve the container. |
| `setDestination(name)` | Sets the Queue or Topic name. |
| `setSelector(expression)` | Sets the JMS message selector. |
| `setSubscription(name)` | Sets the durable subscription name when using a Topic. |
| `setConcurrency(value)` | Sets concurrency for the listener if the container supports it. |
| `setMessageListener(listener)` | Sets the JMS callback that performs message processing. |

### MessageListener Receiving the Raw JMS Message

With a simple endpoint, the listener receives a `jakarta.jms.Message` object:

~~~java
endpoint.setMessageListener(message -> {
    if (message instanceof TextMessage textMessage) {
        try {
            System.out.println(textMessage.getText());
        }
        catch (JMSException ex) {
            throw new IllegalStateException("Cannot read TextMessage", ex);
        }
    }
});
~~~

You decide how to read the message type and handle JMS headers/properties yourself. This is a low-level JMS API, suitable when full control over the message is needed or when an existing listener already implements `MessageListener`.

If you want a delegate to receive a converted String, Map, or POJO, configure an appropriate converter/adapter or use a method endpoint to take advantage of argument resolution.

## 5. MethodJmsListenerEndpoint

`MethodJmsListenerEndpoint` is also an implementation of `JmsListenerEndpoint`, but it describes a method on a bean to be invoked when a message arrives.

Required information:

- The bean instance to call.
- The `java.lang.reflect.Method` to execute.
- The `MessageHandlerMethodFactory` that creates the invocation handler and argument resolvers.
- The destination, ID, and inherited endpoint properties.

Skeleton example:

~~~java
MethodJmsListenerEndpoint endpoint = new MethodJmsListenerEndpoint();
endpoint.setId("orderMethodEndpoint");
endpoint.setDestination("orders.queue");
endpoint.setBean(orderService);
endpoint.setMethod(OrderService.class.getMethod("processOrder", String.class));
endpoint.setMessageHandlerMethodFactory(messageHandlerMethodFactory);
registrar.registerEndpoint(endpoint);
~~~

Target bean:

~~~java
public class OrderService {

    public void processOrder(String orderId) {
        System.out.println("order=" + orderId);
    }
}
~~~

`MethodJmsListenerEndpoint` uses `MessagingMessageListenerAdapter` to convert the message into method parameters and call the bean. This is close to the mechanism of `@JmsListener`.

If the bean is proxied by AOP, you may need to supply the specific method on the target class with `setMostSpecificMethod` depending on the proxy structure. The method and bean must be compatible; the method must be invokable by the invocation infrastructure.

### MessageHandlerMethodFactory

`MessageHandlerMethodFactory` provides the mechanism for creating `InvocableHandlerMethod`, including argument resolvers, conversion, and validation.

By default, Spring uses `DefaultMessageHandlerMethodFactory`. It can be customized to add a validator or converter:

~~~java
@Bean
DefaultMessageHandlerMethodFactory jmsHandlerMethodFactory(
        Validator validator) {

    DefaultMessageHandlerMethodFactory factory =
            new DefaultMessageHandlerMethodFactory();
    factory.setValidator(validator);
    return factory;
}
~~~

Then configure the factory on the registrar and the endpoint:

~~~java
registrar.setMessageHandlerMethodFactory(jmsHandlerMethodFactory);
endpoint.setMessageHandlerMethodFactory(jmsHandlerMethodFactory);
~~~

A method endpoint can receive the payload, raw JMS `Message`, JMS `Session`, Spring `Message<?>`, `@Header`, `@Headers`, and other supported parameters. A payload parameter can be declared explicitly with `@Payload`; `@Valid` can trigger validation if a validator has been configured.

## 6. How Do Simple Endpoint and Method Endpoint Differ?

| Criterion | SimpleJmsListenerEndpoint | MethodJmsListenerEndpoint |
|---|---|---|
| Listener input | A JMS `MessageListener` | A specific bean and method |
| How it is invoked | Calls `onMessage(Message)` | Uses `MessagingMessageListenerAdapter` and method invocation |
| Payload conversion | The listener reads the message or uses a converter itself | Has argument resolution and conversion |
| Header binding | The listener reads JMS headers/properties itself | Can use `@Header` and `@Headers` |
| Validation | Calls validation itself inside the listener | Can be configured via `MessageHandlerMethodFactory` |
| Complexity | Less configuration, direct control | More flexible for POJO methods |
| Suitability | Existing JMS listeners or raw message logic | POJOs, method signatures, conversion, and validation |

Choose `SimpleJmsListenerEndpoint` when you already have a `MessageListener` and want to register it via configuration. Choose `MethodJmsListenerEndpoint` when you want Spring to manage calling a bean method with bound parameters.

## 7. Setting ID, Destination, Selector, and Concurrency

### Endpoint ID

Each endpoint should have a unique ID within the same registry:

~~~java
endpoint.setId("billingOrdersEndpoint");
~~~

The ID is used to identify the listener container:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("billingOrdersEndpoint");
~~~

Giving a meaningful ID helps make logs, metrics, and operational actions easy to trace. If omitted, the endpoint can be assigned a default ID, but an explicit ID is more convenient for management.

Do not register two endpoints with the same ID in one registry. Generate IDs that are stable, unique, and do not depend on uncontrolled data.

### Destination

`setDestination("orders.queue")` takes a destination name as a String. The listener container uses the factory's DestinationResolver to resolve the name into a Queue or Topic.

The domain must match the actual destination:

- A Queue uses the point-to-point domain.
- A Topic uses the publish/subscribe domain.
- If using a separate factory, configure `pubSubDomain` on the corresponding factory.

The String name does not determine Queue vs. Topic by itself.

### Message Selector

A selector is a JMS expression applied to the message's headers/properties:

~~~java
endpoint.setSelector("eventType = 'OrderCreated'");
~~~

Only messages with a matching `eventType` property are delivered to the consumer. The selector does not query a JSON body. The producer needs to set the property with the right type and name.

### Concurrency

You can set concurrency as a string:

~~~java
endpoint.setConcurrency("3-8");
~~~

The meaning is usually the minimum and maximum number of consumers, if the container supports scaling. A value like `"5"` sets the upper limit to 5 and the minimum to 1.

Actual scaling capability depends on the container type and provider. With `DefaultMessageListenerContainer`, concurrency can adjust the number of consumers within the configured range. Balance this against database, downstream, and broker capacity.

### Durable Subscription

With a Topic, the endpoint can set a subscription name:

~~~java
endpoint.setSubscription("inventorySubscription");
~~~

This name is only part of the durable subscription configuration. The listener container also needs the pub-sub domain, durable subscription enabled, and appropriate client ID/provider settings. Setting the subscription name alone does not turn a Queue endpoint into a durable Topic subscription.

## 8. Choosing the Container Factory for an Endpoint

The endpoint only describes where to receive and the listener. The factory creates the container and determines most of the operational behavior.

Example factory:

~~~java
@Bean
DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory) {

    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setSessionTransacted(true);
    factory.setConcurrency("2-6");
    return factory;
}
~~~

You can register an endpoint using the default factory:

~~~java
registrar.registerEndpoint(endpoint);
~~~

Or choose a separate factory:

~~~java
registrar.registerEndpoint(endpoint, topicListenerFactory);
~~~

An application using both Queues and Topics can define:

- A Queue factory with `pubSubDomain=false`.
- A Topic factory with `pubSubDomain=true`.
- A transacted factory for listeners that need rollback.
- A non-transacted factory for listeners with a different policy.

Do not assume endpoints sharing one factory will automatically have different destination domains based on name.

## 9. JmsListenerEndpointRegistry and Lifecycle

`JmsListenerEndpointRegistry` creates listener containers from registered endpoints and factories. It also manages the lifecycle of those containers within the application context.

Commonly used APIs:

| API | Purpose |
|---|---|
| `getListenerContainer(id)` | Gets the container by endpoint ID. |
| `getListenerContainerIds()` | Gets the set of registered container IDs. |
| `getListenerContainers()` | Gets the collection of containers currently managed by the registry. |
| `start()` | Starts containers according to the registry's lifecycle. |
| `stop()` | Stops containers according to the registry's lifecycle. |
| `isRunning()` | Checks whether the registry is running. |

Example:

~~~java
@Autowired
private JmsListenerEndpointRegistry registry;

public void inspectListeners() {
    for (String id : registry.getListenerContainerIds()) {
        MessageListenerContainer container =
                registry.getListenerContainer(id);
        System.out.println(id + " -> " + container);
    }
}
~~~

The listener containers created by the registry are not separate beans in the application context and cannot be autowired directly like regular beans. To manage them, access them through the registry by ID.

### Registration at Startup vs. Runtime Registration

`JmsListenerConfigurer` is the appropriate place to register endpoints during the application context configuration phase. The registrar collects the endpoints and the registry creates the containers during the startup lifecycle.

If you need to create an endpoint after the application is already running, you can use the registry's API:

~~~java
registry.registerListenerContainer(endpoint, containerFactory, true);
~~~

The last parameter `true` asks the container to start immediately. When registering at runtime, you need to control unique IDs, valid destinations, access rights, and container lifecycle. Do not create a new endpoint per message or per HTTP request without a clear limit policy; the number of consumers/containers can grow uncontrollably.

The registry manages start/stop and destroy. When the application shuts down, containers managed by the registry are stopped according to the lifecycle.

## 10. Combining Programmatic Registration with @JmsListener

An application can use both at the same time:

- `@JmsListener` for simple, fixed endpoints.
- `JmsListenerConfigurer` for endpoints generated from configuration or a list of destinations.

Annotation example:

~~~java
@Component
public class AuditListener {

    @JmsListener(destination = "audit.queue")
    public void receive(String event) {
        System.out.println("audit=" + event);
    }
}
~~~

At the same time, the configurer registers an endpoint:

~~~java
@Override
public void configureJmsListeners(JmsListenerEndpointRegistrar registrar) {
    SimpleJmsListenerEndpoint endpoint = new SimpleJmsListenerEndpoint();
    endpoint.setId("dynamicOrdersEndpoint");
    endpoint.setDestination("orders.queue");
    endpoint.setMessageListener(orderMessageListener);
    registrar.registerEndpoint(endpoint);
}
~~~

Both kinds of endpoints are managed by `JmsListenerEndpointRegistry` and use the corresponding container factory.

If you want to omit annotations completely, you can still use only `@EnableJms` and `JmsListenerConfigurer`. The registrar/registry infrastructure is needed to create listener containers.

## 11. Registering Multiple Endpoints from Configuration

A common case is that the list of destinations comes from application properties or deployment configuration. You can loop over a validated list and create an endpoint for each destination.

Illustrative example:

~~~java
@Override
public void configureJmsListeners(JmsListenerEndpointRegistrar registrar) {
    for (String queueName : configuredQueues) {
        SimpleJmsListenerEndpoint endpoint = new SimpleJmsListenerEndpoint();
        endpoint.setId("queue-" + queueName);
        endpoint.setDestination(queueName);
        endpoint.setMessageListener(message -> process(queueName, message));
        registrar.registerEndpoint(endpoint);
    }
}
~~~

Each endpoint needs:

- A unique ID.
- A valid destination.
- A listener capable of handling the message type received.
- A factory suitable for Queue/Topic.
- Concurrency and transaction policy suited to the load.

The destination list should come from controlled configuration. Do not arbitrarily take destinations from external requests and register listeners, because doing so can open consume access to queues/topics the service is not permitted to access.

If a list contains both Queues and Topics, carry the domain in the configuration and register with the factory of the right domain. Do not infer the destination type from a name suffix.

## 12. Customizing Method Binding, Conversion, and Validation

With `MethodJmsListenerEndpoint`, Spring uses `MessageHandlerMethodFactory` to create the method invocation mechanism. The default factory supports common parameters:

- Converted payload.
- Raw `jakarta.jms.Message`.
- `jakarta.jms.Session`.
- Spring `Message<?>`.
- Parameters with `@Header`.
- A Map with `@Headers`.
- `@Payload` and validation with `@Valid`.

Method example:

~~~java
public void process(
        @Payload OrderCreated order,
        @Header("tenantId") String tenantId) {
    // Process the tenant's order.
}
~~~

You can set a custom validator or conversion support:

~~~java
DefaultMessageHandlerMethodFactory factory =
        new DefaultMessageHandlerMethodFactory();
factory.setValidator(orderValidator);
factory.afterPropertiesSet();

registrar.setMessageHandlerMethodFactory(factory);
~~~

In normal Spring configuration, if the factory is declared as a bean, the container lifecycle calls the initialization callback. There is no need to call `afterPropertiesSet()` again yourself for a Spring-managed bean.

Only customize `MessageHandlerMethodFactory` when you need to change argument resolvers, conversion, or validation. For a simple endpoint receiving a raw JMS Message, this factory does not control how the listener lambda reads the payload.

## 13. Replies and Error Handling

A programmatic endpoint can use a simple listener to send a reply using the JMS Session if the listener receives the session via a suitable Spring mechanism, or use `JmsTemplate` to send a response explicitly.

With a method endpoint, the method invocation mechanism can return a response value. The annotation-driven JMS infrastructure supports reply destinations via `JMSReplyTo` or `@SendTo`; for programmatically registered method endpoints, you need to configure the appropriate invocation/response path and check the factory/endpoint implementation being used.

Do not assume `SimpleJmsListenerEndpoint` automatically converts a lambda's return value into a reply. It only accepts a JMS `MessageListener` whose `onMessage` returns `void`.

Listener errors are handled by the container and the transaction policy:

- With a transacted session, an exception can cause the session to roll back and the message to be redelivered according to the provider.
- With automatic acknowledgement, reliability depends on the provider/container semantics; you need to understand the behavior when the listener fails.
- If the listener runs asynchronously, errors cannot be propagated back through the producer's call stack.
- Retries/redelivery can create duplicates; handlers should be idempotent.
- Configure the error handler, dead-letter policy, and observability at the right JMS/provider layer.

Do not treat successful endpoint registration as proof that messages have been processed. Registration only creates the consumer/listener container; business results must be confirmed via logs, replies, events, or application state.

## 14. Common Mistakes

| Symptom | Cause | Resolution |
|---|---|---|
| No messages arrive at the listener | `@EnableJms` is not enabled, the endpoint is not registered, or the container factory is missing | Check the configurer, registrar, and factory |
| `No default JMS listener container factory` | The endpoint does not specify a factory and there is no default factory | Register a factory or pass a factory to `registerEndpoint` |
| Destination is not resolved | Wrong name, wrong Queue/Topic domain, or the broker has not provisioned it | Check the destination resolver and the broker |
| Two endpoints unexpectedly receive the same message | Same destination, same selector, and consumer/topic semantics not designed properly | Check Queue/Topic, subscription, and selector |
| Duplicate endpoint ID | Same ID created in the registry | Generate a stable, unique ID |
| Listener does not run after registration | Container has not started or registry lifecycle has not been activated | Check the registry and container factory |
| Concurrency does not change | The container implementation does not support dynamic scaling or the endpoint does not use the intended factory | Check the actual container type and factory |
| Method endpoint cannot bind parameters | Bean/method or method handler factory has not been set | Check MethodJmsListenerEndpoint and argument resolvers |
| `@Header` does not find a value | The producer did not send the corresponding property/header | Check JMS properties and header name |
| Message is redelivered continuously | The listener keeps throwing an exception in a transacted session | Handle poison messages, retry limits, and DLQ |
| Listener receives the wrong body type | Simple endpoint receives the raw JMS Message | Check the Message type or use a converter/method endpoint |
| Runtime endpoints grow continuously | Repeatedly registering new ones per request or not managing IDs | Only register under a controlled lifecycle and monitor the registry |

## 15. Runnable Java 17+ Example: Registering an Endpoint with Embedded Artemis

The example uses Spring Boot 4.1.2 and embedded ActiveMQ Artemis. `@JmsListener` is not used; the endpoint is created in `configureJmsListeners` and registered through the registrar.

The producer sends a String to `orders.queue`. The default Spring JMS converter converts the String into a `TextMessage`. The simple endpoint receives the raw JMS Message and the listener reads the content.

### Project Structure

~~~text
jms-programmatic-endpoint-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          ProgrammaticJmsApplication.java
          OrderMessageHandler.java
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
    <artifactId>jms-programmatic-endpoint-demo</artifactId>
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

The embedded broker configuration is suitable for demo/test. It does not produce production durability when data is stored in memory.

### OrderMessageHandler.java

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageListener;
import jakarta.jms.TextMessage;

import org.springframework.stereotype.Component;

@Component
public class OrderMessageHandler implements MessageListener {

    private final CountDownLatch received = new CountDownLatch(1);

    @Override
    public void onMessage(Message message) {
        if (!(message instanceof TextMessage textMessage)) {
            throw new IllegalArgumentException("Expected a TextMessage");
        }

        try {
            System.out.println("received=" + textMessage.getText());
            received.countDown();
        }
        catch (JMSException ex) {
            throw new IllegalStateException("Cannot read order message", ex);
        }
    }

    public boolean await(long timeout, TimeUnit unit)
            throws InterruptedException {
        return received.await(timeout, unit);
    }
}
~~~

### ProgrammaticJmsApplication.java

~~~java
package demo;

import java.util.concurrent.TimeUnit;

import jakarta.jms.ConnectionFactory;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.config.JmsListenerConfigurer;
import org.springframework.jms.config.JmsListenerEndpointRegistrar;
import org.springframework.jms.config.SimpleJmsListenerEndpoint;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
@EnableJms
public class ProgrammaticJmsApplication implements JmsListenerConfigurer {

    private final OrderMessageHandler orderMessageHandler;

    public ProgrammaticJmsApplication(OrderMessageHandler orderMessageHandler) {
        this.orderMessageHandler = orderMessageHandler;
    }

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(ProgrammaticJmsApplication.class, args)) {
            // ApplicationRunner waits for the registered endpoint to receive one message.
        }
    }

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setPubSubDomain(false);
        factory.setConcurrency("1");
        return factory;
    }

    @Override
    public void configureJmsListeners(JmsListenerEndpointRegistrar registrar) {
        registrar.setContainerFactoryBeanName("jmsListenerContainerFactory");

        SimpleJmsListenerEndpoint endpoint = new SimpleJmsListenerEndpoint();
        endpoint.setId("programmaticOrdersEndpoint");
        endpoint.setDestination("orders.queue");
        endpoint.setConcurrency("1");
        endpoint.setMessageListener(orderMessageHandler);

        registrar.registerEndpoint(endpoint);
    }

    @Bean
    ApplicationRunner sendOrder(
            JmsTemplate jmsTemplate,
            OrderMessageHandler orderMessageHandler) {

        return args -> {
            jmsTemplate.convertAndSend("orders.queue", "ORD-42");

            if (!orderMessageHandler.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Timed out waiting for the programmatic JMS endpoint"
                );
            }
        };
    }
}
~~~

Run with Java 17+ and Maven:

~~~bash
mvn spring-boot:run
~~~

The stdout line printed by the application (ignoring the Spring Boot startup log):

~~~text
received=ORD-42
~~~

### Explanation of the Execution Flow

1. `@EnableJms` enables the listener endpoint infrastructure and registry.
2. Spring creates `OrderMessageHandler`, an object implementing JMS `MessageListener`.
3. Spring calls `configureJmsListeners` on the application configurer.
4. The configurer sets the default factory by the bean name `jmsListenerContainerFactory`.
5. `SimpleJmsListenerEndpoint` is created with ID `programmaticOrdersEndpoint`, destination `orders.queue`, and the handler.
6. The registrar registers the endpoint. The registry uses the factory to create and manage the listener container.
7. `ApplicationRunner` sends the String `ORD-42` through `JmsTemplate`.
8. The listener container receives the JMS TextMessage and calls `OrderMessageHandler.onMessage`.
9. The handler reads the text, prints the result, and counts down the latch so the runner finishes.
10. The application context closes and the registry stops the listener container according to the lifecycle.

The example shows that the endpoint is registered programmatically even though no method is annotated with `@JmsListener`. The factory decides connection, transaction, and concurrency; the endpoint decides destination and listener.

## 16. Testing Endpoints

You should test these cases:

- The endpoint has a unique ID and the right destination.
- The registrar uses the right default factory or a directly passed factory.
- Messages go to the right Queue/Topic domain.
- The listener receives the right JMS message type and payload.
- The selector filters only the messages that should be received.
- Concurrency is appropriate and the listener is thread-safe.
- A durable subscription has an appropriate subscription name/client ID if using a Topic.
- A listener exception leads to transaction rollback/redelivery per policy.
- The registry starts/stops with the application context.
- Runtime registration does not create duplicate endpoints or exceed configured limits.

For method endpoints, also test:

- The bean and method have been attached properly.
- MethodHandlerMethodFactory has the required argument resolvers.
- Payload conversion and custom header binding work.
- Validation rejects invalid data.
- Reply destination and response converter are configured properly if the method returns a result.

## 17. Deployment Checklist

- [ ] Enable `@EnableJms` to initialize the endpoint infrastructure.
- [ ] Implement `JmsListenerConfigurer` in a Spring-managed bean.
- [ ] Register endpoints in `configureJmsListeners`.
- [ ] Choose `SimpleJmsListenerEndpoint` for a raw `MessageListener`.
- [ ] Choose `MethodJmsListenerEndpoint` for a bean method needing argument binding.
- [ ] Each endpoint has a unique and stable ID.
- [ ] Destination, Queue/Topic domain, and selector are accurate.
- [ ] Choose the default factory or pass a separate factory to the endpoint.
- [ ] Concurrency and transactions are suited to the load.
- [ ] Method endpoints have a `MessageHandlerMethodFactory` if custom conversion/validation is needed.
- [ ] Use `JmsListenerEndpointRegistry` to observe and manage lifecycle.
- [ ] Do not create new endpoints per message/request without limits.
- [ ] Test redelivery, rollback, shutdown, and destination resolution.
- [ ] Do not log raw messages or secrets outside security policy.

## Key Takeaways

- `JmsListenerConfigurer` is a callback to customize the registrar and register JMS endpoints programmatically.
- `JmsListenerEndpointRegistrar` accepts endpoints and selects `JmsListenerContainerFactory`.
- `SimpleJmsListenerEndpoint` attaches a JMS `MessageListener`; `MethodJmsListenerEndpoint` attaches a bean and method.
- An endpoint can configure ID, destination, selector, durable subscription name, and concurrency.
- `JmsListenerEndpointRegistry` creates listener containers and manages lifecycle; these containers are not independent beans in the application context.
- You can combine programmatic endpoints with `@JmsListener`, or use only programmatic registration.
- Register endpoints in the configurer phase at startup; use the registry API if you need to add endpoints at runtime in a controlled manner.
- The factory decides connection, transaction, concurrency, and Queue/Topic domain; the endpoint decides destination and listener.
- `MessageHandlerMethodFactory` controls argument binding, conversion, and validation for method endpoints.

## Official Documentation

- [Spring Framework Reference 7.0: Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/7.0/integration/jms/annotated.html)
- [Spring Framework 7.0.10 Javadoc: JmsListenerConfigurer](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/jms/annotation/JmsListenerConfigurer.html)
- [Spring Framework 7.0.10 Javadoc: JmsListenerEndpointRegistrar](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistrar.html)
- [Spring Framework 7.0.10 Javadoc: JmsListenerEndpoint](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/jms/config/JmsListenerEndpoint.html)
- [Spring Framework 7.0.10 Javadoc: SimpleJmsListenerEndpoint](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/jms/config/SimpleJmsListenerEndpoint.html)
- [Spring Framework 7.0.10 Javadoc: MethodJmsListenerEndpoint](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/jms/config/MethodJmsListenerEndpoint.html)
- [Spring Framework 7.0.10 Javadoc: JmsListenerEndpointRegistry](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistry.html)
- [Spring Framework Reference: Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Spring Boot 4.1 Reference: JMS](https://docs.spring.io/spring-boot/4.1/reference/messaging/jms.html)
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
