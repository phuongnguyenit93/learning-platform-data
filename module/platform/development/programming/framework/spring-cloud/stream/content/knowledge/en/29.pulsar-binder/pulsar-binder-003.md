# Mapping Destination, Group, and Subscription

Spring Cloud Stream provides an abstraction layer for an application to declare where it sends and receives messages. With the Pulsar binder, three concepts must be distinguished: **destination**, **consumer group**, and **subscription**:

- **Destination** identifies the Pulsar topic that a binding reads from or writes to.
- **Group** identifies the logical identity of a group of consumers in Spring Cloud Stream.
- **Subscription** is the cursor and message delivery rules that Pulsar maintains for consumers on a topic.

The Pulsar binder maps an input binding's group to the consumer's subscription identity. Instances of the same application sharing the same group join the same subscription; different groups on the same destination maintain independent backlogs and acknowledgment progress. The Pulsar subscription type determines how consumers within the same subscription split messages.

Confusing these three layers can cause an application to read duplicate data, miss fan-out, fail to scale because the subscription is in `Exclusive` mode, or create a new subscription on every deployment. This lesson explains how they map to one another, how to configure them per binding, and how to verify behavior on the broker.

## 1. Big Picture: Bindings Connect the Application to Pulsar

A binding is the connection between an application function and a middleware destination. The function does not need to know how Pulsar manages brokers, topics, or subscriptions; the binder handles the wiring.

~~~text
Spring Cloud Stream application
+-----------------------------------------------+
| Function: processOrder                       |
|                                               |
| processOrder-in-0  <--- input binding         |
| processOrder-out-0 ---> output binding        |
+-------------------------|---------------------+
                          |
                          | Pulsar binder
                          v
                 Apache Pulsar cluster
                 +---------------------+
                 | Topic: orders       |
                 |                     |
                 | Subscription:      |
                 | order-projection    |
                 |                     |
                 | Consumer instances  |
                 +---------------------+
~~~

The three configuration layers have distinct meanings:

| Component | Spring Cloud Stream configuration | Pulsar object |
|---|---|---|
| Destination | `bindings.<binding>.destination` | Topic |
| Group | `bindings.<input-binding>.group` | Consumer subscription identity |
| Subscription type | Pulsar extended consumer properties | Exclusive, Shared, Failover, or Key_Shared |
| Subscription mode | Pulsar extended consumer properties | Durable or NonDurable |
| Partition count | Pulsar binder producer/consumer properties | Number of topic partitions |

A topic can have multiple subscriptions. Each subscription has a name and its own delivery mode. A subscription can have multiple consumers depending on the subscription type.

## 2. Destination Maps to a Pulsar Topic

In Spring Cloud Stream, a destination is the target name of a binding. With Pulsar, the destination is used as the topic name that a producer publishes to or a consumer subscribes to.

A full Pulsar topic name has the structure:

~~~text
{persistent|non-persistent}://tenant/namespace/topic
~~~

Examples:

~~~text
persistent://acme/orders/orders-created
persistent://acme/orders/orders-approved
non-persistent://acme/telemetry/device-heartbeat
~~~

Components:

| Component | Meaning |
|---|---|
| `persistent` | Messages are stored durably in Pulsar storage |
| `non-persistent` | Messages exist only in memory while being delivered to consumers |
| `tenant` | Administrative and multi-tenancy boundary |
| `namespace` | Group of topics sharing management, retention, and configuration policies |
| `topic` | Specific message stream name |

For business data that needs recovery after broker restarts or consumer disconnects, persistent topics are typically used. Non-persistent topics are suitable only when the application can tolerate losing in-flight messages if a broker or subscriber fails.

Use full topic names in production configuration to avoid depending on the client's default tenant/namespace. The topic name is also the contract between producer and consumer: two bindings that want to exchange the same data stream must point to the same destination.

## 3. Binding Name Is Not the Destination

Spring Cloud Stream generates default binding names from the function bean name:

- A `Supplier` has an output binding: `<function>-out-0`.
- A `Function` has input and output bindings: `<function>-in-0` and `<function>-out-0`.
- A `Consumer` has only an input binding: `<function>-in-0`.

Example:

~~~java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderConsumer {

    @Bean
    Consumer<OrderCreated> processOrder() {
        return order -> {
            // Process order business logic.
        };
    }

    public record OrderCreated(
        String orderId,
        String customerId,
        long total
    ) {}
}
~~~

The default input binding is `processOrder-in-0`. We can map that binding to a Pulsar topic:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder

    stream:
      bindings:
        processOrder-in-0:
          destination: persistent://acme/orders/orders-created
~~~

Here:

- `processOrder` is the function bean name.
- `processOrder-in-0` is the binding name.
- `persistent://acme/orders/orders-created` is the actual destination/topic.

If no destination is declared, Spring Cloud Stream uses the binding name as the destination name. That default is useful for quick experiments, but in production applications you should explicitly declare the destination so renaming a function does not accidentally change the topic.

With multiple functions in the same application, declare `spring.cloud.function.definition` to activate the exact functions that should run. Binding names remain tied to bean names, while destinations are configured independently.

## 4. Producer and Consumer Can Use the Same Destination

One producer sends messages to a topic; one or more consumer bindings can subscribe to that topic.

~~~yaml
spring:
  cloud:
    function:
      definition: publishOrder;processOrder

    stream:
      bindings:
        publishOrder-out-0:
          destination: persistent://acme/orders/orders-created

        processOrder-in-0:
          destination: persistent://acme/orders/orders-created
          group: order-projection-v1
~~~

A producer does not declare a group because `group` applies only to input bindings. A consumer group does not create a new topic; it creates a subscription identity on the selected topic.

Multiple consumer bindings can point to the same destination while using different groups. In that case, each subscription receives an independent copy of the messages. This is how fan-out across multiple business services is built.

## 5. Consumer Group in Spring Cloud Stream

A consumer group represents a set of instances jointly performing one consumption task. For example, three replicas of an order projection service all belong to the `order-projection-v1` group.

~~~text
Destination: orders-created

Group order-projection-v1
  +-- instance A
  +-- instance B
  +-- instance C

Group billing-v1
  +-- instance D
  +-- instance E
~~~

Within the same group, instances coordinate message consumption according to Pulsar's subscription type. Across different groups, each group tracks its own acknowledgment progress and receives a copy of the message stream.

| Configuration | Outcome |
|---|---|
| Same destination, same group | Same consumption group |
| Same destination, different groups | Each group gets its own copy of the message stream |
| Same group, multiple instances | Instances join the same subscription |
| Different groups, same instance name | Still independent subscriptions |

Example of two services that both need to receive every order:

~~~yaml
spring:
  cloud:
    function:
      definition: projectOrder

    stream:
      bindings:
        projectOrder-in-0:
          destination: persistent://acme/orders/orders-created
          group: order-projection-v1
~~~

The billing service uses the same destination but its own group:

~~~yaml
spring:
  cloud:
    function:
      definition: createInvoice

    stream:
      bindings:
        createInvoice-in-0:
          destination: persistent://acme/orders/orders-created
          group: billing-v1
~~~

As a result, both projection and billing receive the messages. If the two services used the same group, they would split messages between them and one service could miss events it requires.

**Operational rule:** name the group after the logical task, not after a hostname, pod name, or individual instance ID. When scaling from 2 to 5 replicas, keep the group unchanged so all replicas join the same subscription.

## 6. How Are Group and Subscription Name Related?

Pulsar does not use the term "consumer group" like Kafka does. Pulsar uses a subscription name to identify the consumption progress of a group of consumers on a topic.

The Pulsar binder maps Spring Cloud Stream's consumer group to the subscription identity. Therefore, the group must remain stable across restarts and rollouts if the application should resume its existing backlog and acknowledgment state.

You can set the group like this:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: persistent://acme/orders/orders-created
          group: order-projection-v1
~~~

The corresponding subscription name should have a similar meaning to `order-projection-v1`. If you need direct control over the subscription name via native Pulsar consumer properties, the binder supports configuring it at the extended binding level:

~~~yaml
spring:
  cloud:
    stream:
      pulsar:
        bindings:
          processOrder-in-0:
            consumer:
              subscription:
                name: order-projection-v1
                type: Shared
                mode: Durable
~~~

When configuring both `group` and `subscription.name`, use the same value to maintain a consistent logical identity. Avoid setting two different names unless you clearly understand your binder version and configuration precedence order.

If you omit `group`, Spring Cloud Stream treats the consumer as anonymous. An anonymous consumer does not represent a durable group identity that multiple instances can intentionally share. For production consumers that must retain backlog across restarts, declare `group` explicitly.

## 7. Subscription as Pulsar's Cursor and Acknowledgment State

A subscription is consumption state stored by Pulsar for a topic. It tracks which messages have been acknowledged and which messages remain pending.

~~~text
Topic: persistent://acme/orders/orders-created
  message 1
  message 2
  message 3
  message 4
  message 5
       |
       +---- subscription: order-projection-v1
       |       acked: 1, 2, 3
       |       pending: 4, 5
       |
       +---- subscription: billing-v1
               acked: 1, 2
               pending: 3, 4, 5
~~~

Two subscriptions can be at different positions because each service processes at its own pace. A message acknowledged by one subscription does not mean other subscriptions have acknowledged that message.

Pulsar retains unacknowledged messages so they can be redelivered if a consumer fails or disconnects. Messages are deleted according to retention policies and the acknowledgment state of the relevant subscriptions. If a namespace has a retention policy, even acknowledged messages may be retained according to that policy.

Operational actions such as deleting a subscription, skipping backlog, or changing initial position can alter the ability to re-read data. Do not use them as routine cleanup operations without assessing the impact on consumers.

## 8. Pulsar's Four Subscription Types

The subscription name identifies the consumer group; the subscription type determines how the broker distributes messages within that group.

| Type | Consumers in the same subscription | Delivery | Ordering |
|---|---|---|---|
| Exclusive | Only one consumer can connect | One consumer receives all messages | In topic order; per partition for partitioned topics |
| Failover | Multiple consumers connect, one active | Standby consumer takes over when active fails | In order per partition |
| Shared | Multiple active consumers | Broker distributes messages among consumers | No ordering guarantee |
| Key_Shared | Multiple active consumers | Messages with the same key go to the same consumer | Preserves ordering per key |

### Exclusive

`Exclusive` is Pulsar's default subscription type. Only one consumer can attach to the subscription. If multiple replicas attempt to use the same `Exclusive` subscription, additional consumers are rejected.

Use `Exclusive` when there is only one consumer or when the application intentionally wants a single consumer to process the entire subscription. Do not choose `Exclusive` for deployments with multiple replicas that need to process in parallel.

### Failover

`Failover` allows multiple consumers to attach to the same subscription, but at any given time only the active consumer receives messages on a non-partitioned topic. Remaining consumers act as standbys. When the active consumer disconnects, a standby consumer is selected to take over.

With a partitioned topic, each partition has one active consumer. Thus `Failover` can distribute partitions across multiple consumers while still keeping one active consumer per partition.

Use `Failover` when you need standby failover, or when you want to preserve per-partition ordering. It is not the same as `Shared`: standby consumers do not process messages concurrently on a single partition.

### Shared

`Shared` allows multiple consumers to be active simultaneously, with the broker distributing messages among them. This is the right choice for competing consumers needing higher throughput.

`Shared` provides no message ordering guarantee. Two messages with the same key may be delivered to two different consumers and finish processing in a different order. If business logic requires ordering per order, account, or device, consider `Key_Shared` or design key-based serialization.

### Key_Shared

`Key_Shared` allows multiple active consumers while delivering messages with the same key to the same consumer at any given time. This supports parallelism across keys while preserving ordering within each key.

Producers must configure batching appropriately. If default batching packs messages from multiple keys into the same batch, the broker may dispatch the batch in a way that breaks `Key_Shared` semantics. Disable batching or use key-based batching when supported by the producer.

`Key_Shared` requires messages to carry explicit keys. If messages lack keys, default dispatch cannot ensure that the same business entity always routes to the same consumer.

## 9. Choosing a Subscription Type by Business Need

Some common scenarios:

| Requirement | Suitable type | Reason |
|---|---|---|
| Single consumer, no scaling needed | Exclusive | One consumer owns the subscription |
| Multiple replicas, standby only | Failover | Provides backup consumer |
| Multiple replicas processing in parallel, reordering acceptable | Shared | Distributes messages across multiple active consumers |
| Multiple replicas, per-key ordering required | Key_Shared | Same key routes to one consumer |
| Two services both need every event | Two separate subscription names | Each service has its own backlog |

Do not choose `Shared` merely because you want to add replicas. If business logic depends on ordering by customer ID, account ID, or order ID, `Shared` can introduce race conditions when multiple consumers process the same key concurrently.

Likewise, do not choose `Failover` to replace a high-throughput `Shared` subscription. `Failover` favors one active consumer per partition; standbys do not increase processing throughput for that partition.

## 10. Configuring Subscription Type at the Binding Level

Spring Cloud Stream Pulsar binder supports Pulsar consumer properties at the binder level, Spring Boot level, and extended binding level. Extended binding properties have the narrowest scope and highest precedence.

Example using `Shared` for an input binding:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder

    stream:
      bindings:
        processOrder-in-0:
          destination: persistent://acme/orders/orders-created
          group: order-projection-v1

      pulsar:
        bindings:
          processOrder-in-0:
            consumer:
              subscription:
                type: Shared
                mode: Durable
~~~

Configuration paths:

~~~text
spring.cloud.stream.pulsar.bindings.<binding-name>.consumer.subscription.type
spring.cloud.stream.pulsar.bindings.<binding-name>.consumer.subscription.mode
spring.cloud.stream.pulsar.bindings.<binding-name>.consumer.subscription.name
~~~

These native properties are inherited from Spring for Apache Pulsar consumer configuration. Binding-level configuration lets one function use `Shared` while another function in the same application uses `Failover` or `Key_Shared`.

If configured application-wide via `spring.pulsar.consumer...` or `spring.cloud.stream.pulsar.binder.consumer...`, multiple consumer bindings may inherit the same settings. Use extended bindings when functions have different requirements.

## 11. Subscription Mode: Durable vs. NonDurable

Subscription type and subscription mode are two distinct configuration axes.

- **Type** determines which consumer receives a message.
- **Mode** determines whether the subscription cursor is stored durably.

`Durable` is the default subscription mode. It persists the cursor durably; when a consumer disconnects or a broker restarts, acknowledgment state and read position are recovered. A consumer reconnecting with the same subscription name can resume from the acknowledged position.

A `NonDurable` subscription uses a non-persistent cursor. If the broker stops, the cursor is not recovered and the consumer cannot resume from its previous position. Use this only for temporary streams that can tolerate losing reading progress; for business consumers that must retain backlog across restarts, choose `Durable`.

Spring for Apache Pulsar typically configures subscription mode via `spring.pulsar.consumer.subscription.mode`; with the binder, it can be set on the extended binding:

~~~yaml
spring:
  cloud:
    stream:
      pulsar:
        bindings:
          processOrder-in-0:
            consumer:
              subscription:
                mode: Durable
                type: Shared
                initial-position: Earliest
~~~

In production, explicitly decide the initial position for new subscriptions. An existing subscription already has its own cursor; changing `initial-position` does not rewind an existing cursor.

## 12. Initial Position: Earliest vs. Latest

When Pulsar creates a new subscription, initial position determines where reading the backlog begins.

| Initial position | Behavior |
|---|---|
| Earliest | Starts from the oldest retained message |
| Latest | Starts from new messages published after the subscription is created |

Configuration example:

~~~yaml
spring:
  cloud:
    stream:
      pulsar:
        bindings:
          processOrder-in-0:
            consumer:
              subscription:
                initial-position: Earliest
~~~

Choose `Earliest` when a new consumer needs to process historical data. Choose `Latest` when you only want messages produced from the time the new subscription is created.

Initial position matters only when the subscription has no existing consumption state. If the subscription already exists, Pulsar continues based on its current cursor and acknowledgment state. Replaying requires a controlled reset/seek operation along with an assessment of downstream side effects.

## 13. Destination and Subscription Do Not Replace Each Other

One topic can serve multiple consumer groups. Each group creates its own subscription.

~~~text
persistent://acme/orders/orders-created
                 |
                 +---- order-projection-v1 (Shared)
                 |       +-- replica A
                 |       +-- replica B
                 |
                 +---- billing-v1 (Failover)
                 |       +-- active replica
                 |       +-- standby replica
                 |
                 +---- audit-v1 (Exclusive)
                         +-- audit consumer
~~~

If you change the destination, the consumer switches to another topic. If you change the group, the consumer uses a different subscription identity on the same topic and may re-read backlog according to the new subscription's initial position.

Therefore:
- Changing destination changes the data stream.
- Changing group changes the logical consumer identity.
- Changing subscription type changes how messages are distributed within the group.
- Changing subscription mode changes the lifecycle of subscription state.

Do not change the group just to scale out more pods. Keep the group unchanged and choose an appropriate subscription type. Changing the group creates a different subscription and may cause old data to be re-read.

## 14. Partitioned Topics and Subscriptions

A partitioned topic splits one logical topic into multiple internal partitions. Pulsar distributes partitions across brokers to increase throughput.

~~~text
Topic: orders-created (8 partitions)
  partition-0  partition-1  partition-2  partition-3
  partition-4  partition-5  partition-6  partition-7

Subscription: order-projection-v1
  Shared consumers:
    replica A  <--- messages dispatched by broker
    replica B  <--- messages dispatched by broker
    replica C  <--- messages dispatched by broker
~~~

Partition count and subscription type solve two different problems:

- Partition count determines how the topic is partitioned and parallelized on the broker side.
- Subscription type determines how consumers within the same subscription receive messages.

With `Failover`, each partition has one active consumer; a standby can take over if the active consumer fails. With `Shared`, multiple consumers receive messages from the subscription without ordering guarantees. With `Key_Shared`, messages with the same key are sent to the same consumer according to that subscription type's semantics.

You cannot increase throughput merely by adding replicas if the topic has too few partitions or the subscription type prevents concurrent consumption. Evaluate partition count, routing keys, subscription type, and message processing time together.

## 15. Configuring Partition Count with the Pulsar Binder

The Pulsar binder includes a topic provisioner. When a topic does not yet exist, the binder can create a basic non-partitioned topic. To create a partitioned topic, configure the partition count and appropriate administrative permissions.

There are two scopes:

- Binder level: `spring.cloud.stream.pulsar.binder.partition-count` applies to topics created by the binder.
- Binding level: `spring.cloud.stream.pulsar.bindings.<binding-name>.producer.partition-count` or `consumer.partition-count` for a specific binding.

Example setting partition count for an output binding:

~~~yaml
spring:
  cloud:
    function:
      definition: publishOrder

    stream:
      bindings:
        publishOrder-out-0:
          destination: persistent://acme/orders/orders-created

      pulsar:
        bindings:
          publishOrder-out-0:
            producer:
              partition-count: 8
~~~

The topic provisioner uses the Pulsar administration API. If the cluster does not run at the default address, configure the administration service URL:

~~~yaml
spring:
  pulsar:
    client:
      service-url: pulsar://localhost:6650
    administration:
      service-url: http://localhost:8080
~~~

In production, grant appropriate admin permissions for topic provisioning or pre-create topics via infrastructure workflows. Do not grant broad admin privileges to a service just so it can publish/consume if your organization manages topics centrally.

Increasing partition count is an infrastructure change. Before doing so, evaluate routing keys, per-key ordering, throughput, consumer concurrency, and compatibility with running clients.

## 16. Topic Auto-Creation and Namespaces

Pulsar can automatically create a topic when a client publishes or subscribes to a non-existent topic, if the broker allows auto topic creation. The Pulsar binder also provides a topic provisioner to create required topics.

Auto-created topics are typically non-partitioned. Partitioned topics must be created with the desired partition count through the admin API/provisioner.

A namespace is an important administrative boundary. Policies such as retention, backlog quota, message TTL, replication, and access permissions can be applied at the namespace level. Divide namespaces by domain or environment when operational requirements differ.

Example:

~~~text
tenant: acme
  namespace: orders-dev
    orders-created
    orders-approved
  namespace: orders-prod
    orders-created
    orders-approved
  namespace: billing-prod
    invoice-created
~~~

Do not use the same destination for dev and production if they share a Pulsar cluster without separate namespaces. Also avoid relying on default tenants/namespaces in production when full topic names can be declared.

## 17. One Topic, Multiple Groups: Fan-Out and Competing Consumers

Pulsar supports combining pub-sub and queue semantics.

**Fan-out:** each service uses its own subscription name.

~~~text
Topic orders-created
  |
  +--> order-projection-v1
  |
  +--> billing-v1
  |
  +--> audit-v1
~~~

Each subscription maintains an independent backlog and acknowledgment state. Billing can lag behind projection without blocking projection.

**Competing consumers:** multiple replicas share one subscription name.

~~~text
Topic orders-created
  |
  +--> order-projection-v1
         +--> replica A
         +--> replica B
         +--> replica C
~~~

The broker distributes messages within the subscription according to the selected type. This is the scaling pattern for a consumer application.

Do not create a separate group per pod when pods are supposed to share work on one business stream. Doing so causes every pod to receive a copy of all messages instead of sharing the load.

## 18. Key_Shared, Message Keys, and Ordering

`Key_Shared` is useful when a single order must be processed in order while different orders are still processed in parallel.

Example messages sent by a producer:

~~~text
key=order-1001, event=OrderCreated
key=order-1002, event=OrderCreated
key=order-1001, event=OrderPaid
key=order-1003, event=OrderCreated
key=order-1001, event=OrderShipped
~~~

With `Key_Shared`, messages with key `order-1001` are delivered to the same consumer at any given time. Other keys can be processed on other consumers.

The producer needs to set a stable key:

~~~java
pulsarTemplate.newMessage(orderEvent)
    .withMessageCustomizer(messageBuilder ->
        messageBuilder.key(orderEvent.orderId())
    )
    .send();
~~~

When using `Key_Shared`, the producer must disable batching or use key-based batching. Otherwise, a batch may contain multiple keys and the broker cannot maintain per-key routing as expected.

Ordering guarantees apply only within the scope guaranteed by Pulsar per key/partition. They do not automatically guarantee that database side effects in the application complete in order if the consumer processes asynchronously or dispatches work to other threads. Applications still need idempotency and ordering controls at the business layer.

## 19. Multi-Topic Subscriptions and Multiple Destinations

Pulsar allows a single consumer to subscribe to multiple topics, either via a list of topics or a pattern. A Spring Cloud Stream input binding can also accept multiple destinations depending on binder support.

Example of one binding reading two topics:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrderEvents

    stream:
      bindings:
        processOrderEvents-in-0:
          destination: persistent://acme/orders/orders-created,persistent://acme/orders/orders-cancelled
          group: order-events-v1
~~~

When using multiple topics, verify your binder version and how it passes the destination list to the Pulsar consumer. When using a pattern subscription, topics matched by the regex must reside in the same namespace.

There is no ordering guarantee across different topics. If business ordering is required across multiple event types, consolidate them into the same topic or design timestamps/sequences and a state machine to order them in the application.

## 20. Configuring Subscription Properties at Application and Binding Levels

The Pulsar binder uses Spring for Apache Pulsar to create producers and consumers. Consequently, many Spring Boot Pulsar properties can also be used with the binder.

There are three configuration scopes:

| Scope | Prefix | Affected scope |
|---|---|---|
| Spring Boot Pulsar | `spring.pulsar.consumer...` | Consumers across the entire application |
| Pulsar binder | `spring.cloud.stream.pulsar.binder.consumer...` | Consumers using the binder in the application |
| Extended binding | `spring.cloud.stream.pulsar.bindings.<binding>.consumer...` | One specific input binding |

Binder precedence order:

1. Extended binding properties.
2. Binder properties.
3. Spring Boot properties.

Example of an application with two consumer bindings:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder;processPayment

    stream:
      bindings:
        processOrder-in-0:
          destination: persistent://acme/orders/orders-created
          group: order-projection-v1

        processPayment-in-0:
          destination: persistent://acme/payments/payments-created
          group: payment-projection-v1

      pulsar:
        bindings:
          processOrder-in-0:
            consumer:
              subscription:
                type: Shared
                mode: Durable

          processPayment-in-0:
            consumer:
              subscription:
                type: Failover
                mode: Durable
~~~

The two functions use two different subscription types even though they reside in the same Spring Boot application. Setting the subscription type application-wide would cause both bindings to inherit the same setting and fail to meet their distinct requirements.

## 21. Changing Group or Subscription Type During Deployment

Changing the group is not the same as changing the replica count.

- Keeping the group unchanged: new instances join the existing subscription and resume from its cursor.
- Changing the group: creates a new subscription identity; the new subscription uses its own initial position.
- Changing the subscription type: changes how consumers in the subscription distribute messages.
- Changing the destination: switches to a different topic.

A Pulsar subscription can have only one type at a time. To change the type, stop all consumers currently using that subscription and restart them with the new type. Do not perform a rolling update across replicas to a different type while old replicas remain connected to the same subscription.

Procedure for changing type:

1. Identify the topic and subscription to change.
2. Stop all consumers on the subscription.
3. Verify no active consumers remain.
4. Configure the new type on the extended binding.
5. Start the consumers with the new configuration.
6. Inspect the subscription type and backlog on the broker.
7. Monitor redelivery, ordering, and throughput after the switch.

If blue/green deployment with two parallel groups is needed, use separate subscription names/groups and isolated outputs. Do not change the type mid-flight while two groups share a single subscription.

## 22. Backlog, Acknowledgment, and Subscription Lifecycle

Consumers acknowledge messages after successful processing. Pulsar stores acknowledgment state per subscription. Unacknowledged messages remain in the backlog and can be redelivered when a consumer fails, negatively acknowledges (`nack`), or hits an ack timeout.

Key points to remember:

- Different subscriptions on the same topic have independent backlogs.
- A slow consumer does not move another subscription's cursor backward.
- Durable subscriptions preserve state when consumers disconnect.
- Deleting a subscription can lose that group's cursor/backlog state.
- Namespace retention policies may retain acknowledged messages.
- TTL or backlog quotas can affect unprocessed data.

When an application changes its group, the old subscription may still exist and retain backlog. Only delete the old subscription after confirming no consumer needs the data and deciding how to handle the backlog.

## 23. Inspecting Destination and Subscription on Pulsar

When an application does not receive messages, check in order:

1. Which topic is the producer publishing to?
2. Does the input binding's destination match that exact topic?
3. Are the tenant and namespace correct?
4. Does the consumer group match the expected subscription?
5. Does the subscription already exist?
6. Does the subscription type allow the current number of running replicas?
7. Is the subscription mode `Durable` when backlog must be retained?
8. Is the initial position of a new subscription appropriate?
9. Is the topic partitioned and is the partition count right?
10. Does the consumer have permission to subscribe to the namespace/topic?

The Pulsar Admin API and CLI can inspect topics, subscriptions, and stats. For example, a single topic might show multiple subscriptions such as `order-projection-v1`, `billing-v1`, and `audit-v1`. Inspecting subscriptions helps detect cases where the producer sends to the right topic but the consumer is subscribed under the wrong group.

Do not inspect only Spring Boot logs. Check broker state as well, since subscriptions are state managed by Pulsar.

## 24. Common Mistakes

| Symptom | Possible cause | Resolution |
|---|---|---|
| Consumer receives no messages | Wrong tenant/namespace/topic in destination | Use full topic URI and check the broker |
| Every pod receives a copy of all messages | Each pod uses a separate group | Use the same group across replicas |
| Second consumer fails to start | Subscription is `Exclusive` | Switch to `Shared`, `Key_Shared`, or `Failover` as required |
| No fan-out to second service | Both services use the same group | Assign a distinct group to each logical consumer |
| Messages processed out of order | Using `Shared` when ordering is needed | Choose `Key_Shared` or `Failover` and design keys |
| `Key_Shared` does not preserve per-key routing | Producer batching is not key-based | Disable batching or use key-based batching |
| New consumer skips old backlog | New subscription has initial position `Latest` | Choose `Earliest` if historical data is needed |
| Restart creates a new subscription | Unstable or anonymous group | Configure a durable, stable group |
| Topic has no partitions | Binder created a basic non-partitioned topic | Configure `partition-count` and provisioning permissions |
| Subscription type change rejected | Old consumers are still connected | Stop all consumers before changing |
| Old backlog remains after rollout | Old group still exists | Inspect the old subscription and plan cleanup |
| Two input topics processed out of order | No cross-topic ordering guarantee | Merge streams or order by sequence/event time |

## 25. Testing Destination, Group, and Subscription Mapping

An integration test with a Pulsar broker should verify both the topic name and subscription, not just that the function was invoked.

### Scenario 1: Producer and Consumer on the Same Destination

1. Create an output binding pointing to `persistent://acme/orders/orders-created`.
2. Create an input binding pointing to the same topic.
3. Send an `OrderCreated`.
4. Verify the consumer receives the payload.

### Scenario 2: Two Groups Receiving the Same Message

1. Create consumer group `projection-v1`.
2. Create consumer group `billing-v1`.
3. Publish a message.
4. Verify both subscriptions receive the message.
5. Acknowledge in projection and verify billing still has backlog until it processes the message.

### Scenario 3: Multiple Replicas in the Same Group

1. Run two replicas with the same destination and group.
2. Configure `Shared`.
3. Publish multiple messages.
4. Verify both consumers receive messages from the subscription.
5. Verify total processed message count and check duplicate/idempotency handling.

### Scenario 4: Per-Key Ordering

1. Run two replicas with `Key_Shared`.
2. Publish multiple messages with the same key and multiple different keys.
3. Configure key-based batching or disable batching on the producer.
4. Verify messages with the same key are dispatched in order.
5. Verify different keys can still be processed in parallel.

### Scenario 5: New Subscription and Initial Position

1. Publish several messages before creating the subscription.
2. Create a subscription with `Earliest` and verify backlog is received.
3. Create a new subscription with `Latest`.
4. Verify the `Latest` subscription starts from new messages arriving after creation.
5. Restart the consumer with the same group and verify the existing cursor resumes.

### Scenario 6: Partitioned Topic

1. Provision a topic with the specified partition count.
2. Send messages with stable keys.
3. Run multiple consumers in `Shared` or `Key_Shared`.
4. Verify partition routing, throughput, and per-key ordering.
5. Change the replica count and verify the subscription retains the same identity.

## 26. Hands-On Exercise and Completion Criteria

Build an order processing system with one topic and three consumer applications:

- Topic: `persistent://acme/orders/orders-created`.
- Projection group: `order-projection-v1`.
- Billing group: `billing-v1`.
- Audit group: `audit-v1`.

Steps:

1. Create a `publishOrder` function with output binding `publishOrder-out-0`.
2. Set the full destination for the output binding.
3. Create a `projectOrder` function with input binding `projectOrder-in-0`.
4. Configure group `order-projection-v1` and subscription type `Shared`.
5. Run two replicas of projection in the same group.
6. Create a `createInvoice` function using group `billing-v1`.
7. Create an `auditOrder` function using group `audit-v1`.
8. Publish one message and verify all three groups receive a copy.
9. Publish multiple messages and verify the two projection replicas share the load.
10. Try switching projection to `Key_Shared` and send messages using order ID as the key.
11. Inspect the topic, subscriptions, backlog, and acknowledgments on Pulsar.
12. Restart one replica and verify the subscription resumes from the current cursor.
13. Try changing the group in a test environment and observe the new subscription.
14. Try creating a partitioned topic and measure the effect on throughput.

You have completed this exercise when you can explain how destination differs from binding name; how group maps to subscription identity; what semantics same-group vs. different-group configurations produce; how to choose `Exclusive`, `Failover`, `Shared`, or `Key_Shared` appropriately; and how to configure topic, partition count, subscription mode, and initial position in Spring Cloud Stream Pulsar binder.

## 27. Official References

- [Spring Cloud Stream Binder for Apache Pulsar](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html) — dependency, function binding, destination mapping, native encoding/decoding, extended binding properties, and topic provisioner.
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html) — destination, group, and input binding properties.
- [Spring Boot — Application Properties](https://docs.spring.io/spring-boot/4.1/appendix/application-properties/index.html) — Pulsar consumer subscription name, type, mode, and initial position.
- [Apache Pulsar — Messaging Concepts](https://pulsar.apache.org/docs/concepts-messaging/) — topic URI, tenant, namespace, subscription, partitioned topic, and routing.
- [Apache Pulsar 5.0 — Messaging Concepts](https://pulsar.apache.org/docs/5.0.x/concepts-messaging/) — Durable/NonDurable subscription mode, cursor, topic, and retention.
- [Apache Pulsar — Work with Consumer](https://pulsar.apache.org/docs/client-libraries/consumers/) — subscription types, consumer distribution, ordering, and Key_Shared batching.
- [Spring for Apache Pulsar — Message Consumption](https://docs.spring.io/spring-pulsar/reference/reference/pulsar/message-consumption.html) — subscription name, consumer configuration, and acknowledgment.
