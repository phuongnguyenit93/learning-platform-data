# Choosing When to Register Flows in an Application

An `IntegrationFlow` can be declared statically alongside the Spring ApplicationContext or created and registered while the application is running. This choice determines when endpoints appear, when consumers begin receiving messages, which dependencies must be ready, and who is responsible for stopping and removing the flow.

`IntegrationFlowContext` serves cases where flows must be registered dynamically. However, dynamic registration is not the default choice for every flow. If the topology is known when writing the application and always exists, declaring flows with `@Bean` is usually easier to manage. Register at runtime only when the timing or structure of a flow genuinely depends on configuration, tenants, partners, or a business lifecycle event.

## 1. Two ways to bring an IntegrationFlow into the ApplicationContext

### Static flow with @Bean

When the topology is stable, declare the flow as a bean:

~~~java
@Configuration
@EnableIntegration
public class OrderFlowConfiguration {

    @Bean
    IntegrationFlow orderFlow(OrderService orderService) {
        return IntegrationFlow.from("orders.input")
                .handle(orderService, "process")
                .get();
    }
}
~~~

Spring creates and registers the flow during ApplicationContext initialization. Endpoints belonging to the flow participate in bean and Spring Integration lifecycles. This approach fits when the application always has the same channels, handlers, and routing rules on every startup.

The advantages are that configuration is explicit in source code, dependencies are injected normally, configuration errors usually surface at startup, and Spring manages endpoint lifecycles. There is no need to store registration IDs manually or write flow-removal logic for application shutdown.

### Dynamic flow with IntegrationFlowContext

When a flow exists only after a runtime condition, you can build an `IntegrationFlow` object and register it using `IntegrationFlowContext`:

~~~java
IntegrationFlow flow = IntegrationFlow.from(MessageChannels.direct())
        .handle((payload, headers) -> partnerService.process(partnerId, payload))
        .get();

IntegrationFlowRegistration registration = flowContext.registration(flow)
        .id("partner-" + partnerId)
        .useFlowIdAsPrefix()
        .register();
~~~

`registration(...)` creates a builder for the registration. `id(...)` sets a stable ID to look up and remove the flow; `useFlowIdAsPrefix()` gives components created inside the flow a dedicated prefix, reducing the risk of name collisions when registering multiple flows with similar structures. `register()` places the flow and related components into the Integration context and returns an `IntegrationFlowRegistration` to interact with the newly registered flow.

The registration provides capabilities such as retrieving the input channel, accessing the flow, and controlling lifecycle. For example, when a flow uses an input channel created by the DSL, you can send messages via `registration.getInputChannel()`. When the flow is no longer needed, use `IntegrationFlowContext.remove(flowId)` to remove the registration along with the beans managed by that registration.

## 2. Choosing timing based on the application lifecycle

Registration timing should be decided from two questions: what data is needed to build the flow, and which message sources could start sending as soon as the flow becomes active?

| Timing | When appropriate | What to control |
|---|---|---|
| `@Bean` declaration at context initialization | Fixed topology, dependencies already in context | Dependency injection and endpoint lifecycle ordering |
| `ApplicationRunner` or `CommandLineRunner` | Need to read initial configuration from database or file after context refresh | Finish registering before application reports ready; coordinate with auto-started inbound endpoints |
| `ApplicationReadyEvent` | Flow is only needed after runners complete and application is nearly ready | If the flow receives inbound messages, ensure senders do not emit messages before the listener finishes registering |
| Business or administrative event | Tenant is activated, partner is configured, or feature is enabled at runtime | Idempotent registration, unique ID, cleanup when configuration is removed |
| Explicit administrative action | Operator manually enables/disables an integration | Authorization, input validation, and observable registration state |

Do not register flows inside a constructor. At that point, aware callbacks and part of bean configuration are not yet complete. `@PostConstruct` is also not a good default for dynamic registration: it runs during bean creation, before the entire context and lifecycle components are guaranteed to be ready.

If a flow must exist before the application accepts traffic, `ApplicationRunner` is usually an intuitive point: the context has refreshed, dependencies are injected, and runners execute before `ApplicationReadyEvent`. However, an inbound adapter implementing `SmartLifecycle` may already have auto-started during refresh. If that source can emit messages immediately, a runner registering the flow might arrive after the first message. When strict ordering is required, keep inbound endpoints unstarted, register and start the flow first, and only then start the message source; or coordinate components using appropriate lifecycle phases.

`ContextRefreshedEvent` should not be used mechanically for every registration. This event can fire multiple times in applications with parent/child contexts or on context refreshes. If using a listener, identify the exact target context to handle and make registration idempotent.

## 3. Startup sequence to avoid losing messages

For a dynamic flow acting as a consumer for an inbound source, the desired order is usually:

~~~mermaid
sequenceDiagram
    participant App as ApplicationContext
    participant Config as Configuration Store
    participant Flow as IntegrationFlowContext
    participant Source as Inbound Adapter
    App->>Config: Read integration configurations to enable
    Config-->>App: List of valid configurations
    App->>Flow: Create and register IntegrationFlows
    Flow-->>App: Return IntegrationFlowRegistration
    App->>Flow: start() verified flows
    App->>Source: start() message source
    Source->>Flow: Send message to input channel
~~~

If the message source runs before the registration step, messages may arrive when there is no subscriber yet. The outcome depends on channel type and how the source sends: synchronous sends may fail due to no consumer; queues may buffer messages waiting; brokers may retry or retain messages according to broker semantics. Do not rely on luck. Explicitly define the start order and the policy when a flow is not yet ready.

You can split registration and startup into two phases using `autoStartup(false)`:

~~~java
IntegrationFlowRegistration registration = flowContext.registration(flow)
        .id(flowId)
        .useFlowIdAsPrefix()
        .autoStartup(false)
        .register();

// Check required dependencies and state before receiving messages.
registration.start();
~~~

`autoStartup(false)` lets the application register the flow first without actively starting endpoints under the registration lifecycle. Only call `start()` when dependencies and ingress paths are ready. If you want to keep the flow registered without receiving traffic yet, do not expose the input channel to producers beforehand.

For complex startup coordination requirements, use `SmartLifecycle` to manage start/stop and phases. The phase determines the order in which lifecycle components are started and stopped; choose phases based on actual dependency relationships, and verify the ordering via startup logs. Do not assume ordering merely from the declaration order of `@Bean` methods.

## 4. Registering flows when runtime configuration changes

A typical case is each partner having its own flow, or a tenant only having a flow after activation. The flow is created once configuration is valid, without recreating it on every message.

~~~java
@Component
public class PartnerFlowRegistrar {

    private final IntegrationFlowContext flowContext;
    private final PartnerService partnerService;
    private final Map<String, IntegrationFlowRegistration> registrations =
            new HashMap<>();

    public PartnerFlowRegistrar(IntegrationFlowContext flowContext,
                                PartnerService partnerService) {
        this.flowContext = flowContext;
        this.partnerService = partnerService;
    }

    public synchronized IntegrationFlowRegistration register(String partnerId) {
        String flowId = "partner-" + partnerId;
        IntegrationFlowRegistration existing = registrations.get(flowId);
        if (existing != null) {
            return existing;
        }

        IntegrationFlow flow = IntegrationFlow.from(MessageChannels.direct())
                .handle((payload, headers) ->
                        partnerService.process(partnerId, payload))
                .get();

        IntegrationFlowRegistration registration = flowContext.registration(flow)
                .id(flowId)
                .useFlowIdAsPrefix()
                .autoStartup(false)
                .register();

        registrations.put(flowId, registration);
        registration.start();
        return registration;
    }

    public synchronized void unregister(String partnerId) {
        String flowId = "partner-" + partnerId;
        if (registrations.remove(flowId) != null) {
            flowContext.remove(flowId);
        }
    }
}
~~~

The example uses `synchronized` so two activation events for the same partner do not concurrently create two registrations with the same ID on this instance. Multi-instance applications still need clear assignment rules: if every instance receives the tenant-activated event and creates a consumer, duplicate processing may occur. Decide whether a flow belongs to one instance, a group of instances, or all instances; use distributed locks, partitioning, or an appropriate coordination mechanism if only one instance is allowed to own the consumer.

In the example, `registrations` is the registrar's in-memory registry. When the application restarts, the map will be empty; the application must reload the list of active partners from a durable configuration store and re-register them. Do not treat an in-memory map as the primary source of truth for integration state.

Flow IDs must be stable and unique within the context. If an ID is derived from an external tenant or partner code, normalize characters and bound length before using it as a bean name. Avoid generating random names on every restart unless multiple concurrent versions are needed; stable IDs help observe, inspect, and remove the right flow.

## 5. Choosing timing for specific scenarios

### Topology always present while the application runs

Use `@Bean`. For example: a flow that receives orders, validates data, saves to the database, and emits events always exists. Place the configuration in the ApplicationContext so dependencies and lifecycles are managed consistently.

### Topology dependent on configuration available at startup

Read configuration in `ApplicationRunner`, validate it, and then register flows. This fits when the tenant or partner list is stored in a database and may change between deployments. If an inbound source can emit messages while the runner is executing, coordinate source startup as shown earlier.

### Topology changing while the application is running

Use a flow-management service and invoke `IntegrationFlowContext` on configuration events. For example: when a partner is enabled, register the flow; when disabled, stop and remove the flow. Operations must be idempotent because events may be replayed or reprocessed.

### Flow needed only for a short-lived operation

Consider using a stable flow with a router or dynamic configuration instead of continually creating and destroying flows. Registering a flow carries the cost of creating beans, endpoints, and lifecycle state; creating flows per request easily causes component leaks, increases bean counts, and makes runtime harder to observe. Only use temporary flows when there are clear lifecycle boundaries and reliable cleanup mechanisms.

## 6. Changing configuration and removing flows safely

When a flow's configuration changes, do not simply register a new flow with a different ID and forget the old flow. Define a replacement strategy:

1. Stop accepting new messages into the old flow or redirect the source to another entry point.
2. Process or wait for in-flight messages according to the chosen drain policy.
3. Stop and remove the old registration via `IntegrationFlowContext.remove(flowId)`.
4. Register the new flow with validated configuration.
5. Start the new flow and direct traffic to it.

If zero interruption is required, you can register a new versioned flow in parallel with a separate ID and input, verify it first, and then switch producers or routers to the new version. Only remove the old flow once no messages remain to be processed. Avoid letting two flows consume from the same message source simultaneously if downstream operations are not idempotent.

Removing a flow does not automatically resolve all business state outside the flow. Messages sitting in a broker, queue, or MessageStore must be handled according to the policy of that storage component itself. Before deleting a registration, identify where messages currently reside, whether they must be drained or forwarded, and who is responsible for incomplete messages.

## 7. Common errors when choosing the wrong timing

| Symptom | Possible cause | Remediation |
|---|---|---|
| Messages arrive before the flow has a consumer | Inbound adapter starts before registration | Register/start the flow before the source, or keep the source at `autoStartup(false)` |
| Flow registration fails due to duplicate bean name | ID or component name is not unique | Use a stable flow ID, prefix component names, and check for duplicates before registering |
| Same tenant has multiple flows | Duplicate events, multiple threads, or multiple instances registering concurrently | In-instance idempotency and distributed ownership mechanisms if needed |
| Flow does not appear after enabling tenant | Listener missed event, invalid configuration, or registration failed | Log flow ID, registration state, bean creation errors, and start status |
| Tenant disabled yet messages still processed | Registration was not removed or messages already sit in queue/broker | Remove flow and handle remaining messages separately per source semantics |
| Bean count grows over time | Creating flows per request or missing cleanup | Register only per configuration unit with a clear lifecycle; remove when unused |
| Application reports ready while flow is not ready | Registered too late or not participating in readiness | Register in a runner or include flow state in application readiness checks |

## 8. Observing and checking registration state

Every flow registration or removal should produce structured logs containing the flow ID, reason for change, tenant/partner masked or encoded per policy, timestamp, and outcome. Do not log credentials or full connection configurations.

In operations, distinguish at least four states:

- **Unregistered:** no registration exists in `IntegrationFlowContext`.
- **Registered, not started:** flow and endpoints have been created, but are not yet receiving messages per lifecycle.
- **Active:** registration has started; also verify downstream channels, consumers, and dependencies.
- **Removed:** registration has been removed; any messages remaining in brokers/queues still have their own lifecycle.

You can look up a registration by ID via `IntegrationFlowContext` and inspect the registration's input channel. Combine Integration Graph, endpoint logs, and metrics to verify the runtime topology. Merely seeing a registration does not prove messages are being processed successfully; check whether consumers are active, whether backlogs are growing, and whether error flows are receiving errors.

Track the number of registered flows, started flows, registration failures, registration duration, and removal counts. For per-tenant flows, these metrics help detect duplicate events inflating component counts or tenant groups failing to activate properly.

## 9. Checklist for deciding registration timing

- [ ] Is the topology fixed across all runs? If yes, prefer declaring with `@Bean`.
- [ ] For dynamic flows, are the conditions that trigger creation and removal clearly known?
- [ ] Are required dependencies and configuration ready before calling `register()`?
- [ ] Can inbound sources emit messages before the flow starts?
- [ ] Is `autoStartup(false)` needed to separate registration from startup?
- [ ] Is the flow ID stable, unique, and safe to use as a bean name?
- [ ] Could duplicate events or multiple threads create duplicate registrations?
- [ ] When updating or disabling configuration, who stops the flow and handles remaining messages?
- [ ] After restart, can the application rebuild active flows from durable configuration?
- [ ] Do logs, metrics, and Integration Graph clearly show whether a flow is registered, started, or removed?

Choose registration timing based on the true lifecycle of the topology and message sources. Static flows belong in ApplicationContext configuration; dynamic flows should be created once configuration is valid and before producers can send messages into them. Once registered, the application must retain IDs, start/stop states, and cleanup rules so the flow's lifecycle never drifts from the business lifecycle.

## References

- [Spring Integration Reference: Dynamic and Runtime Integration Flows](https://docs.spring.io/spring-integration/reference/dsl/java-runtime-flows.html)
- [Spring Integration API: IntegrationFlowContext](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/dsl/context/IntegrationFlowContext.html)
- [Spring Boot Reference: Application Events and Runners](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- [Spring Framework Reference: Lifecycle callbacks and SmartLifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
