# DefaultJmsListenerContainerFactory and the Generated Container in Spring JMS

## 1. Essence: Factory vs. Runtime Container

When building a Spring JMS application, a Java method can listen for messages simply with an annotation:

~~~java
@Component
public class OrderListener {
    @JmsListener(destination = "orders.queue")
    public void onOrder(String payload) {
        System.out.println(payload);
    }
}
~~~

This is a Spring snippet, not a standalone Java program. However, the annotation does not itself open Connections, Sessions, consumer threads, manage transactions, or automatically recover when the broker fails. Spring deploys an infrastructure layer that performs those tasks.

Two classes are very easy to confuse:

- **DefaultJmsListenerContainerFactory** in `org.springframework.jms.config`: a factory typically registered as a **Spring bean**, holding configuration and creating a listener container for each endpoint.
- **DefaultMessageListenerContainer** in `org.springframework.jms.listener`: the **runtime container** created by the factory. It directly manages JMS Connections, Sessions, MessageConsumers, polling, invocation, transactions, concurrency, and recovery.

One factory can create **multiple DefaultMessageListenerContainer instances**. Each `@JmsListener` endpoint typically spawns its own container, and each container can hold multiple JMS consumers if concurrency is greater than one.

For example: one factory bean with two listeners (orders and audit) can create two runtime containers; the orders container has one consumer, while the audit container has two consumers. When 100 more messages arrive, Spring does not create 100 more factories or 100 more containers for those 100 messages.

**Goal:** understand the flow from factory to container, API hooks, lifecycle and registry, the difference between counts of factories/containers/consumers, key DMLC configurations, and how to observe two containers generated from a single factory in a Java 17 + Spring Boot + ActiveMQ Artemis project.

## 2. Diagram from @JmsListener to Broker

~~~mermaid
flowchart TD
    App["ApplicationContext"] --> Infra["@EnableJms or Boot JMS auto-configuration"]
    App --> F["Bean: jmsListenerContainerFactory"]
    Infra --> BPP["JmsListenerAnnotationBeanPostProcessor"]
    BPP --> E1["Endpoint: orders"]
    BPP --> E2["Endpoint: audit"]
    E1 --> R["JmsListenerEndpointRegistrar / Registry"]
    E2 --> R
    F --> R
    R --> C1["DefaultMessageListenerContainer #1"]
    R --> C2["DefaultMessageListenerContainer #2"]
    C1 --> JMS1["Session/MessageConsumer/invoker"]
    C2 --> JMS2["Session/MessageConsumer/invoker(s)"]
    JMS1 --> Broker["JMS Broker"]
    JMS2 --> Broker
~~~

| Component | Role | Does It Receive Messages Directly? |
| --- | --- | --- |
| @JmsListener | Declares method endpoint, destination, ID, selector | No. |
| DefaultJmsListenerContainerFactory | Creates runtime containers, sets shared policies | No. |
| DefaultMessageListenerContainer | Polling, JMS resources, invoking listeners and transactions | Yes. |
| MethodJmsListenerEndpoint | Metadata of an annotated method | No. |
| JmsListenerEndpointRegistry | Manages containers by endpoint IDs | No. |
| JMS ConnectionFactory | Creates JMS Connections for the provider | Does not directly process methods. |
| JmsTemplate | Template for synchronous send/receive from code | Does not create `@JmsListener` containers. |

A factory and a JMS `ConnectionFactory` are also two different objects. `DefaultJmsListenerContainerFactory` takes a `ConnectionFactory` to configure containers; `ConnectionFactory` belongs to the Jakarta Messaging API (`jakarta.jms.ConnectionFactory`), not an interface that creates Spring listener containers.

### 2.1. Three Numbers to Count Separately

Suppose:

~~~text
Factory bean:
  jmsListenerContainerFactory

Annotated endpoints:
  ordersEndpoint
  auditEndpoint

Containers:
  DMLC ordersEndpoint: concurrency 1-1
  DMLC auditEndpoint:  concurrency 2-2

=> Factory beans = 1
=> Runtime containers = 2
=> Configured core consumers = 1 + 2 = 3
~~~

The same factory creates two containers, **not one shared container for both queues**. The total number of consumers does not equal the number of factory beans, nor does it necessarily equal the number of endpoint methods.

### 2.2. Containers from @JmsListener Are Not Necessarily Spring Beans

According to the Spring reference, containers created by the annotated endpoint infrastructure **are not registered as regular standalone beans in ApplicationContext**, but can be retrieved through `JmsListenerEndpointRegistry`. `@JmsListener(id="ordersEndpoint")` sets the ID for the registry, which does not mean a `@Bean` named `ordersEndpoint` exists.

Therefore, if you do not find a `DefaultMessageListenerContainer` bean named `ordersEndpoint`, do not conclude that the listener was not created. Check the registry instead.

## 3. Key Classes and Signatures

Spring Framework 6.x describes the factory as:

~~~java
// Simplified signature to understand the type; not a file to redefine:
public class DefaultJmsListenerContainerFactory
        extends AbstractJmsListenerContainerFactory<
                DefaultMessageListenerContainer> {
}
~~~

It implements `JmsListenerContainerFactory<DefaultMessageListenerContainer>` via its superclass. This is why the runtime type created is `DefaultMessageListenerContainer` rather than `SimpleMessageListenerContainer`.

Some APIs/hooks:

~~~java
// Simplified signatures from the Spring API:
protected DefaultMessageListenerContainer createContainerInstance();

protected void initializeContainer(
        DefaultMessageListenerContainer container);

// Infrastructure works via the factory method:
// createListenerContainer(JmsListenerEndpoint endpoint)
~~~

- **createContainerInstance()** constructs an empty `DefaultMessageListenerContainer` instance.
- **initializeContainer(...)** applies additional settings from `DefaultJmsListenerContainerFactory`.
- **createListenerContainer(endpoint)** orchestrates building and configuring the container from an endpoint.
- Endpoint holds method, destination, selector, subscription, concurrency override, and related metadata.
- Registry handles registration, initialization, and lifecycle.

This is an architectural description, not code to call protected methods from a business service. Application developers normally do not call `createContainerInstance` themselves; Spring calls it when registering endpoints.

### 3.1. Packages to Remember

| Class/interface | Package |
| --- | --- |
| DefaultJmsListenerContainerFactory | org.springframework.jms.config |
| AbstractJmsListenerContainerFactory | org.springframework.jms.config |
| JmsListenerContainerFactory | org.springframework.jms.config |
| JmsListenerEndpointRegistry | org.springframework.jms.config |
| DefaultMessageListenerContainer | org.springframework.jms.listener |
| SimpleMessageListenerContainer | org.springframework.jms.listener |
| SimpleJmsListenerContainerFactory | org.springframework.jms.config |
| JmsListenerAnnotationBeanPostProcessor | org.springframework.jms.annotation |
| @EnableJms / @JmsListener | org.springframework.jms.annotation |
| ConnectionFactory / Session / MessageConsumer | jakarta.jms |

In Spring Framework 6 and Spring Boot 3, avoid importing `javax.jms.*` from older tutorials; use `jakarta.jms.*` consistently.

## 4. Container Creation Flow Over Time

~~~mermaid
sequenceDiagram
    autonumber
    participant A as ApplicationContext
    participant B as AnnotationBeanPostProcessor
    participant R as EndpointRegistrar/Registry
    participant F as DefaultJmsListenerContainerFactory
    participant C as DefaultMessageListenerContainer
    participant P as JMS Provider
    A->>B: Scan beans with @JmsListener
    B->>R: Register MethodJmsListenerEndpoint
    R->>F: createListenerContainer(endpoint)
    F->>F: createContainerInstance()
    F->>C: Apply config and endpoint setup
    F->>C: initializeContainer(...)
    F-->>R: Return configured container
    R->>C: Initialize and manage lifecycle
    C->>P: Start and create JMS resources
    P-->>C: Message matching selector/destination
    C->>A: Invoke annotated method
~~~

The diagram illustrates **responsibilities**, not an immutable bytecode order across all Spring versions. Key points:

1. Infrastructure scans for `@JmsListener` on Spring-managed beans.
2. Each annotation is modeled as endpoint metadata.
3. Registrar/registry selects the factory by bean name or default.
4. Factory creates a new runtime container and applies configuration.
5. Endpoint wires the method-invoking adapter into the container.
6. Registry prepares lifecycle and starts the container according to policy.
7. Container connects to the broker, creates sessions/consumers, and receives messages.
8. After one message finishes, the container continues receiving other messages on the same runtime object.

### 4.1. Containers Are Not Created Per Message

Wrong: every message sent to a queue calls `createContainerInstance()`. Right: the factory creates a runtime container when the endpoint is deployed; the container is long-lived and manages receive cycles, and can **recreate JMS resources** during a broker outage.

### 4.2. Mutating the Factory Bean After Startup Does Not Auto-Update Containers

~~~java
factory.setConcurrency("3-8");
~~~

If called after the registry has already created containers, there is no contract that existing containers immediately change their configuration. Each container already has its own state. To change concurrency at runtime, use the appropriate container API/management or roll out the configuration after testing.

### 4.3. Who Creates the Factory Bean, and Who Creates the DMLC?

- Spring `ApplicationContext` creates `DefaultJmsListenerContainerFactory` from `@Bean`.
- Annotation infrastructure asks the factory to create DMLCs.
- Registry holds and controls the DMLCs.
- DMLC creates/obtains JMS Connection/Session/MessageConsumer via `ConnectionFactory`.
- The broker does not create Spring DMLCs; the broker provides JMS destinations and delivers messages.

## 5. Registering the Default Bean for @JmsListener

The default name Spring looks up when the annotation does not specify a factory:

~~~text
jmsListenerContainerFactory
~~~

Example:

~~~java
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

This is a syntactically valid Spring configuration class when the project has Spring JMS and a `ConnectionFactory` bean; it does not by itself create a project with a broker.

If a listener:

~~~java
@JmsListener(destination = "orders.queue")
public void handle(String payload) {
    // ...
}
~~~

has no `containerFactory` attribute, the default bean above will be selected. If you specify:

~~~java
@JmsListener(
        destination = "orders.priority",
        containerFactory = "priorityFactory")
public void handlePriority(String payload) {
    // ...
}
~~~

then the application must have a bean named `priorityFactory`. This attribute is a **Spring bean name**, not a Queue name or class name.

### 5.1. Creating Multiple Factories Does Not Immediately Create Multiple Containers

You can register three beans (default, priority, topic). However, if no annotated endpoints use them yet, you cannot assume three runtime DMLCs exist. Container count depends on endpoint registrations, not the number of factory beans.

### 5.2. One Method with Multiple Endpoints

`@JmsListener` is a repeatable annotation:

~~~java
@JmsListener(id = "importsA", destination = "imports.a")
@JmsListener(id = "importsB", destination = "imports.b")
public void importData(String payload) {
    // Same Java method, two endpoint registrations.
}
~~~

This is a snippet. Spring can create two DMLCs for the two annotations, even though business code has only one method.

### 5.3. Default Lookup Differs from @Primary

Do not assume `@Primary` on a factory bean replaces the `jmsListenerContainerFactory` naming convention for all `@JmsListener`s. Factory selection has its own rules: default bean name, annotation `containerFactory`, or `JmsListenerConfigurer` registrar default.

## 6. Inside DefaultMessageListenerContainer

`DefaultMessageListenerContainer` (DMLC) is a **polling listener container**. It uses consumer invokers and JMS `MessageConsumer.receive(...)` inside tasks to fetch messages. It is not merely a POJO callback.

~~~text
DefaultMessageListenerContainer (ordersEndpoint)
  |
  +-- JMS Connection / recovery coordination
  |
  +-- consumer invoker #1
  |     +-- JMS Session
  |     +-- JMS MessageConsumer
  |     +-- receive(timeout)
  |     +-- listener adapter -> handler method
  |
  +-- consumer invoker #2 (if concurrency allows)
        +-- JMS Session
        +-- JMS MessageConsumer
        +-- receive(timeout)
        +-- listener adapter -> handler method
~~~

Conceptual diagram: the JMS Connection may be shared/retained or recreated depending on cache level, transaction manager, and `ConnectionFactory` wrapper. Do not claim each invoker has a separate TCP connection.

### 6.1. Steps for a Message

1. Consumer receives a valid message for the destination/selector.
2. DMLC calls the Spring listener adapter.
3. `MessageConverter`/argument resolution turns `TextMessage`, `MapMessage`, and headers into method parameters.
4. Handler processes on the consumer invoker thread.
5. Result or exception returns to the container.
6. Container commits/rolls back/acks according to configuration.
7. Invoker continues receiving or terminates based on stop, failure, or scale-down.

A handler accepting `String` typically receives from `TextMessage` via `SimpleMessageConverter`. For JSON DTOs, configure an `ObjectMapper`/type ID converter and schema validation. **Factory type** does not automatically determine all Java payload types.

### 6.2. Do Not Hand Off the JMS Session to a Background Thread

~~~java
@JmsListener(destination = "jobs.queue")
public void receive(String body, jakarta.jms.Session session) {
    // Do not call session.close() yourself.
    // Do not store session for use outside the callback.
}
~~~

This is a snippet. The Session belongs to the container and has lifecycle/transaction/threading constraints. Using a Session after the container has rolled back/recovered or on another thread can cause errors and inconsistent data.

### 6.3. How Does DMLC Differ from SimpleMessageListenerContainer?

| Characteristic | DefaultMessageListenerContainer | SimpleMessageListenerContainer |
| --- | --- | --- |
| Factory | DefaultJmsListenerContainerFactory | SimpleJmsListenerContainerFactory |
| Receive model | Polling via consumer invokers | JMS provider callback via `setMessageListener` |
| Dynamic consumer scaling | Yes | Not in the DMLC model |
| Recovery/cache tuning | More flexible | Fewer options |
| External transaction management | Supported | More limited |
| Suitable for | Most Spring JMS workloads | Simple systems needing minimal policy |

Do not assume one type is always faster across all providers. Choose based on transaction/recovery/concurrency requirements and measure against a real broker.

## 7. Concurrency: One Container Does Not Mean One Consumer

The factory has:

~~~java
factory.setConcurrency("2-6");
~~~

Per the DMLC API, each container has core/min=2, max=6, and can scale the number of invokers as load grows. This is a setting **per endpoint container**, not a limit across the entire `ApplicationContext`.

**Subtle bug:** a String with a single number, such as `"6"`, is an **upper limit of 6 with a default lower bound of 1**. It is not equivalent to a fixed six consumers.

| Configuration | Core/min | Max | Explanation |
| --- | ---: | ---: | --- |
| "1-1" | 1 | 1 | Fixed one consumer. |
| "2-2" | 2 | 2 | Fixed two consumers. |
| "1-6" | 1 | 6 | Dynamic up to six. |
| "6" | 1 | 6 | A single number is the max. |
| "3-10" | 3 | 10 | Three core, max ten. |

### 7.1. Annotation Override

~~~java
@JmsListener(
    id = "auditEndpoint",
    destination = "audit.queue",
    concurrency = "2-2")
public void audit(String payload) { /* ... */ }
~~~

If the factory has `setConcurrency("1-1")`, the `audit` endpoint is configured individually as 2/2, while the `orders` endpoint stays 1/1. Thus, one factory creates two DMLCs with different settings.

### 7.2. Core/Max vs. Current Consumer Count

~~~java
int core = container.getConcurrentConsumers();
int max = container.getMaxConcurrentConsumers();
int active = container.getActiveConsumerCount();
int scheduled = container.getScheduledConsumerCount();
~~~

This snippet requires a container of type `DefaultMessageListenerContainer`. Core and max are configured values; active/scheduled are runtime metrics that can change with load. Do not treat `max=6` as proof that the broker always has exactly six consumers.

### 7.3. Calculating Total Resource Budget

If you have four endpoints, each core 2/max 5, total configured core can be 8 and max 20 consumers. Broker session limits, DB connection pool, CPU, and executor must suffice for **all endpoints combined**, not just one factory.

### 7.4. Queue Ordering and Topic Fan-Out

Multiple competing Queue consumers can cause message B to finish processing before A even though the producer sent A before B. If the domain requires strict ordering, use low concurrency, grouping, or partitioning/serial processing.

Topic subscriptions have different semantics from Queues. Increasing concurrency on a Topic does not safely increase throughput like a Queue; durable/shared subscriptions require provider-specific design and testing. Separate a topic factory with `pubSubDomain=true` if needed.

## 8. Polling, TaskExecutor, and receiveTimeout

DMLC has these setters:

~~~java
factory.setReceiveTimeout(1_000L);
factory.setConcurrency("1-4");
// factory.setTaskExecutor(taskExecutor); // When using a custom executor.
~~~

`receiveTimeout` is the wait time of **a single `MessageConsumer.receive` call**, not message TTL and not a business method timeout. DMLC can continue polling repeatedly even when a receive returns `null`.

Consumer invoker tasks can be long-lived and hold threads. If you attach a small custom `TaskExecutor` pool shared with HTTP/cron jobs, there is a risk of thread starvation. Bound concurrency and consider a dedicated executor. DMLC already has a default executor for typical use cases.

The `setMaxMessagesPerTask(...)` API limits the number of receive attempts of a consumer task before rescheduling; this is **not a message payload batch size** or the number of JMS messages received in a single receive call. Measure before customizing.

Java 17 does not yet have stable virtual threads. Do not copy Java 21+ examples about DMLC virtual threads and expect them to run in a Java 17 demo.

## 9. JMS Cache, Native ConnectionFactory, and Ownership

DMLC has these cache levels:

| Cache level | Meaning |
| --- | --- |
| CACHE_NONE | Does not cache JMS resources at the DMLC level like higher levels. |
| CACHE_CONNECTION | Caches the appropriate Connection. |
| CACHE_SESSION | Caches Connection and Session. |
| CACHE_CONSUMER | Caches Connection, Session, and MessageConsumer. |
| CACHE_AUTO | Spring selects based on the transaction strategy. |

~~~java
factory.setCacheLevelName("CACHE_CONSUMER");
~~~

This is a snippet. Do not always pick the highest cache level; it may be unsuitable for XA/JTA, recovery, or provider-specific behavior.

Spring provides the `CachingConnectionFactory` wrapper, often useful for `JmsTemplate`. DMLC manages resource caching/recovery itself; nesting an external cache wrapper can complicate closing/reopening connections/consumers.

Spring Boot 3.x provides the `ConnectionFactoryUnwrapper` helper:

~~~java
// Requires importing org.springframework.boot.jms.ConnectionFactoryUnwrapper.
configurer.configure(
        factory,
        ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));
~~~

This is a snippet; variables `configurer`/`factory`/`connectionFactory` must be available. In a real application, check JTA/XA/managed provider proxies; do not unwrap arbitrary `ConnectionFactory` wrappers blindly.

**Do not call `close()` on a JMS Session/Connection provided by DMLC**, do not retain them beyond the lifecycle method, or pass them to another thread. The container/transaction manager has the authority to recreate resources during recovery.

## 10. Transactions, Ack, and Redelivery

### 10.1. Local Transacted Session

~~~java
factory.setSessionTransacted(true);
~~~

With a local JMS transaction, the listener method is invoked within a transacted JMS Session; success typically leads to commit, and an escaping eligible exception leads to rollback. The broker can redeliver per retry policy. A JMS transaction does not automatically cover JDBC transactions, HTTP calls, or sending emails.

### 10.2. AUTO_ACKNOWLEDGE in DMLC

Per Spring DMLC Javadoc, `AUTO_ACKNOWLEDGE` typically acknowledges before the user listener executes, so an exception in the handler carries no reliable redelivery guarantee. Spring recommends `setSessionTransacted(true)` or an appropriate external transaction manager when rollback capability is needed.

### 10.3. Do Not Swallow Exceptions and Report False Success

~~~java
@JmsListener(destination = "orders.queue")
public void receive(String payload) {
    try {
        processOrder(payload);
    } catch (RuntimeException ex) {
        // Logging and returning can cause the container to commit/ack.
    }
}
~~~

This is an anti-pattern; `processOrder` is a hypothetical business method. If business logic requires retries, you must propagate the exception or apply an explicit failure policy, not simply return normally.

### 10.4. Idempotency and External Transactions

The DB can commit and then the JMS commit fails: the broker redelivers, repeating the business side effect. You need business event IDs, an idempotent inbox/unique constraint, transactional outbox, or reconciliation. JTA/XA can help achieve atomic multi-resource commits, but only when supporting infrastructure/resources are actually configured.

### 10.5. Boot Defaults vs. Manual Defaults

Spring Boot's auto-configured listener factory is typically transactional by design: it uses a JTA transaction manager if present, or a local JMS transacted session. A factory instantiated manually with `new` **does not automatically inherit all Boot properties**. If you need to preserve properties/transactions/converters, use `DefaultJmsListenerContainerFactoryConfigurer` or set them explicitly.

## 11. Recovery When the Broker Disconnects

DMLC has logic to refresh JMS resources on provider errors. The factory can configure:

~~~java
factory.setRecoveryInterval(5_000L);
~~~

Or use `BackOff`. This controls retry behavior, not a promise that reconnection will complete in exactly five seconds.

~~~text
Container RUNNING
  → Consumer.receive encounters JMS exception
  → Close/clean up broken handles
  → Recovery/backoff
  → Recreate Connection/Session/Consumer
  → Resume polling on runtime container
~~~

The factory bean itself is not recreated because of a broker restart. Distinguish **recovering JMS resources inside DMLC** from **recreating an endpoint's DMLC instance**.

### 11.1. isRunning Does Not Mean Broker Healthy

A container can report `isRunning=true` while in recovery. Monitor broker consumer count, connection metrics, queue lag, last successful receive, recovery logs, DLQ, and active/scheduled counts—not just registry state.

### 11.2. Start/Stop Lifecycle via Registry

~~~java
registry.stop();
registry.start();
~~~

This snippet acts on registry-managed containers. Stopping does not purge queues, delete messages, or necessarily guarantee all in-flight transactions have committed instantaneously. Rolling deployments require graceful drain, readiness, and idempotency.

## 12. JmsListenerEndpointRegistry: Observing What Was Created

~~~java
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.listener.MessageListenerContainer;

MessageListenerContainer c =
        registry.getListenerContainer("ordersEndpoint");

if (c == null) {
    throw new IllegalStateException("Endpoint missing");
}
System.out.println(c.getClass().getSimpleName());
System.out.println(c.isRunning());
~~~

This snippet requires an injected `registry` bean. A DMLC created from an annotation may not appear in `ApplicationContext` by its ID name, but the registry can provide it.

### 12.1. Registry ID Differs from Destination

~~~java
@JmsListener(
    id = "ordersEndpoint",
    destination = "orders.queue")
public void onOrder(String payload) { /* ... */ }
~~~

`ordersEndpoint` is the ID to manage the container; `orders.queue` is the JMS destination name. Two listeners can listen to the same Queue with different IDs: they act as competing consumers and do not automatically receive two copies. For Topics, subscription semantics differ.

### 12.2. Registry Holds Multiple Containers

~~~java
for (MessageListenerContainer c :
        registry.getListenerContainers()) {
    System.out.println(c.getClass().getSimpleName());
}
~~~

This snippet helps observe the total number of containers, but when distinguishing a specific endpoint, use `getListenerContainer(id)` with an explicit ID.

### 12.3. Do Not Rely Solely on Bean Name

When there are multiple factories or Boot auto-configuration, an endpoint may use a custom factory via the `containerFactory` attribute. Inspect the runtime type and settings of each container; do not assume every endpoint uses the same bean just because they all have `@JmsListener`.

## 13. Demo Java 17, Spring Boot 3.3, Artemis: Two Containers from One Factory

This demo actually creates one factory bean and two `@JmsListener` endpoints:

- `ordersEndpoint`: queue `demo.runtime.orders`, concurrency from the factory is `"1-1"`.
- `auditEndpoint`: queue `demo.runtime.audit`, annotation overrides `concurrency="2-2"`.

The registry returns two DMLCs with **different identities**, of the same class. `JmsTemplate` sends one `TextMessage` to each queue; handlers use `CountDownLatch` so the application prints stdout in a deterministic order.

### 13.1. Environment

Requires Java 17+, Maven 3, Docker, and port 61616 available. Use a dedicated Artemis broker for the demo:

~~~bash
docker run --detach --rm --name dmlc-runtime-demo \
  -p 61616:61616 -p 8161:8161 \
  apache/artemis:latest-alpine
~~~

Wait for Artemis to start before running Maven. Credentials `artemis/artemis` are for a learning environment example, not for production. If the broker disables auto-create, create the two queues with valid ACLs before running. Use a clean broker/queues to avoid receiving messages from a previous run.

Structure:

~~~text
dmlc-runtime-demo/
├── pom.xml
└── src/main/
    ├── java/example/dmlcruntime/
    │   ├── DemoApplication.java
    │   ├── JmsConfig.java
    │   └── TwoQueueListener.java
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
    <artifactId>dmlc-runtime-demo</artifactId>
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

The version is pinned so learners can reproduce the Spring 6/Jakarta JMS APIs; in production deployments, use a supported version per organizational policy.

### 13.3. application.properties

~~~properties
spring.main.web-application-type=none
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis
~~~

No HTTP server is started. Listener containers may continue running after `CommandLineRunner` finishes printing.

### 13.4. JmsConfig.java

~~~java
package example.dmlcruntime;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
public class JmsConfig {

    @Bean("jmsListenerContainerFactory")
    public DefaultJmsListenerContainerFactory factory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory f =
                new DefaultJmsListenerContainerFactory();
        f.setConnectionFactory(connectionFactory);
        f.setPubSubDomain(false);
        f.setSessionTransacted(true);
        f.setConcurrency("1-1");
        f.setReceiveTimeout(1_000L);
        return f;
    }
}
~~~

This is a standalone Spring configuration class. A factory bean provides policy; there is no DMLC until the infrastructure registers endpoints.

### 13.5. TwoQueueListener.java

~~~java
package example.dmlcruntime;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class TwoQueueListener {

    private final CountDownLatch ordersLatch = new CountDownLatch(1);
    private final CountDownLatch auditLatch = new CountDownLatch(1);
    private final AtomicReference<String> order =
            new AtomicReference<>();
    private final AtomicReference<String> audit =
            new AtomicReference<>();

    @JmsListener(
            id = "ordersEndpoint",
            destination = "demo.runtime.orders")
    public void orders(String text) {
        order.set(text);
        ordersLatch.countDown();
    }

    @JmsListener(
            id = "auditEndpoint",
            destination = "demo.runtime.audit",
            concurrency = "2-2")
    public void audit(String text) {
        audit.set(text);
        auditLatch.countDown();
    }

    public boolean awaitBoth(long seconds)
            throws InterruptedException {
        if (!ordersLatch.await(seconds, TimeUnit.SECONDS)) {
            return false;
        }
        return auditLatch.await(seconds, TimeUnit.SECONDS);
    }

    public String orderValue() {
        return order.get();
    }

    public String auditValue() {
        return audit.get();
    }
}
~~~

`CountDownLatch` here only gives the demo deterministic output; it does not certify JMS commit, nor does it replace business idempotency/storage.

### 13.6. DemoApplication.java

~~~java
package example.dmlcruntime;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.listener.DefaultMessageListenerContainer;
import org.springframework.jms.listener.MessageListenerContainer;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CommandLineRunner run(
            JmsTemplate jms,
            JmsListenerEndpointRegistry registry,
            TwoQueueListener listener) {

        return args -> {
            MessageListenerContainer orders =
                    registry.getListenerContainer("ordersEndpoint");
            MessageListenerContainer audit =
                    registry.getListenerContainer("auditEndpoint");

            if (!(orders instanceof DefaultMessageListenerContainer)
                    || !(audit instanceof DefaultMessageListenerContainer)) {
                throw new IllegalStateException(
                        "Expected two DMLC instances");
            }

            DefaultMessageListenerContainer oc =
                    (DefaultMessageListenerContainer) orders;
            DefaultMessageListenerContainer ac =
                    (DefaultMessageListenerContainer) audit;

            System.out.println(
                    "runtime: "
                    + oc.getClass().getSimpleName()
                    + ", " + ac.getClass().getSimpleName());
            System.out.println("distinct: " + (oc != ac));
            System.out.println(
                    "orders core/max: "
                    + oc.getConcurrentConsumers() + "/"
                    + oc.getMaxConcurrentConsumers());
            System.out.println(
                    "audit core/max: "
                    + ac.getConcurrentConsumers() + "/"
                    + ac.getMaxConcurrentConsumers());

            jms.convertAndSend("demo.runtime.orders", "ORDER-42");
            jms.convertAndSend("demo.runtime.audit", "AUDIT-42");

            if (!listener.awaitBoth(10L)) {
                throw new IllegalStateException(
                        "Listeners not invoked in time");
            }
            System.out.println(
                    "payloads: " + listener.orderValue()
                    + " | " + listener.auditValue());
        };
    }
}
~~~

In the code above, two endpoint IDs are retrieved from the registry; the default factory creates two runtime DMLC objects. Both share the same class but have distinct object identities. Because the `audit` annotation specifies `concurrency="2-2"`, the `audit` configuration differs from `orders`.

### 13.7. Run

In the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

If the broker is ready, the queues are clean, there are no competing consumers, and both listeners receive within the timeout, stdout from those `System.out.println` statements is:

~~~text
runtime: DefaultMessageListenerContainer, DefaultMessageListenerContainer
distinct: true
orders core/max: 1/1
audit core/max: 2/2
payloads: ORDER-42 | AUDIT-42
~~~

Spring Boot/Artemis may print additional logs. If the broker is not connected, queues are not allowed to auto-create, or listener processing fails, the demo throws an exception rather than printing a false success.

**Test limitation:** the latch opens when the handler runs, before the container can complete JMS commit. Thus, the output proves the annotated endpoints were deployed and the methods ran, **not** exactly-once or successful commit/ack. When finished, press Ctrl+C to stop the app, then:

~~~bash
docker stop dmlc-runtime-demo
~~~

### 13.8. Extended Experiments

- Change audit `concurrency="2"` and compare with the current core/max. Per the DMLC API, a single string is upper bound 2, default lower bound 1.
- Add a third listener using the same factory; verify the runtime container count increases to three.
- Run two listeners on the same Queue destination to observe competing consumers instead of broadcast.
- Stop a container via the registry and start it again; inspect pending messages and broker metrics.
- Throw an exception in a transacted handler; observe redelivery and idempotency.
- Disconnect and reconnect the broker; inspect recovery logs and JMS consumer count.

## 14. Spring Boot Auto-Configuration and Custom Factories

In Spring Boot with a valid JMS starter/`ConnectionFactory`, the framework can auto-create the default factory for `@JmsListener`. You do not always have to manually declare `@EnableJms` and `@Bean` just to get a basic endpoint.

If you manually declare a bean named `jmsListenerContainerFactory`, Boot may back off per auto-configuration conditions; a manual bean **does not automatically inherit all Boot properties**.

### 14.1. DefaultJmsListenerContainerFactoryConfigurer

Spring Boot 3.x provides the class:

~~~java
import org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer;
~~~

A custom factory can inherit Boot defaults:

~~~java
@Configuration
public class BulkConfig {

    @Bean("bulkListenerFactory")
    DefaultJmsListenerContainerFactory bulkFactory(
            ConnectionFactory connectionFactory,
            DefaultJmsListenerContainerFactoryConfigurer configurer) {

        DefaultJmsListenerContainerFactory f =
                new DefaultJmsListenerContainerFactory();
        configurer.configure(f, connectionFactory);
        f.setConcurrency("2-6");
        return f;
    }
}
~~~

This is a snippet; it requires imports for Jakarta JMS, Spring Bean/Configuration, and Spring JMS classes. Call `configure` first, then override specific policies. With `CachingConnectionFactory`, refer to the guide for using the native connection factory and the unwrap helper matching your Boot version.

### 14.2. Related Boot Properties

~~~properties
spring.jms.listener.min-concurrency=1
spring.jms.listener.max-concurrency=4
spring.jms.listener.auto-startup=true
~~~

These can be applied by the Boot configurer, whereas a manual factory that only calls `setConnectionFactory` will not automatically receive all settings. When a listener has the wrong concurrency or transaction policy, verify the **actual factory the endpoint uses**, not just `application.properties`.

### 14.3. Different Transaction Policies

Boot documentation notes that the auto-configured factory is usually transactional; a freshly instantiated manual factory may not have the same default. Explicitly call `setSessionTransacted(true)` or use the appropriate configurer to avoid unintended differences in acknowledgment/retry.

## 15. Troubleshooting

| Symptom | Causes to Check | Resolution |
| --- | --- | --- |
| `@JmsListener` exists but registry does not show it | JMS infrastructure not enabled or component scan missing | Check `@EnableJms`/Boot and `@Component`. |
| Default factory not found | Bean named differently from `jmsListenerContainerFactory` | Match `@Bean` name or `containerFactory` attribute. |
| Factory bean exists but no DMLC | No endpoints registered | Check `@JmsListener` methods. |
| DMLC Spring bean not found | DMLC is managed by registry, not registered as a separate bean | Use `registry.getListenerContainer(id)`. |
| Found right ID but `isRunning=false` | `autoStartup` disabled or container stopped | Check lifecycle/registry. |
| `isRunning=true` but broker shows no consumers | Recovery/network/ACL/wrong domain | Check logs and broker connections. |
| One factory produces multiple sessions | Multiple endpoints or concurrency > 1 | Calculate total consumer budget. |
| Concurrency `"4"` shows only one core | `"4"` is max, not `4-4` | Use `"4-4"` if fixed is needed. |
| Listener processes out of order | Multiple concurrent consumers | Use grouping/partitioning or reduce concurrency. |
| Broker restarts but listener does not recover | Cache wrapper, recovery strategy | Check DMLC recovery, native CF. |
| No redelivery when handler fails | `AUTO_ACKNOWLEDGE` or swallowed exception | Configure transactions and propagate errors. |
| JSON deserialization error | Converter/DTO/schema mismatch | Inspect raw JMS `Message` and `MessageConverter`. |
| Topic receives duplicate messages | Wrong subscription/concurrency | Separate topic factory, test shared/durable config. |
| Queue has messages but listener does not receive | Selector mismatch, wrong domain/resolver | Inspect JMS properties and broker topology. |
| Manual factory ignores Boot properties | Bypassed configurer | Use configurer or set directly. |
| Mutating factory settings at runtime has no effect | Containers were already created | Control the container directly or roll out. |

### 15.1. Ordered Debugging Procedure

1. Check `ConnectionFactory`/ACL and the actual broker.
2. Check factory bean name/type.
3. Check `@EnableJms`/Boot infrastructure and Spring-managed listener beans.
4. Check `@JmsListener` ID, destination, selector, `containerFactory`, and concurrency.
5. Query the registry and verify the actual runtime container class.
6. Read core/max/active/scheduled consumers, recovery logs, and broker metrics.
7. Check `MessageConverter`, arguments, transaction/ack, and redelivery/DLQ.
8. Run integration tests against the actual broker/provider and versions.

## 16. Misconceptions to Remember

**Wrong 1:** One factory only creates one DMLC. **Right:** A factory can create a separate DMLC for each registered endpoint.

**Wrong 2:** Every arriving message creates a new DMLC. **Right:** The container lives across many receives; internal JMS resources can be refreshed.

**Wrong 3:** The `@JmsListener` ID is the DMLC's bean name. **Right:** It is primarily the key in `JmsListenerEndpointRegistry`.

**Wrong 4:** One DMLC has only one JMS consumer. **Right:** Concurrency can create multiple consumer invokers.

**Wrong 5:** `setConcurrency("4")` always creates a fixed four core consumers. **Right:** DMLC interprets a single string as the maximum; use `"4-4"` for fixed.

**Wrong 6:** `isRunning=true` means the broker connection is healthy. **Right:** The container could still be in recovery; check broker logs/metrics.

**Wrong 7:** A JMS transaction also commits the DB. **Right:** A local JMS transaction only manages JMS; XA/JTA or another design is needed.

**Wrong 8:** Simple factory and Default factory always create the same runtime type. **Right:** One creates `SimpleMessageListenerContainer`, the other creates `DefaultMessageListenerContainer`.

**Wrong 9:** Configuring the factory after startup updates all DMLCs automatically. **Right:** Existing containers have their own state; manage them at runtime or roll out.

**Wrong 10:** JMS `MessageConverter` handles retries itself. **Right:** The converter transforms payloads; ack/recovery/transactions are managed by container policies.

## 17. Checklist and Exercises

### Production Checklist

- [ ] Know which factory bean serves each endpoint.
- [ ] Know the count of annotated endpoint registrations and runtime DMLC instances.
- [ ] Calculate total consumer count from the concurrency of every container.
- [ ] Assign unique, stable endpoint IDs.
- [ ] Queue/Topic and selector/resolver match the contract.
- [ ] Transaction/ack configuration includes idempotency.
- [ ] Tested retry/backoff, recovery, and DLQ.
- [ ] Resource caching/native `ConnectionFactory`/JTA verified.
- [ ] `TaskExecutor`, broker connection/session limits, and DB pool have capacity.
- [ ] Runtime monitoring combines the registry with broker metrics.
- [ ] Graceful shutdown/drain and rolling deployment tested.
- [ ] Do not expect mutating a factory after startup to alter containers automatically.
- [ ] Integration/load tests run against actual broker and Spring versions.

### Exercises

1. Run the demo and confirm two distinct DMLC instances.
2. Add a third `@JmsListener` and observe the registry gaining another container.
3. Compare concurrency `"2"` and `"2-2"` via `getConcurrentConsumers`/`getMaxConcurrentConsumers`.
4. Send 50 messages to observe active/scheduled counts under load.
5. Use two listeners on the same Queue and explain competing-consumer semantics.
6. Create a separate topic factory and verify subscription behavior.
7. Stop the broker while the app is running, inspect recovery logs, then restart it.
8. With JMS transactions enabled, throw an exception and observe redelivery.
9. Rename the factory bean and use the annotation's `containerFactory` attribute to select it properly.
10. Use the Boot configurer to create `bulkFactory` and compare with Boot properties.
11. Write an integration test asserting registry IDs, runtime class, and distinct identities.
12. Compare `DefaultMessageListenerContainer` with `SimpleMessageListenerContainer` under the same workload.

## 18. References

- Spring Framework — Annotation-driven JMS Endpoints: https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html
- Spring Framework — Using JMS / Listener Containers: https://docs.spring.io/spring-framework/reference/integration/jms/using.html
- Spring Framework — Receiving and Transactions: https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html
- Spring Framework 6.2 — DefaultJmsListenerContainerFactory API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html
- Spring Framework 6.2 — AbstractJmsListenerContainerFactory API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/AbstractJmsListenerContainerFactory.html
- Spring Framework 6.2 — DefaultMessageListenerContainer API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html
- Spring Framework 6.2 — JmsListenerEndpointRegistry API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistry.html
- Spring Boot 3.4 — JMS guide (same API line as the Boot 3.3 demo): https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html
- Spring Boot — Getting Started with JMS: https://spring.io/guides/gs/messaging-jms/
- Jakarta Messaging 3.1 specification: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Apache ActiveMQ Artemis — Docker: https://artemis.apache.org/components/artemis/documentation/latest/docker.html
