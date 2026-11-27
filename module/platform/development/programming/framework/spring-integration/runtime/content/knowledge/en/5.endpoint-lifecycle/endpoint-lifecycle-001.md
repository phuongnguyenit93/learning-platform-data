# AbstractEndpoint and the Lifecycle Contract

In Spring Integration, an endpoint is the component that connects a message handler to a channel and controls how the handler receives messages. An endpoint does not merely describe a processing step; it also has a lifecycle: being initialized, starting to receive messages, pausing, or stopping when the application shuts down. `AbstractEndpoint` is the base class in Spring Integration's endpoint model, integrating with Spring's lifecycle contract so that the ApplicationContext can manage these steps.

Understanding `AbstractEndpoint` and `SmartLifecycle` helps distinguish between an endpoint having been created as a bean and the endpoint actually being active. This is the foundation for configuring `autoStartup`, ordering startup using `phase`, proactively starting/stopping endpoints, and diagnosing cases where messages are not consumed even though the flow exists in the configuration.

After this lesson, you can:

- Explain the role of an endpoint and the place of `AbstractEndpoint` in Spring Integration.
- Understand the `Lifecycle` and `SmartLifecycle` contracts that endpoints participate in.
- Distinguish between bean initialization, start, stop, and destroy.
- Configure `autoStartup` and `phase` to control the endpoint lifecycle.
- Distinguish the lifecycle behavior of an event-driven consumer and a polling consumer.
- Observe endpoint state and diagnose issues during start/stop.

## 1. What does an endpoint do in a message flow?

A message flow typically has a channel to transport messages and a handler to perform the work. The endpoint connects these two parts: it registers the handler with the channel or schedules message retrieval, depending on the endpoint type.

```text
Producer
   |
   v
Input Channel ---> Consumer Endpoint ---> Message Handler
                         |
                         +-- lifecycle: start / stop
```

For example, a service activator may invoke a method on a business service. The service is where processing takes place; the consumer endpoint is responsible for connecting that service to the input channel and controlling how messages are delivered to the service.

An endpoint should not be conflated with a handler:

- **Message handler** performs an action on a message, such as invoking a service, transforming a payload, or routing.
- **Channel** is the message transmission point and determines how messages are distributed or buffered.
- **Endpoint** connects the handler to the channel and manages the message consumption mechanism.
- **Lifecycle contract** allows Spring and the application to control when the endpoint starts or stops operating.

Therefore, a handler can exist as a bean while the endpoint connected to it has not started yet. In that case, the handler is still created in the ApplicationContext, but the endpoint may not have registered a subscriber or scheduled a poller yet.

## 2. AbstractEndpoint and Spring's lifecycle contract

`org.springframework.integration.endpoint.AbstractEndpoint` is the base class for message-consuming endpoints in Spring Integration. This class integrates with Spring's lifecycle mechanism, in which the key contract is `SmartLifecycle`.

Spring Framework provides two commonly encountered contract levels:

| Contract | Role |
|---|---|
| `Lifecycle` | Declares `start()`, `stop()`, and `isRunning()` so that a component can be started, stopped, and queried for its state. |
| `SmartLifecycle` | Extends `Lifecycle`, adding auto-startup, lifecycle ordering via `phase`, and a callback for the stop operation. |

`SmartLifecycle` inherits the component lifecycle concept and adds important methods:

```java
public interface SmartLifecycle extends Lifecycle, Phased {

    boolean isAutoStartup();

    void stop(Runnable callback);
}
```

This is the core part of the contract to remember. In addition, `getPhase()` comes from `Phased`; `start()`, `stop()`, and `isRunning()` come from `Lifecycle`.

In the endpoint model, `AbstractEndpoint` provides the foundation for concrete endpoints to participate in this contract. Subclass endpoints decide what action to take when starting or stopping, such as subscribing/unsubscribing a handler with a channel or starting/stopping a polling task. Spring Integration users typically configure and control endpoints through DSL, XML, endpoint properties, or bean lifecycle; there is no need to create custom `AbstractEndpoint` subclasses for standard flows.

## 3. Lifecycle: initialization vs. start

The endpoint lifecycle has multiple milestones. Distinguishing them helps avoid wrong conclusions when debugging:

```text
Bean definition
      |
      v
Bean instantiated and configured
      |
      v
Initialized in ApplicationContext
      |
      v
Lifecycle start (if autoStartup is enabled)
      |
      v
Running <-------> Stopped
      |
      v
ApplicationContext shutdown / bean destruction
```

**Initialization** creates the object, injects dependencies, applies configuration, and performs internal setup steps. An initialized endpoint may appear in the ApplicationContext without receiving messages yet.

**Start** transitions the endpoint to the active state according to the contract. Depending on the endpoint type, this operation may register the handler as a subscriber or activate the polling schedule.

**Stop** instructs the endpoint to stop accepting new work according to its mechanism. The bean remains in the ApplicationContext and can be started again.

**Destroy** belongs to the bean/registration destruction and resource release phase. Stop does not mean destroy: stopping an endpoint does not remove the bean from the context, nor does it automatically delete messages currently sitting in a queue.

Spring manages `SmartLifecycle` beans during ApplicationContext refresh and closing. Beans that allow auto-startup are started according to their phase. When the context shuts down, Spring instructs them to stop in reverse phase order and complete the required lifecycle callbacks.

## 4. Key methods of SmartLifecycle

| Method | Operational Meaning |
|---|---|
| `start()` | Instructs the endpoint to start operating. Can be called automatically when the context starts or invoked manually. |
| `stop()` | Instructs the endpoint to stop. The bean still exists and can be started again. |
| `stop(Runnable callback)` | Instructs it to stop and notifies via the callback when the stop process completes. Useful for components that need to stop asynchronously. |
| `isRunning()` | Indicates the current lifecycle state of the component. |
| `isAutoStartup()` | Tells Spring whether to automatically start the component during context startup. |
| `getPhase()` | Returns the phase used to order start/stop across components. |

Start/stop operations are designed to control component state; applications should not assume that calling `start()` multiple times creates multiple consumers or that calling `stop()` deletes message data. Exact behavior under concurrent operations must follow the contract and the endpoint implementation in the version being used.

`isRunning()` only reflects the lifecycle state. It does not indicate how many messages the endpoint has processed, whether the handler is failing, whether the queue is congested, or whether downstream is ready. To evaluate flow health, combine lifecycle state with logs, metrics, queue depth, and tracing.

## 5. autoStartup: does the endpoint start automatically with ApplicationContext?

`autoStartup` determines whether Spring automatically starts the endpoint during context startup. For endpoints that need to wait for resources, tenants, configuration, or business conditions to be ready, auto-startup can be disabled and the endpoint can be started manually later.

Example of configuring an endpoint in Java DSL:

```java
@Bean
IntegrationFlow ordersFlow(OrderHandler handler) {
    return IntegrationFlow.from("ordersInput")
            .handle(handler, endpoint -> endpoint
                    .id("ordersConsumer")
                    .autoStartup(false))
            .get();
}
```

Here, the `autoStartup(false)` configuration is attached to the endpoint created for the processing step. The flow and related beans are still registered; the endpoint does not start automatically via the context's auto-startup mechanism. Once the required conditions are ready, the application can control the endpoint lifecycle through the corresponding runtime bean or a configured management mechanism.

The runtime bean name of an endpoint may be generated from its ID and DSL structure. You should not guess the bean name solely from the `@Bean` method name returning `IntegrationFlow`. When manual control is needed, identify the actual endpoint bean via ID configuration, ApplicationContext, or enabled observability tools.

Example of operating on an identified endpoint bean:

```java
Lifecycle endpoint = applicationContext.getBean(
        "configuredEndpointBeanName", Lifecycle.class);

if (!endpoint.isRunning()) {
    endpoint.start();
}

// When it is necessary to stop receiving new messages:
endpoint.stop();
```

`configuredEndpointBeanName` is the actual endpoint bean name in the application, not a fixed name applicable to every flow. In production applications, this operation should be encapsulated in a lifecycle management component rather than letting multiple services arbitrarily start/stop endpoints.

## 6. phase: controlling start and stop order

`phase` is an integer provided by `Phased`. Spring uses phase to order components implementing `SmartLifecycle`:

- Lower phase starts earlier.
- Higher phase starts later.
- On shutdown, the stop order is reversed: higher phase stops earlier.

This is useful when endpoints have operational dependencies. For example, at startup you want the downstream consumer to be ready before the upstream producer begins emitting messages. You can place the consumer at a lower phase and the producer at a higher phase. At shutdown, the producer will be instructed to stop before the consumer, helping prevent continuing to emit messages into a stopped consumer.

```text
Startup (ascending phase):
Consumer / downstream  --->  Producer / upstream
       low phase               high phase

Shutdown (descending phase):
Producer / upstream  --->  Consumer / downstream
       high phase              low phase
```

Do not set phase arbitrarily or treat phase as a message processing priority level. Phase only controls lifecycle ordering among components managed by this mechanism; it does not determine message ordering, thread counts, throughput, or task priority in an executor.

When there are multiple endpoints, choose phase values based on actual dependencies. Avoid creating too many phase groups that make operations hard to understand. If there is no special ordering requirement, keep the configuration simple and rely on the system's default ordering.

## 7. Event-driven endpoints and polling endpoints

The lifecycle contract is the same at the start/stop level, but the work performed on start differs depending on the endpoint type.

### 7.1. EventDrivenConsumer

With a `SubscribableChannel` such as `DirectChannel`, an event-driven endpoint registers the message handler as a subscriber. When the endpoint starts, the handler is registered to receive messages. When the endpoint stops, the endpoint unsubscribes the subscriber according to its implementation.

```text
DirectChannel ---> EventDrivenConsumer ---> MessageHandler
                       |
                    start: subscribe
                    stop: unsubscribe
```

Because `DirectChannel` typically invokes subscribers on the sending thread, an event-driven endpoint does not necessarily create a separate background thread. The execution thread depends on the channel and subsequent coordinating components.

If the endpoint stops, messages sent to the channel are not processed by that endpoint. `DirectChannel` is not a queue that holds messages waiting for the endpoint to run again. The send result depends on subscribers and channel configuration; producers should check the send result or handle errors appropriately.

### 7.2. PollingConsumer

With a `PollableChannel` such as `QueueChannel`, a polling endpoint uses a poller to retrieve messages on a schedule. When starting, the endpoint activates the polling mechanism; when stopping, the polling task is stopped or cancelled according to the lifecycle.

```text
QueueChannel ---> PollingConsumer ---> MessageHandler
                       |
                    start: schedule poll
                    stop: cancel polling
```

Messages already in the queue usually remain after the endpoint stops and can be retrieved when the endpoint starts again. Stopping an endpoint is not purging the queue. If messages are stored in a `MessageStore`, retention time and recovery also depend on the store, configuration, and application policies.

A poller can run on a fixed delay, fixed rate, or cron trigger, and can limit the number of messages per poll. Those properties determine the polling cadence; they do not change the meaning of the lifecycle contract.

## 8. Stop, callbacks, and graceful shutdown

When Spring shuts down the ApplicationContext, the lifecycle processor instructs `SmartLifecycle` components to stop in phase order. For components that can stop asynchronously, `stop(Runnable callback)` allows notifying Spring when stopping has completed.

A stopped endpoint typically stops accepting new work according to the endpoint's mechanism. However, you should not assume that every message or task received prior to the stop time is cancelled immediately. A handler may be performing I/O, an executor may already have accepted a task, or a transaction may be in the process of completing.

For controlled shutdown, clearly determine:

- In which phases producers need to stop before consumers.
- Whether the endpoint is using polling or event-driven subscription.
- What policy governs completing, waiting for, or cancelling tasks already handed to an executor.
- How queues and message stores retain messages during shutdown.
- How transactions, retries, and error flows handle in-flight messages.
- Whether the shutdown timeout is appropriate for the handler's maximum processing time.

`stop()` does not mean `destroy()`, and neither automatically means deleting pending messages. If the application needs to drain a queue or discard messages, implement a dedicated, controlled policy aligned with business requirements.

## 9. Controlling endpoints while the application is running

In an operational environment, it may be necessary to pause an endpoint for downstream maintenance, configuration changes, or load control. Control operations should be centralized in a management component instead of letting business services depend directly on endpoints.

A management component can inject `ApplicationContext` or an appropriate registry to look up an endpoint by its known bean name/ID, then invoke the lifecycle API. For dynamically registered flows, `IntegrationFlowContext` and `IntegrationFlowRegistration` provide handles to manage registrations; distinguish between stopping a registration and destroying a registration.

Spring Integration also supports Control Bus for sending administrative commands to integration components when this feature is configured. Control Bus can be useful for starting/stopping endpoints via administrative messages, but access must be restricted and only permitted operations should be exposed in the deployment environment.

Integration Graph and management tools can help identify components and connection relationships. However, the graph describes topology; `isRunning()` state and metrics are what help determine how an endpoint is operating. Do not use a single observation source to conclude that the entire flow is healthy.

## 10. Diagnosing common lifecycle issues

| Symptom | Cause to Check | Resolution |
|---|---|---|
| Endpoint bean exists but does not receive messages | `autoStartup=false`, endpoint has been stopped, or has not started yet. | Check `isRunning()` and the startup mechanism. |
| Polling endpoint does not retrieve messages from the queue | Poller is not running, scheduler is inactive, wrong trigger, or endpoint is stopped. | Check lifecycle, scheduler, trigger, and poll logs. |
| Event-driven endpoint does not receive messages | Handler is not subscribed, wrong input channel, or endpoint is stopped. | Check subscriber, channel wiring, and lifecycle. |
| Endpoint is running but messages still fail | Handler exception, downstream error, transaction/retry, or error channel. | Check logs, error flow, retry, and dependencies. |
| Shutdown takes a long time | Handler is processing slowly, executor still has tasks, or stop callback has not completed. | Check in-flight work, timeout, and graceful shutdown mechanism. |
| Messages remain in the queue after stop | Stop does not purge the queue. | Check queue depth and decide when to restart or drain according to policy. |

The inspection workflow should move from state to data:

1. Identify the exact endpoint bean and read `isRunning()`.
2. Check `isAutoStartup()` and `getPhase()` if the endpoint implements `SmartLifecycle`.
3. Determine whether the endpoint is event-driven or polling; inspect the corresponding subscriber or scheduler.
4. Inspect channels, queue depth, executor, and in-flight messages.
5. Read logs, error channels, retries, and transactions to find processing errors.
6. After fixing, test start/stop and send a test message to confirm the endpoint receives the expected message.

## 11. Extension: when should you subclass AbstractEndpoint?

Most applications should use built-in endpoints via Java DSL or XML: service activators, transformers, filters, routers, inbound/outbound adapters, and the corresponding consumer endpoints. These abstractions already integrate with Spring Integration's lifecycle.

Consider subclassing `AbstractEndpoint` only when developing a new infrastructure endpoint type that built-in endpoints do not cover. In that case, the implementation must clearly define start/stop actions, manage subscriptions or schedulers, handle created resources, prevent duplicate registrations, and clean up at the right time. It must also define behavior for repeated start/stop calls and ApplicationContext shutdown.

Do not subclass `AbstractEndpoint` just to add business logic. Business logic belongs in handlers/services; the endpoint is responsible for wiring and lifecycle. Separating these two roles makes the endpoint easy to test and avoids turning infrastructure lifecycle into part of business logic.

## 12. Self-check

**Scenario:** A `PollingConsumer` has been created as a bean but configured with `autoStartup=false`. The application sends messages to a `QueueChannel`, the queue grows steadily, and the handler is not invoked.

1. Why does the bean exist while the handler has not received any messages?
2. When `start()` is called on the endpoint, what mechanism is activated?
3. If the endpoint is stopped after the queue has 20 messages, are those 20 messages automatically deleted?
4. If there is a producer endpoint that needs to stop before the consumer during shutdown, which property should be considered?

**Suggested answers:** (1) Creating a bean does not mean the endpoint has started; `autoStartup=false` prevents Spring from automatically starting the endpoint. (2) A polling endpoint activates its poll schedule to retrieve messages from the channel. (3) No; stopping stops polling, and the queue usually retains messages according to its storage policy. (4) Use `phase` to order start and stop among `SmartLifecycle` components.

**Hands-on exercise:** Create a flow that receives messages from a `QueueChannel` using a polling endpoint. Try configuring `autoStartup=false`, observe the queue depth, then start the endpoint and watch the messages get processed. Next, stop the endpoint while the queue still has messages, verify the messages remain, and start it again to resume processing. Finally, replace it with a `DirectChannel` and compare the behavior when the endpoint stops.

## References

- [Spring Integration Reference — Endpoint](https://docs.spring.io/spring-integration/reference/endpoint.html)
- [Spring Integration Javadoc — AbstractEndpoint](https://docs.spring.io/spring-integration/api/org/springframework/integration/endpoint/AbstractEndpoint.html)
- [Spring Framework Javadoc — SmartLifecycle](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/SmartLifecycle.html)
- [Spring Framework Reference — Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html#beans-factory-lifecycle)
- [Spring Integration Reference — Control Bus](https://docs.spring.io/spring-integration/reference/control-bus.html)
