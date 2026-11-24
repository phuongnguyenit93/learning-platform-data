# Diagnosing Disappearing MBeans After Enabling AOP or Transactions in Spring Framework JMX

## 1. Scenario and Objectives

A Spring Framework application has a management bean appearing normally in JConsole. After adding \`@Transactional\`, \`@Async\`, \`@Cacheable\`, or AOP advice, the MBean disappears, changes name, or retains only some attributes/operations. Business methods still execute, yet JMX tools no longer see the resource under the familiar ObjectName.

Example:

\`\`\`java
@Component
@ManagedResource(
    objectName = "com.example.orders:type=OrderService,name=Primary")
public class OrderService {

    @ManagedAttribute
    public int getPendingOrders() {
        return 7;
    }

    @ManagedOperation
    public void refreshCache() {
        // Reload a cache used by the service.
    }

    @Transactional
    public void placeOrder() {
        // Business transaction.
    }
}
\`\`\`

Before enabling transactions, the exporter could discover the bean and expose its getter/operation. After adding AOP, Spring may place a **proxy** into the ApplicationContext. If the exporter/metadata assembler inspects only an interface or a different type from the original class, annotations and management methods may no longer be discovered properly. There are also cases where the MBean still exists under a **different ObjectName**, or the exporter registered it into an MBeanServer other than the one the client is observing.

This lesson helps you:

1. Distinguish an MBean truly not being registered from a client looking up the wrong name/server.
2. Understand how JDK dynamic proxies and class-based proxies (CGLIB) affect type and method visibility.
3. Explain the interaction among autodetection, \`AnnotationMBeanExporter\`, \`MBeanExporter\`, metadata assemblers, and Spring AOP.
4. Inspect target class, proxy interfaces, annotations, and \`MBeanInfo\` of a registered MBean.
5. Design low-risk configuration fixes without hastily disabling transactions or AOP.
6. Write integration tests protecting the JMX contract before and after enabling proxies.

## 2. Do Not Start by Assuming “The MBean Disappeared”

When JConsole does not display an MBean under its old name, there are several possibilities:

\`\`\`text
MBean not visible?
       |
       +-- Exporter not started / bean not selected
       |
       +-- Exporter registration failed, ObjectName collision
       |
       +-- Exporter uses a different MBeanServer
       |
       +-- ObjectName changed due to naming strategy/proxy type
       |
       +-- MBean exists but management interface changed
       |
       +-- JConsole/JMX client connected to different JVM or cached old UI
       |
       +-- Spring context closed, exporter unregistered
\`\`\`

The first thing to establish is whether the MBean exists in the server **actually used by the exporter**.

Example in the same JVM:

\`\`\`java
MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.orders:type=OrderService,name=Primary");

System.out.println(server.isRegistered(name));
\`\`\`

This snippet is only meaningful if the exporter uses the platform MBeanServer. With a custom \`MBeanServer\`, obtain the exact server injected into the exporter.

If \`isRegistered(name) == false\`, that is not yet enough to conclude the MBean disappeared: the name may have been generated differently after proxying was applied.

## 3. Execution Chain of Spring JMX Autodetection

Spring JMX can export beans by metadata or autodetection rules. Related components:

| Component | Role |
|---|---|
| \`MBeanExporter\` | Registers and manages MBean lifecycle |
| \`AnnotationMBeanExporter\` | Supports annotation-based exporting and autodetection |
| \`@ManagedResource\` | Describes the managed resource |
| \`@ManagedAttribute\` | Describes a managed getter/setter |
| \`@ManagedOperation\` | Describes a managed operation |
| \`MBeanInfoAssembler\` | Creates metadata for the exposed interface |
| \`ObjectNamingStrategy\` | Selects the ObjectName |
| Spring AOP proxy | Object seen by Spring container clients after applying advice |

You can picture it as:

\`\`\`text
Bean definition
      |
      v
Spring instantiates target
      |
      v
BeanPostProcessors may create proxy
      |
      v
Bean retrieved from container
      |
      v
JMX autodetection / exporter
      |
      +--> inspect target/proxy/metadata
      |
      +--> choose ObjectName
      |
      +--> build MBean interface
      |
      v
MBeanServer.registerMBean(...)
\`\`\`

An AOP change can affect **the bean type observed when the exporter runs** or the metadata assembler. Thus, Spring still being able to create the bean does not prove the exporter can expose the MBean under the current configuration.

### 3.1. Autodetection Does Not Mean Every Bean Is Exported

The exporter typically picks only objects matching the rules and metadata it uses. A class with \`@ManagedResource\` does not create an MBean automatically without a suitable exporter. If \`@EnableMBeanExport\` is configured in a different ApplicationContext or excluded from the current context, the exporter will not see the bean regardless of AOP.

### 3.2. Different Conditions Leading to Similar Symptoms

- No MBean in the registry: bean selection or registration error.
- ObjectName present but attributes missing: metadata/exposure error.
- Attributes present but invocation fails: proxy method dispatch or target invocation error.
- Name present but JConsole does not display it: connection/caching or UI issue.
- MBean present in a custom server but not in the platform server: server selection issue, not AOP.

## 4. JDK Proxies and CGLIB: What Changes?

### 4.1. JDK dynamic proxy

When a bean has interfaces and interface-based proxying is configured, Spring can create a JDK dynamic proxy. Then:

\`\`\`text
OrderServiceImpl implements OrderServiceApi
             |
             v
     JDK dynamic proxy
     implements OrderServiceApi
\`\`\`

The bean retrieved from the context may be a proxy class exposing only methods on the interface. A \`@ManagedOperation\` annotation placed on a method present only on the implementation may not be seen as expected by an introspection path.

Example:

\`\`\`java
public interface OrderServiceApi {
    void placeOrder();
}

@ManagedResource(
    objectName = "com.example.orders:type=OrderService,name=Primary")
public class OrderServiceImpl implements OrderServiceApi {

    @Override
    @Transactional
    public void placeOrder() {}

    @ManagedAttribute
    public int getPendingOrders() {
        return 7;
    }
}
\`\`\`

If \`getPendingOrders\` is not on the interface, a JDK proxy does not directly provide that method through its public interface. Spring has mechanisms to handle target class/metadata in some export paths, but **do not assume every custom exporter/assembler will handle it accurately**. Observe the actual type, metadata, and MBeanInfo.

### 4.2. Class-based proxy (CGLIB)

A class-based proxy subclasses the target class. Most public methods may still appear on the proxy class, but Java rules still apply:

- Final classes cannot be subclassed for this kind of proxy.
- Final methods cannot be overridden/advised.
- Private methods are not proxied via overriding.
- Self-invocation usually bypasses the proxy when using Spring proxy-based AOP.

A class-based proxy can help in some cases where methods absent from interfaces must be exposed, but it is not the default fix for every JMX error. It alters AOP semantics and may not suit the current class.

### 4.3. Do Transactions Necessarily Cause Proxying?

With Spring proxy-based transaction management, \`@Transactional\` usually causes eligible methods to be invoked through a proxy to apply transaction advice. However, which methods are actually proxied and by which mechanism depend on transaction config, interfaces, visibility, and Spring version.

**Do not disable transactions just to make the MBean appear.** First identify the actual proxy and introspection path. If a fix is needed, prefer adjusting exporter/interface/naming configuration rather than removing an essential business mechanism.

## 5. Diagnostic Step 1: Inspect the Actual Bean and Proxy

In the running ApplicationContext:

\`\`\`java
import org.springframework.aop.support.AopUtils;
import org.springframework.aop.framework.Advised;
import org.springframework.context.ApplicationContext;

Object bean = context.getBean("orderService");

System.out.println("Bean class: " + bean.getClass().getName());
System.out.println("AOP proxy: " + AopUtils.isAopProxy(bean));
System.out.println("JDK proxy: " + AopUtils.isJdkDynamicProxy(bean));
System.out.println("CGLIB proxy: " + AopUtils.isCglibProxy(bean));
System.out.println("Target class: " +
    AopUtils.getTargetClass(bean).getName());
\`\`\`

To use \`AopUtils\`, the project needs the appropriate Spring AOP module. After AOP is enabled, the expected result may be \`isAopProxy=true\`. Proxy class names may be JDK proxy classes or framework-generated subclasses with suffixes; do not build production logic on auto-generated class name strings.

### 5.1. Check proxy interfaces

\`\`\`java
for (Class<?> type : bean.getClass().getInterfaces()) {
    System.out.println(type.getName());
}
\`\`\`

If using a JDK proxy, identify which interfaces are actually exposed, especially management getters/operations. Do not just look at implementation source and assume the proxy has the same public API.

### 5.2. Inspect target metadata in a controlled manner

\`\`\`java
Class<?> targetType = AopUtils.getTargetClass(bean);
ManagedResource annotation =
    org.springframework.core.annotation.AnnotationUtils
        .findAnnotation(
            targetType,
            org.springframework.jmx.export.annotation.ManagedResource.class);

System.out.println(annotation != null);
\`\`\`

This tells you whether the target type has \`@ManagedResource\` metadata. It **does not prove the exporter received the metadata**, because the exporter may use a different metadata assembler or different autodetection configuration.

Do not unwrap the proxy to call the target directly in production just to “make JMX work”; doing so can bypass security, transactions, or other advice.

## 6. Diagnostic Step 2: Locate the Right MBeanServer

In Spring, an exporter can be configured with \`setServer(customMBeanServer)\` or receive a server from the context.

\`\`\`java
MBeanServer platform =
    ManagementFactory.getPlatformMBeanServer();
\`\`\`

If the application has its own server bean:

\`\`\`java
MBeanServer configured =
    context.getBean(MBeanServer.class);
\`\`\`

Only call \`getBean(MBeanServer.class)\` if the context actually has an unambiguous matching bean. In multi-server environments, use an explicit qualifier/bean name.

Compare:

\`\`\`java
System.out.println(
    platform.isRegistered(expectedObjectName));
System.out.println(
    configured.isRegistered(expectedObjectName));
\`\`\`

If the exporter uses a separate server, local JConsole usually looks at the JVM's platform server rather than automatically scanning every server created in the process.

### 6.1. Query names instead of checking only the old name

\`\`\`java
Set<ObjectName> found =
    configured.queryNames(
        new ObjectName("com.example.orders:*"),
        null);

for (ObjectName name : found) {
    System.out.println(name.getCanonicalName());
}
\`\`\`

If names are generated by a naming strategy based on class/proxy identity, the ObjectName may change after AOP is enabled. In that case, the MBean **did not disappear**—it merely changed identifier.

On large systems, prefer narrow domain patterns over \`*:* \` to avoid fetching the entire JMX registry.

## 7. Diagnostic Step 3: Verify Registration and Metadata

If an ObjectName is found, read \`MBeanInfo\`:

\`\`\`java
MBeanInfo info = configured.getMBeanInfo(name);

for (MBeanAttributeInfo attr : info.getAttributes()) {
    System.out.printf(
        "ATTR %s type=%s read=%s write=%s%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable());
}

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.println("OP " + op.getName());
}
\`\`\`

Analysis:

- \`MBeanInfo\` returns successfully with the right attributes/operations: the issue may be on the client/console side or searching the wrong name.
- Missing attributes: check annotations on methods, interfaces, and the metadata assembler.
- Missing operations: check \`@ManagedOperation\`, proxy interfaces, and the assembler.
- \`MBeanInfo\` differs from before: the exporter may be exposing a different interface due to the proxy.

### 7.1. Case where only a Standard MBean interface remains

If the implementation directly follows an \`XxxMBean\` interface while a JDK proxy implements only a business interface, the exporter may no longer see the object under the same JMX compliance criteria. Use a Standard MBean adapter or appropriate explicit exposure when needed; do not automatically assume annotation-only export will solve every case.

## 8. Diagnostic Step 4: Check Registration Logs and Initialization Errors

An MBean may fail to appear because the exporter attempted registration and failed. Helpful errors:

| Exception / symptom | May relate to |
|---|---|
| \`NotCompliantMBeanException\` | Object/proxy does not meet the MBean contract along the export path |
| \`InstanceAlreadyExistsException\` | Duplicate ObjectName, multiple exporters or contexts |
| \`MalformedObjectNameException\` | Naming strategy generated syntactically invalid name |
| \`BeanCreationException\` | Exporter or dependent bean failed to initialize |
| \`IllegalArgumentException\` from assembler | Invalid metadata/method exposure |
| No error yet MBean is missing | Autodetection did not select bean, wrong server or name |

During controlled diagnostics, raise log levels for Spring JMX export, such as \`org.springframework.jmx\`, and inspect exception chains. How logging is enabled depends on the application's logging framework.

Do not leave full Spring debug logging enabled in production long-term if it adds overhead and leaks sensitive data.

### 8.1. Why can errors be masked?

Some registration policy configurations can skip an already-existing ObjectName. With \`RegistrationPolicy.IGNORE_EXISTING\`, the new exporter may skip registering the expected bean while the server keeps the old MBean. This is easily mistaken for AOP causing the bean to “disappear” or “not update”.

To diagnose, confirm which exporter/context owns the existing MBean and do not use \`REPLACE_EXISTING\` just to hide collisions.

## 9. Diagnostic Step 5: Check ApplicationContext Boundaries

A Spring application can have multiple contexts:

\`\`\`text
RootContext:
  - Service + Transaction AOP
  - Exporter R

ChildContext:
  - Controller + Exporter C
\`\`\`

The parent does not automatically enumerate child beans. An exporter belonging to the root will not necessarily see beans existing only in the child. If AOP configuration is moved to another context or beans are redeclared, where the exporter runs may no longer match.

Check:

1. In which context is the bean defined?
2. To which context does the exporter belong?
3. Do the exporters share the same server?
4. In which context is annotation export enabled?
5. Are beans duplicated between parent and child?
6. Has the context been closed or refreshed?

A transaction change may simultaneously alter configuration structure, package scanning, or context hierarchy. Do not blame every error occurring after that change on proxies without verifying.

## 10. Example Reproducing a JDK Proxy and Management Getter

### 10.1. Business interface

\`\`\`java
public interface PaymentService {
    void pay();
}
\`\`\`

### 10.2. Implementation with management metadata

\`\`\`java
import org.springframework.jmx.export.annotation.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@ManagedResource(
    objectName = "training.proxy:type=PaymentService,name=Primary")
public class PaymentServiceImpl implements PaymentService {

    private volatile int processed;

    @Override
    @Transactional
    public void pay() {
        processed++;
    }

    @ManagedAttribute
    public int getProcessed() {
        return processed;
    }

    @ManagedOperation
    public void resetProcessed() {
        processed = 0;
    }
}
\`\`\`

When Spring creates a JDK proxy implementing only \`PaymentService\`, the getter \`getProcessed()\` and operation \`resetProcessed()\` are not on the business interface. Depending on the exporter and metadata mechanism, JMX output may differ from when the bean is unproxied.

### 10.3. Adjustment Options

**Approach A — Design a clear management interface**

\`\`\`java
public interface PaymentManagement {
    int getProcessed();
    void resetProcessed();
}
\`\`\`

If a JDK proxy must expose a management interface, the target class can implement this interface and the proxy can be configured to preserve it. Also ensure the assembler/exporter exposes the desired methods.

**Approach B — Class-based proxy when appropriate**

Class-based proxying can be configured in an application designed for it. For instance, \`@EnableTransactionManagement(proxyTargetClass = true)\` when using Spring proxy-based transaction management:

\`\`\`java
@Configuration
@EnableTransactionManagement(proxyTargetClass = true)
class TransactionConfig {
}
\`\`\`

This can preserve introspection of the class's methods, but you must check final classes/methods, other proxies, and transaction semantics. Do not change proxy strategy application-wide without evaluating impact.

**Approach C — Export a separate management adapter**

Instead of directly exporting a bean with heavy AOP advice, create a simple management facade:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "training.proxy:type=PaymentManagement,name=Primary")
public class PaymentManagementFacade {
    private final PaymentService paymentService;
    private final PaymentStatistics statistics;

    public PaymentManagementFacade(
            PaymentService paymentService,
            PaymentStatistics statistics) {
        this.paymentService = paymentService;
        this.statistics = statistics;
    }

    @ManagedAttribute
    public int getProcessed() {
        return statistics.processedCount();
    }

    @ManagedOperation
    public void resetStatistics() {
        statistics.reset();
    }
}
\`\`\`

The facade separates the JMX contract from proxy details of the business service. In the example, \`PaymentStatistics\` is a service/component that must be defined in a real project. State-changing operations still need authorization and auditing where appropriate.

## 11. Checking Annotation Content and the Metadata Assembler

A bean can be registered yet lack metadata because the chosen assembler mechanism does not read \`@ManagedAttribute\` and \`@ManagedOperation\`.

For Spring annotation export, annotation metadata infrastructure such as \`AnnotationJmxAttributeSource\` and an appropriate assembler are typically used. If the project overrides \`MBeanInfoAssembler\` with \`MethodNameBasedMBeanInfoAssembler\` or a custom assembler, annotations may no longer be the source governing exposure.

Check:

- Which assembler is \`MBeanExporter\` using?
- Is the annotation exporter still enabled?
- Which target class or interface is the assembler inspecting?
- Are annotated methods public and do they have valid signatures?
- Is \`@ManagedResource\` detected from the appropriate type?
- Is an explicit ObjectName being overridden by a naming strategy?

**Do not blindly slap annotations onto both the interface and the implementation.** Annotation placement must fit your project version's Spring JMX metadata mechanism; testing actual JMX output is how you confirm.

## 12. Quick Diagnostics via Java Program

The helper below uses an \`MBeanServer\` available in the JVM. You can place it in a test or internal diagnostic snippet.

\`\`\`java
import javax.management.*;
import java.util.Set;

public final class JmxDiagnostic {
    public static void inspect(
            MBeanServer server,
            String domainPattern) throws Exception {

        ObjectName pattern =
            new ObjectName(domainPattern + ":*");

        Set<ObjectName> names =
            server.queryNames(pattern, null);

        System.out.println("MBeans found: " + names.size());

        for (ObjectName name : names) {
            System.out.println("NAME " +
                name.getCanonicalName());

            MBeanInfo info = server.getMBeanInfo(name);

            for (MBeanAttributeInfo a : info.getAttributes()) {
                System.out.printf(
                    "  ATTR %s %s read=%s write=%s%n",
                    a.getName(), a.getType(),
                    a.isReadable(), a.isWritable());
            }

            for (MBeanOperationInfo op : info.getOperations()) {
                System.out.println(
                    "  OP " + op.getName());
            }
        }
    }
}
\`\`\`

Invoke:

\`\`\`java
JmxDiagnostic.inspect(server, "training.proxy");
\`\`\`

This evidence answers “did the MBean truly disappear?” and “did metadata change?” without guessing from a UI. If no suitable server exists in the same JVM, use \`MBeanServerConnection\` from an authorized JMX connector.

## 13. Regression Testing Before and After Enabling AOP

Write an integration test using the same exporter configuration while varying how proxying is applied, then verify the **JMX contract**, not just business logic.

Key assertions:

\`\`\`java
ObjectName name = new ObjectName(
    "training.proxy:type=PaymentService,name=Primary");

assertTrue(server.isRegistered(name));

MBeanInfo info = server.getMBeanInfo(name);

// Check required attribute name and type.
// Check getProcessed is readable.
// Check resetProcessed operation is exposed.
// Invoke operation then verify value.
\`\`\`

With a Spring context containing transactions/AOP, test execution through the actual proxy provided by the container. If you only instantiate the implementation via \`new PaymentServiceImpl()\`, the test will not reproduce proxying.

### 13.1. Suggested Test Matrix

| Scenario | Goal |
|---|---|
| No AOP | Baseline MBean interface |
| JDK proxy | Ensure annotation/method exposure is not lost |
| Class-based proxy | Check visibility and limitations |
| Custom assembler | Ensure consistent metadata |
| Multiple contexts | Avoid duplicates/wrong unregistration |
| Context restart | MBean re-registers under the right name |
| Remote client | Verify connection to the actual server |

If using \`MBeanServerFactory.newMBeanServer()\` as a server fixture, remember to inject that server into the exporter. A test reading only the platform server can falsely fail if the exporter registered into a separate fixture server.

### 13.2. Practical Metadata Assertions

\`\`\`java
import java.util.Arrays;

boolean hasProcessed =
    Arrays.stream(info.getAttributes())
        .anyMatch(a -> a.getName().equals("Processed")
            && a.isReadable());

boolean hasReset =
    Arrays.stream(info.getOperations())
        .anyMatch(op -> op.getName().equals("resetProcessed"));

assertTrue(hasProcessed);
assertTrue(hasReset);
\`\`\`

When a tester switches from JDK proxy to CGLIB proxy, both assertions should still represent a stable management contract if the JMX feature is committed as supported.

## 14. Common Errors and How to Handle Them

| Symptom | Possible Cause | How to Verify |
|---|---|---|
| MBean existed before AOP, gone after AOP | Autodetection misses proxy or metadata is hidden | Check \`AopUtils\`, exporter, logs |
| MBean remains but missing management getter | Getter absent from JDK proxy interface | Check proxy interfaces and \`MBeanInfo\` |
| MBean has strange ObjectName | Naming strategy uses identity/proxy type | Query domain and canonical names |
| \`NotCompliantMBeanException\` error | Proxy does not conform to MBean contract | Check adapter/assembler and exported object |
| Bean not visible in JConsole | Exporter uses custom server | Check server identity |
| \`InstanceAlreadyExistsException\` error | Multiple exporters/contexts collide on name | Check registration policy and ownership |
| Bean exists but JMX metadata is empty | Annotation assembler not active | Check exporter config |
| Transactions misbehave after JMX fix | Proxy bypassed or self-invocation | Restore proxy boundary, use facade |
| Only remote client fails | Connector/auth/network or different server | Separate transport layer from export |

Do not choose a “fix” by extracting the target object via \`Advised.getTargetSource().getTarget()\` and calling it directly if the goal is preserving transaction/security advice. That can be a controlled debugging technique, but calling the target directly bypasses AOP proxy semantics.

## 15. Ordered Troubleshooting Workflow

### Phase 1 — Confirm symptoms

1. Record ObjectName and attributes/operations before enabling AOP if baseline data exists.
2. Confirm the current JVM and MBeanServer.
3. Query ObjectNames by domain.
4. Distinguish non-registration, renaming, or metadata change.

### Phase 2 — Confirm proxy

5. Print \`AopUtils.isAopProxy\`, \`isJdkDynamicProxy\`, \`isCglibProxy\`.
6. Inspect target class and interfaces.
7. Check annotations on target/interface per actual configuration.
8. Inspect which exporter and assembler are active.

### Phase 3 — Fix configuration appropriately

9. If naming changed: choose a stable logical ObjectName.
10. If JDK proxy lacks management methods: consider a management interface or management facade.
11. If assembler misses metadata: configure the appropriate annotation assembler.
12. If collision: fix namespace/ownership; do not mask errors with replace policy.
13. If different server: inject the right MBeanServer and connect to the right endpoint.
14. If proxy strategy must change: check impact on transactions and other advice.

### Phase 4 — Protect results

15. Add integration tests for ObjectName, metadata, and invocation.
16. Check context restart/unregister lifecycle.
17. Run tests with actual AOP/transaction configuration.
18. For remote JMX, test connector/security separately from export errors.

## 16. Security and Operations Notes

JMX is a management interface. A proxy change sometimes tempts developers into directly exporting implementations or over-expanding metadata to recover old methods. Avoid:

- Exposing all public methods for debugging convenience.
- Exposing credentials, tokens, or personal data in attributes.
- Bypassing AOP security/transactions just to make an operation “work”.
- Using \`RegistrationPolicy.REPLACE_EXISTING\` to overwrite another module's bean.
- Opening unprotected remote JMX just to verify an MBean exists.
- Invoking destructive operations on production systems just to test.

A clear management facade is usually more stable than depending on business service proxy internals.

## 17. Practice Exercises

### Exercise A — Observe proxy

Create a service with \`@Transactional\`, print \`AopUtils.isAopProxy\` and \`AopUtils.getTargetClass\`. Switch JDK/CGLIB proxy configuration in a lab environment and compare. Explain why the same bean definition can return different object classes.

### Exercise B — Getter absent from interface

Create \`PaymentService\` with only \`pay()\`, while the implementation adds \`@ManagedAttribute getProcessed()\`. Enable JDK proxying and check MBeanInfo. Then move \`getProcessed()\` onto a suitable interface or use a management facade, and re-verify the contract.

### Exercise C — ObjectName change

Try an identity-based naming strategy, then enable AOP. Query ObjectNames in the server before and after. Explain why a dashboard hard-coding generated names may report an MBean as missing even though it is still registered.

### Exercise D — Two ApplicationContexts

Create parent/child contexts and place the exporter in root. Register a management bean only in child. Check whether it is autodetected. Move the exporter or configure explicit registration with appropriate ownership, then recheck.

### Exercise E — Contract regression

Write a JUnit test verifying the same ObjectName, \`Processed\` attribute, and \`resetProcessed\` operation exist before/after enabling transaction advice. Conclude it is resolved only when access through \`MBeanServerConnection\` succeeds.

## 18. Self-Check Questions

1. Why can adding \`@Transactional\` change the class Spring returns?
2. How does a JDK dynamic proxy differ from a class-based proxy in method exposure capability?
3. Why does \`isRegistered(oldName) == false\` not yet prove the MBean is gone?
4. How do you determine whether the exporter uses the right MBeanServer?
5. Which failure modes does \`MBeanInfo\` help distinguish?
6. Why should you not disable AOP just to fix a JMX issue?
7. When is a management facade better than directly exporting a business bean?
8. Which error can \`RegistrationPolicy.IGNORE_EXISTING\` mask?
9. Why does a parent exporter not necessarily detect beans in a child context?
10. How do you protect the JMX contract against a proxy strategy change?

## 19. References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Reference — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework API — \`MBeanExporter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework API — \`AnnotationMBeanExporter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/AnnotationMBeanExporter.html
- Spring Framework API — \`AopUtils\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/support/AopUtils.html
- Java SE 21 API — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html

**Remember:** after enabling AOP or transactions, a “disappearing MBean” may be a change in proxy, metadata, naming strategy, server, or context lifecycle. Diagnose with evidence from ApplicationContext, MBeanServer, and MBeanInfo before changing configuration. Prefer keeping JMX contracts stable without breaking transaction and security semantics.
