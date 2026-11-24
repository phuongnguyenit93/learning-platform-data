# Annotation Not Recognized Due to Proxy Interface in Spring Framework JMX

> **Topic:** Spring Framework JMX  
> **Knowledge Group:** Troubleshooting  
> **Lesson:** Annotation Not Recognized Due to Proxy Interface

## 1. Lesson Objectives

In a Spring application, a bean may be annotated with \`@ManagedResource\`, \`@ManagedAttribute\`, or \`@ManagedOperation\`, yet when opening JConsole, the MBean does not appear, is missing attributes, or is missing operations. One hard-to-spot cause is that **the bean was replaced by an AOP proxy**, especially a JDK dynamic proxy that only exposes the interfaces it implements.

After this lesson, you will be able to:

- Distinguish the implementation class, management interface, and actual proxy object in the Spring ApplicationContext.
- Explain why a JDK dynamic proxy does not expose every public method on the target class.
- Identify which class/method carries the JMX annotations and which object the exporter/assembler is observing.
- Distinguish **MBean not registered**, **MBean present but missing metadata**, and **metadata present but invocation fails**.
- Inspect \`AopUtils\`, \`MBeanInfo\`, \`ObjectName\`, \`MBeanServer\`, and \`MBeanExporter\` configuration.
- Choose a fix: an appropriate interface, a management facade, a class-based proxy, or a verified exporter/metadata assembler configuration.
- Write regression-preventing integration tests instead of relying merely on the code compiling.

## 2. Common Symptoms

Example Spring bean:

\`\`\`java
public interface JobService {
    void startJob();
}

@Service
@ManagedResource(
    objectName = "app.management:type=JobService,name=main"
)
public class JobServiceImpl implements JobService {

    @Override
    @Transactional
    @ManagedOperation(description = "Start job")
    public void startJob() {
        // Business logic.
    }

    @ManagedOperation(description = "Internal maintenance")
    public void maintenance() {
        // Method not part of the JobService interface.
    }
}
\`\`\`

The application uses AOP, creating a JDK dynamic proxy. The developer expects the MBean to contain both \`startJob\` and \`maintenance\` operations, yet in practice may encounter one of these situations:

1. The MBean is not found at \`app.management:type=JobService,name=main\`.
2. The MBean exists, but \`maintenance\` is missing.
3. The MBean has the operation in its metadata, yet calling \`invoke\` fails.
4. The operation can be invoked, yet AOP advice such as transactions or security does not behave as expected.
5. The exporter throws an exception at startup related to metadata, class/interface, or method lookup.

Do not lump all of the above into a single problem. In some cases **the annotation is not detected**, in others **the annotation is detected properly but the method cannot be invoked through the proxy**, and in others **the exporter uses a different server/name**.

## 3. Flow Diagram

\`\`\`text
JobServiceImpl target
  - @ManagedResource
  - @ManagedOperation startJob()
  - @ManagedOperation maintenance()
                 |
                 v
           Spring AOP
                 |
                 v
       JDK dynamic proxy
       implements JobService
       exposes startJob()
       NOT maintenance()
                 |
                 v
      Spring JMX exporter
                 |
                 +--> Annotation metadata lookup
                 +--> Operation/attribute assembly
                 +--> ObjectName registration
                 |
                 v
            MBeanServer
                 |
                 v
        JConsole / JMX client
\`\`\`

The diagram illustrates the risk around **what object the exporter receives and which methods the proxy can execute**. It does not assert that every Spring version ignores implementation annotations when a proxy exists: Spring has mechanisms to look up target classes and annotation metadata. Actual behavior depends on the exporter, assembler, proxy strategy, and library version.

## 4. What Is a JDK Dynamic Proxy?

A JDK dynamic proxy is an object generated at runtime to implement Java interfaces:

\`\`\`java
public interface JobService {
    void startJob();
}
\`\`\`

The proxy can be obtained via:

\`\`\`java
JobService service = context.getBean(JobService.class);
\`\`\`

However, the runtime object is not a direct instance of \`JobServiceImpl\`. The Java methods callable through the proxy are primarily those belonging to the interfaces the proxy implements.

\`\`\`text
Proxy API:
  startJob()        OK (present on JobService)
  maintenance()     NOT on JobService
\`\`\`

A public method on the target **is not automatically present on the proxy interface**. This affects management operations if the exporter/adapter is designed to invoke through the proxy.

### Comparing JDK Proxy and CGLIB

| Aspect | JDK Dynamic Proxy | Class-Based / CGLIB Proxy |
|---|---|---|
| Object form | Implements interfaces | Subclass of the target class |
| Methods exposed via type | Primarily interface methods | Methods accessible via the target class |
| Requires an interface? | Yes | Not mandatory |
| Methods existing only on implementation | Not a proxy interface method | Accessible when conditions are met |
| AOP limitations | Self-invocation, advisor matching, interface surface | Self-invocation, final/private methods, advisor matching |
| Relationship to JMX | Requires aligning interface/metadata/invocation | Does not eliminate the need to check metadata |

Switching to a class-based proxy sometimes overcomes interface limitations, but it is **not a cure-all for every JMX annotation issue**.

## 5. Where Are the Annotations Placed?

You may encounter several declaration styles.

### 5.1. Annotations on the implementation

\`\`\`java
@Service
@ManagedResource(
    objectName = "app.management:type=Worker,name=main"
)
public class WorkerServiceImpl implements WorkerService {

    @ManagedOperation
    public void restart() {
        // ...
    }
}
\`\`\`

### 5.2. Annotations on a management interface

\`\`\`java
@ManagedResource(
    objectName = "app.management:type=Worker,name=main"
)
public interface WorkerManagement {

    @ManagedOperation
    void restart();
}
\`\`\`

### 5.3. Annotations on a dedicated facade

\`\`\`java
@Component
@ManagedResource(
    objectName = "app.management:type=Worker,name=main"
)
public class WorkerManagementFacade {

    private final WorkerService workerService;

    public WorkerManagementFacade(
            WorkerService workerService
    ) {
        this.workerService = workerService;
    }

    @ManagedOperation
    public void restart() {
        workerService.restart();
    }
}
\`\`\`

There is no general Java rule guaranteeing that an annotation on an implementation will automatically appear on a JDK proxy interface. Spring JMX metadata handling can look up annotations across target/interface structures depending on the specific implementation; test against the exact Spring version and exporter path in use.

**The clearest architectural choice when you need a stable management boundary:** a dedicated management facade that exposes only permitted operations and calls services through Spring-managed dependencies.

## 6. Separating Three Failure Layers to Avoid Wrong Fixes

| Layer | Symptom | What to Inspect |
|---|---|---|
| Registration | MBean does not exist | Exporter, ObjectName, MBeanServer, bean discovery |
| Metadata | MBean exists, but operation/attribute is missing | Annotation source, assembler, target type, proxy-visible methods |
| Invocation | Metadata exists, but invoking fails | Proxy interface, method signature, runtime object, advice, business exception |

Example:

\`\`\`java
ObjectName name = new ObjectName(
    "app.management:type=Worker,name=main"
);

boolean registered = server.isRegistered(name);
\`\`\`

If \`false\`, do not start by modifying \`@ManagedOperation\`. First verify that the exporter registered the bean on the right server/name.

If \`true\`, read \`MBeanInfo\`:

\`\`\`java
MBeanInfo info = server.getMBeanInfo(name);

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.println(op.getName());
}
\`\`\`

If the method appears in metadata, the next step is to test \`invoke\`, rather than continuing to assume the annotation was not detected.

## 7. Checking Whether the Runtime Bean Is an AOP Proxy

Spring provides \`org.springframework.aop.support.AopUtils\`.

\`\`\`java
import org.springframework.aop.support.AopUtils;

Object bean = context.getBean("jobServiceImpl");

System.out.println(
    "Runtime type: " + bean.getClass().getName()
);
System.out.println(
    "Is proxy: " + AopUtils.isAopProxy(bean)
);
System.out.println(
    "JDK proxy: " + AopUtils.isJdkDynamicProxy(bean)
);
System.out.println(
    "CGLIB proxy: " + AopUtils.isCglibProxy(bean)
);
System.out.println(
    "Target class: " + AopUtils.getTargetClass(bean).getName()
);
\`\`\`

These APIs identify the proxy type and target class far more safely than guessing from class name strings like \`$Proxy...\` or \`$$SpringCGLIB$$...\`.

Note that \`AopUtils.getTargetClass\` returns the target type based on available metadata; it is not a mechanism for automatically extracting the target instance via reflection. Do not alter configuration to unwrap the target and call methods directly just to bypass a JMX error, as doing so can skip essential advice.

## 8. Checking Which Interfaces Actually Have the Method

Suppose:

\`\`\`java
Object bean = context.getBean("jobServiceImpl");
Class<?>[] interfaces = bean.getClass().getInterfaces();

for (Class<?> itf : interfaces) {
    System.out.println(itf.getName());
}
\`\`\`

With a JDK proxy, identify the relevant interfaces, especially the interface containing the management methods you want to expose.

You can inspect:

\`\`\`java
for (var method : JobService.class.getMethods()) {
    System.out.println(method);
}
\`\`\`

If \`maintenance\` is not on \`JobService\`, a JDK proxy backed solely by \`JobService\` cannot accept a \`maintenance()\` call as a method of that interface.

One caveat: a Spring proxy may implement multiple interfaces, including infrastructure interfaces. Do not use the fact that a proxy implements multiple interfaces as proof that every implementation method is exposed.

## 9. Why Annotations Can Drop Off the Metadata Path

Java reflection distinguishes methods declared on:

\`\`\`text
JobService.startJob()
JobServiceImpl.startJob()
\`\`\`

An annotation placed on an implementation method does not automatically become an annotation on the interface method under plain Java reflection rules.

A metadata source operating on interface methods may not see annotations placed on the implementation unless additional lookup logic is present. Conversely, Spring Framework has utilities to resolve the most specific method and annotations by target type, so do not claim "a JDK proxy always strips @ManagedOperation."

The right questions are:

- From which type is the exporter reading metadata?
- Is the assembler inspecting a \`Method\` representing the interface or the target?
- Does the annotation source handle proxies/interfaces?
- Can the MBean registration adapter invoke the exposed method?

This is why **runtime metadata inspection** is needed, not just reading source code.

## 10. AnnotationJmxAttributeSource and MetadataMBeanInfoAssembler

In Spring Framework JMX, annotation-based metadata can involve:

\`\`\`text
AnnotationJmxAttributeSource
    |
    v
MetadataMBeanInfoAssembler
    |
    v
ModelMBeanInfo
    |
    v
Spring MBeanExporter / ModelMBean
\`\`\`

\`AnnotationJmxAttributeSource\` supplies metadata from Spring JMX annotations. \`MetadataMBeanInfoAssembler\` builds MBeanInfo for the appropriate attributes, operations, and notifications.

However:

- The assembler cannot by itself guarantee every method inside the target is callable through a proxy.
- Metadata can be limited by the methods handled by the export adapter.
- The exporter may be using a different assembler than the default.
- A custom proxy may obscure target type information.
- Scanner configuration, bean names, and object naming strategies also affect registration.

In an application with multiple exporters, check which exporter actually registers the ObjectName being diagnosed.

## 11. Complete Diagnostic Example

### 11.1. Business interface

\`\`\`java
package example.jmx;

public interface BillingOperations {
    String settle(String batchId);
}
\`\`\`

### 11.2. Target implementation

\`\`\`java
package example.jmx;

import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@ManagedResource(
    objectName = "app.management:type=Billing,name=main"
)
public class BillingService implements BillingOperations {

    @Override
    @Transactional
    @ManagedOperation(description = "Settle a billing batch")
    public String settle(String batchId) {
        return "accepted:" + batchId;
    }

    @ManagedOperation(description = "Reset local diagnostic state")
    public void resetDiagnostics() {
        // Method present only on implementation.
    }
}
\`\`\`

### 11.3. Java configuration

\`\`\`java
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@ComponentScan(basePackageClasses = BillingService.class)
@EnableTransactionManagement
@EnableMBeanExport
public class BillingConfig {
}
\`\`\`

This snippet illustrates proxy/annotation export configuration. \`@EnableTransactionManagement\` requires an appropriate transaction manager for advice to take effect; the annotation does not supply a transaction manager by itself.

### 11.4. Inspect bean

\`\`\`java
Object bean = context.getBean("billingService");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.getTargetClass(bean));
\`\`\`

If \`isJdkDynamicProxy=true\`, inspect the proxy's interfaces and annotation placement. Although \`settle\` belongs to the interface, \`resetDiagnostics\` only exists on the target, so it may not be invokable if the exporter uses the proxy interface as the invocation surface.

### 11.5. Inspect JMX

\`\`\`java
MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "app.management:type=Billing,name=main"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException(
        "MBean not registered: " + name
    );
}

MBeanInfo info = server.getMBeanInfo(name);

for (var operation : info.getOperations()) {
    System.out.println(
        operation.getName() + " -> " +
        operation.getReturnType()
    );
}
\`\`\`

The example uses the platform server; if the exporter uses a custom server, query the exact MBeanServer bean.

## 12. Solution 1: Explicit Management Interface

Instead of leaving a management method only on the implementation:

\`\`\`java
public interface BillingManagement {
    String settle(String batchId);
    void resetDiagnostics();
}
\`\`\`

The implementation can implement the interface:

\`\`\`java
public class BillingService
        implements BillingOperations, BillingManagement {

    @Override
    @ManagedOperation
    public String settle(String batchId) {
        return "accepted:" + batchId;
    }

    @Override
    @ManagedOperation
    public void resetDiagnostics() {
        // ...
    }
}
\`\`\`

If the proxy is created with both interfaces, the management methods have a valid invocation path through the JDK proxy. However, you still need to verify that the annotation source/exporter recognizes the metadata and exposes it as intended.

Note that a management interface should not be a full copy of the entire business interface. Expose only safe, meaningful, and permitted administrative operations.

## 13. Solution 2: Separate Management Facade

A design that is often more predictable:

\`\`\`text
JMX client
    |
    v
BillingManagementFacade @ManagedResource
    |
    v
BillingOperations (Spring AOP proxy)
    |
    v
BillingService target
\`\`\`

Example:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "app.management:type=Billing,name=main"
)
public class BillingManagementFacade {

    private final BillingOperations billingOperations;

    public BillingManagementFacade(
            BillingOperations billingOperations
    ) {
        this.billingOperations = billingOperations;
    }

    @ManagedOperation(
        description = "Settle a billing batch"
    )
    public String settle(String batchId) {
        if (batchId == null || batchId.isBlank()) {
            throw new IllegalArgumentException("batchId required");
        }
        return billingOperations.settle(batchId);
    }
}
\`\`\`

The facade is an independent Spring bean carrying dedicated management metadata, while the business service still receives transaction/logging/security advice via its Spring proxy.

Advantages:

- The exporter gets a management class with clear public methods.
- Exposes only explicitly chosen operations.
- Prevents the service's JDK proxy from dictating the entire management API.
- Keeps the ObjectName stable when implementations change.
- Easy to add validation, authorization, auditing, and tests.

If the facade itself is also proxied by AOP, you still need to verify how it is exported. A facade reduces coupling; it does not exempt you from Spring's proxy/metadata rules.

## 14. Solution 3: Class-Based Proxy

Spring supports class-based proxies when appropriate:

\`\`\`java
@EnableAspectJAutoProxy(proxyTargetClass = true)
\`\`\`

or with transaction infrastructure depending on version:

\`\`\`java
@EnableTransactionManagement(proxyTargetClass = true)
\`\`\`

With a CGLIB proxy, methods on the target class typically remain callable on the proxy subclass, provided they are not constrained by \`final\`, visibility, or how advice applies.

However:

- A \`final\` method cannot be overridden by a subclass to intercept under this mechanism.
- Self-invocation via \`this\` still generally bypasses advice.
- Annotation metadata is not guaranteed to export properly if using a custom assembler.
- \`proxyTargetClass\` can affect many other beans, not just one MBean.
- You should not change the entire proxy strategy merely to cover up an unclear management API design.

Use this when it fits the overall AOP architecture, while re-verifying MBeanInfo and invocation.

## 15. Solution 4: Intentional Exporter and Assembler Configuration

In manual configuration:

\`\`\`java
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;

AnnotationJmxAttributeSource source =
    new AnnotationJmxAttributeSource();

MetadataMBeanInfoAssembler assembler =
    new MetadataMBeanInfoAssembler(source);

MBeanExporter exporter = new MBeanExporter();
exporter.setAssembler(assembler);
\`\`\`

This only illustrates metadata configuration. A complete exporter also needs an MBeanServer, bean mapping/ObjectName, and Spring lifecycle integration.

Adjusting the assembler only makes sense if the fault genuinely lies in the metadata source/assembly. It does not add methods to a JDK proxy, does not handle authorization automatically, and does not fix an exporter pointing to the wrong MBeanServer.

Some cases call for \`InterfaceBasedMBeanInfoAssembler\` or an explicit management interface instead of annotation metadata. In that case, understand the assembler's purpose: selecting which interface methods are exposed; do not swap assemblers without a clear management contract.

## 16. Inspecting MBeanInfo Accurately

Read each operation along with its signature:

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.print(op.getName() + "(");

    MBeanParameterInfo[] params = op.getSignature();
    for (int i = 0; i < params.length; i++) {
        if (i > 0) {
            System.out.print(", ");
        }
        System.out.print(params[i].getType());
    }

    System.out.println(") -> " + op.getReturnType());
}
\`\`\`

If \`settle(java.lang.String)\` is present, a client can try:

\`\`\`java
Object result = server.invoke(
    name,
    "settle",
    new Object[] { "batch-001" },
    new String[] { "java.lang.String" }
);
\`\`\`

If the operation is missing, do not blindly call a different signature; first check the exporter/assembler and annotations.

If the operation is present yet \`invoke\` fails, examine the exception chain, runtime proxy, and business logic. \`ReflectionException\` often points to a reflection/signature issue, though not always caused by annotations.

## 17. Checking @ManagedAttribute with a JDK Proxy

A similar issue can occur with getters/setters.

\`\`\`java
public interface QueueService {
    int getDepth();
}
\`\`\`

Implementation:

\`\`\`java
@ManagedAttribute
public int getDepth() {
    return 12;
}

@ManagedAttribute
public void setWorkerLimit(int limit) {
    // ...
}
\`\`\`

If the JDK proxy only has \`getDepth\`, the \`setWorkerLimit\` method is not on the proxy interface. Depending on the metadata exporter and invocation path, the writable attribute may not appear or may fail when written.

Therefore:

1. Check \`MBeanAttributeInfo.isReadable()\` and \`isWritable()\`.
2. Cross-check getters/setters against the proxy interface.
3. Determine where the annotations are placed.
4. Test \`getAttribute\`/\`setAttribute\` in a test.
5. Consider a management facade if you need to restrict the JMX surface.

Do not treat the existence of Java getters/setters on the target as proof that a JMX client can read/write them.

## 18. Verify the Right ObjectName and MBeanServer Before Blaming the Proxy

An error that looks like "annotation not recognized" may simply be querying the wrong registry.

Example:

\`\`\`java
MBeanServer actual =
    context.getBean("managementServer", MBeanServer.class);

ObjectName name = new ObjectName(
    "app.management:type=Billing,name=main"
);

System.out.println(
    actual.isRegistered(name)
);
\`\`\`

If the exporter is configured with \`setServer(customMBeanServer)\` while JConsole is observing the platform MBeanServer, not seeing the MBean is expected behavior.

Distinguish:

- \`@ManagedResource.objectName\` declares an explicit name.
- \`ObjectNamingStrategy\` may determine a different actual name.
- Multiple exporters may register MBeans on different servers.
- RegistrationPolicy may cause a registration to be skipped or replaced.

Thus, the first diagnostic step is verifying the exporter, server, and ObjectName before adjusting AOP.

## 19. Creation Order of Proxy, Exporter, and Metadata

In the Spring container:

\`\`\`text
Bean definitions
       |
       v
BeanPostProcessors / AutoProxyCreator
       |
       v
Target bean initialized
       |
       v
AOP proxy (if applicable)
       |
       v
MBeanExporter receives bean reference
       |
       v
Metadata assembler / naming
       |
       v
MBeanServer registration
\`\`\`

This is a generalized order in normal cases. Do not treat it as an absolute guarantee for all \`BeanFactoryPostProcessor\` setups, infrastructure beans, and complex lifecycles.

If a bean is instantiated too early before full auto-proxy infrastructure is ready, the exporter may receive the target instead of the proxy, yielding unexpected behavior. One sign is Spring logging that a bean is not eligible for getting processed by all BeanPostProcessors.

To diagnose:

- Check bean/runtime types after context initialization.
- Identify the exporter bean and its dependencies.
- Verify the target is not manually instantiated with \`new\` outside the Spring context.
- Avoid retrieving business beans too early from BeanPostProcessor/infrastructure code.
- Use integration tests to observe the actual ObjectName/metadata/invocation behavior.

## 20. Does Aspect Advice Run When Invoked via JMX?

An operation with \`@Transactional\` may be invoked via:

\`\`\`text
MBeanServer
   |
   +--> Spring AOP proxy -> Transaction advice -> target
   |
   +--> Direct target -> may bypass advice
\`\`\`

Having both \`@ManagedOperation\` and \`@Transactional\` on the same method **does not guarantee** the transaction interceptor runs during a JMX invocation.

Verify:

1. The bean is actually auto-proxied.
2. The exporter holds the appropriate reference.
3. The operation is invoked through a proxy-visible method.
4. A transaction manager exists and the advisor applies.
5. It is not bypassed by self-invocation.
6. Tests verify real transactional side effects, not just an in-memory counter.

For critical administrative operations, a management facade calling a business interface proxy can make the invocation path easier to control.

## 21. Integration Testing to Prevent Regressions

A Spring test can assert three levels:

\`\`\`text
A. Bean:
   AopUtils.isJdkDynamicProxy(bean) == true/false per configuration

B. Registration/metadata:
   server.isRegistered(name) == true
   MBeanInfo contains the required operation

C. Invocation:
   server.invoke(...) executes successfully
   state/transaction/advice behaves properly
\`\`\`

Example assertion:

\`\`\`java
MBeanInfo info = server.getMBeanInfo(name);

boolean exposed = Arrays.stream(info.getOperations())
    .anyMatch(op ->
        op.getName().equals("settle")
        && op.getSignature().length == 1
        && op.getSignature()[0].getType()
            .equals("java.lang.String")
    );

assertTrue(exposed);

Object result = server.invoke(
    name,
    "settle",
    new Object[] { "batch-001" },
    new String[] { "java.lang.String" }
);

assertEquals("accepted:batch-001", result);
\`\`\`

This snippet requires \`server\` and \`name\` to be initialized along with the appropriate imports. When business side effects exist, tests must run with a safe fixture and verify actual state.

Do not merely assert via reflection that \`@ManagedOperation\` exists on the target class; that does not test the exporter or proxy.

## 22. A Troubleshooting Decision Table

| Observation | Suspected Cause | Resolution Approach |
|---|---|---|
| Bean does not exist in context | Scanning/configuration | Fix component scan/bean definition |
| Bean exists, JDK proxy, MBean missing | Exporter annotation detection/naming/lifecycle | Check exporter/server/ObjectName and metadata source |
| MBean exists, but target-only method is missing | Proxy interface does not expose method or assembler skips it | Management interface/facade |
| MBeanInfo has method, but invoke fails | Invocation path/signature/business method | Inspect root cause and proxy type |
| Annotation on interface, exporter misses it | Assembler annotation lookup rules | Check version/config, use facade or appropriate metadata |
| Works after switching to CGLIB | JDK proxy surface limitation played a role | Keep tests and evaluate proxy strategy impact |
| Operation runs, but advice is lost | Exporter calls target or self-invocation | Check proxy reference, facade, and transaction config |
| Only JConsole misses it, local server query sees it | Client connected to a different server | Configure connector to use the same MBeanServer |

## 23. Mistakes to Avoid

### Mistake 1: Switching proxy-target-class=true immediately

This can affect many Spring beans and fails to fix exporter/server or metadata source errors.

### Mistake 2: Moving all annotations onto the interface without checking

There is no guarantee every assembler/version interprets interface annotations identically. Test both metadata and invocation.

### Mistake 3: Using the target object directly to bypass the proxy

This can lose transaction/security/logging advice and create an administrative invocation path that differs from the business path.

### Mistake 4: Thinking seeing annotations in source code is enough

You must inspect the \`MBeanInfo\` published by the MBeanServer.

### Mistake 5: Testing only with JConsole

JConsole has UI limitations. Use the JMX API to verify ObjectName, metadata, and invocation.

### Mistake 6: Changing registration policy to mask the error

\`REPLACE_EXISTING\` or \`IGNORE_EXISTING\` will not fix methods hidden by a proxy. ObjectName collisions are a separate class of error.

### Mistake 7: Exposing every public method from a service

This can expose internal services or dangerous operations. Use a narrow management API.

## 24. Diagnostic Checklist

- [ ] Are the Spring bean and bean name correct?
- [ ] Is the runtime bean a target, JDK dynamic proxy, or CGLIB proxy?
- [ ] Was the target class confirmed via \`AopUtils.getTargetClass\`?
- [ ] Is the management method present on the proxy interface?
- [ ] Are annotations placed on the interface, implementation, or facade?
- [ ] Is the exporter enabled and receiving the right bean?
- [ ] Which assembler/annotation source is being used?
- [ ] Are the ObjectName and MBeanServer correct?
- [ ] Does \`isRegistered\` return true?
- [ ] Does \`MBeanInfo\` have the attributes/operations with exact signatures?
- [ ] Do \`invoke\` or \`getAttribute\` succeed?
- [ ] Does required AOP advice actually execute?
- [ ] Are there no duplicate exporters or overly early bean instantiations?
- [ ] Is there an integration test protecting the JMX contract?

## 25. Hands-on Exercises

**Scenario:** The \`OrderService\` interface only declares:

\`\`\`java
public interface OrderService {
    void processOrder(String orderId);
}
\`\`\`

The implementation adds:

\`\`\`java
@ManagedOperation
public void clearTemporaryState() {
    // ...
}
\`\`\`

The application uses a JDK dynamic proxy and \`@EnableMBeanExport\`. JConsole does not show \`clearTemporaryState\`.

**Question A:** Why is inspecting \`OrderServiceImpl.class.getDeclaredMethods()\` alone insufficient to draw a conclusion?

Because the JMX exporter may operate on the proxy interface, and the actual management surface resides in \`MBeanInfo\`.

**Question B:** How can you fix this without expanding the \`OrderService\` business interface?

Create a separate \`OrderManagementFacade\`, annotate it with \`@ManagedResource\`, and expose only \`clearTemporaryState\` if that action is genuinely appropriate for management. The facade injects the necessary service interface.

**Question C:** How do you prove the fix works?

Verify that the ObjectName is registered, \`MBeanInfo\` contains the \`clearTemporaryState\` operation, and \`MBeanServer.invoke\` runs successfully against a safe fixture.

## 26. Self-Check Questions

1. Does a JDK dynamic proxy expose every public implementation method?
2. Why might an implementation annotation not show up when metadata is read from an interface method?
3. What evidence does \`AopUtils.isJdkDynamicProxy\` provide?
4. How does a missing MBean differ from an MBean missing an operation?
5. Does a CGLIB proxy solve all annotation and invocation issues?
6. Why is a management facade often more appropriate than exposing an entire service?
7. When should you inspect \`MBeanInfo\`, and when should you test \`invoke\`?
8. How can an exporter using the target directly affect AOP advice?
9. How can a wrong ObjectName and MBeanServer produce symptoms similar to an annotation issue?
10. Why is an integration test better than merely checking annotations in source code?

## 27. Key Takeaways

\`\`\`text
Target implementation
  @ManagedResource / @ManagedOperation
           |
           v
      Spring AOP
           |
     JDK proxy interface
           |
           v
   Exporter + metadata assembler
           |
           v
        MBeanInfo
           |
           v
      MBeanServer
           |
           v
        JMX client
\`\`\`

**Core Principle:** When JMX annotations "disappear" in an AOP-enabled application, first determine which proxy the actual bean is, where the exporter reads metadata from, and what contract the MBeanServer publishes. Do not assume JDK proxies always strip annotations or that CGLIB always solves everything. For a management API that needs stability, separate a clear facade, use a fixed ObjectName, and test registration, metadata, and invocation alike.