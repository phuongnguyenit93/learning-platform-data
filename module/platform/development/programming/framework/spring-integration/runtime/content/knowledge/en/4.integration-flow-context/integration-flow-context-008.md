# Managing Dynamic Flows in Multi-Tenant or Plugin Systems

In **SPRING_INTEGRATION_RUNTIME**, an IntegrationFlow is typically declared as a bean when the application starts. However, some systems only learn the integration configuration after startup: each tenant has its own data source or connection details, a plugin is enabled or disabled via configuration, or a partner only operates for a certain period. In those cases, the application can register and remove an IntegrationFlow right at runtime using **IntegrationFlowContext**.

Managing dynamic flows requires more than a single register() call. The application needs stable flow identifiers, protection against bean name collisions, control over start/stop states, strict tenant data isolation, handling of concurrent configuration updates, and resource release when a tenant or plugin is removed. This article focuses on those decisions, along with how to operate when the application runs across multiple instances.

## 1. When should dynamic flows be used?

Dynamic flows are appropriate when the number or configuration of integrations changes while the application is running. Common scenarios include:

- **Multi-tenant**: each tenant has its own endpoints, credentials, polling schedule, or outbound destination.
- **Plugins**: extension modules can be installed, enabled, paused, or removed without rewriting application-wide configuration.
- **Integration partners**: connections are created only after an administrator registers the partner or completes an onboarding workflow.
- **Devices or connection sessions**: a flow exists only while a device is online or an integration session remains valid.
- **Changing configuration**: endpoints, filters, or processing policies must be replaced according to a new configuration version.

For example, a sales platform has multiple tenants. Tenant A submits orders over HTTP, Tenant B reads orders from SFTP, and Tenant C receives messages from a broker. Tenants may share the same business logic in some steps, while message sources, credentials, and ingestion schedules differ. Creating separate flows lets you manage each connection's lifecycle independently.

Having multiple tenants does not automatically require creating multiple flows. If all tenants use the same protocol, message structure, and processing logic, a single shared flow combined with a router or tenant-routing service is usually simpler and more resource-efficient. Dynamic flows should be chosen when endpoint structures or runtime configurations genuinely differ.

## 2. Comparing static flows, dynamic flows, and a shared router

| Model | Organization | Strengths | Costs and limits |
|---|---|---|---|
| Static flows | Declare IntegrationFlow as beans at startup | Easy to validate configuration, easy to observe, fits a fixed number of flows | Topology changes typically require updating configuration or restarting |
| Dynamic flow per tenant/plugin | Register each flow via IntegrationFlowContext | Independent lifecycle per tenant or plugin; configuration can be built at runtime | More endpoints, channels, and resources; must manage register/remove |
| Shared flow + router | One flow receives messages and routes by tenant or plugin type | Fewer beans and endpoints; easy to scale to many tenants when processing is uniform | Harder to isolate polling schedules, credentials, or differing integration topologies |

A practical selection rule:

- Choose **static flows** when the number of routes is known upfront and rarely changes.
- Choose **dynamic flows** when each tenant/plugin requires its own set of endpoints or resources and an independent lifecycle.
- Choose **a shared router** when tenants differ only in data or minor policies while sharing the same processing structure.
- You can combine them: shared core background flows alongside dynamically registered partner connection adapters.

Dynamic flows solve creating and managing integration structure. They do not automatically provide tenant authorization, configuration storage, leader election, message delivery guarantees, or cross-node state synchronization.

## 3. IntegrationFlowContext and registrations

### 3.1 Role of IntegrationFlowContext

IntegrationFlowContext is the Spring Integration Java DSL API for registering an IntegrationFlow in the ApplicationContext while the application is running. It provides a builder to create registrations, look up registered flows, and remove flows by ID.

Core operations:

1. Build an IntegrationFlow from business configuration.
2. Call flowContext.registration(flow) to begin configuring the registration.
3. Set a unique ID for the flow.
4. Choose whether to auto-start after registration.
5. Optionally enable useFlowIdAsPrefix() to prefix bean names created by the flow.
6. Call register() to register the flow.
7. Use the registration to obtain the input channel, send messages, inspect, or control lifecycle.
8. Use flowContext.remove(id) when removing the flow and the beans registered with it.

A registration represents an IntegrationFlow added to the runtime. The commonly used API type is IntegrationFlowContext.IntegrationFlowRegistration.

### 3.2 Flow IDs must be stable and unique

IDs allow locating the registration and removing the right flow when a tenant/plugin changes state. Construct IDs from entity type and a normalized identifier, for example:

- tenant-acme-orders
- tenant-northwind-sftp
- plugin-inventory-v2
- partner-bank-a-inbound

Never use an arbitrary string from an external request directly as an ID. Validate the tenant/plugin identifier, bound its length, and normalize characters before building the name. If an ID could contain spaces, unwanted separators, or user-controlled data, convert it into a safe slug.

Do not reuse the same ID for two simultaneously existing flows. When replacing a flow, follow a controlled update procedure: stop or redirect the message source, remove the old registration, and then register the new flow; or use a new versioned ID and shift traffic in an explicitly managed step.

### 3.3 useFlowIdAsPrefix avoids bean name collisions

A single flow typically creates many internal beans such as channels, endpoints, handlers, and supporting components. When registering multiple dynamic flows, auto-generated bean names can collide if not differentiated.

useFlowIdAsPrefix() tells Spring Integration to use the flow ID as a prefix for bean names created from the flow. This is a helpful option when an application registers multiple flows with similar structures.

For example, two tenants may share the same transform → handle structure. Prefixing by flow ID gives runtime components of tenant-acme-orders and tenant-northwind-orders separate namespaces.

Prefixing does not replace unique IDs and does not by itself isolate data. It solves bean name collisions inside the ApplicationContext. The application must still route messages to the right tenant and enforce data access controls.

## 4. Example: registering one flow per tenant

Suppose each tenant has its own runtime input channel and invokes the same order-processing service. The tenant ID comes from validated configuration and is attached to the message inside the flow so downstream steps can handle logging, correlation, and authorization checks.

~~~java
public record TenantConfig(String tenantId) {
}

public interface TenantOrderService {
    OrderResult process(String tenantId, Order order);
}

@Service
public class TenantFlowManager {

    private final IntegrationFlowContext flowContext;
    private final TenantOrderService orderService;

    public TenantFlowManager(
            IntegrationFlowContext flowContext,
            TenantOrderService orderService) {
        this.flowContext = flowContext;
        this.orderService = orderService;
    }

    public IntegrationFlowContext.IntegrationFlowRegistration register(
            TenantConfig tenant) {

        String flowId = "tenant-" + tenant.tenantId() + "-orders";

        if (flowContext.getRegistrationById(flowId) != null) {
            throw new IllegalStateException(
                "Flow already registered: " + flowId);
        }

        IntegrationFlow flow = IntegrationFlow
            .from(MessageChannels.direct())
            .enrichHeaders(headers ->
                headers.header("tenantId", tenant.tenantId()))
            .<Order>handle((order, messageHeaders) ->
                orderService.process(tenant.tenantId(), order))
            .get();

        return flowContext.registration(flow)
            .id(flowId)
            .useFlowIdAsPrefix()
            .autoStartup(false)
            .register();
    }
}
~~~

The example omits imports and the application's Order/OrderResult types. The flow uses a DirectChannel as its input channel, attaches tenantId from the validated TenantConfig, and invokes the business service. The tenant ID is never taken from an arbitrary client-supplied header.

You can start the registration once dependent conditions are ready:

~~~java
IntegrationFlowContext.IntegrationFlowRegistration registration =
    tenantFlowManager.register(tenantConfig);

registration.start();
~~~

If the flow begins with a MessageChannel, the registration can provide a MessagingTemplate to send messages into the flow:

~~~java
registration.getMessagingTemplate()
    .send(MessageBuilder.withPayload(order).build());
~~~

Alternatively, the application can obtain the input channel and send a Message directly. Not every flow exposes an input channel for producers; flows starting with an inbound adapter or source have their own ingestion mechanism.

### 4.1 Why attach tenantId inside the flow?

The tenant ID is attached from validated configuration so downstream steps can:

- Emit per-tenant logs and metrics.
- Build tenant-namespaced correlation keys.
- Select appropriate retry or error-handling policies.
- Validate data before invoking repositories or services.
- Route results to the right tenant destination.

Never treat a tenantId header as proof of authorization. A message could originate from an untrusted source. The entry point must determine the tenant from an authenticated identity or a dedicatedly configured adapter before attaching internal headers. Data-access services must still enforce tenant boundaries.

## 5. Managing the tenant lifecycle

A tenant typically moves through several states: unconfigured, configured, activating, running, paused, removing, and removed. The flow manager must map this business state to the registration.

| Tenant state | Expected flow state | Action |
|---|---|---|
| Unconfigured | No registration | Do not create flow |
| Configured | Registered but not yet running, if waiting on conditions | Validate config and register |
| Activating | Registration is being started | Open connections or enable endpoints |
| Running | Registration running | Receive and process messages |
| Paused | Registration stopped | Stop accepting messages, retain registration for restart |
| Removing | Stopping and cleaning up resources | Stop source, drain if needed, remove |
| Removed | No registration left | Delete tenant mappings and resources |

Treat activate/deactivate as an explicit stateful workflow. Do not merely save an enabled boolean in a database and assume the flow was successfully started or stopped.

### 5.1 Activating a tenant

An activation sequence typically includes:

1. Reading tenant configuration from a trusted source.
2. Verifying the tenant is active and the caller is authorized to enable the integration.
3. Validating endpoints, credentials, polling schedule, and processing policies.
4. Building the IntegrationFlow and required components.
5. Registering the flow with a stable ID and useFlowIdAsPrefix().
6. Checking dependencies such as connection factories or remote endpoints.
7. Calling start() once the flow is ready to accept messages.
8. Saving ACTIVE status and the registration ID after the operation succeeds.

If register() succeeds but start() fails, the flow must not be marked ACTIVE. Log the error, stop or remove the registration depending on state, and allow safe activation retries.

### 5.2 Pausing a tenant

Pausing means the tenant stops accepting new work while waiting. If it needs to resume later, keep the registration and use stop()/start() through its lifecycle.

However, stopping the entire registration can stop multiple endpoints in the flow at once. If the requirement is to stop the source from accepting new messages while letting downstream consumers finish draining the backlog, design the source and processing stages with separate lifecycle boundaries. Calling stop() on the whole registration does not by itself guarantee queues have drained.

### 5.3 Removing a tenant

When a tenant is permanently deleted:

1. Prevent new messages from being produced by external sources.
2. Identify queued messages or in-flight tasks.
3. Wait for draining according to the chosen policy and timeout.
4. Stop remaining active endpoints.
5. Call flowContext.remove(flowId) to remove the registration.
6. Close tenant-specific connections, clients, or resources if owned by the application.
7. Remove the tenant → flow ID mapping and references to registrations/channels.
8. Record the removed state.

remove(id) removes the flow from IntegrationFlowContext. If message processing must be guaranteed before removal, design the drain step beforehand; remove is not a promise to finish draining the backlog.

## 6. Managing installable, enableable, and removable plugins

Plugins typically package an isolated integration capability, such as reading data from a warehouse system, receiving partner webhooks, or sending events to an external service. A plugin manager can use IntegrationFlowContext to bring a plugin's flow into the runtime when the plugin is enabled.

A simple plugin contract can provide metadata and a flow factory:

~~~java
public interface IntegrationPlugin {

    String pluginId();

    IntegrationFlow createFlow(PluginRuntimeContext context);
}
~~~

PluginRuntimeContext is an application-defined type holding controlled dependencies such as decrypted credentials, permitted endpoints, business services, or policies. Do not pass the entire ApplicationContext or arbitrary access to a plugin unnecessarily.

The plugin manager registers the flow under a namespaced ID:

~~~java
String flowId = "plugin-" + normalize(plugin.pluginId());

IntegrationFlow flow = plugin.createFlow(pluginRuntimeContext);

IntegrationFlowContext.IntegrationFlowRegistration registration =
    flowContext.registration(flow)
        .id(flowId)
        .useFlowIdAsPrefix()
        .autoStartup(false)
        .register();

registration.start();
~~~

This structure gives each plugin a clear registration. When a plugin is disabled, the manager stops and removes the flow by its corresponding ID.

### 6.1 Plugin resource boundaries

A plugin may create extra resources such as HTTP clients, connections, schedulers, or third-party library handles. Define who owns each resource and who closes it.

- If a resource is a shared application bean, do not close it when removing a single plugin.
- If a resource is created specifically for the plugin, hold a reference in the plugin registration or a resource holder and close it after endpoints have stopped.
- If the plugin spawns its own threads, provide a way to request shutdown and wait for threads to terminate.
- If the plugin creates its own message store or metadata, define a retention policy when the plugin is removed.
- If the plugin is loaded from external code, manage classloaders and dependency lifecycles; removing an IntegrationFlow does not automatically close all plugin classloaders or resources.

### 6.2 Updating a plugin or configuration

When a plugin's configuration changes, avoid mutating a flow concurrently while it processes messages if its endpoints and resources do not support hot reloading.

A replacement workflow might be:

1. Build and validate the new configuration.
2. Register a new flow with a versioned ID, such as plugin-inventory-v2.
3. Start and verify the new flow.
4. Switch message sources or producers to the new flow.
5. Stop the old flow's source and drain in-flight messages.
6. Remove the old flow.
7. Update the plugin → current flow ID mapping.

Exact steps depend on adapter types and traffic-switching capabilities. If two versions cannot run concurrently, allow a controlled pause window and an explicit rollback plan.

## 7. Preventing duplicate registration and handling concurrent operations

A multi-tenant system may receive two requests to activate the same tenant almost simultaneously. If both check the registry before calling register(), both may see that the flow does not exist yet and both attempt to create it.

Checking getRegistrationById() helps detect existing flows, but checking and then registering is not an atomic transaction on its own. Synchronize operations per tenant or use an appropriate locking mechanism.

Options:

- **In-JVM lock**: suitable when only a single process manages that tenant.
- **Database unique constraint**: protects the tenant → flow ID mapping from duplicate writes.
- **Distributed lock or leader election**: used when multiple instances could execute activation concurrently.
- **Idempotency key**: identifies repeated activation requests so extra flows are not created.
- **Versioned state transition**: allows updates only when the current state still matches the version read by the request.

Example of a simple service serializing operations within the same JVM:

~~~java
public synchronized IntegrationFlowContext.IntegrationFlowRegistration activate(
        TenantConfig tenant) {

    String flowId = "tenant-" + tenant.tenantId() + "-orders";

    IntegrationFlowContext.IntegrationFlowRegistration existing =
        flowContext.getRegistrationById(flowId);

    if (existing != null) {
        if (!existing.isRunning()) {
            existing.start();
        }
        return existing;
    }

    IntegrationFlow flow = buildFlow(tenant);

    IntegrationFlowContext.IntegrationFlowRegistration registration =
        flowContext.registration(flow)
            .id(flowId)
            .useFlowIdAsPrefix()
            .autoStartup(false)
            .register();

    registration.start();
    return registration;
}
~~~

synchronized only serializes calls against the same service instance inside one JVM. It does not lock other replicas and does not replace unique constraints or distributed locks when multiple nodes exist.

Also handle cases where register succeeds but writing the database mapping fails, or the database records ACTIVE while start fails. You can use intermediate states like REGISTERING/STARTING and a reconciliation process to compare persisted state against the runtime registry.

## 8. Multi-instance: flow registries are not automatically shared across nodes

IntegrationFlowContext manages flows within the current process's ApplicationContext. When an application runs three replicas, each replica has its own ApplicationContext and registry. Registering a flow on node A does not automatically register that flow on node B.

This creates several scenarios:

- If every node reads the tenant list and registers flows independently, all three nodes may open connections to the same source.
- If only one node is allowed to poll a directory or queue, use leader election, distributed locks, or an appropriate consumer group mechanism.
- If the flow must run on every node to serve local traffic, register on each node and ensure the message source supports multiple consumers.
- When a tenant is disabled, emit an event or update state so all relevant nodes stop and remove the flow.
- When a node restarts, reconcile durable configuration against the newly created runtime registry.

Do not store only a single ACTIVE status in the database and assume all nodes started successfully. Track per-node status or collect activation confirmations from individual nodes when required by the architecture.

~~~mermaid
flowchart TD
    DB["Tenant / plugin configuration"] --> M["Activation coordinator"]
    M --> L{"Leadership / ownership"}
    L -->|Node A| A["ApplicationContext A"]
    L -->|Node B| B["ApplicationContext B"]
    A --> RA["IntegrationFlowContext A"]
    B --> RB["IntegrationFlowContext B"]
    RA --> FA["Dynamic flow A"]
    RB --> FB["Dynamic flow B"]
~~~

The diagram illustrates two deployment models you can choose: only the leader/owner node registers the flow, or multiple nodes register the flow if the architecture requires it. The coordinator decides which nodes are permitted to run; IntegrationFlowContext only manages local registrations.

## 9. Isolating data, credentials, and correlation per tenant

Separate flows do not automatically guarantee data isolation. Tenant boundaries must be enforced at every step that accesses resources.

### 9.1 Tenant identity

Tenant ID must originate from validated configuration or an authenticated identity. Never trust an arbitrary client-supplied tenantId header. At the entry point, resolve the tenant and attach internal metadata for downstream steps.

Every service accessing a database must scope queries by tenant. If using separate connections or schemas, verify the exact credentials/schema bound to that registration.

### 9.2 Credentials and outbound destinations

Never put credentials in flow names, logs, or message headers. Fetch secrets from a secret manager or secure store, supply them only to the adapters/handlers that need them, and close clients when the flow is removed.

When configuring outbound endpoints per tenant, validate permitted hosts, schemes, and network destinations. Accepting a URL from tenant configuration should never automatically allow the application to connect to arbitrary addresses.

### 9.3 Correlation and message stores

When multiple tenants generate messages simultaneously, correlation keys should be namespaced by tenant to avoid merging messages across two tenants. For example, a logical key can combine tenantId + businessCorrelationId.

If using aggregators or message stores, ensure keys and metadata distinguish tenants. When sharing a store, verify how correlation keys and access controls are constructed. When using per-tenant stores, manage store lifecycle and retention when a tenant is deleted.

### 9.4 Error channels and retries

Flow errors must preserve tenant context for proper investigation and handling. Record tenant ID, flow ID, message ID, and correlation ID in logs/metrics. Avoid placing sensitive payloads or credentials into ErrorMessage logs.

Retry policies should match error types and tenant requirements. One tenant experiencing external system failures should not exhaust all workers or starve other tenants. Use separate executors/queues, concurrency limits, or per-tenant circuit breakers when strict load isolation is required.

If using a shared error channel, error messages must retain flow/tenant identifying metadata, and error-handling logic must re-verify authorization before accessing data. For tenants with strict isolation requirements, consider dedicated per-flow or per-adapter error handling.

## 10. Resources and limits as flow counts grow

Each dynamic flow can create channels, endpoints, handler adapters, scheduler tasks, or connections. Therefore, growing tenant/plugin counts increase runtime resource consumption.

Monitor:

- Current registration count and running registration count.
- Endpoints, channels, and adapters created per flow.
- Thread count, executor active count, and queue depth.
- Connections to brokers, databases, HTTP servers, or SFTP.
- Error rates during register/start/stop/remove.
- Activation/deactivation durations and retry counts.
- Orphaned registrations left behind after a tenant/plugin has been deleted.

Do not create a large dedicated thread pool per tenant if flows can use a centrally managed executor. Conversely, if load isolation is needed, set explicit bounds instead of an unbounded pool.

With thousands of tenants sharing the same structure, a shared flow and router are usually easier to operate than thousands of dynamic endpoints. You can group flows by protocol or partner type and route by tenant within each group.

## 11. Testing and observing dynamic flows

Dynamic flows must be tested on both happy paths and failure lifecycles. Key scenarios:

| Scenario | What to verify |
|---|---|
| First-time tenant activation | One registration created, correct ID and running state |
| Repeated activation | No duplicate flow created |
| Two concurrent activation requests | Only one valid registration retained |
| Invalid tenant configuration | No partial registration or dangling resources left behind |
| start failure | State is not mistakenly recorded as ACTIVE |
| Pause and resume | Registration still exists and resumes operating properly |
| Deactivate tenant | Flow is stopped/removed and references are released |
| Two tenants send same correlation ID | Messages are not aggregated together or written across tenants |
| Plugin updated | New flow operates before old flow is removed per procedure |
| Multiple replicas | Only the authorized node opens an exclusive source |

At runtime, you can use IntegrationFlowContext.getRegistry() and getRegistrationById(id) to inspect registrations. Combine with the integration graph, lifecycle logs, and adapter/executor metrics to confirm whether a flow is registered, started, or hitting connection errors.

Fields to include in structured logs:

- Verified tenantId or pluginId.
- flowId and configuration version.
- Operation: register/start/stop/remove.
- Message ID and correlation ID.
- Name of the failing endpoint or adapter.
- Node/process owning the flow.
- Start and end timestamps of the lifecycle operation.

Do not log secrets, tokens, or full sensitive payloads. When a flow is removed, retain necessary audit events for investigation while deleting or masking data according to retention policies.

## 12. Sample operational workflow

A flow manager can be organized into clear business operations:

~~~mermaid
flowchart TD
    A["Receive activate/deactivate request"] --> B["Authenticate tenant/plugin"]
    B --> C["Check state and ownership"]
    C --> D{"Operation"}
    D -->|Activate| E["Validate config and credentials"]
    E --> F["Build IntegrationFlow"]
    F --> G["Register with ID + bean prefix"]
    G --> H["Start and check status"]
    H --> I["Record ACTIVE"]
    D -->|Pause| J["Stop along lifecycle boundaries"]
    J --> K["Keep registration to resume"]
    D -->|Remove| L["Stop ingress and drain"]
    L --> M["Stop and remove registration"]
    M --> N["Close resources, delete mapping"]
~~~

Separate validation, registration, startup, and state persistence into observable and retryable steps. If a step fails, the system must know what state the registration is in so it can continue or roll back. Avoid a long activate method that merely catches exceptions and returns success.

## 13. Pitfalls to avoid

- **IntegrationFlowContext is not a tenant manager**: it registers/removes flows; the application must still manage tenants, permissions, and configuration.
- **Unique ID does not equal data isolation**: IDs and bean prefixes only distinguish runtime components.
- **useFlowIdAsPrefix() does not replace ID**: every flow still needs a stable, non-colliding ID.
- **getRegistrationById() followed by register() is not atomic**: locking or idempotency is needed under concurrent requests.
- **stop() does not equal drain**: you must plan how to handle queued messages and running tasks.
- **remove() does not automatically close all external resources**: the application must manage clients, threads, and plugin-owned resources.
- **The registry is local to an ApplicationContext**: multiple replicas need a separate coordination mechanism.
- **Separate flows do not automatically guarantee tenant security**: tenant identity, repository queries, credentials, and correlation must all be isolated.
- **More flows are not always better**: for large tenant counts with uniform logic, a shared router usually scales better.
- **Recording ACTIVE before start succeeds creates false state**: update status only after verifying the registration is running.

## 14. Self-check

1. When should you create one IntegrationFlow per tenant, and when should you use a shared flow with a router?
2. What problem does useFlowIdAsPrefix() solve? Why is a unique ID still required for each registration?
3. Why is calling getRegistrationById() before register() insufficient to prevent two concurrent activation requests?
4. If a tenant only pauses an integration temporarily, should you keep the registration or remove it? What about when a tenant is permanently deleted?
5. An application runs three replicas. Why does registering a flow on node A not make it appear on node B?
6. How do you ensure identical correlation IDs from two tenants do not cause an aggregator to merge messages across tenants?
7. When a plugin is removed, which resources must be closed beyond removing the IntegrationFlow?
8. Why does calling stop() on the whole registration not necessarily satisfy queue-draining requirements before shutdown?

## Conclusion

IntegrationFlowContext lets an application register and remove flows at runtime, making it well suited for tenants, partners, or plugins with independent configurations and lifecycles. To operate safely, each flow needs a stable ID, its own bean prefix, a stateful activate/deactivate workflow, duplicate-registration protection, and a resource cleanup plan. With multiple replicas, flow ownership must be coordinated at the system level because the registry exists only within each process's ApplicationContext. When tenant counts are high and processing structures are identical, consider a shared flow with a router to reduce endpoint and runtime resource overhead.
