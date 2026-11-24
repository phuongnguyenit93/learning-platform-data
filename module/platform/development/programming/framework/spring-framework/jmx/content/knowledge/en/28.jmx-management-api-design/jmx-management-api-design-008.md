# Do Not Turn JMX into a Substitute Business API

> **Topic:** Spring Framework JMX  
> **Knowledge Group:** Management API Design  
> **Lesson:** Do Not Turn JMX into a Substitute Business API

## 1. Objective

JMX (Java Management Extensions) is very useful for observing and controlling a running Java application. However, the fact that Spring Framework can export a method as a \`@ManagedOperation\` **does not mean that method should become a primary business channel**.

After this lesson, you will be able to:

- Distinguish a **management API** from a **business API** by purpose, callers, frequency, and contract stability.
- Recognize signs that JMX is being misused to process orders, handle payments, query customers, or integrate systems.
- Explain why JMX/RMI does not inherently provide the semantics of a modern business API: per-user authentication, per-resource authorization, versioning, idempotency, schemas, pagination, retries, or distributed tracing.
- Design a small, least-privilege **management facade** decoupled from business services.
- Choose appropriately among JMX, HTTP APIs, messaging, schedulers, and observability tools based on the goal.
- Keep JMX operations safe, audited, and testable via \`MBeanServer\`.

## 2. What Is JMX Designed For?

JMX provides a management model built around **MBeans**, **ObjectNames**, **MBeanServer**, attributes, operations, and notifications.

\`\`\`text
               Application JVM
                       |
                Business services
                       |
            Management facade/adapter
                       |
                       v
                   MBeanServer
                       |
            +----------+----------+
            |                     |
         JConsole          Monitoring/JMX client
            |
     Read status, adjust configuration,
     trigger bounded operational actions
\`\`\`

Tasks JMX is well suited for:

- Reading active worker counts, queue depth, cache hit ratio, or connection state.
- Viewing configuration version, last refresh timestamp, or failure counts.
- Adjusting operational limits safely, such as worker count or timeout within bounded ranges.
- Pausing/resuming a component during incident mitigation.
- Requesting cache refresh, configuration reload, or counter reset.
- Receiving notifications when notable operational events occur.

These actions **manage how the application operates**. They should not replace normal business processing paths that end users or other systems depend on.

## 3. How Do Business APIs and Management APIs Differ?

| Criterion | Business API | JMX Management API |
|---|---|---|
| Purpose | Execute product use cases | Observe and control runtime behavior |
| Callers | Frontends, partners, services, batch workers | Operators, SREs, authorized monitoring/automation |
| Frequency | Can be very high | Usually low, outside the hot path |
| Data | Domain objects, schema-bound requests/responses | Compact, clear management types with metadata |
| Authorization | Per-user, per-tenant, per-resource, per-action | By management channel and MBean/operation policy |
| Versioning | Public API contract with deprecation | ObjectName/attribute/operation contract managed separately |
| Reliability | Retries, idempotency, queues, SLOs, error contracts | Depends on JMX connector and application-added logic |
| Audit | By business event and actor | By administrative action and authenticated actor if available |
| Transport | HTTP/gRPC/messaging, etc. | Local JMX or remote connector such as RMI |
| Client expectations | SDKs, service discovery, gateways | JConsole, VisualVM, JMX clients, or monitoring agents |

Because JMX supports operations, it is **technically** still possible to invoke business logic. Yet technical feasibility does not prove it is an appropriate, safe, or stable communication channel.

## 4. Anti-Pattern: Exposing an Entire Business Service via JMX

Suppose an order system has a service:

\`\`\`java
public interface OrderService {
    Order createOrder(CreateOrderRequest request);
    void cancelOrder(String orderId);
    PaymentResult charge(String orderId, PaymentDetails details);
    Order getOrder(String orderId);
}
\`\`\`

A poor choice is exposing these methods as management operations:

\`\`\`java
@Component
@ManagedResource(
    objectName = "app.management:type=OrderService,name=main"
)
public class OrderServiceMBean {

    private final OrderService orders;

    public OrderServiceMBean(OrderService orders) {
        this.orders = orders;
    }

    @ManagedOperation
    public Order createOrder(CreateOrderRequest request) {
        return orders.createOrder(request);
    }

    @ManagedOperation
    public PaymentResult charge(
            String orderId,
            PaymentDetails details
    ) {
        return orders.charge(orderId, details);
    }
}
\`\`\`

The issue is not just that \`CreateOrderRequest\` is awkward to type in JConsole. More importantly:

1. The JMX channel can bypass business API gateway layers and HTTP authorization.
2. Management clients can become an unmonitored path for creating business transactions.
3. Business DTOs create classpath/serialization coupling between the JVM and JMX clients.
4. Retries, duplicate commands, auditing, and rate limiting are not handled automatically by JMX.
5. Remote JMX connectors are high-privilege surfaces and must not be exposed to user traffic.
6. Every service change risks becoming a JMX contract change.
7. Operating under multi-tenant models and per-end-user identity becomes difficult.

Never add \`@ManagedOperation\` simply because a method is already public and you want a "quick way to call it externally."

## 5. Principle: JMX Manages the System, Business APIs Execute Business Logic

\`\`\`text
Customer / frontend / integration
                 |
                 v
           Business API
       (HTTP/gRPC/message)
                 |
           Authentication
           Authorization
           Validation
           Transaction
           Idempotency
           Audit
                 |
                 v
           Business service
                 ^
                 |
     Management facade (bounded operations)
                 ^
                 |
             JMX client
\`\`\`

A management facade may call business services, but only through a **small set of operational actions** with clear constraints and preconditions. For example, "pause queue processing" differs from "create one million orders"; "re-run an approved batch job by ID" differs from "charge arbitrary client-supplied orders."

JMX and business APIs may share internal dependencies. That **does not** turn JMX into a substitute business API as long as the operational scope is tightly controlled.

## 6. Good Example: Management Facade for a Queue Worker

A business service:

\`\`\`java
public interface OrderProcessingService {
    void processNextBatch();
    int pendingCount();
}
\`\`\`

A separate management interface:

\`\`\`java
public interface WorkerManagement {
    int getPendingCount();
    int getActiveWorkers();
    void pause();
    void resume();
}
\`\`\`

Facade implementation:

\`\`\`java
package example.management;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "app.management:type=WorkerPool,name=orders",
    description = "Order worker operations"
)
public class OrderWorkerManagement {

    private final WorkerCoordinator coordinator;

    public OrderWorkerManagement(
            WorkerCoordinator coordinator
    ) {
        this.coordinator = coordinator;
    }

    @ManagedAttribute(description = "Queued jobs")
    public int getPendingCount() {
        return coordinator.pendingCount();
    }

    @ManagedAttribute(description = "Active workers")
    public int getActiveWorkers() {
        return coordinator.activeWorkers();
    }

    @ManagedOperation(
        description = "Pause dispatch of new jobs"
    )
    public void pause() {
        coordinator.pauseDispatch();
    }

    @ManagedOperation(
        description = "Resume dispatch of new jobs"
    )
    public void resume() {
        coordinator.resumeDispatch();
    }
}
\`\`\`

\`WorkerCoordinator\` is a hypothetical business/operational dependency of the application. It must supply proper implementation, concurrency control, validation, and policy enforcement.

This facade exposes **worker control**, not \`processOrder(customerId, payment)\` or direct payment APIs. Business execution paths continue flowing through the designed business service.

## 7. Designing by the Principle of Least Privilege

A management API should answer: what does an operator need to inspect or control to run the system?

Examples worth considering:

\`\`\`java
@ManagedAttribute
public long getPendingJobs() { ... }

@ManagedOperation
public void pauseConsumers() { ... }

@ManagedOperation
public void resumeConsumers() { ... }
\`\`\`

Examples to avoid:

\`\`\`java
@ManagedOperation
public void deleteAllCustomerRecords() { ... }

@ManagedOperation
public String dumpApiTokens() { ... }

@ManagedOperation
public Object executeArbitraryCommand(String command) { ... }
\`\`\`

Even "internal" operations remain privileged entry points if a client holds sufficient permissions. Do not treat \`@ManagedResource\` as a security mechanism. It determines the management surface that the exporter may publish; authentication and authorization must be handled at the appropriate layers.

## 8. JMX Does Not Replace an API Gateway

A typical business API may sit behind:

- Per-user authentication.
- Per-tenant and per-resource authorization.
- Request validation.
- Rate limiting or quotas.
- Business transaction auditing.
- Idempotency keys.
- API versioning and contract schemas.
- Observability with correlation IDs.
- Timeout and retry policies.

A JMX remote connector has its own security mechanisms, yet it does not provide all of the above semantics out of the box.

Example:

\`\`\`text
Business API:
POST /orders
Authorization: Bearer ...
Idempotency-Key: ...
Body: create order request

JMX:
MBeanServer.invoke(
  "app.management:type=OrderService,name=main",
  "createOrder",
  ...
)
\`\`\`

The JMX path does not automatically inherit the HTTP filter chain, API gateway policies, or end-user request identity. Enforcing the same business policies would require re-implementing and verifying them at the service boundary. The simpler and clearer approach is not exposing that use case via JMX.

## 9. Which Management Actions Can Impact Business Flow?

Not all management operations are read-only. Useful operational actions can still affect business processing.

For instance, \`pauseConsumers()\` can temporarily halt order processing; \`reloadRoutingRules()\` can change message routing; \`refreshCache()\` can generate load.

Categorization is therefore needed:

| Category | Examples | Risk to Manage |
|---|---|---|
| Observation | \`getPendingCount()\` | Data leakage or cardinality |
| Bounded adjustment | \`setMaxWorkers(int)\` | Excessive values, resource exhaustion |
| Lifecycle control | \`pause()\`, \`resume()\` | Service interruption |
| Maintenance | \`refreshCache()\`, \`resetCounters()\` | Side effects, missing metrics after reset |
| Job launch | \`requestReindex()\` | Duplicate jobs, high load, async state |
| Destructive actions | \`purgeAllData()\` | Data loss; usually should not be exposed via JMX |

No action is automatically safe merely because it is labeled "maintenance." Scope, bounds, authorized actors, and recovery plans must be defined.

## 10. Runtime Adjustments Under Constraints

Example worker count adjustment:

\`\`\`java
@ManagedOperation(
    description = "Set maximum worker count"
)
public void setMaxWorkers(int requested) {
    if (requested < 1 || requested > 64) {
        throw new IllegalArgumentException(
            "requested must be 1..64"
        );
    }
    workerCoordinator.setMaxWorkers(requested);
}
\`\`\`

The \`1..64\` range is just an example. In real systems, base limits on system capacity and operational policy.

An operation must specify:

1. Can it be invoked repeatedly safely?
2. Which input values are valid?
3. What are the side effects?
4. How long does it take?
5. What state remains if it fails partway through?
6. How can the client verify the outcome?
7. Is pre/post auditing required?

Returning \`void\` does not guarantee the operation finished every background task it initiated.

## 11. Management APIs Should Use Simple Data Types

JMX clients usually work best with:

\`\`\`text
boolean
int
long
double
java.lang.String
java.lang.String[]
CompositeData
TabularData
\`\`\`

Example:

\`\`\`java
@ManagedOperation
public String requestCacheRefresh(String cacheName) {
    // Validate allowlist, submit job,
    // return job identifier
    return "job-123";
}
\`\`\`

This is easier to interact with than an operation accepting deep business objects:

\`\`\`java
@ManagedOperation
public CacheRefreshResult execute(
        InternalRefreshOptions options,
        RequestContext context
) { ... }
\`\`\`

Custom Java objects are not strictly forbidden by JMX, but they typically create classpath/serialization coupling, are awkward in JConsole or non-Java clients, and leak domain details.

A management contract should favor summary data, stable schemas, and explicit bounds. When structured data is needed, consider MXBeans/Open Types under a suitable contract.

## 12. ObjectName Must Reflect Management Role

Do not make a Java class name the sole contract:

\`\`\`text
com.example.internal:type=RedisOrderCacheService
\`\`\`

If the goal is managing a logical cache, a more stable name is:

\`\`\`text
app.management:type=Cache,name=orders
\`\`\`

Management clients do not need to know that \`RedisOrderCacheService\` was replaced by \`CaffeineOrderCacheService\` if the JMX contract stays unchanged.

The management surface must be governed like a small API:

- \`ObjectName\`.
- Attribute names and types.
- Operation names, parameter signatures, and return types.
- Notification types, if any.
- Authentication/authorization expectations.
- Semantics, side effects, and lifecycle.

Avoid breaking these accidentally during implementation refactoring.

## 13. When to Choose HTTP, gRPC, or Message Queues Instead of JMX?

### HTTP or gRPC

Appropriate when:

- Multiple services or end users need to invoke business capabilities.
- There is an explicit request/response contract.
- A gateway, per-user auth, rate limiting, and versioning are required.
- Multi-language integration beyond Java is required.
- Tracing or API governance independent of the JVM is needed.

### Messaging

Appropriate when:

- Jobs are asynchronous, high-volume, or require retries.
- High reliability with durable queues is required.
- Request submission time must be decoupled from processing time.
- Dead-letter handling, backpressure, or consumer groups are needed.

### Scheduler/Workflow Systems

Appropriate when:

- Business tasks run on schedules or across multi-step workflows.
- Visibility into state, retries, approvals, and checkpoints is needed.
- Dedicated governance for long-running processes is required.

### JMX

Appropriate when:

- Operators need to inspect internal JVM and application state.
- Bounded control is needed during debugging or incident mitigation.
- Expected clients are JConsole, monitoring agents, or JMX tooling.
- Invocation frequency is low and access privileges are tightly restricted.

**Choose based on requirements**, not simply whichever takes fewer lines of code.

## 14. Spring Boot Actuator and JMX

Spring Boot Actuator provides operational endpoints such as \`health\`, \`info\`, and \`metrics\` depending on dependencies and configuration. Endpoints can be exposed over HTTP or JMX according to their respective exposure policies.

\`\`\`text
Actuator endpoint model
      |
      +--> HTTP exposure
      |
      +--> JMX exposure -> MBeanServer
\`\`\`

This does not make Actuator a business API. A custom Actuator endpoint with write operations must still account for side effects and security.

Settings such as:

\`\`\`properties
management.endpoints.jmx.exposure.include=health,info
\`\`\`

control Actuator JMX exposure for the corresponding Boot version, and **do not automatically open a remote JMX port**. Spring \`@ManagedResource\` and Actuator \`@Endpoint\` are two different ways of defining management interfaces.

If the problem is time-series metrics or health checks, consider Actuator and observability tooling rather than building custom business MBeans for every use case.

## 15. Performance and Throughput Risks

JMX invocations pass through management infrastructure and may incur metadata lookups, serialization, or network I/O over a remote connector.

Do not use a path like:

\`\`\`text
API request -> remote JMX -> business processing
\`\`\`

for thousands of production requests per second merely because Java methods can be invoked over JMX.

Risks:

- Monitoring systems compete for resources with business traffic.
- A connector can become a bottleneck.
- Long operations cause timeouts, block threads, or create memory pressure.
- Troubleshooting errors is hard without a full business API contract.
- Retries can multiply side effects.
- If the JMX connector fails, the business path breaks with it.

Business paths deserve proper SLAs, concurrency controls, backpressure, and suitable transports. JMX was not designed as a general-purpose replacement for distributed transaction systems.

## 16. Identity and Multi-Tenancy Risks

A JMX client may authenticate to the connector with an administrative account. That identity is not automatically the end-user identity of individual business requests.

For example, a business API must check:

\`\`\`text
Can User A view order #123?
Can Tenant B update this item's state?
Does Partner C have API quota?
\`\`\`

When shifting to JMX, many applications inadvertently check only "who can connect to JMX," bypassing domain-object authorization.

Do not design:

\`\`\`java
@ManagedOperation
public Order getOrder(String orderId) { ... }
\`\`\`

as a customer data lookup shortcut simply for debugging convenience. Use aggregate metrics or diagnostics with proper redaction and authorization policies instead.

For sensitive information, having an \`ObjectName\` and management method does not replace privacy controls.

## 17. Auditing Management Operations

State-mutating operations should record:

- Timestamp.
- \`ObjectName\`.
- Operation or writable attribute.
- Authenticated identity if present, and identity source.
- Allowlisted/masked parameters.
- Outcome: accepted, success, failed, denied.
- Correlation ID or job ID.

Example audit event:

\`\`\`json
{
  "event": "management.operation",
  "objectName": "app.management:type=WorkerPool,name=orders",
  "operation": "pause",
  "actor": "jmx-operator",
  "actorSource": "authenticated-connector",
  "outcome": "SUCCESS"
}
\`\`\`

This is an application-designed illustrative schema, not an event automatically emitted by Spring JMX.

If multiple operators share credentials, the backend cannot distinguish specific individuals from the shared account alone. Never trust a client-supplied \`requestedBy\` parameter as an authenticated identity.

## 18. Asynchronous Jobs: Return a Request ID, Not a Fake Result

A management operation sometimes triggers heavy work:

\`\`\`java
@ManagedOperation
public String requestReindex() {
    return jobCoordinator.scheduleReindex();
}
\`\`\`

If the method only enqueues work, the JMX result should mean **request accepted**, not "reindex completed successfully."

A sensible interface:

\`\`\`java
@ManagedOperation
public String requestReindex() {
    return jobCoordinator.scheduleReindex();
}

@ManagedOperation
public String reindexStatus(String jobId) {
    return jobCoordinator.status(jobId);
}
\`\`\`

\`jobCoordinator\` is a hypothetical application dependency. In production, it must prevent duplicate jobs, bound concurrent jobs, and handle timeouts.

For high-reliability workflows, persist state in an appropriate job system. JMX should serve only as the operational portal to **request/observe**, not own the full workflow orchestration.

## 19. Handling Retries and Idempotency

A remote client calls:

\`\`\`java
connection.invoke(
    objectName,
    "requestReindex",
    new Object[0],
    new String[0]
);
\`\`\`

What can happen:

\`\`\`text
Server receives request
     |
     v
Job is enqueued
     |
     X response lost due to network failure
     |
Client times out
\`\`\`

The client cannot be sure the job never started. If it retries blindly, two jobs may be enqueued.

Possible solutions:

- Use a management-client-generated request ID verified by the service.
- Provide an operation to look up request status.
- Make operations idempotent where appropriate.
- Audit acceptance and completion separately.
- Restrict retries when the previous outcome is unknown.

JMX does not natively provide an idempotency-key protocol like a purpose-built business API.

## 20. MBean Lifecycle and Stability

A JMX MBean can be unregistered when:

- The Spring \`ApplicationContext\` closes.
- The exporter replaces a registration.
- The application restarts.
- A management module reloads.
- MBeans are created/destroyed dynamically.

If a critical business workflow depends on a single \`ObjectName\` to process commands, this lifecycle can cause outages.

A business API needs availability and service-level routing, not reliance on an MBean registered inside one specific JVM.

\`RegistrationPolicy.REPLACE_EXISTING\` resolves \`ObjectName\` collisions; it is not load balancing, failover, or zero-downtime upgrades.

## 21. Test the Management Surface, Not Just the Happy Path

Suppose a management facade should expose only:

\`\`\`text
Attributes:
  PendingCount (read-only)
  ActiveWorkers (read-only)

Operations:
  pause()
  resume()
\`\`\`

An integration test can inspect \`MBeanInfo\`:

\`\`\`java
ObjectName name = new ObjectName(
    "app.management:type=WorkerPool,name=orders"
);

MBeanInfo info = server.getMBeanInfo(name);

Set<String> operations = Arrays.stream(
    info.getOperations()
)
    .map(op -> op.getName())
    .collect(Collectors.toSet());

assertTrue(operations.contains("pause"));
assertTrue(operations.contains("resume"));
assertFalse(operations.contains("processCustomerPayment"));
\`\`\`

This snippet needs the appropriate Java/JMX imports and \`server\` initialized from an integration-test context. To verify the full contract, also check signatures and data types; asserting that one name is absent is only a minimal check.

Tests should cover:

1. Correct \`ObjectName\` registration.
2. Only expected attributes/operations appear.
3. Validation rejects out-of-range parameters.
4. Operations have properly scoped side effects.
5. Auditing records outcomes.
6. Security integration blocks unauthorized callers.
7. Runtime errors leave no corrupted state.
8. Startup/shutdown lifecycles do not create duplicate MBeans.

## 22. Governing Permissions by Risk Level

Not everyone with JMX access should be able to invoke every operation.

A classification:

| Role | Appropriate Scope |
|---|---|
| Read-only monitoring | Read non-sensitive attributes/metrics |
| Operator | Controlled pause/resume/reload actions |
| Administrator | Sensitive configuration actions under approval |
| Automation account | Specific, tightly bounded operations |
| Developer debug | Non-production test environments, not enabled by default in prod |

JMX connectors have their own security mechanisms; fine-grained authorization by \`ObjectName\`/operation depends on infrastructure, JDK, connector, or custom layers. Never assume connecting alone properly separates all roles.

Protect the management path with network isolation, authentication, TLS, and by restricting operations in the MBean design itself.

## 23. When Should a Management Operation Be Removed?

An operation originally helpful for debugging can become a liability if kept forever.

Example:

\`\`\`java
@ManagedOperation
public void forceCompleteAllPendingOrders() { ... }
\`\`\`

If an action no longer has a clear operational need or is too dangerous, remove it from the management surface via a contract-change plan.

Before removal:

- Inventory tools, runbooks, and automation using it.
- Review recent audit activity.
- Announce deprecation and migration if long-lived clients exist.
- Provide a proper business API or workflow if the capability is truly needed.
- Update \`MBeanInfo\` tests to guard the new surface.

Do not keep an administrative backdoor around just in case "we might need it someday."

## 24. A Reference Architecture

\`\`\`text
                     External clients
                            |
                 Business API Gateway
                            |
               HTTP/gRPC authentication
                            |
                  Business services
                            |
         +------------------+------------------+
         |                                     |
   Database / event bus                 Job scheduler
         ^
         |
   WorkerCoordinator
         ^
         |
   Management facade
         ^
         |
     MBeanServer
         ^
         |
  Restricted JMX connector
         ^
         |
        Operator
\`\`\`

Internal business services may be shared underneath, but the **business path** still goes through its own policies and transport. The **management path** stays restricted to defined operational capabilities.

## 25. Anti-Patterns and Fixes

### Anti-pattern A: Turning an HTTP Endpoint into JMX Because "Connecting to the JVM Is Easy"

**Problem:** HTTP endpoints have security, validation, tracing, and versioning; JMX calls can bypass those layers.

**Fix:** Keep the business endpoint. If endpoint health monitoring is needed, expose metrics/health separately via JMX.

### Anti-pattern B: Exposing an Entire Bean for Debugging Convenience

**Problem:** methods may hold sensitive or unstable functionality.

**Fix:** create a \`@ManagedResource\` facade containing only approved methods.

### Anti-pattern C: Using MBeans as Integration Points Between Microservices

**Problem:** tight coupling to JVM, \`ObjectName\`, RMI, and class serialization; hard to autoscale and fail over.

**Fix:** use HTTP/gRPC/messaging or workflows suited to system requirements.

### Anti-pattern D: Running Long Business Batches via JConsole

**Problem:** unclear timeouts, retries, and job lifecycle.

**Fix:** use a scheduler/job system; JMX only requests or inspects state when needed.

### Anti-pattern E: Using Shared JMX Accounts for Personal Data Operations

**Problem:** hard to trace identity, scope permissions, and protect privacy.

**Fix:** use a business/admin API with designed identity and authorization, or manage privileged operations through an approval workflow.

## 26. Management API Design Checklist

- [ ] The operation's goal is operational observation/control, not a regular business use case.
- [ ] There is a clear rationale for exposing it over JMX.
- [ ] The JMX contract is decoupled from internal service implementations/interfaces.
- [ ] The \`ObjectName\` is meaningful and stable.
- [ ] Only necessary attributes/operations are exposed.
- [ ] No secrets, personal data, or large business object graphs are returned.
- [ ] Parameter/return types suit management clients.
- [ ] Inputs are validated against ranges and allowlists.
- [ ] Side effects are bounded with a way to verify outcomes.
- [ ] Asynchronous operations have separate job IDs and status tracking.
- [ ] Auditing and security match the risk level.
- [ ] Retry/idempotency policies exist where needed.
- [ ] Business-API throughput/SLAs are not demanded of the JMX connector.
- [ ] Integration tests verify metadata and behavior.
- [ ] JMX is not used as a backdoor bypassing business authorization.
- [ ] An owner and deprecation plan exist for the management API.

## 27. Hands-on Exercise

**Scenario:** an application has \`InventoryService\` with:

\`\`\`java
InventoryResult reserve(
    String sku,
    int quantity,
    String customerId
);

void release(String reservationId);

int currentStock(String sku);
\`\`\`

The operations team wants to use JConsole to "get everything done quickly."

**Question A:** Should \`reserve\` and \`release\` be exported directly via JMX?

Normally no. These are customer/reservation business use cases requiring authorization, transactions, idempotency, and auditing. Keep them in the business API/workflow.

**Question B:** What should be exposed to support operations?

For example, a management facade with:

\`\`\`java
@ManagedAttribute
public long getPendingReservations() { ... }

@ManagedAttribute
public boolean isReservationConsumerPaused() { ... }

@ManagedOperation
public void pauseReservationConsumer() { ... }

@ManagedOperation
public void resumeReservationConsumer() { ... }
\`\`\`

These methods manage the processing flow rather than directly mutating a specific customer reservation.

**Question C:** What if a faulty reservation genuinely must be fixed in production?

Use an admin workflow or business API with proper authorization, approval, auditing, and idempotency. JMX must not become a shortcut to bypass those requirements.

## 28. Self-Check Questions

1. Why shouldn't \`@ManagedOperation\` be added to every public method of a service?
2. Why does a JMX connector not replace a business API gateway?
3. Which action fits JMX better: reading queue depth or creating a new order?
4. How does a management facade separate the domain API from the management API?
5. Why are \`String\`/primitives usually easier to consume than business DTOs in JMX?
6. When an operation only enqueues a job, why shouldn't it return "completed" immediately?
7. If remote JMX times out, does the client know whether the operation ran?
8. Why is a stable \`ObjectName\` alone not enough to guarantee compatibility?
9. When should HTTP/gRPC/messaging be chosen over JMX?
10. How do you verify no dangerous methods were accidentally exposed after a refactor?

## 29. Key Takeaways

\`\`\`text
Business API
   -> user-facing use cases
   -> domain authorization, transactions, idempotency
   -> normal request traffic

JMX Management API
   -> runtime visibility and limited control
   -> ObjectName, attributes, operations, notifications
   -> restricted operator/monitoring traffic

Do not use JMX as a substitute business API.
\`\`\`

**Core principle:** **JMX is a management channel, not a substitute business execution path.** Publish a small management facade with stable \`ObjectName\`s, validation, auditing, and appropriate permissions. Keep business use cases in APIs/workflows designed for throughput, identity, transactions, idempotency, and scalability.