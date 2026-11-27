# From Synchronous Calls to Event-Driven Processing

In a small application, the easiest way to coordinate components is usually direct invocation: the order service calls the validation service, waits for the result, and then calls the inventory service. This approach works well when the caller needs an immediate answer and the number of components is small. As the system grows, each direct call introduces another dependency on the called service's address, protocol, response time, and availability.

Event-driven processing changes how that coordination works. The emitting component records that something happened and sends a message through messaging infrastructure. Components interested in the event can receive and process it independently. Spring Cloud Stream provides a programming model and integration layer so Java applications can work with messaging systems like Kafka, RabbitMQ, or Pulsar without coupling all business logic to each broker's proprietary API.

This lesson opens the **Overview** chapter of the `SPRING_CLOUD_STREAM` module. The module progresses from the `Supplier`/`Function`/`Consumer` functional model, bindings, and binders to consumer groups, partitioning, message schemas, retries/DLQ, stateful processing with Kafka Streams, testing, and delivery guarantees in production. To build a solid foundation for later topics, you first need to understand why a system moves from synchronous calls to event exchange, as well as the trade-offs involved.

## 1. How Do Synchronous Calls Work?

In the synchronous model, the caller sends a request to a specific component and typically blocks its processing thread until a response arrives or a timeout expires. For example, when a customer places an order, the application might sequentially call the order validation service, the inventory service, and the payment service.

```text
Ordering Application
    |-- HTTP: validate order ------> Order Service
    |<-- HTTP: valid --------------|
    |-- HTTP: reserve stock -------> Inventory Service
    |<-- HTTP: reserved -----------|
    |-- HTTP: process payment -----> Payment Service
    |<-- HTTP: succeeded ----------|
    |
    +-- return result to customer
```

Characteristics of this coordination style:

- **Known recipient:** the caller must know the endpoint or client used to reach the target service.
- **Temporal coupling:** the target service must respond within a timeout acceptable to the caller.
- **Centralized control flow:** the caller decides the invocation order, how to handle responses, and often how to retry.
- **Immediate result:** convenient when the UI needs to know right away whether the operation succeeded or failed.

Synchronous calls are not the wrong choice. They fit queries requiring immediate responses, direct interactive operations, and steps where the outcome of the previous step immediately dictates the next. Problems arise when a single request has to fan out across too many services or when components need to operate independently of one another.

## 2. Why Do Chains of Direct Calls Become Hard to Scale?

Suppose the ordering service calls three different services. If the inventory service is slow, the ordering flow must wait even though recording the order may already be done. If the payment service is temporarily unavailable, the caller must decide whether to hold the connection, retry, roll back, or return an error. When multiple services slow down at once, latencies add up and tie up many threads or connections in the system.

Several common forms of coupling appear:

| Coupling Type | Symptom | Consequence |
|---|---|---|
| Location coupling | Caller knows the recipient's URL, service name, or client | Deployment changes can force changes in the caller |
| Temporal coupling | Caller waits for a direct response | An outage or high load in one service cascades to its callers |
| Deployment coupling | Both sides must coordinate when APIs change | Hard to deploy and scale each component independently |
| Business flow coupling | One service orchestrates multiple sequential calls | Centralized orchestration logic and difficulty handling late-arriving tasks |

Retrying synchronous calls also requires care. If the caller retries when the previous request was already processed but the response was lost, the operation may execute twice. If many callers retry in lockstep, traffic spikes can prolong an incident. Timeouts, retry limits, backoff, and idempotency still need to be designed even when using messaging.

## 3. Event-Driven Thinking

In an event-driven architecture, the emitting component publishes an event describing what occurred, such as `OrderPlaced`, `PaymentAuthorized`, or `InventoryReserved`. The emitter does not need to directly call each service that will react to the event. A broker receives and delivers the message to registered consumers.

```text
                       +----------------------+
                       |       Broker         |
                       | topic / queue        |
                       +----------+-----------+
                                  ^
                                  | publish event
                                  |
+------------------+              |
|  Order Service   |--------------+
+------------------+
                                  |
                 +----------------+----------------+
                 |                                 |
                 v                                 v
       +-------------------+             +--------------------+
       | Inventory Consumer|             | Notification Cons. |
       +-------------------+             +--------------------+
```

The typical processing sequence is:

1. A business action occurs in the producing application, such as an order being created.
2. The application turns the event into a message and sends it to the configured destination.
3. The broker stores or routes the message according to its mechanism.
4. Consumers receive the message via an input binding and perform their own work.
5. A consumer may finish processing or emit a new event for the next step to continue.

An event should express a fact that has already happened, usually named in the past tense like `OrderPlaced`. By contrast, a command like `ReserveInventory` expresses a request for the recipient to perform an action. Distinguishing these two concepts helps make contracts clearer: an event announces what happened; a command requests an action and usually has one responsible handler.

Consumers can be developed and deployed independently. The order service only needs to publish an event contract understood by interested parties. The inventory service can reserve stock; the notification service can send emails; the analytics service can update metrics. When adding a new consumer, you usually do not have to modify direct call flows in the emitting service.

## 4. Benefits and Trade-Offs

Event exchange reduces direct coupling between services and helps absorb load better when the broker provides buffering. Consumers can scale their instance count to match message volume and processing capacity. A consumer that is stopped briefly can catch up on messages retained by the broker once it comes back online, depending on configuration and retention policies.

In return, the system becomes asynchronous. The publisher usually only knows that the message was sent according to the acknowledgment level provided by the infrastructure; it does not mean every consumer has finished its business processing. State may become consistent after a delay rather than changing atomically within a single request. Users and related services must accept or represent intermediate states such as `PENDING`, `PROCESSING`, or `CONFIRMED`.

| Aspect | Synchronous Call | Event-Driven Processing |
|---|---|---|
| Communication | Call a service and wait for a response | Send a message; consumers process later |
| Coupling | Caller knows the recipient and API | Publisher depends on the message contract and destination |
| Completion time | Usually within the request duration | May complete after the initial request |
| Scaling | Usually scales with the called service | Can scale consumers based on message volume |
| Resilience | Must handle timeouts and retries in the call flow | Can buffer, replay, or route failed messages depending on broker and config |
| Complexity | Easy to trace in short flows | Must manage schemas, duplicates, ordering, retries, and cross-service observability |

You should not turn every call into a message. A query that needs immediate data can still use HTTP or a request-response protocol. A real-world system usually combines both styles: synchronous for interactions needing instant feedback, asynchronous for tasks that can be processed later or interest multiple parties.

## 5. Where Does Spring Cloud Stream Fit In?

Spring Cloud Stream is a framework for building message-driven applications on Spring Boot. It provides a functional model and abstractions so business logic works with messages through **bindings**. A **binder** connects an application's bindings to a specific messaging system such as Kafka, RabbitMQ, or Pulsar.

You can picture the layers as follows:

```text
Application Logic
  Supplier / Function / Consumer
            |
            v
     Application Binding
            |
            v
          Binder
            |
            v
  Kafka / RabbitMQ / Pulsar
```

Three concepts to distinguish:

- **Message:** the unit of data transferred, usually consisting of a payload and headers. The payload carries business content; headers can carry information such as content type, correlation ID, or routing metadata.
- **Binding:** the logical connection point between a function in the application and the message stream. A binding name is typically derived from the function name and its input/output role.
- **Binder:** the integration adapter that communicates with the broker. The binder maps bindings to the corresponding constructs of Kafka, RabbitMQ, or Pulsar.

`destination` is the name of the target resource on the broker, such as a topic or queue depending on the binder type. A destination name and a binding name serve different purposes: a binding is the connection point name inside the application; a destination is where messages are sent to or read from. Switching brokers mainly affects binder dependencies and configuration, while function logic can stay unchanged if the message contract and required semantics remain compatible.

## 6. The Supplier, Function, and Consumer Functional Model

Spring Cloud Stream integrates with Spring Cloud Function. An application can represent message-processing roles using three familiar function types:

| Function Type | Role | Typical Bindings |
|---|---|---|
| `Supplier<T>` | Produces output data to emit messages | `<functionName>-out-0` |
| `Function<T, R>` | Receives data, processes it, and produces output data | `<functionName>-in-0`, `<functionName>-out-0` |
| `Consumer<T>` | Receives and processes data without producing function output | `<functionName>-in-0` |

`Supplier` fits when the application proactively generates messages, such as periodically reading data to publish. For an ordinary supplier, the framework invokes the function via polling; the polling interval must be chosen carefully to avoid emitting too frequently or missing business requirements. `Function` fits a transformation or validation step. `Consumer` fits a terminal processing step such as updating inventory or sending notifications. An application can use a single role or combine multiple functions.

The following example illustrates a function that validates an order event and emits a confirmation event. The records only describe the payload to keep focus on the processing flow; in a real application, they should be placed in appropriate packages and contracts.

```java
import java.math.BigDecimal;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderPlaced(String orderId, BigDecimal total) {}

record OrderAccepted(String orderId, BigDecimal total) {}

@Configuration
class OrderEventFunctions {

    @Bean
    Function<OrderPlaced, OrderAccepted> validateOrder() {
        return event -> {
            if (event.orderId() == null || event.orderId().isBlank()) {
                throw new IllegalArgumentException("orderId is required");
            }
            if (event.total() == null || event.total().signum() <= 0) {
                throw new IllegalArgumentException("total must be positive");
            }

            return new OrderAccepted(event.orderId(), event.total());
        };
    }
}
```

When the `validateOrder` function is selected as the function definition, Spring Cloud Stream creates input and output bindings by convention. The YAML configuration example below connects them to two destinations:

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
          destination: orders.accepted
          content-type: application/json
```

The application needs the binder dependency corresponding to the chosen broker and broker connection configuration per deployment environment. The example above uses the default binding names derived from the function; `orders.placed` and `orders.accepted` are destinations. The `group` property assigns a consumer group to the input binding so instances in the same group coordinate consumption according to the broker's capabilities. Details on groups, partitions, and message distribution will be covered in dedicated lessons.

The example function throws an exception when data is invalid to illustrate where errors can arise. A production application must clearly decide which errors are retried, which go to a dead-letter queue (DLQ), how to log, and how to ensure safe duplicate handling. Returning from a function or having the binder send a message should not be treated as proof that every downstream consumer has completed the entire business workflow.

## 7. A Message Is a Contract Between Components

When two services communicate via messages, the payload becomes a contract that both publisher and subscriber depend on. The contract needs clear field names, stable data types, and rules for handling added, removed, or modified fields. Several useful principles:

- Name events after the business fact that occurred, such as `OrderPlaced`.
- Include an event identifier or business identifier so consumers can detect duplicate messages.
- Consider timestamps, schema versions, and a correlation ID when tracing a business flow is needed.
- Avoid putting secrets or unnecessary personal data into payloads.
- Agree on schema compatibility rules before deploying producers and consumers at different versions.

Not every message has a single copy or arrives in global order. Kafka typically organizes data by topics and partitions; RabbitMQ has exchanges, queues, and routing; Pulsar has topics and subscriptions. Each binder maps Spring Cloud Stream bindings to the broker's own concepts and capabilities. Therefore, you need to understand the semantics of the broker in use rather than assuming all binders behave identically.

## 8. Challenges to Address in Asynchronous Processing

Event-driven architecture reduces direct coupling but introduces operational responsibilities. The following questions must be answered in the design:

1. **Can a message be delivered multiple times?** Consumers should be idempotent: processing the same event again must not duplicate business effects. You can use an event ID, unique key, or inbox table to detect already-processed messages.
2. **What ordering must be preserved?** If events for the same order must be processed in sequence, choose a key, partition, or serialization mechanism suited to the broker and binder.
3. **What happens when a consumer fails?** Define retry counts, backoff intervals, retryable exception types, and where to store unprocessable messages. A DLQ helps isolate failed messages for investigation and controlled reprocessing.
4. **Can a producer write business data but fail to send the event?** If updating the database and sending the message are not inside a guaranteed distributed transaction, transactional outbox is a common pattern to record the event to publish in the same data transaction and forward it afterward.
5. **How do you know where a message is?** You need logs with correlation IDs, metrics for ingress/egress rates, latency, retry counts, backlog, and alerts when consumers fall behind.
6. **Is state or computation over a continuous stream needed?** Kafka Streams and stateful processing mechanisms can maintain keyed state, time windows, or topologies; they require separate design and testing.

Delivery guarantees such as at-most-once, at-least-once, and configurations approaching exactly-once depend on the broker, binder, transactions, and how the application processes data. Do not claim a system has exactly-once just because a configuration property was enabled. Idempotency and business transaction boundaries remain essential parts of the design.

## 9. When to Choose Each Approach?

Use synchronous calls when the caller needs data right away to continue the interaction, such as looking up current pricing or checking access permissions. Consider events when a business action has happened and multiple components can react independently, such as an order being created requiring inventory updates, notifications, and analytics recording.

An ordering workflow can combine both:

1. The API receives the order request and synchronously validates required fields to respond quickly.
2. The service saves the order together with the event to publish using an appropriate guarantee mechanism, such as transactional outbox.
3. A forwarding process publishes `OrderPlaced` to the broker.
4. Independent consumers handle inventory reservation, payment, or notification in their own workflows.
5. When results arrive, services emit follow-up events such as `InventoryReserved` or `PaymentAuthorized`; the order status updates as the workflow progresses.

With this approach, the API can return an accepted status instead of waiting for every background task to finish. The UI should display intermediate states and provide a way to query or receive updates when the workflow completes.

## 10. A Safe Transition Path

You do not need to convert an entire system to event-driven all at once. You can start with a business capability that has clear boundaries and low need for instant feedback:

1. Identify the business event and the exact point when the event is considered to have occurred.
2. Design the payload, identifiers, schema, and compatibility rules.
3. Select the broker, binder, and destination based on retention, routing, ordering, load, and operational requirements.
4. Write a small producer and consumer; make the consumer resilient to duplicate messages.
5. Set up retries, DLQ, timeouts, metrics, logs, and alerts before increasing traffic.
6. Test happy paths, transient failures, malformed data, consumer restarts, duplicate messages, and schema changes.
7. Roll out incrementally, observe backlog and latency, and only then scale consumer counts or add subscribers.

In Spring Cloud Stream, subsequent lessons will make this path concrete: how to configure bindings and binders; how to choose consumer groups and partitions; how to convert payloads and manage schemas; how to handle errors, retries, and DLQs; how to use Kafka Streams for stateful processing; and how to test, observe, secure, tune, and deploy applications.

## 11. Self-Check

- [ ] Can explain why chains of synchronous calls create temporal and availability coupling.
- [ ] Can distinguish an event describing what happened from a command requesting an action.
- [ ] Can describe the roles of message, binding, binder, and destination in Spring Cloud Stream.
- [ ] Can identify when to use `Supplier`, `Function`, or `Consumer`.
- [ ] Understands that asynchronous processing requires designing for duplicates, ordering, errors, schemas, and observability.
- [ ] Knows that binders simplify broker integration without erasing semantic differences across Kafka, RabbitMQ, and Pulsar.

## Conclusion

Moving from direct calls to event exchange enables components to react independently and scale on demand, but it also makes workflows asynchronous and requires managing message contracts, state, errors, and observability. Spring Cloud Stream helps structure applications around processing functions and bindings, while the binder connects the application to the broker. Understanding the boundary between business logic, bindings, and messaging infrastructure gives you the foundation to design reliable and operable event flows.
