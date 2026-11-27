# What is the Spring Integration runtime and what are its responsibilities?

The Spring Integration runtime is the execution engine for integration flows declared in a Spring application. It receives data from external systems or internal code, wraps the data into messages, moves messages across channels, invokes the appropriate handlers, coordinates execution timing and flow, and forwards results to the next destination.

You can think of an `IntegrationFlow` as the blueprint of a process, and the runtime as the engine that makes that process run. The runtime manages the Spring components, wires them into a message flow, decides whether messages are dispatched synchronously or asynchronously, triggers endpoints that require polling, manages state for stateful patterns, and routes errors to the appropriate handler.

Spring Integration provides the infrastructure for Enterprise Integration Patterns (EIP). Business logic still belongs to the application: the runtime coordinates invoking that logic and manages how messages traverse the system.

## 1. Looking at the overall message flow

A flow typically consists of the following roles:

- **Data source** produces events or records: HTTP, files, databases, message brokers, TCP, other applications, or internal code.
- **Inbound adapter** brings data from a source into the messaging system. An **inbound gateway** typically receives a request and can send a reply back to the caller.
- **Message channel** transfers messages between components while also determining the dispatch or buffering behavior.
- **Endpoint** connects a channel to a consumer or `MessageHandler`.
- **Handler** performs a processing step such as transform, filter, route, enrich, split, aggregate, or invoking a business service.
- **Outbound adapter** sends data out to a target system in a one-way fashion. An **outbound gateway** supports request-reply exchanges with a target system.

~~~mermaid
flowchart LR
    A["Data source"] --> B["Inbound adapter / gateway"]
    B --> C["Message"]
    C --> D["Channel"]
    D --> E["Endpoint + handler"]
    E --> F["Next channel"]
    F --> G["Endpoint + handler"]
    G --> H["Outbound adapter / gateway"]
    E -. "error" .-> X["errorChannel"]
    D -. "buffer / state" .-> S["MessageStore"]
~~~

Components may reside within the same JVM or connect to external systems. Channels within the same application are typically internal abstractions; when network communication or durable message storage is needed, the flow uses the appropriate adapter, gateway, broker, or store.

### Messages carry data and context

A Spring Integration message has two main parts:

- `payload`: the data that a handler needs to process, such as an `Order`, a JSON string, or a byte array.
- `headers`: accompanying metadata, such as `id`, `timestamp`, `correlationId`, `replyChannel`, `errorChannel`, sequence information, or application-specific headers.

Headers allow the runtime and patterns to coordinate without stuffing all metadata into the payload. For example, an aggregator uses the correlation ID to group messages belonging to the same unit of work; a gateway can use the reply channel to receive the result.

Messages and headers are designed to be immutable. When you need to modify headers or create a new message, use `MessageBuilder` or the framework APIs instead of mutating a message shared across multiple components directly.

## 2. What is the runtime responsible for?

| Responsibility | What the runtime does | Operational questions to answer |
|---|---|---|
| Flow initialization | Registers beans, creates endpoints, and binds channels to handlers | Have the flows been created and started? |
| Message dispatch | Sends messages to consumers according to channel semantics | Which thread processes the message? Is it buffered? |
| Consumer activation | Registers listeners or runs polling tasks | Is the endpoint event-driven or polling? |
| Concurrency coordination | Uses caller threads, schedulers, or executors depending on configuration | Is there thread pool saturation or resource contention? |
| State management | Stores messages, message groups, and correlation state when patterns require it | Are messages/groups piling up or expiring? |
| Error control and retry | Converts exceptions into `ErrorMessage` and applies advice and recovery | Are errors thrown back to the caller or sent to an error flow? |
| Lifecycle management | Starts, stops, and destroys endpoints/flows | When the application stops or a tenant is removed, do flows stop properly? |
| Runtime observability | Exposes graphs, metrics, and observations when configured | Which component is slow, failing, or has a backlog? |

The runtime does not automatically guarantee that every message is processed exactly once. Durability and recoverability depend on the inbound source, channel, transaction manager, message store, broker, retry policy, and handler idempotency.

## 3. Channels determine how messages are transferred

A `MessageChannel` is the connection point between a producer and a consumer. The producer only needs to send a message to the channel; it does not need to know directly which handler will process it. However, the channel type significantly affects threading, processing order, buffering, and how errors are observed.

| Channel | How messages are transferred | Notable behavior |
|---|---|---|
| `DirectChannel` | Dispatches directly to a single subscriber on the thread calling `send()` | Synchronous; exceptions can propagate back to the caller; usually the default choice |
| `PublishSubscribeChannel` | Broadcasts a message to all subscribers | Used for broadcast/events; if no executor is configured, subscribers run on the sending thread |
| `QueueChannel` | Places messages into a queue for consumers to receive later | Buffered; consumers typically poll; should configure a bounded capacity |
| `PriorityChannel` | Receives messages in priority order backed by a store | Used when priority matters more than pure FIFO |
| `RendezvousChannel` | Sender waits until the receiver accepts the message | Useful for synchronous handoff between two parties |
| `ExecutorChannel` | Dispatches to a single subscriber via a `TaskExecutor` | Decouples sending thread and processing thread; transactions bound to the sending thread do not propagate automatically to the handler |

A few key differences to keep in mind:

- `DirectChannel` has point-to-point semantics: each send is dispatched to one handler. If there are multiple subscribers, the dispatcher selects one subscriber according to the configured load-balancing and failover strategy.
- `PublishSubscribeChannel` has broadcast semantics: each subscriber receives a delivery of the message. It is not a queue that stores messages for consumers to pick up later.
- `QueueChannel` holds messages in a queue. If the queue is full, a send operation may block or fail depending on the timeout and how it is invoked. A queue does not create consumer threads on its own; a polling endpoint must read from the queue.
- `ExecutorChannel` switches the execution context using an executor, but it is not itself a business queue with storage semantics. Task queuing behavior depends on the executor configuration.

With `QueueChannel`, configuring a bounded capacity helps enforce load limits. An unbounded queue can continuously grow memory usage when the producer rate exceeds the consumer rate. If messages must survive a process crash, an in-memory queue is not enough; you need a persistent message store or a broker with appropriate durability.

## 4. Endpoints, consumers, and handlers

An endpoint is the component that connects a channel to processing logic. The handler focuses on the action performed on a message; the endpoint manages how the handler is invoked and how it participates in the runtime.

Two common consumer types are selected based on the input channel type:

- **`EventDrivenConsumer`** subscribes a handler to a `SubscribableChannel`. When a message is sent to the channel, the handler is invoked according to the channel's dispatch mechanism.
- **`PollingConsumer`** reads messages from a `PollableChannel` on a schedule. This endpoint requires a poller to determine when to call `receive()` and how many messages can be read in one polling cycle.

Several other common endpoint types:

- **Channel adapter** connects an external source or target to a message channel. An inbound adapter typically produces messages; an outbound adapter typically receives messages and sends data out.
- **Messaging gateway** creates a request-reply boundary between application code and a message flow or external system.
- **Service activator** invokes a method/service to execute business logic.
- **Transformer** converts a payload or message structure.
- **Filter** decides whether a message continues or is discarded.
- **Router** selects the next channel based on message content or metadata.
- **Splitter and aggregator** split one message into multiple messages and then combine related messages into a result.

These endpoints are runtime components that can be managed as Spring beans. Therefore, endpoint configuration also affects lifecycle, transaction advice, retry advice, metrics, and diagnostics.

## 5. Pollers and executors coordinate timing and threads

Pollers and executors often appear together in a flow, but they solve two different problems:

- **Poller** determines when an endpoint reads messages from a pollable source or `PollableChannel`.
- **TaskScheduler** schedules the next execution of the polling task.
- **TaskExecutor** determines which thread executes a task or message handler and under what pool/queue policy.

A poller can use fixed-delay, fixed-rate, or cron triggers. Properties commonly requiring attention:

- `maxMessagesPerPoll`: maximum number of messages received in one polling cycle. This value tunes batch size; it does not directly dictate the number of threads.
- `receiveTimeout`: wait duration when calling receive if no message is available yet.
- `taskExecutor`: executor used to run polling work when configured.
- `adviceChain`: where cross-cutting concerns such as transactions or retries are attached to the polling endpoint.

Example of a `MessageSource` read on a schedule:

~~~java
@Bean
IntegrationFlow pollingOrders(
        MessageSource<Order> orderSource,
        OrderService orderService) {

    return IntegrationFlow.from(orderSource,
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(Duration.ofMillis(500))
                                    .maxMessagesPerPoll(25)))
            .handle(orderService, "process")
            .get();
}
~~~

This example reads up to 25 messages per cycle, with a 500 ms delay between trigger invocations according to the poller configuration. It does not mean there are always 25 threads processing in parallel. To increase concurrency, you must examine the endpoint type, executor, and how messages are distributed.

### Distinguishing three common execution paths

1. **DirectChannel:** the producer calls `send()`, and the handler runs immediately on the producer's thread. The call completes only after the handler finishes processing.
2. **QueueChannel:** the producer sends the message to a queue; a polling consumer receives the message at a different time. The producer can continue once the message is accepted into the queue.
3. **ExecutorChannel:** the producer hands the message to a dispatcher using an executor; the handler runs on a thread supplied by the executor. A successful send usually confirms only the handoff, not that downstream processing succeeded.

Avoid adding executors to every channel out of habit. An asynchronous boundary can increase parallel processing capability, but it also changes observed ordering, error propagation, transaction boundaries, and backlog management needs.

## 6. Lifecycle of an IntegrationFlow

In a typical configuration, an `IntegrationFlow` is declared as a Spring bean. When the `ApplicationContext` initializes, Spring Integration registers the necessary components, creates endpoints, wires channels and handlers, and manages endpoint lifecycles via Spring's lifecycle mechanism.

`@EnableIntegration` activates Spring Integration infrastructure when an application uses Java configuration. This infrastructure can register foundational beans such as default channels, an error channel, and a task scheduler. In a Spring Boot application, you should understand what auto-configuration already provides to avoid duplicate configuration.

Endpoints typically have lifecycle properties such as `autoStartup` and `phase`. These determine whether an endpoint starts automatically when the context starts and the relative order in which components are started/stopped. When shutting down the application, inbound sources should stop accepting new work and running components should have an opportunity to complete or handle remaining work according to system policy.

### Dynamic flow registration

Some applications need to create flows per tenant, customer configuration, new connection, or runtime request. In such cases, `IntegrationFlowContext` allows registering an `IntegrationFlow` along with its dependent beans while the application is running.

The typical workflow is:

1. Build the `IntegrationFlow` from validated configuration or business data.
2. Register the flow via `IntegrationFlowContext`, assigning a stable ID and choosing an appropriate `autoStartup`.
3. Keep the registration handle to access the flow or control its lifecycle when needed.
4. When the flow is no longer needed, call `IntegrationFlowRegistration.destroy()` to stop and remove the flow together with its registered dependent beans.

An explicit ID helps identify the flow in logs and avoids bean name collisions when creating multiple similar flows. With dynamic flows, the application must manage registration and destruction timing consistently; merely dropping the reference to the registration without destroying the flow can leave endpoints or associated resources alive.

## 7. Transactions and execution boundaries

Transactions in Spring Integration rely on Spring's transaction mechanism. The key point is that a transaction is normally bound to the current thread.

In a flow running through a `DirectChannel`, subsequent handlers are invoked on the same thread. Unless another thread boundary exists, the transaction context can continue across the synchronous steps of the flow.

With `QueueChannel`, `ExecutorChannel`, or code that spawns a new thread manually, the flow has crossed into a different execution context. A transaction bound to the original thread does not automatically follow the message. Therefore, if a producer sends a message into a queue inside one transaction and a consumer processes it later, the producer's transaction does not cover the consumer's processing.

Pollers support configuring transaction advice to wrap a receive-and-forward cycle in a transaction. This is especially useful when reading a message from a persistent store that can participate in the same transaction. For example, if a message is fetched from a JDBC-backed channel store inside a transaction and processing fails, a rollback can restore the message retrieval when the store and transaction manager are configured compatibly.

When designing transactions, clarify:

- Where does the transaction start: when receiving from the source, when a handler runs, or when writing the result?
- Which resources actually participate in the same transaction manager?
- Does any channel or executor change threads between steps?
- When sending to a broker or calling an external API, how does the system handle the case where the database commit succeeds but the external send fails?

Do not assume a local transaction spans all external systems. For multi-system integration, you typically need idempotency, outbox/inbox patterns, message acknowledgments, or compensation mechanisms depending on business requirements.

## 8. Retry, recovery, and the error channel

Retry is a policy for re-invoking a handler when an operation fails. Spring Integration supports retry through handler advice, typically `RequestHandlerRetryAdvice`, built on Spring Framework's retry mechanism.

There are two types to distinguish:

- **Stateless retry:** the advice performs retry attempts within the same invocation. The thread may have to wait during backoff periods.
- **Stateful retry:** the advice stores retry state keyed by the message. When a processing attempt fails, the exception is thrown back to the source; the source can redeliver the message and the next delivery resumes the stored retry state.

When attempts are exhausted, a recovery callback can forward the error to a dedicated handling channel, for example via `ErrorMessageSendingRecoverer`. Retries should be bounded in attempt count, use appropriate backoff, and apply only to recoverable errors. If a handler already caused side effects before throwing an exception, a retry may repeat those side effects; therefore critical operations must be idempotent or have deduplication mechanisms.

### Where do errors go?

How exceptions are observed depends on whether the flow runs synchronously or asynchronously:

- In a synchronous flow via `DirectChannel`, an exception from a handler can propagate back up the call stack to the caller.
- In an asynchronous flow via an executor or polling task, the original caller is no longer waiting on the same call stack. The runtime wraps the error as an `ErrorMessage` and sends it to an error channel according to the endpoint's error handling mechanism.
- If the message has an `errorChannel` header, the runtime prioritizes that channel. Otherwise, errors are typically sent to the global channel bean named `errorChannel`.

The default error channel is a `PublishSubscribeChannel` with a `LoggingHandler` that logs at the ERROR level. An application can register additional handlers, routers, or error flows to classify errors, record status, send alerts, or route messages to a dead-letter queue.

A useful error flow should preserve diagnostic context: the original exception, the failing message, component name, correlation ID, and source information. Avoid merely logging and dropping the message if business requirements call for retry, redelivery, or manual handling.

## 9. MessageStore and correlation for state management

Many patterns work only when the runtime remembers previously arrived messages. For example, an aggregator must hold messages belonging to the same group until conditions are met to produce a result. `MessageStore` and `MessageGroupStore` provide abstractions for storing that state.

- **`MessageStore`** stores individual messages, such as messages buffered in a `QueueChannel`.
- **`MessageGroupStore`** stores message groups and group metadata, commonly used by aggregators, resequencers, and other correlation-based patterns.
- **In-memory stores** are easy to use, but state can be lost when the process stops.
- **Persistent stores** such as JDBC implementations can retain state across restarts and participate in transactions if configured compatibly.

### Correlation and aggregators

Correlation determines which messages belong to the same unit of work. By default, correlation handlers typically rely on the `correlationId` header; an application can supply a custom `CorrelationStrategy`.

An aggregator typically works in sequence:

1. Receive a message and determine the correlation key.
2. Add the message to the corresponding group in `MessageGroupStore`.
3. Call `ReleaseStrategy` to check whether the group is ready to emit a result.
4. When ready, process the group and emit the aggregated message.
5. Manage completed groups, late-arriving messages, and state retention timeouts.

The `sequenceNumber` and `sequenceSize` headers often help identify message position and expected part count in a sequence. Relying solely on message count may not suffice if a filter in the flow drops part of a sequence; in that case, a business-appropriate release strategy is needed.

Message groups can linger for a long time if messages are missing or the release condition is never satisfied. Configure timeouts, expiry, and cleanup mechanisms such as `MessageGroupStoreReaper` when appropriate. In a multi-instance environment, a shared persistent store needs consistent locking/correlation mechanisms so multiple nodes do not update the same group inconsistently.

A persistent store helps persist state, but it does not automatically create an exactly-once guarantee for the whole flow. You still need to handle duplicates, late-arriving messages, retries, and failures between steps.

## 10. Observing and diagnosing the runtime

When a flow does not behave as expected, inspect along the message's path rather than looking only at the final stack trace.

1. **Is the source producing messages?** Check inbound adapters/gateways, external connections, polling schedules, and ingestion logs.
2. **Did the message enter the channel?** Check channel names, send results, capacity, timeouts, and backlog.
3. **Is the endpoint created and running?** Check lifecycle state, `autoStartup`, poller configuration, and subscriptions.
4. **Is the handler being invoked?** Check thread names, processing duration, exceptions, and retries.
5. **Is there an asynchronous boundary?** Identify which `QueueChannel`, `ExecutorChannel`, poller, or executor took over downstream processing.
6. **Does the transaction cover the right operations?** Check the transaction manager, thread boundaries, and participating resources.
7. **Is state being held somewhere?** Check the message store, message count in groups, correlation keys, and expiration times.
8. **Is the error flow receiving errors?** Check the `errorChannel` header, global `errorChannel`, recovery callbacks, and dead-letter path.

Spring Integration provides `IntegrationGraphServer` to represent components and links in a runtime graph. The graph helps compare the actual registered flow against the flow the development team believes they configured.

For metrics and tracing, Spring Integration integrates with Micrometer Observation. When an `ObservationRegistry` and appropriate integration management configuration are present, producers, handlers, gateways, and certain endpoints can be instrumented to collect timing, outcomes, and traces. You can use `@EnableIntegrationManagement` with `observationPatterns()` to select which component groups to observe. Propagate correlation IDs or trace context across system boundaries to link logs and traces for the same unit of work.

### Signs of common performance issues

| Symptom | Causes to inspect | Remediation direction |
|---|---|---|
| Queue grows continuously | Producer faster than consumer; blocked handler or slow downstream | Measure ingress/egress rates, bound capacity, scale consumers safely, or shed load |
| Heap grows over time | Unbounded queue, large message payloads, or non-expiring message groups | Use bounded queues, limit payload sizes, configure expiry and group cleanup |
| Slow polling response | Trigger too infrequent, long receive timeout, or poller processing large batches | Tune trigger, timeout, and `maxMessagesPerPoll` for target latency |
| Executor frequently saturated | Pool too small, task queue full, or long-blocking handlers | Measure handler duration, tune pool/queue sizing and rejection policy |
| Errors appear on a different thread than caller | Flow transitioned to an executor or polling task | Monitor error channel, trace ID, and consumer thread logs |
| Transaction does not roll back later steps | Flow crossed a thread boundary or resources do not share the transaction | Place transaction at consumer boundary and design idempotency/outbox |
| Aggregator holds groups too long | Missing messages, wrong correlation, or release strategy never met | Check sequence/headers, release condition, and expiry |

Increasing the number of threads does not always make a flow faster. If the bottleneck is a database, an external API, or message group locking, more threads can increase contention and the number of waiting tasks. Measure each endpoint, channel, and dependency before changing concurrency.

## 11. Minimal synchronous flow example

The example below declares a flow that receives orders, normalizes data, calls a business service, and sends the result to an output channel. All channels are `DirectChannel`, so steps in the flow run synchronously on the message-sending thread.

In the example, assume `OrderService.process(Order)` returns a result for the flow to forward. If the processing method returns `void`, there will be no reply message for the output channel to receive.

~~~java
@Configuration
@EnableIntegration
class OrderFlowConfiguration {

    @Bean
    MessageChannel ordersIn() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel ordersOut() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow orderFlow(OrderService orderService) {
        return IntegrationFlow.from(ordersIn())
                .<Order, Order>transform(order -> order.normalized())
                .handle(orderService, "process")
                .channel(ordersOut())
                .get();
    }
}
~~~

To switch this flow to asynchronous processing, choose the appropriate channel or endpoint and clearly define where consumers continue processing. If using a `QueueChannel`, configure a poller for the endpoint reading the queue and choose a store if persistence is needed. If using an `ExecutorChannel`, configure the executor, resource limits, and error handling. After each change, re-evaluate transaction boundaries, processing order, and retry behavior.

## 12. Checklist when designing a flow

Before putting a flow into production, be able to answer these questions:

- Is the input source an adapter, gateway, `MessageSource`, or code actively sending messages?
- Which channels need to be synchronous, broadcast, buffered, or dispatched via an executor?
- Which consumers are event-driven, and which are polling? What trigger and batch size does the poller use?
- Do thread pools, queue capacities, and timeouts have clear bounds?
- Where do transactions start and end? Which resources participate in the transaction?
- Which errors does retry apply to, what is the maximum attempt count, and where does recovery route?
- Do messages or message groups require persistence, expiry, and cleanup?
- Is the correlation key unique and stable per unit of work?
- Does the error channel retain enough context for retry, alerting, or manual handling?
- Are graphs, metrics, traces, and logs sufficient to identify slow or failing components?

Once these questions are answered, the development team can explain how the flow runs, where messages reside, which threads are processing them, what state is being held, and which path errors take. That is the core scope of the Spring Integration runtime's responsibilities.

## References

The links below point to the Spring Integration Reference Guide. Cross-check against the Spring Integration version your application uses, as some APIs and configuration details may vary across versions.

- [Overview of Spring Integration Framework](https://docs.spring.io/spring-integration/reference/overview.html)
- [Message Endpoints and Pollers](https://docs.spring.io/spring-integration/reference/endpoint.html)
- [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
- [Dynamic and Runtime Integration Flows](https://docs.spring.io/spring-integration/reference/dsl/java-runtime-flows.html)
- [Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html)
- [Retry Advice](https://docs.spring.io/spring-integration/reference/handler-advice/classes.html)
- [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
- [Message Store](https://docs.spring.io/spring-integration/reference/message-store.html)
- [Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html)
- [Integration Graph](https://docs.spring.io/spring-integration/reference/graph.html)
- [Metrics and Management](https://docs.spring.io/spring-integration/reference/metrics.html)
