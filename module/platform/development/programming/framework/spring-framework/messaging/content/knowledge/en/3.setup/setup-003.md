# Declaring Infrastructure Beans with Java Configuration

## Objectives

After this lesson, you will be able to:

- Explain the roles of `@Configuration`, `@Bean`, and dependency injection when building messaging infrastructure.
- Distinguish Spring Messaging abstractions, Spring Integration components, and broker connection adapters.
- Declare `MessageChannel`, `IntegrationFlow`, and endpoints using Java Configuration.
- Choose the appropriate channel type for dispatching, buffering, and concurrency.
- Declare the required RabbitMQ or JMS beans without hardcoding environment details.
- Verify configuration at startup and avoid common mistakes with beans, channels, threads, and lifecycle.

## 1. Identify the Infrastructure Layer to Configure

The word "messaging" in the Spring ecosystem can refer to several different layers. Before declaring beans, identify which layer the application is using:

| Layer | Role | Example types or APIs |
|---|---|---|
| Spring Messaging | Message model and common communication interfaces | `Message<T>`, `MessageChannel`, `MessageHandler`, `MessageBuilder` |
| Spring Integration | Channels, endpoints, transformers, and integration flows inside the application | `DirectChannel`, `QueueChannel`, `IntegrationFlow`, `@ServiceActivator` |
| Transport adapter / client | Connects to an external system or broker | Spring AMQP, Spring JMS, Spring for Apache Kafka, MQTT adapter |

Spring Framework provides abstractions in the `spring-messaging` module. These interfaces describe messages and how to send messages; they do not by themselves provide a broker, distributed queue, or durable storage mechanism.

Spring Integration builds message-processing components on top of those abstractions. `DirectChannel`, `PublishSubscribeChannel`, and `QueueChannel` are implementations belonging to Spring Integration. The Spring Integration Java DSL allows assembling endpoints into an `IntegrationFlow`.

RabbitMQ, Kafka, or a JMS provider is a separate transport layer. When inter-process communication is required, the application must configure the corresponding client or adapter. An in-memory Spring Integration channel does not automatically become a message broker.

An application can combine all three layers:

~~~text
Business service
    |
    v
Spring Messaging: Message / MessageChannel
    |
    v
Spring Integration: channel -> transform -> handler
    |
    +----> internal processing in ApplicationContext
    |
    +----> outbound adapter -> RabbitMQ / Kafka / JMS
                                  |
                                  v
                             other services
~~~

The following sections focus on how to register beans for these layers using Java Configuration.

## 2. Spring's Java Configuration Mechanism

### @Configuration and @Bean

`@Configuration` marks a class as a source of bean definitions. Each method annotated with `@Bean` creates or configures an object for Spring to manage in the `ApplicationContext`.

~~~java
@Configuration
public class MessagingConfiguration {

    @Bean
    public MessageChannel ordersChannel() {
        return new DirectChannel();
    }
}
~~~

The default bean name is the method name, `ordersChannel` in this example. You can specify a different name with `@Bean("orderInputChannel")` or declare aliases when needed.

Key principles:

1. **Declare an appropriate return type:** use a concrete type when other components need to look up or inject the implementation; use an interface when you want to reduce coupling to the implementation.
2. **Let Spring inject dependencies:** parameters of a `@Bean` method are resolved by Spring from beans in the context, similar to constructor injection.
3. **Do not recreate dependencies yourself:** if a bean needs a `ConnectionFactory`, accept it as a method parameter instead of calling a constructor to create a new connection in multiple places.
4. **Understand configuration class proxies:** `@Configuration` by default uses a proxy mechanism to intercept calls between `@Bean` methods. With `@Configuration(proxyBeanMethods = false)`, direct Java calls between those methods are not intercepted; use method parameters to receive dependent beans.
5. **Pay attention to scope and lifecycle:** beans are singletons by default. For executors, connection factories, or listener containers, configure initialization and resource shutdown according to the context lifecycle.

Example of injecting dependencies via parameters:

~~~java
@Configuration(proxyBeanMethods = false)
public class MessagingConfiguration {

    @Bean
    public MessageConverter messageConverter() {
        return new StringMessageConverter();
    }

    @Bean
    public MessagePublisher messagePublisher(
            MessageChannel ordersChannel,
            MessageConverter messageConverter) {
        return new MessagePublisher(ordersChannel, messageConverter);
    }
}
~~~

The example above illustrates how to pass dependencies; `StringMessageConverter` and `MessagePublisher` are hypothetical types defined by the application. In a real configuration, use the implementation corresponding to the chosen messaging library.

### Splitting Configuration into Multiple Classes

Do not cram all infrastructure into one large configuration class. You can split it by responsibility:

- `MessagingCoreConfiguration`: shared channels and Spring Integration components.
- `OrderFlowConfiguration`: business processing flows for the Order module.
- `RabbitInfrastructureConfiguration`: connection, exchange, queue, binding, and listener container.
- `JmsInfrastructureConfiguration`: `JmsTemplate` and JMS listener container.
- `MessagingProperties`: configuration that can vary by environment.

Use `@Import` to compose configuration classes:

~~~java
@Configuration
@Import({
    MessagingCoreConfiguration.class,
    OrderFlowConfiguration.class
})
public class ApplicationMessagingConfiguration {
}
~~~

This approach ensures an application only imports the infrastructure it actually uses. If there are multiple environments, you can use `@Profile` or Spring Boot's conditional mechanisms to select the appropriate adapter.

## 3. Enabling Spring Integration Infrastructure

When configuring Spring Integration purely in Java, use `@EnableIntegration` on a configuration class:

~~~java
@Configuration
@EnableIntegration
public class IntegrationConfiguration {
    // MessageChannel and IntegrationFlow beans
}
~~~

This annotation registers the foundational infrastructure needed for Spring Integration, including processors supporting endpoints and annotations, default components such as `errorChannel`, and the scheduler infrastructure used for pollers.

`@EnableIntegration` does not connect to RabbitMQ, Kafka, or JMS on its own. It enables Spring Integration infrastructure in the `ApplicationContext`. To send messages over the network, you must declare the corresponding adapter/client and connection.

If the application uses Spring Boot and the Spring Integration starter, some configuration may already be provided by auto-configuration. Before creating beans with duplicate names or duplicate functionality, check which configuration the application already has enabled.

## 4. Declaring MessageChannel as Beans

A `MessageChannel` is the point that receives messages from producers and passes them to consumers. The channel type determines how messages are dispatched or buffered.

### DirectChannel

~~~java
@Bean
public MessageChannel orderInputChannel() {
    return new DirectChannel();
}
~~~

`DirectChannel` is a subscribable channel, typically used for synchronous processing flows. When a producer sends a message, the handler is invoked on the sending thread. If there are multiple subscribers, the dispatcher selects a subscriber to process each message according to the channel's dispatching strategy; by default it provides load balancing and failover.

Use it when a message needs to be handled by one handler in the current flow. This is a common choice for sequential steps in an integration flow.

### PublishSubscribeChannel

~~~java
@Bean
public MessageChannel orderEventsChannel() {
    return new PublishSubscribeChannel();
}
~~~

`PublishSubscribeChannel` broadcasts one message to all registered subscribers. It is suitable when multiple components all need to receive a notification, such as auditing, index updating, and sending internal notifications.

If you pass a `TaskExecutor` to the channel, subscriber processing can be dispatched asynchronously. In that case, consider completion ordering, exception handling, and executor bounds. Without an executor, subscribers typically run on the sending thread.

### QueueChannel

~~~java
@Bean
public PollableChannel pendingOrdersChannel() {
    return new QueueChannel(100);
}
~~~

`QueueChannel` stores messages in a queue so consumers can receive them via poll/receive operations. This is a pollable channel with point-to-point semantics: one message is retrieved by one consumer.

You should set an explicit capacity. An unbounded queue can hold too many messages on the heap when producers outpace consumers. `QueueChannel` stores messages in memory by default; messages can be lost when the process stops. For durable storage, you need to configure an appropriate `MessageStore`, and even then you must evaluate transactions, recovery, and the store's limitations.

### ExecutorChannel

`ExecutorChannel` dispatches messages through a `TaskExecutor`, allowing handlers to run on a different thread. It is useful when decoupling the producer thread from the consumer. However, the executor queue is still an in-process resource; it does not provide durable delivery or inter-process exchange.

### Channel Selection Table

| Channel | Dispatching behavior | Default processing thread | Buffer |
|---|---|---|---|
| `DirectChannel` | One subscriber selected per message | Sending thread | No dedicated queue |
| `PublishSubscribeChannel` | All subscribers | Sending thread if no executor | No dedicated queue |
| `QueueChannel` | One consumer receives each message | Consumer calling receive/poll | In-memory queue or configured store |
| `ExecutorChannel` | One subscriber selected | Executor thread | Depends on executor |

Do not pick a channel just because its name sounds like a queue or topic. Clearly determine how many consumers need to receive each message, whether buffering is needed, whether thread switching is needed, and what the durability requirements are.

## 5. Declaring IntegrationFlow with Java DSL

The Spring Integration Java DSL represents a message flow as an `IntegrationFlow` bean. Steps such as filter, transform, route, and handle are chained in a clear sequence. When the context starts, Spring Integration registers the endpoints and channels needed for the flow.

Example:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableIntegration
public class OrderFlowConfiguration {

    @Bean
    public MessageChannel orderInputChannel() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow orderFlow() {
        return IntegrationFlow.from("orderInputChannel")
                .<String, String>transform(String::trim)
                .filter((String payload) -> !payload.isBlank())
                .handle(String.class, (payload, headers) -> {
                    System.out.println("Handled order: " + payload);
                    return null;
                })
                .get();
    }
}
~~~

Explanation:

- `IntegrationFlow.from("orderInputChannel")` starts the flow from the channel with that name. If a channel bean already exists, the flow uses that bean.
- `transform(String::trim)` transforms the payload before further processing.
- `filter(...)` only allows messages whose payload satisfies the condition to proceed.
- `handle(...)` invokes the final handler. Returning `null` means no reply message is emitted from this endpoint.
- `get()` completes building the flow.

Adjacent steps that do not declare an explicit channel are typically connected by internal channels created by the DSL, which default to `DirectChannel`. If a channel needs to be shared across multiple flows or other beans, declare it as an explicitly named bean and reference it by that name.

You can use `@ServiceActivator`, `@Transformer`, `@Filter`, or `@Router` on beans/methods to declare endpoints via annotations. These endpoint annotations belong to Spring Integration; they are not annotations from the core Spring Messaging module.

## 6. Complete Runnable Example

The following example uses Java 17 and Spring Integration 6.5.2. It creates an internal channel, normalizes the input string, and then handles the message. No RabbitMQ or external broker is required.

Directory structure:

~~~text
java-configuration-messaging/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── MessagingApplication.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>java-configuration-messaging</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.integration</groupId>
            <artifactId>spring-integration-core</artifactId>
            <version>6.5.2</version>
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

File `src/main/java/demo/MessagingApplication.java`:

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public class MessagingApplication {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             MessagingConfiguration.class)) {

            MessageChannel input = context.getBean(
                    "orderInputChannel",
                    MessageChannel.class
            );

            boolean sent = input.send(
                    MessageBuilder.withPayload("  ORD-1001  ").build()
            );

            System.out.println("send returned: " + sent);
        }
    }
}

@Configuration(proxyBeanMethods = false)
@EnableIntegration
class MessagingConfiguration {

    @Bean
    public MessageChannel orderInputChannel() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow orderFlow() {
        return IntegrationFlow.from("orderInputChannel")
                .<String, String>transform(String::trim)
                .handle(String.class, (payload, headers) -> {
                    System.out.println("Handled order: " + payload);
                    return null;
                })
                .get();
    }
}
~~~

Run from the directory containing `pom.xml`:

~~~bash
mvn -q compile org.codehaus.mojo:exec-maven-plugin:3.5.0:java -Dexec.mainClass=demo.MessagingApplication
~~~

Stdout output:

~~~text
Handled order: ORD-1001
send returned: true
~~~

The output shows that the channel bean was registered, the flow was created when the context started, and the message was processed synchronously before the `send()` call returned. If you change `DirectChannel` to `ExecutorChannel`, the moment the handler finishes may occur after `send()` returns.

## 7. Declaring RabbitMQ Infrastructure with Java Configuration

When connecting to a RabbitMQ broker, Spring AMQP provides common beans:

- `ConnectionFactory`: manages connections to the broker.
- `RabbitTemplate`: sends and receives messages in request/reply style or via template operations.
- `Queue`, `Exchange`, `Binding`: describe topology.
- `RabbitAdmin`: declares topology on the broker.
- `SimpleRabbitListenerContainerFactory`: creates listener containers for `@RabbitListener` methods.

The example below assumes a `ConnectionFactory` bean is already provided, for example by Spring Boot from environment configuration:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableRabbit
public class RabbitMessagingConfiguration {

    @Bean
    public Queue ordersQueue() {
        return QueueBuilder.durable("orders.queue").build();
    }

    @Bean
    public DirectExchange ordersExchange() {
        return new DirectExchange("orders.exchange");
    }

    @Bean
    public Binding ordersBinding(
            Queue ordersQueue,
            DirectExchange ordersExchange) {
        return BindingBuilder.bind(ordersQueue)
                .to(ordersExchange)
                .with("orders.created");
    }

    @Bean
    public RabbitAdmin rabbitAdmin(ConnectionFactory connectionFactory) {
        return new RabbitAdmin(connectionFactory);
    }

    @Bean
    public RabbitTemplate rabbitTemplate(
            ConnectionFactory connectionFactory) {
        return new RabbitTemplate(connectionFactory);
    }

    @Bean
    public SimpleRabbitListenerContainerFactory rabbitListenerContainerFactory(
            ConnectionFactory connectionFactory) {
        var factory = new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrentConsumers(2);
        factory.setMaxConcurrentConsumers(5);
        return factory;
    }
}
~~~

Main imports:

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitAdmin;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
~~~

A listener can reference the queue and container factory:

~~~java
@Component
public class OrderListener {

    @RabbitListener(
            queues = "orders.queue",
            containerFactory = "rabbitListenerContainerFactory"
    )
    public void receive(String payload) {
        System.out.println("Received: " + payload);
    }
}
~~~

Deployment notes:

1. `@EnableRabbit` enables detection and registration of `@RabbitListener` endpoints; it does not create a broker or replace `ConnectionFactory`.
2. `RabbitAdmin` can automatically declare topology beans such as queues, exchanges, and bindings when connecting to the broker.
3. A durable queue is only one part of durability. You must configure message persistence, acknowledgements, retries, publisher confirms, and DLQ policies according to business requirements.
4. Do not write usernames, passwords, or sensitive broker addresses in source code. Put them in external configuration, a secret store, or environment variables.
5. With Spring Boot, `ConnectionFactory`, `RabbitTemplate`, `RabbitAdmin`, and listener factories may already be auto-configured. Only declare custom beans when you need to change behavior or the application does not use Boot; avoid creating duplicate beans.
6. Registering `Queue`, `Exchange`, and `Binding` as beans does not mean messages are sent. They describe topology; producers must still call `RabbitTemplate` or an adapter to send messages.

## 8. Declaring JMS Infrastructure with Java Configuration

With a JMS provider, Spring JMS typically uses `jakarta.jms.ConnectionFactory`, `JmsTemplate`, and `DefaultJmsListenerContainerFactory`. The provider is responsible for supplying the actual connection.

~~~java
@Configuration(proxyBeanMethods = false)
@EnableJms
public class JmsMessagingConfiguration {

    @Bean
    public JmsTemplate jmsTemplate(
            jakarta.jms.ConnectionFactory connectionFactory) {
        return new JmsTemplate(connectionFactory);
    }

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            jakarta.jms.ConnectionFactory connectionFactory) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrency("2-5");
        return factory;
    }
}
~~~

A listener can receive messages with `@JmsListener`:

~~~java
@Component
public class BillingListener {

    @JmsListener(
            destination = "billing.events",
            containerFactory = "jmsListenerContainerFactory"
    )
    public void receive(String payload) {
        System.out.println("Billing event: " + payload);
    }
}
~~~

`@EnableJms` enables annotation-driven listener infrastructure; it does not create a JMS broker or supply a connection factory. If using Spring Integration to connect JMS with a flow, you need to add the corresponding adapter/module and configure channels/endpoints for that flow.

## 9. Verifying Configuration at Startup

A good messaging configuration should be verified as soon as the context initializes:

- **Bean existence:** verify bean names and types using `ApplicationContext.getBean(...)` or `getBeansOfType(...)`.
- **Valid dependencies:** verify that each `@Bean` receives the expected `ConnectionFactory`, converter, executor, or channel.
- **Consistent channel names:** `IntegrationFlow.from("...")`, `@ServiceActivator(inputChannel = "...")`, and producers must reference the exact same name.
- **Registered flows:** check startup logs and endpoint beans created by Spring Integration.
- **Broker readiness:** verify connectivity, authentication, exchanges/queues/bindings, and access permissions.
- **Messages flow end-to-end:** send a test message and observe that the handler/consumer receives it.
- **Lifecycle:** closing the context must stop listener containers and executors as configured; do not leave threads or connections alive outside the application lifecycle.

You can write integration tests with `AnnotationConfigApplicationContext` or Spring Test to verify channels and flows. With a real broker, use a test broker or Testcontainers to verify topology, serialization, and acknowledgement. Tests that only check whether beans exist are not enough to prove messages are routed and processed successfully.

## 10. Common Configuration Mistakes

1. **Forgetting `@EnableIntegration` in plain Java configuration.** Annotations/endpoints or the Java DSL may not be processed properly because Spring Integration infrastructure is missing.
2. **Confusing `MessageChannel` with a broker queue.** `DirectChannel` and `QueueChannel` belong to the current process; they do not send messages over the network.
3. **Using `@Configuration(proxyBeanMethods = false)` and calling a `@Bean` method directly.** That call is an ordinary Java method call and may create a new object. Inject beans via method parameters instead.
4. **Declaring a channel whose name does not match the flow.** A typo in `from("...")` or `inputChannel` can prevent endpoints from connecting as expected.
5. **Using an unbounded `QueueChannel`.** Producers can push messages faster than consumers and cause the heap to grow continuously. Set appropriate capacity, timeouts, and back-pressure strategies.
6. **Assuming `QueueChannel` is durable by default.** It stores messages in memory; stopping the process can lose waiting messages.
7. **Using `PublishSubscribeChannel` when only one consumer should receive.** This channel broadcasts to all subscribers; use a channel with point-to-point semantics if only one consumer per message is needed.
8. **Creating an unbounded executor.** Uncontrolled thread and queue growth can exhaust resources. Configure pool size, queue capacity, and rejection policy.
9. **Declaring a listener factory while forgetting to enable annotation support.** RabbitMQ requires `@EnableRabbit`; JMS requires `@EnableJms`.
10. **Creating topology without permission to declare on the broker.** RabbitAdmin needs appropriate permissions to create queues, exchanges, and bindings; verify permissions and resource names in the deployment environment.
11. **Creating beans that collide with auto-configuration.** Check existing beans before replacing them or give custom beans explicit names.
12. **Putting connection details in source code.** Use external configuration and manage secrets per environment.

## 11. Design Checklist

- [ ] Identified whether using Spring Messaging, Spring Integration, or a broker adapter.
- [ ] Enabled the right infrastructure annotation: `@EnableIntegration`, `@EnableRabbit`, or `@EnableJms`.
- [ ] Declared channels with the required semantics: direct, publish-subscribe, queue, or executor.
- [ ] Named beans and channels consistently and traceably.
- [ ] Injected dependencies via `@Bean` method parameters.
- [ ] Avoided calling `@Bean` methods directly when using `proxyBeanMethods = false`.
- [ ] Set queue capacities and executor bounds.
- [ ] Separated broker configuration from internal flow configuration.
- [ ] Moved hosts, credentials, and environment details out of source code.
- [ ] Verified context startup, broker connectivity, topology, and actual message flow.
- [ ] Ensured listener containers, connections, and executors stop properly with the lifecycle.

## 12. Conclusion

Java Configuration turns messaging infrastructure into beans with explicit names, types, and dependencies inside `ApplicationContext`. `@Configuration` and `@Bean` create the components; `@EnableIntegration` enables Spring Integration infrastructure; `MessageChannel` determines how messages move within the application; `IntegrationFlow` chains processing steps; and RabbitMQ or JMS requires its own connection factory, template, topology, and listener container. When designing, distinguish internal channels from inter-process transports, configure bounded resources, and test the entire message path.

## Official References

- [Spring Framework Reference: Using the @Configuration annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/configuration-annotation.html) — configuration classes and dependencies between beans.
- [Spring Framework Reference: Using the @Bean annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html) — bean declaration, dependencies, lifecycle, and scope.
- [Spring Integration Reference: Overview and @EnableIntegration](https://docs.spring.io/spring-integration/reference/overview.html) — infrastructure registered when enabling Spring Integration.
- [Spring Integration Reference: Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html) — Java Configuration for DirectChannel, PublishSubscribeChannel, and QueueChannel.
- [Spring Integration Reference: Working With Message Flows](https://docs.spring.io/spring-integration/reference/dsl/java-flows.html) — declaring IntegrationFlow with Java DSL.
- [Spring Integration Reference: Service Activators and .handle()](https://docs.spring.io/spring-integration/reference/7.0/dsl/java-handle.html) — handling messages with handlers and lambdas.
- [Spring AMQP Reference: Enable Listener Endpoint Annotations](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven/enable.html) — @EnableRabbit and listener container factories.
- [Spring AMQP Reference: AmqpTemplate](https://docs.spring.io/spring-amqp/reference/amqp/template.html) — sending and receiving messages with RabbitTemplate.
