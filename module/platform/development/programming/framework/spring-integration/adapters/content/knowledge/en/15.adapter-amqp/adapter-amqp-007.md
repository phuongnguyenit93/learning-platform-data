# Message-Driven Container and Prefetch

## Learning Objectives

After this lesson, you will be able to:

- Explain why an **AMQP inbound channel adapter** typically uses a **message-driven listener container** instead of a Spring Integration poller.
- Distinguish the responsibilities of the RabbitMQ broker, **Spring AMQP listener container**, AMQP inbound adapter, MessageChannel, and service activator.
- Compare **SimpleMessageListenerContainer (SMLC)** and **DirectMessageListenerContainer (DMLC)**, especially regarding thread models and concurrency settings.
- Understand **prefetch (basic.qos)**, unacked delivery counts, and their relationships with throughput, memory, fairness, and processing latency.
- Configure a **Spring Integration Java DSL** flow with SMLC, prefetch, concurrent consumers, automatic ACK, and a dead-letter queue.
- Analyze premature ACKs, repeated requeues, redelivery, idempotency, connection failures, and graceful shutdown.
- Establish a methodology for measuring **ready/unacked backlog**, publish/ack rates, latency, and load tests to tune prefetch with evidence.

## 1. Problem: Messages Arrive Faster Than Processing Capacity

A RabbitMQ queue **orders.created.q** receives order events. The publisher emits several hundred events per second, while the receiving application must validate schemas, call a database, and write inventory state. If a consumer processes messages sequentially one by one, backlog can grow. If too many consumers are opened or prefetch is raised too high, many deliveries get held on the application side, increasing memory usage, causing unfairness, or triggering ACK timeouts.

Spring Integration solves the integration boundary using an **AMQP inbound channel adapter**: the adapter receives data from a Spring AMQP listener and sends it to a MessageChannel. However, reception speed and message redelivery behavior depend heavily on the **listener container** and RabbitMQ's **prefetch** mechanism.

~~~mermaid
flowchart LR
    P["Producer"] --> X["RabbitMQ exchange"]
    X --> Q["Queue<br/>orders.created.q"]
    Q --> LC["Spring AMQP<br/>listener container"]
    LC --> IA["AMQP inbound<br/>channel adapter"]
    IA --> CH["Spring Integration<br/>MessageChannel"]
    CH --> H["Service activator<br/>OrderService"]
    H --> DB[("Database")]
    LC -. "ACK / NACK" .-> Q
~~~

**Two questions must be kept separate:**

1. **How many unacked messages can be delivered ahead?** Governed by prefetch/broker QoS.
2. **How many consumers or concurrent processing tasks run?** Governed by listener concurrency, thread model, and downstream capacity.

Prefetch **does not create extra processing workers**. Increasing concurrency **does not guarantee** that the database or downstream APIs will process faster.

## 2. From Queue to MessageChannel: Layers of Responsibility

| Component | Function | Do Not Confuse With |
| --- | --- | --- |
| **RabbitMQ queue** | Holds ready messages or messages currently delivered to consumers | Spring MessageChannel |
| **ConnectionFactory** | Supplies AMQP connections/channels | Queue or message store |
| **Message listener container** | Manages consumers, receives deliveries, concurrency, prefetch, ACK/NACK, shutdown | Business handler |
| **AMQP inbound channel adapter** | Converts deliveries into Spring Messages and sends to output channel | Request–reply AMQP inbound gateway |
| **MessageConverter** | Converts AMQP body into an appropriate payload type | Domain-standardizing transformer |
| **MessageChannel** | Transfers internal messages to filters, transformers, service activators | Durable RabbitMQ queue |
| **Service activator** | Validates and executes business logic | Listener managing acknowledgment |

A single delivery can follow this path:

~~~mermaid
sequenceDiagram
    participant B as RabbitMQ queue
    participant L as Listener container
    participant A as AMQP inbound adapter
    participant C as DirectChannel
    participant H as OrderService
    B-->>L: Deliver message (within prefetch)
    L->>A: Invoke listener
    A->>C: send(Spring Message)
    C->>H: Synchronous processing
    H-->>C: Complete / throw exception
    C-->>A: Synchronous processing outcome
    A-->>L: Listener callback completes
    L-->>B: ACK / NACK per policy
~~~

This diagram assumes a **DirectChannel and synchronous handler**. If the MessageChannel is changed to an **ExecutorChannel**, the listener may return after handing off the task to the executor without **knowing** whether business logic on another thread succeeded. That is a major change to the ACK boundary, not a harmless performance tweak.

## 3. How Does Message-Driven Differ from Polling?

File, SFTP, and JDBC adapters typically use **MessageSource + Spring Integration poller** to actively scan sources on a schedule. With AMQP inbound, RabbitMQ already has consumer/delivery push mechanics, so the common approach is a **message-driven listener container**.

| Characteristic | Polling File/SFTP/JDBC | AMQP Message-Driven |
| --- | --- | --- |
| Trigger source | Scheduler calls MessageSource.receive() | RabbitMQ/client pushes deliveries to listener |
| Cadence settings | fixedDelay/fixedRate, maxMessagesPerPoll | consumer concurrency, prefetch, listener container |
| Source progress | File filter, watermark, metadata store | Consumer ACK/NACK, ready/unacked, redelivery |
| When no data exists | Poller keeps running and gets null | Consumer waits for deliveries via client mechanism |
| Load control | Poll frequency/batch size, capacity | QoS/prefetch, consumer count, processing time |
| Start/stop | Enable/disable scheduled endpoint | Start/stop listener container/consumers |

**The RabbitMQ client handles internal reception**, which does not mean every AMQP inbound adapter needs a **Spring Integration Poller**. Conversely, when using RabbitTemplate.receive(...) to pull messages actively, the application is choosing a different model and must design cadence, errors, ACK, and lifecycle itself.

### 3.1. Is a Message-Driven Container a Request–Reply Gateway?

No. An **AMQP inbound channel adapter** receives deliveries one-way and does not return a business response. An **AMQP inbound gateway** receives requests and sends AMQP replies following a reply-to/correlation contract. Both can use a listener container, yet they are different endpoint types with different caller expectations.

Broker **consumer ACK** only confirms delivery at the protocol level; it does not turn a one-way inbound adapter into a two-way gateway.

## 4. Two Common Listener Container Types

Spring AMQP provides multiple listener container implementations. The two common ones for RabbitMQ integration are:

- **SimpleMessageListenerContainer (SMLC)**.
- **DirectMessageListenerContainer (DMLC)**.

| Criterion | SimpleMessageListenerContainer | DirectMessageListenerContainer |
| --- | --- | --- |
| Thread model | Deliveries pass through the container's internal mechanism and invoke the listener on container-managed consumer threads | Listener is invoked directly on RabbitMQ Java client thread mechanics, coordinated differently from SMLC |
| Concurrency settings | **concurrentConsumers**, **maxConcurrentConsumers**; can scale within a range when configured | **consumersPerQueue** and related settings; does not use SMLC's autoscaling algorithm |
| Prefetch | Configure **prefetchCount** on the container | Configure **prefetchCount** on the container |
| Queue management | Suits many traditional listener models; has dynamic worker scaling | Has its own per-queue consumer management and direct thread model |
| ACK/requeue | Based on acknowledge mode, transactions, error handlers/advice | Also based on ACK mode and container policy, implemented differently |
| When to choose | Easy starting point, especially when range-based consumer scaling is useful | Consider when direct dispatch, per-queue consumer management, and its thread model fit better |

Never claim DMLC is **always faster** than SMLC or SMLC is **always safer**. Benchmark based on payload, handler latency, queue count, connections, concurrency, and library version.

### 4.1. SMLC: concurrentConsumers and maxConcurrentConsumers

With SMLC:

- **concurrentConsumers** is the initial/minimum number of consumers.
- **maxConcurrentConsumers** is the upper bound when dynamic autoscaling applies.
- Active/idle trigger thresholds and adjustment intervals govern how quickly consumers scale up or down.
- Scaling up consumers requires downstream capacity; it cannot fix schema errors or lost broker connectivity.

For example, **concurrentConsumers = 2**, **maxConcurrentConsumers = 4** lets SMLC adjust consumer count within that range per its algorithm, rather than always running 4 workers.

### 4.2. DMLC: consumersPerQueue

With DMLC, **consumersPerQueue** specifies the number of consumers for **each queue** managed by the container. If a DMLC listens to two queues with consumersPerQueue = 3, the setup runs three consumers per queue, totaling roughly six consumers during normal operation.

Do not copy SMLC parameters like maxConcurrentConsumers mechanically to DMLC. Check the API, thread pools, connection setup, and consumer scaling behavior for your Spring AMQP version.

### 4.3. Do You Need to Create a Container Manually?

Spring Boot can configure a listener container factory, while a Spring Integration endpoint can use a **manually constructed container** or configure one via the DSL/factory. The crucial rule: know **which exact container** owns your inbound adapter, instead of tweaking an unused listener factory bean and thinking prefetch changed.

## 5. What Is Prefetch?

**Prefetch** limits how many **unacknowledged deliveries** the broker may push ahead under the active QoS settings. In RabbitMQ, this is typically configured via **basic.qos(prefetchCount)** through Spring AMQP.

~~~mermaid
flowchart LR
    Q["RabbitMQ queue<br/>ready"] -->|"Push up to QoS window"| C["Consumer"]
    C --> D["Unacked deliveries"]
    D --> H["Handler"]
    H -->|"ACK"| ACK["Free quota<br/>receive next delivery"]
    H -. "NACK / reject" .-> R["Requeue / dead-letter<br/>per policy"]
~~~

For example, **prefetchCount = 5** on a consumer means the broker can deliver multiple unacked messages capped at a 5-delivery window under that QoS setting. When one delivery is ACKed, one slot opens in the window so the broker can send another.

**Prefetch does not mean receiving exactly 5 messages at once**, nor does it give one consumer 5 parallel business threads. It caps the **unacked window**, not Java batch size or total messages stored in the queue.

### 5.1. How Does RabbitMQ Apply Prefetch per Consumer?

RabbitMQ applies **per-consumer prefetch** in standard configurations: the limit applies individually to each consumer rather than defaulting to a single shared quota across the whole channel. Global QoS settings or other client options can alter this scope.

In Spring AMQP, the container's **prefetchCount** typically applies to consumers managed by that container. Therefore, to estimate potentially in-flight messages, calculate **prefetch per consumer × actual number of consumers** rather than looking at a single prefetch value alone.

### 5.2. Ready, Unacked, and ACK Are Three Distinct States

In RabbitMQ management, you commonly see:

- **Ready:** messages in the queue available to be delivered to consumers.
- **Unacked:** deliveries sent by the broker awaiting consumer ACK/NACK under active semantics.
- **Total/queue depth:** total messages reported by the broker, which can include both ready and unacked.

A queue with **Ready = 0** and **Unacked = 80** does not mean consumers finished 80 business tasks; they may be holding many unacknowledged deliveries. Conversely, **Ready climbing steadily** while consumers lag behind producers signals accumulating backlog.

### 5.3. Estimating the Unacked Window

Suppose there are **N consumers**, each with prefetch **P**, and no additional global cap:

~~~text
Potentially in-flight unacked deliveries ≈ N × P
~~~

For example, **4 consumers × prefetch 20** permits up to roughly **80 unacked deliveries** under ideal QoS conditions. This is **not** a promise the broker always pushes all 80, nor is it a cap on total backlog in RabbitMQ. Actual counts depend on processing speed, connections, ACKs, batching, active consumers, and other limits.

If an average payload is **256 KiB**, raw data alone for 80 deliveries is around **20 MiB**, before counting wrapper objects, decoding, buffers, and business objects. With large messages, raising prefetch can cause significant memory pressure.

### 5.4. Prefetch = 1

**Prefetch = 1** is often considered when:

- Messages take a long and uneven time to process.
- You want to prevent one consumer from hoarding work while another sits idle.
- Each consumer should hold very few unacked messages.
- You need to limit how many messages get redelivered when one consumer dies.

In trade-off, throughput may drop because the broker waits for an ACK before sending the next message to that consumer. With fast tasks and noticeable network latency, a higher prefetch often helps. **No single prefetch value is optimal for every workload.**

### 5.5. Large Prefetch

A large prefetch can:

- Reduce consumer wait time for the next delivery.
- Boost throughput for fast handlers.
- But also increase **unacked** counts, memory footprint, and held deliveries if a consumer slows down or dies.
- Worsen load distribution fairness across consumers when processing times vary.
- Increase the burst of deliveries that must be requeued/redelivered if a connection drops before ACK.

Therefore, tune **prefetch**, **concurrency**, **payload size**, and **actual handler latency** together rather than raising one parameter until the ready queue drops.

## 6. Prefetch Cannot Be Separated from ACK Mode

Spring AMQP listener containers support common ACK modes:

| AcknowledgeMode | Confirmation Behavior | Impact on Prefetch |
| --- | --- | --- |
| **AUTO** | Container ACKs on successful listener completion; errors handled per policy | Prefetch bounds deliveries awaiting container ACK |
| **MANUAL** | Application code must ACK/NACK with delivery tag and AMQP channel | Prefetch quota can saturate completely if ACK is forgotten |
| **NONE** | Consumer runs without manual ACK; broker treats deliveries as settled | Unacked window does not protect business execution the way AUTO/MANUAL do |

**AUTO does not mean the broker ACKs immediately upon sending.** In Spring AMQP, AUTO means the container manages ACK based on listener execution outcome. By contrast, NONE offers no redelivery protection if the process crashes after receiving but before business work completes.

### 6.1. Synchronous DirectChannel and AUTO ACK

If the inbound adapter sends to a **DirectChannel** and the handler completes synchronously, handler exceptions propagate back through the channel/adapter to the listener container. The container ACKs when the callback succeeds, or rejects/NACKs per error policy when it fails.

**Consumer ACK still does not create an atomic transaction with the database.** If the handler commits the DB and the process crashes before ACK reaches the broker, the message can be redelivered. Consumers still need business idempotency.

### 6.2. ExecutorChannel/QueueChannel Can Trigger Premature ACKs

If the inbound adapter sends to an **ExecutorChannel**:

~~~text
RabbitMQ delivery -> listener -> inbound adapter
                   -> ExecutorChannel accepts task
                   -> listener callback returns
                   -> container may ACK
                   -> handler runs later on another thread
                   -> handler fails after ACK already happened
~~~

This creates a **risk window where RabbitMQ-level redelivery is lost**. Do not replace DirectChannel with ExecutorChannel solely to increase throughput if business ACK guarantees require waiting for the handler to finish. QueueChannel creates a similar asynchronous boundary; with a durable queue/message store you can design a safe handoff point, provided you clearly define when durability is achieved.

### 6.3. Manual ACK Requires Strict Discipline

With MANUAL, ensure **every branch—success, recoverable error, permanent error, and shutdown**—performs a controlled ACK/NACK.

If the handler forgets to ACK, **unacked** climbs until hitting prefetch; the broker stops pushing deliveries to that consumer while the ready queue keeps growing. When the channel/connection closes, unacked deliveries can be redelivered per policy, causing duplicate processing.

With asynchronous processing, do not pass AMQP channel/delivery tag references casually across threads expecting ACKs to always remain valid. Channel validity, lifecycle, and coordination must be verified against actual Spring AMQP/RabbitMQ client semantics.

### 6.4. Batch Size and Transactions Affect ACK Timing

With SMLC, certain **batchSize**, transaction, or consumer batching settings can cause ACKs to be issued in batches rather than per delivery. Depending on version/configuration, the container may ensure prefetch is not smaller than the required batch size.

So assuming "prefetch = 10 means every message is ACKed right after the handler" is wrong. Know your **acknowledge mode, batch size, channelTransacted, advice chain, and container behavior**. The handler's DB transaction also keeps its own scope; do not conflate it with RabbitMQ transaction/channel ACK.

## 7. Concurrency × Prefetch: Impact on Throughput and Latency

Suppose the handler's average processing time is **T seconds/message**, with **N consumers** truly working independently, ignoring other bottlenecks. An optimistic upper bound on throughput is:

~~~text
Max handler-bound throughput ≈ N / T (messages/second)
~~~

If each message takes roughly **0.2 seconds**, one sequential consumer handles about **5 messages/second**, and four consumers can reach about **20 messages/second**, *if* the database, broker, and CPU keep up. Raising prefetch from 10 to 100 **will not shrink a single message's processing time below 0.2 seconds**.

| Adjustment | Can Improve | Can Worsen |
| --- | --- | --- |
| Increase prefetch | Reduces delivery wait time for fast handlers | Memory, unacked count, fairness, redelivery bursts |
| Increase concurrent consumers | Increases parallel processing | DB contention, processing order, connection/channel load |
| Increase downstream executor threads | Reduces channel-send latency in some designs | Premature ACK, internal backlog, async errors |
| Decrease prefetch | Fairness, fewer buffered unacked messages | Lower throughput if ACK/network latency is significant |
| Batch processing | Reduces per-message overhead/transaction cost depending on domain | Increases delivery hold time, rollback/ACK complexity |

### 7.1. Fairness Across Consumers

Two consumers on the same queue: worker A takes 2 seconds/message, worker B takes 20 ms/message. With a high prefetch, worker A can hoard a large batch of unacked deliveries while B sits idle after finishing its share. Lowering prefetch gives the broker more opportunities to dispatch further work to B after each ACK.

**Fair dispatch** is not simply toggling a boolean flag. It depends on prefetch, handler latency, consumer count, requeues, queue policies, and delivery scheduling. Measure individual consumers instead of looking only at total messages in the queue.

### 7.2. Processing Order Is Not Guaranteed by a Single Queue Alone

With multiple consumers, large prefetch, retries/requeues, or async handlers, **business completion order** can differ from publish order. If OrderCreated must be applied before OrderCancelled for the same orderId, enforce domain sequence/version checks and idempotency or use ordered partitioning rather than relying on one queue.

Prefetch = 1 **does not guarantee global ordering** when multiple consumers are active.

## 8. Choosing Starting Values and Measuring Instead of Guessing

There is no universal "standard" prefetch for all systems. Start with a moderate configuration in tests, then tune against real workload metrics:

1. **Measure baseline:** handler p50/p95/p99 latency, payload size, ready/unacked counts, consumer count, ACK rate.
2. **Choose ACK semantics:** what must finish before ACK? Are there side effects?
3. **Bound concurrency:** DB capacity, downstream HTTP limits, pools, CPU, and RabbitMQ connections/channels.
4. **Test a small-to-moderate prefetch:** measure throughput and fairness across consumers.
5. **Increase in controlled steps:** monitor unacked, heap, GC, latency, and redelivery when killing a consumer.
6. **Test failures:** poison messages, downstream timeouts, broker reconnects, shutdown.
7. **Document proven settings:** tie them to volume, message size, and SLA targets; do not copy sample numbers blindly into another environment.

**A load test result is only valid for its workload and conditions.** Document producer rate, exchange/queue types, consumer concurrency, payload size, message converter, DB pool, prefetch, batching, ACK mode, and retry config.

## 9. Java DSL Example: AMQP Inbound with SMLC and Prefetch

Let's build a one-way flow receiving **OrderCreated** events:

~~~text
RabbitMQ direct exchange: orders.events
  └── routing key: orders.created
       └── durable queue: orders.created.q
            └── SimpleMessageListenerContainer
                 ├── acknowledgeMode = AUTO
                 ├── prefetchCount = 16
                 ├── concurrentConsumers = 2
                 └── maxConcurrentConsumers = 4
                      └── AMQP inbound channel adapter
                           └── DirectChannel / service activator
~~~

The example also configures a **dead-letter exchange/queue** for messages rejected without requeue, preventing a poison message from looping infinitely. This is an **illustrative policy**, not a rule that transient errors should skip retries.

### 9.1. Dependencies

With Spring Boot, use compatible modules managed by the Spring Boot BOM:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-amqp</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-amqp</artifactId>
    </dependency>
</dependencies>
~~~

The practice environment requires a RabbitMQ broker and a ConnectionFactory configured with host, port, virtual host, and proper permissions. Never put real credentials in code; use environment variables or a secret manager. Create topology in the exact virtual host used by the app.

### 9.2. Declaring Exchange, Queue, Binding, and Dead-Letter Queue

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderAmqpTopology {

    public static final String EVENTS_EXCHANGE = "orders.events";
    public static final String EVENTS_ROUTING_KEY = "orders.created";
    public static final String INBOUND_QUEUE = "orders.created.q";

    public static final String DEAD_EXCHANGE = "orders.dead.exchange";
    public static final String DEAD_ROUTING_KEY = "orders.dead";
    public static final String DEAD_QUEUE = "orders.created.dlq";

    @Bean
    public DirectExchange ordersExchange() {
        return new DirectExchange(EVENTS_EXCHANGE, true, false);
    }

    @Bean
    public Queue ordersQueue() {
        return QueueBuilder.durable(INBOUND_QUEUE)
            .deadLetterExchange(DEAD_EXCHANGE)
            .deadLetterRoutingKey(DEAD_ROUTING_KEY)
            .build();
    }

    @Bean
    public Binding ordersBinding(
            Queue ordersQueue, DirectExchange ordersExchange) {
        return BindingBuilder.bind(ordersQueue)
            .to(ordersExchange)
            .with(EVENTS_ROUTING_KEY);
    }

    @Bean
    public DirectExchange ordersDeadExchange() {
        return new DirectExchange(DEAD_EXCHANGE, true, false);
    }

    @Bean
    public Queue ordersDeadQueue() {
        return QueueBuilder.durable(DEAD_QUEUE).build();
    }

    @Bean
    public Binding ordersDeadBinding(
            Queue ordersDeadQueue,
            DirectExchange ordersDeadExchange) {
        return BindingBuilder.bind(ordersDeadQueue)
            .to(ordersDeadExchange)
            .with(DEAD_ROUTING_KEY);
    }
}
~~~

**Meaning:** Producers publish to exchange **orders.events** with routing key **orders.created**. The broker routes into **orders.created.q**. When a delivery is rejected/NACKed with **requeue=false**, the broker dead-letters it to **orders.dead.exchange**, routing it into **orders.created.dlq**.

**Topology warning:** Spring beans only describe resources. RabbitAdmin/AmqpAdmin must be enabled and authorized, or infrastructure must provision the topology. If the broker already has a queue with the same name and different arguments, redeclaration may be rejected. Never alter production topology casually via an application restart.

### 9.3. SMLC with Prefetch and Consumer Concurrency

~~~java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.listener.SimpleMessageListenerContainer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersListenerConfiguration {

    @Bean
    public SimpleMessageListenerContainer ordersListenerContainer(
            ConnectionFactory connectionFactory) {

        SimpleMessageListenerContainer container =
            new SimpleMessageListenerContainer(connectionFactory);

        container.setQueueNames(OrderAmqpTopology.INBOUND_QUEUE);
        container.setConcurrentConsumers(2);
        container.setMaxConcurrentConsumers(4);
        container.setPrefetchCount(16);
        container.setAcknowledgeMode(AcknowledgeMode.AUTO);

        // Demo: errors propagating to the container will be rejected without requeue.
        // Queue must have DLX/DLQ if you want to keep failed messages.
        container.setDefaultRequeueRejected(false);

        return container;
    }
}
~~~

**Configuration analysis:**

| Setting | Example Value | What to Understand |
| --- | ---: | --- |
| **concurrentConsumers** | 2 | Base/initial number of consumers in SMLC |
| **maxConcurrentConsumers** | 4 | Upper bound when consumer scaling applies |
| **prefetchCount** | 16 | Unacked delivery window per consumer under standard QoS |
| **acknowledgeMode** | AUTO | Container manages ACK based on callback outcome |
| **defaultRequeueRejected** | false | Errors reaching the container can be rejected without requeue instead of looping infinitely |

With 2 active consumers, theoretical in-flight capacity can reach roughly **32 unacked deliveries**. If SMLC scales up to 4 consumers, it can reach roughly **64 deliveries**. This is neither the guaranteed active message count nor the maximum number of business threads; batching, transactions, QoS, and actual handler behavior all interact.

**defaultRequeueRejected(false) is not a complete retry policy.** Without a proper retry mechanism, it can send transient database errors straight to the dead-letter queue. In real systems, classify errors, bound retries/backoff, and route to the DLQ according to policy.

### 9.4. Wiring the Container into Spring Integration

~~~java
import org.springframework.amqp.rabbit.listener.SimpleMessageListenerContainer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.amqp.dsl.Amqp;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class OrdersInboundIntegrationConfiguration {

    @Bean
    public MessageChannel rabbitOrders() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow ordersInboundFlow(
            SimpleMessageListenerContainer ordersListenerContainer) {

        return IntegrationFlow
            .from(Amqp.inboundAdapter(ordersListenerContainer))
            .channel("rabbitOrders")
            // Synchronous handler, keeping exceptions inside the listener call chain.
            .handle(String.class, (payload, headers) -> {
                String[] fields = payload.split("\\|", -1);
                if (fields.length != 3
                        || !fields[0].matches("[A-Za-z0-9_-]{1,80}")
                        || !fields[1].matches("[A-Za-z0-9_-]{1,80}")
                        || !fields[2].matches("[0-9]+")) {
                    throw new IllegalArgumentException(
                        "Payload must have format eventId|orderId|totalVnd");
                }

                long totalVnd = Long.parseLong(fields[2]);
                if (totalVnd <= 0) {
                    throw new IllegalArgumentException(
                        "totalVnd must be greater than 0");
                }

                System.out.println(
                    "Received " + fields[0]
                        + " for order " + fields[1]
                        + ", totalVnd=" + totalVnd);

                // One-way inbound: do not return a business reply.
                return null;
            })
            .get();
    }
}
~~~

The configuration classes above are **separate Java files**. They illustrate passing a **pre-configured listener container** to the AMQP inbound adapter instead of letting it create a default container with unknown prefetch/concurrency settings.

**Important note on ACK:** The handler in this example runs synchronously in the flow behind the adapter. If an exception propagates back to the listener/container, reject-without-requeue can route the message to the DLQ as designed. However, if you add an **errorChannel** or error handler that catches the exception and finishes normally, the container may see a successful callback and ACK anyway. Always verify final ACK behavior rather than relying solely on whether the handler throws.

**Do not use this sample to claim an order was processed successfully.** The handler only parses and logs. Production requires a service activator writing to the database, eventId as an idempotency key, transactions, error handling, and formal schema validation.

### 9.5. Why Not Raise Prefetch Before Adding Idempotency?

A handler that commits to the DB before the process crashes prior to sending ACK can trigger redelivery. Large prefetch increases the number of deliveries potentially in-flight when a connection drops. **Redelivery does not turn a message into a new business event**: keep eventId and record processed markers.

For instance, the consumer receives **evt-1001** again after a crash. If the database already recorded Order O-1001, the second delivery must be recognized as a duplicate without creating a second side effect. Use a unique constraint on eventId or an inbox table within the same business transaction.

## 10. Sending a Test Message and Verifying Prefetch

With a RabbitTemplate connected to the same virtual host:

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;

public class OrdersTestPublisher {
    private final RabbitTemplate rabbitTemplate;

    public OrdersTestPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void sendOne() {
        rabbitTemplate.convertAndSend(
            OrderAmqpTopology.EVENTS_EXCHANGE,
            OrderAmqpTopology.EVENTS_ROUTING_KEY,
            "evt-1001|O-1001|150000");
    }
}
~~~

When topology, broker connection, converter, and listener align, the String payload reaches the handler. If a producer sends **JSON** or **binary** using a different converter, the String handler in this example will not match; configure a contract-appropriate message converter or transformer first.

### 10.1. Verifying the Receiving Path

1. Spin up a test broker and verify exchange/queue/bindings exist.
2. Start the application with the listener container above.
3. Publish **evt-1001|O-1001|150000**.
4. Observe the handler printing the message and the broker advancing delivery/ACK counts.
5. Pause the listener and send multiple messages; the broker retains ready messages per policy. Resume it and watch the queue drain.
6. Send a malformed message such as **bad-message**: as the error reaches the container, reject-without-requeue plus DLX should move it to the DLQ instead of looping forever.
7. Simulate a slow handler in tests to observe unacked counts. Adjust prefetch in controlled steps and record the results.

### 10.2. Why Slow Down the Handler in a QoS Test?

When a handler finishes very quickly, continuous ACKs rapidly free quota, so unacked counts in RabbitMQ management can stay low even with high prefetch. That does not mean prefetch was ignored.

To observe the QoS window, run a **test handler with controlled latency** or a test downstream service. In isolated tests, vary latency and consumer count, then compare **peak unacked**, **ready queue depth**, **ACK rate**, and total batch completion time.

Never add artificial sleep to production handlers to "stabilize prefetch"; it is strictly a test simulation tool.

### 10.3. Crash and Redelivery Testing

1. Publish a batch of events with distinct IDs.
2. Let the listener receive part of them without ACKing all (in a controlled test environment).
3. Abruptly kill the consumer process/connection instead of performing a graceful shutdown.
4. Restart the consumer; verify unacked deliveries are handled/redelivered by the broker per policy.
5. Reconcile **eventIds applied in the database** against **actual delivery counts** to verify idempotency.

Never infer business ordering from post-crash redelivery order. Requeue behavior, consumer concurrency, and broker policies can alter processing order.

## 11. When Do You Need DirectMessageListenerContainer?

**DirectMessageListenerContainer** (DMLC) is an alternative when a direct-dispatch model and per-queue consumer management fit better.

Example Spring AMQP container configuration:

~~~java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.listener.DirectMessageListenerContainer;

// Illustrative SMLC replacement; do not run two listener
// containers on the same queue concurrently if testing independently.
DirectMessageListenerContainer direct =
    new DirectMessageListenerContainer(connectionFactory);
direct.setQueueNames("orders.created.q");
direct.setConsumersPerQueue(2);
direct.setPrefetchCount(16);
direct.setAcknowledgeMode(AcknowledgeMode.AUTO);
~~~

This is a **comparison configuration snippet**, not code to spawn a second competing container inside the same sample app. When using DMLC in Spring Integration, wire it into the endpoint instead of SMLC and verify API compatibility for your Spring Integration/Spring AMQP version.

### 11.1. SMLC or DMLC?

Evaluate based on:

- Handler workload profile: slow I/O, CPU-heavy, synchronous DB calls, or async downstream calls.
- Queue count, consumers per queue, frequency of topology changes, and how the container manages consumers.
- Need for SMLC's **dynamic scaling** vs. DMLC's **consumersPerQueue** management.
- How thread pools and the RabbitMQ Java client executor are utilized.
- Interactions among prefetch, ACK, batching, and shutdown.
- Logs, connection errors, timeouts, and benchmarks on the **same workload**.

Never infer from the word **Direct** in its name that DMLC equals Spring Integration's **DirectChannel**. One is a RabbitMQ listener container; the other is an internal MessageChannel type.

## 12. Retry, Requeue, and Dead-Letter Must Coordinate with Prefetch

When a handler fails, unacked counts and container error handling determine how backlog behaves:

~~~mermaid
flowchart TD
    Q["RabbitMQ queue"] --> L["Listener container"]
    L --> A{"Handler outcome?"}
    A -->|"Success"| ACK["ACK, free quota"]
    A -->|"Transient error"| RET["Bounded retry + backoff"]
    RET --> A
    A -->|"Permanent error / retries exhausted"| NACK["Reject/NACK without requeue"]
    NACK --> DX["Dead-letter exchange if configured"]
    DX --> DQ["Dead-letter queue"]
~~~

### 12.1. Poison Messages and Requeue Loops

A message with invalid JSON or missing required fields can cause the handler to throw on every delivery. If the container requeues by default on every error, the broker repeatedly redelivers that exact message, spiking CPU, inflating redeliveries, and stalling queue progress.

For permanent data errors:

- Validate payloads against a schema.
- Quarantine failing messages or reject without requeue into an appropriate DLQ.
- Log event ID, cause, and attempt count.
- Maintain a controlled data-fix/replay workflow; never retry infinitely.

### 12.2. Transient Errors and Retries

When a database or downstream API fails briefly, bounded retries with backoff can help. Decide between **retrying inside the listener** vs. **returning to a queue with delay/retry policies**; each affects prefetch differently:

- In-listener retry holds the delivery **unacked** longer, occupying a prefetch slot.
- Immediate requeue can create a hot redelivery loop while the downstream target stays down.
- Delay/DLX queue retries or persisted progress tracking require careful topology and duplicate handling.

**High prefetch + slow retries** can pin many deliveries in unacked state at once; changing one parameter without measuring ACK latency, consumer memory, and backlog is risky.

### 12.3. Do Not Confuse Consumer DLQ with Publisher Return

A publisher sends a message to an exchange with no matching binding: that is **unroutable**. **Mandatory/returns** or an alternate exchange handle it on the producer side. A delivery already in a queue rejected by a consumer without requeue: that can be **dead-lettered**. The two situations occur at **two different stages**.

### 12.4. Exceptions and errorChannel in Spring Integration

With DirectChannel, handler errors can propagate back to the listener. However, if an endpoint has an **errorChannel** configured and errors are converted into ErrorMessages, the container may no longer see the exception as a callback failure.

Therefore, when designing ACK/NACK:

1. Verify whether exceptions actually reach the Spring AMQP container.
2. Determine whether the error flow ends in failure or returns normally.
3. Check whether listener error handlers/advice retry or swallow/transform exceptions.
4. Confirm actual broker ACK/NACK behavior in an integration test.

**Never treat "the handler logged an error" as proof that the broker will automatically redeliver.**

## 13. SMLC Dynamic Scaling: Adding Consumers at the Right Time

**SimpleMessageListenerContainer** can scale consumers up and down within configured bounds as workload shifts. Relevant settings can include:

- **concurrentConsumers:** baseline count.
- **maxConcurrentConsumers:** upper bound.
- **consecutiveActiveTrigger** and **consecutiveIdleTrigger:** active/idle thresholds over observation cycles.
- **startConsumerMinInterval** and **stopConsumerMinInterval:** minimum intervals between scaling changes.
- **receiveTimeout**, **batchSize**, and active/idle cycle evaluation rules.

These parameters interact; check the exact scaling algorithm for your Spring AMQP version. **Do not simply shrink startConsumerMinInterval expecting the container to jump immediately to maxConcurrentConsumers.** Active/idle triggers, message availability, timeouts, and downstream behavior still govern scaling.

### 13.1. Scaling Consumers Does Not Scale the Database

Suppose each consumer opens a transaction updating inventory. If the database connection pool only supports limited concurrency, raising consumers from 4 to 32 can cause:

- More threads waiting on DB connections.
- Higher lock contention.
- Longer processing times and more unacked deliveries.
- More retries from transaction timeouts.
- Worse p95/p99 latency despite higher consumer counts.

Set **maxConcurrentConsumers** based on downstream capacity and application instance count, not CPU core count alone.

### 13.2. Scale-Out and Total Consumer Count

With **3 application instances**, each scaling from 2 to 4 consumers, the service as a whole can run roughly **6 to 12 consumers** on the same queue. At prefetch **16**, theoretical unacked deliveries across the fleet can far exceed a single instance's numbers.

When scaling out, sum **total consumers and prefetch across all instances**, not just one JVM. Network limits, RabbitMQ channels/connections, total database pool size, and ordering constraints must all be evaluated.

### 13.3. Do Not Assume Every Container Autoscales Automatically

SMLC supports dynamic concurrency scaling when configured. DMLC uses a different consumer management model with **consumersPerQueue**. When adjusting a running container dynamically, verify which setters or runtime configurations your library version supports and when changes take effect.

## 14. Container Lifecycle, Connections, and Graceful Shutdown

Listener containers and AMQP endpoints typically participate in Spring's **Lifecycle/SmartLifecycle** via **start()**, **stop()**, **isRunning()**, **autoStartup**, and **phase** per bean/configuration.

### 14.1. Milestones to Distinguish

| Observation | Can Infer | Cannot Yet Conclude |
| --- | --- | --- |
| Container isRunning = true | Container is in running lifecycle state | Broker is healthy, queue exists, business handler has no errors |
| RabbitMQ consumer count rises | Broker sees registered consumers | Throughput meets SLA or side effects committed |
| Ready = 0 | No messages waiting for delivery at measurement time | Zero unacked or zero in-progress tasks |
| Unacked = 0 | No deliveries awaiting ACK per that metric | Zero messages processing in async channels |
| Handler returns | Callback reached a processing point | All external long-running systems completed |

**isRunning() is a lifecycle state**, whereas broker connectivity, queue metrics, and business outcomes are separate perspectives. A listener can be stuck in a reconnect loop without processing a single message.

### 14.2. During Application Shutdown

A reference graceful shutdown sequence:

1. Stop upstream sources from generating new work if the application also owns producers.
2. Instruct the listener container to stop accepting deliveries via supported controls.
3. Monitor **in-flight/unacked**, active handlers, and running DB transactions.
4. Let accepted work complete within operational bounds, or rely on requeue/redelivery/idempotency if it cannot finish in time.
5. Stop downstream resources and close ConnectionFactory/shared resources in Spring lifecycle order.
6. On restart, verify backlog, consumer count, requeues, retries, and business checkpoints.

**stop() does not automatically mean every message has finished draining.** Containers have shutdown timeouts and specific behaviors when listeners remain busy; if connections/channels close while deliveries are unacked, the broker may redeliver them. Test **shutdown under load**, not just when the queue is empty.

### 14.3. Connection Drops and Prefetch Impact

If a consumer holds many unacked deliveries and the connection drops, RabbitMQ returns unacked deliveries to a redeliverable state per policy. New consumers may receive messages that a prior handler partially processed.

Higher prefetch means more potentially pre-fetched deliveries. Yet **lowering prefetch to 1 does not eliminate duplicate business risk**: the gap between DB commit and ACK still exists.

### 14.4. Do Not Close a Shared ConnectionFactory Arbitrarily

Multiple endpoints often share one **CachingConnectionFactory**: inbound listeners, outbound RabbitTemplates, AMQP gateways. Stopping one endpoint does not mean the application should immediately close the shared connection factory. ApplicationContext normally manages ConnectionFactory; closing it prematurely can break other flows.

## 15. Observability: Which Metrics Prove Configuration Is Healthy?

To tune prefetch effectively, measure across **broker**, **container**, **channel**, and **business** layers:

| Layer | Metrics to Collect | Question Answered |
| --- | --- | --- |
| RabbitMQ queue | ready, unacked, total, message age | Where is backlog, and how many delivered messages await ACK? |
| RabbitMQ consumer | consumer count, delivery rate, ACK/NACK/requeue rate | Are enough consumers connected and making progress? |
| Listener container | Active consumer count, reconnects, handler failures, running status | Is the container working or hitting connection errors? |
| JVM/threads | Thread count, CPU, heap, GC pauses, executor queue | Are prefetch/concurrency straining resources? |
| Handler | p50/p95/p99 latency, DB latency, transaction timeouts | Where is the business bottleneck? |
| Error flow | Retry attempts, poison message count, DLQ ingress | Are errors looping in requeue or quarantined properly? |
| Business | Unique eventIds processed, duplicate skips, completion rate | How much real business work actually succeeded? |

### 15.1. Interpreting Common Metric Patterns

**Ready rising, unacked low, consumer count low:** likely missing consumers, stopped listeners, low prefetch, or consumers processing slowly with few deliveries. Inspect logs/reconnects and per-consumer throughput.

**Ready high, unacked near N × P:** consumers have saturated their prefetch window. Inspect handler latency, downstream services, or slow ACKs; raising prefetch further may not help.

**Unacked high while CPU is low:** likely waiting on DB/network, forgotten MANUAL ACKs, hung transactions, or waiting executors. Do not blame RabbitMQ automatically.

**Very high redelivery/requeue and low business success:** suspect poison messages, downstream outages, or an unbounded requeue policy.

**High ACK rate yet low business outcomes:** check whether ACKs happen before async processing finishes, or whether an error flow swallowed exceptions.

### 15.2. Prefetch Is Not End-to-End Flow Control

RabbitMQ prefetch caps unacked deliveries per consumer/QoS. It **does not bound** total messages producers send to exchanges, events piling up in other queues, or tasks already ACKed by consumers and queued in internal executors.

To control end-to-end overload, you may need:

- Producer rate limiting or backpressure.
- Bounded internal channel/executor capacities.
- Consumer concurrency sized to downstream limits.
- Bounded retries/backoff.
- Durable state storage if ACKing at an internal boundary before final business completion.

## 16. Data-Driven Prefetch Tuning Scenario

Suppose an application has these **illustrative** requirements, not measurements from a real system:

| Factor | Assumption |
| --- | --- |
| Producer | 120 messages/second during peak hours |
| Handler | 50 ms/message average, synchronous execution |
| Application instances | 2 |
| Consumers per instance | 2 (4 total) |
| Initial prefetch | 10 per consumer |
| Payload | 4 KiB average |
| ACK mode | AUTO |

If each consumer processes sequentially at 50 ms/message and all other layers keep up, ideal total capacity is roughly **4 / 0.05 = 80 messages/second**, below the producer's 120 messages/second. **Raising prefetch from 10 to 100 cannot make four consumers process faster than 80 messages/second merely by holding more pre-fetched deliveries.**

Improvements to test and verify:

1. Reduce handler/DB transaction duration if possible.
2. Raise consumer count within DB and broker limits, measuring p95/p99 afterward.
3. Add instances if infrastructure can sustain the load.
4. Adjust prefetch when evidence shows consumers waiting too long for deliveries or experiencing unfairness.
5. Accept controlled backlog and define a drain-time target if this is a short-lived traffic spike.

### 16.1. Comparing Three Test Configurations

| Test Config | Total Consumers | Prefetch per Consumer | Estimated Unacked Window | Hypothesis to Measure |
| --- | ---: | ---: | ---: | --- |
| A | 4 | 1 | ~4 | Fair, few pre-fetched messages, though higher ACK wait overhead possible |
| B | 4 | 10 | ~40 | Less delivery wait time without increasing business parallelism |
| C | 8 | 10 | ~80 | Can raise throughput if DB/CPU allow; increases in-flight deliveries |

After each test run, compare **completed throughput**, **ready/unacked**, **memory**, **p95/p99 latency**, **retries/DLQ**, and recovery after killing one consumer. Never pick a configuration solely because the ready count drops fastest while ignoring business correctness.

### 16.2. Uneven Workloads

If 90% of messages finish in 5 ms while 10% take several seconds, prefetch and multiple consumers distribute work very differently than in a uniform workload. Test with **realistic latency distributions**, mixed small/large payloads, and realistic failure rates—not just a single message type against a no-op handler.

## 17. Pre-Production Test Matrix

| Test | Action | Outcome to Verify |
| --- | --- | --- |
| Normal connectivity | Start broker/consumer, publish valid message | Handler receives data and broker records proper ACK |
| No messages | Keep queue empty | Container stays active without falsely reporting failure |
| Low prefetch | Prefetch 1, slow handler | Unacked follows QoS properly without over-fetching |
| High prefetch | Prefetch 32, slow handler | Unacked rises within cap; measure heap and latency |
| Multiple consumers | 2 then 4 consumers | Verify total in-flight, throughput, and fairness |
| SMLC autoscale | Ramp load up and down over time | Consumer count adjusts within configured bounds when triggers match |
| Forgotten Manual ACK | Isolated test, never in production | Unacked climbs and new deliveries pause at limit |
| Poison message | Invalid schema payload | Retry/DLQ follows policy without infinite requeue |
| Downstream timeout | Simulate transient DB/API error | Bounded retry and accurate ACK/NACK |
| Async channel | Switch DirectChannel to ExecutorChannel in test | Verify ACK timing and worker errors after listener returns |
| Consumer crash | Kill one instance while unacked exist | Broker redelivers; business logic creates no duplicate side effects |
| Broker restart | Stop and restart test broker | Container reconnects; backlog drains per policy |
| Scale-out | Run multiple instances on same queue | Deliveries split across consumers; not broadcast by default |
| Shutdown under load | Stop app while handlers are running | Tasks finish or recover without misreporting progress |
| DLX missing binding | Reject invalid message | Topology gap detected; never assume DLQ receives automatically |

### 17.1. Practical Verification Checklist

Before increasing prefetch in production, document:

1. **Goal:** higher throughput, lower latency, or better fairness?
2. **Format and size:** String/JSON/bytes payload, mean and p99 size.
3. **ACK point:** synchronous handler, batch, manual ACK, or errorChannel?
4. **Limits:** max consumers, DB pool, thread pool, heap, max connections.
5. **Recovery:** are unacked messages on crash reprocessed idempotently?
6. **Alert thresholds:** ready/unacked, retries, DLQ, consumer lag/age, and business failures.
7. **Config rollback:** if latency or memory spikes, can prior prefetch/concurrency be restored quickly?

## 18. Common Mistakes

**"Prefetch = 100 means 100 processing threads."** Prefetch is the unacked delivery window, not concurrency.

**"Raising prefetch always increases throughput."** When the handler/DB is the bottleneck, it only buffers more pre-fetched messages.

**"Prefetch applies once globally across all consumers."** RabbitMQ commonly applies prefetch per consumer; account for QoS scope and total consumer count.

**"SMLC and DMLC are two names for the same container."** They have different thread models and consumer management mechanisms.

**"DMLC is DirectChannel."** One is a RabbitMQ listener container; the other is a synchronous Spring Integration channel.

**"AMQP inbound adapter needs Pollers.fixedDelay like File inbound."** Message-driven listeners normally receive via broker consumers/containers and do not need that poller.

**"AUTO ACK means the broker auto-ACKs upon delivery."** Spring AMQP AUTO lets the container ACK based on callback outcome, unlike NONE.

**"Using ExecutorChannel does not change delivery guarantees."** The listener may ACK before the asynchronous handler finishes.

**"Unacked = 0 means all business work is done."** Messages may already be ACKed yet still sit in an internal queue or executor.

**"MANUAL ACK is always safer."** Forgetting to ACK fills the prefetch window; mishandling delivery tags/channels causes errors.

**"Every exception definitely triggers broker requeue."** ErrorChannel, retry advice, error handlers, and container policies can change the outcome.

**"DLQ exists automatically when calling setDefaultRequeueRejected(false)."** You must declare actual DLX, DLQ, and bindings; otherwise rejected messages may simply be dropped.

**"Prefetch = 1 guarantees exactly-once and strict ordering."** Redelivery, multiple consumers, and non-broker side effects still exist.

**"Having a durable queue removes the need for idempotency."** Messages can be redelivered if a consumer crashes before ACK; business deduplication is still required.

**"Raising consumers only affects one JVM."** In multi-instance deployments, sum consumers/prefetch across the entire fleet.

## 19. Self-Check Questions

1. How do the roles of RabbitMQ queue, Spring AMQP listener container, and Spring Integration AMQP inbound adapter differ?
2. Why does a message-driven adapter usually not require a Spring Integration Poller?
3. Compare SMLC and DMLC by thread model and concurrency configuration.
4. With prefetchCount = 20 and four consumers, roughly how many unacked deliveries are permitted? Is that number throughput?
5. How do ready and unacked differ? When can ready = 0 while business processing is not yet finished?
6. Why can prefetch = 1 improve fairness yet reduce throughput?
7. How do AUTO ACK, MANUAL ACK, and NONE differ regarding who confirms delivery?
8. If the handler commits to the DB and the process crashes before ACK, what can happen?
9. Why can switching from DirectChannel to ExecutorChannel cause the listener to ACK too early?
10. In the Java DSL example, which settings determine concurrency and the unacked window?
11. Does `defaultRequeueRejected(false)` create a DLQ automatically? Which resources must exist?
12. When a handler hits a transient database error, why might rejecting straight to a DLQ not be the best policy?
13. With 3 instances each running 4 consumers and prefetch 16, how should total in-flight capacity be evaluated?
14. If unacked approaches the quota while CPU stays low, which components should be investigated?
15. Why does raising prefetch fail to speed up a DB-bound handler?
16. When the container stops or the RabbitMQ connection drops, how can unacked deliveries be handled?
17. To ensure both Warehouse and Analytics receive every event, should you use two queues or two consumers on one queue?
18. Which metrics and tests tell you a prefetch configuration is ready for production?
19. Why check errorChannel and retry advice before concluding the container will NACK when a handler throws?
20. When business logic requires processing once per eventId, can prefetch and ACK replace a unique constraint/inbox table?

## Summary

A **message-driven listener container** is the bridge receiving RabbitMQ deliveries so the Spring Integration **AMQP inbound channel adapter** can build Spring Messages and send them to a **MessageChannel**. **SimpleMessageListenerContainer** and **DirectMessageListenerContainer** use different consumer-management models; both require understanding ACK semantics, concurrency, and connection lifecycles before operating in production.

**Prefetch** limits how many **unacked** deliveries the broker may push ahead under QoS rules typically applied per consumer. It is not a thread count, not a whole-queue backlog limit, and does not automatically increase handler speed. Good configuration balances **throughput, fairness, memory, consumer count, message size, and downstream latency**. In particular, identify the **ACK point** when using DirectChannel or asynchronous channels, classify errors for proper retry/DLQ handling, and enforce idempotency whenever redelivery is possible. Only increase prefetch based on ready/unacked metrics, ACK rates, latency, error rates, and verified business outcomes from load and failure tests.
