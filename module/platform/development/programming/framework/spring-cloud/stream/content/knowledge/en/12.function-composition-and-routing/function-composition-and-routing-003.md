# Distinguishing In-Process Composition from Connecting Applications via a Broker

In Spring Cloud Stream, multiple event-processing steps can be organized in two ways. Functions can be composed directly within the same process using Spring Cloud Function, or each application can perform part of the work and exchange messages via Kafka, RabbitMQ, or Pulsar. Both approaches form a multi-step business workflow, but they differ in execution boundaries, delivery semantics, deployment, scalability, and error handling.

In-process function composition fits when steps belong to the same application, need direct invocation, and can be deployed together. Connecting applications via a broker fits when capabilities need independence in lifecycle, scale, technology, or ownership. The choice should be driven by operational requirements and data contracts, not merely the number of steps in a diagram.

## 1. Two ways to organize a processing flow

Suppose an **OrderCreated** event needs to be enriched with customer information, validated against rules, and persisted.

With in-process composition, a single application can invoke Functions sequentially:

~~~mermaid
flowchart LR
    A[Input binding] --> B[enrichOrder]
    B --> C[validateOrder]
    C --> D[Output binding]
~~~

Messages are passed from one function to the next within the same process. The broker participates only at the input or output of the entire chain if the application has corresponding bindings.

With independent applications connected via a broker, each step can run in its own process:

~~~mermaid
flowchart LR
    A[Order API] --> B[Topic orders]
    B --> C[Order enrichment service]
    C --> D[Topic enriched-orders]
    D --> E[Validation service]
    E --> F[Topic validated-orders]
    F --> G[Order persistence service]
~~~

Here the broker sits between applications. Each application receives messages from its own destination, processes them, and emits new events to the next destination. The broker establishes the messaging and storage boundary according to its policies.

## 2. Composing functions in the same process

Spring Cloud Function allows composing Function beans using the **|** symbol in the **spring.cloud.function.definition** property. The output of the preceding function becomes the input of the next function. The data types at both ends must be compatible.

For example, an application with two steps:

~~~java
@Configuration
public class OrderFunctions {

    @Bean
    public Function<OrderCreated, OrderEnriched> enrichOrder(
            CustomerDirectory customers) {
        return order -> {
            Customer customer = customers.find(order.customerId());
            return new OrderEnriched(
                    order.orderId(),
                    order.customerId(),
                    customer.segment(),
                    order.total()
            );
        };
    }

    @Bean
    public Function<OrderEnriched, OrderValidated> validateOrder(
            OrderRules rules) {
        return order -> {
            rules.validate(order);
            return new OrderValidated(
                    order.orderId(),
                    order.customerId(),
                    order.segment(),
                    order.total(),
                    true
            );
        };
    }
}
~~~

Declaring the function chain:

~~~yaml
spring:
  cloud:
    function:
      definition: enrichOrder|validateOrder
~~~

Spring Cloud Function creates a composite Function. When this Function is invoked with **OrderCreated**, it calls **enrichOrder**, obtains **OrderEnriched**, and passes the result to **validateOrder** to receive **OrderValidated**.

Do not confuse **|** with the semicolon in a function definition list. The **|** operator composes functions into a sequential call chain. The semicolon selects multiple independent functions; it does not automatically pass the output of one function to the input of another and does not create a broker boundary.

When using that function chain as a Spring Cloud Stream processing endpoint, the composite function is bound as a single endpoint. You can configure destinations for the composite function's input and output bindings. The default binding names are formed from the composite function definition; if you want more manageable names, you can use Spring Cloud Stream's binding mapping mechanism. Verify the generated binding names in your project's version and use those exact names in configuration.

You can assign short aliases to the two bindings of the composite function to make destination configuration easier to read:

~~~yaml
spring:
  cloud:
    function:
      definition: enrichOrder|validateOrder
    stream:
      function:
        bindings:
          "enrichOrder|validateOrder-in-0": orders-in
          "enrichOrder|validateOrder-out-0": validated-out
      bindings:
        orders-in:
          destination: orders
          group: order-processing-v1
        validated-out:
          destination: validated-orders
~~~

The two keys in **spring.cloud.stream.function.bindings** are the default binding names of the composite function; the values **orders-in** and **validated-out** are the aliases used in the **spring.cloud.stream.bindings** configuration section. This mapping lets destinations and groups be declared with short names while keeping a clear distinction between the chain's binding and the alias binding name. Do not assume that the single bean name **enrichOrder-in-0** serves as the input of the entire chain.

### How is data forwarded?

When composing functions in the same process, the Java return value of the previous function is passed directly to the next function according to the data type contract. There is no broker publish/consume round trip between the two steps unless application logic itself explicitly sends additional messages.

This yields several characteristics:

- No need to serialize and deserialize data between individual functions.
- No network hop or broker round trip between steps.
- Steps share the same process, configuration, classpath, and runtime resources.
- An unhandled error in a function propagates up the call chain and fails the current invocation.
- Steps are typically deployed, scaled, and rolled back as a single application unit.

Function composition does not automatically create distributed transactions or intermediate persistence checkpoints. If the first step calls an external service and a later step fails, that external side effect is not automatically rolled back. Design idempotency, local transactions, or compensating mechanisms when required by the business logic.

## 3. Connecting independent applications via a broker

When steps need to be independent, each application can own one part of the event flow. An application publishes events to a destination; the next application registers an input binding to receive them.

For example, an API application publishes order events using StreamBridge:

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: ordersOut
      bindings:
        ordersOut:
          destination: orders
          content-type: application/json
~~~

~~~java
@Service
public class OrderEventPublisher {

    private final StreamBridge streamBridge;

    public OrderEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(OrderCreated event) {
        return streamBridge.send("ordersOut", event);
    }
}
~~~

The customer enrichment application runs independently and consumes from the same destination:

~~~java
@Bean
public Function<OrderCreated, OrderEnriched> enrichOrder(
        CustomerDirectory customers) {
    return event -> {
        Customer customer = customers.find(event.customerId());
        return new OrderEnriched(
                event.orderId(),
                event.customerId(),
                customer.segment(),
                event.total()
        );
    };
}
~~~

~~~yaml
spring:
  cloud:
    function:
      definition: enrichOrder
    stream:
      bindings:
        enrichOrder-in-0:
          destination: orders
          group: order-enrichment-v1
          content-type: application/json
        enrichOrder-out-0:
          destination: enriched-orders
          content-type: application/json
~~~

Another order validation application can consume from **enriched-orders**, use its own group, and emit **OrderValidated** to the **validated-orders** destination. Each application can be packaged, deployed, configured, and scaled separately.

In this model, the broker is the boundary between processes. Data must have a stable wire format; producer and consumer must agree on schema, content type, versioning, and rules for handling invalid messages.

## 4. Direct comparison

| Criterion | In-process composition | Connecting applications via broker |
|---|---|---|
| Boundary | Functions within the same process. | Independent applications or processes. |
| Data transfer | Function invocation passing Java objects. | Serialize, publish, broker stores/routes, consumer deserializes. |
| Latency | Typically lower due to no network hop between steps. | Adds overhead of sending, storing, and receiving messages. |
| Loose coupling | Steps depend on the same runtime and application configuration. | Applications communicate through message contracts. |
| Deployment | Usually released together as one artifact. | Each application can be released independently. |
| Scaling | Scale the entire application or within runtime limits. | Each consumer group/service can scale independently. |
| Fault isolation | Errors can fail the entire composite invocation. | Broker can retain messages while a consumer is paused; failures still need retry/DLQ. |
| Intermediate persistence | No automatic storage point between functions. | Broker can persist messages at each boundary per retention/queue policy. |
| Schema | Steps can share Java types in the same codebase. | Requires compatible wire contracts across application versions. |
| Observability | Follow traces and logs in a single process. | Requires correlation/trace context across the broker and multiple services. |
| Delivery | Depends on processing of the outermost binding and internal logic. | Depends on acknowledgments, offsets/cursors, retries, and per-broker configuration. |

Neither choice is universally better. Function composition keeps a processing chain concise and efficient inside one application. A broker fits when you need operational boundaries and resilience between independent capabilities.

## 5. Differences in errors and delivery

In function composition, if **enrichOrder** throws an exception, **validateOrder** does not receive a result for that call. The error propagates via in-process invocation mechanics. If the chain is triggered by an input binding, the binder's error-handling, retry, and dead-letter behaviors still apply at that binding boundary as configured. There is no separate broker-acknowledged intermediate message between **enrichOrder** and **validateOrder**.

In an application chain connected via a broker, each boundary can have its own delivery state:

1. Producer sends an event to the broker.
2. Broker acknowledges receipt according to binder and broker mechanics.
3. Consumer receives and processes the event.
4. Consumer acknowledges or commits progress according to broker semantics.
5. If processing fails, the message can be retried or routed to a DLQ as configured.
6. The next application receives the output event only after the previous step publishes successfully.

This provides buffering and the ability to resume after an application stops. However, you should not interpret a broker as guaranteeing end-to-end business exactly-once processing. A producer may resend after a timeout, a consumer may reprocess after a lost ACK or incomplete commit, and effects on databases outside the broker must be protected separately.

### Idempotency and business side effects

Suppose a consumer has written an order to the database but stops before the offset is committed. On restart, the broker may redeliver the same event. The consumer should use **eventId** or a business key to detect duplicate processing.

~~~java
@Transactional
public void apply(OrderValidated event) {
    if (processedEventRepository.existsByEventId(event.eventId())) {
        return;
    }

    orderRepository.markValidated(event.orderId());
    processedEventRepository.save(event.eventId());
}
~~~

This snippet illustrates the idea; enforcing uniqueness requires appropriate database unique constraints and transactions. If updating the database and publishing the next event must be consistent, consider a transactional outbox or equivalent integration pattern. Calling StreamBridge inside a **@Transactional** method does not automatically create an atomic transaction spanning both the database and the broker.

## 6. Differences in ordering and partitioning

Within the same process, the invocation order of Functions in a composition is determined by the **|** chain. However, if a function processes asynchronously or returns a reactive type, element completion order may depend on reactive operators and chosen concurrency.

With a broker, ordering depends on the broker, partitions, queues, subscriptions, and how consumers process in parallel. Kafka guarantees order within a single partition; different partitions have no global ordering. RabbitMQ and Pulsar also have their own delivery and ordering rules per queue or subscription type.

If ordering by **orderId** is required, choose a consistent key or partition key and ensure related events route to the same partition according to the binder's capabilities. At the same time, do not let consumers process the same key in parallel in a way that reorders business operations.

In-process function composition does not need partitions to pass data between steps. However, if the overall chain receives multiple concurrent messages from the input binding, different invocations can still execute concurrently. Distinguish ordering across steps within a single execution from ordering across multiple events.

## 7. Differences in deployment and scaling

A composite function is typically deployed as a single application. When additional processing behavior is needed, the development team modifies code and re-releases that application. Scaling typically increases the instance count of the entire application, even when only one step is the bottleneck.

With a broker, each application can have a different replica count:

| Application | Work | Example scaling approach |
|---|---|---|
| Order enrichment | Looks up customer information. | Increase replicas when customer system call latency grows. |
| Order validation | Evaluates business rules. | Add consumers when the validation backlog grows. |
| Order persistence | Writes results to the database. | Limit concurrency to match database capacity. |

In return, the multi-application model requires managing additional deployments, configurations, broker permissions, dashboards, alerts, schemas, and version compatibility. One service may upgrade faster than another; therefore event contracts must support periods where multiple versions coexist.

## 8. Choosing boundaries between processing steps

Do not create a new application for every small transformation. Application boundaries carry operational overhead and data contract costs. Consider splitting when there are one or more clear reasons:

- A processing step has significantly different scaling needs from the rest.
- A step has an independent release cycle or owning team.
- A step requires distinct technology, permissions, or security boundaries.
- A step must continue processing while another application is temporarily down.
- Intermediate events need to be retained for replay, auditing, or building multiple independent consumers.
- A processing step can be reused by multiple systems via an event contract.

Keep steps in the same process when they are small transformations requiring low latency, changing together, and needing no intermediate state persistence. For example, string normalization, format validation, derived field calculation, and applying internal rules can often be composed in one Function.

A practical approach is to start with simple boundaries, measure latency, backlog, deployment cost, and ownership needs. Only split a step into a separate application when there is evidence of a bottleneck or independence requirement. Once a broker boundary exists, keep the event contract stable and do not let consumers depend on the producer's internal Java class structure.

## 9. Combining function composition and broker in the same architecture

The two approaches are not mutually exclusive. An application can consume messages from a broker, compose multiple Functions in-process for processing, and publish the result to another destination. Applications on both sides remain independent.

Example:

~~~mermaid
flowchart LR
    A[Producer service] --> B[(Topic orders)]
    B --> C[Input binding]
    C --> D[enrichOrder]
    D --> E[validateOrder]
    E --> F[Output binding]
    F --> G[(Topic validated-orders)]
    G --> H[Persistence service]
~~~

In the diagram, **enrichOrder** and **validateOrder** are composed within the same order-processing application. The producer service and persistence service are independent applications communicating via the broker. This keeps overhead low for internal steps while preserving clear boundaries between capabilities that need independence.

When combining them, name destinations after event semantics, such as **orders** and **validated-orders**; use stable groups for consumers; version payloads when contracts change; and carry event IDs/correlation IDs across the flow. Avoid letting internal Function names become public contracts between services.

## 10. Testing both models

Testing function composition focuses on invocation order, data types, and error behavior across steps. You can test the composite function directly or use the test binder to verify the chain's input/output bindings.

Testing applications connected via a broker requires verifying both the contract between applications and broker behavior:

| Test area | In-process composition | Connecting applications via broker |
|---|---|---|
| Data types | Verify the previous function's output matches the next function's input. | Verify serializers and deserializers are compatible across the wire format. |
| Step ordering | Verify Functions are called according to composition. | Verify destinations and topology connect applications properly. |
| Mid-step errors | Verify exceptions propagate along the chain and are handled at the outermost binding. | Verify retries, ACK/commit, and DLQ at the respective consumer boundary. |
| Restarts | Check behavior of the whole application and input binding. | Stop one service, verify the broker retains backlog, then restart the consumer. |
| Schema versions | Check DTOs and mappers within the same application. | Test new producer with old consumer and vice versa per compatibility rules. |
| Load | Measure throughput and concurrency of the entire composite. | Measure backlog, lag, and independent scaling of each consumer group. |
| Duplicate processing | Verify idempotency when the input binding redelivers. | Verify idempotency across timeouts, redelivery, and replay. |

With the test binder, you can verify Spring Cloud Stream logic without a real broker. However, the test binder does not fully simulate retention, partition rebalancing, queue durability, subscription cursors, or broker acknowledgments. Those properties require integration tests with Kafka, RabbitMQ, or Pulsar respectively.

### Scenario matrix to test

1. Send a valid event and verify the final result.
2. Make the first step throw an exception and verify later steps do not process incomplete data.
3. Make a later step fail and verify binding retry or error flows.
4. Stop a consumer in the broker model, send more events, and restart it to confirm the backlog is processed.
5. Send the same event ID twice and confirm business side effects apply only once when idempotency is required.
6. Change the event schema and run the consumer against fixtures from the previous version.
7. Increase load on one step and observe whether scaling the whole application or scaling a separate service is more appropriate.

## 11. Common design mistakes

| Symptom | Cause | Remedy |
|---|---|---|
| Splitting every Function into a separate service even for minor transforms | Operational, network hop, and schema costs were overlooked. | Compose internal steps that share a lifecycle. |
| Composing too many steps into one application | Steps need independent scaling, release, or recovery. | Introduce a broker boundary at capabilities with distinct operational needs. |
| Assuming Function composition creates checkpoints between steps | Confusing direct function calls with publish/consume. | Use a broker if intermediate message storage and independent replay are needed. |
| Assuming the broker guarantees end-to-end business exactly-once | Overlooking gaps between commits, ACKs, and external system updates. | Use idempotency, local transactions, or outbox as required. |
| New consumer cannot read old events | Incompatible schema contract changes. | Maintain backward compatibility and test historical payloads. |
| Services process out of order per key | Missing partition key or uncontrolled parallel consumer processing. | Design keys/partitions and concurrency to match ordering requirements. |
| Cannot trace flows across multiple services | Missing event ID, correlation ID, or trace context. | Propagate correlation metadata and configure tracing across the broker. |
| Scaling one step forces scaling the entire application | Steps are composed in the same deployment unit. | Consider extracting the step with distinctly different load. |

## 12. Selection and implementation workflow

Before deciding, list the business steps and answer:

1. Do the steps share the same owning team and release cycle?
2. Do they need to scale independently or use different resources?
3. Do intermediate events need to be persisted to resume after failures or replay?
4. Do other independent consumers need to receive the same event?
5. Can the data contract remain stable across versions?
6. Is the operational cost of an extra service justified by the benefits?

After choosing a model:

- If composing in-process, declare **spring.cloud.function.definition**, verify input/output types of each function, and configure bindings for the composite function.
- If connecting via a broker, define destinations, groups, content types, schemas, retry/DLQ, access permissions, and retention policies.
- If combining both, place broker boundaries where independence is required and keep internal transformations in composite functions.
- For both models, test error handling, load, redelivery, and schema compatibility before deployment.

In-process function composition and connecting applications via a broker are two organizational styles with distinct characteristics. Function composition passes results directly between Functions in one runtime, reducing latency and simplifying internal flows. A broker establishes an asynchronous boundary between applications, enabling buffering, independent deployment, and independent scaling, while requiring management of data contracts, delivery semantics, and cross-service observability. Spring Cloud Stream supports combining both to balance processing efficiency with operational independence.
