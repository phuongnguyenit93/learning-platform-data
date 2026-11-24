# maxMessagesPerTask and Receive Task Lifecycle in DefaultMessageListenerContainer

**Topic:** Spring Framework - jms → Default container.

## 1. What Problem Does maxMessagesPerTask Solve?

When an application uses `@JmsListener` with Spring JMS's `DefaultMessageListenerContainer`, receiving messages does not happen via Spring making a single `receive()` call and exiting. The container runs **receive tasks (consumer/invoker tasks)**: each task repeats waiting for/receiving a JMS message, invoking the listener when a message arrives, and continuing.

Configuration:

~~~java
container.setMaxMessagesPerTask(10);
~~~

sets a limit on **the number of receive attempts within a single task execution**. Per Spring Framework 6.2 Javadoc, this counter includes both:

- Calls where `MessageConsumer.receive(...)` returns a JMS message and the listener processes it.
- Calls where `receive(...)` hits `receiveTimeout`, returning `null` because no message is available.

That is the most easily misunderstood aspect of the property name **maxMessagesPerTask**: looking closely at the implementation, it is a limit on *receive attempts per task*, **not** a guarantee of processing exactly N business messages in a batch.

Hypothetical example with `maxMessagesPerTask = 4`:

| Receive attempt | Receive result | Actual messages processed | Receive attempts used |
| --- | --- | ---: | ---: |
| 1 | Message A | 1 | 1 |
| 2 | Timed out, `null` | 1 | 2 |
| 3 | Message B | 2 | 3 |
| 4 | Timed out, `null` | 2 | 4 |
| Task turn ends | May yield/reschedule per container | **2**, not 4 | **4** |

**The limit applies only to a single task execution.** It does not cap the total messages a consumer processes over the application's lifetime, does not delete remaining messages in the queue, and does not order the entire listener container to stop.

A container can still process millions of messages across **many task executions**; core consumers are maintained per configuration and necessary tasks continue to be scheduled.

This lesson uses **Spring Framework 6.2.x, Spring JMS, and Jakarta Messaging 3.1** with Java **17+**. Spring Boot 3.x projects use the same configuration approach via `DefaultJmsListenerContainerFactory`. Note that older versions may differ in default details; the limit and idle behavior descriptions are based on Spring Framework 6.2 Javadoc.

## 2. Distinguishing Message, Receive Attempt, Task, Consumer, Thread, and Container

These six concepts are **not synonymous**:

| Concept | Description | Lifetime |
| --- | --- | --- |
| **JMS message** | Unit of data delivered by the broker | From send until processed/acked/expired per policy |
| **Receive attempt** | One receive call cycle that may succeed or time out | Measured per `receive(...)` call |
| **Consumer task/invoker** | Work executed by Spring `TaskExecutor`; contains a loop of multiple receives | Bounded by `maxMessagesPerTask` or potentially long-lived |
| **JMS MessageConsumer** | Client object receiving messages from a destination | May be retained/cached or recreated depending on cache level/transaction/recovery |
| **Thread** | Executor thread running the task | May be dedicated to the task or reused via a thread pool |
| **Listener container** | `DefaultMessageListenerContainer` managing consumers, lifecycle, connections, and dispatch | Typically lives for the application/context lifetime |

A **task** is not a **message**. A **task** also does not necessarily equal one **thread** forever: a thread pool may run many tasks sequentially on the same thread; a non-pooling executor may spawn a new thread for the next task.

Conceptual diagram:

~~~text
                    Spring ApplicationContext
                            |
               DefaultMessageListenerContainer
                            |
             core consumers / surplus consumers
                            |
                        TaskExecutor
                            |
                   Async invoker task
                            |
                +-----------+-----------+
                |                       |
           receive() #1              ...
                |
          Message or null
                |
          Message -> listener
          null    -> idle signal
                |
           receive() #2
                |
               ...
                |
      reaches maxMessagesPerTask or
      idle/recovery/shutdown condition
                |
             task finishes
                |
    container considers reschedule/scale-down
    (core consumers are still maintained)
~~~

Setting `maxMessagesPerTask=3` can cause a core consumer to be **rescheduled onto another task** after three receive attempts. It does **not** close the application context, destroy the destination, or stop the ability to keep receiving messages.

## 3. Why Does DefaultMessageListenerContainer Have a Receive Loop?

`org.springframework.jms.listener.DefaultMessageListenerContainer` is a listener container using the **polling-style JMS client API**, specifically looping on `jakarta.jms.MessageConsumer.receive(...)`. This differs from `SimpleMessageListenerContainer`, which relies on registering a provider callback via `MessageConsumer.setMessageListener(...)`.

Typical processing flow:

1. The container initializes JMS connections/sessions/consumers per `ConnectionFactory` and configuration.
2. The container submits one or more **invoker tasks** to `TaskExecutor`.
3. Each task runs a message receive loop.
4. When a message arrives, Spring dispatches it to `@JmsListener`/message listener adapter, handling ack/transactions per configuration.
5. When `null` is returned after timeout, the container records an empty (idle) receive.
6. After the receive attempt limit or an idle/lifecycle condition, the task ends or is rescheduled.
7. The container maintains core consumers while scaling surplus consumers up/down.

`DefaultMessageListenerContainer` suits native JMS environments and environments needing transactions/recovery/caching. Distinguish it from **`JmsTemplate.receive(...)`**: `JmsTemplate` is a synchronous receive initiated by application code; the Default container is **background listener** infrastructure for annotated endpoints.

### 3.1. Why Limit Task Lifetimes?

In a **non-pooling** executor, keeping consumer tasks on the same thread long-term is often efficient due to minimal rescheduling. In a **thread pool** executor, a task holding a thread forever makes it difficult to share the pool with other work. Finite tasks allow the executor to rebalance work periodically.

| Long-lived task | Short-lived task |
| --- | --- |
| Less scheduling/task-switching overhead | More flexible when sharing a thread pool |
| Can hold a thread for a long time | Can release threads between turns |
| Suits simple executors, dedicated consumer threads | Often useful with pooled/`SchedulingTaskExecutor` |
| If misconfigured, can monopolize the thread pool | If too short, can increase overhead and churn |

**There is no universally best choice.** It depends on thread model, receive timeout, throughput, idle patterns, Session/consumer caching, provider, and resource limits.

## 4. Default Value: -1 or 10?

Spring 6.2 Javadoc explains: `maxMessagesPerTask` **does not have a single default number across all `TaskExecutor`s**.

| Task executor used by container | Default maxMessagesPerTask | Reason |
| --- | ---: | --- |
| Default `SimpleAsyncTaskExecutor` or standard executor not preferring short tasks | **-1** (unlimited receive attempts per task) | Keeps invoker/thread long-lived until shutdown or other lifecycle events |
| `SchedulingTaskExecutor` reporting `prefersShortLivedTasks() == true` | **10** | Gives the executor opportunities to schedule shorter tasks |
| Application explicitly calls `setMaxMessagesPerTask(20)` | **20** | Overrides auto-selected value |
| Application explicitly calls `setMaxMessagesPerTask(3)` | **3** | Example illustrating frequent task turnover |

For pools preferring short tasks, Spring documentation suggests considering roughly **10–100 receive attempts per task** to balance overhead and fairness. This is a tuning guideline, **not a hard API constraint**; the value `3` in the demo simply makes observation easier.

### 4.1. Why -1 Does Not Mean the Listener Has One Eternal Task

`-1` means **no cap on receive count for a task via this property**. A task can still terminate due to stop/shutdown, connection errors/recovery, idle conditions on surplus consumers, or other lifecycle events.

Do not write "-1 prevents the container from ever restarting" or "-1 cannot scale down". `maxMessagesPerTask` is only **one** condition in the task lifecycle.

### 4.2. How Does a Thread Pool Signal a Short-Lived Preference?

Spring's `org.springframework.scheduling.SchedulingTaskExecutor` interface has the method `prefersShortLivedTasks()`. If the active executor implements this interface and returns `true`, `DefaultMessageListenerContainer` takes that preference into account when choosing the appropriate default limit.

Not every class with "pool" in its name causes Spring to automatically pick 10 across all versions/configs. Observe the actual value via `getMaxMessagesPerTask()` on the created container; when certainty is needed, **set an explicit value**.

## 5. Configuration APIs and Related Classes

On a concrete container:

~~~java
import org.springframework.jms.listener.DefaultMessageListenerContainer;

DefaultMessageListenerContainer container =
        new DefaultMessageListenerContainer();

container.setMaxMessagesPerTask(30);
int configured = container.getMaxMessagesPerTask();
~~~

This is a snippet that **does not yet create a working listener**, since `ConnectionFactory`, destination, and message listener are missing. It only illustrates the setter/getter API.

With `@JmsListener`, the common approach is configuring a **factory** so every endpoint it creates receives the same parameters:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
class ListenerConfig {

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrency("1-3");
        factory.setMaxMessagesPerTask(30);
        factory.setReceiveTimeout(1_000L);
        factory.setSessionTransacted(true);
        return factory;
    }
}
~~~

This is a valid Spring Framework 6.x configuration when a `ConnectionFactory` bean exists, though without its own runnable broker/consumer. The method named `jmsListenerContainerFactory` creates the **default factory bean** used by `@JmsListener` when the annotation omits `containerFactory`.

Specifically:

- `DefaultMessageListenerContainer.setMaxMessagesPerTask(int)` applies to a **container instance**.
- `DefaultJmsListenerContainerFactory.setMaxMessagesPerTask(Integer)` applies to **containers created by the factory**.
- `@JmsListener` **does not** have a direct `maxMessagesPerTask` attribute to write `@JmsListener(maxMessagesPerTask=...)`.
- You can create **multiple listener factories** for groups of endpoints requiring separate thread/idle/timeout policies.

### 5.1. Selecting a Custom Factory on @JmsListener

~~~java
@Bean("shortTaskJmsFactory")
DefaultJmsListenerContainerFactory shortTaskJmsFactory(
        ConnectionFactory connectionFactory) {

    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setMaxMessagesPerTask(20);
    factory.setReceiveTimeout(500L);
    return factory;
}
~~~

Listener:

~~~java
@JmsListener(
    destination = "demo.task.events",
    containerFactory = "shortTaskJmsFactory")
public void onEvent(String body) {
    System.out.println(body);
}
~~~

These are **two snippets**, which must be placed in Spring-managed configuration/components with proper imports. The name `shortTaskJmsFactory` is a **bean name**, not a destination. A listener omitting `containerFactory` uses the default factory rather than automatically picking this custom factory.

### 5.2. Do Not Confuse with JmsTemplate Configuration

`JmsTemplate.setReceiveTimeout(...)` configures the timeout for **`JmsTemplate`'s synchronous receive calls**. It **does not** automatically set `maxMessagesPerTask` or the listener container's receive timeout.

With `DefaultMessageListenerContainer`, the timeout is set on the container/factory:

~~~java
factory.setReceiveTimeout(1_000L);
~~~

In Spring Framework 6.2, the Default container defaults to **1000 ms** per receive round, unlike the indefinite wait default of a synchronous `JmsTemplate` receive call (if unconfigured). Do not share one configuration value assuming the two APIs are the same.

## 6. Relationship with receiveTimeout: Duration of One Receive Attempt

`receiveTimeout` specifies **the maximum wait time per message check** of one receive attempt.

| Configuration | Behavior in Default container |
| --- | --- |
| `setReceiveTimeout(1_000L)` | Each receive can wait roughly 1 second before returning null |
| `setReceiveTimeout(250L)` | Can detect idle/stop sooner, but increases polling frequency |
| `setReceiveTimeout(5_000L)` | Each receive waits longer when no message is available |
| `setReceiveTimeout(0L)` | Receive can wait indefinitely; with listener containers/transactions this can hinder shutdown and should not be used casually |
| Negative values like `-1L` | No-wait receive; can make an empty receive loop spin rapidly |

Example configuration:

~~~java
factory.setMaxMessagesPerTask(3);
factory.setReceiveTimeout(1_000L);
~~~

If the queue stays empty across three receive attempts, a task can wait roughly **3 seconds** plus overhead to finish three attempts. If messages arrive, the processing cycle also includes handler time, ack/transactions, and provider operations.

**Do not treat** `maxMessagesPerTask * receiveTimeout` as a **hard deadline** for the task: messages may arrive immediately, handlers may run long, and retries/recovery may add time. The limit is **number of receive attempts**, not a wall-clock timer for task lifetime.

### 6.1. What About an Infinite Timeout?

If a `receive()` call waits indefinitely because no message exists, the `maxMessagesPerTask` counter **does not advance until that receive call returns**. Hence even `maxMessagesPerTask=1` does not force a blocking `receive(0)` to exit after 1 second. Timeout selection must evaluate shutdown responsiveness and transaction timeouts separately.

### 6.2. Counting Attempts Without Confusing Them with Messages

Suppose `maxMessagesPerTask=5`, `receiveTimeout=1000`, and a task encounters the sequence:

~~~text
receive #1 -> Message A
receive #2 -> null (timeout)
receive #3 -> Message B
receive #4 -> null (timeout)
receive #5 -> null (timeout)
--------------------------
5 attempts, 2 messages processed
task reached attempts ceiling
~~~

When the task hits the threshold, the container can reschedule the work or let a surplus consumer exit if idle/scale-down conditions are met. That is not a "5-message batch".

## 7. Idle Behavior: Three Easily Confused Settings

Alongside `maxMessagesPerTask`, Spring 6.2's `DefaultMessageListenerContainer` has very important **idle-related** properties.

| Property | API on DefaultMessageListenerContainer | Unit | Meaning |
| --- | --- | --- | --- |
| `maxMessagesPerTask` | `setMaxMessagesPerTask(int)` | **Receive attempts/task** | Lets a task yield/rotate turns after a number of receive attempts |
| `idleReceivesPerTaskLimit` | `setIdleReceivesPerTaskLimit(int)` | **Consecutive null receives** | Marks a task idle after a streak of empty receives |
| `idleTaskExecutionLimit` | `setIdleTaskExecutionLimit(int)` | **Task executions marked idle** | Decides whether a surplus consumer should stop after idle rounds |
| `idleConsumerLimit` | `setIdleConsumerLimit(int)` | **Allowed idle consumers** | Adjusts conditions for scheduling new invokers |
| `receiveTimeout` | `setReceiveTimeout(long)` | Milliseconds per receive | Affects the rate at which null/idle events occur |
| `concurrentConsumers` | `setConcurrentConsumers(int)` | Core consumer count | Minimum consumers maintained |
| `maxConcurrentConsumers` | `setMaxConcurrentConsumers(int)` | Max consumer count | Ceiling for adding surplus consumers |

The first three properties are not the same kind of limit: **attempts**, **consecutive idle receives**, and **idle task executions**. Do not interchange them.

### 7.1. idleReceivesPerTaskLimit

Per Spring 6.2 Javadoc, `idleReceivesPerTaskLimit` marks a task idle once enough consecutive receives return `null` after timeout. It is useful if you want a task to be deemed idle **before hitting a large `maxMessagesPerTask`**.

Conceptual example:

~~~java
container.setMaxMessagesPerTask(500);
container.setIdleReceivesPerTaskLimit(60);
container.setReceiveTimeout(1_000L);
container.setIdleTaskExecutionLimit(1);
~~~

If no messages remain, the task can be marked idle after 60 consecutive empty receives (roughly one minute with `receiveTimeout=1s`), **without waiting for all 500 receive attempts**. Subsequent release/scale-down behavior also depends on whether the task is core or surplus, the executor, and other limits.

**Spring 6.2 note:** `idleReceivesPerTaskLimit` on its own primarily affects **surplus consumers** beyond core; for core consumers, rescheduling behavior also involves `maxMessagesPerTask` and the executor. It is not a command that shrinks consumers below `concurrentConsumers`.

### 7.2. idleTaskExecutionLimit

`idleTaskExecutionLimit` defaults to **1**. It limits how many task executions are deemed idle before a **surplus consumer** should leave the receiving pool, avoiding holding resources after load drops.

Suppose an elastic configuration:

~~~java
container.setConcurrentConsumers(1);
container.setMaxConcurrentConsumers(4);
container.setIdleTaskExecutionLimit(3);
~~~

When the queue is busy, consumers can scale up to 4 if scheduling conditions allow. When quiet long enough, surplus consumers can stop one by one; **the minimum 1 core consumer is still maintained** until container stop/shutdown.

A limit of 3 does not mean the consumer stops after three messages. It is a limit on **idle task executions**, not successful message count.

### 7.3. idleConsumerLimit

`idleConsumerLimit` defaults to **1**. It limits how many idle consumers the container tolerates when considering scheduling additional invokers. Raising this value can make the container spawn invokers more aggressively to stay ready, at the cost of extra JMS resources.

Do not raise `idleConsumerLimit` just to "process 10 messages per task". The two goals are different: **aggressiveness when scaling up** versus **task receive-attempt lifespan**.

### 7.4. What Does the Default of 10 Idle Receives Apply To?

With the default/simple non-pooling executor in Spring 6.2, `idleReceivesPerTaskLimit` has an effective default of **10 for surplus consumers**. With the default 1000 ms receive timeout and continuously no messages, a surplus task can scale down after roughly **10 seconds** of empty receives, depending on other factors.

Do not confuse that 10 with the `maxMessagesPerTask=10` default of an executor preferring short-lived tasks. Those two "10"s appear in **two different contexts and two different counters**.

## 8. Task Lifecycle During Container Dynamic Scaling

Dynamic scaling is not enabled by `maxMessagesPerTask` alone. It requires:

~~~java
container.setConcurrentConsumers(1);
container.setMaxConcurrentConsumers(5);
~~~

The container is permitted to run **at least 1 and at most 5 consumers**. When messages arrive, it can schedule additional invokers within this range if conditions permit. When messages drain and idle limits are exceeded, surplus consumers scale down.

~~~text
When idle:
    core = 1 consumer

Load rises:
    core 1 -> 2 -> 3 ... max 5
    (not creating a consumer per message)

Load drops:
    surplus consumers become idle
         |
         v
    idleReceive / idleTaskExecution logic
         |
         v
    surplus consumers exit
    core 1 is still maintained

Container stop:
    tasks/consumers are stopped per lifecycle
~~~

A few rules to remember:

- `maxMessagesPerTask` governs **each task execution's length in receive attempts**.
- `maxConcurrentConsumers` governs **how many consumers can exist at most**.
- `idleTaskExecutionLimit` and `idleReceivesPerTaskLimit` influence when **surplus consumers** scale down.
- `idleConsumerLimit` influences **scheduling additional** consumers.
- `receiveTimeout` influences how long one receive attempt waits for a message.
- A task finishing **does not** drop core consumers below `concurrentConsumers`.
- There is no promise the container hits max consumers immediately when queue depth is high; scaling depends on algorithm/demand/provider and executor.

### 8.1. Caution When Using Topics

With a traditional Topic, creating multiple consumers/subscriptions can cause **the same event to be received multiple times** within the same instance, depending on subscription configuration. The Default container's dynamic scaling fits **Queues** better; Spring Javadoc typically recommends keeping **one consumer** for Topics unless a provider-specific setup guarantees what you need.

If business logic requires messages to be processed in strict order, increasing concurrent consumers on a Queue can also break ordering expectations because multiple listener methods run in parallel. In that case, choose `concurrentConsumers=1` or use provider-supported JMS message groups/partitioning and test thoroughly.

## 9. Java 17+ Configuration in Spring Boot 3.x with Artemis

This complete example illustrates:

- Configuring a `DefaultJmsListenerContainerFactory` with `maxMessagesPerTask=3`.
- Setting `receiveTimeout=500 ms` so empty receives do not block too long.
- Using only **1 consumer** in the demo, avoiding concurrency and ordering nondeterminism.
- Registering `@JmsListener` with an ID and verifying the actual container uses the config.
- Sending **6 messages** and verifying the listener still processes all of them, even though each task execution is capped at 3 receive attempts.

### 9.1. Preparation

Create a Maven project at [Spring Initializr](https://start.spring.io/) with Java 17+, Spring Boot **3.x**, group `com.example`, artifact `jms-task-lifecycle-demo`, and dependency **Spring for Apache ActiveMQ Artemis**, corresponding to the Maven starter:

~~~text
org.springframework.boot:spring-boot-starter-artemis
~~~

You need an **Artemis broker running outside the process** at `tcp://localhost:61616`. The broker must allow the application's user/password to connect, send, and consume queue `demo.task.lifecycle`. Either pre-create the queue or allow auto-create per broker policy. Use a clean queue with no other consumers for easily verifiable output.

Set environment variables `ARTEMIS_USER` and `ARTEMIS_PASSWORD` matching the broker. Do not commit real passwords to Git.

File `src/main/resources/application.properties`:

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=${ARTEMIS_USER}
spring.artemis.password=${ARTEMIS_PASSWORD}
spring.jms.pub-sub-domain=false
~~~

`spring.artemis.mode=native` **does not start an Artemis broker automatically**. Boot only configures the JMS client from properties and dependencies; queue creation and security permissions belong to the broker.

### 9.2. Complete Java Code

File `src/main/java/com/example/JmsTaskLifecycleApplication.java`:

~~~java
package com.example;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.jms.ConnectionFactory;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.listener.DefaultMessageListenerContainer;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableJms
public class JmsTaskLifecycleApplication {

    private static final String QUEUE = "demo.task.lifecycle";

    public static void main(String[] args) {
        SpringApplication.run(JmsTaskLifecycleApplication.class, args);
    }

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrency("1");
        factory.setMaxMessagesPerTask(3);
        factory.setReceiveTimeout(500L);
        factory.setSessionTransacted(true);
        return factory;
    }

    @Bean
    ApplicationRunner demo(
            JmsTemplate template,
            TaskLifecycleListener listener,
            JmsListenerEndpointRegistry registry) {

        return args -> {
            var endpoint =
                    registry.getListenerContainer("taskLifecycleEndpoint");

            if (!(endpoint instanceof DefaultMessageListenerContainer dmlc)) {
                throw new IllegalStateException(
                        "Expected DefaultMessageListenerContainer");
            }

            System.out.println("MAX_ATTEMPTS="
                    + dmlc.getMaxMessagesPerTask());

            for (int i = 1; i <= 6; i++) {
                template.convertAndSend(QUEUE, "event-" + i);
            }
            System.out.println("SENT=6");

            boolean allReceived = listener.awaitAll();
            System.out.println("ALL_RECEIVED=" + allReceived);
            System.out.println("HANDLED_COUNT=" + listener.handledCount());
        };
    }
}

@Component
class TaskLifecycleListener {

    private final AtomicInteger handled = new AtomicInteger();
    private final CountDownLatch latch = new CountDownLatch(6);

    @JmsListener(
            id = "taskLifecycleEndpoint",
            destination = "demo.task.lifecycle")
    public void receive(String body) {
        handled.incrementAndGet();
        System.out.println("HANDLED=" + body);
        latch.countDown();
    }

    boolean awaitAll() throws InterruptedException {
        return latch.await(20, TimeUnit.SECONDS);
    }

    int handledCount() {
        return handled.get();
    }
}
~~~

**Compilation check:** The code has one public class matching the file name and one package-private `@Component` in the same package scanned by Spring Boot. `@EnableJms` enables annotation-driven endpoint registration; in normal Spring Boot this infrastructure can also be auto-configured, yet the annotation is included for learning clarity.

**Configuration check:** `jmsListenerContainerFactory` is the default factory bean name, using the Boot-configured `jakarta.jms.ConnectionFactory`. `factory.setMaxMessagesPerTask(3)` is a real Spring JMS 6.x API; it applies to the `DefaultMessageListenerContainer` created by the factory.

**Listener check:** `@JmsListener(id=...)` creates endpoint `taskLifecycleEndpoint` lookable via `JmsListenerEndpointRegistry`. The code checks `instanceof DefaultMessageListenerContainer` before calling `getMaxMessagesPerTask()`, avoiding a blind cast.

**Result check:** `CountDownLatch(6)` waits for six listener executions; `AtomicInteger` records method invocations, thread-safe even if concurrency is adjusted later. The latch is merely a test/demonstration tool, not a replacement for broker acknowledgment or business transactions.

### 9.3. Run

In the Maven project directory:

~~~bash
mvn spring-boot:run
~~~

If the project has a Maven Wrapper on Windows:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

With valid broker/queue/credentials, a clean queue, and no other consumers, the lines printed by the program include:

~~~text
MAX_ATTEMPTS=3
HANDLED=event-1
HANDLED=event-2
HANDLED=event-3
HANDLED=event-4
HANDLED=event-5
HANDLED=event-6
SENT=6
ALL_RECEIVED=true
HANDLED_COUNT=6
~~~

This is the **expected set of lines**, **not a mandatory stdout order**. `MAX_ATTEMPTS=3` always prints before the `AppRunner` send loop. `SENT=6` may appear before or after some `HANDLED` lines because the listener runs asynchronously. The last two lines print after `awaitAll()` returns; on timeout, error, or stale queue data, `ALL_RECEIVED` may be false and the count may differ from 6. Spring Boot startup logs also appear.

**Key verification point:** Even with `MAX_ATTEMPTS=3`, all **six** messages are still processed during listener operation. Tasks rotate/reschedule, with **no** application-wide message limit of 3.

### 9.4. Why You Cannot Infer "Each Task Handled Exactly 3 Messages" from Logs Alone

Even with six consecutive sends, a task can hit receive attempts returning `null` due to timing, broker delivery, transaction/connection setup, or load shifts. When a task finishes also depends on rescheduling and idle logic.

Reading `HANDLED=...` lines alone is not enough to identify **task boundaries**. To observe task lifecycles, combine Spring JMS debug logs, thread/task executor metrics, and if needed profiling/JFR. In a thread pool, thread names can be reused across multiple tasks, so logging thread names is not a unique task ID either.

### 9.5. Why Did the Demo Choose concurrency = 1?

`maxMessagesPerTask` and `concurrency` are two different parameters. With a single core consumer, the code is easy to observe without explaining interleaving across multiple consumers.

If you switch to:

~~~java
factory.setConcurrency("2-5");
~~~

the container can run 2 core and up to 5 concurrent consumers, with each consumer's task having its own receive-attempt limit. There is no "3-message limit shared across all 5 consumers". Re-test ordering, throughput, database connection pool, and idempotency under concurrent workloads.

## 10. Choosing a TaskExecutor: Dedicated Threads or Thread Pool?

By default, `DefaultMessageListenerContainer` uses `SimpleAsyncTaskExecutor`, spawning worker threads for listener invokers. With the default setup and `maxMessagesPerTask=-1`, invoker tasks can be very long-lived to minimize scheduling overhead.

If integrating with `ThreadPoolTaskExecutor`/a managed thread pool, a JMS consumer holding a thread for the entire pool lifetime can starve other tasks of threads. Finite tasks let the engine schedule in turns.

### 10.1. Dedicated Executor Configuration (Variant, Do Not Mix Into the Demo)

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Bean
ThreadPoolTaskExecutor jmsConsumerExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(8);
    executor.setThreadNamePrefix("jms-consumer-");
    return executor;
}
~~~

In **another factory**, inject the executor and configure:

~~~java
factory.setTaskExecutor(jmsConsumerExecutor);
factory.setMaxMessagesPerTask(20);
factory.setConcurrency("1-4");
~~~

This is an **alternative configuration snippet**, requiring a `jmsConsumerExecutor` bean of the proper type; it is **not** included in the section 9 demo. With a Spring-managed executor bean, Spring performs initialization/shutdown according to the corresponding lifecycle.

When using a thread pool, check:

1. The pool has enough threads for your desired `maxConcurrentConsumers`, plus other workloads if the pool is not dedicated.
2. Queue capacity/rejection policy does not cause JMS invokers to be rejected or starved.
3. `maxMessagesPerTask` is not so large that tasks hold threads nearly forever, yet not so small that it causes excessive rescheduling.
4. Session caching config matches the provider; do not optimize threads while neglecting JMS resources.
5. Shutdown and recovery do not leave tasks blocked indefinitely in `receiveTimeout=0`.

**Advice:** if you only have a few JMS listeners and no managed pool requirement, prefer the simpler setup with the default executor. Integrate a custom pool only when there is a measurable reason and observability.

### 10.2. Benefits and Costs of Limiting Tasks

| Low value, e.g. 3 | Moderate value, e.g. 20–100 | Unlimited, -1 |
| --- | --- | --- |
| Tasks rotate turns frequently | Balances scheduling and task retention | Invokers can run long-term |
| Easy to observe lifecycle in demos | Can suit pooled executors | Suits dedicated threads |
| Can cause context-switch/reinit overhead | Often used as a tuning starting point | Can hold pool threads long-term |
| Does not mean processing exactly 3 messages | Does not mean a 20–100 message batch transaction | Does not mean the container never stops |

There is no guarantee that changing `3 → 20` increases throughput proportionally. JMS send/receive cost, transactions, message size, session caching, and business I/O usually matter more.

## 11. Resource Caching and JMS Session/MessageConsumer Lifecycle

When an invoker task finishes, **do not assume** every JMS `Connection`, `Session`, and `MessageConsumer` is closed immediately and recreated from scratch. Actual resources are governed by:

- `cacheLevel`/`CACHE_AUTO`, `CACHE_CONNECTION`, `CACHE_SESSION`, `CACHE_CONSUMER`.
- Transaction management (local transaction vs. external `PlatformTransactionManager`/JTA).
- JMS provider/client and recovery capability.
- Task rescheduling, consumer scale-up/scale-down, and container stop/shutdown.

In native JMS environments, DMLC typically caches Sessions/MessageConsumers per listener thread to reduce overhead. With an external transaction manager, default caching levels may change to ensure Jakarta EE server compatibility.

### 11.1. CachingConnectionFactory Can Introduce Risks

Spring Javadoc warns that using `CachingConnectionFactory` outside a `DefaultMessageListenerContainer` has caveats, especially with dynamic scaling and custom `maxMessagesPerTask`: a message may be routed to a **cached consumer no longer attached to the listener container** in the way operators expect.

Therefore:

- Avoid automatic "two-layer caching" for a listener container without verifying provider behavior.
- Usually let `DefaultMessageListenerContainer` itself manage JMS resource caching for listeners.
- If `CachingConnectionFactory` must be used, test stop/restart, scaling, provider prefetch, and actual resource cleanup.

`maxMessagesPerTask` is not a "close socket after N messages" mechanism. Do not use it in place of connection recovery, keep-alive, or pool sizing.

### 11.2. Verify Session/Transaction Semantics Before Tuning

With `factory.setSessionTransacted(true)`, each message receive and listener execution is tied to the JMS session transaction per container semantics. A task processing multiple messages **is not** automatically a single transaction bundling all messages in the task.

Nor does a task ending cause unacknowledged messages to be dropped or committed by "batch size". Ack/commit/rollback depend on session policy, listener success/failure, external transactions, and the provider.

## 12. Reliability Impact: Do Not Confuse Task Turnover with Redelivery

Suppose the handler throws an exception on a message. Outcomes may include:

- The container handles the error and rolls back the JMS session (if configured transacted).
- The broker redelivers the message later, per retry/DLQ policy.
- The container continues receiving or recovers connection/session on infrastructure errors.
- The current task may hit its attempt limit or enter recovery, though that **does not** independently decide business transaction outcomes.

It is **false** to say "`maxMessagesPerTask=5` means committing once every five messages." No such rule exists in Spring's Default container.

Example:

~~~java
factory.setSessionTransacted(true);
factory.setMaxMessagesPerTask(5);
~~~

These two lines serve two distinct responsibilities:

1. `sessionTransacted=true`: selects JMS local transactions.
2. `maxMessagesPerTask=5`: caps receive attempts per task execution.

If each message requires atomic DB and JMS operations, a local JMS transaction does not automatically wrap the database in a unified transaction. Consider outbox/inbox, idempotency, or proper JTA/XA coordination as required.

### 12.1. Why Is Idempotency Still Required?

Task turnover does not cause duplicates by design, yet any messaging system can redeliver after failures, rollbacks, or reconnects. Listeners must detect already-processed messages whenever correctness matters.

Rather than trusting "tasks don't restart so duplicates won't happen", design:

- Stable business/event IDs.
- Idempotent processing recorded via unique constraints/inbox.
- Retries with backoff and DLQ for poison messages.
- Logging and metrics separating task lifecycle from delivery count.

### 12.2. AUTO_ACKNOWLEDGE and Transactions

Spring DMLC Javadoc recommends `sessionTransacted=true` or an external transaction manager for critical processing. With DMLC's default `AUTO_ACKNOWLEDGE`, acknowledgment can occur **before listener execution**, so an exception in business code does not automatically guarantee message redelivery.

Do not infer from `maxMessagesPerTask` that a listener guarantees at-least-once/exactly-once. Configure ack/transactions properly and test against a real broker.

## 13. Observing Container and Task State

`JmsListenerEndpointRegistry` allows looking up endpoints by `id`:

~~~java
@JmsListener(
        id = "billingEndpoint",
        destination = "billing.incoming")
public void consume(String body) {
    // ...
}
~~~

An administrative service can inspect:

~~~java
var endpoint = registry.getListenerContainer("billingEndpoint");
if (endpoint instanceof DefaultMessageListenerContainer dmlc) {
    System.out.println("CONFIGURED_MAX_ATTEMPTS="
            + dmlc.getMaxMessagesPerTask());
    System.out.println("CORE_CONSUMERS="
            + dmlc.getConcurrentConsumers());
    System.out.println("MAX_CONSUMERS="
            + dmlc.getMaxConcurrentConsumers());
    System.out.println("SCHEDULED_CONSUMERS="
            + dmlc.getScheduledConsumerCount());
    System.out.println("ACTIVE_CONSUMERS="
            + dmlc.getActiveConsumerCount());
    System.out.println("RUNNING=" + dmlc.isRunning());
}
~~~

This is a **snippet**; `registry` must be injected from the Spring context and the endpoint ID must exist. The getters are real APIs on Spring 6.2 `DefaultMessageListenerContainer`.

### 13.1. Reading the Numbers Correctly

| Metric / Getter | Explanation | What Not to Infer |
| --- | --- | --- |
| `getMaxMessagesPerTask()` | Receive attempt limit per task | Total max messages in the app |
| `getConcurrentConsumers()` | Configured core consumers | Always equals active consumers at every instant |
| `getMaxConcurrentConsumers()` | Configured consumer ceiling | Container always spawns consumers up to ceiling |
| `getScheduledConsumerCount()` | Currently scheduled invokers | Number of messages processed |
| `getActiveConsumerCount()` | Currently active consumers | Queue depth / throughput / committed transactions |
| `isRunning()` | Container started per lifecycle | Broker has messages or business logic succeeded |

Combine with JMS broker metrics such as **queue depth**, **consumer count**, **message age**, and **redelivery/DLQ**, alongside application metrics like **processed/sec**, **handler latency**, **error rate**, and **CPU/thread use**.

### 13.2. Why Thread Name Alone Is Insufficient

In `ThreadPoolTaskExecutor`, one thread may execute task A and then task B. Conversely, with a non-pooling executor, a rescheduled task may run on a different thread. Thus logs like `Thread.currentThread().getName()` only tell you the **executing thread**, not a persistent ID of the "receive task".

To study task-level execution, inspect `org.springframework.jms.listener` logs at DEBUG level in a test environment (avoid overly verbose logging in production), JFR/profilers, or executor instrumentation. Do not use thread counts to infer "one thread per message" when the container uses a receive loop.

## 14. Tuning in Real-World Scenarios

### 14.1. Steady Service, Even Traffic, Low Queue Depth

Starting suggestion:

~~~java
factory.setConcurrency("1");
factory.setReceiveTimeout(1_000L);
// Can keep default maxMessagesPerTask depending on executor.
~~~

With the default executor, keeping long-lived invoker tasks is usually sensible. You are not forced to set a low `maxMessagesPerTask` just because the property exists.

### 14.2. Multiple Listeners Sharing a Thread Pool

If one pool is shared across multiple workloads, prevent a few long-lived JMS receive tasks from monopolizing every thread.

~~~java
factory.setMaxMessagesPerTask(20);
factory.setReceiveTimeout(1_000L);
~~~

This can serve as a starting point, not an "optimal" value for every application. Monitor scheduling fairness, task rejections, pool active count, and queue backlog. If the thread pool is too small or has an unsuitable queue capacity, starvation or unexecuted task submissions can occur.

### 14.3. Bursty Traffic Needing Scale-Up/Scale-Down

Direct container example:

~~~java
container.setConcurrentConsumers(1);
container.setMaxConcurrentConsumers(6);
container.setIdleTaskExecutionLimit(2);
container.setIdleConsumerLimit(1);
container.setMaxMessagesPerTask(30);
container.setReceiveTimeout(1_000L);
~~~

This is an **illustrative configuration**, not benchmarked production settings. Note that each variable affects a distinct aspect: core/max consumers, idle task count, scheduling aggressiveness, attempts/task, and timeout. Raising all parameters simultaneously does not guarantee higher throughput.

### 14.4. Sparse Traffic Wanting Fast Surplus Release

Consider empty-receive settings such as `receiveTimeout` around 250–1000 ms in a test environment, an appropriate `idleReceivesPerTaskLimit`, and a small `idleTaskExecutionLimit`. However, if tuned too aggressively, consumer count can **oscillate up and down continuously** when messages arrive in clusters, increasing connection/session churn.

Do not force core consumers down to 0 by abusing idle limits; DMLC's core min must be maintained per configuration. To pause consumption completely, use lifecycle `stop()` or disable auto-startup with clear operational procedures.

### 14.5. Long-Running Handler

If a listener takes 20 seconds to process a message, `maxMessagesPerTask=3` does not interrupt processing after 3 seconds. The task counts receive attempts and runs the listener synchronously; handler duration extends the task.

To bound business processing duration, use DB/HTTP client timeouts, proper cancellation semantics, bounded queues/concurrency, and observability. Do not use `maxMessagesPerTask` as a business processing timeout.

## 15. Common Mistakes

| Mistake | Why It Is Wrong | Correct Understanding |
| --- | --- | --- |
| `maxMessagesPerTask=5` caps the whole listener at 5 messages | It applies only to one invoker task execution | The container can reschedule to keep consuming |
| A value of 5 always delivers 5 successful messages | Timed-out receive attempts returning null also count | Fewer than 5 messages may be processed in a task |
| Setting this limit reduces consumers to 5 | This is not a concurrency setting | Use `concurrentConsumers`/`maxConcurrentConsumers` |
| Setting this limit commits every 5 messages | It is not a transaction batch size | Ack/commit depends on session/transaction |
| `maxMessagesPerTask=-1` means the thread never stops | Stop/recovery/idle can still take effect | `-1` only removes the per-task attempt cap |
| Container's default `maxMessagesPerTask` is always 10 | Standard executors usually default to `-1` | Check `TaskExecutor` and `prefersShortLivedTasks()` |
| `receiveTimeout=1000` means the whole task lives only 1 second | Timeout is **per receive call** | A task includes multiple attempts + handler time |
| `idleTaskExecutionLimit=3` means 3 idle receives | It counts idle task executions | Distinguish from `idleReceivesPerTaskLimit` |
| Core consumers close after a streak of nulls | Core min is maintained by the container | Primarily surplus consumers scale down |
| Each task corresponds to a new JMS session | Cache level/provider/transactions affect reuse | Do not infer resource lifecycle from task count |
| `maxMessagesPerTask` enables dynamic scaling automatically | Scaling requires `maxConcurrentConsumers > concurrentConsumers` | Coordinate concurrency and idle limits |
| Scaling consumers on a Topic works like a Queue | Topic/subscription semantics differ | Avoid duplicate subscriptions/deliveries |
| Reading thread names in logs tells you task count | Thread pools reuse threads | Measure task/executor separately |
| Setting `JmsTemplate` receive timeout changes listener too | The two components have separate configs | Configure on `DefaultJmsListenerContainerFactory` |
| Raising `maxMessagesPerTask` always boosts throughput | May increase pool starvation | Benchmark handler/broker/pool |
| Lowering `maxMessagesPerTask` always saves memory | May increase task churn/overhead | Monitor actual resources |
| Using `CachingConnectionFactory` everywhere is always better | Can conflict with DMLC caching/scaling | Prefer letting the listener container cache properly |
| DMLC and `SimpleMessageListenerContainer` share the same task loop | Simple relies on provider callbacks | Apply properties to the right container type |

## 16. Testing and Operations Checklist

Use this checklist when tuning `maxMessagesPerTask`:

1. Verify the listener actually uses **`DefaultMessageListenerContainer`**, not `SimpleMessageListenerContainer`.
2. Check `getMaxMessagesPerTask()` on the container registered in the registry.
3. Check core consumers, max consumers, and active/scheduled counts.
4. Identify whether the task executor is `SimpleAsyncTaskExecutor` or a pooled/`SchedulingTaskExecutor`.
5. Check `prefersShortLivedTasks()` or set an explicit limit for certainty.
6. Verify the actual `receiveTimeout` and any transaction manager timeout.
7. Send **more** messages than `maxMessagesPerTask`; verify the listener keeps processing across tasks.
8. Send sparse messages with `null` receives; measure task turnover and idle behavior.
9. Apply bursty load; confirm scale-up does not exceed max and scale-down does not drop below core.
10. Verify concurrency does not break business ordering/idempotency.
11. Test broker restarts, connection recovery, container stop/start, and graceful shutdown.
12. Measure queue depth, latency, throughput, CPU/thread counts, session/consumer counts, task rejections, and GC.
13. If using `CachingConnectionFactory`, specifically test provider prefetch and stop/restart.
14. Verify rollback/redelivery/DLQ when the listener method throws an exception.
15. Record before-and-after benchmark results; change only a few variables per test run to isolate causes.
16. Do not copy demo setting `maxMessagesPerTask=3` straight to production without benchmarking.

### 16.1. Short Test Scenarios

| Scenario | What to Prove |
| --- | --- |
| Send 10 messages, `maxMessagesPerTask=3` | Total processed messages can exceed 3 |
| Empty queue, `maxMessagesPerTask=3`, timeout 500ms | A task can exhaust 3 receive attempts without processing any message |
| Core 1, max 4, traffic rises then falls | Consumer count scales within 1–4 |
| Small thread pool, `maxMessagesPerTask=-1` | Observe thread starvation and pool occupancy |
| Handler failure after receive | Verify transaction/redelivery, **not** by task boundaries |
| Stop container with a very large `receiveTimeout` | Evaluate shutdown responsiveness |
| External `CachingConnectionFactory` enabled | Verify actual caching and consumer lifecycle |
| Messages with `JMSXGroupID`/ordering constraints | Verify grouping/ordering when concurrency changes |

## 17. Self-Check Questions

**Question 1.** Does `maxMessagesPerTask=3` make the listener stop after three messages across the entire application?

**Answer:** No. It limits three **receive attempts per task execution**, and the container can reschedule tasks to continue receiving.

**Question 2.** Out of three receives, two return `null` and one receives a message. Has `maxMessagesPerTask=3` been reached?

**Answer:** All three attempts have been used. In that task, only one message was processed successfully.

**Question 3.** Is Spring DMLC's default `maxMessagesPerTask` always 10?

**Answer:** No. For standard/non-pooling executors the default is **-1**; for `SchedulingTaskExecutor.prefersShortLivedTasks()==true` the default is typically **10** per Spring 6.2 Javadoc.

**Question 4.** Why can `receiveTimeout=0` block a task for a long time even if `maxMessagesPerTask` is low?

**Answer:** The attempts counter only advances when a receive call returns; `receive(0)` can wait indefinitely before that iteration finishes.

**Question 5.** How do `setMaxMessagesPerTask(10)` and `setMaxConcurrentConsumers(10)` differ?

**Answer:** One caps receive attempts per task; the other caps how many consumers can operate concurrently.

**Question 6.** How do `idleReceivesPerTaskLimit` and `idleTaskExecutionLimit` differ?

**Answer:** The former counts consecutive receives returning null within a task; the latter counts task executions deemed idle before a surplus consumer may exit.

**Question 7.** Once a task reaches max attempts, must the JMS `MessageConsumer` close immediately?

**Answer:** Not necessarily. Resource caching, transaction manager, provider, and container lifecycle determine how resources are retained or recreated.

**Question 8.** Does `factory.setMaxMessagesPerTask(5)` automatically spawn 5 threads?

**Answer:** No. Concurrency is governed by `concurrentConsumers`, `maxConcurrentConsumers`, and the executor.

**Question 9.** Why is `maxMessagesPerTask=5` not a "5-message batch commit"?

**Answer:** It only controls the task's receive loop; JMS ack/transaction boundaries are configured separately.

**Question 10.** When using a pooled `TaskExecutor`, what parameters matter besides `maxMessagesPerTask`?

**Answer:** Pool size, queue capacity/rejection, `prefersShortLivedTasks`, receive timeout, concurrency/idle limits, session caching, transactions, and measured throughput.

**Question 11.** When the queue is quiet, are core consumers reduced to 0 by `idleTaskExecutionLimit`?

**Answer:** No. The container maintains at least the configured core consumers until shutdown/stop; surplus consumers are what scale down.

**Question 12.** Can Queue concurrency tuning be applied directly to a Topic?

**Answer:** Do not apply mechanically. Topic/subscription semantics differ and risk duplicate delivery when creating multiple consumers/subscriptions.

**Question 13.** How do you verify which `maxMessagesPerTask` a container uses at runtime?

**Answer:** Look up the container by endpoint ID via `JmsListenerEndpointRegistry`, check `instanceof DefaultMessageListenerContainer`, and call `getMaxMessagesPerTask()`.

**Question 14.** Why did the listener receive all 6 messages in the demo even with `maxMessagesPerTask=3`?

**Answer:** A bounded receive task yields/reschedules; the container continues receiving messages across multiple task executions, with no global limit of 3.

## Official References

- [Spring Framework 6.2 Javadoc — DefaultMessageListenerContainer](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html): how it works, `setMaxMessagesPerTask`, -1/10 defaults, dynamic scaling, idle limits, and caching warnings.
- [Spring Framework 6.2 Javadoc — AbstractPollingMessageListenerContainer](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/listener/AbstractPollingMessageListenerContainer.html): default 1,000 ms `receiveTimeout` and transaction/receive loop.
- [Spring Framework 6.2 Javadoc — DefaultJmsListenerContainerFactory](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html): `setMaxMessagesPerTask(Integer)`, `setReceiveTimeout(Long)`, `setTaskExecutor(Executor)`, concurrency, and factory API.
- [Spring Framework 6.2 Javadoc — SchedulingTaskExecutor](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/SchedulingTaskExecutor.html): `prefersShortLivedTasks()` executor scheduling hint.
- [Spring Framework Reference — Annotation-driven JMS Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html): `@JmsListener`, default factory, and endpoint registration.
- [Spring Framework Reference — JMS Namespace Support](https://docs.spring.io/spring-framework/reference/integration/jms/namespace.html): listener container types and configuration.
- [Spring Boot 3.5 Reference — JMS/ActiveMQ Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html): starters, connections, and native broker.
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): JMS `MessageConsumer.receive`, queue/topic semantics, acknowledgment, and transactions.
