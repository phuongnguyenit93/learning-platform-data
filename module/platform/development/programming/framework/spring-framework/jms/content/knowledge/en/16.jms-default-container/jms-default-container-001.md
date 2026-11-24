# DefaultMessageListenerContainer and the Polling-Based Receive Mechanism in Spring JMS

## 1. The Problem: Why Do We Need a Listener Container?

JMS applications typically must continuously receive messages from a Queue or Topic, convert them into Java data, and then invoke a business handler. If you manually write a loop to open a `Connection`, create a `Session`, receive messages, ACK, and reconnect, each service would have to handle resource lifecycle, exceptions, concurrency, and shutdown on its own.

Spring Framework provides `org.springframework.jms.listener.DefaultMessageListenerContainer` (abbreviated **DMLC**) to run those steps. DMLC is a **message listener container**: the application specifies the destination, consumer configuration, and a listener; the container takes responsibility for registering consumers, receiving JMS messages, invoking the handler, managing transactions, scaling the number of consumers, and recovering connections.

The most important point of this lesson:

> **DMLC uses a blocking/polling `MessageConsumer.receive(...)` loop from Spring consumer tasks. It does not register a callback using `MessageConsumer.setMessageListener(...)` like `SimpleMessageListenerContainer`.**

In Spring documentation, DMLC is called a *polling*-based container. That does **not** mean the application checks the broker once every 1,000 ms. When a `receive(timeout)` call is waiting, an arriving message can wake the call **as soon as the provider delivers the message**; the timeout only defines the maximum wait time when **no message is available yet**.

This lesson is part of the **Default container** group in Spring Framework – JMS. You will:
1. Distinguish DMLC from `SimpleMessageListenerContainer` and `JmsTemplate.receive(...)`.
2. Understand the exact receive loop, `receiveTimeout`, receives returning `null`, consumer tasks, and threads.
3. Configure `DefaultJmsListenerContainerFactory` for `@JmsListener` or use a DMLC bean directly.
4. Tune `concurrentConsumers`, `maxConcurrentConsumers`, caching, idle/task scheduling, and recovery.
5. Understand the impact of local JMS transactions, XA/JTA, acknowledgment, Queue/Topic, and durable subscriptions.
6. Run a Java 17 + Spring Boot + embedded Artemis project, verifying that the application receives three messages without manually writing a polling loop.
7. Have a checklist for testing, diagnostics, and production operations.

The main examples use **Java 17+, Spring Framework 6.x, Spring Boot 3.x, `jakarta.jms.*`**. Do not use Spring Framework 5's `javax.jms.*` for a Boot 3 project.

## 2. Three Commonly Confused Ways to Receive Messages

| Mechanism | Who Performs the Receive? | Main API | Behavior |
|---|---|---|---|
| `JmsTemplate.receive(...)` | The thread **calling** the template | `JmsTemplate.receive`, `receiveSelected` | **Synchronous** receive, returns a message/object or `null` on timeout; the application must actively call it again. |
| `SimpleMessageListenerContainer` | The JMS provider calls the listener | `MessageConsumer.setMessageListener(...)` | Creates a relatively fixed number of Sessions/Consumers, callbacks via the JMS API; limited support for dynamic scaling and external transactions. |
| **`DefaultMessageListenerContainer`** | Spring-managed consumer tasks | `MessageConsumer.receive(...)` loop | Blocking/polling receive, invokes listener within a task, supports dynamic concurrency, caching, transactions, and recovery. |

Specifically:

~~~text
JmsTemplate.receive()
    service thread --------> receive(timeout) --------> return message/null

SimpleMessageListenerContainer
    provider --------> MessageConsumer.setMessageListener(listener)
                         provider invokes callback when a message arrives

DefaultMessageListenerContainer
    Spring consumer task:
       while (container running) {
           Message message = consumer.receive(timeout);
           if (message != null) invoke listener(message);
           maintain transaction / cache / scaling / recovery...
       }
~~~

The diagram above is a **mental model**, not line-by-line DMLC source code. In actual Spring Framework, the logic spans `AbstractPollingMessageListenerContainer`, `DefaultMessageListenerContainer`, and consumer invokers. Do not copy the loop in the diagram as a second listener.

**Why is it called polling if `receive` is blocking?** Because Spring actively repeats the receive call to fetch each message, instead of registering `setMessageListener` and letting the JMS provider invoke a callback. Receive calls **are not necessarily HTTP requests** or network queries to the broker on every iteration; the JMS client/provider may receive data using internal protocols and buffers.

## 3. Lifecycle of a Consumer Task

~~~text
ApplicationContext refresh
   |
   +-> Initialize ConnectionFactory / listener factory
   |
   +-> Create DefaultMessageListenerContainer for endpoint
   |      - destination, selector, QoS/transaction
   |      - concurrentConsumers / maxConcurrentConsumers
   |      - cacheLevel, receiveTimeout, TaskExecutor
   |
   +-> start container (SmartLifecycle)
           |
           +-> Schedule ConsumerInvoker task
                   |
                   +-> Open/obtain Connection, Session, MessageConsumer
                   |
                   +-> consumer.receive(receiveTimeout)
                   |      |
                   |      +-- JMS Message -> invoke listener/adapter/handler
                   |      |                   -> commit/ACK or rollback
                   |      |
                   |      +-- null        -> idle receive / continue loop
                   |
                   +-> Under load: may schedule additional consumer tasks
                   |
                   +-> On stop / connection loss: shutdown/recovery per policy
~~~

Three boundaries to understand:

- **A JMS Session is not arbitrarily thread-safe**. DMLC allocates a Session/Consumer within the invoker's scope according to policy, rather than letting multiple handlers carelessly share a single Session.
- A Java listener bean can be a **singleton**. Multiple concurrent invokers may call the same `@JmsListener` method; handler code must still be thread-safe.
- Receiving a message and processing it successfully are **two different milestones**. A receive returning a message does not guarantee that a database transaction has committed or an external API has finished processing.

### Polling Is Not Equivalent to Busy-Wait

With `receiveTimeout=1000`, an invoker can wait up to 1 second if there is no message. If a message arrives after 30 ms, receive **can return immediately**. This is not a loop like:

~~~java
while (true) {
    if (queueHasMessage()) {
        // ...
    }
    Thread.sleep(1_000);
}
~~~

The snippet above is not DMLC and should not be used to simulate latency. DMLC is built on JMS `MessageConsumer.receive`. The timeout number is the **wait limit on receive**, not a hard sleep between two messages.

## 4. receiveTimeout: The Most Misunderstood Number

`DefaultMessageListenerContainer` inherits `setReceiveTimeout(long)` from `AbstractPollingMessageListenerContainer`. As of Spring Framework 6.2, the default is **1,000 milliseconds**.

| Value | Meaning | Recommendation |
|---|---|---|
| `1000L` | If no message is available, a receive waits at most approximately 1 second before returning `null`. | Suitable default for many applications. |
| `500L` | Waits at most approximately half a second when no message is available. | Simple demos; may cause more timeout/idle accounting iterations. |
| `5000L` | Each receive can wait up to 5 seconds when the queue is empty. | Reduces empty returns frequency but affects responsiveness/tuning/transaction timeout. |
| `0L` | Waits indefinitely on receive. | **Usually avoid**: hard to stop the container cleanly and unsuitable for transaction managers with timeouts. |
| `-1L` (negative) | Performs `receiveNoWait()`. | Do not use as a default to "speed up"; can create overly aggressive polling and unnecessary overhead. |

**Transaction note:** if an external transaction manager is used, `receiveTimeout` should be **smaller than the corresponding transaction timeout**. A receive blocked longer than the transaction duration can cause a rollback/timeout even when no message has arrived yet.

### Example Timeline

~~~text
receiveTimeout = 1000 ms

t=0      ConsumerInvoker calls receive(1000)
t=200    Message A arrives -> receive returns A (does not wait until t=1000)
t=205    Handler A completes; invoker calls receive again
t=1205   No message -> receive returns null
t=1206   Invoker continues or checks idle state
t=1230   Message B arrives, new receive can return immediately
~~~

These timestamps are **illustrative only**; scheduling, transactions, network, and handler duration cause real timings to vary. DMLC does not guarantee millisecond precision, and a receive may fail to complete if the network/provider encounters an issue until the recovery mechanism detects it.

### What Other Properties Is receiveTimeout Not?

- It is not **`JmsTemplate.setReceiveTimeout`**: that setter only governs synchronous receives on a separate template.
- It is not **broker message TTL**: TTL determines when a message expires, not how long a listener waits.
- It is not **delivery delay**: delay is the earliest time a message is delivered; timeout is the wait duration per receive.
- It is not **business handler timeout**: a method executing a long HTTP/DB call is not automatically canceled by Spring after `receiveTimeout`.
- It is not **recoveryInterval**: the interval for retrying broker connection on error.
- It is not **batch interval**: DMLC can receive multiple consecutive messages many times faster than `receiveTimeout`.

## 5. Creating DMLC via DefaultJmsListenerContainerFactory

With `@JmsListener`, the common approach is to create a `DefaultJmsListenerContainerFactory` bean. **The factory does not receive messages directly**; it creates a `DefaultMessageListenerContainer` for each registered endpoint.

Example in Spring Framework 6.x:

`src/main/java/example/jms/PollingContainerConfig.java`:

~~~java
package example.jms;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.listener.DefaultMessageListenerContainer;

@Configuration
@EnableJms
public class PollingContainerConfig {

    @Bean("pollingJmsListenerContainerFactory")
    DefaultJmsListenerContainerFactory pollingFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false);                 // JMS Queue
        factory.setSessionTransacted(true);             // JMS local transaction
        factory.setConcurrency("1-3");                  // core 1, max 3
        factory.setReceiveTimeout(1_000L);             // wait at most ~1 s
        factory.setCacheLevel(
                DefaultMessageListenerContainer.CACHE_CONSUMER);
        factory.setRecoveryInterval(5_000L);
        return factory;
    }
}
~~~

This is a compilable class in a Spring project with `spring-jms` and a valid `ConnectionFactory`. With Spring Boot auto-configuration, **you are not required to declare a factory manually** when the defaults are already appropriate; declare a custom factory when you need specific policy boundaries.

Listener selecting the factory:

~~~java
package example.jms;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderQueueListener {

    @JmsListener(
            id = "pollingOrderConsumer",
            destination = "orders.commands",
            containerFactory = "pollingJmsListenerContainerFactory",
            concurrency = "2-3")
    public void onOrder(String text) {
        System.out.println("received=" + text);
    }
}
~~~

`concurrency="2-3"` on the annotation **overrides** the factory's `setConcurrency("1-3")` for this endpoint. `id` is the container name in `JmsListenerEndpointRegistry`, **not** the JMS consumer name on the broker or the subscription name.

### Default Factory Name

If `@JmsListener` omits `containerFactory`, Spring typically looks up the `jmsListenerContainerFactory` bean as the default factory. If you only create a bean named `pollingJmsListenerContainerFactory`, you must declare that name in the annotation or register a default through configuration. Avoid naming a factory something else and assuming every listener will use it automatically.

### What Does Spring Boot Create for You?

With `spring-boot-starter-artemis`, Spring Boot can automatically create a `ConnectionFactory`, `JmsTemplate`, and an appropriate JMS listener factory when auto-configuration conditions are satisfied. Spring Boot also supports discovering `@JmsListener` when JMS infrastructure is available. However, **do not equate "having the Boot starter" with "having a working broker"**; endpoints/credentials/Queues, broker routing, and transactions must still be configured properly.

## 6. Direct DMLC: @JmsListener Is Not Mandatory

If you need to integrate a legacy listener implementing `jakarta.jms.MessageListener`, you can create the container bean directly:

~~~java
package example.jms;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.Message;
import jakarta.jms.MessageListener;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.listener.DefaultMessageListenerContainer;

@Configuration
public class DirectContainerConfig {

    @Bean
    DefaultMessageListenerContainer directContainer(
            ConnectionFactory connectionFactory) {

        DefaultMessageListenerContainer container =
                new DefaultMessageListenerContainer();
        container.setConnectionFactory(connectionFactory);
        container.setDestinationName("orders.commands");
        container.setPubSubDomain(false);
        container.setConcurrency("1-2");
        container.setReceiveTimeout(1_000L);
        container.setSessionTransacted(true);

        MessageListener listener = (Message message) -> {
            try {
                System.out.println("jmsMessageId="
                        + message.getJMSMessageID());
            } catch (jakarta.jms.JMSException ex) {
                throw new IllegalStateException(
                        "Cannot read JMSMessageID", ex);
            }
        };
        container.setMessageListener(listener);
        return container;
    }
}
~~~

**Do not copy this bean into the same `@JmsListener` demo app pointing to the same Queue** if you expect deterministic output: two containers will act as **two competing consumer groups**. This snippet is an **alternative** to the factory/annotation approach when using a direct listener.

DMLC is a `SmartLifecycle` bean; in a normal Spring context it is initialized/started/stopped according to the container lifecycle. Do not manually call `start()` repeatedly from a constructor or HTTP request without checking its lifecycle.

## 7. Concurrency: Core, Max, and Consumer Invokers

DMLC has two main parameters:
- `setConcurrentConsumers(int)`: the **core/minimum** number of consumers to maintain, default 1.
- `setMaxConcurrentConsumers(int)`: the maximum number the container can scale up to, default 1.

Shorthand syntax:

~~~java
container.setConcurrency("2-5");
// equivalent to core=2, max=5 intent
~~~

| Configuration | Meaning |
|---|---|
| `"1-1"` | One fixed consumer. |
| `"3-3"` | Three fixed consumers; can process the Queue in parallel. |
| `"2-5"` | Keep at least two, scale up to five under load, then scale back to two when idle. |
| `"5"` | Default lower bound is 1, **upper=5**, not fixed five. |
| Omit concurrency | Typically defaults to core=max=1 in DMLC. |

Dynamic scaling depends on message load, invoker scheduling, idle counters, `TaskExecutor`, and provider limits; `maxConcurrentConsumers=5` is a **ceiling**, not a guaranteed number of active threads.

### Illustration with Three Application Replicas

~~~text
3 replicas × (core 2, max 5) on the same Queue

Total core around 6 JMS consumers
Total max around 15 JMS consumers
(excluding other endpoints)
~~~

When the same Queue has multiple consumers, messages can be delivered to any eligible consumer, and business **completion order** is no longer guaranteed. Each Session follows JMS sequential rules, but multiple sessions/consumers allow parallel execution. If business logic requires ordering by `accountId` or `orderId`, you need message grouping/partitioning or sequence/idempotency, not just increasing `concurrency`.

### Why Adding Consumers May Not Increase Throughput

- Broker client prefetch buffers messages at a single consumer.
- Database pool exhaustion causes handler threads to wait for connections.
- Downstream API rate-limits or shared locks.
- Long-running transactions increase in-flight messages/rollbacks.
- Message groups require affinity and cannot be distributed evenly.
- Spontaneous extra replicas increase contention instead of speeding up processing.

Increase concurrency based on measurements of **Queue depth, oldest message age, processing time, activeConsumers, DB pool, and broker prefetch**, rather than defaulting to CPU core count as the max.

## 8. TaskExecutor and maxMessagesPerTask

Each consumer invoker is a task submitted by DMLC to a `TaskExecutor`. With the default executor, Spring typically uses `SimpleAsyncTaskExecutor`, and invokers can be long-lived, holding a thread for receiving work.

`setMaxMessagesPerTask(int)` limits the number of **receive attempts** in a single task execution, **including receives that return `null`**, not just successful message processings.

~~~java
container.setMaxMessagesPerTask(50);
~~~

With this configuration, an invoker task yields/reschedules after at most 50 receive attempts (unless terminated earlier by idle/error/shutdown). Do not call it a business payload batch size or "50 messages guaranteed to be processed".

### Default Value Depends on the Executor

- With a standard `TaskExecutor`, the default is `maxMessagesPerTask=-1`: a task can run long-term until shutdown/idle policy.
- With a `SchedulingTaskExecutor` that declares a preference for short-lived tasks, the default may be **10 receive attempts/task** so the thread pool can reschedule easily.
- Values of 10–100 can be a starting point when you truly need to share an executor/task pool, but you must measure performance and stop/scale behavior.

A small thread pool with `maxPoolSize=4` will not necessarily handle a DMLC with 10 long-lived consumer tasks: the tasks occupy threads because they continuously wait on receive. **Do not share a bounded thread pool with unrelated work** if polling tasks can exhaust it.

### When Should You Customize TaskExecutor?

Typically only when:
- Running in a Jakarta EE environment with a managed executor.
- You have specific thread naming, lifecycle, or pool resource requirements.
- You want to use Java 21 virtual threads with a supporting Spring version (not needed for Java 17 examples).
- You need control over rescheduling and task monitoring when changing concurrency.

Without a real requirement, let Spring DMLC manage the default executor. Increasing max messages per task merely to "reduce latency" does not necessarily improve responsiveness.

## 9. Idle Counters: Why Consumers Scale Up and Down

DMLC can spawn additional **surplus consumers** when the Queue is busy and scale them down when the Queue is idle.

Three easily confused properties:

| Property | Practical Meaning |
|---|---|
| `idleConsumerLimit` | How many **simultaneously idle** consumers are allowed before restricting creation of new invokers; default 1. |
| `idleTaskExecutionLimit` | After how many task executions deemed idle a surplus invoker may stop; default 1. |
| `idleReceivesPerTaskLimit` | Number of consecutive receive calls returning `null` before a task is marked idle; typically defaults to 10 for surplus consumers with Spring 6.2's default executor. |

For example, a Queue with `core=1,max=4`: when there is a backlog, DMLC can create consumers 2–4. When the backlog clears, surplus consumers go through receive timeouts returning `null`, and then stop according to idle policies. **The minimum core consumer is retained** (unless the container stops or fails).

### Illustrative Scenario

~~~text
receiveTimeout = 1000 ms
maxConcurrency = 4
idleReceivesPerTaskLimit = 10

Queue just ran out of messages
  |
  +-> surplus consumer receives null multiple times
  |
  +-> after about 10 idle rounds (actual time depends on load)
  |
  +-> surplus consumer scales down to core
~~~

This is an approximate description, not a fixed 10-second SLA clock. If new messages arrive in between, the idle counter/marking changes. With a `TaskExecutor` preferring short-lived tasks, `maxMessagesPerTask` and `idleTaskExecutionLimit` also participate in the rescheduling decision.

**Avoid tuning all idle knobs from the start.** For bursty traffic, too low a limit can cause consumers to be created and closed repeatedly; too high a limit can hold broker resources unnecessarily. Observe active/scheduled consumer counts across multiple load cycles before adjusting.

## 10. Caching: Connection, Session, and Consumer

DMLC can cache JMS resources to reduce the overhead of recreating Connection/Session/MessageConsumer between receives.

| Cache level | Meaning |
|---|---|
| `CACHE_NONE` | Does not retain JMS resources for subsequent receives; recreates/reacquires as needed. |
| `CACHE_CONNECTION` | Caches Connection, acquires Session/Consumer per receive. |
| `CACHE_SESSION` | Caches Connection and Session, but does not retain Consumer. |
| `CACHE_CONSUMER` | Caches Connection, Session, and MessageConsumer; efficient for long-running receive loops. |
| `CACHE_AUTO` | Spring selects the caching level based on the transaction strategy. |

**Practical default of `CACHE_AUTO`:**
- **Without an external transaction manager:** DMLC typically selects `CACHE_CONSUMER`.
- **With an external transaction manager:** DMLC defaults to `CACHE_NONE` so JMS resources are properly enlisted in each transaction in XA/Jakarta EE environments.

This is especially important when using `JtaTransactionManager`. Some application servers require a connection/session to be freshly acquired within the transaction scope to enlist XA. Do not force `CACHE_CONSUMER` with XA without verifying compatibility; it may cause messages to fall outside the intended transaction.

### Is an External CachingConnectionFactory Needed?

Not by default. DMLC already has caching **built into the container lifecycle**. Adding `org.springframework.jms.connection.CachingConnectionFactory` on top can create **two-tier caching**, which behaves unpredictably with dynamic scaling and container restarts. Spring Javadoc notes that an externally cached consumer can hold prefetched messages even after leaving the container.

If the application uses `CachingConnectionFactory` for a **producer `JmsTemplate`**, the listener container should not necessarily use the same wrapper. Read the Spring/provider documentation and test shutdown/restart/failover before applying it.

### Caching and Non-Durable Topics

A non-durable Topic subscription can disappear when a consumer closes. If caching is disabled and the container repeatedly creates/closes consumers, messages published during the gap without a subscription may **not be retained for later delivery**. For Topics, caching level and subscription durability must be designed together.

## 11. Transactions, ACK, and Handler Errors

Receiving a message in the container does not mean the message is **completed**. Behavior on error depends on the transaction or ACK mode.

| Configuration | When Handler Succeeds | When Handler Throws an Exception |
|---|---|---|
| `AUTO_ACKNOWLEDGE` by DMLC default | The message may already be ACKed **before** the listener runs. | **Redelivery is not guaranteed**; Spring warns about auto-ack before listener execution. |
| `sessionTransacted=true` (local JMS transaction) | Session commits after successful invocation. | Container rolls back the JMS session; provider applies redelivery policy. |
| Appropriate external `PlatformTransactionManager` | Receive/handler can participate in the transaction manager. | Transaction can roll back; must verify resource enlistment/XA. |
| `CLIENT_ACKNOWLEDGE`/other modes | Follows the specific container/provider contract. | Do not infer exactly-once from ACK mode alone. |

**Common safe choice:** configure `setSessionTransacted(true)` for critical Queue listeners, then verify broker redelivery, max attempts, backoff, DLQ, and idempotency.

Example:

~~~java
factory.setSessionTransacted(true);
factory.setConcurrency("1-3");
~~~

If `@JmsListener` throws an unchecked exception, the JMS local transaction typically rolls back and the message can be redelivered. However, **rollback does not automatically cap retry attempts** and does not automatically create a DLQ. Those policies belong to the provider/broker and must be configured separately.

### The Database Is Not Automatically in the Same JMS Transaction

Suppose a handler:
1. Updates the database successfully, commits DB.
2. Then the JMS commit fails or the process is killed.
3. The broker redelivers the same message.
4. The handler repeats the side effect.

`sessionTransacted=true` **does not guarantee DB+JMS atomicity**. Use a business event ID + unique constraint/idempotent consumer, transactional outbox/inbox, or JTA/XA if truly needed and supported. You must also test crashing after DB commit but before JMS commit.

### Poison Messages

A malformed JSON message can cause the converter/adapter to throw an exception every time; if the broker retries indefinitely, the container gets stuck. Design max delivery attempts, DLQ/parking queue, replay after fixes, and metrics. **Do not swallow all exceptions in the listener and return normally** when business processing has not finished, because the transaction may commit the failed message.

## 12. Recovery When the Broker Loses Connection

DMLC has built-in recovery capability when the `ConnectionFactory`/broker temporarily fails. According to Spring Javadoc, it defaults to a **5,000 ms** retry interval, which can be adjusted:

~~~java
factory.setRecoveryInterval(5_000L);
~~~

or by using a `BackOff` object supporting another strategy when creating the factory/container, with appropriate configuration order. An example using a container bean:

~~~java
import org.springframework.util.backoff.ExponentialBackOff;

// Configuration snippet if DefaultMessageListenerContainer container already exists.
ExponentialBackOff backOff = new ExponentialBackOff();
backOff.setInitialInterval(1_000L);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(30_000L);
container.setBackOff(backOff);
~~~

This snippet is only a **configuration fragment** in a Spring project that already imports the corresponding classes. Using backoff does not automatically heal lost broker data or expired credentials. When choosing between `setRecoveryInterval` and `setBackOff`, check **which setting takes effect last** according to the API; do not configure both arbitrarily.

### Recovery Does Not Guarantee No Duplicate Messages

When the network drops:
- The container detects a receive error or resource error.
- The container may close/refresh the session/consumer/connection and retry.
- Messages received by the broker/consumer but not yet ACKed/committed may be redelivered.
- Messages that already had business side effects before JMS commit was confirmed may be **reprocessed**.

Therefore, you must check broker state, `JMSXDeliveryCount`, idempotency, and DB outcomes. Container recovery is an **operational capability**, not proof of exactly-once business semantics.

### Connection Failure Is Not the Same as an Empty Queue

- **Empty Queue:** `receive(timeout)` may return `null`; the container continues normal receive/idle accounting.
- **Broker/Connection failure:** `receive`/session may throw a JMS exception; the container enters the setup/recovery path and should not log "no work".
- **Wrong Queue/destination or ACL:** the container may repeat provisioning/authorization errors; alert on these rather than expecting infinite retries to fix them.
- **Messages exist but selector does not match:** the consumer may still receive `null` while Queue backlog grows; inspect JMS properties/selectors.

## 13. Queue and Topic: Why Does Polling Have Specific Limitations?

### Queue

With a Queue, each JMS message is typically delivered to one consumer in the eligible group. DMLC can scale consumers `1-4` to share the load. If business handlers are independent, this is where DMLC shines most clearly: stable polling while scaling up when backlog increases.

However, multiple consumers can break completion ordering, and consumer prefetch can cause uneven distribution. DMLC does not automatically know that "job B must wait for job A of the same order".

### Topic

With a Topic, each independent subscription can receive a **copy** of the event. If you increase concurrency on a non-shared Topic, you may create multiple independent subscriptions and receive **duplicate copies** from a single service's perspective. Per Spring Javadoc, you should not increase concurrent consumers on a regular Topic without an appropriate broker-specific design.

If multiple replicas need to share one subscription, configure a **shared subscription** (and **durable** when offline backlog is needed) with `pubSubDomain=true`, `subscriptionShared=true`, `subscriptionDurable=true`, and a stable subscription name. The provider/client must support JMS 2.0+ shared subscription semantics.

DMLC `CACHE_NONE` with a non-durable Topic risks losing the subscription between consumer recreations. For Topics, caching, durability, and lifecycle must be considered together, not just optimizing throughput.

### Selectors on Consumers

A listener with `@JmsListener(selector = "region = 'EU'")` only selects messages with the matching property. Selectors do not read JSON bodies. Non-matching messages on a Queue may remain on the Queue for other consumers and are not automatically routed to a DLQ. For a Topic, the selector typically determines which messages are added to the subscription upon publish.

**Selectors do not replace isolation/security**. If messages carry sensitive tenant/region data, use ACLs/broker namespaces or separate Queues; properties can be mislabeled by producers.

## 14. Lifecycle: Start, Stop, and Container State

DMLC is a Spring `SmartLifecycle` component. With `@JmsListener`, the container is managed via `JmsListenerEndpointRegistry` by the annotation's `id`.

Complete example class for observation:

~~~java
package example.jms;

import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
public class ListenerStatus {
    private final JmsListenerEndpointRegistry registry;

    public ListenerStatus(JmsListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public boolean isRunning(String id) {
        MessageListenerContainer container =
                registry.getListenerContainer(id);
        return container != null && container.isRunning();
    }
}
~~~

With a specific DMLC, you can inspect `getConcurrentConsumers()`, `getMaxConcurrentConsumers()`, `getActiveConsumerCount()`, and `getScheduledConsumerCount()` for diagnostics via an appropriate container reference.

**Distinguish:**
- `configured core/max`: the configured bounds.
- `scheduled consumers`: the number of invokers currently scheduled.
- `active consumers`: the number of active consumers as managed by the container.
- `message throughput`: the actual number of messages processed, not the number of scheduled consumers.

Do not count JVM threads and conclude "there are 4 consumers running"; threads can belong to task executors and other frameworks. Similarly, `start/stop` on the container does not mean creating/deleting a durable subscription; actual semantics depend on subscription identity and the broker.

### Safe Shutdown

When a pod/service needs to stop:
1. Stop accepting new work via lifecycle/graceful shutdown.
2. Wait for in-flight messages to reach a valid commit/rollback point.
3. Close consumers/sessions/connections via the container.
4. Verify uncommitted messages are handled by the broker according to policy.
5. Use a readiness/termination grace period long enough for business handlers; do not kill the process immediately upon stopping receive if work is still unfinished.

Do not treat `receiveTimeout=1000` as the **total shutdown limit**. An executing business method may take longer; transactions/recovery/connection closing also take time.

## 15. Hands-On Demo: DMLC Polling with Spring Boot and Embedded Artemis

The demo uses **Java 17 + Spring Boot 3.5.16 + embedded Artemis**:
- Creates a `demo.polling` Queue on the embedded broker.
- Creates a `DefaultJmsListenerContainerFactory` with `receiveTimeout=500 ms`, `concurrency="1-2"`, and JMS local transactions.
- `@JmsListener` is registered through that factory; Spring creates a DMLC underneath.
- An `ApplicationRunner` sends three messages using `JmsTemplate` after a short idle interval.
- `CountDownLatch` awaits three messages and `ConcurrentSkipListSet` sorts the output, so the result does not depend on the callback order of the two consumers.

**Important:** the producer **does not call `receive` itself**. DMLC performs it on listener threads. The experiment demonstrates the timeout-based polling mechanism and automatic handler invocation.

### 15.1. Structure

~~~text
jms-polling-lab/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── resources/application.yml
    └── java/example/jms/PollingLabApplication.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-polling-lab'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
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
    runtimeOnly 'org.apache.activemq:artemis-jakarta-server'
}
~~~

The Gradle Spring Boot plugin uses the corresponding Spring BOM, avoiding mixing Jakarta JMS dependencies across major versions. The project requires JDK 17+ and a plugin-compatible Gradle version. This is an **embedded broker for a lab**, without production requirements like TLS/failover.

`src/main/resources/application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
  artemis:
    mode: embedded
    embedded:
      queues: demo.polling
      persistent: false
~~~

Embedded Artemis here uses non-persistent storage to minimize configuration; do not use the demo to claim messages survive restarts.

### 15.2. Complete Java File

`src/main/java/example/jms/PollingLabApplication.java`:

~~~java
package example.jms;

import java.util.List;
import java.util.concurrent.ConcurrentSkipListSet;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

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
import org.springframework.jms.listener.MessageListenerContainer;

@SpringBootApplication
@EnableJms
public class PollingLabApplication {
    private static final String QUEUE = "demo.polling";

    public static void main(String[] args) {
        SpringApplication.run(PollingLabApplication.class, args);
    }

    @Bean("pollingFactory")
    DefaultJmsListenerContainerFactory pollingFactory(
            ConnectionFactory connectionFactory) {
        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false);          // Queue
        factory.setSessionTransacted(true);      // JMS local transaction
        factory.setConcurrency("1-2");          // Core 1, max 2
        factory.setReceiveTimeout(500L);        // At most 500 ms per receive
        factory.setCacheLevel(
                DefaultMessageListenerContainer.CACHE_CONSUMER);
        return factory;
    }

    static final class Results {
        private final ConcurrentSkipListSet<String> messages =
                new ConcurrentSkipListSet<>();
        private final CountDownLatch received =
                new CountDownLatch(3);

        void add(String body) {
            if (messages.add(body)) {
                received.countDown();
            }
        }

        void awaitAll() throws InterruptedException {
            if (!received.await(15, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Timed out waiting for three JMS messages");
            }
        }

        List<String> snapshot() {
            return List.copyOf(messages);
        }
    }

    @Bean
    Results results() {
        return new Results();
    }

    static final class PollingListener {
        private final Results results;

        PollingListener(Results results) {
            this.results = results;
        }

        @JmsListener(
                id = "pollingOrders",
                destination = QUEUE,
                containerFactory = "pollingFactory")
        public void handle(String body) {
            results.add(body);
        }
    }

    @Bean
    PollingListener pollingListener(Results results) {
        return new PollingListener(results);
    }

    @Bean
    ApplicationRunner demonstrate(
            JmsTemplate template,
            Results results,
            JmsListenerEndpointRegistry registry) {

        return args -> {
            MessageListenerContainer container =
                    registry.getListenerContainer("pollingOrders");
            if (!(container instanceof DefaultMessageListenerContainer)) {
                throw new IllegalStateException(
                        "Expected DefaultMessageListenerContainer");
            }

            System.out.println(
                    "CONTAINER=DefaultMessageListenerContainer");

            // Give the container time to call receive while the Queue is empty.
            Thread.sleep(1_200L);

            // Producer sends three messages; DMLC polls and invokes the handler.
            template.convertAndSend(QUEUE, "order-C");
            template.convertAndSend(QUEUE, "order-A");
            template.convertAndSend(QUEUE, "order-B");

            results.awaitAll();

            List<String> actual = results.snapshot();
            List<String> expected =
                    List.of("order-A", "order-B", "order-C");

            if (!actual.equals(expected)) {
                throw new IllegalStateException(
                        "Unexpected results: " + actual);
            }

            for (String item : actual) {
                System.out.println("RECEIVED=" + item);
            }

            System.out.println("ALL_RECEIVED=true");
        };
    }
}
~~~

### 15.3. Step-by-Step Explanation

1. `pollingFactory` is used by Spring JMS to create a **DMLC** when registering `@JmsListener`.
2. DMLC maintains a receive loop for the `demo.polling` Queue. `setReceiveTimeout(500L)` makes receive return `null` when empty after the wait time, **without** forcing every message to wait 500 ms.
3. `setConcurrency("1-2")` allows one core consumer and can add another if load is sufficient; **there is no guarantee it will scale up to 2** just from sending three messages rapidly.
4. `setSessionTransacted(true)` wraps receive/handler in a JMS local transaction; uncommitted messages can be redelivered on failure.
5. `@JmsListener` works automatically, with no `while/receive` code written by the application developer.
6. `Results` uses a concurrent data structure and `CountDownLatch` to avoid reading the collection while another handler is still adding items.
7. `snapshot()` is ordered by `ConcurrentSkipListSet`, so stdout is deterministic even though callbacks can run in parallel and out of send order.
8. `Thread.sleep(1_200L)` only makes the Runner wait before **sending** to illustrate the container is still calling receive while the Queue is empty; it is not a required part of DMLC.
9. The registry check confirms that the Spring container is indeed of type `DefaultMessageListenerContainer`. Spring Boot/Artemis log lines vary by environment.

Note: `Results.add` in the handler writes to memory **before** the JMS transaction commits; the demo does not prove exactly-once database commit. In a real application, business results should be persisted in a transactional resource/idempotent storage before marking success, and failure/recovery must be tested separately.

### 15.4. How to Run and Stdout

In the `jms-polling-lab` directory, use JDK 17+ and a compatible Gradle version.

If Gradle Wrapper is present:

~~~bash
./gradlew bootRun
~~~

If there is no Wrapper, use an installed Gradle:

~~~bash
gradle bootRun
~~~

Windows PowerShell with Wrapper:

~~~powershell
.\gradlew.bat bootRun
~~~

After the startup logs, **the lines printed by the application** when the lab succeeds:

~~~text
CONTAINER=DefaultMessageListenerContainer
RECEIVED=order-A
RECEIVED=order-B
RECEIVED=order-C
ALL_RECEIVED=true
~~~

DMLC may scale from one to two consumers or stay at one, depending on load and scheduling. The output above is sorted in the application and **does not reflect broker dispatch order**. If the broker fails to start, the Queue does not exist, or the consumer does not register in time, the Runner may time out after 15 seconds; this is an active verification check, not a JMS timing guarantee.

### 15.5. Controlled Experiments

- Change `factory.setReceiveTimeout(500L)` to `2_000L`: normally the handler still receives messages quickly when they arrive; there is no "exact 2-second wait".
- Change `setConcurrency("1-2")` to `"1-1"`: a single consumer; the result for the three messages is still correct.
- Set `setConcurrency("3-3")`: multiple core consumers; output is still correct, with additional Sessions/Consumers and potential parallel callbacks.
- Simulate an exception in the handler: with `setSessionTransacted(true)`, observe rollback/redelivery per broker policy; do **not** assume exactly-once automatically.
- Stop the broker or use wrong credentials in an integration environment: observe container recovery and setup failure logs; do not use the embedded lab to draw conclusions about production failover.
- Test multiple replicas and broker prefetch: compare active consumers against Queue depth and processing speed.

## 16. Standalone Java 17 Example: Visualizing Timeout-Based Polling

The small program below only simulates the **waiting/polling principle** using Java's `BlockingQueue`, **not** a JMS implementation. It helps illustrate how "timeout" differs from "fixed sleep" and produces deterministic stdout without depending on a broker:

Create `PollingMentalModel.java`:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;

public class PollingMentalModel {
    public static void main(String[] args) throws Exception {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(2);

        String empty = queue.poll(50, TimeUnit.MILLISECONDS);
        System.out.println("EMPTY=" + (empty == null));

        queue.add("job-1");
        String received = queue.poll(50, TimeUnit.MILLISECONDS);
        System.out.println("RECEIVED=" + received);

        System.out.println("POLLING_IS_NOT_FIXED_SLEEP=true");
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 PollingMentalModel.java
java PollingMentalModel
~~~

Stdout:

~~~text
EMPTY=true
RECEIVED=job-1
POLLING_IS_NOT_FIXED_SLEEP=true
~~~

`BlockingQueue.poll(timeout)` sends no network traffic and has no JMS transactions, broker, or duplicates; it is only an **analogy for the waiting mechanism**. In DMLC, waiting is performed through the JMS provider's `MessageConsumer.receive(timeout)` and a more complex resource lifecycle.

## 17. Observability and Production Operations

Valuable metrics:

| Metric | Why It Is Useful |
|---|---|
| DMLC `activeConsumerCount` and `scheduledConsumerCount` | Shows whether invokers actually scale up/down with concurrency. |
| `concurrentConsumers` and `maxConcurrentConsumers` | Configured limits; not the actual active count. |
| Queue depth, oldest message age, enqueue/dequeue rate | Detects backlog and whether consumers are keeping up. |
| Receive timeouts/idle invokers | Evaluates idle/dynamic scaling cadence; do not treat each timeout as an error. |
| Handler duration p50/p95/p99 | Identifies bottlenecks in business processing rather than the broker. |
| DB pool saturation, HTTP downstream latency | Proves whether increasing concurrency helps or not. |
| JMS exceptions, recovery count, last recovery cause | Distinguishes broker disconnection from an empty Queue. |
| JMS transaction rollback/redelivery/DLQ | Monitors payload errors, poison messages, and reliability. |
| Broker connection/session/consumer count | Prevents exceeding quotas when multiplying max consumers by replicas. |
| Provider prefetch/cache and consumer lag | Detects skewed distribution or consumers holding messages during shutdown. |

When monitoring containers via `JmsListenerEndpointRegistry`, use a stable `@JmsListener(id=...)` and do not attach per-pod changing IDs to the registry. Record metrics by destination, listener ID, and outcome, avoiding high-cardinality dynamic labels such as `userId` or `correlationId`.

### Thread and Pool Checks

If a DMLC with `concurrency="2-6"` runs 4 replicas, the theoretical ceiling is `4 × 6 = 24` consumers for **one endpoint**. If the application has 3 similar endpoints, the total can reach 72, excluding connection/session pools. Consider:

- Broker connection and consumer quotas.
- Spring `TaskExecutor` thread scheduling.
- Memory and CPU per replica.
- Database pools and downstream HTTP connections.
- Transaction/serialization overhead and max in-flight messages.
- Prefetch/message grouping, which affects ordering.

Do not increase all parameters simultaneously. Form a hypothesis, change a single knob, measure across at least one representative traffic cycle, and then decide.

## 18. Common Mistakes and How to Fix Them

| Symptom / Misconception | Actual Cause | Fix |
|---|---|---|
| "receiveTimeout 1s slows every message down by 1s" | Timeout is the maximum wait time when **no message is available**. | Send a message while receive is blocked; measure actual handler latency. |
| "DMLC uses JMS setMessageListener callbacks" | That is `SimpleMessageListenerContainer`'s mechanism. | Look at DMLC's `MessageConsumer.receive` loop. |
| "Empty Queue = broker disconnected" | Empty receive returning null differs from JMS exceptions/recovery. | Monitor failure logs and broker availability separately. |
| "concurrency='4' means exactly 4 consumers" | DMLC treats 4 as the upper bound, with lower bound defaulting to 1. | Use `"4-4"` if you want fixed consumers and have the resources. |
| "maxMessagesPerTask=100 processes exactly 100 messages" | It includes receive attempts returning null. | Check idle/executor settings; do not call it business batch size. |
| "Set receiveTimeout=0 for fastest speed" | 0 waits indefinitely, which can cause shutdown/transaction issues. | Use a finite timeout, typically around 1 second, and tune by measuring. |
| "Using CACHE_NONE is good everywhere" | Can repeatedly create/close Sessions/Consumers, and non-durable Topics risk losing messages. | Choose cache level per transaction strategy and test the provider. |
| "Always set CACHE_CONSUMER even with JTA/XA" | Some app servers only enlist JMS resources freshly acquired within the transaction. | Use `CACHE_AUTO`/default and verify XA. |
| "DMLC needs an extra CachingConnectionFactory to be fast" | Two-tier caching can leave prefetched consumers detached from the container after scale-down. | Prefer internal caching; test carefully if using a wrapper. |
| "Set high concurrency on a Topic to scale" | Non-shared Topics may create duplicate subscriptions/copies. | Choose shared subscriptions if broker/contract supports them. |
| "Exceptions in AUTO_ACK always redeliver" | DMLC may ACK **before** invoking the handler. | Configure `sessionTransacted` and provider retry/DLQ. |
| "5-second recovery guarantees no lost messages" | Recovery only manages reconnects; transaction state, expiry, and provider policies still govern delivery. | Design idempotency/retention/failover and test crashes. |
| "Handler writing DB once means JMS is exactly-once" | Redelivery after DB commit can repeat side effects. | Use event IDs/unique constraints/outbox-inbox. |
| "Increased max consumers but throughput did not increase" | DB/prefetch/selector/handler is the actual bottleneck. | Measure the entire pipeline, not just consumer count. |

## 19. Test Suite for DMLC

1. **Startup:** Container is created properly from the factory, listener id/destination/selector are valid, and broker authentication succeeds.
2. **Idle receive:** Queue stays empty longer than several `receiveTimeout` intervals while the listener remains ready; empty returns are not treated as handler failures.
3. **Wake-up:** Send a message in the middle of a blocking receive; the handler can be invoked sooner than `receiveTimeout`.
4. **Concurrency:** Send multiple independent messages, verify core/max consumer counts and scaling during burst/idle. Compare broker session/consumer counts.
5. **Cache:** Test `CACHE_AUTO`/`CACHE_CONSUMER` as appropriate; with an external TM, verify enlistment before tuning cache.
6. **Transaction:** Throw an exception, test rollback/redelivery; check default ACK mode, DLQ, and max delivery attempts.
7. **Recovery:** Stop the broker, bring it back up, inspect exception/backoff logs, automatic recovery, and duplicate handling.
8. **Shutdown:** Stop the app while a task is receiving and while a handler is processing; verify no message loss from early ACK.
9. **Topic:** If using Topics, test non-durable vs durable/shared, caching, and subscription creation timing.
10. **TaskExecutor:** Configure a custom executor when needed; measure thread pool starvation, `maxMessagesPerTask`, idle counters, and CPU.
11. **Provider-specific:** Benchmark prefetch, queue depth, client buffers, redelivery counts, and selectors so you do not extrapolate from embedded Artemis.
12. **Security:** Verify broker ACLs, TLS/credentials, connection/recovery rotation; never log secrets.

### Deployment Checklist

- [ ] Understood that DMLC polls via `MessageConsumer.receive` rather than `setMessageListener`.
- [ ] `receiveTimeout` is finite and compatible with transaction timeouts/shutdown.
- [ ] `concurrentConsumers`/`maxConcurrentConsumers` are sized based on Queue load and downstream capacity.
- [ ] Did not increase concurrency on a regular Topic without properly designing shared subscriptions.
- [ ] Selected a cache level appropriate for local JMS or external XA/JTA; avoided unnecessary two-tier caching.
- [ ] JMS local transactions or a transaction manager are tested; ACK, rollback, and DLQ are clear.
- [ ] Broker recovery/backoff, liveness/readiness, shutdown, and restart have integration tests.
- [ ] Consumer handler is thread-safe and idempotent; business key ordering is controlled when needed.
- [ ] Observed active/scheduled consumers, Queue depth, oldest message, handler p95, and DB pool.
- [ ] Did not equate receiving a message with a committed business outcome.

## 20. Self-Check Questions

**Question 1.** DMLC is calling `receive(1000)`. A message arrives after 25 ms. Does the listener have to wait the full 1 second before processing?

**Answer:** No. Blocking receive can return as soon as the provider has a message. 1000 ms is the upper wait bound when no message is available.

**Question 2.** What is the core difference between DMLC and `SimpleMessageListenerContainer` regarding how messages are received?

**Answer:** DMLC uses a `MessageConsumer.receive` loop executed by Spring invokers. Simple container registers `MessageConsumer.setMessageListener` for provider callbacks.

**Question 3.** How many maximum consumers does `concurrency="2-5"` across two replicas create for one endpoint?

**Answer:** At most around `2 × 5 = 10` consumers, with a core of around 4. The actual active count depends on load, scheduling, and resources.

**Question 4.** Does `receiveTimeout=0` mean do not wait?

**Answer:** No. It means receive waits indefinitely. A negative value like -1 means a no-wait receive in Spring.

**Question 5.** When adding `JtaTransactionManager`, why might DMLC default to disabling Session/Consumer caching?

**Answer:** With an external transaction manager, DMLC typically uses `CACHE_NONE` to acquire fresh resources within the transaction scope, enabling JMS resources to enlist properly with XA as required by the application server.

**Question 6.** Why does `maxMessagesPerTask=20` not guarantee that exactly 20 business messages are processed?

**Answer:** It counts receive attempts, including calls that return null. It is not a business batch size.

**Question 7.** A Queue consumer stays online but continuously receives null while the broker reports a Queue backlog. What are the possible causes?

**Answer:** Messages do not match the selector, are prefetched to another consumer, are not yet eligible/have delivery delay, or have transaction/routing/ACL issues; inspect raw properties, broker consumer counts, and metrics.

**Question 8.** Does enabling `sessionTransacted(true)` guarantee that each business event updates the DB exactly once?

**Answer:** No. The JMS local transaction and DB transaction are separate; redelivery after DB commit can still repeat side effects. You need an idempotent handler/unique event ID or an appropriate transaction strategy.

**Question 9.** DMLC loses connection to the broker for 20 seconds and then resumes. Can we guarantee zero lost or duplicate messages?

**Answer:** Not from recovery alone. You must check durability, ACK/commit, expiry, redelivery, broker storage, and idempotency; recovery only allows the container to re-establish its ability to receive.

## 21. Official References

- [Spring Framework 6.2 — DefaultMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html).
- [Spring Framework 6.2 — AbstractPollingMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/AbstractPollingMessageListenerContainer.html).
- [Spring Framework 6.2 — DefaultJmsListenerContainerFactory Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html).
- [Spring Framework — Using JMS: Choosing a Listener Container](https://docs.spring.io/spring-framework/reference/integration/jms/using.html).
- [Spring Framework — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html).
- [Spring Framework — Receiving JMS Messages, Transactions, and ACK](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html).
- [Spring Boot — Messaging with JMS / Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html).
- [Jakarta Messaging 3.1 specification — MessageConsumer, receive, transactions, Queue/Topic semantics](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html).
