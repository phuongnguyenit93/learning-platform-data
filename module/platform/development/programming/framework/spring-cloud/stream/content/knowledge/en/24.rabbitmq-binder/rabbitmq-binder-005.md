# Durable Queues, Anonymous Groups, and Auto-Delete

In the Spring Cloud Stream RabbitMQ binder, each consumer binding is connected to a queue on RabbitMQ. That queue can be long-lived to retain backlog while the application is stopped, or exist only while an active consumer is running. This choice depends on whether the binding declares a **group**, the **durableSubscription** property, and RabbitMQ's queue lifecycle policies.

Understanding the three concepts **durable**, **anonymous group**, and **auto-delete** helps prevent two common deployment mistakes: using a temporary queue for business events that must survive application downtime, or creating durable queues for temporary consumers and causing the broker to accumulate unused resources.

## 1. The RabbitMQ Binder Maps Destinations to Exchanges and Queues

In the default model, the RabbitMQ binder provisions a topic exchange for the destination. When a consumer binding is present, the binder creates a queue and binds it to the exchange. The default binding routing key for non-partitioned bindings is **#**, so the queue receives all messages routed to that exchange.

The queue name depends on the group configuration:

- With a **group**: the queue has a stable name of the form **prefix + destination + group**.
- Without a **group**: the binder creates an anonymous queue with a random name, defaulting to start with **anonymous.**; this queue is configured as auto-delete.

~~~mermaid
flowchart TD
    P[Producer binding] --> X[(Topic exchange: orders)]
    X --> Q1[Queue: orders.billing]
    X --> Q2[Queue: orders.analytics]
    X --> QA[Anonymous queue: anonymous.UUID]
    Q1 --> C1[Billing consumer instances]
    Q2 --> C2[Analytics consumer instances]
    QA --> CA[Temporary consumer]
~~~

In the diagram, **billing** and **analytics** are two stable groups, so each group gets its own queue. Instances in the same group share their respective queue. An anonymous consumer gets its own queue and does not join the shared queue of a named group.

Example configuration for a consumer with a group:

~~~yaml
spring:
  cloud:
    function:
      definition: billingConsumer
    stream:
      bindings:
        billingConsumer-in-0:
          destination: orders
          group: billing
          content-type: application/json
~~~

With an empty default prefix, the queue is provisioned with the name **orders.billing**. Another application with group **analytics** gets queue **orders.analytics**, also bound to the **orders** exchange.

## 2. What Does a Durable Queue Mean?

A queue with the **durable** attribute is recovered by RabbitMQ after a broker restart. Queue metadata such as name, bindings, and configuration is stored durably. A non-durable queue is transient; it is deleted when the node restarts.

In the RabbitMQ binder, named consumer groups configure **durableSubscription**:

| Property | Meaning | Default |
|---|---|---|
| **durableSubscription** | Whether the consumer group's queue/subscription survives a broker restart. | true |
| **exchangeDurable** | Whether the exchange declared by the binder survives a broker restart. | true |
| **exchangeAutoDelete** | Whether the exchange is deleted after the last queue is unbound. | true |

**durableSubscription** only applies when the input binding has a **group**. If no group is declared, the binder uses an anonymous auto-delete queue; setting `durableSubscription` to `true` does not make an anonymous queue durable.

Example explicitly setting a durable queue:

~~~yaml
spring:
  cloud:
    function:
      definition: billingConsumer
    stream:
      bindings:
        billingConsumer-in-0:
          destination: orders
          group: billing
      rabbit:
        bindings:
          billingConsumer-in-0:
            consumer:
              durable-subscription: true
              exchange-durable: true
~~~

This is also the default behavior for a group queue if `durable-subscription` is not overridden. Explicit declaration is useful when you want to make operational requirements clear in configuration.

### A Durable Queue Does Not Mean Every Message Is Retained

Queue durability and message persistence are two separate attributes:

- A durable queue preserves metadata and is restored after restart.
- Persistent messages are marked so RabbitMQ saves them durably and restores them along with the durable queue.
- Transient messages can be discarded when the broker restarts, even if the queue is durable.

The RabbitMQ binder sets the producer's default `deliveryMode` to **PERSISTENT**. You can keep this default or configure it explicitly:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderPublisher-out-0:
          destination: orders
      rabbit:
        bindings:
          orderPublisher-out-0:
            producer:
              delivery-mode: PERSISTENT
~~~

Therefore, for a queue to receive and retain backlog across restarts, you need at least a durable queue and persistent messages. For high data-safety requirements, you must also consider publisher confirms, consumer acknowledgments, queue type, and replication. The durable/persistent properties alone do not create an absolute end-to-end guarantee.

## 3. durableSubscription and group in Spring Cloud Stream

**group** is a general Spring Cloud Stream property, whereas **durableSubscription** is a RabbitMQ binder-specific extension property. The two properties work together as follows:

| Input binding configuration | Queue outcome |
|---|---|
| With group, durable-subscription true | Stable queue name, durable. |
| With group, durable-subscription false | Stable queue name, non-durable/transient. |
| Without group | Anonymous queue with random name and auto-delete; `durableSubscription` does not apply. |

Example with two consumer instances in the same group:

~~~yaml
spring:
  cloud:
    function:
      definition: billingConsumer
    stream:
      bindings:
        billingConsumer-in-0:
          destination: orders
          group: billing
      rabbit:
        bindings:
          billingConsumer-in-0:
            consumer:
              durable-subscription: true
              max-concurrency: 2
~~~

Instances running the same application with the same **billing** group consume from the **orders.billing** queue. RabbitMQ distributes messages among active consumers on that queue. When one instance stops, unacknowledged messages can be redelivered by the broker mechanism; remaining instances continue receiving messages.

If two applications each need to receive a copy of all events, they must use different groups, such as **billing** and **analytics**. If they use the same group, they load-balance across a single queue rather than each receiving its own copy.

### Why Shouldn't You Change Groups Arbitrarily?

The group name helps determine the queue name. Changing **group: billing** to **group: billing-v2** can cause the binder to create a new queue **orders.billing-v2**. The old queue may still exist and hold unprocessed backlog. Changing a group is therefore a topology and consumption-progress change, not merely a config rename.

Before changing a group, decide how to handle the old queue: keep draining it, move the backlog, replay, archive, or delete it after confirming no needed data remains.

## 4. Anonymous Groups When No Group Is Declared

When an input binding has no **group**, the RabbitMQ binder creates an anonymous queue with a unique name. By default, the queue name starts with **anonymous.** followed by the Base64 representation of a UUID. You can change the prefix with the **anonymousGroupPrefix** property.

Example:

~~~yaml
spring:
  cloud:
    function:
      definition: liveNotificationConsumer
    stream:
      bindings:
        liveNotificationConsumer-in-0:
          destination: notifications
      rabbit:
        bindings:
          liveNotificationConsumer-in-0:
            consumer:
              anonymous-group-prefix: "live."
~~~

This binding has no group. The binder creates an anonymous queue, such as **live.UUID**, and binds it to the **notifications** exchange. The prefix only makes the queue name easier to identify; it does not create a stable group and does not make the queue durable.

### Behavior When Running Multiple Instances

Suppose three application instances all declare a consumer without a group. Each instance creates its own anonymous queue:

~~~mermaid
flowchart TD
    X[(Exchange notifications)] --> Q1[Queue anonymous A]
    X --> Q2[Queue anonymous B]
    X --> Q3[Queue anonymous C]
    Q1 --> A[Instance A]
    Q2 --> B[Instance B]
    Q3 --> C[Instance C]
~~~

Each queue is bound to the same exchange, so every instance can receive a copy of each message. This is per-queue broadcast behavior. It fits when each instance needs its own temporary stream, such as session-bound connections or experimental consumers.

This behavior differs from three instances sharing the **notifications-service** group: with a group, all three instances share one queue and distribute messages to balance load. Without a group, each instance gets its own queue and can receive the same message; if processing writes business data or sends payments, this can cause duplicate side effects.

### Anonymous Queues Are Not for Long-Term Backlog Storage

Anonymous queues are designed for temporary consumers. When the application stops and the last consumer is cancelled, the auto-delete queue is deleted. Messages remaining in the queue are lost once the queue is deleted.

If the consumer reconnects, the binder creates a new anonymous queue with a different name. The new queue does not automatically recover the old queue's backlog and has no shared cursor/offset to resume from the previous run.

Therefore:

- Use anonymous groups for ephemeral data that only needs to be received while the consumer is active.
- Use stable groups for events that must be retained when the consumer is temporarily stopped.
- Do not use anonymous queues for orders, payments, invoices, or audit events that must be processed after restarts.

## 5. How Does an Auto-Delete Queue Work?

RabbitMQ's **auto-delete** attribute specifies that a queue is deleted when its last consumer is cancelled or disappears, provided the queue previously had at least one consumer. A consumer can disappear because the application cancels the subscription, the channel/connection closes, or the TCP connection is lost.

Key points:

1. Auto-delete does not mean the queue is deleted immediately after all messages are processed.
2. The queue is only auto-deleted when the last consumer leaves.
3. A queue that has never had a consumer will not delete itself solely due to auto-delete.
4. Auto-delete differs from exclusive: an exclusive queue is deleted when the declaring connection closes; an auto-delete queue waits for the last consumer to leave the queue.
5. Auto-delete differs from TTL: TTL is a time-based expiration mechanism.

For an anonymous consumer in the Rabbit binder, the binder creates an auto-delete queue. When the application shuts down gracefully, the consumer is cancelled and the queue is deleted. If the application crashes, RabbitMQ detects that the connection/channel has closed or dropped and handles the queue per auto-delete rules.

### Auto-Delete Queues vs. Exclusive Queues

| Attribute | Auto-delete | Exclusive |
|---|---|---|
| Deletion condition | The last consumer is cancelled or disappears, after the queue has had at least one consumer. | The connection that declared the queue closes or drops. |
| Who can use the queue | Can have multiple consumers, subject to queue and permissions. | Only the connection that declared the queue can use it. |
| Lifespan scope | Tied to the lifecycle of the last consumer. | Tied directly to the declaring connection. |
| Common use case | Temporary queue for active consumers. | Temporary queue dedicated to a single client connection. |

Do not infer that a binder's anonymous queue is exclusive merely because it is auto-delete. These are two distinct attributes in RabbitMQ. When a single-connection queue is required, verify the `exclusive` attribute of the actual topology.

## 6. Auto-Delete Queues vs. TTL and exchangeAutoDelete

The Rabbit binder has several lifecycle properties that are easily confused:

| Property | Applies to | Meaning |
|---|---|---|
| Queue auto-delete | Anonymous queue | Deletes the queue when the last consumer leaves after the queue has had a consumer. |
| **expires** | Group queue declared by binder | Deletes the queue if the queue remains unused for the configured duration. |
| **ttl** | Messages in the queue | Default message time-to-live; expired messages can be dropped or dead-lettered per broker configuration. |
| **exchangeAutoDelete** | Exchange | Deletes the exchange after the last queue is unbound. |
| **exchangeDurable** | Exchange | Keeps the exchange across broker restarts. |
| **durableSubscription** | Group queue | Keeps the queue across broker restarts when enabled. |

Example of a group queue that can be deleted if unused for a period of time:

~~~yaml
spring:
  cloud:
    function:
      definition: archiveConsumer
    stream:
      bindings:
        archiveConsumer-in-0:
          destination: archive-events
          group: temporary-archive-reader
      rabbit:
        bindings:
          archiveConsumer-in-0:
            consumer:
              durable-subscription: true
              expires: 86400000
~~~

**expires** in the example is 24 hours in milliseconds. This is how long the queue can sit unused before the broker deletes it; it is not the expiration time of individual messages. While consumers are actively using the queue, do not treat `expires` as a fixed deletion countdown from creation time.

The **ttl** property has a different meaning:

~~~yaml
spring:
  cloud:
    function:
      definition: notificationsConsumer
    stream:
      bindings:
        notificationsConsumer-in-0:
          destination: notifications
          group: notification-worker
      rabbit:
        bindings:
          notificationsConsumer-in-0:
            consumer:
              ttl: 3600000
~~~

Here, messages in the queue have a one-hour TTL according to queue configuration. A durable queue can still contain expired messages; durability does not prevent TTL or queue length policies from discarding messages.

**exchangeAutoDelete** controls only the exchange and does not delete consumer queues. Example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderPublisher-out-0:
          destination: orders
      rabbit:
        bindings:
          orderPublisher-out-0:
            producer:
              exchange-durable: true
              exchange-auto-delete: true
~~~

When the last queue is removed, the exchange can be deleted according to `exchange-auto-delete`. If the exchange is shared by multiple queues or other applications, evaluate this lifecycle before enabling it.

## 7. Choosing a Queue Model Based on Business Requirements

Not every consumer needs a durable queue. Start with the question: must messages be retained while the consumer is inactive?

| Requirement | Recommended configuration | Reason |
|---|---|---|
| Process orders after application restart | Stable group and `durable-subscription: true` | Queue has a stable name and survives broker restarts. |
| Each business app receives a copy of events | Each app uses a separate group | Each group gets its own queue bound to the exchange. |
| Load-share across multiple instances of the same service | Instances share the same group | Consume from one queue together and distribute messages. |
| Temporary consumer per session or connection | Omit group declaration | Each consumer gets an anonymous auto-delete queue. |
| Group queue not needed across broker restarts | Stable group and `durable-subscription: false` if broker/version permits | Transient queue, though messages are not protected across restarts. |
| Clean up unused group queues | Stable group and `expires` | Queue expires after a period of inactivity. |

For critical business events, the typical choice is a stable group, durable queue, and persistent messages. For ephemeral data such as presence state, live notifications to connected clients, or experimental feeds, an anonymous auto-delete queue can be appropriate.

## 8. Configuring a Durable Queue for a Business Service

Example of an order-processing service that must retain backlog during downtime:

~~~java
import java.util.function.Consumer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderConsumerConfiguration {

    @Bean
    public Consumer<OrderCreated> orderConsumer(
            OrderService orderService) {
        return orderService::handle;
    }
}
~~~

~~~yaml
spring:
  cloud:
    function:
      definition: orderConsumer
    stream:
      bindings:
        orderConsumer-in-0:
          destination: orders
          group: order-processing
          content-type: application/json
      rabbit:
        bindings:
          orderConsumer-in-0:
            consumer:
              durable-subscription: true
              exchange-durable: true
              acknowledge-mode: AUTO
  rabbitmq:
    host: rabbitmq.internal
    port: 5672
~~~

Producer sending persistent messages:

~~~yaml
spring:
  cloud:
    function:
      definition: orderPublisher
    stream:
      bindings:
        orderPublisher-out-0:
          destination: orders
          content-type: application/json
      rabbit:
        bindings:
          orderPublisher-out-0:
            producer:
              delivery-mode: PERSISTENT
              exchange-durable: true
~~~

In this configuration:

1. Queue **orders.order-processing** has a stable name.
2. `durable-subscription: true` preserves the queue across broker restarts.
3. The producer emits messages with persistent delivery mode.
4. The consumer uses a stable group to resume processing backlog upon restart.
5. `acknowledge-mode: AUTO` lets the container manage ACKs based on message processing outcomes.

A durable queue does not automatically create a standby queue or per-instance message copies. If queue-level fault tolerance is needed, consider quorum queues and RabbitMQ cluster/replication configuration.

## 9. Configuring an Anonymous Consumer for Ephemeral Data

Example of a service delivering status updates to active sessions:

~~~java
import java.util.function.Consumer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class LiveNotificationConfiguration {

    @Bean
    public Consumer<NotificationEvent> liveNotificationConsumer(
            NotificationService service) {
        return service::deliverToConnectedClient;
    }
}
~~~

~~~yaml
spring:
  cloud:
    function:
      definition: liveNotificationConsumer
    stream:
      bindings:
        liveNotificationConsumer-in-0:
          destination: live-notifications
      rabbit:
        bindings:
          liveNotificationConsumer-in-0:
            consumer:
              anonymous-group-prefix: "session."
~~~

No **group** is declared. The binder creates a queue named **session.<unique-id>** and binds it to the **live-notifications** exchange. When the service stops, the auto-delete queue is removed after the last consumer leaves. When the service restarts, a new queue is created.

If two service instances run, each instance gets its own anonymous queue and can receive the same notifications. If the goal is to distribute each notification to one instance in a worker pool, define a stable group instead of omitting it.

## 10. Using Pre-Created Queues

In production environments, the operations team may pre-create exchanges and queues using RabbitMQ definitions, Terraform, Ansible, or management tools. In that case, the binder can be configured not to provision resources automatically:

~~~yaml
spring:
  cloud:
    function:
      definition: legacyOrderConsumer
    stream:
      bindings:
        legacyOrderConsumer-in-0:
          destination: orders-exchange
          group: orders-legacy
      rabbit:
        bindings:
          legacyOrderConsumer-in-0:
            consumer:
              bind-queue: false
              declare-exchange: false
              queue-name-group-only: true
~~~

With **queue-name-group-only: true**, the binder uses the group name as the queue name—**orders-legacy** in this example. **bind-queue: false** and **declare-exchange: false** require the infrastructure to already have the necessary queue/exchange and binding in place.

Before deploying, confirm:

- The queue exists in the correct virtual host.
- The queue has the required durability and queue type.
- The queue is already bound to the exchange with the appropriate routing key.
- The application user has the required read/configure permissions.
- Queue and exchange names match the configuration.

If the queue exists with declaration attributes differing from what the binder requests, RabbitMQ may return **PRECONDITION_FAILED** when the application attempts to redeclare it. Changing durable, auto-delete, exclusive, or queue type is not always an in-place update; it may require creating a new queue, draining backlog, and switching bindings.

## 11. Changing Durability and Cleaning Up Queues Safely

Queues are stateful resources. Changing a group or durability setting can alter where messages are stored.

### Migrating from Anonymous to a Named Group

1. Identify the current anonymous queue and any remaining messages in it.
2. Create a new group with a stable name.
3. Verify the durable queue is provisioned.
4. Configure producers and consumers so messages route to the new queue as planned.
5. Test message reception and backlog processing.
6. Stop the anonymous consumer and confirm the old queue is auto-deleted.

Do not expect backlog in an anonymous queue to transfer automatically to a new group queue. If existing data must be kept, plan to drain or republish before the queue is deleted.

### Migrating from Non-Durable to Durable

1. Create a new queue with a new name or group and `durable-subscription: true`.
2. Ensure producers send persistent messages.
3. Switch routing/bindings as planned so producers write to the new queue.
4. Wait for or drain the remaining backlog in the old queue.
5. Verify the new consumer processes stably.
6. Delete the old queue after confirming no needed data remains.

RabbitMQ checks attribute equivalence when a client redeclares a queue with the same name. If the declarations mismatch, the broker may close the channel with error 406 **PRECONDITION_FAILED**. Do not alter a live queue directly without a data migration plan.

### Cleaning Up Old Queues

Durable group queues can remain after a service is decommissioned. Use `expires`, RabbitMQ policies, or administrative procedures to clean up unused queues. Before deleting, check ready messages, unacknowledged messages, active consumers, DLQs, and audit requirements.

## 12. RabbitMQ Version and Queue Type Notes

RabbitMQ 4.3.0 and later disallow declaring transient non-durable, non-exclusive classic queues by default; this feature has been deprecated and disabled by default. If an application sets `durable-subscription: false` for a named group and the binder creates a non-durable, non-exclusive classic queue, the declaration may be rejected on newer brokers depending on queue type and configuration.

With modern RabbitMQ:

- Prefer durable queues for business flows that must survive restarts.
- Use non-durable exclusive queues for ephemeral data tied to a single connection.
- To clean up idle durable queues, consider queue TTL (`expires`) instead of creating transient non-exclusive queues.
- Quorum queues are durable and replicated; do not use exclusive or transient queues for quorum queues.

The Rabbit binder supports configuring quorum queues for a group:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderConsumer-in-0:
          destination: orders
          group: order-processing
      rabbit:
        bindings:
          orderConsumer-in-0:
            consumer:
              durable-subscription: true
              quorum:
                enabled: true
                initial-group-size: 3
~~~

This example illustrates choosing a quorum queue; the initial group size must fit the node count and RabbitMQ deployment policy. Quorum queues have different replication overhead and operational requirements from classic queues. Do not enable them just to get a durable queue; choose based on fault-tolerance needs and actual infrastructure.

## 13. Testing Durability and Auto-Delete

Function unit tests cannot prove that RabbitMQ declares a queue as durable or auto-delete. Integration tests against a real RabbitMQ broker or test container are required, followed by inspecting queue attributes on the broker.

### Named Durable Group Test Scenario

1. Start RabbitMQ.
2. Start a consumer with group `billing` and `durable-subscription: true`.
3. Verify the `orders.billing` queue exists and is durable.
4. Stop the consumer while keeping the broker running.
5. Send persistent messages to the `orders` exchange.
6. Verify the queue still exists and messages are retained in the backlog.
7. Restart the broker in the test environment.
8. Verify the queue and persistent messages are recovered.
9. Restart the consumer and verify the backlog is processed.

### Anonymous Auto-Delete Test Scenario

1. Start a consumer without a group.
2. Verify the queue has the `anonymous.` prefix or the custom prefix.
3. Send a message while the consumer is active and verify delivery.
4. Stop the consumer or close the connection.
5. Verify the queue is deleted after the last consumer leaves.
6. Restart the application and verify a new queue with a different name is created.
7. Verify messages sent before the new queue existed do not automatically appear in the new queue.

### Test Matrix

| Scenario | Configuration | Expected verification |
|---|---|---|
| Durable group | Named group, `durable-subscription: true` | Queue has a stable name and is durable. |
| Transient group | Named group, `durable-subscription: false` | Queue is non-durable; verify RabbitMQ version compatibility. |
| Anonymous consumer | No group declared | Queue has a random name and auto-delete. |
| Two instances, same group | Same destination and group | Share consumption from the queue; messages are load-balanced. |
| Two anonymous instances | Same destination, no group | Each instance has its own queue and receives copies of messages. |
| Consumer stops | Stop last instance of an anonymous queue | Auto-delete queue is deleted after the consumer leaves. |
| Queue with no consumers yet | Provisioned queue with no consumers yet | Do not assume auto-delete deletes the queue automatically; check TTL/expires if needed. |
| Broker restart | Durable queue and persistent messages | Queue and messages are recovered per broker guarantees. |
| Durable queue, transient messages | Durable queue, non-persistent producer delivery mode | Queue survives, but transient messages may be lost on restart. |
| Queue expiration | Group queue with `expires` | Idle queue is deleted after the configured duration. |
| Message TTL | Consumer queue with `ttl` | Messages expire per TTL without deleting the queue. |
| Queue declaration mismatch | Changing durability/queue type on the same queue name | Catch `PRECONDITION_FAILED` and follow a migration plan. |

### Observing Queues on RabbitMQ

The RabbitMQ Management UI displays queue name, durability, auto-delete, consumers, ready messages, and unacknowledged messages. You can also use the CLI to inspect basic attributes:

~~~bash
rabbitmqctl list_queues name durable auto_delete consumers messages_ready messages_unacknowledged
~~~

When testing an anonymous queue, record the queue name before stopping the application and verify that the queue disappears afterward. When testing a durable queue, confirm the same queue name remains after the consumer stops and after a broker restart.

## 14. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Messages vanish when application restarts | Consumer has no group and uses an anonymous auto-delete queue. | Define a stable group if backlog retention is needed. |
| Queue remains but messages are lost after broker restart | Queue is durable, but messages were published as transient. | Use persistent delivery mode and verify publisher confirms. |
| Every instance processes the same message | No group declared; each instance has its own anonymous queue. | Use the same group if load balancing is desired. |
| Old anonymous queue does not disappear | A consumer is still active or the queue never had a consumer. | Check connections/consumers and use TTL/expires for appropriate resources. |
| Durable queue is not created | `durable-subscription` is set to false or the binder has no group. | Check `group` and `durableSubscription`. |
| Broker reports `PRECONDITION_FAILED` | A queue with the same name already exists with different attributes. | Migrate the queue systematically; do not redeclare with conflicting attributes. |
| Old queues accumulate after service removal | Durable group queues remain in place. | Use `expires`/policies and a resource cleanup process. |
| Changed `anonymousGroupPrefix` but queue still has the old name | The new prefix only applies to queues created after the binding reinitializes. | Inspect existing queues and reinitialize bindings as planned. |
| Confusing `exchangeAutoDelete` with queue auto-delete | The two properties apply to two different resource types. | Check consumer properties and producer/exchange properties separately. |
| `durableSubscription` enabled but no backlog when consumer stops | Producer did not publish to that queue, queue was created after publish, or messages were dropped by TTL/overflow. | Check queue provisioning, `requiredGroups`, routing keys, TTL, and queue limits. |

When investigating, inspect the live queue first: queue name, group, durability, auto-delete, consumer count, and message counts. Then compare against the resolved binding configuration rather than just looking at YAML. Finally, check producer delivery mode, exchange bindings, routing keys, TTL, queue expiration, and broker version.

## 15. Pre-Deployment Checklist

- [ ] Every consumer has an explicit decision between a stable group and an anonymous queue.
- [ ] Critical business flows use stable groups.
- [ ] `durable-subscription` is configured properly and understood to apply only when `group` is declared.
- [ ] Producers send persistent messages if messages must survive broker restarts.
- [ ] Exchange durability is evaluated separately from queue durability.
- [ ] Anonymous queues are used only for ephemeral data where losing backlog on queue deletion is acceptable.
- [ ] Differences between auto-delete, exclusive, `expires`, and `ttl` are understood.
- [ ] `exchange-auto-delete` is not confused with queue auto-delete.
- [ ] Queue names, prefixes, and groups have been verified in the RabbitMQ Management UI.
- [ ] Old queues have a drain, migration, or cleanup procedure before deletion.
- [ ] Queue declarations do not conflict with pre-provisioned resources.
- [ ] Broker restarts, consumer restarts, and multi-instance behavior have been tested.
- [ ] RabbitMQ 4.3+ behavior has been reviewed if using non-durable non-exclusive classic queues.

In the RabbitMQ binder, an input binding with a group typically uses a stably named queue with `durableSubscription` defaulting to `true`; this queue suits business flows that must retain backlog. When no group is declared, the binder creates an anonymous auto-delete queue with a random name; this suits temporary consumers and can be deleted when the last consumer leaves. Queue durability must be paired with persistent messages when data recovery across broker restarts is required. Properly distinguishing queue auto-delete, exclusive, queue expiration, message TTL, and exchange auto-delete helps select the right resource lifecycle and prevent unexpected backlog loss.

## References

- [Spring Cloud Stream — RabbitMQ Consumer Properties](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/rabbitmq-consumer-properties.html)
- [Spring Cloud Stream — Using Existing Queues and Exchanges](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/existing-destinations.html)
- [Spring Cloud Stream — RabbitMQ Producer Properties](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/prod-props.html)
- [RabbitMQ — Queues, Durability and Temporary Queues](https://www.rabbitmq.com/docs/queues)
- [RabbitMQ — Message Persistence](https://www.rabbitmq.com/docs/publishers)
