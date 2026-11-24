# Registering SimpleJmsListenerEndpoint Programmatically in Spring JMS

## 1. Goal and Scope

When a Spring JMS application receives messages, the familiar approach is placing `@JmsListener(destination = "orders.queue")` on a method. Yet not every endpoint is suited to annotation-based declaration. Some systems read a list of Queues from configuration at startup, need to attach a prebuilt `MessageListener`, or must configure each endpoint with its own ID and filter. In those cases, Spring Framework supports **registering JMS listener endpoints in Java code**.

The focus of this lesson is `org.springframework.jms.config.SimpleJmsListenerEndpoint` and the workflow:

1. Enable listener infrastructure with `@EnableJms`.
2. Implement `JmsListenerConfigurer` to receive `JmsListenerEndpointRegistrar`.
3. Create a `SimpleJmsListenerEndpoint` and set `id`, `destination`, and `MessageListener`.
4. Call `registrar.registerEndpoint(endpoint)` or the overload specifying a factory.
5. Let Spring create and manage the listener container via `JmsListenerContainerFactory`.
6. Look up the registered container via `JmsListenerEndpointRegistry` when monitoring or controlling start/stop.

After this lesson, you will:
- Distinguish **endpoint metadata**, **message listener**, **container factory**, **runtime container**, and **endpoint registry**.
- Build a Spring Boot Java 17+ example sending/receiving with an Artemis broker without `@JmsListener` on the receiver.
- Know how to configure multiple endpoints, selectors, concurrency, Queue/Topic, and different factories.
- Distinguish startup-phase registration from **dynamic registration after the application is running**.
- Avoid duplicate IDs, wrong destinations, missing factories, wrong listener types, missing transactions, competing consumers, and lifecycle errors.
- Verify accurately whether callbacks ran, messages committed, the broker acknowledged them, and the endpoint is genuinely owned by the registry.

This lesson uses **Spring Framework 6.x** with **Spring Boot 3.5.8**, **Java 17+**, **Jakarta Messaging (`jakarta.jms.*`)**, and **Apache ActiveMQ Artemis**. The integration example requires an external running broker; compiling Java alone does not prove broker connectivity.

## 2. What Is SimpleJmsListenerEndpoint?

`SimpleJmsListenerEndpoint` is an implementation of `JmsListenerEndpoint`, extending `AbstractJmsListenerEndpoint`. It holds the message reception description (ID, destination, selector, concurrency...) and an actual **`jakarta.jms.MessageListener` object** that will be invoked when messages arrive.

A basic declaration snippet:

```java
SimpleJmsListenerEndpoint endpoint = new SimpleJmsListenerEndpoint();
endpoint.setId("orders-programmatic");
endpoint.setDestination("orders.queue");
endpoint.setMessageListener(message -> {
    // Business handling goes here.
});
```

This only **creates the endpoint model**; it has not yet created a consumer connected to the broker. The snippet above requires importing `org.springframework.jms.config.SimpleJmsListenerEndpoint` and related JMS APIs. To activate the listener, you must **register the endpoint** with Spring's infrastructure.

### 2.1. A Common Confusion Due to Class Names

**`SimpleJmsListenerEndpoint` is NOT `SimpleMessageListenerContainer`.**

- `SimpleJmsListenerEndpoint`: endpoint configuration model holding ID/destination/`MessageListener`. It owns no connection, consumer, executor, or transaction.
- `SimpleMessageListenerContainer`: a specific Spring runtime container type that registers `MessageConsumer.setMessageListener(...)` for provider dispatch.
- `DefaultMessageListenerContainer`: another container type; typically uses worker threads calling `receive`, dispatches to the listener itself, and supports flexible recovery/concurrency.
- `DefaultJmsListenerContainerFactory`: factory creating **`DefaultMessageListenerContainer`** instances from endpoint metadata and shared settings.

Therefore, **registering a `SimpleJmsListenerEndpoint` through `DefaultJmsListenerContainerFactory` still creates a `DefaultMessageListenerContainer`**. The word "Simple" in the endpoint's name does not force you to use the "Simple" container.

### 2.2. Infrastructure Diagram

```text
@EnableJms
   |
   +--> JMS endpoint annotation infrastructure
             |
             +--> @JmsListener methods (if any)
             |
             +--> JmsListenerConfigurer.configureJmsListeners(...)
                         |
                         +--> JmsListenerEndpointRegistrar
                                  |
                                  +--> SimpleJmsListenerEndpoint
                                          id="orders-programmatic"
                                          destination="orders.queue"
                                          messageListener=<bean>
                                  |
                                  +--> JmsListenerContainerFactory
                                           |
                                           v
                                 DefaultMessageListenerContainer
                                           |
                                           v
                                 ConnectionFactory -> Artemis broker

JmsListenerEndpointRegistry
   |
   +--> ["orders-programmatic" -> container runtime]
   +--> manages endpoint container lifecycle
```

`JmsListenerEndpointRegistry` manages containers created via the endpoint infrastructure. **These containers are normally not standalone Spring beans to inject directly by container name.** To access them, use the registry and endpoint ID, e.g., `registry.getListenerContainer("orders-programmatic")`.

### 2.3. Classes and Packages to Remember

| Role | Class/interface | Package |
| --- | --- | --- |
| Enables JMS listener infrastructure | `@EnableJms` | `org.springframework.jms.annotation` |
| Programmatic configuration hook | `JmsListenerConfigurer` | `org.springframework.jms.annotation` |
| Accepts endpoint registration at startup | `JmsListenerEndpointRegistrar` | `org.springframework.jms.config` |
| Simple endpoint model | `SimpleJmsListenerEndpoint` | `org.springframework.jms.config` |
| Endpoint contract | `JmsListenerEndpoint` | `org.springframework.jms.config` |
| Common container factory | `DefaultJmsListenerContainerFactory` | `org.springframework.jms.config` |
| Registry managing containers | `JmsListenerEndpointRegistry` | `org.springframework.jms.config` |
| Raw JMS callback | `MessageListener` | `jakarta.jms` |
| Common runtime container | `DefaultMessageListenerContainer` | `org.springframework.jms.listener` |

Do not accidentally import Rabbit's `RabbitListenerEndpointRegistry` from Spring AMQP; this lesson is **Spring JMS**, using `org.springframework.jms.*`.

## 3. Startup Registration via JmsListenerConfigurer

Spring Framework documents the standard way:

```java
@Configuration
@EnableJms
public class JmsEndpointConfig implements JmsListenerConfigurer {

    @Override
    public void configureJmsListeners(
            JmsListenerEndpointRegistrar registrar) {

        SimpleJmsListenerEndpoint endpoint =
                new SimpleJmsListenerEndpoint();
        endpoint.setId("orders-programmatic");
        endpoint.setDestination("orders.queue");
        endpoint.setMessageListener(message -> {
            // Process message.
        });

        registrar.registerEndpoint(endpoint);
    }
}
```

This is a **condensed configuration snippet**: it requires Spring imports, a JMS provider, a `ConnectionFactory`, and a discoverable `JmsListenerContainerFactory` bean. An endpoint with full ID/destination/listener still cannot run without a suitable container factory.

**Step-by-step roles:**

1. `@Configuration` puts the class into the Spring ApplicationContext.
2. `@EnableJms` registers the endpoint processing infrastructure, covering both annotated methods and the `JmsListenerConfigurer` hook. You do not need a `@JmsListener` method to use this infrastructure.
3. Spring calls `configureJmsListeners(registrar)` while initializing the endpoint infrastructure.
4. `endpoint.setId(...)` uniquely identifies the container/endpoint in the registry.
5. `endpoint.setDestination(...)` sets the **destination name** for the container's `DestinationResolver`. The example uses a direct broker Queue name without JNDI aliases.
6. `endpoint.setMessageListener(...)` provides a Jakarta Messaging callback; Spring invokes it with a JMS `Message` rather than automatically adapting a lambda into a `String`-accepting method signature.
7. `registrar.registerEndpoint(endpoint)` tells the registrar to record the endpoint and use the **default listener container factory** to create its container.
8. During startup, the registry creates, initializes, and manages the container lifecycle, connecting to JMS when the container starts running.

### 3.1. What Is the Endpoint ID Used For?

`setId("orders-programmatic")` is the **runtime ID in the registry**, not the JMSMessageID, Queue name, or listener bean name. For operational needs:

```java
MessageListenerContainer container =
        registry.getListenerContainer("orders-programmatic");

if (container != null) {
    System.out.println("running=" + container.isRunning());
}
```

The snippet above sits inside a Spring bean with `JmsListenerEndpointRegistry registry`; `MessageListenerContainer` is in `org.springframework.jms.listener`.

**Duplicate IDs** colliding with another endpoint (including annotated endpoints sharing the same `id`) cause a registration error, typically `IllegalStateException`. Use a namespaced convention such as `billing-orders-consumer`, `audit-events-consumer`. Add an environment prefix if an application context truly holds multiple similar endpoints, without embedding random hostnames into IDs that make operational lookup harder.

### 3.2. Where Does the Default Factory Come From?

When calling `registrar.registerEndpoint(endpoint)` without a factory argument, the registrar needs **a default factory**. By Spring convention, a bean named `jmsListenerContainerFactory` is used. Without a matching factory, startup may fail to resolve a factory.

A simple factory bean:

```java
@Bean(name = "jmsListenerContainerFactory")
DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory) {

    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setPubSubDomain(false);
    factory.setSessionTransacted(true);
    factory.setConcurrency("1-2");
    return factory;
}
```

This is a snippet placed inside a `@Configuration` class with corresponding imports. `setSessionTransacted(true)` enables local JMS transactions for listeners; `setConcurrency("1-2")` illustrates one to two concurrent consumers depending on load.

If you already have a factory bean with another name, you can select it in the configurer:

```java
registrar.setContainerFactoryBeanName("ordersJmsListenerContainerFactory");
registrar.registerEndpoint(endpoint);
```

This is a **startup configuration snippet**, not an operation for swapping factories on an already running container. There is also the overload:

```java
registrar.registerEndpoint(endpoint, specificFactory);
```

where `specificFactory` is a configured `JmsListenerContainerFactory<?>` instance with proper lifecycle. This overload is useful when the system has multiple factories for different brokers or transaction modes.

### 3.3. What Type Does setMessageListener() Accept?

`SimpleJmsListenerEndpoint.setMessageListener` takes a **`jakarta.jms.MessageListener`**:

```java
endpoint.setMessageListener(message -> {
    if (!(message instanceof TextMessage text)) {
        throw new IllegalArgumentException(
                "Expected TextMessage");
    }
    try {
        process(text.getText());
    } catch (JMSException exception) {
        throw new IllegalStateException(
                "Cannot read JMS body", exception);
    }
});
```

This is a snippet; `process` is an application business method and requires importing `TextMessage`/`JMSException`. `MessageListener.onMessage` **does not declare checked `JMSException`**, so a lambda cannot throw `JMSException` directly. If you want a POJO method `void handle(String payload)` with Spring automatic conversion/argument resolution like `@JmsListener`, consider `MethodJmsListenerEndpoint` or `MessageListenerAdapter` rather than expecting `SimpleJmsListenerEndpoint` to do it automatically.

## 4. Complete Spring Boot Example: Self-Registered Endpoint in Java Code

The example uses **Java 17+, Spring Boot 3.5.8, Apache ActiveMQ Artemis**. The code uses **`SimpleJmsListenerEndpoint` and `JmsListenerConfigurer`, completely without `@JmsListener` on the receiving method**.

Characteristics:
- A `TrainingMessageListener` bean implementing `jakarta.jms.MessageListener`.
- An `EndpointRegistrationConfig` creating `DefaultJmsListenerContainerFactory` and registering endpoint `trainingOrders`.
- An `ApplicationRunner` querying the registry to confirm the endpoint is present, sending a message via `JmsTemplate`, and awaiting the callback with `CountDownLatch`.
- The listener container uses **JMS local transactions** (`sessionTransacted=true`).
- All three Java classes share package `example.jms`, allowing Spring Boot to scan beans without manual scan config.

### 4.1. Prerequisites to Run

- JDK 17+ and Maven.
- An **external Artemis broker** running and listening on `tcp://localhost:61616` or an endpoint passed via environment variables.
- Broker account permitted to send to and receive from Queue `learning.programmatic.queue`.
- The Queue is pre-created, **or** the broker permits Queue auto-creation with matching policy and routing.
- For deterministic demo output, the Queue should initially be clean with no other consumers. If old messages or other replicas consume simultaneously, results may vary.
- Do not put legacy `javax.jms` clients alongside Spring Framework 6.x using `jakarta.jms`.

### 4.2. Directory Structure

```text
programmatic-jms-endpoint/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── example/
        │       └── jms/
        │           ├── ProgrammaticEndpointApplication.java
        │           ├── EndpointRegistrationConfig.java
        │           └── TrainingMessageListener.java
        └── resources/
            └── application.properties
```

### 4.3. Maven pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.8</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>programmatic-jms-endpoint</artifactId>
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
```

`spring-boot-starter-artemis` pulls in compatible Spring JMS/Jakarta client dependencies via Spring Boot dependency management. In applications with a custom BOM, check for version conflicts; never add `javax.jms-api` just to silence a Jakarta JMS compile error.

### 4.4. Connecting to the Broker

**`src/main/resources/application.properties`**

```properties
spring.artemis.mode=native
spring.artemis.broker-url=${JMS_BROKER_URL:tcp://localhost:61616}
spring.artemis.user=${JMS_USERNAME}
spring.artemis.password=${JMS_PASSWORD}

# Queue (point-to-point) instead of Topic:
spring.jms.pub-sub-domain=false

# Example intentionally avoids an external session cache layer outside the listener container:
spring.jms.cache.enabled=false
```

- `spring.artemis.mode=native` uses an Artemis broker external to the application. Maven/config files **do not** start Artemis automatically.
- `JMS_USERNAME` and `JMS_PASSWORD` must be supplied before startup; never commit real credentials to source control.
- `spring.jms.cache.enabled=false` makes the example transparent: the listener container manages JMS resource caching/recovery itself. In real systems, choose raw/cached/pooled connection factories based on workload and provider docs; do not conclude caching is always wrong.
- If the broker uses TLS/HA/failover, replace endpoint and security parameters per Artemis docs instead of copying localhost config to production.

### 4.5. MessageListener Bean (Without @JmsListener)

**`src/main/java/example/jms/TrainingMessageListener.java`**

```java
package example.jms;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageListener;
import jakarta.jms.TextMessage;

import org.springframework.stereotype.Component;

@Component
public final class TrainingMessageListener implements MessageListener {

    private final CountDownLatch observed = new CountDownLatch(1);

    @Override
    public void onMessage(Message message) {
        if (!(message instanceof TextMessage textMessage)) {
            throw new IllegalArgumentException(
                    "Expected a JMS TextMessage");
        }

        try {
            String body = textMessage.getText();
            if (!"demo-175".equals(body)) {
                throw new IllegalArgumentException(
                        "Unexpected body: " + body);
            }

            System.out.println("received=" + body);
            observed.countDown();
        } catch (JMSException exception) {
            throw new IllegalStateException(
                    "Cannot read TextMessage", exception);
        }
    }

    public boolean await(long timeout, TimeUnit unit)
            throws InterruptedException {
        return observed.await(timeout, unit);
    }
}
```

The `TrainingMessageListener` bean is a Spring singleton. By itself, it **does not self-register** with any Queue because it lacks `@JmsListener`. `EndpointRegistrationConfig` in the next step wires this bean into `SimpleJmsListenerEndpoint`.

`CountDownLatch` is a demo way to wait for the callback without busy-polling; it only signals **entry into the callback up to `countDown`**, not that the JMS transaction committed. In production, never use a one-shot latch to coordinate messages; use metrics, event IDs, idempotency, and real business processing.

**Why doesn't the lambda `throws JMSException`?** `MessageListener.onMessage` declares no checked exceptions. `textMessage.getText()` declares `throws JMSException`, so we catch and wrap it as unchecked so the Spring container sees callback failures.

### 4.6. @EnableJms + JmsListenerConfigurer + SimpleJmsListenerEndpoint

**`src/main/java/example/jms/EndpointRegistrationConfig.java`**

```java
package example.jms;

import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListenerConfigurer;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.config.JmsListenerEndpointRegistrar;
import org.springframework.jms.config.SimpleJmsListenerEndpoint;

@Configuration(proxyBeanMethods = false)
@EnableJms
public class EndpointRegistrationConfig implements JmsListenerConfigurer {

    public static final String DESTINATION = "learning.programmatic.queue";
    public static final String ENDPOINT_ID = "trainingOrders";

    private final TrainingMessageListener listener;

    public EndpointRegistrationConfig(TrainingMessageListener listener) {
        this.listener = listener;
    }

    @Bean(name = "jmsListenerContainerFactory")
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1-2");
        return factory;
    }

    @Override
    public void configureJmsListeners(
            JmsListenerEndpointRegistrar registrar) {

        var endpoint = new SimpleJmsListenerEndpoint();
        endpoint.setId(ENDPOINT_ID);
        endpoint.setDestination(DESTINATION);
        endpoint.setMessageListener(listener);

        // Uses default bean named jmsListenerContainerFactory.
        registrar.registerEndpoint(endpoint);
    }
}
```

**This is the centerpiece of the lesson.** It uses the exact `SimpleJmsListenerEndpoint` API and Spring's programmatic endpoint registration mechanism, rather than instantiating `DefaultMessageListenerContainer` manually and calling start by hand.

Points to note:

1. `@EnableJms` enables endpoint infrastructure. If the configuration class is not scanned/imported into the context, `configureJmsListeners` will not run.
2. `JmsListenerConfigurer` is an extension point invoked **when Spring builds the endpoint infrastructure**, not a callback invoked per message.
3. Constructor injection injects the `@Component` `TrainingMessageListener` bean, so the endpoint uses the exact Spring-managed instance.
4. `setId(ENDPOINT_ID)` assigns ID `trainingOrders` for registry management and lookup.
5. `setDestination(DESTINATION)` sets Queue `learning.programmatic.queue`; because the factory has `pubSubDomain=false`, this is a Queue. If JNDI aliases are needed, configure a suitable `DestinationResolver` on the factory.
6. `setMessageListener(listener)` attaches a **real `MessageListener`** to the endpoint. Spring does not turn `onMessage` into an annotated endpoint automatically.
7. `registrar.registerEndpoint(endpoint)` relies on the default factory bean named `jmsListenerContainerFactory`; if that bean is absent and no other default is set, startup fails with a configuration error.
8. `factory.setSessionTransacted(true)` makes the container commit when the listener finishes normally and roll back when an error escapes; the broker can redeliver per policy.
9. `factory.setConcurrency("1-2")` allows the container to run multiple consumers under load. The singleton listener bean must be thread-safe if multiple workers invoke `onMessage` concurrently.
10. Do not call `session.commit()` manually inside `TrainingMessageListener` because the container owns the local JMS transaction.

### 4.7. Application Main: Sending a Message and Checking the Registry

**`src/main/java/example/jms/ProgrammaticEndpointApplication.java`**

```java
package example.jms;

import java.util.concurrent.TimeUnit;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class ProgrammaticEndpointApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProgrammaticEndpointApplication.class, args);
    }

    @Bean
    ApplicationRunner demo(
            JmsTemplate template,
            TrainingMessageListener listener,
            JmsListenerEndpointRegistry registry) {

        return args -> {
            if (registry.getListenerContainer(
                    EndpointRegistrationConfig.ENDPOINT_ID) == null) {
                throw new IllegalStateException(
                        "Programmatic JMS endpoint is not registered");
            }

            System.out.println("endpointRegistered=true");

            template.convertAndSend(
                    EndpointRegistrationConfig.DESTINATION,
                    "demo-175");

            boolean invoked = listener.await(10, TimeUnit.SECONDS);
            System.out.println("listenerInvoked=" + invoked);

            if (!invoked) {
                throw new IllegalStateException(
                        "JMS listener was not invoked within 10 seconds");
            }
        };
    }
}
```

`@SpringBootApplication` scans package `example.jms`, picking up both the `@Component` listener and the `@Configuration` configurer. `ApplicationRunner` executes after context startup to send one message and await the callback.

**Why check the registry before sending?** To clearly separate two errors: an endpoint **not registered by Spring** versus an endpoint registered but **not connecting/receiving messages**. Having a container in the registry **does not prove the broker is ready**; it only checks internal wiring.

**Why is there no `@JmsListener`?** Because this lesson uses `SimpleJmsListenerEndpoint.setMessageListener`. If you also add `@JmsListener` on a method listening to the same Queue, Spring can create a second competing consumer, preventing the demo from receiving the message on the expected instance.

### 4.8. Running It

PowerShell (Windows):

```powershell
$env:JMS_BROKER_URL = "tcp://localhost:61616"
$env:JMS_USERNAME = "dev-user"
$env:JMS_PASSWORD = "dev-password"

mvn spring-boot:run
```

POSIX Shell:

```bash
JMS_BROKER_URL=tcp://localhost:61616 \
JMS_USERNAME=dev-user \
JMS_PASSWORD=dev-password \
mvn spring-boot:run
```

Supply the actual account provided by the broker. If the Queue is not provisioned and the broker disallows auto-create, the application may hit a destination error. Without a broker, Maven can still compile the code, yet running JMS will fail to connect.

When the broker, Queue, and credentials are valid and no other consumer is active, the three lines explicitly printed by the code on the happy path are:

```text
endpointRegistered=true
received=demo-175
listenerInvoked=true
```

Spring Boot, Artemis client, or container logs may interleave. The application's own output order in this example is coordinated: endpoint check before send; listener prints body before `countDown`; runner prints result after `await` succeeds. Thus, in an **isolated environment**, valid output consists of those three lines in that relative order.

**Important warning:** `received=demo-175` and `listenerInvoked=true` confirm the listener executed. `CountDownLatch` is decremented **inside** the callback, potentially before the container commits the local JMS transaction. Therefore, the demo **does not use the latch to claim commit or exactly-once processing**. To test transactions, use integration tests/broker metrics and redelivery scenarios.

Build without a broker:

```bash
mvn -q -DskipTests package
```

Running the project with `mvn spring-boot:run` only succeeds end-to-end when a valid broker and credentials are available. Do not claim the workflow was verified in an environment lacking an Artemis test broker.

## 5. End-to-End Analysis of the Registration Mechanism

There are four distinct phases:

| Phase | What happens | Who performs it |
| --- | --- | --- |
| Java bean creation | `TrainingMessageListener`, `EndpointRegistrationConfig`, `ConnectionFactory`, container factory are created | Spring IoC / Spring Boot |
| Metadata registration | `configureJmsListeners` creates `SimpleJmsListenerEndpoint`, calls `registerEndpoint` | Spring JMS annotation infrastructure + configurer |
| Runtime container creation | Factory configures `DefaultMessageListenerContainer` with destination/listener/transaction/concurrency | `JmsListenerEndpointRegistry` / factory |
| Startup and execution | Container starts consuming from broker, calls `onMessage` when messages arrive | Spring container + JMS provider |

`JmsListenerConfigurer` does not implement a poll loop itself. It describes endpoints to the registrar. Once registered, **the registry owns the container lifecycle**; inside `onMessage`, you never open or close `Connection` or `Session`.

### 5.1. How Are the Registry and Containers Managed?

Spring creates `JmsListenerEndpointRegistry` to track containers registered via the endpoint infrastructure. You can query IDs:

```java
Set<String> ids = registry.getListenerContainerIds();

MessageListenerContainer container =
        registry.getListenerContainer("trainingOrders");

if (container != null) {
    boolean running = container.isRunning();
    // Feed running into health/metrics if needed.
}
```

This is a snippet inside a Spring-managed component with a `registry` field/parameter. Requires importing `java.util.Set` and `org.springframework.jms.listener.MessageListenerContainer`.

**Do not confuse registry containers with container beans:**

- `TrainingMessageListener` is a normal Spring bean.
- `DefaultJmsListenerContainerFactory` is a Spring bean.
- Containers **created by the registry per endpoint** are not necessarily individual Spring beans and usually cannot be injected directly by name.
- Therefore, to stop/start a programmatically registered listener, call `registry.getListenerContainer(endpointId)` and invoke lifecycle methods on that container, rather than looking for `@Qualifier("trainingOrders") DefaultMessageListenerContainer`.

### 5.2. Starting and Stopping at the Right Time

```java
MessageListenerContainer container =
        registry.getListenerContainer("trainingOrders");

if (container != null) {
    container.stop();  // Pause listener.
    // When needing to reopen:
    container.start();
}
```

This is an **operational snippet**, not per-message logic. If the container has messages in flight, stop/shutdown semantics and wait timeouts depend on the container; test graceful draining per workload and provider. Stopping **does not delete the endpoint from the registry or delete the Queue on the broker**. Protect start/stop actions with operational authorization, auditing, and concurrency controls.

### 5.3. Why Not Create a @Bean DefaultMessageListenerContainer for the Same Endpoint?

Those are two ways to solve the same problem with different ownership:

1. **Programmatic endpoint registration:** create `SimpleJmsListenerEndpoint`, register with registrar/registry, let factory/registry manage the container.
2. **Manual container bean:** return a `DefaultMessageListenerContainer` from `@Bean`, manually setting connection factory/destination/listener so Spring manages that bean.

They **do not automatically merge or share a registration**. Using both simultaneously on the same Queue can accidentally spawn **two competing consumers**, skewing observability and increasing concurrency unintentionally.

## 6. Endpoint Options: ID, Selector, Concurrency, Subscription

Besides the three required parameters in the example, `SimpleJmsListenerEndpoint` inherits setters from `AbstractJmsListenerEndpoint`:

| Setter | Meaning | Notes |
| --- | --- | --- |
| `setId(String)` | Endpoint ID in registry | Unique within the same registry; not the Queue name. |
| `setDestination(String)` | Destination name | Resolved by the container's resolver; must match Queue/Topic. |
| `setMessageListener(MessageListener)` | Callback receiving JMS message | Does not auto-convert to a `String` method payload. |
| `setSelector(String)` | JMS selector filtering headers/properties | Does not query inside JSON bodies directly. |
| `setConcurrency(String)` | Overrides concurrency for this endpoint | E.g., `"2-5"`; scaling capability depends on actual container. |
| `setSubscription(String)` | Subscription name for Topic | Valid only with corresponding subscription mode and client ID. |

### 6.1. Selecting by Property with Selector

```java
endpoint.setSelector("eventType = 'ORDER_CREATED'");
```

When the publisher sends a message, it must set the matching JMS property:

```java
jmsTemplate.send("orders.queue", session -> {
    var message = session.createTextMessage("order-created");
    message.setStringProperty("eventType", "ORDER_CREATED");
    return message;
});
```

These are two separate snippets: the first sits inside `configureJmsListeners` **before registration**; the second sits in a service with `JmsTemplate jmsTemplate`. If the Queue holds messages not matching the selector, the endpoint will not receive them. Do not assume "listener not running" means the broker is down before checking selectors.

### 6.2. Per-Endpoint Concurrency

You can set shared concurrency on the factory:

```java
factory.setConcurrency("1-2");
```

Or specify it on the endpoint:

```java
endpoint.setConcurrency("2-4");
```

The second can override the factory level appropriately for that endpoint. With `DefaultMessageListenerContainer`, the range denotes core consumers and max under load; **it does not guarantee four threads are always receiving**. On containers lacking dynamic scaling, ranges may be interpreted differently.

**Caution on ordering:** a Queue with competing consumers processes in parallel; business completion order is not guaranteed to match send order. If ordering per `orderId` is needed, consider broker-supported grouping/partitioning and matching consumer settings.

### 6.3. Queue vs. Topic

The main example uses a Queue:

```java
factory.setPubSubDomain(false);
endpoint.setDestination("orders.queue");
```

To use a Topic, you need **another factory** or a factory configured with `pubSubDomain=true`:

```java
topicFactory.setPubSubDomain(true);
topicEndpoint.setDestination("orders.events");
```

These are snippets; `topicFactory` and `topicEndpoint` must be created separately and registered with the Topic factory. For durable subscriptions, configure `clientId`/subscription name and lifecycle per provider. Do not merely swap a Queue name for a Topic name assuming competing-consumer semantics remain unchanged.

## 7. Multiple Endpoints Built from Configuration at Startup

A major use case for programmatic registration is an application needing many Queues whose names are known only from deployment configuration.

Suppose the service must consume `orders.created` and `orders.cancelled`. Code can loop to create endpoints:

```java
record EndpointSpec(String id, String queue) {}

List<EndpointSpec> specs = List.of(
        new EndpointSpec("orders-created", "orders.created"),
        new EndpointSpec("orders-cancelled", "orders.cancelled")
);

for (EndpointSpec spec : specs) {
    SimpleJmsListenerEndpoint endpoint =
            new SimpleJmsListenerEndpoint();

    endpoint.setId(spec.id());
    endpoint.setDestination(spec.queue());
    endpoint.setMessageListener(message -> {
        // Dispatch message to handler by endpoint type.
        handle(spec.id(), message);
    });

    registrar.registerEndpoint(endpoint);
}
```

This is a **snippet inside `configureJmsListeners`**, assuming `registrar` is present and `handle(String, Message)` is an application-defined method. Requires importing `java.util.List`, `SimpleJmsListenerEndpoint`, and `jakarta.jms.Message` if `Message` is referenced.

Benefits:
- Shares configuration logic and the listener container factory.
- Assigns a distinct ID to each endpoint.
- Allows toggling endpoints via configuration **at startup** instead of compiling annotations onto every method.
- Easily attaches different selectors or concurrency per Queue type.

**However**, avoid losing configuration control:
- Validate Queue names, unique IDs, and endpoint counts before registering.
- Cap how many Queues are created; each Queue/endpoint can consume multiple connections/sessions/threads.
- Avoid taking IDs/destinations directly from untrusted runtime input once broker permissions exist.
- Never share one singleton `MessageListener` with non-thread-safe mutable state across dozens of endpoints/concurrent consumers.
- With hundreds of concurrent Queues, budget broker load, connection/session pools, retries, and monitoring before writing an unbounded loop.

### 7.1. Receiving Config via @ConfigurationProperties

In Spring Boot, you can bind an endpoint list from `application.yml` into a `@ConfigurationProperties` class and inject it into the configurer. Then loop over the list inside `configureJmsListeners` as above.

Idea:

```yaml
app:
  jms:
    endpoints:
      - id: orders-created
        destination: orders.created
      - id: orders-cancelled
        destination: orders.cancelled
```

This sample config **does not work automatically without defining/enabling `@ConfigurationProperties` binding**. When used, validate for unique IDs, non-blank destination names, and an allowlist matching broker policy.

**Distinguish** two kinds of changes: editing config and **restarting the Spring context** versus registering endpoints **after startup**. `JmsListenerConfigurer` runs when infrastructure initializes, not automatically whenever a config file changes on the filesystem.

## 8. Post-Startup Registration: Using JmsListenerEndpointRegistry

This differs from `configureJmsListeners`. If a system **genuinely needs to add another endpoint after the ApplicationContext is already running**, Spring provides:

```java
registry.registerListenerContainer(
        endpoint, listenerContainerFactory, true);
```

Here:
- `endpoint` is a fully configured `JmsListenerEndpoint` (ID/destination/listener).
- `listenerContainerFactory` is the factory creating the container.
- `true` requests starting immediately if appropriate for the lifecycle.
- The registry holds the newly created container for ID-based management.

**Minimal service example:**

```java
package example.jms;

import jakarta.jms.MessageListener;

import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.config.SimpleJmsListenerEndpoint;
import org.springframework.stereotype.Service;

@Service
public class RuntimeEndpointRegistration {

    private final JmsListenerEndpointRegistry registry;
    private final DefaultJmsListenerContainerFactory factory;

    public RuntimeEndpointRegistration(
            JmsListenerEndpointRegistry registry,
            DefaultJmsListenerContainerFactory factory) {
        this.registry = registry;
        this.factory = factory;
    }

    public void register(
            String endpointId, String destination, MessageListener listener) {

        var endpoint = new SimpleJmsListenerEndpoint();
        endpoint.setId(endpointId);
        endpoint.setDestination(destination);
        endpoint.setMessageListener(listener);

        registry.registerListenerContainer(endpoint, factory, true);
    }
}
```

This is a **syntactically complete Java class** inside a Spring project with configured registry/factory beans, though not standalone runnable; it has no `main` or broker provisioning. With section 4's startup example, if you add this class, do not call `register("trainingOrders", ...)` because that ID already exists: the registry will report a duplicate ID.

**Why doesn't the runtime API use the registrar?** `JmsListenerEndpointRegistrar` collects endpoints **during configuration**, whereas the registry creates/manages actual containers and exposes `registerListenerContainer`. Never stash the registrar in a singleton and call `registerEndpoint` arbitrarily from HTTP requests after startup.

### 8.1. Safety Conditions for Dynamic Registration

Calling the registry directly carries greater operational responsibility than startup config:
- Protect with administrative privileges and auditing: never let untrusted requests spawn consumers on arbitrary destinations.
- Validate ID/selector/destination and ensure no collision with already registered containers.
- Account for concurrency when multiple threads add endpoints simultaneously.
- Have a strategy if registration fails while the broker is disconnected.
- Plan stop/restart and endpoint lifetimes; `stop()` does not remove entries from the registry.
- Changing Queue names should handle draining, old messages, and proper rollouts rather than mutating a registered endpoint object expecting the container to update automatically.
- Avoid creating duplicate endpoints across every replica if only one consumer should run at a time. On a Queue, multiple replicas become competing consumers, which may or may not fit your business logic.

**Do not assume your version of the registry has a remove/unregister API identical to Spring AMQP.** Registry interfaces differ across technologies. For complex dynamic lifecycles, read the exact Spring Framework Javadoc and design cleanup/stop explicitly.

## 9. Transactions, Acknowledgements, and Error Handling

### 9.1. Endpoints Do Not Decide Transactions Alone

`SimpleJmsListenerEndpoint` only describes how messages are dispatched. **Acknowledgement and transactions** are governed primarily by the listener container/factory:

```java
factory.setSessionTransacted(true);
```

In section 4's example, the factory creates a container with **JMS local transactions**. After `MessageListener.onMessage` returns normally, the container commits. If the callback throws an exception, the container can roll back and the broker redelivers.

Do not place `@Transactional` on the configurer class expecting callbacks to automatically run in transactions; transaction boundaries belong on **the container factory, transaction manager, or listener business boundary** appropriately. A database transaction is not automatically atomic with a local JMS transaction.

### 9.2. Spring DMLC and Raw MessageListener Differ

`DefaultMessageListenerContainer` can invoke a `MessageListener` while receiving messages on Spring worker threads, rather than necessarily registering a raw provider callback `MessageConsumer.setMessageListener`. Thus applications should follow **container transaction rules** instead of assuming callbacks always run under a raw async provider handler.

If a factory uses `SimpleJmsListenerContainerFactory` (where available), callback mechanics stay closer to the JMS provider, with different recovery/concurrency and transaction restrictions. **Never choose a factory based solely on the word "Simple" in the endpoint name.**

### 9.3. Never Swallow Exceptions When Rollback Is Needed

```java
@Override
public void onMessage(Message message) {
    try {
        processOrder(message);
    } catch (RuntimeException ex) {
        logger.error("Unable to process", ex);
        // Returning normally -> container may COMMIT.
    }
}
```

This is an **illustrative anti-pattern**; `processOrder`/`logger` are undefined and this is not runnable standalone code. If business logic fails and needs broker redelivery, **let the exception propagate** when using a transacted container or apply proper rollback policies. To stop retrying poison messages, configure a DLQ/parking queue or durable error logging rather than catching every exception and committing silently.

### 9.4. JMS Transactions and Databases Are Not One

For example, the listener writes an order to SQL and then the JVM dies before the JMS commit. The broker can redeliver the event, causing the handler to insert into SQL again. Never treat `setSessionTransacted(true)` as a distributed transaction.

Common solutions:
- **Idempotent consumer** using a business `eventId` as a deduplication key.
- **Inbox table** recording processed events inside the same database transaction.
- **Transactional outbox** on the publisher when DB changes must reliably emit messages.
- JTA/XA when infrastructure truly supports it and requirements justify the substantial operational overhead.

### 9.5. Selectors Cannot Rescue Business Errors

If an endpoint sets the wrong `selector`, the listener may receive zero messages despite a Queue backlog. If set too broadly, incompatible payloads hit the listener and fail conversion. Use clear property schemas, per-destination/type metrics, and test selectors against the broker.

## 10. Comparing Listener Registration Approaches in Spring

| Approach | Example | Benefits | Limitations |
| --- | --- | --- | --- |
| `@JmsListener` | Annotate `handle(String body)` | Concise; Spring converters and parameter resolvers support POJOs | Endpoint names tied directly to code/annotations; less flexible for dynamic config lists. |
| `SimpleJmsListenerEndpoint` + registrar | `registrar.registerEndpoint(endpoint)` | Programmatic startup registration; customizable ID/destination/listener | Must supply raw `MessageListener` and configure factory. |
| `MethodJmsListenerEndpoint` | Describes bean + method + handler factory | Programmatically registers a method with argument resolution | More complex setup API; distinct from `SimpleJmsListenerEndpoint`. |
| Manual `DefaultMessageListenerContainer` bean | `new` container inside `@Bean` | Fine-grained control of the container bean | Must wire many properties/lifecycle manually; does not automatically use the endpoint registry the same way. |
| Runtime `registry.registerListenerContainer(...)` | Add endpoints after context starts | Supports runtime admin-driven registration | Requires permissions, validation, duplicate prevention, auditing, and shutdown strategy. |

### Conceptually Equivalent Annotation Example

```java
@Component
public class OrdersAnnotatedReceiver {

    @JmsListener(
            id = "orders-programmatic",
            destination = "orders.queue")
    public void handle(String body) {
        System.out.println("received=" + body);
    }
}
```

This is an **alternative option**; do not place it into the same ApplicationContext that already registered a `SimpleJmsListenerEndpoint` with **the same ID**. Registering duplicate IDs causes a registry error. Using a different ID on the same Queue creates two competing consumers, making single-spot log expectations unreliable.

`@JmsListener` can automatically invoke converters to map JMS `TextMessage` to `String`, whereas `SimpleJmsListenerEndpoint`'s raw `MessageListener` must read/cast `Message` itself or use a `MessageListenerAdapter` you configure.

## 11. Common Errors with Programmatic Registration

| Symptom | Common Cause | How to Fix |
| --- | --- | --- |
| `configureJmsListeners` never runs | Missing `@EnableJms` or config class outside component scan | Ensure config is loaded and annotation infrastructure is enabled. |
| Startup reports missing listener container factory | `registrar.registerEndpoint(endpoint)` cannot find default factory | Declare `jmsListenerContainerFactory` bean or pass factory to registrar. |
| `Another endpoint is already registered with id ...` | Duplicate ID across code/annotations/runtime | Use unique IDs and enforce a naming convention. |
| `getListenerContainer(id) == null` | Wrong ID or endpoint not registered yet | Check exact ID, startup timing, and that configurer ran. |
| Endpoint in registry yet receives no messages | Broker offline, wrong Queue, credentials/permissions, another consumer, selector mismatch | Check broker health, address/queue routing, metrics, destination, and selector. |
| `ClassCastException`/`IllegalArgumentException` from listener | Raw `MessageListener` received unexpected message type | Use `instanceof`, schema validation, and suitable converters/adapters. |
| Cannot `@Autowired` `DefaultMessageListenerContainer` | Registry-managed container is not a direct bean | Fetch via `registry.getListenerContainer(endpointId)`. |
| Used `SimpleJmsListenerEndpoint` expecting SMLC | Confused endpoint metadata with container type | Check container factory; `DefaultJmsListenerContainerFactory` builds DMLC. |
| Listener throws exception yet message not redelivered | AUTO_ACKNOWLEDGE, or callback caught and ignored error | Enable JMS local transactions if needed; let exceptions reach container. |
| Message processed twice | JMS rollback/redelivery, broker restart, publisher retry | Use eventId/idempotency; inspect delivery count and DLQ. |
| Higher concurrency changes processing order | Multiple sessions/competing consumers | Test ordering/message grouping; do not promise global FIFO business processing. |
| Endpoint created twice on deployment | Two registration paths or two configurers creating the same ID | Keep one registration owner per endpoint; QA the ID list. |
| Mutating endpoint object at runtime does not change listener | Container was already built from old metadata | Perform rolling restart or controlled re-registration. |
| Runtime-added endpoint does not start | Called `registerListenerContainer` overload without immediate start | Pass `startImmediately=true` when appropriate or start container per lifecycle. |
| Broker connected yet physical Queue missing | Java destination name does not guarantee Queue provisioning | Admin creates Queue or enables auto-create per broker policy. |
| Confused Spring JMS with Spring AMQP | Wrongly imported `RabbitListenerEndpointRegistry` | Use `org.springframework.jms.config.JmsListenerEndpointRegistry`. |

## 12. Testing Programmatic Endpoints in Practice

### 12.1. Unit Testing Endpoint Config Without a Broker

You can mock `JmsListenerEndpointRegistrar` with Mockito or test the configurer class in a test ApplicationContext. A simple check verifies:
- `configureJmsListeners` was invoked.
- The registered endpoint has the exact `id`, `destination`, and `MessageListener`.
- The default factory is set/declared properly.

Pseudo-test:

```java
// JUnit + Mockito snippet; not a standalone test class.
var registrar = mock(JmsListenerEndpointRegistrar.class);
var configurer = new EndpointRegistrationConfig(listener);

configurer.configureJmsListeners(registrar);

verify(registrar).registerEndpoint(
        argThat(endpoint ->
                "trainingOrders".equals(endpoint.getId())
                && "learning.programmatic.queue".equals(
                        endpoint.getDestination())));
```

`listener`, `mock`, `verify`, and `argThat` come from your test fixtures/libraries. This tests **wiring**, not real JMS delivery. With strict Mockito typing where `argThat` must match an overload, configure mock/test imports accordingly.

### 12.2. Integration: One Endpoint, One Queue

1. Start an Artemis test broker with Queue `learning.programmatic.queue`.
2. Load the example's Spring context; only **one** endpoint ID `trainingOrders` exists.
3. Assert `registry.getListenerContainer("trainingOrders") != null`.
4. Send a message with a controlled eventId/payload.
5. Wait for the callback via Awaitility or CountDownLatch for a few seconds.
6. Verify body/headers and zero exceptions from the listener.
7. If you need to verify transaction commit, inspect broker state and test failure/rollback separately; never treat the latch as commit proof.

### 12.3. Negative Tests: Duplicate IDs and Missing Factory

- Register a second endpoint with the same ID in another configurer and verify startup fails instead of silently overwriting.
- Remove the `jmsListenerContainerFactory` bean from the test context without declaring a default factory; verify configuration failure.
- Try registering an endpoint missing `destination` or `messageListener` and verify validation/initialization fails per API.

### 12.4. Broker Failures and Redelivery

- Stop and restart the broker; verify DMLC recovery/backoff.
- Have the callback throw an exception in a transacted container; the broker should redeliver per policy, potentially with delay/DLQ.
- Simulate listener SQL commit succeeded followed by JMS commit failure; verify the application handles duplicate eventIds.
- Test listener lifecycle: start, stop, and graceful shutdown without spawning duplicate consumers.

### 12.5. Multi-Endpoint and Selectors

- Register two distinct endpoint IDs pointing to separate Queues; send payloads with selector properties.
- Verify each listener receives only matching message types.
- If multiple endpoints share one Queue, verify **competing consumer** behavior rather than expecting each endpoint to receive a copy.
- Monitor open broker sessions/consumers and latency as endpoint counts grow.

## 13. Pre-Production Checklist

- Enable `@EnableJms` and ensure `JmsListenerConfigurer` is scanned by Spring.
- Assign a unique `id`, exact `destination`, and suitable `MessageListener` for each endpoint.
- Configure the default container factory named `jmsListenerContainerFactory` or specify factories explicitly.
- Do not confuse `SimpleJmsListenerEndpoint` with `SimpleMessageListenerContainer`; the factory decides the container type.
- Let Spring's registry manage lifecycle; never close connections/sessions inside callbacks.
- Consider `sessionTransacted=true` for critical work Queues and understand redelivery/DLQ/poison messages.
- Test listener bean thread safety under chosen concurrency; never rely on global ordering with multiple consumers.
- Implement eventIds, idempotency, and deduplication when downstream databases/APIs have side effects.
- Restrict runtime registration behind admin privileges, validate inputs, and prevent unbounded endpoint creation.
- Verify broker URLs, credentials, Queues/Topics, selectors, and TLS rather than inferring health from `registry != null`.
- Monitor registry IDs, container running state, Queue depth, redeliveries, and error counters.
- Test startup, missing factory, duplicate IDs, broker outages, restarts, stop/start, and commit semantics.

## 14. Self-Check Questions

**1.** Why doesn't `new SimpleJmsListenerEndpoint()` automatically create a consumer on the broker?

Because it is **endpoint metadata**. You must call `registrar.registerEndpoint` (startup) or the registry API (runtime) so a factory builds the container and starts receiving.

**2.** Does `SimpleJmsListenerEndpoint` force using `SimpleMessageListenerContainer`?

No. Choosing `DefaultJmsListenerContainerFactory` creates a `DefaultMessageListenerContainer` despite "Simple" in the endpoint name.

**3.** Which method does Spring invoke for code to self-register endpoints at startup?

`JmsListenerConfigurer.configureJmsListeners(JmsListenerEndpointRegistrar registrar)`, inside which your code calls `registrar.registerEndpoint(endpoint)`.

**4.** If you call `registrar.registerEndpoint(endpoint)` without passing a factory, what is required?

A default `JmsListenerContainerFactory`, usually a bean named `jmsListenerContainerFactory` or a default factory configured on the configurer.

**5.** To retrieve a registered container by ID, which API do you use?

`JmsListenerEndpointRegistry.getListenerContainer(endpointId)`. Registry-managed containers are not necessarily directly injectable beans.

**6.** To add another endpoint after the Spring context is already running, should you manually call `configureJmsListeners` again?

No. Use `JmsListenerEndpointRegistry.registerListenerContainer(endpoint, factory, true)` with proper policies and authorization.

**7.** Once the callback logs `received=demo-175`, is it certain that both JMS and database transactions committed?

No. Logs/callbacks can run before the JMS commit; local JMS transactions do not include database transactions.

**8.** With the same Queue and two different IDs, do both endpoints receive every message?

Not in normal Queue competing-consumer setups. Each message goes to one consumer at a time; broadcasting requires a Topic and matching subscriptions.

## Conclusion

`SimpleJmsListenerEndpoint` lets you describe **listener endpoints in Java code**: create the endpoint, set its **ID**, **destination**, and **`MessageListener`**, then register it via **`JmsListenerConfigurer` / `JmsListenerEndpointRegistrar`**. Spring uses **`JmsListenerContainerFactory`** to build the runtime container and manages it in **`JmsListenerEndpointRegistry`**. This is especially useful when listener lists or endpoint configurations must be determined **at startup**, rather than annotating individual methods with `@JmsListener`.

In production, cleanly separate startup configuration from runtime registration; enforce unique IDs, valid destinations/selectors, transactions, concurrency, and lifecycle controls. An endpoint appearing in the registry proves registration succeeded, **not that the broker/Queue can deliver messages or that business work committed**. Pair it with integration tests, idempotency, and operational monitoring.

## References

- Spring Framework 6.2 — *Annotation-driven Listener Endpoints*, section *Programmatic Endpoint Registration*: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html
- Spring Framework 6.2 — `SimpleJmsListenerEndpoint` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/SimpleJmsListenerEndpoint.html
- Spring Framework 6.2 — `AbstractJmsListenerEndpoint` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/AbstractJmsListenerEndpoint.html
- Spring Framework 6.2 — `JmsListenerConfigurer` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/annotation/JmsListenerConfigurer.html
- Spring Framework 6.2 — `JmsListenerEndpointRegistrar` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistrar.html
- Spring Framework 6.2 — `JmsListenerEndpointRegistry` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistry.html
- Spring Framework — *Using Spring JMS* / listener containers: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html
- Spring Boot 3.5 — JMS & Artemis integration: https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html
- Spring Boot 3.5 — Common application properties: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/
- Jakarta Messaging 3.1 — `MessageListener` API: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messagelistener
- Apache ActiveMQ Artemis — Using JMS: https://artemis.apache.org/components/artemis/documentation/latest/using-jms