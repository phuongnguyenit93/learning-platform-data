# Delivery Mode and Durable Message Persistence Conditions

When a producer sends a message to RabbitMQ, the message can be marked as persistent or transient. Delivery mode is a per-message property that tells RabbitMQ whether the message should be retained across a broker restart or may be discarded when the broker restarts. However, merely setting delivery mode to persistent is not enough to guarantee a message survives a restart. The receiving queue must also be durable, the exchange and binding must be recovered, the message must actually be routed to the queue, and the publisher needs to know to what extent the broker accepted the message.

The Spring Cloud Stream RabbitMQ Binder maps these concepts to producer and consumer configuration. This lesson focuses on durability conditions, how to configure delivery mode, durable subscriptions, publisher confirms, and choosing between classic queues and quorum queues. The goal is to design a path where critical messages do not vanish simply because a consumer app pauses or the broker restarts.

## 1. Delivery Mode Is a Message Property

AMQP 0-9-1 defines delivery modes for messages:

| Delivery mode | AMQP value | Meaning |
|---|---:|---|
| `NON_PERSISTENT` / transient | 1 | Message is not required to survive a broker restart |
| `PERSISTENT` | 2 | Message is marked for durable storage |

Delivery mode resides in message properties. It does not determine whether a queue survives a restart. Queues have their own lifecycle and durability attribute.

For classic queues:

- Persistent messages are retained after a restart if they reside in a durable queue.
- Transient messages may be discarded on broker restart, even if the queue is durable.
- Persistent messages in a non-durable queue also disappear after a restart because the queue itself is deleted.

Therefore, producer and topology must align. You cannot compensate for a temporary queue just by sending persistent messages.

## 2. Durable Queues and Durable Exchanges

RabbitMQ can restore metadata for durable queues and durable exchanges after a node restarts. Queues hold messages; exchanges route messages to queues. Bindings connect exchanges to queues via routing keys or binding rules.

For an event stream that must survive restarts:

1. The exchange must be durable so routing topology is restored.
2. The consumer group queue must be durable so the queue and its backlog survive.
3. The binding between exchange and queue must exist; when both ends are durable, RabbitMQ stores the binding in topology and restores it after restart.
4. Messages sent to classic queues must have persistent delivery mode.
5. The publisher must track publisher confirms to know the broker accepted the message.

A durable exchange is not a message store. If an exchange exists without a matching bound queue, messages have nowhere to be stored. If a queue is durable while messages are transient, messages may be dropped on broker restart.

By default, the RabbitMQ Binder creates a topic exchange for a destination. `exchangeDurable` defaults to `true`; `exchangeAutoDelete` defaults to `true`. If the exchange must remain long-lived even when no queues are bound to it, consider setting `exchange-auto-delete: false`. Durable and auto-delete control two different behaviors: durable governs restarts, whereas auto-delete governs deleting the exchange once the last bound queue is removed.

## 3. Durable Consumer Groups in the RabbitMQ Binder

The RabbitMQ Binder maps a destination to an exchange. For each consumer group, the binder creates a queue and binds it to the exchange. The group queue is where messages are held while consumers are paused.

Example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-in-0:
          destination: orders.events
          group: order-processing
      rabbit:
        bindings:
          orders-in-0:
            consumer:
              durable-subscription: true
              exchange-durable: true
              exchange-auto-delete: false
~~~

In this example, the `order-processing` group causes the binder to create a queue named after the destination and group. `durable-subscription` defaults to `true` and only takes effect when the binding specifies a group. When enabled, the subscription/queue is declared durable so it can survive broker restarts.

If no group is declared, the binder creates an anonymous queue with a random name and auto-delete enabled. This queue suits temporary clients, not consumers that must receive messages published while the application was stopped. Persistent messages sent to an exchange do not automatically create a durable queue to store them.

You can set `durable-subscription: false` for a group if you specifically want a non-durable queue. In that case, do not expect the queue backlog to remain after a broker restart or when the queue is deleted.

## 4. Provisioning Queues Before Consumers Start

An easily overlooked scenario: the producer begins publishing before the consumer group has ever created its queue. If the exchange has no matching bound queue yet, RabbitMQ has nowhere to store messages. Persistent delivery mode does not retain an unrouted message.

Spring Cloud Stream supports `required-groups` on output bindings so the binder provisions queues/bindings for consumer groups that must receive messages, even before consumers are running:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.events
          producer:
            required-groups:
              - order-processing
      rabbit:
        bindings:
          orders-out-0:
            producer:
              delivery-mode: PERSISTENT
              exchange-durable: true
              exchange-auto-delete: false
~~~

With `required-groups`, the binder creates queues and bindings for the listed groups. This helps when producers and consumers deploy independently, or when producers may emit events before the consumer's first run. Queues are provisioned using binder settings; verify the actual queue and durability attributes in the RabbitMQ Management UI.

`required-groups` does not replace `group` on the consumer's input binding. Both sides must use the same group name and destination. If no queue is provisioned or queue bindings do not match, a publisher may send successfully to the exchange while no consumer queue receives the message.

## 5. Configuring Delivery Mode in the Rabbit Binder

The Rabbit binder exposes the producer property `deliveryMode`. The current default is `PERSISTENT`. You can declare it explicitly so the publishing contract is easy to audit:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.events
      rabbit:
        bindings:
          orders-out-0:
            producer:
              delivery-mode: PERSISTENT
~~~

This property sits under `spring.cloud.stream.rabbit.bindings.<bindingName>.producer`. `PERSISTENT` is the right choice for business events that must be retained in durable queues across restarts. Only choose `NON_PERSISTENT` when data can be regenerated or lost without business inconsistency, such as certain short-lived telemetry.

Do not confuse delivery mode with:

- `durableSubscription`: durability of the consumer group queue.
- `exchangeDurable`: durability of the exchange.
- Publisher confirms: confirmation that the broker processed the publish.
- Consumer acknowledgement: confirmation that the application processed the message.

Each mechanism protects a different stage.

## 6. Conditions for Recovering Persistent Messages

For classic queues, the following table summarizes common cases:

| Queue | Message | Outcome after broker restart |
|---|---|---|
| Durable | Persistent | Recovered according to RabbitMQ storage mechanisms |
| Durable | Transient | Message may be discarded on restart |
| Non-durable | Persistent | Queue is deleted; message has nowhere to remain |
| Non-durable | Transient | Neither queue nor message exists after restart |

Conditions also require that the message was actually routed into the queue. If the exchange has no matching binding, the message is not stored in any queue. If the queue has a TTL or length limit, the message may still expire or be dropped by policy before a consumer processes it.

For quorum queues, queues are always durable and data is replicated via Raft. Quorum queues are designed for higher durability and availability than single classic queues. RabbitMQ stores messages in quorum queues on disk regardless of the message's delivery mode; however, the original delivery mode is preserved when a message is dead-lettered to another queue. If the destination DLQ is a classic queue and must retain messages across restarts, ensure messages going to the DLQ are persistent and the DLQ is durable. Producers still need publisher confirms to know the quorum accepted the message; unconfirmed messages may still be in transit or not yet accepted by the leader.

## 7. Publisher Confirms: Knowing the Broker Accepted the Message

Publishing over AMQP is asynchronous. The client writing frames to a socket does not prove the broker received and persisted the message. The network could drop after the broker receives the message but before the confirm reaches the client, or the message may never have reached the broker.

Publisher confirms allow a producer to receive confirmation from the broker:

- `ack`: the broker processed the publish according to the routed queues' semantics.
- `nack`: the broker could not accept the publish.
- If the message is unrouted and the publish is mandatory, the broker may return the message to the client via `basic.return`; returns are sent before the publisher confirm.

For persistent messages routed to a durable classic queue, RabbitMQ sends the publisher confirm after persisting the message to disk via the message store. Writes are batched to reduce I/O overhead, so confirms may exhibit latency. For quorum queues, confirms are sent after quorum replicas accept the message.

A publisher confirm does not mean a consumer processed the message. It only confirms the publish stage to the broker. Consumer acknowledgement is an independent signal at the receive-and-process stage.

## 8. Enabling Publisher Confirms in Spring Cloud Stream

Spring Boot can configure the connection factory to use correlated publisher confirms and publisher returns:

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.events
          producer:
            error-channel-enabled: true
      rabbit:
        bindings:
          orders-out-0:
            producer:
              use-confirm-header: true
~~~

With `use-confirm-header`, the application attaches correlation data to outbound messages and awaits the corresponding confirm result. `publisher-confirm-type: correlated` is required for the connection factory to emit publisher confirms. `publisher-returns: true` enables receiving unrouted messages back when publishing is configured as mandatory on the send path.

Example using `StreamBridge`:

~~~java
import java.util.concurrent.TimeUnit;

import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.support.AmqpHeaders;
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public void publishAndCheck(
        StreamBridge streamBridge,
        OrderCreated event) throws Exception {

    CorrelationData correlation =
        new CorrelationData(event.eventId());

    Message<OrderCreated> message = MessageBuilder
        .withPayload(event)
        .setHeader(AmqpHeaders.PUBLISH_CONFIRM_CORRELATION, correlation)
        .build();

    boolean sent = streamBridge.send("orders-out-0", message);
    if (!sent) {
        throw new IllegalStateException("Output binding did not accept the message");
    }

    var confirm = correlation.getFuture().get(10, TimeUnit.SECONDS);
    if (!confirm.isAck()) {
        throw new IllegalStateException("RabbitMQ did not confirm the publish");
    }
    if (correlation.getReturnedMessage() != null) {
        throw new IllegalStateException("Message was not routed to a queue");
    }
}
~~~

This example illustrates awaiting a correlated confirm result and checking for a returned message. In production applications, handle timeouts, interruptions, nacks, and retries; avoid blocking business threads too long when confirms can be handled asynchronously. Correlation IDs must be unique per in-flight publish awaiting confirmation.

Without returns and the mandatory flag on the send path, a publisher may receive a confirm without knowing the message was not routed to any queue. Confirms and returns answer two different questions: whether the broker processed the publish, and whether the message was routed to a queue. Inspect your actual binder/template configuration to ensure mandatory is enabled when the application needs to detect unroutable messages.

## 9. Publish Retries and Duplication Risk

Suppose the broker received a message, but the connection dropped before the publisher received the confirm. The producer does not know for sure whether the message was saved. If it resends, two copies of the message may appear; if it does not resend, the message could be lost if the broker never received it.

Therefore, publisher confirms are typically combined with retries and consumer idempotency:

- Attach a stable `eventId` to the message.
- If a confirm times out or the connection closes, retry with the same event ID.
- The consumer stores processed event IDs or uses a unique constraint to eliminate duplicates.
- Do not generate a new event ID for the same business operation on each retry.

Publisher confirms reduce the risk of message loss, but do not create end-to-end exactly-once delivery. When a confirm is lost in transit back to the client, resending can create duplicates. Consumers must tolerate redelivery and handle duplicates safely.

## 10. Consumer Acknowledgement Protects the Processing Stage

After a message is delivered to a consumer, the broker needs to know when it can delete the message from the queue. By default, the Rabbit binder uses `acknowledgeMode: AUTO`: the listener container acknowledges the message after the handler completes successfully per container semantics. If processing fails, the binder/broker applies retry, reject, or requeue according to configuration.

Distinction:

| Signal | Who sends? | Stage protected |
|---|---|---|
| Publisher confirm | RabbitMQ to producer | Broker accepted the publish |
| Consumer ack | Consumer/container to RabbitMQ | Application processed the delivery and broker may remove the message |
| Consumer nack/reject | Consumer/container to RabbitMQ | Processing failed; broker may requeue or dead-letter |

If a consumer acks before finishing business side effects, a subsequent process crash can lose work. If a consumer commits to the database but dies before acking, the broker may redeliver and create duplicates. Apply idempotency/inbox for side effects and align acknowledgement with the moment processing is complete.

## 11. Choosing Classic Queues or Quorum Queues

Durable classic queues work well for many straightforward workloads that need to survive restarts of the queue-owning node. However, classic queues do not automatically replicate data across nodes using a quorum model.

Quorum queues are replicated, durable queues that use Raft to maintain copies and elect a leader. In the Rabbit binder, you can configure a group queue to use a quorum queue:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-in-0:
          destination: orders.events
          group: order-processing
      rabbit:
        bindings:
          orders-in-0:
            consumer:
              quorum:
                enabled: true
                initial-group-size: 3
~~~

Quorum queues require a member count suited to the cluster and can continue serving while a majority of replicas remain. Publisher confirms are how producers know the quorum has accepted a message. Quorum queues have higher write latency than a single classic queue due to replication and consensus.

Choose quorum queues when high availability is required and critical data must be replicated. For temporary queues, exclusive queues, or workloads not needing replication, classic queues may be more appropriate. Do not create quorum queues on a cluster with too few nodes or without a sensible replica placement plan.

## 12. Queues, Exchanges, and Bindings Must Share a Consistent Lifecycle

A durable queue does not help if the topology cannot route messages to it. With the Rabbit binder, each destination is typically mapped to a topic exchange; each group's queue is bound to the exchange. Conditions to verify:

- The exchange has the right name and is durable.
- The group queue exists, is durable, and is not an anonymous auto-delete queue.
- The binding uses the right routing key or pattern.
- The producer has permission to publish to the exchange.
- The consumer has permission to read from the queue.
- The queue is not expired or deleted unexpectedly by TTL, auto-delete, or policies.
- If producers may emit before consumers run, `required-groups` provisions the queue.

If relying on pre-existing infrastructure, the binder can disable `declareExchange` or `bindQueue`; operations must then ensure topology is created and bound properly. Never assume binder durability settings can alter an existing queue declared with different arguments without a migration.

## 13. Limitations of Persistent Messages

Persistent does not mean messages are stored forever. Messages can still be removed by:

- Consumer ack after processing.
- Expired message TTL.
- Queue length limit or overflow policy.
- Queue deletion or expiration.
- Separate TTL/overflow policies on a DLQ.
- Administrator purging/deleting the queue.
- Disk alarms, storage failures, or incidents exceeding the queue type's fault tolerance.

Persistent also does not automatically create backup copies. With a classic queue, data resides on the queue-owning node. Surviving node failures requires replicated queues, such as quorum queues, on a cluster with appropriate replica count and placement.

Do not use RabbitMQ queues as long-term storage or an archive system. If you need to store event history, write to a database, object storage, or an event log suited to your retention period.

## 14. Testing Durability

Tests must verify behavior after restarts and publish failures, not merely that the application boots:

1. Create a durable exchange and a durable consumer group queue.
2. Publish a persistent message and await the publisher confirm.
3. Stop the consumer and verify the message remains in the queue.
4. Restart the RabbitMQ node per your test scenario; verify the durable queue and persistent message are recovered.
5. Repeat with a transient message to verify it is not expected to survive restart.
6. Repeat with a non-durable/anonymous queue and verify the temporary queue is not restored.
7. Publish to an exchange with no queue binding; enable publisher returns/mandatory and verify the producer receives the returned message.
8. Stop the consumer after receiving but before acking; verify the message is redelivered.
9. With a quorum queue, stop one node and verify the queue continues operating while a majority remains.
10. Simulate a disconnect before the confirm reaches the publisher; retry with the same event ID and verify the consumer deduplicates.

The Test Binder is helpful for checking binding configuration and application logic, but it does not prove durability across broker restarts, disk persistence, quorum replication, or publisher confirms. Use a real RabbitMQ broker or Testcontainers for these tests; quorum queues require a multi-node cluster environment.

## 15. Deployment Checklist

- [ ] Producer sends messages with `PERSISTENT` delivery mode for critical data.
- [ ] Consumer group has a stable name; queue is not anonymous auto-delete.
- [ ] `durable-subscription` is enabled for the group queue.
- [ ] Exchange is durable with an appropriate lifecycle; check `exchange-auto-delete`.
- [ ] Bindings and routing keys direct messages into the right queue.
- [ ] Use `required-groups` if queues must be provisioned before consumers start.
- [ ] Publisher confirms are enabled and ack/nack outcomes are handled.
- [ ] Publisher returns/mandatory are enabled when unroutable messages must be detected.
- [ ] Consumer acknowledgement occurs only after business processing finishes.
- [ ] Consumers have idempotency to handle redeliveries or publisher retries.
- [ ] Chosen between durable classic queues and quorum queues based on required fault tolerance.
- [ ] Tested restarts, node failures, unroutable publishes, and redeliveries.

For a message to survive a restart, both a persistent message and a durable queue are needed simultaneously; exchanges and bindings must also be restored so messages go to the right place. The RabbitMQ Binder defaults to sending persistent messages and creating durable subscriptions when a consumer group is configured, yet applications must still verify actual queue/topology settings. Publisher confirms show the broker accepted the message, while consumer acknowledgements confirm processing finished. Combining both signals, the right queue type, and idempotent processing allows applications to build more reliable delivery flows without mistaking a single property for an end-to-end guarantee.

## References

- [Spring Cloud Stream — RabbitMQ Binder Reference Guide](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview.html)
- [RabbitMQ — Queues and Durability](https://www.rabbitmq.com/docs/queues)
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms)
- [RabbitMQ — Quorum Queues](https://www.rabbitmq.com/docs/quorum-queues)
- [Spring AMQP — Publisher Confirms and Returns](https://docs.spring.io/spring-amqp/reference/amqp/template.html)