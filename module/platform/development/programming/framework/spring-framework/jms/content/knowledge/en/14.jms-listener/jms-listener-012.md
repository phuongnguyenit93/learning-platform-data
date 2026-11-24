# autoStartup, phase, and Start/Stop Ordering with @JmsListener (Spring JMS)

## 1. The Problem: Application Startup Does Not Mean Consumers Must Receive Immediately

A Spring Boot service has two activities: initializing resources for order processing and consuming JMS events from queue `orders.in`. If a listener receives messages before data sources or dependencies are ready, processing can fail immediately during deployment. Conversely, on shutdown, if data sources close while the listener is still processing, in-flight messages may fail or require redelivery.

We need to control three distinct decisions:

1. **`autoStartup`:** should the listener container automatically start running when the Spring `ApplicationContext` refreshes?
2. **`phase`:** when `SmartLifecycle` components auto-start/stop in the same context, which components are **asked to start first**, and which are **asked to stop first**?
3. **Runtime control:** once the application has started, who is allowed to call `start()`/`stop()` on a specific listener, and what happens to in-flight messages?

Target flow:

```text
                   AT STARTUP
Spring creates beans / endpoint / listener container
                       |
                       v
                Check autoStartup
                       |
                +------+------+
                |             |
               true          false
                |             |
                v             v
       lifecycle start   keep container
       by phase          in non-running state
                |             |
                v             v
       receive message   wait for explicit start()
                |
                v
       @JmsListener processes

                   ON SHUTDOWN
Spring requests stopping SmartLifecycle components:
higher phase first -> lower phase later
          |
listener stops receiving/drains per capabilities & config
          |
required dependencies can stop after listener
```

**Core point:** in Spring JMS 6.x, `@JmsListener` **does not directly declare** `autoStartup` or `phase` attributes. Those two settings belong to the **listener container** or **`JmsListenerContainerFactory`**, and are coordinated by `JmsListenerEndpointRegistry` and Spring's lifecycle processor.

## 2. Distinguishing Annotation, Factory, Container, and Registry

Look at an endpoint:

```java
@JmsListener(
        id = "ordersWorker",
        destination = "orders.in",
        containerFactory = "controlledJmsListenerFactory")
public void consume(String body) {
    orderService.process(body);
}
```

This is an **illustrative method snippet** inside a managed Spring bean; `orderService` is injected, not a standalone Java program.

| Component | Lifecycle Role |
| --- | --- |
| `@JmsListener` | Declares endpoint, `id`, `destination`, `containerFactory`, `selector`, `concurrency`... |
| `DefaultJmsListenerContainerFactory` | Creates `DefaultMessageListenerContainer` for endpoints; has `setAutoStartup(boolean)` and `setPhase(int)` |
| `DefaultMessageListenerContainer` | Actually owns consumer/session, controls `start()`, `stop()`, and `isRunning()` state |
| `JmsListenerEndpointRegistry` | Registers/looks up/manages `@JmsListener`-created containers; participates in `SmartLifecycle` itself |
| Spring's `DefaultLifecycleProcessor` | Coordinates start/stop of lifecycle components by `phase` within an `ApplicationContext` |
| JMS broker | Holds and dispatches messages; the broker knows nothing about Spring bean lifecycle phases |

A method written as:

```java
@JmsListener(
        destination = "orders.in",
        autoStartup = "false", // WRONG: not a @JmsListener attribute in Spring JMS 6.2.
        phase = 100)           // WRONG: not a @JmsListener attribute.
public void consume(String body) {}
```

is an **intentional counter-example** that **does not compile**. Never copy lifecycle attributes from `@KafkaListener` onto `@JmsListener` assuming both annotations share the same attribute set.

Proper Spring JMS configuration places those two settings on `DefaultJmsListenerContainerFactory`:

```java
DefaultJmsListenerContainerFactory factory =
        new DefaultJmsListenerContainerFactory();
factory.setConnectionFactory(connectionFactory);
factory.setAutoStartup(false);
factory.setPhase(100);
```

This snippet assumes a `jakarta.jms.ConnectionFactory connectionFactory` variable inside a configuration method. It only illustrates setters, not a complete Spring context.

## 3. autoStartup: Creating an Endpoint Differs from Starting Consumption

`DefaultMessageListenerContainer` inherits `setAutoStartup(boolean)` from `AbstractJmsListeningContainer`:

- **`true`**, the container default: the container is allowed to auto-start during lifecycle refresh via the registry/context mechanism.
- **`false`:** the container is still created, registered, and configured with destination/handler, yet does not automatically consume messages just because the app refreshed. It can be started with an explicit `start()` call.

These are distinct states:

| State | `@JmsListener` endpoint exists? | Container running? | Consumer receiving messages? |
| --- | --- | --- | --- |
| Registered, `autoStartup=false`, `start` not called | Yes | Not running | No, for this container |
| `start()` called successfully at lifecycle level | Yes | `isRunning()` can become `true` | Can start receiving if connection/broker/selector are valid |
| `stop()` called and stop finished | Yes | `false` | That container stops receiving |
| Another application still has a consumer on the same queue | Unrelated | Depends on the other app | Other consumers can still receive |

**Do not confuse `autoStartup=false` with "disabling the annotation".** Spring still discovers the endpoint; the listener bean and its dependencies still must initialize cleanly. It also **does not** pause the whole queue on the broker, stop consumers in other instances, or prevent producers from sending messages.

### 3.1. When Should You Disable autoStartup?

Sensible scenarios:

- Only allow consumption after an actual readiness check or migration step succeeds.
- Decouple application deployment from turning on consumers (cutover/blue-green).
- Start the service early while consuming only during an approved operational window.
- Perform a dry run checking connectivity/configuration before enabling real intake.
- In demo environments, send multiple messages to a queue before explicitly starting the listener.

`autoStartup=false` **does not perform readiness checks automatically**; the application must define who checks readiness and who calls `start`.

### 3.2. Spring Boot: Global Property vs. Custom Factory

When using **Spring Boot's auto-configured default listener factory**, Spring Boot 3.4 supports:

```yaml
spring:
  jms:
    listener:
      auto-startup: false
```

That configures `spring.jms.listener.auto-startup`, which defaults to `true`. It affects the default factory provided by Boot (and factories configured via Boot's configurer appropriately).

If the application **manually creates** a `DefaultJmsListenerContainerFactory` bean without Boot's `DefaultJmsListenerContainerFactoryConfigurer`, do not assume that property updates your factory automatically. Call `factory.setAutoStartup(false)` directly or let Boot's configurer configure the factory and override deliberately.

There is no universal Spring Boot property named `spring.jms.listener.phase` in standard 3.4 properties. If you want to configure phase via YAML for a custom factory, make it an **application-defined property**, e.g., `app.jms.listener-phase`.

## 4. phase: Start Order Is the Reverse of Stop Order

`DefaultMessageListenerContainer` implements `SmartLifecycle` through its superclasses. Spring's `SmartLifecycle` rules are clear:

- On context startup, components with **lower phase start before** components with higher phase.
- On context shutdown, components with **higher phase stop before** components with lower phase.
- Components sharing **the same phase** have no guaranteed relative order within that phase.
- `SmartLifecycle.DEFAULT_PHASE` is `Integer.MAX_VALUE`. `AbstractJmsListeningContainer` uses this default, meaning it typically starts quite late and stops quite early compared to lifecycle beans at lower phases.
- Plain `Lifecycle` (non-`SmartLifecycle`) beans are treated by Spring's lifecycle processor as phase 0 unless special rules apply.
- Explicit bean `depends-on` relationships can take precedence over phases per the `SmartLifecycle` specification. However, listener containers created by the registry **are not simple beans matching the endpoint name**, so you cannot just put `@DependsOn` on a listener method to force per-container start ordering.

Example:

| Component | Phase | Start | Stop |
| --- | ---: | --- | --- |
| Dependency preparer (SmartLifecycle) | `0` | First | Last |
| Registry holding JMS listeners | `100` | After dependency | Before dependency |

Timeline:

```text
START:
  phase 0:   prerequisite.start() finishes
                         |
  phase 100: registry/JMS listener containers start
                         |
             consumers begin receiving once provider is ready

STOP:
  phase 100: registry/JMS listener containers stop
                         |
  phase 0:   prerequisite.stop()
```

This is a **lifecycle invocation order**. It is **not** a guarantee that the consumer is already connected to the broker the instant `start()` returns, that a dependency is healthy if its `start()` returns immediately after launching background work, or that all business tasks finish by a fixed deadline.

### 4.1. phase Is Not a Delay, Priority, or Message Order

`setPhase(100)` does **not** mean wait 100 seconds, buffer 100 messages, run 100 threads, or give messages JMS priority 100.

Concepts to keep distinct:

- `phase`: start/stop order among Spring lifecycle components.
- `autoStartup`: whether to auto-start on context refresh or wait for an explicit command.
- `concurrency`: number of concurrent consumers used by the container.
- `receiveTimeout`: wait duration per poll in receive-loop containers.
- `JMSPriority`: 0–9 priority level of a **message**, handled by the JMS provider per policy.
- `JMS transaction/acknowledgment`: committing/rolling back JMS processing per configuration.

### 4.2. Important Caveat: The Registry Shares a Single Phase

With `@JmsListener`, each annotated method registers as a container managed by `JmsListenerEndpointRegistry`. The registry itself is what participates in the Spring context's `SmartLifecycle`.

In Spring JMS 6.2's implementation, the registry unifies the phase across the containers it creates; if factories produce containers with **conflicting custom phases**, the registry can throw a phase mismatch error. Therefore, **do not** configure endpoint A with phase 10 and endpoint B with phase 20 via two factories expecting to force A to start before B inside the same registry.

If you need explicit ordering between **two endpoints in the same registry**, coordinate them via **ID + explicit start/stop** and real readiness checks (or isolate them into separate lifecycles/contexts), rather than mistaking the registry's phase for a per-method scheduler.

**Conclusion:** `phase` is most useful for placing **the entire JMS listener group** after a shared prerequisite at startup and before that prerequisite at shutdown.

## 5. Standalone Java 17 Example: Computing Phase Order Yourself

Before integrating Spring, we can simulate the sorting rule in plain Java 17. File `PhaseOrderDemo.java`:

```java
import java.util.Comparator;
import java.util.List;

public class PhaseOrderDemo {
    record Unit(String name, int phase) {}

    public static void main(String[] args) {
        List<Unit> units = List.of(
                new Unit("jms-registry", 100),
                new Unit("datastore", 0));

        units.stream()
                .sorted(Comparator.comparingInt(Unit::phase))
                .forEach(unit -> System.out.println(
                        "START " + unit.name() + " phase=" + unit.phase()));

        units.stream()
                .sorted(Comparator.comparingInt(Unit::phase).reversed())
                .forEach(unit -> System.out.println(
                        "STOP " + unit.name() + " phase=" + unit.phase()));
    }
}
```

Run:

```bash
javac PhaseOrderDemo.java
java PhaseOrderDemo
```

Exact stdout:

```text
START datastore phase=0
START jms-registry phase=100
STOP jms-registry phase=100
STOP datastore phase=0
```

This program **only simulates the phase rule via sorting**; there is no Spring, JMS, listener registry, or broker. In real Spring, the lifecycle processor also handles bean dependencies, `autoStartup`, shutdown callbacks, and timeouts; never use this demo program to claim framework lifecycle testing.

## 6. Spring Boot 3.x / Java 17+ Project: Manually Started Listener

Example using Spring Boot 3.4.x, Java 17+, ActiveMQ Artemis, and `jakarta.jms`. Key point: the application has `@JmsListener` yet **does not automatically consume on context startup**. Only when the demo admin profile is enabled or `start()` is called explicitly does the container begin running.

Environment prerequisites:

- JDK 17+ and Gradle compatible with Spring Boot 3.4.x.
- Artemis broker running at `tcp://localhost:61616` or your supplied URL.
- Queue `orders.lifecycle` exists (or broker allows auto-creation per policy).
- Broker account has send/receive permissions.
- No external consumer running on the same queue if you want to observe the demo with one consumer.

### 6.1. File Structure

```text
jms-lifecycle-demo/
  settings.gradle
  build.gradle
  src/main/resources/application.yml
  src/main/java/demo/lifecycle/LifecycleApplication.java
  src/main/java/demo/lifecycle/JmsLifecycleConfiguration.java
  src/main/java/demo/lifecycle/OrdersListener.java
  src/main/java/demo/lifecycle/ManualStartAfterReady.java
  src/main/java/demo/lifecycle/PublishDemoRunner.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'jms-lifecycle-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This example pins versions to avoid behavior shifts across major upgrades. If a real project already has a Spring Boot plugin or BOM, use existing dependency management; never mix different Spring Framework versions.

### 6.2. application.yml

File `src/main/resources/application.yml`:

```yaml
spring:
  artemis:
    mode: native
    broker-url: "${JMS_BROKER_URL:tcp://localhost:61616}"
    user: "${JMS_USER}"
    password: "${JMS_PASSWORD}"
  lifecycle:
    timeout-per-shutdown-phase: 20s

app:
  jms:
    queue: "${JMS_ORDERS_QUEUE:orders.lifecycle}"
    auto-start: "${JMS_AUTO_START:false}"
    listener-phase: "${JMS_LISTENER_PHASE:100}"
```

Explanation:

- `spring.artemis.*` is Spring Boot's JMS connection configuration.
- `spring.lifecycle.timeout-per-shutdown-phase` caps how long the lifecycle processor waits for **one shutdown phase**, set here to 20 seconds for illustration. It does not guarantee a 60-second slow business transaction finishes cleanly within that limit.
- `app.jms.auto-start` and `app.jms.listener-phase` are **two custom properties** for this example, not default Spring Boot property names.
- Values `auto-start=false` and `listener-phase=100` are injected into the factory in the next step. Override them via environment variables when running different modes.
- Supply real secrets via a credentials manager; never commit passwords to the repository.

### 6.3. Spring Boot Application

File `src/main/java/demo/lifecycle/LifecycleApplication.java`:

```java
package demo.lifecycle;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.jms.annotation.EnableJms;

@SpringBootApplication
@EnableJms
public class LifecycleApplication {
    public static void main(String[] args) {
        SpringApplication.run(LifecycleApplication.class, args);
    }
}
```

`@EnableJms` enables detection of annotation-driven JMS endpoints. In Spring Boot configured for JMS, this is also typically enabled by auto-configuration; declaring it explicitly here explains listener registration in a self-contained project.

### 6.4. Factory Configuring autoStartup and phase

File `src/main/java/demo/lifecycle/JmsLifecycleConfiguration.java`:

```java
package demo.lifecycle;

import jakarta.jms.ConnectionFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration(proxyBeanMethods = false)
public class JmsLifecycleConfiguration {

    @Bean("controlledJmsListenerFactory")
    public DefaultJmsListenerContainerFactory controlledJmsListenerFactory(
            ConnectionFactory connectionFactory,
            @Value("${app.jms.auto-start:false}") boolean autoStart,
            @Value("${app.jms.listener-phase:100}") int phase) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1");
        factory.setAutoStartup(autoStart);
        factory.setPhase(phase);
        return factory;
    }
}
```

Analyzing the choices:

1. `DefaultJmsListenerContainerFactory` creates the listener container for endpoints referencing this factory.
2. `setAutoStartup(false)`: by default in this demo, the container **does not auto-start** on context refresh.
3. `setPhase(100)`: when lifecycle auto-start is enabled, the listener group joins phase 100 ordering relative to other `SmartLifecycle` beans. On manual start, `phase` does **not** impose a wall-clock delay.
4. `setConcurrency("1")`: limits to one consumer inside **the endpoint's container**, not the total across replicas running in multiple JVMs.
5. `setSessionTransacted(true)`: uses local JMS session transactions; when a handler throws an exception to the container, the container can roll back so the provider redelivers per policy. This does not make JMS and external database transactions atomic.

The example uses one factory for one endpoint to avoid phase conflicts. When using multiple factories and multiple endpoints in the same registry, verify they have compatible lifecycle phases.

### 6.5. @JmsListener Method with a Fixed ID

File `src/main/java/demo/lifecycle/OrdersListener.java`:

```java
package demo.lifecycle;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrdersListener {

    @JmsListener(
            id = "ordersWorker",
            destination = "${app.jms.queue}",
            containerFactory = "controlledJmsListenerFactory")
    public void onOrder(String payload) {
        if (payload == null || payload.isBlank()) {
            throw new IllegalArgumentException("Empty order event");
        }
        System.out.println("RECEIVED " + payload);
    }
}
```

`id = "ordersWorker"` is the key used by `JmsListenerEndpointRegistry.getListenerContainer("ordersWorker")`. Without `id`, Spring auto-generates an ID, making it hard for management code to reference stably across deployments.

**Caution:** having `@JmsListener` registered and `OrdersListener` present **does not mean** the consumer is running when `autoStartup=false`. That is the exact point of the example.

### 6.6. Starting the Listener Only After ApplicationReadyEvent in the Demo Profile

File `src/main/java/demo/lifecycle/ManualStartAfterReady.java`:

```java
package demo.lifecycle;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.annotation.Profile;
import org.springframework.context.event.EventListener;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@Component
@Profile("manual-demo")
public class ManualStartAfterReady {

    private final JmsListenerEndpointRegistry registry;

    public ManualStartAfterReady(JmsListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void startAfterReady() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersWorker");

        if (container == null) {
            throw new IllegalStateException(
                    "JMS endpoint ordersWorker is not registered");
        }

        if (!container.isRunning()) {
            container.start();
            System.out.println("MANUAL_START_CALLED");
        }
    }
}
```

Here profile `manual-demo` **intentionally triggers start when `ApplicationReadyEvent` fires**. `ApplicationReadyEvent` only indicates Spring Boot startup reached the ready milestone; it **does not prove** databases, remote services, or brokers satisfy business dependency readiness. If production needs a real condition like migration completion or downstream health checks, verify that condition **before `container.start()`**, or withhold the profile/start command until verified.

Calling `container.start()` creates and launches consumer tasks, yet a successful call does not prove the broker is ready to deliver/dispatch at that instant. `isRunning()` is a **lifecycle state**, not a metric saying queue lag is zero or consumers finished processing.

### 6.7. Test Producer

File `src/main/java/demo/lifecycle/PublishDemoRunner.java`:

```java
package demo.lifecycle;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@Component
@Profile("publish-demo")
public class PublishDemoRunner implements ApplicationRunner {

    private final JmsTemplate template;
    private final String destination;

    public PublishDemoRunner(
            JmsTemplate template,
            @Value("${app.jms.queue}") String destination) {
        this.template = template;
        this.destination = destination;
    }

    @Override
    public void run(ApplicationArguments args) {
        template.convertAndSend(
                destination, "OrderCreated:ORDER-1001");
        System.out.println("PUBLISH_FINISHED");
    }
}
```

Profile `publish-demo` sends **one message on startup**. Because the example defaults to `auto-start=false` and omits `manual-demo`, this sending process **does not consume** its own message. The broker must have the queue and accept messages; this makes no assumption about whether consumers run in another process.

### 6.8. Running and Observing

Set broker `JMS_USER` and `JMS_PASSWORD` in the environment, then use the project's Gradle wrapper (or generate a wrapper with compatible Gradle):

```bash
# 1. Send message without explicitly starting the listener in this process.
./gradlew bootRun --args='--spring.profiles.active=publish-demo'

# 2. Stop the test process above, then run a process with the manual-demo profile.
./gradlew bootRun --args='--spring.profiles.active=manual-demo'
```

On Windows use `gradlew.bat` instead of `./gradlew`. The example can also run from an IDE with the matching profile, JDK, broker, and credentials.

If broker/queue connectivity is healthy, the publish process may print:

```text
PUBLISH_FINISHED
```

The `manual-demo` process may print:

```text
MANUAL_START_CALLED
RECEIVED OrderCreated:ORDER-1001
```

These are merely **lines the application may print**; Spring Boot also logs other startup messages, and broker connectivity and async processing have no strict schedule. The two lines in `manual-demo` are not an ordering guarantee across all brokers/versions; the listener thread may execute almost immediately after `start()`, printing `RECEIVED` before `MANUAL_START_CALLED`. If another consumer took the message from the queue, you may see only `MANUAL_START_CALLED`. If the broker is unavailable, the container may sit in connection retry state.

**Never use `publish-demo` and `manual-demo` profiles in production** unless you want every startup to emit test data or auto-enable receiving uncontrollably.

## 7. Additional Example: SmartLifecycle Prerequisite at Phase 0

To demonstrate phases between the listener registry and another lifecycle component, add a bean active only under profile `phase-demo`.

File `src/main/java/demo/lifecycle/PrerequisiteLifecycle.java`:

```java
package demo.lifecycle;

import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("phase-demo")
public class PrerequisiteLifecycle implements SmartLifecycle {
    private volatile boolean running;

    @Override
    public void start() {
        // Demo: phase 0 simulates that the prerequisite has started.
        // Production must check real readiness before returning.
        System.out.println("PREREQUISITE_START phase=0");
        running = true;
    }

    @Override
    public void stop() {
        System.out.println("PREREQUISITE_STOP phase=0");
        running = false;
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return 0;
    }
}
```

`SmartLifecycle.stop(Runnable)` has a default implementation that calls `stop()` and notifies the callback; for real services with async shutdown, implement `stop(Runnable)` properly so the lifecycle processor waits until shutdown completes. Never forget to invoke the callback on completion.

To run the phase scenario, you must **actually enable auto-start**, unlike the manual scenario:

```bash
JMS_AUTO_START=true ./gradlew bootRun --args='--spring.profiles.active=phase-demo'
```

This shell command uses Unix syntax. In PowerShell, set the environment variable first with `$env:JMS_AUTO_START="true"` and run `gradlew.bat`; Windows does not support inline prefix variable assignment like Bash.

On context startup, the lifecycle processor asks `PrerequisiteLifecycle` (phase 0) to start before the phase 100 listener group. On normal context shutdown, the phase 100 listener group is asked to stop before `PrerequisiteLifecycle` (phase 0) stops. There is no assumption that stdout across JMS threads always follows a fixed order while the broker delivers messages.

**Decisive condition:** if a dependency starts asynchronously and its `start()` returns before the dependency is truly ready, phase 0 still finishes before real readiness. In that case phase 100 does **not** automatically wait for health checks; a dedicated readiness gate is needed.

### 7.1. What to Ask When Choosing a Phase

Examples:

- "Must the listener start only after reference cache loading finishes?" → load/validate the cache in a lower-phase component, then start listeners at a higher phase, or manually start after readiness.
- "Must the listener stop before the database pool closes?" → give the listener a higher phase than the lifecycle component managing the dependency (while verifying the actual bean's shutdown mechanism).
- "Must Listener A start before Listener B while both use the same `@JmsListener` registry?" → do not assign two conflicting custom phases arbitrarily; the registry enforces group-phase constraints. Use explicit ID-based orchestration or separate architectural lifecycles.
- "Do you just want to wait 10 seconds before opening consumers?" → `phase` does **not** provide time delays; use an explicit gating condition/scheduler, not phase 10.

## 8. Managing a Specific Listener with JmsListenerEndpointRegistry

`JmsListenerEndpointRegistry` manages listener containers created by `@JmsListener`. When an endpoint has a fixed `id`, you can retrieve its exact container to control it.

Example **internal service class** (not an HTTP endpoint):

```java
package demo.lifecycle;

import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
public class OrdersConsumerControl {

    private final JmsListenerEndpointRegistry registry;

    public OrdersConsumerControl(JmsListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    private MessageListenerContainer getContainer() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersWorker");
        if (container == null) {
            throw new IllegalStateException(
                    "Listener ordersWorker does not exist");
        }
        return container;
    }

    public void start() {
        getContainer().start();
    }

    public void stop() {
        getContainer().stop();
    }

    public boolean isRunning() {
        return getContainer().isRunning();
    }

    public int phase() {
        return getContainer().getPhase();
    }

    public boolean isAutoStartup() {
        return getContainer().isAutoStartup();
    }
}
```

These `start/stop` methods are invoked when a **protected, authenticated, authorized operator flow** decides to toggle the consumer; never expose them directly as unguarded public HTTP APIs.

- Call `getListenerContainer("ordersWorker")` to avoid affecting other endpoints.
- Calling `registry.start()` issues a **start command to all containers managed by the registry**, not just `ordersWorker`. After context refresh, an explicit start can start even containers with `autoStartup=false`.
- Calling `registry.stop()` likewise affects multiple containers.
- `isRunning() == true` is merely lifecycle state at read time; it does not imply messages are in flight, the broker connection is healthy, or backlog is zero.
- `container.start()`/`stop()` can be called at runtime, yet never spam commands across threads/operators since in-flight handling and final state become hard to control.

### 8.1. Re-Enabling After Stopping

The flow may look like:

```text
Registered, autoStartup=false
       |
  operator.start()
       v
    Running ---- operator.stop() ----> Stopped
       ^                                  |
       |------------ operator.start() ----|
```

This is an application-level lifecycle diagram. The container may have to reconnect to the broker and recreate consumers when restarted; stopping does not delete the queue or unprocessed messages. Messages can remain on the broker for subsequent processing depending on delivery/expiration/transaction/provider policies.

### 8.2. When Listeners Are Registered Dynamically After Context Refresh

`autoStartup` primarily governs **automatic startup during context refresh**. For endpoints registered dynamically after context refresh, start behavior also depends on how `JmsListenerEndpointRegistry.registerListenerContainer(...)` is invoked and its start-immediately flag; implementations may intentionally start immediately per the lifecycle contract. Therefore, test **dynamic registration** on your exact Spring version instead of assuming `autoStartup=false` keeps every late-registered container idle.

The example in this lesson uses annotated endpoints discovered at normal startup and does not demonstrate dynamic registration.

## 9. Shutdown: Stopping Intake Differs from Completing All Running Tasks

On a shutdown signal, Spring's lifecycle processor invokes `stop(Runnable)` on `SmartLifecycle` beans in **descending phase order**. With listeners at phase 100 and prerequisites at phase 0, listeners are asked to stop first, and dependencies stop afterward.

Still, distinguish:

1. **Stopping new message intake:** the listener container stops initiating further receives within its own scope.
2. **Processing in-flight messages:** consumer tasks may still be executing business logic.
3. **JMS ACK/commit/rollback:** transactions may not have finished yet; if they fail, messages can be redelivered.
4. **Cleaning up JMS resources:** sessions/consumers/connections close per provider lifecycle.
5. **Stopping dependencies:** database pools or external resources should not be torn down before handlers using them finish, within the shutdown policy.

Thus, **phase is stop-call order**, not magic guaranteeing every in-flight message committed before anything else closes. Configure and test shutdown timeouts/cancellation appropriately.

Property example:

```yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
```

In Spring Boot 3.4, this property sets the timeout for each shutdown phase. Twenty seconds is an illustrative choice, not a promise that a 60-second handler completes in 20 seconds. Once the timeout expires, the lifecycle processor can proceed to the next phase even if a component has not stopped cleanly.

### 9.1. What Happens to Unfinished Messages?

Depends on configuration:

- **Local JMS transaction:** an uncommitted in-flight message can roll back/redeliver if the connection/session closes or fails at the processing boundary.
- **Non-transacted `AUTO_ACKNOWLEDGE`:** depending on container/provider, ACK may occur **before** the listener body runs, so exceptions or shutdown may not trigger redelivery as expected.
- **Business database transaction:** a DB transaction may have committed while the JMS transaction did not; redelivery causes duplicates without idempotency.
- **Other consumers on the queue:** as soon as this listener stops, consumers in other JVMs continue consuming; stopping one endpoint does not "close the queue".

At minimum, design:

- Handlers with timeouts and idempotency mechanisms.
- Explicit transaction/ack modes, defined retries, and DLQs.
- A shutdown period long enough for typical workloads, plus a plan for timeout overruns.
- Metrics for in-flight work, queue age, redeliveries, and DLQs.
- Restart scenarios after process kills and broker reconnects.
- Never use `System.exit(0)` as a way to "gracefully stop listeners".

### 9.2. Order Within the Same Phase Is Not Fixed

If two components share phase 100:

```text
phase=100: component A, component B
START: do not require A to always start before B
STOP:  do not require B to always stop before A
```

Spring can process lifecycle components in the same phase without guaranteeing a stable order. Pick **distinct phases for valid lifecycle groups** or real dependency relationships, rather than relying on bean registration order, method names, classpath order, or log order.

For **endpoints sharing a `JmsListenerEndpointRegistry`**, do not try to bypass group-phase limits by building conflicting-phase factories; use explicit startup control or separate structures when ordering is truly required.

## 10. Real-World Operational Scenarios

### Scenario A — Enabling Consumers Only After Migration

1. Deploy code with listener factory `autoStartup=false`.
2. Application builds Spring context and registers the listener, yet that consumer does not receive messages.
3. Run migrations or verify schema versions, access policies, and dependency readiness.
4. Once conditions **are genuinely satisfied**, an operator/initializer calls `getListenerContainer(id).start()`.
5. Monitor connections, consumer counts, backlogs, and handler errors; roll back if issues arise.

Do not use `ApplicationReadyEvent` as automatic proof that external migrations outside Spring have completed.

### Scenario B — Blue/Green Cutover

1. Blue is consuming the queue; green deploys with `autoStartup=false`.
2. Verify green connectivity/configuration using probes that do not disrupt production consumption.
3. Stop blue's listener and inspect in-flight work/transactions per policy.
4. Start green and watch backlog/redeliveries/DLQ.
5. Keep eventId/idempotency because cutovers can still see duplicates or uncertain outcomes.

Do not assume stopping one endpoint stops all blue consumers across all replicas. Coordinate per instance or via service-level orchestration.

### Scenario C — Ordered Shutdown When a Listener Depends on a Cache

A `SmartLifecycle` component managing the cache has phase `0`; the listener group has phase `100`. On startup, the cache starts first and listeners start after. On shutdown, listeners stop first and the cache stops after.

If cache startup is actually async, ensure the cache marks itself ready only after loading finishes and uses a verification/gating mechanism. Setting `phase` alone does not replace readiness checks.

### Scenario D — Pausing Processing Due to Downstream Overload

You can call `container.stop()` on the specific endpoint, lower concurrency, or apply other backpressure policies. Once downstream recovers, call `start()`. Never do tight stop/start loops every second; each cycle creates/closes consumers and triggers redeliveries.

If a large backlog built up, restarting abruptly across many replicas can cause a "thundering herd". Budget concurrency and downstream limits.

## 11. Testing Lifecycle: Do Not Just Read Logs

### 11.1. Unit-Level Check of the Phase Rule

`PhaseOrderDemo` in section 5 showed standalone Java 17 output, yet that test **does not test Spring**. For Spring apps, verify registry/container states directly.

### 11.2. Integration Tests Require a Context and Compatible JMS Provider

Test against a test broker (embedded or compatible Testcontainers/Artemis setup), using endpoint ID `ordersWorker` and `auto-start=false`:

| Step | Check | Expected Conclusion |
| --- | --- | --- |
| Context initialized | `registry.getListenerContainer("ordersWorker") != null` | Endpoint is registered |
| Before `start()` | `container.isAutoStartup() == false`; `!container.isRunning()` | Container does not auto-start in normal flow |
| Send a message | Handler does not run within bounded observation window, and queue retains message if no other consumer exists | Container is not consuming yet |
| Call `container.start()` | `isRunning()` flips; handler then receives message once broker is ready | Manual start works |
| Call `container.stop()` | After stop settles, no new messages arrive via that container | Manual stop works |
| Restart | `container.start()` resumes receiving | Runtime restart works |
| Context shutdown | Higher-phase component stops before lower-phase component per tracer/lifecycle callbacks | Phase ordering matches configuration |
| Handler running during stop | Record in-flight state, transaction outcome, and redelivery | Never equate "stop" with commit |
| Broker down before start | Container may retry/recover per policy; `isRunning` does not prove broker ready | Lifecycle state differs from broker health |

Do not rely solely on `println` order across threads. Use `CountDownLatch`, registry state, broker queue metrics, and bounded timeouts. For phase ordering, use test lifecycle components with thread-safe recorders rather than treating message processing order as proof of bean start order.

### 11.3. Sample Spring Context Configuration Test (Outline)

In an integration test booting a context with `app.jms.auto-start=false` and proper JMS infrastructure:

```java
@Autowired
JmsListenerEndpointRegistry registry;

@Test
void endpointIsRegisteredButNotStarted() {
    MessageListenerContainer container =
            registry.getListenerContainer("ordersWorker");

    assertNotNull(container);
    assertFalse(container.isAutoStartup());
    assertFalse(container.isRunning());
    assertEquals(100, container.getPhase());
}
```

This is an **outline of fields/methods inside a JUnit/Spring test class**, not a standalone Java file. Requires importing `@Autowired`, `@Test`, `MessageListenerContainer`, `JmsListenerEndpointRegistry`, and JUnit Jupiter assertions. The `!isRunning()` result holds only if the test **does not enable** the manual controller profile or call start elsewhere; in parallel integration test suites, isolate Spring contexts and endpoint registries.

Specifically, this test does not check whether the broker delivered messages or local transactions rolled back. Configuration API verification must be paired with integration tests against a real broker.

## 12. Troubleshooting

| Symptom | Causes Worth Checking | Resolution |
| --- | --- | --- |
| `@JmsListener` annotated yet receives nothing after boot | `autoStartup=false` on factory/default property; container not started | Query registry ID, `isAutoStartup`, `isRunning`; call start when permitted |
| Tried writing `autoStartup`/`phase` directly on `@JmsListener` | Copied from another mechanism like Kafka | Put them on `JmsListenerContainerFactory`/container |
| Changed `spring.jms.listener.auto-startup` yet endpoint unchanged | App uses custom factory without Boot default configurer | Configure custom factory directly or use Boot configurer |
| Factory A phase 10, Factory B phase 20 fails startup | JMS registry may require consistent custom phases | Use one registry/group phase; coordinate endpoints by ID |
| High phase yet listener receives before dependency is ready | Dependency `start()` returned early while async task wasn't ready | Real readiness gate, manual start after health/migration |
| Called `registry.start()` and many listeners turned on together | Registry manages all endpoints | Use `getListenerContainer(id).start()` to start just one |
| `container.start()` returned, no messages arrive | Broker offline, wrong queue, selector, ACL, connection retry, empty queue | Check broker health, container logs, metrics, destination |
| `container.isRunning() == true` yet huge lag | Running does not mean fast enough processing | Inspect queue age, throughput, consumer count, errors |
| Called `stop()` yet processing logs keep appearing | In-flight work/threads finishing or another replica consuming | Inspect shutdown drain, transactions, all instances |
| Listener stopped after DB already shut down | Wrong phase or dependency not participating in lifecycle as expected | Verify actual lifecycle beans/phases and dependency links |
| Used phase 100 to "wait 100 seconds" | Phase is ordering, not duration | Use scheduler/gating on real conditions |
| Frequent stop/start causes duplicate events | Uncertain transaction outcome, retry/redelivery | Idempotency, eventId, appropriate retry/DLQ |
| Endpoint ID not found | Bean not scanned, factory error, wrong ID, wrong context | Check `@EnableJms`, component scan, registry IDs |
| No traffic on deploy while broker stays active | This instance's listener is stopped; messages wait or other consumers take them | Inspect system-wide state, not just one JVM |

## 13. Decision Rules

When designing a new `@JmsListener`, ask yourself:

1. **Should the consumer start receiving immediately at app startup?** If yes, keep `autoStartup=true` unless constrained; if no, set `false` and define explicitly who calls start.
2. **Are there lifecycle dependencies that must start before and stop after?** Use sensible phases between `SmartLifecycle` groups. Never assign arbitrary distinct phases to endpoints sharing the same registry.
3. **Are there readiness conditions outside the Spring context?** Use a health-check/gate or manual start; phase alone is insufficient.
4. **Do you need to pause one endpoint without affecting others?** Use the endpoint ID and `JmsListenerEndpointRegistry.getListenerContainer(id)`.
5. **How must shutdown preserve consistency?** Nail down JMS transaction/ack mode, in-flight policy, idempotency, drain/timeouts, retries, and DLQs.
6. **Running multiple instances on the same queue?** Coordinate per instance; a local `stop` call does not control all consumers.

**Remember:** `autoStartup` governs *whether it starts automatically*, `phase` governs *relative order across lifecycle groups when Spring starts/stops*, and `JmsListenerEndpointRegistry` enables *runtime toggling and observation*. These three mechanisms **do not** replace real readiness verification, properly designed graceful shutdown, or business message-processing guarantees.

### References

- Spring Framework 6.2 API — `JmsListener` (attribute list; no `autoStartup`/`phase`): https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/annotation/JmsListener.html
- Spring Framework 6.2 API — `DefaultJmsListenerContainerFactory` and `AbstractJmsListenerContainerFactory`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html
- Spring Framework 6.2 API — `AbstractJmsListeningContainer` (`setAutoStartup`, `setPhase`, `isRunning`): https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/AbstractJmsListeningContainer.html
- Spring Framework 6.2 API — `JmsListenerEndpointRegistry` (`getListenerContainer`, `start`, `stop`, and phase): https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistry.html
- Spring Framework 6.2 API — `SmartLifecycle` (lower phase starts first, higher phase stops first): https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Boot 3.4 — Common Application Properties (`spring.jms.listener.auto-startup` and `spring.lifecycle.timeout-per-shutdown-phase`): https://docs.spring.io/spring-boot/3.4/appendix/application-properties/index.html
- Spring Boot 3.4 — JMS auto-configuration and Artemis: https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html
- Spring Framework source — `JmsListenerEndpointRegistry` (registry group phase and start-if-necessary): https://github.com/spring-projects/spring-framework/blob/main/spring-jms/src/main/java/org/springframework/jms/config/JmsListenerEndpointRegistry.java
