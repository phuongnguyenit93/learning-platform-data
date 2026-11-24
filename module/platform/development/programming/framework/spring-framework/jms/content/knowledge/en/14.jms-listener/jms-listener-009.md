# JmsListenerConfigurer and JmsListenerEndpointRegistrar in Spring JMS

> **Context:** Spring Framework JMS, specifically the `@JmsListener` mechanism and registering message listener endpoints via Java configuration.  
> **Goal:** Distinguish `JmsListenerConfigurer`, `JmsListenerEndpointRegistrar`, `JmsListenerEndpointRegistry`, `JmsListenerEndpoint`, and `JmsListenerContainerFactory`; know when to use annotations versus programmatic endpoint registration; build a Java 17+ application with both listener styles; understand transactions, ID management, method invocation configuration, lifecycle, and limits of dynamic registration.

**Illustrative versions:** Spring Framework 6.2.x, Spring Boot 3.5.x, Jakarta Messaging (`jakarta.jms`), and Apache ActiveMQ Artemis in the hands-on example. Spring 5.x uses `javax.jms`; do not mix the legacy namespace with Java 17+/Boot 3.x.

## 1. The Problem These Two Components Solve

For simple cases, Spring lets you declare a method as a JMS consumer:

~~~java
@Component
class OrderConsumer {
    @JmsListener(destination = "orders.in")
    public void onOrder(String orderId) {
        // Process message.
    }
}
~~~

Spring detects the annotation, creates a listener container, and invokes the method when a message arrives. Yet real applications may want to:

- Change the **default listener container factory** for all endpoints that do not specify `containerFactory`.
- Configure parameter conversion/validation for **`@JmsListener` methods**.
- Register **new endpoints programmatically** instead of annotating a specific method.
- Use queues/selectors/subscriptions determined from trusted configuration at startup.
- Bind different endpoints to different factories (transactions, concurrency, destination resolvers...).
- Retrieve a listener container's ID to observe, pause, or restart it operationally.

`JmsListenerConfigurer` and `JmsListenerEndpointRegistrar` are designed for **startup-time customization and registration**, whereas `JmsListenerEndpointRegistry` manages containers throughout the application's lifecycle.

### Quick Reference Formula

~~~text
@JmsListener     -> way to declare an endpoint on a method
JmsListenerConfigurer
                 -> where Spring invokes custom endpoint registration code
JmsListenerEndpointRegistrar
                 -> object receiving configuration and endpoint declarations
JmsListenerEndpoint
                 -> describes an endpoint (ID, destination, callback...)
JmsListenerContainerFactory
                 -> creates MessageListenerContainer from endpoint description
JmsListenerEndpointRegistry
                 -> holds, looks up, and manages container lifecycles
MessageListenerContainer
                 -> runs JMS consumer, session, polling/callback, and listener
~~~

**Mistake to avoid:** the registrar is **neither** a producer/consumer **nor** the registry of running containers. It is the bridge that **feeds endpoint declarations into container creation**.

## 2. Accurately Distinguishing Each API

| Component | Spring Package | Primary Role | Example Operation |
| --- | --- | --- | --- |
| `@JmsListener` | `org.springframework.jms.annotation` | Attaches destination/ID/selector/factory to a Java method | `@JmsListener(destination="orders.in")` |
| `@EnableJms` | `org.springframework.jms.annotation` | Enables listener annotation discovery infrastructure | Placed on `@Configuration` or app class |
| `JmsListenerConfigurer` | `org.springframework.jms.annotation` | Callback to customize listener registration | `configureJmsListeners(registrar)` |
| `JmsListenerEndpointRegistrar` | `org.springframework.jms.config` | Accepts endpoints/factories and handler method factory | `registerEndpoint(endpoint, factory)` |
| `JmsListenerEndpoint` | `org.springframework.jms.config` | Endpoint model, not directly a consumer | `getId()`, `getDestination()`... |
| `SimpleJmsListenerEndpoint` | `org.springframework.jms.config` | Endpoint using a raw JMS `MessageListener` | `setMessageListener(...)` |
| `MethodJmsListenerEndpoint` | `org.springframework.jms.config` | Endpoint model invoking a Java method | Used in method-based listener infrastructure |
| `JmsListenerContainerFactory<?>` | `org.springframework.jms.config` | Strategy for creating a container from an endpoint | `createListenerContainer(endpoint)` |
| `DefaultJmsListenerContainerFactory` | `org.springframework.jms.config` | Creates `DefaultMessageListenerContainer` | `setSessionTransacted(true)` |
| `JmsListenerEndpointRegistry` | `org.springframework.jms.config` | Owns/queries/controls registered listener containers | `getListenerContainer(id)`, `stop()` |

### 2.1. The Registrar Only Performs Registration

The `JmsListenerConfigurer` interface has exactly one callback to implement:

~~~java
@Override
public void configureJmsListeners(
        JmsListenerEndpointRegistrar registrar) {
    // Set default factory, method factory, or register endpoints.
}
~~~

Spring invokes this callback via the listener annotation infrastructure when initializing the application context. You do **not** instantiate an arbitrary `JmsListenerEndpointRegistrar` yourself expecting listeners to activate: Spring creates it and wires it to the context's registry.

### 2.2. An Endpoint Is Not a Container

`SimpleJmsListenerEndpoint` only describes an endpoint. Calling:

~~~java
var endpoint = new SimpleJmsListenerEndpoint();
endpoint.setId("ordersDynamic");
endpoint.setDestination("orders.in");
endpoint.setMessageListener(message -> {
    // callback processing raw JMS Message
});
~~~

**does not create a consumer** or open a connection yet. After `registrar.registerEndpoint(...)`, the infrastructure uses a factory to build the container, and the registry coordinates its lifecycle. One endpoint normally corresponds to one listener container; the container may open multiple JMS consumers if concurrency is configured.

### 2.3. The Registry Is Where You See the Actual Container

You can inject `JmsListenerEndpointRegistry` and do:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("ordersDynamic");

if (container != null) {
    System.out.println("running=" + container.isRunning());
}
~~~

This is a **code snippet inside a Spring bean**; it requires importing the registry and `org.springframework.jms.listener.MessageListenerContainer`. The registry also holds containers generated from `@JmsListener` whose IDs were registered by the infrastructure. Those containers **are not necessarily standalone Spring beans**, so do not try to autowire a container bean by endpoint name.

## 3. Lifecycle from Annotation/Configurer to JMS Consumer

Mechanism diagram:

~~~text
@SpringBootApplication / @EnableJms
                |
  JmsListenerAnnotationBeanPostProcessor
                |
       scans @JmsListener methods
                |
      discovers JmsListenerConfigurer
                |
  configureJmsListeners(registrar)
        |                |
        |                +--> registerEndpoint(SimpleJmsListenerEndpoint)
        |
        +--> setContainerFactory / setMessageHandlerMethodFactory
                |
      JmsListenerEndpointRegistrar
                |
        JmsListenerEndpointRegistry
                |
      JmsListenerContainerFactory
                |
        MessageListenerContainer
                |
       jakarta.jms.Consumer(s)
                |
           JMS broker
~~~

Separate **two phases**:

1. **Startup registration:** reads annotations, calls `configureJmsListeners`, gathers endpoint definitions, creates containers, and manages them via the registry.
2. **Runtime operations:** queries status, stops/starts, and when needed registers an additional endpoint via the **registry** with a specific factory. This is **not** when the startup registrar runs again.

Do not think `configureJmsListeners` is called per message or on every broker reconnect. It is an **infrastructure configuration** callback during bootstrap, not a business handler.

### Note on Spring Boot

Spring Boot can auto-configure JMS infrastructure when the starter is enabled, and in standard setups can detect `@JmsListener` without explicitly declaring `@EnableJms`. In the Java configuration examples and lab below, **`@EnableJms` is placed explicitly** to highlight the Spring mechanism. Do not declare duplicate special infrastructure beans if Boot already configures them sufficiently.

## 4. When to Use @JmsListener vs. Implementing JmsListenerConfigurer

| Scenario | Usually Suitable Approach | Why |
| --- | --- | --- |
| Fixed queue and Java method handler | `@JmsListener` | Concise, convenient type conversion/argument resolution |
| Multiple fixed listeners with different factories | `@JmsListener(containerFactory="...")` | Clear endpoint–factory relationship |
| Changing default factory for listeners that omit it | `JmsListenerConfigurer` + `registrar.setContainerFactory(...)` | Centralized configuration |
| Configuring method argument conversion/validators | `registrar.setMessageHandlerMethodFactory(...)` | Affects invocation of annotated method endpoints |
| Endpoints determined by trusted config at startup | `JmsListenerConfigurer` + `registerEndpoint(...)` | Avoids compiling separate annotations per config |
| Raw JMS `MessageListener` callback handling | `SimpleJmsListenerEndpoint` | No `@JmsListener` method argument binding |
| Managing container stop/start by ID | `JmsListenerEndpointRegistry` | Runtime lifecycle management |
| Adding/removing endpoints **while app is running** | Registry APIs + a controlled coordinator | Do not use startup registrar as a dynamic registry |
| Multi-tenant system with thousands of dynamic queues | Evaluate topology + broker and factory limits | Each endpoint/container has overhead; never create unboundedly from user input |

**You do not need all three components every time you use `@JmsListener`.** A simple annotation may suffice; bring in configurer/registrar only when actual configuration needs demand them.

## 5. The configureJmsListeners Callback and Key Methods

Inside `JmsListenerConfigurer.configureJmsListeners(JmsListenerEndpointRegistrar registrar)`, there are three main customization groups:

### 5.1. Selecting the Default Container Factory

~~~java
@Override
public void configureJmsListeners(
        JmsListenerEndpointRegistrar registrar) {
    registrar.setContainerFactory(myFactory);
}
~~~

When an endpoint is registered **without an explicit factory**, the registrar uses the default. You can also set it by bean name:

~~~java
registrar.setContainerFactoryBeanName("jmsListenerContainerFactory");
~~~

This name must reference an **existing factory bean**, and the resolver/bean factory context must be wired properly. Do not mistake the name string for a destination or listener container ID.

An endpoint registered with an explicit factory can be added via:

~~~java
registrar.registerEndpoint(endpoint, highReliabilityFactory);
~~~

With this call, the passed factory **takes precedence for that specific endpoint**, independent of the default. This is the safe pattern when different listener types require different transaction/concurrency policies.

### 5.2. Registering an Endpoint Programmatically

~~~java
@Override
public void configureJmsListeners(
        JmsListenerEndpointRegistrar registrar) {
    SimpleJmsListenerEndpoint endpoint =
            new SimpleJmsListenerEndpoint();

    endpoint.setId("auditEvents");
    endpoint.setDestination("audit.events");
    endpoint.setMessageListener(message -> {
        // Read jakarta.jms.Message and process.
    });

    registrar.registerEndpoint(endpoint, auditFactory);
}
~~~

Requirements:
- `auditFactory` is a managed/configured `JmsListenerContainerFactory`.
- `"auditEvents"` is a **unique ID in the registry**, not the queue name.
- `"audit.events"` is the broker **destination**; multiple endpoints may point to the same destination, creating competing consumers if it is a Queue.
- `MessageListener.onMessage(Message)` cannot throw checked `JMSException`; if calling `TextMessage.getText()`, use try/catch and wrap into an appropriate unchecked exception.
- The endpoint is registered by the registrar and its lifecycle is managed by the container; **do not** spawn `new Thread(...)` or close the JMS Session inside the callback.

### 5.3. Configuring the Handler Method Factory for @JmsListener

~~~java
@Override
public void configureJmsListeners(
        JmsListenerEndpointRegistrar registrar) {
    registrar.setMessageHandlerMethodFactory(myHandlerMethodFactory);
}
~~~

`MessageHandlerMethodFactory` is the abstraction that builds invokers for **method-based endpoints**; Spring's default is `DefaultMessageHandlerMethodFactory`. It allows configuring validators/converters for annotated methods, such as `@Valid` payloads and `@Header` arguments.

These are **two different layers**:
- `MessageHandlerMethodFactory` controls how the **Java method** is invoked and arguments are resolved.
- `JmsListenerContainerFactory` controls the **JMS listener container**: connection factory, transactions, concurrency, consumer caching, destination resolver, error handling...

**`setMessageHandlerMethodFactory` does not automatically install a JMS `MessageConverter` onto every `SimpleJmsListenerEndpoint`.** Simple endpoints invoke a raw `jakarta.jms.MessageListener` directly; if you want a JSON DTO, read/parse the body explicitly or use a method-based endpoint with a proper converter.

## 6. Spring Configuration: One Default Factory and an Explicit Endpoint

A concise pattern suitable for Spring Framework 6.x:

~~~java
@Configuration
@EnableJms
public class ConsumerConfig implements JmsListenerConfigurer {

    private final JmsListenerContainerFactory<?> criticalFactory;

    public ConsumerConfig(
            JmsListenerContainerFactory<?> criticalFactory) {
        this.criticalFactory = criticalFactory;
    }

    @Override
    public void configureJmsListeners(
            JmsListenerEndpointRegistrar registrar) {

        registrar.setContainerFactory(criticalFactory);

        var endpoint = new SimpleJmsListenerEndpoint();
        endpoint.setId("auditPoller");
        endpoint.setDestination("audit.in");
        endpoint.setMessageListener(message -> {
            // Inspect body/headers and process per contract.
        });

        registrar.registerEndpoint(endpoint, criticalFactory);
    }
}
~~~

This is a **configuration class fragment**, requiring imports for `@Configuration`, `@EnableJms`, `JmsListenerConfigurer`, `JmsListenerEndpointRegistrar`, `JmsListenerContainerFactory`, and `SimpleJmsListenerEndpoint`. `criticalFactory` must be an existing bean; if multiple factories exist, use `@Qualifier` to avoid ambiguous injection. When the factory is passed explicitly in `registerEndpoint`, `setContainerFactory` only helps other endpoints **that omit a factory** in the same registration setup.

**Do not use this configuration verbatim to create production containers** without defining error/retry policies, transactions, schemas, and destination permissions.

## 7. Names, Identifiers, and Uniqueness

Three concepts are frequently confused:

| Name | Example | Role |
| --- | --- | --- |
| **Endpoint/container ID** | `"billingWorker"` | Identifier in `JmsListenerEndpointRegistry` for management |
| **Destination name** | `"billing.commands"` | Broker Queue or Topic consumed by the endpoint |
| **Container factory bean name** | `"businessListenerFactory"` | Spring bean name used to create the container |

Example:

~~~java
@JmsListener(
    id = "billingWorker",
    destination = "billing.commands",
    containerFactory = "businessListenerFactory")
public void handle(String command) {
    // ...
}
~~~

`id` is the lookup key:

~~~java
registry.getListenerContainer("billingWorker");
~~~

`destination` is where messages arrive; it is not used to look up containers unless you intentionally set the ID equal to the destination name. Assign distinct IDs for clearer diagnostics.

### Preventing ID Collisions

- When using multiple `JmsListenerConfigurer` beans, review the combined set of endpoint IDs in **the same registry**.
- Never reuse a `@JmsListener`'s ID when registering an additional programmatic endpoint.
- If registering endpoints from a config list, normalize and validate IDs; guarantee uniqueness before calling the registrar.
- If `id` is omitted on `@JmsListener`, Spring can generate an ID automatically; it is not a stable contract for long-term operations.
- Do not expect duplicate IDs to overwrite/replace an old container; the registry typically rejects duplicates or fails bootstrap.

### Do Multiple Endpoints on the Same Queue "Duplicate" Messages?

**No.** On a Queue, two listeners on the same destination normally act as **competing consumers**; each message is dispatched to one eligible consumer, not delivered to both. If two independent groups must each receive a copy, use a Topic with appropriate subscriptions or a queue-per-group architecture.

For Topics, consider `pubSubDomain`, durable/shared subscriptions, client IDs, subscription names, selectors, retention, and broker behavior; **the registrar does not automatically turn a Queue into a Topic**.

## 8. Choosing a Factory and Inheriting Spring Boot Configuration

### 8.1. Why Does the Factory Matter?

`DefaultJmsListenerContainerFactory` can configure:
- `ConnectionFactory` and `DestinationResolver`.
- `pubSubDomain` for Queue/Topic.
- `sessionTransacted` or an appropriate transaction manager.
- `concurrency` (`"1"`, `"3-10"`...).
- JMS selector/subscription behavior agreed upon by endpoint and container.
- `MessageConverter` and request–reply behavior for Spring-supported adapters.
- Error/recovery policy, caching, task executor, receiving messages during shutdown...

So **do not** treat `JmsListenerEndpointRegistrar` as the place to override every listener container setting. The registrar simply pairs endpoints with factories; **the factory decides how the container is built**.

### 8.2. Avoiding Losing Boot Defaults When Manually Instantiating a Factory

With Spring Boot 3.5.x, the pattern to create a custom factory while inheriting auto-configuration:

~~~java
@Bean("demoFactory")
DefaultJmsListenerContainerFactory demoFactory(
        ConnectionFactory connectionFactory,
        DefaultJmsListenerContainerFactoryConfigurer configurer) {

    var factory = new DefaultJmsListenerContainerFactory();

    configurer.configure(
        factory,
        ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));

    factory.setSessionTransacted(true);
    factory.setConcurrency("1");
    return factory;
}
~~~

Key imports: `jakarta.jms.ConnectionFactory`; `org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer`; `org.springframework.boot.jms.ConnectionFactoryUnwrapper`; `org.springframework.jms.config.DefaultJmsListenerContainerFactory`; `org.springframework.context.annotation.Bean`.

This is a **bean method**, not a standalone Java file. `ConnectionFactoryUnwrapper.unwrapCaching` (Boot 3.5) strips caching wrappers before handing the connection factory to the listener container, avoiding shared cache issues across polling/recovery lifecycles. `configurer.configure(...)` applies Boot-prepared settings; afterward, override transaction/concurrency as needed.

### 8.3. Default Factory and Overrides

When `@JmsListener` omits `containerFactory`, Spring typically looks up the bean named `jmsListenerContainerFactory`. The registrar can set a **different default factory** for endpoints that omit one.

For programmatic endpoints, the clearest pattern when multiple factories exist is:

~~~java
registrar.registerEndpoint(endpoint, demoFactory);
~~~

Do not guess that Spring will pick a matching factory by type when multiple similar beans exist in the context. In systems with multiple policies, name factories clearly and use `@Qualifier`/explicit registration.

## 9. Complete Java 17+ Lab: Annotated + Programmatic Endpoints

The lab creates **two different queues**, one listener per queue:
- `orders.annotation`: handler via `@JmsListener`.
- `payments.programmatic`: raw `MessageListener` registered by `JmsListenerConfigurer` through `JmsListenerEndpointRegistrar`.

An `OutcomeLog` waits for both callbacks to run and prints a summary in a deterministic order. The lab also uses `JmsListenerEndpointRegistry` to verify both containers are registered.

### 9.1. Initializing the Maven Project

Use https://start.spring.io/:
- Java 17+, Maven, Spring Boot **3.5.x**.
- Group `com.example`, artifact `jms-registrar-lab`.
- Java package `com.example.jmsregistrarlab`.
- Dependency **Spring for Apache ActiveMQ Artemis** (`spring-boot-starter-artemis`).

Add to `<dependencies>` in `pom.xml` (with Spring Boot parent/BOM):

~~~xml
<dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>artemis-jakarta-server</artifactId>
</dependency>
~~~

This dependency adds the embedded broker for the lab, not the entire `pom.xml`. Let the Boot BOM manage the Artemis version. The embedded broker is strictly for learning, not for proving persistent backlogs, high availability, or production failover.

### 9.2. application.properties

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=jms-registrar-lab
spring.artemis.mode=embedded
spring.artemis.embedded.queues=orders.annotation,payments.programmatic
spring.artemis.embedded.persistent=false
spring.jms.pub-sub-domain=false
spring.main.web-application-type=none
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

Because the app has no web server, both JMS listeners keep background tasks alive after the runner finishes. Stop the app with Ctrl+C for graceful shutdown rather than expecting the process to exit when the runner returns.

### 9.3. File 1 — Entry Point, Factory, and Sender

Save `src/main/java/com/example/jmsregistrarlab/JmsRegistrarLabApplication.java`:

~~~java
package com.example.jmsregistrarlab;

import java.util.concurrent.TimeUnit;

import jakarta.jms.ConnectionFactory;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer;
import org.springframework.boot.jms.ConnectionFactoryUnwrapper;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
@EnableJms
public class JmsRegistrarLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsRegistrarLabApplication.class, args);
    }

    @Bean("demoFactory")
    DefaultJmsListenerContainerFactory demoFactory(
            ConnectionFactory connectionFactory,
            DefaultJmsListenerContainerFactoryConfigurer configurer) {

        var factory = new DefaultJmsListenerContainerFactory();
        configurer.configure(factory,
                ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));
        factory.setSessionTransacted(true);
        factory.setConcurrency("1");
        return factory;
    }

    @Bean
    ApplicationRunner publishDemo(
            JmsTemplate template,
            JmsListenerEndpointRegistry registry,
            OutcomeLog results) {

        return args -> {
            if (registry.getListenerContainer("annotatedOrders") == null) {
                throw new IllegalStateException(
                        "Missing annotatedOrders listener container");
            }
            if (registry.getListenerContainer("programmaticPayments") == null) {
                throw new IllegalStateException(
                        "Missing programmaticPayments listener container");
            }

            template.convertAndSend("orders.annotation", "order-101");
            template.convertAndSend("payments.programmatic", "pay-202");

            if (!results.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Listeners did not finish inside test budget");
            }

            System.out.println("HANDLED=" + results.snapshot());
        };
    }
}
~~~

**Why include `@EnableJms`?** It illustrates Spring's listener annotation infrastructure. Boot can auto-enable it in standard setups; declaring it once on the app class keeps the code explicit.

**Why `setSessionTransacted(true)`?** When a handler throws an unchecked exception, the container can roll back the JMS transaction so the broker redelivers per policy. Setting JMS transactions alone does not make DB transactions or external side effects atomic.

### 9.4. File 2 — Recording Results from Both Listeners

File `src/main/java/com/example/jmsregistrarlab/OutcomeLog.java`:

~~~java
package com.example.jmsregistrarlab;

import java.util.concurrent.ConcurrentSkipListSet;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.stereotype.Component;

@Component
public class OutcomeLog {

    private final CountDownLatch latch = new CountDownLatch(2);
    private final ConcurrentSkipListSet<String> values =
            new ConcurrentSkipListSet<>();

    public void record(String entry) {
        values.add(entry);
        latch.countDown();
    }

    public boolean await(long timeout, TimeUnit unit)
            throws InterruptedException {
        return latch.await(timeout, unit);
    }

    public String snapshot() {
        return String.join("|", values);
    }
}
~~~

`ConcurrentSkipListSet` produces repeatable ordering for stdout regardless of whether the annotated or programmatic listener thread runs first. `CountDownLatch` lets the runner wait for two callbacks instead of guessing thread timing. The lab has two distinct messages; in production, **never** use a fixed-count latch to manage an unbounded queue.

### 9.5. File 3 — Listener Using @JmsListener

File `src/main/java/com/example/jmsregistrarlab/AnnotatedOrders.java`:

~~~java
package com.example.jmsregistrarlab;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class AnnotatedOrders {

    private final OutcomeLog results;

    public AnnotatedOrders(OutcomeLog results) {
        this.results = results;
    }

    @JmsListener(
            id = "annotatedOrders",
            destination = "orders.annotation",
            containerFactory = "demoFactory")
    public void onOrder(String orderId) {
        results.record("ANNOTATION:" + orderId);
    }
}
~~~

Spring converts the `TextMessage` body produced by `convertAndSend(String)` into the `String` parameter of the annotated method via the default converter, and the container manages reception. Never manually fetch/close JMS connections inside this method.

### 9.6. File 4 — Configurer and Registrar

File `src/main/java/com/example/jmsregistrarlab/ProgrammaticListeners.java`:

~~~java
package com.example.jmsregistrarlab;

import jakarta.jms.JMSException;
import jakarta.jms.TextMessage;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.JmsListenerConfigurer;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.config.JmsListenerEndpointRegistrar;
import org.springframework.jms.config.SimpleJmsListenerEndpoint;

@Configuration(proxyBeanMethods = false)
public class ProgrammaticListeners implements JmsListenerConfigurer {

    private final OutcomeLog results;
    private final DefaultJmsListenerContainerFactory demoFactory;

    public ProgrammaticListeners(
            OutcomeLog results,
            @Qualifier("demoFactory")
            DefaultJmsListenerContainerFactory demoFactory) {

        this.results = results;
        this.demoFactory = demoFactory;
    }

    @Override
    public void configureJmsListeners(
            JmsListenerEndpointRegistrar registrar) {

        var endpoint = new SimpleJmsListenerEndpoint();
        endpoint.setId("programmaticPayments");
        endpoint.setDestination("payments.programmatic");

        endpoint.setMessageListener(message -> {
            if (!(message instanceof TextMessage textMessage)) {
                throw new IllegalArgumentException(
                        "Expected TextMessage");
            }

            try {
                results.record("PROGRAM:" + textMessage.getText());
            } catch (JMSException ex) {
                throw new IllegalStateException(
                        "Cannot read JMS TextMessage", ex);
            }
        });

        // Use explicit factory, do not rely on default bean.
        registrar.registerEndpoint(endpoint, demoFactory);
    }
}
~~~

**API check points:**
- `ProgrammaticListeners` implements `org.springframework.jms.annotation.JmsListenerConfigurer` from the right package.
- The callback receives `org.springframework.jms.config.JmsListenerEndpointRegistrar`, not a `JmsListenerEndpointRegistry`.
- `SimpleJmsListenerEndpoint` accepts **`jakarta.jms.MessageListener`**, so the lambda sees a raw JMS `Message`. It **does not automatically bind `String` parameters like `@JmsListener`**.
- `TextMessage.getText()` throws checked `JMSException`; the example catches and converts it to an unchecked exception to satisfy the `MessageListener` interface.
- `registrar.registerEndpoint(endpoint, demoFactory)` specifies the exact factory used for the endpoint.
- `"programmaticPayments"` is the ID in the registry; `"payments.programmatic"` is the queue name.
- Every Java file has one public top-level class matching its filename, with complete package and imports.

### 9.7. Running and Results

Linux/macOS:

~~~bash
./mvnw spring-boot:run
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

When embedded Artemis starts properly, both queues begin empty, no other consumer competes, and both callbacks complete within 10 seconds, the application prints:

~~~text
HANDLED=ANNOTATION:order-101|PROGRAM:pay-202
~~~

Spring/Artemis startup logs may appear before or after this line; do not claim Spring's entire stdout is a single line. `ConcurrentSkipListSet` sorts the two entries by name, independent of which listener executes first.

**Correctness warning:** `OutcomeLog.record` is called **inside** the callbacks, potentially before the final JMS session commit. The `HANDLED` line proves the callbacks ran, **not** that the broker committed messages, DB writes persisted, or side effects happened once. Testing transactions/retries requires inspecting broker/DB state in dedicated integration tests.

### 9.8. Self-Guided Experiments

1. Temporarily remove `@EnableJms` in the lab; if Boot auto-enables JMS listener infrastructure, the code may still run. Do not conclude the annotation is "useless" in plain Spring Framework projects without Boot.
2. Change `payments.programmatic` to a nonexistent queue and disable auto-create on a staging broker; observe startup/recovery errors and fix the destination mapping.
3. Change `endpoint.setId("programmaticPayments")` to `"annotatedOrders"` to observe the duplicate ID error in tests; restore it before shipping to production.
4. Make the programmatic listener intentionally throw an exception before `record`; observe broker redelivery/rollback with `sessionTransacted=true` and retry policies.
5. Send a `BytesMessage` to `payments.programmatic`; the handler must reject it since it only accepts `TextMessage`.
6. Add a JMS selector to the endpoint (`endpoint.setSelector("kind = 'payment'")`) and set the matching `kind` JMS property on the producer; messages lacking the property will not match.
7. Switch the factory to a non-transacted bean; inspect the difference in redelivery behavior when the callback fails, without relying solely on endpoint names.
8. Use the registry to print `getListenerContainerIds()` and see how IDs differ from destinations; never rename a live container without updating monitoring.

## 10. Registrar vs. Registry: Differences to Remember in Operations

### 10.1. Initialization Phase with the Registrar

~~~java
@Override
public void configureJmsListeners(
        JmsListenerEndpointRegistrar registrar) {
    registrar.registerEndpoint(endpoint, factory);
}
~~~

This is how you declare an endpoint to the infrastructure **before normal execution**. The registrar accepts:
- Endpoint models.
- Factories used to create containers.
- The default factory.
- The handler method factory for annotated method invocation.

It is not a live status list of active/idle running JMS consumers.

### 10.2. Runtime Phase with the Registry

~~~java
// Code snippet in a Spring service with injected registry.
MessageListenerContainer running =
        registry.getListenerContainer("programmaticPayments");

if (running != null && running.isRunning()) {
    running.stop();
}

// To resume once authorized by operations:
if (running != null && !running.isRunning()) {
    running.start();
}
~~~

Calling `stop()` on a container requests stopping reception per lifecycle; it **does not remove it from the registry**. `start()` can resume it if the container remains valid, though some providers/caches/subscriptions require testing restarts and timing. Never call stop/start per message from inside the callback itself, as that can cause deadlocks or races; let an administrative thread or coordinator handle it.

`JmsListenerEndpointRegistry` participates in **`SmartLifecycle`**, managing start/stop/destroy when the Spring `ApplicationContext` closes. These containers are normally not standalone beans to autowire individually; looking them up by ID through the registry is the standard approach.

### 10.3. Runtime Registration via Registry, Not Startup Registrar

When you truly must add an endpoint after the context is already running:

~~~java
// Java snippet inside a controlled admin service.
// registry: JmsListenerEndpointRegistry bean
// factory : configured JmsListenerContainerFactory<?> bean

var endpoint = new SimpleJmsListenerEndpoint();
endpoint.setId("newQueueConsumer");
endpoint.setDestination("new.queue");
endpoint.setMessageListener(message -> {
    // Process message per contract.
});

registry.registerListenerContainer(endpoint, factory, true);
~~~

`true` indicates **startImmediately** if the container is allowed to run. This is a registry API, distinct from `registrar.registerEndpoint`. Never invoke it from an uncontrolled loop, never construct endpoint IDs/destinations directly from untrusted HTTP input, and enforce permissions, uniqueness, and lifecycle cleanup.

**Limitation:** runtime registration does not turn those endpoints into individually Spring-managed business beans; the callback still needs pre-wired dependencies, transactions/metrics, and an owner managing container IDs. Do not assume `stop()` "unregisters" an endpoint: stopping does not remove the ID from the registry.

## 11. Configuring MessageHandlerMethodFactory for Method-Based Endpoints

Spring supports annotated methods with parameters:

~~~java
@JmsListener(destination = "payments.in")
public void accept(
        PaymentCommand command,
        @Header("tenantId") String tenantId) {
    // Validate then process.
}
~~~

This is a snippet; imports include Spring's `@JmsListener` and `@Header`, along with a suitable converter and DTO. `MessageHandlerMethodFactory` is responsible for building the method invoker with resolved arguments, validation, and payload conversion support.

Validator configuration pattern:

~~~java
@Bean
DefaultMessageHandlerMethodFactory handlerMethodFactory(
        Validator validator) {

    var factory = new DefaultMessageHandlerMethodFactory();
    factory.setValidator(validator);
    return factory;
}
~~~

Then inside `JmsListenerConfigurer`:

~~~java
@Override
public void configureJmsListeners(
        JmsListenerEndpointRegistrar registrar) {
    registrar.setMessageHandlerMethodFactory(handlerMethodFactory);
}
~~~

This is a **configuration snippet**: `DefaultMessageHandlerMethodFactory` is in `org.springframework.messaging.handler.annotation.support`; `Validator` is `org.springframework.validation.Validator`. Ensure the bean exists and is injected, and avoid declaring conflicting method factories in multiple places unexpectedly.

Distinction:
- **JMS `MessageConverter`** converts raw JMS messages ⇄ Java/Spring payloads per listener adapter/template settings.
- **Handler method factory** configures invokers, argument resolvers, and validation in the method pipeline.
- **`SimpleJmsListenerEndpoint`** uses a raw `jakarta.jms.MessageListener` callback and therefore has no `@Valid` method parameter binding automatically.

If JSON messages carry DTOs, ensure converters, Jackson allowlists/type mappings, validators, and exception policies match on both ends. An annotated method parameter of type `PaymentCommand` **does not by itself make messages of unknown schemas safe**.

## 12. Multiple Configurers, Custom Registries, and Configuration Order

### 12.1. Multiple JmsListenerConfigurer Beans Are Allowed

When different Spring modules each provide a configurer, each can add endpoints or modify the default factory/method factory. **Independent endpoint registrations** can coexist cleanly, whereas multiple configurers setting **a single default factory** make configuration unpredictable without strict ordering.

**Recommendation:** centralize default rules in one clearly owned configurer; let remaining modules register endpoints with explicit factories. If multiple configurers are unavoidable, define Spring bean ordering and write integration tests verifying the active policy.

### 12.2. Should You Create a Custom JmsListenerEndpointRegistry?

Usually **no**. Spring's annotation-driven infrastructure provides a default registry managing all annotated and programmatically registered endpoints. `registrar.setEndpointRegistry(...)` exists for advanced integrations, yet replacing the registry without understanding infrastructure ownership and initialization can break container lookup/stopping.

Before creating a custom registry, answer:
- Why does the default registry not meet requirements?
- Does the registry bean participate in ApplicationContext lifecycle and shut down cleanly?
- Which registry do monitoring/actuator/admin endpoints inspect?
- Are IDs unique across annotated and programmatic endpoints?
- Are you avoiding creating two registries managing the same destination while ops only monitors one?

### 12.3. Avoid Registering Both Annotated and Programmatic Endpoints for the Same Work

If a method already has `@JmsListener` and you also register a `SimpleJmsListenerEndpoint` pointing to the same queue/callback, Spring runs **two consumer containers** rather than "upgrading" the existing endpoint. On a Queue, they compete for messages. On a Topic, they may receive independent copies depending on subscriptions. Register only intended endpoints and assert the final container count.

## 13. Selectors, Topics, and Durable Subscriptions in Programmatic Endpoints

`SimpleJmsListenerEndpoint` supports endpoint properties such as `id`, `destination`, `selector`, and `subscription` via the Spring API:

~~~java
var endpoint = new SimpleJmsListenerEndpoint();
endpoint.setId("apacInvoices");
endpoint.setDestination("invoices.in");
endpoint.setSelector("region = 'APAC' AND priorityGroup >= 2");
endpoint.setMessageListener(message -> {
    // Raw MessageListener
});
registrar.registerEndpoint(endpoint, factory);
~~~

This is a startup configuration snippet; **selectors filter JMS properties**, not JSON bodies. Producers must set `region` and `priorityGroup` using typed JMS setters. It uses the SQL-92 subset with three-valued logic `TRUE/FALSE/UNKNOWN`; missing properties do not match automatically.

If the destination is a Topic:
- The factory/container must configure `pubSubDomain=true`.
- Durable subscriptions require proper identity/clientID/subscription name per JMS/provider and broker policy.
- `setSubscription(...)` sets the subscription name and **does not** automatically enable durability on every factory; configure the matching subscription mode.
- Scaling multiple replicas with shared/unshared durable subscriptions requires checking provider support, IDs, and retention.
- Selectors on durable subscriptions affect backlogs and selector updates; test before rolling deployments.

Do not assume Topic semantics merely because you use an endpoint registrar; the endpoint API **does not decide** queue-vs-topic. That belongs to the factory/connection/destination.

## 14. Transactions, Exceptions, and Rollback for Both Listener Styles

### 14.1. Do @JmsListener and Raw MessageListener Share the Same Container Model?

They can be created by **the same `DefaultJmsListenerContainerFactory`** and share identical transaction/connection/concurrency policies. The main difference is invocation adaptation:
- Annotated methods receive converted payloads, `@Header` values, and validation.
- Simple endpoints receive **raw JMS `Message`** and read bodies/headers/properties manually.

With the same factory using `setSessionTransacted(true)`:
- If the listener succeeds, the container commits the JMS session.
- If the listener throws an exception, the container rolls back so the message can be redelivered per broker policy.
- Session transactions do not automatically include database writes or HTTP side effects; use idempotency/outbox where needed.

### 14.2. Handling Exceptions Properly in MessageListener

Do not write:

~~~java
endpoint.setMessageListener(message -> {
    try {
        processPayment(message);
    } catch (Exception ex) {
        logError(ex);
        // Returning normally: container may treat it as success!
    }
});
~~~

This is an **illustrative anti-pattern**, assuming external helper methods. If an error leaves business work incomplete and requires rollback, throw an unchecked exception so the container handles it per transaction policy rather than logging and ignoring it.

Controlled approach:

~~~java
endpoint.setMessageListener(message -> {
    try {
        performIdempotentOperation(message);
    } catch (JMSException ex) {
        throw new IllegalStateException(
                "Could not read JMS message", ex);
    }
});
~~~

This is a snippet: `performIdempotentOperation` may throw `JMSException`; unchecked business errors continue to propagate. For poison messages with permanent errors, never retry endlessly: use backoff, max-attempt bounds, and DLQs/quarantine.

### 14.3. Controlled Application Shutdown

`JmsListenerEndpointRegistry` participates in the Spring lifecycle. When SIGTERM/`ApplicationContext.close()` occurs:
- Containers stop accepting new messages during the lifecycle shutdown phase.
- In-flight handlers get a window to finish within the configured shutdown timeout.
- Sessions/consumers/connections are cleaned up by containers and connection factories after stopping.
- If the process is killed forcibly or exceeds the timeout budget, broker transactions/redeliveries and idempotency act as the recovery layer.

Never close the container's connection/session from inside `onMessage`; never call `registrar.registerEndpoint` to "restart" on broker reconnect—containers have their own recovery mechanisms.

## 15. Common Errors and How to Diagnose Them

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| `@JmsListener` does not work | JMS infrastructure not enabled, bean not scanned, missing factory/connection | Check `@EnableJms`/Boot config, component scan, starters, bean names |
| `configureJmsListeners` callback does not run | Configurer is not a Spring bean, wrong interface package, annotation infra disabled | Ensure `@Configuration` and exact `org.springframework.jms.annotation.JmsListenerConfigurer` |
| Registered endpoint yet container missing | Wrong factory, startup failure, different registry, missing ID/destination | Read startup logs and `registry.getListenerContainerIds()` |
| `NoSuchBeanDefinitionException` for factory | `containerFactory` or `setContainerFactoryBeanName` points to wrong bean name | Compare actual bean names |
| Duplicate ID across endpoints | Two `@JmsListener`/programmatic endpoints share an ID | Set unique stable IDs, test bootstrap |
| Listener receives raw `TextMessage` instead of `String` | Using `SimpleJmsListenerEndpoint` | Raw MessageListener must extract JMS body or switch to method-based listener |
| `@Valid` does not run on simple callback | Handler method factory does not apply to raw JMS MessageListener | Validate explicitly or use the annotated method pipeline |
| Calling `registrar.registerEndpoint` after context init | Registrar is a bootstrap mechanism | At runtime use `registry.registerListenerContainer(...)` with explicit factory |
| Consumer receives nothing due to selector | Selector reads only JMS properties; property missing/wrong type | Inspect selector and producer properties |
| Two unintended consumers on the same queue | Both annotation and programmatic registration target the same destination | Inspect IDs and topology; remove duplicate registration |
| Stopping one endpoint does not drain queue backlog | Stop affects only that container; broker retains messages per policy | Monitor queue metrics and competing consumers |
| Handler throws errors without redelivery | ACK mode, transaction boundary, or swallowed exception | Configure transacted sessions/rollback and broker DLQ |
| Startup hangs when broker is down | Recovery, connection timeout, provider config | Check broker URL/`recoveryInterval`, timeouts, and fail-fast policy |
| Redeploy receives duplicate messages | Side effects committed before JMS commit | Idempotent consumer and inbox/unique business keys |
| Listener still runs after expected destruction | Multiple registries/containers, custom threads, or another broker connection | Check registry IDs, active connections, and shutdown logs |
| Factory uses wrong queue/topic domain | `pubSubDomain` does not match destination | Inspect factory, connection resolver, and broker address |

## 16. Pre-Production Review Checklist

- **Registration owner:** Is each endpoint created by `@JmsListener` or `JmsListenerConfigurer`? Are any created twice?
- **Endpoint ID:** Is it unique, stable, and meaningful for monitoring/admin?
- **Factory:** Does the endpoint use the right `DefaultJmsListenerContainerFactory` and inherit Boot defaults when needed?
- **Fallback:** Do you know the default factory for endpoints omitting `containerFactory`/explicit factory?
- **Registry:** Does the app query the right registry instead of looking up containers as direct beans?
- **Dynamic:** If registered at runtime, are endpoint counts bounded and stop/start/cleanup policies defined?
- **Concurrency:** Do session/consumer counts suit queue/topic and ordering requirements?
- **Conversion:** Do annotated methods and Simple callbacks use the right body/DTO contracts?
- **Validation:** Are `MessageHandlerMethodFactory` and validators applied in the right places?
- **Selector:** Have property names/types, SQL-92 syntax, and NULL handling been tested?
- **Reliability:** Do `sessionTransacted`, ACK, retries, redelivery, DLQ, and idempotency meet SLAs?
- **Topology:** Are queues competing-consumer or do topics have proper durable subscriptions?
- **Security:** Do broker authentication/TLS/ACLs and tenant authorization avoid relying solely on selectors?
- **Shutdown:** Do registries/connection pools stop in order without closing resources mid-handler?
- **Tests:** Have startup IDs, the two-queue lab, runtime stop/start, listener exceptions, and redeploy backlogs been tested?
- **Versioning:** Can new listeners still read older messages sitting in queues/DLQs?

## 17. Reinforcement Exercises

1. Distinguish `JmsListenerConfigurer`, `JmsListenerEndpointRegistrar`, and `JmsListenerEndpointRegistry` in your own diagram.
2. Why does calling `new SimpleJmsListenerEndpoint()` not immediately add a consumer on the broker?
3. Register `auditEvents` on queue `audit.in` with factory `auditFactory`; which is the endpoint ID, destination, and bean name?
4. An endpoint uses `@JmsListener(containerFactory="criticalFactory")`; the registrar sets default `commonFactory`. Which factory does the endpoint use?
5. Write a configurer registering two `SimpleJmsListenerEndpoint` instances on two different queues; how do you guarantee IDs do not collide?
6. Given a `MessageListener` receiving `TextMessage`, why can't the lambda declare throwing `JMSException`? Write appropriate catch/rethrow handling.
7. An annotated method accepts `@Header("tenantId")` and `@Valid` DTO, while a simple endpoint receives raw `Message`. Why doesn't the method factory apply automatically to the simple endpoint?
8. When the app is already running and must add a consumer, why should you use `registry.registerListenerContainer` instead of the startup registrar?
9. Two business groups register on the same queue with different endpoint IDs. Do both automatically receive a copy of every message? When is a Topic needed?
10. In the lab, remove `sessionTransacted=true` and make the programmatic listener throw an exception. Plan how to test redelivery on the broker rather than guessing from logs alone.
11. Add selector `kind = 'payment'` to the programmatic endpoint; which property and type must the producer set?
12. Attempt to create a runtime endpoint with an already existing ID. Describe expected registry uniqueness behavior and how to test safely.
13. Describe the sequence when SIGTERM arrives while a listener is processing, and the limits of graceful shutdown compared to a process crash.
14. If an app uses 3 different `JmsListenerConfigurer` beans, what conventions prevent overriding the default factory or colliding IDs?
15. Explain why `registrar.setMessageHandlerMethodFactory` does not replace configuring a JMS `MessageConverter` on the listener container.

## 18. Official References

- Spring Framework 6.2 — **Annotation-driven Listener Endpoints**, including **Programmatic Endpoint Registration**: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html
- Spring Framework 6.2 — **JmsListenerConfigurer** Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/annotation/JmsListenerConfigurer.html
- Spring Framework 6.2 — **JmsListenerEndpointRegistrar** Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistrar.html
- Spring Framework 6.2 — **SimpleJmsListenerEndpoint** Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/SimpleJmsListenerEndpoint.html
- Spring Framework 6.2 — **JmsListenerEndpointRegistry** Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistry.html
- Spring Framework 6.2 — **Receiving a Message**: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html
- Spring Boot 3.5 — **JMS configuration and listener container factory configurer**: https://docs.spring.io/spring-boot/3.5/how-to/messaging.html
- Spring Boot 3.5 — **Messaging with JMS** integration guide: https://spring.io/guides/gs/messaging-jms/
