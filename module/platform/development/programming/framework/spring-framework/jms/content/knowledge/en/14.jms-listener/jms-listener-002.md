# Registering DefaultJmsListenerContainerFactory for @JmsListener in Spring JMS

## 1. The Problem: Who Creates and Runs the JMS Listener?

In Spring Framework JMS, a Java method can listen for messages asynchronously just by using an annotation:

~~~java
@Component
public class OrderListener {

    @JmsListener(destination = "orders.incoming")
    public void receive(String body) {
        System.out.println("Received: " + body);
    }
}
~~~

This is a snippet requiring Spring imports and placed inside an application with JMS annotation processing enabled, not a standalone program yet.

However, an annotation does not open a connection to the broker by itself, nor does it manage the JMS Session, MessageConsumer, transactions, threads, network errors, or conversion. Spring needs a **listener container** to perform those tasks. To create a listener container for each @JmsListener according to a unified configuration policy, Spring uses **JmsListenerContainerFactory**.

The standard and most common implementation is:

~~~text
org.springframework.jms.config.DefaultJmsListenerContainerFactory
~~~

This factory creates **DefaultMessageListenerContainer** instances, which are the runtime containers that directly poll/receive JMS messages and then invoke the @JmsListener method. It can apply settings for ConnectionFactory, Queue/Topic, concurrency, transactions, acknowledgement, MessageConverter, DestinationResolver, recovery, and lifecycle.

**Goal of this lesson:** accurately understand how to register DefaultJmsListenerContainerFactory in Spring, choose the bean name/default factory, point listeners to a factory, leverage Spring Boot auto-configuration, and avoid operational pitfalls. At the end, there is a runnable standalone project using Java 17, Spring Boot 3.3, and Apache ActiveMQ Artemis.

## 2. Three Key Layers: Factory, Container, Listener

~~~mermaid
flowchart TD
    A["Spring ApplicationContext"] --> B["@EnableJms / annotation infrastructure"]
    A --> F["Bean: jmsListenerContainerFactory"]
    F --> B
    B --> L1["@JmsListener: orders.incoming"]
    B --> L2["@JmsListener: audit.events"]
    L1 --> C1["DefaultMessageListenerContainer #1"]
    L2 --> C2["DefaultMessageListenerContainer #2"]
    F -.-> C1
    F -.-> C2
    C1 --> J["jakarta.jms.ConnectionFactory → JMS Broker"]
    C2 --> J
    R["JmsListenerEndpointRegistry"] --> C1
    R --> C2
~~~

| Component | Role | Does it directly receive messages? |
| --- | --- | --- |
| @JmsListener | Declares endpoint, destination, selector, factory | No. |
| DefaultJmsListenerContainerFactory | Creates the container and attaches configuration policies | No; it creates the container. |
| DefaultMessageListenerContainer | Holds connection/session/consumer, receives and passes messages to the listener | Yes. |
| JmsListenerEndpointRegistry | Manages/retrieves containers by endpoint ID, lifecycle | Does not convert payloads itself. |
| JmsTemplate | Template for sending or synchronous receiving from application code | Separate from listener factory. |
| JMS ConnectionFactory | Creates JMS connections to the broker | Not a factory for creating listener containers. |

This is a foundational distinction. Registering a factory as a Spring bean **does not mean** all listeners are already registered; @JmsListener must still be discovered by Spring and the JMS annotation infrastructure must be active.

### 2.1. Processing Sequence

1. Spring initializes the ConnectionFactory along with configuration beans.
2. `@EnableJms` or Spring Boot auto-configuration activates annotation-driven JMS.
3. Spring scans bean methods with `@JmsListener`, turning each annotation into endpoint metadata.
4. The infrastructure selects a JmsListenerContainerFactory for the endpoint.
5. The factory creates a DefaultMessageListenerContainer with the configured settings.
6. The container starts according to the Spring lifecycle, connects to the broker, and registers/receives messages from the destination.
7. When the broker delivers a message, the container calls the message handler method via an adapter/converter.
8. On success/error, the container handles acknowledge/commit/rollback/recovery according to configuration.

The factory is reused to create containers sharing the same policy; actual containers and consumers exist with their own lifecycle per listener endpoint.

## 3. Packages and Classes to Import Correctly

| Name | Package | Meaning |
| --- | --- | --- |
| DefaultJmsListenerContainerFactory | org.springframework.jms.config | Creates DefaultMessageListenerContainer. |
| JmsListenerContainerFactory | org.springframework.jms.config | General factory interface. |
| DefaultMessageListenerContainer | org.springframework.jms.listener | Runtime consumer container. |
| @JmsListener | org.springframework.jms.annotation | Method annotation for receiving JMS messages. |
| @EnableJms | org.springframework.jms.annotation | Enables annotation infrastructure. |
| JmsListenerConfigurer | org.springframework.jms.annotation | Customizes registrar/default factory or endpoints. |
| JmsListenerEndpointRegistrar | org.springframework.jms.config | Registrar passed to the configurer. |
| JmsListenerEndpointRegistry | org.springframework.jms.config | Queries/starts/stops annotated listener containers. |
| ConnectionFactory | jakarta.jms | JMS API for creating connections/contexts. |
| MessageConverter | org.springframework.jms.support.converter | JMS Message ↔ Java payload. |
| DestinationResolver | org.springframework.jms.support.destination | Converts String name into JMS Destination. |

With **Spring Framework 6.x/Spring Boot 3.x**, import JMS from jakarta.jms.*, **do not use javax.jms.*** from Spring Framework 5.

The class name DefaultJmsListenerContainerFactory looks very similar to DefaultMessageListenerContainer. Distinguish the two when debugging: one is the **bean factory**, and the other is the **runtime listener** created by the factory.

## 4. Default Registration in Spring Framework

When a @JmsListener does not specify containerFactory, Spring looks by default for a Spring bean named **jmsListenerContainerFactory**.

A standard configuration:

~~~java
package example.config;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
public class JmsConfig {

    @Bean("jmsListenerContainerFactory")
    public DefaultJmsListenerContainerFactory listenerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1-3");
        return factory;
    }
}
~~~

This is a **compilable configuration class** if the project has Spring JMS dependencies and a ConnectionFactory bean registered. It is not a full runnable project without a provider/broker.

Explanation of key points:

- @Configuration: Spring recognizes the class as containing bean definitions.
- @EnableJms: activates the infrastructure for processing annotated JMS endpoints.
- @Bean("jmsListenerContainerFactory"): registers **the exact default bean name**.
- setConnectionFactory: points to the JMS broker via the injected ConnectionFactory.
- setPubSubDomain(false): uses Queue domain when resolving names dynamically.
- setSessionTransacted(true): local JMS transaction, suitable when rollback/redelivery is needed.
- setConcurrency("1-3"): gives a container a minimum of 1 and maximum of 3 concurrent consumers depending on workload.

You can use a method with the exact name so Spring uses the method name as the bean name:

~~~java
@Bean
public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory cf) {
    DefaultJmsListenerContainerFactory f =
            new DefaultJmsListenerContainerFactory();
    f.setConnectionFactory(cf);
    return f;
}
~~~

This snippet is shorter but depends on the method name; if refactoring renames the method without updating @JmsListener, it can break the bean name contract. In larger projects, using an explicit bean name is usually easier to review.

### 4.1. Is Registering the Factory Alone Enough?

No. In plain Spring Framework you need:

1. Compatible Jakarta JMS provider/client library.
2. Spring JMS on the classpath.
3. A ConnectionFactory bean connecting to the right broker.
4. JMS annotation infrastructure enabled, typically via @EnableJms.
5. A suitable JmsListenerContainerFactory.
6. A Spring-managed @Component/@Service bean with @JmsListener methods.

If OrderListener is created manually with new without being managed by Spring, the annotation will not be scanned into an endpoint. If the broker is not running, the factory bean can be created, but the listener container cannot receive messages.

## 5. Selecting a Specific Factory on @JmsListener

For example, if you want to dedicate a factory with separate concurrency for high-priority work:

~~~java
@Component
public class PriorityOrderConsumer {

    @JmsListener(
        id = "priorityOrderConsumer",
        destination = "orders.priority",
        containerFactory = "priorityListenerFactory")
    public void handle(String text) {
        // Process high-priority order.
    }
}
~~~

This is a snippet; it requires importing @Component and @JmsListener. The containerFactory value is the **Spring bean name**, not a fully-qualified class name or queue name.

Register the corresponding bean:

~~~java
@Bean("priorityListenerFactory")
DefaultJmsListenerContainerFactory priorityListenerFactory(
        ConnectionFactory connectionFactory) {
    DefaultJmsListenerContainerFactory f =
            new DefaultJmsListenerContainerFactory();
    f.setConnectionFactory(connectionFactory);
    f.setSessionTransacted(true);
    f.setPubSubDomain(false);
    f.setConcurrency("2-6");
    return f;
}
~~~

This is a snippet inside a @Configuration class, without a standalone main().

If a listener omits containerFactory, it uses the default jmsListenerContainerFactory (or the default factory specified by the registrar). **Do not assume @Primary on a bean of the same type always determines the factory for an endpoint.** The annotated endpoint mechanism has its own bean name convention.

### 5.1. Can One Application Have Multiple Factories?

Yes. Different workloads may need different policies:

| Factory bean name | Domain | Concurrency | Purpose |
| --- | --- | --- | --- |
| jmsListenerContainerFactory | Queue | 1-3 | Default consumer. |
| bulkListenerFactory | Queue | 3-10 | Independent batch jobs, high throughput. |
| financeListenerFactory | Queue | 1 | Work requiring ordering/strict control. |
| topicListenerFactory | Topic | 1 | Event subscriptions. |

The table is only an **architectural example**, not a mandatory configuration. For Topic durable/shared subscriptions, you must add other settings and consider provider limits; do not take high concurrency from a queue factory and assume topics behave identically.

## 6. Role of Spring Boot Auto-Configuration

### 6.1. Spring Boot Can Pre-Register the Factory

In a Spring Boot application with a JMS starter and suitable ConnectionFactory, Boot usually automatically creates JmsTemplate and the default JMS listener container factory. According to Spring Boot documentation, annotated listeners can also be enabled automatically; **it is not strictly necessary to add @EnableJms** for a typical Boot app.

Dependency example:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-artemis</artifactId>
</dependency>
~~~

Then @JmsListener(destination="orders.incoming") can work without explicitly declaring a factory bean.

**However**, when you create a bean named jmsListenerContainerFactory, Boot auto-configuration will typically back off conditionally. At that point, options you have not configured may **not** automatically match Boot defaults. Do not define a manual bean and still assume Boot always applies all spring.jms.listener.* properties.

### 6.2. When Should You Choose a Manual Factory?

Create a manual factory when you have specific needs such as:

- Local transactions or an external transaction manager.
- Different concurrency for different workload groups.
- Queue/Topic domain and custom subscriptions.
- DestinationResolver for JNDI or naming policies.
- MessageConverter/Jackson, reply QoS, validation.
- ErrorHandler, recovery backoff, polling timeout, task executor.
- Using a native ConnectionFactory or JTA-managed resources.
- Custom start/stop policy, operations, and listener-level monitoring.

If Boot's defaults already fit, **there is no need to write a factory just to have a visible bean in source code**.

## 7. Leveraging DefaultJmsListenerContainerFactoryConfigurer in Spring Boot 3.x

Spring Boot provides **DefaultJmsListenerContainerFactoryConfigurer** to apply the defaults and properties Boot has computed onto a factory you create, so you only override what differs. This is the most useful approach when an app has multiple listener factories.

**Import for Spring Boot 3.x:**

~~~java
import org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer;
~~~

In Spring Boot 4.x, the related package changed; do not blindly use Boot 4 API docs to compile a Boot 3.3 project.

Example:

~~~java
@Configuration
class ListenerFactories {

    @Bean("bulkListenerFactory")
    DefaultJmsListenerContainerFactory bulkFactory(
            ConnectionFactory connectionFactory,
            DefaultJmsListenerContainerFactoryConfigurer configurer) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        configurer.configure(factory, connectionFactory);
        factory.setConcurrency("3-8");
        factory.setPubSubDomain(false);
        return factory;
    }
}
~~~

This snippet needs imports for Configuration, Bean, ConnectionFactory, and DefaultJmsListenerContainerFactory; it illustrates an important order:

1. Create a new factory.
2. Call configurer.configure(factory, connectionFactory) to receive Boot defaults.
3. **Then** override setConcurrency/setPubSubDomain for the specific factory.

If you call overrides before configure, configure may reset some settings, leading to unintended behavior.

### 7.1. CachingConnectionFactory and Native Connections

DefaultMessageListenerContainer manages connection recovery and appropriate JMS resource caching on its own. Boot usually recommends that listener containers work with a native ConnectionFactory rather than accidentally sharing a caching wrapper intended for producers.

In Spring Boot 3.x there is a helper:

~~~java
import org.springframework.boot.jms.ConnectionFactoryUnwrapper;

configurer.configure(
        factory,
        ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));
~~~

This is a snippet. Inspect the actual ConnectionFactory: JTA/XA providers, connection pools, and caching wrappers have different characteristics. **Do not arbitrarily unwrap every kind of wrapper** if special transaction integration is involved.

### 7.2. Which Boot Properties Are Relevant?

~~~properties
spring.jms.listener.min-concurrency=2
spring.jms.listener.max-concurrency=6
spring.jms.listener.auto-startup=true
~~~

These properties can be applied by the Boot configurer to the default factory. If you create a manual factory and **do not use the configurer**, do not expect them to always be applied. Test the runtime configuration and check against the exact Boot version.

When an application has both producers and listeners, **JmsTemplate** properties (for example, receive timeout for the template) are not all **listener container** properties; the two components have different lifecycles.

## 8. Important Settings of DefaultJmsListenerContainerFactory

| Setting | Effect | Notes |
| --- | --- | --- |
| setConnectionFactory | JMS connection resource | Must match broker/credentials and topology with producer. |
| setPubSubDomain | Queue or Topic | false queue, true topic when resolving names accordingly. |
| setDestinationResolver | String name → Destination | Dynamic/JNDI/custom resolver depending on deployment. |
| setMessageConverter | JMS Message ↔ Java payload | Must align with method signature and sender converter. |
| setSessionTransacted | Local JMS transaction | Listener errors can trigger rollback/redelivery. |
| setSessionAcknowledgeMode | JMS acknowledge mode | Not identical to local JMS transaction. |
| setTransactionManager | External Spring transaction manager | Only achieves XA when infrastructure/resources truly support it. |
| setConcurrency | Number of concurrent consumers | Affects throughput, ordering, and broker resources. |
| setReceiveTimeout | Receive polling timeout | Different from message TTL and business timeout. |
| setRecoveryInterval / setBackOff | Recovery after connection failure | Depends on provider and operational policy. |
| setCacheLevel | Cache JMS handles | Consider transaction manager, pooling, and container lifecycle. |
| setTaskExecutor | Executor running invoker tasks | Thread pool needs sufficient resources and safe bounds. |
| setErrorHandler | Logs/observes listener exceptions | Does not replace transaction/redelivery policy. |
| setAutoStartup | Auto-starts container per lifecycle | Useful for phased rollout or maintenance. |
| setReplyQosSettings | QoS of response messages | Does not apply to input message TTL. |

Some setters are inherited from AbstractJmsListenerContainerFactory, while others are specific to DefaultJmsListenerContainerFactory. **You do not need to call every setter in every configuration.** Start with well-understood ConnectionFactory, transaction, and concurrency settings, then expand according to tested requirements.

## 9. Concurrency: setConcurrency("min-max") and Consequences

~~~java
factory.setConcurrency("3-10");
~~~

For each DefaultMessageListenerContainer created from the factory, this is the policy for the number of consumers from core/minimum to maximum. It does **not** mean "the entire application has at most 10 consumers".

For example, if 4 @JmsListener endpoints share a 3-10 factory, the total number of sessions/consumers can exceed 10. The actual number of consumers also depends on load, executor, broker, constraints, and scaling strategy.

### 9.1. With Multiple Consumers, Ordering Changes

~~~text
Queue delivers message A → consumer #1 processes for 2 seconds.
Queue delivers message B → consumer #2 processes for 100 ms.

B can finish before A.
~~~

If a workflow requires updating order status strictly in order, do not increase concurrency without an ordering strategy. Some brokers support message grouping such as JMSXGroupID, but integration tests are required to prove behavior in the running topology.

### 9.2. Annotation Concurrency Can Override the Factory

~~~java
@JmsListener(
    destination = "orders.bulk",
    containerFactory = "bulkListenerFactory",
    concurrency = "2-5")
public void onBulk(String body) { /* ... */ }
~~~

This is a snippet. Concurrency declared on the endpoint can override the factory default for that listener. If architecture manages concurrency centrally, avoid unreviewed scattered overrides.

### 9.3. Topics Are Not Like Queues

With a Queue, adding consumers is typically the competing-consumer pattern. With a Topic, semantics are subscription-based; multiple consumers on a non-shared subscription can cause duplicate deliveries or provider errors. Durable subscriptions also require identity/clientId and subscription names managed according to JMS provider rules.

Do not apply a queue's setConcurrency("3-10") to a topic without designing shared/durable subscriptions. Topic factories are usually kept separate and tested against a real broker.

## 10. Transactions and Acknowledgement

### 10.1. Local JMS Transaction

~~~java
factory.setSessionTransacted(true);
~~~

With DefaultMessageListenerContainer, this allows each listener invocation to receive a message within a local JMS transaction. When the method finishes normally and commits, the message is acknowledged under the transaction. When an appropriate error escapes, the transaction can roll back; the broker redelivers according to policy.

This does **not** turn message processing into end-to-end exactly-once. Consumers need an idempotency key because a message may be received again after a rollback or a failure between a side effect and commit.

### 10.2. If the Listener Swallows Exceptions

~~~java
@JmsListener(destination = "orders.incoming")
public void handle(String body) {
    try {
        processOrder(body);
    } catch (RuntimeException ex) {
        // If you only log and return, the container may treat it as a success.
    }
}
~~~

This is an anti-pattern: if business logic requires retry, exceptions must propagate or have an explicit failure policy. Logging and returning normally inside a transacted session can cause the container to commit despite failed processing.

### 10.3. AUTO_ACKNOWLEDGE and the Risk of Losing Redelivery

In DefaultMessageListenerContainer, AUTO_ACKNOWLEDGE has semantics where acknowledgement occurs before the user listener executes; thus listener errors may not result in redelivery. Spring recommends setSessionTransacted(true) or an appropriate transaction manager when reliable rollback is required.

Do not change the ack mode based solely on constant names; the JMS provider, container class, and transaction config jointly determine actual behavior.

### 10.4. External Transaction Manager

~~~java
factory.setTransactionManager(jmsTransactionManager);
~~~

The snippet requires an injected PlatformTransactionManager compatible with the resources. A local JmsTransactionManager can manage JMS but **does not automatically bundle a JDBC database** into the same transaction. Achieving XA/JTA atomicity between JMS and DB requires a JTA coordinator, XA-capable ConnectionFactory/DataSource, and suitable infrastructure.

In systems that do not need or cannot use XA, a transactional outbox + idempotency/reconciliation architecture is usually more practical. Regardless of approach, you need retry limits, redelivery backoff, poison message handling, and a DLQ policy on the broker.

### 10.5. Boot Default Differs from a Manual Factory

Spring Boot's default JMS listener factory may be configured as transactional according to Boot's policy. If you replace it with a manual bean that only calls setConnectionFactory, **do not** assume the auto-configured transactional policy and transaction manager still apply as before. Use the configurer if you want to preserve Boot defaults, then override explicitly.

## 11. MessageConverter and Method Signatures

~~~java
@JmsListener(destination = "orders.incoming")
public void receive(String body) {
    // TextMessage can be converted to String.
}
~~~

Spring's default SimpleMessageConverter handles standard JMS Message types such as TextMessage, BytesMessage, and MapMessage as String/byte[]/Map respectively. If a producer sends JSON in a TextMessage, the default converter usually returns a String and **does not automatically deserialize it into an arbitrary record**.

### 11.1. Configuring Jackson MessageConverter

~~~java
@Bean
MessageConverter converter(ObjectMapper mapper) {
    MappingJackson2MessageConverter c =
            new MappingJackson2MessageConverter();
    c.setObjectMapper(mapper);
    c.setTargetType(MessageType.TEXT);
    c.setTypeIdPropertyName("PayloadType");
    c.setTypeIdMappings(
            Map.of("order-created-v1", OrderCreatedEvent.class));
    return c;
}
~~~

This is a snippet inside @Configuration with Spring JMS/Jackson/java.util.Map imports and an OrderCreatedEvent DTO available. According to Spring JMS, MappingJackson2MessageConverter typically requires a type-id property to convert from a JMS message to the right DTO class.

With a manual factory:

~~~java
factory.setMessageConverter(converter);
~~~

This is a snippet using the injected converter bean. If the Boot configurer is used, an auto-configured converter is usually applied to the factory based on beans/properties; verify this when creating custom factories.

**Important:** configuring a converter on the listener factory **does not automatically change** a JmsTemplate bean created separately by the application. Producer and consumer must agree on wire format, target type, type ID, and Jackson settings.

### 11.2. @Header, @Payload, and jakarta.jms.Message

@JmsListener can accept String/DTO, raw jakarta.jms.Message, jakarta.jms.Session, or annotated parameters like @Header. Spring Messaging argument resolution runs on top of the JMS layer, so a "could not resolve method argument" exception is not necessarily a broker error.

With DTOs, validate the payload right at the consumer boundary; the message converter does not enforce business semantics for nulls, monetary amounts, timestamps, and business schema versions.

## 12. DestinationResolver and Selectors in the Listener Factory

### 12.1. DestinationResolver

String names in @JmsListener are converted into jakarta.jms.Destination by the container's DestinationResolver. You can configure:

~~~java
factory.setDestinationResolver(
        new DynamicDestinationResolver());
~~~

This is a snippet; import org.springframework.jms.support.destination.DynamicDestinationResolver. In enterprise/JNDI deployments, it can be replaced with JndiDestinationResolver or a custom resolver.

**Do not confuse:** calling only jmsTemplate.setDestinationResolver(...) does not make @JmsListener endpoints automatically use that resolver. Producer JmsTemplate and the listener factory must be configured consistently so one side does not send to a physical queue while the other looks up a different JNDI name.

### 12.2. Selector

~~~java
@JmsListener(
    destination = "orders.incoming",
    selector = "EventType = 'ORDER_CREATED'",
    containerFactory = "jmsListenerContainerFactory")
public void handle(String payload) { /* ... */ }
~~~

Selectors filter based on JMS headers/properties, not by querying a JSON body directly. If the producer does not attach the EventType property with the right type, the message will not match even if the JSON body contains a similar eventType field.

### 12.3. Reply QoS

The factory can configure delivery quality of service for response messages from annotated endpoints when using @SendTo or JMSReplyTo:

~~~java
QosSettings replyQos = new QosSettings();
replyQos.setPriority(2);
replyQos.setTimeToLive(10_000L);
factory.setReplyQosSettings(replyQos);
~~~

This is a snippet; QosSettings is in org.springframework.jms.support.QosSettings. It does not change the TTL or priority of **incoming messages**.

## 13. Runnable Java 17 Project: Spring Boot 3.3 + ActiveMQ Artemis

This demo proves that the jmsListenerContainerFactory bean is registered and actually creates a container that receives messages via @JmsListener. We use a String payload to focus on registration/lifecycle without adding a JSON converter.

### 13.1. Preparing the Broker

Requires JDK 17+, Maven, Docker, and free TCP port 61616. Start the Artemis broker:

~~~bash
docker run --detach --rm --name jms-factory-lab \
  -p 61616:61616 -p 8161:8161 \
  apache/artemis:latest-alpine
~~~

Wait for the broker to finish starting; you can view logs with docker logs jms-factory-lab. Demo images often configure credentials artemis/artemis for learning environments; do not use demo credentials in production.

The broker must allow using or auto-creating queue demo.factory.orders. Run the project against a **clean** broker/queue to avoid leftover messages from earlier runs.

Directory structure:

~~~text
spring-jms-factory-lab/
├── pom.xml
└── src/main/
    ├── java/example/jmsfactory/
    │   ├── JmsFactoryLabApplication.java
    │   ├── JmsFactoryConfiguration.java
    │   └── OrderReceiver.java
    └── resources/application.properties
~~~

### 13.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>spring-jms-factory-lab</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
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

This is a pinned version to reproduce the Spring Framework 6.x/Jakarta JMS demo. When moving to production, choose a maintained Spring Boot release and test dependency security per organizational policy.

### 13.3. application.properties

~~~properties
spring.main.web-application-type=none
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis
~~~

No web server is started. The program sends a message from CommandLineRunner after the Spring context initializes and the listener container auto-starts per lifecycle.

### 13.4. JmsFactoryConfiguration.java

~~~java
package example.jmsfactory;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
public class JmsFactoryConfiguration {

    @Bean("jmsListenerContainerFactory")
    public DefaultJmsListenerContainerFactory listenerFactory(
            ConnectionFactory cf) {

        DefaultJmsListenerContainerFactory f =
                new DefaultJmsListenerContainerFactory();
        f.setConnectionFactory(cf);
        f.setPubSubDomain(false);
        f.setSessionTransacted(true);
        f.setConcurrency("1");
        f.setReceiveTimeout(1_000L);
        return f;
    }
}
~~~

This is a complete Java file. The factory bean has the exact name jmsListenerContainerFactory so the listener does not need to declare containerFactory. setConcurrency("1") keeps the demo simple and avoids unnecessary extra sessions/consumers. Local JMS transactions enable ack/rollback per transaction.

### 13.5. OrderReceiver.java

~~~java
package example.jmsfactory;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderReceiver {

    private final CountDownLatch latch = new CountDownLatch(1);
    private final AtomicReference<String> last =
            new AtomicReference<>();

    @JmsListener(
        id = "orderEndpoint",
        destination = "demo.factory.orders")
    public void onOrder(String payload) {
        last.set(payload);
        latch.countDown();
    }

    public boolean waitForMessage(long seconds)
            throws InterruptedException {
        return latch.await(seconds, TimeUnit.SECONDS);
    }

    public String getLast() {
        return last.get();
    }
}
~~~

This class is a Spring @Component, component-scanned by @SpringBootApplication in the parent package. The listener method receives String thanks to the default converter for TextMessage.

CountDownLatch and AtomicReference are tools **only for deterministic illustrative output**; they are not a production job tracking system or ack logic.

### 13.6. JmsFactoryLabApplication.java

~~~java
package example.jmsfactory;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class JmsFactoryLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsFactoryLabApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(JmsTemplate template, OrderReceiver receiver) {
        return args -> {
            template.convertAndSend(
                    "demo.factory.orders", "ORDER-42");
            System.out.println("sent: ORDER-42");

            if (!receiver.waitForMessage(10)) {
                throw new IllegalStateException(
                        "Listener did not receive within 10 seconds");
            }
            System.out.println(
                    "listener received: " + receiver.getLast());
        };
    }
}
~~~

Explanation:

1. Boot creates ConnectionFactory and JmsTemplate from the Artemis starter.
2. Spring creates JmsFactoryConfiguration and the jmsListenerContainerFactory bean.
3. @EnableJms/Boot infrastructure detects @JmsListener on OrderReceiver.
4. The factory produces a DefaultMessageListenerContainer and the listener starts.
5. CommandLineRunner sends a TextMessage containing ORDER-42 to the queue.
6. The container receives the message, converts the payload to String, and invokes OrderReceiver.onOrder.
7. CountDownLatch opens, and CommandLineRunner prints the received result. If the listener does not run or receive within 10 seconds, the program throws an error.

**Important note:** the latch counts down when the handler runs, which is not yet proof that the transaction committed successfully in the broker. The demo only verifies that the listener was registered and invoked. Proving ack/commit/idempotency requires dedicated integration tests.

### 13.7. Running and Output

In the directory containing pom.xml:

~~~bash
mvn spring-boot:run
~~~

When the broker is running properly, the queue is clean, and there are no competing consumers, the two lines printed by the application itself are:

~~~text
sent: ORDER-42
listener received: ORDER-42
~~~

Spring Boot/Artemis may log additional lines. Because the listener container is a continuously running component, the process **may keep running** after those two lines; press Ctrl+C to stop the app when finished checking. Stop the broker afterward:

~~~bash
docker stop jms-factory-lab
~~~

### 13.8. Useful Experiments

- Rename the @Bean to ordersFactory without changing @JmsListener: check startup/factory resolution; Spring Boot may auto-register another default depending on conditions, so **verify the actual beans** instead of guessing.
- Keep the bean name ordersFactory and set containerFactory="ordersFactory" on the annotation; observe the listener using that factory.
- Change setConcurrency("1") to "2-4", send many messages; observe throughput/ordering.
- Try sending a bytes message while the method expects String; check the converter and logs.
- Have the listener throw RuntimeException while the Session is transacted; observe broker redelivery/DLQ.
- Switch the domain to Topic while the sender still uses Queue; explain why the two sides fail to communicate properly.
- Use JmsListenerEndpointRegistry to fetch endpoint "orderEndpoint" and check isRunning.

## 14. Managing Listener Containers with JmsListenerEndpointRegistry

A factory bean is a template for creating containers; containers generated by the annotation infrastructure can be managed through the registry.

~~~java
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.listener.MessageListenerContainer;

MessageListenerContainer container =
        registry.getListenerContainer("orderEndpoint");

if (container != null) {
    System.out.println(container.isRunning());
}
~~~

This snippet assumes registry is an injected JmsListenerEndpointRegistry bean; it is not a standalone runnable file.

During maintenance, the registry provides start()/stop() operations for registered listener containers:

~~~java
registry.stop();
registry.start();
~~~

**Do not use stop/start as a way to delete messages.** Messages remain subject to broker policies, prefetch/in-flight delivery, and JMS transactions. During rolling deployments, use graceful shutdown, readiness/drain, and controlled timeouts.

If @JmsListener does not declare an id, Spring can generate an internal id; for systems requiring runtime management, assign a **unique and stable** id for easier monitoring. Endpoint id is not synonymous with destination name.

## 15. When Do You Need JmsListenerConfigurer?

The @Bean named jmsListenerContainerFactory approach is the simple path. For special requirements, JmsListenerConfigurer lets you configure JmsListenerEndpointRegistrar to select a default factory or register endpoints programmatically.

~~~java
@Configuration
@EnableJms
class RegistrarConfig implements JmsListenerConfigurer {

    private final JmsListenerContainerFactory<?> selectedFactory;

    RegistrarConfig(
            @Qualifier("priorityListenerFactory")
            JmsListenerContainerFactory<?> selectedFactory) {
        this.selectedFactory = selectedFactory;
    }

    @Override
    public void configureJmsListeners(
            JmsListenerEndpointRegistrar registrar) {
        registrar.setContainerFactory(selectedFactory);
    }
}
~~~

This is a snippet requiring imports for @Configuration, @EnableJms, @Qualifier, and JmsListenerConfigurer/JmsListenerEndpointRegistrar/JmsListenerContainerFactory. The priorityListenerFactory bean must exist; this code does not create the factory itself.

JmsListenerConfigurer can also register SimpleJmsListenerEndpoint programmatically. Use it only when registration is driven by runtime metadata or when changing the default factory for a clear reason; there is no need to overcomplicate applications with only a few @JmsListener methods.

## 16. Common Errors and How to Debug

| Symptom | Possible Cause | How to Verify |
| --- | --- | --- |
| Annotation exists but method does not run | JMS infrastructure not enabled, bean outside component scan | Check @EnableJms or Boot auto-config, component scan. |
| Default factory not found | Bean not named jmsListenerContainerFactory | Check BeanFactory and containerFactory attribute. |
| Multiple factories exist but wrong one used | Endpoint does not specify factory | Set exact containerFactory, check registry/container. |
| Manually created bean ignores Boot properties | Not using configurer | Use Boot configurer or set properties manually. |
| Sending succeeds but nothing received | Wrong broker, destination, queue/topic, selector, or ACL | Compare ConnectionFactory, DestinationResolver, and broker stats. |
| Listener throws conversion error | Converter/argument mismatch | Check Message type, Jackson type ID, DTO, logs. |
| Error in handler without redelivery | AUTO_ACKNOWLEDGE, swallowed exception | Use proper transaction policy and let errors propagate. |
| Message processed repeatedly after restart | JMS redelivery or retry | Add idempotency and broker DLQ/retry config. |
| High concurrency breaks ordering | Multiple competing consumers | Lower concurrency or design grouping/partitioning. |
| Topic receives messages incorrectly | Wrong subscription/shared/durable config | Separate topic factory and test with a real broker. |
| Resource leak/too many sessions | Caching wrapper/lifecycle or too many endpoints | Check native ConnectionFactory and container cache. |
| Factory fails to connect at startup | Broker not running/bad credentials | Check connection URL, recovery logs, firewall, ACL. |
| Listener container not found as a bean | Container created by infrastructure, managed by registry | Query JmsListenerEndpointRegistry. |
| Selector runs but does not match | Missing/wrong-type property, JSON field is not a JMS property | Inspect message headers/properties. |
| Container stopped but messages remain | Stopping does not clear the queue, messages stay on broker | Use broker metrics; it does not auto-purge. |
| @Transactional enabled but DB/JMS not atomic | Only local transaction manager present | Design outbox/JTA-XA per actual requirements. |

### 16.1. Ordered Debugging Checklist

1. Is there a real ConnectionFactory bean and is it connecting to **the right broker**?
2. Does the ApplicationContext have the factory bean with the right name and type?
3. Has @EnableJms/Boot infrastructure detected the @JmsListener method?
4. Does @JmsListener have the right id, destination, selector, and containerFactory?
5. Can the Registry find the container by endpoint id, and what is container.isRunning()?
6. Does the JMS broker have the right queue/topic, subscriber/consumer, ACL, and routing?
7. Do the listener converter/DTO/arguments match the message type?
8. Do transaction/ack/rollback, retry, DLQ, and exception handling follow policy?
9. Do concurrency/executor/cache cause starvation or race/ordering issues?
10. Do sender/consumer deployment versions share the same destination name and payload contract?

## 17. Production Design Decisions

### 17.1. Do Not Turn the Factory into a Runtime-Mutable Singleton

The factory is usually configured **at bootstrap** before it creates listener containers. Calling factory.setConcurrency(...) after containers have already been created is not a reliable way to update all running runtime containers. If dynamic concurrency changes are needed, use the container's appropriate management API, restart/rollout, or a verified config strategy rather than mutating the bean and expecting every listener to update itself.

### 17.2. Use Separate Factories for Genuinely Different Policies

One factory for all listeners is simple and easy to maintain. Multiple factories make sense when:

- Workloads need different queues/topics.
- Concurrency/SLA requirements differ.
- Transaction managers or security/connection factories differ.
- Converters/payload versions differ.
- Retry/error/lifecycle needs to be cleanly separated.

Do not create dozens of factories just because each listener has a different queue; destination is normally an attribute of @JmsListener, whereas the factory manages **shared policy**.

### 17.3. Do Not Use Selectors as a Security Boundary

If a listener uses selector TenantId = 'A', that is only delivery filtering, **not a substitute for broker ACLs/credentials or tenant isolation**. Connecting the factory with an account having appropriate permissions is a true enforcement layer. Never log sensitive payloads in ErrorHandler without masking.

### 17.4. Operational Monitoring

At a minimum, you should monitor:

- Broker connection/session/consumer count.
- Queue depth, message age, processing rate, expiry count.
- Listener container started/stopped, recovery attempts.
- Failed processing, redelivery, DLQ/quarantine count.
- End-to-end latency, idempotency conflicts.
- Thread/executor saturation, DB pool utilization.
- Schema conversion/validation errors.

Do not merely count "how many times the listener method was called" to conclude that business transactions committed successfully.

## 18. Self-Check Questions

**1. Is DefaultJmsListenerContainerFactory the container that directly receives messages?** No. It creates a DefaultMessageListenerContainer for the endpoint.

**2. What is the default bean name that @JmsListener looks for?** jmsListenerContainerFactory, unless the endpoint/registrar specifies a different factory.

**3. Does Spring Boot always require @EnableJms?** No. Boot auto-configuration can enable the JMS annotated listener infrastructure; plain Spring Framework usually needs @EnableJms.

**4. When should you use DefaultJmsListenerContainerFactoryConfigurer?** When creating a custom factory in Boot while wanting to inherit defaults/properties instead of resetting them manually.

**5. What does @JmsListener(containerFactory="...") hold?** The Spring bean name of JmsListenerContainerFactory, not the destination.

**6. Is setConcurrency("3-10") an application-wide limit?** No, it configures each container created from the factory.

**7. Does setSessionTransacted(true) help roll back JMS when a listener throws an exception?** Yes, within a local JMS transaction when configuration/provider support it; retry/idempotency are still needed.

**8. Does a local JMS transaction commit the DB at the same time?** Not automatically; JTA/XA or an alternative consistency architecture is required.

**9. Why can two listeners on the same Queue processing in parallel change ordering?** Because multiple consumers can receive and finish at different times.

**10. Can a Queue factory be used to receive from a Topic?** You must properly configure pubSubDomain and subscription semantics; do not just change the destination String.

**11. Why does a listener fail to receive a DTO from JSON even though JmsTemplate sends successfully?** The converter/target type/type ID/ObjectMapper or method argument is incompatible.

**12. Who can start/stop annotated JMS listener containers?** JmsListenerEndpointRegistry and the container lifecycle API.

**13. Does having the factory bean registered guarantee the JMS listener is already running?** No; you must also have annotation processing, a valid endpoint, broker connection, and container startup.

**14. Why is swallowing exceptions inside a listener dangerous?** The container can commit/ack while the application silently fails, preventing message redelivery.

**15. What should you check before scaling consumers to 10?** Ordering, idempotency, broker/session limits, executor, DB pool, throughput, and retry rates.

### Practice Exercises

1. Run the project in section 13; confirm the two stdout lines and observe the container in the broker console.
2. Rename the bean to ordersFactory, add containerFactory="ordersFactory" on the listener; explain the bean name dependency.
3. Create one dedicated factory for topics and one dedicated factory for queues, and test proper publish/subscribe semantics.
4. Send 20 messages, increase concurrency, measure processing time and completion order.
5. Make the listener throw RuntimeException with setSessionTransacted(true), and observe redelivery and the broker DLQ.
6. Create a Configurer-based factory and use Boot min/max concurrency properties; compare with a manual factory.
7. Attach a suitable DynamicDestinationResolver/JndiDestinationResolver; verify sender and listener target the same physical destination.
8. Add a JMS property EventType on the producer and use a @JmsListener selector; test when the property is missing.
9. Use JmsListenerEndpointRegistry to find the endpoint ID and check isRunning.
10. Configure MappingJackson2MessageConverter with a type ID; send a DTO and test conversion errors.
11. Set up two listeners on the same queue with different selectors; observe that non-matching messages remain on the broker.
12. Write a production deployment checklist covering credentials, transactions, concurrency, retry/DLQ, observability, and shutdown.

## 19. References

- Spring Framework 6.2 — Annotation-driven Listener Endpoints: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html
- Spring Framework 6.2 — Using Spring JMS / Message Listener Containers: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html
- Spring Framework 6.2 — Processing Messages Within Transactions: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html
- Spring Framework 6.2 — DefaultJmsListenerContainerFactory API: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html
- Spring Framework 6.2 — JmsListener API: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/annotation/JmsListener.html
- Spring Framework 6.2 — JmsListenerEndpointRegistry API: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistry.html
- Spring Boot 3.4 — JMS reference: https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html
- Spring Boot 3.4 — DefaultJmsListenerContainerFactoryConfigurer API: https://docs.spring.io/spring-boot/3.4.4/api/java/org/springframework/boot/autoconfigure/jms/DefaultJmsListenerContainerFactoryConfigurer.html
- Spring guide — Messaging with JMS: https://spring.io/guides/gs/messaging-jms/
- Jakarta Messaging 3.1 specification: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Apache ActiveMQ Artemis Docker guide: https://artemis.apache.org/components/artemis/documentation/latest/docker.html
