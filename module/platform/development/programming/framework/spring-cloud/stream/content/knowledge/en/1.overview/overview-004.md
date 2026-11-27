# Roles of Producers, Consumers, and the Message Broker

In an event-processing system, an application often needs to notify other applications that something has happened: an order was created, a payment completed, inventory changed, or a device sent a new measurement. If the publisher calls each recipient directly, both sides must know each other's address, interface, and availability status. As the number of services grows, direct coupling makes changes harder to deploy and failures in one service can cascade to others.

A message broker creates an intermediary point for this exchange. The producer sends messages to the broker; the broker accepts, routes, and distributes messages; and consumers retrieve messages to process them. Spring Cloud Stream provides a programming model for Java applications to work with message streams through bindings and binders. This lets business code focus on creating, transforming, or processing events, while binder configuration handles connecting to Kafka, RabbitMQ, Pulsar, or another supported platform.

## 1. Three Roles in a Message Flow

### 1.1. Producer

The producer is the component that creates a message and sends it into the system. A source of messages may be:

- A business service that just completed an operation, such as an order service emitting an OrderCreated event.
- A scheduled process that reads data and emits summary messages.
- An adapter receiving data from HTTP, a database, a device, or an external system.
- A processing function that received a previous message and produces the next message.

The producer is responsible for defining the meaning of the message, constructing a payload matching the data contract, and sending it to the configured logical destination. An event should describe a fact that has occurred, such as OrderCreated or PaymentCompleted. An event usually carries an entity identifier, occurrence timestamp, and the data needed for recipients to understand what happened. If a message expresses a request for another party to perform an action, such as ReserveInventory, it is closer to a command than an event. Distinguishing the two keeps service names and responsibilities clear.

The producer does not need to know how many services will process each message. It sends the message to a logical destination; the broker and routing configuration decide how it is distributed. This reduces direct dependencies between services, though it does not eliminate the responsibility for designing data contracts and handling send failures.

In Spring Cloud Stream's functional model, a Supplier bean can act as a message source. The framework invokes a Supplier by polling to fetch data and push it to an output binding. For emissions triggered by an external event, such as an HTTP request, an application can also send via StreamBridge to push data into an output binding. Thus, Supplier fits pollable sources, while StreamBridge fits when application code actively decides when to emit.

### 1.2. Consumer

The consumer subscribes to receive messages from a destination and performs the corresponding work. For example:

- The inventory service receives OrderCreated to check and reserve stock.
- The payment service receives PaymentRequested to call the payment gateway.
- The notification service receives ShipmentDispatched to send emails or text messages.
- The analytics service receives transaction events to update metrics.

The consumer is responsible for validating input data, applying business rules, recording results, and handling recoverable errors. A consumer should be capable of safe duplicate processing. In distributed systems, a message may be redelivered if an application fails after performing part of the work but before the broker records completion. If reprocessing triggers a second payment or deducts inventory twice, the system will create business inconsistencies.

Spring Cloud Stream represents a terminal consumer with a Consumer bean. If you need to transform a message and send the result to another destination, use a Function: the function receives input, processes it, and returns output. A Function can therefore be both a consumer for one stream and a producer for the next stream.

### 1.3. Message Broker

The broker is the intermediary infrastructure that accepts and distributes messages. Depending on the product and configuration, a broker can provide capabilities such as:

- Accepting and buffering messages for consumers to process at an appropriate time.
- Routing messages to the corresponding topic, queue, or subscription.
- Delivering the same data stream to multiple independent service groups.
- Retaining messages for a period of time or until acknowledged.
- Partitioning data to increase parallel processing capacity.
- Supporting acknowledgements, retries, failed-message storage, and delivery guarantee mechanisms.

The broker decouples the time of sending from the time of processing. When a consumer is temporarily stopped, messages can be held for later processing if the broker type and retention settings support it. However, the broker does not understand business rules on its own. It cannot know whether a payment has been recorded in a database, nor can it automatically guarantee that a business operation occurs only once.

The three roles may reside in three separate systems, though they do not have to be three separate applications. A single application can both produce and consume messages; the broker is usually independent infrastructure outside the applications and shared across multiple services.

## 2. How Does a Message Flow Through the System?

Consider an example where the order service creates a new order. This service emits OrderCreated. The inventory service receives the event, checks stock, and emits ReservationRequested. Another service receives that message to perform the reservation.

~~~mermaid
flowchart LR
    P["Order Service<br/>Producer"] -->|"OrderCreated"| B[("Message broker")]
    B -->|"Route by destination"| C["Inventory Service<br/>Consumer / Function"]
    C -->|"ReservationRequested"| B
    B -->|"Next message"| N["Reservation Service<br/>Consumer"]
~~~

The basic flow consists of these steps:

1. The producer builds the payload and required metadata, then sends it to the output binding.
2. The binding passes the message through the corresponding binder to reach the destination on the broker.
3. The broker accepts and stores or routes the message according to its mechanism.
4. The consumer's input binding pulls the message from the configured destination.
5. Spring Cloud Stream converts the payload to the data type declared by the handler function, if content-type conversion is appropriately configured.
6. A Consumer processes it and ends the flow, or a Function returns a new message to emit via an output binding.
7. Acknowledgement, retry, or dead-letter routing outcomes depend on the binder, broker, and error-handling configuration.

A successful send from the application only indicates that one step of the workflow completed. It does not mean all consumers have succeeded. Tracing the full flow requires a correlation ID, logs, metrics, and status observability across services.

## 3. Spring Cloud Stream Connects Applications to Brokers

Spring Cloud Stream provides an abstraction layer around sending and receiving messages. Applications declare handler functions and logical bindings; binders connect those bindings to specific messaging technologies.

| Component | Role |
|---|---|
| Supplier | Supplies output data, typically invoked by the framework on a polling schedule |
| Function | Receives input data, transforms or processes it, and returns output data |
| Consumer | Receives and processes data without producing output for that stream |
| Binding | Links a logical input or output of a function to a destination |
| Destination | Physical or logical target on the broker, such as a topic or queue |
| Binder | Adapter connecting bindings to a specific broker like Kafka, RabbitMQ, or Pulsar |

### 3.1. Supplier, Function, and Consumer

Function beans are recognized by Spring Cloud Function by their declared types:

~~~java
@Bean
Supplier<PurchaseCreated> purchaseSource() {
    return () -> new PurchaseCreated(
        UUID.randomUUID().toString(),
        Instant.now()
    );
}
~~~

PurchaseSource illustrates a message source. The framework polls the Supplier and sends the returned value to the output binding. In a real application, data typically comes from a meaningful business source; you should not emit synthetic data periodically without explicitly configuring the cadence and emission conditions.

~~~java
@Bean
Function<PurchaseCreated, ReservationRequested> reserveInventory() {
    return purchase -> new ReservationRequested(
        purchase.purchaseId(),
        Instant.now()
    );
}
~~~

ReserveInventory receives a purchase event, processes it, and produces a reservation-request message. The Function's input and output are wired to two separate bindings.

~~~java
@Bean
Consumer<ReservationRequested> notifyWarehouse() {
    return request -> {
        // Invoke business logic to accept the inventory reservation request.
        log.info("Received reservation request for order {}", request.purchaseId());
    };
}
~~~

NotifyWarehouse receives the message and performs the final task in the flow. If the task calls another service or writes data, the handler must account for timeouts, transient failures, and potential message redelivery.

The example data types can be declared as Java records:

~~~java
public record PurchaseCreated(
    String purchaseId,
    Instant createdAt
) {}

public record ReservationRequested(
    String purchaseId,
    Instant requestedAt
) {}
~~~

The example above focuses on function shapes; imports, logging setup, and business logic are omitted. In a real system, producers and consumers usually live in separate applications or services.

### 3.2. Bindings and Binding Names

A binding is the logical name Spring Cloud Stream uses to connect a function to a destination. For standalone function beans, binding names are derived from the bean name and data direction:

| Function Bean | Binding | Direction |
|---|---|---|
| purchaseSource | purchaseSource-out-0 | Output of Supplier |
| reserveInventory | reserveInventory-in-0 | Input of Function |
| reserveInventory | reserveInventory-out-0 | Output of Function |
| notifyWarehouse | notifyWarehouse-in-0 | Input of Consumer |

The in suffix indicates input, out indicates output, and 0 is the port index. This naming convention allows a function to declare multiple inputs or outputs when needed. The binding name is a configuration identifier inside the application, whereas the destination is the resource name the binder maps onto the broker.

Example configuration for the reservation-request service:

~~~yaml
spring:
  cloud:
    function:
      definition: reserveInventory
    stream:
      bindings:
        reserveInventory-in-0:
          destination: purchases.created
          group: inventory-service
          content-type: application/json
        reserveInventory-out-0:
          destination: inventory.reservation.requested
          content-type: application/json
~~~

In this configuration:

- reserveInventory is the activated function.
- reserveInventory-in-0 receives messages from the purchases.created destination.
- inventory-service is the stable consumer group for the inventory service.
- reserveInventory-out-0 sends results to inventory.reservation.requested.
- content-type declares the content format so the framework chooses the appropriate converter.

A producer and consumer can use the same destination name to exchange messages without sharing binding names. Binding names belong to each application's configuration; the destination name is the meeting point on the broker. When changing a destination, coordinate configuration changes and data migration plans to avoid disrupting active consumers.

### 3.3. Binders and Broker Technology Independence

The binder implements how bindings communicate with the broker. An application can use the Kafka, RabbitMQ, or Pulsar binder via the corresponding dependency and connection configuration. Through this abstraction layer, Supplier, Function, and Consumer code stays largely decoupled from broker-specific APIs.

However, independence does not mean every broker shares identical semantics or features. Kafka organizes data into topics and partitions; RabbitMQ routes through exchanges to queues; Pulsar provides topics and subscriptions with multiple consumption modes. Options for retention, ordering, acknowledgements, retries, DLQs, transactions, and scalability still have to be understood in the context of the binder and broker in use.

| Broker | Common Concepts | Mental Model |
|---|---|---|
| Apache Kafka | Topic, partition, offset, consumer group | Record streams stored by partition; consumers read by offset |
| RabbitMQ | Exchange, queue, binding, routing key | Exchanges route messages to queues; consumers pull messages from queues |
| Apache Pulsar | Topic, subscription, subscription type | Consumers receive data via subscriptions; subscription type determines distribution |

At deployment time, add the right binder to the classpath and configure broker addresses along with authentication, TLS, destination, and binder-specific options. Do not copy Kafka configuration verbatim to RabbitMQ or Pulsar simply because binding names look the same.

## 4. Consumer Groups, Partitioning, and Scalability

A consumer group represents a group of consumers collaborating to process a logical stream. Brokers differ in how they implement groups, but the common goal is allowing multiple instances to share load.

With Kafka, consumers in the same group split the topic's partitions among themselves. At any point in time, each partition is assigned to at most one consumer in the same group. Therefore, if a topic has four partitions, a single group generally cannot utilize more than four consumers to read that topic in parallel. Extra consumers can still run, but they will receive no partitions. When scaling instances up or down, Kafka may rebalance partition assignments.

Two different Kafka groups can read the same topic independently. For instance, inventory-service and analytics-service both receive order events, with each group maintaining its own read position. Within a group, instances share load; across groups, each service has its own consumption stream.

With RabbitMQ, consumers reading from the same queue usually compete for messages in that queue. To let multiple independent services each receive a copy of an event, you typically need separate queues bound to an exchange. With Pulsar, subscriptions manage consumption; Exclusive, Failover, Shared, and Key_Shared each have distinct distribution rules. Consequently, you should not assume a Spring Cloud Stream consumer group behaves identically across every binder.

In Spring Cloud Stream, the group property sets a stable consumer group name. For a service running multiple instances, those instances usually share one group to distribute load as supported by the binder. If group is omitted, the binder may create an anonymous subscription or queue; its behavior and lifetime depend on the broker. Production environments should configure group intentionally to control distribution and resume reading after application restarts.

### 4.1. Partition Keys and Processing Order

Partitioning splits a destination into segments so multiple consumers can process in parallel. When producing messages, a partition key is often chosen from a business attribute such as purchaseId or customerId. Messages with the same key can be routed to the same partition, thereby preserving relative order within that partition as guaranteed by the broker.

Do not assume an entire topic has a single strict global order when there are multiple partitions. If two events belong to different partitions, consumers may process them concurrently and finish in a different order. When business rules require per-order or per-account ordering, choose an appropriate key and ensure related events share that key.

The partition key also affects load distribution. If all messages use one popular key, one partition can become a hotspot while others sit underutilized. Consider partition count, key distribution, and consumption speed during design.

## 5. Message Contracts and Schema Compatibility

A message typically has two parts:

- Payload: business data, such as order ID, amount, or payment status.
- Header: metadata for transport and processing, such as content type, correlation ID, message identifier, emission timestamp, or routing details.

Spring Messaging represents a message as Message with payload and headers. When headers need to be set explicitly, applications can use MessageBuilder; when simply exchanging a plain object, the framework can convert the payload according to the configured content type.

A data contract is a commitment between the producer and consumers. If the producer renames a field or changes the meaning of a value, older consumers may no longer process it properly. Several principles help reduce risk:

1. Use clear, meaningful names for events and fields.
2. Add new fields in a compatible way, such as optional fields with sensible defaults.
3. Avoid changing the data type or meaning of fields currently used by consumers.
4. Have a schema versioning strategy when breaking changes are unavoidable.
5. Test new producers against existing consumers before rolling out broadly.

JSON is commonly used because it is easy to inspect and widely supported across languages, though systems may choose Avro, Protobuf, or other formats. A Schema Registry, if integrated, can manage versions and enforce compatibility rules. The broker itself does not necessarily understand or validate schemas; validation depends on configured serializers, binders, and schema management components.

Avoid dumping an entire internal entity of a service into the payload. Publish only the data recipients need and treat emitted events as public contracts. This reduces coupling to the producer's database structure and internal models.

## 6. Delivery, Acknowledgements, Retries, and Dead Letter Queues

When designing a messaging system, determine what happens if the producer, broker, or consumer fails. Three common ways to describe delivery semantics are:

| Semantics | Meaning | Implications to Handle |
|---|---|---|
| At-most-once | A message is processed no more than once under the delivery mechanism | Messages may be lost if failure occurs before processing finishes |
| At-least-once | The system attempts delivery until acknowledged | Duplicates may be received or processed; consumers must be idempotent |
| Exactly-once | Restricts duplicate outcomes within a supported processing scope | Guarantee boundaries depend on broker, binder, transactions, and target systems |

At-least-once is usually the practical choice for many business flows because it prioritizes not losing messages. In return, consumers must handle duplicates safely. A common approach is using a message ID or business key to check whether an event has already been applied. When writing data and marking an event as processed, design transactions to avoid a state where the business change is saved without the processed marker, or vice versa.

Exactly-once must be understood within specific boundaries. Kafka has transaction mechanisms and supports certain end-to-end flows within Kafka boundaries. That does not automatically make an HTTP call, an email send, or a database transaction outside Kafka exactly-once. For workflows that update a database and then emit an event, consider Transactional Outbox to save the business change and the event record in the same transaction; a separate process publishes that record to the broker. Consumers should still protect against duplicate processing.

### 6.1. Retries

Retries fit transient failures such as network timeouts, overloaded downstream services, or temporarily unavailable brokers. Bound the number of attempts, wait intervals, and total duration. Exponential backoff, optionally with jitter, helps avoid many consumers retrying in tight loops and worsening system overload.

Not every error should be retried. Malformed data, missing required fields, or business-rule violations are typically non-recoverable by simply re-sending the exact same message. Unbounded retries allow one bad message to consume resources and block processing. Retry configuration in Spring Cloud Stream can be set per binding; attempt counts and backoff should be chosen based on dependent service recovery times.

### 6.2. Dead Letter Queue (DLQ)

A DLQ stores messages that remain unprocessable after retry policies are exhausted. Depending on the binder, this mechanism may be called a dead-letter queue or a dead-letter topic. A DLQ isolates failing messages from the main flow so valid messages continue to be processed.

A DLQ is only useful when paired with an operational process. Record the failure reason, timestamp, attempt count, and identifying details; alert when failed-message counts spike; assign ownership for investigation; and establish a procedure to fix data or handler code before replaying. Replaying a message back into the main stream without checks can duplicate actions or reproduce the same failure.

DLQ queue/topic names, access permissions, and activation settings depend on the binder. For example, the Kafka binder and RabbitMQ binder have distinct configuration properties. Read the documentation for your active binder and test real failure scenarios rather than assuming one generic property produces identical behavior across brokers.

## 7. Stateful Processing with Kafka Streams

Supplier, Function, and Consumer functions fit many straightforward message flows. When you need windowed aggregations, stream-to-stream joins, stateful table updates, or continuous keyed computations, Kafka Streams provides a stateful stream-processing model.

Spring Cloud Stream's Kafka Streams binder lets applications declare functions working with types such as KStream, KTable, or GlobalKTable. This is a specialized binder with its own dependencies and configuration; do not confuse it with the standard Kafka message binder.

- KStream represents a stream of event records, where each record is processed as an individual event in the flow.
- KTable represents keyed, updatable state, where newer records can supersede previous state for the same key.
- GlobalKTable is a state table replicated across instances via Kafka Streams mechanisms, useful for certain lookup joins.
- State stores hold local state to support computations. Changelog topics can be used to restore state when an instance restarts or moves processing assignments.

For example, a retail system can aggregate total revenue over five-minute windows. The order or store key determines partitioning; the window defines the aggregation interval; and results are emitted as an aggregated stream. With stateful processing, you must design keys, event time, windowing policies, state storage, and recovery behavior. You also need to verify how late-arriving events and duplicate data are handled.

Kafka Streams fits problems requiring continuous processing and state kept close to the data stream. If you only need to receive a message and invoke an independent business operation, a regular Function or Consumer is usually simpler to deploy and operate.

## 8. Testing and Operations

A message flow should be tested at multiple levels:

| Testing Level | Objective | Tools or Approach |
|---|---|---|
| Function tests | Verify Supplier, Function, or Consumer with deterministic inputs | Invoke beans directly; mock business dependencies |
| Binding tests | Verify payloads enter and exit the expected bindings | Spring Cloud Stream Test Binder with InputDestination and OutputDestination |
| Broker integration tests | Verify binder config, groups, partitions, retries, and DLQ on a real broker | Kafka, RabbitMQ, or Pulsar running in test environments such as Testcontainers |
| Contract tests | Verify producer and consumer agree on message structure | Schema or contract tests between services |

The Test Binder lets you verify flows inside the JVM without starting a real broker. It is useful for verifying functions and bindings, but it does not replace integration tests for broker-specific behaviors like rebalancing, acknowledgements, ordering, transactions, or DLQ routing. For those features, test against the actual broker.

In production, monitor at least:

- Message production and consumption rates, along with processing latency.
- Consumer lag or queue depth to spot consumers falling behind.
- Retry counts, DLQ message counts, and common error causes.
- Error rates, timeouts, and processing duration per consumer.
- Correlation IDs or message IDs to link logs across producer, broker, and consumer.
- Partition changes, rebalances, and broker connection health.

Avoid logging full payloads if they contain sensitive data. Log identifiers, event types, and sufficient diagnostic details while enforcing your system's data protection policies.

## 9. Common Design Mistakes

**Tightly coupling the producer to each consumer.** If the producer calls each service directly, adding a new consumer requires modifying the producer and handling more connection failures. Routing messages through a broker keeps participants more independent.

**Sharing one consumer group across services that each need an independent copy.** In Kafka, consumers in the same group divide partitions, so each record is not delivered separately to every instance in the group. If two services both need to process every event, they need independent groups.

**Adding consumers without checking partition counts.** In Kafka, the number of active consumers in a group is bounded by the number of assignable partitions. Balance partition count against expected load.

**Assuming messages arrive only once.** Retries, rebalances, or failures during acknowledgement can cause redelivery. Consumers need idempotency and consistent state tracking.

**Changing schemas without checking older consumers.** Producers may deploy before consumers or vice versa. Contract changes require a compatibility plan and an appropriate rollout sequence.

**Treating a DLQ as a write-only dumping ground.** Without alerts, ownership, and a replay workflow, a DLQ merely hides failures from the main stream.

**Assuming binders make all brokers identical.** Bindings standardize how applications connect, while groups, partitions, acknowledgements, retention, and DLQs still retain broker-specific semantics.

## 10. Defining Responsibilities When Designing a New Flow

Before implementing, the development team should answer these questions:

1. Which event occurred, and which service owns that event?
2. Which services need to receive the event, and does each service need an independent copy or just load sharing across instances?
3. Which destinations, bindings, and binders will be used?
4. Which partition key preserves the ordering required by the business?
5. Which payload fields and headers form the data contract, and how is schema versioning managed?
6. Which errors are retryable, how many times should they be retried, and which DLQ receives failed messages?
7. How does the consumer prevent duplicate processing, and where are the transaction boundaries?
8. What metrics, logs, alerts, and replay procedures support operating the flow?

When responsibilities are clearly defined, the producer can focus on publishing events conforming to the contract; the broker accepts and distributes them as configured; and consumers process independently and resiliently. Spring Cloud Stream connects these three parts through Supplier, Function, Consumer, bindings, and binders, while letting teams choose the broker that fits their retention, routing, ordering, and scalability needs.
