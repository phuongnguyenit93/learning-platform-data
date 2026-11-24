# Spring Framework JMX — Autodetection on Proxied Beans

## 1. The Problem to Understand

Spring Framework allows exporting beans to JMX via \`MBeanExporter\`. One useful mode is **autodetection**: the exporter finds eligible beans in the \`ApplicationContext\` instead of forcing us to list each bean in \`setBeans\`.

However, the actual bean managed by Spring is not always a direct instance of the business class. Spring AOP can wrap a **proxy** around a bean to apply transactions, caching, security, retries, or other advice. Therefore, when the JMX exporter finds and inspects a bean, it may encounter:

- An executing object of class \`OrderService\`.
- A JDK proxy implementing only the \`OrderOperations\` interface.
- A subclass-style proxy created by CGLIB.
- Metadata annotations located on the implementation class rather than directly on the proxy.
- Methods described in JMX from the target class, while actual invocations must go through the proxy.

The topic “autodetection on proxied beans” is about how Spring JMX **detects the right MBean, retrieves the right metadata, invokes the right methods, and preserves important interceptors** when a bean is proxied.

\`\`\`text
Spring ApplicationContext
       |
       +---- orderService (Spring bean name)
                      |
                 AOP proxy
                 /       \
             JDK proxy   class-based proxy
                 \       /
                  target OrderService
                      |
            @ManagedResource / @ManagedOperation
                      |
             Spring MBeanExporter
            autodetect + assembler
                      |
              ModelMBean / MBeanServer
                      |
                    JConsole
\`\`\`

This lesson clearly distinguishes: **whether a bean is selected for export** and **whether operations are invoked through the proxy or through the target** are two different questions. Both must be resolved properly.

## 2. Fundamental Concepts

| Concept | Meaning |
|---|---|
| \`MBeanExporter\` | Spring component that registers beans into \`MBeanServer\` |
| Autodetection | Automatically selecting certain beans for export based on configured mechanisms and metadata |
| \`@ManagedResource\` | Spring annotation marking a managed resource |
| \`@ManagedAttribute\` | Marks a getter/setter to expose as a JMX attribute |
| \`@ManagedOperation\` | Marks a method to expose as a JMX operation |
| \`MetadataMBeanInfoAssembler\` | Builds MBean metadata based on annotation information |
| AOP proxy | Intermediary object receiving calls and running interceptors/advice |
| JDK dynamic proxy | Proxy based on Java interfaces |
| CGLIB class-based proxy | Proxy creating a subclass of the target class under supported conditions |
| Target class | The underlying business implementation class behind the proxy |
| \`ObjectName\` | MBean identifier in the JMX registry |

A Spring bean can simultaneously have the name \`orderService\`, a runtime object that is a JDK proxy, and a business class of \`OrderServiceImpl\`. Looking only at \`proxy.getClass()\` can miss annotations declared on the implementation class.

## 3. Where Does Spring JMX Autodetection Work?

\`MBeanExporter\` is responsible for exporting MBeans. When autodetection is enabled with proper configuration, it iterates through candidate beans and uses a strategy/assembler to decide which beans can be exposed as JMX resources.

In Spring, annotation-driven export is commonly enabled via:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
\`\`\`

This option sets up annotation-based infrastructure. Beans annotated with \`@ManagedResource\` and appropriate metadata become export candidates.

Explicit configuration approach:

\`\`\`java
import org.springframework.jmx.export.MBeanExporter;

MBeanExporter exporter = new MBeanExporter();
exporter.setAutodetect(true);
\`\`\`

However, **merely enabling \`setAutodetect(true)\` does not mean every POJO is selectively exported by annotations**. You need to configure the appropriate \`MBeanInfoAssembler\` and \`ObjectNamingStrategy\` if relying on Spring metadata; also verify the exact mechanism of the Spring version in use. For annotation-based applications, \`@EnableMBeanExport\` typically reduces this complexity.

The MBean exporter can also accept \`setBeans(Map)\` to register specific beans. Autodetection and explicit mapping are two different ways to select beans; proactively define scope to avoid duplicate registrations.

## 4. Why Do AOP Proxies Complicate Autodetection?

Suppose a bean:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.app:type=OrderService,name=primary"
)
public class OrderServiceImpl {

    @ManagedOperation(description = "Reprocess failed orders")
    public void reprocessFailedOrders() {
        // ...
    }
}
\`\`\`

When Spring creates the bean, a \`BeanPostProcessor\` may replace that object with a proxy. For instance, if a method has \`@Transactional\` or the class matches an applicable aspect, callers receive the proxy instead of the direct target object.

With a JDK proxy:
- The runtime object is typically a JDK-generated proxy class, not \`OrderServiceImpl\`.
- The proxy only exposes methods present in the interfaces it implements (plus relevant Object methods).
- The \`@ManagedResource\` annotation on \`OrderServiceImpl\` does not automatically appear as a direct annotation on the runtime proxy class.
- Spring needs a mechanism to resolve the appropriate target class/metadata to identify the resource.

With a class-based proxy:
- The runtime proxy subclasses the business class, so it generally exposes more of the class's methods.
- However, annotation resolution, method interception, and rules for final/private methods still must be understood.
- Do not assume using CGLIB eliminates all AOP/JMX limitations.

Therefore, solid autodetection must understand **beans inside the Spring container** rather than simply checking \`bean.getClass().isAnnotationPresent(ManagedResource.class)\`.

## 5. JDK Dynamic Proxy Example: Interface and Implementation

Define the interface:

\`\`\`java
package com.example.jmx;

public interface OrderMaintenance {
    long getFailedOrders();
    void retryFailedOrders();
}
\`\`\`

Implementation with JMX annotations:

\`\`\`java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicLong;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.app:type=OrderMaintenance,name=primary",
    description = "Runtime order maintenance"
)
public class OrderMaintenanceImpl implements OrderMaintenance {
    private final AtomicLong failedOrders = new AtomicLong();

    @Override
    @ManagedAttribute(description = "Failed order count")
    public long getFailedOrders() {
        return failedOrders.get();
    }

    @Override
    @ManagedOperation(description = "Retry failed orders")
    public void retryFailedOrders() {
        // Business call, potentially wrapped in transaction.
    }
}
\`\`\`

In Spring configuration:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class ManagementConfig {

    @Bean
    public OrderMaintenance orderMaintenance() {
        return new OrderMaintenanceImpl();
    }
}
\`\`\`

**Important:** \`@EnableAspectJAutoProxy\` only enables AOP infrastructure; it does not automatically create a proxy for a bean unless an applicable advisor/aspect applies. To actually get a JDK proxy, a matching advice/transactional configuration is required and Spring decides to use an interface-based proxy.

For example, you can put \`@Transactional\` on a business method (when transaction management is enabled), or define an aspect matching \`execution(* ...)\`. How AOP is applied does not change the requirement that the JMX exporter must handle target-class metadata and proxy invocation paths properly.

### Design Question

If \`retryFailedOrders()\` is not declared in the \`OrderMaintenance\` interface, the JDK proxy will not have that public method. Even if the target class has \`@ManagedOperation\`, invoking via the proxy may not work as expected. Therefore, management operations meant to be invoked through a JDK proxy should **exist in an interface exposed by the proxy**, or the application needs a management facade or different proxy strategy.

## 6. How to Inspect the Actual Proxy Yourself

A simple approach is using Spring AOP utilities:

\`\`\`java
import org.springframework.aop.support.AopUtils;

Object bean = applicationContext.getBean("orderMaintenance");

System.out.println("isAopProxy=" + AopUtils.isAopProxy(bean));
System.out.println("isJdkDynamicProxy="
    + AopUtils.isJdkDynamicProxy(bean));
System.out.println("isCglibProxy="
    + AopUtils.isCglibProxy(bean));
System.out.println("runtimeClass=" + bean.getClass().getName());
System.out.println("targetClass="
    + AopUtils.getTargetClass(bean).getName());
\`\`\`

These utilities classify common proxies created by Spring AOP. For custom proxies or objects that are not Spring AOP proxies, consult the documentation of the corresponding proxy mechanism.

When \`isJdkDynamicProxy=true\`, inspect the interfaces the proxy actually implements and the JMX operations that must be invoked. When \`isCglibProxy=true\`, check whether methods can be overridden/intercepted and whether annotations are found by the assembler.

Do not cast a JDK proxy to the implementation class:

\`\`\`java
OrderMaintenanceImpl concrete =
    (OrderMaintenanceImpl) applicationContext.getBean("orderMaintenance");
\`\`\`

This can throw \`ClassCastException\`. Instead, use the interface:

\`\`\`java
OrderMaintenance management =
    applicationContext.getBean(OrderMaintenance.class);
\`\`\`

## 7. Role of the Metadata Assembler and Naming Strategy

When exporting annotated POJOs, there are usually two key components:

- \`MetadataMBeanInfoAssembler\`: finds JMX metadata to build attribute/operation information.
- \`MetadataNamingStrategy\` or an appropriate naming strategy: determines the resource's ObjectName.

Illustrative configuration example:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Bean
AnnotationJmxAttributeSource annotationJmxAttributeSource() {
    return new AnnotationJmxAttributeSource();
}

@Bean
MetadataMBeanInfoAssembler jmxAssembler(
        AnnotationJmxAttributeSource source) {

    MetadataMBeanInfoAssembler assembler =
        new MetadataMBeanInfoAssembler();
    assembler.setAttributeSource(source);
    return assembler;
}

@Bean
MetadataNamingStrategy namingStrategy(
        AnnotationJmxAttributeSource source) {

    MetadataNamingStrategy strategy =
        new MetadataNamingStrategy();
    strategy.setAttributeSource(source);
    return strategy;
}

@Bean
MBeanExporter exporter(
        MetadataMBeanInfoAssembler assembler,
        MetadataNamingStrategy namingStrategy) {

    MBeanExporter exporter = new MBeanExporter();
    exporter.setAssembler(assembler);
    exporter.setNamingStrategy(namingStrategy);
    exporter.setAutodetect(true);
    return exporter;
}
\`\`\`

The configuration above is meant to illustrate extension points. If the application also uses \`@EnableMBeanExport\`, there is a risk of creating multiple exporters both trying to register the same bean. In an application, choose **one primary export mechanism**, or clearly separate bean scopes between exporters.

When a bean is proxied, both components above need to receive valid metadata; if ObjectName succeeds while operation metadata is missing, diagnose the assembler/method exposure rather than naming alone.

## 8. AOP and the Issue of Choosing Target vs. Proxy for Export

A common mistake is “so JMX sees the annotation on the real class, let's just grab the target and export it directly”. This can lose AOP behavior.

Suppose:

\`\`\`java
@Transactional
public void retryFailedOrders() {
    // Write DB, send command, change state.
}
\`\`\`

In a Spring application, transaction interceptors usually sit on the **proxy invocation path**. If a JMX operation calls the target directly bypassing the proxy, transactional advice may not run. Similar issues can occur with security checks, metrics, retries, and audit advice.

The design approach should be:

1. JMX metadata finds the right class/method to expose.
2. The JMX invoker calls through an object carrying the desired AOP behavior.
3. Operations to export are compatible with interfaces when using JDK proxies.
4. Dangerous operations are validated/authorized directly at the management boundary rather than relying solely on assumptions about AOP.
5. Observe using integration tests or runtime diagnostics when deploying the system.

One solution that reduces dependence on proxy internals is creating a separate **management facade**:

\`\`\`text
JMX ManagementFacade (exported)
        |
        v
OrderMaintenance service interface
        |
        v
Spring AOP proxy (transactions/security)
        |
        v
Business implementation
\`\`\`

The facade is exported directly, while calls to the business service go through the Spring-managed interface/proxy. As a result, transaction/security paths are expressed much more clearly.

## 9. Management Facade Example Avoiding Method Exposure Issues

Business service:

\`\`\`java
package com.example.jmx;

public interface OrderMaintenance {
    long getFailedOrders();
    void retryFailedOrders();
}
\`\`\`

Management facade:

\`\`\`java
package com.example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.app:type=OrderMaintenance,name=primary",
    description = "Operational control interface"
)
public class OrderMaintenanceJmxFacade {
    private final OrderMaintenance service;

    public OrderMaintenanceJmxFacade(OrderMaintenance service) {
        this.service = service;
    }

    @ManagedAttribute(description = "Number of failed orders")
    public long getFailedOrders() {
        return service.getFailedOrders();
    }

    @ManagedOperation(description = "Retry failed orders")
    public void retryFailedOrders() {
        service.retryFailedOrders();
    }
}
\`\`\`

Spring wiring:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxFacadeConfig {

    @Bean
    public OrderMaintenanceJmxFacade orderMaintenanceJmxFacade(
            OrderMaintenance orderMaintenance) {

        return new OrderMaintenanceJmxFacade(orderMaintenance);
    }
}
\`\`\`

For \`OrderMaintenance\` to actually be a proxy, the application still needs an advice/transactional setup applied to the service bean. The facade receives the bean by interface, so if Spring injects a proxy, calls from the facade go through the proxy.

Benefits:
- JMX annotations live on a stable management class.
- No need to put every JMX operation into business interfaces.
- Easy to restrict permissions and validation for the JMX path.
- Business AOP executes through the injected dependency.
- JMX names and metadata are more independent of implementation refactoring.

The trade-off is adding an adapter/facade layer. For systems with sensitive operations, this cost is usually acceptable.

## 10. JDK Proxy vs. CGLIB: Where Do They Differ?

### JDK dynamic proxy

A JDK proxy operates through interfaces. When a bean implements multiple public methods while the interface has only a subset, the proxy typically exposes only that interface subset.

Example:

\`\`\`java
interface WorkerTasks {
    void execute();
}

class WorkerTasksImpl implements WorkerTasks {
    @Override
    public void execute() {}

    @ManagedOperation
    public void refreshInternalState() {}
}
\`\`\`

If Spring creates a JDK proxy for \`WorkerTasks\`, the \`refreshInternalState\` method is not on the interface, so it cannot be called directly through a proxy cast to this interface. The JMX adapter can also encounter issues if it tries to invoke a target method not present on the proxy.

Remedies: add the required operation to an appropriate management interface, use a class-based proxy if valid, or prefer a management facade.

### CGLIB class-based proxy

A CGLIB proxy is typically a subclass of the implementation:

\`\`\`java
@EnableAspectJAutoProxy(proxyTargetClass = true)
\`\`\`

If an advisor applies, this configuration requests a class-based proxy in many cases.

Notes:
- A \`final\` class cannot be subclassed via normal CGLIB mechanisms.
- A \`final\` method cannot be overridden to apply method-level advice.
- Private methods do not become AOP join points through proxy-based method interception.
- Do not conclude that all annotations on the target are directly visible on the runtime proxy subclass.
- \`@EnableAspectJAutoProxy\` still requires an actual advisor/aspect for a bean to be proxied.

When only stable JMX export is needed, switching the entire application to CGLIB **should not be the default choice** just to fix one management operation. A facade or clear interface is usually easier to control.

## 11. Spring AOP Self-Invocation and JMX

Another important scenario is self-invocation:

\`\`\`java
public class BillingService {

    public void runManualSettlement() {
        settleInternally(); // called on this directly
    }

    @Transactional
    public void settleInternally() {
        // ...
    }
}
\`\`\`

In proxy-based Spring AOP, calling \`this.settleInternally()\` usually **does not go through the proxy**, so transactional advice on that method may not apply as expected.

If JMX invokes \`runManualSettlement\` through the proxy, that does not automatically turn the internal call \`settleInternally()\` into a proxied call. Service boundaries must be organized clearly, such as separating components or calling through an appropriate Spring-managed dependency.

For data-modifying JMX operations, do not assume having \`@Transactional\` somewhere in the call chain guarantees a transaction is actually running. Use integration tests to verify required behavior.

## 12. When Does Autodetection Pick the Wrong Bean or Miss a Bean?

Common scenarios:

1. **Proxy hides metadata**: the runtime proxy class lacks direct annotations, and custom discovery logic only reads \`bean.getClass()\`.
2. **Bean is not in the scanned context**: the exporter belongs to another context or the bean was not created.
3. **Annotation is on a class/method not exposed by the proxy**: the operation is described, but invocation hits interface restrictions.
4. **Bean is exported twice**: both autodetection and explicit mapping, or multiple exporters scanning the same beans.
5. **Duplicate ObjectName**: multiple instances share the same \`@ManagedResource(objectName=...)\`.
6. **Unsuitable assembler**: the MBean is registered, but metadata is wrong or missing operations.
7. **Different MBeanServer**: the client is looking at the wrong registry.
8. **Proxy appears after the exporter selects the bean**: unusual lifecycle ordering or custom infrastructure.
9. **Special/lazy/scoped beans**: the proxy represents a request/session or a target that only exists when the scope is active.

Not every “missing MBean” is caused by a JDK proxy. You must separate bean discovery, ObjectName creation, registration, metadata discovery, and operation execution.

## 13. Practical Diagnostic Workflow

When a bean with \`@ManagedResource\` does not appear, follow this order.

### Step 1: Identify bean and proxy

\`\`\`java
Object bean = ctx.getBean("orderMaintenance");

System.out.println("Bean runtime = " + bean.getClass());
System.out.println("AOP proxy = " + AopUtils.isAopProxy(bean));
System.out.println("Target class = " + AopUtils.getTargetClass(bean));
\`\`\`

### Step 2: Check the exporter

- Is there an \`MBeanExporter\` or annotation-driven infrastructure in the context?
- Is autodetection enabled and is a suitable metadata assembler configured?
- Are two exporters processing this same bean?
- Under what name/key is the bean exported?

### Step 3: Check ObjectName

\`\`\`java
ObjectName name = new ObjectName(
    "com.example.app:type=OrderMaintenance,name=primary"
);

boolean registered = mbeanServer.isRegistered(name);
System.out.println("registered = " + registered);
\`\`\`

If not registered, check logs for \`InstanceAlreadyExistsException\`, \`MalformedObjectNameException\`, detection errors, or exporter lifecycle issues.

### Step 4: Read JMX metadata

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;

MBeanInfo info = mbeanServer.getMBeanInfo(name);
for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println(operation.getName());
    for (var parameter : operation.getSignature()) {
        System.out.println("  param: " + parameter.getType());
    }
}
\`\`\`

If the operation is missing from metadata, it likely involves \`@ManagedOperation\`, the assembler, or how Spring resolves the target class.

### Step 5: Test invoking the operation in a suitable environment

\`\`\`java
mbeanServer.invoke(
    name,
    "retryFailedOrders",
    new Object[0],
    new String[0]
);
\`\`\`

**Never run state-modifying operations on production just to test JMX.** In tests, replace side-effecting operations with harmless ones, or use controlled test data.

### Step 6: Confirm advice actually ran

You can use:
- Logging inside AOP advice;
- Transaction synchronization or checking the appropriate transaction context;
- Metrics and tracing;
- Integration tests with fake services;
- Assertions on security/authorization boundaries.

Merely succeeding at \`invoke\` does not mean AOP advice ran. If the target method is called while bypassing the proxy, business logic may execute under different conditions than calls from application code.

## 14. Example Testing the JMX Contract with a Proxied Service

One way to test is to create a Spring test context where the service is AOP-proxied and the management facade is exported.

JUnit 5 skeleton:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(JmxFacadeConfig.class)
class OrderMaintenanceJmxTest {

    @Autowired
    MBeanServer server;

    @Test
    void exportsManagementFacade() throws Exception {
        ObjectName name = new ObjectName(
            "com.example.app:type=OrderMaintenance,name=primary"
        );

        assertTrue(server.isRegistered(name));

        var info = server.getMBeanInfo(name);
        assertTrue(
            java.util.Arrays.stream(info.getOperations())
                .anyMatch(op ->
                    op.getName().equals("retryFailedOrders"))
        );
    }
}
\`\`\`

This is an **illustrative skeleton**, not a standalone runnable test: the test configuration must define an \`MBeanServer\` bean, mock/fake service, JMX exporter, and if the goal is testing proxies, actual advice must be configured.

In practice, there should be two independent assertion groups:
- The management bean is registered and has the expected metadata.
- The JMX operation invokes the right service and triggers the desired AOP concerns.

Testing only \`isRegistered\` does not verify the call path through the proxy.

## 15. Scoped or Lazy Beans with Proxies

Not every proxy is an AOP proxy used for transactions. Spring can create scoped proxies for request/session/custom-scoped beans.

Example:

\`\`\`java
@Scope(
    value = "request",
    proxyMode = ScopedProxyMode.TARGET_CLASS
)
@Component
class RequestState {
    // ...
}
\`\`\`

An application-lifetime MBean is usually unsuitable for directly exposing an object that needs an active request scope. When a JMX client accesses it from a thread without a request context, an inactive scope error can occur.

For state that only exists per request:
- Do not auto-export every request-scoped bean as an MBean.
- Prefer an application-scoped management facade that aggregates metrics.
- Do not put secrets, request headers, or user identities into JMX ObjectNames.
- Limit the cardinality of metrics and MBeans.

Lazy beans must also be considered: autodetection or export may trigger initialization depending on the mechanism. Do not rely on assuming every bean will always be initialized at the right moment or never be initialized by JMX infrastructure.

## 16. Proxies and ObjectName: Do Not Use Runtime Class Names

A poor naming strategy:

\`\`\`java
public ObjectName getObjectName(Object bean, String beanKey)
        throws MalformedObjectNameException {

    return new ObjectName(
        "com.example.app:type=" + bean.getClass().getSimpleName()
    );
}
\`\`\`

With a JDK proxy, the runtime class may be a JVM-generated class (a name with no business meaning). With a class-based proxy, the runtime name may contain a proxy suffix. These details can change when Spring/AOP configuration changes.

Instead use:
- A validated, stable \`beanKey\`;
- A resource ID provided by the management bean;
- Annotation metadata \`@ManagedResource(objectName=...)\`;
- Explicit ObjectName mapping.

Example:

\`\`\`java
ObjectName name = new ObjectName(
    "com.example.app:type=OrderMaintenance,name=primary"
);
\`\`\`

A JMX client should not need to know whether an implementation uses JDK proxy or CGLIB in order to find the right MBean.

## 17. Security When Exposing Proxied Beans

Some applications use AOP to enforce security or auditing. When the JMX exporter turns a method into an operation, treat it as a special management call path.

- Do not assume remote JMX clients automatically pass through HTTP security filter constraints.
- If relying on method security via AOP, confirm JMX operations genuinely pass through the proxy.
- Manage authentication/authorization on the JMX connector/server.
- Use a management facade to validate parameters, restrict actions, and write audit logs.
- Do not export internal or sensitive methods merely because they are public.
- Do not put passwords, tokens, or user identities in ObjectNames or notification payloads.
- For dangerous operations, verify post-conditions and avoid blind retries when execution status is uncertain.

A Spring AOP proxy is an implementation mechanism, not a substitute for security at the JMX boundary.

## 18. Common Issues Table

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Annotated MBean not visible | Exporter/scan/metadata incorrect; invalid ObjectName | Context, autodetection, registration logs |
| JDK proxy has MBean but missing operation | Method not on interface or wrong assembler selection | Interfaces, \`MBeanInfo\`, metadata source |
| Operation callable but \`@Transactional\` does not run | Target called directly or self-invocation | Invocation path, facade, transaction test |
| \`ClassCastException\` when getting Spring bean | Casting JDK proxy to implementation | Inject interface or change design |
| \`InstanceAlreadyExistsException\` | Duplicate auto-export or static name for multiple beans | Ownership, ObjectName, exporter count |
| MBean name contains strange proxy string | Naming from runtime \`getClass()\` | Use logical/annotation name |
| Scoped proxy fails on JMX invoke | Scope not active | Application-scoped management facade |
| CGLIB does not intercept method | \`final\`/private method or proxy constraints | Method visibility and proxy design |
| JMX client checks wrong server | Exporter uses a different server | Check the exact \`MBeanServer\` |
| Callback/operation runs outside expected context | JMX thread and application execution context differ | Explicit security/context propagation |

## 19. Practice Exercises

### Exercise 1: Find the JDK Proxy Bug

\`\`\`java
interface TaskService {
    int getQueueSize();
}

class TaskServiceImpl implements TaskService {
    @Override
    public int getQueueSize() { return 10; }

    @ManagedOperation
    public void clearQueue() {}
}
\`\`\`

If Spring creates a JDK proxy for the \`TaskService\` interface, why might \`clearQueue()\` be hard to export/invoke through the proxy?

**Hint:** the proxy does not expose that method because it is not in the interface. Place management behavior in an appropriate interface or use a facade.

### Exercise 2: Distinguish Annotation and Proxy Class

\`\`\`java
Object bean = ctx.getBean("taskService");
boolean annotated =
    bean.getClass().isAnnotationPresent(ManagedResource.class);
\`\`\`

Why is \`annotated == false\` not enough to conclude the bean has no JMX annotations?

**Hint:** the runtime object may be a proxy while the annotation resides on the target class. Spring metadata discovery must consider the target class.

### Exercise 3: Impact of Self-Invocation

A JMX method is invoked through the proxy, then calls \`this.internalTransactionalMethod()\`. Is the transaction on the internal method guaranteed to run?

**Hint:** With proxy-based AOP, self-invocation can bypass transactional advice. Split boundaries or invoke via a Spring-managed collaborator.

### Exercise 4: Choose the Fix

An application has two beans of the same implementation class, both having \`@ManagedResource(objectName="com.example:type=Worker")\`. Autodetection fails on one bean due to duplicate name.

**Hint:** Use distinct ObjectNames per role/instance, or explicit mapping/naming strategy. Do not simply switch from JDK proxy to CGLIB to fix a naming error.

### Exercise 5: Design a Facade

A service has a transaction proxy and needs a JMX operation \`rebuildIndex()\`. Design an \`IndexMaintenanceJmxFacade\` with:
- \`@ManagedResource\` with a stable ObjectName;
- \`@ManagedOperation\` on \`rebuildIndex\`;
- Dependency on the \`IndexMaintenanceService\` interface;
- Audit logging and validation;
- Unit/integration test verifying that JMX calls go through the service proxy.

### Exercise 6: Why Not Export Request-Scoped Objects Directly?

**Hint:** A JMX call may run on a thread without a request scope; it is better to export an application-scoped bean that aggregates state.

## 20. Takeaways

Autodetection in Spring JMX reduces manual configuration, but AOP proxies create a boundary between the **runtime bean**, the **target class holding annotations**, and the **methods actually invocable**. With JDK proxies, interfaces are a critical contract; with CGLIB, subclass/final-method limitations must be understood. \`MBeanExporter\` and the metadata assembler must locate the resource and expose the right contract.

If a JMX operation modifies data, check both the **exported metadata** and the **call path through the AOP proxy**. A dedicated management facade is a maintainable choice when preserving transaction/security advice while restricting the management API. JMX names should be stable and independent of proxy class names, and the final result should be verified via \`MBeanServer\`, \`MBeanInfo\`, and a safe invocation check.