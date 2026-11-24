# JmsListenerEndpointRegistry for Finding and Managing Containers in Spring JMS

**Parent topic:** `@JmsListener` — Spring Framework / JMS.

**Goal:** Know how to use `JmsListenerEndpointRegistry` to **list registered JMS listener endpoints, find the exact `MessageListenerContainer` by ID, inspect status, pause/restart a single listener or the entire group, and register endpoints programmatically when needed**. Understand the boundaries between *Spring bean*, *listener endpoint*, *listener container*, *destination*, and *JMS broker*, so operational actions never drop processing or stop the wrong consumer.

**Environment and how to read the code:** Java 17+, Spring Framework 6.x / Spring Boot 3.x with Jakarta Messaging (`jakarta.jms`). The integration example uses Spring Boot 3.5.0 and an Apache ActiveMQ Artemis **broker running outside the application**; this does not claim to be the newest Spring Boot release. The APIs illustrated below exist in Spring Framework 6.2.x; re-verify when upgrading major versions.

> **Most important takeaway:** `MessageListenerContainer` instances created by `@JmsListener` infrastructure **are usually not registered as individual beans in `ApplicationContext`**. To find or control them, inject the **`JmsListenerEndpointRegistry`** bean and call `getListenerContainer(id)`. The management ID is neither the queue name nor the `JmsListenerContainerFactory` name.

## 1. Why Does an Application Need a Registry?

Normally, business code only has:

~~~java
@Component
class InvoiceConsumer {

    @JmsListener(
            id = "invoiceCommands",
            destination = "invoice.commands")
    public void handle(String command) {
        System.out.println("Received: " + command);
    }
}
~~~

**This is a snippet** inside a Spring JMS project importing `org.springframework.stereotype.Component` and `org.springframework.jms.annotation.JmsListener`. Questions arise after deployment: *Which listeners are running? Can we pause only the invoice listener? How do we know Spring discovered the annotation?*

Spring builds the infrastructure in a chain:

~~~text
ApplicationContext
   ├─ InvoiceConsumer bean
   │     └─ @JmsListener(id="invoiceCommands", destination="invoice.commands")
   │
   ├─ JmsListenerContainerFactory bean
   │     └─ creates container with transaction/connection/concurrency settings
   │
   └─ JmsListenerEndpointRegistry bean
         └─ registry["invoiceCommands"]
               └─ MessageListenerContainer instance
                     ├─ JMS Connection / Session / MessageConsumer
                     ├─ consumer threads / listener lifecycle
                     └─ callback → InvoiceConsumer.handle(...)
                                        │
                                        ▼
                                  JMS broker/queue
~~~

The container is the runtime listener unit: it manages receiving messages, threading, resources, recovery, and transactions/ACK. The registry holds the **catalog of containers created for endpoints** and coordinates lifecycle. The registry **does not store message contents** and **does not replace broker management APIs**.

Sometimes you may manually declare a `DefaultMessageListenerContainer` as a `@Bean`. Such a manual bean **does not automatically appear in the registry** just because it shares the same type. Keep this distinction in mind when listing listeners.

## 2. Distinguishing Five Easily Confused Terms

| Term | Example | Function |
| --- | --- | --- |
| **Listener bean** | `InvoiceConsumer` | Spring object containing the business method |
| **Endpoint ID** | `invoiceCommands` | Identifier key for an endpoint/container in the registry |
| **Destination** | `invoice.commands` | Queue/topic name where the container creates a JMS consumer |
| **Container factory** | `jmsListenerContainerFactory` | Configuration bean used to **create** containers |
| **Listener container** | `DefaultMessageListenerContainer` | Live runtime instance with start/stop and JMS resources |

Full annotation attribute example:

~~~java
@JmsListener(
        id = "invoiceCommands",
        destination = "invoice.commands",
        containerFactory = "criticalJmsFactory",
        selector = "eventType = 'CreateInvoice'")
public void handleInvoice(String payload) {
    // Process payload after the listener has been dispatched by the container.
}
~~~

In the snippet above:
- `id` is the key used for `registry.getListenerContainer("invoiceCommands")`.
- `destination` is the queue/topic name, **not** the key for `getListenerContainer(...)`.
- `containerFactory` points to the factory bean named `criticalJmsFactory`, not a container instance.
- `selector` is a JMS filter expression over headers/properties; it does not parse JSON bodies automatically.

If you only write `@JmsListener(destination = "invoice.commands")` and omit `id`, the framework can **auto-generate an endpoint ID**. You can still list IDs, yet never rely on generated IDs for stable monitoring and operations across rebuilds. **Assign a unique, intentional ID** whenever precise endpoint control is needed.

## 3. Where the Registry Lives in Spring

`JmsListenerEndpointRegistry` resides in package:

~~~java
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.listener.MessageListenerContainer;
~~~

For Spring to register the registry and annotation-based endpoints:

- **Plain Spring Framework:** enable `@EnableJms` on a `@Configuration`, with a `ConnectionFactory` and suitable `JmsListenerContainerFactory` bean.
- **Spring Boot 3.x:** with `spring-boot-starter-artemis` or a compatible JMS provider starter/client, Boot can auto-configure listener infrastructure when conditions match; explicitly writing `@EnableJms` is usually unnecessary.
- The listener class must be managed by Spring: `@Component`/`@Bean`/matching component scan. An object created via `new` outside the container will not be discovered as an annotated endpoint.

**Injection distinction:** the registry is a **Spring bean**, so it can be constructor-injected; `MessageListenerContainer` instances created by the registry **are not necessarily beans**, so `@Autowired MessageListenerContainer` usually fails to resolve a specific endpoint. This is Spring Framework's intended design; querying the registry by ID is the supported path.

### 3.1. Minimal Plain Spring Configuration

~~~java
package example.jms;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
public class JmsListenerConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1-3");
        return factory;
    }
}
~~~

This class compiles when Spring 6.x/Jakarta JMS dependencies and a `ConnectionFactory` bean exist. It does not run standalone because it still needs an application starting `ApplicationContext` and a real broker. The default factory is named `jmsListenerContainerFactory`; for listeners omitting `containerFactory`, Spring looks up that default factory. Once endpoints are discovered, the registry manages containers built from the factory.

## 4. Actual API of JmsListenerEndpointRegistry

Key methods in Spring Framework 6.2.x:

| API | Result / meaning |
| --- | --- |
| `getListenerContainerIds()` | `Set<String>` of **endpoint IDs** managed by the registry |
| `getListenerContainer(String id)` | `MessageListenerContainer` for the ID, or **`null`** if not found |
| `getListenerContainers()` | `Collection<MessageListenerContainer>` of containers managed by the registry |
| `isRunning()` | Registry lifecycle state, **true if at least one container is running** |
| `start()` | Sends start command to containers per lifecycle |
| `stop()` | Stops containers managed by the registry |
| `stop(Runnable callback)` | Stops with a lifecycle callback supported by Spring |
| `getPhase()` | Lifecycle phase used to coordinate startup/shutdown |
| `registerListenerContainer(endpoint, factory)` | Creates and registers a container for the supplied endpoint |
| `registerListenerContainer(endpoint, factory, startImmediately)` | Same as above, plus whether to request immediate start |

**There are NO `getAllListenerContainers()` or `unregisterListenerContainer(String)` methods in `JmsListenerEndpointRegistry` in Spring Framework 6.2.x.** Those two names are easily copied by mistake from **Spring AMQP/Rabbit** or another version's API. Check the **JMS** package and Javadoc instead of assuming all registries match.

Returned collections are for observation and management, **not mutable lists for the app to remove containers**. Never attempt to mutate `getListenerContainerIds()`/`getListenerContainers()` to "remove a listener" from the registry; that is not a supported registration/unregistration operation.

## 5. Listing Endpoint IDs in a Running Application

Reusable Spring service pattern:

~~~java
package example.jms;

import java.util.Set;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.stereotype.Service;

@Service
public class JmsEndpointCatalog {

    private final JmsListenerEndpointRegistry registry;

    public JmsEndpointCatalog(JmsListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public Set<String> endpointIds() {
        return Set.copyOf(registry.getListenerContainerIds());
    }

    public int endpointCount() {
        return registry.getListenerContainerIds().size();
    }
}
~~~

**Benefit:** retrieves the endpoint list at runtime instead of hardcoding everything in dashboards. `Set.copyOf` takes a snapshot so callers do not depend on the live collection returned by the registry. **Do not assume Set order reflects registration order or business priority**; for deterministic display, sort with `Comparator.naturalOrder()` or a `TreeSet`.

If the registry has no endpoints yet, the ID list can be empty. That can be a valid state when an app intentionally disables listeners or has not registered endpoints yet—not proof of a lost broker connection.

### 5.1. Logging at Application Startup

~~~java
@Bean
ApplicationRunner logJmsEndpoints(JmsListenerEndpointRegistry registry) {
    return args -> registry.getListenerContainerIds().stream()
            .sorted()
            .forEach(id -> {
                MessageListenerContainer c =
                        registry.getListenerContainer(id);
                System.out.printf(
                        "JMS_ENDPOINT id=%s registered=%s running=%s%n",
                        id, c != null, c != null && c.isRunning());
            });
}
~~~

This snippet lives in a `@Configuration`/`@SpringBootApplication` class importing `@Bean`, `ApplicationRunner`, `JmsListenerEndpointRegistry`, and `MessageListenerContainer`. It **does not guarantee** the broker is reachable at log time. A container may still be starting or recovering while `isRunning()` returns true.

## 6. Finding a Container by ID and Checking Null

This is the core operation of this lesson:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("invoiceCommands");

if (container == null) {
    throw new IllegalArgumentException(
            "Unknown JMS listener id: invoiceCommands");
}

System.out.println("listener running = " + container.isRunning());
~~~

`getListenerContainer(...)` **returns `null`** when the key is missing; it does not throw a "bean not found" exception. Never call `container.stop()` before checking null. If null, diagnose in order:

1. Is `@JmsListener(id="invoiceCommands")` inside a Spring bean class?
2. Is that package component-scanned?
3. Is listener annotation infrastructure enabled?
4. Does the ID match exact casing, whitespace, and resolved property placeholder value?
5. Did a duplicate ID cause endpoint registration to fail at startup?
6. Are you querying the wrong registry/`ApplicationContext` in a multi-context test setup?

### 6.1. Do Not Look Up Containers by Destination Name

~~~java
// RIGHT: exact id as in @JmsListener(id = "invoiceCommands").
registry.getListenerContainer("invoiceCommands");

// USUALLY WRONG: this is the destination, not the registered ID.
registry.getListenerContainer("invoice.commands");
~~~

An accidental match occurs only if you **deliberately set the ID equal to the destination name**; that is not an automatic Spring rule.

## 7. Calling start() and stop() on a Specific Listener

`MessageListenerContainer` is the common abstraction exposing lifecycle methods:

~~~java
MessageListenerContainer listener =
        registry.getListenerContainer("invoiceCommands");

if (listener == null) {
    throw new IllegalArgumentException("Listener does not exist");
}

listener.stop();            // Stop only this endpoint
boolean afterStop = listener.isRunning();

listener.start();           // Restart that same endpoint
boolean afterStart = listener.isRunning();
~~~

**Impact boundary:** calling `listener.stop()` does not delete the broker queue, remove the `@JmsListener` bean, or remove the registration from the registry. When a queue has appropriate persistence/retention, messages can remain on the broker while the endpoint is stopped and be consumed after restarting. However, **non-durable topic subscriptions behave differently**, and messages may be missed while the subscription is inactive.

**Regarding in-flight messages:** the container may be processing a message when `stop()` is called. How long it waits for the handler, or whether it rolls back or commits, depends on container implementation, transaction mode, broker, and grace period. Never assume `stop()` means all messages finished business transactions, nor call stop to immediately abort a payment mid-execution.

### 7.1. start() Does Not Mean the Broker Is Ready

`isRunning()==true` generally reflects that the container has started in lifecycle terms. A `DefaultMessageListenerContainer` could still be trying to reconnect to an unreachable broker. To conclude "consumer ready", monitor connection/authentication, broker-side consumer counts, destination permissions, and message handling metrics.

### 7.2. What If stop() Is Called Again While Already Stopped?

Lifecycle methods are designed to behave sensibly when already in that state; however, never treat them as **atomic transactional APIs** across concurrent callers. If multiple admin requests issue stop/start concurrently, races or confusing states can occur. Use an orchestrating service with authorization and serialization for operational actions.

## 8. Stopping or Starting the Entire Registry

~~~java
registry.stop();      // Stop all listener containers managed by the registry.
registry.start();     // Restart the group per lifecycle.
~~~

This is a broad operation, **different from** `registry.getListenerContainer("invoiceCommands").stop()`:

| Intent | Call |
| --- | --- |
| Pause only the invoice consumer | Fetch by exact ID then call `stop()` |
| Restart the invoice consumer | Fetch by exact ID then call `start()` |
| Stop all endpoints managed by the registry | `registry.stop()` |
| Start all endpoints managed by the registry | `registry.start()` |

`registry.stop(Runnable callback)` integrates with Spring's `SmartLifecycle` cycle, where the callback fires after listener containers report stop completion. This is not a way to synchronize "all invoices committed"; it is a callback for **lifecycle stop**, distinct from business completion.

**Never use `registry.stop()` as a "pause the entire message broker" command.** It affects only listener containers belonging to the registry **in the current ApplicationContext/process**. Other service instances, other apps, or manually created consumers continue taking messages normally.

### 8.1. Special Note on registry.isRunning()

In Spring Framework 6.2.x, `JmsListenerEndpointRegistry.isRunning()` returns **true when at least one running container is found**. Therefore:

~~~java
boolean anyRunning = registry.isRunning();
~~~

**Never interpret** `anyRunning=true` as "all endpoints are healthy". If an app has 10 listeners and only 1 is running, the registry still returns true. Conversely, to check whether all endpoints have started, inspect **each container individually**:

~~~java
boolean allRegisteredRunning =
        !registry.getListenerContainerIds().isEmpty()
        && registry.getListenerContainerIds().stream()
            .map(registry::getListenerContainer)
            .allMatch(c -> c != null && c.isRunning());
~~~

This code computes **lifecycle running state of registered endpoints**, **not broker readiness**. When there are no endpoints, it intentionally returns false so "allMatch on an empty set" is not treated as a false healthy state.

## 9. Spring Boot 3.x: Complete Demo to Find, Stop, and Restart

The goal of this example is **observing the difference between container lifecycle and broker queues**. A `@JmsListener` has a known ID, and an `ApplicationRunner` looks up the container, stops it, publishes a message to a test queue, and then starts it again. This is purely a learning demo—**never call stop/start on production queues** just to debug logs.

### 9.1. Dependencies and Versions

`build.gradle` using Java 17 and Spring Boot 3.5.0:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-endpoint-registry'
~~~

### 9.2. application.yaml

File `src/main/resources/application.yaml`:

~~~yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: demo
  jms:
    pub-sub-domain: false
    listener:
      auto-startup: true
      min-concurrency: 1
      max-concurrency: 1
~~~

**Prerequisites:** an Artemis broker running at the URL, queue `demo.registry.jobs` (or auto-create enabled), and account `demo` with consume/send permissions. Supply the password via environment variable `SPRING_ARTEMIS_PASSWORD` or a secret store; never commit credentials to Git. The properties above configure the auto-configured listener factory when Boot conditions match.

### 9.3. Complete Single Java File

`src/main/java/example/jmsregistry/RegistryApplication.java`:

~~~java
package example.jmsregistry;

import java.util.Set;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class RegistryApplication {

    public static void main(String[] args) {
        SpringApplication.run(RegistryApplication.class, args);
    }

    @Bean
    ApplicationRunner demonstrateRegistry(
            JmsListenerEndpointRegistry registry,
            JmsTemplate jmsTemplate) {

        return args -> {
            Set<String> ids = Set.copyOf(
                    registry.getListenerContainerIds());
            System.out.println("REGISTERED_IDS=" + ids);

            MessageListenerContainer listener =
                    registry.getListenerContainer("jobsDemo");

            if (listener == null) {
                throw new IllegalStateException(
                        "Listener jobsDemo was not registered");
            }

            System.out.println(
                    "INITIAL_RUNNING=" + listener.isRunning());

            listener.stop();
            System.out.println(
                    "RUNNING_AFTER_STOP=" + listener.isRunning());

            // Test queue: no other consumer competes for messages.
            jmsTemplate.convertAndSend(
                    "demo.registry.jobs", "job-created-42");
            System.out.println("SEND_WHILE_STOPPED_RETURNED");

            listener.start();
            System.out.println(
                    "RUNNING_AFTER_START=" + listener.isRunning());
        };
    }
}

@Component
class DemoJobListener {

    @JmsListener(
            id = "jobsDemo",
            destination = "demo.registry.jobs")
    public void handle(String payload) {
        System.out.println("HANDLER_THREAD="
                + Thread.currentThread().getName()
                + " PAYLOAD=" + payload);
    }
}
~~~

**Why this example proves the point:** `jobsDemo` is the annotation ID looked up by the registry; `demo.registry.jobs` is the destination the producer sends to; `MessageListenerContainer` is the object with `stop/start/isRunning`. The `ApplicationRunner` thread does not become the consumer thread. The broker queue (holding the message) is consumed by the listener once restarted.

**There is no injecting `DemoJobListener` and calling `handle(...)` to emulate stop/start.** Calling the handler directly only invokes a Java method without JMS receive/ACK; you must control the container.

### 9.4. Running and Interpreting Output

After setting up the broker and Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

The main lines **may** include:

~~~text
REGISTERED_IDS=[jobsDemo]
INITIAL_RUNNING=true
RUNNING_AFTER_STOP=false
SEND_WHILE_STOPPED_RETURNED
RUNNING_AFTER_START=true
HANDLER_THREAD=... PAYLOAD=job-created-42
~~~

**Do not treat this as fixed stdout:** the `HANDLER_THREAD` line can interleave as soon as `listener.start()` is called; once started, the listener may execute **before** `RUNNING_AFTER_START` prints. If the broker fails or auth is wrong, send may throw an exception and the listener may be recovering; if other consumers or old messages exist on the queue, received data differs. `Set<String>` guarantees no print order across multiple IDs. A broker-persisted queue holds messages while the listener is stopped within TTL/retention limits, whereas topic policies may differ.

**The demo does not prove business success:** the handler only prints a string, uses no DB, and has no idempotency or outbox. Every startup sends a message, so never copy this `ApplicationRunner` into a production application.

## 10. Are Endpoints Registered from @JmsListener Spring Beans?

Spring Framework states clearly: containers created for annotated endpoints are managed **inside the registry**, **not registered individually as beans for automatic autowiring**. Therefore:

~~~java
// Do not expect the endpoint container to have bean name "jobsDemo"
// in ApplicationContext merely because of @JmsListener(id = "jobsDemo").

// Reliable approach:
MessageListenerContainer listener =
        registry.getListenerContainer("jobsDemo");
~~~

Distinguish three objects:
- `JmsListenerEndpointRegistry` **is a Spring bean**, injectable into controllers/services.
- `DefaultJmsListenerContainerFactory` **is a Spring factory bean**, holding configuration to build containers.
- `DefaultMessageListenerContainer` **instances created by the registry** are normally not standalone Spring beans.

**Exception:** if you manually declare a `DefaultMessageListenerContainer` bean, that bean can be autowired as a Spring bean. However, **do not assume it appears in the registry**; the registry is not a "scanner of every bean of type MessageListenerContainer".

## 11. Deeper Status and Observability

Generic `MessageListenerContainer` exposes `isRunning()` and lifecycle methods. If the actual container is a `DefaultMessageListenerContainer`, you can read additional metrics:

~~~java
MessageListenerContainer listener =
        registry.getListenerContainer("jobsDemo");

if (listener instanceof DefaultMessageListenerContainer dmlc) {
    int scheduled = dmlc.getScheduledConsumerCount();
    int active = dmlc.getActiveConsumerCount();

    System.out.println("SCHEDULED=" + scheduled);
    System.out.println("ACTIVE=" + active);
    System.out.println("RECOVERING=" + dmlc.isRecovering());
}
~~~

This snippet requires importing `org.springframework.jms.listener.DefaultMessageListenerContainer`. **Never cast blindly**, as Spring has multiple container implementations; e.g., a custom factory could create `SimpleMessageListenerContainer`.

- `scheduled`: number of consumer invoker tasks currently scheduled by the container.
- `active`: number of active consumer invokers internally in the container; **not the exact count of messages currently being processed at that instant**.
- `isRecovering()`: sign that the Default container is trying to recover JMS resources, not an end-to-end business metric.
- `isRunning()`: lifecycle status, **not proof** that broker connections, queues/selectors, and handlers are healthy.

If a system needs to know "are messages actually being processed?", add broker-side connected consumers, queue depth/oldest age, listener metrics, conversion/transaction error logs, and business DB outcomes.

### 11.1. Interpreting Real-World Scenarios

| `isRunning()` | Broker consumer count | Queue messages | Reasonable diagnosis |
| --- | --- | --- | --- |
| false | 0 for this endpoint | May grow | Container stopped in this JVM; do not treat as cluster-wide queue pause |
| true | 0, recovery logs | May grow | Lifecycle started yet no real consumer connected |
| true | > 0 | 0 | Consumer active, no backlog; unknown if business succeeded without app metrics |
| true | > 0 | High, oldest age rising | Likely slow consumer, downstream bottleneck, selector/routing issue, or low concurrency |
| true | > 0 | DLQ rising | Persistent message failures; inspect redelivery/rejection policies |
| false | Other consumers active | Deliveries continue | Other replicas/services are consuming; local stop does not stop the cluster |

**Never use `registry.isRunning()` as the sole health probe:** it only requires one endpoint running to be true, and running does not cover broker or business readiness.

## 12. A Single-Endpoint Management Service Is Safer Than Calling Registry Directly from Controllers

In production, encapsulate management logic in a service with an **allowlist**, authorization, audit logs, and race controls. The Java 17 service below operates only on a designated endpoint:

~~~java
package example.jmsregistry;

import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
public class JmsListenerControlService {

    private static final String MANAGED_ID = "jobsDemo";

    private final JmsListenerEndpointRegistry registry;

    public JmsListenerControlService(
            JmsListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public synchronized boolean stopLocalListener() {
        MessageListenerContainer container = requireContainer();
        if (container.isRunning()) {
            container.stop();
        }
        return container.isRunning();
    }

    public synchronized boolean startLocalListener() {
        MessageListenerContainer container = requireContainer();
        if (!container.isRunning()) {
            container.start();
        }
        return container.isRunning();
    }

    public synchronized boolean isLocalListenerRunning() {
        return requireContainer().isRunning();
    }

    private MessageListenerContainer requireContainer() {
        MessageListenerContainer container =
                registry.getListenerContainer(MANAGED_ID);
        if (container == null) {
            throw new IllegalStateException(
                    "Unknown JMS endpoint: " + MANAGED_ID);
        }
        return container;
    }
}
~~~

This is a valid Spring class if within component scan and a registry bean exists. `synchronized` only serializes calls **on the same service instance**; it **does not** coordinate across JVMs/replicas, replace security, or prevent lifecycle interference from elsewhere.

**Never expose an unauthenticated public HTTP endpoint** like `POST /jms/stop?listenerId=...`. An external user could halt all queue processing, causing an SLA outage. If an operational API is required, restrict IDs, enforce roles, add CSRF/authorization protections, write audit logs, set timeouts, and expose only on admin networks. For production changes, keep a runbook and verify impact on in-flight messages.

### 12.1. Stop Is a Local "Pause Intake"

A stopped listener stops accepting new messages. However:
- Other consumers on **the same queue** can still consume.
- The broker may continue storing incoming messages; queue backlog and TTL keep operating.
- Non-durable topic subscriptions while offline can **miss** messages.
- In-flight messages may still be committing or rolling back per transaction state.

To **truly pause across the entire cluster**, you need a control plane/orchestrator coordinating all instances, or broker administrative controls per policy; one JVM's registry cannot do that alone.

## 13. Startup Management and autoStartup

When the Spring context refreshes, the registry participates in lifecycle as a `SmartLifecycle` component. Each container can have `autoStartup` and `phase`:

~~~java
@Bean
DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory) {
    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setAutoStartup(false);
    factory.setSessionTransacted(true);
    return factory;
}
~~~

This is a Spring `@Configuration` snippet requiring imports `jakarta.jms.ConnectionFactory`, `org.springframework.context.annotation.Bean`, and `org.springframework.jms.config.DefaultJmsListenerContainerFactory`. With `setAutoStartup(false)`, listeners created by this factory **will not start automatically on context startup**; a service/operator can call `registry.getListenerContainer(id).start()` once dependencies/brokers are ready.

**Important:** `autoStartup=false` only governs **automatic startup**; it does not forbid calling `start()` manually. After context refresh, `registry.start()` may actively start containers in the registry, **including endpoints configured with autoStartup=false** in implementations like Spring 6.2.x. Hence never call `registry.start()` indiscriminately when you only intend to start one listener.

Boot can configure `spring.jms.listener.auto-startup=false` on the default listener factory (if the app has not replaced the factory). When creating multiple factories, auto-startup behavior can differ across endpoints; inspect each container instead of assuming from one global property.

### 13.1. Phase and Shutdown Ordering

`SmartLifecycle.getPhase()` indicates the relative phase for Spring to coordinate start/stop. Higher phases typically start later and stop earlier than lower phases in the standard lifecycle processor. Never tweak phases as a substitute for backend connectivity readiness; the broker can be unavailable even if beans start in order.

When the app stops on SIGTERM/Kubernetes, the lifecycle processor calls stop/destroy per Spring mechanics, yet grace periods are bounded. If a handler blocks too long in DB/HTTP calls, the orchestrator may kill the process before completion. Ensure idempotency, transaction timeouts, and proper recovery.

## 14. Programmatic Endpoint Registration: Registrar Before, Registry at Runtime

Not every listener uses annotations. Spring supports `JmsListenerEndpoint` and `JmsListenerConfigurer` for programmatic registration.

### 14.1. Static/Programmatic Configuration at Startup

~~~java
package example.jmsregistry;

import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListenerConfigurer;
import org.springframework.jms.config.JmsListenerEndpointRegistrar;
import org.springframework.jms.config.SimpleJmsListenerEndpoint;

@Configuration
@EnableJms
public class ExtraEndpointConfiguration
        implements JmsListenerConfigurer {

    @Override
    public void configureJmsListeners(
            JmsListenerEndpointRegistrar registrar) {

        var endpoint = new SimpleJmsListenerEndpoint();
        endpoint.setId("auditEvents");
        endpoint.setDestination("audit.events");
        endpoint.setMessageListener(message ->
                System.out.println("Received JMS audit event"));

        registrar.registerEndpoint(endpoint);
    }
}
~~~

This Spring Framework 6.x class compiles when JMS infrastructure, a default `JmsListenerContainerFactory`, and a valid broker/destination exist. Even without `@JmsListener` on an audit method, endpoint `auditEvents` is registered via the registrar, creates a container, and appears in the registry.

**Why use the registrar:** it performs registration during the initialization phase while Spring prepares endpoints, rather than manually creating/starting containers before context refresh.

### 14.2. Registering an Endpoint While the Application Is Running

If you genuinely need a listener created from runtime config, the registry exposes:

~~~java
SimpleJmsListenerEndpoint endpoint =
        new SimpleJmsListenerEndpoint();
endpoint.setId("dynamicAudit");
endpoint.setDestination("audit.dynamic");
endpoint.setMessageListener(message ->
        System.out.println("Dynamic audit event received"));

registry.registerListenerContainer(
        endpoint, listenerFactory, true);
~~~

This snippet requires:
- `registry` as an injected `JmsListenerEndpointRegistry`.
- `listenerFactory` as a configured `JmsListenerContainerFactory<?>` matching provider/destination/transactions.
- Invocation **after context refresh** if `startImmediately=true` is expected to take effect immediately.
- A unique ID not colliding with existing endpoints; duplicate IDs can throw `IllegalStateException`.
- Access control over who can trigger registration, since the new listener can open connections/sessions/consumers and consume messages right away.

You can inject the factory as follows:

~~~java
@Bean
ApplicationRunner registerDynamicAudit(
        JmsListenerEndpointRegistry registry,
        @Qualifier("jmsListenerContainerFactory")
        JmsListenerContainerFactory<?> listenerFactory) {

    return args -> {
        var endpoint = new SimpleJmsListenerEndpoint();
        endpoint.setId("dynamicAudit");
        endpoint.setDestination("audit.dynamic");
        endpoint.setMessageListener(message ->
                System.out.println("Received audit.dynamic"));
        registry.registerListenerContainer(
                endpoint, listenerFactory, true);
    };
}
~~~

This snippet lives in a `@Configuration` class importing `org.springframework.boot.ApplicationRunner`, `org.springframework.context.annotation.Bean`, `org.springframework.beans.factory.annotation.Qualifier`, `org.springframework.jms.config.JmsListenerContainerFactory`, `org.springframework.jms.config.SimpleJmsListenerEndpoint`, and `org.springframework.jms.config.JmsListenerEndpointRegistry`. It needs a broker/queue and an ID not colliding with existing endpoints. `ApplicationRunner` executes after refresh, making it convenient to demonstrate post-startup registration; in real environments, handle registration failures and post-restart rehydration policies.

### 14.3. Why Should Runtime Registration Not Be Used to Replace "Pause"?

Registration creates **a new endpoint/container**, whereas pause/resume acts on an **existing container**. If every pause/resume called `registerListenerContainer` with a new ID, the app would accumulate consumers, leak sessions/connections, and potentially process the same queue concurrently by accident. To pause or resume, use `container.stop/start`.

**API limitation:** in Spring JMS 6.2.x, the registry does not provide an `unregisterListenerContainer(String)` method equivalent to the familiar Spring Rabbit API. Stopping does not delete the registration. If an app must dynamically create/destroy thousands of subscriptions, design dedicated lifecycle and cleanup strategies instead of treating the registry as a CRUD store for endpoints.

## 15. Runtime Concurrency: Registry Manages Containers, Does Not Replace Factories

`DefaultMessageListenerContainer` can expose:

~~~java
MessageListenerContainer listener =
        registry.getListenerContainer("invoiceCommands");

if (listener instanceof DefaultMessageListenerContainer dmlc) {
    System.out.println(
            "Core consumers = " + dmlc.getConcurrentConsumers());
    System.out.println(
            "Max consumers = " + dmlc.getMaxConcurrentConsumers());
    System.out.println(
            "Scheduled = " + dmlc.getScheduledConsumerCount());
    System.out.println(
            "Active = " + dmlc.getActiveConsumerCount());
}
~~~

This is a snippet importing `org.springframework.jms.listener.DefaultMessageListenerContainer`. If the factory builds `SimpleMessageListenerContainer`, the cast will not match. If runtime concurrency changes are needed and supported by the implementation, setters on the concrete container can be used **after assessing impact**; that is not part of the generic `MessageListenerContainer` interface.

**When NOT to raise concurrency:** strict message ordering required on a queue, small downstream DB pools, topic subscriptions where duplicate semantics could arise, or a broker already serving many consumers across replicas. A registry with three endpoints each capped at 5 consumers is not 5 total; on one replica that can reach 15 invokers before multiplying by replica count.

**Note:** `DefaultMessageListenerContainer.getActiveConsumerCount()` can include invokers blocked in `receive(timeout)`; do not equate it with the number of business handlers actively executing simultaneously.

## 16. Registry and Spring Boot: Factory Overrides Can Change Behavior

With Spring Boot 3.x, a JMS starter, and a suitable provider, Boot usually auto-configures the default `JmsListenerContainerFactory`. If the application declares a factory bean with the same name, Boot may back off creating the default factory. Choices such as `MessageConverter`, `DestinationResolver`, `sessionTransacted`, native ConnectionFactory, and concurrency must be kept explicit.

When you need a new factory while inheriting Boot 3.5.x default config, use the configurer:

~~~java
@Configuration(proxyBeanMethods = false)
class CustomJmsFactoryConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory criticalQueueFactory(
            DefaultJmsListenerContainerFactoryConfigurer configurer,
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        configurer.configure(factory,
                ConnectionFactoryUnwrapper.unwrapCaching(
                        connectionFactory));
        factory.setConcurrency("2-5");
        factory.setSessionTransacted(true);
        return factory;
    }
}
~~~

Imports:
- `jakarta.jms.ConnectionFactory`.
- `org.springframework.context.annotation.Configuration`, `Bean`.
- `org.springframework.jms.config.DefaultJmsListenerContainerFactory`.
- `org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer`.
- `org.springframework.boot.jms.ConnectionFactoryUnwrapper`.

On the annotation, pick the bean explicitly:

~~~java
@JmsListener(
        id = "criticalInvoices",
        destination = "critical.invoice.queue",
        containerFactory = "criticalQueueFactory")
public void process(String body) {
    // Business processing.
}
~~~

**The registry will hold ID `criticalInvoices`**, not the factory name `criticalQueueFactory`. One factory can create **multiple containers** for multiple annotated endpoints. If you alter factory settings after containers have already been created, do not assume existing containers automatically reconfigure entirely; verify behavior and plan safe restarts.

## 17. Transactions, ACK, and Handler Errors During Stop/Start

The registry controls **container lifecycle**; it **does not directly change** a container's JMS acknowledgment mode or transaction manager.

- With `sessionTransacted=true`, if the listener handler succeeds, the container commits the JMS receive; appropriate exceptions trigger rollback/redelivery per provider policy.
- With `AUTO_ACKNOWLEDGE` on `DefaultMessageListenerContainer`, ACK can occur **before the handler runs**, so exceptions do not guarantee broker redelivery.
- With a separate DB transaction, failures between **DB commit** and **JMS commit** can still cause duplicate messages. Use a stable `eventId` and idempotent consumers.
- When stopping a container with in-flight messages, evaluate transaction completion/rollback, retry policy, DLQ, stop wait times, and graceful shutdown.
- Upon restart, you may receive old messages, new messages, or redeliveries; ordering depends on queue/topic, concurrency, and broker.

**Dangerous scenario:** using `stop()` to "cancel in-progress business work", then letting the client resend the same command with a new event ID. If the old handler already committed the database or payment before JMS ACK completed, the new send can cause a double charge. Stop/start only controls intake, not business idempotency/reconciliation.

## 18. Multi-Replica: The Registry Is Local to ApplicationContext

A service deployed across multiple pods:

~~~text
Pod A                       Pod B                       Pod C
 └─ Registry A                └─ Registry B               └─ Registry C
     └─ jobsDemo container       └─ jobsDemo container       └─ jobsDemo container
            │                          │                          │
            └──────────────────────────┼──────────────────────────┘
                                       ▼
                                  JMS broker queue
~~~

`Registry A.stop()` **does not** stop `Registry B` or `Registry C`. Moreover, an application can host multiple ApplicationContexts in tests or framework setups; injecting from the wrong context makes the registry list unexpected endpoints.

If you need "system-wide pause of consumption":
1. Define scope clearly: one endpoint, one replica, one deployment, or an entire broker address.
2. Use a control plane with auth/auditing to apply changes consistently, or broker administrative APIs where appropriate.
3. Observe consumer counts on the broker after the command, not just a Java boolean.
4. Handle in-flight messages and deadlines; roll back/redeliver per policy.
5. On resume, anticipate large backlogs and burst load; limit concurrency/backpressure.
6. Ensure operational actions record owner, timestamp, reason, and rollback plan.

An endpoint ID **only identifies a container inside one registry/context**, not a globally unique identifier across JVMs.

## 19. Meaningful Health, Metrics, and Logging

Measure at least three layers:

| Layer | Metric/state | Meaning |
| --- | --- | --- |
| Registry | Registered IDs, `getListenerContainer(id)!=null` | Endpoint infrastructure exists |
| Container | `isRunning()`, scheduled/active invokers, `isRecovering()` | Lifecycle/consumer invokers of this JVM |
| Broker | Connected consumers, queue depth, in-flight, oldest age, DLQ | Actual broker delivery/routing |
| Business | Success/failure, DB commits, retries/idempotency | Business work truly completed |

An administrative log should include `endpointId`, `applicationInstanceId`, `action` (STOP/START), operator, UTC timestamp, old/new lifecycle state, and correlation ID. For message processing, log `eventId` and `JMSMessageID` under data protection policies; never print usernames/passwords/sensitive PII.

**Never use the registry as a message inventory.** The registry does not know how many messages sit in a queue, TTL deadlines, offsets, processed event counts, or DLQ details. Broker consoles, metrics, and business data provide the complete picture.

### Health Aggregation: Distinguishing ANY from ALL

~~~java
Set<String> ids = Set.copyOf(
        registry.getListenerContainerIds());

boolean anyRunning = ids.stream()
        .map(registry::getListenerContainer)
        .anyMatch(c -> c != null && c.isRunning());

boolean allRunning = !ids.isEmpty()
        && ids.stream()
            .map(registry::getListenerContainer)
            .allMatch(c -> c != null && c.isRunning());
~~~

`anyRunning` matches **"at least one endpoint is running"**. `allRunning` can evaluate **the start state of all registered endpoints**, though if any listener intentionally sets `autoStartup=false` or is stopped on schedule, using `allRunning` for readiness will report false negatives. Readiness should check **the endpoints required to serve at that moment** plus broker health, not just an all/any boolean.

## 20. Troubleshooting by Symptom

| Symptom | Possible Cause | How to Verify |
| --- | --- | --- |
| Injecting registry fails | `@EnableJms` missing or Boot JMS infrastructure not activated | Classpath, condition report, annotation config |
| `getListenerContainerIds()` is empty | No endpoints, wrong component scan, annotation support off, late registration | Check listener beans, package scan, context |
| `getListenerContainer("myId")==null` | Wrong/omitted ID, used queue name instead of ID, different context | Compare `@JmsListener(id=...)` with actual IDs |
| App startup fails with duplicate endpoint ID | Two endpoints share the same ID | Assign unique IDs per annotation/registration |
| `isRunning()==true` yet no messages arrive | Broker down/recovering, auth, queue/topic, selector, conversion | Recovery logs, broker consumer count, metrics |
| `registry.isRunning()==true` yet endpoint X is stopped | Registry returns true when **at least one** container is running | Inspect per ID |
| Calling `registry.stop()` silences every endpoint | This stops the **entire registry** | Use `getListenerContainer(id).stop()` |
| One pod stops yet queue is still consumed | Other replicas/consumers still running | Broker consumer list across cluster |
| Messages lost when stopping topic | Non-durable subscription offline | Durable/shared subscriptions + TTL/retention |
| Messages redelivered after resume | In-flight rollback, uncommitted JMS transaction | Redelivery count, broker logs, consumer idempotency |
| `getActiveConsumerCount()` does not match handler count | Active invokers may be waiting in receive | Handler tracing, broker in-flight metrics |
| Custom factory causes listener to lose transactions | Skipped Boot configurer or forgot `sessionTransacted` | Inspect runtime factory/container and fault test |
| Runtime registration keeps creating growing IDs | Registering new endpoints instead of starting/stopping existing ones | Keep IDs stable and manage registration lifecycle |
| Tried `unregisterListenerContainer` and failed to compile | Confused **RabbitListenerEndpointRegistry** with **JmsListenerEndpointRegistry** | Check imports, Spring Framework JMS Javadoc |
| Registry started yet `JmsTemplate` send fails | Producer and listener use different connection config or broker error | Check both factories and client logs |
| Slow/hanging stop during shutdown | Handler in flight, network timeout, transaction commit/recovery | Thread dumps, timeouts, grace period |

Read startup logs/condition reports before changing configurations randomly. An annotated class outside Spring component scan will not be registered; changing the broker URL will not fix that error.

## 21. Testing Behavior Rather Than a Single Status Line

**Exercise 1 — ID listing:** create one listener with `id="jobsDemo"` and one without an ID. Print `getListenerContainerIds()`; identify the stable ID and generated ID.

**Exercise 2 — Finding the right container:** test `getListenerContainer("jobsDemo")`, `getListenerContainer("demo.registry.jobs")`, and a nonexistent ID. Explain the `null` results.

**Exercise 3 — Single-endpoint lifecycle:** create two listeners on two queues. Stop only listener A; send messages to both; verify B still receives in the JVM while A receives again only after start (if broker policy retains the message).

**Exercise 4 — Registry-wide stop:** call `registry.stop()` in a test environment; verify both endpoints stop. Compare with `listener.stop()`; never run this exercise in production.

**Exercise 5 — ANY vs. ALL:** stop one of two listeners, compare `registry.isRunning()` against each `container.isRunning()`. Explain why the registry can return true.

**Exercise 6 — Consumer runtime type:** cast via `instanceof DefaultMessageListenerContainer` and log scheduled/active counts and recovering status; compare with connected consumers on the broker.

**Exercise 7 — Broker outage:** shut down test Artemis, observe the container stays running while `isRecovering()`/logs change; start the broker and verify recovery and delivery.

**Exercise 8 — Auto-startup:** set `spring.jms.listener.auto-startup=false` with the default factory, observe the container exists yet is not running. Start the right ID; do not call registry-wide start when other endpoints must stay disabled.

**Exercise 9 — Programmatic endpoint:** register a `SimpleJmsListenerEndpoint` via `JmsListenerConfigurer` at startup; verify the new ID in the registry.

**Exercise 10 — Runtime registration:** call `registerListenerContainer(endpoint,factory,true)` after context refresh; send messages and observe; test duplicate IDs in a test environment and explain the exception.

**Exercise 11 — Transactions:** enable local `sessionTransacted=true`, make the listener throw an error; verify rollback/redelivery or DLQ per provider policy. Stop/start does not alter ACK policies.

**Exercise 12 — Multi-replica:** run two instances on the same queue with the same listener ID. Stop one instance and observe the other consumer still receiving; explain why IDs are not global control-plane keys.

**Exercise 13 — Topic:** test stopping/starting a non-durable topic subscriber and observe potential missed events; never assume queue semantics hold for topics.

**Exercise 14 — Graceful shutdown:** create a slow handler, call stop then shut down the JVM, and record stop duration, in-flight state, DB commits, and redeliveries after restart.

**Exercise 15 — Security:** simulate an administrative route with an allowlist and audit logging; verify unauthorized users cannot start/stop any listener.

### Self-Assessment Checklist

- [ ] Distinguish **endpoint ID**, destination, factory bean, and container instance.
- [ ] Know `JmsListenerEndpointRegistry` is a Spring bean, whereas annotation-created containers are usually **not** individual beans.
- [ ] Know `getListenerContainerIds()`, `getListenerContainers()`, and `getListenerContainer(id)` with the `null` branch.
- [ ] Know how to stop/start **a single container** and stop/start **the entire registry**.
- [ ] Never interpret `registry.isRunning()` as "all endpoints are healthy".
- [ ] Know `DefaultMessageListenerContainer`'s scheduled/active/recovering metrics are not business outcomes.
- [ ] Know IDs must be unique within the registry and never rely on generated IDs for critical operations.
- [ ] Know how to register endpoints via `JmsListenerConfigurer`/`SimpleJmsListenerEndpoint` or runtime `registerListenerContainer`.
- [ ] Never copy Rabbit's `unregisterListenerContainer` into JMS by mistake.
- [ ] Understand `stop/start` controls **local intake**, not stopping the broker/queue or all replicas.
- [ ] Have auth/audit mechanisms whenever exposing lifecycle controls via management APIs.
- [ ] Understand transactions/ACK, in-flight work, and idempotency across stop/start/shutdown.
- [ ] Verify using broker tests, logs, and metrics rather than relying on a single boolean.

**Closing question:** "An application has `@JmsListener(id="payments", destination="payment.commands")`. How do you stop only this consumer without stopping all listeners?" — Inject `JmsListenerEndpointRegistry`, call `getListenerContainer("payments")`, verify it is non-`null`, and call `stop()` on **the returned container**. Never pass the queue name, never call `registry.stop()`, and remember other replicas may still be consuming.

## 22. Official References

1. [Spring Framework Reference — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html): `@JmsListener`, containers not being standalone beans, registry, and programmatic endpoint registration.
2. [Spring Framework 6.2 — JmsListenerEndpointRegistry Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistry.html): `getListenerContainerIds`/`getListenerContainer`/`getListenerContainers` signatures, start/stop, and registration.
3. [Spring Framework 6.2 — JmsListenerEndpointRegistrar Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistrar.html): endpoint registration during annotation infrastructure setup.
4. [Spring Framework 6.2 — SimpleJmsListenerEndpoint Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/config/SimpleJmsListenerEndpoint.html): configuring ID, destination, and `MessageListener` directly.
5. [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): listener containers, concurrency, session transactions, resource management.
6. [Spring Framework 6.2 — DefaultMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html): invoker states, recovery, and lifecycle.
7. [Spring Boot 3.5 — JMS](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html): Artemis starter, auto-configuration, and default listener factory.
8. [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `spring.jms.listener.*` and `spring.artemis.*`.
9. [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): JMS consumers/connections/sessions, ACK, transactions, and redelivery.

**Conclusion:** `JmsListenerEndpointRegistry` is **the access and lifecycle coordination point** for containers created from `@JmsListener`. Use **stable IDs** to locate containers, apply start/stop at **the right scope**, and combine registry state with broker metrics and business outcomes. Lifecycle control does not replace broker administration or business processing guarantees.