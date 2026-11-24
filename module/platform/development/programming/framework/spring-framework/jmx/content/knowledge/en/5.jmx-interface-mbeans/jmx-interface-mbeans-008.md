# Impact of Proxies and Decorators on MBean Identification

## Objectives

After this lesson, you will be able to explain why a Java object that implements a valid MBean interface can still be rejected by JMX registration once wrapped by a proxy or decorator; distinguish the identification rules of Standard MBeans, MXBeans, and Spring's JMX exporter; choose an explicit MBean export strategy; and diagnose errors such as `NotCompliantMBeanException`, `InstanceAlreadyExistsException`, or missing attributes/operations in `MBeanInfo`.

## 1. Which Object Does JMX See?

JMX registers **the actual object passed to `MBeanServer.registerMBean`**, meaning the runtime type and management contract detected from that object. The source type in code is not always the type of the object crossing the registration boundary.

Simple example:

```java
public interface PaymentMonitorMBean {
    int getPendingPayments();
    void retryFailedPayments();
}

public class PaymentMonitor implements PaymentMonitorMBean {
    @Override
    public int getPendingPayments() {
        return 12;
    }

    @Override
    public void retryFailedPayments() {
        System.out.println("Retry requested");
    }
}
```

Direct object:

```java
PaymentMonitor target = new PaymentMonitor();
server.registerMBean(target, objectName);
```

With a Standard MBean, the `PaymentMonitor` / `PaymentMonitorMBean` pair follows the naming convention. JMX can recognize the management interface of the target class.

However, once wrapped by Spring AOP, an instrumentation library, a decorator, or a custom proxy:

```text
Client / MBeanServer
         |
         v
      Proxy object
         |
         v
    Target object
       PaymentMonitor
```

The class passed to registration may be a dynamically generated proxy class instead of `PaymentMonitor`. Even though business calls still work properly, MBean detection relies on **the runtime type and visible interfaces**. Therefore, being able to invoke methods through the proxy does not automatically guarantee JMX will expose the right metadata.

## 2. Standard MBean and the Interface Convention

A typical Standard MBean uses a public interface named `<ConcreteClassName>MBean` and a class implementing that interface.

```java
public interface WorkerManagerMBean {
    int getActiveWorkers();
    void pause();
}

public class WorkerManager implements WorkerManagerMBean {
    @Override
    public int getActiveWorkers() {
        return 4;
    }

    @Override
    public void pause() {
        // Manage worker
    }
}
```

If you register a `WorkerManager` directly, the naming convention can be recognized. However, a runtime proxy has a class such as `jdk.proxy2.$Proxy...` or `WorkerManager$$SpringCGLIB$$...`; this proxy class does not necessarily have an interface whose name matches the proxy class.

Common consequences:

- `registerMBean(proxy, name)` may throw `NotCompliantMBeanException` because a valid Standard MBean or MXBean cannot be identified.
- The object may register, yet the management interface JMX selects does not match expectations.
- The proxy only exposes a subset of interfaces; `WorkerManagerMBean` might not be among the interfaces exposed by the proxy.
- A decorator implements the business interface without implementing the MBean interface, so the JMX contract disappears on the outermost object.

One way to make the boundary explicit is using `javax.management.StandardMBean` to specify the management interface, reducing reliance on runtime class naming conventions:

```java
import javax.management.StandardMBean;

WorkerManager target = new WorkerManager();
StandardMBean managed = new StandardMBean(
    target, WorkerManagerMBean.class
);
server.registerMBean(managed, objectName);
```

The `StandardMBean(implementation, interface)` constructor requires the implementation to match the declared interface. If you pass a proxy as the implementation, the proxy must also implement that interface. Specifying the interface solves contract detection, yet **does not automatically give a proxy missing methods or fix wiring bugs**.

## 3. JDK Dynamic Proxy: Exposing Only Selected Interfaces

A JDK dynamic proxy implements a specified list of interfaces; it does not subclass the target class. For example:

```java
import java.lang.reflect.Proxy;

WorkerManager target = new WorkerManager();

WorkerManagerMBean proxy = (WorkerManagerMBean) Proxy.newProxyInstance(
    WorkerManagerMBean.class.getClassLoader(),
    new Class<?>[] { WorkerManagerMBean.class },
    (p, method, args) -> method.invoke(target, args)
);
```

This proxy is a different object from `WorkerManager`, yet still `instanceof WorkerManagerMBean`. However, the proxy's class is not named `WorkerManager`, so do not rely on the Standard MBean naming convention based on the target's class name when registering the proxy directly.

Register with an explicit interface:

```java
StandardMBean exposed = new StandardMBean(
    proxy, WorkerManagerMBean.class
);
server.registerMBean(exposed, objectName);
```

When `MBeanServer` invokes an operation through the wrapper, the call goes to the proxy and then to the target. This can matter if the proxy applies security, transactions, tracing, or other aspects.

Points to watch:

1. A proxy implementing only `BusinessService` without `WorkerManagerMBean` does not match `new StandardMBean(proxy, WorkerManagerMBean.class)` and cannot be safely cast.
2. If you expose the target instead of the proxy, JMX calls go directly to the target and can **bypass advice logic**.
3. If you expose the proxy, operations must actually be supported by the proxy, including attribute getter/setter signatures.
4. Java reflection handlers like the example above can wrap exceptions in `InvocationTargetException`; production code should unwrap and propagate exceptions according to the contract.

## 4. CGLIB/Class-Based Proxy: Subclasses Without Guaranteed Identical Detection

Spring AOP can create class proxies based on subclassing. Such a proxy is typically a subtype of the target class and can inherit interfaces implemented by the target class.

```text
WorkerManager
      ^
      |
WorkerManager$$SpringCGLIB$$...
```

This can keep the proxy compatible with `WorkerManagerMBean`, yet the runtime class name has changed. Whether JMX automatically detects the interface by naming convention should not be inferred merely from `instanceof`.

Runtime inspection example:

```java
Object bean = applicationContext.getBean("workerManager");

System.out.println(bean.getClass().getName());
System.out.println(bean instanceof WorkerManagerMBean);
```

If using Spring AOP:

```java
import org.springframework.aop.support.AopUtils;

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
System.out.println(AopUtils.getTargetClass(bean));
```

These APIs help distinguish proxy classes from target classes, but do not replace checking `MBeanInfo` after registration. Spring and JMX may apply different interface selection strategies depending on configuration.

With CGLIB, there are also technical limits such as `final` classes/methods, subclassability, and visibility; a `final` method cannot be advised by CGLIB via overriding. If a management operation must be guarded by an aspect, verify that JMX calls actually pass through the advice.

## 5. Decorator: Is the MBean Interface Forwarded?

A decorator is an object that wraps and forwards calls to another object, often written manually without a proxy framework.

```java
public interface WorkerService {
    void pause();
}

public class WorkerServiceImpl implements WorkerService, WorkerManagerMBean {
    @Override public int getActiveWorkers() { return 4; }
    @Override public void pause() { /* ... */ }
}

public class AuditedWorkerDecorator implements WorkerService {
    private final WorkerService delegate;

    public AuditedWorkerDecorator(WorkerService delegate) {
        this.delegate = delegate;
    }

    @Override public void pause() {
        System.out.println("Audit");
        delegate.pause();
    }
}
```

`AuditedWorkerDecorator` only implements `WorkerService`, so it **does not expose `getActiveWorkers()` via the MBean interface**. Registering the decorator directly may fail to be recognized by JMX under the expected contract.

A JMX-specific decorator can implement the full management interface:

```java
public class AuditedWorkerMBean implements WorkerManagerMBean {
    private final WorkerManagerMBean delegate;

    public AuditedWorkerMBean(WorkerManagerMBean delegate) {
        this.delegate = delegate;
    }

    @Override
    public int getActiveWorkers() {
        return delegate.getActiveWorkers();
    }

    @Override
    public void pause() {
        System.out.println("Audit JMX pause");
        delegate.pause();
    }
}
```

Register with an explicit wrapper:

```java
WorkerManagerMBean audited = new AuditedWorkerMBean(
    new WorkerManager()
);
server.registerMBean(
    new StandardMBean(audited, WorkerManagerMBean.class),
    objectName
);
```

This preserves the management contract while keeping audit logic on the call path. Ensure audit/security sits at a layer aligned with operational goals; a business decorator is not necessarily adequate to protect remote JMX if other invocation paths exist.

## 6. MXBeans Are Also Affected by Proxies

MXBeans rely on naming interfaces ending in `MXBean`, the `@MXBean` annotation, or explicit MXBean declaration via `StandardMBean`. MXBeans also apply mapping rules from Java types to Open Types.

Example:

```java
public interface WorkerStatsMXBean {
    long getCompletedTasks();
    void resetCounters();
}

public class WorkerStats implements WorkerStatsMXBean {
    @Override
    public long getCompletedTasks() {
        return 18;
    }

    @Override
    public void resetCounters() {
        // Reset statistics
    }
}
```

When wrapped by a proxy, ensure the exposed object actually implements `WorkerStatsMXBean`. If automatic detection is unsuitable, use the constructor specifying MXBean mode:

```java
WorkerStatsMXBean exposed = new WorkerStats();
StandardMBean wrapper = new StandardMBean(
    exposed, WorkerStatsMXBean.class, true
);
server.registerMBean(wrapper, objectName);
```

The `true` argument requests MXBean handling. In this example, `WorkerStatsMXBean` uses only primitives, so it complies with Open Type mapping.

Do not confuse two separate issues:

- **Interface identification:** Does JMX know to use `WorkerStatsMXBean`?
- **Type mapping:** Do getters/operations in the MXBean interface use types supported by MXBean rules?

A properly identified proxy can still hit mapping errors if the interface contains unsupported types. Conversely, an interface using simple types may still go undetected if the proxy does not expose the interface.

## 7. Spring Framework JMX: Exporter, Metadata, and Proxies

Spring can export MBeans via `org.springframework.jmx.export.MBeanExporter`. For Spring beans wrapped by AOP, exporting must consider both the proxy type and target class/annotation metadata.

An annotated bean:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.worker:type=WorkerManager",
    description = "Worker management"
)
public class WorkerManagerResource {

    @ManagedAttribute
    public int getActiveWorkers() {
        return 4;
    }

    @ManagedOperation
    public void pause() {
        // Pause service
    }
}
```

Spring's metadata assembler, annotation source, and exporter can expose methods declared in metadata. When a bean is proxied, the exporter's ability to inspect annotations on the target, whether methods are exposed by the proxy, and exporter settings all affect the result.

Do not assume that `@ManagedResource` on the target class is always enough for any JDK proxy to be exported as expected. Verify behavior against your actual Spring configuration.

Example exporter configuration using annotations:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class JmxConfig {
    @Bean
    public MBeanExporter mBeanExporter() {
        AnnotationJmxAttributeSource source =
            new AnnotationJmxAttributeSource();

        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);

        MetadataNamingStrategy naming = new MetadataNamingStrategy();
        naming.setAttributeSource(source);

        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(naming);
        exporter.setAutodetect(true);

        return exporter;
    }
}
```

This is an illustrative Spring Framework configuration. In applications using `@EnableMBeanExport`, Spring Boot auto-configuration, or XML namespaces, avoid creating extra exporters that cause duplicate registrations. Check exactly which exporter is active and which `ObjectName`s are registered.

### Why Might Annotations Fail to Appear?

Suppose an annotation is placed on a specific method of the target class, while a JDK proxy only exposes an interface that lacks that method. The metadata assembler might read the target's info, yet calling through the proxy lacks a matching method. Issues can arise during introspection or invocation.

Common resolutions:

1. Expose an explicit management interface that the proxy implements.
2. Choose JDK proxies vs. class-based proxies based on the contract to expose, understanding advice limitations.
3. Export a dedicated MBean adapter instead of the entire service proxy.
4. Use a `StandardMBean`/MXBean wrapper when you want to control the JMX management interface.
5. Inspect actual `MBeanInfo` and execute `getAttribute`/`invoke` rather than just checking that the bean has annotations.

## 8. MBean Adapter: Cleanly Separating Management API from Proxied Objects

In Spring applications, a clean pattern is keeping the business service behind its proxy and building a separate adapter for JMX.

```java
public interface BillingService {
    int pendingCount();
    void retryFailures(int limit);
}
```

```java
public interface BillingAdminMBean {
    int getPendingCount();
    void retryFailures(int limit);
}
```

```java
public final class BillingAdmin implements BillingAdminMBean {
    private final BillingService service;

    public BillingAdmin(BillingService service) {
        this.service = service;
    }

    @Override
    public int getPendingCount() {
        return service.pendingCount();
    }

    @Override
    public void retryFailures(int limit) {
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("limit out of range");
        }
        service.retryFailures(limit);
    }
}
```

Register the adapter as a separate Standard MBean:

```java
BillingAdmin admin = new BillingAdmin(billingServiceProxy);
server.registerMBean(
    new StandardMBean(admin, BillingAdminMBean.class),
    new ObjectName("com.example.billing:type=Admin")
);
```

Call flow:

```text
JMX client
    |
    v
BillingAdmin (MBean contract)
    |
    v
BillingService proxy (security / transaction / tracing)
    |
    v
BillingService implementation
```

Benefits include an explicit, stable JMX contract; service methods are not accidentally exposed; the Spring proxy stays in the call chain; and the adapter can constrain parameters/data types for remote JMX.

If using Spring `@ManagedResource`, you can annotate the adapter and export it via `MBeanExporter`. Avoid registering the same adapter both manually and via an auto-detecting exporter under the same `ObjectName`.

## 9. Using MBeanInfo to Verify the Actual Contract

After registration, do not only check `isRegistered(name)`. Read the metadata:

```java
import javax.management.*;

MBeanInfo info = server.getMBeanInfo(objectName);

System.out.println("MBean class: " + info.getClassName());

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "Attribute %s [%s] read=%s write=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.printf(
        "Operation %s -> %s%n",
        operation.getName(),
        operation.getReturnType()
    );
}
```

If `getPendingCount()` is exposed as an attribute, clients read it with:

```java
Object count = server.getAttribute(objectName, "PendingCount");
```

If `retryFailures(int)` is an operation:

```java
server.invoke(
    objectName,
    "retryFailures",
    new Object[] { 10 },
    new String[] { "int" }
);
```

Attribute flags (readable/writable), operation names, parameter types, and notifications are determined by the registered MBean. Proxies/adapters can make metadata differ from the full set of public methods on the target class.

Also verify the intended effect of operations: if transactions or security are required, confirm that JMX calls actually traverse the corresponding proxy. `MBeanInfo` proves interface discoverability, not that an aspect executed.

## 10. Diagnostic Checklist When Registration Fails

### Case A: NotCompliantMBeanException

Example error:

```text
javax.management.NotCompliantMBeanException
```

The cause is usually that the object does not satisfy Standard MBean, MXBean, or Dynamic MBean rules. Pay special attention to the runtime proxy class and the interfaces it implements.

Investigation steps:

```java
Object candidate = context.getBean("workerManager");

System.out.println(candidate.getClass());
System.out.println(
    java.util.Arrays.toString(candidate.getClass().getInterfaces())
);
System.out.println(candidate instanceof WorkerManagerMBean);
```

If the MBean interface exists on the proxy, try registering with an explicit wrapper. Otherwise, design an adapter or configure proxying appropriately.

### Case B: InstanceAlreadyExistsException

```text
javax.management.InstanceAlreadyExistsException
```

This means an MBean with the same `ObjectName` already exists in the `MBeanServer`. Possible causes include the same bean exported twice, multiple exporters, or an old lifecycle not unregistering.

Fix by establishing a clear owner and a single registration mechanism; do not append random UUIDs merely to dodge collisions.

### Case C: MBean Registers but Is Missing Operations

Check whether the interface exposed by the proxy contains that method. For Spring annotations, verify the annotation source/assembler and how the exporter selects metadata. For Standard MBeans, only methods on the management interface are exposed.

### Case D: Operation Runs but Aspects Do Not Apply

If the MBean holds a reference to the raw target, calls may bypass the proxy. Trace which object the adapter delegates to; if aspects are needed, the delegate should be the Spring proxy of the right interface, or use an independent safeguard at the JMX boundary.

### Case E: MXBean Data Type Errors

If metadata recognizes the interface yet reports type mapping errors, the issue may lie in Open Types rules, DTOs, generics, or constructor mapping rather than the AOP proxy itself. Address each layer according to observed symptoms.

## 11. Security and Lifecycle Considerations

Registering a proxy versus a target has operational consequences:

- **Security advice:** if security is enforced on a Spring AOP proxy, registering the target directly can let JMX calls bypass that advice. Remote JMX requires independent authentication/authorization configuration.
- **Transaction advice:** operations invoked directly on a target may not start transactions the way calls through a Spring proxy do.
- **Exception handling:** methods invoked via reflection or proxies may produce exception wrappers. Distinguish business errors, JMX errors, and proxy errors.
- **Lifecycle:** the exporter or registering component must unregister the MBean when the context closes; repeated registrations of the same `ObjectName` in a JVM need a clear owner.
- **Sensitive data:** expose only attributes and operations truly needed for management, using simple types or MXBeans/Open Data when appropriate.
- **Performance:** JMX getters may be polled continuously by clients; tracing/transaction advice on getters can add overhead.

An explicit JMX adapter is a strong choice when a system uses many Spring aspects and needs a maintainable management contract.

## 12. Practical Example: Comparing Three Registration Paths

Suppose `WorkerManager` implements `WorkerManagerMBean`.

**A. Registering the target directly:**

```java
server.registerMBean(new WorkerManager(), name);
```

Suitable when no Spring proxy is needed on the JMX call path and the class follows the Standard MBean convention.

**B. Registering a JDK proxy via wrapper:**

```java
WorkerManagerMBean proxied = /* proxy implementing WorkerManagerMBean */;
server.registerMBean(
    new StandardMBean(proxied, WorkerManagerMBean.class), name
);
```

Preserves the proxy in the call flow and declares the interface contract explicitly.

**C. Registering a separate adapter:**

```java
BillingAdmin admin = new BillingAdmin(billingServiceProxy);
server.registerMBean(
    new StandardMBean(admin, BillingAdminMBean.class),
    new ObjectName("com.example.billing:type=Admin")
);
```

Used when a business service should not implement an MBean interface and JMX capabilities need strict scoping.

In real deployments, pick one registration path per `ObjectName` and use `MBeanInfo` to verify the interface seen by clients.

## 13. Exercises

1. Write `WorkerManagerMBean` and `WorkerManager`. Register directly, then print `MBeanInfo.getAttributes()` and `getOperations()`.
2. Create a JDK proxy implementing only `WorkerManagerMBean`; register it through `StandardMBean`. Invoke `pause` via `MBeanServer.invoke`.
3. Create a decorator implementing only `WorkerService`. Explain why it does not automatically satisfy the `WorkerManagerMBean` contract; switch to an adapter or decorator implementing the MBean interface.
4. Create a Spring AOP proxy for a service with an update operation. Use a JMX adapter delegating to the Spring proxy and verify that the aspect runs when invoked via JMX.
5. Create a `@ManagedResource` in Spring and inspect actual attributes and operations after the exporter registers it. Try changing proxy mode and record any metadata differences.

## 14. Self-Check Questions

- Why might an object implementing a business interface still fail to be recognized as a Standard MBean?
- How do JDK proxies and CGLIB proxies differ in runtime type and interfaces?
- How does `StandardMBean` help handle proxy interface identification?
- What happens if you expose the target instead of a Spring proxy when transactions/security live in advice?
- Why is `@ManagedResource` alone insufficient to conclude clients will definitely see every operation?
- Which approach lets you keep business proxies while maintaining a separate, stable JMX contract?

**Key takeaway:** JMX registers whatever object is supplied at runtime. Proxies or decorators can change the type, interfaces, and call path that JMX observes. Declare MBean interfaces explicitly with `StandardMBean`, MXBeans, or adapters when needed; register the right object to preserve critical advice; and verify the actual contract with `MBeanInfo`.