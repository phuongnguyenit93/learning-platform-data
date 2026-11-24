# Reviewing ObjectName, Permissions, Lifecycle, and Registration Policy

> **Topic:** Spring Framework JMX  
> **Knowledge Group:** Design Review  
> **Lesson:** Reviewing ObjectName, Permissions, Lifecycle, and Registration Policy

## 1. Objectives

In Spring Framework JMX, an MBean must do more than simply show up in JConsole. Management design must also ensure stable identification, bounded access permissions, a clear lifecycle, and an intentional policy for handling duplicate registrations.

After this lesson, you will be able to:

- Evaluate ObjectName syntax, uniqueness, and contract stability.
- Distinguish JMX connection permissions from permissions to read attributes, write attributes, and invoke operations.
- Identify the exporter, ApplicationContext, and MBeanServer responsible for registration/unregistration.
- Compare `FAIL_ON_EXISTING`, `IGNORE_EXISTING`, and `REPLACE_EXISTING`.
- Recognize the risks when multiple contexts or multiple exporters share an MBeanServer.
- Write integration tests checking metadata, permissions, registration, shutdown, and conflicts.
- Create a review checklist and an operational troubleshooting runbook.

## 2. Review Model

A system may consist of:

```text
Spring ApplicationContext
       |
       +-- Business bean
       +-- Management facade
       +-- MBeanExporter
                |
                | ObjectName + RegistrationPolicy
                v
            MBeanServer
                |
       +--------+----------+
       |                   |
   Local client       Remote connector
                           |
                     JMX client
```

Four design axes must be evaluated together:

| Axis | Key Question | Warning Signs |
|---|---|---|
| ObjectName | Can clients identify the MBean stably? | Named after proxy class, duplicate names, changes after restart |
| Permissions | Who can read/write/invoke operations? | Monitoring account can invoke dangerous actions |
| Lifecycle | When is the MBean registered/unregistered? | Stale MBean or accidentally unregistered |
| Registration policy | Are conflicts handled intentionally? | IGNORE hides an old bean; REPLACE overwrites another module's MBean |

Do not just read annotations in source code: inspect the actual registry and metadata from the MBeanServer that clients use.

## 3. Start with an Inventory

Before reviewing, list:

1. Owning Spring ApplicationContext name and module.
2. Whether the implementation bean or a management facade is exported.
3. Which exporter performs the registration.
4. Which MBeanServer receives the registration.
5. The final ObjectName.
6. Exposed attributes, operations, and notifications.
7. Consuming clients, including dashboards, JConsole, agents, or automation.
8. Lifecycle, policy, and contract change process.
9. Local/remote access path, authentication, and authorization approach.
10. Data sensitivity and side effects.

Example:

| MBean | Owner | ObjectName | Expected Permissions |
|---|---|---|---|
| Orders queue | Orders module | app.management:type=Queue,name=orders | Read depth; operator may pause |
| Product cache | Catalog module | app.management:type=Cache,name=products | Read hit ratio; controlled refresh |
| Worker pool | Worker module | app.management:type=WorkerPool,name=main | Read active count; bounded resize |

The inventory must record the exact server. Two different JVMs or two different MBeanServers can share the same ObjectName without conflict.

## 4. ObjectName Is a Management Contract

A JMX ObjectName consists of a domain and key properties:

```text
app.management:type=Cache,name=products
```

Here the domain is `app.management`; `type` describes the resource; `name` distinguishes the logical instance.

```java
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "app.management:type=Cache,name=products"
);

System.out.println(name.getDomain());
System.out.println(name.getCanonicalName());
```

A durable name should:

- Be meaningful to operators.
- Distinguish instances that genuinely need distinguishing.
- Not depend on class names, package names, or AOP-generated proxies.
- Not contain secrets, tokens, emails, or personal data.
- Not change arbitrarily during implementation refactoring.
- Not embed request IDs or timestamps creating unbounded cardinality.
- Follow a consistent organization-wide domain, type, and name convention.

Poor name:

```text
com.example.internal:type=RedisProductCacheServiceImpl
```

Logical resource name:

```text
app.management:type=Cache,name=products
```

Switching from a Redis implementation to Caffeine does not need to force clients to change ObjectName if the management contract is preserved.

## 5. Scope of Uniqueness

Each MBeanServer allows only one registration under a given ObjectName at a time.

```text
Server A:
  app.management:type=Queue,name=orders -> Queue A

Server B:
  app.management:type=Queue,name=orders -> Queue B
```

These two registrations are valid because they are on different servers.

However, within the same Server A, two beans simultaneously claiming `app.management:type=Queue,name=orders` will cause a conflict.

The following two key orderings describe the same ObjectName:

```text
app.management:type=Queue,name=orders
app.management:name=orders,type=Queue
```

You can compare them:

```java
ObjectName first = new ObjectName(
    "app.management:type=Queue,name=orders"
);
ObjectName second = new ObjectName(
    "app.management:name=orders,type=Queue"
);

System.out.println(first.equals(second)); // true
```

Do not determine uniqueness by manual string comparison. Use `ObjectName.equals` or the canonical name.

## 6. Naming in Multi-Module Applications

Two modules both using `type=Queue` should have a distinguishing key:

```text
app.management:type=Queue,name=orders
app.management:type=Queue,name=payments
```

If multiple Spring contexts manage a single logical queue, clearly decide whether one context is the sole owner or each instance must have its own ObjectName.

An additional context or instance key can be used when genuinely needed:

```text
app.management:type=Queue,name=orders,context=primary
```

Do not automatically append a PID or UUID to every name to dodge conflicts. That can force clients to rediscover ObjectNames after every restart. Only use instance identity when operations genuinely need to manage each instance independently.

## 7. Verifying the Actual ObjectName

With an `MBeanServerConnection` pointing to the right registry:

```java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import java.util.Set;

Set<ObjectName> names = connection.queryNames(
    new ObjectName("app.management:*"),
    null
);

for (ObjectName actual : names) {
    System.out.println(actual.getCanonicalName());
}
```

When an MBean is missing, check:

- Was the bean created by Spring?
- Is the exporter enabled?
- Does the name declared in `@ManagedResource` or `setBeans` match the name being queried?
- Does `ObjectNamingStrategy` produce a different name?
- Does the exporter use a custom MBeanServer?
- Was a registration error masked by a policy?
- Is the client connected to the right JVM?

Do not rush to change annotations when the root cause is the wrong server or remote connector URL.

## 8. MBeanInfo Is the Published Surface

Having many public methods on a bean does not mean every method belongs in JMX.

```java
import javax.management.MBeanInfo;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanOperationInfo;

MBeanInfo info = connection.getMBeanInfo(name);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "%s %s read=%s write=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println(operation.getName());
}
```

A full review also requires comparing parameter signatures and return types. For example, `resize(int)` and `resize(long)` are not the same JMX operation signature.

An illustrative contract allowlist:

```text
Attributes:
  PendingCount : int  read-only
  ActiveCount  : int  read-only
  MaxWorkers   : int  read-write

Operations:
  pause()  : void
  resume() : void
```

Any attribute/operation outside the allowlist must be justified and approved through the design process.

## 9. Reviewing Access Permissions

Permissions are evaluated across multiple layers:

```text
Network:
  Can the client reach the JMX endpoint?

Authentication:
  What identity has the client proven?

Authorization:
  What can that identity read, write, or invoke?

Business validation:
  Are inputs and side effects within bounds?
```

Spring Security HTTP filters do not automatically protect remote JMX/RMI. A client inside the same JVM can also call `MBeanServer` directly without going through the remote connector.

Therefore, do not place all controls solely on the JMX port. Critical invariants such as maximum worker count, preventing deletion of sensitive data, and controlling business actions must be enforced in the appropriate service/facade.

## 10. Role Separation and Least Privilege

| Role | Read | Write | Invoke |
|---|---|---|---|
| Monitoring reader | Safe attributes per allowlist | No | No, except approved read-only actions |
| Operator | Operational data | Selected bounded settings | Appropriate pause/resume/reload |
| Automation account | Goal-specific metrics | Restricted | Specific commands with rate limit and audit |
| Administrator | Per policy | Per policy | Per policy |
| Unknown caller | No | No | No |

The JDK management agent can support an access-control file with read-only/read-write permissions depending on version, but that level does not guarantee per-operation authorization. When fine-grained roles and policies are needed, use a controlled authorization layer or gateway combined with allowlists and server-side validation.

Do not assume every account that can connect to JMX is allowed to invoke every operation.

## 11. Reviewing Sensitive Attributes

Examples that should NOT be exposed:

```java
@ManagedAttribute
public String getDatabasePassword() {
    return password;
}
```

Or:

```java
@ManagedOperation
public String dumpAllEnvironmentVariables() {
    // ...
}
```

Even read-only attributes can leak secrets, user metadata, or sensitive configuration.

Prefer aggregated status:

```java
@ManagedAttribute
public boolean isDatabaseHealthy() {
    return healthProbe.isHealthy();
}
```

For diagnostics, return only necessary details, with redaction and appropriate permission limits. Never use "internal network" as an excuse to skip security.

## 12. Writable Attributes and Operations Need Validation

Example of a bounded setter:

```java
@ManagedAttribute
public void setMaxWorkers(int requested) {
    if (requested < 1 || requested > 64) {
        throw new IllegalArgumentException(
            "requested must be between 1 and 64"
        );
    }

    workerCoordinator.setMaxWorkers(requested);
}
```

The `1..64` range is just an example and must be tuned to the real system.

A review must answer:

1. Who is allowed to make changes?
2. What is the valid value range?
3. Is the operation idempotent?
4. Can the action be reversed?
5. If the connection drops after server execution, how does the client learn the outcome?
6. Is it audited?
7. Are there concurrency/rate limits?

JMX does not automatically provide retries/idempotency for side-effecting operations.

## 13. Remote JMX Connectors Are Not Auto-Created by the Exporter

Spring annotation-based export only registers MBeans into the appropriate server.

```java
@Configuration
@EnableMBeanExport
public class JmxConfig {
}
```

It does not open a remote RMI port by default.

A remote JMX connector uses separate configuration, such as the JDK management agent or an application-managed `JMXConnectorServer`. You must verify:

- Registry port and RMI connector endpoint port.
- Hostname advertised by RMI.
- Firewall/security group/NetworkPolicy.
- Authentication and authorization.
- TLS/truststore/keystore if required.
- The actual MBeanServer exposed by the connector.

Do not open JMX ports to the public Internet to work around JConsole connectivity issues. Prefer a private management network and least-privilege access.

## 14. Auditing Administrative Actions

An operation like `pauseWorkers()` can affect a running service.

An audit event should contain:

```json
{
  "event": "jmx.operation",
  "objectName": "app.management:type=WorkerPool,name=orders",
  "operation": "pause",
  "actor": "verified-operator-id",
  "actorSource": "authenticated-connector",
  "outcome": "SUCCESS",
  "requestId": "ops-124"
}
```

This is an illustrative schema built by the application, not a built-in Spring JMX structure.

Do not treat OS user, IP, or a client-supplied `requestedBy` parameter as proof of operator identity. If shared JMX credentials are used, audit logs may only know the service account.

Record actions denied at the security layer, operations failing in business code, and asynchronous operations that were only accepted so far.

## 15. Registration and Unregistration Lifecycle

A simple lifecycle:

```text
Spring context refresh
        |
        v
Managed bean initialized
        |
        v
MBeanExporter registers MBean
        |
        v
MBeanServer serves clients
        |
        v
Context shutdown
        |
        v
Exporter unregisters owned MBeans
```

Detailed ordering depends on the exporter, lifecycle hooks, BeanPostProcessors, and Spring version.

A review must specify who owns the MBean, when it becomes ready, and when it is destroyed. Do not assume an MBean created by one context is automatically managed by all other contexts in the same JVM.

## 16. Startup Issues

Startup failures may include:

- Bean was not scanned/initialized.
- Exporter is disabled or points to the wrong MBeanServer.
- MBean registers before dependencies are ready.
- Multiple exporters register the same ObjectName.
- Proxy interface hides the method to export.
- Metadata assembler does not recognize annotations.
- Registration policy silently ignores the new bean.

A technical probe:

```java
ObjectName name = new ObjectName(
    "app.management:type=Queue,name=orders"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException(
        "MBean not registered: " + name
    );
}
```

Then inspect `MBeanInfo` and read a safe read-only attribute. `isRegistered=true` is not enough to prove the right implementation or contract.

## 17. Shutdown Issues

When a context stops, the exporter typically unregisters the registrations it manages.

Scenarios to test:

- Does the MBean disappear after the context closes?
- Is an MBean belonging to another module accidentally unregistered?
- Are `NotificationListener`s removed?
- Does a replaced MBean cause the old exporter's cleanup to affect the new exporter?
- How does a client holding a proxy to the old ObjectName handle `InstanceNotFoundException`?
- Do any stale registrations remain after restart?

Swapping the underlying object inside an MBean does not guarantee old listeners, state, or identity automatically transfer to the new object.

## 18. Spring's RegistrationPolicy

The policies:

```java
import org.springframework.jmx.support.RegistrationPolicy;
```

| Policy | When ObjectName Exists | Purpose |
|---|---|---|
| `FAIL_ON_EXISTING` | Reports registration conflict | Detect naming/ownership bugs |
| `IGNORE_EXISTING` | Skips new registration | Intentionally keep the existing MBean |
| `REPLACE_EXISTING` | Replaces old registration | Controlled replacement |

Example:

```java
MBeanExporter exporter = new MBeanExporter();

exporter.setRegistrationPolicy(
    RegistrationPolicy.FAIL_ON_EXISTING
);
```

This snippet is not a complete exporter; server/bean mappings must be configured and Spring must manage its lifecycle.

`RegistrationPolicy` only handles conflicts at registration time; it does not provide transactions, ownership transfer, compatibility, or high availability.

## 19. Why FAIL_ON_EXISTING Is Often Useful

An ObjectName conflict can reveal:

- Two modules using the same logical name.
- Overlap between Spring Boot auto-configuration and a manual exporter.
- Two ApplicationContexts exporting the same bean.
- An overly broad naming strategy.
- An old MBean that was not cleaned up.
- Another library already claiming the name.

If a conflict is a bug, `FAIL_ON_EXISTING` catches it early instead of silently ignoring or overwriting the old MBean.

Do not use IGNORE/REPLACE just to make startup errors disappear before establishing legitimate ownership.

## 20. IGNORE_EXISTING Can Retain an Old Version

Example:

```text
Old MBean:
  ObjectName X -> version=1

New exporter:
  ObjectName X -> version=2
  policy=IGNORE_EXISTING
```

If the old MBean remains, the new exporter skips registration. Clients may still see `version=1`.

Therefore, in addition to checking `server.isRegistered(name)`, read an identifying attribute or metadata to confirm registration of the right version/instance:

```java
Object version = server.getAttribute(
    name,
    "Version"
);
```

The `Version` field is an illustrative attribute and must be exposed by the actual MBean; do not assume every MBean has it.

## 21. What Are the Risks of REPLACE_EXISTING?

Scenario:

```text
Context A registers MBean A
           |
Context B replaces with MBean B
           |
Context A closes
```

Risks:

- Clients see a window where the ObjectName is unregistered.
- Notification listeners attached to the old MBean do not automatically transfer.
- The new MBean may have different metadata; old clients may fail.
- State from the old MBean does not automatically migrate to the new MBean.
- Cleanup of the old exporter may impact the live registration depending on ownership/lifecycle.
- An unintended exporter can overwrite a critical MBean.

`REPLACE_EXISTING` is not an atomic hot swap or a failover tool. Use it only with an explicit replacement design and integration tests covering multiple contexts.

## 22. Hands-On Exercise with Two Beans Sharing an ObjectName

Create a Standard MBean:

```java
public interface CounterMBean {
    int getValue();
}

public class Counter implements CounterMBean {
    private final int value;

    public Counter(int value) {
        this.value = value;
    }

    @Override
    public int getValue() {
        return value;
    }
}
```

Dedicated test server:

```java
MBeanServer server =
    MBeanServerFactory.newMBeanServer("review.test");

ObjectName name = new ObjectName(
    "app.management:type=Counter,name=shared"
);
```

Register `Counter(10)` first, then let Spring `MBeanExporter` attempt to register `Counter(20)` under the same ObjectName. Run each policy in an isolated test:

| Policy | Expected Result |
|---|---|
| `FAIL_ON_EXISTING` | Error; old value remains 10 without other cleanup |
| `IGNORE_EXISTING` | Keeps 10 |
| `REPLACE_EXISTING` | Replaced with 20 if new registration succeeds |

Do not run replacement experiments on a platform MBeanServer holding live operational data.

## 23. Testing Lifecycle with a Spring Test

Conceptual example:

```java
MBeanServer server =
    MBeanServerFactory.newMBeanServer("lifecycle.test");

ObjectName name = new ObjectName(
    "app.management:type=WorkerPool,name=main"
);

// Spring context configured with an exporter using the server above.
AnnotationConfigApplicationContext context =
    new AnnotationConfigApplicationContext();

context.register(TestJmxConfiguration.class);
context.refresh();

assertTrue(server.isRegistered(name));

context.close();

assertFalse(server.isRegistered(name));
```

This snippet is a skeleton requiring `TestJmxConfiguration` and proper dependency injection. Ensure the configuration actually uses the created `server` instance. If the server is created inside the context, the test must retrieve that exact `MBeanServer` bean after refresh.

Do not apply a simple unregister assertion to an MBean owned by another component or replaced by another exporter. Ownership must be built into test expectations.

## 24. Managing Notification Listener Lifecycle

If an MBean emits notifications:

- When is the listener registered?
- Is the listener attached to the right ObjectName?
- When the MBean is unregistered, is the listener cleaned up?
- When the MBean is replaced, is the listener re-registered?
- Are events lost during downtime?
- Are duplicate notifications handled?

Notifications do not provide storage/replay by default. Do not use a listener as the sole audit trail for critical actions.

## 25. Proxies and Metadata

Spring AOP can cause an exported bean to be a JDK dynamic proxy or a class-based proxy.

```java
Object bean = context.getBean("workerManagement");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.getTargetClass(bean));
```

A JDK proxy may only expose methods on interfaces. Annotations placed on the implementation may be handled by the metadata assembler depending on version/configuration rules, but do not assume every implementation method is invocable through the proxy.

Reviews should check both `MBeanInfo` and actual invocation, not just annotation presence.

A separate management facade usually lowers the risk of accidentally exposing service methods and keeps the ObjectName independent of implementation.

## 26. Quick Verification Snippet

```java
ObjectName name = new ObjectName(
    "app.management:type=WorkerPool,name=main"
);

if (!connection.isRegistered(name)) {
    throw new IllegalStateException("Missing MBean");
}

MBeanInfo info = connection.getMBeanInfo(name);

for (MBeanAttributeInfo a : info.getAttributes()) {
    System.out.println(
        a.getName() +
        " readable=" + a.isReadable() +
        " writable=" + a.isWritable()
    );
}

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.println(
        "operation=" + op.getName()
    );
}
```

Verify that `connection` points to the exact server the exporter uses. This is a technical contract check, not a substitute for security testing with real accounts.

## 27. Design Matrix

| Finding | Concern Level | Mitigation |
|---|---|---|
| MBean named after proxy class | High | Use logical naming |
| Two modules use the same ObjectName | High | Fix naming/ownership |
| Monitoring account invokes state-changing operation | High | Restrict permissions |
| Read-only attribute returns secret | High | Do not expose / mask |
| IGNORE hides old MBean | Medium–high | Review owner and deployment |
| REPLACE lacks lifecycle tests | High | Add integration tests |
| MBean exists but misses operation | Medium | Check assembler/proxy |
| Client connects to wrong MBeanServer | Medium | Align exporter/connector |
| Listener not cleaned up | Medium–high | Manage lifecycle |
| No audit for dangerous commands | High | Add boundary auditing |

Concern levels are directional guidelines; organizations should calibrate them to real risk and impact.

## 28. Review Scenario

An application has `orders` and `payments` modules, both creating a `QueueMonitor` under ObjectName:

```text
app.management:type=Queue
```

Startup fails with a duplicate name error; the developer switches the policy to `REPLACE_EXISTING` to silence the error.

Review questions:

1. Are the two queues two distinct resources?
2. Do they need separate ObjectNames?
3. Same MBeanServer or different servers?
4. Are dashboards already reading the old name?
5. Who owns the MBean and its registration lifecycle?
6. Which accounts may pause/resume each queue?
7. If the `payments` context closes, will the `orders` MBean be affected?
8. Does REPLACE have a legitimate purpose here?

If both queues must coexist simultaneously, change them to:

```text
app.management:type=Queue,name=orders
app.management:type=Queue,name=payments
```

instead of letting two exporters fight over one ObjectName. Once names no longer collide, registration policy stops being a naming workaround.

## 29. Handover Checklist

- [ ] Inventory exists for MBeans, exporters, servers, owners, and clients.
- [ ] ObjectNames are valid, logical, stable, and unique per server.
- [ ] No tokens/PII appear in ObjectNames.
- [ ] `MBeanInfo` matches the approved contract.
- [ ] Only necessary attributes and operations are exposed.
- [ ] Writable attributes have validation.
- [ ] Remote JMX connector has network restrictions, authentication, and TLS.
- [ ] Authorization separates read/write/operation as needed.
- [ ] Auditing is in place for side-effecting operations.
- [ ] Startup exhibits no unintended registration conflicts.
- [ ] Context shutdown cleans up owned registrations properly.
- [ ] Multiple exporters/contexts do not unintentionally overwrite each other's names.
- [ ] Purpose of IGNORE/REPLACE is clearly documented.
- [ ] Tests exist for ObjectName collision scenarios.
- [ ] Notification listener lifecycle is managed.
- [ ] Runbook exists for investigating when a client cannot find an MBean.

## 30. Self-Check Questions

1. Is ObjectName unique per JVM or per MBeanServer?
2. Why do implementation-class-based names easily cause breaking changes?
3. Does a read-only attribute automatically mean it is safe?
4. Do Spring Security HTTP filters protect JMX RMI by default?
5. Which MBean does `IGNORE_EXISTING` keep when names collide?
6. Does `REPLACE_EXISTING` automatically transfer state/notification listeners?
7. What is the risk when closing the old context after a replacement?
8. Is `isRegistered=true` enough to prove the right implementation?
9. How do you verify that exporter and connector use the same server?
10. Why are integration tests needed for both registration and shutdown?

## 31. Key Takeaways

```text
ObjectName:
  logical + stable + unique + non-sensitive

Permissions:
  least privilege + network isolation
  + authentication + authorization + audit

Lifecycle:
  register at the right time
  unregister by the right owner
  avoid stale and duplicate registrations

RegistrationPolicy:
  FAIL   -> detect conflicts
  IGNORE -> keep old MBean
  REPLACE -> replace old MBean, must manage risks
```

**Conclusion:** A reliable Spring JMX design must clearly answer four questions: what the MBean is named, who can access it, who manages its lifecycle, and what happens when the ObjectName already exists. Never use a registration policy to mask faulty naming or bypass security. Verify via real metadata, access control, integration tests, and an operational plan.
