# Diagnosing beans skipped after enabling auto-proxy in Spring Framework JMX

## Objectives

In the Spring Framework, a JMX exporter can autodetect eligible beans and register them with \`MBeanServer\`. When AOP auto-proxying is enabled — for example via \`@EnableAspectJAutoProxy\`, \`@Transactional\`, \`@Async\`, or library-added advisors — the Spring bean seen by the exporter may no longer be the original implementation object. It may be a **JDK dynamic proxy** or a **class-based proxy**. This change affects type information, published interfaces, annotation metadata, and JMX introspection mechanisms.

A common symptom: before enabling auto-proxy, the bean appears in JConsole; afterward, the MBean disappears or the exporter skips the bean. Sometimes the error is \`NotCompliantMBeanException\`, and sometimes there is no clear error because the bean simply no longer meets autodetection criteria. You must diagnose at the right layer: Spring bean, proxy, MBean exporter, \`MBeanServer\`, \`ObjectName\`, and JMX client.

After this lesson, you will be able to:

1. Distinguish between a target bean, a proxy bean, and a management interface.
2. Explain why a JDK proxy can obscure the class or interfaces JMX needs for recognition.
3. Understand the difference between Standard MBean introspection and annotation-driven export.
4. Trace whether a bean was filtered out at autodetection, metadata assembly, or registration.
5. Use \`AopUtils\`, \`AopProxyUtils\`, \`BeanFactory\`, and \`MBeanServer\` to isolate the issue.
6. Evaluate when to choose a class-based proxy, expose an appropriate interface, export the target, or use a dedicated management adapter.
7. Test startup, contract, and cleanup without losing required Spring AOP advice.
8. Avoid confusing an MBean not visible in JConsole with a bean that truly does not exist.

## 1. Looking accurately at bean creation and MBean export flow

A regular bean:

\`\`\`text
Bean definition
     |
     v
Instantiate target class
     |
     v
BeanPostProcessor / AutoProxyCreator
     |
     v
Spring bean exposed to container
     |
     v
MBeanExporter autodetection
     |
     v
MBeanServer.registerMBean(...)
\`\`\`

Without an AOP proxy, the final object is usually the implementation. With auto-proxy:

\`\`\`text
Target: InventoryMonitor implements InventoryMonitorMBean
     |
     +── JDK dynamic proxy
     |      implements selected interfaces
     |      runtime class: jdk.proxy... / com.sun.proxy...
     |
     +── CGLIB/class-based proxy
            subclass-like proxy with generated class name
\`\`\`

The exporter may see the proxy instead of the target. Whether JMX recognizes the bean as an MBean depends not only on the Spring bean name, but also on the type and JMX contract of the exported object.

Note: Spring has capabilities to support proxies/targets during export. Do not assert that every JDK proxy breaks JMX or every CGLIB proxy fixes it. Actual behavior depends on the Spring version, \`MBeanInfoAssembler\`, exporter mode, and the bean's interfaces/annotations.

## 2. Common symptoms

| Symptom | Hypothesis to check |
|---|---|
| MBean existed before AOP, missing after AOP | Proxy changed type/metadata used by autodetect |
| Bean still injects into services, yet absent from JMX | Bean exists, merely excluded from export |
| Logs report non-compliant MBean | JMX introspection cannot find contract on proxy |
| \`@ManagedResource\` on class yet exporter ignores it | Target/proxy metadata lookup or assembler config unsuitable |
| JConsole shows MBean yet operation is missing | Exposed interfaces or metadata selection changed |
| One bean has two unexpected \`ObjectName\`s | Multiple exporters/naming strategies |
| JMX fails only when \`@Transactional\` is enabled | Transaction advisor triggered proxying |
| MBean disappears after refresh | Registration lifecycle or \`ObjectName\` collision |

A diagnostic principle: **a bean being skipped by JMX does not mean the bean was skipped by the \`ApplicationContext\`**. Check bean registration and JMX registration separately.

## 3. JDK dynamic proxy and interface limitations

A JDK dynamic proxy operates through the interfaces chosen for proxying. If an implementation has many public methods yet the proxy does not expose an interface containing them, external code sees only the methods of the interfaces the proxy implements.

Example:

\`\`\`java
public interface WorkerServiceApi {
    void process();
}

public interface WorkerStatusMBean {
    String getState();
}

public class WorkerService
        implements WorkerServiceApi, WorkerStatusMBean {

    @Override
    public void process() {
        // Business logic.
    }

    @Override
    public String getState() {
        return "RUNNING";
    }
}
\`\`\`

If the JDK proxy publishes only \`WorkerServiceApi\`, \`MBeanServer\` cannot automatically treat that proxy as \`WorkerStatusMBean\`. Depending on auto-proxy configuration and the Spring exporter, JMX detection may fail to recognize the management interface or fail to register.

What needs confirmation is not merely whether the target class implements \`WorkerStatusMBean\`, but whether **the object the exporter actually uses exposes the management contract**.

You can check:

\`\`\`java
Object bean = context.getBean("workerService");
System.out.println(bean.getClass());
System.out.println(Arrays.toString(bean.getClass().getInterfaces()));
System.out.println(bean instanceof WorkerStatusMBean);
\`\`\`

Calling \`getInterfaces()\` directly on a class does not display indirectly inherited interfaces, so use \`instanceof\`, \`AopUtils\`, and appropriate introspection helpers to confirm the contract.

## 4. How does a class-based proxy differ?

A class-based proxy (commonly described as a CGLIB proxy in Spring) creates a proxy subclass for the target type when feasible. It can preserve more class-based introspection traits than a JDK interface proxy, yet also has limitations:

- \`final\` classes cannot be subclassed in the usual way.
- \`final\` methods cannot be overridden to apply advice.
- Self-invocation can go straight to the target method without passing through proxy advice.
- Annotations and metadata may require looking up the target class rather than only the proxy-generated class.
- Special Java types or constructors/lifecycles can cause unexpected behavior.

Configuration example:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AopConfiguration {
}
\`\`\`

This configuration requests preferring class-based proxies within its scope, yet **is not the default solution to use solely so JMX picks up one bean**. It can impact the entire proxy strategy in the context, including unrelated beans. For an isolated JMX issue, a dedicated management adapter usually has less architectural impact.

## 5. Standard MBean: naming conventions and management interfaces

A Standard MBean typically has an interface named \`<ImplementationClass>MBean\`:

\`\`\`java
public interface CacheMonitorMBean {
    long getHitCount();
    void resetCounters();
}

public class CacheMonitor implements CacheMonitorMBean {
    @Override
    public long getHitCount() {
        return 0L;
    }

    @Override
    public void resetCounters() {
        // Reset.
    }
}
\`\`\`

When registering a \`CacheMonitor\` object matching the contract, JMX can publish the \`HitCount\` attribute and \`resetCounters\` operation.

However, after auto-proxy, the runtime class may be a generated proxy class, no longer bearing the same \`CacheMonitor\` name. If the exporter/JMX introspection does not recognize the management interface as expected, the bean may be skipped or fail registration.

Key point: \`MBeanExporter\` has mechanisms to support exporting beans/proxies in Spring JMX; do not ignore it and mechanically apply plain-object Standard MBean rules. Diagnose **the active export mechanism**, not just the runtime proxy name.

## 6. Annotation-driven export: @ManagedResource on the target

With annotations:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.ops:type=Worker,name=Import")
public class ImportWorkerMonitor {

    @ManagedAttribute
    public String getState() {
        return "RUNNING";
    }
}
\`\`\`

When an advisor causes the bean to be proxied, the annotation may sit on the **target class** while the exporter receives a proxy. Spring's annotation assembler can support finding metadata on the target, yet success depends on configuration and framework version. In anomalous cases, inspect \`AnnotationMBeanExporter\`, \`MetadataMBeanInfoAssembler\`, the proxy type, and the actual object.

Do not try to add \`@ManagedResource\` onto a JDK proxy generated class — that class is generated by the framework, not source code you control. If JMX metadata sits on an interface or target, determine whether the assembler mechanism supports that annotation location.

## 7. Layered diagnostic steps

### Step 1 — Does the bean still exist in the Spring context?

\`\`\`java
boolean exists = context.containsBean("importWorkerMonitor");
Object bean = context.getBean("importWorkerMonitor");

System.out.println("exists=" + exists);
System.out.println("type=" + bean.getClass().getName());
\`\`\`

If the bean does not exist, the error involves bean registration, component scanning, profiles/conditions, or bean name. If the bean exists yet the MBean is absent, proceed to the next steps; do not change \`@ComponentScan\` before knowing the root cause.

### Step 2 — Is the bean an AOP proxy?

\`\`\`java
import org.springframework.aop.support.AopUtils;

Object bean = context.getBean("importWorkerMonitor");

System.out.println("AOP proxy: " + AopUtils.isAopProxy(bean));
System.out.println("JDK proxy: " + AopUtils.isJdkDynamicProxy(bean));
System.out.println("CGLIB proxy: " + AopUtils.isCglibProxy(bean));
System.out.println("target class: " +
    AopUtils.getTargetClass(bean).getName());
\`\`\`

Compare before/after enabling AOP. If the target class stays the same yet the runtime bean class changes, the proxy is a lead to investigate. However, correlation does not by itself prove causation: adding configuration may simultaneously alter exporters/bean definitions.

### Step 3 — Which interfaces does the proxy expose?

\`\`\`java
Object bean = context.getBean("importWorkerMonitor");

for (Class<?> iface : bean.getClass().getInterfaces()) {
    System.out.println(iface.getName());
}
\`\`\`

With a management interface:

\`\`\`java
System.out.println(bean instanceof ImportWorkerMonitorMBean);
\`\`\`

If the interface is missing, inspect \`ProxyFactory\`, introduction advisors, interface filtering, and proxy configuration. Do not force-cast a proxy to a missing interface merely because the target implements that interface.

### Step 4 — Which exporters are active?

\`\`\`java
import org.springframework.jmx.export.MBeanExporter;

String[] names = context.getBeanNamesForType(
    MBeanExporter.class, true, false);

System.out.println(Arrays.toString(names));
\`\`\`

Check whether there is one or more exporters, \`AnnotationMBeanExporter\` vs. \`MBeanExporter\`, autodetect mode, explicit mappings, naming strategy, and assembler. If no exporter is enabled or the bean is out of scope, this is not a proxy introspection error.

### Step 5 — Is it the right MBeanServer?

\`\`\`java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
    "com.example.ops:type=Worker,name=Import");

System.out.println(server.isRegistered(name));
\`\`\`

If the exporter uses a custom \`MBeanServer\`, query that server instead of the platform server. JConsole may connect via a connector to a different registry. An MBean not appearing in JConsole does not prove the exporter skipped the bean.

### Step 6 — Did the actual ObjectName change?

When an exporter uses a naming strategy based on bean name or metadata, proxying or refactoring can impact naming assumptions. Query the relevant domain:

\`\`\`java
Set<ObjectName> actual = server.queryNames(
    new ObjectName("com.example.ops:*"), null);
actual.forEach(System.out::println);
\`\`\`

If the bean is exported under a different name, the issue is naming rather than autodetection. For MBeans serving as monitoring contracts, use an explicit \`ObjectName\` when appropriate.

### Step 7 — Did registration error out or roll back?

Inspect the exporter's startup logs and exceptions:

- \`NotCompliantMBeanException\`: object does not satisfy the JMX contract.
- \`InstanceAlreadyExistsException\`: \`ObjectName\` already exists in the server.
- \`MalformedObjectNameException\`: invalid name.
- \`BeanCreationException\`: Spring configuration/bean initialization error.
- \`JMException\`, \`MBeanRegistrationException\`: registration failed.
- \`IOException\`: may come from a client-side remote connector, not necessarily a local registration failure.

Read the stack trace to identify which exporter, bean, and server performed registration. Do not turn every error into an AOP hypothesis.

## 8. Autodetection modes affect bean selection

\`MBeanExporter\` can use explicit mappings or appropriate autodetection modes per API/version:

| Selection approach | What to verify after proxying |
|---|---|
| Explicit \`setBeans\` | Does the MBean object have a compliant contract? |
| Standard MBean autodetection | Does the proxy have a recognizable Standard MBean interface? |
| MXBean autodetection | Does the proxy expose an MXBean interface and valid data types? |
| Assembler-based autodetection | Does the assembler treat the target/proxy as a candidate? |
| Annotation-based autodetection | Is annotation metadata found on the target? |

Distinguish **a bean excluded from candidates** from **a bean selected yet failing registration**. The former usually produces no new \`ObjectName\`; the latter produces an exception or registration log. Adjusting export mode without knowing the failing step can uncontrollably increase the number of exported beans.

## 9. MBeanInfoAssembler and proxy classes

An \`MBeanInfoAssembler\` generates attribute/operation metadata for a bean. Some assemblers rely on reflection, some use annotations, and some restrict methods by interface. If the assembler receives the proxy type instead of the target type, metadata may lack expected methods.

Interface-based exposure example:

\`\`\`java
public interface WorkerMonitorMBean {
    String getState();
    long getCompletedCount();
}
\`\`\`

When the exporter uses an explicitly chosen management interface, the management surface is more stable than guessing from all public methods of the target class. However, ensure the final object actually exposes the right interface or is wrapped/adapted appropriately.

If using Spring's \`MetadataMBeanInfoAssembler\`, verify metadata lookup against the target class and annotations in your current Spring version. Do not mix multiple assemblers or metadata sources without understanding how they decide inclusion.

## 10. Solution 1: dedicated management adapter, not directly proxied

Usually the least disruptive solution is separating a management adapter from the proxied business service.

\`\`\`text
Spring service target
     |
     v
@Transactional / @Async / AOP proxy
     |
     v
Management adapter (injected with service proxy)
     |
     v
MBeanExporter / AnnotationMBeanExporter
     |
     v
MBeanServer
\`\`\`

Example:

\`\`\`java
public interface WorkerStatusMBean {
    String getState();
    long getCompletedCount();
}
\`\`\`

\`\`\`java
public class WorkerStatus implements WorkerStatusMBean {

    private final WorkerServiceApi service;

    public WorkerStatus(WorkerServiceApi service) {
        this.service = service;
    }

    @Override
    public String getState() {
        return service.currentState();
    }

    @Override
    public long getCompletedCount() {
        return service.completedCount();
    }
}
\`\`\`

Here \`WorkerServiceApi\` must define the corresponding methods. The adapter does not publish sensitive business operations. You can register \`WorkerStatus\` as a Standard MBean with an explicitly chosen \`ObjectName\`:

\`\`\`java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
    "com.example.ops:type=WorkerStatus,name=Import");
server.registerMBean(new WorkerStatus(service), name);
\`\`\`

In a real application, let the Spring exporter manage registration/lifecycle or write symmetric cleanup if registering manually. Do not let tests or another context unregister an \`ObjectName\` owned by this exporter.

Benefit: the service continues receiving transactional/asynchronous advice through the Spring proxy, while the JMX interface does not depend on the service's proxy class.

## 11. Solution 2: expose the management interface through the proxy

If you want to export the proxy bean itself, verify the proxy exposes the management interface:

\`\`\`java
public interface ImportWorkerMBean {
    String getState();
}
\`\`\`

Implementation:

\`\`\`java
public class ImportWorker implements ImportWorkerMBean, WorkerServiceApi {
    @Override
    public String getState() { return "RUNNING"; }

    @Override
    public void process() { /* ... */ }
}
\`\`\`

When using a JDK proxy, Spring can expose suitable interfaces, yet specific AOP configurations may select an interface subset. If needed, configure the proxy to support the management interface, then assert:

\`\`\`java
Object proxy = context.getBean("importWorker");
assertTrue(proxy instanceof ImportWorkerMBean);
\`\`\`

Do not rely only on asserting that the target class implements the interface. Also pay attention to Standard MBean naming conventions or use a \`StandardMBean\` wrapper to specify the management interface explicitly.

## 12. Solution 3: StandardMBean wrapper

A wrapper can explicitly specify the contract when the implementation/proxy name does not follow conventions.

\`\`\`java
import javax.management.StandardMBean;

WorkerStatusMBean implementation = new WorkerStatus(service);

StandardMBean exposed =
    new StandardMBean(implementation, WorkerStatusMBean.class);

server.registerMBean(exposed,
    new ObjectName("com.example.ops:type=WorkerStatus,name=Import"));
\`\`\`

The wrapper decouples the runtime implementation name from the management interface name. It does not automatically turn an object that does not implement the interface into a compliant MBean; the passed object must satisfy the contract. Nor does the wrapper fix issues where the Spring bean does not exist, the exporter is disabled, or the wrong server is used.

If using an MXBean, apply MXBean rules or the wrapper with the proper MXBean flag, and ensure data types have valid Open Type mappings.

## 13. Solution 4: intentionally changing proxyTargetClass

One option is:

\`\`\`java
@EnableAspectJAutoProxy(proxyTargetClass = true)
\`\`\`

This can make a class-based proxy retain the class/type traits needed by the exporter. However, it has a broad impact on the entire context and can change the proxying of final classes or AOP behavior. Do not use it as the first fix if the error affects only a single management bean.

Compare:
- Does the current interface-based proxy expose the management interface?
- Does the Spring exporter have a mechanism to unwrap the target or build an appropriate ModelMBean?
- Can a dedicated adapter solve the issue with a smaller blast radius?
- Are there operations on the management interface that must run through Spring advice?
- Do startup tests, JMX contracts, and transactional/async behavior remain accurate?

If you adjust the proxy strategy, test related AOP services rather than checking JConsole alone.

## 14. Why should you not arbitrarily export the target instead of the proxy?

When a target bean is Spring-proxied to apply transaction, audit, or security advice, calling target methods directly via JMX can **bypass advice**. Especially for operations with side effects, this difference is dangerous.

Service example:

\`\`\`java
@Transactional
public void requestRebuild() { ... }
\`\`\`

If JMX exports the target object and invokes directly, transaction advice may not run. Depending on the Spring proxy mechanism and call path, calling through the proxy is what applies advice properly. Therefore, before unwrapping a target, understand which advices the method requires and whether a safe call path exists.

A management adapter calling the service via a Spring-injected proxy is usually clearer: the JMX method is the adapter entry point, while business execution goes through the service proxy like other consumers.

## 15. Multiple exporters and registration conflicts

When adding AOP configuration, an application may simultaneously import other configurations, creating an additional exporter. If a bean disappears from JConsole, check the number of exporters and duplicate \`ObjectName\`s.

Examples:
- \`@EnableMBeanExport\` in the main module.
- Spring Boot JMX auto-configuration enabled.
- A library declaring \`@Bean MBeanExporter\`.

If two exporters register the same \`ObjectName\`, the result can be an exception or a replaced registration depending on policy. Do not "fix" it with \`REPLACE_EXISTING\`: context A may clean up an MBean that B is using during shutdown.

An MBean disappearing after enabling AOP is not necessarily caused by the proxy; changes to the configuration graph may be the true cause.

## 16. AOP and annotations on interfaces

In Java, annotations on classes/interfaces are not always inherited in the way authors assume. Spring has merged annotation lookup mechanisms, yet you should not assume every JMX assembler interprets interface annotations identically.

For \`@ManagedResource\`, place metadata where the exporter/assembler explicitly supports it in your current Spring version. When using JDK proxies, the target class and proxy interfaces differ; check where metadata is actually read from.

One option to reduce uncertainty is a dedicated adapter class carrying \`@ManagedResource\` and the needed \`@ManagedAttribute\` or \`@ManagedOperation\` annotations, without relying on multiple layers of interface annotations.

## 17. Diagnostics via logs and breakpoints

When an issue is hard to trace:

1. Enable appropriate logging for \`org.springframework.jmx\` and \`org.springframework.aop\` in dev/test environments.
2. Inspect the exporter bean, auto-detection timing, MBean names, and exceptions.
3. Set breakpoints on bean initialization or the \`MBeanExporter\` registration path.
4. Observe the runtime object being processed by the exporter.
5. Inspect \`AopUtils.isAopProxy\`, target class, and exposed interfaces.
6. Check the assembler's \`includeBean\`/metadata if applicable.
7. Identify the generated \`ObjectName\`.
8. Call \`MBeanServer.isRegistered\` after the context finishes startup.

Do not leave sensitive debug logging enabled long-term in production, and never log credentials/secrets from beans/connectors.

## 18. Integration tests locking behavior before and after auto-proxy

A test should verify that the bean and MBean coexist:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class ProxyAndJmxTest {

    @Test
    void managementBeanRemainsVisible() throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
            "com.example.ops:type=WorkerStatus,name=Import");

        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(
                     AppConfigWithAop.class)) {

            Object bean = context.getBean("workerStatus");

            assertNotNull(bean);
            // Check proxy type if the fixture has an advisor creating a proxy.
            System.out.println("AOP proxy=" + AopUtils.isAopProxy(bean));

            assertTrue(server.isRegistered(name));
            assertNotNull(server.getMBeanInfo(name));
        }

        assertFalse(server.isRegistered(name));
    }
}
\`\`\`

\`AppConfigWithAop\` must define the service, advisor/proxy, adapter, exporter, and server matching the fixture. The example is a test skeleton, not a claim that a single annotation creates a proxy on its own. In parallel tests, use a separate server or unique test namespace to avoid collisions. Only assert unregistration when the context truly owns the registration.

Extend the test:
- Ensure the \`State\` attribute exists.
- Verify internal operations are not exported.
- Ensure the service still receives AOP advice when called through the adapter.
- Check context refresh and absence of duplicate MBeans.
- Test both JDK proxies and class-based proxies if the application supports both styles.

## 19. A remediation decision table

| Confirmed finding | Preferred remediation |
|---|---|
| Proxy does not expose management interface | Choose right proxy interfaces or dedicated adapter |
| Annotation on target yet assembler misses it | Configure metadata/export path or annotated adapter |
| \`MBeanServer\` is not the server client is viewing | Align exporter/connector servers |
| \`ObjectName\` generated differently than before | Set stable naming strategy/explicit name |
| Two exporters register the same name | Remove duplicate export path or partition scope |
| Standard MBean non-compliant after proxy | Use management adapter/\`StandardMBean\` wrapper |
| Proxy type changed context-wide | Consider class-based proxy with broad-scope tests |
| Operation needs transaction/security advice | Call service through Spring proxy, do not bypass target |
| MBean exported yet missing members | Check \`MBeanInfoAssembler\` and management contract |
| Bean does not exist in context | Fix bean registration/profiles/conditions before touching JMX |

## 20. Common misconceptions

**“Enabling @Transactional makes Spring delete the bean.”** No. Usually the bean still exists yet is exposed via a proxy, and the exporter may recognize it differently.

**“JDK proxies can never be exported as MBeans.”** No. If the interfaces and export mechanism match, a proxy can be exported. Verify the actual contract and registration.

**“CGLIB definitely fixes every JMX error.”** No. It has limitations with final classes/methods and can alter behavior across the entire context.

**“Just grab the target from the proxy and register it.”** Dangerous: JMX may invoke the target directly and bypass transaction/security advice.

**“MBean missing in JConsole means autodetection skipped it.”** Not necessarily: it could be the wrong server, connector, \`ObjectName\`, or a failed registration.

**“@ManagedResource guarantees an exporter exists.”** No. Metadata requires an enabled and properly configured export mechanism.

**“Just look at the proxy's class name.”** Insufficient: you need exposed interfaces, target class, assembler, and registry.

**“Switching registration policy to replace is fine.”** No. That can mask duplicate exporter bugs and break lifecycle.

## 21. Applied exercises

### Exercise 1 — Checking the proxy

A \`WorkerService\` implements \`WorkerServiceApi\` and \`WorkerStatusMBean\`, yet the JDK proxy exposes only \`WorkerServiceApi\`. Which assertions would you write to prove the management interface is missing? Propose an adapter or proxy interfaces configuration.

### Exercise 2 — Missing MBean

After enabling AOP, \`context.containsBean("cacheMonitor")\` returns true, yet \`server.isRegistered(name)\` returns false. Build a diagnostic workflow checking the exporter, metadata, \`ObjectName\`, exceptions, and server.

### Exercise 3 — Spring advice

An MBean operation \`rebuild()\` must run with \`@Transactional\`. Why could registering the raw target directly be wrong? Design an adapter calling the service proxy.

### Exercise 4 — CGLIB

You try enabling \`proxyTargetClass=true\`. List the non-JMX tests needed to ensure the proxy change does not affect other services.

### Exercise 5 — Negative contract

Write a test verifying the MBean is exported properly yet does not expose an out-of-contract \`deleteAllData\` operation. Explain why JMX exposure must be treated as a privileged administrative API.

## Summary

When a bean is skipped by JMX after enabling auto-proxy, first distinguish **whether the Spring bean exists** from **whether the MBean is registered**. Auto-proxy can change the runtime class and exposed interfaces, causing Standard MBean mechanisms or Spring metadata assemblers to recognize it differently than before. The right diagnostic workflow checks bean/proxy, interfaces, exporter mode, assembler, \`ObjectName\`, \`MBeanServer\`, and registration logs. A resilient solution is usually a management adapter with a small contract calling the service through its Spring proxy to preserve advice, or intentionally configured proxy/assembler settings. Do not pick a context-wide change before knowing which layer actually failed.
