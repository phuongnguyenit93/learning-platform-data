# Queues, Topics, and the Point-to-Point Model

In a single application, components typically invoke each other's methods directly. When a system is split into multiple services, direct communication requires the sender to know where the receiver is running and whether it is available. Asynchronous messaging solves this problem by having the sending service create a message, send it to a logical address, and let the receiving service process it when it can.

Spring Cloud Stream provides a functional programming model for building such applications. The application declares functions that produce, transform, or consume messages; bindings connect a function's inputs and outputs to destinations; and binders connect those destinations to messaging systems such as Kafka, RabbitMQ, or Pulsar. To design flows properly, you first need to understand queues, topics, and the two common delivery patterns: point-to-point and publish/subscribe.

## 1. Messages, Destinations, and Brokers

A **message** typically consists of a payload and metadata. The payload holds business data, such as an order ID and total amount. Metadata may contain an event ID, timestamp, partition key, content type, or tracing information. You should not rely on broker-generated metadata as if it were a stable business identifier.

A **destination** is the logical name an application uses to send or receive messages. Depending on the binder, a destination may map to a topic, an exchange, a queue, or a corresponding resource on the broker. Therefore, using the same destination name in source code does not mean every broker has the same physical structure.

A **broker** receives messages from producers, stores or routes them according to configuration, and delivers them to consumers. The broker usually handles responsibilities that applications should not build themselves: buffering when consumers are slow, load distribution, delivery acknowledgements, message retention, and routing failed messages to isolation.

You can picture the basic flow as follows:

~~~text
Producer
   |
   | sends message to destination
   v
Broker
   |
   | stores / routes / delivers
   v
Consumer
   |
   | processes and acknowledges
   v
Complete or retry / route to DLQ
~~~

Producers and consumers do not need to call each other directly. The producer only needs to know the destination and the message contract; the consumer can be deployed, scaled, or restarted independently.

## 2. Queues and the Point-to-Point Model

A **queue** is a place that holds messages waiting to be processed. Producers send messages to the queue; one or more consumers subscribe to receive from that queue. When multiple consumers compete on the same queue, the broker delivers each message to one consumer in the processing group. This arrangement is commonly called **competing consumers**.

The **point-to-point (P2P)** model describes a delivery goal: each message is delivered to one logical processing party. "One party" here means a group of consumers belonging to the same service, not necessarily a single process or a single server. You can run multiple instances of a service to increase processing capacity; they compete on a queue or participate together in a consumer group.

For example, an order service sends an `OrderCreated` event to an inventory processing stream. Multiple instances of the inventory service can receive messages together. For each message, only one instance in the inventory group performs the work of reserving stock. If two instances process a copy of the same message due to redelivery, the application still needs to protect the business operation with idempotency.

~~~text
                    +--> Inventory Consumer A
Producer --> Queue -+--> Inventory Consumer B
                    +--> Inventory Consumer C

Each message is assigned to one consumer in the group.
~~~

A queue decouples the time of sending from the time of processing. If the inventory service stops temporarily, the broker can retain messages for later processing, within the configured retention policy and storage capacity. When a consumer acknowledges success, the broker or messaging system records processing progress according to its mechanism. If the consumer fails before acknowledging, the message can be redelivered.

This leads to three design considerations:

- **Acknowledgement:** determines when a message is considered processed. Acknowledging too early can lose work if the process crashes midway; acknowledging too late can cause redelivery.
- **Retry:** handles transient errors such as an unavailable downstream service. You should bound the number of attempts and consider backoff delays to avoid overloading the broker or downstream service.
- **Dead-letter queue (DLQ):** isolates messages that cannot be processed after the retry policy, so they can be investigated and handled in a controlled manner instead of looping indefinitely.

Queues fit work that needs to be completed by a single processing group, such as sending invoices, creating shipping labels, or updating inventory. If multiple independent services all need to receive the same event, a single shared queue usually does not express that requirement accurately.

## 3. Topics and the Publish/Subscribe Model

A **topic** is a logical address representing a category of message stream, such as `orders.created` or `payments.completed`. Producers publish messages to the topic; interested parties subscribe to receive messages. This model is commonly called **publish/subscribe (pub/sub)**.

The key point is that each subscriber needs independent consumption progress. For example, after an order is created:

- The inventory service needs to reserve stock.
- The payment service needs to initiate a transaction.
- The analytics service needs to record the event to compute metrics.

All three services need to know that an order was created. If they compete on a single queue, each message might reach only one service and the other two services would miss it. With pub/sub, each service has its own subscription or queue; the broker delivers a logical copy of the message to each subscription.

~~~text
                         +--> Inventory Subscription --> Inventory Consumer
Producer --> Topic ------+--> Payment Subscription ----> Payment Consumer
                         +--> Analytics Subscription --> Analytics Consumer

Each subscription receives an independent event stream.
~~~

Topics are not implemented the same way across every broker:

- **Kafka:** a topic is a log split into partitions. A consumer group has its own offsets to track progress. Multiple groups read the same topic independently; consumers within the same group divide up the partitions.
- **RabbitMQ:** producers usually send to an exchange; the exchange routes messages to bound queues. Each subscribing service can have its own queue. Consumers of the same service share that queue to distribute load.
- **Pulsar:** producers write to a topic; consumers read through a subscription. The subscription type determines how multiple consumers coordinate, such as `Exclusive`, `Failover`, `Shared`, or `Key_Shared`.

Therefore, when talking about "subscribing to a topic," you need to specify both the broker and the specific subscription/group. The topic name only identifies the stream; the subscription or consumer group determines progress tracking and delivery semantics for a group of receivers.

## 4. Comparing P2P and Pub/Sub

| Criterion | Point-to-Point (P2P) | Publish/Subscribe (Pub/Sub) |
|---|---|---|
| Goal | One processing group completes each message | Multiple independent groups receive the same event |
| Receivers | One consumer within the processing group | Each subscription/group has its own receiving stream |
| Scaling | Add consumers to the same queue/group to share load | Add a subscription/group to add a receiver; add consumers within a group to share load |
| Examples | Reserving stock, sending invoices | A new order observed simultaneously by inventory, payment, and analytics |
| Design risks | Redelivery can cause an operation to run multiple times | Subscriptions may process the same event at different times |

P2P and pub/sub are application-level communication semantics. You should not equate P2P with a single broker type or assume that having a topic name automatically broadcasts to every consumer. For instance, Kafka uses a topic with a single consumer group to achieve load-sharing behavior close to P2P; two different consumer groups on the same topic create pub/sub behavior. With RabbitMQ, multiple consumers reading the same queue are competing consumers; multiple queues bound to an exchange can create fan-out to independent services.

## 5. Representing the Model with Spring Cloud Stream

Spring Cloud Stream separates processing logic from broker connection details:

- **Supplier** generates data or events to emit.
- **Function** receives data, transforms it, or produces output results.
- **Consumer** receives data and performs an action, usually without producing output.
- **Binding** connects a function's input/output ports to a destination.
- **Binder** translates a binding's send/receive operations into operations appropriate for Kafka, RabbitMQ, Pulsar, or another supported broker.

In the functional model, default binding names are derived from the function name and data direction. For example, the function `validateOrder` has input `validateOrder-in-0` and output `validateOrder-out-0`. The `destination` property sets the stream name the binding connects to; the `group` property identifies the consumer group for an input binding.

Here is an example of a function that validates an order and emits the validated result:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderValidationFunctions {

    @Bean
    Function<OrderCreated, OrderValidated> validateOrder() {
        return event -> {
            // Validate data and create the result event.
            return new OrderValidated(event.orderId(), event.customerId());
        };
    }
}

record OrderCreated(String orderId, String customerId) {}

record OrderValidated(String orderId, String customerId) {}
~~~

Binding configuration for the function above:

~~~yaml
spring:
  cloud:
    function:
      definition: validateOrder
    stream:
      bindings:
        validateOrder-in-0:
          destination: orders.created
        validateOrder-out-0:
          destination: orders.validated
~~~

The input binding receives events from `orders.created`; the output binding publishes results to `orders.validated`. The binder decides how to map these two destinations to resources on the configured broker. The processing code does not need to directly instantiate a `KafkaProducer`, `RabbitTemplate`, or Pulsar client.

A consumer that processes validated events can be declared as follows:

~~~java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;

@Configuration
class InventoryFunctions {

    @Bean
    Consumer<Message<OrderValidated>> reserveInventory() {
        return message -> {
            OrderValidated event = message.getPayload();
            // Reserve inventory for event.orderId().
        };
    }
}
~~~

And the input configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: reserveInventory
    stream:
      bindings:
        reserveInventory-in-0:
          destination: orders.validated
          group: inventory-service
~~~

The group `inventory-service` represents a logical processing group. When deploying multiple instances of the inventory service with the same `group` configuration, they join the same group and share load according to the binder/broker's capabilities. If you omit `group`, some binders may create anonymous consumers or subscriptions; behavior and progress recovery may differ from a named group. For business consumers that need stable progress tracking, specify `group` explicitly and verify the behavior of the binder in use.

## 6. How Are Destination and Group Mapped?

### Kafka Binder

With Kafka, `destination` typically maps to a topic, and `group` maps to a consumer group:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        reserveInventory-in-0:
          destination: orders.created
          group: inventory-service
~~~

Instances sharing the `inventory-service` group divide up the partitions of the `orders.created` topic. Each record in a partition is processed by one consumer in that group at a time according to Kafka's assignment mechanism. Another group, such as `billing-service`, has its own offsets and can read the same records to handle billing. This is how two independent processing streams are created on the same topic.

If you run more consumers than partitions, some consumers in the group will not be assigned any partitions and will not add useful parallelism. To increase parallel processing capacity, consider the partition count, per-partition load, and the processing capacity of each instance.

### RabbitMQ Binder

With RabbitMQ, a binding's `destination` usually represents an exchange. The consumer `group` determines the queue attached to that exchange for the group. Multiple instances in the same group compete to read from the group's queue; another group has its own queue to receive the same kind of messages.

For example, the `orders.created` exchange can route to the queue for `inventory-service` and the queue for `billing-service`. Inventory consumers share the inventory queue; billing consumers share the billing queue. The exchange type and routing key determine which queues receive a message, so configure and verify them according to business requirements.

### Pulsar Binder

With Pulsar, `destination` maps to a topic and `group` relates to a subscription. The subscription type determines how consumers share messages. `Shared` fits multiple consumers sharing load; `Exclusive` restricts activity to one active consumer; `Failover` provides standby consumers; `Key_Shared` distributes by key so messages with the same key go to the same consumer within Pulsar's mechanism.

These mappings help explain the general meaning of `destination` and `group`. When implementing, check the documentation and configuration for your exact binder version because property names and some defaults can vary across binders.

## 7. Partitions, Keys, and Processing Order

A stream can be split into multiple **partitions** to increase parallel writes and reads. In Kafka, records are written to a partition; the consumer group assigns partitions to its members. Ordering is guaranteed within a single partition, not across the entire topic when there are multiple partitions.

Producers typically choose a partition based on a key. If all events for the same order use `orderId` as the key, they have a chance of landing in the same partition and being read in order within that partition. Without an appropriate key, or if the key changes between events, two related events may be processed in parallel and arrive in a different order.

You should not assume every broker provides the same ordering guarantees. RabbitMQ can change observed ordering when multiple consumers read concurrently, when messages are retried, or when messages are routed to multiple queues. Pulsar has its own subscription types and key-based distribution policies. If your business logic requires ordering, clearly define the scope that must be serialized (by order, by customer, or system-wide), choose the appropriate key and subscription type, and test with the actual deployment configuration.

## 8. Message Contracts and Schemas

A queue or topic only transports messages; they do not automatically guarantee that producers and consumers understand the same data structure. Both sides must agree on a **message contract**:

- Event name and business meaning, for example `OrderCreated` is an event that already occurred, not a request to create an order.
- Required fields, data types, units of measurement, and nullability rules.
- A stable event identifier to detect redelivery, along with entity identifiers such as `orderId`.
- Event occurrence timestamp and correlation information to trace the processing flow.
- Compatibility rules when adding, renaming, or removing fields.

Prefer backward-compatible changes: adding optional fields with sensible defaults is usually safer than changing the type or meaning of an existing field. When breaking changes are necessary, consider schema versioning or a new event and plan a consumer migration. Do not use internal Java class names as the sole contract between services with independent deployment lifecycles.

## 9. Delivery Semantics, Errors, and Idempotency

A broker may redeliver a message if the consumer performed part of the work without acknowledging, or if the connection dropped at the time of acknowledgement. Therefore, the at-least-once model often leads to the possibility that an event is observed multiple times. Consumers should handle duplicates safely by storing processed `eventId` values, using unique constraints in the database, or designing idempotent update operations.

At-most-once reduces the risk of duplicate processing but can lose messages if acknowledged before work completes. Exactly-once is a complex guarantee that depends on the broker, transactions, state storage scope, and how side effects are performed. A single broker configuration cannot guarantee that all external operations such as calling a payment API or sending an email happen strictly once.

A practical error-handling policy typically includes:

1. Retrying transient errors with a bounded attempt count and backoff delay.
2. Routing unprocessable messages to a DLQ or equivalent isolation mechanism.
3. Logging with `eventId`, `destination`, `group`, and error cause for traceability.
4. Having a process to inspect, repair data, and replay messages from the DLQ.
5. Monitoring latency, backlog size, retry rates, and DLQ message counts.

Do not use retries to mask permanent data errors. A message with a malformed schema or business rule violation needs to be isolated and handled through a clear process.

## 10. Testing and Choosing the Right Model

Testing should verify both function logic and delivery semantics:

- **Function testing:** pass a sample payload into a `Function` or `Consumer` and assert the business outcome. Test valid data, missing fields, and duplicate processing cases.
- **Binding testing:** use the Spring Cloud Stream test binder to send messages into a binding and read results from an output binding. Verify binding names, payloads, and important headers.
- **Integration testing:** run the appropriate broker in the test environment, for instance with Testcontainers, to verify groups, queues, partitions, routing, acks, retries, and DLQs. The test binder cannot replace testing the specific behavior of Kafka, RabbitMQ, or Pulsar.
- **Deployment testing:** run multiple instances in the same group to confirm load sharing; run two different groups to confirm each receives an independent stream.

When choosing a model, start from the business question:

| Need | Model to Consider |
|---|---|
| One service needs to process each job; multiple replicas may run to share load | Queue or topic with a single consumer group |
| Multiple independent services all need to react to the same event | Topic with a separate subscription/group for each service |
| Ordering needed per entity | Partition/key or key-based subscription, depending on broker |
| Consumer may stop for a long time and needs to resume from saved progress | Named group/subscription and appropriate retention policy |
| Need to isolate failed messages for investigation | Bounded retries combined with a DLQ |

Before releasing, verify the actual destination created by the binder, the group/subscription of each service, how the broker distributes load as instance counts increase, retention and acknowledgement policies, and schema compatibility. These checks help avoid common mistakes: multiple services accidentally sharing the same group so only one service receives events, or each instance using a separate group so every instance processes the same event.

Once you understand queues, topics, and groups, you can choose the right communication semantics and use Spring Cloud Stream bindings to implement them. Queues and groups fit when you need to distribute work across a load-sharing pool; topics with multiple subscriptions/groups fit when multiple services need to observe the same event. The binder keeps processing code concise, while decisions around delivery, ordering, schemas, and acknowledgement still need to be designed for your system's requirements.
