# Message-driven container and concurrency

## 1. Problem: receiving JMS continuously and processing many messages concurrently

A sales system forwards orders from an ERP into the JMS queue `orders.in`. Normally only a few messages arrive per second, but during peak hours thousands of orders arrive together. If a single consumer processes one message at a time, the queue backs up; if you increase consumer count without control, the database and downstream services overload or events for the same order get processed out of order.

In **Spring Integration**, a **JMS message-driven inbound channel adapter** uses a Spring JMS **message listener container** to receive from the broker and push onto a `MessageChannel`. **Concurrency** is the number of consumers/listeners able to receive and process messages simultaneously. These two concepts govern latency, throughput, thread/connection usage, processing order, and rollback behavior.

The **SPRING_INTEGRATION_ADAPTERS** module focuses on connecting external systems via inbound/outbound adapters, gateways, pollers, and `MessageChannel`s while handling message contracts, errors, and connection lifecycles for JMS alongside technologies such as files, SFTP, HTTP, AMQP, Kafka, and databases. This lesson focuses on **message-driven containers and concurrency in JMS**; the delivery, backpressure, and idempotency principles are also useful when designing other adapters.

Learning objectives:

1. Explain how a listener container receives messages and triggers an integration flow.
2. Distinguish `DefaultMessageListenerContainer`, `SimpleMessageListenerContainer`, and a polling inbound adapter.
3. Configure `concurrentConsumers`, `maxConcurrentConsumers`, task executors, and transactions.
4. Understand the impact of concurrency on queues, topics, ordering, broker prefetch, and downstream systems.
5. Design throughput/backlog measurements, connection recovery, and error handling for production.

## 2. Where does the container sit in a Spring Integration flow?

~~~mermaid
flowchart LR
    P["ERP / Producer"] -->|"JMS TextMessage"| Q[("Broker queue orders.in")]
    subgraph C["Spring JMS Listener Container"]
        C1["Consumer 1"]
        C2["Consumer 2"]
        C3["Consumer N"]
    end
    Q --> C1
    Q --> C2
    Q --> C3
    C1 --> A["JMS message-driven inbound adapter"]
    C2 --> A
    C3 --> A
    A -->|"Spring Message"| M["MessageChannel"]
    M --> H["Validate + import order"]
    H --> DB[("Database")]
~~~

Steps for a JMS request/event:

1. The listener container uses `ConnectionFactory` to open and manage JMS connections/sessions/consumers.
2. The broker delivers a JMS message to a consumer on the queue. `DefaultMessageListenerContainer` (DMLC) runs a JMS receive loop across listener tasks; when a message arrives, it invokes the registered listener.
3. The adapter converts the JMS message into a Spring Message via converter/header mapper, then sends it to the `MessageChannel`.
4. The handler executes business logic. When using a `DirectChannel`, the handler normally runs **on the same thread** as the listener invocation.
5. The listener container acknowledges or commits/rolls back the JMS session as configured, then continues receiving messages.

**"Message-driven" here refers to how the Spring Integration endpoint is triggered:** the listener infrastructure stays ready at all times without needing an integration-flow `PollerMetadata` calling `JmsTemplate.receive()` on a `fixedDelay`. DMLC itself may call JMS `MessageConsumer.receive()` in an internal loop; that **does not turn the endpoint into a Spring Integration polling inbound adapter**.

### Component responsibilities

| Component | Responsibility | What to check |
|---|---|---|
| `ConnectionFactory` | Provides JMS connections/sessions via provider | Broker URL, permissions, caching/pooling, recovery |
| `DefaultMessageListenerContainer` | Receives messages, maintains consumers, scales listener tasks, handles transactions/recovery | Concurrency, `TaskExecutor`, receive timeout, cache level |
| `ChannelPublishingJmsMessageListener` | Converts JMS messages to Spring Messages and sends to channel | Payload converter, header mapper, error handling |
| `JmsMessageDrivenEndpoint` | Binds listener and container into Spring Integration's lifecycle | Start/stop, container shutdown |
| `MessageChannel` | Delivers messages to the integration flow's consumer | Synchronous (`DirectChannel`) vs. asynchronous (`ExecutorChannel`/`QueueChannel`) |
| Handler/service | Executes business logic and reports errors | Timeouts, idempotency, DB transactions |
| Broker | Delivery, redelivery, backlog retention | Queue depth, prefetch, DLQ, TTL, ACLs |

A message-driven inbound **channel adapter** is a **one-way** entry point; it sends no reply back to the producer. When a JMS client expects request-reply, use a **JMS inbound gateway**. Both can use a listener container, but their response contracts differ.

## 3. Choosing the listener container type

Spring JMS offers two common choices:

| Criterion | `SimpleMessageListenerContainer` | `DefaultMessageListenerContainer` |
|---|---|---|
| Mechanism | Registers a callback with the JMS provider via `MessageConsumer.setMessageListener()` | Listener tasks receive in a `receive()` loop and invoke the listener |
| Consumer count | Typically fixed as configured at startup | Has baseline `concurrentConsumers` and `maxConcurrentConsumers` for dynamic scaling |
| Recovery, stop/start | Simpler, depends on provider and container features | More flexible for recovery and lifecycle management |
| Local JMS transactions | Can use `sessionTransacted` | Can use `sessionTransacted` |
| External transaction manager coordination | Lacks DMLC's dynamic/external transaction support | Can integrate with `PlatformTransactionManager`, including JTA when eligible |
| Typical use case | Fixed, simple requirements | Most Spring JMS apps needing explicit concurrency/recovery/transactions |

Spring Integration can create a `DefaultMessageListenerContainer` from `ConnectionFactory`, destination, and config properties. If a custom container is needed, you can pass a pre-configured `AbstractMessageListenerContainer` instance. **Properties meant for an internally created container may no longer take effect when you supply an external container**; configure those directly on the supplied container instead.

Do not pick `SimpleMessageListenerContainer` merely because of its "simple" name if the system sees varying load, needs dynamic concurrency, or participates in externally coordinated transactions.

## 4. Concurrency: minimum, maximum, and dynamic scaling

With DMLC:

- `concurrentConsumers` is the **baseline consumer count** maintained by the container. Common default is **1**.
- `maxConcurrentConsumers` is the **upper bound** on active consumers. Default is **1**; when higher than `concurrentConsumers`, DMLC can spin up additional consumers while messages keep arriving.
- `setConcurrency("2-6")` is a shorthand setting: minimum 2, maximum 6. `setConcurrency("3")` corresponds to a fixed count of 3 in typical usage.

Scaling from 2 to 6 **does not instantly create 6 consumers**: it depends on live load, task state, idle thresholds, the JMS provider, and executor resources. Once the queue drains, DMLC can dynamically scale active consumers back down to the baseline.

~~~mermaid
flowchart TD
    A["Queue has low traffic"] --> B["Maintain 2 baseline consumers"]
    B --> C{"Backlog and non-empty receives increasing?"}
    C -->|"Yes"| D["Spawn more listener tasks / consumers"]
    D --> E["Up to 6 consumers max"]
    E --> F{"Load drops and tasks exceed idle threshold?"}
    F -->|"Yes"| G["Scale back down to 2 consumers"]
    F -->|"No"| E
    C -->|"No"| B
~~~

### Estimating throughput to pick a starting point

If the **average synchronous processing time per message** is 200 ms with no network/DB contention, one consumer has an ideal capacity of around 5 messages/second.

| Active consumers | Ideal capacity at 200 ms/message | Real-world constraints |
|---:|---:|---|
| 1 | ~5 msg/s | One slow message blocks those behind it |
| 2 | ~10 msg/s | More connections/sessions, database contention |
| 4 | ~20 msg/s | Completion order can diverge from send order |
| 6 | ~30 msg/s | DB pool, broker, CPU, or downstream APIs may saturate |

These numbers are only an **idealized model** `throughput ≈ consumerCount / secondsPerMessage`, not an SLA. If each handler takes 500 ms due to a slow DB, 6 consumers yield an ideal capacity of only 12 msg/s. If all consumers contend on a single lock, adding consumers may not improve throughput at all.

Therefore, scale concurrency based on real measurements: ingress rate, queue backlog, p95 processing latency, DB pool size, and broker connection/session counts. Never raise concurrency unboundedly just because a queue is deep.

### Concurrency is not the same as instance count or downstream threads

Suppose you deploy **3 instances**, each with `concurrency="2-6"`. Total consumers on the **same queue** can range from 6 to 18, excluding consumers from other services. Always calculate **the sum across replicas** to avoid sizing per pod and exhausting connections or DB pools cluster-wide.

If downstream uses an `ExecutorChannel` with a 20-thread pool, those 20 threads are **not** 20 JMS consumers. JMS consumer count remains governed by the listener container; once decoupled asynchronously, the JMS transaction may finish before work in the executor completes.

## 5. Java DSL configuration: message-driven with concurrency 2–6

The example uses **Spring Integration 6+ / Spring Framework 6+**, Jakarta JMS (`jakarta.jms`), and Java 17+. The project needs `spring-integration-jms`, a JMS provider, and a `ConnectionFactory` bean connected to the broker.

Illustrative dependencies with the Spring Boot BOM:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-jms</artifactId>
</dependency>
<!-- Add the JMS client/starter matching the broker in use. -->
~~~

The app has queue `orders.in`; its consumer reads `TextMessage` payloads containing order JSON. Flow:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;

@Configuration
@EnableIntegration
public class OrdersJmsMessageDrivenConfig {

    @Bean
    public IntegrationFlow ordersInboundFlow(
            ConnectionFactory connectionFactory,
            OrderImportService orderImportService) {

        return IntegrationFlow
                .from(Jms.messageDrivenChannelAdapter(connectionFactory)
                        .destination("orders.in")
                        .configureListenerContainer(container ->
                                container.concurrentConsumers(2)
                                        .maxConcurrentConsumers(6)
                                        .sessionTransacted(true)
                                        .recoveryInterval(5000)))
                .handle(String.class, (json, headers) -> {
                    orderImportService.importOrder(json);
                    return null; // One-way handler.
                })
                .get();
    }
}
~~~

Business service for the learner to implement:

~~~java
public interface OrderImportService {
    void importOrder(String orderJson);
}
~~~

**Configuration breakdown:**

- `.destination("orders.in")` selects the JMS queue. The queue must exist or be auto-creatable per broker policy; name and ACLs must be valid.
- `.configureListenerContainer(...)` configures the `DefaultMessageListenerContainer` created by Java DSL from `ConnectionFactory`.
- `.concurrentConsumers(2)` maintains two baseline consumers; `.maxConcurrentConsumers(6)` permits scaling up to six under load.
- `.sessionTransacted(true)` requests local JMS transactions: when the listener succeeds, the transaction commits; when an appropriate error escapes, it can roll back.
- `.recoveryInterval(5000)` configures the wait interval in milliseconds before attempting connection recovery on container errors.
- `.handle(String.class, ...)` expects the converter to turn JMS `TextMessage` into a `String` payload; the real service must parse/validate JSON and handle idempotency.

This example **does not need a poller**. For a test producer demo, a JMS producer can call:

~~~java
// jmsTemplate is a test-application bean using a compatible JMS provider.
jmsTemplate.convertAndSend(
        "orders.in",
        "{\"eventId\":\"evt-801\",\"orderId\":\"ORD-801\",\"version\":1}");
~~~

While the broker and flow are running, the listener picks up the message via one of the active consumers. Concurrency determines how many **distinct** messages on the queue can be processed simultaneously; it does not multiply a single message into six copies.

### Equivalent XML configuration

~~~xml
<int:channel id="ordersInput"/>

<int-jms:message-driven-channel-adapter
        id="ordersMessageDriven"
        connection-factory="jmsConnectionFactory"
        destination-name="orders.in"
        channel="ordersInput"
        concurrent-consumers="2"
        max-concurrent-consumers="6"
        acknowledge="transacted"/>

<int:service-activator
        input-channel="ordersInput"
        ref="orderImportHandler"
        method="handle"/>
~~~

The XML above is a **fragment**: the app needs `int`/`int-jms` namespaces, the `jmsConnectionFactory` bean, and the `orderImportHandler` bean. When Spring Integration creates the container internally, concurrency/acknowledge attributes on the adapter are applied to that container. If configuring via `container="beanId"`, set these same properties directly **on the external container bean**.

## 6. When you need to manage DefaultMessageListenerContainer yourself

If you need fine-grained control over cache levels, executors, subscriptions, or recovery settings, the app can create its own container bean and pass it to the adapter.

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;
import org.springframework.jms.listener.DefaultMessageListenerContainer;

@Bean
public DefaultMessageListenerContainer ordersListenerContainer(
        ConnectionFactory connectionFactory) {
    DefaultMessageListenerContainer container =
            new DefaultMessageListenerContainer();
    container.setConnectionFactory(connectionFactory);
    container.setDestinationName("orders.in");
    container.setConcurrentConsumers(2);
    container.setMaxConcurrentConsumers(6);
    container.setSessionTransacted(true);
    container.setRecoveryInterval(5000L);
    return container;
}

@Bean
public IntegrationFlow ordersFlowWithExternalContainer(
        DefaultMessageListenerContainer ordersListenerContainer,
        OrderImportService orderImportService) {

    return IntegrationFlow
            .from(Jms.messageDrivenChannelAdapter(ordersListenerContainer))
            .handle(String.class, (json, headers) -> {
                orderImportService.importOrder(json);
                return null;
            })
            .get();
}
~~~

**Note:** this **replaces the entire flow from section 5**; do not register both flows on the same queue at once if only one endpoint is intended. When the container is app-created, coordinate bean and endpoint lifecycles so the listener is attached before startup; verify this in integration tests. `DefaultMessageListenerContainer` participates in Spring lifecycle management, and `JmsMessageDrivenEndpoint` governs container shutdown on stop.

For systems needing an external manager (such as `JtaTransactionManager`), DMLC supports `setTransactionManager(...)`, though simply setting `setSessionTransacted(true)` **does not imply** XA transactions.

## 7. Deeper settings: executor, receive timeout, and scaling

### 7.1. DMLC's TaskExecutor

DMLC uses a `TaskExecutor` to run listener invoker tasks. A single task can hold a session/consumer and loop receiving messages; do not think a new thread is spawned **per message**. By default, the initial number of invokers equals `concurrentConsumers`.

If supplying a custom executor, ensure it has enough capacity for the **expected listener task count** up to `maxConcurrentConsumers`, and understand how DMLC manages long-lived tasks. An undersized executor pool can prevent real concurrency from reaching configured levels. A huge executor does not give downstream more DB connections.

Example for a queue environment needing dedicated threads:

~~~java
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.context.annotation.Bean;

@Bean("jmsListenerExecutor")
public ThreadPoolTaskExecutor jmsListenerExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(6);
    executor.setQueueCapacity(0);
    executor.setThreadNamePrefix("jms-orders-");
    return executor;
}
~~~

This only shows creating the executor; Spring invokes the bean's lifecycle initialization automatically. To use it, inject the bean into the container via `setTaskExecutor(executor)` or DSL `taskExecutor(...)` and measure actual behavior. Setting `queueCapacity(0)` avoids queuing unstarted listener tasks in the executor, though you should verify task-rejection handling and scaling behavior before production use. **Never arbitrarily share an executor saturated by HTTP/DB tasks** with JMS listeners.

### 7.2. DMLC receive timeout vs. poller

`DefaultMessageListenerContainer` has a `receiveTimeout` property controlling how long **a single JMS receive waits inside a listener task**. It affects stop/reconfigure/scaling responsiveness and how tasks detect idleness, rather than creating a Spring Integration `fixedDelay` schedule.

| Setting | Meaning | Effects to observe |
|---|---|---|
| `concurrentConsumers` | Baseline consumers | Baseline load on broker/session pool |
| `maxConcurrentConsumers` | Dynamic consumer ceiling | Potential throughput and risk of downstream overload |
| `receiveTimeout` | Wait time for one JMS receive in DMLC | Stop responsiveness and idle detection |
| `maxMessagesPerTask` | Maximum receive attempts per invoker task, including empty receives | Task lifecycle and executor behavior; not Spring Integration's poll batch limit |
| `idleTaskExecutionLimit` | Idle executions before terminating a dynamic invoker | Prevents overly frequent scale-up/scale-down thrashing |
| `idleConsumerLimit` | Limit on extra consumers kept idle | Balances scaling readiness and resource cost |
| `recoveryInterval` / `BackOff` | Retry cadence for recovery on JMS failures | Recovery time and reconnect load on broker |
| `cacheLevel` | DMLC connection/session/consumer caching level | Performance, transaction semantics, resource lifecycle |

**Do not confuse `maxMessagesPerTask` with `maxMessagesPerPoll`.** `maxMessagesPerPoll` belongs to Spring Integration's polling consumer and caps source polls per poll cycle. `maxMessagesPerTask` belongs to DMLC infrastructure and caps receive attempts an invoker task executes before yielding/rescheduling per config.

### 7.3. Caching and ConnectionFactory

DMLC maintains its own caching for JMS connections/sessions/consumers according to `cacheLevel`. With native JMS, the container usually reuses sessions/consumers to cut overhead. With an external transaction manager, caching behavior may differ to remain compatible with managed transactions.

Do not blindly **wrap a `DefaultMessageListenerContainer` with `CachingConnectionFactory`** the way you might optimize `JmsTemplate` sends; stacking multiple caching/pooling layers can cause unpredictable behavior on stop/restart or scaling. If the JMS provider already pools connections/sessions, clarify exactly which layer owns caching before tuning.

## 8. Queue concurrency, ordering, and prefetch

### 8.1. On queues, concurrency splits work

If queue `orders.in` has 100 messages and 4 active consumers, the broker can hand different messages to those 4 consumers. However, **completion** order depends on processing duration. For example:

~~~text
Receive time:
  Worker 1: ORD-1 (handler takes 900 ms)
  Worker 2: ORD-2 (handler takes 100 ms)

Commit time:
  ORD-2 finishes before ORD-1.
~~~

Even if the queue initially received `ORD-1` then `ORD-2`, the app cannot rely on commit order with multiple consumers. If two events for the **same order** must be processed sequentially, use a single consumer for that scope, partition by `orderId`, use broker-supported message groups, or enforce optimistic concurrency via `aggregateVersion` in the database.

### 8.2. Prefetch affects distribution, not handler count

Many JMS brokers use a **prefetch/consumer window** mechanism: the broker may pre-deliver a batch of messages to each consumer. When one consumer processes slowly, messages buffered for that consumer may sit waiting in the provider's client buffer while another consumer sits idle.

Consequently:

- Low queue depth **does not necessarily** mean every message has finished handler processing.
- Distribution across consumers may be uneven if prefetch/window sizes differ.
- Concurrency and prefetch should be tested against a real broker, especially when message processing times vary widely.

Property names and prefetch mechanics **differ across JMS providers**. Never copy ActiveMQ Artemis configuration to another JMS provider and assume equivalent semantics.

### 8.3. When to scale horizontally by instances?

Raising `maxConcurrentConsumers` on one instance and adding more instances both increase queue consumers. Adding instances also spreads CPU and failure domains, though total connections and DB pressure also climb. If a queue requires strict ordering per aggregate, both scaling approaches must preserve the same ordering and idempotency strategy.

## 9. Be careful with topics and subscription concurrency

Queues and topics do not share the same multi-consumer semantics. On a **regular topic**, each consumer creates an independent subscription that can receive a copy of the same event; raising `concurrentConsumers` from 1 to 4 risks making one app process **four copies of the same event** rather than splitting work four ways.

With an **unshared durable subscription**, JMS/brokers typically restrict concurrent active consumers on the same subscription identity. To split work within **one subscription**, use a **shared subscription** or **shared durable subscription** supported by the JMS provider and container, and configure `clientId`/`subscriptionName` accurately.

| Need | Right direction | What not to do |
|---|---|---|
| Worker pool processing commands | Queue + multiple consumers | Use a topic with multiple subscriptions so every worker runs the same command |
| Three services all receive `OrderPaid` | Topic + three independent subscriptions | Let all three services compete on the same queue |
| One topic service wants to scale processing | Provider-supported shared subscription, or dispatch into an internal queue | Raise concurrency on a plain topic without checking duplicates |
| Receive events while subscriber is offline | Durable subscription with appropriate TTL/retention | Enable concurrency while ignoring durable identity |

For example, `order-paid` sent to topic `orders.events` must be handled by both accounting and warehouse. Accounting and warehouse need **two distinct subscriptions**. If accounting runs three replicas and wants each event processed by only one replica, they must share **one shared subscription** if supported by the provider or route into a dedicated downstream work queue.

## 10. Transactions and acknowledgement with multiple consumers

Spring Integration creates JMS message-driven adapters with **transacted** acknowledgement by default since version 4.2, **unless you supply an external container**, in which case the container's transaction/acknowledgement settings are up to your app. A standalone DMLC does not share the same default transaction setting as an internally created Spring Integration adapter. That is why our Java DSL example explicitly sets `sessionTransacted(true)`.

### 10.1. Synchronous processing path

~~~mermaid
flowchart LR
    A["JMS Session receives message"] --> B["Adapter builds Spring Message"]
    B --> C["DirectChannel"]
    C --> D["Validate + write DB"]
    D --> E{"Handler throws exception?"}
    E -->|"No"| F["JMS commit"]
    E -->|"Yes, not swallowed"| G["JMS rollback"]
    G --> H["Broker redelivery / DLQ per policy"]
~~~

With `DirectChannel` and the handler running on the listener thread, synchronous errors can propagate out to the JMS container's transaction boundary. If the handler throws an exception, the listener container can roll back the JMS session and the broker can redeliver the message. If the handler catches the error and only logs it, the transaction may commit despite the business failure.

**Do not assume the DB transaction rolled back alongside the JMS transaction.** `sessionTransacted=true` manages only the local JMS session. If the DB commits successfully and then the JMS transaction rolls back, the same message may arrive again. Use `eventId`/`commandId` as an idempotency key alongside a unique constraint or DB inbox table.

### 10.2. Asynchronous boundary

When switching from `DirectChannel` to `ExecutorChannel` or `QueueChannel`:

~~~text
JMS listener -> Spring Message -> ExecutorChannel -> Handler on another thread
                |                 |
                |                 +-- error may happen after JMS already committed
                +-- listener callback may already have returned
~~~

The listener may acknowledge/commit the message as soon as it is placed on the channel, before the asynchronous handler completes. If the handler fails, downstream errors **do not automatically** roll back the original JMS message. To preserve reliability, add a durable handoff, async-layer retry/error flows, or avoid switching threads inside a section needing transactional coverage.

### 10.3. Error channel and exception propagation

The Spring Integration JMS inbound adapter supports `errorChannel`. When a conversion or dispatch error is routed as an `ErrorMessage`, the author of the error flow must decide whether to **rethrow the exception**. If the error flow absorbs the error and returns normally, the listener may treat the receive as successful and commit the JMS transaction.

Do not treat `errorChannel` as a retry queue or DLQ. Redelivery and DLQ behavior are governed by broker/provider policies together with transactions/acknowledgement; application retries must have bounded attempts/backoff and avoid poison-message loops.

### 10.4. AUTO_ACKNOWLEDGE and differences between containers

With `DefaultMessageListenerContainer`, `AUTO_ACKNOWLEDGE` can acknowledge before the listener runs, so an exception in the handler **does not guarantee redelivery**. Therefore, for queues carrying critical business work, transacted sessions are generally safer. `SimpleMessageListenerContainer` invokes listeners differently and still requires checking acknowledgement/provider behavior; do not conflate both container types into a single guarantee.

## 11. Recovery, stop/start, and lifecycle

At runtime, the message-driven container must keep connections/sessions/consumers healthy. During broker outages, DMLC runs recovery logic. Per Spring Framework, the default base recovery interval is typically 5 seconds; set `recoveryInterval` or a `BackOff` when a different backoff curve is needed.

Key lifecycle behaviors:

1. **Startup:** the container creates listener tasks/consumers up to `concurrentConsumers`. If destination or ACLs are wrong, the container may retry repeatedly while the queue keeps growing.
2. **Scale up:** when messages are sustained, DMLC can add consumers up to `maxConcurrentConsumers`. Broker/session pools and task executors must have sufficient headroom.
3. **Scale down:** after extended idleness, dynamic invokers may shut down; baseline consumers stay alive.
4. **Stop endpoint:** since Spring Integration 5.1, `JmsMessageDrivenEndpoint` shuts down the container by default when the endpoint stops, releasing connections/consumers. `shutdownContainerOnStop(false)` alters this behavior and should be used intentionally.
5. **Broker reconnect:** an app still running does not prove consumers recovered cleanly. Monitor listener health, active consumer counts, and queue age.
6. **Restart/crash:** uncommitted messages may be redelivered by the broker; if the DB already committed before a crash, idempotency prevents duplicate processing.

Do not configure aggressive recovery that causes many replicas to hammer a struggling broker with simultaneous reconnects. Use proper backoff and alert when messages stop arriving within SLA thresholds.

### DefaultMessageListenerContainer metrics

DMLC exposes methods such as `getActiveConsumerCount()` and `getScheduledConsumerCount()`:

- **Scheduled consumer count:** number of scheduled listener invokers, which can differ from how many are actively processing right now.
- **Active consumer count:** number of currently active consumers according to container state; **not equivalent** to successful business messages processed per second.

These metrics help verify scaling, though they must be combined with broker metrics, DB data, and handler timings. For a listener container defined inside Java DSL, accessing the instance directly for monitoring/tuning usually requires managing the bean/endpoint or exporting metrics via appropriate instrumentation.

## 12. Capacity design and backpressure

A common incident is a queue backing up to 50,000 messages. Raising `maxConcurrentConsumers` from 4 to 40 may temporarily pull the backlog down, yet if the DB pool has only 12 connections, many threads will block waiting; p99 latency climbs and broker sessions/heap take extra pressure.

Process for choosing concurrency:

1. **Measure ingress rate:** average messages/sec, peak bursts, payload size.
2. **Measure processing time:** p50, p95, p99 for handlers, DB transactions, and downstream HTTP calls.
3. **Estimate baseline capacity:** `ideal throughput = activeConsumers / avgProcessingSeconds`; load-test to measure real capacity.
4. **Identify bottlenecks:** DB pool, broker connections, threads, CPU, network, API rate limits, per-aggregate locks.
5. **Pick baseline and ceiling:** start small, observe backlog and latency; scale up until gains plateau or downstream degrades.
6. **Configure retry/backoff and DLQ:** poison messages and transient faults must not occupy all consumers indefinitely.
7. **Track totals across all replicas:** avoid multiplying `maxConcurrentConsumers` by instance count beyond total system capacity.

The Spring JMS listener container adjusts consumer counts at a basic level; it is **not an end-to-end backpressure control system**. If downstream is slower than upstream, messages still accumulate in the broker or trigger retries, requiring queue-depth/oldest-age alerts plus source throttling or infrastructure scaling.

### Operations checklist

| Metric/event | Why monitor | How to respond |
|---|---|---|
| `queue depth` | Unprocessed backlog | Compare ingress/egress rates, inspect consumers |
| Oldest message age | Processing SLA degradation | Prioritize investigation when rising steadily |
| `activeConsumerCount` | Whether listeners scale and run | Check connection errors and executor limits |
| `scheduledConsumerCount` | Listener task scheduling health | Inspect invoker count and scaling settings |
| Handler latency p95/p99 | Slow DB/API drag | Optimize handlers, tune timeouts/pools |
| JMS redelivery count | Repeated failures or rollbacks | Classify errors, tune retry/backoff, idempotency |
| DLQ/poison messages | Data errors requiring intervention | Quarantine, fix payload/schema |
| Broker connection/session count | Infrastructure overload | Sum across all replicas/containers |
| Reconnect/recovery errors | Broker/ACL/network issues | Alert, verify recovery policy |

## 13. Hands-on lab: scaling load on an order queue

**Context:** deploy a test broker, queue `orders.in`, an order-import service simulating 200 ms processing time, and a `processed_event(event_id)` table with a unique constraint. Use a producer sending `eventId`/`orderId` JSON; test on a real broker or provider-compatible container. Exercises involving redelivery, transactions, and prefetch cannot be fully verified with mocks alone.

### Lab A — Baseline concurrency measurement

1. Set `concurrentConsumers=1`, `maxConcurrentConsumers=1`, and send 100 messages.
2. Record start/end times per handler and actual throughput. Compare against the ideal 5 msg/s figure for a 200 ms handler.
3. Switch to `concurrentConsumers=2`, `maxConcurrentConsumers=6`, and send 100 new messages.
4. Observe active/scheduled consumers, total processing time, queue depth, and CPU/DB pool usage.
5. Raise `maxConcurrentConsumers` to 10 **in the test environment only** and find where downstream begins to saturate.

### Lab B — Ordering and idempotency

1. Send `OrderCreated(v1)` and `OrderPaid(v2)` for the same `orderId` with multiple consumers running.
2. Have the v1 handler sleep longer than v2; record how completion order can invert.
3. Add an `aggregateVersion` check or sequential per-order-key processing.
4. Make the handler throw an exception after writing to DB, then observe broker redelivery.
5. Use the unique constraint on `eventId` to ensure no duplicate business side effects occur.

### Lab C — Errors and transaction boundaries

1. With `sessionTransacted(true)`, have the synchronous handler throw an exception; observe rollback/redelivery per broker policy.
2. Configure an `errorChannel` that absorbs the exception and observe the difference in commit behavior.
3. Update the error flow to rethrow when rollback is desired, bound retries, and configure an appropriate DLQ.
4. Replace `DirectChannel` with `ExecutorChannel`, fail the async handler, and explain why the original JMS transaction may already have committed.
5. Verify idempotency when retrying after a crash between DB commit and JMS commit.

### Lab D — Broker offline and recovery

1. Stop the broker while messages sit in the queue; watch error logs and active consumer counts.
2. Bring the broker back up; measure how long DMLC takes to reconnect and resume receiving.
3. Compare `recoveryInterval=5000` with a longer backoff across multiple instances; observe reconnect load.
4. Stop/start the endpoint; verify connections and consumers are released and recreated.

### Lab E — Queue vs. topic

1. Use a queue with 3 consumers; verify a normal command is processed by only one consumer unless redelivered.
2. Publish 10 messages to a topic with multiple unshared subscriptions; verify multiple subscribers can receive the same event.
3. Try raising concurrency on a plain topic and explain the duplicate-processing risk.
4. If the broker supports it, use a shared durable subscription to split load **within one subscription**; verify subscription identity and offline behavior.

### Self-check questions

1. Does DMLC use `MessageConsumer.receive()` internally? Why is the Spring Integration endpoint still called message-driven?
2. What is the difference between `concurrentConsumers=2` and `maxConcurrentConsumers=6`?
3. Why can configuring 6 consumers per pod result in more than 6 consumers cluster-wide?
4. When a queue holds 100 messages, does setting 6 consumers guarantee all complete in send order?
5. Why should you generally not raise concurrent consumers on a topic without configuring a shared subscription?
6. How does `maxMessagesPerTask` differ from `maxMessagesPerPoll`?
7. When switching from `DirectChannel` to `ExecutorChannel`, which part does the JMS transaction protect?
8. Why does `sessionTransacted=true` not guarantee an atomic commit with PostgreSQL?
9. How do `getActiveConsumerCount()` and `getScheduledConsumerCount()` differ from actual throughput?
10. When the DB pool is the bottleneck, does multiplying concurrency by ten always shrink the backlog?

## 14. References

- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): message-driven channel adapters, internal/external containers, `concurrent-consumers`, acknowledgement, error channels, and lifecycle.
- [Spring Integration API — JmsMessageDrivenChannelAdapterSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jms/dsl/JmsMessageDrivenChannelAdapterSpec.html): Java DSL endpoint and listener container configuration.
- [Spring Integration API — JmsDefaultListenerContainerSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jms/dsl/JmsDefaultListenerContainerSpec.html): `concurrentConsumers`, `maxConcurrentConsumers`, `receiveTimeout`, `recoveryInterval`, and `taskExecutor`.
- [Spring Framework Reference — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html): message listener containers and JMS transactions.
- [Spring Framework API — DefaultMessageListenerContainer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html): dynamic scaling, idle tasks, caching, concurrency, and recovery.

**Remember:** the message-driven container is the infrastructure that continuously pulls JMS messages and passes them into Spring Integration without needing a flow poller. Concurrency boosts receive capacity **on queues**, but you must account for instance counts, downstream limits, ordering, and prefetch; on **topics**, scale only via shared subscriptions when supported by provider and contract. Transactions, error propagation, idempotency, and backlog monitoring are prerequisites for scaling speed without sacrificing correctness.
