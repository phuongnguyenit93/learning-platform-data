# Spring Framework JMX — Security proxies and operation invocation permissions

## 1. The problem: is a JMX operation truly protected by Spring Security?

Spring Framework JMX lets operations tools read state or invoke operations on a bean via \`MBeanServer\`. When an application uses Spring AOP and Spring Security method authorization, a crucial question arises:

**If a method is protected by \`@PreAuthorize\`, does a JMX call to \`@ManagedOperation\` automatically have to pass through the same permission check?**

You should not assume the answer is yes.

Proxy-based Spring Security method authorization operates when calls **pass through a Spring AOP proxy** carrying security advice. Meanwhile, a JMX exporter may read metadata from the target class and register the MBean in a way where the actual execution path is not identical to a normal business call. If an operation is called directly on the target or through an adapter that bypasses the proxy, the method-security interceptor may not run.

At the same time, a remote JMX call typically starts from a different thread/connector context than an HTTP request. A user authenticated with the JMX connector is not necessarily turned into an \`Authentication\` in Spring Security's \`SecurityContextHolder\`.

Therefore, you must distinguish **two independent protection layers**:

1. **JMX transport/server security:** who is allowed to connect to JMX and act on MBeans.
2. **Spring method security:** whether Java method calls pass through the security proxy and have an appropriate \`Authentication\`.

The goal of this lesson is to design a management API that does not bypass permission checks, protect dangerous operations, and verify behavior along the actual JMX call path.

\`\`\`text
JConsole / JMX client
       |
       v
JMX Connector (authentication / authorization / TLS)
       |
       v
MBeanServer.invoke(ObjectName, operation, parameters, signature)
       |
       v
Spring MBeanExporter / ModelMBean adapter
       |
       +-- path A: call target directly --> possible AOP bypass
       |
       +-- path B: call Spring AOP proxy --> method security advice
                                                |
                                                v
                                           business method
\`\`\`

**Key idea:** having a security annotation in source code does not prove a JMX invocation is authorized. You must know the actual object invoked by the MBean invoker, the proxy path, and the identity on the thread executing the operation.

## 2. Related components

| Component | Role |
|---|---|
| \`@ManagedResource\` | Marks a Spring bean as a JMX-managed resource |
| \`@ManagedOperation\` | Publishes a method as a JMX operation |
| \`MBeanExporter\` | Registers MBeans in \`MBeanServer\` |
| \`MBeanServer.invoke\` | Client entry point for invoking an operation |
| Spring AOP proxy | Intermediary object applying interceptors/advice |
| \`@EnableMethodSecurity\` | Enables method security in modern Spring Security |
| \`@PreAuthorize\` | Declares an authorization condition before calling a method |
| \`Authentication\` | Principal and authorities information in Spring Security |
| \`SecurityContextHolder\` | Stores security context per configured strategy, thread-bound by default |
| JMX remote connector | Connection path from client to \`MBeanServer\` |
| Management facade | Bean dedicated to exposing JMX and forwarding calls to business services via proxy |

Three concepts that are easy to confuse:

- **MBean registration:** the server has the \`ObjectName\` and the operation is exposed.
- **JMX authorization:** permissions at the connector/\`MBeanServer\` or a dedicated control layer for clients.
- **Spring method authorization:** security interceptor checking \`Authentication\` when a method call passes through the proxy.

They are related, yet **do not automatically replace one another**.

## 3. Java methods, AOP proxies, and JMX operations

Suppose you have a service:

\`\`\`java
package com.example.orders;

import org.springframework.security.access.prepost.PreAuthorize;

public class OrderAdministrationService {
    @PreAuthorize("hasAuthority('orders:retry')")
    public void retryFailedOrders() {
        // Retry failed orders.
    }
}
\`\`\`

If Spring Security method authorization is enabled and the caller obtains the Spring bean through an AOP proxy, the interceptor can check permissions before the method runs.

\`\`\`text
Spring caller --> proxy --> authorization advice --> target method
\`\`\`

However, a JMX client knows only the MBean and operation:

\`\`\`java
server.invoke(
    objectName,
    "retryFailedOrders",
    new Object[0],
    new String[0]
);
\`\`\`

The JMX contract does not mandate that the server find a Spring AOP proxy, extract a security context from an HTTP request, or evaluate \`@PreAuthorize\` expressions.

In practice, it depends on how the MBean is exported:
- Is the bean reference held by the exporter a proxy or the target?
- Is MBean metadata built from an interface or the target class?
- Does the operation exist on the proxy?
- Does the adapter use a call path that preserves AOP interceptors?
- Is there a valid \`Authentication\` on the thread executing the JMX call?

Therefore, a secure design must actively establish the security boundary rather than relying on annotations on the implementation taking effect automatically.

## 4. Dangerous case: JMX exports the target and bypasses the proxy

Simple example:

\`\`\`java
@ManagedResource(
    objectName = "com.example:type=OrderAdmin,name=primary"
)
public class OrderAdminTarget {

    @ManagedOperation(description = "Retry failed orders")
    @PreAuthorize("hasAuthority('orders:retry')")
    public void retryFailedOrders() {
        // ...
    }
}
\`\`\`

If the operation ultimately gets called through a proxy carrying a method-security advisor, the call can be controlled by \`@PreAuthorize\`. However, if an adapter or configuration exports the **target object directly**, the Spring Security interceptor never gets a chance to run.

Conceptual risk example:

\`\`\`java
Object target = ...; // raw object, not a Spring AOP proxy
exporter.setBeans(Map.of(
    "com.example:type=OrderAdmin,name=primary",
    target
));
\`\`\`

Having \`@PreAuthorize\` on a class **does not turn a raw object into something that self-enforces permission checks**. The annotation requires method-security infrastructure along with an appropriate invocation path.

This issue does not happen with security alone:
- \`@Transactional\` can also be bypassed.
- Retry/caching/logging advice may not be invoked.
- Metrics/audit relying on AOP proxies may fail to record.
- Self-invocation rules still apply.

**Do not use JMX as a shortcut around a business-service proxy** merely to call management methods faster.

## 5. JDK dynamic proxy and CGLIB proxy

### 5.1. JDK dynamic proxy

JDK proxies are interface-based.

\`\`\`java
public interface OrderMaintenance {
    void retryFailedOrders();
}
\`\`\`

\`\`\`java
public class OrderMaintenanceImpl implements OrderMaintenance {
    @Override
    @PreAuthorize("hasAuthority('orders:retry')")
    public void retryFailedOrders() {
        // ...
    }
}
\`\`\`

With a JDK proxy, Java clients usually interact through the \`OrderMaintenance\` interface. A JMX method to be invoked through the proxy must appear in an interface exposed by the proxy; if it exists only on the implementation class, the JMX adapter may fail to invoke it properly through the proxy.

This is distinct from having metadata:
- JMX annotations can be read on the target class.
- Yet the invocation path must have the method available on the proxy.
- If metadata publishes a method uncallable through the proxy, clients may receive invocation errors.

### 5.2. CGLIB class-based proxy

A class-based proxy is a subclass of the implementation in supported cases. It typically exposes class methods more broadly than a JDK proxy, yet still has limitations:

- \`final\` classes cannot be subclassed by standard CGLIB.
- \`final\` methods cannot be overridden to apply proxy advice.
- Private methods are not interception points for Spring proxy-based AOP.
- Self-invocation within the same target can bypass advice.

Do not switch the entire application to CGLIB just to "protect JMX". It is better to build a management facade and define a clear call path to the business service.

## 6. JMX threads and SecurityContext

In web applications, \`SecurityContextHolder\` is typically populated per request by security filters.

\`\`\`text
HTTP request -> Security filter chain -> SecurityContext -> Controller -> Service
\`\`\`

A remote JMX invocation does not necessarily pass through the HTTP security filter chain:

\`\`\`text
JMX connector thread -> MBeanServer.invoke -> MBean method
\`\`\`

Therefore, even when the JMX connector has authenticated an operator account, \`SecurityContextHolder.getContext().getAuthentication()\` may be \`null\` or fail to reflect the JMX client's principal.

Consequences:
- If the method-security proxy runs, \`@PreAuthorize\` may deny access due to missing \`Authentication\`.
- If the proxy is bypassed, there may be no check from method security at all.
- Do not assume a JMX username and a Spring Security principal represent the same identity.
- Do not synthesize an \`Authentication\` with top privileges for **every** JMX call just to get past \`@PreAuthorize\`.

If you need to integrate JMX identity with Spring Security, design a **trusted bridge** that validates mappings, binds permissions, and manages context explicitly per call. Do not treat a username passed as an operation parameter as a trustworthy identity source.

## 7. A management facade is an easily controlled boundary

Recommended design for applications with management operations:

\`\`\`text
JMX client
    |
    v
MBeanServer -> OrderJmxManagementFacade (Spring bean)
                    |
             explicit validation + audit
                    |
                    v
          OrderMaintenance interface
                    |
                    v
          Spring Security AOP proxy
                    |
            @PreAuthorize check
                    |
                    v
             business target
\`\`\`

The facade exports a small, meaningful API, while the business service is injected via Spring DI. This avoids directly exporting an implementation class containing many internal methods.

### 7.1. Service interface

\`\`\`java
package com.example.orders;

public interface OrderMaintenance {
    long getFailedOrderCount();
    void retryFailedOrders();
}
\`\`\`

### 7.2. Service implementation

\`\`\`java
package com.example.orders;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class OrderMaintenanceImpl implements OrderMaintenance {

    @Override
    public long getFailedOrderCount() {
        return 0L; // Replace with real data.
    }

    @Override
    @PreAuthorize("hasAuthority('orders:retry')")
    public void retryFailedOrders() {
        // Business operation.
    }
}
\`\`\`

For \`@PreAuthorize\` to take effect, the application must enable Spring Security method authorization and ensure the bean is called via a proxy, for example:

\`\`\`java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
\`\`\`

This is the annotation from \`org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity\` in Spring Security versions supporting that API.

### 7.3. JMX facade

\`\`\`java
package com.example.orders;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.app:type=OrderMaintenance,name=primary",
    description = "Operational controls for order maintenance"
)
public class OrderJmxManagementFacade {

    private final OrderMaintenance service;

    public OrderJmxManagementFacade(OrderMaintenance service) {
        this.service = service;
    }

    @ManagedAttribute(description = "Number of failed orders")
    public long getFailedOrderCount() {
        return service.getFailedOrderCount();
    }

    @ManagedOperation(description = "Retry failed orders")
    public void retryFailedOrders() {
        service.retryFailedOrders();
    }
}
\`\`\`

Spring configuration:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxExportConfiguration {

    @Bean
    public OrderJmxManagementFacade orderJmxManagementFacade(
            OrderMaintenance service) {
        return new OrderJmxManagementFacade(service);
    }
}
\`\`\`

When Spring injects the \`OrderMaintenance\` proxy into the facade, calling \`service.retryFailedOrders()\` passes through the proxy, so method-security advice executes **if the proper infrastructure is enabled and the method belongs to an interface exposed by the proxy**.

However, you still must answer **who creates the \`Authentication\` on the JMX thread**. This facade preserves the invocation path; it does not automatically translate JMX credentials into a Spring Security identity.

## 8. Enforcing permissions directly at the management boundary

When JMX is used as a separate control plane, you can design an authorization layer tailored for JMX rather than trying to reuse the HTTP security context.

Example of an abstract management policy:

\`\`\`java
public interface ManagementAuthorizer {
    void requirePermission(String permission);
}
\`\`\`

Facade:

\`\`\`java
@ManagedResource(
    objectName = "com.example.app:type=OrderMaintenance,name=primary"
)
public class SecuredOrderJmxFacade {

    private final ManagementAuthorizer authorizer;
    private final OrderMaintenance service;

    public SecuredOrderJmxFacade(
            ManagementAuthorizer authorizer,
            OrderMaintenance service) {
        this.authorizer = authorizer;
        this.service = service;
    }

    @ManagedOperation(description = "Retry failed orders")
    public void retryFailedOrders() {
        authorizer.requirePermission("orders:retry");
        service.retryFailedOrders();
    }
}
\`\`\`

\`ManagementAuthorizer\` in the example is an **application-defined** interface, not a built-in Spring API. Its implementation must rely on an identity reliably authenticated at the JMX boundary or in a managed execution environment.

If there is no reliable way to identify the caller, the safe policy is usually **deny by default**, or not exposing state-mutating operations via remote JMX.

Do not base security checks on parameters supplied by the caller:

\`\`\`java
@ManagedOperation
public void retryFailedOrders(String claimedRole) {
    if ("ADMIN".equals(claimedRole)) {
        // Unsafe: caller self-declares their role.
    }
}
\`\`\`

A client can pass \`"ADMIN"\` on its own; this is not authorization.

## 9. JMX connector permissions differ from Spring Security roles

For remote JMX, the server can configure:
- Authentication to identify who connects.
- Authorization at the JMX layer or via specific policies.
- Transport protection to secure credentials and data.
- Network restrictions to limit accessible endpoints.

These settings do not map one-to-one with a Spring Security authority like \`orders:retry\`.

For instance, a JMX account with broad remote management permissions may be allowed by the server to invoke an operation, yet the Spring Security proxy does not know who that account is. Conversely, someone with admin rights in an HTTP web UI does not automatically have JMX connector permissions.

Define specific operational roles:
- **Read-only monitoring:** querying status/metrics.
- **Runtime configuration:** changing bounded attributes.
- **High-impact administration:** controlled reset, delete, or reload actions.
- **Infrastructure administration:** broader connector/server actions.

Do not grant full JMX permissions to a monitoring account that only needs to read CPU and heap memory.

## 10. ObjectName and operation names are not permissions

\`ObjectName\` identifies the MBean:

\`\`\`text
com.example.app:type=OrderMaintenance,name=primary
\`\`\`

The operation name identifies the action:

\`\`\`text
retryFailedOrders()
\`\`\`

These two values are not authentication data. Knowing or guessing an \`ObjectName\` and operation name must never grant permission to invoke it.

Authorization must be enforced at the connector/\`MBeanServer\` or a trusted management facade. Similarly, \`@ManagedOperation(description="Admin only")\` adds descriptive metadata only; it does not block unauthorized callers.

Good design keeps the JMX contract small and auditable:
- Operation names reflect specific actions.
- Expose only operations genuinely needed for operations.
- Do not expose methods like \`deleteAllData\` without proper policy and permission controls.
- Do not let callers send Java class names or expressions for arbitrary code execution.

## 11. Self-invocation cases

Suppose:

\`\`\`java
public class JobService {

    public void runFromJmx() {
        executePrivilegedTask(); // this.executePrivilegedTask()
    }

    @PreAuthorize("hasAuthority('jobs:execute')")
    public void executePrivilegedTask() {
        // ...
    }
}
\`\`\`

In Spring proxy-based AOP, calling from \`runFromJmx\` to \`executePrivilegedTask\` on the same object typically **does not pass through the proxy**. Thus, method-security advice placed on \`executePrivilegedTask\` may not run.

Even if \`runFromJmx\` is invoked through a proxy, that does not automatically turn the internal call \`this.executePrivilegedTask()\` into a proxied call.

Remediation:
1. Extract the privileged method into another bean/service.
2. Inject that service into the facade via an interface.
3. Ensure cross-bean calls pass through the proxy.
4. Actually test that an unauthorized caller is rejected.

Do not use self-injection/\`AopContext\` arbitrarily, as it couples business code to proxy internals and can create circular dependencies.

## 12. Security context in asynchronous operations

A JMX operation may submit work to an executor:

\`\`\`java
@ManagedOperation
public void startReindex() {
    executor.execute(() -> indexService.reindex());
}
\`\`\`

If the JMX thread has a security context, do not assume the context propagates to worker threads. \`SecurityContextHolder\` uses thread-local semantics by default. To propagate it, design intentionally using appropriate Spring Security concurrency mechanisms or a controlled internal identity.

This becomes even more critical when:
- JMX operations run asynchronously.
- \`CompletableFuture\` switches threads.
- A scheduler performs the remainder after the JMX call returns.
- Auditing needs to record the original caller and approval context.

Do not copy an \`Authentication\` from an arbitrary request into background jobs. You must know where the caller identity comes from, its lifetime, and its delegation scope.

## 13. Authorization for operations with side effects

For operations like \`retryFailedOrders\`, \`clearQueue\`, \`resetCounters\`, \`shutdownWorker\`, define:

| Question | Design Requirement |
|---|---|
| Who may invoke? | Authenticated principal/role/permission |
| Via which channel? | Local JMX, authenticated remote JMX, or internal management service |
| What does the action affect? | Data, availability, resources, runtime state |
| What is valid input? | Validation and range limits |
| Can it be repeated? | Idempotency and retry policy |
| How is it logged? | Audit actor, operation, timestamp, outcome; do not expose secrets |
| How to check post-state? | Read-only attribute/metric or operation status |
| Is there a rate limit? | Rate limiting or operational policy at the boundary |

For instance, placing \`@PreAuthorize\` on a service does not solve all the questions above. The JMX endpoint must be restricted by network and authentication, operations need validation, and the path through the security proxy must be verified.

## 14. Checking the actual proxy with Spring AOP

Spring provides the \`AopUtils\` utility:

\`\`\`java
import org.springframework.aop.support.AopUtils;

Object bean = context.getBean("orderMaintenance");

System.out.println(
    "isAopProxy=" + AopUtils.isAopProxy(bean)
);
System.out.println(
    "isJdkDynamicProxy=" + AopUtils.isJdkDynamicProxy(bean)
);
System.out.println(
    "isCglibProxy=" + AopUtils.isCglibProxy(bean)
);
System.out.println(
    "targetClass=" + AopUtils.getTargetClass(bean).getName()
);
\`\`\`

If it is a JDK proxy, confirm the interface contains the method to call. If it is a class-based proxy, confirm the method can be intercepted by the proxy. However, \`isAopProxy=true\` **does not by itself prove the JMX exporter is calling that exact proxy**.

You also need an actual invocation test via \`MBeanServer.invoke\` or a JMX client using an account/identity representing an insufficiently privileged user.

## 15. Inspecting MBeanInfo before invoking operations

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.app:type=OrderMaintenance,name=primary"
);

if (server.isRegistered(name)) {
    MBeanInfo info = server.getMBeanInfo(name);

    for (var op : info.getOperations()) {
        System.out.print(op.getName() + "(");
        for (var param : op.getSignature()) {
            System.out.print(param.getType() + " ");
        }
        System.out.println(")");
    }
}
\`\`\`

This metadata determines which operations are actually published, yet **does not prove authorization is active**. An operation may appear in JConsole and still enforce permission checks on invocation; or conversely, be exposed unintentionally without security interception.

If the exporter uses an \`MBeanServer\` other than the platform server, you must inspect the exact server where the bean was registered. Avoid misdiagnosing a security issue when the client is actually connected to the wrong registry.

## 16. How to test JMX permissions end-to-end

A reliable test must create a scenario with an insufficiently privileged caller and verify the operation produces no side effects.

Example test plan:

1. Initialize the Spring context with method security enabled.
2. Register the management facade into a test-controlled \`MBeanServer\`.
3. Use a fake \`OrderMaintenance\` that records operation invocation counts.
4. Prepare an identity matching the JMX boundary's real authorization mechanism.
5. Call \`MBeanServer.invoke\` with insufficient permissions.
6. Verify the operation is rejected.
7. Verify the fake service **was not called** and state did not change.
8. Call with a sufficiently privileged identity.
9. Verify a single execution and that an audit entry was recorded.
10. Clean up MBean registrations when the test finishes.

Invocation skeleton:

\`\`\`java
ObjectName name = new ObjectName(
    "com.example.app:type=OrderMaintenance,name=primary"
);

server.invoke(
    name,
    "retryFailedOrders",
    new Object[0],
    new String[0]
);
\`\`\`

Do not treat just any \`SecurityException\` as sufficient proof. You must know whether the exception came from JMX connector authorization, the management authorizer, or the Spring Security method interceptor. Two separate layers may require independent tests.

For in-JVM integration tests, \`MBeanServer.invoke\` may not accurately reproduce a remote connector's caller identity. To verify remote security, test through the actual connector/transport and configured accounts.

## 17. Common mistakes and misconceptions

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Operation runs despite \`@PreAuthorize\` | Call bypasses AOP proxy or method security not enabled | Check invocation path, \`@EnableMethodSecurity\`, test deny |
| Operation is always denied from JMX | JMX thread lacks Spring \`Authentication\` | Design a trusted identity bridge or JMX-specific authorization |
| HTTP admin can invoke yet JMX cannot | Two different authentication/authorization systems | Distinguish HTTP roles from JMX permissions |
| JDK proxy missing operation | Method absent from proxy-exposed interface | Use a management interface or facade |
| CGLIB proxy fails to intercept method | \`final\`/private/self-invocation | Split components and verify method interception |
| Operation shows in JConsole yet invoke fails | Signature, authorization, or business exception | Inspect metadata and cause chain |
| Audit does not record JMX call | Advice bypassed or missing caller context | Log at management boundary and inspect proxy |
| Operation on another thread skips security | Async context propagation not designed | Use controlled propagation mechanisms |
| Remote JMX has overly broad permissions | Connector credentials/policy too permissive | Least privilege, network isolation, TLS |
| Sensitive operation exposed unintentionally | Assembler reflects too many public methods | Whitelist \`@ManagedOperation\`/management interface |

Do not fix authorization issues by silently granting \`ROLE_ADMIN\` to every JMX thread. That masks the lack of a trustworthy identity and introduces a privilege escalation vulnerability.

## 18. Practice exercises

### Exercise 1: Is an annotation on the target enough?

\`\`\`java
@PreAuthorize("hasAuthority('system:shutdown')")
public void shutdown() { /* ... */ }
\`\`\`

If the exporter exposes the raw target without calling through a Spring security proxy, does the annotation automatically block JMX clients?

**Answer:** No. Method security relies on AOP interception; if the call path bypasses the proxy, the annotation does not enforce permission checks on its own.

### Exercise 2: Identity on the JMX thread

An account with JMX connector permissions connects successfully. Can you assume \`SecurityContextHolder\` already holds a corresponding \`Authentication\`?

**Answer:** No. An explicitly designed bridge mechanism is required if you want to use JMX identity in Spring Security.

### Exercise 3: JDK proxy

\`\`\`java
interface Worker {
    void run();
}

class WorkerImpl implements Worker {
    public void run() {}

    @ManagedOperation
    public void resetQueue() {}
}
\`\`\`

Why might \`resetQueue\` not be callable through a JDK proxy?

**Answer:** The method is not in the interface exposed by the proxy. A suitable management interface or facade is needed.

### Exercise 4: Self-invocation

JMX method \`trigger()\` calls \`this.securedOperation()\`, while \`securedOperation\` has \`@PreAuthorize\`. Why might security advice fail to run?

**Answer:** Self-invocation in proxy-based Spring AOP generally does not pass through the proxy.

### Exercise 5: Secure facade

Design an \`IndexJmxFacade\` exposing only \`rebuildIndex()\`, inject \`IndexMaintenanceService\` through a Spring proxy, validate authorization at the management boundary, and verify via an integration test that an unauthorized caller leaves the index unchanged.

### Exercise 6: Risk assessment

Is \`@ManagedOperation(description = "Admin only")\` sufficient to protect \`deleteAllData()\`?

**Answer:** No. Description is metadata only; real authorization is required.

## 19. Checklist before taking an operation to production

1. Is invoking this operation via JMX genuinely necessary?
2. Does the JMX connector have proper authentication and authorization?
3. Does the remote endpoint have TLS/transport protection and network isolation?
4. Is the operation exported from the right owner bean/facade?
5. Do actual JMX calls pass through the Spring Security proxy if relying on \`@PreAuthorize\`?
6. Does the JMX thread have a trustworthy identity/\`Authentication\`?
7. Is missing authentication handled as deny by default?
8. For JDK proxies, is the method on the management interface?
9. For CGLIB, is the method \`final\` or restricted from interception?
10. Are self-invocation bypasses avoided?
11. Is there a test with an insufficiently privileged caller verifying state remains unchanged?
12. Are auditing, validation, and safe retry policies in place for operations with side effects?

## 20. Conclusion

Spring JMX and Spring Security AOP can coexist, yet authorization **is not automatically preserved merely because a bean carries \`@PreAuthorize\`**. Method security takes effect only when actual calls pass through the appropriate proxy/advice and an identity exists in the security context. The JMX connector has its own authentication/authorization system that does not convert into a Spring Security principal by default.

The resilient solution is to treat JMX as an independent management boundary: use connector security and least privilege, expose a small facade, call business services through Spring proxies, control identities from trusted sources, and test end-to-end using a JMX call with insufficient permissions.