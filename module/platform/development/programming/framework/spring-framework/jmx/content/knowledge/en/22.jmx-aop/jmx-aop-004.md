# Order of proxy creation, exporter, and metadata assembler in Spring JMX and AOP

> **Topic:** Spring Framework JMX  
> **Knowledge group:** JMX and AOP  
> **Lesson:** Order of proxy creation, exporter, and metadata assembler

## 1. Learning objectives

When a Spring bean uses both AOP and JMX export, the outcome does not depend solely on whether the class has \`@ManagedResource\`. The timing of bean instantiation, \`BeanPostProcessor\` application, AOP proxy creation, metadata resolution, and MBean registration in \`MBeanServer\` all affect the management surface visible to clients.

After this lesson, you will be able to:

- Describe the high-level ordering among bean initialization, AOP proxies, \`MBeanExporter\`, and \`MetadataMBeanInfoAssembler\`.
- Distinguish between the **target object**, **AOP proxy**, **exporter**, and **ModelMBean**.
- Understand why annotations on the implementation can sometimes be hard to detect when the exporter sees a JDK dynamic proxy.
- Distinguish Spring JMX metadata from methods that can actually be invoked through the proxy.
- Inspect \`MBeanInfo\`, the bean's runtime type, advisors, and \`ObjectName\` to diagnose export failures.
- Organize configurations to avoid premature bean usage, duplicate exporters, or accidental bypassing of AOP advice.

## 2. Context: a bean with multiple layers of representation

Suppose you have a Spring service:

\`\`\`java
@Service
@ManagedResource(
    objectName = "app.management:type=Billing,name=main"
)
public class BillingService {

    @Transactional
    @ManagedOperation
    public void reconcile() {
        // Perform business processing.
    }
}
\`\`\`

The application enables both Spring AOP or transaction proxying and JMX export.

In a common setup, the published object may pass through:

\`\`\`text
BillingService implementation (target)
                   |
                   v
           Spring AOP proxy
                   |
                   v
      MBeanExporter / JMX adapter
                   |
                   v
              MBeanServer
                   |
                   v
        JConsole / JMX client
\`\`\`

However, this is a **generalized model**, not a guarantee that every Spring version always creates every kind of proxy before a fixed point in time. What matters is identifying which bean/proxy the exporter actually receives when it builds \`ModelMBeanInfo\` and registers the MBean.

If the proxy sits between the client and the target, invocations can pass through AOP advice such as transactions, logging, validation, or security. If the exporter is configured directly with a different target object, the JMX call path may bypass the proxy and miss the expected advice.

## 3. Components to distinguish

| Component | Role |
|---|---|
| Spring target bean | Implementation containing the actual logic |
| \`BeanPostProcessor\` | Can participate in the bean creation/wrapping phase |
| AOP \`AutoProxyCreator\` | Creates proxies applying interceptors/advice per configuration |
| JDK dynamic proxy | Proxy based on Java interfaces |
| CGLIB/class-based proxy | Subclass-style proxy of the target class |
| \`MBeanExporter\` | Exports eligible beans as MBeans |
| \`AnnotationMBeanExporter\` | Infrastructure for annotation-based MBean export |
| \`MetadataMBeanInfoAssembler\` | Reads JMX metadata and builds \`ModelMBeanInfo\` |
| \`AnnotationJmxAttributeSource\` | Metadata source from Spring JMX annotations |
| \`ObjectNamingStrategy\` | Determines the \`ObjectName\` for the MBean |
| \`MBeanServer\` | JMX registry and execution endpoint |
| \`MBeanInfo\` | Contract of attributes, operations, and notifications seen by clients |

An example \`ObjectName\`:

\`\`\`text
app.management:type=Billing,name=main
\`\`\`

It is a management identifier in \`MBeanServer\`, **not the class name** of the proxy or target.

## 4. High-level initialization sequence

In a typical \`ApplicationContext\`:

\`\`\`text
[1] Read @Configuration / bean definitions
                      |
[2] Register BeanFactoryPostProcessor/BeanPostProcessor
                      |
[3] Instantiate singleton beans per dependencies and lifecycle
                      |
[4] BeanPostProcessor may wrap beans into AOP proxies
                      |
[5] Exporter obtains bean references / discovers beans
                      |
[6] Assembler builds management metadata for the MBean
                      |
[7] Exporter chooses ObjectName and registers the MBean
                      |
[8] Client queries MBeanInfo / invokes operations
\`\`\`

Steps [3] through [7] can depend on dependency order, \`SmartInitializingSingleton\`, exporter lifecycle, bean post-processing, and Spring version. Do not treat this diagram as an immutable total order across all applications.

In particular, within a Spring container, \`BeanPostProcessor\` beans are registered before normal instantiation of most application beans, yet some infrastructure beans may be created early and miss certain kinds of post-processing. This is why you should avoid retrieving business beans too early from an infrastructure component.

## 5. Why think about the proxy before the exporter?

Suppose a service has an interface:

\`\`\`java
public interface BillingOperations {
    void reconcile();
}
\`\`\`

Implementation:

\`\`\`java
@Service
public class BillingService implements BillingOperations {

    @Override
    @Transactional
    public void reconcile() {
        // Logic requiring a transaction.
    }
}
\`\`\`

When using a JDK dynamic proxy, the object a client obtains from the context may implement only \`BillingOperations\` and a few proxy interfaces, rather than directly being an instance of the \`BillingService\` class.

\`\`\`text
Bean name "billingService"
             |
             v
JDK dynamic proxy (BillingOperations)
             |
             v
BillingService target
\`\`\`

If the JMX exporter holds a reference to the bean proxy, calls through the interface can pass through advice. If the exporter tries to call a method that exists only on the implementation and not on the JDK proxy's interfaces, the invocation may not be available in the way you expect.

With a CGLIB proxy, the subclass proxy usually exposes more public methods of the target class, yet that does not mean every method is advised or exported automatically. \`final\` methods, \`private\` methods, and self-invocation have their own AOP limitations.

## 6. What does the metadata assembler read?

The Spring JMX annotation model commonly uses:

\`\`\`java
@ManagedResource(...)
@ManagedAttribute(...)
@ManagedOperation(...)
\`\`\`

When the exporter prepares an MBean, \`MetadataMBeanInfoAssembler\` relies on \`JmxAttributeSource\` to build metadata describing the managed resource.

\`\`\`text
Target class / proxy-visible methods
                 |
                 v
      AnnotationJmxAttributeSource
                 |
                 v
      MetadataMBeanInfoAssembler
                 |
                 v
      ModelMBeanInfo: attributes,
      operations, notifications
                 |
                 v
          ModelMBean registered
\`\`\`

The key point is that **metadata** and **method executability** must match. A method annotated on the target where the exporter or proxy fails to expose the matching method signature can lead to a missing operation or invocation error.

Do not assume adding an annotation to a class guarantees the operation will appear; inspect \`MBeanInfo\` from the actual server.

## 7. Example of Spring JMX combined with AOP

### 7.1. Management interface

\`\`\`java
package example.jmx;

public interface JobControl {
    int getPendingJobs();
    String requestDrain(int maxBatch);
}
\`\`\`

### 7.2. Annotated implementation

\`\`\`java
package example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedOperationParameters;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@ManagedResource(
    objectName = "app.management:type=JobControl,name=main",
    description = "Queue job management"
)
public class JobControlService implements JobControl {

    private volatile int pendingJobs = 10;

    @Override
    @ManagedAttribute(description = "Pending job count")
    public int getPendingJobs() {
        return pendingJobs;
    }

    @Override
    @Transactional
    @ManagedOperation(description = "Request batch drain")
    @ManagedOperationParameters({
        @ManagedOperationParameter(
            name = "maxBatch",
            description = "Maximum jobs to drain"
        )
    })
    public String requestDrain(int maxBatch) {
        if (maxBatch < 1 || maxBatch > 100) {
            throw new IllegalArgumentException(
                "maxBatch must be 1..100"
            );
        }

        // In a real application, call a task-processing service.
        pendingJobs = Math.max(0, pendingJobs - maxBatch);
        return "accepted";
    }
}
\`\`\`

Annotations on the implementation express both management metadata and transaction advice. The example uses a simple counter field; in a multithreaded application, design state/concurrency appropriately.

### 7.3. Export configuration

\`\`\`java
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@ComponentScan(basePackageClasses = JobControlService.class)
@EnableTransactionManagement
@EnableMBeanExport
public class JmxAndAopConfiguration {
}
\`\`\`

The \`@EnableTransactionManagement\` configuration activates transaction interception infrastructure when a transaction manager and suitable conditions are present. Adding the annotation alone does not create a database or transaction manager.

### 7.4. Querying the exported contract

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "app.management:type=JobControl,name=main"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException(
        "MBean not registered: " + name
    );
}

MBeanInfo info = server.getMBeanInfo(name);

for (var op : info.getOperations()) {
    System.out.println(
        op.getName() + " -> " + op.getReturnType()
    );
}
\`\`\`

The example assumes the exporter uses the platform \`MBeanServer\`. If the exporter is configured with a dedicated \`MBeanServer\`, you must connect to the actual server.

## 8. JDK proxy and CGLIB proxy

| Criterion | JDK dynamic proxy | CGLIB/class-based proxy |
|---|---|---|
| Mechanism | Implements interfaces | Creates a subclass of the target class |
| Methods visible via proxy | Methods belonging to interfaces implemented by the proxy | Overridable/exposed methods on the class |
| Interface dependency | Explicit | Not required |
| AOP limitations | Methods outside proxy interfaces cannot be called through proxy | Final/private/self-invocation remain issues |
| JMX impact | Management methods need a valid call path through an interface | May be easier to find methods on the class, yet metadata must still match |

With a Spring AOP proxy, the runtime type may differ from the target class:

\`\`\`java
Object bean = context.getBean("jobControlService");

System.out.println(bean.getClass().getName());
\`\`\`

The output may be a JDK proxy or CGLIB-generated class name. Do not use the runtime proxy class name as a durable \`ObjectName\` contract for clients.

You can use Spring AOP utilities to inspect it:

\`\`\`java
import org.springframework.aop.support.AopUtils;

boolean proxied = AopUtils.isAopProxy(bean);
boolean jdk = AopUtils.isJdkDynamicProxy(bean);
boolean cglib = AopUtils.isCglibProxy(bean);
Class<?> targetType = AopUtils.getTargetClass(bean);
\`\`\`

This is in-process type/proxy observation, not a mechanism that automatically fixes all JMX issues.

## 9. Annotations on the interface or implementation?

A common question: should you put \`@ManagedOperation\` on the interface, the implementation, or both?

Annotation metadata can be looked up by the framework on methods/interfaces/classes according to specific rules. These rules also depend on the exporter, assembler, proxy, and Spring version. Therefore, you should not claim that one annotation placement always works across all configurations.

A maintainable strategy:

1. Create a narrow management interface defining the methods to expose.
2. Ensure the proxy can invoke those methods.
3. Place metadata on the class/methods that the exporter actually supports and recognizes.
4. Use \`MBeanInfo\` to verify that attributes and operations have appeared.
5. Verify invocation via \`MBeanServer\` in an integration test.

If the application uses JDK proxies and the annotation sits only on a method absent from the interface, one option is to adjust the management design so the method is exposed via an appropriate interface, or use a dedicated facade.

## 10. Exporting a separate management facade

When an internal service has complex AOP, a facade design can reduce reliance on proxy details:

\`\`\`text
JMX client
    |
    v
Management facade @ManagedResource
    |
    v
Business service interface
    |
    v
Spring AOP proxy
    |
    v
Business implementation
\`\`\`

Example:

\`\`\`java
@Component
@ManagedResource(
    objectName = "app.management:type=JobControl,name=main"
)
public class JobManagementFacade {

    private final JobControl jobControl;

    public JobManagementFacade(JobControl jobControl) {
        this.jobControl = jobControl;
    }

    @ManagedAttribute
    public int getPendingJobs() {
        return jobControl.getPendingJobs();
    }

    @ManagedOperation
    public String requestDrain(int maxBatch) {
        return jobControl.requestDrain(maxBatch);
    }
}
\`\`\`

Advantages:

- JMX annotations are centralized on the facade.
- The service still receives AOP advice via interface injection.
- Other business methods are not exposed.
- \`ObjectName\` remains stable when the implementation changes.
- Easier to observe/test the contract independently.

However, the facade must still hold a reference to the **Spring proxy** of the service if advice is to apply. If the facade instantiates \`new JobControlService()\` directly instead of receiving injection from the context, Spring AOP interceptors will not participate automatically.

## 11. Bean and exporter initialization order

One risk is that an exporter or a related bean causes a service to be instantiated **before** all required post-processors/proxy infrastructure are ready.

Warning signs:

- The runtime bean is not a proxy even though you expected AOP.
- Transaction advice does not run for JMX calls.
- Spring logs indicate a bean is not eligible for all \`BeanPostProcessor\`s.
- The exporter receives a target or reference different from the bean injected into other modules.
- MBean metadata differs from the annotations developers see in source code.

How to address this:

1. Avoid instantiating business services from the constructor/static initializer of an infrastructure bean.
2. Let Spring manage lifecycle and dependency injection.
3. Do not invoke JMX operations in constructors or too early in \`@PostConstruct\`.
4. Minimize customizing \`BeanFactoryPostProcessor\`/\`BeanPostProcessor\` unless necessary.
5. Read the proxy type and metadata after the context finishes initializing.
6. Use integration tests rather than only unit-testing the target object directly.

Do not mechanically enforce an initialization order with \`@DependsOn\` before identifying the real dependency. \`@DependsOn\` can affect bean initialization order, yet it does not resolve all AOP/metadata conflicts.

## 12. Proxy calling its own internal methods: self-invocation

Spring AOP is proxy-based. A method inside the target calling another method via \`this.method()\` typically **does not pass through the proxy**.

\`\`\`java
@Service
public class JobControlService {

    @Transactional
    public void drainTransactional() {
        // ...
    }

    public void drainAll() {
        this.drainTransactional();
    }
}
\`\`\`

If JMX invokes \`drainAll()\` through the proxy, the initial call may pass through the proxy; however, the call from \`drainAll\` to \`drainTransactional\` is an internal self-invocation on the target and usually does not trigger a new transaction interceptor.

Therefore, do not assume "because it is exported through an AOP proxy, every internal method is advised". Design service boundaries and invocation paths to fit the proxy model.

## 13. The proxy-target-class option

Spring AOP can be configured to use class-based proxies:

\`\`\`java
@EnableAspectJAutoProxy(proxyTargetClass = true)
\`\`\`

Or configure transaction proxies appropriately for your version:

\`\`\`java
@EnableTransactionManagement(proxyTargetClass = true)
\`\`\`

Choosing CGLIB can make methods on the target class easier to reach, but should not be used as the sole fix to "repair" JMX metadata.

Remaining risks:

- \`final\` methods cannot be overridden by a subclass for advice in the normal way.
- \`private\` methods are not advised like public methods on the proxy.
- Self-invocation does not automatically go through the proxy.
- The exporter/assembler still needs to read annotations accurately.
- A bean may have multiple advisors/interceptors with different ordering.

A separate management facade is usually a more predictable choice when the JMX surface needs long-term stability.

## 14. Metadata assembler and proxy-visible methods

A \`MetadataMBeanInfoAssembler\` needs to align:

- Which methods the MBean can expose.
- Annotations describing attributes/operations.
- Parameter types and return types.
- Operation names/descriptions/impacts.
- Attribute read/write access.
- Notification metadata if present.

If a method has an annotation yet lacks a valid call path through the exported bean, errors may occur during registration or invocation.

Therefore, verify two layers:

\`\`\`text
Metadata layer:
  Does MBeanInfo contain the expected operation?

Execution layer:
  Does MBeanServer.invoke execute the operation
  and run the required advice?
\`\`\`

Reading \`MBeanInfo\` only proves the operation is published; it does not by itself prove that transaction, logging, security, or retry advice executed.

## 15. Configuring an explicit assembler when needed

With a manual \`MBeanExporter\`, Spring allows supplying an \`MBeanInfoAssembler\` to control the MBean's metadata.

Conceptual example:

\`\`\`java
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;

AnnotationJmxAttributeSource attributeSource =
    new AnnotationJmxAttributeSource();

MetadataMBeanInfoAssembler assembler =
    new MetadataMBeanInfoAssembler(attributeSource);

MBeanExporter exporter = new MBeanExporter();
exporter.setAssembler(assembler);
\`\`\`

This is an illustrative configuration fragment, not a complete standalone exporter. You must configure the beans to export, \`ObjectName\`, \`MBeanServer\`, and lifecycle appropriately.

Avoid configuring multiple exporters simultaneously for the same bean/\`ObjectName\`. When a built-in annotation exporter is available, use that mechanism unless you genuinely need to customize the assembler.

## 16. Mismatch between metadata and runtime type

Suppose you have an interface:

\`\`\`java
public interface Operations {
    void start();
}
\`\`\`

Implementation:

\`\`\`java
public class OperationsImpl implements Operations {
    @Override
    public void start() { ... }

    @ManagedOperation
    public void internalReset() { ... }
}
\`\`\`

If Spring creates a JDK proxy implementing only \`Operations\`, the \`internalReset()\` method is not in the proxy interface. An assembler that reads the implementation method and exposes it when the runtime proxy provides no suitable invocation path can cause errors.

How to reduce risk:

- Do not annotate internal methods if you do not want to expose them.
- If an operation is needed, place it in a clear management interface or facade.
- Cross-check metadata against the actual proxy type.
- Test \`MBeanServer.invoke\` and verify effects/exceptions.
- Do not force proxy unwrapping or use reflection into the target merely to bypass AOP design.

## 17. Checking advice ordering and operation behavior

A method wrapped by multiple advices:

\`\`\`text
JMX invocation
    |
    v
Proxy
    |
    +--> Security advice
    +--> Logging advice
    +--> Transaction advice
    |
    v
Target method
\`\`\`

Advice order affects behavior. For example, security needs to execute before an operation with side effects; a transaction boundary may need to enclose the entire state-updating logic.

Spring AOP provides \`@Order\`, \`Ordered\`, and specific infrastructure advisor rules to control order, but you should not infer order from annotation order in source code.

For instance, placing \`@Transactional\` directly above \`@ManagedOperation\` does not determine which interceptor runs first. Inspect the advisor configuration and how the Spring proxy is actually constructed.

## 18. Verifying proxies in the ApplicationContext

After the context initializes:

\`\`\`java
import org.springframework.aop.support.AopUtils;

Object bean = context.getBean("jobControlService");

System.out.println(
    "Runtime type: " + bean.getClass().getName()
);
System.out.println(
    "Is AOP proxy: " + AopUtils.isAopProxy(bean)
);
System.out.println(
    "Target class: " +
        AopUtils.getTargetClass(bean).getName()
);
\`\`\`

To inspect advisors when the bean implements \`Advised\`:

\`\`\`java
import org.springframework.aop.framework.Advised;

if (bean instanceof Advised advised) {
    for (var advisor : advised.getAdvisors()) {
        System.out.println(advisor);
    }
}
\`\`\`

Do not assume every AOP proxy implements \`Advised\` or allows full access to the target; some proxies may use opaque settings or different mechanisms.

## 19. Verifying actual MBeanInfo

Use the exact \`MBeanServer\` where the exporter registered the MBean:

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanOperationInfo;
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "app.management:type=JobControl,name=main"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException(
        "MBean not registered: " + name
    );
}

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attr : info.getAttributes()) {
    System.out.printf(
        "Attribute %s (%s) readable=%s writable=%s%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable()
    );
}

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.println(
        "Operation " + op.getName() +
        " -> " + op.getReturnType()
    );
}
\`\`\`

In the \`JobControlService\` example, you expect attribute \`PendingJobs\` and operation \`requestDrain(int)\` when the metadata exporter supports it properly.

If an operation is missing from \`MBeanInfo\`, do not conclude that AOP advice is not running; first determine whether the metadata assembler published the method.

## 20. Verifying invocation and advice

Once \`requestDrain(int)\` has appeared:

\`\`\`java
Object result = server.invoke(
    name,
    "requestDrain",
    new Object[] { 3 },
    new String[] { "int" }
);

System.out.println(result);
\`\`\`

To verify transaction advice in a real application, use an integration test with a transaction manager and appropriate dependencies, observing commit/rollback behavior or controlled test interceptor logs.

Do not use \`@Transactional\` on an example that only updates an in-memory field and conclude that transactions definitely ran: transactions take effect with appropriate resources and an invocation path through the proxy.

## 21. Common mistakes

### 21.1. Annotations exist yet the MBean does not appear

Check:

1. Was the bean created and scanned by Spring?
2. Is the exporter enabled?
3. Is the \`ObjectName\` valid and non-conflicting?
4. Which \`MBeanServer\` does the exporter use?
5. Were there exceptions during export?
6. Is any class/interface/proxy altering metadata detection?

### 21.2. MBean appears yet an operation is missing

Check annotation placement, proxy-visible methods, assembler, overloads/signatures, and actual metadata in \`MBeanInfo\`.

### 21.3. Operation is callable yet transaction advice does not run

Check whether the exporter points to the proxy or target, whether the Spring bean is actually auto-proxied, self-invocation, advisor selection, and the transaction manager.

### 21.4. Exporter fails because the method does not exist on the proxy

This typically occurs when metadata is built from the implementation while the runtime object is a JDK proxy with a narrow interface. Choose a compatible management interface/facade or configure export appropriately rather than bypassing the proxy arbitrarily.

### 21.5. MBean name changes when switching proxies

Do not construct \`ObjectName\` solely from \`bean.getClass().getName()\`, because the proxy class can differ from the implementation. Use \`@ManagedResource(objectName = "...")\` or a stable naming strategy.

### 21.6. Multiple exporters for the same bean

\`@EnableMBeanExport\`, Spring Boot auto-configuration, and a manual \`MBeanExporter\` can cause duplicate exports when configurations overlap. Inventory your exporters and clarify \`ObjectName\` ownership rather than using \`REPLACE_EXISTING\` to mask the error.

## 22. Example of a layered verification sequence

\`\`\`text
Step A: Spring context
  - Does the bean exist?
  - Is the runtime bean a target or AOP proxy?
  - Are advisors applied?

Step B: Exporter
  - Which exporter was initialized?
  - Which MBeanServer is used?
  - Which NamingStrategy / assembler?

Step C: Metadata
  - Does MBeanInfo have expected attributes and operations?
  - Do signatures match Java types?

Step D: Invocation
  - Can a client invoke the operation?
  - Does required AOP advice execute?
  - Does business state change as expected?

Step E: Lifecycle
  - Is the MBean registered/unregistered properly?
  - Do proxies and clients avoid invoking before the exporter is ready?
\`\`\`

This workflow separates metadata errors from proxy/invocation errors, reducing guesswork around tweaking AOP configuration when the real cause is a wrong \`ObjectName\` or wrong \`MBeanServer\`.

## 23. When to use a management facade?

Consider a separate facade when:

- The business service has many interfaces and advisors.
- A JDK proxy does not expose all desired management methods.
- You want to keep the \`ObjectName\` stable even if the implementation is refactored.
- You want to protect the service from exposing too many methods.
- You need to separate management from business-layer transactions/security while still calling through the proper service proxy.
- Long-lived JMX clients depend on explicit metadata.
- You need to test the management surface independently of AOP internals.

Design pattern:

\`\`\`text
JMX -> ManagementFacade -> BusinessInterfaceProxy -> Target
\`\`\`

There is no single proxy/exporter ordering that solves every project; a management facade makes boundaries clearer and more resilient.

## 24. Self-check questions

1. Why might a Spring bean with \`@ManagedOperation\` not appear as expected when using an AOP proxy?
2. How does a JDK dynamic proxy differ from a CGLIB proxy in how methods are exposed?
3. What two different responsibilities do \`MetadataMBeanInfoAssembler\` and \`MBeanServer\` handle?
4. Why must both \`MBeanInfo\` and actual invocation be verified?
5. When JMX invokes an operation through a Spring proxy, how can advice be applied?
6. How does self-invocation affect transaction advice?
7. Why should you not use the proxy's class name as the \`ObjectName\`?
8. In what situations might an exporter receive a bean before post-processing finishes?
9. How does a management facade reduce coupling with AOP/proxies?
10. Why does \`@EnableTransactionManagement\` not by itself guarantee transactions work when a transaction manager is missing?

## 25. Remember

\`\`\`text
Spring bean definition
      |
      v
Bean initialization / BeanPostProcessors
      |
      v
AOP proxy (if created)
      |
      v
MBeanExporter
      |
      +--> naming strategy -> ObjectName
      |
      +--> metadata assembler -> MBeanInfo
      |
      v
MBeanServer registration
      |
      v
Client attribute access / operation invoke
      |
      v
Proxy/advice/target per actual call path
\`\`\`

**Key principle:** when JMX and AOP appear together, inspect **the actual object used by the exporter**, **the metadata built by the assembler**, and **the call path through the proxy**. An annotation in source code is not enough to prove an operation has been exposed or that advice will run. Designing a management facade and running integration tests against a real \`MBeanServer\` help keep the management surface stable.