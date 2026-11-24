# Auditing Administrative Invocations and Actors in Spring Framework JMX

> **Topic:** Spring Framework JMX  
> **Knowledge Group:** Security and Operations  
> **Lesson:** Auditing Administrative Invocations and Actors

## 1. Objectives

A JMX operation can inspect or mutate the state of a running application. When an action has side effects—such as clearing caches, changing thresholds, resetting counters, or toggling components—controlling invoke permissions alone is not enough: the system also needs to know **who did what, to which target, when, and with what outcome**.

After this lesson, you will be able to:

- Distinguish **authentication**, **authorization**, **audit logging**, and **observability** for JMX.
- Identify the minimum fields of an audit event for an administrative invocation.
- Understand the limitations of identifying callers over JMX/RMI, especially with a local MBeanServer, proxies, shared credentials, or custom connectors.
- Design a management facade in Spring to audit critical operations.
- Distinguish client-side logs, interceptors, JMX connectors, and server-side operation logs.
- Avoid writing passwords, tokens, secrets, personal data, or sensitive payloads into audit logs.
- Build verification flows that distinguish **requested**, **accepted**, **executed**, and **completed**.

## 2. Why Do JMX Operations Need Auditing?

JMX is a management channel for the Java runtime and application. An MBean can expose:

- **Read-only attributes** such as connection counts or queue status.
- **Writable attributes** such as timeout configurations, limits, or operational flags.
- **Operations** such as cache refresh, pausing workers, changing logging, or reloading configuration.
- **Notifications** reflecting events and state changes.

For example:

\`\`\`java
@ManagedOperation(description = "Pause background workers")
public void pauseWorkers() {
    workerService.pause();
}
\`\`\`

If an operator invokes an operation and the system stops processing jobs, investigation questions typically include:

1. Did anyone invoke \`pauseWorkers\`?
2. When did the action happen and on which instance?
3. What were the exact ObjectName and operation name?
4. Which parameters were used?
5. Which person or service account was authenticated?
6. Was the command denied, failed, or completed?
7. Is there a correlation ID linking the audit entry to application logs?

Without auditing, incidents are hard to reproduce, accountability is hard to establish, and an administrative action can easily be mistaken for an application bug.

## 3. Four Distinct Control Layers

| Layer | Question Answered | Example |
|---|---|---|
| Authentication | Which identity does the caller prove? | JMX connector authenticates account |
| Authorization | What is this identity permitted to do? | Allow reads, restrict operation invokes |
| Audit | Who requested/performed which action and what resulted? | Emit \`jmx.operation.invoke\` event |
| Observability | How is the application behaving and changing? | Queue depth metrics, JMX notifications |

**Auditing does not replace authorization.** Recording an unauthorized action after it has already executed is not a valid preventive control.

**Authentication does not automatically produce complete auditing either.** A connector may authenticate a user without recording the full MBean name, operation, permitted parameters, result, and correlation ID by default.

## 4. Administrative Call Flow to Observe

\`\`\`text
JConsole / JMX client
          |
          | credentials / subject
          v
JMXConnectorServer
          |
          | authentication + authorization
          v
MBeanServerConnection
          |
          | ObjectName + attribute/operation
          v
MBeanServer
          |
          v
Spring ModelMBean / management facade
          |
          | scope check + audit
          v
Business service
          |
          v
State change / operational task
\`\`\`

Auditing can occur at multiple layers:

- **Connector/access layer**: logs connection info, authenticated account, and allowed/denied access.
- **MBeanServer/interceptor**: logs JMX actions by ObjectName, signature, and result if supported by infrastructure.
- **Management facade**: logs operationally meaningful management actions and actual outcomes.
- **Business service**: logs critical state transitions regardless of whether they originate from JMX, HTTP, schedulers, or message consumers.

A robust design combines these layers by responsibility rather than relying on a single log line inside \`@ManagedOperation\`.

## 5. What Fields Should an Audit Event Have?

A well-structured audit event:

\`\`\`json
{
  "event": "jmx.operation",
  "timestamp": "2026-11-11T10:15:30.000Z",
  "application": "order-service",
  "instance": "order-service-2",
  "objectName": "app.management:type=WorkerPool,name=background",
  "operation": "pause",
  "signature": [],
  "actor": "jmx-operator-17",
  "actorSource": "authenticated-jmx-subject",
  "requestId": "ops-7cfe1a",
  "outcome": "SUCCESS",
  "durationMs": 12
}
\`\`\`

This is an **application-designed log structure template**, not a standard schema emitted automatically by Spring JMX.

| Field | Meaning |
|---|---|
| \`timestamp\` | UTC time or timestamp with explicit offset |
| \`event\` | Action type recorded |
| \`application\`, \`instance\` | Application and node where execution occurred |
| \`objectName\` | Target MBean identifier invoked |
| \`operation\`, \`signature\` | JMX operation name and signature |
| \`actor\` | Verified identity or system identity |
| \`actorSource\` | Source of identity verification |
| \`requestId\` | Correlation ID for tracing |
| \`outcome\` | SUCCESS, DENIED, FAILED, ACCEPTED, or other status |
| \`durationMs\` | Execution duration of the action |
| \`reasonCode\` | Non-sensitive error code or denial reason |

Recording all parameter values is not always necessary. For some actions, logging only parameter names and allowlisted/masked values is sufficient.

## 6. The Hard Part: Who Is Actually the JMX Caller?

This is where flawed assumptions happen most easily.

### 6.1. Local JMX

Code in the same JVM can invoke directly:

\`\`\`java
MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

server.invoke(
    objectName,
    "pause",
    new Object[0],
    new String[0]
);
\`\`\`

This call does not necessarily pass through a remote connector or authentication layer. In many setups, no “logged-in operator” metadata accompanies the call.

You cannot use \`System.getProperty("user.name")\` alone to prove who invoked a JMX operation; that value typically reflects the OS user running the JVM, **not the actor of each invocation**.

### 6.2. Remote JMX with Dedicated Accounts

When a JMX connector authenticates a client, it can create a corresponding security subject/principal. In configurations where the subject is propagated into the call's security context, server-side code can retrieve the subject through the appropriate JMX/RMI API.

However, do not claim that \`Subject.current()\` or any subject-retrieval API works identically across all JDKs and connectors. Security context depends on the JDK, connector implementation, authentication mechanism, and call path.

### 6.3. Shared Credentials

If multiple operators share one \`jmx-admin\` account, auditing can only confirm **the shared account** was used. It cannot reliably identify which individual performed the action without an additional identity layer or workflow.

### 6.4. Client-Supplied Username

An operation like:

\`\`\`java
public void pause(String requestedBy) { ... }
\`\`\`

does not establish a trustworthy identity; the client can pass any string. \`requestedBy\` is only caller-declared metadata, not proof of authentication.

**Rule:** separate \`verifiedActor\` (from a trustworthy authentication mechanism) from \`claimedActor\` (client-supplied data). Do not merge both fields into a verified identity.

## 7. Security Subject in Remote JMX

Remote JMX can associate a Java security \`Subject\` and \`Principal\` when the connector establishes an authenticated context.

Design model:

\`\`\`text
Client credentials
       |
       v
JMXAuthenticator / connector
       |
       v
Authenticated Subject (if supported by mechanism)
       |
       v
Invocation authorization context
       |
       v
Management operation audit
\`\`\`

When reliable caller identification is needed, build identity architecture at the **connector/authentication layer** and propagate the actor along a controlled path to the audit layer, or use centralized connector-supported auditing.

Notes:

- Do not rely on arbitrary ThreadLocals if the connector does not guarantee context propagation.
- Do not rely on thread names as user IDs.
- Do not infer users from source IP when NAT, bastions, or shared monitoring agents exist.
- Do not trust a username passed into an operation by the client as authenticated.
- If the actor cannot be determined, log \`UNKNOWN\` or \`SYSTEM\` explicitly with the reason; do not fabricate identities.

## 8. Designing an Audited Management Facade

A business service:

\`\`\`java
public interface WorkerService {
    void pause();
    void resume();
    boolean isPaused();
}
\`\`\`

Management facade:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "app.management:type=WorkerPool,name=background"
)
public class WorkerManagementFacade {

    private final WorkerService workers;
    private final ManagementAudit audit;

    public WorkerManagementFacade(
            WorkerService workers,
            ManagementAudit audit
    ) {
        this.workers = workers;
        this.audit = audit;
    }

    @ManagedAttribute
    public boolean isPaused() {
        return workers.isPaused();
    }

    @ManagedOperation(description = "Pause background workers")
    public void pause() {
        long started = System.nanoTime();
        String actor = audit.resolveVerifiedActorOrUnknown();

        try {
            workers.pause();
            audit.recordSuccess(
                actor,
                "app.management:type=WorkerPool,name=background",
                "pause",
                System.nanoTime() - started
            );
        } catch (RuntimeException e) {
            audit.recordFailure(
                actor,
                "app.management:type=WorkerPool,name=background",
                "pause",
                e.getClass().getSimpleName()
            );
            throw e;
        }
    }
}
\`\`\`

\`ManagementAudit\` is an **application-designed** abstraction, not a built-in Spring Framework API. It must define how actors are resolved, how logs are written, how logging errors are handled, and ensure elapsed time measured in nanoseconds is converted to the unit expected by the audit schema.

The example intentionally omits the exception message because messages sometimes contain sensitive data. A real logger can record standardized error codes and correlation IDs.

### A Minimal Audit Interface

\`\`\`java
public interface ManagementAudit {

    String resolveVerifiedActorOrUnknown();

    void recordSuccess(
        String actor,
        String objectName,
        String operation,
        long elapsedNanos
    );

    void recordFailure(
        String actor,
        String objectName,
        String operation,
        String reasonCode
    );
}
\`\`\`

\`resolveVerifiedActorOrUnknown()\` must not guess callers from hostnames or OS accounts. If no identity is available from a trusted connector, return \`UNKNOWN\` or an explicitly defined system identifier.

## 9. Auditing Access Denials

An operation can be rejected **before the facade method is invoked**, for example in connector authorization or the MBeanServer access-control layer.

In that case, a \`try/catch\` inside \`@ManagedOperation\` **cannot record the DENIED event** because the method never executes.

\`\`\`text
Client
   |
   v
Authorization check
   |
   +--> DENIED --> audit at security/connector layer
   |
   v
Facade method invoked
   |
   +--> SUCCESS/FAILED --> audit at operation
\`\`\`

Therefore, complete auditing must account for calls **denied before reaching the business layer**.

If using a security proxy/gateway in front of the connector, ensure security logs correlate with management sessions. Do not build a separate authorization check inside the facade and treat it as a substitute for securing the JMX connection.

## 10. Audit Attribute Reads or Only Operations?

Not all JMX activity is \`invoke\`:

\`\`\`java
connection.getAttribute(name, "QueueDepth");
connection.setAttribute(
    name,
    new Attribute("MaxWorkers", 16)
);
connection.invoke(
    name,
    "pause",
    new Object[0],
    new String[0]
);
\`\`\`

There are three distinct action types:

| Action | Example | Audit Priority |
|---|---|---|
| Attribute read | \`getAttribute("QueueDepth")\` | Depends on sensitivity and query volume |
| Attribute write | \`setAttribute("MaxWorkers")\` | Should be audited since it mutates state |
| Operation invoke | \`invoke("pause")\` | Should audit operations with side effects |

For very high-frequency attribute reads, logging every single read can generate high volume. Define policy based on sensitivity and compliance requirements. Aggregated access metrics can cover ordinary indicators, while sensitive data or critical management actions need detailed auditing.

If choosing to audit writable attributes, do not instrument only \`@ManagedOperation\` because administrative setters go through \`setAttribute\`, not necessarily a same-named operation in every model.

## 11. AOP Can Help Audit, But Does Not Replace Security Architecture

Spring AOP can use an aspect to log methods on management facades:

\`\`\`java
@Aspect
@Component
public class ManagementAuditAspect {

    private final ManagementAudit audit;

    public ManagementAuditAspect(ManagementAudit audit) {
        this.audit = audit;
    }

    @Around(
        "execution(* com.example.management.*ManagementFacade.*(..))"
    )
    public Object around(ProceedingJoinPoint pjp)
            throws Throwable {

        long start = System.nanoTime();
        String actor = audit.resolveVerifiedActorOrUnknown();
        String method = pjp.getSignature().getName();

        try {
            Object result = pjp.proceed();
            audit.recordSuccess(
                actor,
                "management-facade",
                method,
                System.nanoTime() - start
            );
            return result;
        } catch (Throwable error) {
            audit.recordFailure(
                actor,
                "management-facade",
                method,
                error.getClass().getSimpleName()
            );
            throw error;
        }
    }
}
\`\`\`

This example assumes proper Spring AOP and AspectJ annotation support, along with imports for \`Aspect\`, \`Around\`, \`ProceedingJoinPoint\`, and \`Component\`.

Limitations to understand:

- If the exporter references the raw target directly instead of the Spring AOP proxy, the advice can be bypassed.
- Self-invocation via \`this.method()\` usually does not trigger new advice.
- \`@ManagedAttribute\` getters/setters may require separate audit policies.
- Advice does not run when the connector rejects the call before method invocation.
- The actor is still only as trustworthy as the resolver's identity source.

Do not log all of \`pjp.getArgs()\` by default: arguments may contain credentials, business payloads, or personal data.

## 12. Outcomes: SUCCESS Differs from ACCEPTED

A synchronous operation:

\`\`\`java
@ManagedOperation
public void resetCounters() {
    counters.reset();
}
\`\`\`

If it returns without an exception, the synchronous action can be recorded as \`SUCCESS\`, according to the method contract.

However, an asynchronous operation:

\`\`\`java
@ManagedOperation
public String requestRebuild() {
    return jobs.enqueueRebuild();
}
\`\`\`

only confirms the request was placed onto a queue. The audit should record:

\`\`\`json
{
  "operation": "requestRebuild",
  "outcome": "ACCEPTED",
  "jobId": "job-019"
}
\`\`\`

When the worker finishes, a separate event:

\`\`\`json
{
  "event": "management.job.completed",
  "jobId": "job-019",
  "outcome": "SUCCESS"
}
\`\`\`

Do not record \`SUCCESS\` for the entire job simply because the enqueue call returned. Correlation IDs or job IDs link the command audit to the execution outcome.

## 13. Notification Auditing Differs from Command Auditing

JMX notifications can record state changes:

\`\`\`text
app.worker.paused
app.cache.refreshed
app.job.completed
\`\`\`

However, notifications do not prove who performed the action.

An \`app.worker.paused\` event could occur because:

- An operator invoked a JMX operation.
- An internal task paused automatically.
- A scheduler or business rule changed state.
- Another non-JMX API performed the same action.

If identity attribution is needed, command auditing must obtain the actor from a trusted security context and generate a correlation ID; status events can reference that correlation ID when allowed by contract.

**Notifications are not durable audit logs by default.** Listeners may not be registered yet, connections may drop, or MBeans may be unregistered. For critical auditing, use an audit sink with durable storage and appropriate retention/immutability policies.

## 14. Protecting Data Inside Audit Logs

Do not log:

- Passwords or tokens used to sign in to JMX.
- \`Authorization\` headers, keystore passwords, or private keys.
- Full environment variables or system properties.
- Java objects whose \`toString()\` may contain secrets.
- Unclassified \`Notification.userData\` payloads.
- Personal data unnecessary for auditing purposes.

An example operation:

\`\`\`java
@ManagedOperation
public void rotateCredentials(String secret) { ... }
\`\`\`

Auditing all arguments via:

\`\`\`java
log.info("args={}", Arrays.toString(args));
\`\`\`

will inadvertently copy the secret into logs. The fix is not merely post-log masking; it is better **not to design JMX operations that accept plaintext secrets** when a safer secret management mechanism exists.

### Allowlisting Logged Parameters

For example, an operation:

\`\`\`text
resizeWorkers(int workers)
\`\`\`

can log \`workers=16\` if allowed by policy. For \`refreshCache(String cacheName)\`, logging the cache name is fine if it holds no sensitive data. For operations taking passwords/tokens, log only \`argumentPresent=true\` or an action code, never the value.

## 15. Identifying Callers Through a Bastion or Gateway

In an organization, operators may traverse a bastion or gateway before reaching the JMX connector.

\`\`\`text
Operator identity
      |
      v
Bastion / privileged access manager
      |
      v
JMX connector (service account)
      |
      v
MBeanServer
\`\`\`

If the JMX connector only sees a shared service account, JVM-level auditing cannot distinguish individuals by itself. You need to correlate:

1. Session ID or ticket ID from the bastion/PAM.
2. Operator identity authenticated at the gateway.
3. Session connect/disconnect timestamps.
4. Service account identity connecting to JMX.
5. Server-side operation audit when a trustworthy correlation mechanism exists.

Design a controlled identity propagation path; do not simply trust a client-supplied \`operatorName\`.

## 16. A Safe Actor Resolution Strategy

If the audit component cannot identify the user:

\`\`\`java
public enum ActorSource {
    AUTHENTICATED_JMX_SUBJECT,
    TRUSTED_MANAGEMENT_GATEWAY,
    APPLICATION_SYSTEM,
    UNKNOWN
}
\`\`\`

Record \`actorSource\` alongside \`actor\`. For example:

\`\`\`json
{
  "actor": "UNKNOWN",
  "actorSource": "UNKNOWN",
  "operation": "pause",
  "outcome": "SUCCESS"
}
\`\`\`

Audit data missing identity is a gap to improve in identity infrastructure, yet **honestly recording unknown is better than fabricating an identity**.

Also distinguish whether an actor is a human or a service account: a monitoring agent might invoke operations to auto-tune settings. An \`actorType\` field can hold \`HUMAN\` or \`SERVICE\` when determinable from the identity system.

## 17. Logging Failures Without Masking Primary Errors

Suppose the business operation fails and the audit sink also fails. There are two architectural choices:

- **Best-effort audit:** log audit failures separately without blocking the operation; suitable for some metrics/low-risk actions, though evidence may be lost.
- **Fail-closed audit:** refuse to execute the action if auditing cannot be recorded first per policy; suitable for highly sensitive actions, though transaction/idempotency design must be clear.

No single choice fits every system. What must be avoided is an audit logger exception accidentally masking a business exception without leaving a trace.

If auditing is mandatory, use a durable mechanism such as an append-only event store, outbox, or queue with bounded retries. Still, define transaction boundaries and ensure audit records do not confuse \`ACCEPTED\` with \`COMPLETED\`.

## 18. Idempotency, Retries, and Side-Effecting Commands

Remote JMX can time out after the server executed the operation but before the client received the response.

\`\`\`text
Client invoke("reset")
       |
       v
Server executes reset successfully
       |
       X response lost
       |
Client observes timeout
\`\`\`

If the client retries blindly, a non-idempotent operation can run twice.

For critical operations, consider:

- Request/correlation IDs.
- Trustworthily managed idempotency keys containing no secrets.
- Auditing \`REQUESTED\`, \`ACCEPTED\`, \`COMPLETED\`, \`FAILED\` states.
- A mechanism to query outcomes by request ID.
- Bounded retry policies aware of side effects.

Auditing must reflect **what actually happened on the server**, not merely what the client assumed happened.

## 19. Verifying Auditing with Integration Tests

A test can use an isolated MBeanServer:

\`\`\`java
MBeanServer server =
    MBeanServerFactory.newMBeanServer("audit.test");
\`\`\`

Then:

1. Register an MBean facade or initialize a Spring context exporting MBeans to this server.
2. Use an in-memory \`ManagementAudit\` implementation to capture audit records.
3. Invoke \`pause()\` via \`MBeanServer.invoke\`.
4. Assert the business operation produced the expected effect.
5. Assert the audit event contains ObjectName, operation, outcome, timestamp, and actor source.
6. Trigger a business failure and assert outcome \`FAILED\`.
7. Verify no secrets appear in the audit payload.
8. If security integration exists, separately test the \`DENIED\` case where authorization actually runs.
9. Close the context and unregister test MBeans to avoid affecting other tests.

Conceptual assertion example:

\`\`\`java
server.invoke(
    name,
    "pause",
    new Object[0],
    new String[0]
);

assertTrue(workerService.isPaused());
assertEquals("pause", audit.lastEvent().operation());
assertEquals("SUCCESS", audit.lastEvent().outcome());
\`\`\`

This is a test sketch with application-provided classes/fixtures, not a complete standalone snippet.

## 20. Checking Whether the Call Path Bypasses AOP

If auditing is applied via Spring AOP, verify that the exporter invokes the actual Spring proxy.

\`\`\`text
Client
   |
   v
MBeanServer
   |
   v
Exporter target reference
   |
   +--> Spring proxy -> AuditAspect -> business target
   |
   +--> Direct target -> bypasses AuditAspect
\`\`\`

For services using JDK dynamic proxies, only methods on the proxy interface can be routed through the proxy according to proxy rules. A separate management facade is often easier to control when intentional auditing and authorization are needed.

Use \`MBeanInfo\` to verify the operation is exposed, then invoke the operation in an integration test to confirm the audit interceptor actually runs. Having metadata does not guarantee audit advice executes.

## 21. Auditing at MBeanServerConnection and MBeanServer Levels

A client can wrap \`MBeanServerConnection\` to log:

\`\`\`java
connection.invoke(name, operation, params, signature);
\`\`\`

However, client-side logging has limitations:

- Clients can be modified or bypass the wrapper.
- Another client can connect directly.
- The client does not necessarily know the final business outcome.
- Client logs can be lost if the process crashes.
- Self-declared client identities do not prove real users.

When mandatory auditing is required for every command, place logging at the **server-side security/invocation boundary** or on a management facade/service traversed by all state-changing paths.

There is no single public Spring JMX annotation that automatically audits the entire MBeanServer. Combine tools appropriate to your connector, platform, and operational requirements.

## 22. Auditing setAttribute

A writable attribute:

\`\`\`java
@ManagedAttribute
public void setMaxWorkers(int maxWorkers) {
    // ...
}
\`\`\`

Clients can mutate it via:

\`\`\`java
connection.setAttribute(
    name,
    new Attribute("MaxWorkers", 16)
);
\`\`\`

If only \`@ManagedOperation\` is audited, this action can be missed. Enforce controls in the setter or an appropriate audit layer to cover \`setAttribute\`.

One design approach is avoiding writable attributes for critical changes, replacing them with a \`@ManagedOperation\` that has explicit validation and auditing:

\`\`\`java
@ManagedOperation(description = "Change worker limit")
public void changeWorkerLimit(int value) {
    // Validate + authorization + audit + mutate.
}
\`\`\`

This is not a mandatory rule; writable attributes remain valid. The goal is ensuring all state-mutating paths carry the same required controls.

## 23. Retention, Integrity, and Audit Access

An audit log has value only when it is retrievable and trustworthy.

Define:

- **Retention**: how long records are kept per organizational/regulatory policy.
- **Access control**: who is allowed to view audit records.
- **Integrity**: restrict unauthorized edits/deletions; use append-only or immutable storage if needed.
- **Time synchronization**: keep node clocks synchronized and log UTC timestamps.
- **Correlation**: request ID, job ID, session ID, and instance ID.
- **Privacy**: record only necessary data; apply masking and proper retention.
- **Failure handling**: detect when the audit sink stops working.
- **Monitoring**: alert on sudden spikes in administrative actions or denied commands.

For critical actions, the audit trail should live outside the managed process or be shipped to a centralized system with appropriate retention policies. If written only to local logs and the container is deleted, evidence can disappear.

## 24. Common Mistakes

### 24.1. Assuming JMX Usernames Automatically Populate Spring Caller Context

A JMX connector may authenticate a principal, yet that does not guarantee every Spring method receives the identity in \`SecurityContextHolder\`. Spring Security HTTP context and the JMX security subject are two separate flows requiring deliberate integration.

### 24.2. Using IP Addresses as Operator Identities

An IP may belong to NAT, a proxy, a bastion, or an agent. It is useful connection metadata when from a trusted source, not proof of an individual.

### 24.3. Using Method-Parameter Usernames

That is a claimed identity and easily spoofed. Use it only as supplemental display info if needed, never in place of a verified actor.

### 24.4. Logging All Parameters

This can leak secrets, tokens, or personal data. Audit using field allowlists and strip sensitive payloads.

### 24.5. Recording SUCCESS Simply When the Method Returns

For asynchronous operations, that may only mean the request was accepted. Log the final job outcome separately.

### 24.6. Auditing Only JMX Invoke

This misses \`setAttribute\`, actions rejected by the security layer, and non-JMX state-changing paths.

### 24.7. Logging Only on the Client

Clients may be untrusted or fail to cover all entry points. Place server-side auditing at the proper boundary.

### 24.8. Attaching an Aspect While the Exporter Bypasses the Proxy

Advice may not run if the exporter holds the raw target directly. Test invocations through the actual MBeanServer.

## 25. JMX Audit Design Checklist

- [ ] Side-effecting MBean operations and writable attributes are classified.
- [ ] Appropriate authentication and authorization policies exist for the JMX connector.
- [ ] Actor is resolved explicitly from a trusted source, with \`UNKNOWN\` when indeterminable.
- [ ] OS user, IP, or client-supplied usernames are not used as verified identities.
- [ ] ObjectName, operation, signature, timestamp, outcome, and instance are recorded.
- [ ] Correlation ID/job ID exists for asynchronous actions.
- [ ] No secrets or sensitive payloads are written to audit logs.
- [ ] A mechanism exists to log DENIED events at the authorization layer.
- [ ] \`setAttribute\` is covered whenever it mutates state.
- [ ] Audit sink failures are handled according to criticality.
- [ ] Retention, integrity, and audit access policies are defined.
- [ ] Actual JMX call paths are integration-tested through the exporter/proxy.
- [ ] Remote JMX is open only to authorized clients with proper TLS/authentication.

## 26. Practice Scenario

**Context:** A Spring Boot application exposes MBean \`app.management:type=Scheduler,name=main\`. The JMX operation \`resume()\` is invoked through a bastion using a shared service account.

**Question A:** Can you record “Alice invoked resume” based solely on the \`jmx-admin\` account?

No. JVM-level auditing only knows the shared service account was used. Attributing an individual requires trustworthy session identity from the bastion/PAM and a correlation mechanism.

**Question B:** If \`resume()\` is permitted, yet the underlying task fails after running for 30 seconds, which outcome should be recorded?

If \`resume\` only enqueues work, the invocation audit should record \`ACCEPTED\`; once the worker finishes, it logs a \`COMPLETED\` or \`FAILED\` event linked by job ID.

**Question C:** If a caller is rejected by the JMX security layer before reaching the method, can auditing inside \`resume()\` record it?

No. DENIED events must be audited at the layer handling authentication/authorization.

**Question D:** If \`MaxWorkers\` is changed via \`setAttribute\`, does an aspect intercepting only \`@ManagedOperation\` cover it?

Not guaranteed. You must audit the setter/attribute-write or an appropriate security boundary.

## 27. Self-Check Questions

1. How does authentication differ from auditing?
2. Why is \`System.getProperty("user.name")\` insufficient as a verified actor?
3. When using a shared JMX account, can you prove which individual ran an operation?
4. Why must DENIED actions be recorded outside the management facade?
5. Is \`setAttribute\` an ordinary \`invoke\` operation?
6. Why should full \`params\` or \`Notification.userData\` not be logged?
7. How does auditing \`ACCEPTED\` differ from \`SUCCESS\`?
8. If remote JMX times out after an operation already ran, what issues can blind retries cause?
9. Why can an audit aspect be bypassed in a Spring AOP application?
10. What are the minimum fields to trace an administrative invocation?

## 28. Key Takeaways

\`\`\`text
JMX caller
    |
    +--> Authentication -> trusted identity/subject if available
    |
    +--> Authorization -> ALLOW / DENY
    |         |
    |         +--> Audit DENIED at security boundary
    |
    +--> MBean invocation / attribute write
              |
              v
        Management facade / service
              |
              +--> Audit request + actor + ObjectName + operation
              |
              +--> Business action
                       |
                       +--> SUCCESS / FAILED
                       +--> ACCEPTED -> later job outcome
\`\`\`

**Core principle:** auditing JMX administrative invocations must capture **the action, time, target resource, outcome, and identity with a clear trust level**. Do not assume every JMX invocation provides a user identity; do not treat shared credentials as individual identities; and do not treat notifications as a durable audit trail. Cover operations, writable attributes, denied actions, and asynchronous tasks—while keeping sensitive data out of audit logs.