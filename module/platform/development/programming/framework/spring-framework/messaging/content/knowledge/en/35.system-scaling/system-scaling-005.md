# Scaling JMS Consumers and Processing Order Trade-Offs in Spring

## Objectives

A JMS queue can receive messages faster than a single consumer can process them. When a backlog grows, increasing the number of consumers is a common way to utilize more CPUs, I/O, and application instances. However, multiple consumers processing concurrently change the order observed by business logic.

This lesson explains how to scale Spring JMS consumers, how Spring manages concurrency, the limits of scaling, and options when you need both higher throughput and ordering guarantees. The focus is on queues; topics have different semantics and must be handled separately.

Basic flow:

`producer → broker queue → listener container → JMS Session/Consumer → @JmsListener → service/database`

Distinguish three kinds of ordering:

- **Send/broker-arrival order:** the order in which producers send and the broker accepts messages.
- **Delivery/receive order:** the order in which the broker dispatches messages to consumers.
- **Business completion order:** the order in which listeners finish processing and commit side effects.

These three orders can differ. Increasing consumers primarily increases concurrent processing capacity; it does not guarantee business completion order.

## 1. JMS Consumers and Listener Containers in Spring

A JMS consumer receives messages from a destination through a JMS `Session`. Spring manages consumer lifecycles via a listener container, typically `DefaultMessageListenerContainer` (DMLC), and invokes methods annotated with `@JmsListener`.

With Spring Boot, the JMS starter auto-configures `ConnectionFactory`, `JmsTemplate`, and the listener infrastructure. Example:

~~~java
@Component
public class OrderListener {

    @JmsListener(destination = "orders.queue")
    public void receive(OrderEvent event) {
        orderService.process(event);
    }
}
~~~

The listener method is invoked by a listener container thread. When multiple consumers are configured, the container creates multiple independent receiving sessions; listener invocations can execute concurrently on different threads.

Points to remember:

- One consumer processes messages on its own JMS `Session`.
- A JMS `Session` is not thread-safe for concurrent use across multiple threads. Do not share sessions/consumers across application threads.
- Multiple consumers on the same queue compete for messages; the broker distributes work among them.
- Listener container concurrency is the number of active consumers/receiving sessions, not arbitrary worker threads spawned by the listener itself.
- If a listener hands off work to an asynchronous executor and returns immediately, the broker may consider delivery complete before the work actually finishes. This affects acknowledgements, retries, and ordering.

## 2. Configuring Concurrency with Spring Boot

In modern Spring Boot, you can configure the minimum and maximum number of consumers in `application.yml`:

~~~yaml
spring:
  jms:
    listener:
      min-concurrency: 3
      max-concurrency: 10
~~~

This allows the listener container to maintain a minimum of three consumers and scale up to a maximum of ten consumers as load increases. When load drops, DMLC can scale consumers back down toward the baseline.

Current properties:

| Property | Meaning |
| --- | --- |
| `spring.jms.listener.min-concurrency` | Minimum number of consumers |
| `spring.jms.listener.max-concurrency` | Maximum number of consumers |
| `spring.jms.listener.auto-startup` | Whether to automatically start the listener container |
| `spring.jms.listener.receive-timeout` | Wait time for receiving a message between polls |
| `spring.jms.listener.session.transacted` | Whether to use JMS `Session` transactions |

In Spring Boot 3.x and 4.x, use `min-concurrency` and `max-concurrency`. Some older Boot versions used `spring.jms.listener.concurrency` for the minimum; check the Common Application Properties for your exact version.

You can set concurrency per endpoint using the attribute on `@JmsListener`:

~~~java
@JmsListener(
        destination = "orders.queue",
        concurrency = "3-10")
public void receive(OrderEvent event) {
    orderService.process(event);
}
~~~

The string `"3-10"` means a baseline of three consumers and a maximum of ten consumers. A single value like `"5"` sets a maximum of five consumers, with a baseline of one in DMLC.

Endpoint-level configuration overrides the factory's default concurrency. Use it when queues have different loads or ordering requirements.

## 3. Configuring via `DefaultJmsListenerContainerFactory`

If you need multiple listener factories with different policies, create separate factories:

~~~java
@Configuration
@EnableJms
public class JmsListenerConfiguration {

    @Bean
    public DefaultJmsListenerContainerFactory scalableQueueFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrency("3-10");
        factory.setSessionTransacted(true);
        return factory;
    }

    @Bean
    public DefaultJmsListenerContainerFactory orderedQueueFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrency("1");
        factory.setSessionTransacted(true);
        return factory;
    }
}
~~~

Specify the factory on each endpoint:

~~~java
@JmsListener(
        destination = "orders.queue",
        containerFactory = "scalableQueueFactory")
public void processInParallel(OrderEvent event) {
    orderService.process(event);
}

@JmsListener(
        destination = "account.events",
        containerFactory = "orderedQueueFactory")
public void processSequentially(AccountEvent event) {
    accountService.apply(event);
}
~~~

These are illustrative configurations. If Spring Boot already created a default factory, you can use `DefaultJmsListenerContainerFactoryConfigurer` to initialize a custom factory with Boot's settings and override only concurrency. Avoid accidentally omitting converters, transaction managers, destination resolvers, or error handlers used by the application.

DMLC maintains the baseline consumer count and can schedule additional consumers when enough messages arrive. Scaling up/down follows the container's mechanics rather than jumping instantaneously per message. Monitor the actual active consumer count; configuring a maximum does not mean all consumers are always created.

## 4. How Does Concurrency Increase Throughput?

Suppose one consumer processes an average of `μ` messages per second and there are `n` active consumers. The approximate theoretical capacity is:

[
Throughput_{max} approx n 	imes mu
]

If each message takes 100 ms on average and one consumer processes sequentially, that consumer's theoretical capacity is about 10 messages/second. Ten consumers can approach 100 messages/second if tasks are independent and the broker, CPU, database, and other dependencies can keep up.

This is only an estimation model. Actual throughput also depends on:

- Processing time and proportion of I/O wait time.
- CPU, heap, garbage collection, and thread count.
- Connection pools, database pools, transaction limits, and lock contention.
- Broker dispatch, persistence, disk I/O, network, and in-flight message count.
- Message size, converters, and serialization/deserialization cost.
- Prefetch or consumer window configured by the JMS provider.
- Retries, redeliveries, transaction commits, and acknowledgements.
- Number of application instances reading from the same queue.

If consumers are CPU-bound, increasing concurrency beyond usable cores may merely increase context switching. If consumers mainly wait on a database or HTTP calls, extra concurrency can hide wait latency, but eventually pushes the bottleneck onto downstream dependencies.

With multiple instances, total consumers equal the sum of concurrency across all instances. For example, three pods with up to eight consumers each can create up to 24 consumers on the queue. Account for this total when sizing database pools, broker sessions, connections, and downstream rate limits.

## 5. Measure Before Scaling Consumers

Do not raise concurrency merely because a queue has a backlog. Measure:

- **Queue depth:** number of waiting messages.
- **Oldest message age:** age of the oldest message; often reflects user-perceived delay better than depth alone.
- **Enqueue/dequeue rate:** rate at which messages enter and leave the queue.
- **Processing duration:** how long the listener takes per message; track p50/p95/p99.
- **In-flight/unacknowledged:** messages dispatched to consumers but not yet completed.
- **Active consumer count:** number of actually active consumers.
- **Redelivery/DLQ:** redelivery counts and messages moved to the dead-letter queue.
- **CPU, heap, threads, DB pool, and downstream latency:** helps pinpoint where the bottleneck sits.

If the arrival rate `λ` exceeds total processing capacity `n × μ` for a sustained period, the backlog will grow. If the backlog grows while consumers have already saturated CPU or the database pool, adding more consumers can make the system slower.

Little's Law provides a useful relationship for a stable system:

[
L = lambda 	imes W
]

Where `L` is the average number of items in the system, `λ` is average throughput, and `W` is the average time an item spends in the system. This formula relates queue depth, throughput, and latency; it does not replace measuring individual layers.

## 6. Why Do Multiple Consumers Break Ordering?

Suppose the broker holds messages in order:

`A1 → A2 → A3 → A4`

With one consumer, the listener can process A1, A2, A3, A4 sequentially. With two consumers, the broker may deliver:

- Consumer 1: A1, A3
- Consumer 2: A2, A4

Consumer 2 may finish A2 before consumer 1 finishes A1. Or A3 may finish before A2 if processing times vary. Thus, completion order can become A2, A1, A4, A3 even though the broker dispatched messages in sequence.

Spring Framework explicitly notes that registering multiple concurrent consumers on a queue forfeits ordering guarantees. For queues requiring order, keep a single consumer or use an appropriate grouping/partitioning mechanism.

There are many sources of reordering:

1. Multiple consumers receiving messages concurrently.
2. Listeners invoking an async executor without waiting for completion.
3. Messages having varying processing times.
4. Retries/redeliveries causing a failed message to return behind later messages.
5. Priorities, scheduled delivery, expiration, or selectors affecting dispatch order.
6. Multiple concurrent producers; global business order does not appear automatically just from using one queue.
7. Consumers committing side effects in a different order than receipt order.

Therefore, "broker delivers in order" does not mean "business logic completes in order."

## 7. When Should You Keep a Single Consumer?

Use concurrency of one when a queue requires strict sequential processing:

~~~java
@JmsListener(
        destination = "payments.ordered",
        concurrency = "1")
public void process(PaymentCommand command) {
    paymentService.apply(command);
}
~~~

This approach fits when:

- Every message in the queue must be processed sequentially.
- Traffic is low and backlog is negligible.
- Operations have tight state dependencies.
- The domain has no clear partition key yet.
- Simplicity and predictability matter more than maximum throughput.

The limitation is that only one message is processed at a time on that listener. When one message takes a long time or is retried, subsequent messages must wait. A poison message can stall the queue if policy keeps redelivering it at the head of the stream.

A single consumer also preserves order only within what the broker and producers guarantee. If multiple producers send related messages concurrently, add a business sequence/version instead of assuming a single global order.

## 8. Increasing Concurrency While Preserving Business Order with `JMSXGroupID`

Many systems do not need global ordering. They only need messages for the same entity to be processed sequentially, such as:

- Changes to the same order.
- Transactions on the same account.
- Events for the same customer.
- Commands for the same device or aggregate.

Apache ActiveMQ Artemis supports message grouping via the JMS property `JMSXGroupID`. The broker pins messages with the same group ID to the same consumer. Different groups can be distributed across different consumers.

Example producer attaching the order ID as the group ID:

~~~java
public record OrderEvent(
        String orderId,
        long version,
        String status) {}

@Component
public class OrderPublisher {

    private final JmsTemplate jmsTemplate;

    public OrderPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void publish(OrderEvent event) {
        jmsTemplate.convertAndSend(
                "orders.events",
                event,
                message -> {
                    message.setStringProperty(
                            "JMSXGroupID",
                            event.orderId());

                    message.setLongProperty(
                            "aggregateVersion",
                            event.version());

                    return message;
                });
    }
}
~~~

The listener can use multiple consumers:

~~~java
@Component
public class OrderEventListener {

    private final OrderService orderService;

    public OrderEventListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @JmsListener(
            destination = "orders.events",
            concurrency = "4-16")
    public void receive(OrderEvent event) {
        orderService.applyInOrder(event);
    }
}
~~~

With Artemis, messages sharing the same `JMSXGroupID` are delivered to the same consumer, even when the queue has multiple consumers. That enables sequential processing within each group and parallel processing across groups.

Conditions for this approach to preserve business order:

- Producers must attach the same group ID to every message belonging to the same aggregate.
- Producers must send messages of a group in the correct business sequence.
- Listeners process synchronously until completion; do not return and hand off messages to another executor to run in parallel.
- Transactions/acknowledgements must reflect when business processing completes.
- If multiple producers publish messages for the same group, sequence assignment and order coordination are needed at the producer or domain layer.

`JMSXGroupID` is a broker-dependent capability. Check your provider's documentation before relying on it in production. ActiveMQ Artemis and ActiveMQ Classic both document message grouping, though configuration details and failover behavior can differ.

## 9. Trade-Offs of Message Grouping

Message grouping scales by key, but it does not turn a single group into parallel work:

- All messages in the same group are processed sequentially by one consumer at a time.
- A hot group can become a bottleneck even while other consumers sit idle.
- The number of distinct groups and distribution across groups determine actual parallelism.
- If there is only one group, adding consumers does not increase throughput for that group.
- When the consumer owning a group closes or dies, the broker may reassign the group to another consumer. Verify transactions and redelivery to avoid duplicate side effects.
- If the listener offloads processing to an executor, broker grouping only ensures the consumer receives the messages; it does not ensure asynchronous tasks for that group finish in order.

Artemis also notes that a block of grouped messages at the head of a queue can temporarily reduce concurrent processing of non-grouped messages due to FIFO semantics. If grouped and non-grouped traffic have different characteristics, consider separating them into distinct queues.

Do not choose an overly coarse group ID. For example, using `"orders"` as the group ID for every message turns the entire queue into a single sequential stream. Choose a key aligned with the aggregate you need to protect, such as order ID or account ID.

## 10. Partitioning Queues by Key

If the broker does not support suitable message grouping, you can partition across multiple queues:

1. Create N queues, for example `orders.0` through `orders.7`.
2. Compute the partition from the business key, such as `hash(orderId) % N`.
3. Producers send every message for the same order to the same queue.
4. Each queue has one sequential consumer or a controlled consumer group.
5. Different queues are processed in parallel.

Example:

~~~java
int partitionFor(String orderId, int partitionCount) {
    return Math.floorMod(orderId.hashCode(), partitionCount);
}

void publish(OrderEvent event) {
    int partition = partitionFor(event.orderId(), 8);
    String destination = "orders." + partition;

    jmsTemplate.convertAndSend(destination, event);
}
~~~

Partitioning creates several independent sequential streams. With eight queues and one consumer per queue, up to eight partitions can run concurrently; each order remains in one partition.

Points to watch:

- The same key must always use the same partition function and the same partition count.
- Changing the partition count can route a key to a different queue while older messages are still queued. Plan draining, migration, or versioned partition mappings.
- One partition can run hotter than others.
- Manage retries/DLQ and replay per partition.
- Never send messages for the same aggregate to two different queues concurrently if strict ordering is required.

## 11. Sequence Numbers and Order Checking at the Domain Layer

Even when using a single consumer or message groups, include a business sequence/version to detect duplicate or out-of-order messages.

For example, an aggregate has versions 41, 42, 43. The consumer stores the last processed version:

- Receiving version 42 while at 41: process and update to 42.
- Receiving version 42 again while at 42: detect duplicate and skip per idempotency policy.
- Receiving version 44 while at 42: version 43 is missing; hold, retry, or request replay per policy.
- Receiving version 41 while at 42: stale message; do not reapply side effects.

Pseudocode:

~~~java
@Transactional
public void applyInOrder(OrderEvent event) {
    long currentVersion =
            orderRepository.currentVersion(event.orderId());

    if (event.version() <= currentVersion) {
        return; // duplicate or old event already processed
    }

    if (event.version() != currentVersion + 1) {
        throw new OutOfOrderEventException(
                event.orderId(),
                currentVersion,
                event.version());
    }

    orderRepository.apply(event);
    orderRepository.updateVersion(
            event.orderId(),
            event.version());
}
~~~

This is illustrative logic; retry and transaction behavior must match the broker. If throwing an exception rolls back the message, the broker may continuously redeliver a message whose preceding version is missing. You may need backoff retries, a parking queue, or a mechanism to hold messages awaiting an earlier version.

Sequence numbers protect correctness under reordering; they do not reorder messages automatically. If buffering/resequencing is required, design storage for early arrivals, gap timeouts, and handling when a missing message never arrives.

## 12. Retries, Redeliveries, and Poison Messages

Increasing concurrency complicates ordering investigation when failures occur. A message may fail in consumer A and be redelivered after consumer B has already processed a subsequent message.

Decide explicitly:

- Retry inside the listener or fail so the broker redelivers?
- Are retry counts and backoff capped?
- Once retries are exhausted, where does the message go?
- Must DLQ replay preserve sequence/version?
- Should subsequent messages proceed if an earlier message has not succeeded yet?

With strict ordering, if message version 10 fails and version 11 is processed first, state can become inconsistent. You may need to pause the group/partition, move the failing message to a parking queue, and resume only after fixing or replaying. With Artemis message groups, verify broker behavior on rollback, redelivery, and consumer failover.

Never use infinite retries without backoff. One poison message can create a loop, overload the broker, and stall the group. Design idempotent handlers, cap delivery attempts, use a DLQ, and provide controlled replay tooling.

If a listener writes to a database and acknowledges JMS, choose explicit transaction semantics. A local JMS transaction is not automatically atomic with an independent database transaction. Use JTA/XA only when distributed atomic commit is genuinely needed; in many systems, inbox/outbox and idempotency are a more practical choice.

## 13. Queues and Topics Do Not Scale the Same Way

Queues have competing consumers: multiple consumers read from the same queue, and each message is processed by one consumer according to broker semantics.

Topics use publish/subscribe: each subscription receives a copy of the message. Creating multiple independent subscribers causes every subscriber to receive the message; that is not load-sharing like a queue.

Therefore:

- For queues, increasing concurrent consumers is a standard way to share load.
- For topics, multiple subscriptions normally mean multiple copies to multiple subscribers.
- If load-sharing within a topic subscription is needed, use shared subscriptions only when supported by the JMS provider and configured properly. Verify provider ordering and failover semantics.
- Spring Framework advises against increasing concurrency on topic listeners under standard settings without appropriate vendor-specific setup.

Do not set `spring.jms.pub-sub-domain=true` and raise concurrency as if it were a queue. Explicitly choose queues, topics, durable subscriptions, or shared subscriptions to match requirements.

## 14. Prefetch, In-Flight Messages, and Fairness

A broker can push a batch of messages ahead to each consumer to reduce round trips. Naming and configuration depend on the provider, such as prefetch size in ActiveMQ Classic or consumer window size in Artemis.

Large prefetch can:

- Increase throughput when consumers are fast and steady.
- Cause one consumer to hold many unprocessed messages while other consumers sit idle.
- Create imbalance when message processing times vary widely.
- Slow down shutdown/rebalancing because dispatched messages have not finished yet.
- Affect ordering and latency during retries or consumer failures.

Smaller prefetch can improve fairness and reduce in-flight messages at the cost of higher network/dispatch overhead. There is no single right value for every queue; measure under real workloads and consult broker documentation.

Also monitor session/consumer counts and connections. Adding consumers does not just add threads; it increases resources on both the broker and client sides.

## 15. Safe Process for Scaling Consumers

A practical process:

1. Measure queue depth, oldest age, enqueue/dequeue rate, processing latency, and resource usage.
2. Determine whether the queue requires global order, per-key order, or no order.
3. Start from current concurrency and step up gradually, e.g., 1 → 2 → 4 → 8.
4. After each step, measure throughput, p95/p99 latency, CPU, DB pool, broker resources, and redeliveries.
5. Verify business invariants: no skipped versions, no duplicate side effects, and groups/partitions preserve keys.
6. Set max concurrency based on dependency limits, not just CPU count.
7. Keep the ability to roll back configuration quickly if latency or error rate rises.
8. Test multi-instance scale-out, consumer restarts, broker failover, and DLQ replay.

If the queue uses message groups, track throughput per group or partition to spot hot keys. Overall throughput may look healthy while one specific account/order lags behind.

## 16. Testing Concurrency and Ordering with a Real Broker

Unit tests for a service do not prove broker grouping works. Use integration tests against the real broker used in production to verify:

- Sending multiple messages with the same group ID and sequences 1..N; verify the listener applies them in order.
- Sending messages across multiple groups; verify different groups can be processed concurrently.
- Increasing concurrency and instance counts; verify messages in the same group stay pinned per provider semantics.
- Deliberately slowing down one message; verify subsequent messages in the same group do not overtake it.
- Throwing an exception; verify redelivery, transaction rollback, and impact on subsequent messages.
- Stopping the consumer owning a group; verify another consumer takes over the group without duplicate side effects.
- Sending messages with duplicate, missing, or stale versions; verify idempotency and gap handling.
- Replaying messages from the DLQ; verify ordering and sequence policies.

A simple test can use a `CountDownLatch` to wait for N messages, a thread-safe collection to record receipt order, and assertions after listeners finish. Avoid fixed `Thread.sleep`; use bounded timeouts and condition-based waiting. Use dedicated test queues so leftover messages from previous runs do not interfere.

## 17. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Raising concurrency from 1 to 10 without checking business rules | Messages for the same entity finish out of order | Classify global/per-key/no-order requirements before scaling |
| Using the same group ID for all messages | All messages are serialized onto one consumer | Choose a group key per aggregate |
| Using different group IDs for messages of the same order | One order can run concurrently on multiple consumers | Bind stably by order/account/device ID |
| Listener returns before async task completes | Broker may acknowledge before business work finishes; tasks may run out of order | Wait for completion in the listener or use another durable work mechanism |
| Using multiple topic subscribers to share load | Every subscriber receives a copy | Use a queue or properly configured shared subscription |
| Looking only at queue depth | Missing whether consumers are bottlenecked on the DB | Monitor latency, in-flight count, CPU, and downstream pools |
| Prefetch set too high | One consumer hoards messages while others stay idle | Tune per broker and processing-time distribution |
| Retrying failed messages immediately | Poison message loops infinitely and stalls the group | Backoff, retry cap, DLQ, and replay |
| Changing partition count while messages remain in queues | Same key can land in two partitions | Drain/migrate cleanly and keep versioned mappings |
| Using one consumer while multiple producers lack sequence numbers | No well-defined global business order | Assign per-aggregate sequence numbers and validate versions |

## 18. Deployment Checklist

- [ ] Determined whether the queue needs global order, per-key order, or no order.
- [ ] Measured throughput, latency, queue age, and resources before adding consumers.
- [ ] Chosen min/max concurrency within broker, database, and downstream limits.
- [ ] Calculated total consumers across all application instances.
- [ ] Kept concurrency at 1 for flows requiring strict global sequentiality.
- [ ] Used `JMSXGroupID` or stable partition keys for per-key ordering if supported by the broker.
- [ ] Listeners do not offload work and acknowledge before processing finishes.
- [ ] Sequence/version checks and idempotency exist to catch duplicate or out-of-order events.
- [ ] Retries, redeliveries, DLQ, and replay do not violate business invariants.
- [ ] Prefetch/consumer window has been measured and tuned per provider.
- [ ] Topics/shared subscriptions are configured with the right semantics.
- [ ] Integration tests against a real broker cover concurrency, grouping, failover, and redelivery.
- [ ] Dashboards monitor active consumers, queue age, throughput, processing latency, and DLQ.

## References

- [Spring Framework — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html): `@JmsListener`, listener container factories, and concurrency configuration.
- [Spring Framework — DefaultMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html): concurrent consumers, dynamic scaling, and ordering caveats.
- [Spring Boot — JMS](https://docs.spring.io/spring-boot/reference/messaging/jms.html): JMS auto-configuration, listener factories, and transaction behavior.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): `spring.jms.listener.min-concurrency`, `max-concurrency`, and listener properties.
- [Apache ActiveMQ Artemis — Message Grouping](https://artemis.apache.org/components/artemis/documentation/latest/message-grouping.html): `JMSXGroupID`, consumer pinning, group lifecycle, and trade-offs.
- [Apache ActiveMQ Classic — Message Groups](https://activemq.apache.org/components/classic/documentation/message-groups): sticky load balancing and per-group ordering.
- [Spring Framework — Receiving JMS Messages](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html): listener transactions, rollback, and message acknowledgement.

