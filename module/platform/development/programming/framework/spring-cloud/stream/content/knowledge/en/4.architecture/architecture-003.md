# Input Bindings, Output Bindings, and Physical Broker Resources

In Spring Cloud Stream, application processing functions connect to the messaging system through **bindings**. A binding is a logical connection point on the application side; a binder is the integration layer with the broker; and topics, exchanges, queues, or subscriptions are the resources actually managed by the broker. Distinguishing these three layers helps configure data flows accurately and prevents confusing binding names with broker resource names.

The `SPRING_CLOUD_STREAM` module uses the `Supplier`/`Function`/`Consumer` functional model and supports brokers such as Kafka, RabbitMQ, or Pulsar. The same Java function can stay unchanged when switching binders, but how a binding maps to physical resources depends on the broker. This lesson belongs to the **Architecture** chapter, focusing on input bindings, output bindings, destinations, consumer groups, and the corresponding resource topology.

## 1. Three Layers to Distinguish

A message flow typically passes through three layers:

```text
+------------------------ Spring Application ------------------------+
|                                                                    |
|  Supplier / Function / Consumer                                    |
|             |                                                      |
|             v                                                      |
|       Output or input binding                                      |
+-------------|------------------------------------------------------+
              |
              v
        Broker binder
              |
              v
   Physical resources on broker
   Kafka: topic / partition
   RabbitMQ: exchange / queue / binding
   Pulsar: topic / partition / subscription
```

| Component | Role | Example |
|---|---|---|
| Application function | Executes business logic on a payload or message | `validateOrder`, `inventoryProjection` |
| Binding | Logical connection point between a function and a message stream | `validateOrder-in-0`, `validateOrder-out-0` |
| Binder | Translates binding send/receive operations into broker-appropriate operations | Kafka binder, Rabbit binder, Pulsar binder |
| Destination | Logical target name referenced by binding configuration | `orders.placed`, `orders.validated` |
| Physical resource | Object stored, routed, or tracked by the broker | Topic, exchange, queue, subscription |

A binding is not a topic or a queue. It is a connection contract on the application side. A destination is the name configured for the binding; the binder interprets this name according to the broker's model. Consequently, the same `destination: orders.placed` value can map to a Kafka topic, a RabbitMQ exchange, or a Pulsar topic.

## 2. Input Bindings and Output Bindings

Binding direction is defined from the application's perspective:

- **Input binding:** receives messages from the broker and passes them into the processing function.
- **Output binding:** receives results produced by the function and sends messages to the broker.

Spring Cloud Stream's functional model derives binding names from the function bean name and input/output positions:

| Function Type | Message Direction | Default Binding Name |
|---|---|---|
| `Supplier<T>` | Generates messages to send to the broker | `<functionName>-out-0` |
| `Function<T, R>` | Receives messages and emits results | `<functionName>-in-0` and `<functionName>-out-0` |
| `Consumer<T>` | Receives messages for processing | `<functionName>-in-0` |

For example, the `validateOrder` function receives order events and produces validated events. The input binding is `validateOrder-in-0`; the output binding is `validateOrder-out-0`. The `0` suffix is the index of the input or output argument. For functions with multiple inputs or multiple outputs, subsequent indices distinguish each binding.

```java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderPlaced(String orderId, long total) {}

record OrderValidated(String orderId, long total) {}

@Configuration
class OrderFunctions {

    @Bean
    Function<OrderPlaced, OrderValidated> validateOrder() {
        return event -> {
            if (event.orderId() == null || event.orderId().isBlank()) {
                throw new IllegalArgumentException("orderId is required");
            }
            if (event.total() <= 0) {
                throw new IllegalArgumentException("total must be positive");
            }
            return new OrderValidated(event.orderId(), event.total());
        };
    }
}
```

The function can be selected via `spring.cloud.function.definition`. Binding configuration assigns separate destinations for input and output:

```yaml
spring:
  cloud:
    function:
      definition: validateOrder
    stream:
      bindings:
        validateOrder-in-0:
          destination: orders.placed
          group: order-validation
          content-type: application/json
        validateOrder-out-0:
          destination: orders.validated
          content-type: application/json
```

In this example, `validateOrder-in-0` reads from the `orders.placed` destination; `validateOrder-out-0` writes to `orders.validated`. `group` is configured on the input binding because it identifies the consumer group. Output bindings do not need a consumer group.

If using a `Consumer<OrderValidated>` named `inventoryProjection`, the application only has the binding `inventoryProjection-in-0`. If using a `Supplier<Heartbeat>` named `heartbeat`, the application has the binding `heartbeat-out-0`. With a supplier, the framework typically invokes the function via polling; the emission schedule and handling of empty emissions should align with application goals.

## 3. Destinations and Binding Names Serve Different Purposes

A binding name is derived from the function name and processing direction. It is the configuration identifier the application uses to tune a connection point. A destination specifies the target stream or resource that the binding connects to.

For example:

```yaml
spring:
  cloud:
    stream:
      bindings:
        validateOrder-in-0:
          destination: company.sales.order-created.v1
          group: order-validation
        validateOrder-out-0:
          destination: company.sales.order-validated.v1
```

Here, the binding names remain `validateOrder-in-0` and `validateOrder-out-0`; the destination names reflect the organization's topic or exchange naming convention. Destinations can be changed per environment or stream layout without renaming Java beans, as long as the binding configuration references the correct names.

Destinations should follow a consistent naming convention expressing the business domain, event type, and contract version when needed. Avoid overly generic names like `input`, `output`, or `data`, as they are hard to trace when a broker hosts many streams. A single destination may be shared by multiple applications if message contracts and access policies allow.

## 4. What Resources Do Output Bindings Map To?

For an output binding, the application function produces a message and the binder delivers it to the destination. The physical resource depends on the binder:

| Binder | Output Destination Typically Maps To | Message Path |
|---|---|---|
| Kafka | Topic, potentially with multiple partitions | Producer sends records to the topic; key and partitioner determine the partition |
| RabbitMQ | Exchange | Producer publishes messages to the exchange; the exchange routes messages to queues via bindings and routing keys |
| Pulsar | Topic, which may be a partitioned topic | Producer sends messages to the topic; key and producer config influence routing or key ordering |

### Kafka

An output binding with `destination: orders.validated` sends records to the `orders.validated` topic. The topic may consist of multiple partitions for data storage and load distribution. If the producer sets a key such as `orderId`, messages with the same key are typically routed to the same partition according to the active partitioner; this forms the basis for preserving ordering within a partition.

```text
validateOrder-out-0
        |
        v
   Kafka binder
        |
        v
  topic: orders.validated
      |       |       |
   part-0  part-1  part-2
```

### RabbitMQ

An output binding with `destination: orders.validated` typically publishes to the corresponding exchange. An exchange is not a queue; it applies exchange type, routing keys, and queue bindings to decide where messages are delivered.

```text
validateOrder-out-0
        |
        v
   Rabbit binder
        |
        v
 exchange: orders.validated
        |                 |
   routing key       routing key
        |                 |
        v                 v
 queue inventory     queue analytics
```

If no queue is bound appropriately, messages may not reach any consumer, depending on exchange and publisher configuration. Therefore, design exchanges, routing keys, and queue bindings together, and verify the policy for unroutable messages.

### Pulsar

An output binding with `destination: orders.validated` sends messages to the corresponding Pulsar topic. The topic may be partitioned to increase parallel throughput. Consumer subscriptions are created on the receiving side; the producer simply sends to the topic and applies keys or message properties as required for routing.

## 5. What Resources Do Input Bindings Map To?

An input binding reads messages from a destination. The `group` property is critical because it determines how multiple application instances coordinate consumption and how independent groups receive copies of the data stream.

| Binder | Input Destination | Role of `group` |
|---|---|---|
| Kafka | Topic | Acts as consumer group ID; instances in the same group share partitions and coordinate offsets. Other groups can read the topic independently |
| RabbitMQ | Exchange connected by the binder through a queue | Typically identifies the queue dedicated to the consumer group; instances in the same group consume from the shared queue, while other groups have their own queues bound to the exchange |
| Pulsar | Topic | Used by the binder to identify the subscription; consumers in the same subscription coordinate according to the subscription type |

### Kafka: Topic and Consumer Group

With this configuration:

```yaml
spring:
  cloud:
    stream:
      bindings:
        inventoryProjection-in-0:
          destination: orders.validated
          group: inventory-projection
```

The Kafka binder creates a consumer reading the `orders.validated` topic with group ID `inventory-projection`. Kafka tracks offsets by topic, partition, and consumer group. Multiple instances with the same group ID divide assigned partitions among themselves; a single partition within a group is assigned to only one consumer at a time. Another group, such as `analytics-projection`, maintains its own offsets and can independently read the same topic.

```text
                 topic: orders.validated
                    /    |    \
                   /     |     \
                p0      p1      p2
                 \      |      /
                  \     |     /
             group: inventory-projection
                 instance A / B

             group: analytics-projection
                 instance C
```

A Kafka consumer group is a coordination and offset-tracking identifier; it is not a topic or queue that an administrator must pre-create as an independent data resource. If `group` is omitted, the binder typically creates a separate anonymous group identifier for the consumer binding. Offset retention and replay behavior must be considered when restarting the application.

### RabbitMQ: Exchange, Queue, and Group

The Rabbit binder uses an exchange as the destination and a queue as the consumer's receiving point. When a group is specified, the binder typically declares a queue bound to the exchange according to binding settings. Multiple instances in the same group read from the shared queue, distributing messages across instances. Another group has its own queue bound to the same exchange and can receive a copy of the message stream.

```text
                exchange: orders.validated
                      |
              +-------+-------+
              |               |
              v               v
       queue inventory   queue analytics
          group A           group B
          /    \               |
       app 1  app 2          app 3
```

In RabbitMQ, `group` is tied to the receiving queue. If `group` is omitted, the binder may use an anonymous queue with a different lifecycle and durability than a stably named queue. Review `durable`, `exclusive`, `auto-delete`, routing key settings, and resource declaration permissions when deploying.

### Pulsar: Topic and Subscription

Pulsar separates topics from subscriptions. Topics store the message stream; subscriptions hold consumption state such as read positions and consumer dispatch mode. The binder uses `group` to determine the subscription for an input binding. Instances sharing the same subscription participate in a common consumption stream; other subscriptions can read the same topic independently.

Subscription type affects how messages are dispatched:

| Subscription Type | General Coordination Behavior | Common Use Cases |
|---|---|---|
| Exclusive | A single active consumer on the subscription | Simple consumption stream needing one consumer |
| Failover | One active consumer, others on standby to take over | Needs one primary consumer with failover on error |
| Shared | Multiple consumers receive messages concurrently to share load | High throughput without global ordering requirements |
| Key_Shared | Multiple consumers share load by key | Parallel processing across keys while preserving per-key affinity/ordering under compatible configuration |

Subscription name, subscription type, and key ordering must be configured consistently across producer, binder, and consumer. Choosing `Shared` solely to raise throughput may be unsuitable if business logic requires per-order ordering.

## 6. One Destination Can Have Multiple Independent Consumers

An event stream often serves multiple purposes. Once an order is confirmed, the inventory system updates stock, the analytics system updates metrics, and the notification service sends emails. These applications do not need to call each other directly; they can consume the same event stream through separate groups or subscriptions.

```text
Producer: Order Service
          |
          v
    orders.placed
          |
   +------+------+----------------+
   |             |                |
   v             v                v
Inventory     Analytics       Notification
group         group           group
   |             |                |
   v             v                v
Update stock  Update metrics  Send message
```

In Kafka, each group maintains independent offsets. In RabbitMQ, each consumer group typically has its own queue bound to the exchange. In Pulsar, each group corresponds to an independent subscription. The physical representations differ, but the architectural goal is the same: multiple applications can react independently to the same event.

Conversely, multiple instances belonging to the same group typically share load to perform a single processing role. If you want two applications to both receive every message, do not place them in the same shared consumer group.

## 7. Configuring Bindings per Environment

Destination names often differ across local, staging, and production. Configuration can be separated by profiles or environment variables so the same Java function connects to the appropriate resources:

```yaml
spring:
  cloud:
    function:
      definition: validateOrder
    stream:
      bindings:
        validateOrder-in-0:
          destination: ${ORDERS_INPUT_DESTINATION:orders.placed}
          group: ${ORDERS_CONSUMER_GROUP:order-validation}
          content-type: application/json
        validateOrder-out-0:
          destination: ${ORDERS_OUTPUT_DESTINATION:orders.validated}
          content-type: application/json
```

Environment variables allow changing destinations and groups without modifying code. With multiple binders, a binding can specify which binder to use via Spring Cloud Stream configuration; ensure the corresponding binder dependency is present in the application along with appropriate broker connection settings.

Do not put broker addresses, passwords, or tokens directly into committed configuration files. Use environment variables, a secret manager, or the deployment platform's secrets mechanism. Destinations and groups are not credentials, but should still follow naming conventions to avoid connecting to the wrong environment.

## 8. Provisioning and Resource Lifecycle

Binders may support declaring or creating physical resources at application startup. However, auto-creation depends on the binder, version, configuration, and connection account permissions. Some broker environments also disable automatic topic creation or restrict exchange/queue declaration privileges.

Before deployment, determine who is responsible for creating and managing resources:

- **Auto-created by the binder:** convenient for local development or test environments. Understand the resulting names, default attributes, and required permissions.
- **External provisioning:** administrators or infrastructure pipelines create topics, partitions, exchanges, queues, subscriptions, retention, and policies before the application runs. This allows reviewing resource changes and restricting runtime privileges.
- **Hybrid:** the platform provisions core resources; the binder only declares permitted entities or validates configuration upon connecting.

A checklist for each destination:

| Aspect | Questions to Answer |
|---|---|
| Name and namespace | Does it follow environment, business domain, and version conventions? |
| Access control | Where can producers publish? Which resources can consumers read or declare? |
| Capacity and parallelism | How many partitions does Kafka/Pulsar need? How many queues or consumers does RabbitMQ need? |
| Retention | How long are messages retained? Is replay needed after an incident? |
| Durability | Are resources durable/persistent as required? |
| Errors | How are retries, dead-letter exchanges/topics/queues, and replay policies configured? |
| Lifecycle | Who creates, modifies, monitors, and deletes resources? |

Do not delete a topic, queue, or subscription simply because an application instance has stopped. These resources may still hold unconsumed data or offsets required on the next startup. Changing retention, altering partitions, or deleting subscriptions should follow an agreed operational procedure.

## 9. Differences to Preserve in Multi-Broker Designs

Spring Cloud Stream enables applications to share the same functional model, but the abstraction does not make brokers completely identical.

| Aspect | Kafka | RabbitMQ | Pulsar |
|---|---|---|---|
| Output target | Topic | Exchange | Topic |
| Input target | Topic + consumer group | Queue bound to exchange | Topic + subscription |
| Distribution within a group | Partitions divided among consumers | Multiple consumers reading a queue | Determined by subscription type |
| Independent groups | Separate consumer group, separate offsets | Separate queue bound to the exchange | Separate subscription |
| Ordering | Within a single partition | Basic queue delivery order; multiple consumers/requeues may alter completion order | Depends on partitions, subscription type, and key |
| Consumption position tracking | Offsets per group and partition | Queue message/ack state | Subscription cursor |

When switching binders, verify at least the following points:

1. Does the destination map to the right kind of resource?
2. Does `group` carry the intended semantics of load sharing versus receiving a copy?
3. Have routing mechanisms, partition keys, or ordering keys been reconfigured?
4. Do acknowledgment, retry, DLQ, and replay behaviors change?
5. Are resources created with the right permissions, durability, and retention?

If business logic relies on a broker-specific feature, document that dependency explicitly in configuration and runbooks. Do not assume that swapping the binder name is enough to migrate an entire topology.

## 10. End-to-End Flow Example

Suppose an order service receives an order-creation request and publishes `OrderPlaced`. A `validateOrder` function reads the event, validates the data, and emits `OrderValidated`. Two different consumers receive the validated event: one updates inventory, and the other updates analytics.

```text
Order API
   |
   v
orders.placed
   |
   v
validateOrder-in-0
   |
   v
Function validateOrder
   |
   v
validateOrder-out-0
   |
   v
orders.validated
   |                         |
   v                         v
inventory-projection      analytics-projection
   |                         |
   v                         v
Update inventory          Update metrics
```

In a Kafka setup, `orders.placed` and `orders.validated` are topics; `inventory-projection` and `analytics-projection` are two consumer groups with independent offsets. In RabbitMQ, the two groups typically have two separate queues bound to the `orders.validated` exchange. In Pulsar, the two groups create two separate subscriptions on the topic. The same logical diagram is realized with different physical topologies.

Operational checks include verifying that the producer published to the right destination, the binder connected to the right broker, the consumer binding subscribed to the right destination, and consumer groups were created as intended. When only one consumer stops receiving messages, inspect that specific consumer's queue/subscription/group rather than checking only whether the producer succeeded.

## 11. Common Configuration Pitfalls

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Function does not have expected bindings | Function name missing from `spring.cloud.function.definition` or binding name typo | Check the function bean and derived binding names |
| Producer sends but consumer does not receive | Output and input destinations do not match, or RabbitMQ topology lacks matching queue/routing binding | Check destination, exchange, queue, routing key, and publish/consume permissions |
| Only one of two applications receives a message | Both consumers accidentally share the same group/queue/subscription and balance load | Determine whether each application needs an independent group |
| Multiple instances of the same application each receive every message | Each instance uses its own anonymous group or group configuration is inconsistent | Check group ID, queue, or subscription name |
| Kafka consumer does not process in parallel as expected | Fewer partitions than consumers or uneven partition assignment | Check partition count and consumer group assignment |
| RabbitMQ has an exchange but consumer gets no messages | Queue not declared or not bound with the right routing key | Check queue, binding, exchange type, and routing key |
| Pulsar subscription not in expected state | Subscription name or subscription type differs across configs | Check subscription on the topic and binder configuration |
| Application starts but cannot create resources | Broker disables auto-provisioning or account lacks privileges | Check permissions, broker policy, and external provisioning |

When debugging, trace from function to binding, from binding to binder, and then to physical resources. Logging binding names and destinations verifies application configuration; broker admin tools confirm which topics, exchanges, queues, partitions, or subscriptions actually exist.

## 12. Self-Check

- [ ] Can distinguish application functions, bindings, binders, destinations, and physical resources.
- [ ] Can determine the input/output binding names for `Supplier`, `Function`, and `Consumer`.
- [ ] Can explain why a binding name does not have to match the destination name.
- [ ] Can describe how an output binding maps to a Kafka topic, RabbitMQ exchange, or Pulsar topic.
- [ ] Can describe how an input binding pairs with a consumer group, queue, or subscription.
- [ ] Can distinguish a consumer group sharing load from independent groups receiving the same event stream.
- [ ] Know which physical resources require provisioning and monitoring before production deployment.
- [ ] Know to re-verify broker semantics when switching binders.

## Conclusion

A binding is the logical connection point between an application function and a message stream; a destination names the target the binding uses; a binder maps that connection to broker resources. With Kafka, output goes to a topic and input combines a topic with a consumer group. With RabbitMQ, producers publish to an exchange while consumers receive via a queue bound to that exchange. With Pulsar, producers send to a topic and consumers read via a subscription. Understanding this mapping helps configure flows accurately, distribute load properly, build suitable topologies, and operate Spring Cloud Stream safely across multiple brokers.
