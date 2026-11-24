# Ordering with Multiple Consumers, Redelivery, or Different Priorities

In JMS, the order in which messages are sent is not synonymous with the order in which processing completes at the consumer. When a queue has multiple consumers, when messages are rolled back and redelivered, or when producers send with different priority levels, the observed order can change.

To design a reliable flow, you need to distinguish three concepts:

- **Delivery/receipt order:** the order in which consumers receive messages.
- **Processing order:** the order in which listeners start processing messages.
- **Completion order:** the order in which business processing finishes.

Jakarta Messaging specifies certain ordering constraints, but does not guarantee a global order across all producers, consumers, and failure situations. Spring JMS also warns that increasing the number of consumers loses ordering guarantees. If the business logic needs sequential processing per order, account, or aggregate, you must choose concurrency, transactions, message grouping, and sequence checks appropriately.

## 1. Basic ordering guarantees of Jakarta Messaging

JMS defines ordering per Session and Destination, not a global ordered queue for every application.

### Send order within the same Session

According to Jakarta Messaging 3.1, messages that **one Session sends to the same Destination** must be received in send order, with some exceptions stated in the specification.

Example of sending from the same Session:

~~~text
Session S1 -> orders.queue:
    M1
    M2
    M3
~~~

When ordering conditions hold, the consumer receives M1 before M2 and then M3. This is a partial ordering constraint: it does not define order across different Destinations or across messages sent from multiple Sessions.

### Multiple Sessions or multiple producers

If two Sessions send to the same queue:

~~~text
Session S1 -> orders.queue: A1, A2
Session S2 -> orders.queue: B1, B2
~~~

JMS does not specify an interleaved total order such as A1, B1, A2, B2. The order depends on send timing, the provider, the broker, and when the messages arrive at the Destination. Each Session has its own order under the JMS rules; the application must not assume that different Sessions form a single shared FIFO sequence.

If business order depends on a single producer, use the same Session for related sends or add an application-level sequence number for the consumer to check.

### Exceptions affecting send order

Even when using the same Session and Destination, the following factors can make the observed order differ from the order of send calls:

1. A message with a higher priority can overtake a lower-priority message sent earlier.
2. A message with a later delivery time is only allowed to appear once its delivery time is reached; other messages may be delivered earlier in the meantime.
3. If PERSISTENT and NON_PERSISTENT are mixed, order is only guaranteed within each delivery mode. A NON_PERSISTENT message sent later may arrive before a PERSISTENT message sent earlier.
4. A provider failure can lose NON_PERSISTENT messages.
5. The send order within a transaction to the same Destination is significant; the send order across multiple Destinations in the same transaction is undefined.

Therefore, when FIFO is needed, you must control Session, Destination, priority, delivery mode, and delivery delay.

## 2. Multiple consumers on the same queue

A queue can have multiple consumers. Each message in the queue is delivered to one consumer; Jakarta Messaging does not specify exactly how the broker must distribute messages among the consumers.

Example:

~~~text
orders.queue
    |
    +---- Consumer A
    |
    +---- Consumer B
    |
    +---- Consumer C
~~~

The broker can distribute messages among the consumers to increase throughput. One consumer may receive M1 and then M3; another consumer receives M2 and then M4. Each consumer has its own receipt order under JMS rules, but there is no global completion order among A, B, and C.

Example:

| Message | Consumer | Processing time | Completion order |
|---|---|---:|---:|
| M1 | A | 900 ms | 2 |
| M2 | B | 100 ms | 1 |
| M3 | A | 200 ms | 3 |

Even though M1 was delivered before M2, B can finish processing M2 before A completes M1. If the two messages update the same order, the completion order can corrupt the business state.

### Receipt order differs from completion order

A Session may only be used sequentially under JMS threading rules. A Session also serializes the invocation of asynchronous listeners attached to that Session. To process concurrently, an application creates multiple Sessions; listeners on different Sessions can run in parallel.

Spring **DefaultMessageListenerContainer** uses separate Sessions and MessageConsumers for listener workers. When concurrency increases, multiple listener methods can process at the same time. Spring explicitly notes that when registering multiple consumers, ordering guarantees are lost.

### Spring JMS: configuring concurrency

With **DefaultJmsListenerContainerFactory**, you can set concurrency:

~~~java
@Configuration
@EnableJms
public class JmsConfiguration {

    @Bean
    public DefaultJmsListenerContainerFactory orderedQueueFactory(
            ConnectionFactory connectionFactory
    ) {
        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);

        // One consumer/session for a queue that needs sequential processing.
        factory.setConcurrency("1");

        // Listener exception rolls back the local JMS transaction.
        factory.setSessionTransacted(true);

        return factory;
    }
}
~~~

A listener using that factory:

~~~java
@Component
public class OrderListener {

    @JmsListener(
            destination = "orders.queue",
            containerFactory = "orderedQueueFactory"
    )
    public void handle(String event) {
        orderService.apply(event);
    }
}
~~~

You can set concurrency directly on **@JmsListener**:

~~~java
@JmsListener(
        destination = "orders.queue",
        concurrency = "1",
        containerFactory = "orderedQueueFactory"
)
public void handle(String event) {
    orderService.apply(event);
}
~~~

**concurrency = "1"** keeps one consumer for the endpoint. A configuration of **"3-10"** allows three to ten consumers depending on the container; this increases parallel processing capacity but no longer guarantees global processing order on the queue.

**Note:** **sessionTransacted=true** creates a local JMS transaction for the Session. It does not automatically put database operations into the same transaction. If the listener updates a database and needs atomicity between the database and acknowledging the message, you must design suitable JTA/XA or transactional outbox.

## 3. Multiple consumers while still needing per-business-entity ordering

An application does not always need a single order for the entire queue. Often only messages belonging to the same aggregate need to be processed sequentially, while different aggregates can run in parallel.

Example:

- Changes for **order-1001** must follow sequence 1, 2, 3.
- Changes for **order-2002** must also follow sequence 1, 2, 3.
- Two different orders can be processed concurrently.

This is a case suited to **message grouping** if the broker supports it.

### JMSXGroupID and JMSXGroupSeq

Jakarta Messaging defines two standard properties:

- **JMSXGroupID**: a String identifying which group the message belongs to.
- **JMSXGroupSeq**: the sequence number of the message within the group; the first value is 1, followed by 2, and so on.

These properties are part of Jakarta Messaging and providers must support them. However, how the broker assigns a group to a consumer, retains the group when a consumer fails, and preserves processing order must be checked against the provider's documentation.

Example of a producer sending the steps of an order:

~~~java
public void publishOrderStep(
        String orderId,
        int sequence,
        String payload
) {
    jmsTemplate.execute("orders.queue", (session, producer) -> {
        TextMessage message = session.createTextMessage(payload);

        message.setStringProperty("JMSXGroupID", orderId);
        message.setIntProperty("JMSXGroupSeq", sequence);

        producer.send(
                message,
                DeliveryMode.PERSISTENT,
                4,
                0L
        );

        return null;
    });
}
~~~

Here:

- **orderId** is the group ID, for example **order-1001**.
- **sequence** is the business sequence number within the group.
- All messages of the same order use the same JMSXGroupID.
- Priority is kept fixed at level 4 to avoid priority changing the order.
- Delivery mode is kept PERSISTENT and no delivery delay is set in the example.

### How do message groups work?

Brokers such as ActiveMQ Artemis and ActiveMQ Classic support message grouping: messages with the same JMSXGroupID are pinned to one consumer while the group remains assigned to that consumer; other groups can be distributed to other consumers.

~~~text
orders.queue
    |
    +---- group order-1001 ----> Consumer A
    |          seq 1
    |          seq 2
    |          seq 3
    |
    +---- group order-2002 ----> Consumer B
               seq 1
               seq 2
               seq 3
~~~

This approach allows parallelism across groups while keeping one processing stream per group according to the mechanism supported by the broker.

Do not infer that merely setting JMSXGroupID will give every broker the same pinning and failover behavior. Verify the provider documentation, group configuration, prefetch policy, consumer failover, and redelivery handling.

### Which aggregate should Group ID represent?

Choose a key shared by the operations that need to be sequential:

| Business case | Suggested Group ID |
|---|---|
| Changes to one order | orderId |
| Transactions on one account | accountId |
| Events from one device | deviceId |
| Changes to one profile | customerId |

Do not use a single group ID for the entire queue if you want to take advantage of multiple consumers; doing so funnels every message into the same group and nearly eliminates concurrency.

Also do not generate a random group ID for each message if the goal is to preserve order per aggregate. Related messages must use the same stable key.

## 4. Application-level sequence numbers

JMSXGroupSeq helps describe order within a group, but the application should have its own business sequence number if strict ordering is an important requirement.

Example payload:

~~~json
{
  "eventId": "evt-901",
  "aggregateId": "order-1001",
  "sequence": 12,
  "eventType": "OrderPaid"
}
~~~

The consumer stores the last sequence applied for the aggregate. When receiving an event:

- **sequence == lastSequence + 1**: can proceed with processing.
- **sequence <= lastSequence**: the event was already processed or is stale; check eventId to distinguish duplicates.
- **sequence > lastSequence + 1**: an earlier event is missing; defer, buffer, or request reconciliation.

Example logic:

~~~java
public void apply(OrderEvent event) {
    long lastSequence = repository.lastAppliedSequence(event.aggregateId());

    if (event.sequence() <= lastSequence) {
        // Duplicate or stale event: do not reapply the side effect.
        return;
    }

    if (event.sequence() != lastSequence + 1) {
        throw new OutOfOrderEventException(
                "Expected " + (lastSequence + 1)
                        + " but received " + event.sequence()
        );
    }

    repository.applyAndAdvanceSequence(event);
}
~~~

**applyAndAdvanceSequence** should update the business data and the sequence in the same database transaction. If multiple consumers can process the same aggregate at the same time, you need row locking, optimistic locking, or an equivalent serialization mechanism to prevent two threads from reading the same lastSequence and then both writing.

A sequence number does not itself sort messages in the broker. It helps detect out-of-order messages and prevents the consumer from silently applying an incorrect state.

## 5. Redelivery: when a message is delivered again

Redelivery occurs when a consumer has received a message but the message has not yet been acknowledged successfully, or the transaction is rolled back/recovered. The broker may deliver the message again for further processing.

Some common causes:

- The listener throws an exception inside a transaction.
- A transacted Session is rolled back.
- The application calls **Session.recover()** in the appropriate acknowledgement mode.
- The process or connection fails before the acknowledgement completes.
- A transaction times out or the broker detects that the consumer lost its connection.

### Redelivery can affect ordering

Suppose a queue has:

~~~text
M1 -> M2 -> M3
~~~

The consumer receives M1 but processing fails. After rollback, M1 is delivered again. In the meantime, there may be a higher-priority message, a message whose delivery time just arrived, or another message delivered to another consumer.

Jakarta Messaging specifies that **Session.recover()** restarts the stream from the first unacknowledged message. However, the messages delivered after recover may differ from the original sequence because messages expired, higher-priority messages arrived, or delayed-delivery messages just became eligible for delivery.

Therefore, do not assume that after redelivery, all messages will reappear in the same sequence order as before the error.

### JMSRedelivered and JMSXDeliveryCount

The consumer can inspect these two pieces of metadata:

- **JMSRedelivered**: boolean indicating the provider is redelivering the message.
- **JMSXDeliveryCount**: the number of times the provider has delivered the message. The first receive has value 1; a value of 2 or more indicates the message has been redelivered.

Example:

~~~java
@JmsListener(destination = "orders.queue")
public void inspect(Message message) throws JMSException {
    boolean redelivered = message.getJMSRedelivered();
    int deliveryCount = message.getIntProperty("JMSXDeliveryCount");

    log.info(
            "messageId={}, redelivered={}, deliveryCount={}",
            message.getJMSMessageID(),
            redelivered,
            deliveryCount
    );
}
~~~

**JMSXDeliveryCount** is useful for observing delivery counts and detecting poison messages, but the provider is not required to guarantee the value is always absolutely accurate after every failure because it does not have to persist this counter. Do not use the delivery count as a unique business identifier.

### Redelivery and acknowledgement modes

| Mode | Behavior related to acknowledgement |
|---|---|
| **AUTO_ACKNOWLEDGE** | The provider acknowledges automatically after receive returns successfully or the listener processes successfully per JMS semantics. |
| **CLIENT_ACKNOWLEDGE** | Calling acknowledge() on one message acknowledges all messages already delivered in that Session. recover() can request redelivery of unacknowledged messages. |
| **Transacted Session** | commit() acknowledges received messages and sends outgoing messages; rollback() recovers incoming messages and cancels outgoing messages in the transaction. |

In Spring **DefaultMessageListenerContainer**, the default **AUTO_ACKNOWLEDGE** mode can acknowledge before the listener runs; an exception from the listener does not trigger redelivery in that default configuration. When you need retry based on listener failure, configure **sessionTransacted=true** or a suitable external transaction manager.

Example of a local JMS transaction factory:

~~~java
@Bean
public DefaultJmsListenerContainerFactory reliableFactory(
        ConnectionFactory connectionFactory
) {
    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setConcurrency("1");
    factory.setSessionTransacted(true);

    return factory;
}
~~~

When the listener throws an exception, the Spring container can roll back the Session transaction. The provider then decides redelivery according to the configured policy. If using a JTA transaction, configure an external transaction manager instead of committing/rolling back the Session yourself.

## 6. Poison messages, retry, and Dead Letter Queues

A message that repeatedly fails can become a **poison message**. For example, JSON with the wrong schema or a business value that always makes the listener throw an exception. If you keep rolling back indefinitely, the message can be delivered over and over and consume resources.

A common policy:

~~~text
Receive
   |
   v
Process
   |
   +---- success ----> Commit / acknowledge
   |
   +---- transient error
   |          |
   |          v
   |      Retry with backoff
   |          |
   |          +---- retry limit reached
   |                       |
   |                       v
   |                 Dead Letter Queue
   |
   +---- permanent error
              |
              v
        Quarantine / DLQ
~~~

Elements to configure:

- Maximum number of redeliveries.
- Wait interval between retries or exponential backoff.
- Target queue for messages that exhaust their retry count.
- How to preserve the original destination, exception cause, and correlation ID.
- How to alert and replay after fixing the error.
- Policy for handling out-of-order messages when an event in a group is moved to the DLQ.

The redelivery limit, delay, dead-letter address, and how order is preserved when moving to the DLQ are provider-dependent features. Jakarta Messaging does not define a uniform DLQ configuration across all brokers.

If you skip a message in a business sequence, subsequent messages may no longer be valid. For example, if event sequence 12 fails and is moved to the DLQ, event sequence 13 should not automatically update state if the application requires a complete sequence. The consumer needs to keep a missing-event state, pause that aggregate, or perform reconciliation.

## 7. Priority: messages with different priority levels

JMS defines the **JMSPriority** header with ten levels:

| Priority | Meaning |
|---:|---|
| 0 | Lowest |
| 1–4 | Normal levels |
| 5–9 | High-priority (expedited) levels |

The default value is usually 4. Jakarta Messaging does not require providers to perform strict priority ordering; the provider should try to deliver expedited messages (5–9) before normal messages (0–4).

This means a high-priority message can overtake a lower-priority message that was sent earlier. Priority is a provider scheduling hint, not a tool to guarantee business order.

### Setting priority on send

With Jakarta Messaging, you can set priority through the **MessageProducer.send(...)** overload:

~~~java
producer.send(
        message,
        DeliveryMode.PERSISTENT,
        8,
        60_000L
);
~~~

Here:

- **PERSISTENT**: delivery mode.
- **8**: high priority.
- **60_000L**: time-to-live of 60 seconds.

Do not set JMSPriority using a setter on Message. The provider assigns this header based on the send parameter or the producer configuration.

With Spring **JmsTemplate**, you can use a ProducerCallback to set custom QoS for each message:

~~~java
jmsTemplate.execute("alerts.queue", (session, producer) -> {
    TextMessage message = session.createTextMessage("Critical alert");
    producer.send(
            message,
            DeliveryMode.PERSISTENT,
            9,
            30_000L
    );
    return null;
});
~~~

If only a single shared priority level is needed, JmsTemplate can also configure delivery mode, priority, and TTL; you must enable explicit QoS so the template passes the configured values.

### How does priority affect FIFO?

Suppose a producer sends to the same queue:

~~~text
M1 priority=4
M2 priority=4
M3 priority=9
M4 priority=4
~~~

The provider may deliver M3 before M1/M2/M4 because M3 belongs to the expedited group. Therefore, if M1–M4 are update steps for the same order and must follow a sequence, do not change priority across steps.

Some systems may use priority to classify SLAs, but if messages need business ordering you should:

- Keep priority uniform within the same aggregate/group.
- Use separate queues for critical and normal flows if the two flows have different SLAs.
- Do not rely on priority to replace sequence numbers.
- Check the actual behavior of the broker under backlog, multiple consumers, and in-flight messages.

Prolonged high-priority traffic can make low-priority messages wait a long time. If fairness or starvation avoidance is needed, you must design queues and scheduling policies suited to the broker.

## 8. Delivery delay, expiration, and delivery mode also affect ordering

Besides priority, three other attributes must be considered at the same time.

### Delivery delay

JMS 2.0 and later allow the producer to specify a delivery delay. A message is not allowed to be delivered before its delivery time.

If M1 is sent first but has a 30-second delay, while M2 is sent later with no delay, M2 can be delivered before M1. When using delay, send order no longer equals receipt order.

### Time-to-live and expiration

A message may expire before the consumer receives it. If sequence 10 expires while sequence 11 is still delivered, the consumer sees a sequence gap. The application needs to detect and handle missing events rather than assuming sequence 11 is valid by default.

### Persistent and non-persistent

Persistent delivery asks the provider to store messages with persistent semantics. Non-persistent messages may be lost if the provider fails.

If you mix the two delivery modes on the same Destination, JMS only guarantees order within each delivery mode. A NON_PERSISTENT message sent later may be delivered before a PERSISTENT message sent earlier. If strict ordering matters, keep the delivery mode consistent.

## 9. Designing for ordering requirements

| Requirement | Design to consider |
|---|---|
| FIFO for the entire queue | One producer Session in order, one consumer/session, same priority, delivery mode, and delivery delay. |
| Per-order ordering while processing many orders in parallel | Message grouping by orderId, a broker supporting group pinning, and a business sequence number. |
| High throughput, order does not matter | Multiple consumers/concurrency, idempotent processing. |
| Prioritizing critical alerts | Priority or a separate queue; do not mix with an event stream requiring strict FIFO. |
| Retrying failed messages | Transacted listener, bounded redelivery policy, backoff, and DLQ. |
| No missing sequence allowed | Business sequence number, persisting the last processed state, and a replay/reconciliation mechanism. |
| Multiple producers sending for the same aggregate | Partition by aggregate or serialize publishing; do not rely on ordering across Sessions. |

### One queue or multiple queues?

If messages belong to independent business flows, splitting queues can help reduce interference between them. Example:

- **orders.critical**: urgent alerts or commands.
- **orders.normal**: regular events.
- **orders.retry**: messages waiting to retry if the broker/provider supports this policy.

Splitting queues lets each flow have its own consumers and QoS, but increases the number of destinations and requires managing order across queues if they have a business relationship. Do not split queues by priority if messages across the two queues still must be processed in the same sequence.

## 10. Combined example: processing per orderId

Suppose a queue processes order events with multiple consumers. Each orderId is a group. The broker supports JMS message grouping and assigns the same group to the same consumer. The consumer uses a transacted Session to roll back on error, while checking the business sequence.

### Producer

~~~java
public void publishOrderStep(
        String orderId,
        int sequence,
        String payload
) {
    jmsTemplate.execute("orders.queue", (session, producer) -> {
        TextMessage message = session.createTextMessage(payload);
        message.setStringProperty("JMSXGroupID", orderId);
        message.setIntProperty("JMSXGroupSeq", sequence);
        message.setStringProperty("eventId", UUID.randomUUID().toString());

        // Keep priority/delivery mode the same within a group.
        producer.send(
                message,
                DeliveryMode.PERSISTENT,
                4,
                0L
        );

        return null;
    });
}
~~~

### Listener

~~~java
@Component
public class OrderEventListener {

    private final OrderService orderService;

    public OrderEventListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @JmsListener(
            destination = "orders.queue",
            containerFactory = "groupedOrderFactory"
    )
    public void receive(TextMessage message) throws JMSException {
        String groupId = message.getStringProperty("JMSXGroupID");
        String eventId = message.getStringProperty("eventId");
        boolean redelivered = message.getJMSRedelivered();
        int deliveryCount = message.getIntProperty("JMSXDeliveryCount");

        orderService.applyInSequence(
                groupId,
                eventId,
                message.getText(),
                redelivered,
                deliveryCount
        );
    }
}
~~~

### Listener container

~~~java
@Bean
public DefaultJmsListenerContainerFactory groupedOrderFactory(
        ConnectionFactory connectionFactory
) {
    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);

    // Allow multiple groups to be processed in parallel.
    factory.setConcurrency("4-12");

    // Listener exception rolls back the message transaction.
    factory.setSessionTransacted(true);

    return factory;
}
~~~

In the example, the broker can distribute different groups to multiple consumers, while events within one group are processed according to the provider's grouping semantics. **orderService.applyInSequence(...)** must perform the sequence check and data update atomically in the database.

This is Spring JMS integration code that needs a ConnectionFactory, a broker, a queue, and a suitable JSON converter if the payload is JSON. There is no fixed stdout because the order and outcome depend on the actual messages, consumers, and provider. If the broker does not support the desired grouping semantics, do not use this concurrency configuration as a FIFO guarantee; partition the queue or serialize processing per aggregate.

## 11. Idempotency: redelivery must not create repeated side effects

A message can be redelivered after the consumer has performed part of the work but has not yet acknowledged or committed. If the consumer is not idempotent, the same business operation may run twice.

Do not use **JMSMessageID** or **JMSXDeliveryCount** as the unique business key:

- **JMSMessageID** identifies a message assigned by the provider.
- **JMSXDeliveryCount** only reflects the delivery count, not the event identity.
- A stable **eventId** or business key generated by the producer is suitable for deduplicating.

A common pattern is to store eventId in an inbox table with a unique constraint in the same database transaction as the business update. If eventId already exists, the consumer recognizes the duplicate and does not apply the side effect again.

When JMS and the database use two separate transactions, you must clearly design the commit/acknowledge boundary. If atomicity between the database and JMS consumption is required, consider JTA/XA; if not using XA, you need a suitable outbox/inbox, retry, and reconciliation strategy.

## 12. Common mistakes

1. **"A queue always delivers messages in global FIFO."** Incorrect. Ordering is specified per Session/Destination and has exceptions for priority, delivery time, and delivery mode.
2. **"Increasing concurrentConsumers only speeds things up without changing order."** Incorrect. Spring warns that multiple consumers lose ordering guarantees.
3. **"Every consumer receives every message."** Incorrect for a competing queue; each message is delivered to only one consumer.
4. **"Receipt order is completion order."** Incorrect when multiple consumers process in parallel or processing times differ.
5. **"Multiple producers sending to the same queue will have one combined order."** Incorrect. JMS does not define a receipt order across messages sent from multiple Sessions.
6. **"Rollback only resends that exact message and then everything continues in the same order."** Incorrect. Recovery can change the receipt sequence due to new messages, priority, delay, and expiration.
7. **"AUTO_ACKNOWLEDGE always redelivers when a listener throws an exception in Spring DMLC."** Incorrect for the default configuration of DefaultMessageListenerContainer; acknowledgement may happen before listener execution. Use a transacted session or an external transaction manager when reliability is needed.
8. **"JMSXDeliveryCount is the exact count in every situation."** Incorrect. The value may not be absolutely accurate after a provider failure.
9. **"Just setting JMSXGroupID makes every broker guarantee identical group FIFO."** Incorrect. The standard property exists in JMS; how groups are pinned and fail over must be verified per provider.
10. **"Priority 9 is always processed before priority 4 in every situation."** Incorrect. JMS does not require strict priority ordering; the provider only needs to try to prioritize expedited messages.
11. **"Priority can be used to number a sequence."** Incorrect. Priority is a scheduling hint; use a business sequence number to determine order.
12. **"The DLQ automatically preserves the exact business order."** Do not assume this. DLQ routing, retries, and replay depend on the broker; the application must detect missing sequences.
13. **"A redelivered message definitely never ran business logic before."** Incorrect. The consumer may have already performed side effects before failing or losing the acknowledgement; idempotency is needed.
14. **"A Session can be shared across multiple threads to increase throughput."** Incorrect. A JMS Session is designed for sequential use; for concurrency, use multiple Sessions/consumers.

## 13. Key takeaways

- JMS guarantees send order from the same Session to the same Destination within the limits of the specified exceptions.
- Ordering across multiple Sessions, multiple producers, or multiple Destinations is not globally defined.
- A queue can have multiple consumers; how messages are distributed among them is decided by the provider.
- Spring **DefaultMessageListenerContainer** loses ordering guarantees when registering multiple consumers.
- One Session serializes listener execution; multiple Sessions allow parallel processing.
- **JMSXGroupID** and **JMSXGroupSeq** describe group and sequence; check the broker's grouping semantics.
- Rollback/recover can cause messages to be redelivered; **JMSRedelivered** and **JMSXDeliveryCount** help observe redelivery.
- Spring DMLC needs **sessionTransacted=true** or an external transaction manager if you want listener exceptions to lead to rollback/redelivery.
- Priority 0–9 can let higher-priority messages jump ahead; JMS does not require strict priority ordering.
- Delivery delay, expiration, and delivery mode also affect the receipt sequence.
- Use sequence numbers, idempotency, bounded retry, and DLQ/reconciliation to protect business order.

When choosing concurrency, start from the business ordering requirement: queue-wide FIFO needs a single sequential receive stream; per-aggregate ordering can use message grouping and sequences; only when order does not matter should you scale out multiple consumers freely. Do not let priority, redelivery, or retry inadvertently alter business state without the consumer detecting it.

## References

- [Jakarta Messaging 3.1 — Queue semantics and message order](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
- [Spring Framework 6.2 — DefaultMessageListenerContainer API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)
- [Spring Framework 6.2 — JmsListener API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/annotation/JmsListener.html)
- [Spring Framework 6.2 — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html)
- [ActiveMQ Artemis — Message Grouping](https://artemis.apache.org/components/artemis/documentation/latest/message-grouping.html)
- [ActiveMQ Classic — Message Groups](https://activemq.apache.org/components/classic/documentation/message-groups)
