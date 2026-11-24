# Distinguishing Business Bean Lifecycle from Listener Container Lifecycle in Spring JMS

## 1. The Problem to Understand

A method annotated with `@JmsListener` does not mean the Java object containing that method is itself a JMS consumer or is responsible for opening/closing connections. In Spring JMS there are **two related yet distinct lifecycles**:

- **Spring business bean lifecycle**: instantiate object, inject dependencies, run `@PostConstruct`, serve business calls, and finally run `@PreDestroy` when the ApplicationContext destroys the bean.
- **JMS listener container lifecycle**: register endpoint, create/manage Connection/Session/MessageConsumer, start receiving messages, coordinate listener threads, handle transactions/recovery, stop, and release resources.

**Crucial scenario:** an `OrderBusinessService` may be completely initialized by Spring while the JMS listener container is still **stopped**. Calling `container.start()` only tells Spring to start receiving messages; the bean is not reconstructed. Calling `container.stop()` leaves the bean alive and callable by other callers; `@PreDestroy` has not run yet.

After this lesson, you will know how to:

1. Explain the roles of `@Component`, `@Service`, and `@PostConstruct`/`@PreDestroy` versus `@JmsListener`/`MessageListenerContainer`.
2. Distinguish listener endpoint registration, container startup, broker connectivity, handler execution, and business commit.
3. Use `@EnableJms`, `JmsListenerContainerFactory`, `JmsListenerEndpointRegistry`, and `SmartLifecycle`.
4. Configure `autoStartup`, `phase`, and start/stop/pause/resume individual listeners by ID.
5. Design readiness, graceful shutdown, transactions, recovery, and thread safety.
6. Run a **Java 17+, Spring Boot 3.5.x, and embedded ActiveMQ Artemis** example proving the two lifecycles are different.

## 2. Two Objects, Two Responsibilities

| Perspective | Spring business bean | Spring JMS listener container |
| --- | --- | --- |
| Represents | Service/handler responsible for business logic. | Infrastructure receiving messages and invoking the handler. |
| Created by | `BeanFactory`/`ApplicationContext` via component scan or `@Bean`. | Spring JMS annotation infrastructure via `JmsListenerContainerFactory` or manually declared by the application. |
| Initialization | Constructor, dependency injection, bean post-processing, `@PostConstruct`. | Endpoint/factory config, JMS resources, listening infrastructure setup. |
| Start | No mandatory start for a plain POJO service. | `start()`, auto-startup, `SmartLifecycle`. |
| When broker disconnects | The bean can still exist. | The container may recover/reconnect or log errors. |
| Stop | Not automatically destroyed when the listener stops. | `stop()` stops/throttles receiving per its implementation. |
| Restart | Constructor/`@PostConstruct` do not necessarily re-run. | `start()` again, potentially recreating JMS consumer resources. |
| Shutdown | `@PreDestroy`/destroy callbacks when context closes. | Stops lifecycle and releases Connection/Session/Consumer. |
| Concurrency | Singleton methods may be invoked by multiple threads. | Concurrency, task executor, session/consumer threads. |

Core takeaway: **The bean answers "how to process a message?"; the container answers "who receives messages, when, and with which JMS resources?"**. A business method does not open a JMS connection merely by having an annotation.

~~~mermaid
flowchart TD
  A["ApplicationContext"] --> B["OrderBusinessService bean"]
  A --> C["OrderListener bean @JmsListener"]
  A --> D["JmsListenerEndpointRegistry"]
  D --> E["MessageListenerContainer"]
  E --> F["Connection / Session / MessageConsumer"]
  F <--> G[("Broker Queue")]
  E --> C
  C --> B
~~~

`jakarta.jms.MessageListener` is a JMS **callback contract**, different from `org.springframework.jms.listener.MessageListenerContainer` which is **lifecycle infrastructure**. Spring can create a listener adapter to invoke the annotated method on a bean.

## 3. How Does Spring Create Endpoints?

With `@JmsListener`:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @JmsListener(id = "ordersListener", destination = "orders.commands")
    public void receive(String orderId) {
        orderService.handle(orderId);
    }
}
~~~

The code above is a **fragment containing a Spring-managed class**; `OrderService` is an application dependency you must define. When JMS infrastructure is enabled:

1. Spring creates the `OrderListener` bean and injects `OrderService`.
2. `JmsListenerAnnotationBeanPostProcessor` detects the annotated method.
3. The method becomes a listener endpoint; `JmsListenerContainerFactory` creates the corresponding container/adapter.
4. `JmsListenerEndpointRegistry` manages the annotation endpoint's container.
5. If `autoStartup=true` is configured, Spring's lifecycle processor tells the container to start during context refresh.
6. The container receives messages and dispatches to the bean's method; the business bean performs processing.

**An easy-to-miss detail:** a container created by the annotation infrastructure **is not a standalone Spring bean that can be autowired directly**. To retrieve it, use `registry.getListenerContainer("ordersListener")`. If the application **manually declares** `DefaultMessageListenerContainer` via `@Bean`, that is a different case: that container truly is a bean.

`@JmsListener(id=...)` sets the **container/endpoint ID**, not the queue name, bean name, or class name. A stable ID helps control and monitor each listener. If `id` is omitted, Spring generates one; for runtime management, declare an explicit ID.

### 3.1. One method can have multiple endpoints

`@JmsListener` is repeatable; a single method can register multiple endpoints. One bean does not imply only one container. Conversely, one container can have multiple JMS consumers depending on concurrency. When monitoring, do not confuse:

- Number of Spring business beans.
- Number of endpoint containers.
- Number of JMS consumers/sessions.
- Number of message handler invocations.

These quantities are conceptually independent.

### 3.2. What does @EnableJms do?

In plain Spring Framework, `@EnableJms` enables infrastructure to discover `@JmsListener` and register endpoints. It requires a `ConnectionFactory` and a `JmsListenerContainerFactory`, looking by default for a bean named `jmsListenerContainerFactory` if the endpoint specifies no factory. Spring Boot can auto-configure these components when JMS dependencies are present.

**`@EnableJms` is not equivalent to `container.start()`**, nor does it prove the broker is reachable. If an annotated method is not scanned or its profile/condition is inactive, the endpoint **does not exist**, which differs from an endpoint that **exists but is stopped**.

## 4. Timeline Between the Two Lifecycles

| Phase | Business bean | Listener container |
| --- | --- | --- |
| Context creates bean definitions | No instance yet. | No container yet for annotated method. |
| Instantiate/inject | Constructor/injection. | Listener processor detects endpoint metadata. |
| Bean initialization | `@PostConstruct` and init callbacks. | Factory/registry prepares endpoint and container. |
| Context lifecycle start | Bean remains ready for method calls. | Auto-startup containers are asked to `start()`. |
| Application running | Methods execute business logic, possibly using DB/APIs. | JMS consumers receive, convert/dispatch, manage transactions. |
| Calling `stop()` | Bean is **not automatically destroyed**. | Container stops receiving per its mechanism. |
| Calling `start()` again | `@PostConstruct` **does not re-run** due to container stop/start. | Container resumes listening. |
| ApplicationContext close | `@PreDestroy`/destroy callbacks (normal shutdown). | Containers stop per phases and destroy JMS resources. |

~~~mermaid
flowchart LR
  B0["Bean not created yet"] --> B1["Bean init @PostConstruct"]
  B1 --> B2["Bean active"]
  B2 --> B3["Bean destroy @PreDestroy"]
  C0["Endpoint/container registered"] --> C1["Container stopped"]
  C1 --> C2["Container running"]
  C2 --> C1
  C1 --> C3["Container destroyed"]
  C2 --> C3
~~~

The two lines are **two separate state machines**. The container can cycle between stopped/running multiple times within a single singleton bean's lifetime. With custom bean scopes or context refreshes, behavior may differ, yet **simply restarting a container does not recreate singletons**.

### 4.1. @PostConstruct does not mean "listener started"

`@PostConstruct` belongs to the **bean lifecycle**; it runs during initialization. It is suitable for validating config, initializing internal state, or setting up resources **owned by the bean itself**. Do not create a `receive()` loop, block indefinitely waiting for a broker, or call `registry.start()` before annotation endpoints are registered.

Conversely, container `start()` may happen **after** the bean is initialized, using broker resources. A structurally ready bean is **not sufficient** proof that DB migrations or upstream APIs are ready for processing.

### 4.2. ApplicationRunner is not a default startup gate

In Spring Boot, `ApplicationRunner`/`CommandLineRunner` run after context refresh. Spring has an opportunity to start auto-startup `SmartLifecycle` components **before runners are invoked**; `ApplicationReadyEvent` is published after runners. Thus an auto-startup listener can already receive messages before the app reports ready.

If you must wait for custom system initialization, **disable autoStartup and explicitly start** from a coordinator/runner once readiness criteria are satisfied. Do not merely add an `ApplicationReadyEvent` listener and assume no JMS messages were delivered before that event.

## 5. SmartLifecycle and Runtime States

Spring JMS `MessageListenerContainer` implements `SmartLifecycle` with APIs:

| API | Meaning |
| --- | --- |
| `isAutoStartup()` | Should the container start automatically with Spring's lifecycle? |
| `getPhase()` | Start/stop ordering relative to other lifecycle components. |
| `start()` | Requests the container to begin operating. |
| `stop()` | Requests stopping the container's operation. |
| `stop(Runnable callback)` | Stops and invokes the callback after stopping completes per implementation contract. |
| `isRunning()` | Lifecycle running state; **does not mean the broker is healthy**. |

**Lifecycle phase:** starts from **lowest to highest phase**; stops from **highest to lowest phase**. With typical JMS container defaults, starting late and stopping early helps ensure dependencies are ready before receiving messages and have a chance to stay alive while handlers finish during shutdown. However, actual phases must be verified in applications with many custom factories/components.

For example, a cache configuration bean may also implement `SmartLifecycle` with a lower phase than the listener. In that case, the cache starts first, and the listener stops before the cache. **Phase does not replace dependency injection or readiness checks** for external systems.

### 5.1. isRunning differs from isConnected

`container.isRunning()==true` only indicates the container was asked to run / is in the running lifecycle state. It **does not by itself guarantee**:

- The broker is currently connected successfully.
- A JMS consumer is active on the broker.
- The listener has no business or converter errors.
- The queue has messages being processed.
- The database transaction committed.
- Events are not rolling back/redelivering.

`DefaultMessageListenerContainer` performs recovery/backoff when the broker is temporarily unavailable; during that window the container may report running while not yet receiving messages. For health visibility, combine broker metrics, recovery logs, consumer counts, and last successful processing timestamp.

## 6. Runnable Example: Java 17 + Spring Boot + Embedded Artemis

The following demo proves via output that the business bean **is already initialized while the listener is not yet started**; after calling `start()`, the handler processes; after `stop()`, the bean **still exists**; only when closing the ApplicationContext does `@PreDestroy` run.

Requirements: **JDK 17+**, Maven, Spring Boot **3.5.7**, and embedded Artemis. The demo uses `CountDownLatch`/stop callback rather than arbitrary sleeps, and sends only one message so output is easy to verify.

### 6.1. Structure

~~~text
jms-lifecycle-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/jmslifecycle/
    │   ├── JmsLifecycleApplication.java
    │   ├── OrderBusinessService.java
    │   └── OrderMessageListener.java
    └── resources/
        └── application.properties
~~~

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>jms-lifecycle-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

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

Spring Boot parent manages dependency versions. `spring-boot-starter-artemis` provides JMS integration/client; `artemis-jakarta-server` enables creating an embedded broker.

### 6.3. application.properties

~~~properties
spring.artemis.mode=embedded
spring.artemis.embedded.queues=demo.lifecycle
spring.artemis.embedded.persistent=false
spring.jms.pub-sub-domain=false
spring.jms.listener.auto-startup=false
spring.lifecycle.timeout-per-shutdown-phase=20s
spring.main.web-application-type=none
spring.main.banner-mode=off
~~~

**Key setting:** `spring.jms.listener.auto-startup=false` does not delete the bean or unregister the endpoint; it only disables auto-starting the Boot-configured listener container. Queue `demo.lifecycle` still exists in the embedded broker, so the producer can send before the listener starts receiving.

`persistent=false` is for the demo only; do not use this setting to claim a queue preserves messages across restarts. `timeout-per-shutdown-phase` adjusts the lifecycle wait budget during normal shutdown and does not guarantee every task finishes if the process is killed.

### 6.4. OrderBusinessService.java

~~~java
package com.example.jmslifecycle;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;

import org.springframework.stereotype.Service;

@Service
public class OrderBusinessService {

    private final CountDownLatch processed = new CountDownLatch(1);
    private volatile boolean initialized;

    @PostConstruct
    public void initialize() {
        initialized = true;
        System.out.println("BUSINESS_POST_CONSTRUCT");
    }

    public void process(String orderId) {
        if (!initialized) {
            throw new IllegalStateException("Business service not ready");
        }
        System.out.println("BUSINESS_HANDLE=" + orderId);
        processed.countDown();
    }

    public boolean awaitProcessed(long timeout, TimeUnit unit)
            throws InterruptedException {
        return processed.await(timeout, unit);
    }

    public boolean isInitialized() {
        return initialized;
    }

    @PreDestroy
    public void destroy() {
        initialized = false;
        System.out.println("BUSINESS_PRE_DESTROY");
    }
}
~~~

`@PostConstruct` runs when Spring initializes the bean. The `process` method can be called per message; `@PreDestroy` runs when the Spring context destroys the bean. `CountDownLatch` is only for observing one message in the demo; do not use a single-use latch as long-lived processing state in production.

### 6.5. OrderMessageListener.java

~~~java
package com.example.jmslifecycle;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderMessageListener {

    private final OrderBusinessService business;

    public OrderMessageListener(OrderBusinessService business) {
        this.business = business;
    }

    @JmsListener(
            id = "orderLifecycleListener",
            destination = "demo.lifecycle")
    public void onMessage(String body) {
        business.process(body);
    }
}
~~~

The listener bean simply delegates the message to `OrderBusinessService`. The container with ID `orderLifecycleListener` is managed separately by the registry. Placing business logic inside a service enables testing independently of JMS and cleanly applying DB transactions via Spring proxies.

### 6.6. JmsLifecycleApplication.java

~~~java
package com.example.jmslifecycle;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.listener.MessageListenerContainer;

@SpringBootApplication
@EnableJms
public class JmsLifecycleApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(
                             JmsLifecycleApplication.class, args)) {
            // Runner has already executed when SpringApplication.run returns.
            // Close context after the demo to observe @PreDestroy.
        }
    }

    @Bean
    ApplicationRunner demonstrateLifecycle(
            OrderBusinessService business,
            JmsTemplate template,
            JmsListenerEndpointRegistry registry) {

        return args -> {
            MessageListenerContainer container =
                    registry.getListenerContainer("orderLifecycleListener");

            if (container == null) {
                throw new IllegalStateException("Endpoint not registered");
            }

            System.out.println(
                    "BUSINESS_INITIALIZED=" + business.isInitialized());
            System.out.println(
                    "LISTENER_RUNNING_BEFORE=" + container.isRunning());

            if (container.isRunning()) {
                throw new IllegalStateException(
                        "Expected auto-startup=false");
            }

            template.convertAndSend("demo.lifecycle", "ORDER-160");
            System.out.println("MESSAGE_SENT_WHILE_STOPPED");

            container.start();

            if (!business.awaitProcessed(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Listener did not handle message in 10 seconds");
            }

            CountDownLatch stopped = new CountDownLatch(1);
            container.stop(stopped::countDown);

            if (!stopped.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Listener stop did not finish in 10 seconds");
            }

            System.out.println(
                    "LISTENER_RUNNING_AFTER_STOP=" + container.isRunning());
            System.out.println(
                    "BUSINESS_INITIALIZED_AFTER_STOP="
                            + business.isInitialized());
        };
    }
}
~~~

**Step-by-step explanation:**

1. Spring Boot creates the singleton `OrderBusinessService` and runs `@PostConstruct`. It is also injected into the listener and `ApplicationRunner`.
2. `@EnableJms` enables annotation endpoint infrastructure (Spring Boot JMS auto-configuration can also assist with this step).
3. `auto-startup=false` ensures the container is registered yet not automatically started during normal context refresh.
4. The runner fetches the exact container via `registry.getListenerContainer("orderLifecycleListener")`, rather than looking up a bean by class name.
5. `BUSINESS_INITIALIZED=true` and `LISTENER_RUNNING_BEFORE=false` illustrate **two independent states**.
6. The `JmsTemplate` producer sends a message to the broker while the listener is still stopped; the message can be held by the queue for a future consumer per broker policy.
7. `container.start()` allows the listener to receive; `CountDownLatch` is released when the business method has been invoked.
8. `container.stop(stopped::countDown)` and `stopped.await` wait for stopping to complete. With `DefaultMessageListenerContainer`, the callback signals when listener processing has actually stopped.
9. After stop, the business bean remains initialized; calling stop **does not run `@PreDestroy`**.
10. The `try-with-resources` block in `main` closes the Spring context; `@PreDestroy` is invoked when bean destruction occurs.

**Note:** the handler latch is released before the callback handler completely finishes; the demo uses the stop callback to avoid treating each latch release as proof that the JMS transaction committed. Do not assume from this output alone that exactly-once processing is guaranteed.

### 6.7. Running and observing

In the project directory:

~~~bash
mvn spring-boot:run
~~~

Lines printed by application code (excluding Maven/Spring/Artemis logs), assuming the embedded broker starts successfully and the Queue has no competing consumers:

~~~text
BUSINESS_POST_CONSTRUCT
BUSINESS_INITIALIZED=true
LISTENER_RUNNING_BEFORE=false
MESSAGE_SENT_WHILE_STOPPED
BUSINESS_HANDLE=ORDER-160
LISTENER_RUNNING_AFTER_STOP=false
BUSINESS_INITIALIZED_AFTER_STOP=true
BUSINESS_PRE_DESTROY
~~~

This is **expected output**, not an actual local build/run result. If the listener fails to receive the message within 10 seconds or fails to stop within 10 seconds, the demo throws a meaningful exception to catch errors rather than failing silently. On a production broker with backlog, TTL, other consumers, or connection issues, timing behavior may differ.

### 6.8. Experiments for deeper understanding

- Change `spring.jms.listener.auto-startup=false` to `true`: the container may already be running before the Runner starts, causing the explicit assertion to fail.
- Omit `container.start()`: the bean remains initialized, yet messages are not processed by **this listener**. Without competing consumers, they can wait on the Queue.
- Call `container.stop()` and then `start()` again: the container resumes receiving messages, but `@PostConstruct` does not re-run; testing a second message requires a new latch/counter since the demo latch is single-use.
- Remove `@JmsListener` or use an inactive `@Profile`: `registry.getListenerContainer(...)` returns null, unlike an existing container that is stopped.
- Close the context early while a handler is still running: you must consider transactions/ack and shutdown budgets; do not assume every message finished processing.

## 7. Runtime Control with JmsListenerEndpointRegistry

With multiple listeners, give each endpoint an ID:

~~~java
@Component
public class PaymentListener {

    @JmsListener(
            id = "paymentCommandsListener",
            destination = "payments.commands")
    public void onPayment(String payload) {
        // Delegate to the business service.
    }
}
~~~

In an authorized coordinator/operator component:

~~~java
// Fragment: registry is an injected JmsListenerEndpointRegistry.
org.springframework.jms.listener.MessageListenerContainer container =
        registry.getListenerContainer("paymentCommandsListener");

if (container == null) {
    throw new IllegalArgumentException("Unknown endpoint ID");
}

if (!container.isRunning()) {
    container.start();
}

// When needing to pause this exact endpoint:
container.stop();
~~~

`registry.getListenerContainerIds()` lists IDs; `getListenerContainers()` returns the collection of containers; `getListenerContainer(id)` returns one container or null if the endpoint does not exist.

**Distinguish the commands:**

| API | Scope |
| --- | --- |
| `registry.start()` | Requests starting registry-managed containers; when called manually after context refresh, may also start containers configured with autoStartup=false. |
| `registry.stop()` | Stops all registry-managed containers, not just one Queue. |
| `container.start()` | Starts only the container selected by ID. |
| `container.stop()` | Stops only the selected container. |
| `container.isRunning()` | Lifecycle status of a specific container. |

`registry.isRunning()` does not prove **all** endpoints are healthy/running. With multiple containers, inspect each container individually along with broker-level consumer counts/queue age. Never expose an unprotected public HTTP endpoint allowing anyone to call `registry.stop()`: it could halt all pipelines. Such controls need RBAC, auditing, feature policies, and synchronization when multiple operators/automations exist.

### 7.1. Annotation-created container beans vs manually declared container beans

~~~java
@Bean
DefaultMessageListenerContainer manuallyManagedContainer(
        jakarta.jms.ConnectionFactory factory,
        jakarta.jms.MessageListener listener) {
    DefaultMessageListenerContainer container =
            new DefaultMessageListenerContainer();
    container.setConnectionFactory(factory);
    container.setDestinationName("orders.commands");
    container.setMessageListener(listener);
    return container;
}
~~~

This is a **bean factory fragment** requiring Spring JMS imports and a matching `MessageListener` bean. This container is registered directly in the Spring context and can be autowired; Spring manages its lifecycle as a `SmartLifecycle` bean. It **is not the container auto-created by the registry for `@JmsListener`** unless you explicitly wire them via a custom mechanism. Never declare both a manual container and an annotation endpoint on the same destination without understanding competing consumers.

## 8. Configuring autoStartup: Boot, Factory, and Endpoint

### 8.1. Spring Boot property

~~~properties
spring.jms.listener.auto-startup=false
~~~

This property applies to the **Boot auto-configured listener container factory**. Business beans are still created; annotated endpoints are still registered. If the application defines a custom factory without Boot's configurer, the corresponding policy must be set on that factory.

### 8.2. Custom factory (preserving Boot defaults)

~~~java
// Fragment in @Configuration; requires importing Bean,
// DefaultJmsListenerContainerFactory, and ConnectionFactory.
@Bean
DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        jakarta.jms.ConnectionFactory connectionFactory,
        org.springframework.boot.autoconfigure.jms
                .DefaultJmsListenerContainerFactoryConfigurer configurer) {

    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();
    configurer.configure(factory, connectionFactory);

    factory.setAutoStartup(false);
    factory.setConcurrency("2-4");
    factory.setSessionTransacted(true);
    return factory;
}
~~~

`DefaultJmsListenerContainerFactoryConfigurer` is a Spring Boot helper that configures a factory with Boot's properties/defaults; subsequent setters customize further. This fragment **replaces the default factory** if named `jmsListenerContainerFactory`; do not copy it into a demo alongside conflicting configurations without understanding bean selection.

### 8.3. Per-endpoint custom factory

~~~java
@JmsListener(
        id = "priorityListener",
        destination = "orders.priority",
        containerFactory = "priorityJmsListenerContainerFactory")
public void onPriority(String body) {
    // Handler.
}
~~~

`@JmsListener` has a `containerFactory` attribute, but **no per-endpoint `autoStartup` attribute defined as an annotation field** in Spring JMS 6.x. If two endpoints need different auto-start policies, use two corresponding factories or manage them separately via the registry.

Do not interpret `autoStartup=false` as permanently disabling the listener: a valid `start()` call can still begin receiving.

## 9. Readiness: Preventing Premature Message Reception

A service may need to finish database migrations, warm caches, fetch credentials, or check feature flags or routing metadata before processing. If a listener auto-starts before those steps complete, messages may fail/retry even though the business bean already exists.

Controlled approach:

1. Set listener `autoStartup=false` initially.
2. Let Spring create all business beans and register endpoints.
3. After context refresh, a startup coordinator checks readiness criteria with a timeout.
4. When ready, look up the container by ID and call `start()`.
5. Log/record metrics at the state transition timestamp.
6. When readiness is lost, transition the system into an agreed pause/retry policy; do not replace broker failure/recovery with pointless context refreshes.

~~~java
// Fragment: registry and readinessService belong to the injected coordinator.
MessageListenerContainer listener =
        registry.getListenerContainer("orderLifecycleListener");

if (listener == null) {
    throw new IllegalStateException("Listener not registered");
}

if (readinessService.isReadyForOrders()) {
    listener.start();
}
~~~

`readinessService.isReadyForOrders()` is an **application method**, not a standard Spring API. When conditions are not met, surface alerts and coordinator retry/resume mechanisms; do not silently allow Queues to build unbounded backlogs.

**Note:** Spring Boot's `ApplicationReadyEvent` fires after runners, yet if a container auto-starts, it can receive messages **before** the event. Kubernetes/Actuator readiness controls HTTP traffic and does not stop JMS listeners by default; sharing business readiness requires explicit coordination.

## 10. Graceful Shutdown: Stopping Containers Before Destroying Beans

When a Spring ApplicationContext closes normally, the lifecycle processor stops `SmartLifecycle` components in **descending phase order**, and then Spring runs destruction callbacks. That is why container stopping must be separated from business bean destruction.

Desired timeline:

~~~text
10:00:00  Listener receives message M1, opens JMS transaction.
10:00:02  Application receives normal shutdown signal.
10:00:02  Lifecycle processor requests listener stop.
10:00:03  Handler M1 finishes and transaction/ack is resolved.
10:00:03+ Stop callback reports container stopped.
10:00:04  Spring proceeds with bean destruction callbacks.
~~~

This timeline is **illustrative**. Depending on provider, prefetch, concurrency, and processing duration, stopping may take longer; if the process receives SIGKILL, `@PreDestroy` may not run and messages may be redelivered.

### 10.1. stop(Runnable) for controlled shutdown

~~~java
// Fragment with MessageListenerContainer container.
java.util.concurrent.CountDownLatch stopped =
        new java.util.concurrent.CountDownLatch(1);

container.stop(stopped::countDown);

if (!stopped.await(30, java.util.concurrent.TimeUnit.SECONDS)) {
    throw new IllegalStateException("Timed out stopping listener");
}
~~~

For `DefaultMessageListenerContainer`, Javadoc states the stop callback is invoked once listener processing has actually stopped. **Do not call `start()` concurrently while waiting for the stop callback**; the callback might never be invoked if a new start interleaves. If `stop(callback)` is called multiple times before stopping completes, a later callback may replace an earlier one depending on implementation — serialize operational commands.

Boot configuration:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

This is a budget per shutdown phase; it **does not guarantee** every handler gets exactly 20 seconds, does not guarantee DB/JMS commits under all failures, and does not replace Kubernetes deadlines.

### 10.2. What should a bean's @PreDestroy do?

A business bean's `@PreDestroy` makes sense for **resources owned by that bean** (flushing buffers, closing schedulers or files it created safely). **Never close JMS Connections/Sessions/Consumers owned by the listener container** inside `OrderBusinessService.@PreDestroy`; Spring's JMS container manages its own resources.

Conversely, container `stop()` is not a command to destroy all business dependencies. Separating ownership avoids double-closes, races, and callbacks trying to use already-destroyed dependencies.

## 11. Recovery: Broker Down Does Not Mean Bean Destroyed

`DefaultMessageListenerContainer` has built-in recovery attempts when the JMS broker becomes temporarily unavailable. Business beans stay alive; the container can maintain a running state even without healthy connections/consumers during a retry/backoff window.

~~~text
Business bean:         initialized ---------------- initialized
Container lifecycle:   running --------------------- running
Broker availability:   UP ------- DOWN ---- retry --- UP
Message processing:    yes ------ none ------------- yes
~~~

Observations to keep separate:

- `registry.getListenerContainer(id)!=null`: endpoint is registered.
- `container.isRunning()`: container lifecycle has started.
- Broker consumer count/connection health: JMS resources are active.
- Queue depth, oldest-message age, DLQ/redelivery: flow is progressing or stuck.
- Last-successful-process timestamp and business error rate: handler is actually succeeding.

Never manually call `new OrderBusinessService()` or `ApplicationContext.refresh()` on every broker reconnect: that confuses **JMS infrastructure lifecycle** with **bean lifecycle**.

### 11.1. DefaultMessageListenerContainer vs SimpleMessageListenerContainer

| Criterion | DefaultMessageListenerContainer | SimpleMessageListenerContainer |
| --- | --- | --- |
| Receiving messages | Actively polls/dispatches in consumer tasks. | Uses `MessageConsumer.setMessageListener` for provider callbacks. |
| Concurrency scaling | Supports scaling within configured bounds. | Consumer count is essentially fixed. |
| Broker recovery | Has configurable recovery/backoff. | Simpler, lacks some of DMLC's adaptive/recovery capabilities. |
| External/JTA transactions | Can be configured to join XA/JTA with suitable infrastructure. | Does not support external transaction modes equivalently. |
| Lifecycle | `SmartLifecycle` start/stop. | `SmartLifecycle` start/stop. |

In many Spring Boot setups, the default factory creates `DefaultMessageListenerContainer`, yet if the application replaces the factory, verify the actual implementation. Do not generalize DMLC's stop callback/recovery assertions to every provider or custom container.

## 12. Transactions and Acknowledgements Remain Separate Responsibilities

Stopping a container does not by itself determine whether in-flight message processing succeeded or failed. That depends on JMS Session mode, transaction manager, and provider:

- `AUTO_ACKNOWLEDGE` has reliability limitations when a listener throws exceptions depending on container/provider.
- `CLIENT_ACKNOWLEDGE` acknowledges per JMS Session semantics; a business method logging does not mean the message was acked.
- `sessionTransacted=true` makes the container use a local JMS transaction, committing/rolling back within the session on success/failure.
- `JtaTransactionManager` can coordinate XA resources when configured properly; it is **not enabled automatically** merely by adding `@Transactional`.
- A business `@Transactional` with a DB transaction manager **does not automatically** combine DB and JMS into one atomic transaction.

Example of a service invoked through a Spring proxy:

~~~java
@Service
public class PaymentService {

    @Transactional
    public void persistPayment(String eventId, String paymentId) {
        // DB operation and idempotency constraint.
    }
}

@Component
public class PaymentListener {

    private final PaymentService service;

    public PaymentListener(PaymentService service) {
        this.service = service;
    }

    @JmsListener(destination = "payments.events")
    public void handle(String jsonBody) {
        // Parse/validate message and call service.persistPayment(...).
    }
}
~~~

These are **two fragments**, not standalone compilable/runnable files: they need packages/imports, repository logic, a transaction manager, and a broker. The goal is to separate the JMS callback adapter from the business transaction proxy. Avoid **self-invocation** that prevents `@Transactional` from applying as expected.

If the app crashes between DB commit and JMS ack, the message may be redelivered; the business method needs **idempotency** via `eventId`/unique key or an inbox pattern. `container.stop()` also does not mean all messages on the Queue were acknowledged.

## 13. Concurrency: There Is No New Bean Per Message

With `@JmsListener(concurrency = "3-10")` or factory `setConcurrency("3-10")`, the container can spawn multiple JMS consumer tasks and invoke **the same singleton listener/service** from multiple threads.

~~~java
@Service
public class UnsafeStats {

    private int handled;

    public void count() {
        handled++; // Not thread-safe when multiple listener threads call concurrently.
    }
}
~~~

This is an **anti-pattern**. A singleton business bean does not replicate itself per message or consumer thread. In production, use thread-safe counters/metrics, transactional database writes, and avoid unprotected shared mutable state.

**Important:** `@PostConstruct` still typically runs only once for a singleton instance, even if the handler is called thousands of times. Restarting a JMS consumer thread after a broker reconnect is not a reason to re-invoke the bean constructor either.

If using prototype/custom-scoped beans, design scope and injection explicitly; Spring JMS does not provide "a new business bean per message" by default. Avoid storing `ThreadLocal` values without cleanup in worker pools; tracing/request context can leak across messages.

## 14. When to Start/Stop and When Not To

**Sensible:**

- Temporarily pausing a Queue during planned downstream maintenance.
- Waiting for database migrations or config preparation before starting to consume.
- Enabling/disabling a group of listeners via monitored feature flags.
- Managing graceful shutdown/in-flight processing during rollouts.
- Stopping a failing consumer for investigation without destroying business service beans.

**Not sensible:**

- Starting/stopping the container for **every message** (resource creation/teardown cost, race risks).
- Calling `registry.stop()` when intending to stop just one listener; it can stop all of them.
- Manually calling `@PostConstruct` to "restart a bean", or treating it as a listener start callback.
- Manually constructing listener containers inside business handlers on every error.
- Using pause as a permanent substitute for retry/backoff/idempotency.
- Relying on stop to guarantee a Queue has no remaining messages, or that a non-durable Topic retains all events while offline.

**Topic note:** with a non-durable subscription, stopping the consumer/subscription may cause messages published while offline to be dropped. Durable subscriptions/retention still depend on broker policy. With a Queue, unprocessed messages usually wait, yet remain subject to TTL, expiry, DLQ, and capacity limits. Never apply one simplistic assumption to every destination.

## 15. Testing Both Lifecycles

### 15.1. Unit testing the business bean

For `OrderBusinessService`:

- Test processing logic and validation independently without a broker.
- If instantiating a bean with `new` outside Spring, `@PostConstruct` **does not run automatically**; callbacks are Spring-managed. Construct appropriate test fixtures or test via a Spring context.
- Do not mock `JmsListenerEndpointRegistry` solely to unit test pure domain logic.

### 15.2. Integration testing with a broker

A solid integration test:

1. Set `spring.jms.listener.auto-startup=false`.
2. Inject business service + registry; assert service is initialized, endpoint exists, and container is stopped.
3. Send a message to a test-dedicated Queue.
4. Verify the handler has not been called while the listener is stopped within a controlled window.
5. Start the listener; use a latch/polling with timeout to wait for the real handler.
6. Stop the listener using `stop(Runnable)` and wait for the callback.
7. Assert the business bean is still **the exact same instance** if singleton-scoped.
8. Restart, send a second message; assert `@PostConstruct` does not run a second time.
9. Close ApplicationContext; assert destroy callback on normal shutdown.
10. Add separate tests for broker disconnect, transaction rollback, in-flight stop, and redelivery.

Use a test Queue **without competing consumers**; if another worker grabs the message, tests become flaky. Never use `Thread.sleep(10)` as conclusive proof of lifecycle ordering.

### 15.3. Assertions to keep separate

| Assertion | Proves |
| --- | --- |
| Bean present in context, init flag true. | Bean initialized. |
| Registry returns container for the expected ID. | Endpoint registered. |
| `container.isRunning()==false` before start. | Container did not auto-start in test config. |
| Handler latch released after start. | Handler method was invoked. |
| Stop callback completed. | Container stopped per callback contract. |
| Bean remains initialized after stop. | Stopping container does not destroy business bean. |
| `@PreDestroy` runs on context close. | Bean destruction is separate from listener stop. |
| Broker consumer count and logs. | Additional evidence of JMS connectivity. |

Do not conflate "handler ran" and "business commit succeeded" in the same assertion; transactions must be verified independently.

## 16. Common Troubleshooting Table

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| `@PostConstruct` runs but no JMS received | Auto-startup false, broker offline, wrong Queue, missing permissions. | Registry, container `isRunning`, broker logs. |
| Listener receives message before ApplicationRunner | SmartLifecycle auto-start during context refresh. | Configure autoStartup; use a controlled readiness gate. |
| `getListenerContainer(id)==null` | Wrong ID, `@JmsListener` not scanned/enabled, inactive profile. | Annotation ID, registry IDs, factory config. |
| Stopped listener yet bean did not run `@PreDestroy` | Stop only controls the container. | Close ApplicationContext if bean destruction is expected. |
| Started listener yet constructor did not re-run | Singleton bean already exists. | This is expected Spring bean lifecycle behavior. |
| Container running yet broker shows zero consumers | Broker connectivity/recovery/authorization. | Consumer count, recovery logs, queue depth. |
| Changing Boot property has no effect | Custom factory skips Boot configurer or endpoint selects another factory. | Factory bean name, `containerFactory` on annotation. |
| Bean hits race processing multiple messages | Container concurrency >1, mutable shared fields. | Thread-safety, transaction boundaries. |
| Duplicate side effects after restart | JMS ack/commit out of sync with DB. | Idempotency/outbox/inbox/transactions. |
| Shutdown timeout | Slow handler, prefetch, receive timeout, resource cleanup. | SmartLifecycle phase, stop callback, logs. |
| `registry.stop()` halts multiple Queues | Stopped all registry-managed containers. | Control by ID instead of stopping entire registry. |
| Broker reconnects repeatedly recreate beans | Code refreshes context at the wrong responsibility layer. | Let DMLC recover; never recreate beans. |
| Context closed yet messages still processing | In-flight/async tasks not drained or broken lifecycle shutdown. | Stop callback, task executor, termination deadline. |
| Queue keeps growing while paused | Producers continue sending while listener is stopped. | Backlog, TTL/expiry, producer rate. |
| Topic loses messages while listener is stopped | Non-durable subscription semantics. | Choose durable subscription when appropriate. |

## 17. Production Design Principles

1. **Separate JMS adapter and business service** when logic is complex: the listener only parses/validates/dispatches while the service owns domain transactions.
2. **Keep bean initialization independent of JMS reception**: never place receive loops or long-blocking broker calls in `@PostConstruct`.
3. **Configure autoStartup per readiness needs**: use manual start when special dependency conditions apply.
4. **Use stable IDs for every endpoint**: manage via registry and monitor per destination.
5. **Protect start/stop controls with RBAC and auditing**; avoid unguarded public controls.
6. **Respect SmartLifecycle phases** during startup/shutdown; do not assume bean init callbacks replace phase ordering.
7. **Handle in-flight work with timeouts** and idempotency; never expect crashes to always invoke `@PreDestroy`.
8. **Never treat isRunning as complete health**: monitor broker metrics, last success, exception rates, and backlogs.
9. **Keep handlers thread-safe** as listener concurrency scales; singleton business beans are not copied automatically.
10. **Test both paused and running states**, transaction/recovery, concurrency, and Topic durable semantics where applicable.

## 18. Review Questions

1. Does `@JmsListener` make Spring create a new business bean per message? **No**, the container invokes the bean's method according to its current scope.
2. Does an initialized bean imply the listener is running? **No.**
3. Does `container.stop()` run `@PreDestroy`? **No**, beans are only destroyed per ApplicationContext/bean lifecycle.
4. Does calling `container.start()` after stop re-run `@PostConstruct`? **No**, as long as the singleton bean/context still exists.
5. What does `JmsListenerEndpointRegistry` manage? **The listener containers of annotation endpoints** and their lifecycles.
6. Why shouldn't you `@Autowired MessageListenerContainer` to grab an annotated endpoint? **Registry-managed containers are not standalone beans by default**.
7. What does `spring.jms.listener.auto-startup=false` affect? **Prevents the container from auto-starting; does not prevent bean init or endpoint registration**.
8. Does `isRunning()==true` guarantee the broker is reachable? **No**, DMLC could be recovering.
9. In what order do lifecycle phases start/stop? **Startup in ascending phase order; shutdown in descending phase order**.
10. Can a listener receive before `ApplicationReadyEvent`? **Yes**, if auto-startup is enabled.
11. What is the benefit of `stop(Runnable)`? **Knowing when listener processing has stopped per implementation**, to coordinate shutdown.
12. Does concurrency 5 mean 5 copies of the business bean? **No**, multiple threads normally call the same singleton.
13. Does a handler exception automatically destroy the Spring bean? **No**; it enters the container's transaction/error handling.
14. Does broker downtime re-run `@PostConstruct`? **No**; container/recovery infrastructure handles it.
15. Does pausing a Queue listener forbid producers from sending? **No**; Queue/backlog remains governed by broker policies.
16. Does DB `@Transactional` automatically combine with the JMS transaction? **No**, explicit transaction design is required.
17. To pause only the payment listener, should you call `registry.stop()`? **No**, use `getListenerContainer(id).stop()`.
18. When an app is killed with SIGKILL, is `@PreDestroy` guaranteed to run? **No**.
19. Can a registered listener that was never started receive messages? **Not from that listener itself**.
20. What is the goal of separating business services from listener containers? **Separating "what to process" from "when and how to receive/dispatch"**.

## 19. Official Documentation

- [Spring Framework 6.2 — Annotation-driven JMS listener endpoints](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html): annotations, endpoint registration, `@EnableJms`, factories, and registry.
- [Spring Framework 6.2 — Using Spring JMS](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html): POJO listeners, Simple/Default MessageListenerContainer.
- [Spring Framework — JmsListenerEndpointRegistry API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistry.html): `getListenerContainer`, start, stop, lifecycle.
- [Spring Framework — @JmsListener API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/annotation/JmsListener.html): `id`, `destination`, `containerFactory`, concurrency.
- [Spring Framework — DefaultMessageListenerContainer API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html): recovery and `stop(Runnable)`.
- [Spring Framework — SmartLifecycle API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/SmartLifecycle.html): phase, auto-startup, stop callback.
- [Spring Boot 3.5 — JMS/Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html): JMS integration/embedded Artemis.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): `spring.jms.listener.auto-startup` and related settings.
- [Spring Boot 3.5 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html): `spring.lifecycle.timeout-per-shutdown-phase`.
- [Spring Boot 3.5 — DefaultJmsListenerContainerFactoryConfigurer API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/jms/DefaultJmsListenerContainerFactoryConfigurer.html): custom factory preserving Boot defaults.

**Remember:** a Spring business bean goes through **create → inject → initialize (`@PostConstruct`) → serve → destroy (`@PreDestroy`)**; a listener container goes through **register/init → start → receive/dispatch → stop/restart → destroy**. The two lifecycles coordinate through the Spring context yet are not the same object. Use `JmsListenerEndpointRegistry` to control containers by ID, `SmartLifecycle`/autoStartup/phase to coordinate, and transactions/idempotency/monitoring for reliability.
