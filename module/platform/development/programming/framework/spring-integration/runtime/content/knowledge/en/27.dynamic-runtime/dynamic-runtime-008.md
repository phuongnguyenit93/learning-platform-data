# Resource Cleanup When Deleting a Tenant in a Dynamic Runtime

In a multi-tenant system, each tenant may be backed by a **dynamically created `IntegrationFlow`** to receive messages, invoke handlers, poll data, retain correlation state, retry, or emit events to external systems. When a tenant is deleted, simply deleting a row from the <code>tenants</code> table is not enough: inbound adapters may still be accepting messages, executors may still have running tasks, delayers may hold upcoming messages, aggregators may still hold pending groups, or a broker connection may still hold open resources.

The topic **"Resource Cleanup When Deleting a Tenant"** belongs to the **Dynamic runtime** chapter of the **SPRING_INTEGRATION_RUNTIME** module. The goal is to design a safe flow-teardown procedure while the application is running, using <code>IntegrationFlowContext</code> together with lifecycles, channels, consumer endpoints, pollers, executors, transactions, retries, message stores, error handling, and correlation.

> **Make this distinction upfront:** <code>IntegrationFlowContext.remove(flowId)</code> or <code>IntegrationFlowRegistration.destroy()</code> removes the dynamically registered flow and the dependent beans owned by that registration. They do **not** decide on their own what to do with unprocessed messages, running transactions, rows in persistent stores, external tasks, or resources shared across multiple tenants.

## 1. Tenant Deleted While Runtime Still Active: What Can Happen?

Suppose tenant <code>T-42</code> has a flow:

~~~text
Tenant inbound adapter
    → tenant.input
    → transformer
    → ExecutorChannel
    → service activator
    → router
    ├─ outbound broker adapter
    └─ tenant audit store
~~~

A tenant deletion command arrives right as the executor is processing the third message in a batch, while a poller is still fetching data and an aggregator is waiting for the final fragment.

If the delete handler simply calls <code>flowContext.remove("tenant.T-42")</code> immediately, the outcome can be:

- The flow is no longer registered, yet a <code>Runnable</code> already handed to the executor still runs to completion.
- Messages are redelivered by the broker after restart and hit a handler that no longer exists.
- Data in <code>MessageGroupStore</code> remains because it lives in JDBC/Redis independently of bean lifecycles.
- Scheduled tasks or HTTP callbacks created by application code still hold references to the tenant's resources.
- A shared connection bean is accidentally closed, halting other tenants' processing.
- The tenant is recreated with the same ID while the old cleanup is still deleting, causing race conditions and losing newly created data.

Therefore, the problem is **not simply calling a destroy API**. It is a process of blocking new work intake, settling already-accepted work, tearing down the right owned resources, and verifying the final state.

~~~mermaid
flowchart TD
    A["Tenant deletion request"] --> B["Mark DELETING durably"]
    B --> C["Block admission / pause new intake"]
    C --> D{"In-flight or pending remaining?"}
    D -->|Yes| E["Drain, complete, or move to quarantine"]
    E --> D
    D -->|No, or handled per policy| F["Stop flow"]
    F --> G["Destroy registration / remove flow"]
    G --> H["Close tenant-owned resources"]
    H --> I["Purge data per retention policy"]
    I --> J["Verify and mark DELETED"]
    D -. "Expired / error" .-> K["Keep DELETING_FAILED state for retry"]
~~~

This diagram shows an **application workflow you must implement**, not a built-in automated feature inside <code>IntegrationFlowContext</code>.

## 2. Inventory Ownership Before Cleaning Up

Before writing a single line of resource-deletion code, determine which components are **owned by the tenant** and which are **shared**. "Uses a resource" does not mean "has the right to close that resource."

| Resource | Typical Ownership Scope | Policy on Tenant Deletion |
|---|---|---|
| Tenant's <code>IntegrationFlowRegistration</code> | Tenant-specific | Stop and then destroy/remove by exact ID |
| Channels/endpoints created with the dynamic flow | Flow-specific | Managed by the registration's lifecycle if registered as dependent beans |
| Shared <code>DirectChannel</code>/<code>PublishSubscribeChannel</code> | Application-wide | Disconnect only the tenant's subscribers/routes; **never** destroy the shared channel |
| Dedicated per-tenant <code>ThreadPoolTaskExecutor</code> | Tenant-specific | Block new tasks, drain/cancel per SLA, shut down once zero owners remain |
| Global executor or <code>TaskScheduler</code> | Shared | Never shut down; cancel only tenant-created tasks/registrations if any |
| Dedicated Kafka/JMS/AMQP listener container | Potentially tenant-specific | Pause/stop only that container; verify ACKs and redelivery |
| Shared connection factory or broker client | Shared | Never close; detach only the tenant's endpoints/consumers |
| <code>MessageGroupStore</code>, <code>JdbcMessageStore</code> | Possibly shared backend partitioned by region/key | Purge **only the right partition** per policy; never wipe the whole table |
| Pending delayer/aggregator messages | Tenant-specific data | Choose completion, audited cancellation, or quarantine |
| Retry queues, DLQs, outbox/inbox, and error records | Usually in persistent stores/brokers | Apply retention, idempotency, and data-preservation policies |
| Tenant credentials/secrets, file watchers, custom timers | Tenant-specific | Revoke/close once no in-flight work needs them |
| Metrics, subscriptions, callbacks, caches | Depends on how registered | Unregister listeners/registrations and tenant-scoped cache keys |

**Ownership rule:** Whatever creates a resource must explicitly specify who owns closing it, when closing is permitted, and what happens if cleanup fails. A singleton injected into many flows does **not** become a tenant-owned resource simply because a flow uses it.

## 3. Dynamic Flow Removal APIs: `stop`, `destroy`, and `remove`

Spring Integration provides <code>org.springframework.integration.dsl.context.IntegrationFlowContext</code> to create and manage flows at runtime. A registered flow returns an <code>IntegrationFlowContext.IntegrationFlowRegistration</code>.

| API | Purpose | Limitations |
|---|---|---|
| <code>flowContext.registration(flow)</code> | Creates a builder to register a flow | Not registered until <code>register()</code> |
| <code>.id(flowId)</code> | Attaches an explicit ID for management, avoiding random names | ID must be unique within the context |
| <code>.useFlowIdAsPrefix()</code> | Prefixes the flow's bean names, reducing collisions across similar flows | Requires <code>.id(...)</code> to be set first |
| <code>.autoStartup(false)</code> | Registers without auto-starting | Application must call <code>registration.start()</code> |
| <code>registration.start()</code> | Starts the flow's lifecycle components | Does not reopen data/configs already deleted from DB |
| <code>registration.stop()</code> | Stops the flow's lifecycle | Does **not wait for all in-flight tasks to finish** by default |
| <code>registration.destroy()</code> | Destroys the flow and dependent beans managed by the registration, clearing the internal registry | Does not delete persistent message data or external resources outside its ownership |
| <code>flowContext.remove(flowId)</code> | Destroys the registration by ID and clears context caches | Same behavioral family as <code>destroy()</code>; no need to call both |
| <code>flowContext.getRegistrationById(flowId)</code> | Looks up an existing dynamic registration | Returns <code>null</code> after cleanup or after a restart before rebuilding |

Dependent beans registered via the builder's <code>addBean(...)</code> are also within the registration's destruction scope. Never pass a **shared** singleton into <code>addBean(...)</code> merely for lookup convenience, unless you want that resource destroyed alongside a single tenant's flow.

Spring Integration documentation recommends specifying an **explicit flow ID**. For flows containing components with the same internal IDs, <code>useFlowIdAsPrefix()</code> prevents bean name collisions. This section refers to 6.x APIs; check your actual dependency version when using advanced methods.

### How Does `stop` Differ From `destroy`?

~~~text
RUNNING
  ├─ registration.stop()    → STOPPED (definition/registration retained)
  │                           registration.start() can run it again
  └─ registration.destroy() → no registration remains in context
                              to run again, a new flow must be built and registered
~~~

Use `stop` to pause temporarily, adjust configuration, or transition state before draining. Use `destroy`/`remove` when the flow **must no longer exist** in the context. Never use <code>remove()</code> as a "pause," because recreating the flow can generate new bean/resource names or re-register subscriptions.

## 4. Java DSL Example: Registering an `IntegrationFlow` Per Tenant

Java 17+ and Spring Integration 6.x example: the application creates a flow receiving messages over a dedicated <code>DirectChannel</code>, invokes a **shared** service with tenant validation, and ends. This is a minimal model highlighting **flow-owned** vs. **shared** resources.

**Step 1 — define the command and shared service:**

~~~java
public record TenantEvent(
        UUID tenantId,
        String eventId,
        String payload) {}

@Service
public class TenantBusinessService {
    public void process(TenantEvent event) {
        // Verify tenant is still ACTIVE against durable state;
        // write to DB idempotently by (tenantId, eventId).
        // Actual business logic must not be assumed managed by Spring Integration.
    }
}
~~~

<code>eventId</code> is the idempotency key for **one action**; <code>tenantId</code> is the partition/ownership key. Never substitute <code>MessageHeaders.ID</code> for the business event ID, because redelivery can mint a new message ID.

**Step 2 — build the flow and register with a stable ID:**

~~~java
@Component
public class TenantFlowFactory {
    private final IntegrationFlowContext flowContext;
    private final TenantBusinessService businessService;

    public TenantFlowFactory(IntegrationFlowContext flowContext,
                             TenantBusinessService businessService) {
        this.flowContext = flowContext;
        this.businessService = businessService;
    }

    public String flowId(UUID tenantId) {
        return "tenant.flow." + tenantId;
    }

    public IntegrationFlowContext.IntegrationFlowRegistration create(
            UUID tenantId) {
        String id = flowId(tenantId);
        if (flowContext.getRegistrationById(id) != null) {
            throw new IllegalStateException("Flow already exists: " + id);
        }

        GenericHandler<TenantEvent> handler = (event, headers) -> {
            if (!tenantId.equals(event.tenantId())) {
                throw new IllegalArgumentException("Wrong tenant message");
            }
            businessService.process(event);
            return null; // One-way handler; sends no reply.
        };

        IntegrationFlow flow = IntegrationFlow
            .from(new DirectChannel())
            .handle(handler)
            .get();

        var registration = flowContext.registration(flow)
            .id(id)
            .useFlowIdAsPrefix()
            .autoStartup(false)
            .register();

        registration.start(); // Only after appropriate state/routing is registered.
        return registration;
    }
}
~~~

Key imports: <code>java.util.UUID</code>, <code>org.springframework.integration.dsl.IntegrationFlow</code>, <code>org.springframework.integration.dsl.context.IntegrationFlowContext</code>, <code>org.springframework.integration.handler.GenericHandler</code>, <code>org.springframework.integration.channel.DirectChannel</code>, and <code>org.springframework.stereotype.Component</code>/<code>Service</code>.

In this example, <code>TenantBusinessService</code> is a shared bean in the Spring context. **Never destroy that service** when deleting a tenant flow. A fresh <code>DirectChannel</code> is created per flow; each flow's endpoint binds to its own channel. Two tenants can share service code without sharing an input channel.

This example illustrates the registration API. In production, checking <code>getRegistrationById()</code> followed by <code>register()</code> must have **application-layer synchronization for create/delete**; that pair of calls is not an atomic multi-node transaction. Also, start the flow only after the tenant state is ready to accept messages.

### Sending Messages to the Right Flow

~~~java
UUID tenantId = UUID.fromString(
    "a9a67cb0-ec34-4f6d-9fab-d35464a55c3b");
String id = tenantFlowFactory.flowId(tenantId);

// Send only after confirming tenant is still ACTIVE and allowed to receive.
var registration = flowContext.getRegistrationById(id);
if (registration == null) {
    throw new IllegalStateException("Tenant flow unavailable");
}

Message<TenantEvent> event = MessageBuilder
    .withPayload(new TenantEvent(tenantId, "event-1001", "data"))
    .setHeader("tenantId", tenantId.toString())
    .setHeader("correlationId", "request-1001")
    .build();

registration.getInputChannel().send(event);
~~~

<code>MessageBuilder</code> lives in <code>org.springframework.integration.support</code>. Obtaining the registration successfully **does not stop** another cleanup thread from destroying the flow immediately afterward. Therefore, in real applications, all send paths should pass through a tenant-synchronized **admission gate** instead of letting callers send freely via cached channel references.

## 5. State Machine for Tenant Deletion

A single <code>DELETED</code> status is not enough to represent a multi-step cleanup that can fail partway through. A suggested state machine:

~~~mermaid
stateDiagram-v2
    [*] --> ACTIVE
    ACTIVE --> DELETING: delete command + CAS/version
    DELETING --> DRAINING: ingress blocked successfully
    DRAINING --> QUIESCED: in-flight=0 or quarantined
    QUIESCED --> UNREGISTERED: stop + destroy flow
    UNREGISTERED --> CLEANING_DATA: reclaim dedicated resources
    CLEANING_DATA --> DELETED: postconditions verified
    DELETING --> CLEANUP_FAILED: error
    DRAINING --> CLEANUP_FAILED: timeout / error
    QUIESCED --> CLEANUP_FAILED: error
    UNREGISTERED --> CLEANUP_FAILED: error
    CLEANING_DATA --> CLEANUP_FAILED: error
    CLEANUP_FAILED --> DELETING: checkpointed retry
~~~

State names are an **application contract**, not states built into Spring Integration. Persist <code>tenantId</code>, <code>deletionRequestId</code>, <code>generation</code>, current phase, timestamps, last error, and completed checkpoints durably. If one pod dies mid-cleanup, another pod can resume cleanup from this state.

### Why Not Mark `DELETED` First and Clean Up Later?

If you mark a tenant deleted before resources actually stop accepting messages, background paths may keep updating the database or calling external systems for an invalid tenant. Conversely, waiting for all infrastructure cleanup **inside one long database transaction** holds DB locks too long and still cannot atomically span external brokers/APIs.

The standard solution is a short transaction transitioning <code>ACTIVE → DELETING</code>, followed by asynchronous, idempotent, checkpointed cleanup steps. The delete API returns an "in progress" status if full cleanup cannot finish within a normal HTTP request.

## 6. Step 1 — Block New Message Intake (Quiesce Ingress)

This is the **most critical step** so draining has a finite end. If consumers keep receiving new messages, in-flight counts may never reach zero.

An **admission gate** is an application-enforced check before messages enter the flow:

~~~text
Incoming request / broker delivery
   → check tenantId + generation + tenant state
   → ACTIVE?  ── Yes ──> submit to tenant flow
        │
        No
        ↓
   reject / NACK / quarantine per source type
~~~

A check like <code>if (tenant.isActive()) send(message)</code> is insufficient if deletion can happen between the two lines. Within one JVM, use a read/write lock or serialize admission and mark-deleting. Across multiple pods, use **durable versioned/CAS state**, partition ownership, or shared coordination. Local <code>synchronized</code> cannot block producers on another JVM.

| Input Source | Appropriate Quiesce Mechanism | Caution |
|---|---|---|
| Shared multi-tenant HTTP/gateway | Router blocks tenants in DELETING before calling dynamic flow | Do not shut down the shared gateway |
| Dedicated per-tenant Kafka/JMS/AMQP container | Pause/stop that container or unsubscribe listener cleanly | ACK, redelivery, requeue, and partition ownership depend on the adapter |
| Dedicated per-tenant polling inbound adapter | Stop new polls on that endpoint | Tasks that already pulled messages may still be running |
| Shared input channel with tenant router | Block routes to that tenant while keeping paths open for other tenants | Never remove the shared channel bean |
| Custom schedulers/callbacks | Cancel future schedules; reject new callbacks by generation | Already-started callbacks may still run |

Do not rely on <code>registration.stop()</code> as the **sole step** to halt all ingress; it does not replace tenant checks at shared sources or external APIs calling services directly. Decisions for messages arriving after DELETING must be explicit: reject, ACK and validly skip, NACK/redeliver, or send to DLQ/quarantine. Never ACK "processed successfully" for a business message that must still be preserved.

## 7. Step 2 — Drain In-Flight Work and Handle Pending Messages

Once zero **new work is being admitted**, handle work already accepted prior to deletion.

| Work State | Options | What Must Be Recorded |
|---|---|---|
| Synchronous handler running | Let finish or apply controlled timeout/cancel | In-flight count, transaction outcome |
| Tasks handed to executor | Wait for queue/tasks to finish or move to quarantine | <code>send()</code> succeeding does not mean the task finished |
| In-memory <code>QueueChannel</code> | Drain before shutdown, or accept loss if policy allows | No persistence across restarts |
| Queue backed by <code>JdbcChannelMessageStore</code> | Drain/move via queue APIs and transactions | Never raw-DELETE rows while consumers still poll |
| Delayer holding future messages | Audited cancel, intentional early release, or move to durable store | <code>messageGroupId</code>, scheduled time, deadline |
| Aggregator/resequencer holding pending groups | Wait for remaining parts, force complete, or quarantine fragments | Correlation key, partial/discard policy, group status |
| Waiting retry/backoff | Finish or block new attempts per tenant state | Never re-execute after DELETED |
| DLQ/error messages/outbox | Retain per retention policy or run recovery | Do not delete permanently by default |

**"Drained" must be measured by actual completion**, such as handler exit, ACKs, and transaction commits. Counting `send()` returns is meaningless when flows use <code>ExecutorChannel</code> or reactive consumers.

### Timeout Is a Business Decision, Not "Drained"

If the wait budget expires, three common options exist:

1. **Keep waiting and leave the tenant in DELETING/DRAINING**; suitable for critical work that cannot be dropped.
2. **Move pending work to durable quarantine/DLQ**, recording full correlation, reason, and replay owner; proceed with cleanup only after the move succeeds.
3. **Cancel work per approved policy**, log an audit entry, and never assume external resources rolled back.

Never set <code>inFlight=0</code> by resetting a counter just to pass a drain check. Distinguish active handlers, scheduled tasks, broker deliveries, and persisted data awaiting consumers.

## 8. Step 3 — Stop and Destroy the Right Flow Without Over-Deleting

Only after admission is closed and in-flight work has finished or transitioned to proper recovery should you stop and remove the flow.

~~~java
public void unregisterTenantFlow(UUID tenantId) {
    String id = tenantFlowFactory.flowId(tenantId);

    var registration = flowContext.getRegistrationById(id);
    if (registration == null) {
        // May already be destroyed or not rebuilt after a restart.
        return;
    }

    registration.stop();
    registration.destroy();
    // Do not also call flowContext.remove(id) for the same registration.
}
~~~

This is the **final step** of cleanup, not the entire cleanup. Elsewhere, an application may use <code>flowContext.remove(id)</code> as an equivalent removal path; choose **one** destruction path per ID and stay consistent on retries.

When a tenant has multiple flows (inbound, outbound, scheduler, error processing), maintain a business registry listing **all flow IDs** by tenant/generation and tear them down in dependency order. Never match bean names via loose string checks like <code>startsWith(tenantId)</code> to bulk-destroy when namespaces aren't strictly controlled.

### Why Prefix Flow IDs?

Multiple tenants can share the same structure:

~~~text
tenant.flow.A1.handler
tenant.flow.A1.channel
tenant.flow.B2.handler
tenant.flow.B2.channel
~~~

<code>.id(id).useFlowIdAsPrefix()</code> ensures beans generated by dynamic flows get distinct names when internal endpoints use similar names. However, **globally declared** beans retain independent lifecycles. Never conclude from a name prefix that every bean containing that prefix is safe to delete.

## 9. Step 4 — Clean Up Resources by Ownership, Not by Reference Location

Application-created resources need explicit **cleanup hooks**, for example:

~~~java
public interface TenantResourceLease extends AutoCloseable {
    UUID tenantId();
    String resourceName();
    @Override void close() throws Exception;
}
~~~

An application-built <code>TenantResourceRegistry</code> can store tenant-specific leases, track owners, and ensure each lease closes only once per policy. When destroying a flow, close only leases actually created for that tenant.

**Key distinctions:**

- If a tenant-dedicated connection factory was registered via builder <code>.addBean(...)</code> as a dependent bean, its bean lifecycle may already be handled during registration destruction. Do not both register it as dependent and manually <code>close()</code> it twice if the library does not support idempotent close.
- If using an app-wide singleton connection pool or shared scheduler, **never** put it into the tenant's cleanup registry.
- If the application created <code>ScheduledFuture</code>s, Reactor <code>Disposable</code>s, dedicated threads, or callback registrations outside dependent beans, cancel those handles explicitly.
- If using dynamic broker listeners/consumers, verify the listener actually unregistered or unsubscribed via the adapter/container API, rather than merely dropping Java references.

A good practice is building a table of **resource → owner → create action → close action → postcondition** right when provisioning a tenant. Deletion cleanup simply runs the pre-defined actions rather than scanning the entire Spring context to guess.

## 10. Step 5 — Pending Groups, Message Stores, and Retries After the Flow Vanishes

<code>IntegrationFlowContext.remove()</code> is **not** a command that wipes all tenant data. Persistent state can still reside in:

- <code>JdbcMessageStore</code>/<code>MessageGroupStore</code> for aggregators, resequencers, delayers;
- <code>JdbcChannelMessageStore</code> for queues;
- Redis/MongoDB stores and delayed/scheduled messages;
- broker topics/queues, consumer offsets, retry topics, DLQs;
- outbox, inbox, audit events, and idempotency tables.

**Never raw-DELETE records in <code>INT_MESSAGE</code>/<code>INT_MESSAGE_GROUP</code> using <code>LIKE '%tenant%'</code>**. Store schemas, group relationships, locks, and transactions can cause raw row deletion to lose work or break running consumers.

### Designing Keys and Regions for Surgical Cleanup

When creating dynamic flows, use stable namespaces by tenant and generation:

~~~text
flowId          = tenant.flow.<tenantUUID>.<generation>
delayGroupId    = tenant.delay.<tenantUUID>.<generation>
aggregateRegion = tenant.aggregate.<tenantUUID>.<generation>
correlationKey  = <tenantUUID>:<batchId>
retryKey        = <tenantUUID>:<businessEventId>
~~~

These are **application conventions**, not mandatory Spring Integration naming rules. With a shared <code>MessageGroupStore</code>, regions/partitions must be properly supported by the implementation and used consistently with correlating handlers. Never merely attach <code>tenantId</code> to a header and assume the store has a safe "delete all messages for tenant" API.

**When can data be deleted?** Only after no consumer or producer can write to that partition anymore, pending messages have been settled, and retention/audit rules are satisfied. The actual operation must use APIs, transactions, or migration/purge jobs suited to that specific store—not merely bean destruction.

### Shared Error Flows Are a Trap

A global <code>errorChannel</code> can still receive errors from running tasks or adapters after a tenant flow is deleted. Error consumers must check <code>tenantId</code>, <code>generation</code>, and tenant state:

- Never re-initialize a deleted flow just because a late retry exception arrives.
- Never reuse credentials of a revoked tenant.
- Never treat an <code>ErrorMessage</code> as proof that work rolled back or persisted safely.
- Retain correlation and failed/original message metadata at permitted levels for investigation.

## 11. Transactions and End-to-End Consistency of Cleanup

Deleting a tenant spans multiple systems: business databases, the Spring application context, brokers, message stores, schedulers, secret managers, and object storage. **A single JDBC transaction cannot atomically span all of those** without specialized distributed transaction architecture.

A safe design pattern:

1. In a **short transaction**, CAS <code>ACTIVE → DELETING</code>, insert the deletion job, and emit an outbox event.
2. A worker claims the job and executes each idempotent cleanup step.
3. After each successful step, write a durable checkpoint.
4. If any step fails, leave the job retryable with backoff; never silently reset the tenant back to ACTIVE.
5. Mark <code>DELETED</code> only after postconditions are verified.

~~~mermaid
sequenceDiagram
    participant API as Tenant API
    participant DB as Tenant lifecycle DB
    participant W as Cleanup worker
    participant SI as IntegrationFlowContext
    participant EXT as Store / Broker / Resources
    API->>DB: CAS ACTIVE → DELETING + create job
    DB-->>API: accepted + deletionRequestId
    W->>DB: claim job by tenant/generation
    W->>EXT: block ingress and drain
    EXT-->>W: drained / archived
    W->>SI: registration.stop() / destroy()
    SI-->>W: flow unregistered
    W->>EXT: clean up tenant-owned resources
    EXT-->>W: cleanup result
    W->>DB: checkpoint + DELETED when ready
~~~

**Never wrap all of the above in one <code>@Transactional</code> method and hold the transaction open while waiting on executors or brokers.** Doing so holds DB locks unnecessarily while still providing no atomic rollback for external resources.

## 12. Race Condition When a Tenant Is Deleted and Recreated

A tricky edge case:

~~~text
T1: cleanup for tenant A, generation=7 begins
T2: request to recreate tenant A is accepted, generation=8
T1: slow cleanup runs DELETE by tenantId
T3: generation=8's resources are accidentally deleted
~~~

Prevention:

- Include **deletion generation/version** in jobs and resource names, not just tenant ID.
- Cleanup operations must check owner/generation before deleting.
- Explicitly **forbid recreating the same tenant ID** until old cleanup completes, or assign a fresh ID/generation with strict resource isolation.
- Serialize provision/delete per tenant using CAS and, across multiple nodes, appropriate distributed coordination.
- After crashes/restarts, cleanup workers must resume only on the exact generation—never infer by the tenant's current name.

<code>LockRegistry</code> can provide mutual exclusion when multiple workers clean up a tenant, but **does not replace DB CAS/versioning**: if a lease expires or a stale worker runs, generation predicates on target resources remain essential.

## 13. Application Restart Mid-Cleanup

Dynamic registrations live inside one process's application context; they are not runtime configurations automatically restored intact by Spring Integration from a database after a JVM restart. The application must keep a **persistent configuration source** to rebuild flows still permitted to run.

On startup, an application reconciler should:

| Tenant/Job State in DB | Startup Behavior |
|---|---|
| <code>ACTIVE</code> | Rebuild the flow from saved config, check for ID collisions, then start |
| <code>DELETING</code>/<code>DRAINING</code> | **Do not** accept new messages; resume cleanup/recovery job |
| <code>CLEANUP_FAILED</code> | Retry conditionally or escalate to operators; never auto-start as ACTIVE |
| <code>DELETED</code> | Do not rebuild flow; check for leaked resources per retention policy |

Startup order matters: you may need to open channels/flows with <code>autoStartup(false)</code>, load configuration, verify tenant state, and only then allow adapters/gateways to accept messages. If adapters start before the admission gate, messages for a deleting tenant can slip into a new flow.

For messages still sitting in persistent stores, decide explicitly whether to resume processing just to drain/quarantine them. **Never automatically resurrect a deleted tenant's flow** solely to "flush it clean," as that can trigger side effects and revoked credentials.

## 14. Checkpointed Cleanup Orchestrator Example

The code below is an **integration skeleton with application ports**. It demonstrates the proper ordering; the interfaces <code>TenantLifecycleRepository</code>, <code>TenantIngressController</code>, <code>TenantWorkDrain</code>, <code>TenantPendingWorkPolicy</code>, and <code>TenantOwnedResources</code> are application contracts **you must implement**, not built-in Spring Integration APIs.

~~~java
@Service
public class TenantCleanupCoordinator {
    private final TenantLifecycleRepository lifecycle;
    private final TenantIngressController ingress;
    private final TenantWorkDrain drain;
    private final TenantPendingWorkPolicy pending;
    private final TenantFlowFactory factory;
    private final IntegrationFlowContext flowContext;
    private final TenantOwnedResources ownedResources;

    public TenantCleanupCoordinator(
            TenantLifecycleRepository lifecycle,
            TenantIngressController ingress,
            TenantWorkDrain drain,
            TenantPendingWorkPolicy pending,
            TenantFlowFactory factory,
            IntegrationFlowContext flowContext,
            TenantOwnedResources ownedResources) {
        this.lifecycle = lifecycle;
        this.ingress = ingress;
        this.drain = drain;
        this.pending = pending;
        this.factory = factory;
        this.flowContext = flowContext;
        this.ownedResources = ownedResources;
    }

    public void cleanup(UUID tenantId, long generation) {
        // CAS/idempotency in DB: do not run if generation has changed.
        lifecycle.ensureDeleting(tenantId, generation);

        ingress.blockNewMessages(tenantId, generation);
        lifecycle.checkpoint(tenantId, generation, "INGRESS_BLOCKED");

        // Must count handler completions, not successful send() calls.
        drain.awaitQuiescence(tenantId, generation, Duration.ofSeconds(30));

        // Business policy: process, archive, or quarantine pending work.
        pending.settleAndVerify(tenantId, generation);
        lifecycle.checkpoint(tenantId, generation, "QUIESCED");

        var registration =
            flowContext.getRegistrationById(factory.flowId(tenantId));
        if (registration != null) {
            registration.stop();
            registration.destroy();
        }
        lifecycle.checkpoint(tenantId, generation, "FLOW_REMOVED");

        ownedResources.closeTenantOnly(tenantId, generation);
        lifecycle.checkpoint(tenantId, generation, "RESOURCES_CLOSED");

        lifecycle.markDeletedIfComplete(tenantId, generation);
    }
}
~~~

<code>Duration</code> is from <code>java.time</code>. In production, the same flow ID might be reused when generations advance, so **if recreating the same tenant is allowed**, <code>flowId</code> must incorporate the generation or cleanup must verify the registration matches the right generation before destroying it. The snippet above assumes a tenant ID cannot be recreated until old cleanup completes.

To make the workflow genuinely idempotent, every port must handle "step already completed," crash retries, and already-absent resources cleanly. <code>awaitQuiescence()</code> can throw on timeout; when it does, the worker records <code>CLEANUP_FAILED</code>/checkpoint and never transitions to <code>DELETED</code>.

## 15. Diagnosing Resource Leaks and Verifying Cleanup

Never conclude cleanup succeeded merely because <code>getRegistrationById(id) == null</code>. A flow can be unregistered from the context while tasks, threads, connections, or messages remain lingering.

| Symptom | Hypothesis | Evidence to Collect |
|---|---|---|
| Flow is gone yet CPU keeps rising | Custom scheduler/executor or submitted tasks never stopped | Thread dumps, executor active/queue counts, scheduled handles |
| Deleted tenant still receives messages | Ingress gate missing on one pod, broker redelivery, old callbacks | Tenant state/generation logs, consumer offsets, adapter lifecycles |
| Other tenants disrupted after cleanup | Shared connection factory/scheduler/channel was closed | Ownership map, bean lifecycle logs, health of other tenants |
| JDBC store still holds old messages | Persistent store is not cleared by `destroy` | Regions, group IDs, pending/quarantine metrics |
| Duplicate business side effects occur | Post-crash retries, missing idempotency, drain counted only `send` | Event IDs, transaction logs, outbox/inbox |
| Cannot register new flow with same name | Old registration not destroyed or bean ID collision | <code>getRegistry()</code>, active IDs/prefixes |
| Delete API hangs | Waiting forever on in-flight work, deadlocks, unfinished broker ACKs | Deadlines, lock waits, handler stacks, queue depths |
| Cleanup runs twice across cluster | Missing claim/CAS or distributed lock lease expired | Job owner, generation, transaction/version |
| Messages delivered to wrong tenant | Router or cached input channel pointed to wrong flow | Routing keys, per-tenant registration IDs, handler validation |

Minimum metrics to track:

- tenant counts by state: <code>ACTIVE/DELETING/CLEANUP_FAILED/DELETED</code>;
- registered dynamic flow count vs. ACTIVE tenant count;
- in-flight handlers, queue depths, delayed messages, pending groups, and retry counts per tenant **with bounded cardinality**;
- drain durations, flow removal durations, cleanup error counts by step;
- executor active threads, scheduled task counts, connection/session counts before and after deletion;
- messages arriving with already-revoked generations.

Never attach raw high-cardinality tenant IDs or sensitive data directly to every metric label. Put tenant IDs in access-controlled traces/logs for diagnostics while aggregating metrics by resource type, cleanup step, or tenant tier.

## 16. Testing Tenant Deletion While Messages Are Flowing

Test suites must simulate **true async boundaries**, not just call <code>registration.destroy()</code> and check the context.

| Scenario | What Must Be Verified |
|---|---|
| Tenant with zero messages | Flow removed, dedicated resources closed, other tenants keep running |
| Synchronous handler running | Admission closes; accepted work finishes or follows timeout policy |
| Tasks inside <code>ExecutorChannel</code> | Draining verified by actual completion, not <code>send()</code> |
| Persistent queue/message store | Pending work settled/quarantined; no untransectional bulk deletes |
| Delayer holding scheduled messages | Zero side effects for deleted tenant appear after deadline |
| Aggregator holding pending groups | Groups force-completed, archived, or retained per chosen policy |
| Broker redelivery after `markDeleting` | Adapters/routers apply policy properly without invalid processing |
| Cleanup fails closing a resource | Checkpoint preserved; retry never closes shared singletons |
| Two delete commands for same tenant | Single cleanup owner; subsequent calls observe same state/job |
| Concurrent delete and provision | New-generation flows never destroyed by old cleanup |
| JVM restart mid-cleanup | Reconciler skips rebuilding DELETING tenants and resumes cleanup job |
| Other tenants sharing scheduler/connection | Other tenants never stop or lose connectivity |

### Integration Test Sketch for the `remove` API

~~~java
@Test
void dynamicFlowCanBeRemovedWithoutTouchingAnotherTenant() {
    UUID tenantA = UUID.randomUUID();
    UUID tenantB = UUID.randomUUID();

    var a = tenantFlowFactory.create(tenantA);
    var b = tenantFlowFactory.create(tenantB);

    assertNotNull(flowContext.getRegistrationById(a.getId()));
    assertNotNull(flowContext.getRegistrationById(b.getId()));

    a.stop();
    a.destroy();

    assertNull(flowContext.getRegistrationById(a.getId()));
    assertNotNull(flowContext.getRegistrationById(b.getId()));

    b.destroy();
}
~~~

This test only proves basic lifecycle APIs inside **one application context**. It does not prove admission/transactions, executor draining, durable data cleanup, or cluster safety. Those require dedicated integration tests with real brokers/databases or Testcontainers, latches/timeouts to pin in-flight work, failure injection, and post-restart state verification.

## 17. Production Checklist When Deleting a Tenant

- [ ] Durable <code>DELETING</code> state and idempotent deletion jobs tagged with tenant generation/version.
- [ ] Ingress blocked across **all entry points**, including shared HTTP/routers, brokers, pollers, and custom callbacks.
- [ ] Drained criteria defined by **completion/ACK/commit**, not just <code>send()</code> return counts.
- [ ] Predefined disposition for queues, delayed messages, pending groups, retries, DLQs, outboxes, and audits per retention policy.
- [ ] Call <code>registration.stop()</code> then <code>destroy()</code> or <code>flowContext.remove(id)</code> on the exact target; never double-destroy.
- [ ] Stable flow IDs, regions, correlation keys, and namespaces; generations prevent old cleanup from destroying new resources.
- [ ] Close only **tenant-owned** resources; shared executors, schedulers, channels, and connection factories stay alive.
- [ ] Checkpoints support retrying mid-way failures; reconciler never rebuilds DELETING tenants on restart.
- [ ] Error/retry flows recognize deleted tenants and never unintentionally resurrect flows.
- [ ] Metrics and alerts cover resource leaks, pending messages, and failed cleanups; test concurrently across tenants and nodes.

**Conclusion:** Deleting a tenant from a dynamic runtime is a **quiesce → drain or quarantine → unregister flow → clean up owned resources → verify** workflow. <code>IntegrationFlowContext</code> manages the lifecycle of definitions and dependent beans, while the application remains responsible for in-flight messages, persistent state, external sources, and ownership boundaries. Combining admission gates, durable state machines, idempotency, generation fencing, and restart/concurrency tests ensures tenant deletion never drops work unintentionally or disrupts active tenants.

## References

- [Spring Integration Reference — Dynamic and Runtime Integration Flows](https://docs.spring.io/spring-integration/reference/dsl/java-runtime-flows.html)
- [Spring Integration 6.5 Javadoc — IntegrationFlowContext](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/context/IntegrationFlowContext.html)
- [Spring Integration 6.5 Javadoc — IntegrationFlowRegistration](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/context/IntegrationFlowContext.IntegrationFlowRegistration.html)
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html)
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
- [Spring Framework Reference — Application Context Lifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
