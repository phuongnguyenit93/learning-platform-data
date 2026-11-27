# IntegrationContext and Lifecycle of Integration Components

In **SPRING_INTEGRATION_RUNTIME**, Spring Integration does not merely describe message flows—it also creates, registers, starts, pauses, and releases the components participating in a flow. These components live inside the **Spring ApplicationContext** and follow Spring's bean management and lifecycle mechanisms.

In the title of this lesson, **IntegrationContext** is a general term for the management of integration components within the context. When referring to the modern Java DSL API for dynamic flow registration, the exact name is **IntegrationFlowContext**. Some discussions or older documentation may use the phrase IntegrationContext to refer to dynamic flow management capabilities. There is also **IntegrationContextUtils**, a utility class for looking up certain infrastructure beans from the BeanFactory; it is not a separate application context.

This lesson explains the relationship between ApplicationContext, IntegrationFlowContext, and the lifecycle of endpoints, adapters, pollers, and integration resources. The goal is to know when a flow starts automatically, when manual start/stop is needed, how to manage flows created dynamically for business requirements, and how to shut down the application safely.

## 1. Context Layers in a Spring Integration Application

### 1.1 Spring ApplicationContext Is the Root Container

Spring ApplicationContext manages the lifecycle of beans in the application. It is responsible for reading configuration, creating beans, injecting dependencies, invoking initialization callbacks, and destroying beans when the context closes.

In a Spring Integration application, beans typically include:

- **MessageChannel**: where producers send and consumers receive messages.
- **MessageHandler**: processes payloads or messages.
- **Endpoint**: connects a channel to a handler, adapter, or message source.
- **Inbound/Outbound adapter**: connects the flow to external systems.
- **TaskScheduler and TaskExecutor**: coordinate polling schedules and task execution.
- **MessageStore, MetadataStore, errorChannel**: infrastructure services for storage, metadata, and error handling.

These beans are created via Java configuration, annotations, XML, or Java DSL. ApplicationContext is the container that holds and manages them; it is not a message channel and does not directly process individual messages.

In plain Java configuration, annotation and Java DSL infrastructure can be enabled with @EnableIntegration. Spring Boot and the corresponding starters usually auto-configure the required infrastructure; inspect your application's actual configuration before declaring duplicates.

### 1.2 IntegrationFlow Describes an Integration Flow

IntegrationFlow describes the message processing steps and the relationships between them. For example:

~~~java
@Configuration
@EnableIntegration
class OrderIntegrationConfiguration {

    @Bean
    IntegrationFlow orderFlow(OrderService orderService) {
        return IntegrationFlow.from("orders.input")
            .handle(orderService, "process")
            .get();
    }
}
~~~

When an IntegrationFlow bean is registered in the ApplicationContext, Spring Integration analyzes the flow and registers the necessary components—such as channels, endpoints, and handlers—as beans. The endpoints executing the flow are managed by Spring's lifecycle mechanism.

The flow object in Java DSL is a logical configuration model. It does not mean that all message processing happens inside a single object. At runtime, there are concrete endpoints and channels, each with its own responsibility.

### 1.3 IntegrationFlowContext Manages Dynamically Created Flows

IntegrationFlowContext is the public API for programmatically registering an IntegrationFlow while the application is already running, rather than only declaring flows as beans during initial configuration.

Suitable use cases include:

- Each tenant has its own endpoint or group of flows.
- The list of partner connections is only known after the application starts.
- A flow needs to be created or removed based on a connection session, configuration, or business state.
- An adapter only needs to exist for the duration of a specific task.

IntegrationFlowContext is provided by Spring Integration as an infrastructure bean. You can inject it into a flow management service. This API allows registering flows, retrieving a registration by ID, inspecting the registry, obtaining a MessagingTemplate, and removing flows.

~~~java
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

    IntegrationFlowContext.IntegrationFlowRegistration createFlow(String tenantId) {
        IntegrationFlow flow = IntegrationFlow.from("tenant." + tenantId + ".input")
            .handle(orderService, "process")
            .get();

        return this.flowContext.registration(flow)
            .id("tenant-" + tenantId + "-orders")
            .autoStartup(false)
            .register();
    }
}
~~~

The example sets autoStartup(false) so the registration is created without receiving messages yet. The service can verify state or finish configuring dependencies before calling registration.start().

Distinguish clearly between:

| Component | Role |
|---|---|
| ApplicationContext | Container managing application beans and lifecycle |
| IntegrationFlow | Describes the step structure of a message flow |
| IntegrationFlowContext | Dynamically registers, looks up, and removes IntegrationFlows |
| IntegrationFlowRegistration | Represents a registered flow; provides ID, input channel, and lifecycle operations |
| IntegrationContextUtils | Utility for looking up certain infrastructure beans from BeanFactory |

### 1.4 IntegrationContextUtils Is Not IntegrationFlowContext

IntegrationContextUtils is a utility class in the org.springframework.integration.context package. Its methods help access shared components from BeanFactory, such as the error channel, metadata store, task scheduler, and evaluation context.

Do not use IntegrationContextUtils to register dynamic flows. For creating or removing flows at runtime, use IntegrationFlowContext. Distinguishing these two API names avoids confusion when reading stack traces, documentation, or legacy configurations.

## 2. Lifecycle of Spring Beans and Integration Components

### 2.1 Basic Bean Lifecycle

A Spring-managed bean typically goes through these stages:

1. **Definition registration**: Spring reads configuration and records bean definitions.
2. **Instantiation**: the container creates the object and injects dependencies.
3. **Post-injection initialization**: callbacks such as InitializingBean, @PostConstruct, or init methods are invoked according to Spring's rules.
4. **In use**: the bean is ready to serve the application.
5. **Stop and destruction**: when the context closes, beans with lifecycle or destroy callbacks are stopped and release their resources.

Not every bean needs start/stop. An ordinary business service might simply be an object invoked when an endpoint dispatches a message. By contrast, an inbound adapter, polling endpoint, or listener connecting to an external system typically needs to explicitly open, run, and close resources.

### 2.2 Lifecycle and SmartLifecycle

Spring provides two common abstractions:

- **Lifecycle**: provides start(), stop(), and isRunning().
- **SmartLifecycle**: extends Lifecycle, adding autoStartup, phase, and a stop callback to coordinate startup/shutdown order.

Message endpoints in Spring Integration rely on this lifecycle mechanism. The base class AbstractEndpoint implements ManageableSmartLifecycle and DisposableBean. Endpoints have an autoStartup property; the default is true. If set to false, the endpoint does not start automatically via the lifecycle processor and must be started explicitly.

Key properties:

| Property | Meaning | Usage |
|---|---|---|
| autoStartup | Whether to start automatically when the context starts | Set to false when waiting for external conditions |
| phase | Controls start/stop order among SmartLifecycle components | Orders consumers, adapters, and dependent resources |
| role | Groups lifecycle components to control them together | Enables/disables a group of endpoints by business logic |
| isRunning | Indicates whether the component is running or stopped | Checks runtime status |

ApplicationContext's lifecycle processor automatically starts SmartLifecycle components with autoStartup=true after the context is refreshed. Components with lower phase values start first; when stopping the context, the shutdown order is reversed. If multiple components share the same phase, do not rely on any unguaranteed ordering between them.

### 2.3 Endpoints Are an Important Lifecycle Boundary

In an IntegrationFlow, the endpoint is usually the component that determines whether the flow is receiving messages. For example:

- An event-driven consumer registers a subscriber on the channel on start and unregisters on stop.
- A polling consumer starts or stops its polling schedule.
- An inbound channel adapter opens or closes the connection to an external system.
- An outbound endpoint may manage listeners, connections, or its own resources depending on the adapter type.

A channel can still exist as a bean while the downstream endpoint has stopped. Likewise, a service handler can still exist in the ApplicationContext yet never be invoked because the endpoint is no longer receiving messages.

Therefore, when investigating an inactive flow, inspect the endpoint state rather than merely confirming that the channel or service bean was created.

## 3. How Does ApplicationContext Start an IntegrationFlow?

A static flow declared with @Bean is normally managed alongside the ApplicationContext. The process can be visualized as follows:

~~~mermaid
flowchart TD
    A["ApplicationContext reads configuration"] --> B["Create beans and inject dependencies"]
    B --> C["Spring Integration processes IntegrationFlow"]
    C --> D["Register channels, endpoints, and handlers"]
    D --> E["Initialize endpoints"]
    E --> F{"Is autoStartup enabled?"}
    F -->|Yes| G["Lifecycle processor calls start by phase"]
    F -->|No| H["Endpoint waits for start command"]
    G --> I["Flow ready to receive messages"]
    H --> J["Application or controller calls start"]
    J --> I
~~~

Steps to understand:

- Flow configuration is read by Spring and turned into runtime beans.
- Endpoints finish initialization once required dependencies are ready.
- When context refresh completes, the lifecycle processor starts eligible SmartLifecycle components.
- Endpoints register subscribers, open adapters, or schedule polls depending on the endpoint type.
- Once an endpoint is running, messages begin to be received and processed through the corresponding channel.

This is the general model. Some adapters have an additional step to connect to a broker, server, or filesystem; therefore, the moment a connection succeeds may be later than the moment the bean is created.

## 4. Controlling Endpoints with autoStartup and phase

### 4.1 Disabling Auto-Startup

You can set autoStartup(false) on an endpoint in Java DSL to control when it begins running:

~~~java
@Bean
IntegrationFlow controlledOrderFlow(OrderService orderService) {
    return IntegrationFlow.from("orders.controlled.input")
        .handle(orderService, "process", endpoint -> endpoint
            .id("controlled-order-handler")
            .autoStartup(false)
            .phase(100))
        .get();
}
~~~

The endpoint is registered in the context but does not start automatically. A service can inject the endpoint bean if it has a matching ID, or use the lifecycle control mechanism provided for the endpoint, and call start() once conditions are ready.

Do not disable autoStartup and then forget to call start. Such a flow may appear fully present in configuration and the bean registry yet still receive no messages.

### 4.2 Ordering with phase

Phase determines the lifecycle order among components. Spring starts lower phases first and stops higher phases first.

For example, if a downstream consumer must be ready before an inbound source, you can give the consumer a lower phase and the source a higher phase. When the application shuts down, the inbound source is stopped first, while the consumer stays running longer to finish processing already-received messages.

~~~mermaid
flowchart LR
    A["Start: consumer<br/>low phase"] --> B["Start: inbound source<br/>high phase"]
    B --> C["Application processes messages"]
    C --> D["Stop: inbound source<br/>high phase first"]
    D --> E["Stop: consumer<br/>low phase later"]
~~~

Phase does not replace shutdown design. It only controls lifecycle ordering; draining messages requires an additional strategy to stop producers, monitor backlog, and wait for in-flight processing.

## 5. Controlling Multiple Endpoints with role

Role allows assigning multiple endpoints to the same group to start/stop them simultaneously. This is useful when the application has multiple flows that may only operate under a specific condition—for example, only the instance currently holding leadership is allowed to poll a shared directory.

In Java DSL, an endpoint can be assigned a role:

~~~java
@Bean
IntegrationFlow clusteredInboundFlow(FileOrderService service) {
    return IntegrationFlow.from(
            messageSource(),
            endpoint -> endpoint
                .poller(Pollers.fixedDelay(5000))
                .role("cluster"))
        .handle(service, "process")
        .get();
}
~~~

In this example, messageSource() represents a MessageSource bean provided by the application; the role is assigned to the polling endpoint reading that source.

You can use SmartLifecycleRoleController to control the group:

~~~java
@Service
class ClusterFlowLifecycle {

    private final SmartLifecycleRoleController roleController;

    ClusterFlowLifecycle(SmartLifecycleRoleController roleController) {
        this.roleController = roleController;
    }

    void onLeadershipGranted() {
        roleController.startLifecyclesInRole("cluster");
    }

    void onLeadershipRevoked() {
        roleController.stopLifecyclesInRole("cluster");
    }
}
~~~

When using leadership election, endpoints belonging to the role should set autoStartup(false) so the context does not start them automatically before the application determines which instance is authorized to run. Otherwise, multiple instances could poll or consume from the same data source during the window before a leader is elected.

Role is not a security role or user permission. It is a lifecycle label for grouping SmartLifecycle components.

## 6. Dynamically Registering and Managing IntegrationFlows

### 6.1 When Should You Create Dynamic Flows?

Static flows are appropriate when the integration structure is known at development time or application startup. Dynamic flows are appropriate when the number or configuration of flows changes according to business logic at runtime.

Consider a multi-tenant system. Each tenant might have an input channel and a handler configured per tenant. When a tenant is activated, the application registers the flow; when the tenant is deactivated, the application stops and removes the corresponding flow.

Do not create a dynamic flow for every message or every short-lived request if a single static flow can serve many messages. Each dynamic flow can create additional endpoints, channels, beans, and external resources. Uncontrolled growth in the number of flows increases memory, thread, and connection management overhead.

### 6.2 Registering a Flow

IntegrationFlowContext provides a builder to configure a registration. The typical steps are:

1. Build an IntegrationFlow instance according to business configuration.
2. Assign a stable and unique ID within the scope of the ApplicationContext.
3. Choose an appropriate autoStartup setting.
4. Call register() to add the flow and dependent beans to the context.
5. Keep the IntegrationFlowRegistration or ID for later management.

~~~java
IntegrationFlow flow = IntegrationFlow.from("tenant.acme.orders")
    .handle(orderService, "process")
    .get();

IntegrationFlowContext.IntegrationFlowRegistration registration =
    flowContext.registration(flow)
        .id("tenant-acme-orders")
        .autoStartup(false)
        .register();

registration.start();
~~~

When registered with the default autoStartup, the registration automatically starts the flow after registration succeeds. When set to false, the application must call start() explicitly.

Dynamic flows are registered after the standard bean initialization phase, so they do not wait for the ApplicationContext's lifecycle processor to include them in the initial auto-startup pass. IntegrationFlowContext manages flow registration and startup: registrations start automatically after register() by default, whereas autoStartup(false) requires the application to call start() when ready.

A registration can provide an input channel and a MessagingTemplate for sending messages into the flow if the flow begins with a MessageChannel:

~~~java
MessageChannel input = registration.getInputChannel();
MessagingTemplate template = registration.getMessagingTemplate();

template.send(MessageBuilder.withPayload(order).build());
~~~

Not every flow has an input channel for direct sending. If a flow starts with an inbound adapter or source, MessagingTemplate cannot synthesize an arbitrary message entry point for that flow.

### 6.3 Pausing, Restarting, and Removing Flows

There are three operations with distinct meanings:

| Operation | Meaning | When to use |
|---|---|---|
| start() | Starts the lifecycle components of the registration | Enable a flow that is registered but stopped |
| stop() | Stops flow execution while keeping the registration and beans | Pause processing while waiting for a condition |
| remove(id) or destroy() | Destroys the flow and dependent beans, cleans up the related registry | Tenant or connection no longer needs the flow |

Lifecycle management example:

~~~java
void disableTenant(String flowId) {
    IntegrationFlowContext.IntegrationFlowRegistration registration =
        flowContext.getRegistrationById(flowId);

    if (registration == null) {
        return;
    }

    registration.stop();
    flowContext.remove(flowId);
}
~~~

If you only want to pause a tenant, call stop() and keep the registration so it can be started again with start(). When a tenant is permanently deleted, call remove(id) to destroy the flow and its dependent beans. Do not retain references to removed channels, handlers, or registrations once they are no longer needed.

### 6.4 Managing IDs and the Registry

The flow ID is used to look up the registration and manage beans created from the flow. Use IDs that are business-meaningful, stable, and unique within the same context.

Examples:

- tenant-acme-orders
- partner-bank-a-inbound
- device-gateway-42

Store the ID where the lifecycle of the business entity is managed. There is no need to scan the entire ApplicationContext to guess which flow belongs to which tenant.

IntegrationFlowContext provides getRegistry() and getRegistrationById() to inspect registrations. This registry is useful when diagnosing dynamic flows that were forgotten or not yet removed.

When creating many flows, bound their count, define expiration times, and establish a clear removal path. Successful registration does not mean resources will vanish on their own when the business activity ends.

## 7. Shutting Down the Application and Releasing Resources

### 7.1 Closing the Context

When the ApplicationContext closes, the Spring lifecycle processor stops SmartLifecycle components in the reverse phase order of startup. Afterward, bean destroy callbacks are invoked according to Spring's mechanism.

For Spring Integration, this typically includes:

- Stopping inbound adapters so they stop accepting new messages.
- Stopping polling endpoints so no new poll executions are scheduled.
- Unregistering consumers from channels when endpoints stop.
- Stopping components that manage connections or listeners.
- Releasing beans and resources managed with the context.

Regular service beans still follow Spring's bean lifecycle, though they do not necessarily have start/stop. Do not arbitrarily invoke start/stop on every bean; only control objects that implement the corresponding lifecycle contract.

### 7.2 Graceful Shutdown and In-Flight Messages

Stopping an endpoint does not automatically guarantee that every message has finished processing. With QueueChannel, messages may still remain in the queue. With ExecutorChannel, tasks may still be queued or running in the executor. With adapters connected externally, closing a socket or session can affect ongoing operations.

A controlled shutdown sequence typically looks like:

1. Stop accepting new work from external sources.
2. Keep downstream consumers active as long as needed to process already-received messages.
3. Monitor backlog, active task count, and remaining processing time.
4. Stop consumers once the drain condition is met or the configured timeout expires.
5. Close executors, connection factories, sessions, and related resources.

If using an application-declared ThreadPoolTaskExecutor, configure an appropriate shutdown policy, such as waiting for tasks to complete for a bounded period. Explicitly decide what happens when the timeout expires: remaining tasks are interrupted, dropped, or reprocessed after the application restarts.

For messages that must not be lost if the process stops abruptly, use a durable storage mechanism or an appropriate broker. An in-memory queue and a standard stop operation do not provide durability guarantees.

### 7.3 stop vs. destroy

stop is an operation that changes active state. Beans and configuration remain intact, so they can be restarted if the component type supports it.

destroy or remove is an operation that ends the lifecycle of the registration and its dependent beans. After removal, the application must register a new flow if it wants to use it again.

A common mistake is calling stop on a flow and then forgetting about the registration. The flow stops receiving messages, yet its beans, registry entry, or resources remain referenced. If the business need ends permanently, perform remove/destroy and clear any references held by the application itself.

## 8. Inspecting Lifecycle State at Runtime

When a flow is not processing messages, inspect layer by layer:

| Question | Where to check |
|---|---|
| Did ApplicationContext refresh successfully? | Startup logs, application state |
| Has the flow been registered? | Bean registry or IntegrationFlowContext registry |
| Does the endpoint exist? | Bean name, endpoint ID, Integration Graph |
| Is the endpoint running? | isRunning(), lifecycle management |
| Is the endpoint auto-started? | autoStartup and start() calls |
| Was a dynamic flow stopped or removed? | IntegrationFlowRegistration and flowContext |
| Can the adapter connect to the external system? | Connection logs, health, and adapter status |
| Are messages waiting? | Queue depth, broker backlog, executor queue |
| Are resources retained after removing the flow? | Thread dumps, connection metrics, and heap dumps |

A diagnostic procedure:

1. Determine whether the flow is a static bean or a dynamically registered flow.
2. For a static flow, check the bean definition and endpoint ID in the context.
3. For a dynamic flow, inspect flowContext.getRegistrationById(id) and the registry.
4. Check isRunning, autoStartup, and phase of the endpoint.
5. Check whether the adapter, poller, or subscriber has been activated.
6. If the flow is stopped, determine whether it is an intentional pause or a lifecycle error.
7. If the flow has been removed, find where the application still holds references to the registration, channel, or dependent beans.
8. Cross-check start/stop/destroy logs to identify which component did not complete its lifecycle.

When using Spring Boot Actuator and appropriate Spring Integration management, the integration graph and metrics can aid in observing integration components. They supplement runtime visibility but do not replace checking lifecycle state and the registry.

## 9. Practical Scenario: Enabling and Removing a Tenant Flow

Suppose a tenant can be enabled or disabled while the application is running. TenantManager is responsible for creating the flow and storing the registration ID.

~~~mermaid
flowchart TD
    A["Tenant is activated"] --> B["Build IntegrationFlow"]
    B --> C["Register via IntegrationFlowContext"]
    C --> D{"Is configuration ready?"}
    D -->|No| E["Keep registration in stopped state"]
    D -->|Yes| F["registration.start()"]
    F --> G["Flow receives and processes messages"]
    G --> H["Tenant is deactivated"]
    H --> I["Stop message source"]
    I --> J["Wait for in-flight processing / drain"]
    J --> K["flowContext.remove(id)"]
    K --> L["Release registration and dependent beans"]
~~~

Points to ensure:

- The tenant ID maps to the exact corresponding flow.
- Do not register duplicate flows for the same tenant if business rules allow only one flow.
- If flow registration fails partway through, the service must handle the error and not store an incomplete registration.
- If the tenant is only suspended, use stop; if the tenant is deleted, remove the flow.
- Upon removal, clear references held by TenantManager to the channel and registration.
- When the application shuts down, dynamic flows must still be stopped and released according to the context lifecycle.

This example also shows that IntegrationFlowContext is a tool for managing flow structure at runtime; it does not replace a tenant configuration store, leader election mechanism, message delivery guarantees, or retry workflows.

## 10. Common Misconceptions to Avoid

- **ApplicationContext is not IntegrationFlowContext**: ApplicationContext manages all beans; IntegrationFlowContext specializes in managing dynamically registered IntegrationFlows.
- **IntegrationFlow is not a single endpoint**: a flow describes a chain of components; at runtime there are multiple channels, endpoints, and handlers.
- **Bean creation does not mean the endpoint is running**: the endpoint may have autoStartup disabled or not yet be started.
- **stop does not mean remove**: stop keeps the registration and beans; remove/destroy destroys the flow and dependent beans.
- **IntegrationContextUtils does not register flows**: it is a utility for accessing infrastructure beans from BeanFactory.
- **autoStartup=false does not turn itself back on**: the application must call start or use an appropriate lifecycle controller.
- **phase is not message processing priority**: phase controls lifecycle start/stop order, not message ordering within a channel.
- **role is not authorization**: role groups SmartLifecycle components for group lifecycle control.
- **Stopping an endpoint does not guarantee the queue is empty**: a separate drain and shutdown strategy is required.
- **Removing a flow does not clear application-held references**: you must clear references to the removed registration, channels, and resources.

## 11. Self-Check

1. ApplicationContext created the channel and handler, yet the flow receives no messages. How would you check endpoint lifecycle and autoStartup?
2. What is the difference between IntegrationFlowContext and IntegrationContextUtils? Which API is used to register dynamic flows?
3. A dynamically registered flow has autoStartup(false). After register(), why is the flow not processing messages yet, and which operation must be called?
4. When a tenant is temporarily suspended, should you use stop() or remove()? When the tenant is permanently deleted, which operation should you use?
5. Why does stopping a polling endpoint not necessarily mean all messages in the queue have been processed?
6. If a downstream consumer must be ready before an inbound source and stopped after the inbound source, what principle should guide phase ordering?
7. When multiple endpoints must run only on the instance currently holding leadership, how can role and SmartLifecycleRoleController be used?

## References

- [Spring Integration — IntegrationFlowContext API](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/dsl/context/IntegrationFlowContext.html)
- [Spring Integration — StandardIntegrationFlow API](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/dsl/StandardIntegrationFlow.html)
- [Spring Integration — AbstractEndpoint API](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/endpoint/AbstractEndpoint.html)
- [Spring Integration — Endpoint Roles](https://docs.spring.io/spring-integration/reference/endpoint-roles.html)
- [Spring Integration — IntegrationContextUtils API](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/context/IntegrationContextUtils.html)

## Conclusion

ApplicationContext manages the overall beans and lifecycle of the application. Spring Integration endpoints participate in that lifecycle to register subscribers, start pollers or adapters, and release resources on shutdown. For static flows, Spring manages the beans declared in the context; for dynamically created flows, IntegrationFlowContext provides registrations to start, stop, look up, and remove flows. Understanding the distinction between initialization, start, stop, and destroy helps control runtime state, avoid forgotten endpoints, and shut down the application cleanly.
