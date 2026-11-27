# Bean Name, Managed Name, and Runtime Identifiers

In Spring Integration, a component can be identified by multiple names depending on where you observe it. The Spring ApplicationContext uses a **bean name** to register and look up objects. Spring Integration also has component, endpoint, and channel names to describe the message flow structure. The runtime management layer can expose names for metrics and operations. Meanwhile, each message has its own `id` and may have its own `correlationId`.

These identifiers are related but not synonymous. An `IntegrationFlow` may have the bean name `ordersFlow`, contain an endpoint with ID `orders.persist`, read from the channel `orders.input`, and process messages with their own IDs. When diagnosing errors or reading the runtime graph, you need to know which name belongs to the ApplicationContext, which belongs to the Integration structure, and which belongs solely to a specific message.

## 1. Layers of Identifiers to Distinguish

| Identifier | Scope | What is it used for? | Example |
|---|---|---|---|
| Bean name | Spring `BeanFactory` / `ApplicationContext` | Registering, looking up, and injecting a bean | `ordersInput`, `ordersFlow` |
| Bean alias | Spring `BeanFactory` | Additional name pointing to the same bean | `ordersInbound` as an alias of `ordersInput` |
| Integration component name | A Spring Integration component | Identifying a channel, endpoint, or component in the Integration structure | `orders.persist` |
| Endpoint ID | A specific endpoint | Intentionally naming an endpoint for management and diagnostics | `orders.persist` |
| Channel name | A `MessageChannel` in the context | Indicating a message receive/send point in a flow | `orders.input` |
| Flow bean name | Spring `ApplicationContext` | Identifying the flow-describing bean declared with `@Bean` | `ordersFlow` |
| Flow registration ID | `IntegrationFlowContext` | Identifying a dynamically registered flow | `tenantAOrders` |
| Managed name / managed type | Management surface of a management-enabled component | Associating a component with management info and metrics | Component name/type exposed for management |
| Message ID / correlation ID | A message or group of messages | Tracking individual messages or related messages | `MessageHeaders.ID`, `correlationId` |

A single string can be used as a name across multiple scopes, but sharing the same string does not make those identifiers identical. For example, `orders.input` may be the channel's bean name and also the name an endpoint references in configuration. The endpoint is still a separate component from that channel.

## 2. Bean Name in Spring ApplicationContext

A bean name is the key Spring uses to register a bean in `BeanFactory`. This is the name commonly used when looking up a bean by name, referencing a bean in configuration, or resolving a channel by name.

Spring can generate bean names by convention:

- For classes annotated with `@Component`, `@Service`, `@Repository`, or similar stereotypes, the default name is usually the class name with a lowercase first letter, e.g., `OrderHandler` becomes `orderHandler`.
- For `@Bean` methods, the default name is the method name, e.g., `ordersInput()` creates a bean named `ordersInput`.
- You can specify a name explicitly via the stereotype's `value`/`name` attribute or `@Bean`'s `name` attribute.

Example of declaring a channel and handler:

```java
@Configuration
@EnableIntegration
public class OrderIntegrationConfiguration {

    @Bean
    public MessageChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean
    public OrderHandler orderHandler() {
        return new OrderHandler();
    }
}
```

In the configuration above, the ApplicationContext manages two beans named `ordersInput` and `orderHandler`. You can look up the channel and handler by name:

```java
MessageChannel input = context.getBean("ordersInput", MessageChannel.class);
OrderHandler handler = context.getBean("orderHandler", OrderHandler.class);
```

Bean names must be unique within their corresponding registry scope. If two configurations register the same name, the outcome depends on the bean registration policy and whether overriding is allowed; in environments where overriding is disallowed, context startup may fail. Therefore, choose names that reflect the bean's function and scope, especially when modules are combined into the same ApplicationContext.

### Aliases Do Not Create a Second Bean

A bean can have multiple aliases:

```java
@Bean(name = {"ordersInput", "ordersInbound"})
public MessageChannel ordersInput() {
    return new DirectChannel();
}
```

`ordersInput` is the primary bean name in this declaration; `ordersInbound` is an alias. Both names resolve to the same managed object, not two independent channels. You can inspect aliases with `context.getAliases("ordersInput")`.

Aliases are useful when preserving backward-compatible names while changing naming conventions. However, do not treat an alias as if it were a new endpoint or a new instance. If two parts of the application need two independent channels, you must declare two separate channel beans.

### Bean Name, Qualifier, and Bean Type

`@Qualifier` helps Spring select the right bean when injecting a dependency, usually combined with type. A qualifier value sometimes matches a bean name, but a qualifier is dependency-selection metadata; it neither creates an alias nor renames the bean.

```java
@Bean
@Qualifier("priorityOrders")
public MessageChannel priorityOrdersChannel() {
    return new DirectChannel();
}
```

When you need to verify exactly which object is injected, inspect bean type, bean name, and qualifier together at the configuration site. Never conclude two beans are the same simply because they share the same type or qualifier.

## 3. Names of IntegrationFlow and Components Created from Flows

An `IntegrationFlow` declares how messages travel through channels and endpoints. When a flow is declared with `@Bean`, the `@Bean` method name becomes the flow's bean name:

```java
@Bean
public IntegrationFlow ordersFlow(OrderHandler orderHandler) {
    return IntegrationFlow.from("ordersInput")
        .handle(orderHandler, "handle")
        .get();
}
```

In this example:

- `ordersFlow` is the bean name of the flow-describing object.
- `ordersInput` is the name of the channel from which the flow receives messages.
- `.handle(...)` declares a processing step; when the flow is processed for runtime registration, Spring Integration creates and manages the corresponding endpoint and handler.
- The endpoint and auxiliary components may receive framework-generated names derived from the flow and DSL structure.

Therefore, do not assume the bean name `ordersFlow` is also the name of the processing endpoint. The flow is the configuration/composition of steps; the endpoint is the runtime component executing a step in the flow.

### Auto-Generated Names vs. Explicitly Assigned Names

With Java DSL, a single flow can create multiple endpoints, channels, or auxiliary components. If no ID is specified, the framework may generate names based on flow information, component type, and the step's position in the structure. Auto-generated names are useful so the runtime can register components without forcing authors to name every step.

However, auto-generated names can change when the flow structure changes, when steps are added/removed, or when a framework version changes its registration scheme. Do not hard-code an auto-generated name string into business code, operational scripts, or dashboards when an explicit ID can be assigned.

When an endpoint needs stable identification, assign an endpoint ID using the mechanism suited to the declaration style. For annotation-based endpoints, you can use `@EndpointId`:

```java
@EndpointId("orders.persist")
@ServiceActivator(inputChannel = "orders.input")
public void persist(Order order) {
    // Persist the order
}
```

For endpoints declared via Java DSL, you can set the ID in the endpoint spec:

```java
@Bean
public IntegrationFlow ordersFlow(OrderHandler handler) {
    return IntegrationFlow.from("orders.input")
        .handle(handler, "handle", endpoint -> endpoint.id("orders.persist"))
        .get();
}
```

Explicit IDs make logs and management information easier to read. Ensure IDs do not collide within the registry scope where they are registered. If a flow has multiple endpoints of the same type, name IDs after their business function or stage, such as `orders.validate`, `orders.persist`, and `orders.publish`.

## 4. Component Name and Managed Name in Spring Integration

Spring Integration distinguishes Spring beans from components that have meaning in the Integration runtime. Many Integration components implement the `NamedComponent` abstraction, allowing queries for details such as component name and component type. This information is helpful when observing channels, endpoints, adapters, or other Integration components.

Conceptually:

- **Component name** identifies an Integration component, such as an endpoint or channel.
- **Component type** describes the kind of component, such as service activator, transformer, or direct channel.
- **Managed name/type** is the identifying information used by the management surface for components that support management, metrics, or statistics. For components implementing `IntegrationManagement`, you can read them via `getManagedName()` and `getManagedType()`.

These names are often linked to bean names or endpoint IDs so operators can locate components easily. However, do not assume every object in the ApplicationContext is a `NamedComponent`, or that every managed name always equals the bean name. An ordinary business bean may not be an Integration component; conversely, a framework-created endpoint may have its own name even though the business handler is a separate bean.

Example illustrating the difference between handler and endpoint:

```text
ApplicationContext
├── orderHandler       -> OrderHandler business object
├── ordersInput        -> DirectChannel
└── ordersFlow         -> IntegrationFlow

Integration runtime
├── ordersInput        -> channel receiving messages
└── orders.persist     -> endpoint invoking orderHandler.handle(...)
```

`orderHandler` is the bean containing business logic. `orders.persist` is the identifier of the endpoint invoking that logic. The two components have a usage relationship, but they are not the same object.

When you need to inspect a component's name and type, use the API exposed by the component, such as `NamedComponent.getComponentName()` and `getComponentType()` if the bean implements that interface. `IntegrationManagement` extends identification for management; for components implementing this interface, you can read `getManagedName()` and `getManagedType()` to see the name/type exposed for management. Values are often configured or derived for metrics convenience, but do not assume every bean in the context implements `IntegrationManagement` or that every managed name always equals the bean name. Do not split framework-generated name strings to guess the component type; use metadata rather than relying on internal string formats.

## 5. Channel Name and Endpoint ID Have Different Roles

A channel is the communication point between steps in a flow. An endpoint is the adapter connecting a channel to a processing, transforming, routing, or sending behavior. Consequently, channel names are typically used to route messages in configuration, whereas endpoint IDs help identify where behavior executes.

```text
orders.input
    |
    v
orders.validate (endpoint)
    |
    v
orders.validated
    |
    v
orders.persist (endpoint)
    |
    v
orders.saved
```

In the diagram, `orders.input`, `orders.validated`, and `orders.saved` are channel names; `orders.validate` and `orders.persist` are endpoint IDs. When a message gets stuck or fails to reach the persistence step, check both the channel holding/delivering the message and the endpoint subscribed to that channel.

If configuration uses channel name strings, verify the channel is actually registered in the ApplicationContext and has the channel type expected by the flow. For example, `DirectChannel` transfers messages via synchronous invocation, whereas `QueueChannel` holds messages for a consumer to receive later. The same channel name configured with a different channel type can change thread boundaries and how exceptions propagate.

Do not use an endpoint ID in place of a channel name in `inputChannel`, or treat a channel name as if it were an endpoint. The two identifiers serve different roles in the flow.

## 6. Identifiers of Dynamically Registered IntegrationFlows

When an application needs to add or remove flows at runtime, `IntegrationFlowContext` provides a mechanism for dynamic flow registration and management. During registration, you can supply an ID to identify the registration:

```java
IntegrationFlowRegistration registration =
    flowContext.registration(dynamicOrdersFlow)
        .id("tenantAOrders")
        .register();

String registrationId = registration.getId();
```

`tenantAOrders` is the ID of the flow registration in `IntegrationFlowContext`. The framework uses this registration to manage the lifecycle of the flow and the components created from it. This ID is not a message ID, not a correlation ID, and not synonymous with the IDs of individual endpoints inside the flow.

When no explicit ID is specified, the registration mechanism can generate a default ID. In systems with many flows created per tenant, customer, or runtime configuration, assign IDs following a convention and ensure uniqueness. Before registering, define the uniqueness scope and the behavior when an ID already exists to avoid colliding with an active flow.

When removing a flow, act through the corresponding registration so the framework stops and releases the components managed by that flow. Do not manually delete individual generated beans of a flow by guessing their names; doing so can leave endpoints, channels, or runtime bindings in an inconsistent state.

## 7. Message ID and Correlation ID Are Not Component Names

As a message moves through a flow, Spring Messaging provides metadata in `MessageHeaders`. Two headers commonly used for tracing are:

- `MessageHeaders.ID`: the identifier of a specific message. It helps distinguish messages in logs and during processing.
- `correlationId`: information linking multiple messages belonging to the same business transaction or processing group. Correlation ID is typically set by the application or a grouping mechanism based on business context.

For example, a single order may produce multiple messages across validation, persistence, and event-publishing steps. Those messages can have different IDs yet share the same correlation ID so the system can observe that they belong to the same workflow.

```text
orders.validate
    | Message ID: M-101, correlationId: ORDER-9001
    v
orders.persist
    | Message ID: M-102, correlationId: ORDER-9001
    v
orders.publish
    | Message ID: M-103, correlationId: ORDER-9001
```

In this example, the endpoint IDs remain `orders.validate`, `orders.persist`, and `orders.publish`. The message ID changes per message; the correlation ID preserves the relationship among messages for the same order. Do not use a message ID as a bean or endpoint name, because messages are created continuously and their lifecycle differs from the ApplicationContext lifecycle.

In systems with an aggregator or resequencer, the correlation strategy also determines which messages belong to the same message group. In that case, correlation ID affects message group assembly and release; it still never alters bean or runtime component names.

## 8. Observing Identifiers at Runtime

When diagnosing, inspect each identifier layer from broad to narrow scope.

### Checking Bean Names and Aliases

You can list bean names in the ApplicationContext and search for beans by type:

```java
String[] beanNames = context.getBeanDefinitionNames();
String[] channelNames = context.getBeanNamesForType(MessageChannel.class);
String[] aliases = context.getAliases("ordersInput");
```

These calls help confirm whether a bean is registered, which names are aliases, and which channels exist by type. For beans created by factories or special registration mechanisms, distinguish the list of bean definitions from already-instantiated singletons in the context; the two concepts do not always share the exact same scope.

### Checking Component Metadata

For beans implementing `NamedComponent`, you can read component name and component type directly from the object:

```java
Object candidate = context.getBean("orders.persist");
if (candidate instanceof NamedComponent named) {
    String componentName = named.getComponentName();
    String componentType = named.getComponentType();
}
```

This snippet illustrates conditional inspection; the bean name used for lookup must still be a name registered in the application's context. Not every endpoint can be looked up by an arbitrary ID if its configuration or registration mechanism does not register it under that name.

### Checking Integration Graph and Management

When Spring Integration's graph observation feature is enabled, the runtime graph can provide a list of nodes, component types, and links between nodes. This is a helpful way to see which channels an endpoint connects to and spot components outside the expected path.

If the application enables `IntegrationGraphServer` or exposes the graph via a management endpoint, use the graph data to cross-check component names and actual topology. Similarly, Integration metrics can attach component metadata to statistical data. Whether the graph or metrics are available depends on management configuration, Actuator, and application version; having a bean name alone does not mean the graph endpoint is enabled.

## 9. Naming Conventions for Operable Flows

Name components based on function and stay consistent across modules:

| Component | Suggested rule | Example |
|---|---|---|
| Channel bean | Name describing data and direction | `orders.input`, `orders.validated` |
| IntegrationFlow bean | Name describing the business flow | `ordersFlow` |
| Endpoint ID | Business domain + action | `orders.validate`, `orders.persist` |
| Dynamic flow registration ID | Tenant/entity name + flow | `tenantAOrders` |
| Handler bean | Business class name per Spring convention | `orderHandler` |
| Correlation ID | Business key used to link messages | `ORDER-9001` |

Practical guidelines:

1. Assign explicit names to channels and endpoints referenced from multiple places or used in dashboards, logs, and alerts.
2. Keep auto-generated names for internal components that do not require stable external references.
3. Avoid assigning the exact same string to multiple different roles if doing so makes logs ambiguous, such as using `orders` for the flow, channel, and endpoint alike.
4. Assign dynamic registration IDs using a unique convention and check for collisions before registering.
5. Do not put sensitive data or personal information into bean names, endpoint IDs, or correlation IDs, as these values may appear in logs and metrics.
6. When renaming a bean or endpoint already referenced by other systems, treat it as a configuration change affecting dependencies, monitoring, and operations.

## 10. Diagnosing Common Identifier Errors

| Symptom | Possible cause | How to check |
|---|---|---|
| `NoSuchBeanDefinitionException` or bean not found by name | Wrong bean name, only another alias exists, configuration not imported, or bean not registered | Check bean definition names, aliases, package scan, and `@Import` configuration. |
| `NoSuchBeanDefinitionException` when referencing a channel | Channel name string does not point to a registered channel bean | Check `MessageChannel` beans and names in `from(...)`, `inputChannel`, or `.channel(...)`. |
| Multiple endpoints have hard-to-read names | Auto-generated names used or flow has many similar steps | Assign explicit IDs to important endpoints and inspect component metadata. |
| Runtime graph lacks expected component | Flow not registered yet, endpoint not started, or graph management disabled | Check startup, endpoint state, flow registration, and graph configuration. |
| Dynamic flow registration fails | Duplicate registration ID or flow produces conflicting components | Check existing IDs and naming rules for dynamic flows. |
| Logs show different message IDs for the same business transaction | Steps create new messages within the same workflow | Use correlation ID to link messages belonging to the same business transaction. |

When reading logs, log endpoint/component name, channel, message ID, and correlation ID together when available. This separates runtime configuration issues from message-specific issues. Avoid logging only a generic string like `orders`, since it is impossible to tell whether it refers to a bean, channel, endpoint, or business entity.

## 11. How to Think When Reading a Message Flow

When examining a flow, answer four questions in order:

1. **Which objects is Spring managing?** Identify bean names, types, and aliases in the ApplicationContext.
2. **Which components is the Integration runtime operating?** Identify channels, endpoints, component names/types, and flow registrations.
3. **How are components connected?** Use the flow topology or runtime graph to locate input channels, output channels, and processing endpoints.
4. **Which message is being processed?** Use message ID and correlation ID to trace individual messages and business message groups.

Once these four layers are distinguished, looking up beans, reading logs, inspecting metrics, and investigating topology become clear. Bean names locate objects in the Spring container; component and endpoint names identify the Integration structure; managed metadata supports operations; and message IDs and correlation IDs trace data moving through the flow.
