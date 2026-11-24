# Target-Class Proxying When JMX Metadata Must Be Preserved

## Lesson Objectives

After this lesson, you will be able to:

- Explain why Spring AOP proxies can affect the detection of \`@ManagedResource\`, \`@ManagedAttribute\`, and \`@ManagedOperation\` during JMX export.
- Distinguish **JDK dynamic proxies** from **class-based proxies** (proxies based on the target class, typically via CGLIB).
- Understand the meaning of \`proxyTargetClass = true\` and its limitations.
- Design stable JMX management interfaces, even when business services use \`@Transactional\`, \`@Async\`, or Spring AOP.
- Verify the metadata actually exposed using \`MBeanServer.getMBeanInfo(...)\`, rather than inferring solely from annotations in source code.
- Spot bugs when changing proxy strategies causes MBeans to lose attributes/operations or fail to be autodetected.

## 1. The Problem: A Spring Bean at Runtime May Be a Proxy

When an application uses Spring AOP, Spring can return a **proxy** instead of the direct target object. The proxy sits in front of the target to apply advice such as transactions, logging, or security.

Example:

\`\`\`java
@Service
@Transactional
public class PaymentService {
    public void processPayment() {
        // ...
    }
}
\`\`\`

With appropriate AOP configuration, the bean provided by the ApplicationContext can be a proxy. This creates two conceptual layers:

\`\`\`text
Spring ApplicationContext
        |
        v
Managed proxy object
        |
        | method call / advice
        v
Target object: PaymentService
\`\`\`

Meanwhile, JMX information may be declared on the target class:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=Payments,name=Primary"
)
public class PaymentService {
    @ManagedAttribute
    public int getPendingPayments() {
        return 0;
    }
}
\`\`\`

If the exporter/autodetection or metadata assembler sees a different Java type than the one carrying the annotations, it may fail to locate the right resource or fail to expose the expected methods.

**Key point:** Having \`@ManagedResource\` on the original class is not enough to conclude that the MBean is registered and its metadata is accurate. You must understand proxies and verify the actual MBean.

## 2. JDK Dynamic Proxies and Class-Based Proxies

Spring AOP typically has two proxy groups:

| Criterion | JDK dynamic proxy | Class-based proxy |
|---|---|---|
| Structure | Proxy implements one or more interfaces | Proxy is a subclass of the target class when possible |
| When used | Commonly chosen when interfaces exist and config does not force class proxies | When \`proxyTargetClass\` is enabled or class-based proxying is needed |
| Runtime class | Not a direct subclass of the target implementation | Typically a generated subclass of the target class |
| Visible methods | Primarily methods present on the proxied interfaces | Proxyable methods on the target class |
| Possible JMX impact | Annotations on target class/methods absent from proxy interfaces may require target metadata handling | More direct visibility of target class/methods in certain configurations |
| Limitations | If an interface does not declare a method, the proxy lacks that method | Cannot proxy final classes or final methods via subclassing |

**Do not conclude that JDK proxies always break JMX or that class-based proxies always solve everything.** Spring Framework has mechanisms to identify target classes and metadata on proxies in many cases. The final result still depends on the exporter, assembler, naming strategy, advisors, and how the application configures beans.

## 3. Why Can JMX Metadata Be Affected?

Consider a target:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=JobService,name=Primary"
)
public class JobServiceImpl implements JobService {

    @ManagedAttribute
    public int getRunningJobs() {
        return 3;
    }

    @ManagedOperation
    public void resetStats() {
        // ...
    }
}
\`\`\`

Interface:

\`\`\`java
public interface JobService {
    void executeJob();
}
\`\`\`

With a JDK proxy, the proxy object typically implements \`JobService\`, while \`getRunningJobs()\` and \`resetStats()\` do not appear on that interface. Depending on how Spring JMX handles target classes and invocable methods, the exporter may have difficulty exposing or invoking methods that exist only on the implementation.

With a class-based proxy, the proxy can inherit the target's public, non-final methods. This helps preserve the class-level method surface in many situations.

However, three issues must be distinguished:

1. **Autodetection:** does Spring detect the \`@ManagedResource\` resource?
2. **Metadata assembly:** does the MBean expose the right attributes and operations?
3. **Invocation:** when a client invokes an operation or reads an attribute, does the call reach the right method?

Changing proxy strategies can affect each issue differently. Therefore, all three layers need checking.

## 4. What Is a Target Class in Spring AOP?

The target class is the class type represented by the proxy. Spring provides APIs to help identify it:

\`\`\`java
import org.springframework.aop.support.AopUtils;

Object bean = context.getBean("jobService");

Class<?> runtimeClass = bean.getClass();
Class<?> targetClass = AopUtils.getTargetClass(bean);

System.out.println("Runtime: " + runtimeClass.getName());
System.out.println("Target: " + targetClass.getName());
System.out.println("Is proxy: " + AopUtils.isAopProxy(bean));
\`\`\`

Example output might be:

\`\`\`text
Runtime: jdk.proxy...$Proxy...
Target: example.jmx.JobServiceImpl
Is proxy: true
\`\`\`

or with a class-based proxy:

\`\`\`text
Runtime: example.jmx.JobServiceImpl$$SpringCGLIB$$...
Target: example.jmx.JobServiceImpl
Is proxy: true
\`\`\`

The runtime proxy name is an implementation detail that can change across Java/Spring versions. Do not write a JMX naming scheme based on generated proxy class name strings.

**Important:** \`AopUtils.getTargetClass(...)\` helps diagnose or obtain the target type, but calling that API does not itself change how the exporter exposes metadata. Export configuration still needs separate verification.

## 5. When to Consider Target-Class Proxying?

Target-class proxying is useful when:

- JMX methods are annotated on the concrete target class and are absent from the bean's interfaces.
- You need Spring AOP applied to proxyable methods of the concrete class.
- Certain reflection/metadata discovery mechanisms in the application rely on the concrete class.
- Switching from JDK proxy to class proxy helps the exporter recognize or invoke management methods properly, and this has been verified with integration tests.

To force class-based proxies, Spring provides configurations such as:

\`\`\`java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AopConfiguration {
}
\`\`\`

If the application mainly uses transaction AOP, you can use:

\`\`\`java
@Configuration
@EnableTransactionManagement(proxyTargetClass = true)
public class TransactionConfiguration {
}
\`\`\`

Note that \`proxyTargetClass\` applies to the corresponding proxy mechanism and can affect many beans in the context. Do not enable it solely because of one JMX warning without identifying the root cause.

In Spring Boot, proxy strategy is also governed by auto-configuration and related properties. Check the actual runtime proxy rather than relying solely on an annotation present in source.

## 6. Application Example: Proxied Managed Bean

We have a business interface:

\`\`\`java
package example.jmx;

public interface QueueService {
    void submit(String jobId);
}
\`\`\`

Implementation:

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@ManagedResource(
    objectName = "learning.jmx:type=QueueService,name=Primary",
    description = "Queue management"
)
public class QueueServiceImpl implements QueueService {

    private final AtomicInteger pending = new AtomicInteger();

    @Override
    @Transactional
    public void submit(String jobId) {
        pending.incrementAndGet();
    }

    @ManagedAttribute(description = "Pending job count")
    public int getPendingJobs() {
        return pending.get();
    }

    @ManagedOperation(description = "Reset counters")
    public void resetCounters() {
        pending.set(0);
    }
}
\`\`\`

Here \`@ManagedAttribute\` and \`@ManagedOperation\` reside on the implementation, not on the \`QueueService\` interface.

If the application uses interface-based proxies, verify whether the exporter detects and exposes the two management methods. Class-based proxy configuration can help, but another architectural option is separating a JMX facade completely so it does not depend on the service's proxy strategy.

### Spring Configuration with Class-Based Proxy

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@ComponentScan("example.jmx")
@EnableMBeanExport
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class ApplicationConfiguration {
}
\`\`\`

To actually create a transaction proxy in an example using \`@Transactional\`, the application must enable transaction management and have appropriate transaction infrastructure. \`@EnableAspectJAutoProxy\` alone does not automatically guarantee \`@Transactional\` is processed.

You can replace it with or add the corresponding transaction configuration in the application:

\`\`\`java
@EnableTransactionManagement(proxyTargetClass = true)
\`\`\`

Use only the annotations/configuration relevant to the AOP features in use. The goal of the example is to show that **target-class proxying is configured at the AOP/transaction layer**, while the JMX exporter reads metadata at the management layer.

## 7. A More Reliable Approach: Management Facade Unaffected by Business Proxies

In large systems, a clear option is separating the management interface from the business service.

Service:

\`\`\`java
public interface QueueService {
    void submit(String jobId);
    int pendingCount();
}
\`\`\`

Service implementation may be proxied:

\`\`\`java
@Service
public class QueueServiceImpl implements QueueService {
    // Business logic; may have @Transactional or AOP
}
\`\`\`

Facade:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=Queue,name=Primary",
    description = "Queue operational view"
)
public class QueueManagement {

    private final QueueService service;

    public QueueManagement(QueueService service) {
        this.service = service;
    }

    @ManagedAttribute
    public int getPendingJobs() {
        return service.pendingCount();
    }

    @ManagedOperation
    public void refreshStatus() {
        // An appropriate management action, if needed.
    }
}
\`\`\`

Bean configuration:

\`\`\`java
@Bean
QueueManagement queueManagement(QueueService queueService) {
    return new QueueManagement(queueService);
}
\`\`\`

With this approach:

- MBean metadata lives on a dedicated, readable management class.
- The underlying service is proxied according to business needs.
- ObjectNames and JMX attribute/operation names depend less on service refactoring.
- You can clearly control which operations are exposed.
- No need to change the application-wide proxy strategy just to keep JMX annotations on the service.

If a JMX action needs to pass through a transactional service, the facade calls the service proxy so advice is still applied properly.

## 8. Verifying Actual Metadata via MBeanServer

Whether choosing JDK proxy, class-based proxy, or facade, verify the exported MBean:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.MBeanInfo;
import javax.management.ObjectName;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanOperationInfo;

MBeanServer server =
        ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
        "learning.jmx:type=QueueService,name=Primary"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException("MBean not registered");
}

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.println("Attribute: " + attribute.getName());
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println("Operation: " + operation.getName());
}
\`\`\`

Expected for QueueServiceImpl:

\`\`\`text
Attribute: PendingJobs
Operation: resetCounters
\`\`\`

Actual results depend on the exporter, proxy, and metadata assembly. If missing, check logs and runtime configuration instead of assuming annotations in source are enough for export.

### Checking Invocation

\`\`\`java
Object value = server.getAttribute(name, "PendingJobs");

server.invoke(
        name,
        "resetCounters",
        new Object[0],
        new String[0]
);
\`\`\`

This snippet should only run on a test instance or controlled environment; the resetCounters operation mutates state.

**Distinction:** \`ManagementFactory.getPlatformMBeanServer()\` retrieves the current JVM's server. A client running in another JVM must connect via a JMX connector and use \`MBeanServerConnection\`. Also ensure the exporter actually uses this platform server.

## 9. Integration Testing Proxy Strategies

A valuable test should confirm **proxy type**, **registration**, **metadata**, and **invocation** inside a real Spring context.

Draft JUnit 5 example:

\`\`\`java
package example.jmx;

import static org.junit.jupiter.api.Assertions.*;

import java.lang.management.ManagementFactory;
import java.util.Arrays;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class QueueJmxProxyTest {

    @Test
    void exposesManagedMethodsThroughJmx() throws Exception {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                        ApplicationConfiguration.class)) {

            Object bean = context.getBean(QueueService.class);

            System.out.println(
                "Proxy=" + AopUtils.isAopProxy(bean)
            );
            System.out.println(
                "Target=" + AopUtils.getTargetClass(bean)
            );

            MBeanServer server =
                    ManagementFactory.getPlatformMBeanServer();

            ObjectName name = new ObjectName(
                "learning.jmx:type=QueueService,name=Primary"
            );

            assertTrue(server.isRegistered(name));

            boolean hasPendingJobs = Arrays.stream(
                server.getMBeanInfo(name).getAttributes()
            ).anyMatch(a -> "PendingJobs".equals(a.getName()));

            boolean hasResetCounters = Arrays.stream(
                server.getMBeanInfo(name).getOperations()
            ).anyMatch(o ->
                "resetCounters".equals(o.getName())
            );

            assertTrue(hasPendingJobs);
            assertTrue(hasResetCounters);
        }
    }
}
\`\`\`

If you need to be sure it is a class-based proxy, you can use:

\`\`\`java
assertTrue(AopUtils.isCglibProxy(bean));
\`\`\`

However, this assertion is only valid when the test **has configured an advisor that actually applies to the bean** and there is a reason forcing a class-based proxy. Without advice, Spring may return the target bean directly and \`isCglibProxy\` will be false even if \`proxyTargetClass=true\` was configured.

This is a common test mistake: \`proxyTargetClass=true\` is a policy **when creating a proxy**, not a command forcing every bean to be wrapped in a proxy.

### Full Test Checklist

A good test should confirm:

1. The bean is a Spring-managed bean in the context.
2. If an AOP advisor applies, verify the expected proxy type.
3. JMX metadata is recognized from the appropriate target/interface.
4. The MBean is registered under the right ObjectName.
5. Attributes and operations are present in \`MBeanInfo\`.
6. Reading attributes/invoking operations via JMX succeeds.
7. Closing the context unexports MBeans managed by the exporter.

## 10. Why Is proxyTargetClass=true Not a Cure-All?

Other causes can still prevent an MBean from being exported:

- The bean is not in the ApplicationContext managed by the exporter.
- \`@EnableMBeanExport\` or MBeanExporter is not enabled.
- The exporter uses an unsuitable autodetect mode.
- The assembler does not read \`@ManagedResource\`.
- The ObjectName collides or has invalid syntax.
- Metadata is placed on methods incompatible with the contract.
- The MBeanServer you inspect differs from the MBeanServer the exporter registers into.
- Final methods/classes restrict class-based proxying.
- The Spring bean has a special scope, lifecycle, or FactoryBean.
- The remote JMX client lacks permissions or connects to the wrong JVM.

Switching to class-based proxies only addresses a subset of issues involving proxy type/metadata visibility. If the cause is an ObjectName collision or an inactive exporter, changing proxy strategy will not fix it.

## 11. Final Classes, Final Methods, and Class-Based Proxies

Class-based proxies usually rely on subclassing. Therefore:

\`\`\`java
public final class FinalService {
    public void execute() { }
}
\`\`\`

cannot be proxied by creating a subclass of a final class.

A final method also cannot be overridden for Spring to apply advice via normal subclassing.

Example:

\`\`\`java
public class QueueService {
    public final void submit(String jobId) {
        // ...
    }
}
\`\`\`

If \`submit\` needs to be intercepted by Spring AOP, a class-based proxy will be unable to override this method. Consider interface-based proxies or changing the design as needed.

For JMX metadata, a final method can still be a Java method on the target, but the relationship between proxy invocation, advice, and the exporter must be checked in practice. Do not assume class-based proxying guarantees every operation runs expected advice.

## 12. JDK Proxies and Clear Management Interfaces

You do not always need to switch to class-based proxies. If a service uses a JDK dynamic proxy, you can design an appropriate management interface and configure JMX export to expose that contract.

Example:

\`\`\`java
public interface QueueManagementView {
    int getPendingJobs();
    void resetCounters();
}
\`\`\`

If the same proxy needs to execute these methods, the proxy's interface must include them and the exporter/assembler must be configured accordingly.

Another approach is registering a separate management facade, avoiding complicating business interfaces.

**Design trade-offs:**

- JDK dynamic proxies fit when code already uses interfaces as boundaries and only needs to expose methods on those interfaces.
- Class-based proxies are useful when needing to preserve a concrete class surface.
- A management facade fits when the JMX contract needs to remain stable independently of business code and AOP advice.

Choose based on operational requirements, not just whether “JConsole can see the method”.

## 13. Inspecting Metadata When AOP Advice Is Present

When debugging, collect three kinds of information:

**Bean information:**

\`\`\`java
Object bean = context.getBean("queueServiceImpl");

System.out.println(bean.getClass());
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
System.out.println(AopUtils.getTargetClass(bean));
\`\`\`

**MBean registration information:**

\`\`\`java
System.out.println(server.isRegistered(objectName));
\`\`\`

**JMX contract information:**

\`\`\`java
MBeanInfo info = server.getMBeanInfo(objectName);
\`\`\`

If the bean is a JDK proxy and \`MBeanInfo\` is missing an annotated operation from the target, that is a sign to check metadata assembly and invocable method selection.

If the MBean is not registered, read exceptions in startup logs and check the exporter before diving into method metadata.

If the MBean is registered and MBeanInfo is correct but invocation fails, check the signature and exception wrappers on the JMX call; also verify whether the proxy forwards the call properly to the target.

## 14. Lifecycle and ObjectName Collisions in Tests

Spring contexts can be created multiple times in a single JVM, especially in integration tests.

When testing JMX configurations:

- Use a stable ObjectName per managed resource.
- Avoid having two contexts alive simultaneously registering the same name.
- Close contexts after tests so the exporter unregisters MBeans within its scope.
- If tests run in parallel, consider a dedicated MBeanServer for tests.
- Do not set \`REPLACE_EXISTING\` just to mask collisions from other tests.

A dedicated MBeanServer can be created with:

\`\`\`java
MBeanServer testServer =
        MBeanServerFactory.createMBeanServer("test.jmx");
\`\`\`

If using this server, configure the exporter accordingly. Creating a test server does not automatically make the exporter switch registration from the platform server to it.

## 15. Security Considerations for Management Methods

A JMX operation can mutate application state:

\`\`\`java
@ManagedOperation
public void resetCounters() {
    // ...
}
\`\`\`

When using proxies and AOP, do not assume every security advice from the HTTP or service layer automatically applies as expected to a JMX invocation.

For instance, a Spring Security HTTP filter does not automatically control direct calls over JMX. If a method has method-level security, verify that JMX invocations pass through the right proxy/advice. With class-based proxies, final methods can also prevent advice from running.

Design security in layers:

1. Restrict access to local/remote JMX connectors.
2. Narrow the exported attributes and operations.
3. Verify side effects and authentication/authorization at the appropriate layer.
4. Log sensitive management actions if operationally required.
5. Write integration tests confirming actual behavior through JMX, instead of testing only direct method calls.

## 16. Common Errors

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Bean has @ManagedResource but MBean does not appear | Exporter/autodetect not enabled, proxy metadata unread, invalid ObjectName | Check exporter, logs, and isRegistered |
| MBean appears but missing ManagedAttribute | Getter not recognized through metadata/proxy | Check targetClass, assembler, and MBeanInfo |
| Operation appears but invoke fails | Method not invocable on proxy or wrong signature | Check proxy interfaces/methods and exceptions |
| proxyTargetClass=true enabled yet isCglibProxy still false | No advisor applies to the bean | Verify AOP advice is actually created |
| JDK proxy exposes only interface methods | Management method only on implementation | Consider class proxy, suitable interface, or facade |
| Class-based proxy does not work | Final target class or unsuitable AOP configuration | Check class/method modifiers |
| Transaction advice does not run via JMX | Invocation bypasses proxy or wrong configuration | Test JMX invocation and transaction boundary |
| MBean right but no remote permissions | JMX connector/auth/network | Check connection separately; do not treat as metadata failure |
| Duplicate ObjectName registration | Two contexts/beans export the same name | Check owner, lifecycle, and naming strategy |
| Renaming Spring bean loses MBean | Naming strategy depends on bean name | Keep ObjectName stable or migrate intentionally |

## 17. Practice Exercises

### Exercise 1 — Observe Proxy Type

Create a service with an interface and an advisor that actually applies. Run two configurations:

- \`proxyTargetClass = false\`
- \`proxyTargetClass = true\`

Use \`AopUtils.isJdkDynamicProxy\`, \`AopUtils.isCglibProxy\`, and \`AopUtils.getTargetClass\` to compare.

Explain why checking only the bean's class name is insufficient.

### Exercise 2 — Annotations on Target Class

Place \`@ManagedResource\`, \`@ManagedAttribute\`, and \`@ManagedOperation\` on the implementation class; the business interface has only one non-JMX method.

Verify the autodetected MBean and MBeanInfo under both proxy strategies. If results differ, identify the missing metadata/method and try class-based proxying or a management facade.

### Exercise 3 — Switch to a Management Facade

Separate a managed resource from a business service that already has \`@Transactional\`. Put JMX annotations on the new facade and have the facade call the service proxy.

Compare this design with applying \`proxyTargetClass=true\` across the entire application.

### Exercise 4 — Contract Test

Write an integration test verifying:

\`\`\`text
ObjectName = learning.jmx:type=QueueService,name=Primary
Attribute  = PendingJobs
Operation  = resetCounters
\`\`\`

Read \`MBeanInfo\`, then use \`getAttribute\` and \`invoke\` to verify the contract.

### Exercise 5 — Risk Assessment

An important JMX method has \`@ManagedOperation\` and \`@PreAuthorize\`, yet when invoked from JConsole the security advice does not run. List the places to check: JMX connector authorization, bean proxy, target method, AOP advisor, final modifiers, and call path.

## 18. Checklist When Choosing Target-Class Proxying

Before enabling \`proxyTargetClass=true\`, answer:

1. Is there evidence that JDK proxies are causing incorrect JMX metadata/invocation?
2. Are annotations on the target class or interface?
3. Do management methods exist in the JDK proxy's interfaces?
4. Is the runtime bean actually an AOP proxy?
5. Are there any final classes or final methods affecting class proxying?
6. Will changing the proxy strategy impact other beans?
7. Does MBeanExporter have the right assembler, naming strategy, and autodetect mode?
8. Are the MBeanServer and ObjectName right?
9. Does \`MBeanInfo\` show the expected attributes/operations?
10. Can a management facade be used to separate the JMX contract and business proxy?

## 19. Core Takeaways

- **JMX metadata may live on the target class while the runtime Spring bean is a proxy.**
- JDK dynamic proxies primarily expose methods via interfaces; class-based proxies generally preserve the concrete class surface within subclassing limits.
- \`proxyTargetClass=true\` only affects the corresponding proxy creation mechanism; it does not enable JMX export or create a proxy when no advice applies.
- Spring JMX can handle target metadata in many cases; always verify the final result.
- To keep JMX contracts stable, a **management facade** is a worthwhile option when business services have many AOP concerns.
- Use \`AopUtils\` to diagnose beans/proxies, \`MBeanServer.isRegistered\` to confirm registration, and \`MBeanInfo\` to confirm attributes/operations.
- Test invocation via JMX when actions have side effects, transactions, or security advice.
- Change proxy strategy only after identifying the actual root cause; proxies do not fix ObjectName, exporter, or network errors.

## References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Reference — Proxying mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework API — AopUtils: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/support/AopUtils.html
- Spring Framework API — EnableAspectJAutoProxy: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/EnableAspectJAutoProxy.html
- Spring Framework API — ManagedResource: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedResource.html
- Java SE 21 — MBeanServer: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
