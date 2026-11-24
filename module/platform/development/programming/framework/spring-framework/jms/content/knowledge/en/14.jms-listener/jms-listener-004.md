# Declaring destination and containerFactory in @JmsListener (Spring Framework JMS)

## Learning Objectives

In Spring Framework, `@JmsListener` marks a method on a **Spring-managed bean** as an asynchronous JMS message receiving point. Two attributes determine the endpoint's behavior:

- **`destination`**: *where does the listener receive messages from?* This is the destination name resolved to a `jakarta.jms.Queue` or `jakarta.jms.Topic` according to the listener container's strategy.
- **`containerFactory`**: *with which configuration is the listener created and operated?* This is the **Spring bean name** implementing `JmsListenerContainerFactory`, used to create the corresponding `MessageListenerContainer`.

This lesson focuses directly on **declaring destination and containerFactory**. By the end, you will be able to:

1. Correctly write `@JmsListener(destination = "...")` and `@JmsListener(destination = "...", containerFactory = "...")`.
2. Explain `@EnableJms`, `JmsListenerAnnotationBeanPostProcessor`, `JmsListenerContainerFactory`, and `JmsListenerEndpointRegistry` well enough to configure and debug them.
3. Distinguish **destination name**, **`Destination` bean**, **container factory bean name**, and the actual running **container instance**.
4. Use the default factory named `jmsListenerContainerFactory` or create multiple factories by broker, Queue/Topic, transactions, concurrency, selector, converter, and policy.
5. Declare destinations from `application.properties` with `${...}`, understanding the limits of startup-time resolution and broker provisioning/ACLs.
6. Use Spring Boot 3.5 and `DefaultJmsListenerContainerFactoryConfigurer` to inherit default settings without missing key configurations.
7. Run a Java 17 demo receiving messages on **two queues** with **two different factories**, one of which uses a JMS selector.
8. Troubleshoot errors such as wrong bean name, Queue/Topic mismatch, missing listener, message ACKed despite business failure, duplicates, and unsuitable concurrency configuration.

> **Principle:** `destination` selects *the message source*; `containerFactory` selects *how the listener operates*. **`destination` does not automatically create a physical queue by Spring guarantee**, and **`containerFactory` is neither a Java class nor a broker name**.

## 1. Operational Diagram

A short annotation:

~~~java
@Component
class OrderListener {
    @JmsListener(
        destination = "orders.commands",
        containerFactory = "ordersListenerFactory")
    public void onMessage(String payload) {
        System.out.println(payload);
    }
}
~~~

creates the following logical structure when the application starts:

~~~text
Spring ApplicationContext
  |
  +--- @EnableJms enables annotation infrastructure
  |
  +--- @Component OrderListener
  |      |
  |      +--- @JmsListener onMessage(...)
  |                destination = "orders.commands"
  |                containerFactory = "ordersListenerFactory"
  |
  +--- @Bean(name = "ordersListenerFactory")
  |      DefaultJmsListenerContainerFactory
  |                |
  |                +--- ConnectionFactory
  |                +--- DestinationResolver
  |                +--- MessageConverter
  |                +--- sessionTransacted / transactionManager
  |                +--- concurrency / error handler / selector
  |                |
  |                v
  |       creates dedicated MessageListenerContainer
  |                |
  |                +--- JMS Session + MessageConsumer
  |                +--- subscription to destination
  |                |
  |                v
  |       Broker queue "orders.commands"
  |
  +--- JmsListenerEndpointRegistry manages the container
~~~

The Spring Framework **Annotation-driven Listener Endpoints** documentation confirms that a container is created for each annotated endpoint via `JmsListenerContainerFactory`. The container is managed by `JmsListenerEndpointRegistry`; that container does not necessarily appear as a regular standalone bean in the ApplicationContext.

### Separated Responsibilities

| Component | Function |
|---|---|
| `@JmsListener` | Declares the method, destination name, factory to use, and per-endpoint overrides. |
| `@EnableJms` | Enables discovery and registration of listener annotations. |
| `JmsListenerContainerFactory` | Creates a message listener container with the configured settings. |
| `DefaultJmsListenerContainerFactory` | Common factory that creates `DefaultMessageListenerContainer` per Spring JMS config. |
| `DestinationResolver` | Turns a String name into a `Queue` or `Topic` via JMS Session/JNDI. |
| `ConnectionFactory` | Provides connections to the JMS broker. |
| `MessageListenerContainer` | Manages consumer/session, lifecycle, polling threads, error handling, receiving, and dispatching messages. |
| `JmsListenerEndpointRegistry` | Retrieves, starts/stops, and monitors containers of annotated endpoints. |
| JMS broker | Actually manages addresses/queues/topics, routing, ACLs, retention, TTL, DLQs, and durable subscriptions. |

Do not blame every issue on the annotation. For example, `destination="orders.commands"` can be spelled correctly while the broker has not provisioned the queue, has not granted consume permissions, or is routing it as a Topic.

## 2. Minimal Syntax of `destination`

### 2.1. Directly Declaring a JMS Queue

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderConsumer {

    @JmsListener(destination = "orders.commands")
    public void handle(String body) {
        System.out.println("orders=" + body);
    }
}
~~~

This is **a Java class file** that requires a Spring application, JMS dependencies, and appropriate listener infrastructure; compiling/running it standalone with `javac` without the Spring classpath will not work.

`destination` accepts a **String**. If the listener factory is at its default `pubSubDomain=false`, that name is interpreted with **JMS Queue semantics**. A name containing `.events` does not automatically turn it into a Topic; a name containing `.queue` likewise cannot change the JMS destination type.

### 2.2. Choosing a Factory with `containerFactory`

~~~java
@JmsListener(
    destination = "orders.commands",
    containerFactory = "ordersListenerFactory")
public void handle(String payload) {
    // Business processing.
}
~~~

Here `containerFactory="ordersListenerFactory"` is the **bean name** that must exist in the Spring context, not:

- `org.springframework.jms.config.DefaultJmsListenerContainerFactory` — a class name.
- `orders.commands` — a destination name.
- `"tcp://localhost:61616"` — a broker URL.
- `"jmsListenerContainerFactory"` — the default name unless you intentionally want it.

If the `ordersListenerFactory` bean does not exist or is not a suitable factory type, Spring normally throws an error during listener registration/application startup. It does not automatically create a bean just because the annotation contains that string name.

### 2.3. The Annotation Only Matters on Scanned Spring Beans

~~~java
public class OutsideSpring {
    @JmsListener(destination = "orders.commands")
    void receive(String msg) { }
}
~~~

A class that is not a Spring bean will **not** be registered just because it has the annotation. Bring the class into component scan via `@Component`, declare it via `@Bean`, or register the bean using Spring's mechanism. Also activate the listener infrastructure with `@EnableJms` or appropriate auto-configuration; in this lesson's examples, `@EnableJms` is placed explicitly for clarity.

## 3. How Is `destination` Actually Resolved?

### 3.1. A String Is Not Equivalent to a Physical Resource

With the default dynamic resolver, the conceptual mechanism is:

~~~java
// CODE ILLUSTRATING resolver IDEA, not copied from Spring source.
Destination resolve(
        Session session, String name, boolean pubSubDomain)
        throws JMSException {
    return pubSubDomain
            ? session.createTopic(name)
            : session.createQueue(name);
}
~~~

`Session.createQueue` and `Session.createTopic` create a **provider-side destination handle object**, not a standard API that guarantees the physical queue is already allocated on the broker.

When the listener container creates a consumer, the broker may:

- Connect to an already provisioned queue/topic.
- Auto-create the address/queue if configured and the client has permission.
- Reject the consumer or report that the destination does not exist.
- Apply routing, subscriptions, selectors, and permissions differently from what you expected.

This is broker/provider behavior, not something Spring guarantees on its own. In production, it is usually best to provision resources via config/IaC/management API and verify ACLs.

### 3.2. `pubSubDomain` Decides Queue vs. Topic

| Factory setting | `destination` | JMS semantics |
|---|---|---|
| `factory.setPubSubDomain(false)` | `"orders.commands"` | Queue, point-to-point |
| `factory.setPubSubDomain(true)` | `"orders.events"` | Topic, publish/subscribe |

If the same String name is used while the producer sends via Queue and the listener subscribes as Topic, the two sides **do not automatically meet**.

~~~text
Producer JmsTemplate: pubSubDomain=false
   "orders.events" -> Queue

ListenerFactory: pubSubDomain=true
   "orders.events" -> Topic

Same String, DIFFERENT JMS Destination type!
~~~

Avoid assuming a listener targets a topic or queue just because the name ends with `.events`. Check **both the producer and the listener factory**.

### 3.3. `DynamicDestinationResolver` and `JndiDestinationResolver`

Spring has two common strategies:

- **`DynamicDestinationResolver`**: calls `Session.createQueue` or `createTopic` depending on `pubSubDomain`.
- **`JndiDestinationResolver`**: looks up a `Destination` from JNDI with the specified name; caching and dynamic fallback can be configured via its own API.

If an enterprise environment requires destinations registered in JNDI, use the JNDI resolver or inject `Destination` directly rather than assuming annotation names are looked up in JNDI by default. With `JndiDestinationResolver`, enabling fallback to dynamic can mask JNDI errors and rely on broker auto-creation; evaluate per policy.

### 3.4. Destination Names Can Be Configured from Properties

`@JmsListener.destination` in Spring supports property placeholders through annotation processing:

~~~java
@JmsListener(
    destination = "${app.jms.orders-queue}",
    containerFactory = "ordersListenerFactory")
public void handle(String body) { }
~~~

In `application.properties`:

~~~properties
app.jms.orders-queue=dev.orders.commands
~~~

Benefit: code does not hard-code environment-specific queues. Notes:

- The placeholder must be resolvable by Spring in the configuration context.
- A wrong/missing value can prevent endpoint registration or fail consumer startup.
- Changing a property at runtime **does not automatically move the listener container** to a different queue immediately.
- Do not concatenate raw user input/tenantId directly into destinations without validation; when the broker auto-creates queues, typos or arbitrary input can spawn thousands of unwanted queues.
- The property key `app.jms.*` here is **application-defined**, not a built-in `spring.jms.*` property.

Spring supports expression resolution depending on the scenario, but for environment-based configuration, `${...}` is usually easier to read and test. Endpoints are normally registered at Spring startup, **not re-evaluated per message**.

## 4. `containerFactory`: Not a Container Name, but a Factory Bean

### 4.1. Contract

The annotation:

~~~java
@JmsListener(
    destination = "orders.commands",
    containerFactory = "ordersListenerFactory")
~~~

means Spring looks for a **bean named `ordersListenerFactory`** implementing `JmsListenerContainerFactory` to create the corresponding `MessageListenerContainer`. Do not set `containerFactory` to a listener method name or a `ConnectionFactory` object.

One factory can serve **multiple annotated listeners**. Each listener endpoint gets **its own container** created by the factory—not dozens of listeners sharing the exact **same single container instance**.

~~~text
ordersListenerFactory (one bean)
      |
      +--- @JmsListener(destination="orders.commands")
      |         -> Container A
      |
      +--- @JmsListener(destination="orders.retry")
                -> Container B
~~~

Both containers can use the same `ConnectionFactory` while having separate lifecycles/consumers. If on the same Queue, they are competing consumers, which does not mean one message is delivered to both.

### 4.2. Default Factory

If the annotation **does not declare** `containerFactory`:

~~~java
@JmsListener(destination = "orders.commands")
public void receive(String text) { }
~~~

Spring's listener infrastructure looks by default for a bean named:

~~~text
jmsListenerContainerFactory
~~~

This is the **default bean name**, not a class name. With Spring Boot and eligible JMS infrastructure, Boot can auto-configure the default factory; however, do not assume an arbitrary self-defined bean name will always replace the default factory cleanly.

In Spring Framework without Boot, an example manual configuration is:

~~~java
@Configuration
@EnableJms
public class JmsConfiguration {

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1");
        return factory;
    }
}
~~~

Requires imports from Spring and `jakarta.jms.ConnectionFactory`. The bean method named `jmsListenerContainerFactory` satisfies the default name. The `@EnableJms` annotation enables listener detection; by itself it does not create a JMS broker, supply credentials, or provision destinations.

### 4.3. Custom Factory for a Listener

~~~java
@Bean("priorityQueueFactory")
DefaultJmsListenerContainerFactory priorityQueueFactory(
        ConnectionFactory connectionFactory) {
    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setPubSubDomain(false);
    factory.setSessionTransacted(true);
    factory.setConcurrency("2-5");
    return factory;
}
~~~

Used via:

~~~java
@JmsListener(
    destination = "orders.priority",
    containerFactory = "priorityQueueFactory")
public void receivePriority(String payload) {
    // ...
}
~~~

If you want **two factories**, create two beans with distinct names and specify them explicitly on annotations. If you only have a custom factory while some listener omits `containerFactory`, ensure a **default factory** with the proper name still exists or register a default via `JmsListenerConfigurer`. Do not rely on accidental initialization order.

### 4.4. Factory vs. JMS ConnectionFactory Are Different

- `jakarta.jms.ConnectionFactory`: creates JMS connections.
- `org.springframework.jms.config.JmsListenerContainerFactory`: creates Spring listener containers.
- `DefaultJmsListenerContainerFactory`: a Spring factory implementation.
- `DefaultMessageListenerContainer`: the actual container that polls and dispatches messages.

They are easy to confuse because both names contain `Factory`. `@JmsListener(containerFactory="...")` points to a **Spring listener container factory**, not directly to the JMS provider ConnectionFactory.

## 5. Key Settings of `DefaultJmsListenerContainerFactory`

Core options:

| Setting | Role | Risk if misconfigured |
|---|---|---|
| `setConnectionFactory(...)` | Connects to the actual broker. | Listener connects to wrong broker/credentials. |
| `setDestinationResolver(...)` | Maps String names to Queue/Topic. | JNDI lookup fails, typo, or wrong mapping. |
| `setPubSubDomain(...)` | Selects Queue (`false`) or Topic (`true`). | Listener listens to the wrong destination type. |
| `setSessionTransacted(true)` | Local JMS transaction for receive + processing. | If missing, exceptions may not trigger expected redelivery. |
| `setTransactionManager(...)` | External transaction manager, often JTA when using XA. | Wrong transaction semantics/resource enlistment. |
| `setConcurrency("2-5")` | Number of concurrent consumers in the container. | Lost ordering, topic duplicates, or downstream overload. |
| `setMessageConverter(...)` | Converts JMS Message into Java payload. | JSON/serialization errors. |
| `setErrorHandler(...)` | Handles/logs errors when listener fails. | Unobserved errors, swallowing the wrong exceptions. |
| `setMessageSelector(...)` | JMS selector filter at consumer/container level. | Messages sit in queue with no listener receiving them. |
| `setClientId(...)`, durable subscription | Relates to topic subscription identity. | Collisions or broken subscription expectations. |
| `setReceiveTimeout(...)` and cache settings | Affects polling/lifecycle/resources. | Long thread waits, improper throughput. |

Not every setting suits every provider. For example, `setConcurrency("3-10")` is helpful with multiple Queue consumers, whereas Topic non-shared subscriptions can result in **each consumer receiving a copy** or hitting other provider rules rather than load-sharing like a Queue.

### 5.1. Concurrency on the Factory and Overriding on the Annotation

Factory:

~~~java
factory.setConcurrency("2-5");
~~~

Endpoint can override:

~~~java
@JmsListener(
    destination = "orders.commands",
    containerFactory = "ordersListenerFactory",
    concurrency = "1")
public void receiveOrder(String payload) { }
~~~

Per `@JmsListener` Javadoc, `concurrency` on the annotation **overrides** the concurrency set on the factory for that endpoint, if the container supports it. Values like `"5-10"` specify min/max consumers; `"10"` typically denotes max 10 with a lower bound of 1, depending on container implementation. Do not assume 10 fixed threads when writing only `"10"`.

### 5.2. Selector: Per-Endpoint Attribute

~~~java
@JmsListener(
    destination = "orders.commands",
    containerFactory = "ordersListenerFactory",
    selector = "priorityClass = 'HIGH'")
public void receiveHighPriority(String payload) { }
~~~

`selector` is a JMS selector expression applied to headers/properties supported by the provider. `priorityClass` in the example is an **application String property**, not a Java enum value automatically present on every message. The producer must attach this exact property. Otherwise, messages may remain on the queue waiting for a matching consumer.

Multiple listeners with different selectors on **the same Queue** compete according to those filter conditions; this does not automatically turn a Queue into a broadcast Topic. Measure routing and queue depth.

### 5.3. `id`: Identifying the Container for Lifecycle Management

~~~java
@JmsListener(
    id = "orders-listener",
    destination = "orders.commands",
    containerFactory = "ordersListenerFactory")
public void handle(String payload) { }
~~~

`id` is the endpoint/container identifier in `JmsListenerEndpointRegistry`. It is neither the destination nor the JMS connection `clientId`. Each `id` should be unique in the registry.

Management example:

~~~java
// Snippet in a Spring bean with JmsListenerEndpointRegistry injected.
MessageListenerContainer container =
        registry.getListenerContainer("orders-listener");

if (container != null) {
    container.stop();
}
~~~

This is a snippet, not a standalone application. In production, consider draining, timeouts, in-flight transactions, readiness, and coordination across instances before stopping/starting containers.

## 6. Spring Boot 3.5: Leveraging the Default Configurer

When using Boot with `spring-boot-starter-artemis` and JMS auto-configuration, Boot can create:

- `ConnectionFactory` from `spring.artemis.*`.
- `JmsTemplate` for sending JMS messages.
- Default listener container factory when a required factory is missing per auto-configuration conditions.
- Defaults for session transactions, caching, message converters, observation, or related properties.

If you need an additional factory, Spring Boot provides:

~~~java
org.springframework.boot.autoconfigure.jms
    .DefaultJmsListenerContainerFactoryConfigurer
~~~

This is a **Boot helper** responsible for applying default configuration read from properties, after which you add or override specific settings.

### 6.1. Using `DefaultJmsListenerContainerFactoryConfigurer`

~~~java
@Bean("ordersListenerFactory")
DefaultJmsListenerContainerFactory ordersListenerFactory(
        DefaultJmsListenerContainerFactoryConfigurer configurer,
        ConnectionFactory connectionFactory) {

    var factory = new DefaultJmsListenerContainerFactory();

    // Boot 3.5: prefer native factory for message listener container.
    configurer.configure(factory,
        ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));

    factory.setPubSubDomain(false);
    factory.setConcurrency("1");
    factory.setSessionTransacted(true);
    return factory;
}
~~~

Boot 3.5 imports:

~~~java
import org.springframework.boot.autoconfigure.jms
        .DefaultJmsListenerContainerFactoryConfigurer;
import org.springframework.boot.jms.ConnectionFactoryUnwrapper;
~~~

This is a bean declaration snippet. Spring Boot 3.5 documentation recommends `ConnectionFactoryUnwrapper.unwrapCaching(...)` so the listener container uses the **native ConnectionFactory** rather than holding an external connection cache: the listener container has its own management and recovery mechanism. Do not unconditionally use a `CachingConnectionFactory` for the container and expect it to handle restarts/scaling like a native factory.

### 6.2. Why Use the Configurer Instead of `new` Plus Setting a Few Properties?

Both approaches can be valid. But if you only write:

~~~java
var factory = new DefaultJmsListenerContainerFactory();
factory.setConnectionFactory(connectionFactory);
return factory;
~~~

you may miss Boot defaults such as transactions, converters, observation, and listener properties. In particular, `DefaultMessageListenerContainer` with default `AUTO_ACKNOWLEDGE` ACKs before listener execution; exceptions do not automatically guarantee redelivery in that mode. For a self-written factory, actively configure transaction semantics and test them.

**The defaults of a factory you `new` yourself are not necessarily equal to a Boot auto-configured factory.** Environments with JTA can also differ from local transactions. Therefore, the example explicitly sets `setSessionTransacted(true)`.

### 6.3. Boot Properties and Limitations

Example `application.properties`:

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis

app.jms.orders-queue=lesson.orders.commands
app.jms.audit-queue=lesson.audit.commands
~~~

`spring.artemis.*` is understood by Boot; `app.jms.*` is custom application config referenced by annotations via placeholders. `spring.jms.listener.*` properties (e.g., concurrency/acknowledge settings per Boot version) can be applied by the configurer. Do not assume properties will automatically configure a factory you instantiate manually **without calling the configurer**.

## 7. Two Factories or One Factory?

### 7.1. One Factory Suffices When Policies Match

If `orders.incoming`, `orders.retry`, and `notifications.queue` are all JMS Queues on the same broker, with the same Session transaction policy, converter, and suitable concurrency, they can use **the same factory bean**:

~~~java
@JmsListener(
    destination = "orders.incoming",
    containerFactory = "defaultQueueFactory")
void onIncoming(String payload) { }

@JmsListener(
    destination = "orders.retry",
    containerFactory = "defaultQueueFactory")
void onRetry(String payload) { }
~~~

Each endpoint still gets its own container, even though they are created from the same factory.

### 7.2. Split Factories When Policies Differ

Consider splitting factories when there are durable differences:

- Queue vs. Topic (`pubSubDomain`).
- Different native JMS ConnectionFactories due to brokers/credentials.
- Local transaction vs. JTA/different transaction managers.
- Message converter/schema or custom error handler.
- Concurrency/selector/durable subscription policies hard to express via annotation overrides.
- Different client ID/subscription setups.
- Special recovery, caching, or resource behaviors.

You do not need to create one factory **per queue** when queues share the same policy; that makes configuration redundant and hard to maintain. However, choosing separate factories to isolate SLAs/risk or traffic classes can still make sense.

### 7.3. Different from `JmsTemplate`

`JmsTemplate` is usually used for **sending** or synchronous receiving; `DefaultJmsListenerContainerFactory` creates consumer containers for **asynchronous receiving**. Both objects can share a `ConnectionFactory` but do not automatically share all settings.

For example, `jmsTemplate.setPubSubDomain(true)` does not automatically make `ordersListenerFactory` consume Topics. Inspect the actual factory. Conversely, `@JmsListener(destination="x")` does not automatically assign a default destination to the producer template.

## 8. Complete Java 17 Demo: Two Destinations, Two containerFactories

The application will:

1. Use locally running Artemis.
2. Declare two Queues via properties.
3. Create factories `ordersListenerFactory` and `auditListenerFactory`.
4. Create two listener methods: one receiving orders, one receiving audits with a JMS selector.
5. Send two messages using `JmsTemplate`.
6. Observe logs proving both listeners are invoked, each using its own policy.

The example uses Spring Boot **3.5.5**, Java **17**, and `spring-boot-starter-artemis`. There is no need to implement a `MessageListener` interface manually.

### 8.1. Preparing the Artemis Broker

Requirements: JDK 17+, Maven 3.9+, Docker, free ports `61616` and `8161`. Start a dedicated broker for the demo:

~~~bash
docker run --detach --rm --name jms-listener-factory-lab \
  -e ARTEMIS_USER=artemis \
  -e ARTEMIS_PASSWORD=artemis \
  -p 61616:61616 -p 8161:8161 \
  apache/artemis:latest-alpine
~~~

Check broker startup:

~~~bash
docker logs jms-listener-factory-lab
~~~

The Artemis console is usually at `http://localhost:8161`. Demo images typically enable auto-create for addresses/queues. If your organization disables auto-create, provision the two queues with corresponding names and `send`/`consume` permissions before running. Do not use demo passwords in production.

### 8.2. Project Structure

~~~text
jms-listener-factory-lab/
├── pom.xml
└── src/main/
    ├── java/example/JmsListenerFactoryApplication.java
    └── resources/application.properties
~~~

### 8.3. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.5</version>
    <relativePath/>
  </parent>

  <groupId>example</groupId>
  <artifactId>jms-listener-factory-lab</artifactId>
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

### 8.4. `application.properties`

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis

# Custom destination names per application configuration.
app.jms.orders-queue=lesson.orders.commands
app.jms.audit-queue=lesson.audit.commands
~~~

### 8.5. `src/main/java/example/JmsListenerFactoryApplication.java`

~~~java
package example;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.TextMessage;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jms
        .DefaultJmsListenerContainerFactoryConfigurer;
import org.springframework.boot.jms.ConnectionFactoryUnwrapper;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableJms
public class JmsListenerFactoryApplication {

    private static final String ORDERS = "lesson.orders.commands";
    private static final String AUDIT = "lesson.audit.commands";

    public static void main(String[] args) {
        SpringApplication.run(JmsListenerFactoryApplication.class, args);
    }

    @Bean("ordersListenerFactory")
    DefaultJmsListenerContainerFactory ordersListenerFactory(
            DefaultJmsListenerContainerFactoryConfigurer configurer,
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        configurer.configure(
                factory,
                ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));

        factory.setPubSubDomain(false);  // Queue
        factory.setConcurrency("1");
        factory.setSessionTransacted(true);
        return factory;
    }

    @Bean("auditListenerFactory")
    DefaultJmsListenerContainerFactory auditListenerFactory(
            DefaultJmsListenerContainerFactoryConfigurer configurer,
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        configurer.configure(
                factory,
                ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));

        factory.setPubSubDomain(false);  // Queue
        factory.setConcurrency("1");
        factory.setSessionTransacted(true);

        // Only receive messages with JMS property kind = "AUDIT".
        factory.setMessageSelector("kind = 'AUDIT'");
        return factory;
    }

    @Bean
    ApplicationRunner publishExamples(
            JmsTemplate jmsTemplate,
            Receivers receivers) {
        return args -> {
            jmsTemplate.convertAndSend(ORDERS, "order-42");

            jmsTemplate.convertAndSend(
                    AUDIT,
                    "audit-42",
                    message -> {
                        message.setStringProperty("kind", "AUDIT");
                        return message;
                    });

            System.out.println("sentTwo=true");
            System.out.println(
                    "receivedBoth=" + receivers.awaitBoth());
        };
    }

    @Component
    public static class Receivers {
        private final CountDownLatch received =
                new CountDownLatch(2);

        @JmsListener(
            id = "orders-listener",
            destination = "${app.jms.orders-queue}",
            containerFactory = "ordersListenerFactory")
        public void onOrder(String body) {
            System.out.println("ordersReceived=" + body);
            received.countDown();
        }

        @JmsListener(
            id = "audit-listener",
            destination = "${app.jms.audit-queue}",
            containerFactory = "auditListenerFactory")
        public void onAudit(TextMessage message)
                throws JMSException {

            System.out.println(
                    "auditReceived=" + message.getText()
                    + ";kind=" + message.getStringProperty("kind"));
            received.countDown();
        }

        boolean awaitBoth() throws InterruptedException {
            return received.await(15, TimeUnit.SECONDS);
        }
    }
}
~~~

### 8.6. Checking How the Code Connects the Components

- `@SpringBootApplication` enables component scan in package `example` and Boot auto-configuration.
- `@EnableJms` enables registration of `@JmsListener`.
- `ordersListenerFactory` and `auditListenerFactory` are **bean names from `@Bean("...")`**.
- Each factory is configured using Boot's `DefaultJmsListenerContainerFactoryConfigurer`, then explicitly overrides `pubSubDomain`, concurrency, transacted session, and the audit selector.
- Both annotations use **`containerFactory` matching the exact corresponding bean name**.
- Both `destination` values come from `${app.jms.*}`. Names are resolved at startup/endpoint registration, not per payload.
- Boot's `JmsTemplate` sends messages to the two queues. The audit message carries application property `kind="AUDIT"` to match the selector.
- One method receives a `String` payload via the message converter; the other receives a raw `jakarta.jms.TextMessage` and reads the property.
- `CountDownLatch` only waits for both callbacks to reach their end; it **does not replace JMS ACK**, nor does it prove exactly-once or that database side effects are durable.
- The factories use `sessionTransacted=true` so exceptions in listeners cause JMS rollback, allowing redelivery per broker policy.
- The demo code has no DB transactions and makes no claim of automatic deduplication.

### 8.7. Compiling and Running

In the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

With a clean broker, a single application instance, and valid credentials and destinations, you will typically observe **the lines printed by the application**:

~~~text
sentTwo=true
ordersReceived=order-42
auditReceived=audit-42;kind=AUDIT
receivedBoth=true
~~~

The order of the first three lines is not fixed: listener containers run on separate threads. The line `receivedBoth=true` appears only when both listeners have executed within the 15-second limit. If the broker errors, auto-create is disabled, or older messages/other consumers exist, output may differ. Spring Boot prints additional startup logs.

To inspect clearly, open the Artemis console and view the two queues:

~~~text
lesson.orders.commands
lesson.audit.commands
~~~

If an audit message lacks the `kind` property, the selector `kind = 'AUDIT'` will **not select** that message; it may remain in the queue even though the producer reported send success.

Stop the app with `Ctrl+C`, then:

~~~bash
docker stop jms-listener-factory-lab
~~~

The container uses `--rm` without mounting a volume, so demo data is not persisted on stop. Do not use this setup as a production broker.

### 8.8. Controlled Experiments

Try one change **at a time** to understand the causes:

1. Change `destination = "${app.jms.orders-queue}"` to a nonexistent property: observe placeholder/registration error.
2. Change `containerFactory = "ordersListenerFactory"` to a nonexistent bean name: observe factory bean lookup failure.
3. Turn off `setSessionTransacted(true)` in one factory on a test broker; inject a controlled processing error and compare redelivery.
4. Change the audit selector to `kind = 'UNKNOWN'`: audit messages will not match and may stay on the queue.
5. Change the audit factory to `pubSubDomain=true` while the producer still sends to a Queue: observe the mismatch (do not treat matching String names as sufficient).
6. If the broker disables auto-create, provision both queues and rerun without changing Java code.

Do not perform experiments that disrupt message flow on queues carrying production data.

## 9. Default Factory vs. Explicit Factory: Decision Table

| Case | Annotation | Which factory Spring selects |
|---|---|---|
| `containerFactory` omitted | `@JmsListener(destination="orders")` | Default `jmsListenerContainerFactory` or default configured on registrar. |
| Explicitly declared | `@JmsListener(destination="orders", containerFactory="ordersListenerFactory")` | Bean `ordersListenerFactory`. |
| Wrong bean name | `containerFactory="noSuchFactory"` | Usually fails endpoint registration/startup; does not auto-create a factory. |
| Two factories of the same type | `containerFactory="auditListenerFactory"` | By **bean name**, not randomly selected by type. |
| Two methods omit factory while only a differently named bean exists | Unclear default | Needs default bean or registrar config; do not rely on luck. |
| Same factory, two different destinations | Two annotations with different `destination` | Two separate containers from the same factory. |
| Same Queue, two different listeners | Two annotations with same `destination` | Competing consumers, not broadcast. |
| Topic listeners | Factory `pubSubDomain=true` | Topic/subscription semantics; not like queues. |

Key point: **the factory is looked up by bean name** in `containerFactory`, while **the destination is resolved via the container's `DestinationResolver` strategy**. They are not in the same namespace.

## 10. What Additional Attributes Does `@JmsListener` Have?

Although the focus is the two primary attributes, knowing the others prevents placing the wrong value in `containerFactory`:

| Attribute | Purpose | Notes |
|---|---|---|
| `destination` | Queue/topic name the endpoint listens to | Required when using the annotation directly. |
| `containerFactory` | Bean name of `JmsListenerContainerFactory` | Optional if a default exists. |
| `id` | Endpoint/container identifier | Used via `JmsListenerEndpointRegistry`. |
| `selector` | JMS selector on headers/properties | E.g., `kind = 'AUDIT'`. |
| `concurrency` | Overrides concurrency from factory | Use carefully with Topics. |
| `subscription` | Durable subscription name if applicable | Requires proper factory/topic setup. |

Spring also allows repeating `@JmsListener` on a single method to register **multiple endpoints**:

~~~java
@JmsListener(
    destination = "orders.region-a",
    containerFactory = "ordersListenerFactory")
@JmsListener(
    destination = "orders.region-b",
    containerFactory = "ordersListenerFactory")
public void onRegionalOrder(String payload) {
    // One method handles two endpoints.
}
~~~

This is a snippet. Each annotation creates a separate endpoint/container; the business method can be invoked concurrently on different threads. If keeping mutable state in the bean, you must still ensure thread safety and idempotency.

## 11. Topics, Durable Subscriptions, and Why Name Changes Alone Are Not Enough

A Topic listener can be declared as:

~~~java
@JmsListener(
    destination = "orders.events",
    containerFactory = "topicListenerFactory")
void onOrderEvent(String event) { }
~~~

where `topicListenerFactory` has `setPubSubDomain(true)`. However, important rules apply:

- Topics normally broadcast messages to **subscriptions**, not a single work-sharing queue.
- Non-durable subscriptions normally receive only while active; offline consumers can miss messages published during downtime.
- Durable subscriptions require proper setup, such as durable flag, subscription name, and client identity; specifics depend on JMS version, shared durable subscriptions, and broker.
- `concurrency > 1` on a Topic listener does not have the same scaling semantics as on a Queue; it can create multiple subscribers each receiving a copy or hit limits disallowing duplicate client IDs.
- When using durable subscribers, carefully review lifecycle, reconnects, stable subscription names, and destination changes across deployments.

In production, topic factories should have dedicated configurations rather than copying a queue factory and changing only `pubSubDomain=true`.

## 12. Transactions, Acknowledgement, and Error Handling Depend on the Factory

Annotations do not dictate transactions. The listener container/factory determines when messages are acknowledged and when to roll back.

### 12.1. Local JMS Transaction

~~~java
factory.setSessionTransacted(true);
~~~

In `DefaultMessageListenerContainer`, each listener callback runs within a local JMS transaction scope. If the method throws an exception visible to the container, the session can roll back and the broker applies its redelivery policy.

~~~text
Queue M
  |
  v
Listener container receives M (transaction open)
  |
  +-- listener processes successfully
  |       |
  |       +-- commit JMS -> ACK M
  |
  +-- listener throws exception
          |
          +-- rollback -> broker may redeliver M
~~~

**Do not swallow exceptions and return normally** if you want rollback. Classify transient vs. permanent errors, apply controlled retry/DLQ and idempotency, and do not arbitrarily resend a new JMS message inside `catch`.

### 12.2. AUTO_ACKNOWLEDGE and Self-Created Factories

Spring's `DefaultMessageListenerContainer` with default `AUTO_ACKNOWLEDGE` can perform automatic acknowledgement **before listener code runs**, so an exception **does not cause redelivery merely by being thrown**. Therefore, when creating a custom factory, choose a transaction policy deliberately or use the Boot configurer to inherit Boot defaults; do not just declare `destination` and `containerFactory` and assume the system already has proper retries.

### 12.3. DB Transactions Differ from JMS Transactions

`sessionTransacted=true` guarantees a local JMS transaction; it **does not automatically include database updates**. If DB commits and then JMS commit fails, the broker can redeliver M while the DB side effect already exists.

Use a stable business `eventId` and an idempotency store/unique constraint within the same DB transaction as business changes. For external APIs (payments/email), use appropriate idempotency or outbox/saga patterns. Relying solely on `JMSRedelivered` or `JMSXDeliveryCount` is not enough to prevent duplicates.

## 13. Multiple Brokers: Each Factory Has Its Own ConnectionFactory

If an organization uses one Artemis broker for orders and another broker for audit, putting an annotation on a method says nothing about the target broker. **The factory determines the ConnectionFactory**.

~~~text
@JmsListener("orders.commands", containerFactory="ordersFactory")
      |
      +--- ordersFactory -> ordersConnectionFactory -> Broker A

@JmsListener("audit.commands", containerFactory="auditFactory")
      |
      +--- auditFactory  -> auditConnectionFactory  -> Broker B
~~~

In a multi-broker setup, declare two native JMS `ConnectionFactory` beans and inject the right bean with `@Qualifier`; verify explicitly which factory uses which connection factory. A `destination` with the same name `"events"` on two different brokers refers to **two different data sources**.

Do not change broker URLs by mutating a running ConnectionFactory/Factory singleton; follow proper lifecycle/redeploy/reconnect policies. Enforce permissions and TLS per broker. If broker A has a Queue while broker B does not, changing only `containerFactory` can stop the listener from starting.

## 14. DestinationResolver, Naming Policies, and Resource Management

### 14.1. Do Not Create Queues Carelessly

With a broker allowing auto-create, a typo:

~~~java
@JmsListener(destination = "orders.comands")
~~~

can create a queue nobody sends to, while the producer sends to `"orders.commands"`. The listener stays alive but silent. To mitigate this:

- Define names via constants or configuration properties.
- Verify effective runtime property values.
- Use a provisioning catalog/Infrastructure as Code.
- Disable auto-create in environments requiring governance.
- Configure namespace ACLs so app principals cannot create thousands of arbitrary queues.
- Monitor broker metrics for queue depth, consumer count, and unrouted messages.

### 14.2. Never Use Raw User Input as a Destination

If listener endpoints are registered dynamically per tenant/request, enforce mappings/allowlists and quotas. Annotations are typically resolved at Spring startup and are not suited to creating a listener per HTTP request. For dynamic runtime subscriptions, consider `JmsListenerEndpointRegistry` and programmatic registration with managed lifecycle.

### 14.3. Message Selectors Are Not Authorization

`selector = "tenant = 'a'"` only filters delivery by JMS properties; it is not an ACL preventing other tenants from reading data. Broker authentication/authorization and isolation design are the security boundary. Never let all tenants share credentials permitted to consume the entire queue and assume a selector provides security.

## 15. Observing Whether a Listener Is Actually Running

### 15.1. Using `JmsListenerEndpointRegistry`

~~~java
// Snippet in a Spring bean with injected registry.
MessageListenerContainer c =
        registry.getListenerContainer("orders-listener");

if (c != null) {
    System.out.println("running=" + c.isRunning());
}
~~~

`JmsListenerEndpointRegistry` provides a way to retrieve a container by `@JmsListener.id`, inspect/access status, and perform controlled start/stop. This does not verify that the broker has delivered or business processing succeeded; you also need delivery metrics, ACKs, and application logs.

### 15.2. Layers to Verify

| Layer | Question |
|---|---|
| Spring scan | Is the class a Spring bean? |
| Annotation processing | Is `@EnableJms`/auto-config active? |
| Factory lookup | Does `containerFactory` point to a bean of the right name/type? |
| Consumer initialization | Can `ConnectionFactory` connect to the broker? |
| Destination resolver | Are Queue/Topic and effective name correct? |
| Broker | Does the address/queue/subscription exist with proper routing/ACLs? |
| Delivery | Does the broker show consumer count, deliveries, selector matches? |
| Listener | Is the method invoked and does message conversion succeed? |
| Transaction | Did the message commit or roll back/move to DLQ? |
| Business | Did the side effect truly complete, remain idempotent, and get observed? |

A consumer with `isRunning()==true` does not prove messages match its selector or that the broker has delivered matching messages.

## 16. Diagnosing Common Errors

### 16.1. `No bean named 'ordersListenerFactory'`

**Common causes:** annotation specifies a nonexistent factory name; `@Bean` method is outside component scan; bean has a different name; config was skipped due to profiles/conditions.

**How to check:** inspect ApplicationContext beans, exact `@Bean("ordersListenerFactory")`, package scan, profiles, and `containerFactory`. `containerFactory` needs the bean name, **not the class name**.

### 16.2. `No default JmsListenerContainerFactory`

An endpoint omits `containerFactory`, yet the context has no default named `jmsListenerContainerFactory` (and the registrar has no configured default). Create the proper default bean or add `containerFactory` explicitly. Be especially careful when defining a custom factory prevents Boot's auto-config from creating the default as you expected.

### 16.3. Listener Receives Nothing Even Though Producer Sends Successfully

Check in order:

1. Actual destination name from properties and spelling.
2. `pubSubDomain` of **both producer and listener**.
3. Broker host/port, vhost/cluster, user, and permissions.
4. Is the physical resource provisioned with the right routing/queue?
5. Has the listener container started?
6. Does the selector match the message?
7. Did the message expire or move to DLQ?
8. Is another consumer competing on the same Queue?
9. Did the message converter fail before calling the method?

Do not conclude the annotation is wrong if the broker has no messages routed to the consumer.

### 16.4. Factory Defined Yet Its Policy Does Not Seem Applied

The annotation may be omitting `containerFactory` so Spring uses a different default bean. Or the sending code uses `JmsTemplate`, which has its own configuration. Log the factory/bean name and inspect the container's effective `DestinationResolver`, `ConnectionFactory`, transaction mode, and concurrency.

### 16.5. Messages Processed Twice

If a listener throws an exception in a transacted session, the broker can redeliver; if DB committed before JMS commit failed, the message can be reprocessed. Use a business event ID and idempotency; do not treat a transacted factory as an exactly-once guarantee with the DB.

### 16.6. Increasing `concurrency` Breaks Message Ordering

Multiple Queue consumers can process concurrently and finish out of order. If business logic requires ordering, use appropriate consumer concurrency, sharding by key, or a broker/application-guaranteed ordering model. Do not assume `"5-10"` is automatically better than `"1"`.

### 16.7. Topics Receive Multiple Copies of Messages

With publish/subscribe, multiple subscriptions can receive the same event. If you increase concurrency by creating multiple Topic consumers without appropriate shared subscription semantics, messages may be delivered multiple times by design. Clearly distinguish Topic vs. Queue and durable/shared subscription policies.

### 16.8. Listener Stops After Broker Restart or Network Drop

Inspect the recovery interval, ConnectionFactory, and container management. Spring Boot recommends listener containers use a native ConnectionFactory when appropriate so they manage reconnect/recovery themselves. Do not wrap an external cache around the listener container without understanding its impact on restarts/scaling.

### 16.9. `@JmsListener` Method Is Not Detected

The class may not be a Spring bean, may lie outside component scan, `@EnableJms` may not be enabled, the annotation may be on an object manually created with `new`, or the bean was excluded by conditionals/profiles. Do not start by changing `destination` if annotation infrastructure is not active.

### 16.10. Messages Do Not Match Selector

A selector like `kind = 'AUDIT'` requires JMS property `kind` with String value `AUDIT`. If the producer only puts a JSON field `"kind"` in the body **without setting a JMS property**, the broker will not use that JSON field to match the selector. Attach the property via `MessagePostProcessor` and inspect the raw JMS message.

## 17. Key Anti-Patterns

| Anti-pattern | Why it is wrong | Replace with |
|---|---|---|
| `containerFactory="DefaultJmsListenerContainerFactory"` | Annotation needs a **bean name**, not a class. | `containerFactory="ordersListenerFactory"` with matching `@Bean` name. |
| Writing `destination="orders"` assuming Spring provisions the queue | JMS reference does not guarantee broker resources. | Provision/verify addresses, queues, ACLs. |
| Using default factory while expecting another factory's custom settings | Annotations do not auto-select by use case. | Specify `containerFactory` explicitly. |
| Scaling Topic concurrency like a Queue | Can cause duplicate copies, subscription collisions. | Proper Topic/durable/shared design. |
| Treating `selector` as a JSON body query | JMS selectors read JMS headers/properties. | Attach JMS properties or filter in the application appropriately. |
| Catching all exceptions and returning success | Listener may commit despite processing failure. | Propagate errors needing rollback, use retry/DLQ. |
| Believing local JMS transaction also rolls back the DB | Two independent resources. | Idempotency/outbox or properly designed JTA/XA. |
| Passing raw user input directly into destination | Queue sprawl, abuse, ACL risks. | Mapping/allowlists and resource governance. |
| Mutating factory bean setters while listeners are running | Hard-to-control runtime state, inconsistent behavior. | Configure before start, change via clear lifecycle. |
| Accepting `String` when payload needs custom JSON converter not configured | Conversion mismatch/schema errors. | Proper MessageConverter, validation, and tests. |
| Switching JmsTemplate to Topic without updating listener factory | Producer and consumer use different domains. | Align configuration on both sides. |
| Checking only container running to claim business is OK | Running does not equal delivered/committed. | Observe broker + application + transactions. |

## 18. Deployment Checklist

Before deploying listeners to production:

- [ ] `@EnableJms`/auto-configuration enabled and listener bean is within component scan.
- [ ] `destination` has the exact configured name, with no unresolved placeholders.
- [ ] Queue/Topic distinguished clearly; `pubSubDomain` matches between listener and producer.
- [ ] Broker address/queue/topic provisioned with proper routing, retention, DLQ, and ACLs.
- [ ] `containerFactory` points to the exact `JmsListenerContainerFactory` **bean name**.
- [ ] If the listener omits `containerFactory`, a properly named default factory exists or the registrar is configured.
- [ ] Custom factories use an appropriate `ConnectionFactory`, preferring the Boot configurer and native listener connection on Boot 3.5.
- [ ] `sessionTransacted`/transaction manager/ack mode tested with exceptions and redelivery.
- [ ] Concurrency/selector/durable subscription match destination type and ordering requirements.
- [ ] Message converter supports actual payloads with valid schema validation.
- [ ] Logs include listener ID, destination, message ID, event ID, redelivery count, errors, and transaction outcome.
- [ ] Idempotency is in place when business logic has DB/API side effects.
- [ ] Monitoring covers consumer count, queue depth, deliveries, DLQ, and broker/connection errors.
- [ ] Tested broker restart, missing destination, bad credentials, and wrong factory bean name in staging.
- [ ] Unrestricted queue creation permissions and raw user-input destinations are disallowed.
- [ ] Processes exist for config changes and container start/stop without losing in-flight messages.

## 19. Self-Check Questions

**1. Does `@JmsListener(destination="orders")` require declaring `containerFactory`?** No, if the Spring context has a valid default `JmsListenerContainerFactory`. The default bean name is `jmsListenerContainerFactory`.

**2. Does `containerFactory` take a class name or a bean name?** A Spring bean name, such as `"ordersListenerFactory"`.

**3. Does declaring `destination="orders.events"` alone turn the listener into a Topic?** No. Queue/Topic depends on `pubSubDomain` and the container factory's resolver.

**4. Do two methods using the same factory share one container?** No. The factory can create a separate container for each listener endpoint.

**5. On Boot 3.5, why does `DefaultJmsListenerContainerFactoryConfigurer` exist?** To apply auto-configuration settings onto a custom factory before overriding specific options.

**6. Why does Boot recommend `ConnectionFactoryUnwrapper.unwrapCaching(...)` for listener factories?** The container has its own connection/recovery management, and using an external caching wrapper can constrain lifecycle/restarts/scaling.

**7. Do two listeners on the same Queue each receive every message?** No. Queues use competing consumers; one message is dispatched to one eligible consumer, not broadcast automatically.

**8. If Queue concurrency is raised to `"3-10"`, is message completion order still guaranteed?** Do not assume so; multiple consumers processing concurrently can alter completion order.

**9. Does `selector = "kind = 'AUDIT'"` inspect a `kind` field inside a JSON payload?** No. It filters JMS headers/properties; the producer must set the `kind` JMS property.

**10. If the method throws an exception, is the broker guaranteed to redeliver?** It depends on the container's transaction/ack mode and the broker's redelivery policy. Use transacted sessions when you want rollback on errors.

**11. Why does `@JmsListener` on an object created with `new` have no effect?** Because the annotation processor only scans Spring-managed beans.

**12. Can one method have two `@JmsListener` annotations with different destinations?** Yes; the annotation is repeatable, and each declaration creates an endpoint/container.

**13. What is `id="orders-listener"` used for?** Identifying the container/endpoint via `JmsListenerEndpointRegistry`, not as a queue name or JMS clientId.

**14. Does changing `app.jms.orders-queue` in a file while the process is running switch the listener immediately?** Not by default; endpoints are resolved at registration and require proper lifecycle/reconfiguration.

**15. Does a factory with `sessionTransacted=true` automatically guarantee exactly-once database transactions?** No. JMS local transactions and DB transactions are separate resources requiring idempotency/consistency design.

**16. Why must `containerFactory` not be chosen casually when an application has multiple brokers?** Because each factory is bound to a specific ConnectionFactory/broker. The same String name on a different broker is a different resource.

## 20. Official References

- [Spring Framework 6.2 — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html): `@JmsListener` syntax, default bean `jmsListenerContainerFactory`, endpoint/container registry, method signatures.
- [Spring Framework 6.2 — `@JmsListener` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/annotation/JmsListener.html): `destination`, `containerFactory`, `id`, `selector`, `concurrency`, `subscription`.
- [Spring Framework 6.2 — `@EnableJms` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/annotation/EnableJms.html): registration and default factory configuration.
- [Spring Framework 6.2 — Receiving a Message](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html): listener containers, transactions, and acknowledgement.
- [Spring Framework 6.2 — `DefaultJmsListenerContainerFactory`](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html): setters and factory contract.
- [Spring Boot 3.5 — JMS and Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html): auto-configuration of `ConnectionFactory`, `JmsTemplate`, default listener factory.
- [Spring Boot 3.5 — Messaging How-to](https://docs.spring.io/spring-boot/3.5/how-to/messaging.html): configuring custom factories and transacted sessions.
- [Spring Boot 3.5 — `DefaultJmsListenerContainerFactoryConfigurer`](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/jms/DefaultJmsListenerContainerFactoryConfigurer.html): initializing a factory with Boot settings.
- [Spring Boot 3.5 — `ConnectionFactoryUnwrapper`](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/jms/ConnectionFactoryUnwrapper.html): unwrapping a cached ConnectionFactory when configuring listeners.
- [Spring Guide — Messaging with JMS](https://spring.io/guides/gs/messaging-jms/): annotation demo with `destination` and `containerFactory`.
- [ActiveMQ Artemis — Docker](https://artemis.apache.org/components/artemis/documentation/latest/docker.html): local broker for hands-on exercises.

**Remember:** `@JmsListener(destination = "orders.commands", containerFactory = "ordersListenerFactory")` connects **a message source name** to **a listener policy defined by a Spring bean**. `destination` is handled by the resolver according to Queue/Topic and broker provisioning; `containerFactory` selects connection, transaction, concurrency, selector, conversion, and lifecycle settings for **the asynchronous receiving container**. Inspect the annotation, factory, Spring context, and broker together to ensure the listener operates properly.
