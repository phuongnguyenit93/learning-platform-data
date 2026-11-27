# Avoiding Circular Dependencies Among Integration Components

In Spring Integration, a message flow is composed of multiple components such as channels, endpoints, handlers, gateways, adapters, and services. Spring instantiates these components as beans in the `ApplicationContext`, then connects them so messages can travel through the flow. If beans depend on each other in a cycle, the application may fail to start because Spring cannot finish creating the objects.

Circular dependencies commonly arise when a service used by a flow injects the `IntegrationFlow` itself, an endpoint, or a flow-management component to call back into that flow. A safe design lets the flow depend on handlers/services, while services communicate with other steps through channels or messaging gateways with clear boundaries. That keeps the message flow structure flexible without closing the bean-creation graph into a cycle.

After this lesson, you will be able to:

- Identify cycles in the bean dependency graph and distinguish them from message flow loops.
- Understand why injecting `IntegrationFlow`, endpoints, or flow configuration back into a service easily creates a circular dependency.
- Design communication boundaries using `MessageChannel` and messaging gateways.
- Properly evaluate the roles of constructor injection, `@Lazy`, `ObjectProvider`, and `@DependsOn`.
- Read bean initialization errors and trace the dependency chain to fix the structure.

## 1. Two Kinds of Graphs Not to Confuse

When analyzing Spring Integration, separate the **bean dependency graph** from the **message flow graph**. They describe two different relationships.

The bean dependency graph describes which object needs which other object while Spring creates and configures beans. If bean A requires bean B to initialize, there is an edge `A -> B`. A cycle such as `A -> B -> A` means two beans require each other before either can be fully created.

The message flow graph describes the order in which messages travel through channels and endpoints. A message may go from A to B and then be routed back to A by a router. That is a message processing loop; it does not automatically mean Spring beans have a circular dependency.

```text
Bean dependency graph (at startup)

OrderFlowConfig ---> OrderHandler
       ^                 |
       |                 v
       +------------- FlowFacade

Message flow graph (at runtime)

ordersInput ---> OrderHandler ---> inventoryInput ---> InventoryHandler
```

In the figure above, the bean cycle causes initialization problems. The message flow graph below it is a normal processing sequence. An intentional message loop can be valid if it has a termination condition; conversely, a bean cycle does not become safe merely because the message flow is well-designed.

## 2. How Does a Circular Dependency Form?

Suppose a flow configuration requires `OrderCoordinator` as a handler. However, `OrderCoordinator` injects the `IntegrationFlow` bean itself to invoke or inspect the flow:

```java
@Configuration
class OrderFlowConfiguration {

    @Bean
    IntegrationFlow ordersFlow(OrderCoordinator coordinator) {
        return IntegrationFlow.from("ordersInput")
                .handle(coordinator, "process")
                .get();
    }
}

@Component
class OrderCoordinator {

    private final IntegrationFlow ordersFlow;

    OrderCoordinator(IntegrationFlow ordersFlow) {
        this.ordersFlow = ordersFlow;
    }

    public void process(Order order) {
        // Process the order and call back into the flow.
    }
}
```

Spring must create `ordersFlow`, so it needs `OrderCoordinator`. Yet to create `OrderCoordinator`, Spring needs `ordersFlow`. The dependency cycle is:

```text
ordersFlow -> OrderCoordinator -> ordersFlow
```

This is a circular dependency at bean initialization time. Invoking `ordersFlow` inside `process()` is not even the root issue; the issue is that the service holds a direct reference to the flow definition to coordinate work.

Cycles can span more than two beans, for example `FlowConfig -> HandlerA -> GatewayB -> ServiceB -> FlowConfig`. When reading a stack trace, trace the entire dependency chain rather than looking only at the first two beans that appear.

## 3. Flows Should Depend on Handlers; Handlers Communicate Across Boundaries

An `IntegrationFlow` should be responsible for wiring processing steps together. Handlers/services should focus on business logic and depend only on the collaborators needed to perform that business logic. If a handler needs to send a message to another step, use a channel or gateway representing that communication boundary.

The following example separates the flow definition, channel, and gateway into independently instantiable beans:

```java
@MessagingGateway(defaultRequestChannel = "ordersInput")
interface OrderGateway {
    void submit(Order order);
}

@Configuration
@IntegrationComponentScan
class OrderFlowConfiguration {

    @Bean
    MessageChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow ordersFlow(OrderHandler orderHandler) {
        return IntegrationFlow.from("ordersInput")
                .handle(orderHandler, "handle")
                .get();
    }
}

@Component
class OrderHandler {

    private final OrderRepository repository;

    OrderHandler(OrderRepository repository) {
        this.repository = repository;
    }

    public void handle(Order order) {
        repository.save(order);
    }
}

@Service
class OrderApplicationService {

    private final OrderGateway orderGateway;

    OrderApplicationService(OrderGateway orderGateway) {
        this.orderGateway = orderGateway;
    }

    public void submit(Order order) {
        orderGateway.submit(order);
    }
}
```

The dependency graph now looks like:

```text
OrderFlowConfiguration ---> OrderHandler ---> OrderRepository
          |
          v
     ordersInput <--- OrderGateway <--- OrderApplicationService
```

Both the flow and the gateway use `ordersInput`, yet the channel is an independent bean. `OrderHandler` does not need to know which flow invokes it; `OrderApplicationService` only knows the gateway to submit commands. There is no dependency edge from the handler back to the flow definition.

In applications with multiple channels of the same type, use clear bean names and `@Qualifier` when injecting `MessageChannel` directly to avoid selecting the wrong channel. A gateway can declare `defaultRequestChannel` or configure per-method channels with `@Gateway`.

If a handler needs to forward to an inventory check step, create another gateway with its own input channel—for example, `InventoryGateway` sending to `inventoryInput`. The inventory check flow registers its handler on that channel. The first handler depends only on `InventoryGateway`; it does not inject `InventoryFlow` or the inventory flow's endpoints.

A channel creates a clean boundary only when the channel bean can be created independently. If the channel's factory method itself requires a service that depends back on the flow, the cycle remains. Inspect all actual dependency edges rather than mechanically swapping reference types from `IntegrationFlow` to `MessageChannel`.

## 4. Design Rules That Prevent Cycles

### 4.1. Do Not Inject IntegrationFlow or Endpoints into Business Services

`IntegrationFlow` describes how components are wired. Business services should not hold a flow bean just to send messages into the start of the flow, invoke endpoints, or inspect endpoint state. Use a messaging gateway, a channel, or an application service responsible for coordination at the appropriate layer.

Similarly, avoid injecting DSL-created consumer endpoint or handler implementations into another service. These runtime beans are wiring details of the integration layer; depending on them directly obscures initialization structure and easily creates backward edges.

### 4.2. Keep Channels Independent of Services and Flows

Declare channels as small infrastructure beans without letting the channel factory depend on the handlers or services using that channel. A channel is the link between producer and consumer; it does not need to know who sends or who processes messages.

For channels declared inline in Java DSL, consider extracting a channel into its own bean if multiple flows or gateways need to reference it. This clarifies boundaries and avoids backward dependencies through configuration.

### 4.3. Separate Orchestration Responsibilities from Business Logic

A service that handles business logic, manages flow registrations, and calls back into endpoints usually holds too many responsibilities. Split into components with clear roles:

- Flow configuration connects channels, handlers, and adapters.
- Handler/application services execute business logic.
- Gateways represent message-sending operations.
- A flow manager handles dynamic registration if the application genuinely needs to create/remove flows at runtime.

The flow manager can depend on `IntegrationFlowContext` to register dynamic flows. Handlers used by a flow should not depend back on the flow manager merely to invoke another step; use a gateway/channel for message communication.

### 4.4. Prefer Constructor Injection

Constructor injection makes clear which dependencies a bean requires and surfaces cycles immediately at startup. If A's constructor requires B and B's constructor requires A, Spring cannot create either bean first to complete the other.

Do not convert dependencies en masse to field or setter injection just to bypass the error. Some singleton cycles using setter injection may be resolved by Spring via early references in certain configurations, but the outcome depends on bean types, proxies, and initialization lifecycle. An object may be accessed before it is fully initialized; prototypes or constructor-based cycles still cannot be resolved that way.

## 5. `@Lazy`, `ObjectProvider`, and `@DependsOn` Do Not Replace Good Design

When encountering a circular dependency, several mechanisms are often suggested. Each has legitimate use cases, but none should be used simply to hide a flawed dependency graph.

| Mechanism | Effect | Limitation |
|---|---|---|
| `@Lazy` | Injects a proxy and defers bean resolution until first use. | Only delays when the dependency is needed; if two components still call each other or trigger during init, problems can surface later. |
| `ObjectProvider<T>` | Fetches beans on demand, supporting optional or deferred dependencies. | Does not eliminate design-level dependencies; calling `getObject()` too early can still hit the cycle. |
| Setter/field injection | Allows some singletons to be instantiated first before wiring dependencies. | Relies on early reference mechanics; hides dependencies and risks using an unready bean. |
| `@DependsOn` | Instructs Spring to initialize one bean before another. | Only dictates initialization order; cannot eliminate an A-needs-B and B-needs-A cycle. |
| `@Primary` / `@Qualifier` | Selects a bean when multiple candidates of the same type exist. | Resolves bean selection ambiguity, not circular dependencies. |

`@Lazy` or `ObjectProvider` is appropriate when you genuinely need an optional dependency, a late-loaded plugin, or an operation that occurs only after the context is ready. If the sole reason is that the application reports a circular dependency, go back and separate responsibilities and define boundaries first.

Starting with Spring Boot 2.6, circular references between beans are prohibited by default. The `spring.main.allow-circular-references` property can alter this behavior in supported versions, but re-enabling it just to make the application start is not a structural fix. Check the Spring Boot version you are using before relying on version-specific behavior.

## 6. Distinguishing Bean Cycles from Message Flow Loops

A message loop can be a valid business requirement—for instance, a message passing through multiple validation steps until a completion condition is met. It does not necessarily create a circular dependency when Spring instantiates beans, because endpoints can still be created independently.

However, a message loop without a stopping condition can burn CPU, grow queues unboundedly, or repeatedly execute the same business action. With `DirectChannel`, messages may re-enter handlers via nested calls and deepen the call stack. With `QueueChannel` or `ExecutorChannel`, messages may be continuously re-enqueued.

If a flow needs to return to an earlier step, design explicit exit conditions:

- Use a header or business state representing retry/hop count.
- Use a filter/router to terminate or route messages to an error branch when the limit is exceeded.
- Use a correlation ID to trace the same processing chain and an idempotency key to prevent reapplying a business side effect.
- Enforce retry limits and distinguish retries for transient failures from flow-level control loops.
- Log redirections and provide an escape path for messages that cannot proceed.

Do not rely on message ID to bound a loop, because a step that creates a new message can generate a new ID. Use a stable business header or state managed specifically for the entire processing chain.

## 7. Patterns That Easily Create Backward Dependencies in Spring Integration

| Design pattern | Risk | How to reorganize |
|---|---|---|
| Handler injects the `IntegrationFlow` containing that handler. | Flow needs handler to be created; handler needs flow. | Handler only handles business logic; producers send via gateway/channel. |
| Service injects a consumer endpoint to call `start()` or `stop()`. | Business service depends on endpoint lifecycle details; flow may depend back on service. | Create a dedicated flow manager, manage lifecycle through an appropriate API, and avoid handler depending on manager. |
| Two services call each other directly. | Bean cycle appears even without a flow. | Extract shared parts into a third service or emit messages across a boundary. |
| Channel factory requires a service that sends messages into that same channel. | Cycle can pass through the factory method and service. | Channels are independent infrastructure beans; do not inject producers/consumers. |
| Service calls `ApplicationContext.getBean()` to fetch a flow or endpoint. | Dependencies are hidden, hard to trace, and prone to runtime errors. | Declare dependencies intentionally via constructor/gateway/provider. |
| Multiple endpoints unexpectedly subscribe to the same channel. | Not necessarily a circular dependency, but can cause messages to be received by multiple consumers or distributed unexpectedly. | Inspect topology and clarify whether fan-out or competing consumers is intended. |

In particular, two endpoints reading from the same `SubscribableChannel` do not automatically create a bean cycle. That is a topology and message-distribution semantics issue. Diagnose according to the actual relationship type rather than calling every anomaly a circular dependency.

## 8. How to Diagnose Circular Dependency Errors

When the ApplicationContext fails to start, Spring typically reports `BeanCurrentlyInCreationException` or an `UnsatisfiedDependencyException` with a nested cause. Read the dependency path and bean names in the error message.

Practical workflow:

1. **Identify the bean named in the error.** Record which bean was being created and which dependency Spring could not resolve.
2. **Trace constructor and factory method chains.** Inspect constructor injection, `@Bean` parameters, `@Autowired`, gateways, and factories/providers.
3. **Draw the dependency graph.** Write each edge `A -> B` reflecting the exact creation-time requirement; locate the edge returning to the starting bean.
4. **Identify each bean's role.** Which bean is a flow definition, channel, endpoint, handler, gateway, service, or flow manager?
5. **Choose a boundary to remove the backward edge.** Replace the flow/endpoint reference with a gateway or an independent channel, or extract shared logic into a third service.
6. **Restart the context and verify the message flow.** Confirm the bean graph is acyclic, then send test messages to ensure topology and routing remain correct.

An example error may show a chain such as:

```text
Error creating bean with name 'ordersFlow'
  -> constructor/factory method needs 'orderCoordinator'
  -> bean 'orderCoordinator' needs 'flowFacade'
  -> bean 'flowFacade' needs 'ordersFlow'

Circular path:
ordersFlow -> orderCoordinator -> flowFacade -> ordersFlow
```

Actual bean names and formatting vary with Spring versions and declaration styles. Follow the dependency chain provided by the exception, and do not assume every `UnsatisfiedDependencyException` is a circular dependency; it can also stem from a missing bean, wrong qualifier, or another dependency creation failure.

The Integration Graph helps observe integration components and message flow relationships. It is useful for spotting looping message topologies or miswired endpoints, though it does not replace the Spring bean factory dependency path. When an error occurs before context completion, the Integration Graph may not even be ready to query.

## 9. Design Checklist Before Adding Components

Before adding a new handler, gateway, or flow, check:

- Flows only wire components; business services do not need to hold references to flow definitions or endpoints.
- Shared channels are created independently without needing message-sending/receiving services to initialize.
- Gateways clearly express message entry points and target channels.
- Handlers depend only on the services/repositories or gateways they genuinely need.
- A flow manager handles dynamic registrations in one place; handlers do not call back into the manager to control their enclosing flow.
- Constructor injection exposes the dependency graph clearly; `@Lazy` or setter injection is not used merely to hide errors.
- If a message flow contains a loop, exit conditions, loop limits, and error-handling paths are defined.
- Both the initialization-time dependency graph and the runtime message topology are verified.

## 10. Self-Check

**Scenario:** `ordersFlow` uses `OrderHandler`. `OrderHandler` injects `OrderFlowManager`, and `OrderFlowManager` injects the `IntegrationFlow` named `ordersFlow` to re-invoke the flow when further processing is needed.

1. What is the bean dependency cycle?
2. Why does replacing `IntegrationFlow` with `MessageChannel` solve the problem if the channel is an independent bean?
3. If a message from `OrderHandler` is sent via a channel back to `ordersInput`, what kind of loop is that?
4. What mechanisms are needed so the message loop does not run infinitely?

**Suggested answers:** (1) `ordersFlow -> OrderHandler -> OrderFlowManager -> ordersFlow`. (2) Both the flow and the producer reference an independent channel; the channel does not need to create the flow or service, so no bean cycle is closed. (3) That is a message flow loop, not automatically a bean circular dependency. (4) Exit conditions such as hop count, filter/router, business state, retry limits, and error handling are required.

**Design exercise:** Split an order-processing flow into two steps: validation and inventory check. Create a separate input channel for each step and a gateway so the validation step sends to the inventory check step. Draw the bean dependency graph and the message flow graph. Confirm the bean graph has no cycles; then verify messages pass through both steps exactly once according to business rules.

## References

- [Spring Framework Reference — Dependencies and Configuration in Detail](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
- [Spring Framework Reference — Using `@Lazy`](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-lazy-init.html)
- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html)
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html)
- [Spring Boot 2.6 Release Notes — Circular References Prohibited by Default](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-2.6-Release-Notes#circular-references-prohibited-by-default)
