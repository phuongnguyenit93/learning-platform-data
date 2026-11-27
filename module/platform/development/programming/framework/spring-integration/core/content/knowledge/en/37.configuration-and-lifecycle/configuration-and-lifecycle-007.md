# Phase and Lifecycle

In the **Configuration and Lifecycle** chapter of the **SPRING_INTEGRATION_CORE** module, this lesson explains how to control when components start and stop processing messages. The goal is to use `phase`, `autoStartup`, and lifecycle operations to bring a Spring Integration flow into operation in the right order.

These concepts apply to endpoints wrapping transformers, filters, routers, service activators, and aggregators, as well as adapters or gateways with their own lifecycles. We still design business logic using `Message`, `MessageChannel`, and Java DSL; lifecycle adds how to operate that flow when the application starts, pauses, or shuts down.

The main examples use Java 17+, Spring Integration 6.5, and Spring Framework 6.2. Dependencies must be managed with a compatible version set. The phase numbers in the examples are design choices for this lesson, not framework defaults.

## 1. Real-World Problem: Source Is Running Before Destination Is Ready

Suppose an application receives orders through the following flow:

~~~text
Order source → pendingOrders → Normalize code → completedOrders
~~~

At startup, we want the processor ready to accept work before enabling the work-producing source. At shutdown, we want to block intake first, then give accepted work a chance to finish.

If you only look at the order of `@Bean` methods in a configuration file, it is easy to mistakenly assume the flow will operate in that exact order. However, there are at least three distinct concerns:

| Concern | Question to Answer | Example |
| --- | --- | --- |
| Bean creation and initialization | Has the object been created, injected, and configured? | Creating channels and assigning handlers |
| Component startup | Has the component started receiving or emitting messages? | Registering subscribers, scheduling polling |
| Business readiness | Can the component actually serve current requests? | Is the target service responding, is reference data loaded? |

Initialization callbacks like `@PostConstruct` serve bean preparation. `start()`/`stop()` operations serve bringing a component into or out of operation. Those are two different callback groups in Spring. [Bean lifecycle documentation](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html).

In the order scenario, a consumer bean may already exist without having started polling. Conversely, the consumer may already be running while the payment system it calls is failing. When designing operations, clarify which condition you are waiting for.

## 2. Lifecycle Contracts to Know

### 2.1. Lifecycle: Start, Stop, and State

The `Lifecycle` interface provides three core operations:

~~~java
void start();
void stop();
boolean isRunning();
~~~

It describes the operational state of a component. Calling `stop()` does not mean deleting the bean or closing the entire `ApplicationContext`; a component supporting restart can be `start()`ed again later. [Lifecycle Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/Lifecycle.html).

For this lesson, picture the consumer as having two observable states:

~~~mermaid
stateDiagram-v2
    [*] --> Stopped: Bean initialized
    Stopped --> Running: start()
    Running --> Stopped: stop()
    Stopped --> [*]: Bean destroyed
~~~

The diagram only depicts simple operational states. A real implementation may also have work completing during a state transition.

### 2.2. SmartLifecycle: Auto-Startup and Ordering

`SmartLifecycle` extends the contract above with the following details:

| Contract Member | Meaning |
| --- | --- |
| `isAutoStartup()` | Whether to participate in auto-startup when the context refreshes |
| `getPhase()` | Ordering group for startup and shutdown |
| `stop(Runnable callback)` | Signals completion when stopping can occur asynchronously |

When a component implements asynchronous shutdown, it must invoke `callback.run()` after finishing its shutdown per its contract. A forgotten callback can cause the coordinator to wait until timeout. [SmartLifecycle Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/SmartLifecycle.html).

`autoStartup(false)` is an option for controlling explicit startup. It does not remove the bean from the context and does not replace a readiness check mechanism. In the order example, we use it to keep the source stopped while testing the consumer.

### 2.3. LifecycleProcessor as the Coordinator

When the context refreshes or closes normally, the lifecycle processor coordinates lifecycle beans by phase groups. `DefaultLifecycleProcessor` also handles context-level start/stop requests. [DefaultLifecycleProcessor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html).

Therefore, distinguish between:

- `context.start()`: a context-level request that can start multiple components.
- `endpoint.start()`: a direct request for a single endpoint.
- Calling a business method on a service: may not go through an endpoint or respect endpoint state.

In an operations tool, using the exact endpoint ID keeps the operation's scope clear.

## 3. Rules of Phase

### 3.1. Lower Phase Starts First, Stops Last

For phase-coordinated components with no dependency constraints altering the order:

~~~text
Startup:   lower phase → higher phase
Shutdown:  higher phase → lower phase
~~~

Components in the same phase have no relative order guaranteed by phase alone. Explicit `depends-on` relationships take precedence over phase order. [Ordering rules in SmartLifecycle](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/SmartLifecycle.html).

For the order flow, an illustrative allocation is:

| Component | Application-Chosen Phase | Startup | Shutdown |
| --- | ---: | --- | --- |
| Application-managed lifecycle infrastructure | 0 | Before steps below | After steps below |
| Order normalization consumer | 100 | Before source | After source |
| Order-producing source | 200 | After consumer | Before consumer |

~~~mermaid
flowchart LR
    subgraph Startup["Illustrative startup order"]
        A["Infrastructure: 0"] --> B["Consumer: 100"] --> C["Source: 200"]
    end
    subgraph Shutdown["Illustrative shutdown order"]
        D["Source: 200"] --> E["Consumer: 100"] --> F["Infrastructure: 0"]
    end
~~~

This is a local convention to explain design intent. If the application uses executors, schedulers, or listener containers provided by a library, inspect the actual lifecycle of those beans instead of assuming all infrastructure sits at phase 0.

### 3.2. Phase Is Not a Delay or Message Priority

A value of `200` does not mean waiting 200 milliseconds. Phase does not assign priority to individual messages and does not replace polling intervals.

For example, a phase 100 consumer can still use a poller spaced 50 milliseconds apart. The first number describes operational order; the second describes the work-checking schedule.

If step A must finish processing an order before step B processes that same order, express that relationship with channels, request-reply, correlation, or an appropriate business synchronization mechanism. Putting A at phase 100 and B at phase 200 does not describe per-order processing order.

### 3.3. Direct start() Calls Do Not Reorder the Whole Application

Suppose operational code calls:

~~~java
orderIngress.start();
normalizeOrder.start();
~~~

Those are two direct calls in the order chosen by the author. No context-wide coordination pass is created merely because both objects have phases.

If you need to start a group, use an appropriate group coordinator, or explicitly put the necessary checks and ordering into coordination code. Setting phases still helps for container-managed start/stop sweeps.

## 4. Which Component Owns Phase in Spring Integration?

A processing step typically has two layers to distinguish:

~~~text
Endpoint
  ├─ manages connection to the input channel and lifecycle
  └─ invokes MessageHandler
       └─ performs transform, filter, or business logic
~~~

`ConsumerEndpointFactoryBean` chooses the endpoint type based on the input channel: `PollableChannel` leads to a polling consumer; `SubscribableChannel` leads to an event-driven consumer. [ConsumerEndpointFactoryBean source, 6.5.x branch](https://raw.githubusercontent.com/spring-projects/spring-integration/6.5.x/spring-integration-core/src/main/java/org/springframework/integration/config/ConsumerEndpointFactoryBean.java).

With `EventDrivenConsumer`, starting registers the handler with the channel; stopping unregisters it. If the handler also has a lifecycle, the endpoint also coordinates the handler's lifecycle. [EventDrivenConsumer source, 6.5.x branch](https://raw.githubusercontent.com/spring-projects/spring-integration/6.5.x/spring-integration-core/src/main/java/org/springframework/integration/endpoint/EventDrivenConsumer.java).

In Java DSL:

~~~java
.transform(
    transformer,
    endpoint -> endpoint
        .id("normalizeOrder")
        .phase(100)
        .autoStartup(true)
)
~~~

The second lambda configures the transform step's endpoint. It does not attach a phase to individual messages, nor does it alter channel storage policies. [ConsumerEndpointSpec API](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/ConsumerEndpointSpec.html).

A `@MessagingGateway` provides an entry point for business calls. When designing lifecycle, you still must identify which specific endpoint or proxy must be controlled and whether downstream consumers are ready. Having a gateway does not automatically create a durable queue or a mechanism waiting for all components to become ready. [IntegrationFlow starting from a gateway](https://docs.spring.io/spring-integration/reference/6.5/dsl/integration-flow-as-gateway.html).

### Reading Default Values by Endpoint Type

Do not generalize that every Spring Integration component shares the same default phase. Examples in the 6.5.x source branch:

| Implementation | Initial Phase When Not Reconfigured |
| --- | --- |
| Base class `AbstractEndpoint` | `0` |
| `AbstractPollingEndpoint` | `Integer.MAX_VALUE / 2` |
| `EventDrivenConsumer` | `Integer.MIN_VALUE`, or `Integer.MIN_VALUE + 1000` when handler is `MessageProducer` |

These values are declared in [AbstractEndpoint](https://raw.githubusercontent.com/spring-projects/spring-integration/6.5.x/spring-integration-core/src/main/java/org/springframework/integration/endpoint/AbstractEndpoint.java), [AbstractPollingEndpoint](https://raw.githubusercontent.com/spring-projects/spring-integration/6.5.x/spring-integration-core/src/main/java/org/springframework/integration/endpoint/AbstractPollingEndpoint.java), and [EventDrivenConsumer](https://raw.githubusercontent.com/spring-projects/spring-integration/6.5.x/spring-integration-core/src/main/java/org/springframework/integration/endpoint/EventDrivenConsumer.java).

The table describes the named implementations, not every adapter and gateway. For steps requiring clear operational ordering, set phase explicitly and observe `getPhase()` on the actual endpoint.

## 5. Java DSL Example: Consumer Starts First, Source Starts Explicitly

### 5.1. Design

We use two in-memory channels:

~~~text
orderIngress (phase 200, does not auto-start)
       │
       ▼
pendingOrders: QueueChannel
       │
       ▼
normalizeOrder (phase 100, auto-starts, with poller)
       │
       ▼
completedOrders: QueueChannel
~~~

`pendingOrders` holds inputs waiting for normalization. `completedOrders` is just where the demo program retrieves results; in a real application, it can be replaced by the next processing step.

Preparation requirements:

- Include the `org.springframework.integration:spring-integration-core` dependency from your selected version set.
- Have Java 17 or later.
- Place the class below in a Java project with an appropriate Spring classpath.
- If running inside Spring Boot, integrate the configuration into the existing context; the `main` method below is for a standalone Spring application.

~~~java
import java.util.Locale;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class PhaseLifecycleDemo {

    @Configuration
    @EnableIntegration
    public static class FlowConfig {

        @Bean
        public QueueChannel pendingOrders() {
            return new QueueChannel(100);
        }

        @Bean
        public QueueChannel completedOrders() {
            return new QueueChannel(100);
        }

        @Bean
        public IntegrationFlow orderIngressFlow(
                @Qualifier("pendingOrders") QueueChannel pendingOrders) {

            AtomicInteger sequence = new AtomicInteger();

            return IntegrationFlow.fromSupplier(
                    () -> " order-" + sequence.incrementAndGet() + " ",
                    source -> source
                            .id("orderIngress")
                            .phase(200)
                            .autoStartup(false)
                            .sendTimeout(1000)
                            .poller(Pollers.fixedDelay(250)
                                    .maxMessagesPerPoll(1)))
                    .channel(pendingOrders)
                    .get();
        }

        @Bean
        public IntegrationFlow orderProcessingFlow(
                @Qualifier("pendingOrders") QueueChannel pendingOrders,
                @Qualifier("completedOrders") QueueChannel completedOrders) {

            return IntegrationFlow.from(pendingOrders)
                    .<String, String>transform(
                            value -> value.trim().toUpperCase(Locale.ROOT),
                            endpoint -> endpoint
                                    .id("normalizeOrder")
                                    .phase(100)
                                    .autoStartup(true)
                                    .poller(Pollers.fixedDelay(50)
                                            .receiveTimeout(0)
                                            .maxMessagesPerPoll(1)))
                    .channel(completedOrders)
                    .get();
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(FlowConfig.class)) {

            SmartLifecycle ingress =
                    context.getBean("orderIngress", SmartLifecycle.class);
            SmartLifecycle consumer =
                    context.getBean("normalizeOrder", SmartLifecycle.class);

            QueueChannel input =
                    context.getBean("pendingOrders", QueueChannel.class);
            QueueChannel output =
                    context.getBean("completedOrders", QueueChannel.class);

            require(consumer.isRunning(), "Consumer must auto-start");
            require(!ingress.isRunning(), "Source must wait to be started explicitly");

            Message<String> manualOrder = MessageBuilder
                    .withPayload(" manual-1 ")
                    .build();

            require(input.send(manualOrder, 1000), "Failed to send manual order");

            Message<?> manualResult = output.receive(3000);
            require(manualResult != null, "Did not receive manual result");
            require("MANUAL-1".equals(manualResult.getPayload()),
                    "Normalized result is incorrect");

            System.out.println("manual=" + manualResult.getPayload());
            System.out.println("consumer.phase=" + consumer.getPhase());
            System.out.println("ingress.phase=" + ingress.getPhase());

            ingress.start();

            Message<?> generatedResult = output.receive(3000);
            require(generatedResult != null, "Source has not produced a result");
            System.out.println("generated=" + generatedResult.getPayload());

            ingress.stop();

            require(!ingress.isRunning(), "Source did not transition to stopped state");
            require(consumer.isRunning(), "Consumer must remain running");

            System.out.println("ingress.running=" + ingress.isRunning());
            System.out.println("consumer.running=" + consumer.isRunning());
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }
}
~~~

`IntegrationFlow.fromSupplier(...)` creates a polling-triggered message source. Source options such as `phase`, `autoStartup`, and `sendTimeout` are applied via the source endpoint spec. [IntegrationFlow API, 6.5.x branch](https://raw.githubusercontent.com/spring-projects/spring-integration/6.5.x/spring-integration-core/src/main/java/org/springframework/integration/dsl/IntegrationFlow.java), [SourcePollingChannelAdapterSpec, 6.5.x branch](https://raw.githubusercontent.com/spring-projects/spring-integration/6.5.x/spring-integration-core/src/main/java/org/springframework/integration/dsl/SourcePollingChannelAdapterSpec.java).

### 5.2. Interpreting Expected Output

When practiced successfully, expected business output is:

~~~text
manual=MANUAL-1
consumer.phase=100
ingress.phase=200
generated=ORDER-1
ingress.running=false
consumer.running=true
~~~

Framework log lines may appear interleaved. This is the expected output of the example, not a transcript of an execution performed inside this documentation.

Meaningful observations:

1. After the context finishes creating, the consumer is running while the source is not.
2. The order sent manually to `pendingOrders` is still processed. Stopping the source affects only that source; the program can still send to the channel by another path.
3. After `ingress.start()`, messages from the supplier flow through the same consumer.
4. After `ingress.stop()`, the consumer remains in the running state.
5. `try-with-resources` closes the context upon exiting the block, even if a check throws an exception.

The `ingress.start()` call here only illustrates starting the source individually; it does not re-verify the readiness of every other component.

### 5.3. Observing Automatic Phase Ordering

To observe both endpoints auto-starting, create a variant:

- Change the source to `autoStartup(true)`.
- Remove the assertion requiring the source to be stopped and remove the assumption that the first result is the manual order.
- Enable appropriate lifecycle logging and observe the start/stop events of the two endpoint IDs.

With explicit phases 100 and 200 in this configuration, the desired order is consumer before source on startup, and source before consumer when closing the context. Do not use the order of `println` lines after context creation finishes to infer the startup order that already happened earlier.

## 6. Channel Choice Changes the Meaning of Stopping

### 6.1. With QueueChannel

`QueueChannel` can hold messages when the consumer has not yet received them, as long as capacity remains. By default, contents are held in memory; for durability, configure an appropriate message store or use an external mechanism. With `DirectChannel`, the handler runs directly on the sending thread and the channel provides no queue-like buffer. [MessageChannel Implementations](https://docs.spring.io/spring-integration/reference/6.5/channel/implementations.html).

In the example, if the consumer stops while data continues arriving, expect `pendingOrders` occupancy to grow. With a 100-item bounded queue, define what happens when space runs out and how long send timeouts are allowed.

An easy-to-observe practice scenario is setting both endpoints to `autoStartup(false)` when creating the context, then:

1. Send an order to `pendingOrders`.
2. Verify no result exists yet in `completedOrders`.
3. Start the consumer and receive the result.
4. Start the source only after verifying the consumer.

This preparation avoids reasoning about an in-progress poll when stopping a consumer midway.

### 6.2. With DirectChannel

When a consumer endpoint unsubscribes and the channel has no remaining matching subscribers, the next send has no handler and may report a dispatch error. Stopping the consumer also does not turn the channel into a queue.

With synchronous flows, do not use the approach of "pausing the consumer and letting senders queue inside `DirectChannel`." Actively block intake or choose a channel with suitable buffering capability.

If a handler was already invoked before the stop moment, unsubscribing does not mean the in-progress work is recalled. This is why in-flight work must be tracked separately from endpoint state.

## 7. Phase and Controlled Shutdown

### 7.1. Stopping in the Right Order Does Not Guarantee Queue Draining

Consider the moment shutdown begins:

~~~text
pendingOrders still has 30 orders
source at phase 200
consumer at phase 100
~~~

Phase coordination may request stopping the source first and then the consumer. The interval between those two calls does not automatically become a window long enough to process 30 orders.

In this example, distinguish:

| Observation | Can Conclude | Cannot Conclude |
| --- | --- | --- |
| Source reports `isRunning() == false` | Source transitioned its lifecycle state | No tasks or messages are still incoming |
| Queue has size 0 | No items waiting at the moment of observation | No handler is currently processing or transaction committing |
| Consumer reports `isRunning() == true` | Consumer is in the active state | All orders processed successfully |
| One result received | That corresponding order reached the observation point | The entire flow has no remaining work |

The table is a way to analyze the order scenario, not a built-in drain protocol.

### 7.2. An Application-Designed Drain Sequence

For systems needing to finish accepted work, you can design these steps:

1. Stop accepting new requests at the application boundary.
2. Stop or pause sources, then confirm in-flight intake tasks have stabilized per the adapter's contract.
3. Keep consumers, error-handling paths, and required resources running.
4. Wait for completion conditions with a time limit.
5. Stop remaining processing components and close resources.

Completion conditions must reflect the application. A simple model to consider:

~~~text
inputs are quiet
AND no pending messages remain
AND no in-flight work remains
AND required transactions or acknowledgments have completed
~~~

If an executor is used, also account for tasks already submitted to the executor but not yet processed. If an aggregator is used, decide how to handle incomplete message groups. If retry is used, decide whether work awaiting retry should finish, be persisted, or move elsewhere.

Do not wait indefinitely for an aggregator group whose missing items can never arrive once the source has stopped. That situation requires a business decision on timeout, state persistence, or partial handling.

### 7.3. Spring Integration's Orderly Shutdown Mechanism

Spring Integration provides `IntegrationMBeanExporter.stopActiveComponents(timeout)` to support orderly shutdown. This mechanism prepares components supporting `OrderlyShutdownCapable`, throttles intake sources, and grants a window for in-flight messages. The documentation also notes keeping pollers active so messages in queues have a chance to finish processing. [Orderly Shutdown](https://docs.spring.io/spring-integration/reference/6.5/shutdown.html).

This is a dedicated coordination mechanism that must be configured and invoked appropriately. Do not infer that merely setting `phase` activates that entire procedure.

With systems storing orders in in-memory queues, make an explicit choice when the timeout expires while data remains: extend the timeout, hand off data, or accept the model's limitations. Lifecycle ordering does not add storage durability by itself.

## 8. Shutdown Timeout and Completion Callbacks

In a standalone Spring application, you can configure the lifecycle processor using the standard bean name:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.support.DefaultLifecycleProcessor;

// Method placed inside a @Configuration class.
@Bean(name = "lifecycleProcessor")
public static DefaultLifecycleProcessor lifecycleProcessor() {
    DefaultLifecycleProcessor processor = new DefaultLifecycleProcessor();
    processor.setTimeoutPerShutdownPhase(20_000);
    return processor;
}
~~~

`setTimeoutPerShutdownPhase` sets the wait time in milliseconds per phase group during shutdown. It is not a single overall timeout for the entire application. [DefaultLifecycleProcessor timeout configuration](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html).

For example, if multiple phases each have to wait on components stopping asynchronously, total context close time can exceed 20 seconds. Conversely, a phase that finishes quickly does not wait the full 20 seconds.

For a custom lifecycle component, picture the stop contract as follows; this is design pseudocode, not an existing API:

~~~text
stop(callback):
    stop accepting new work
    request current tasks to finish
    when stop conditions are met:
        update state to stopped
        invoke callback exactly once
~~~

The implementation must also handle the case where there is no work to wait for. Invoking the callback too early misleads the coordinator into thinking stopping is complete; failing to invoke it keeps the coordinator waiting.

A timeout does not force an indefinitely blocking `stop()` method to terminate, does not automatically roll back business work, and does not automatically wait for all messages to finish. Therefore, I/O operations, retries, and drain procedures still need their own bounds.

If the application already configures a lifecycle processor through its runtime platform, use that platform's configuration mechanism rather than adding a bean with a duplicate name.

## 9. Controlling a Group of Endpoints with Roles

When multiple sources must start or stop together, you can assign a role to endpoints:

~~~java
endpoint -> endpoint
        .id("orderIngress")
        .phase(200)
        .autoStartup(false)
        .role("order-import")
~~~

Then, a coordinating component can use `SmartLifecycleRoleController`:

~~~java
roleController.startLifecyclesInRole("order-import");
roleController.stopLifecyclesInRole("order-import");
~~~

Roles group components for lifecycle control; they are not access permissions or channel names. When starting a group depends on leadership election, setting `autoStartup(false)` avoids starting sources before a leader decision is made. [Endpoint Roles](https://docs.spring.io/spring-integration/reference/6.5/endpoint-roles.html).

A helpful convention for the order scenario is grouping order-import sources into a dedicated role so consumers continue processing backlog when imports are paused. Only group both sources and consumers into the same stop action if that is genuinely the operational intent.

For dynamically registered flows, use `IntegrationFlowContext` to manage flow registration and lifecycle. Adding a flow after the context is already running does not cause already-running beans to restart according to the new phase. [Dynamic and Runtime Integration Flows](https://docs.spring.io/spring-integration/reference/6.5/dsl/java-runtime-flows.html).

## 10. Error Handling and Observability During Lifecycle Changes

Lifecycle alters the ability to accept work, while message processing errors require their own handling path.

In a synchronous flow via `DirectChannel`, handler errors can propagate back to the sending thread. For polling tasks or asynchronous processing managed by Spring Integration, errors can be wrapped into an `ErrorMessage` and sent to the configured error channel. Not every error during context startup becomes a message on `errorChannel`. [Error Handling](https://docs.spring.io/spring-integration/reference/6.5/error-handling.html).

In the order scenario, record the following data to understand each state transition:

| Observed Data | Question Answered |
| --- | --- |
| Endpoint ID, phase, auto-startup, running | Which components are expected to be running right now? |
| Start/stop request and completion timestamps | Which coordination step is taking long? |
| Queued message count and oldest wait duration | Is there a backlog needing processing before closing? |
| In-flight task count and acknowledged result count | Is an empty queue actually due to finished work? |
| Errors, retries, and routing to error handlers | Where is failed work located? |

When keeping consumers active to drain, error-handling paths and the resources they use must also remain available. If you shut down error handlers too early, a late business error can make shutdown harder to trace.

To inspect an endpoint's configuration directly in the example:

~~~java
SmartLifecycle endpoint =
        context.getBean("normalizeOrder", SmartLifecycle.class);

System.out.println("phase=" + endpoint.getPhase());
System.out.println("autoStartup=" + endpoint.isAutoStartup());
System.out.println("running=" + endpoint.isRunning());
~~~

These lines give the component's state at the moment of reading. To conclude that the system is ready or out of work, combine them with the defined business conditions.

## 11. Common Misconceptions

| Misconception | Accurate Understanding and Action |
| --- | --- |
| Higher phase starts first | Use ascending order on startup, descending order on shutdown |
| Declaring a `@Bean` method first makes its endpoint run first | Configure order via actual lifecycle and dependencies |
| Same phase guarantees fixed order | Do not rely on phase to order two components with the same value |
| `autoStartup(false)` means no bean is created | The bean still needs to be created and configured so it can be started explicitly |
| Stopping a source blocks every send path to the channel | Check gateways, direct calls, and other sources too |
| Stopping a consumer makes `DirectChannel` buffer data | Choose an appropriate buffer if pending work must be held |
| `isRunning()` proves business logic succeeds | Track processing outcomes and business acknowledgments separately |
| Empty queue proves draining is complete | Check in-flight work, executors, transactions, and aggregator groups |
| Increasing shutdown timeout guarantees zero message loss | Design storage, acknowledgments, retries, and completion conditions too |
| Phase alone controls the entire shutdown | Identify coordinators, stop contracts, and time bounds |

## 12. Applying to a Concrete Flow

Before choosing phase values, name the components by role: who produces work, who receives work, who holds waiting data, and who confirms completion. Then choose startup order, shutdown order, and conditions to check in between.

In this lesson's example, the design decision is: normalization consumer at phase 100, source at phase 200, and the source started explicitly after verifying the consumer. Two queues allow observing messages passing through points of the flow, while a drain policy still needs to be added if operational requirements demand finishing all accepted work.

When extending the flow with transformers, routers, filters, or aggregators, continue asking the same questions for each endpoint and asynchronous boundary. A clear message diagram, combined with explicit lifecycle contracts, explains both the data path and application behavior at startup and shutdown.
