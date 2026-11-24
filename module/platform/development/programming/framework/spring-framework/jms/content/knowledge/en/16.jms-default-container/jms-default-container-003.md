# concurrentConsumers and maxConcurrentConsumers in Spring JMS DefaultMessageListenerContainer

## 1. Why Are Two Concurrency Parameters Needed?

When a Spring JMS application consumes a Queue, messages may arrive slowly at night yet spike during peak hours. With only **one consumer**, all messages are processed almost sequentially; one slow callback makes other messages wait. With **many fixed consumers** at all times, the application wastes connections/sessions, consumers, and threads even when the Queue is empty.

`org.springframework.jms.listener.DefaultMessageListenerContainer` (abbreviated **DMLC**) solves this trade-off with two bounds:

- **`concurrentConsumers`**: the core/minimum number of consumers scheduled to be maintained.
- **`maxConcurrentConsumers`**: the ceiling number of consumers the container can scale up to **when load increases**.

These two parameters describe **parallelism at the JMS consumer layer of a single listener container**, not the number of messages in a batch, number of Queues, HTTP threads, guaranteed TCP connections, Kubernetes replicas, or a guarantee that "exactly N tasks run at the same time".

This lesson helps you:

1. Distinguish `concurrentConsumers` and `maxConcurrentConsumers`, their default values, and effective scope.
2. Understand how DMLC calls `MessageConsumer.receive()`, schedules surplus consumers when the Queue is busy, and scales down when idle.
3. Configure via JavaConfig, `setConcurrency("2-5")`, Spring Boot properties, and `@JmsListener(concurrency = "...")`.
4. Run a Java 17+ / Spring Boot 3.5.8 / Apache ActiveMQ Artemis example with a Queue and a multi-worker listener.
5. Inspect **configured** consumer counts versus **scheduled/active** counts via the registry.
6. Tune scaling, prefetch, receive timeout, transactions, and thread executors while avoiding message ordering bugs.
7. Design tests/tuning based on actual backlog, throughput, latency, and resources.

This lesson is based on **Spring Framework 6.2.x** and **Jakarta Messaging 3.x** (`jakarta.jms.*`). Some parameters share names on other versions, but specific idle-scaling behavior may vary; always read the Javadoc for your application's exact version.

## 2. How Does DefaultMessageListenerContainer Operate?

DMLC is the standard listener container in Spring JMS. Unlike a program calling `jmsTemplate.receive(...)` manually, DMLC creates and manages **listener invoker tasks**. Each active invoker can hold its own `Session` and `MessageConsumer`, loop on `receive` calls, and invoke the business listener.

```text
                 Spring ApplicationContext
                           |
                  DefaultMessageListenerContainer
                           |
               +-----------+-----------+
               |           |           |
          Invoker #1    Invoker #2   Invoker #3 ... #N
               |           |           |
           Session 1   Session 2    Session 3
               |           |           |
           Consumer 1  Consumer 2   Consumer 3
               \           |           /
                \          |          /
                   JMS Queue on broker
                           |
                    MessageListener
                  (@JmsListener/POJO)
```

Conceptually:

1. When the container starts, it prepares at least the configured number of core consumers.
2. An invoker waits for a message from `MessageConsumer.receive(...)` for up to `receiveTimeout`.
3. If a message arrives, the invoker calls the corresponding listener and completes acknowledgment/transaction per the container.
4. If more messages arrive and current invokers are all busy, DMLC **may** schedule additional invokers/consumers, up to the `maxConcurrentConsumers` ceiling.
5. When Queue load drops, **surplus consumers above the core count** can become idle and be reclaimed according to timeout/idle-task conditions.
6. Core consumers are retained to maintain receiving readiness, except during container stop/shutdown/recovery.

Increasing consumers makes the most sense for a **Queue with competing consumers**. For a regular Topic, creating multiple consumers on the same Topic can cause **each subscription to receive the same publication**, causing duplicate processing within a single instance. See section 10 before increasing concurrency for a Topic.

### 2.1. One Consumer Does Not Necessarily Equal One Permanent Physical Thread

In the default configuration, DMLC uses a `TaskExecutor` to run listener invokers; an invoker may use a thread to wait on receive and process callbacks. However:
- A **scheduled** task is not always **running** (the executor may be saturated).
- An **active** consumer does not mean it is **processing a useful message**; it could be waiting in `receive`.
- Sessions/consumers may be reused or recreated depending on cache level, transaction manager, and broker errors.
- Java 21+ and Spring Framework 6.2 allow opting into virtual threads for the default executor via `setVirtualThreads(true)`; **the Java 17 example in this lesson does not use this feature**.

Therefore, looking at JVM thread counts or Queue depth alone is not enough to determine how many consumers are receiving.

## 3. concurrentConsumers: The Maintained Core Level

DMLC declares:

```java
container.setConcurrentConsumers(2);
```

Meaning: the container tries to maintain **two scheduled core consumers** during normal operation. DMLC's default value is **1**.

Characteristics:

- Must be an integer **greater than or equal to 1**.
- Increasing from 1 to 2 increases the ability to process two different messages in the Queue concurrently, provided the broker has sufficient messages/permissions/resources.
- Setting 4 means a core level of 4, **not** a guarantee that four messages are being processed at all times.
- When the Queue is empty, core consumers can still keep waiting on receive.
- Raising the core level also affects idle resources: sessions, consumer registrations, thread tasks, and broker memory/prefetch.
- For a low-volume Queue requiring ordering, keeping `concurrentConsumers=1` is usually sensible.

**Important trap:** calling `setConcurrentConsumers(4)` while the old max was 1 will cause Spring to ensure max is **not less than core**. To configure a range of 4..8, set both values rather than changing only core and assuming unlimited scaling.

`getConcurrentConsumers()` returns the **current configuration**, not the number of active consumers. To observe runtime state, use `getScheduledConsumerCount()` and `getActiveConsumerCount()`.

## 4. maxConcurrentConsumers: The Load Scaling Ceiling

DMLC declares:

```java
container.setMaxConcurrentConsumers(6);
```

Meaning: when load increases, DMLC **can open additional consumers**, from the core level up to at most **6 consumers** for **this container**; the default max is also **1**. If max equals core, **there is no dynamic scaling range**.

Example:

```java
container.setConcurrentConsumers(2);
container.setMaxConcurrentConsumers(6);
```

When idle, the goal is to maintain 2 core consumers. When incoming message volume and processing time keep invokers busy, the container can scale up to 3, 4, 5, 6 consumers. When load subsides, surplus invokers can stop while the 2 core consumers keep waiting.

**Do not misunderstand:**

- `maxConcurrentConsumers=6` **does not mean 6 consumers are created immediately at startup**.
- `maxConcurrentConsumers=6` **does not mean 6 messages are always processed in parallel**.
- It **does not spin up 6 extra replicas**, create 6 Queues, or promise 6 TCP connections (connections can be shared).
- It is a limit for **one instance of one listener container**, not a cluster-wide ceiling.
- It is a **configured ceiling**, not a "target CPU utilization" or direct Queue-length auto-scaler.

### 4.1. Default Values

| DMLC Parameter | Default | Meaning |
| --- | ---: | --- |
| `concurrentConsumers` | 1 | Number of core consumers maintained. |
| `maxConcurrentConsumers` | 1 | Consumer ceiling; when both equal 1 there is no dynamic scaling. |
| `receiveTimeout` | 1,000 ms | Wait duration of a single receive call, affecting how idle state is detected. |
| `idleConsumerLimit` | 1 | Limit on idle consumers allowed before creating additional invokers. |
| `idleTaskExecutionLimit` | 1 | Number of task executions marked idle before a surplus consumer may stop. |

On Spring Framework 6.2 with the default executor, the effective `idleReceivesPerTaskLimit` is typically **10 consecutive receives returning null** for surplus consumers. With `receiveTimeout=1s` and normal conditions, scale-down can happen after roughly 10 idle seconds—**not a hard 10-second SLA**. When using a `SchedulingTaskExecutor` preferring short-lived tasks, `maxMessagesPerTask` has different defaults/reschedule cadence. Idle scaling numbers are implementation details, not rigid guarantees regardless of environment.

## 5. Ways to Declare Concurrency — and Syntax Traps

### 5.1. Calling the Two Setters on DefaultMessageListenerContainer

```java
DefaultMessageListenerContainer container =
        new DefaultMessageListenerContainer();

container.setConcurrentConsumers(2);
container.setMaxConcurrentConsumers(5);
```

This is a snippet within JavaConfig that already configures other parameters such as `ConnectionFactory`, destination, and `MessageListener`. It cannot run standalone with just these two setters.

### 5.2. Using a Single setConcurrency String

Spring supports:

```java
container.setConcurrency("2-5"); // core=2, max=5.
container.setConcurrency("5");   // core=1, max=5.
```

**Specifically:** a single-number string `"5"` with DMLC is interpreted as **upper limit 5, core 1**, **not fixed 5 consumers**. To get **fixed 5**, set both core and max to 5:

```java
container.setConcurrency("5-5");
```

Meaning table:

| Configuration | Core | Max | Behavior |
| --- | ---: | ---: | --- |
| Not configured | 1 | 1 | One core consumer, no scaling up. |
| `"1-1"` | 1 | 1 | Equivalent to default. |
| `"2-5"` | 2 | 5 | Keeps around two core, can scale up to five. |
| `"1-8"` | 1 | 8 | Saves idle resources but may scale up more slowly during bursts. |
| `"5"` | 1 | 5 | **One core**, ceiling five. |
| `"5-5"` | 5 | 5 | Five fixed consumers per core/ceiling config. |

`setConcurrency` and the setters require valid values. Avoid zero, negative numbers, `"two-five"`, malformed whitespace, or reversed ranges like `"5-2"`; validate configuration at startup rather than accepting nonsensical configs. The implementation may clamp max up to at least core, which is no reason to intentionally write reversed ranges.

### 5.3. Setting on DefaultJmsListenerContainerFactory

With `@JmsListener`, containers are created by the factory, so configuration usually goes here:

```java
@Bean(name = "jmsListenerContainerFactory")
DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory) {

    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setConcurrency("2-5");
    factory.setSessionTransacted(true);
    return factory;
}
```

This is a snippet requiring imports for `jakarta.jms.ConnectionFactory`, `org.springframework.jms.config.DefaultJmsListenerContainerFactory`, and `@Bean` in a configuration class. The factory passes options to each created `DefaultMessageListenerContainer`. Mutating the factory after containers are running **does not automatically reconfigure all existing containers**.

### 5.4. Per-@JmsListener Override

If all listeners use a default `"2-5"` factory, yet one Queue needs fewer consumers:

```java
@JmsListener(
        id = "paymentsListener",
        destination = "payments.queue",
        concurrency = "1-2")
public void onPayment(String body) {
    // Process payment.
}
```

This is a snippet inside a Spring bean with `@EnableJms` enabled. The endpoint's `concurrency` attribute **overrides the factory value** if supported by the container. Do not mistake `concurrency="2"` for a guaranteed fixed two consumers: with DMLC, a single number means core 1, max 2; for fixed 2 use `"2-2"`.

### 5.5. Spring Boot Properties

If you **use the factory auto-configured by Spring Boot** (without replacing it with a manual bean), Spring Boot 3.5 provides:

```properties
spring.jms.listener.min-concurrency=2
spring.jms.listener.max-concurrency=5
```

At Boot's abstraction layer, `min-concurrency` corresponds to minimum/core; `max-concurrency` is the maximum. The older `spring.jms.listener.concurrency` property was deprecated since Boot 3.2; prefer `min-concurrency` instead of copying outdated configs.

**Integration point:** when you manually define a `jmsListenerContainerFactory` bean with `new DefaultJmsListenerContainerFactory()`, Boot may back off from creating the default factory, and those two properties **will not automatically bind to your custom bean**. You must call `setConcurrency("2-5")` yourself or use `DefaultJmsListenerContainerFactoryConfigurer` to re-apply Boot settings before overriding specific parts.

Example using the configurer, **replacing** the pure manual factory example above:

```java
@Bean(name = "jmsListenerContainerFactory")
DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory,
        DefaultJmsListenerContainerFactoryConfigurer bootConfigurer) {

    var factory = new DefaultJmsListenerContainerFactory();
    bootConfigurer.configure(
            factory,
            ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));

    // Application-specific settings can be overridden here.
    factory.setSessionTransacted(true);
    return factory;
}
```

This snippet is for Spring Boot 3.5 with imports `org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer` and `org.springframework.boot.jms.ConnectionFactoryUnwrapper`, not a standalone Java file. When used, choices around unwrapping/caching/transaction manager must fit Spring Boot/the provider. The full project example in section 7 uses **explicit manual configuration**, so it does not set min/max via Boot properties to avoid competing configuration sources.

## 6. Scaling Mechanism: Scale Up Gradually, Reclaim on Idle

Consider `concurrentConsumers=2`, `maxConcurrentConsumers=5`:

```text
Time            Queue Load                   Expected Consumers
--------        ----------                   ------------------
08:00           Queue empty                  ~2 (core)
09:00           A few messages arrive        2 (usually enough)
09:05           Backlog grows, listeners busy 2 -> 3 -> 4 -> 5 (possible)
09:10           Continuous heavy load        <=5
09:30           Queue drains                 5 -> 4 -> 3 -> 2 (on idle)
10:00           Queue empty                  ~2 (core)
```

This is an **illustrative timeline**, not a fixed measurement chart from Spring. You cannot promise 5 consumers will open after exactly 3 messages or 1 second. Scheduling a new invoker depends on invoker state, `TaskExecutor` thread availability, whether idle consumers already exist, how often `receive` returns messages, and which consumer the broker delivers to.

### 6.1. idleConsumerLimit

`setIdleConsumerLimit(int)` sets the limit on idle consumers permitted when considering creating a new invoker. Default is **1**, meaning the container will not open more when a suitable idle consumer already exists. Raising it to a larger value can make the system **scale up more aggressively**, at the cost of extra consumers/threads when load is insufficient.

```java
container.setIdleConsumerLimit(2);
```

This is a DMLC configuration snippet in an appropriate bean; it is not a switch to "always keep two idle consumers". It only affects scheduler conditions and does not raise the max if `maxConcurrentConsumers` is still 1.

### 6.2. idleTaskExecutionLimit

`setIdleTaskExecutionLimit(int)` specifies after how many task executions marked idle a surplus consumer may be stopped. Default is **1**. Core consumers are retained under normal conditions.

```java
container.setIdleTaskExecutionLimit(3);
```

Raising the limit can reduce invoker churn when load has brief gaps, at the trade-off of holding resources longer. The concept of *task execution* is not identical to a single message and not necessarily identical to a single `receive`.

### 6.3. idleReceivesPerTaskLimit in Spring 6.2

`setIdleReceivesPerTaskLimit(int)` determines after how many **receive attempts returning no message (`null`)** a surplus consumer is marked idle within a task. With Spring 6.2's default executor, the effective default is typically **10 null receives**. DMLC also uses `idleTaskExecutionLimit` to decide whether to reclaim the surplus invoker.

```java
container.setIdleReceivesPerTaskLimit(20);
container.setReceiveTimeout(1_000L);
```

Simple model: if the Queue is truly idle and each receive waits roughly 1 second before returning null, 20 rounds correspond to roughly 20 seconds **under ideal conditions**. Do not treat this as a hard SLA because thread scheduling, broker, task executor, and other policies can alter behavior.

If `receiveTimeout` is set very high, DMLC may take a long time to detect idle state/scale down. If set very small while scaling consumers aggressively, an empty Queue can generate more receive/poll cycles, increasing baseline overhead.

### 6.4. maxMessagesPerTask, TaskExecutor, and Virtual Threads

`maxMessagesPerTask` counts **receive attempts**, including timeouts with no message, not purely successful message processings. With a typical default `TaskExecutor`, the default can be **-1 (unlimited)** so a task runs long-lived; with a `SchedulingTaskExecutor` preferring short-lived tasks, the default can be **10 receive attempts** so tasks are rescheduled frequently.

Therefore, tuning just one idle variable may not suffice; look at the whole set:
- `concurrentConsumers` / `maxConcurrentConsumers`.
- `receiveTimeout`.
- `idleConsumerLimit`.
- `idleTaskExecutionLimit`.
- `idleReceivesPerTaskLimit`.
- `maxMessagesPerTask`.
- `TaskExecutor` and worker thread capacity.

If you attach a fixed thread pool sized **smaller than max consumers**, even with max=10, invokers cannot all run concurrently. With Java 21+ and Spring Framework 6.2, you can consider virtual threads (`setVirtualThreads(true)` on the default executor) to reduce cost while invokers wait on I/O; **virtual threads do not make the broker or database faster**, and the Java 17 example here does not enable them.

## 7. Complete Spring Boot Example: Core 2, Max 5

We build an application with **one Queue**, one `@JmsListener`, and a factory creating a `DefaultMessageListenerContainer`. The code sends **12 messages**; the listener simulates each job taking about 400 ms so we have a chance to observe multiple workers operating.

**Prerequisites to run:**
- Java 17+, Maven.
- An external Apache ActiveMQ Artemis broker at `tcp://localhost:61616` or another endpoint you supply.
- Credentials with send/consume permissions.
- Queue `demo.concurrent.queue` provisioned with proper routing or broker auto-create enabled.
- Clean demo Queue initially with no other consumers if you want to verify all 12 callbacks.

Without a broker you can still build the project, but you cannot verify actual concurrency.

### 7.1. Project Structure

```text
jms-concurrency-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── example/
        │       └── jms/
        │           ├── ConcurrencyDemoApplication.java
        │           ├── JmsListenerConfig.java
        │           └── WorkMessageListener.java
        └── resources/
            └── application.properties
```

### 7.2. pom.xml

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
    <artifactId>jms-concurrency-demo</artifactId>
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

The Artemis starter brings Spring JMS and the Jakarta-compatible Artemis client via Boot's dependency management. Do not mix legacy `javax.jms-api` with Spring Framework 6.x (`jakarta.jms.*`).

### 7.3. application.properties

```properties
spring.artemis.mode=native
spring.artemis.broker-url=${JMS_BROKER_URL:tcp://localhost:61616}
spring.artemis.user=${JMS_USERNAME}
spring.artemis.password=${JMS_PASSWORD}

spring.jms.pub-sub-domain=false

# Demo does not use an extra CachingConnectionFactory outside DMLC.
spring.jms.cache.enabled=false
```

**Note:** The application uses a **manually declared** `DefaultJmsListenerContainerFactory`, so min/max concurrency resides in JavaConfig below. Do not put `spring.jms.listener.min-concurrency` / `max-concurrency` in the same demo expecting them to auto-override a manual factory.

`spring.jms.cache.enabled=false` lets the listener container manage caching/refresh/recovery of connections/sessions/consumers itself without mixing in an external cache wrapper in the demo. In real operations, you can use a dedicated factory/pool for producers and choose an appropriate cache level for listeners; no single choice is optimal for every provider.

### 7.4. Configuring the Listener Container Factory

**`src/main/java/example/jms/JmsListenerConfig.java`**

```java
package example.jms;

import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration(proxyBeanMethods = false)
@EnableJms
public class JmsListenerConfig {

    @Bean(name = "jmsListenerContainerFactory")
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false);
        factory.setConcurrency("2-5");
        factory.setSessionTransacted(true);
        factory.setReceiveTimeout(1_000L);
        return factory;
    }
}
```

`factory.setConcurrency("2-5")` is shorthand equivalent to **`concurrentConsumers=2` and `maxConcurrentConsumers=5`** for the DMLC produced by the factory. The code does not need to manually `new DefaultMessageListenerContainer` or call `start()`; the Spring container lifecycle handles it.

`setSessionTransacted(true)` enables a **local JMS transaction** per callback: on success the container commits, if an exception escapes the listener it rolls back, and the broker can redeliver per policy. This transaction does not automatically encompass SQL or HTTP.

`setReceiveTimeout(1_000L)` illustrates the 1-second timeout of a `MessageConsumer.receive` attempt inside DMLC, **not a business message processing deadline**, and it does not dictate that a message must finish within 1 second. Changing this timeout affects idle/scaling and the poll loop.

### 7.5. Listener Simulating Work

**`src/main/java/example/jms/WorkMessageListener.java`**

```java
package example.jms;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class WorkMessageListener {

    private final CountDownLatch callbacks = new CountDownLatch(12);
    private final AtomicInteger processedCallbacks = new AtomicInteger();

    @JmsListener(
            id = "workListener",
            destination = "demo.concurrent.queue",
            containerFactory = "jmsListenerContainerFactory")
    public void handle(String body) throws InterruptedException {

        String worker = Thread.currentThread().getName();
        System.out.println("received=" + body + " worker=" + worker);

        // Simulate 400ms logic, not CPU-heavy.
        Thread.sleep(400L);

        processedCallbacks.incrementAndGet();
        callbacks.countDown();
    }

    public boolean awaitAll(long timeout, TimeUnit unit)
            throws InterruptedException {
        return callbacks.await(timeout, unit);
    }

    public int callbackCount() {
        return processedCallbacks.get();
    }
}
```

Here `@JmsListener` uses the default message converter to receive the `TextMessage` body as a `String`. Because there are multiple consumers, **the same `WorkMessageListener` Spring bean can be invoked concurrently on multiple threads**. Thus the counter uses `AtomicInteger` and the latch uses `CountDownLatch`.

**Do not treat log line order as processing order.** Message `task-7` can finish before `task-6` due to different workers. `Thread.sleep(400)` only simulates work; production must measure latency of real DB/HTTP processing and enforce appropriate timeouts and retries.

**Transaction note:** the counter/latch is updated **before DMLC commits the JMS transaction** (commit happens after the method returns). Thus, counting 12 callbacks does not by itself prove 12 guaranteed JMS commits. An in-memory counter also does not roll back when a JMS transaction rolls back; production needs durable metrics and state.

### 7.6. Main + Monitoring Concurrency via Endpoint Registry

**`src/main/java/example/jms/ConcurrencyDemoApplication.java`**

```java
package example.jms;

import java.util.concurrent.TimeUnit;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.listener.DefaultMessageListenerContainer;
import org.springframework.jms.listener.MessageListenerContainer;

@SpringBootApplication
public class ConcurrencyDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConcurrencyDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner runDemo(
            JmsTemplate jmsTemplate,
            WorkMessageListener listener,
            JmsListenerEndpointRegistry registry) {

        return args -> {
            MessageListenerContainer base =
                    registry.getListenerContainer("workListener");

            if (!(base instanceof DefaultMessageListenerContainer dmlc)) {
                throw new IllegalStateException(
                        "Expected DefaultMessageListenerContainer");
            }

            System.out.printf(
                    "configuredCore=%d configuredMax=%d%n",
                    dmlc.getConcurrentConsumers(),
                    dmlc.getMaxConcurrentConsumers());

            for (int index = 1; index <= 12; index++) {
                jmsTemplate.convertAndSend(
                        "demo.concurrent.queue", "task-" + index);
            }

            boolean allCallbacks =
                    listener.awaitAll(30, TimeUnit.SECONDS);

            System.out.println("callbacksObserved=" + allCallbacks);
            System.out.println("callbackCount=" + listener.callbackCount());

            // A snapshot, not guaranteed to always equal max.
            System.out.printf(
                    "scheduledSnapshot=%d activeSnapshot=%d%n",
                    dmlc.getScheduledConsumerCount(),
                    dmlc.getActiveConsumerCount());

            if (!allCallbacks) {
                throw new IllegalStateException(
                        "Not all callbacks ran within 30 seconds");
            }
        };
    }
}
```

**This is a runnable Java Spring Boot project at the code level when matching dependencies and broker are present.** Package names are consistently `example.jms`, and `@SpringBootApplication` scans the listener and configuration. `@EnableJms` in `JmsListenerConfig` enables annotation infrastructure, and the registry manages the container created by the factory.

The first two getters are **configured values**; `getScheduledConsumerCount()` and `getActiveConsumerCount()` are **dynamic snapshots**. If the snapshot is printed after all 12 callbacks have run, DMLC may still be holding a few surplus consumers or beginning to scale down; there is no fixed pair of snapshot numbers to hardcode in tests.

### 7.7. Running the Project

PowerShell:

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

Replace `dev-user`/`dev-password` with real Artemis credentials. If the Queue does not exist and auto-create is disabled, provision `demo.concurrent.queue` on the broker. If the broker is not running or permissions are insufficient, the app may build but sending/receiving will fail.

Build without connecting to the broker:

```bash
mvn -q -DskipTests package
```

**Illustrative output (excerpt of lines printed by the application, excluding Spring/Artemis logs):**

```text
configuredCore=2 configuredMax=5
received=task-1 worker=...
received=task-2 worker=...
received=task-3 worker=...
... (other tasks, thread order is not fixed)
callbacksObserved=true
callbackCount=12
scheduledSnapshot=... activeSnapshot=...
```

`...` here is a **notation for runtime-varying output**, not a literal string the code must print. If exact assertions are needed in tests, only assert the configured values `configuredCore=2 configuredMax=5`, and in an isolated Queue environment, that successful callbacks equal 12. Do not assert that allocated threads equal 5 or that logs always appear in order 1..12.

In this example, the application stays running because the listener container remains active after `ApplicationRunner`. Stop with Ctrl+C. To observe autoscaling more clearly, send a larger number of messages and monitor snapshots while the listener is running (via metrics/JMX or an operations endpoint), rather than printing once at the end.

## 8. Configuring DefaultMessageListenerContainer Directly with @Bean

If you do not use `@JmsListener` and have a plain `MessageListener` bean, you can configure the container **directly**:

```java
@Bean
DefaultMessageListenerContainer directContainer(
        ConnectionFactory connectionFactory,
        MessageListener listener) {

    var container = new DefaultMessageListenerContainer();
    container.setConnectionFactory(connectionFactory);
    container.setDestinationName("jobs.queue");
    container.setMessageListener(listener);
    container.setPubSubDomain(false);
    container.setConcurrentConsumers(2);
    container.setMaxConcurrentConsumers(5);
    container.setSessionTransacted(true);
    return container;
}
```

**This is an alternative snippet** to the annotation container, not a required addition to the full project. It requires imports for `jakarta.jms.ConnectionFactory`, `jakarta.jms.MessageListener`, `org.springframework.jms.listener.DefaultMessageListenerContainer`, and `org.springframework.context.annotation.Bean`. If added to the same Queue as the annotation listener in section 7, you create **two competing consumer groups** rather than modifying the existing one.

Min/max values apply **to that specific container bean**. If you declare three DMLC beans, each with a ceiling of five, potential total consumers can reach 15 within the same JVM (depending on broker/`TaskExecutor`), not five shared application-wide.

Do not proactively call `container.start()` inside a `@Bean` method just to "be sure it is receiving": let the Spring lifecycle call it. Likewise, when the bean stops, Spring handles shutdown appropriately.

## 9. Queue, Topic, and the Truth About Message Ordering

### 9.1. Queue with Competing Consumers

With Queue `orders.queue`, three consumers can receive different messages:

```text
Queue: [M1] [M2] [M3] [M4] [M5] ...
             |     |     |
          Consumer A  B    C
          process 500ms 100ms 300ms
```

Due to differing processing times, **B can finish a message after A's before A finishes**, even if the broker dispatches in a logical order. When concurrency increases:
- Throughput typically increases if callbacks are I/O-bound and the backend has spare capacity.
- **Processing completion** order is not guaranteed to match send order.
- Messages with the same business key may be processed in parallel without grouping.
- Rollbacks, redelivery, priority, expiration, and broker prefetch can make actual delivery order hard to infer from producer send order.

If the business requirement is **updating the state of a single order in sequence**, decide on partitioning/message grouping by `orderId`, serializing per key, or keeping one consumer for strictly FIFO streams. Artemis supports provider-level message grouping; consult Artemis documentation and verify your cluster/routing before relying on grouping.

### 9.2. Topics Can Process Duplicate Publications

For a standard JMS Topic, each subscription can receive a copy of a message. If you set multiple consumers without properly sharing a subscription, you may receive the **same publication multiple times** inside a single node. Spring DMLC Javadoc warns **not to increase concurrent consumers for a Topic** unless an appropriate vendor/shared-subscription configuration is in place.

Therefore:
- **Queue:** can use `concurrentConsumers > 1` to process work via the competing-consumer pattern.
- **Non-shared Topic:** typically keep `1` consumer per subscription.
- **Shared/durable Topic:** design subscription name/client ID/shared semantics per Jakarta Messaging/provider before considering concurrency.

Do not mechanically copy a `"2-5"` setting that worked for a Queue over to a production Topic.

### 9.3. Concurrency Cannot Replace Idempotency

Suppose the DB commits, then the JMS receive transaction rolls back due to a network error. The broker can redeliver the same business event. Another consumer in the group may pick up that event. If the handler is not idempotent, increasing concurrency makes duplicate side effects even harder to spot.

Use a business `eventId`/inbox/deduplication logic with a unique constraint and control DB transactions. `JMSMessageID` is useful for tracing, but is not always the best business key when a publisher might resend the same event in a new message.

## 10. Transactions, Acknowledgment, and the Impact of Concurrency

### 10.1. Local JMS Transaction in the Container

`factory.setSessionTransacted(true)` makes each listener execution in DMLC use a local JMS transaction. When the callback finishes normally, the container commits the receive. When the callback throws an exception to the container, it rolls back, and the broker can redeliver per policy.

With concurrency 2..5, **each consumer/session** has its own transaction; there is no "global transaction" spanning all messages processed concurrently across consumers. If message A succeeds, A's transaction can commit even if message B on another consumer fails.

### 10.2. AUTO_ACKNOWLEDGE Carries Risk When Callbacks Fail

Spring DMLC Javadoc notes that in `AUTO_ACKNOWLEDGE`, acknowledgment may occur **before** the listener executes. If the callback subsequently throws an exception, you do not necessarily get reliable redelivery. For critical work Queues, `sessionTransacted=true` is usually the safer choice (verify broker policy, DLQ, and business semantics).

### 10.3. A Spring JMS Transaction Is Not Atomic with the Database

`sessionTransacted=true` is only a **local JMS transaction**. It does not automatically include SQL statements in the same atomic commit. Under high load, multiple consumers may write to the database concurrently:
- Raising `maxConcurrentConsumers` can put pressure on the JDBC connection pool.
- DB lock contention and deadlocks can increase.
- Retries/redeliveries can generate multiple DB calls for the same event.
- If the DB transaction commits while the JMS commit fails, duplicates can still occur.

For systems with a DB, you need an idempotent consumer/inbox, sufficient connection pool capacity, lock policies, and clear transaction boundaries. If distributed transactions are required, evaluate true JTA/XA or an outbox/inbox design rather than blindly adding `@Transactional`.

### 10.4. Retry Thresholds and Dead-Letter Queues

When a message fails and rolls back repeatedly:
- The broker can redeliver according to delay/backoff.
- Once `max-delivery-attempts` or an equivalent policy is exceeded, it can move to a DLQ.
- A fast-retried poison message can keep a consumer busy, reducing actual throughput even with a high max.

Set redelivery counts, delays, DLQ, and alerts according to business requirements; do not simply raise concurrency to mask poison message errors.

## 11. Observing Configuration vs. Reality with Getters

DMLC provides these methods:

```java
int core = container.getConcurrentConsumers();
int max = container.getMaxConcurrentConsumers();

int scheduled = container.getScheduledConsumerCount();
int active = container.getActiveConsumerCount();

boolean running = container.isRunning();
```

This is a **snippet** when `container` is a `DefaultMessageListenerContainer` and has been properly configured/started.

Distinguish the four numbers:

| Getter | Returns | Used To |
| --- | --- | --- |
| `getConcurrentConsumers()` | Configured core consumers | Confirm min/core has been applied. |
| `getMaxConcurrentConsumers()` | Configured consumer ceiling | Confirm upper limit of the container. |
| `getScheduledConsumerCount()` | Scheduled consumer invokers | Observe actual scaling at a point in time. |
| `getActiveConsumerCount()` | Active consumer invokers | Detect gaps between scheduled and executing (e.g., executor thread starvation). |

If `scheduled=5` and `active=3`, it does not necessarily mean two consumers died: they may be **scheduled but not yet running** or in a transitional state. Cross-check logs, executor, broker consumer count, and sample over time.

**Do not treat `active` as "number of messages currently being processed"**. An invoker can be active while waiting on `receive` until timeout on an empty Queue. To measure running business callbacks, create a separate gauge: increment on listener entry and decrement in `finally`, while also measuring processing latency and callback exceptions.

### 11.1. Retrieving the Container from the @JmsListener Endpoint Registry

`@JmsListener(id = "workListener", ...)` enables lookup:

```java
MessageListenerContainer base =
        registry.getListenerContainer("workListener");

if (base instanceof DefaultMessageListenerContainer dmlc) {
    System.out.printf(
            "core=%d max=%d scheduled=%d active=%d%n",
            dmlc.getConcurrentConsumers(),
            dmlc.getMaxConcurrentConsumers(),
            dmlc.getScheduledConsumerCount(),
            dmlc.getActiveConsumerCount());
}
```

This is a snippet inside a Spring bean that has `JmsListenerEndpointRegistry registry`. An endpoint container managed by the registry is not necessarily a Spring bean that can be `@Autowired` directly by the same ID.

### 11.2. Monitoring from the Broker and System

Spring runtime metrics are only half the picture. Also monitor:
- Queue messages ready/pending and in-flight/delivering.
- Actual consumer count on the broker, distributed by connection/node.
- Incoming/enqueue and outgoing/dequeue rates, and message wait age.
- Redelivery count, DLQ count, expired message count.
- JVM CPU/memory, task executor thread count, and GC.
- DB pool active/waiting, HTTP client pool, downstream latency/error rate.
- Business callback gauge, duration (p50/p95/p99), retries, and idempotency hit rate.

Most accurate is viewing these metrics **on the same timeline**. Reaching max=5 without backlog shrinking may indicate a DB bottleneck rather than a lack of JMS consumers.

## 12. A Guiding Formula Before Increasing Concurrency

Suppose each callback performs an independent task taking an average of **200 ms**, with no CPU/DB/broker bottlenecks:

- One consumer ideally processes roughly `1 / 0.2 = 5 messages/second`.
- Four consumers ideally process roughly `4 / 0.2 = 20 messages/second`.
- However, this is an **ideal upper-bound approximation**, not a guarantee. Reality includes network, polling, transaction commits, prefetch, locking, and load skew.

To choose core/max levels, measure:

```text
arrival rate             = incoming messages per second
average processing time  = processing time per message (seconds)
required concurrency     ≈ arrival rate x processing time
```

For example, with an average arrival rate of 12 messages/second and 0.25 seconds per message: roughly `12 × 0.25 = 3` concurrent callbacks are needed to keep up **in the ideal case**. Add headroom for p95/p99, bursts, and downstream variance, while also capping by the DB connection pool and system capacity.

**Do not use the ideal formula to blindly set max=100.** If the service DB only handles 10 concurrent queries, max=100 can complicate queuing/threading and decrease throughput due to contention.

### 12.1. Tuning by Workload

| Workload | Starting Point | Why |
| --- | --- | --- |
| Very low-volume Queue needing FIFO business order | `1-1` | Simple, low resources, reduces risk of parallel execution. |
| Steady Queue, independent processing | `2-4` | Core covers normal load, max handles bursts. |
| Queue with occasional large bursts | `1-6` | Low idle resources; scales up gradually when needed. |
| Consumer mostly waiting on HTTP/DB with spare downstream capacity | Higher core/max after measurement | I/O wait can be masked by concurrency. |
| CPU-heavy consumer | Limit by CPU cores/benchmarking | Too many threads cause context switching/GC. |
| Non-shared Topic subscription | Usually `1-1` | Prevents duplicate publication processing. |

This table is a **starting point for benchmarking**, not a rigid formula; verify p95 latency, broker throughput, DB load, and retry policies.

## 13. Prefetch, Broker, and Consumer Contention

Sometimes core 2/max 5 is set and the broker holds thousands of messages, yet CPU is busy on only a couple of consumers. The cause may be the provider **prefetching** a large batch of messages to individual consumers, causing uneven distribution.

Illustrative example:

```text
Broker Queue has 100 messages
     |
     +-- Consumer A prefetched many messages, processing sequentially
     +-- Consumer B received few messages
     +-- Consumer C newly created, has no messages yet
```

At this point raising max may not reduce latency. You should:
- Check Artemis consumer window/flow control and routing settings; do not treat ActiveMQ Classic property names as identical to Artemis.
- Check how many messages the broker reports **in delivery** versus **ready**.
- Measure per-consumer processing speed, uneven partitions, and poison messages.
- Tune prefetch/window size empirically rather than changing it randomly.
- Check send/consume permissions, queue bindings, selectors, and any filters.

**Do not infer from Queue depth alone:** 100 ready messages differ from 100 messages already dispatched to a consumer but uncommitted.

### 13.1. Multiple Replicas Multiply Total Consumers

If each instance has `concurrentConsumers=2`, `maxConcurrentConsumers=5` and you run **4 replicas**, theoretical configured capacity can be:

```text
Per replica: 2 ... 5 consumers
4 replicas : 8 ... 20 consumers (total configured)
```

This is why JMS concurrency must be coordinated with **horizontal pod autoscaling**. If each replica scales to max when backlog grows, and the autoscaler also adds replicas, total consumers can overwhelm the database/broker. Track total consumer counts and downstream budgets.

## 14. Common Mistakes and Troubleshooting Guide

| Symptom / Misconception | Possible Cause | Resolution |
| --- | --- | --- |
| Set `maxConcurrentConsumers=5` but always see 1 | Core defaults to 1, load insufficient, idle consumers remain, executor lacks threads, or skewed broker prefetch | Apply sustained load, measure scheduled/active and broker; check `TaskExecutor`/idle settings. |
| Set `setConcurrency("5")` expecting fixed 5 | With DMLC, `"5"` means min 1/max 5 | Use `"5-5"` or set both setters to 5. |
| Raising `concurrentConsumers` altered processing order | Multiple consumers run callbacks concurrently | Keep 1 if FIFO is needed, or design grouping/partitioning by business key. |
| Raising max caused duplicate processing on Topic | Non-shared Topic has multiple independent subscriptions | Keep concurrency 1 or configure shared subscription properly. |
| High backlog but `active < scheduled` | Executor lacks worker threads, tasks not running yet, or transitional state | Check thread pool, blocking tasks, container lifecycle. |
| `active=5` yet throughput is low | Active does not mean doing business work; slow DB/HTTP, broker not delivering enough messages | Measure actual in-flight callbacks, database pool, queue ready/delivering, errors. |
| Set min/max in Boot yet getters still show 1/1 | Custom factory ignores Boot properties or endpoint overrides | Check factory bean, `@JmsListener(concurrency)`, and Boot configurer. |
| Consumers scale up and down continuously | Idle thresholds/`receiveTimeout` ill-suited for bursty load | Tune `idleTaskExecutionLimit`, `idleReceivesPerTaskLimit`, `idleConsumerLimit`, receive timeout. |
| Many threads waiting on `receive` when Queue is empty | Core set too high, executor holds long-lived threads | Lower core, consider flexible scaling config. |
| DMLC stops receiving after broker restart | Connection factory cache/recovery/credentials or broker unavailable | Check recovery/backoff, cache level, broker health, and permissions. |
| Callback throws exception but message does not retry | `AUTO_ACKNOWLEDGE` or exception caught and ignored | Use transacted session properly and propagate failure; verify redelivery/DLQ. |
| DB repeatedly times out when raising max | JDBC pool/locks/HTTP connection pool overloaded | Cap max per downstream capacity and apply backpressure. |
| Configured 5 per pod but cluster has 30 consumers | 6 replicas or multiple containers exist | Sum across instances and endpoints; set cluster limits. |
| `maxConcurrentConsumers < concurrentConsumers` | Inconsistent config; implementation may clamp max up | Validate `1 <= core <= max` explicitly at startup. |
| Using `@Async` to increase listener concurrency | Confusing business callback executor with JMS consumers | Tune DMLC consumers; `@Async` does not preserve transaction/ack semantics. |
| Claiming `receiveTimeout=1s` caps callback at 1s | Timeout only applies to the wait for a message | Measure business processing latency and apply separate timeouts for downstream I/O. |

## 15. Testing Concurrency and Scaling

### 15.1. Testing Configuration Values

No broker is needed to unit test setting the two DMLC setters:

```java
DefaultMessageListenerContainer container =
        new DefaultMessageListenerContainer();
container.setConcurrency("2-5");

assertEquals(2, container.getConcurrentConsumers());
assertEquals(5, container.getMaxConcurrentConsumers());
```

This is a **snippet inside a JUnit test** with Spring JMS on the classpath and `assertEquals` imported, not a standalone test class. It verifies parsing/configuration, **not** that DMLC opened five consumers with a broker.

### 15.2. Normal Test When Queue Is Empty

- Start the Spring context with core 2/max 5.
- Isolate the test Queue and ensure no producer is active yet.
- Observe scheduled/active stabilizing near core once the container has started; depends on executor/connection health.
- Verify no busy polling or connection leaks; brief snapshot fluctuations may occur.
- Do not hard-assert "after 100 ms there must be exactly 2 active" because startup/recovery depends on the broker.

### 15.3. Test Under Growing Backlog

- Send enough messages with distinct IDs, each callback taking measurable time.
- Poll active/scheduled counts periodically alongside Queue ready/delivering.
- Ensure max is not exceeded under normal conditions.
- Verify backlog reduction and actual throughput, not just counting thread names in logs.
- If it fails to scale up, check idle consumers, provider prefetch, executor capacity, selectors, locks, and callback timing.

### 15.4. Test Scale-Down

- Stop the producer after a heavy load phase.
- Wait for callbacks and commits to finish; measure time until surplus invokers are reclaimed.
- Cross-check `receiveTimeout`, idle receives/task execution; avoid asserting immediate reclamation.
- Verify core consumers remain ready after the queue becomes idle.
- Run another burst to see whether consumer startup overhead causes abnormal latency.

### 15.5. Error Testing at High Concurrency

- Have the listener throw an exception on a chosen event; transacted session must roll back and broker must redeliver per policy.
- Verify side effects are deduplicated if the event lands on a different consumer after rollback.
- Reduce broker availability or revoke permissions; observe recovery rather than silent failure.
- Keep concurrency 2..5 and measure connection/session/consumer resources during recovery.
- Verify a rolling deploy of two replicas does not create excessive in-flight work.

### 15.6. Performance Benchmarking

Run load at `1-1`, `2-4`, `2-8`, `4-8` with the **same message size**, **same broker**, and **same downstream**. Record:
- Enqueue/dequeue rate, backlog, end-to-end completion latency.
- Processing p95/p99, transaction rollbacks, retries/DLQ.
- CPU/memory/threads and DB/HTTP pool saturation.
- Active/scheduled consumer counts per replica.
- Scale-up/scale-down times and post-burst throughput.

Choose a higher setting only when **the gain justifies the cost and risk**. If throughput stagnates while DB errors climb, a higher max does not help.

## 16. Self-Check Questions

**1.** Does `concurrentConsumers=2`, `maxConcurrentConsumers=5` immediately create 5 consumers at startup?

No. The core target is 2; DMLC **may** open up to 5 depending on load and scheduling conditions.

**2.** Does `setConcurrency("5")` mean a fixed 5 consumers?

No. In Spring 6.x DMLC, that means **core 1, max 5**. For a fixed 5, use `"5-5"`.

**3.** Does `getMaxConcurrentConsumers()=8` while `getActiveConsumerCount()=3` prove a misconfiguration?

No. Max is the configured ceiling; active is a snapshot depending on load, executor, Queue, and lifecycle.

**4.** Why should you not scale consumers on a Topic the same way as a Queue?

With a non-shared Topic, multiple subscriptions can receive the same publication, causing duplicate processing. Scale only after designing clear shared-subscription/vendor semantics.

**5.** Is message `M1` guaranteed to finish before `M2` when `concurrency=4`?

No. Multiple sessions/consumers process independently so completion order can differ from send order; use grouping/ordering policies if business logic requires it.

**6.** Does `receiveTimeout=1_000` guarantee callbacks always finish under 1 second?

No. It only bounds the wait duration of a single DMLC `receive` call, not business logic timeout.

**7.** With 4 pods, each max 5, what is the theoretical maximum total consumers?

Roughly **20 consumers for that endpoint** if all pods scale to max with uniform config, excluding other listener containers.

**8.** Why does a transacted listener still need idempotency?

Because DB/HTTP can succeed while JMS commit fails, causing redelivery; or the publisher may resend the event under a different `JMSMessageID`.

**9.** Do Spring Boot min/max properties always apply to a manually created `DefaultJmsListenerContainerFactory` bean?

No. When creating the factory manually, you must configure it yourself or use Boot's `DefaultJmsListenerContainerFactoryConfigurer`.

**10.** If throughput drops after raising max from 5 to 20, what should you do?

Measure DB/HTTP pools, broker prefetch, CPU, rollbacks/DLQ, and context switching; lower max or fix the bottleneck instead of raising max further.

## 17. Production Checklist

- Confirm destination type: Queue competing consumers vs. Topic subscription; **do not copy Queue concurrency to a Topic**.
- Determine core to handle steady load and max to handle bursts; do not treat max as the "always-on" consumer count.
- For DMLC, remember `"5"` means **1..5**, while `"5-5"` means fixed five.
- Inspect factory/annotation/Boot properties to know the **final effective configuration** applied to the endpoint.
- Keep listener beans thread-safe; avoid unsynchronized mutable counters/caches.
- Do not rely on global ordering with multiple consumers; design grouping/partitioning if needed.
- Use local JMS transactions and propagate exceptions properly; configure retries/DLQ and poison-message handling.
- Ensure business handlers are idempotent when interacting with DB/HTTP.
- Cap total consumers across replicas and listener containers to avoid exceeding broker/downstream limits.
- Monitor `getScheduledConsumerCount`, `getActiveConsumerCount`, broker metrics, in-flight callbacks, and thread/DB pools.
- Tune idle settings together with `receiveTimeout` and `TaskExecutor` after gathering measurements.
- Test empty queue, bursts, scale-down, retries, broker restarts, and rolling deployments.
- Do not mutate concurrency continuously per request; apply runtime changes through audited operational procedures with canarying and performance observation.

## Conclusion

In Spring JMS **`DefaultMessageListenerContainer`**, **`concurrentConsumers` sets the core number of consumers**, while **`maxConcurrentConsumers` caps how many consumers the container can add under load**. Both default to **1**, meaning no dynamic scaling. Setting `setConcurrency("2-5")` maintains a minimum of around two consumers and scales up to five; `setConcurrency("5")` corresponds to min 1/max 5, **not fixed five**.

Configured numbers differ from actual running consumers. Check `getScheduledConsumerCount()`, `getActiveConsumerCount()`, and broker/downstream metrics before tuning. Increasing concurrency helps Queues with independent work, but can break completion order, increase DB load, trigger redeliveries, and waste resources; for regular Topics, avoid opening multiple consumers without proper shared-subscription semantics. A solid production setup combines **transactions, idempotency, resource limits, and benchmarking**, rather than just raising the ceiling high.

## References

- Spring Framework 6.2 — `DefaultMessageListenerContainer` Javadoc, `setConcurrentConsumers`, `setMaxConcurrentConsumers`, `setConcurrency`, scaling/idle settings, getters: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html
- Spring Framework 6.2 — `DefaultJmsListenerContainerFactory` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html
- Spring Framework 6.2 — Annotation-driven JMS endpoints, `@JmsListener`, factory concurrency: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html
- Spring Framework 6.2 — Using Spring JMS / listener containers: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html
- Spring Framework 6.2 — Receiving a Message / listener transactions: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html
- Spring Boot 3.5 — JMS/Artemis messaging: https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html
- Spring Boot 3.5 — Application properties `spring.jms.listener.min-concurrency` and `max-concurrency`: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/
- Spring Boot 3.5 — JMS How-to / `DefaultJmsListenerContainerFactoryConfigurer`: https://docs.spring.io/spring-boot/3.5/how-to/messaging.html
- Jakarta Messaging 3.1 — specification, consumer/session transactions, and Queue/Topic: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Apache ActiveMQ Artemis — Using JMS, queue routing/grouping: https://artemis.apache.org/components/artemis/documentation/latest/using-jms