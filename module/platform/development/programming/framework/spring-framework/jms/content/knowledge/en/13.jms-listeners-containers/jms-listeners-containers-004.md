# Containers Managing Consumers, Threads, and Resources in Spring JMS

**Parent topic:** Listeners and containers — Spring Framework / JMS.

**Goal:** When seeing `@JmsListener`, explain **who creates `MessageConsumer`, who holds `Session` and `Connection`, which thread invokes message handling, and who is responsible for starting/stopping/recovering**, as well as the impact of concurrency, caching, transactions, and broker failures. This lesson focuses on Spring's **JMS Message Listener Container**, not conflating it with servlet containers, Docker/Kubernetes, or message brokers.

**Environment:** Java 17+, Spring Framework 6.x / Spring Boot 3.x, Jakarta Messaging (`jakarta.jms`); examples connect to an external Apache ActiveMQ Artemis broker. Defaults are scoped to specific versions and may change when upgrading Spring/providers. In particular, **a container managing resources for a listener does not mean Spring creates the broker or business DB**.

## 1. Overall Model: @JmsListener Is Only a Configuration Entry Point

`@JmsListener` is typically placed on a **Spring-managed bean**. It is not itself a thread or a consumer. When Spring processes the annotation, the endpoint infrastructure creates a **listener container** via a `JmsListenerContainerFactory`. It is the container that operates the consumer.

~~~text
                          Spring ApplicationContext
                                   │
                   detects @JmsListener on beans
                                   │
                                   ▼
                   JmsListenerEndpointRegistry
                                   │
                                   ▼
                   JmsListenerContainerFactory
                                   │ creates / configures
                                   ▼
                     MessageListenerContainer
                           │       │       │
                           │       │       └── lifecycle: start/stop/recover
                           │       └────────── TaskExecutor / consumer threads
                           └────────────────── JMS resources
                                                 │
                   ┌─────────────────────────────┼──────────────────────┐
                   ▼                             ▼                      ▼
           JMS Connection                 JMS Session            MessageConsumer
                   │                             │                      │
                   └─────────────────────────────┴──────────────────────┘
                                                 │
                                                 ▼
                                         JMS broker / queue
                                                 │
                                                 ▼
                                 @JmsListener method in Spring bean
~~~

**Distinguish ownership layers:**

- **JMS provider/broker:** actually stores, routes, and delivers messages; controls prefetch/credit, expiry, DLQ, redelivery, ACLs, and HA per configuration.
- **Spring ConnectionFactory bean:** provides the capability to open a JMS `Connection`; the factory itself does not necessarily open connections when Spring starts.
- **Listener container:** actively creates/holds/closes connections, sessions, and consumers per policy, runs the receive loop and dispatches callbacks, and manages recovery.
- **Spring listener bean:** contains business logic, converters/validators, and required DB transactions; should **not** manually close JMS resources being used by the container.

The application does not need to manually call `new MessageConsumer(...)` or `new Thread(...)` per message just to use `@JmsListener`. The benefit of a container is **centralized resource ownership and consistent lifecycle management**.

## 2. Why Use a Container Instead of Writing a Receive Loop Yourself?

A hand-written worker at the JMS layer might look simple:

~~~java
while (running) {
    Message m = consumer.receive(1_000L);
    if (m != null) {
        process(m);
    }
}
~~~

However, the application would have to decide: who creates `Connection`/`Session`/`MessageConsumer`, who calls `connection.start()`, how to react to broker restarts, how to stop threads without leaks, how to roll back when a listener throws an error, how to scale consumer counts, measure lag, and manage shutdown. With ten queues or multiple replicas, complexity multiplies rapidly.

Spring's `DefaultMessageListenerContainer` provides a **framework-managed receive loop**. It obtains JMS resources from the factory, schedules consumer tasks, invokes the listener, handles acknowledgements/transactions per configuration, and attempts recovery when the broker disconnects. The application remains responsible for **business retry/idempotency and broker infrastructure**, without having to assemble the lifecycle loop itself.

**Limitations:** the container does not promise "exactly once" processing in the DB, does not override JMS session threading rules, does not automatically manage SQL transactions for every dependency, and does not create unlimited workers at zero resource cost.

## 3. Three Levels of JMS Resources: Connection, Session, MessageConsumer

| Resource | Function | Relationship to the container |
| --- | --- | --- |
| `ConnectionFactory` | Factory/provider client for opening connections | Injected into the container; can be a native factory, cached wrapper, or pool depending on configuration |
| `Connection` | Logical channel to the broker that can support multiple sessions | Container opens/manages connections, starts/stops/re-establishes; **not required to be one physical connection per consumer** |
| `Session` | JMS working context; creates consumers and controls local JMS transactions/ack | Each consumer/invoker normally uses its own session; **never share one session across concurrent threads** |
| `MessageConsumer` | Specific subscription/consumer on a queue/topic/selector | Container creates, retains, or recreates depending on cache level and recovery |
| `TaskExecutor` | Execution infrastructure for consumer invoker tasks | Schedules and runs tasks that may block in `receive()` |
| `@JmsListener` bean | Business handler method | Invoked when the container delivers a message; method may run concurrently if multiple consumers are configured |

One `Connection` can be shared across multiple `Session`s, but a classic JMS `Session` follows a **single-threaded context** model. The container normally provides one session to **one actively executing consumer task at a time**. Do not confuse the hierarchy:

~~~text
1 Connection  ──► multiple Sessions
Session A     ──► consumer A ──► listener invocation on worker A
Session B     ──► consumer B ──► listener invocation on worker B
Session C     ──► consumer C ──► listener invocation on worker C
~~~

The numbers of **listener methods**, **concurrent consumers**, **JMS sessions**, **physical connections**, and **OS threads** are **different quantities**. Typically each consumer task uses one session/consumer, though provider pooling and cache levels can alter the resource counts visible in the broker console.

## 4. Spring's Two Standard Listener Containers

Spring JMS provides two common implementations:

| Feature | `SimpleMessageListenerContainer` | `DefaultMessageListenerContainer` |
| --- | --- | --- |
| Receiving mechanism | Registers callback via `MessageConsumer.setMessageListener(...)` | Runs `MessageConsumer.receive(...)` loop inside consumer invoker tasks |
| Consumer count | Creates a fixed count at startup | Has core consumers and can scale up to max under load |
| Listener callbacks | JMS provider dispatches callbacks | Spring `TaskExecutor` runs invokers and calls the listener |
| Recovery/lifecycle | Simpler mechanism, more provider-dependent | Has self-recovery logic, stop/restart, and runtime configuration changes |
| Local JMS transaction | Can enable `sessionTransacted=true` | Can enable `sessionTransacted=true` |
| External/JTA transaction manager | Does not support participation like Default | Supports configuring an appropriate `PlatformTransactionManager` |
| Concurrency scaling | Essentially fixed | Supports core/max configuration and dynamic scaling |
| When to consider | Simple JMS integration under specific provider conditions | Usually the default choice for Spring workloads needing recovery and resource control |

**Do not assume "Simple" means fewer threads and therefore guaranteed better performance.** `SimpleMessageListenerContainer` delegates callback execution to the JMS provider; it does not mean every listener runs on the configuration thread. Conversely, `DefaultMessageListenerContainer`, despite using a synchronous `receive` loop internally, is still **asynchronous with respect to publisher code and HTTP threads** because the container runs separate invoker tasks.

With `@JmsListener` created from `DefaultJmsListenerContainerFactory`, the runtime container is typically `DefaultMessageListenerContainer`. Applications writing their own factories may choose a different implementation; always verify the **actual runtime class** when diagnosing.

## 5. Lifecycle of a Container: From ApplicationContext to Shutdown

A basic lifecycle flow of `DefaultMessageListenerContainer`:

~~~text
[Configuration / bean definitions]
           │
           ▼
[@EnableJms or Boot auto-config creates annotation infrastructure]
           │
           ▼
[Endpoint registered; factory creates listener container]
           │
           ▼
[Context refresh / autoStartup]
           │
           ▼
[Container start]
  ├─ obtains ConnectionFactory
  ├─ sets up shared/dedicated connection per cache policy
  ├─ schedules consumer invoker tasks
  ├─ creates Session + MessageConsumer for invoker
  ├─ receives message and dispatches to listener
  └─ loops receive, transaction/ACK per configuration
           │
           ├── broker error → recovery/backoff → recreate resources
           │
           ├── stop → stops receiving new messages per lifecycle, drains in-flight
           │
           └── context close / destroy → closes consumer/session/connection,
                                         stops worker tasks appropriately
~~~

**Do not assume a `@Bean` being created means the broker is connected.** Connection setup may happen asynchronously. A container may have `isRunning()==true` yet have no consumers actually connected because the broker is down or recovery is underway. Always correlate runtime state, recovery logs, and broker-side consumer counts.

Spring listener containers implement lifecycle integration, typically via `SmartLifecycle`. `autoStartup` controls whether it starts when the context initializes; `phase` coordinates relative start/stop ordering among lifecycle beans. During shutdown, consider in-flight messages and the orchestrator's total deadline, not just a "container stop called" log line.

## 6. @JmsListener + JmsListenerContainerFactory: What Does One Annotation Create?

Plain Spring Framework can enable annotation support and declare a factory:

~~~java
package example.listener;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
public class ListenerConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false); // queue
        factory.setSessionTransacted(true);
        factory.setConcurrency("2-4");
        factory.setReceiveTimeout(1_000L);
        factory.setRecoveryInterval(5_000L);
        return factory;
    }
}
~~~

This is **a compilable Java 17 class** in a Spring Framework 6.x application with a `jakarta.jms.ConnectionFactory` bean/provider, `spring-jms`, and container configuration. The class **has no `main`**: running it requires initializing an ApplicationContext/component scan and having a broker. `@EnableJms` registers discovery for `@JmsListener`. The factory name `jmsListenerContainerFactory` is the default name the annotation infrastructure looks for when an endpoint does not specify a factory.

Meaning of each line:

- `setConnectionFactory`: selects the provider and connection infrastructure.
- `setPubSubDomain(false)`: destination names are interpreted as queues; topics require their own policy.
- `setSessionTransacted(true)`: each listener invocation uses a local JMS transaction (if supported by the provider); appropriate handler exceptions trigger rollback/redelivery.
- `setConcurrency("2-4")`: maintains core consumers and can scale to max under load, **without sharing a single session concurrently across four threads**.
- `setReceiveTimeout(1_000L)`: each invoker `receive` call waits about one second; **this is not a business processing SLA**.
- `setRecoveryInterval(5_000L)`: interval between configured connection recovery attempts; **not the retry delay for a poison message**.

When using **Spring Boot 3.x** with a JMS starter, you usually do not need to declare the entire class above manually: Boot creates `ConnectionFactory`, template, and the default listener factory conditionally. However, when the application defines its own `jmsListenerContainerFactory` bean, you may **replace Boot's default configuration**; transaction, converter, destination resolver, and caching semantics must be kept explicit.

## 7. Business Beans Are Not Where Consumers Are Created

Listener example inside a Spring-managed component:

~~~java
package example.listener;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class InvoiceWorker {

    @JmsListener(destination = "invoice.commands")
    public void onMessage(String content) {
        System.out.println("Thread=" + Thread.currentThread().getName()
                + " payload=" + content);
    }
}
~~~

Here, `InvoiceWorker` only holds the handler. The annotation does not itself call `connection.createSession`. Spring creates an endpoint container; the container sets up the corresponding consumer, receives messages, and calls `onMessage` from a chosen worker thread.

**Required conditions:**
1. `InvoiceWorker` must actually be a Spring bean (via component scan or `@Bean`); an instance created with `new InvoiceWorker()` outside Spring will not be registered by Spring's listener infrastructure.
2. Annotation support is enabled: `@EnableJms` in plain Spring, or auto-configured by Boot.
3. An appropriate `JmsListenerContainerFactory` and a `ConnectionFactory` pointing to the right broker exist.
4. Queue `invoice.commands` exists or the broker allows provisioning per policy; credentials have consume permissions.
5. The listener container is running, connected to the broker, and message routing is accurate.

The `onMessage(String)` method in the example only runs when a message is converted into a matching `String`; `MessageConverter` and the listener adapter govern conversion. If the message is a binary/JSON POJO that the converter does not understand, the listener can fail **before or during dispatch**.

## 8. Spring Boot 3.x: Runnable Example Observing Threads and Consumer Count

This example uses **Java 17**, **Spring Boot 3.5.0** (a real release, without claiming it is the latest), and an Artemis broker **running outside the application**. The goal is to demonstrate that the container is automatically created, has an endpoint ID for management, and runs listeners on separate threads.

### 8.1. build.gradle file

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
rootProject.name = 'jms-container-resources'
~~~

### 8.2. application.yaml file

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
      min-concurrency: 2
      max-concurrency: 4
      receive-timeout: 1s
~~~

Supply the password via `SPRING_ARTEMIS_PASSWORD` or a secret store; never commit passwords to Git. The broker must have the endpoint, user, and queue `demo.listener.jobs` created or auto-creation enabled. The `spring.jms.listener.*` values control Boot's auto-configured factory when conditions match; if you define a custom factory without Boot's configurer, these properties are **not guaranteed to apply automatically**.

### 8.3. Full Java in one file

`src/main/java/example/jmscontainer/ContainerResourcesApplication.java`:

~~~java
package example.jmscontainer;

import java.util.UUID;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.listener.DefaultMessageListenerContainer;
import org.springframework.jms.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class ContainerResourcesApplication {

    public static void main(String[] args) {
        SpringApplication.run(ContainerResourcesApplication.class, args);
    }

    @Bean
    ApplicationRunner publishAndInspect(
            JmsTemplate jmsTemplate,
            JmsListenerEndpointRegistry registry) {

        return args -> {
            MessageListenerContainer container =
                    registry.getListenerContainer("demoJobsListener");

            if (container == null) {
                throw new IllegalStateException(
                        "Listener endpoint not registered");
            }

            System.out.println("LISTENER_RUNNING=" + container.isRunning());

            if (container instanceof DefaultMessageListenerContainer dmlc) {
                System.out.println("SCHEDULED_CONSUMERS="
                        + dmlc.getScheduledConsumerCount());
                System.out.println("ACTIVE_CONSUMERS="
                        + dmlc.getActiveConsumerCount());
            }

            for (int i = 1; i <= 4; i++) {
                String eventId = UUID.randomUUID().toString();
                String body = "job-" + i;

                jmsTemplate.convertAndSend(
                        "demo.listener.jobs",
                        body,
                        message -> {
                            message.setStringProperty("eventId", eventId);
                            return message;
                        });
            }
            System.out.println("PUBLISHER_SENT_FOUR_MESSAGES");
        };
    }
}

@Component
class JobsListener {

    @JmsListener(
            id = "demoJobsListener",
            destination = "demo.listener.jobs")
    public void onMessage(Message message) throws JMSException {

        String eventId = message.getStringProperty("eventId");
        String body = message instanceof TextMessage text
                ? text.getText() : "<non-text-message>";

        System.out.println(
                "CONSUMED thread=" + Thread.currentThread().getName()
                        + " eventId=" + eventId
                        + " body=" + body);
    }
}
~~~

**Why the example works:** `spring-boot-starter-artemis` brings in Spring JMS and the compatible Artemis Jakarta client; with JMS infrastructure on the classpath, Boot auto-creates `ConnectionFactory`, `JmsTemplate`, the default `JmsListenerContainerFactory`, and detects `@JmsListener`. `@Component` registers the listener; `@JmsListener(id=...)` sets an ID for registry lookup. `ApplicationRunner` runs during startup after the ApplicationContext refreshes. Consumer threads and the publisher do not share the same method call stack.

### 8.4. Running and observing

With Gradle wrapper and a running test broker:

~~~bash
./gradlew bootRun
~~~

The lines below are only **one possible log output**, not fixed stdout:

~~~text
LISTENER_RUNNING=true
SCHEDULED_CONSUMERS=2
ACTIVE_CONSUMERS=2
PUBLISHER_SENT_FOUR_MESSAGES
CONSUMED thread=DefaultMessageListenerContainer-... eventId=... body=job-1
CONSUMED thread=DefaultMessageListenerContainer-... eventId=... body=job-2
CONSUMED thread=DefaultMessageListenerContainer-... eventId=... body=job-3
CONSUMED thread=DefaultMessageListenerContainer-... eventId=... body=job-4
~~~

**No guarantees on numbers or order:** the container starts and connects asynchronously; scheduled/active counts may differ at the exact moment read. Two core consumers do not mean one new thread per message; threads can be reused. On a multi-consumer queue, `job-2` may be processed before `job-1`. The listener may receive while the publisher is still sending, so `CONSUMED` logs can appear **before** `PUBLISHER_SENT_FOUR_MESSAGES`. If the broker cannot connect, lacks permissions, lacks the queue, or hits an error, the example may emit no consume logs and provider logs should be checked.

**Not an example of business state persistence:** the handler only logs; there are no DB commits, idempotency, business retries, or DLQ tests. On each restart, the runner sends four more messages with new IDs. Do not use a startup runner to publish real business events without transactions/outbox.

## 9. Why Are Factory and Container Two Different Objects?

A `DefaultJmsListenerContainerFactory` is a **configuration blueprint** for creating `DefaultMessageListenerContainer` instances. It does **not** mean there is only one consumer across the entire application.

Suppose there are two methods:

~~~java
@JmsListener(id = "billing", destination = "billing.queue")
public void bill(String body) {
    handleBilling(body);
}

@JmsListener(id = "shipping", destination = "shipping.queue")
public void ship(String body) {
    handleShipping(body);
}
~~~

These are **snippets**, with `handleBilling` and `handleShipping` as application-defined business logic. For each endpoint, the factory creates a **separate container**. The two containers share the factory's baseline settings yet have distinct resources/lifecycles and destinations.

~~~text
DefaultJmsListenerContainerFactory
          │
          ├──► billing container  ──► Sessions/Consumers on billing.queue
          │
          └──► shipping container ──► Sessions/Consumers on shipping.queue
~~~

If `concurrency=3-5` is configured **per container** and there are three endpoints, theoretically up to 15 consumer tasks can exist, not 5 total across the application. Capacity planning must calculate **endpoints × consumers per endpoint × replicas**, plus broker limits, sessions, DB connection pools, and downstream APIs. That is why looking solely at `max-concurrency` cannot prove a system is safe.

## 10. Concurrency in DefaultMessageListenerContainer

Two key parameters:

- `concurrentConsumers`: baseline number of consumer invokers the container keeps (default is 1).
- `maxConcurrentConsumers`: upper limit (default 1). Only when max is higher than core can the container **scale up/down** within that range.

Can be configured via string:

~~~java
factory.setConcurrency("2-5");
~~~

or via Boot properties:

~~~yaml
spring:
  jms:
    listener:
      min-concurrency: 2
      max-concurrency: 5
~~~

Practical meaning: the container maintains 2 core consumers and **can** create up to 5 invokers if it detects suitable load. There is no guarantee it will always reach max merely because queue depth rises: broker credit/prefetch, task executor saturation, CPU, DB, and other limits all affect it.

**With a queue**, increasing concurrency can boost throughput, yet generally **eliminates strict processing order** because consumers run in parallel. With a **standard topic subscription**, do not arbitrarily raise consumer counts: you may create multiple subscriptions receiving the same event, causing duplicate processing per pub/sub semantics. For parallel topic processing, look into shared/durable subscriptions supported by JMS 2.0+/providers.

### 10.1. Threads and messages are not one-to-one

~~~text
Consumer invoker A (thread A)
    receive M1 → handle M1 → receive M3 → handle M3 → ...

Consumer invoker B (thread B)
    receive M2 → handle M2 → receive M4 → handle M4 → ...
~~~

One thread can process **multiple messages sequentially**; if a handler takes 5 seconds, that consumer cannot receive the next message while running handler code. Increasing concurrency does not split a single message into parallel parts.

### 10.2. Scheduled count is not active count

`DefaultMessageListenerContainer` exposes:

~~~java
int scheduled = container.getScheduledConsumerCount();
int active = container.getActiveConsumerCount();
int min = container.getConcurrentConsumers();
int max = container.getMaxConcurrentConsumers();
~~~

This snippet assumes `container` is a `DefaultMessageListenerContainer`. Scheduled is the number of scheduled tasks; active is the number currently active per container definition, and they can differ. **Do not treat active as the exact number of messages being processed right now**; an active invoker may be waiting in `receive(timeout)`. Combine with broker in-flight counts and handler metrics.

### 10.3. The pitfall of setting max too high

With 8 replicas, 4 endpoints, and `maxConcurrency=10`, the projected ceiling can be **320 consumer invoker tasks** (8 × 4 × 10) if all endpoints are configured that way. The broker, JVM, DB pool, and external APIs may be overwhelmed. This number is derived from **hypothetical capacity configuration**, not actual broker state.

When scaling, use load tests, downstream concurrency limits, queue depth/age, p95/p99 processing latency, and connection pool utilization to choose core/max. Do not increase consumer counts solely because you see a backlog.

## 11. TaskExecutor: Who Owns the Message-Receiving Threads?

With `DefaultMessageListenerContainer`, Spring schedules invokers via a `TaskExecutor`. If no custom executor is supplied, the container creates a default executor (in Spring 6.x typically `SimpleAsyncTaskExecutor`) to run tasks per `concurrentConsumers`/max. These tasks may be long-lived to loop on `receive`.

~~~text
TaskExecutor
 ├─ invoker #1  ──► session #1 + consumer #1 ──► listener handler
 ├─ invoker #2  ──► session #2 + consumer #2 ──► listener handler
 └─ invoker #3  ──► session #3 + consumer #3 ──► listener handler
~~~

**If using a custom thread pool**, remember that consumer invokers **can hold threads for long durations**, unlike an HTTP task that runs for a few milliseconds and releases its slot. A 4-thread pool shared across 5 listener containers can cause **starvation**: new tasks get no thread to run even if the JVM has free CPU. When a pool reports full, inspect both invokers holding threads and tasks queued in the executor.

### 11.1. Do not spawn `new Thread` inside @JmsListener to "speed up"

~~~java
@JmsListener(destination = "jobs.queue")
public void onMessage(String payload) {
    new Thread(() -> doWork(payload)).start();
}
~~~

This is an **illustrative anti-pattern**, with `doWork` as hypothetical business code. The listener returns before the background thread finishes. If the container is transacted, the JMS transaction may **commit right after the method returns**, and if the external business thread fails, the broker will not automatically redeliver the message. The new thread also does not inherit Spring-managed transaction/thread context.

If work truly must be decoupled, use a **durable handoff** mechanism and explicit outcome protocol, or use an appropriate listener design. Never turn method return into an early ACK just by launching an async task.

### 11.2. Java 21 virtual threads are a separate option

Some Spring Framework 6.2+ versions support configuring virtual threads on `DefaultMessageListenerContainer` (Java 21+). This lesson uses Java 17, so that option is not enabled. Even when virtual threads reduce JVM waiting overhead, JMS sessions/consumers, broker quotas, and downstream DB connections remain **finite resources**; there is no free throughput multiplier.

## 12. Container Cache vs ConnectionFactory Cache and Pools

It is easy to confuse three resource layers:

1. **`DefaultMessageListenerContainer`'s own cache:** retains `Connection`, `Session`, and `MessageConsumer` across receive cycles per `cacheLevel`; can recreate them on errors.
2. **Spring's `CachingConnectionFactory`:** a wrapper around the provider factory that can cache connections/sessions/producers/consumers; often helpful for `JmsTemplate` sending many short requests.
3. **JMS connection pool** (such as `pooled-jms`): can manage multiple physical connections, max connections, borrowing, and resource limits; not equivalent to a session cache.

Detailed table for `DefaultMessageListenerContainer`'s `cacheLevel`:

| Level | Retains resources across receive cycles | When to consider |
| --- | --- | --- |
| `CACHE_NONE` | Does not retain JMS handles | Compatible with some containers/JTA providers requiring fresh handles when a transaction starts |
| `CACHE_CONNECTION` | Retains connection, re-acquires session/consumer as needed | When reducing connection cost without caching everything |
| `CACHE_SESSION` | Retains connection + session, re-acquires consumer | When consumers should not be cached too long |
| `CACHE_CONSUMER` | Retains connection + session + consumer | Native JMS environments using local transactions; minimal per-receive overhead |
| `CACHE_AUTO` | Chooses based on transaction management strategy | Default; does **not** mean a fixed level forever |

In typical environments **without an external transaction manager**, `CACHE_AUTO` effectively acts as `CACHE_CONSUMER`. When an external transaction manager is configured, the default may fall back to `CACHE_NONE` so fresh resources are properly enlisted in the JTA/XA transaction. Changing the cache level without understanding XA enlistment can prevent transactions from **properly spanning JMS receives**.

### 12.1. Why does Boot avoid passing the caching wrapper directly to listeners?

Spring Boot 3.x normally wraps the native JMS `ConnectionFactory` in a `CachingConnectionFactory` for the `JmsTemplate` path. However, the listener container should generally use the **native ConnectionFactory** to manage its own recovery/connections/sessions. Boot's auto-configuration provides `ConnectionFactoryUnwrapper.unwrapCaching(...)` to retrieve the native factory from Boot's wrapper when appropriate.

**Warning:** Boot's unwrapping mechanism recognizes only specific wrappers; if you nest multiple custom proxies/pools, do not assume the container will always obtain the native factory automatically. Inspect the runtime bean graph.

### 12.2. When creating a custom factory in Boot, inherit the configurer

Boot 3.5.x snippet:

~~~java
@Configuration(proxyBeanMethods = false)
class CustomJmsContainers {

    @Bean
    DefaultJmsListenerContainerFactory priorityJobsFactory(
            DefaultJmsListenerContainerFactoryConfigurer configurer,
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        configurer.configure(
                factory,
                ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));

        // Override only what differs from Boot's defaults.
        factory.setConcurrency("2-4");
        factory.setSessionTransacted(true);
        return factory;
    }
}
~~~

Imports:
- `jakarta.jms.ConnectionFactory`.
- `org.springframework.context.annotation.Configuration` and `Bean`.
- `org.springframework.jms.config.DefaultJmsListenerContainerFactory`.
- `org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer`.
- `org.springframework.boot.jms.ConnectionFactoryUnwrapper`.

This snippet must be placed in a Spring Boot 3.5.x application with a provider client; it is **not** a standalone runnable program. With the bean named `priorityJobsFactory`, use:

~~~java
@JmsListener(
        destination = "priority.jobs",
        containerFactory = "priorityJobsFactory")
public void handlePriorityJob(String body) {
    processPriority(body);
}
~~~

`processPriority` is custom business logic. A **custom-named** factory does not automatically replace the default factory for all endpoints; `containerFactory` on the annotation selects the exact bean. Using `DefaultJmsListenerContainerFactoryConfigurer` preserves Boot's applied configuration choices, avoiding accidentally losing transactions/message converters/destination resolvers when creating a new factory.

## 13. Recovery and Reconnect: What Does the Container Recover?

When the broker disconnects, `DefaultMessageListenerContainer` runs recovery logic: catches the exception, waits an interval/backoff, recreates/re-registers JMS resources per configuration, and resumes receiving. In Spring Framework 6.x, `DEFAULT_RECOVERY_INTERVAL` is **5,000 ms** unless customized.

~~~text
RUNNING / receiving
     │
     ▼
Broker network outage
     │
     ▼
receive / setup failure
     │
     ▼
Container recovering
  ├─ closes/refreshes stale resources
  ├─ waits recoveryInterval or BackOff
  └─ retries connection / destination / consumer
     ├─ succeeds → RUNNING / receiving
     └─ fails    → continues per backoff policy
~~~

**Connection recovery is not business retry.** The broker may have delivered a message and the consumer crashed before JMS commit; after reconnect, the message can be redelivered per provider policy. The container does not automatically create unique indexes or idempotency keys in the database.

**Do not confuse two wait settings:**
- `receiveTimeout`: how long one invoker loop waits for a **message**.
- `recoveryInterval` / `BackOff`: how long to wait **before the next connection/resource recovery attempt**.

Appropriate settings should reflect SLAs, broker failover, and load. A recovery interval that is too short across hundreds of replicas can cause a **thundering herd** when the broker comes back online. Use backoff/jitter or appropriate provider mechanisms; do not hot-loop retries indefinitely.

### 13.1. Can you inspect whether the container is recovering?

~~~java
if (container instanceof DefaultMessageListenerContainer dmlc) {
    System.out.println("recovering=" + dmlc.isRecovering());
}
~~~

This snippet assumes `container` of type `MessageListenerContainer` retrieved from the registry. `isRecovering()` is a useful indicator, yet must be combined with broker-side connection metrics, consumer counts, queue age, and logs; never treat one boolean as an entire health check.

### 13.2. Handler errors differ from transport errors

| Scenario | Primary responsible side |
| --- | --- |
| Broker refused connection / auth fail | Provider/config + container recovery |
| Network lost between receive and commit | JMS transaction/rollback + broker redelivery policy |
| JSON converter cannot read payload | Consumer contract, error classification, DLQ |
| Handler throws exception due to DB timeout | Business retry policy, JMS rollback/delivery |
| Handler committed DB but JMS commit failed | Consumer idempotency + reconciliation |
| Message hit TTL expiry | Broker expiry policy, application outcome monitoring |

An `ErrorHandler` on the listener container can receive exception notifications; it **does not replace** transaction rollback, DLQ routing, or retry logic. When handling exceptions inside a handler, avoid swallowing errors and returning success if business work has not committed — the container may ACK/commit the JMS receive and the message will not be redelivered.

## 14. Acknowledgements and Transactions Are Container Configuration Responsibilities

A listener receiving a message and throwing an exception **does not guarantee redelivery** if the container is in non-transacted `AUTO_ACKNOWLEDGE`. With `DefaultMessageListenerContainer`, AUTO_ACK is typically performed **before listener execution**, so an exception from the listener does not trigger broker redelivery the way many people assume.

| Mode | What you need to know |
| --- | --- |
| `AUTO_ACKNOWLEDGE` | ACK may occur before the listener runs in Default container; unsuitable for workloads requiring processing before ACK |
| `CLIENT_ACKNOWLEDGE` | Container actively manages ACK per session semantics; not synonymous with DB commit |
| `DUPS_OK_ACKNOWLEDGE` | May delay ACK; potential redelivery/duplicates must be accepted |
| `sessionTransacted=true` | Local JMS receive transaction; handler success commits JMS, appropriate errors roll back |
| External/JTA transaction manager | Can span JMS + compatible XA resources, though requires dedicated infrastructure/provider/configuration |

Spring Framework generally recommends **transacted sessions** when reliable message processing is needed. Spring Boot 3.x's auto-configured default listener factory is configured as **transactional**: if a suitable JTA manager exists, it binds JTA; otherwise it sets `sessionTransacted=true`. If you build a custom factory without using the configurer, transaction defaults may differ; verify **the exact bean used by the endpoint**.

**Important:** a local JMS transaction does not automatically include PostgreSQL/MySQL. If a handler commits the DB first and then the JMS commit fails, the broker can redeliver; you need a stable `eventId` and idempotency via a DB unique constraint/inbox within a single DB transaction. Provider-assigned `JMSMessageID` can change if the producer re-sends the same business event as a new message.

## 15. Stop, Start, and Shutdown: More Than Just a Running Flag

`JmsListenerEndpointRegistry` lets you look up an endpoint's container by ID:

~~~java
MessageListenerContainer c =
        registry.getListenerContainer("demoJobsListener");

if (c != null) {
    System.out.println(c.isRunning());
    c.stop();   // Stops receiving per lifecycle.
    // After preparing conditions to reopen and resume receiving:
    c.start();
}
~~~

This snippet is intended for operational/test tooling, not inside a listener handler actively processing a message. `stop()` does not mean messages are finished or resources are permanently destroyed; the container can be started again. `destroy()/ApplicationContext.close()` ends the lifecycle, releasing consumers/sessions/connections via the infrastructure. Do not use `stop/start` as a "pause queue" across replicas without coordinating other consumers.

### 15.1. In-flight messages during shutdown

During shutdown there are three groups:

1. Messages still **sitting on the broker** (not dispatched): not processed by the stopped container; behavior after restart depends on queue/topic/subscription/TTL.
2. Messages **delivered but not yet committed/ACKed**: may be redelivered after broker/consumer recovery.
3. Messages **already JMS-committed**: considered consumed by the broker; external business side effects may need reconciliation if a failure window occurred.

When an orchestrator sends SIGTERM or stops the service:
- Stop accepting new traffic / update readiness as appropriate.
- Give the container a chance to stop receiving new messages and let in-flight handlers finish within a bounded **grace period**.
- Set timeouts on DB/HTTP calls; never let handlers hang indefinitely.
- Keep JMS/DB transaction boundaries clear; idempotency protects against abrupt process termination.
- Measure shutdown duration and compare against Kubernetes `terminationGracePeriodSeconds` or runtime deadlines.

**Do not claim** "stop always waits for all business work to finish" under every configuration. A handler can be killed when the grace period expires, network I/O can hang, and exact behavior depends on container/provider settings.

## 16. Lifecycle Registry and Inspecting Endpoint Status

Containers created by `@JmsListener` **are not necessarily standalone beans in the ApplicationContext**. Spring manages them centrally via `JmsListenerEndpointRegistry`.

~~~java
Set<String> ids = registry.getListenerContainerIds();
for (String id : ids) {
    MessageListenerContainer listener =
            registry.getListenerContainer(id);
    System.out.println(id + " running="
            + (listener != null && listener.isRunning()));
}
~~~

This is a snippet; import `java.util.Set`, `JmsListenerEndpointRegistry`, and `MessageListenerContainer`, with `registry` injected into a Spring bean. If you need to control an endpoint, **set an explicit `id` in the annotation** rather than relying on generated IDs/registration order.

A container can be **RUNNING while the broker is unreachable** during recovery. Beyond `isRunning()`, inspect `isRecovering()` on Default containers, scheduled/active consumer task counts, broker consumer counts, oldest message age, DLQ, listener receive counts, and business DB outcomes.

**Do not misinterpret the registry's name:** it manages *listener container instances*, not all JMS connection pools, broker addresses, or message data. Those must be monitored in their respective infrastructure layers.

## 17. Queue, Topic, and Ordering When Increasing Consumer Count

### 17.1. Queue

With a queue `jobs.queue`, multiple consumers can compete to receive messages, usually boosting throughput. The broker decides dispatch and prefetch/credit; listeners running in parallel may finish **out of enqueue order**.

~~~text
Queue: M1, M2, M3, M4
    │      │
    ▼      ▼
Consumer A   Consumer B
  M1 takes 5s   M2 takes 100ms
  M3 ...        M4 ...

Processing outcome: M2 may commit before M1.
~~~

If ordering by aggregate `orderId` is required, use broker-supported partitioning/grouping, reduce concurrency for sensitive streams, or design event-version handling. Raising consumer counts alone cannot deliver both unbounded parallelism and strict total ordering.

### 17.2. Topic

A topic is pub/sub: multiple subscriptions can receive each topic event. Increasing consumer count carelessly can **multiply callbacks receiving the same message**. Durable subscriptions, shared subscriptions, client IDs, subscription names, and broker routing must match the intended topology.

**Do not copy-paste the queue "2-4 consumers for throughput" formula onto a topic.** Across multiple topic replicas, design shared durable/non-durable subscriptions per provider/JMS API or choose a queue for competing consumers. `pubSubDomain=true` only specifies a topic destination; it **does not automatically establish durable/shared semantics**.

## 18. Multi-Endpoint and Multi-Broker: Who Chooses ConnectionFactory?

An application may have:

~~~text
billingFactory         → billingBrokerCF      → billing.queue
auditFactory           → auditBrokerCF        → audit.topic
notificationFactory    → notificationBrokerCF → notify.queue
~~~

`@JmsListener(containerFactory="billingFactory")` selects an application-defined factory. With multiple `ConnectionFactory` beans, use `@Qualifier`, bean names, and `@Primary` carefully; Boot does not infer which destination belongs to which broker. Each factory/container has its own lifecycle and recovery, targeting the same or different brokers.

Do not confuse annotation ID with destination name:
- `id="billingListener"`: ID inside `JmsListenerEndpointRegistry` for observing and managing the endpoint.
- `destination="billing.queue"`: logical address to create consumers on.
- `containerFactory="billingFactory"`: factory bean name that creates the container.

A single method can be registered for multiple destinations via multiple `@JmsListener` annotations (repeatable annotation); that creates multiple endpoints/containers, so total consumers can increase.

### When selectors are used

Selectors filter on JMS headers/properties, not by parsing JSON bodies directly. An endpoint creating a consumer with a selector will not receive non-matching messages even if the queue holds many items; check property types. With multiple selectors, broker dispatch/fairness/prefetch can behave differently, so sizing must be based on operational measurements.

## 19. Observability: Monitoring Resources at the Right Layer

| Layer | Signals/metrics to monitor | Do not infer |
| --- | --- | --- |
| Spring registry | Endpoint IDs, `isRunning`, startup state | Broker is definitely connected |
| Default container | Scheduled/active consumer counts, `isRecovering`, receive/error logs | Number of business messages committed |
| TaskExecutor/JVM | Thread counts/states, executor queue, CPU/memory | More threads automatically equals higher throughput |
| Connection/provider | Physical connections, sessions, consumers, reconnects, auth errors | Each session = one TCP connection |
| Broker | Queue depth, in-flight, oldest message age, DLQ/expiry, dispatch | Queue depth 0 = business success |
| Handler | Started/succeeded/failed, processing latency, retries | Handler return = DB commit in all transactions |
| Business store | Commit counts, idempotency conflicts, invariant errors | JMS commit occurred if DB committed independently |

A good dashboard correlates **the same eventId/operationId** across producer, broker/consumer logs, and business DB; include `JMSMessageID` and `JMSXDeliveryCount` to trace individual messages. Never log tokens/passwords or sensitive data.

When the broker fails, inspect in order:
1. Which broker does `ConnectionFactory` actually target, and are credentials/ACLs valid?
2. Is the endpoint container registered and started?
3. What do `isRecovering`, recovery logs, and broker-side connections/consumers show?
4. What is the destination queue/topic, selector/filter, and backlog/in-flight state?
5. Did the handler throw an exception, fail conversion, roll back a transaction, or route to DLQ?
6. Was the final DB outcome committed?

Never extrapolate a single signal into the entire outcome.

## 20. Anti-Patterns to Avoid

1. **"Having `@JmsListener` means there is one consumer in the JVM"** — false; consumer count is decided by factory/concurrency.
2. **"The container creates a new thread for every message"** — no; invoker tasks process multiple messages sequentially.
3. **"One consumer equals one physical TCP connection"** — no; a connection can hold multiple sessions.
4. **"Increasing `max-concurrency` always increases throughput"** — no; the broker, DB, or external APIs may bottleneck.
5. **"More consumers on a topic means faster processing"** — no; they may be separate subscriptions receiving duplicate copies of the same event.
6. **"Calling `new InvoiceWorker()` runs the annotation automatically"** — no, the object must be Spring-managed.
7. **"Factory and container are a single bean"** — no; one factory can create multiple containers.
8. **"Container RUNNING proves the broker is connected"** — not when recovering.
9. **"Spring Boot's cache wrapper should be attached to every listener"** — listeners should usually use the native CF so the container manages recovery itself.
10. **"`CACHE_CONSUMER` and a connection pool are the same thing"** — no; scope and caching semantics differ.
11. **"Spawning threads inside a listener makes ACK safer"** — on the contrary, the listener can return/ACK before the business result.
12. **"A listener exception always makes the broker retry"** — depends on ACK/transaction mode and DLQ policy.
13. **"`sessionTransacted=true` automatically includes SQL commits"** — not with local JMS transactions.
14. **"`@JmsListener` automatically turns any payload into a JSON POJO"** — depends on `MessageConverter`/schema.
15. **"Stopping the container deletes the queue"** — no, queues are independent broker resources.
16. **"`shutdownNow`/cancel immediately aborts all JDBC/JMS/HTTP I/O"** — no universal guarantee.
17. **"Recovery interval = poison message redelivery delay"** — no; connection recovery and broker delivery policies are separate.
18. **"One `max-concurrency=10` applies application-wide"** — it typically applies **per listener endpoint/container**.
19. **"Default AUTO_ACK is always safe"** — no; in Default container it can ACK before listener execution.
20. **"Message listener finishing means the publisher received the business result"** — no; outcome protocols are a separate layer.

## 21. Progressive Verification Exercises

**Exercise 1 — Prove the container exists:** create a Spring Boot project with the Artemis starter and one `@JmsListener(id="jobs")`, inject `JmsListenerEndpointRegistry`, and print IDs and `isRunning`. Do not use `new Thread`.

**Exercise 2 — Inspect the actual class:** retrieve the endpoint from the registry, print `getClass().getName()`, and explain the difference between factory type, container type, and listener bean type.

**Exercise 3 — Thread ownership:** print `Thread.currentThread().getName()` in both publisher and listener. Send multiple messages and observe the listener running on consumer threads separate from the publisher.

**Exercise 4 — Min/max consumers:** configure `min-concurrency=1` and `max-concurrency=5`, create a test backlog, and observe `getScheduledConsumerCount()` and `getActiveConsumerCount()` over time; do not assume it always scales to 5.

**Exercise 5 — Queue ordering:** send M1–M10 with sequence numbers; compare concurrency 1 and 3. Observe actual processing/completion order instead of concluding from a single run.

**Exercise 6 — Broker outage:** stop the test broker, inspect container recovery/logs/backoff; restart it and verify consumer re-registration and resumed message reception. Never test this in production.

**Exercise 7 — Cache level:** test `CACHE_CONSUMER` with local JMS transactions vs `CACHE_NONE` in a test setup; measure resource churn and compare. Do not apply caching blindly when JTA/XA is present.

**Exercise 8 — Native vs cached factory:** inspect Boot's `ConnectionFactory` bean (wrapper), how the listener actually uses the native CF, and when `ConnectionFactoryUnwrapper` takes effect.

**Exercise 9 — Multi-endpoint capacity:** create two endpoints each with `concurrency=2-4`; project maximum total invoker tasks at 8 per replica, then verify via metrics rather than assuming physical connections are also 8.

**Exercise 10 — Exception/transaction:** configure a listener with `sessionTransacted=true`, intentionally throw before business commit, and observe rollback/redelivery or DLQ per broker. Compare with AUTO_ACK on Default container to see why behavior differs.

**Exercise 11 — DB commit followed by JMS commit failure:** inject a fault in that exact window, and verify `eventId`/unique constraint blocks duplicate business state when the broker redelivers.

**Exercise 12 — Graceful shutdown:** make the handler sleep 3–5 seconds, stop the context mid-processing, and observe in-flight handling, stop duration, JMS rollback/commit, and recovery after restart.

**Exercise 13 — Topic:** test a topic with two independent subscriptions vs a queue with two competing consumers. Explain why "duplicate receipt" can be the intended pub/sub semantics.

**Exercise 14 — Custom TaskExecutor:** configure executor capacity lower than the number of invoker tasks, measure executor queue/pending tasks, and explain starvation without immediately blaming the broker.

**Exercise 15 — Bad payload:** send a message the converter cannot parse, inspect error logs, whether the handler is invoked, broker redelivery, and DLQ policy.

### Checklist before completing the lesson

- [ ] Distinguish `@JmsListener`, `JmsListenerContainerFactory`, and `MessageListenerContainer`.
- [ ] Explain who owns `ConnectionFactory`, `Connection`, `Session`, `MessageConsumer`, and `TaskExecutor`.
- [ ] Know that the container holds lifecycle/recovery while the listener bean holds business logic.
- [ ] Distinguish `SimpleMessageListenerContainer` and `DefaultMessageListenerContainer`.
- [ ] Know when to use `@EnableJms` in plain Spring vs Boot 3.x auto-configuration.
- [ ] Understand `concurrentConsumers`/`maxConcurrentConsumers` and ordering impact.
- [ ] Never equate consumer count with physical connection count.
- [ ] Distinguish container `cacheLevel`, `CachingConnectionFactory`, and connection pools.
- [ ] Grasp the effects of `sessionTransacted`, AUTO_ACK, and the local DB commit gap.
- [ ] Know how to use `JmsListenerEndpointRegistry` to manage/inspect endpoints.
- [ ] Separate connection recovery from business retry and DLQ.
- [ ] Verify shutdown, broker restart, and idempotency via fault injection.
- [ ] Never spawn arbitrary threads inside a listener to offload uncommitted work to the background.

## 22. Official Documentation and Scope of Applicability

1. [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): compares the two containers, transactions, and caching.
2. [Spring Framework — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html): `@EnableJms`, `@JmsListener`, factories, registry, and concurrency configuration.
3. [Spring Framework 6.2 — DefaultMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html): receive loop, `TaskExecutor`, cache levels, recovery, scheduled/active consumer counts.
4. [Spring Framework 6.2 — DefaultJmsListenerContainerFactory Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html): setters mapped from factory to container.
5. [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html): listener containers, recovery capabilities, and acknowledgements.
6. [Spring Boot 3.5 — JMS](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html): Artemis auto-configuration, cached/native factories, and listener transaction defaults.
7. [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `spring.jms.listener.min-concurrency`, `max-concurrency`, `receive-timeout`, and `auto-startup`.
8. [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): JMS `Connection`/`Session`/`MessageConsumer`, threading, transactions, and redelivery.
9. [Spring Guide — Messaging with JMS](https://spring.io/guides/gs/messaging-jms/): sample Spring Boot application sending and receiving messages.

**Conclusion:** Spring's listener container is **the operational unit of a consumer**, not just a convenient annotation. The container manages receiving, threads, JMS resources, scaling, recovery, and shutdown; the application still must manage business transactions, idempotency, and outcome proof. To debug or scale properly, identify **the actual container, actual ConnectionFactory, actual concurrency, and actual broker state** rather than guessing from method names.