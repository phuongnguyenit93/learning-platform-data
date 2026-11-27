# Avoiding Duplicate Flow Names and Registration Leaks

`IntegrationFlowContext` allows registering and destroying `IntegrationFlow` instances while the application is running. This capability is useful when topologies depend on tenants, runtime configuration, or an integration source toggled on demand. However, each registration creates runtime beans such as endpoints, channels, and handlers. If two flows share bean names, registration can fail; if a flow is no longer needed yet its registration remains in the context, its endpoints and associated resources continue to exist.

To manage dynamic flows safely, you need a unique naming rule, a single owner responsible for registration/unregistration, and a clear cleanup procedure. `IntegrationFlowContext` manages the flow's beans; the application must manage the business lifecycle of the registration, including when it is created, when it stops accepting messages, and when it must be destroyed.

## 1. What does a registration contain?

An `IntegrationFlow` bean describes the topology: inbound source, processing steps, channels, and outbound destination. When the flow is registered, Spring Integration creates or wires the runtime components required for the flow to operate. Depending on the flow, those components may include:

- Consumer endpoints connecting channels to handlers.
- Polling adapters and pollers if the flow reads from a `MessageSource`.
- Channels and components declared inside the DSL.
- Transformers, routers, filters, service activators, or aggregators.
- Adapters, listeners, schedulers, or components with dedicated resources.

`IntegrationFlowContext` provides a builder to register a flow and returns an `IntegrationFlowRegistration`:

```java
IntegrationFlowRegistration registration = flowContext
        .registration(tenantFlow)
        .id("tenant-orders-42")
        .useFlowIdAsPrefix()
        .register();
```

The registration is the handle through which the application accesses and controls the registered flow. From this handle, the application can retrieve the ID, access the input channel or messaging template when supported by the flow, start/stop the flow, and destroy the registration when it is no longer used.

One thing to keep in mind: `IntegrationFlow` is the topology definition; `IntegrationFlowRegistration` represents an active registration of that topology in an application context. Holding the registration reference allows the application to manage its lifecycle explicitly.

## 2. Two types of name collisions to distinguish

A common mistake is checking only the flow ID while overlooking component names inside the flow. There are two distinct identifier layers:

| Name type | Scope | Collision example |
|---|---|---|
| Flow registration ID | Identifies a registration in `IntegrationFlowContext` and the current context | Two requests both register ID `tenant-orders-42` |
| Bean/component name | Identifies runtime beans created for endpoints, channels, or components in the context | Two flows both create a component named `transformer.handler` or both declare an explicit channel bean |

Having different IDs does not necessarily eliminate all collisions. When registering multiple flows with similar DSL structures, DSL-generated components can end up with identical default names. `.useFlowIdAsPrefix()` instructs Spring Integration to use the flow ID as a prefix for bean names created in the flow, giving each flow's internal components their own namespace.

For example, two flows might both contain a transformer created with the same DSL structure. With prefixing enabled, generated bean names for flow `tenant-orders-42` and `tenant-orders-84` are distinguished by their respective IDs.

Prefixing does not replace naming rules for every bean in the application. For channels or components named explicitly, determine whether they are flow-private resources or shared resources. If private, the name must include the flow identifier; if shared, declare and manage the shared bean once in the context. Do not create multiple beans with the same name just because each flow has a different registration ID.

## 3. Designing stable and unique flow IDs

A flow ID should have these characteristics:

- Unique within the scope of the application context managing the registration.
- Stable for the same business entity, so register/unregister operations locate the exact same ID.
- Easy to trace in logs, metrics, and when diagnosing errors.
- Independent of unnormalized input data or values that vary per request.
- Equipped with rules distinguishing environments, tenants, flow types, or versions when those factors produce different topologies.

For example, an ID can be generated from the flow type and a normalized tenant key:

```java
String flowIdFor(String tenantKey) {
    String stableKey = tenantKey.trim().toLowerCase(Locale.ROOT);
    String suffix = UUID.nameUUIDFromBytes(
            stableKey.getBytes(StandardCharsets.UTF_8)).toString();
    return "tenant-orders-" + suffix;
}
```

`UUID.nameUUIDFromBytes` produces a deterministic UUID from the same input string. In real systems, normalize the tenant key according to business rules before generating the ID. If the same tenant can have multiple topology versions running concurrently, include the version or flow type in the identifier. Avoid using a purely random number on each registration request: doing so allows the same tenant to create unbounded registrations without the application being able to look up the old registration.

Never use arbitrary client-supplied strings directly as bean names. Validate length, normalize characters, and restrict the value domain. The ID must reflect the flow's identity within the system, not the raw request content.

## 4. Controlled registration and preventing concurrent duplicates

If multiple requests concurrently ask to enable a flow for a tenant, two execution threads may both check that the flow does not exist yet and both call `register()`. This is a race condition: both see an initial unregistered state.

An application-level registry should be the single place owning registration operations. The registry is responsible for:

1. Generating the flow ID from the business key.
2. Checking existing registrations according to idempotency policy.
3. Registering the flow exactly once.
4. Storing the `IntegrationFlowRegistration` handle after registration succeeds.
5. Using the same ID and the same registry when stopping or destroying the flow.

A simple example using synchronization to ensure register and unregister on the same registry do not overlap:

```java
@Component
class TenantFlowRegistry {

    private final IntegrationFlowContext flowContext;
    private final OrderService orderService;
    private final Map<String, IntegrationFlowRegistration> registrations =
            new HashMap<>();

    TenantFlowRegistry(
            IntegrationFlowContext flowContext,
            OrderService orderService) {
        this.flowContext = flowContext;
        this.orderService = orderService;
    }

    public synchronized IntegrationFlowRegistration register(String tenantKey) {
        String flowId = flowIdFor(tenantKey);
        IntegrationFlowRegistration existing = registrations.get(flowId);
        if (existing != null) {
            return existing;
        }

        IntegrationFlow flow = buildFlow(tenantKey);
        IntegrationFlowRegistration registration = flowContext
                .registration(flow)
                .id(flowId)
                .useFlowIdAsPrefix()
                .register();

        registrations.put(flowId, registration);
        return registration;
    }

    public synchronized void unregister(String tenantKey) {
        String flowId = flowIdFor(tenantKey);
        IntegrationFlowRegistration registration = registrations.get(flowId);
        if (registration != null) {
            try {
                registration.stop();
            }
            finally {
                try {
                    registration.destroy();
                }
                finally {
                    registrations.remove(flowId, registration);
                }
            }
        }
    }

    private IntegrationFlow buildFlow(String tenantKey) {
        return IntegrationFlow
                .from(new DirectChannel())
                .handle((MessageHandler) message ->
                        orderService.accept(tenantKey, message.getPayload()))
                .get();
    }

    private String flowIdFor(String tenantKey) {
        String key = tenantKey.trim().toLowerCase(Locale.ROOT);
        return "tenant-orders-" + UUID.nameUUIDFromBytes(
                key.getBytes(StandardCharsets.UTF_8));
    }
}
```

This is an example of a registry with a single shared synchronization lock, suitable when topology changes are infrequent. If the system registers many tenants in parallel, use per-flow-ID locking or a keyed synchronization mechanism so different tenants do not block each other. Either way, checking, registering, and recording the handle must be atomic with respect to the same ID.

The policy when a flow already exists must be explicitly decided. For an "ensure active" operation, returning the existing registration is usually appropriate. For a "replace topology" operation, stop and destroy the old registration in sequence before registering the new version. Never accidentally treat a duplicate registration as a flow replacement request.

## 5. `useFlowIdAsPrefix()` and explicit component names

`.useFlowIdAsPrefix()` is helpful when flows are built from the same builder function and contain DSL components with auto-generated default names. For example, multiple tenants may share the same pipeline of filter, transformer, and service activator; prefixing keeps internal bean names from colliding.

However, inspect names declared directly in the topology. For example, a flow might receive a channel created and named explicitly at the application level:

```java
MessageChannel tenantInputChannel = createTenantInputChannel(tenantKey);
IntegrationFlow flow = IntegrationFlow.from(tenantInputChannel)
        .handle(orderService, "accept")
        .get();
```

If `tenantInputChannel` is a specifically named channel bean, the registry must ensure that channel is created with a unique name and has a clear lifecycle; `createTenantInputChannel` in the example represents an application factory. If multiple flows reference a shared channel, verify whether sending a message to the channel dispatches to one or multiple subscribers and whether that matches the intended semantics.

For components with explicitly assigned IDs, treat those IDs as part of the naming contract. Flow prefixing should never be used as an excuse to skip checking explicit names, externally referenced channels, or beans shared across flows.

## 6. Distinguishing stop, destroy, and closing the context

Registering a flow creates resources in the context. When a tenant is deleted or a topology is no longer needed, the corresponding registration must be released.

| Operation | Meaning | When to use |
|---|---|---|
| `registration.stop()` | Stops the flow's lifecycle components | Stop accepting new work before draining or replacing topology |
| `registration.destroy()` | Destroys the registration and beans created for the flow | Remove the flow from runtime when no longer used |
| `applicationContext.close()` | Closes the entire context and destroys context-owned beans | When the application or context shuts down |

`stop()` does not delete beans and does not release the entire registration. A stopped flow still occupies space in the context and can be started again. Therefore, if a flow is no longer used, calling only `stop()` leaves behind the registration and its runtime beans.

`destroy()` is the required step to eliminate a dynamic registration. When an orderly shutdown is needed, stop first to stop receiving messages, process the backlog per application policy, and then destroy. Even without a separate drain or stop requirement, ensure `destroy()` is called for registrations that have reached the end of their lifecycle.

Closing the application context triggers lifecycle shutdown and destruction of beans managed by the context. That is the final cleanup mechanism when the application shuts down; it does not replace destroying flows promptly when a tenant or configuration is removed while the application is still running.

## 7. How do registration leaks typically appear?

A forgotten registration can retain far more than a single Java object in a map:

| Symptom | Resources that may still exist | Consequence |
|---|---|---|
| Tenant deleted yet flow still runs | Endpoints, subscribers, and adapters | Messages continue being received or processed for an inactive tenant |
| New ID generated on every configuration update | Old beans, channels, and registrations | Component count grows over time |
| Only `stop()` called | Bean definitions and registrations remain | Cannot re-register the same ID or component names as expected |
| Registration kept in map without cleanup | Handles and flow references | Heap retains objects and corrupts registry state |
| Inbound adapter not stopped | Listeners, pollers, or consumers | Continues receiving messages even though business feature is disabled |
| Dedicated executor or scheduler created without closing | Threads and task queues | Background threads linger, resource usage climbs, and app shutdown stalls |

Leaks can manifest as rising endpoint counts, rising thread counts, abnormal queue backlogs, duplicate message processing, or memory growth correlated with tenant enable/disable cycles. Do not monitor only the registration count in the application's map; also observe endpoint state and resources owned by flows.

## 8. Safe unregister procedure

When a flow is no longer needed, proceed in order:

1. Mark the flow or tenant as transitioning to inactive so new requests do not reactivate the registration.
2. Stop receiving new messages by stopping the registration or appropriate inbound endpoints.
3. Wait for or finish in-flight work within the configured shutdown limit.
4. Destroy the registration to remove runtime beans created by the flow.
5. Remove the handle from the application registry and clear related references.
6. Close dedicated resources created by the application itself, if they are not owned by the Spring Integration registration.

The order of removing the handle and destroying must be protected by the same synchronization mechanism used for registration. Do not allow another request to re-register the same ID while the old registration is still being destroyed. The simple synchronized registry example above holds the lock across the entire operation; high-throughput registries should use per-ID locks or a state machine to enforce the same invariant.

If `stop()` or `destroy()` throws an error, log it with the flow ID and current state. Never silently swallow cleanup errors. You can retain a `CLEANUP_FAILED` state so an administrative task can retry cleanup while preventing a new registration with the same ID until the old state is resolved.

## 9. Avoiding leaks of shared resources

Not every bean used by a flow is exclusively owned by the registration. A flow may reference:

- An executor shared across multiple flows.
- A task scheduler managed by the application context.
- A shared connection factory or client.
- A channel declared at the application level.
- A singleton business service.

When destroying a flow, only resources owned by that flow should be removed. Do not close shared executors, connection factories, or channels if other flows still need them. Separate resources created and managed by the registration from dependencies injected from the context.

If a custom adapter or component spawns threads, listeners, or connections itself, bind their creation and release to that bean's lifecycle. Avoid opening resources per message or holding static references to registrations and contexts.

## 10. Managing errors during flow registration and destruction

Flow registration can fail due to duplicate IDs, duplicate bean names, missing dependencies, or endpoint creation errors. The registry should record the registration in its map only after `.register()` returns successfully. If building the flow creates resources outside Spring before registration, clean up those resources if registration fails.

When replacing a topology, do not destroy the old flow before verifying the new configuration if the system requires continuous availability. You can use versioned IDs to create the new flow, verify operation, switch traffic, and then stop/destroy the old flow. This approach requires an explicit message redirection mechanism and avoiding having two flows unintentionally consume from the same input channel.

Do not use a broad catch block and ignore exceptions from `register()` or `destroy()`. Logs should include the flow ID, masked or normalized tenant key, operation being executed, and root cause. For cleanup retries, ensure destroy calls can be invoked safely based on the registration's actual state.

## 11. Testing duplicates and cleanup

Registry tests should focus on observable behavior:

| Case | Expected outcome to verify |
|---|---|
| Register same tenant twice under ensure policy | Only one registration exists; second call returns the existing handle |
| Two different tenants | Two distinct flow IDs and no component name collisions |
| Two concurrent registration requests for same tenant | Only one registration is created |
| Registration fails | Registry does not store a phantom handle or false active state |
| Unregister tenant | Registration is stopped/destroyed and removed from registry |
| Repeated unregister | Operation has deterministic result, creates no new flow, and does not corrupt registry |
| Destroy one flow | Other flows continue running when sharing context or resources |
| Context closes | Remaining registrations and context-owned resources are released |

In integration tests, verify the flow's input channel or handler before and after unregistration, and confirm endpoints no longer receive messages after destroy. If the flow has dedicated listeners or executors, check lifecycle state and verify threads/resources are released.

## 12. Observing dynamic flow counts and state

A production registry should expose minimal operational visibility:

- Flow ID, flow type, and normalized tenant key.
- Registration, start/stop, and destroy timestamps.
- States such as `REGISTERING`, `ACTIVE`, `STOPPING`, `DESTROYED`, or `CLEANUP_FAILED`.
- Active registration count and registration failure count.
- Cleanup failure count and age of the oldest registration.
- In-flight messages or tasks if endpoints expose suitable metrics.

Set a maximum cap on dynamic flows and a policy for exceeding the limit. If a tenant can create multiple versioned topologies, enforce quotas or prune old versions. An unbounded registry can become a source of leaks even if every individual registration is properly named.

When diagnosing issues, compare the business-expected flow count against actual registrations and runtime endpoints. Check for IDs with no corresponding tenant, registrations that are stopped but not destroyed, components with colliding names, and resources still active after unregistration.

## 13. Design principles

- **One registry owns registration:** never let multiple services call `IntegrationFlowContext.register()` independently for the same flow type without coordination.
- **Business-stable IDs:** the same tenant and topology type produce the same ID; different topology versions have distinct IDs.
- **Enable prefixing for DSL-generated components:** use `.useFlowIdAsPrefix()` when registering multiple flows with similar structures.
- **Assign explicit names intentionally:** private channels and beans must have unique names; shared dependencies must be declared and managed once.
- **Prevent race conditions:** check, register, and unregister operations must be synchronized per flow ID.
- **Distinguish stop and destroy:** stop to pause; destroy to eliminate unused registrations.
- **Clean up handles and resources:** remove the registry entry, close private resources, and preserve shared resources.
- **Monitor cleanup:** logs, metrics, and error states help detect orphaned flows before they accumulate.

Before creating dynamic flows, define who owns registrations, how IDs are generated, which components have explicit names, which resources are shared, and what conditions trigger destruction. When those rules are enforced centrally, `IntegrationFlowContext` can evolve topologies at runtime without producing duplicate flows or leaving orphaned endpoints and resources behind.
