# IntegrationManagement and managed components

When a Spring Integration system runs across multiple `MessageChannel`s, consumer endpoints, handlers, pollers, and executors, a "message sent but not processed" issue is very difficult to diagnose from business logs alone. Operators need to know which channel is receiving messages, which handler failed, which endpoint has stopped, which queue is building up, and why latency increased after a topology change.

Spring Integration provides a **management mechanism for runtime components**, centered around the <code>IntegrationManagement</code> interface. This mechanism helps with naming, configuring logging, and connecting supported components to Micrometer/Observation. Alongside this, there are the JMX exporter and the integration graph to inspect or control the runtime through separate channels.

This lesson belongs to the **Observability** chapter of the **SPRING_INTEGRATION_RUNTIME** module. We will understand what a *managed component* is, how to enable management with <code>@EnableIntegrationManagement</code>, how to observe channels/handlers/sources, distinguish metrics from traces and JMX, as well as how this relates to <code>IntegrationFlow</code> lifecycle, transactions, retries, message stores, error flows, correlation, threading, and performance.

> **Principle:** A component implementing <code>IntegrationManagement</code> **does not mean** it automatically becomes an exposed JMX MBean, automatically has traces, or automatically provides all business metrics. Manageability, meter registration, observation creation, and external data export are **separate configuration layers**.

## 1. What is a managed component?

Spring Integration has many types of runtime objects. Some are message channels, some read from sources on a schedule, some process messages, and some manage lifecycle or orchestrate flows. Framework components typically inherit from a base class that already supports management.

| Component | Examples | Runtime role | Useful observability data |
|---|---|---|---|
| Message channel | <code>DirectChannel</code>, <code>ExecutorChannel</code>, <code>QueueChannel</code> | Transports messages, dispatches to consumers | Send/receive counts, errors, channel operation latency, queue depth when supported |
| Message handler | Service activator, transformer, router, outbound gateway | Executes actions on a message | Processing duration, error count, handler name, processing span |
| Message source | JDBC/File/Kafka polling source, custom source based on <code>AbstractMessageSource</code> | Produces messages via polling | Successful receive count, message production rate, source errors |
| Inbound producer/gateway | Message-driven adapter, <code>MessagingGatewaySupport</code> | Receives events/requests from external systems | Processing duration, outcome, trace context |
| Endpoint lifecycle | <code>SourcePollingChannelAdapter</code>, <code>EventDrivenConsumer</code>, <code>PollingConsumer</code> | Start/stop, consumer registration or polling schedule | <code>isRunning()</code>, task status, scheduling errors |
| Message group store | Aggregator/resequencer persistence | Holds fragments and correlation metadata | Waiting group count, group age, timeout rate; may require custom instrumentation |

**Not every row in the table is the same interface.** Channels, handlers, and many sources support <code>IntegrationManagement</code>; endpoint lifecycle is typically controlled via <code>SmartLifecycle</code> or its corresponding registration. Some specialized statistics must be obtained from the store, executor, adapter, or application metrics, and are not necessarily properties of <code>IntegrationManagement</code>.

~~~mermaid
flowchart LR
    P["Inbound adapter / Source"] --> C["orders.input<br/>Managed channel"]
    C --> H["orders.process<br/>Managed handler"]
    H --> O["Outbound channel / Gateway"]
    M["IntegrationManagementConfigurer"] -. "Name, logging, and instrumentation" .-> C
    M -. "Name, logging, and instrumentation" .-> H
    R["MeterRegistry / ObservationRegistry"] -. "Metrics / spans" .-> C
    R -. "Metrics / spans" .-> H
    E["Optional JMX exporter"] -. "MBean view" .-> C
    E -. "MBean view" .-> H
~~~

The dashed arrows represent configuration/management relationships; message channels do not transport this management data.

## 2. The IntegrationManagement interface

In Spring Integration 6.x, the <code>org.springframework.integration.support.management.IntegrationManagement</code> interface extends <code>NamedComponent</code> and <code>DisposableBean</code>. This is the contract that tells the framework how to configure a **managed component**.

Key APIs to remember:

| API | Function |
|---|---|
| <code>getManagedName()</code> / <code>setManagedName(...)</code> | Managed name used for identification/display and instrumentation when supported by the component |
| <code>getManagedType()</code> / <code>setManagedType(...)</code> | Classification of the managed component |
| <code>isLoggingEnabled()</code> / <code>setLoggingEnabled(...)</code> | Controls the framework's routine debug logging at the component |
| <code>registerMetricsCaptor(...)</code> | Provides the Micrometer meter collection mechanism to the component, as supported by the version |
| <code>registerObservationRegistry(...)</code> | Provides the <code>ObservationRegistry</code> for the component to emit Observations |
| <code>isObserved()</code> | Indicates whether the component uses a non-NOOP ObservationRegistry per the interface contract |
| <code>getOverrides()</code> | Information about management properties configured manually, so the configurer does not overwrite them |
| <code>destroy()</code> | Lifecycle hook of the interface; does not mean deleting message stores or external infrastructure |

<code>IntegrationManagement.ManagementOverrides</code> is a structure that serves **configuration precedence**: if a property has been modified directly on the bean, <code>IntegrationManagementConfigurer</code> may refrain from reapplying the default value for that property.

Example of an explicitly configured managed channel:

~~~java
@Bean(name = "orders.input")
DirectChannel ordersInput() {
    DirectChannel channel = new DirectChannel();
    channel.setManagedName("orders.input");
    channel.setLoggingEnabled(false);
    return channel;
}
~~~

<code>DirectChannel</code> belongs to <code>org.springframework.integration.channel</code>. Manually setting <code>managedName</code> makes names easy to recognize when reading metrics; however, you should not generate random names per request or message ID. Disabling logging here only targets **routine flow logs** emitted by the component, not exceptions or the logging system in general.

### How do managedName, componentName, and beanName differ?

A Java DSL endpoint can create multiple internal beans. Therefore:

- **Bean name** is the key in the <code>ApplicationContext</code>, used for bean lookup and lifecycle management.
- **Component name/type** comes from the <code>NamedComponent</code> contract, helping represent the element in the graph.
- **Managed name/type** is metadata for management and metrics/observations per the component's API.
- **Flow ID** or **endpoint ID** identifies the registration/lifecycle; it must not be assumed to be the name of every handler inside.

When debugging a metric with missing data, **print out the runtime metadata** instead of guessing that the name written in the Java DSL is definitely the meter's tag.

## 3. Management is not synonymous with Lifecycle

A channel can exist in the <code>ApplicationContext</code> and have metrics without being the object that executes a poller. Conversely, a <code>SourcePollingChannelAdapter</code> can be <code>start()</code>ed/<code>stop()</code>ped while messages already sitting in a queue remain waiting.

| Task | Primary API | Does it clear pending data? |
|---|---|---|
| Enable/disable debug logging | <code>IntegrationManagement.setLoggingEnabled(...)</code> | No |
| Name/manage components | <code>setManagedName(...)</code>, configurer | No |
| Stop/start endpoint | <code>SmartLifecycle</code>, dynamic flow registration | Does not clear automatically |
| Remove dynamic flow | <code>IntegrationFlowContext.remove(flowId)</code> / registration destroy | Does not delete persistent store by default |
| Export metrics/traces | <code>MeterRegistry</code>, <code>ObservationRegistry</code> | No |
| Expose JMX attributes/operations | <code>IntegrationMBeanExporter</code> | No |
| Handle errors | <code>ErrorMessage</code> / error channel and adapter error handling | Does not decide rollback on its own |

Therefore, when a dashboard shows "handler has no traffic", you need to distinguish between an unstarted endpoint, a source not producing messages, a blocked channel, a queue backlog, or a handler removed from the topology.

## 4. Enabling management with @EnableIntegrationManagement

<code>@EnableIntegrationManagement</code> resides in the <code>org.springframework.integration.config</code> package. It imports management configuration and creates the <code>IntegrationManagementConfigurer</code> bean with the standard name <code>integrationManagementConfigurer</code>.

Basic example:

~~~java
@Configuration
@EnableIntegration
@EnableIntegrationManagement(
    defaultLoggingEnabled = "true",
    observationPatterns = { "orders.*" })
public class ManagedOrderFlowConfig {
    // Managed component beans of the flow are declared here.
}
~~~

Explanation:

1. <code>@EnableIntegration</code> initializes the Spring Integration infrastructure.
2. <code>@EnableIntegrationManagement</code> enables default configuration for components that support management.
3. <code>defaultLoggingEnabled</code> is a <code>"true"</code>/<code>"false"</code> string and supports property placeholders; it does not change SLF4J/Logback levels.
4. <code>observationPatterns</code> is the set of component name patterns **selected to inject ObservationRegistry** when a registry exists in the context. The default is empty, meaning no component has Observation enabled unconditionally.
5. Patterns can use <code>*</code> and <code>!</code> for exclusion according to the framework's pattern matching rules. You must verify the actual names and evaluation order when using multiple patterns.

Configuration example:

~~~java
@EnableIntegrationManagement(
    defaultLoggingEnabled = "false",
    observationPatterns = { "orders.*" })
~~~

The configuration above reduces routine debug logs of managed components by default while scoping observation more narrowly than the entire application. It **does not create** an <code>ObservationRegistry</code> on its own, does not connect Prometheus/Zipkin/OTLP, and does not enable the JMX MBean exporter.

When experimenting in a small application, <code>observationPatterns = "*"</code> can help inspect instrumented components. However, enabling it for all components in production can significantly increase the number of spans, metric series, and overhead.

### Why can manual configuration override global defaults?

If a channel has already called <code>setLoggingEnabled(true)</code>, setting <code>defaultLoggingEnabled = "false"</code> will not necessarily silence that channel: the configurer respects properties that have been marked as manually configured through the override mechanism. Thus, if you see only a few components still logging, inspect the specific bean/DSL configuration.

## 5. Complete Java DSL example: managed channel and handler

The application receives an <code>OrderCommand</code>, executes a service activator, and wants to observe handler execution count, error count, and processing duration. To keep metric names stable, we assign clear channel names and endpoint IDs.

**Step 1 — payload and business service:**

~~~java
public record OrderCommand(String orderId, int quantity) {}

@Service
public class OrderService {
    public void process(OrderCommand command) {
        if (command.quantity() <= 0) {
            throw new IllegalArgumentException("quantity must be > 0");
        }
        // Business logic, e.g. writing to OrderStore or calling another service.
    }
}
~~~

**Step 2 — declare the flow and management:**

~~~java
@Configuration
@EnableIntegration
@EnableIntegrationManagement(
    observationPatterns = { "orders.*" },
    defaultLoggingEnabled = "true")
public class OrderIntegrationConfig {

    @Bean(name = "orders.input")
    DirectChannel ordersInput() {
        DirectChannel channel = new DirectChannel();
        channel.setManagedName("orders.input");
        return channel;
    }

    @Bean
    IntegrationFlow orderFlow(OrderService service) {
        return IntegrationFlow.from("orders.input")
            .handle(service, "process", e -> e.id("orders.process"))
            .get();
    }
}
~~~

Key imports: <code>org.springframework.integration.config.EnableIntegration</code>, <code>org.springframework.integration.config.EnableIntegrationManagement</code>, <code>org.springframework.integration.dsl.IntegrationFlow</code>, <code>org.springframework.integration.channel.DirectChannel</code>, along with <code>org.springframework.context.annotation.Configuration</code>/<code>Bean</code> and <code>org.springframework.stereotype.Service</code>.

The flow uses a <code>DirectChannel</code>, so on the synchronous path, an exception from <code>process()</code> can propagate back to the thread calling <code>send()</code>. With an <code>ExecutorChannel</code> or poller, the same handler may execute on a different thread; this changes where errors are received and how duration is interpreted.

**Step 3 — create registries for an example without Spring Boot auto-configuration:**

~~~java
@Configuration
class LocalTelemetryConfig {

    @Bean
    MeterRegistry meterRegistry() {
        return new SimpleMeterRegistry();
    }

    @Bean
    ObservationRegistry observationRegistry(MeterRegistry meters) {
        ObservationRegistry registry = ObservationRegistry.create();
        registry.observationConfig()
            .observationHandler(new DefaultMeterObservationHandler(meters));
        return registry;
    }
}
~~~

Types: <code>io.micrometer.core.instrument.MeterRegistry</code>, <code>io.micrometer.core.instrument.simple.SimpleMeterRegistry</code>, <code>io.micrometer.core.instrument.observation.DefaultMeterObservationHandler</code>, and <code>io.micrometer.observation.ObservationRegistry</code>.

**Explanation of an easily overlooked detail:** <code>ObservationRegistry</code> is where observations are emitted; <code>DefaultMeterObservationHandler</code> is what converts them into Micrometer meters in this registry. If you are already using Spring Boot Actuator and Boot has created the registry/handlers, **do not create** these example beans to avoid duplicate configuration or auto-configuration conflicts. This code illustrates the minimal setup in a self-managed Spring context.

**Step 4 — send a message:**

~~~java
Message<OrderCommand> valid = MessageBuilder
    .withPayload(new OrderCommand("O-101", 2))
    .setHeader("correlationId", "checkout-O-101")
    .build();

ordersInput.send(valid);
~~~

<code>MessageBuilder</code> belongs to <code>org.springframework.integration.support</code>. Treat <code>send()</code> only as the result of the *send operation*. In an asynchronous topology, a successful send may only mean the task was accepted, not that all downstream work has completed.

## 6. Inspecting existing managed components directly

After the application context is initialized, you can list beans implementing <code>IntegrationManagement</code>:

~~~java
Map<String, IntegrationManagement> managed =
    applicationContext.getBeansOfType(IntegrationManagement.class);

managed.forEach((beanName, component) -> {
    log.info(
        "bean={}, managedName={}, managedType={}, observed={}, logging={}",
        beanName,
        component.getManagedName(),
        component.getManagedType(),
        component.isObserved(),
        component.isLoggingEnabled());
});
~~~

<code>IntegrationManagement</code> belongs to <code>org.springframework.integration.support.management</code>; <code>applicationContext</code> is the current <code>ApplicationContext</code>. If an internal component created by the framework is not listed as an easily accessible bean, inspect the corresponding endpoint ID, graph, and DSL configuration instead of assuming it does not exist.

You can inspect a specific bean:

~~~java
DirectChannel channel =
    applicationContext.getBean("orders.input", DirectChannel.class);

IntegrationManagement management = channel;
assertEquals("orders.input", management.getManagedName());
management.setLoggingEnabled(false);
assertFalse(management.isLoggingEnabled());
~~~

The assertions belong to JUnit 5. Changing <code>setLoggingEnabled(...)</code> is a runtime configuration on that specific bean; it does not require restarting the flow, but it does not create or remove registered meters and does not change the application's global logging level.

### When should you set managed names manually?

- When you want stable metrics across deployments, instead of endpoint names auto-generated by the DSL.
- When multiple flows handle the same business domain but need to be separated by logical component.
- When a dynamic flow has a deterministic ID and you want to trace stop/restart operations or metrics by that exact ID.

Do not use message IDs, order IDs, or tenant IDs with millions of values as managed names. With Micrometer, names or tags with too many values cause **cardinality explosion**, impacting collector memory and monitoring system costs.

## 7. Distinguishing traditional Micrometer meters from the Observation API

Spring Integration supports two related but **not identical** paths for collecting performance data:

| Criterion | Traditional Micrometer meters | Micrometer Observation (Spring Integration 6.0+) |
|---|---|---|
| Entry point | <code>MeterRegistry</code>, <code>MetricsCaptor</code> | <code>ObservationRegistry</code> and <code>ObservationHandler</code>s |
| Primary value | Counter/timer/gauge for send, receive, and handler | A single abstraction that can produce metrics and tracing spans |
| Component selection config | Framework-supported components and meter filters | <code>@EnableIntegrationManagement(observationPatterns=...)</code> |
| Typical metric names | <code>spring.integration.send</code>, <code>spring.integration.receive</code> | <code>spring.integration.handler</code>, <code>spring.integration.producer</code>, <code>spring.integration.gateway</code> |
| Trace data | Does not automatically create spans just from having a timer | Can create spans when a matching tracing ObservationHandler is present |
| When both mechanisms exist | Depends on version/configuration; do not assume both record | When a component already has an ObservationRegistry, standalone <code>MetricsCaptor</code> may be ignored |

According to the Javadoc, <code>registerMetricsCaptor(...)</code> is **ignored if an ObservationRegistry is already** in use for the component. Observation meters are not collected independently in the legacy way, but are forwarded to handlers in the <code>ObservationRegistry</code>. Therefore, a dashboard that previously read <code>spring.integration.send</code> may need its queries updated when switching to observations.

### Metric names and tags to know

**Traditional meters branch:**

| Meter | Type | Important tags |
|---|---|---|
| <code>spring.integration.send</code> | Timer for channel send or handler | <code>type</code> (channel/handler), <code>name</code>, <code>result</code>, <code>exception</code> |
| <code>spring.integration.receive</code> | Counter for pollable channel or source | <code>type</code>, <code>name</code>, <code>result</code>, <code>exception</code> |
| <code>spring.integration.channels</code> | Gauge for total channel count | Depends on registry configuration |
| <code>spring.integration.handlers</code> | Gauge for total handler count | Depends on registry configuration |
| <code>spring.integration.sources</code> | Gauge for total source count | Depends on registry configuration |
| <code>spring.integration.channel.queue.size</code> | Gauge for depth of supported <code>QueueChannel</code> | <code>type=channel</code>, <code>name</code> |

**Observation API branch (6.x):**

| Observation/meter | Meaning | Notable default keys |
|---|---|---|
| <code>spring.integration.handler</code> | Receiving/processing a message at a handler, typically a timer | <code>spring.integration.name</code>, <code>spring.integration.type=handler</code> |
| <code>spring.integration.gateway</code> | Request–reply gateway | <code>spring.integration.name</code>, <code>spring.integration.outcome</code>, <code>spring.integration.type=gateway</code> |
| <code>spring.integration.producer</code> | Send operation at a channel/producer | <code>spring.integration.name</code>, <code>spring.integration.type=producer</code> |
| <code>.active</code> long-task meters | Tracks active observations when supported by the handler | Keys available when the observation starts; may not yet contain outcome information |

Final meter names depend on the <code>ObservationHandler</code>, conventions, and Micrometer version in use. Check the actual meters present in the registry before hardcoding Prometheus/Grafana queries.

### Quick metric check in the example

~~~java
List<Timer> handlerTimers =
    meterRegistry.find("spring.integration.handler").timers();

long attemptsObserved = handlerTimers.stream()
    .mapToLong(Timer::count)
    .sum();

assertTrue(attemptsObserved >= 1);
~~~

The snippet above assumes the flow in Section 5 has received at least one message and <code>ObservationRegistry</code> has a <code>DefaultMeterObservationHandler</code>. <code>Timer</code> belongs to <code>io.micrometer.core.instrument</code>. In a real application, filter by exact tags (managed name, component type) to avoid summing timers from other flows together.

If <code>spring.integration.handler</code> is missing, first check the patterns, component ID, <code>ObservationRegistry</code>, and handlers. Do not immediately conclude "Spring Integration does not create metrics".

## 8. Observability is not free: choosing instrumentation scope

A single message can travel through many channels and handlers. If every step creates a span/timer, the volume of metrics and traces can grow very rapidly.

~~~text
HTTP inbound → input channel → transformer → router
             → executor channel → service activator
             → output channel → outbound gateway
~~~

For a single message, you may see multiple distinct observations along **framework boundaries**, rather than a single measurement for the entire business transaction.

Selection guidelines:

1. Start at endpoints with critical SLAs or failures: inbound gateways, order-processing handlers, outbound adapters.
2. Enable additional channel observations when you need to find bottlenecks or propagate trace context across distributed/persistent channels.
3. Add only low-cardinality tags such as <code>spring.integration.type</code>, stable endpoint names, and operation types.
4. Put order IDs, tenant IDs, or request correlation IDs into trace context/logs with appropriate retention policies; **do not** use them as meter tags with unbounded cardinality.
5. Sample traces under high traffic; metrics are usually aggregated in full to avoid losing trends.
6. Measure CPU/memory overhead and collector costs before and after instrumentation changes.

<code>observationPatterns = "*"</code> is useful for exploration in staging, but is not necessarily the optimal configuration for high-load production environments.

## 9. JMX MBean exporter is a different mechanism

To inspect/control channels and handlers via JMX, you need to add the **JMX export** mechanism. Spring Integration provides <code>IntegrationMBeanExporter</code> and the <code>@EnableIntegrationMBeanExport</code> annotation in the <code>spring-integration-jmx</code> module.

Example:

~~~java
@Configuration
@EnableIntegration
@EnableIntegrationManagement
@EnableIntegrationMBeanExport(
    managedComponents = { "orders.*" })
public class JmxOrderManagementConfig {
}
~~~

Import <code>@EnableIntegrationMBeanExport</code> from <code>org.springframework.integration.jmx.config</code> in Spring Integration 6.x. Appropriate JMX dependencies, an MBean server, and infrastructure configuration are required. The example only illustrates the export layer; do not add a similar configuration if the application already has an exporter managed by another system.

**Three points of distinction:**

- <code>@EnableIntegrationManagement</code> and <code>IntegrationManagement</code> provide management and instrumentation settings for components.
- <code>@EnableIntegrationMBeanExport</code> creates a separate **JMX MBean** path; only beans matching the exporter/pattern criteria are exposed.
- Spring Boot Actuator can provide endpoints for metrics/health and other integrations depending on dependencies/configuration; it does not mean every <code>IntegrationManagement</code> bean automatically gets an MBean.

JMX can expose runtime attributes and certain managed operations. Grant access only to trusted operators; do not expose JMX ports to public networks. In particular, control operations such as stop/start/shutdown can affect availability and in-flight transactions.

## 10. IntegrationGraphServer and managed topology

When flows become complex, isolated metrics do not tell you **which nodes a message passed through**. Spring Integration provides <code>IntegrationGraphServer</code>, which represents the runtime topology as a graph of channels, handlers, endpoints, and connections.

Example of reading the graph:

~~~java
IntegrationGraphServer graphServer =
    applicationContext.getBean(IntegrationGraphServer.class);

Graph graph = graphServer.getGraph();
log.info("Integration graph: {}", graph);
~~~

The types belong to <code>org.springframework.integration.graph</code>. The snippet assumes the application context already has a suitable <code>IntegrationGraphServer</code>. <code>getGraph()</code> returns a cached model; metadata and statistics may change at runtime.

For **dynamic flows** added/removed while the application is running, you need to call:

~~~java
Graph refreshed = graphServer.rebuild();
~~~

This regenerates the topology snapshot and cache. Without rebuilding, the graph may still reflect deleted flows or not yet display newly created ones. Do not call rebuild continuously on every message; it is an administrative operation with overhead.

The graph is very useful for answering:

- Which channels are messages sent through and which endpoints are subscribed?
- Are there terminal handlers with no further output?
- From which boundaries does an error flow receive messages?
- After registering a dynamic <code>IntegrationFlow</code>, how has the topology changed?

**The graph is not a distributed trace.** An edge connecting two nodes describes structure; it does not prove a specific message traversed that edge, does not store replay history, and does not replace correlation IDs.

## 11. Observing threads, pollers, transactions, and error flows

The same <code>spring.integration.handler</code> metric can be measured at one point yet interpreted differently depending on the topology.

| Topology | Processing thread | Metric/tracing interpretation |
|---|---|---|
| <code>DirectChannel</code> → handler | Sender thread | Handler latency may be part of synchronous <code>send()</code> duration |
| <code>ExecutorChannel</code> → handler | Worker thread | Sender may return before the handler; separate enqueue time, queue wait time, and execution |
| <code>QueueChannel</code> + poller | Poller/scheduler worker | Handler timer does not automatically measure time spent **waiting in the queue** |
| <code>PublishSubscribeChannel</code> with executor | Subscriber's executor | A failed subscriber may be handled on another thread; send success does not mean all subscribers succeeded |
| Reactive endpoint | Reactor worker/subscription | Observation must propagate through the appropriate reactive context and subscription |
| Message broker adapter | Listener/container thread and post-handoff worker | ACK, redelivery, and transport latency require adapter/broker-specific metrics |

### Transaction commit is not included in every handler timer

If <code>@Transactional</code> is applied to a service method, a timer at the handler may wrap part or all of the proxied method, whereas a transaction **enclosing the flow** may commit after the handler has returned. Therefore:

- Handler duration does not by itself prove the transaction committed.
- Errors occurring after an executor handoff do not increment the sender's error counter the same way synchronous errors do.
- Retry advice placed outside versus inside the instrumentation point can change the recorded attempt count/duration.
- If an error consumer catches an exception and completes normally, metrics may view the endpoint as recovered, which does not mean the business operation succeeded.

To obtain a reliable **business outcome**, place metrics at the use-case boundary or where transaction commit/recovery is determined, not just on channels.

### A poller may produce no messages for many reasons

If a source's <code>receive()</code> returns <code>null</code> or the consumer is stopped, handler metrics may remain unchanged even though the scheduler keeps ticking. To diagnose, check all of the following:

1. <code>SmartLifecycle.isRunning()</code> of the endpoint.
2. Polling schedule, <code>maxMessagesPerPoll</code>, <code>receiveTimeout</code>, and whether the scheduler still has workers available.
3. Source receive metrics, queue depth, and adapter-specific metrics.
4. Exceptions during polling, error channel, and transaction rollbacks.
5. Connection pools, executor saturation, and network timeouts.

Do not turn a single <code>handler.count == 0</code> indicator into the sole conclusion that the endpoint is stopped.

## 12. Correlation, trace propagation, and message history

Spring Integration's <code>correlationId</code> is typically a business header used to join messages, especially in aggregators/splitters. **Trace ID** belongs to the tracing system (OpenTelemetry/Brave via Micrometer), and **message ID** identifies a single message. They serve different roles:

| Identifier | Used to | Should not be assumed to |
|---|---|---|
| <code>MessageHeaders.ID</code> | Distinguish a specific message | Remain stable across all transformers, redeliveries, and new message creations |
| <code>correlationId</code> | Group messages belonging to a request/batch | Be the trace ID or transaction ID |
| Trace/span ID | Track observations across distributed boundaries | Be present automatically if tracing is not configured |
| Business event/idempotency ID | Prevent duplicate side effects on retry/redelivery | Equal a random message ID |

In Spring Integration 6.x, Observation on channels and consumers can support **propagating tracing context via message headers**. With persistent or distributed channels, appropriate instrumentation is needed on **both the sending and receiving sides** so that trace context is attached to the message before crossing threads/nodes and restored when the consumer reads it.

If Observation is enabled only on a handler but not on a distributed channel, a trace may split into two disconnected segments. This does not mean the message did not arrive; it may simply lack propagation.

**Message history** is a different mechanism that can be enabled to record the names/types of components that processed a message into headers when supported. It does not replace tracing spans, does not retain history once the payload is removed from a store, and carries its own overhead. Enable it only when genuinely needed to investigate paths across multiple endpoints.

## 13. Creating custom managed components when needed

If the application writes a custom handler or source, the most maintainable choice is to **extend a Spring Integration base class**, such as <code>AbstractMessageHandler</code> or <code>AbstractMessageSource</code>. These classes already implement the appropriate lifecycle and instrumentation/framework contracts.

Example custom handler:

~~~java
public final class ValidationMessageHandler extends AbstractMessageHandler {

    @Override
    protected void handleMessageInternal(Message<?> message) {
        Object payload = message.getPayload();
        if (payload == null) {
            throw new IllegalArgumentException("Invalid payload");
        }
        // Only performs validation; depending on the use case, another handler will produce the reply.
    }

    @Override
    public String getComponentType() {
        return "validation-handler";
    }
}
~~~

<code>AbstractMessageHandler</code> belongs to <code>org.springframework.integration.handler</code>; <code>Message</code> belongs to <code>org.springframework.messaging</code>. This snippet is a terminal handler; if you need to transform and send a reply, extend the appropriate reply-producing class or use a Java DSL transformer instead of assuming <code>handleMessageInternal()</code> emits output on its own.

If you write an arbitrary POJO bean and implement <code>IntegrationManagement</code> yourself, do not assume <code>IntegrationManagementConfigurer</code> will turn every POJO method into an automatic observation. Check the actual instrumentation points, handler wrappers, and write tests for incoming messages.

**Do not** manually call <code>registerObservationRegistry()</code> on every bean if <code>@EnableIntegrationManagement</code> already manages them appropriately; injecting instrumentation in multiple places can lead to duplicate measurements or hard-to-control configurations.

## 14. Testing observability properly

Management tests must verify **both configuration and actual observation events**. Having an <code>ObservationRegistry</code> in the application context does not prove a specific handler is instrumented.

| Test case | Expected result |
|---|---|
| Stable channel managed name | <code>getManagedName()</code> is accurate, not dependent on a random UUID |
| Enable <code>observationPatterns</code> for handler | Observation/timer is recorded after sending a message |
| Handler throws runtime exception | Error outcome is reflected per convention; caller receives error if flow is synchronous |
| Pattern does not match component | No Observation on that component per configuration, while the flow still processes messages |
| <code>setLoggingEnabled(false)</code> | Reduces component framework debug logs; error handling continues to work |
| Replace channel with <code>ExecutorChannel</code> | Sender and worker completion are distinguished |
| Dynamic flow created/removed | <code>IntegrationGraphServer.rebuild()</code> reflects the new topology |
| Queue backlog | Queue depth is measurable via queue gauge or store, not inferred from handler timer |
| Correlation across message store/broker | Trace connects when appropriate producer/consumer instrumentation is configured |

**JUnit 5 example** (assuming the Spring test context has loaded the beans from Section 5):

~~~java
@Test
void managedChannelAndHandlerAreInstrumented() {
    DirectChannel channel = applicationContext.getBean(
        "orders.input", DirectChannel.class);

    assertEquals("orders.input", channel.getManagedName());

    channel.send(MessageBuilder
        .withPayload(new OrderCommand("O-T1", 2))
        .build());

    List<Timer> timers =
        meterRegistry.find("spring.integration.handler").timers();

    assertFalse(timers.isEmpty());
    assertTrue(timers.stream().mapToLong(Timer::count).sum() > 0);
}
~~~

With <code>DirectChannel</code> in this example, the send executes synchronously so assertions can run right after the call. If switching to an executor, use a latch/Awaitility or wait for a condition with a timeout instead of a fixed-duration <code>Thread.sleep()</code>.

### Testing failures without relying on guesswork timer counts

~~~java
@Test
void failureDoesNotDisappearBecauseManagementIsEnabled() {
    DirectChannel channel = applicationContext.getBean(
        "orders.input", DirectChannel.class);

    assertThrows(RuntimeException.class, () -> channel.send(
        MessageBuilder
            .withPayload(new OrderCommand("O-BAD", 0))
            .build()));
}
~~~

<code>@EnableIntegrationManagement</code> does not swallow exceptions, automatically retry, or control transactions; this test keeps the synchronous processing boundary to verify that behavior. If the flow has recovery advice, an output/error channel, or an interceptor, the expected exception must match the actual contract instead of assuming it is always thrown back to the sender.

## 15. Common mistakes when metrics or traces are missing

| Symptom | Causes to check | Resolution |
|---|---|---|
| <code>MeterRegistry</code> exists but no <code>spring.integration.handler</code> | Using traditional meters, missing ObservationRegistry or pattern | Identify instrumentation branch, also check <code>spring.integration.send</code> |
| <code>ObservationRegistry</code> exists but no meters appear | Missing <code>ObservationHandler</code> converting to metrics or component does not match | Check registered handlers, <code>observationPatterns</code>, and actual names |
| One handler is not measured | Bean/component name differs from assumed ID, or handler wrapper does not instrument as expected | List <code>IntegrationManagement</code> beans and runtime graph |
| Metric exists but tags do not match | Managed name/type or naming convention changed | Read actual tags from registry before editing dashboards |
| Metrics and traces do not connect | Missing tracing handler/exporter or context propagation across channels | Configure producer and consumer observation, suitable tracer/exporter |
| Queue backlogs yet handler latency is low | Queue wait time is not included in handler timer | Measure queue size, enqueue-to-start lag, and executor saturation |
| No errors seen on sender | Consumer runs on executor/poller; failure happens on worker | Check error channel/adapter and worker telemetry |
| Only partial data remains after restart | In-memory meters are not a persistent store; exporter has not scraped or backend retention expired | Inspect scrape/export topology and retention window |
| Metrics do not update after dynamic flow change | Cached graph or new names/stale series | Rebuild graph, apply meter filters, and manage lifecycle |
| Cardinality spikes sharply | Using tenant ID/message ID as tag/managed name | Use stable component names and low-cardinality tags |

### Recommended investigation workflow

1. Identify the Spring Integration and Micrometer versions and whether the application uses **traditional meters**, **Observation**, or both across different components.
2. Verify <code>@EnableIntegrationManagement</code>, patterns, component names, manual overrides, and the presence of registries/handlers.
3. Send a test message to the right channel, verify the real handler ran, and only then inspect meters.
4. Check thread boundaries (Direct/Executor/Poller/Reactive) and where errors are re-emitted.
5. Compare metrics at channels, handlers, and sources against queue depth, source polling, and business outcomes.
6. Check the tracer/propagator across message headers if spans break between nodes.
7. Check monitoring system exporter/scrape/retention if data appears only locally.

## 16. Production deployment checklist

- [ ] Maintain an inventory of critical managed components, stable names, and corresponding topology.
- [ ] Use <code>IntegrationManagement</code> to configure components; do not confuse it with <code>SmartLifecycle</code> or MBean export.
- [ ] Enable <code>@EnableIntegrationManagement</code> and select only necessary <code>observationPatterns</code>; verify matching on actual beans.
- [ ] Configure appropriate <code>MeterRegistry</code>/<code>ObservationRegistry</code>, ObservationHandlers, and exporter/scrape endpoints explicitly.
- [ ] Dashboards distinguish legacy meter names from observation metric names; do not assume every metric exists in all versions.
- [ ] Critical alerts combine handler error rate, latency, queue lag, poller status, executor saturation, and business outcomes.
- [ ] Traces propagate via message headers across async/persistent/distributed boundaries; correlation and idempotency IDs are managed independently.
- [ ] JMX/Actuator/Control Bus are exposed following least privilege, without exposing sensitive control operations.
- [ ] Do not use raw tenant/message IDs as metric tags; evaluate cardinality, sampling, cost, and payload privacy.
- [ ] Include tests measuring metrics/failures, lifecycle, and dynamic graphs; maintain runbooks for "messages missing" or "timer rising while requests time out".

**Conclusion:** <code>IntegrationManagement</code> provides the contract for **identifying and managing** channels, handlers, sources, and many other Spring Integration components. <code>@EnableIntegrationManagement</code> applies shared settings to managed components; Micrometer/Observation produces telemetry, JMX provides a separate management path, and the graph describes topology. Combining these layers with an understanding of threads, transactions, retries, message stores, and correlation lets observability answer not just "which component is slow" but also "at which boundary is the message and why has it not finished".

## References

- [Spring Integration Reference — Metrics and Management](https://docs.spring.io/spring-integration/reference/metrics.html)
- [Spring Integration 6.5 Javadoc — IntegrationManagement](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/support/management/IntegrationManagement.html)
- [Spring Integration 6.5 Javadoc — EnableIntegrationManagement](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/config/EnableIntegrationManagement.html)
- [Spring Integration Reference — JMX Support](https://docs.spring.io/spring-integration/reference/jmx.html)
- [Spring Integration Reference — Integration Graph](https://docs.spring.io/spring-integration/reference/graph.html)
- [Micrometer Reference — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
