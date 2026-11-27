# Prerequisites and Learning Path from First Application to Operations

Spring Cloud Stream helps build event-processing applications on Spring Boot using the `Supplier`, `Function`, and `Consumer` functional model. Applications work with bindings; binders connect bindings to middleware systems such as Apache Kafka, RabbitMQ, or Apache Pulsar. To master it effectively, learn in sequence: understand message flows, run a small function, configure the broker, design consumer groups and partitioning, handle errors, test, and only then optimize operations.

## 1. Prerequisites Before Starting

### Java and Spring Boot

Make sure you have a solid grasp of the following:

- Core Java to the point of writing lambdas, method references, generics, records or POJOs, exceptions, and collections.
- Interfaces in `java.util.function`: `Supplier<T>`, `Function<T, R>`, and `Consumer<T>`.
- Spring IoC, dependency injection, beans, configuration via `application.yml`, profiles, and environment variables.
- Spring Boot auto-configuration, logging setup, health indicators, and application packaging.
- Maven or Gradle, dependency management, and BOMs.

Spring Cloud Stream runs inside a Spring Boot application. Learners therefore need to know how to start, configure, and test a Boot application before adding a broker.

### Messaging Foundations

Clearly distinguish the following concepts:

| Concept | Meaning |
|---|---|
| Message / event | Data sent between components; an event typically describes something that happened |
| Producer | Component that creates and sends messages |
| Consumer | Component that receives and processes messages |
| Destination | Resource receiving or emitting messages on the broker, such as a topic, exchange, or queue |
| Binding | Logical bridge between application code and a destination |
| Binder | Adapter connecting Spring Cloud Stream to a specific type of middleware |
| Consumer group | Group of instances sharing the work of reading from a destination |
| Partition | Independent slice of a data stream, typically used to scale in parallel and preserve per-key ordering |

You also need to understand publish-subscribe, competing consumers, acknowledgements, offsets, retention, redelivery, ordering, and backpressure. These concepts determine whether messages are retained, redelivered, or processed concurrently.

### Distributed Systems Knowledge

A consumer may complete business processing yet crash before acknowledging the message. In that case, the broker can redeliver the same message. A producer may send successfully yet lose connectivity before receiving confirmation. Therefore, you need to understand retries, timeouts, duplicates, idempotency, eventual consistency, transaction boundaries, and dead-letter queues.

This foundation prevents assuming a message is always processed exactly once merely because the application uses Spring Cloud Stream.

## 2. Understanding Spring Cloud Stream's Programming Model and Architecture

Spring Cloud Stream uses Spring Cloud Function as its programming model. Business code is expressed as function beans; bindings and binders handle connecting to middleware.

~~~mermaid
flowchart LR
  A["Producer or Supplier"] --> B["Input destination"]
  B --> C["Binder and input binding"]
  C --> D["Function or Consumer"]
  D --> E["Output binding and binder"]
  E --> F["Output destination"]
~~~

The three primary function types play distinct roles:

| Function Type | Input | Output | When to Use |
|---|---|---|---|
| `Supplier<T>` | None | `T` | Producing events from an active source or on a polling schedule |
| `Function<T, R>` | `T` | `R` | Receiving events, processing them, and emitting results |
| `Consumer<T>` | `T` | None | Receiving events to perform an action or persist data |

A standard `Supplier` is invoked by the framework via a poller. The default poller runs every second; it can be adjusted via `spring.integration.poller.fixed-delay`. If events arrive from an external push source, such as a webhook or callback, you can use `StreamBridge` to send data into an output binding instead of forcing that source into a polling `Supplier`.

Default binding names are derived from bean names:

- A `Supplier` named `orderSource` has output binding `orderSource-out-0`.
- A `Function` named `validateOrder` has input binding `validateOrder-in-0` and output binding `validateOrder-out-0`.
- A `Consumer` named `saveOrder` has input binding `saveOrder-in-0`.
- For functions with multiple input parameters or multiple outputs, binding indices increment by position starting from 0.

A binding is a logical name inside the application; a destination is the resource name on the broker. For example, `validateOrder-in-0` can be mapped to topic `orders.created`. Because of this, business code does not need to contain topic, exchange, or queue names.

When an application has multiple function beans, declare which functions to activate via `spring.cloud.function.definition`. Use a semicolon to activate multiple independent functions, such as `validateOrder;writeAudit`. Use `|` to compose functions with compatible types into a pipeline, such as `validateOrder|enrichOrder`.

## 3. Building Your First Application

Your first exercise should process a simple event: receive `OrderCreated`, validate the total amount, and emit `OrderValidated`. This exercise lets you observe the complete flow from payload and function to binding and destination.

### Declaring Events and the Function

~~~java
import java.math.BigDecimal;
import java.time.Instant;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

import java.util.function.Function;

@SpringBootApplication
public class OrderValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderValidationApplication.class, args);
    }

    @Bean
    Function<OrderCreated, OrderValidated> validateOrder() {
        return order -> {
            if (order.total().signum() <= 0) {
                throw new IllegalArgumentException("Order total must be positive");
            }

            return new OrderValidated(
                order.orderId(),
                order.customerId(),
                order.total(),
                Instant.now()
            );
        };
    }

    public record OrderCreated(
        String orderId,
        String customerId,
        BigDecimal total
    ) {}

    public record OrderValidated(
        String orderId,
        String customerId,
        BigDecimal total,
        Instant validatedAt
    ) {}
}
~~~

The function only describes business logic. It does not need to know whether messages flow through Kafka, RabbitMQ, or Pulsar.

### Declaring Bindings

The `application.yml` example below maps input and output to two destinations. Broker connection settings are supplied separately per environment.

~~~yaml
spring:
  application:
    name: order-validation

  cloud:
    function:
      definition: validateOrder

    stream:
      bindings:
        validateOrder-in-0:
          destination: orders.created
          group: order-validation-v1
          content-type: application/json

        validateOrder-out-0:
          destination: orders.validated
          content-type: application/json
~~~

Here:

- `orders.created` is the input destination.
- `order-validation-v1` is a consumer group with a stable name.
- `orders.validated` is the output destination.
- `application/json` specifies how payloads are converted at the Spring Messaging layer.

When running, send a matching JSON payload to `orders.created` and observe the output on `orders.validated`. Test both a valid event and an event with an invalid total to see how exceptions enter the error-handling path.

### Choosing a Binder and Dependency

Add the corresponding binder to the application. Manage versions using a Spring Cloud BOM compatible with your Spring Boot version; do not mix incompatible Spring Cloud Stream release trains manually.

| Middleware | Maven Dependency | Typical Destination Mapping |
|---|---|---|
| Apache Kafka | `org.springframework.cloud:spring-cloud-starter-stream-kafka` | Topic |
| RabbitMQ | `org.springframework.cloud:spring-cloud-starter-stream-rabbit` | Exchange and queue |
| Apache Pulsar | `org.springframework.pulsar:spring-pulsar-spring-cloud-stream-binder` | Topic and subscription |
| Kafka Streams | `org.springframework.cloud:spring-cloud-stream-binder-kafka-streams` | `KStream`, `KTable`, and `GlobalKTable` |

The Kafka binder maps destinations to Kafka topics; consumer groups and partitions map directly to Kafka's corresponding concepts. The Rabbit binder works with exchanges and queues; each group has its own queue mechanism so consumers within the same group compete for messages. The Pulsar binder connects to Pulsar topics and subscriptions. The same functional model can be preserved, while configuration, capabilities, and semantics at the broker layer still differ.

For Kafka, connection settings are commonly configured via `spring.kafka.bootstrap-servers` or corresponding binder properties. RabbitMQ commonly uses `spring.rabbitmq.addresses`. Pulsar commonly uses `spring.pulsar.client.service-url`. Actual values must be supplied by the deployment environment. When packaging multiple binders in one application, explicitly specify the binder per binding if the framework cannot resolve a unique default.

## 4. Consumer Groups and Scalability

Consumer groups determine how multiple instances share an event stream. Group configuration lives on the binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        saveOrder-in-0:
          destination: orders.created
          group: order-storage
~~~

Two common organizational patterns exist:

- Multiple instances in the same group: instances share message processing. Each message is delivered to one member of the group according to the broker's mechanism.
- Multiple distinct groups: each group receives a logical copy of the event stream. For example, `order-storage` persists data, `order-notification` sends notifications, and `order-analytics` updates statistics.

In Kafka, the group ID ties into offset management and partition assignment. In RabbitMQ, the binder creates queues corresponding to the destination and group. In Pulsar, subscriptions govern consumption mode; choose a subscription type matching your load-sharing or multi-consumer broadcast needs.

Assign stable group names to applications that must resume reading after restarts. Changing the group name can turn the application into an independent consumer group and either replay or skip data depending on configured starting offsets. Never use anonymous groups for business streams that require offset tracking, replay, or DLQs.

When scaling instance counts, monitor partition counts, consumer counts, and processing rates. With Kafka, a group cannot utilize more active parallel consumers than assigned partitions; excess consumers will remain idle. Adding instances without increasing partitioning does not necessarily increase throughput.

## 5. Partitions, Keys, and Processing Order

Partitioning splits a data stream into multiple segments for parallel processing. If events for the same order must be processed in sequence, use `orderId` as the partition key. If you need to group data per customer, you can use `customerId`.

Example partition-key configuration on an output binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          producer:
            partition-key-expression: payload.customerId
            partition-count: 12
~~~

The framework computes the partition from the selected key. The consumer side must be configured compatibly with the partition count and instance distribution. For binders that rely on generic partitioning support, you may need `consumer.partitioned`, `spring.cloud.stream.instance-count`, and `spring.cloud.stream.instance-index`. Kafka uses Kafka's native rebalance mechanism by default; setting these instance properties is unnecessary in normal cases unless you explicitly disable auto-rebalance or use custom allocation.

Key principles:

- Events with the same key typically route to the same partition, preserving ordering within that partition.
- There is no global ordering guarantee across multiple partitions.
- Skewed key distributions can create hot partitions, turning one consumer into a bottleneck.
- Changing partition counts can alter key-to-partition mappings; assess impacts on ordering and state before scaling partitions.
- Partitioning should be designed around business keys and desired parallelism, not solely around current instance counts.

## 6. Message Design and Schema Management

A message contract is an agreement between producer and consumer. Avoid sending raw database entities or internal objects that can change arbitrarily. Define events independently of persistence models.

An event can carry the following fields:

~~~json
{
  "eventId": "evt-10001",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "occurredAt": "2026-11-24T10:15:30Z",
  "orderId": "ord-9001",
  "customerId": "cus-2001",
  "total": 125000
}
~~~

`eventId` supports duplicate prevention; `eventType` identifies the event kind; `schemaVersion` identifies the contract version; and `occurredAt` records when the business action happened. Correlation IDs and trace context can travel in headers to link logs and traces across services.

Early on, `application/json` and Spring Cloud Stream's message converters are often sufficient. When multiple applications or multiple languages exchange data, manage schemas explicitly. Schema Registry supports schema registration and lookup; Avro converters can reconcile the producer's writer schema with the consumer's reader schema. With Pulsar, you can use Pulsar native schemas via `use-native-encoding` and `use-native-decoding`, along with `schema-type` and `message-type` in extended binding properties.

When evolving schemas:

- Prefer adding optional fields with default values.
- Avoid renaming, deleting, or changing the meaning of fields currently used by consumers.
- Define backward, forward, or full compatibility rules aligned with your deployment strategy.
- Test new producers against old consumers and vice versa before releasing.
- Do not rely solely on Java class names as an inter-service contract.

## 7. Retries, Errors, and Dead Letter Queues

Not every error should be retried. Transient network glitches, brief broker interruptions, or overloaded downstream services can recover on their own. Malformed data, business-rule violations, or missing required fields usually cannot be fixed by immediately resending.

Generic retry configuration for a consumer binding can start as follows:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        validateOrder-in-0:
          consumer:
            max-attempts: 4
            back-off-initial-interval: 1000
            back-off-max-interval: 10000
            back-off-multiplier: 2.0
~~~

`max-attempts` is the total number of attempts, including the initial processing try. Backoff increases the wait time between attempts to avoid hammering an unhealthy downstream service. Set limits consistent with downstream timeouts and the maximum processing duration permitted by the broker.

After exhausting retries, a Dead Letter Queue or Dead Letter Topic holds failed messages for investigation and reprocessing. DLQ configuration depends on the binder.

With Kafka, explicitly set `group` and enable DLQ in extended binding properties:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        validateOrder-in-0:
          group: order-validation-v1
      kafka:
        bindings:
          validateOrder-in-0:
            consumer:
              enable-dlq: true
~~~

With RabbitMQ, the binder provides `auto-bind-dlq` to provision the corresponding dead-letter infrastructure:

~~~yaml
spring:
  cloud:
    stream:
      rabbit:
        bindings:
          validateOrder-in-0:
            consumer:
              auto-bind-dlq: true
~~~

With Pulsar, configure the dead-letter policy according to Pulsar consumer capabilities and the active binder version. Never copy Kafka or RabbitMQ DLQ properties to Pulsar because property names and semantics differ.

A DLQ requires an assigned owner or procedure. Record the error cause, original destination, timestamp, `eventId`, and attempt count; configure appropriate retention; alert when DLQ depth rises; and build a workflow to inspect, fix data or code, and redrive under control. Redriving must still be safe if an event was previously partially processed.

## 8. Stateful Processing with Kafka Streams

The standard Kafka binder passes message payloads into `Supplier`, `Function`, or `Consumer`. When you need stateful stream processing—such as per-customer counts, time-windowed aggregations, joining two streams, or maintaining continuously updated tables—learn the Kafka Streams binder.

The Kafka Streams binder supports primary abstractions:

- `KStream` represents a sequence of event records; each record is an independent event.
- `KTable` represents the latest state per key; newer records update the value for that key.
- `GlobalKTable` is a state table replicated across instances for global lookups.

The following example counts order events per `customerId`. Producers must set `customerId` as the record key so `groupByKey` groups events properly:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Configuration;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.Materialized;
import org.springframework.context.annotation.Bean;

@Configuration
public class CustomerOrderCountTopology {

    @Bean
    Function<KStream<String, String>, KStream<String, Long>> countOrdersByCustomer() {
        return orders -> orders
            .groupByKey()
            .count(Materialized.as("orders-by-customer"))
            .toStream();
    }
}
~~~

Binding and application ID configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: countOrdersByCustomer
    stream:
      bindings:
        countOrdersByCustomer-in-0:
          destination: orders.created
        countOrdersByCustomer-out-0:
          destination: orders.by-customer
      kafka:
        streams:
          binder:
            application-id: customer-order-counts
~~~

The state store named `orders-by-customer` holds materialized state. The Kafka Streams binder can auto-create state stores when using the appropriate DSL; with the Processor API or custom needs, declare stores explicitly. Local state stores are restored from changelog topics on instance restarts, so you must manage application IDs, internal topic permissions, disk capacity, and restore times.

You can query stores inside the application via `InteractiveQueryService`. When running multiple instances, the queried key may live on another instance; the caller must resolve the host owning the key and route the request to that instance. Stores may also not be immediately ready right as the application boots, so queries need retries or readiness checks.

## 9. Layered Testing

Do not test solely by starting the application and sending one manual message. Build these testing layers:

1. Unit tests for function logic: valid inputs, invalid inputs, boundary cases, and exceptions.
2. Test binder tests for in-JVM binding flows: send messages to `InputDestination`, receive messages from `OutputDestination`, and inspect payloads.
3. Integration tests against a real broker: run Kafka, RabbitMQ, or Pulsar in a test environment, such as via Testcontainers.
4. Contract tests: verify schemas, content types, headers, and compatibility between producers and consumers.
5. Failure tests: broker disconnects, slow consumers, repeated exceptions, DLQs, redelivery, and redrive.
6. Load tests: measure throughput, latency, consumer lag, CPU/memory usage, and partition scalability.

The test binder requires no real broker and excels at verifying input/output wiring inside the application. However, it does not prove that Kafka, RabbitMQ, or Pulsar configuration works properly. Broker-dependent behaviors like partition assignment, acknowledgements, transactions, retries, and DLQs must be verified with integration tests.

## 10. Delivery Guarantees and Business Correctness

In distributed systems, duplicate processing is a normal scenario to design for upfront. A consumer can persist data successfully and stop before acknowledgement or offset commit completes. The broker redelivers the message and business logic may run again.

Design consumers to be idempotent: processing the same `eventId` multiple times produces the same final outcome as processing it once. You can save processed `eventId` values inside the same transaction as business updates, enforce unique constraints, or perform upserts keyed by business identifiers. For calls to external services, use idempotency keys or corresponding reconciliation mechanisms.

If an application both updates a database and emits an event, avoid executing two independent operations without coordination. Transactional outbox writes the business change and an outbox record in the same database transaction; a separate process publishes outbox events to the broker. On the consumer side, an inbox or deduplication table can prevent duplicate processing.

The Kafka binder supports transactions for read-process-write flows within Kafka's transaction boundary. Transaction configuration requires a unique transaction ID prefix per instance. This mechanism does not automatically create distributed transactions across databases or REST services. When external side effects exist outside Kafka, you still need outbox, inbox, idempotency, or compensating workflows.

Do not claim a system has end-to-end exactly-once semantics just because broker transactions are enabled. Document exact guarantee boundaries: how durably the producer sends, how the broker persists data, when the consumer acknowledges, whether business side effects resist duplicates, and how the DLQ is recovered.

## 11. Bringing the Application into Production

Before deploying to production, complete the following areas:

### Configuration and Security

- Separate configuration per environment; destinations, groups, broker URLs, and concurrency should not be hardcoded.
- Retrieve passwords, tokens, certificates, and credentials from a secrets manager or your platform's secret store.
- Enable TLS and broker authentication; grant least-privilege permissions for producers, consumers, and topic/queue administration.
- Explicitly define who is allowed to auto-create destinations. In production, provisioning topics, queues, partitions, and retention usually needs to be governed through infrastructure workflows.

### Observability

Monitor at a minimum:

- Inbound/outbound message counts and processing rates.
- Consumer lag or backlog, queue wait time, and processing latency.
- Retry counts, DLQ message counts, redelivery counts, and age of the oldest message.
- Broker connection health, rebalances, serialization errors, and processing errors.
- For Kafka Streams: processor status, state store restore duration, state size, and store query health.

Logs should include `eventId`, `eventType`, correlation ID, function name, binding, group, and partition/offset details when supplied by the broker. Avoid logging full payloads if they contain sensitive data. Use distributed tracing to follow an event across services.

### Deployment and Scaling

- Keep group IDs stable across deployments if you want to continue reading the same offset stream or subscription.
- Use a stable application ID for each Kafka Streams topology; distinct logical applications need separate IDs.
- Ensure partition counts, instance counts, and concurrency match target throughput.
- Configure readiness checks to avoid taking traffic before broker connections and required dependencies are ready.
- Give the application an adequate shutdown grace period to finish in-flight work and cleanly close consumers/producers.
- For Kafka Streams, account for state store recovery time after restarts and local disk capacity.
- Test rolling deployments, scale up/down, broker disconnects, and incident recovery before release.

## 12. Learning Sequence and Completion Criteria

You can follow this milestone-based roadmap:

| Milestone | Hands-On Practice | Completion Criteria |
|---|---|---|
| 1. Foundations | Java functions, Spring Boot, messages, topics/queues, groups, and acknowledgements | Can explain producers, consumers, destinations, bindings, and binders |
| 2. First application | Write `Function<OrderCreated, OrderValidated>` and run with one binder | Send a message to input and receive the result on output |
| 3. Supplier and Consumer | Create a polling source, input-only consumer, and function composition | Accurately distinguish triggers and bindings for each function type |
| 4. Brokers | Run the same business flow on Kafka, RabbitMQ, or Pulsar | Know how to configure connections, destinations, groups, and binders |
| 5. Scaling and ordering | Run multiple instances, set keys, and partition streams | Can explain parallelism limits and per-partition ordering |
| 6. Contracts and errors | Design schemas, retries, DLQs, and redrive | Can test schema compatibility and failed-message paths |
| 7. Kafka Streams | Write `KStream`/`KTable`, materialize state stores, and query them | Can restore state after restarts and understand interactive query routing |
| 8. Testing and operations | Test binder, real brokers, metrics, tracing, security, and deployment | Can diagnose lag, retries, DLQs, connection errors, and duplicates in staging |

Complete each milestone with a small runnable application and an automated test suite. Only move to the next milestone once you can explain the current configuration and observe message behavior inside the broker.

## 13. Official References

- [Spring Cloud Stream Reference](https://docs.spring.io/spring-cloud-stream/reference/index.html) — architecture, bindings, binders, and general configuration.
- [Functional binding names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html) — binding naming rules for `Supplier`, `Function`, and `Consumer`.
- [Consumer groups](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/consumer-groups.html) and [Partitioning](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-partitioning.html) — load sharing, groups, and partitioning.
- [Error handling](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html) — retries and failed-message handling.
- [Kafka binder DLQ](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/dlq.html) and [RabbitMQ binder](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-rabbit.html) — broker-specific configuration.
- [Pulsar binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html) — dependencies, message conversion, schemas, and topic provisioning.
- [Schema Registry](https://docs.spring.io/spring-cloud-stream/reference/schema-registry/spring-cloud-stream-schema-registry.html) — schema management and schema evolution.
- [Kafka Streams binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/usage.html), [State Store](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/state-store.html), and [Interactive Queries](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/interactive-queries.html) — stateful stream processing.
- [Testing](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html) — test binder and testing binding flows.
