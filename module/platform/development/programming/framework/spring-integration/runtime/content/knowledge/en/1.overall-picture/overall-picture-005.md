# Distinguishing flow configuration from runtime state

In Spring Integration, declaring an `IntegrationFlow` only describes how messages should move through components. When the application starts, Spring creates the corresponding beans, connects channels to endpoints, and manages the lifecycle of runnable components. At runtime, an endpoint may be running, stopped, waiting on a poller, or actively processing messages; those states do not live in the flow definition.

Separating these two layers helps answer operational questions accurately: whether a flow has been configured, whether endpoints are registered, whether consumers are receiving messages, whether a queue still holds messages, and whether an executor has pending work. Seeing a flow in configuration or the Integration Graph is not enough to conclude that the entire flow is operating normally.

After this article, you will be able to:

- Explain what `IntegrationFlow` describes and how Spring creates runtime components.
- Distinguish between an existing bean and a started endpoint.
- Understand the roles of `Lifecycle`, `SmartLifecycle`, `autoStartup`, and `phase`.
- Track static flows and flows dynamically registered via `IntegrationFlowContext`.
- Diagnose cases where a flow is configured yet not consuming messages, or stopped yet still holding pending work.

## 1. IntegrationFlow describes how components are wired

An `IntegrationFlow` in the Java DSL is a way to declare a message processing chain or graph. Each step can be a channel, transformer, filter, router, service activator, splitter, aggregator, or adapter. The declaration describes which components to connect and how messages move between them.

Example of a static flow declared as a bean:

```java
@Configuration
class OrderIntegrationConfiguration {

    @Bean
    MessageChannel ordersIn() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow ordersFlow(OrderService orderService) {
        return IntegrationFlow.from("ordersIn")
                .handle(orderService, "process")
                .get();
    }
}
```

The code above describes a flow that receives messages from `ordersIn` and invokes `OrderService.process`. It does not mean a dedicated thread was created to continuously run the flow. With `DirectChannel`, the handler is typically invoked synchronously on the message-sending thread once the endpoint has started and subscribed.

When the ApplicationContext initializes, Spring Integration infrastructure processes the flow definition and registers the required components as runtime beans. Depending on the flow, those components can include channels, message handlers, consumer endpoints, pollers, or adapters. The endpoint is responsible for connecting the handler to the channel and controlling message reception.

Therefore, distinguish between:

- `IntegrationFlow`: describes the processing structure.
- Runtime bean: concrete object created and managed by Spring in the ApplicationContext.
- Running endpoint: a component that has been started and can perform its receiving or sending role.
- Work in progress: specific messages currently being processed, sitting in a queue, or submitted to an executor.

A bean can exist while its corresponding endpoint has not started yet. Likewise, an endpoint can be running while having no messages to process at the moment of observation.

## 2. From configuration to runtime in ApplicationContext

For static flows declared via `@Bean` or XML, the process generally follows these steps:

```text
Java DSL / XML configuration
            |
            v
IntegrationFlow definition
            |
            v
ApplicationContext creates and registers components
            |
            v
Channels <----> handlers <----> consumer endpoints
            |
            v
Lifecycle startup according to autoStartup and phase
            |
            v
Message processing at runtime
```

When the context refreshes, Spring creates and configures beans. Components implementing the lifecycle contract are managed by Spring during application startup and shutdown. `SmartLifecycle` adds auto-startup capability, start/stop ordering, and callbacks for asynchronous shutdown.

Not every object in a flow is an independent process or thread. `DirectChannel` is a synchronous forwarding channel; `QueueChannel` holds messages in a queue; `ExecutorChannel` uses an executor to dispatch handler invocations. The consumer endpoint is what binds the handler to the appropriate message-receiving mechanism.

For an event-driven endpoint, when the endpoint starts, it subscribes its handler to the `SubscribableChannel`. When the endpoint stops, it unsubscribes from receiving messages according to endpoint lifecycle rules. For a polling endpoint, starting activates the poll schedule; stopping halts the poll schedule. Both cases illustrate that channels and endpoints have distinct lifecycles.

## 3. Where do configuration and runtime state differ?

| Aspect | Configuration / definition | Runtime state |
|---|---|---|
| Flow | Steps and wiring relationships declared in `IntegrationFlow`. | Which corresponding components have been registered and which endpoints are running. |
| Channel | Channel type, bean name, and how steps are connected. | Messages currently in the queue, active subscribers, or dispatch capability at that moment. |
| Endpoint | Handler, input channel, poller, `autoStartup`, `phase` attributes. | Whether the endpoint is started or stopped, and whether it is receiving messages. |
| Poller | Trigger, fixed delay/rate, max messages per poll. | Scheduled poll task, latest poll execution, poll outcome and errors. |
| Executor | Selected executor and pool configuration. | Active thread count, task queue, completed or rejected tasks. |
| Retry / transaction | Retry policy and transaction declarations. | Current attempt, open or completed transaction, latest error. |
| Message store | How messages or correlation state are stored. | Actual messages and correlation groups held at observation time. |

Configuration generally remains stable throughout the application lifecycle, whereas runtime state changes over time. A flow can keep the same definition while endpoints are started and stopped multiple times. Queues can grow and drain; executors can alternate between idle and busy; an aggregator can hold message groups waiting for remaining elements.

For that reason, saying "the flow is running" is often too vague. When investigating, specify whether you are asking about definition existence, bean existence, endpoint lifecycle state, or message processing progress.

## 4. Lifecycle, SmartLifecycle, autoStartup, and phase

Spring provides two common interfaces for managing component lifecycles:

- `Lifecycle` provides `start()`, `stop()`, and `isRunning()`.
- `SmartLifecycle` extends `Lifecycle`, adding `isAutoStartup()`, `getPhase()`, and a `stop(Runnable)` mechanism to support callback-based shutdown.

Spring Integration consumer endpoints are lifecycle-managed. You can configure an endpoint not to start automatically on ApplicationContext startup using `autoStartup=false`, then explicitly call `start()` once business preconditions are met. The `phase` attribute controls startup and shutdown order among `SmartLifecycle` components: lower phases start first; during shutdown, the order is reversed.

Example of reading the state of a component retrieved from ApplicationContext:

```java
void logLifecycle(Object component) {
    if (component instanceof SmartLifecycle smartLifecycle) {
        log.info("running={}, autoStartup={}, phase={}",
                smartLifecycle.isRunning(),
                smartLifecycle.isAutoStartup(),
                smartLifecycle.getPhase());
    }
    else if (component instanceof Lifecycle lifecycle) {
        log.info("running={}", lifecycle.isRunning());
    }
    else {
        log.info("Component does not expose Lifecycle state");
    }
}
```

Endpoint bean names are generated from configuration or the DSL and may depend on the flow/component ID. When you need to inspect a specific endpoint, assign a clear ID in configuration and look up the corresponding bean. Do not assume the runtime bean name always matches the `@Bean` method name returning `IntegrationFlow`.

`isRunning()` indicates that the component was started according to its lifecycle contract. It does not prove the handler is actively processing messages, that queues are uncongested, that the executor has available threads, or that downstream systems are healthy. To assess actual processing capability, combine lifecycle state with metrics, queue depth, logs, and external dependency health.

## 5. Static flows and dynamically registered flows

Static flows are typically declared via `@Bean` or XML and processed alongside the ApplicationContext. When the application starts, infrastructure creates the corresponding components and manages their lifecycles.

When flows need to be created or removed while the application is running, Spring Integration provides `IntegrationFlowContext`. A registration represents a dynamically registered flow and lets you control that flow's lifecycle:

```java
@Service
class TenantFlowManager {

    private final IntegrationFlowContext flowContext;
    private final OrderService orderService;

    TenantFlowManager(
            IntegrationFlowContext flowContext,
            OrderService orderService) {
        this.flowContext = flowContext;
        this.orderService = orderService;
    }

    IntegrationFlowRegistration registerTenantFlow() {
        return flowContext
                .registration(flow -> flow
                        .from("tenant.orders")
                        .handle(orderService, "process"))
                .id("tenantOrders")
                .register();
    }
}
```

The returned `IntegrationFlowRegistration` object is the handle for managing the registration. You can call `start()` or `stop()` when changing state, and `destroy()` when you want to cancel the registration and remove the components managed by it. If you need to register without starting immediately, the builder supports configuring `autoStartup` before calling `register()`.

Example of controlling lifecycle after registration:

```java
IntegrationFlowRegistration registration = registerTenantFlow();

registration.stop();   // Stop receiving/processing according to the flow lifecycle.
registration.start();  // Restart the registration.
registration.destroy(); // Destroy the registration and components belonging to the flow.
```

In real applications, keep the registration handle where tenant lifecycles or dynamic configurations are managed. Avoid repeatedly creating new flows for the same tenant without managing old registrations, as doing so can create duplicate endpoints, redundant subscribers, or bean leaks.

`stop()` and `destroy()` have different meanings. Stop puts components into a stopped state while preserving the registration so it can be started again. Destroy removes the registration and components belonging to the flow. Destroying a flow does not automatically delete business data or messages stored in external systems.

## 6. Channels, pollers, and executors have their own state

A flow can consist of several channel and endpoint types. The state of these components explains why seeing the configuration is not enough to know where a message is going.

### 6.1. DirectChannel

`DirectChannel` normally invokes the subscriber on the message-sending thread. When the endpoint is started and its handler is subscribed, a send call can go straight into the handler. If the endpoint is stopped and no subscribers remain, messages are not processed by that endpoint; the send result depends on channel type, subscriber count, and error handling configuration.

There is no internal queue to hold messages while waiting for an endpoint to restart. Therefore, when inspecting a `DirectChannel`, check subscribers and endpoint state, as well as the send outcome.

### 6.2. QueueChannel and PollingConsumer

`QueueChannel` can hold messages waiting for a consumer to retrieve them. A `PollingConsumer` uses a poller to receive messages on a schedule. The poller can be configured with fixed delay, fixed rate, a cron trigger, or a limit on messages per poll.

If the endpoint stops, the polling task stops running according to the endpoint lifecycle. Messages already in the queue usually remain there and can be consumed when the endpoint starts again; long-term retention depends on the queue and message store used. Hence, "endpoint stopped" does not mean "queue empty".

### 6.3. ExecutorChannel

`ExecutorChannel` delegates handler invocation through a `TaskExecutor`, so messages can be processed on a different thread from the sender. The executor has its own state such as active thread count, queued tasks, and task rejection behavior under overload.

Stopping an endpoint does not mean every task previously accepted by the executor is canceled. When diagnosing, inspect both endpoint state and executor state, including the task queue and any rejected execution errors.

## 7. Stopping a flow does not mean erasing all work

A stop operation primarily affects component lifecycle. Depending on channels and execution mechanisms, the following may still exist after an endpoint stops:

- Messages already placed into a `QueueChannel` or message store.
- Tasks already submitted to an executor that have not finished running.
- Handlers currently executing and waiting on I/O or external services.
- Correlation message groups held by an aggregator waiting for missing elements.
- Retry state, transactions, or error records written to their respective storage systems.

Therefore, before stopping a flow in production, know the ingress point, channel types, storage policies, and how the application handles in-flight work. If controlled shutdown is required, coordinate lifecycle phases, endpoint stop behavior, executor wait timeouts, and queue draining mechanisms according to business requirements.

In particular, `stop()` is not a queue purge operation. If messages must be deleted, that is a separate data management action and should be designed per business policy to avoid losing valid messages.

## 8. How to observe runtime state

Combine multiple perspectives instead of relying on a single `isRunning()` flag:

| Question | Appropriate place to inspect |
|---|---|
| Is the flow declared/registered? | ApplicationContext, Java/XML configuration, or `IntegrationFlowContext` for dynamic flows. |
| Has the endpoint started? | Endpoint bean and `Lifecycle.isRunning()`. |
| Does the endpoint auto-start, and what is its lifecycle order? | `SmartLifecycle.isAutoStartup()` and `getPhase()`. |
| Are messages sitting in a queue? | The corresponding queue/channel or MessageStore. |
| Is the poller active? | Polling endpoint lifecycle, scheduler, and poll execution logs. |
| Is the executor saturated? | Active threads, pool size, task queue, completed tasks, and rejected tasks. |
| Which components belong to the flow? | Integration Graph when `IntegrationGraphServer` or the corresponding management endpoint is enabled. |
| Is the handler failing or slow? | Logs, metrics/observations, error channel, and tracing. |

Spring Integration includes Integration Graph to represent components and wiring relationships. In a Spring Boot application, the Integration Graph management endpoint can be exposed via Actuator when appropriate dependencies and configuration are enabled. The graph helps understand runtime structure; it does not replace checking whether endpoints are running or whether queues/executors are under load.

Instrumented components can emit metrics/observations for sending, receiving, and processing messages. When management and the corresponding metrics system are enabled, use those metrics alongside logs and tracing to pinpoint latency, throughput, and bottlenecks. Metric names and exposure capabilities depend on the Spring Integration version, Micrometer configuration, and the application's observability stack.

## 9. Diagnostic scenario

Suppose a dashboard shows `ordersFlow` has been created, yet new orders are not being processed. Follow this sequence:

1. **Confirm definition and registration.** Verify whether the flow exists in configuration or ApplicationContext; for dynamic flows, verify the registration still exists.
2. **Identify the ingress endpoint.** Locate the endpoint attached to the input channel, and inspect the runtime bean and `Lifecycle.isRunning()`.
3. **Inspect the message-receiving mechanism.** For an event-driven endpoint, check subscribers; for a polling endpoint, check the poller, scheduler, and trigger configuration.
4. **Inspect the channel.** For `DirectChannel`, check whether send has subscribers and produces errors. For `QueueChannel`, check queue depth and message wait times.
5. **Inspect executor and downstream.** If using `ExecutorChannel`, inspect the thread pool and task queue. Inspect the handler, transactions, retries, and downstream services invoked later.
6. **Cross-check error channel and observability.** Look for exceptions, rejected tasks, retry exhaustion, or messages routed to an error flow.

For example, if the endpoint is a stopped `PollingConsumer` while the `QueueChannel` holds 120 messages, the flow configuration can still be completely valid. The problem lies in the runtime state of the consumer or scheduler. Conversely, if the endpoint is running while the executor queue keeps growing, the bottleneck may be downstream processing capacity rather than flow wiring configuration.

## 10. Common misconceptions

| Misconception | Accurate understanding |
|---|---|
| Having an `IntegrationFlow` bean means the flow is processing messages. | The bean describes the flow; inspect runtime endpoints and lifecycle state. |
| An endpoint existing means it has started. | A bean can exist with `autoStartup=false` or in a stopped state. |
| `isRunning() == true` means the flow is healthy. | It only reflects component lifecycle state; inspect metrics, queues, executors, and errors. |
| Stopping a flow deletes pending messages. | Stop controls lifecycle; messages in queues/stores may still remain. |
| Every step in a flow has its own thread. | Threading depends on channels and executors; `DirectChannel` typically runs synchronously. |
| Dynamic flows only need `stop()` when no longer used. | Stop retains the registration; call `destroy()` when removing the flow and components from the context. |
| Integration Graph proves messages passed through the flow successfully. | The graph represents component structure; use logs, metrics, and tracing to confirm actual processing. |

## 11. Self-check

**Scenario:** A static flow is declared with `@Bean`. After the application starts, the polling endpoint is configured with `autoStartup=false`. The `QueueChannel` continues receiving messages, yet the consumer does not pull them.

1. Does the flow definition exist?
2. Does the existence of the endpoint bean prove polling is occurring?
3. Which runtime states should be inspected to explain why the queue grows?
4. When `start()` is called on the endpoint, what gets activated?

**Suggested answers:** (1) Yes, the flow was declared and processed in the ApplicationContext. (2) No, an endpoint can exist without being started. (3) Inspect the polling endpoint lifecycle, poller/scheduler, and queue depth. (4) The endpoint starts and the polling schedule activates per configuration; waiting messages can now be pulled by the consumer.

**Operational exercise:** Create a flow with a `QueueChannel` and a polling endpoint. Run the application, observe endpoint state, send a few messages, then stop the endpoint and send more messages. Record queue depth before and after restarting the endpoint. Repeat with a flow using `DirectChannel` to compare behavior when there is no queue holding messages.

## References

- [Spring Integration Reference — Programming Tips and Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html)
- [Spring Integration Reference — Endpoint Lifecycle](https://docs.spring.io/spring-integration/reference/endpoint.html)
- [Spring Integration Reference — Integration Graph](https://docs.spring.io/spring-integration/reference/graph.html)
- [Spring Framework Reference — Lifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Integration Javadoc — IntegrationFlowContext](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/context/IntegrationFlowContext.html)
