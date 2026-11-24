# TaskExecutor and the Actual Thread Count of DefaultMessageListenerContainer in Spring JMS

## 1. Practical Question: If 2–6 Consumers Are Configured, How Many Threads Does the Application Have?

In Spring JMS, `DefaultMessageListenerContainer` (commonly abbreviated **DMLC**) is the standard listener container for receiving messages asynchronously. A common configuration is:

~~~java
factory.setConcurrency("2-6");
~~~

Many people interpret this statement as "Spring always creates six threads" or "the application has at most six threads". Both are **inaccurate**.

`2-6` is the **JMS consumer/invoker limit of a single listener container**: normally the container maintains a minimum of two and can dynamically scale up to six when message traffic is high enough. It does not mean six handlers are executing at all times. How many threads **actually exist, are running, are waiting on the broker, or are executing business logic** also depends on:

1. The `TaskExecutor` attached to DMLC.
2. How the executor creates, retains, and reuses threads.
3. `concurrentConsumers` and `maxConcurrentConsumers`.
4. Message volume, processing speed, and receive timeout.
5. Rules for scaling invokers up/down when messages are present or absent.
6. Broker capacity, consumer creation permissions, connectivity, and recovery state.
7. CPU limits, container runtime, external pools, and other resources.

~~~text
                          @JmsListener / DMLC
                                   |
                concurrency: concurrentConsumers=2
                             maxConcurrentConsumers=6
                                   |
                                   v
                            JMS invoker tasks
                              2 ... max 6
                                   |
                                   v
                               TaskExecutor
                      +---------------------------+
                      | SimpleAsyncTaskExecutor   |
                      | or ThreadPoolTaskExecutor |
                      +---------------------------+
                                   |
                      Actual thread executing invoker
                                   |
                      JMS receive -> handler -> ACK/commit
                                   |
                               Broker Queue
~~~

**Main takeaway:** Do not use `concurrency` alone to claim a thread count, and do not use thread count alone to claim how many messages are being processed. You need to measure **different quantities**.

### Learning Objectives

After this lesson, you can:

- Distinguish `TaskExecutor`, consumer, invoker task, Java thread, and busy handler.
- Understand `DefaultMessageListenerContainer`'s default executor.
- Explain why `setConcurrency("2-6")` is not an instant thread count.
- Configure `ThreadPoolTaskExecutor` properly, avoiding executor queue bottlenecks when scaling consumers.
- Read `getScheduledConsumerCount()`, `getActiveConsumerCount()`, and thread pool metrics.
- Run a Java 17/Spring Boot 3/Artemis demo and observe thread names and handler concurrency.
- Recognize thread starvation, task rejection, ordering loss, and ACK/transaction bugs.

## 2. Architecture: One Consumer Does Not Equal One In-Flight Message

DMLC implements a **polling** strategy: each *async message listener invoker* obtains or creates a JMS Session/MessageConsumer, waits for a message, invokes the listener, and then continues the receive loop per configuration. `TaskExecutor` runs **the invokers**, rather than simply spawning a new task for each message.

~~~text
TaskExecutor thread: orders-jms-1
    |
    +-- Invoker A
          |
          +-- JMS Session A / MessageConsumer A
          +-- receive() waits for message
          +-- call listener.handle(message 1)
          +-- transaction/ack per container
          +-- receive() again
          +-- process next message

TaskExecutor thread: orders-jms-2
    |
    +-- Invoker B
          |
          +-- JMS Session B / MessageConsumer B
          +-- receive() waits for message
          +-- call listener.handle(message 2)
          +-- ...
~~~

In a typical setup, each invoker processes messages sequentially on the thread running the invoker. An invoker can be long-lived, holding a thread while **waiting on the broker**; a thread existing or active in the executor is not necessarily executing a business handler.

Difference from a familiar pattern:

~~~java
executor.execute(() -> processOneMessage(message));
~~~

DMLC **does not by default** dispatch a separate task per message like the snippet above. A DMLC task manages the entire receive-and-callback cycle. Thus, a thread pool "with 20 worker threads" backing a listener container configured for at most 3 consumers will not magically run 20 message handlers in parallel.

### 2.1. Quantities That Must Not Be Conflated

| Quantity | Exact Meaning |
| --- | --- |
| `concurrentConsumers` | Minimum consumer level configured for a DMLC |
| `maxConcurrentConsumers` | Consumer/invoker ceiling DMLC can scale up to |
| `scheduledConsumerCount` | Number of consumer invokers currently scheduled by the container |
| `activeConsumerCount` | Number of invokers actually active/executing according to the container |
| `ThreadPoolTaskExecutor.poolSize` | Current number of threads in the thread pool (if using a pool) |
| `ThreadPoolTaskExecutor.activeCount` | Pool threads busy running tasks, including those waiting on JMS receive |
| `handlerInFlight` | Number of business method executions currently underway (must instrument yourself) |
| `brokerConsumerCount` | Consumers seen registered by the broker; may differ during recovery/caching |
| `Runtime.availableProcessors()` | Estimated CPUs available to the JVM, **not** consumer count |

If metrics differ, it is not necessarily a bug: they measure **different layers** and can change even between two observations.

## 3. Default Executor: SimpleAsyncTaskExecutor

Per Spring Framework Javadoc, if `setTaskExecutor(...)` is not called, DMLC creates a `SimpleAsyncTaskExecutor` internally.

~~~java
DefaultMessageListenerContainer container =
        new DefaultMessageListenerContainer();
// Do not call container.setTaskExecutor(...)
// => container uses SimpleAsyncTaskExecutor internally.
~~~

`SimpleAsyncTaskExecutor` **is not a thread pool that reuses threads**. It creates a new thread for task executions; a listener invoker task can hold its thread for a long time because the task runs a polling cycle.

Consequences:

- DMLC defaults to `concurrentConsumers=1` and `maxConcurrentConsumers=1` if unchanged.
- With `setConcurrency("2-6")`, at least two invokers are maintained during steady operation; surplus invokers can be added under traffic.
- Invoker tasks are typically long-lived; "SimpleAsync" does not mean "spawn a new thread after **every** message".
- When an invoker finishes and is rescheduled, this executor may use a new Java thread instead of reusing the old thread.
- There is no `getPoolSize()` on the default executor like `ThreadPoolTaskExecutor`, because there is no pool in that sense.
- Use thread dumps and DMLC metrics to understand runtime behavior rather than trying to read a non-existent pool metric.

### 3.1. Spring 6.2 and Virtual Threads

In Spring Framework **6.2 and later**, DMLC supports configuring virtual threads for the default executor, targeting Java 21+. That **does not apply** to the Java 17/Spring 6.1 project in the example below. Virtual threads do not remove `concurrentConsumers` and `maxConcurrentConsumers` bounds; the broker, sessions, message processing, and DB still need their own resource limits.

When reading documentation, verify the **exact version**: a new API in 6.2 does not necessarily exist in 6.1. Idle rescheduling behavior has also evolved between releases. Do not copy virtual-thread configuration from newer Javadoc expecting Java 17 to compile it.

## 4. Concurrency: Minimum, Maximum, and Actual Counts

DMLC can be configured in either of two ways:

~~~java
// Option 1: separate setters:
container.setConcurrentConsumers(2);
container.setMaxConcurrentConsumers(6);

// Option 2: using a String range:
container.setConcurrency("2-6");
~~~

`setConcurrency("2-6")` corresponds to setting minimum=2 and maximum=6. Per Spring, a single-number form like `setConcurrency("6")` is interpreted as **minimum=1, maximum=6**, not maintaining a fixed six consumers.

| Configuration | Minimum | Maximum | Meaning |
| --- | ---: | ---: | --- |
| Not configured | 1 | 1 | One permanent invoker |
| `setConcurrency("2")` | 1 | 2 | Can scale up to two |
| `setConcurrency("2-6")` | 2 | 6 | Baseline of two, scales with load |
| `setConcurrentConsumers(4)` with default maximum | 4 | At least 4 | Setter may raise max when new minimum exceeds old max |
| `setConcurrentConsumers(2); setMaxConcurrentConsumers(6)` | 2 | 6 | Explicit minimum and maximum bounds |

Do not increase consumers for a Topic mechanically. With a Queue, multiple consumers split work; with a Topic lacking proper subscription configuration, multiple consumers may each receive the same message via separate subscriptions. For order-sensitive applications, adding consumers can break desired ordering.

### 4.1. Why Does Scheduled Count Rise Gradually Rather Than Jumping to Maximum Immediately?

DMLC spawns additional invokers when it detects arriving messages and sees it has not exceeded `maxConcurrentConsumers` and idle consumer limits. It does not invoke "start max threads" merely because an upper bound was declared.

Example with `2-6`:

~~~text
Queue empty or low load:
  minimum 2 invokers are usually maintained

Traffic increases:
  2 -> 3 -> 4 -> ... can scale up to 6 invokers

Traffic drops:
  surplus invokers are released after idle condition
  typically returns to minimum=2
~~~

This is a **model**, not exact second-by-second output. Scale-up/down speed is also influenced by receive timeout, idle settings, executor configuration, and the broker.

### 4.2. Parameters Controlling Scaling

DMLC has these setters:

| Option | Role |
| --- | --- |
| `setIdleConsumerLimit(int)` | Maximum idle consumers allowed when deciding whether to create a new invoker |
| `setIdleTaskExecutionLimit(int)` | Limit of executions where a task is deemed idle before a surplus task stops |
| `setIdleReceivesPerTaskLimit(int)` | Consecutive empty receives before marking a task idle |
| `setMaxMessagesPerTask(int)` | Limit on *receive attempts* for a single task execution |
| `setReceiveTimeout(long)` | How long each receive can wait for a message |
| `setTaskExecutor(Executor)` | Where invoker tasks are executed and rescheduled |

These properties interact with each other. Do not treat them as independent switches to "spawn more threads" without recalculating container behavior.

**Important:** `maxMessagesPerTask` counts `receive` attempts that obtain no message as well. If set to `20` and every receive times out, a task can terminate after 20 empty polls, not after "20 real messages processed".

### 4.3. The Executor Can Affect Task Lifecycle Defaults

DMLC Javadoc states:

- With a standard executor, tasks can be long-lived, receiving many consecutive messages.
- With a `SchedulingTaskExecutor` indicating a preference for short-lived tasks, DMLC may default to `maxMessagesPerTask=10` to return threads to the pool more frequently.
- With a simple/non-pooling executor, the strategy for terminating idle invokers differs, especially for surplus consumers.

Exact idle-scheduling behavior differs between Spring 6.1 and 6.2; read the **Javadoc for your exact version** before copying default numbers. When deterministic behavior is required, set explicit bounds and test under realistic workloads, avoiding tuning too many knobs before gathering data.

## 5. DMLC's TaskExecutor Is Not the @Async Executor

Spring uses `Executor` in multiple places: tasks for `@Async`, schedulers for `@Scheduled`, an executor serving HTTP requests, and the executor for JMS listener invokers.

**They are not automatically the same pool.** For example:

~~~properties
spring.task.execution.pool.core-size=8
spring.task.execution.pool.max-size=16
~~~

Spring Boot's task execution keys only control the corresponding auto-configured executor. They **do not automatically alter** the executor inside DMLC without explicit wiring.

To attach an executor to a listener, configure it on the container:

~~~java
container.setTaskExecutor(myExecutor);
~~~

Or via `DefaultJmsListenerContainerFactory`:

~~~java
factory.setTaskExecutor(myExecutor);
~~~

`myExecutor` must be a compatible bean or instance implementing `java.util.concurrent.Executor`. Spring supports `TaskExecutor` through the same abstraction.

**Design warning:** sharing a pool between long-lived JMS invokers and short `@Async` tasks can cause starvation. Invokers waiting on JMS still hold pool threads; other tasks may sit queued even when the application is processing no messages.

## 6. ThreadPoolTaskExecutor: When It Helps and When It Bottlenecks

`ThreadPoolTaskExecutor` is an executor backed by JDK `ThreadPoolExecutor`, providing:

- `corePoolSize`: core thread count.
- `maxPoolSize`: pool thread limit.
- `queueCapacity`: capacity to queue tasks before creating additional threads up to maximum.
- `keepAliveSeconds`: time to keep non-core idle threads alive.
- `threadNamePrefix`: how to identify threads in logs/dumps.
- `getPoolSize()` and `getActiveCount()`: runtime executor metrics.

However, DMLC **does not** simply submit one short task per message. It submits invoker tasks, which typically run both the receive loop and handler. If the pool is misconfigured, there may not be enough threads to run the requested number of invokers.

### 6.1. The Trap of an Overly Large queueCapacity

Suppose:

~~~java
executor.setCorePoolSize(2);
executor.setMaxPoolSize(6);
executor.setQueueCapacity(100);
~~~

While the two core threads run two long-lived invokers, new invokers are typically **placed into the executor's queue**. The pool may not grow to six threads until the queue fills up per `ThreadPoolExecutor` rules.

Scenario:

~~~text
DMLC: concurrency=2-6
Executor: core=2, max=6, queueCapacity=100

2 running invokers -> occupy 2 core threads
DMLC wants to schedule a 3rd invoker:
  executor queues the task
  does not allocate a 3rd thread immediately
DMLC metrics may show:
  scheduled=3, active=2
Pool:
  poolSize=2, activeCount=2
~~~

Thus **`maxPoolSize=6` does not mean the pool will grow to six** when `queueCapacity=100`. To give invokers threads promptly, consider a small queue or `queueCapacity=0`, alongside an appropriate maximum limit.

### 6.2. queueCapacity=0 Opens Threads Quickly but Needs Bounds

~~~java
ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
executor.setCorePoolSize(2);
executor.setMaxPoolSize(6);
executor.setQueueCapacity(0);
executor.setThreadNamePrefix("orders-jms-");
~~~

With `queueCapacity=0`, new tasks do not sit waiting in a bounded backlog queue, so the pool typically creates a new thread up to maximum if core threads are busy. However, once maximum is reached, the executor **may reject tasks** with `TaskRejectedException`. DMLC has certain logging/rescheduling mechanisms, yet you must not assume task rejection is harmless.

A dedicated pool for JMS invokers isolates resources from `@Async`/web executors, especially when receive tasks are long-lived. Do not share a single `queueCapacity=0` pool across dozens of listeners without summing total demand.

### 6.3. Why a Large Thread Pool Does Not Mean Many JMS Consumers

If the pool has `maxPoolSize=20` while DMLC has `maxConcurrentConsumers=4`, the container will not scale beyond four JMS invokers per its own limit. The pool may hold threads not serving JMS or sitting idle. Conversely, if DMLC wants six while the pool only has four execution slots, some invokers may not run yet.

In other words:

~~~text
Number of running JMS invokers
  <= DMLC limit
  and also bounded by executor/broker/resources.

Number of in-progress handler executions
  <= number of actually running invokers
  and can be much lower if they are waiting on receive.
~~~

Do not use CPU core count as a rigid formula for JMS consumers: if handlers mainly wait on DB/network, suitable concurrency differs from a CPU-bound workload. You must load test and measure saturation.

## 7. Which Getters Reveal the "Actual Numbers"?

DMLC provides useful getters:

~~~java
int configuredMin = container.getConcurrentConsumers();
int configuredMax = container.getMaxConcurrentConsumers();

int scheduled = container.getScheduledConsumerCount();
int active = container.getActiveConsumerCount();
~~~

Per Javadoc:

- `getConcurrentConsumers()` / `getMaxConcurrentConsumers()` return **configured values**.
- `getScheduledConsumerCount()` is the number of invokers scheduled by the container, which **can exceed active** if the executor does not yet have threads to run some invokers.
- `getActiveConsumerCount()` is the number of invokers actually active per DMLC, **not the number of currently executing handler methods**.
- During container startup, shutdown, or recovery, these numbers may fluctuate or be lower than normal. Do not turn a snapshot taken mid-failure into a conclusion that configuration is always broken.

### 7.1. From @JmsListener to the Actual Container via Registry

The `@JmsListener` annotation uses `JmsListenerEndpointRegistry` to manage listener containers. For a listener with `id="ordersTasks"`:

~~~java
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.listener.MessageListenerContainer;
import org.springframework.jms.listener.DefaultMessageListenerContainer;

// Snippet inside a service with injected registry:
MessageListenerContainer value =
        registry.getListenerContainer("ordersTasks");
if (value instanceof DefaultMessageListenerContainer dmlc) {
    System.out.println(dmlc.getScheduledConsumerCount());
    System.out.println(dmlc.getActiveConsumerCount());
}
~~~

This is a snippet, not a standalone Java file. Use `instanceof` to avoid an invalid cast if the application uses a different container factory.

**Note:** containers created from `@JmsListener` do not necessarily exist as `ApplicationContext` beans under the annotation id name. The registry is the proper way to access and manage them.

### 7.2. Measure the Pool and Business Handlers Separately

When using `ThreadPoolTaskExecutor`:

~~~java
int poolSize = ordersExecutor.getPoolSize();
int activePoolThreads = ordersExecutor.getActiveCount();
~~~

These two metrics still do not tell you how many message handlers are running. An invoker may occupy a thread while blocked in `MessageConsumer.receive()` waiting on the broker without doing business processing.

To measure handler concurrency, add instrumentation **inside the handler**:

~~~java
private final AtomicInteger inFlight = new AtomicInteger();
private final AtomicInteger peak = new AtomicInteger();

public void onMessage(String body) {
    int now = inFlight.incrementAndGet();
    peak.accumulateAndGet(now, Math::max);
    try {
        processBusiness(body);
    } finally {
        inFlight.decrementAndGet();
    }
}
~~~

This is a snippet inside a class that already has `processBusiness` and imports `AtomicInteger`. `inFlight` reflects how many callbacks are currently running on that instance; `peak` reflects the highest concurrency observed **since the bean was initialized**, not current concurrency. With multiple pods/instances, aggregate metrics per instance and do not mistake one instance's value for a cluster-wide count.

## 8. Java 17 + Spring Boot 3.3 + Artemis Project: Measuring Four Kinds of Numbers

This lab creates one Queue, one `@JmsListener` backed by DMLC, a dedicated executor pool, and a sender dispatching multiple messages. Each handler sleeps briefly to simulate I/O so multiple messages can be processed concurrently.

**Goal:** observe the difference between:

1. Configured min/max bounds.
2. DMLC scheduled/active invoker counts.
3. Thread pool size/active count.
4. Actual handlers concurrently processing at the same moment.

### 8.1. Local Artemis

On a machine with Docker:

~~~bash
docker run --detach --rm --name artemis-taskexecutor-lab -p 127.0.0.1:61616:61616 -p 127.0.0.1:8161:8161 -e ARTEMIS_USER=demo -e ARTEMIS_PASSWORD=demo apache/artemis:latest
~~~

Wait for the broker to be ready and check logs:

~~~bash
docker logs artemis-taskexecutor-lab
~~~

The `demo/demo` credentials are for the lab only. If the broker disables Queue auto-create, create `orders.tasks.demo` beforehand and grant send/consume permissions. Use a clean Queue or configure a distinct name per run so stale messages do not skew results.

### 8.2. File Structure

~~~text
jms-executor-lab/
  settings.gradle
  build.gradle
  src/main/resources/application.properties
  src/main/java/demo/jms/
    ExecutorLabApplication.java
    JmsWorkerConfig.java
    CountingOrderListener.java
    DemoSender.java
  src/test/java/demo/jms/
    CountingOrderListenerTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-executor-lab'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'demo'
version = '1.0.0'

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
~~~

This is a fixed dependency set for illustration, not claiming to be the latest release. Use JDK 17+ and a compatible Gradle version; Spring Boot 3 requires `jakarta.jms` (do not mix legacy `javax.jms`).

### 8.3. application.properties

~~~properties
spring.main.web-application-type=none
spring.artemis.mode=native
spring.artemis.broker-url=${JMS_BROKER_URL:tcp://localhost:61616}
spring.artemis.user=${JMS_BROKER_USER:demo}
spring.artemis.password=${JMS_BROKER_PASSWORD:demo}
spring.jms.pub-sub-domain=false
spring.jms.cache.enabled=false

app.jms.destination=${JMS_QUEUE:orders.tasks.demo}
~~~

Real Spring placeholders use `${...}` syntax with a dollar sign. `spring.jms.cache.enabled=false` keeps the lab simpler regarding connection factory lifecycle: DMLC manages its own consumers/sessions; this is not a claim that caching is always wrong in production.

Only use the `demo` credential fallback locally. In production, inject secrets/credentials securely and grant per-destination ACLs.

### 8.4. Entry Point

File `src/main/java/demo/jms/ExecutorLabApplication.java`:

~~~java
package demo.jms;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.jms.annotation.EnableJms;

@SpringBootApplication
@EnableJms
public class ExecutorLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExecutorLabApplication.class, args);
    }
}
~~~

`@EnableJms` enables `@JmsListener` processing. Spring Boot provides `ConnectionFactory`/`JmsTemplate` when the Artemis starter and configuration are valid.

### 8.5. Dedicated JMS ThreadPoolTaskExecutor and Factory

File `src/main/java/demo/jms/JmsWorkerConfig.java`:

~~~java
package demo.jms;

import jakarta.jms.ConnectionFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class JmsWorkerConfig {

    @Bean("ordersExecutor")
    ThreadPoolTaskExecutor ordersExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setThreadNamePrefix("orders-jms-");
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(0);
        return executor;
    }

    @Bean("ordersListenerFactory")
    DefaultJmsListenerContainerFactory ordersListenerFactory(
            ConnectionFactory connectionFactory,
            @Qualifier("ordersExecutor")
            ThreadPoolTaskExecutor executor) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrency("2-4");
        factory.setTaskExecutor(executor);

        // Relatively short tasks so the pool has a chance to reschedule:
        factory.setMaxMessagesPerTask(20);
        factory.setReceiveTimeout(1000L);

        // Only a JMS local session transaction:
        factory.setSessionTransacted(true);
        return factory;
    }
}
~~~

Key points to understand:

- `ordersExecutor` is a **dedicated bean**. Do not share it with `@Async` or every other JMS listener without accounting for total resources.
- The pool has minimum/core two, maximum four threads; `queueCapacity=0` gives the pool a chance to spin up extra threads promptly instead of queuing invokers behind core tasks.
- DMLC also has minimum two and maximum four invokers. These two bounds are aligned for the lab, yet **do not guarantee four threads are always running**.
- `setMaxMessagesPerTask(20)` controls the number of receive attempts a task executes, not an independent business message batch size.
- `setReceiveTimeout(1000L)` applies to each DMLC JMS poll; it is not an HTTP request timeout or `JmsTemplate.receive` timeout.
- `setSessionTransacted(true)` enables a JMS local transaction: a successful handler can commit the JMS session; failures can roll back/redeliver per broker. It does not automatically create a DB+JMS transaction.
- Spring manages the executor bean's lifecycle. Do not call `executor.initialize()` manually on a `@Bean` in this configuration.

### 8.6. Listener with an In-Flight Handler Counter

File `src/main/java/demo/jms/CountingOrderListener.java`:

~~~java
package demo.jms;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class CountingOrderListener {

    private final AtomicInteger inFlight = new AtomicInteger();
    private final AtomicInteger peak = new AtomicInteger();
    private final AtomicInteger finishedCalls = new AtomicInteger();
    private final CountDownLatch latch = new CountDownLatch(12);

    @JmsListener(
            id = "ordersTasks",
            destination = "${app.jms.destination}",
            containerFactory = "ordersListenerFactory")
    public void onOrder(String body) {
        int current = inFlight.incrementAndGet();
        peak.accumulateAndGet(current, Math::max);

        try {
            // Simulate handler waiting on I/O for 250 ms.
            Thread.sleep(250);
            System.out.printf(
                    "HANDLE body=%s thread=%s inFlight=%d%n",
                    body, Thread.currentThread().getName(),
                    current);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted", ex);
        } finally {
            inFlight.decrementAndGet();
            finishedCalls.incrementAndGet();
            latch.countDown();
        }
    }

    public boolean await(long timeout, TimeUnit unit)
            throws InterruptedException {
        return latch.await(timeout, unit);
    }

    public int peakHandlerConcurrency() {
        return peak.get();
    }

    public int inFlightHandlers() {
        return inFlight.get();
    }

    public int finishedCalls() {
        return finishedCalls.get();
    }
}
~~~

This is a demo, not production business code:

- `inFlight` increments **as soon as the callback starts** and decrements in `finally`.
- `peak` stores the highest callback concurrency since the bean was created.
- `finishedCalls` counts **handler exits**, including when an exception occurs, not successful business commits.
- `CountDownLatch(12)` lets main wait for 12 handler completions; it does not prove ACK, DB commit, or exactly-once.
- `Thread.sleep` only simulates I/O; do not intentionally hold a JMS transaction open with sleep in production handlers.

### 8.7. Sender and Runtime Measurement Snippet

File `src/main/java/demo/jms/DemoSender.java`:

~~~java
package demo.jms;

import java.util.concurrent.TimeUnit;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.CommandLineRunner;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.listener.DefaultMessageListenerContainer;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Component;

@Component
public class DemoSender implements CommandLineRunner {

    private final JmsTemplate template;
    private final JmsListenerEndpointRegistry registry;
    private final ThreadPoolTaskExecutor executor;
    private final CountingOrderListener listener;
    private final String queue;

    public DemoSender(
            JmsTemplate template,
            JmsListenerEndpointRegistry registry,
            @Qualifier("ordersExecutor")
            ThreadPoolTaskExecutor executor,
            CountingOrderListener listener,
            @Value("${app.jms.destination}") String queue) {
        this.template = template;
        this.registry = registry;
        this.executor = executor;
        this.listener = listener;
        this.queue = queue;
    }

    @Override
    public void run(String... args) throws Exception {
        for (int i = 1; i <= 12; i++) {
            template.convertAndSend(queue, "ORDER-" + i);
        }

        boolean done = listener.await(20, TimeUnit.SECONDS);
        var container = registry.getListenerContainer("ordersTasks");

        if (!(container instanceof DefaultMessageListenerContainer dmlc)) {
            throw new IllegalStateException(
                    "ordersTasks is not a DMLC");
        }

        System.out.printf(
                "LIMITS min=%d max=%d%n",
                dmlc.getConcurrentConsumers(),
                dmlc.getMaxConcurrentConsumers());

        System.out.printf(
                "RUNTIME scheduled=%d activeInvokers=%d " +
                "poolSize=%d poolActive=%d handlerInFlight=%d%n",
                dmlc.getScheduledConsumerCount(),
                dmlc.getActiveConsumerCount(),
                executor.getPoolSize(),
                executor.getActiveCount(),
                listener.inFlightHandlers());

        System.out.printf(
                "DONE=%s FINISHED_CALLS=%d HANDLER_PEAK=%d%n",
                done,
                listener.finishedCalls(),
                listener.peakHandlerConcurrency());
    }
}
~~~

**Why is `JmsListenerEndpointRegistry` needed?** Containers created from `@JmsListener` are managed by the registry; `id="ordersTasks"` lets us look up the exact container. Do not assume this DMLC can be fetched via `applicationContext.getBean("ordersTasks")`.

### 8.8. Running and Interpreting Stdout Properly

Once Artemis is ready:

~~~bash
gradle test
gradle bootRun
~~~

With a clean lab Queue, a broker granting send/consume permissions, and no competing consumers, the program usually prints 12 `HANDLE ...` lines and three summary lines. **The order of HANDLE lines, thread names, invoker counts at the instant of the snapshot, and HANDLER_PEAK are runtime data; do not hardcode a fixed output.**

Illustrative excerpt of output:

~~~text
HANDLE body=ORDER-2 thread=orders-jms-2 inFlight=2
HANDLE body=ORDER-1 thread=orders-jms-1 inFlight=1
...
LIMITS min=2 max=4
RUNTIME scheduled=2 activeInvokers=2 poolSize=4 poolActive=2 handlerInFlight=0
DONE=true FINISHED_CALLS=12 HANDLER_PEAK=4
~~~

**Only the `LIMITS min=2 max=4` line is a fixed configuration value.** The runtime numbers in the example are **an illustrative snapshot**, not guaranteed stdout; `scheduled` may be 2–4 under normal operation, `poolSize` can exceed active threads, and peak depends on message timing and load. Seeing `HANDLER_PEAK=2` or `3` instead of `4` is still normal behavior.

If `DONE=false`, check the Queue for stale messages, competing consumers, broker readiness, task rejection, authorization/transaction failures, and logs; do not immediately blame a lack of threads.

Stop the broker:

~~~bash
docker stop artemis-taskexecutor-lab
~~~

## 9. A JMS-Free Java 17 Demo to Understand Pool Size and Task Queue

To separate the thread pool concept from the broker, the following program intentionally blocks two tasks in a fixed two-thread pool and submits two more waiting tasks. It proves **four submitted tasks do not mean four threads executing in parallel**.

File `ExecutorCapacityProof.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class ExecutorCapacityProof {

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch started = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger inFlight = new AtomicInteger();

        try {
            for (int i = 0; i < 4; i++) {
                pool.execute(() -> {
                    inFlight.incrementAndGet();
                    started.countDown();
                    try {
                        release.await();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    } finally {
                        inFlight.decrementAndGet();
                    }
                });
            }

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Threads not started");
            }

            System.out.println("SUBMITTED_TASKS=4");
            System.out.println("POOL_SIZE_LIMIT=2");
            System.out.println(
                    "IN_FLIGHT_DURING_GATE=" + inFlight.get());
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Compile and run with JDK 17:

~~~bash
javac ExecutorCapacityProof.java
java ExecutorCapacityProof
~~~

Output when two threads start normally:

~~~text
SUBMITTED_TASKS=4
POOL_SIZE_LIMIT=2
IN_FLIGHT_DURING_GATE=2
~~~

The first two tasks occupy the two threads and wait at the latch; the remaining two tasks sit waiting in the executor queue. This program uses no JMS and **does not simulate broker delivery**; it only illustrates why *submitted tasks*, *running threads*, and *queued tasks* must be distinguished.

## 10. Unit Test: Bounded to Java Code, Not Verifying the Broker

File `src/test/java/demo/jms/CountingOrderListenerTest.java`:

~~~java
package demo.jms;

import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CountingOrderListenerTest {

    @Test
    void recordsHandlerExecution() throws Exception {
        CountingOrderListener listener = new CountingOrderListener();

        listener.onOrder("ORDER-1");

        assertTrue(listener.await(1, TimeUnit.MILLISECONDS) == false);
        assertEquals(1, listener.finishedCalls());
        assertEquals(0, listener.inFlightHandlers());
        assertEquals(1, listener.peakHandlerConcurrency());
    }
}
~~~

The test calls one handler directly; since the latch requires 12 completions, `await` has not completed after one call. This is a unit test that **can run without a broker**, testing instrumentation rather than DMLC thread scheduling.

Even though the test has a `Thread.sleep(250)` and `await(1 ms)`, it is deterministic because the `onOrder` call runs synchronously on the test thread and finishes before the assertions. Do not use this test to conclude Artemis created a session or ACKed successfully.

### 10.1. What Should an Integration Test Verify?

With an Artemis/Testcontainers broker:

1. The factory configures `concurrency="2-4"` and a dedicated 2–4 thread pool.
2. The endpoint registry contains `ordersTasks` and it is of type DMLC.
3. DMLC reports the expected configured min/max.
4. Real messages cause callbacks to run on threads prefixed with `orders-jms-`.
5. Vary processing speed and backlog to observe `scheduled`, `active`, and `handlerInFlight` over time.
6. Messages are not lost or excessively reprocessed under the designed ACK/transaction policy.
7. When the queue is empty, surplus invokers can scale down per idle policy.
8. On broker restart, the container recovers and metrics may diverge temporarily.
9. When the pool is too small or tasks are rejected, logs/alerts reflect the error.
10. When raising concurrency, handlers are thread-safe and business ordering holds.

Use **bounded waits and eventual conditions**, rather than asserting that at one exact millisecond `scheduled==4`. Dynamic scaling is asynchronous and timing depends on the CI machine.

## 11. Dangerous Differences from SimpleMessageListenerContainer

The names `DefaultMessageListenerContainer` and `SimpleMessageListenerContainer` are similar, but `setTaskExecutor` **does not have the same semantics**.

- **DMLC:** `TaskExecutor` runs **polling invoker tasks**. An invoker executes receive and then calls the listener on the task thread; the container manages sessions/transactions in DMLC's way.
- **SimpleMessageListenerContainer:** `TaskExecutor` may be used to dispatch the listener callback to another thread after the JMS provider receives the message. Per Spring Javadoc, this can cause **ACK to happen before the handler executes** and yield undefined results when combined with transacted sessions/client acknowledgment.

Therefore, **do not copy DMLC's `TaskExecutor` setup to SMLC assuming ACK/transaction behavior is identical**. If business logic needs JMS rollback on handler failure, choose the right container and transaction policy from the start and read that container's own Javadoc.

## 12. Thread Dumps, JMX, and Metrics for Production

For a production service, monitor across multiple layers:

| Source | Metric / Signal | What It Tells You |
| --- | --- | --- |
| DMLC JMX/bean | `getConcurrentConsumers()`, `getMaxConcurrentConsumers()` | Configured min/max |
| DMLC runtime | `getScheduledConsumerCount()` | Invokers scheduled by the container |
| DMLC runtime | `getActiveConsumerCount()` | Invokers actually active |
| ThreadPoolTaskExecutor | `getPoolSize()`, `getActiveCount()` | Total pool threads and threads running tasks |
| Handler instrumentation | inFlight, peak, duration p95/p99 | Business callbacks currently executing and latency |
| Artemis broker | consumer count, queue depth, delivering, messages added/acked | Message and consumer state on the broker side |
| JVM | thread dump, CPU, GC, blocked threads | Overall system state |
| DB | connection pool active/pending, transaction latency | Downstream bottlenecks that may stall handlers |

A thread dump may show multiple `orders-jms-...` threads in `WAITING` or `TIMED_WAITING` inside `MessageConsumer.receive`. This is usually normal **waiting for messages**, not a deadlock. A `RUNNABLE` thread is also not guaranteed to be burning CPU; native I/O can appear in that state.

### 12.1. Do Not Add Up Active Threads to Infer Messages/Second

Having eight active threads where each handler spends one second waiting on the DB does not guarantee eight messages/second. There is also overhead, transactions, broker prefetch, uneven load, and retry errors. Little's Law approximations only apply when measuring a steady-state workload:

~~~text
Required concurrency ≈ target throughput × average processing time
~~~

For example, a target of 20 messages/s with a 0.1 s average handler needs concurrency of about two under simplified assumptions. This is an **input estimate for load testing**, not a guaranteed configuration for every JMS broker or tail latency. You must account for DB capacity, peak load, and ACK/transactions.

### 12.2. Watch Counts Across Multiple Instances

`concurrency="2-6"` configures **each DMLC on each app instance**, not a cluster-wide maximum. Running four pods can yield up to 24 invokers of that kind under corresponding load, not six.

Still, do not treat that number as exact broker consumer count during connection failures, scale-downs, or rolling updates. Tag metrics with instance, queue, listener ID, and deployment revision.

## 13. When Should You Increase concurrentConsumers?

Increase the minimum when:

- The Queue has steady traffic and you want lower arrival latency.
- Enough DB/API connections exist for parallel processing.
- You want to avoid slow ramp-up during normal traffic periods.
- Handlers are thread-safe and do not depend on strict global ordering.

Keep minimum small and maximum larger when:

- Load fluctuates by hour or batch.
- Traffic-driven ramp-up is acceptable.
- You do not want to hold too many JMS Sessions/Consumers while idle.
- You have clear metrics to tune idle behavior.

Do not increase when:

- Business logic requires sequential processing and has no key grouping.
- The DB pool is already saturated; adding consumers only creates more waiting threads.
- The broker enforces strict session/consumer limits.
- Consumers are not yet idempotent and redeliveries cause duplicate side effects.
- Topic subscription semantics could cause messages to be processed multiple times.

## 14. Safe Configuration and Resilience

### 14.1. Size Executor Capacity to JMS Demand

Example of a DMLC with at most six invokers using a dedicated pool:

~~~java
executor.setCorePoolSize(2);
executor.setMaxPoolSize(6);
executor.setQueueCapacity(0);
factory.setConcurrency("2-6");
factory.setTaskExecutor(executor);
~~~

While matching the maximum is easy to reason about, it is not a rigid law. If multiple DMLCs share a pool, evaluate **total invokers**, other tasks, and rescheduling; you may need headroom or separate pools.

### 14.2. Do Not Use an Unbounded Thread Pool

`ThreadPoolTaskExecutor` defaults to a small core pool and a large queue capacity. Setting `maxPoolSize=Integer.MAX_VALUE` combined with `queueCapacity=0` without proper bounds can spawn excessive threads during a surge, causing memory pressure and broker/DB overload. Set explicit bounds on both the executor and DMLC sides.

### 14.3. Transactions and Resource Ownership

An invoker typically manages its corresponding JMS Session/MessageConsumer. DMLC has its own cache level and transaction management. If using `CachingConnectionFactory`, external pools/executors, or an XA transaction manager, evaluate ownership and recovery; do not layer extra caching blindly assuming it is better.

### 14.4. When Handlers Fail

With `sessionTransacted=true`, the container can roll back the JMS session when the handler throws an error; the message can be redelivered per broker policy. Thread count does not solve permanent data errors. You need a DLQ, retry/backoff, event IDs, and idempotency. Do not swallow exceptions and treat failed messages as succeeded.

### 14.5. Ordering and Competing Consumers

Multiple consumers on the same Queue can process messages in parallel, making **handler completion** order differ from send order. If the same order ID requires sequential execution, consider JMS Message Groups, key partitioning, or aggregate-based processing rather than just tuning min/max threads.

## 15. Common Mental Traps

| False Claim | Truth |
| --- | --- |
| "concurrency=6 always creates six threads" | DMLC may have fewer depending on syntax and load; active differs from configured |
| "concurrency=2-6 means exactly six handlers run concurrently" | Those are consumer min/max bounds; handlers may be idle |
| "TaskExecutor spawns one task per JMS message" | In DMLC, the executor runs polling invokers with a receive loop |
| "SimpleAsyncTaskExecutor reuses threads in a pool" | It is not a reusing thread pool |
| "Pool max=6 automatically grows to six when tasks arrive" | A large queue capacity can hold waiting tasks instead of creating threads immediately |
| "activeConsumerCount is the number of handlers processing payloads" | Invokers may be waiting in `receive` |
| "getScheduledConsumerCount = JVM thread count" | Scheduled invokers might not be running yet due to the executor |
| "getPoolSize is the consumer count seen by the broker" | That is a pool metric, not a JMS destination registration |
| "Adding consumers solves every backlog" | Bottlenecks may lie in DB, broker, network, locks, schema, or retries |
| "A WAITING thread is a deadlock" | It may simply be waiting normally in `receive()` |
| "@Async pool size automatically changes DMLC executor" | Explicit `setTaskExecutor` wiring is required |
| "SimpleMessageListenerContainer has the same executor/ACK behavior" | Dispatch/ACK semantics can differ significantly |
| "A Queue with six consumers preserves absolute completion order" | Concurrency changes observed completion order |
| "maxConcurrentConsumers=6 is a cluster-wide max of six" | It is a cap per container/instance |
| "ThreadPoolTaskExecutor activeCount=4 means four messages are being processed" | Tasks may be polling the broker without invoking handlers |

## 16. Quick Troubleshooting

| Symptom | Possible Cause | Action |
| --- | --- | --- |
| Scheduled > Active persistently | Pool lacks threads, tasks queued/rejected, or in recovery | Check executor `poolSize`/`activeCount`/`queueCapacity` and DMLC logs |
| Active invokers > Handler inFlight | Invokers waiting for messages or between callbacks | Check broker queue depth, receive timeout, thread dump |
| High `maxConcurrentConsumers` yet no scaling | Low message volume, `idleConsumerLimit`, executor capacity, or broker | Load test under right conditions, inspect task scheduling |
| Thread pool never exceeds `corePoolSize` | Large `queueCapacity` with long-lived invokers | Check executor queue; consider small or 0 capacity |
| `TaskRejectedException` occurs | Pool saturated or shutting down | Raise bounded capacity, isolate pools, adjust rescheduling |
| Queue depth grows, CPU is low | Waiting on DB/API/locks, backlog, insufficient consumers | Measure handler latency, DB pool, and consumer count |
| Many threads yet TPS does not rise | Downstream bottleneck or transaction overhead | Profile business path, DB, broker; stop adding threads |
| Active count drops after broker restart | Reconnect/recovery or resource unavailable | Check recovery logs, ACLs, session/connection metrics |
| Pod startup creates too many consumers | Many listeners/instances each with a minimum | Multiply across containers and replicas |
| Handler duplicates processing when raising concurrency | Retries/redelivery and missing idempotency | Track event IDs, handle duplicates, check rollback/DLQ |
| Test expecting exactly four threads fails | Dynamic scaling is non-deterministic | Assert bounds and throughput/peak instead of rigid snapshots |

## 17. Self-Guided Exercises

**Exercise 1 — Predict consumer count.** With `setConcurrency("4")`, what are the configured minimum and maximum? Inspect `getConcurrentConsumers` and `getMaxConcurrentConsumers`; do not guess "fixed four".

**Exercise 2 — queueCapacity.** Change `setQueueCapacity(0)` to `setQueueCapacity(100)` with core=2, max=4. Keep 12 messages and 250ms sleep. Observe `poolSize`, `activeCount`, and scheduled/active invokers over time. Explain why the pool may not grow to four threads.

**Exercise 3 — Busy handlers.** Remove `Thread.sleep(250)` or raise it to 1000ms. Observe `HANDLER_PEAK` and total processing time. Does peak always equal `maxConcurrentConsumers`? Why or why not?

**Exercise 4 — Default TaskExecutor.** Remove `factory.setTaskExecutor(executor)` so DMLC uses internal `SimpleAsyncTaskExecutor`. Measure thread names in callbacks and invoker counts via the registry. Why is there no shared `getPoolSize` for this executor?

**Exercise 5 — Multi-instance.** With three pods and `2-6` consumers per pod, estimate the upper bound of total consumers, then explain why actual broker metrics might be lower.

**Exercise 6 — Broker failure.** Stop Artemis while the app is running; watch DMLC recovery, active/scheduled counts, and `ThreadPoolTaskExecutor`. Restart the broker and verify message flow resumes. Never test this failure in production.

**Exercise 7 — Isolation.** Add an `@Async` service using a dedicated executor, then compare with sharing `ordersExecutor`. What happens if JMS invokers hold all pool threads?

**Exercise 8 — Transactions.** Make the handler throw an exception for a specific message using a transacted session, and observe redelivery and DLQ policy. Why does simply adding threads not cure a poison message?

## 18. Self-Check Questions

**1.** What executor does DMLC use by default?

`SimpleAsyncTaskExecutor`, not a reusing thread pool like `ThreadPoolTaskExecutor`.

**2.** What minimum/maximum does `setConcurrency("5")` correspond to?

Minimum=1, maximum=5 in DMLC, not five fixed consumers.

**3.** How do `getScheduledConsumerCount()` and `getActiveConsumerCount()` differ?

Scheduled counts invokers scheduled by the container; active counts invokers actually running. Scheduled can be higher than active if the executor has not yet allocated threads to run tasks.

**4.** Why can pool `activeCount` exceed the number of handlers currently processing?

JMS invoker tasks may be blocked on `receive()`, holding threads without executing a business callback yet.

**5.** Does setting `maxPoolSize=6` guarantee `ThreadPoolTaskExecutor` grows to six threads?

No. If `queueCapacity` is large, new tasks can queue behind core threads instead of spawning extra threads up to maximum.

**6.** Does an invoker spawn a new task after every JMS message?

Not by default. A DMLC invoker typically runs a receive loop and can process multiple messages within the same task.

**7.** Which API retrieves the container created by `@JmsListener(id="ordersTasks")`?

`JmsListenerEndpointRegistry.getListenerContainer("ordersTasks")`, followed by checking for DMLC type before reading runtime counters.

**8.** Do `SimpleMessageListenerContainer` and `DefaultMessageListenerContainer` share the same `TaskExecutor` ACK behavior?

No. SMLC can dispatch callbacks to another thread and alter the ACK timing; read its own Javadoc.

**9.** Does concurrency "2-6" apply across an entire multi-pod cluster?

No. It applies per listener container on each instance.

**10.** Which metric accurately reflects how many business callbacks are currently running?

Instrumentation such as `handlerInFlight` incremented/decremented inside the callback, rather than `poolSize` or configured max alone.

## 19. Official References

- Spring Framework 6.1 — `DefaultMessageListenerContainer` Javadoc: https://www.springframework.org/spring/docs/6.1.11/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html
- Spring Framework 6.1 — `DefaultJmsListenerContainerFactory` Javadoc: https://www.springframework.org/spring/docs/6.1.0-RC2/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html
- Spring Framework — Annotation-driven Listener Endpoints: https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html
- Spring Framework — JMS receiving and listener containers: https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html
- Spring Framework 6.1 — `ThreadPoolTaskExecutor` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Framework 6.1 — `SchedulingTaskExecutor` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/scheduling/SchedulingTaskExecutor.html
- Spring Framework — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework — `SimpleMessageListenerContainer` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.0-M3/javadoc-api/org/springframework/jms/listener/SimpleMessageListenerContainer.html
- Spring Framework 6.2 Release Notes — idle scheduling changes and virtual thread support: https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.2-Release-Notes
- Spring Boot 3.3 — JMS/Artemis support: https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html

**Remember:** `TaskExecutor` runs DMLC's **invoker tasks**, while `concurrency` sets consumer bounds. To know "how many actual threads", correlate **configured min/max**, **scheduled/active invokers**, **pool threads**, **handlerInFlight**, and broker-reported consumer counts. A single thread dump snapshot does not replace workload and transaction behavior measurements.
