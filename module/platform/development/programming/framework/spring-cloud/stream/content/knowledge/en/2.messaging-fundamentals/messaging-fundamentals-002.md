# Publish-Subscribe Messaging

In an event-driven architecture, a service often needs to notify several different parts of the system when a business event has occurred. For example, after an order is created, the inventory system needs to reserve stock, the payment system needs to prepare a transaction, and the notification system needs to send an email. If the order service called each service directly, it would have to know the list of recipients and how to handle cases where a service is temporarily unavailable.

The **publish-subscribe (pub/sub)** model lets a publisher send a message to a shared destination. The broker accepts the message and distributes it to subscribed groups. The publisher does not need to know how many groups are listening or how many instances each group has.

Spring Cloud Stream provides the programming model and binder integration layer to build pub/sub with Kafka, RabbitMQ, Pulsar, or another suitable binder. This lesson focuses on how messages are published, how groups subscribe to receive messages, and how those relationships are expressed using bindings, destinations, and consumer groups.

## Learning Objectives

After this lesson, you will be able to:

- Explain the roles of publisher, subscriber, broker, destination, and consumer group.
- Distinguish between broadcasting messages to multiple groups and load-sharing among multiple instances in the same group.
- Configure output bindings and input bindings using Spring Cloud Stream's functional model.
- Choose appropriate consumer groups so each service receives an independent event stream.
- Recognize limitations around ordering, retention, acknowledgement, and delivery when using different brokers.

## 1. Scenario: One Event, Multiple Reactions

Suppose the order service publishes an `OrderCreated` event when a new order is confirmed. Different parts of the system need to react to this event:

- The inventory team updates available stock quantities.
- The billing team creates a charge request.
- The notification team sends an email or in-app notification.
- The analytics team records data for reporting.

This is an event describing what happened, not a command telling a specific service to perform work. The order service publishes the event to the `orders` destination. Each business group subscribes to that destination and decides independently how to process it.

~~~mermaid
flowchart LR
    P["Order Service<br/>Publisher"] -->|"OrderCreated"| B[("Broker<br/>destination: orders")]
    B --> G1["Consumer group: inventory"]
    B --> G2["Consumer group: billing"]
    B --> G3["Consumer group: notification"]
    G1 --> I1["Inventory instance A"]
    G1 --> I2["Inventory instance B"]
    G2 --> T1["Billing instance A"]
    G3 --> N1["Notification instance A"]
    G3 --> N2["Notification instance B"]
~~~

All three business groups can receive the `OrderCreated` event. If the inventory group has two instances, those two instances typically share the inventory group's workload; they do not by default receive two separate copies of every event.

This model reduces coupling between services: the publisher only needs to know the event contract and the destination; subscribers can be deployed, scaled, or changed independently; a failing subscriber does not necessarily prevent the publisher from sending events to the broker; and new subscribers can be added without modifying publisher code.

Pub/sub does not automatically solve every delivery concern. Message retention, retry timing, processing acknowledgements, and behavior when a subscriber stops still depend on the broker and binder configuration.

## 2. Components of the Pub/Sub Model

| Component | Role |
|---|---|
| Publisher | Creates and publishes events or messages. |
| Message/Event | The transmitted data, usually representing a business event that occurred. |
| Destination | Logical name of where publishers send and subscribers receive messages. |
| Broker | Intermediary system that accepts, stores, or routes messages. |
| Subscription / consumer group | A group subscribed to a message stream with its own consumption state. |
| Subscriber | Component that processes received messages. |
| Binder | Spring Cloud Stream layer connecting bindings to a specific broker technology. |

In Spring Cloud Stream, a **binding** is the bridge between an application function and the messaging system. An input binding brings messages from the broker into a function; an output binding sends data from a function or application to the broker. Bindings are configured with a destination and consumption properties such as `group`.

Three concepts need to be distinguished:

- **Binding** describes the application's connection point.
- **Destination** identifies the stream or logical address that the binding connects to.
- **Group** identifies a subscriber group with independent consumption progress on that destination.

Multiple bindings can point to the same destination. When they belong to different groups, each group can receive the entire event stream according to the broker's mechanism.

## 3. Fan-Out Across Groups vs. Load Sharing Within a Group

This is the most important distinction when designing pub/sub.

### Different Groups: Each Group Receives the Event Stream

If `inventory`, `billing`, and `notification` are three separate groups, each group has an independent subscription or read position. When a publisher emits an event, all three groups can receive and process that event.

This is the fan-out behavior usually expected when multiple independent services care about the same event.

### Multiple Instances in the Same Group: Sharing Work

If the `inventory` group runs three instances, the instances join the same group to divide up message processing. The broker decides which instance receives a message or which partitions are assigned to which instance.

Therefore, the same message is usually processed by only one member of the group at a time under the broker's distribution mechanism. You should not create multiple instances in the same group expecting each instance to receive a copy of every event.

| Arrangement | Expected Behavior |
|---|---|
| Three services, three different groups | Each service receives an independent event stream. |
| Three instances, same group | Instances share the processing load of one service. |
| Three instances, three separate groups | Each instance has its own subscription and may receive the entire stream; usually not the way to scale a single service. |

In production, give groups stable names based on business roles, such as `inventory`, `billing`, or `notification`. Group names help the broker identify subscriptions and preserve consumption progress within the binder's capabilities.

If you omit `group`, Spring Cloud Stream and the binder may create anonymous subscriptions. How anonymous subscriptions behave and how long they persist varies across brokers. Do not rely on that behavior for consumers that must resume reading after an application restart; configure an explicitly named group.

## 4. Expressing Pub/Sub with Spring Cloud Stream

Spring Cloud Stream encourages a functional programming model:

| Function Type | Data Direction | Default Binding |
|---|---|---|
| `Supplier<T>` | Produces data to publish | `<functionName>-out-0` |
| `Function<I, O>` | Receives data, transforms it, and publishes output | `<functionName>-in-0` and `<functionName>-out-0` |
| `Consumer<T>` | Receives and processes data | `<functionName>-in-0` |

Binding names are derived from the function bean name. For example, a bean named `inventory` has the default input binding `inventory-in-0`. You can configure that binding to point to destination `orders` and group `inventory`.

When you need to publish events from regular business logic, `StreamBridge` allows sending data to an output binding. This is useful when an event is produced inside a service, controller, or component that is not a `Supplier`.

### Configuration Example

The example below shows an application with two consumer functions and one output binding sent via `StreamBridge`. In a real system, the publisher and subscribers may live in independently deployed applications; each application only needs to configure the bindings it uses.

~~~yaml
spring:
  cloud:
    function:
      definition: inventory;billing
    stream:
      bindings:
        orders-out-0:
          destination: orders
        inventory-in-0:
          destination: orders
          group: inventory
        billing-in-0:
          destination: orders
          group: billing
~~~

The configuration above means:

- `orders-out-0` sends messages to the `orders` destination.
- `inventory-in-0` receives from the same destination but belongs to group `inventory`.
- `billing-in-0` also receives from destination `orders`, but belongs to group `billing`.
- The two groups track consumption progress separately, so both can process published events.

### Declaring the Event

Events should have a clear, stable structure and contain only the data subscribers need:

~~~java
import java.math.BigDecimal;
import java.time.Instant;

public record OrderCreated(
    String eventId,
    String orderId,
    Instant occurredAt,
    BigDecimal total,
    int schemaVersion
) {}
~~~

`eventId` identifies the event; `orderId` is the business key; `occurredAt` records when the event happened; `schemaVersion` supports contract evolution. This is a minimal example and can be extended with currency or other required details according to your system's contract.

### Subscribers

Each consumer function is a subscriber. The bean name determines the input binding name:

~~~java
import java.util.function.Consumer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderConsumers {

    @Bean
    Consumer<OrderCreated> inventory() {
        return event -> {
            // Inventory business logic to process event.orderId()
        };
    }

    @Bean
    Consumer<OrderCreated> billing() {
        return event -> {
            // Create a billing request for event.orderId()
        };
    }
}
~~~

When an application has multiple function beans, declaring `spring.cloud.function.definition` tells Spring Cloud Stream which functions to activate as endpoints. In the example, `inventory;billing` activates both consumers.

### Publisher Using StreamBridge

The publisher sends events through the configured output binding:

~~~java
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final StreamBridge streamBridge;

    public OrderEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public void publish(OrderCreated event) {
        boolean sent = streamBridge.send("orders-out-0", event);

        if (!sent) {
            throw new IllegalStateException(
                "Failed to send OrderCreated event"
            );
        }
    }
}
~~~

The name `orders-out-0` in the call must match the configured output binding. The boolean result indicates whether sending through the binding succeeded at the send step; it does not prove that every subscriber has received or finished processing the event.

You can use `Supplier<OrderCreated>` if the application proactively supplies data to an output stream, or `Function<A, B>` if it needs to receive a message and publish a transformed one. Regardless of the function type, the pub/sub principle still rests on the destination and the subscriptions/groups configured for that destination.

## 5. How Does the Binder Map Destination and Group?

Spring Cloud Stream keeps the binding model consistent at the application level, while the binder translates configuration into the broker's corresponding concepts.

| Spring Cloud Stream Concept | Kafka Binder | RabbitMQ Binder | Pulsar Binder |
|---|---|---|---|
| Destination | Topic | Exchange and bound queues | Topic |
| Consumer group | Kafka consumer group | Group-specific queue bound to the exchange | Subscription name |
| Load sharing within group | Consumers divide partitions | Multiple consumers read the same queue | Depends on subscription type |
| Read state | Offsets per partition and group | Queue state, acknowledgements, and remaining messages | Subscription/cursor state |

A publisher sending to destination `orders` does not need to know whether the binder connects to Kafka, RabbitMQ, or Pulsar. However, details such as resource creation, acknowledgement, retention, distribution, and ordering are still governed by the broker.

### With Kafka

`destination` typically maps to a topic. Each consumer group maintains its own offsets, so two independent groups can read the same topic without interfering with each other's progress. Instances in the same group divide up partitions; partition count and partition assignment limit the group's parallelism.

Kafka guarantees ordering within a single partition. If events related to the same order need to preserve order, the publisher should use an appropriate partition key, such as `orderId`, so that events for that order land in the same partition.

### With RabbitMQ

`destination` typically maps to an exchange. The binder creates a queue for the consumer group and binds that queue to the exchange. Independent groups get their own queues so they can receive the same message; multiple consumers in the same group compete to read from the group's queue.

Pay attention to durable queue settings, acknowledgements, prefetch, and how rejected or requeued messages are handled. These settings affect recoverability and load distribution.

### With Pulsar

`destination` maps to a topic and `group` maps to a subscription. Multiple independent subscriptions can read the same topic. How messages are distributed among consumers in a subscription depends on the subscription type and the Pulsar binder configuration.

Do not assume every binder shares the same default behavior. When switching brokers, re-verify subscription settings, ordering, acknowledgements, retries, and retention.

## 6. Lifecycle of a Pub/Sub Message

A publish-and-consume flow typically proceeds through these steps:

1. A business service determines that an event occurred, such as an order being created successfully.
2. The publisher constructs the payload according to the event contract and sends it via an output binding.
3. The binder converts the payload into the appropriate format and sends it to the broker.
4. The broker routes or stores the message according to the destination and registered subscriptions/groups.
5. Each group receives the message via the broker's mechanism; instances in the group share the work.
6. The subscriber processes the message and acknowledges it according to the binder's acknowledgement or offset mechanism.
7. If processing fails, retry, retention, or dead-letter routing behavior depends on configuration and the broker.

Publishers usually do not wait for all subscribers to finish their work. This lets services operate independently, but it also means business state across services can update at different times. This is the eventual consistency characteristic common in event-driven architectures.

A new subscriber can only replay old events if the broker still retains the data and the subscriber's subscription/offset is positioned appropriately. Registering a new group does not mean every broker will automatically replay the entire history; you must understand the retention, offset, or cursor policies of the system you use.

## 7. Designing Event Contracts for Multiple Subscribers

An event consumed by multiple services becomes an integration contract between components. Therefore, design payloads with these principles:

- **Express an event that occurred:** prefer names such as `OrderCreated`, `PaymentCaptured`, or `ShipmentDispatched`. Event names should reflect a business fact, not tie to a specific subscriber.
- **Include a stable identifier:** use `eventId` to support logging, deduplication, and tracing.
- **Carry the business key:** `orderId` helps subscribers look up the right entity and can serve as a partition key.
- **Include timestamp and version:** `occurredAt` and `schemaVersion` assist with historical analysis and change management.
- **Keep payloads focused:** publish only necessary data; avoid sending raw persistence entities or internal fields outside the public contract.
- **Stay compatible when changing:** prefer adding optional fields with sensible defaults; renaming, retyping, or redefining fields requires a migration strategy and coordination with consumers.

If publishers and subscribers deploy independently, schema changes should be treated like API changes. Use schema compatibility tests or integration tests between producer and consumer versions before releasing.

## 8. Guarantees to Understand Accurately

Pub/sub distributes messages to multiple groups, but it does not automatically create identical delivery guarantees across every broker and configuration.

**Successful send does not mean processing completed.** The result of `StreamBridge.send` is not proof that every subscriber has finished processing. If the business flow needs to know when a subscriber has completed, design a response event or separate orchestration flow.

**Messages can be processed more than once.** With at-least-once delivery, a subscriber may receive a message again if a failure happens after executing business side effects but before acknowledging. Handlers should be idempotent: processing the same `eventId` multiple times should not produce unintended duplicate business effects.

**Ordering has a scope.** Do not assume global ordering across multiple partitions, queues, or subscriptions. If ordering per entity matters, use an appropriate key and verify the binder's ordering limits.

**Sending a message and updating a database are not automatically atomic.** If an application writes an order to the database and then sends an event, a failure between the two operations can leave the database and event stream out of sync. For high reliability requirements, consider the transactional outbox pattern or an appropriate transactional integration mechanism.

**Subscribers need an error strategy.** Bounded retries, dead-letter queues/topics, monitoring, and replay procedures help handle failing messages. These need to be configured per binder and tested in a production-like environment.

## 9. Testing Publish-Subscribe Flows

You should test at multiple levels:

1. **Handler unit tests:** call the consumer function directly with a sample event; verify business behavior and idempotent handling.
2. **Binding tests:** use the Spring Cloud Stream test binder to verify the application sends and receives with the right bindings, payloads, and headers.
3. **Broker integration tests:** run the target broker, for example via Testcontainers, to verify destination/group mapping and actual binder behavior.
4. **Fan-out tests:** publish one event and verify that two independent groups both receive it.
5. **Load-sharing tests:** run multiple instances in the same group and verify work is distributed according to the broker's mechanism.
6. **Failure tests:** simulate a stopped subscriber, processing failure, retry, and recovery to verify messages are not lost beyond the chosen policy.

Unit tests alone do not prove broker fan-out behavior. In particular, integration tests are essential whenever changing binders or group configurations.

## 10. Common Design Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Sharing one group across services that need independent delivery | Services split messages between them; one service may miss events it needs | Create a separate group per subscriber role |
| Creating a separate group per replica just to scale | Each replica has an independent subscription and may receive the entire stream | Have replicas of the same service join one group |
| Omitting a stable group configuration | Anonymous subscription behavior may not survive restarts or multi-instance scaling | Name groups explicitly for production consumers |
| Assuming the publisher waits for subscribers to finish | Business flows rely incorrectly on response timing | Design explicit acknowledgements or reply events if truly needed |
| Assuming all brokers share the same ordering and retry semantics | Incorrect behavior when switching binders | Read and test the semantics of the specific binder |
| Non-idempotent handlers | Retries or redelivery can create duplicate business side effects | Use event IDs and appropriate deduplication mechanisms |
| Unplanned schema changes | Older consumers may fail when receiving new payloads | Manage versions and run compatibility tests |

## 11. Hands-On Workflow

For the `OrderCreated` problem, implement in this sequence:

1. Identify which components truly need to receive the event and assign a separate group to each.
2. Design the `OrderCreated` payload with `eventId`, `orderId`, `occurredAt`, and a schema version.
3. Configure the output binding `orders-out-0` pointing to destination `orders`.
4. Create consumer functions named `inventory` and `billing`, and configure their input bindings with separate groups.
5. Publish a sample event using `StreamBridge`.
6. Verify both groups receive the event.
7. Increase the instance count of the inventory consumer while keeping group `inventory`; observe how the broker shares the load.
8. Resend the same `eventId` and verify the handler does not create duplicate business effects.
9. Repeat the tests against your deployed binder to confirm actual runtime behavior.

When finished, you should be able to explain why two services using two different groups both receive a given event, whereas two instances sharing one group primarily split the processing work between them.

## Conclusion

Publish-subscribe lets a publisher emit events to a destination without knowing the list of subscribers. In Spring Cloud Stream, bindings connect application functions to destinations, while consumer groups define subscription boundaries and independent consumption progress. Different groups create fan-out; multiple instances in the same group create load sharing.

Designing destinations, groups, and event contracts properly is the foundation for independent coordination across Spring Cloud Stream services. When deploying, also verify delivery semantics, ordering, retention, and retry behavior for the specific Kafka, RabbitMQ, or Pulsar binder your system uses.
