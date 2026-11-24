# MethodNameBasedMBeanInfoAssembler in Spring Framework JMX

## 1. Lesson objectives

After this lesson, you will be able to:

- Explain the role of `MethodNameBasedMBeanInfoAssembler` in building the **management interface** for a Spring bean.
- Configure the list of method names exported via JMX using `managedMethods` and corresponding configuration mechanisms.
- Distinguish Java methods, JMX attributes, and JMX operations when the assembler builds `ModelMBeanInfo`.
- Combine the assembler with `MBeanExporter`, `ObjectName`, and `MBeanServer`.
- Recognize limitations of selecting by **method name** when dealing with overloaded methods, proxies, API renames, and multiple beans.
- Inspect the actual management contract using `MBeanInfo`, JConsole, or Java Mission Control.

## 2. Where the assembler fits in the MBean export process

Spring JMX can export a Spring bean as an MBean without requiring the bean to define a `SomethingMBean` interface per the Standard MBean convention. With **Model MBeans**, Spring uses an `MBeanInfoAssembler` to decide which members of the bean will be published.

Conceptual flow:

```text
Spring bean
  |
  v
MBeanExporter
  |
  +--> ObjectNamingStrategy --> ObjectName
  |
  +--> MBeanInfoAssembler --> management metadata
  |                            (attributes, operations, descriptions)
  v
ModelMBean registered in MBeanServer
  |
  v
JConsole / JMC / JMX client
```

`org.springframework.jmx.export.assembler.MethodNameBasedMBeanInfoAssembler` is an assembler that provides a way to select managed methods based on **method names**, rather than having to annotate every method or use a Java interface dedicated solely to management.

This is a useful option when you need to export a small subset of methods from an existing class, especially when that class should not depend on Spring JMX annotations.

**Distinguish three elements:**

| Component | Function |
| --- | --- |
| `MBeanExporter` | Takes beans, creates/registers MBeans into `MBeanServer`, and manages lifecycle |
| `MethodNameBasedMBeanInfoAssembler` | Selects methods participating in the management contract by a list of names |
| `ObjectName` | MBean identifier in `MBeanServer`, e.g., `com.example.jobs:type=Worker,name=Billing` |

The assembler is not a JMX server and does not open remote JMX connections by itself. It supplies **metadata** to the exporter.

## 3. When should MethodNameBasedMBeanInfoAssembler be used?

Suppose a Java service has multiple methods:

```java
public class BillingWorker {
    private volatile boolean paused;
    private volatile int pendingJobs = 25;

    public int getPendingJobs() {
        return pendingJobs;
    }

    public boolean isPaused() {
        return paused;
    }

    public void setPaused(boolean paused) {
        this.paused = paused;
    }

    public void retryFailedJobs(int limit) {
        // Calls retry business logic with a limit.
    }

    public void reconcileLedger() {
        // Internal logic, not intended to be exposed via JMX.
    }
}
```

You want operators to only view `PendingJobs` and `Paused`, and be able to request `retryFailedJobs`, while **not** being able to call `reconcileLedger`.

Instead of exporting all public methods, create an allowlist containing only the exact names needed for management:

```text
getPendingJobs
isPaused
setPaused
retryFailedJobs
```

The assembler selects the corresponding methods. In JMX, getters/setters recognized by JavaBeans conventions can become attributes, while business actions are exposed as operations depending on Spring's metadata-building logic.

**Security mindset:** the list of managed methods is part of the application's public contract. Choose intentionally and keep it narrow; do not treat `public` as synonymous with `safe for remote management`.

## 4. Java configuration with MBeanExporter

The following example configures the assembler and exporter using Spring Java configuration:

```java
package com.example.billing.config;

import com.example.billing.BillingWorker;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.assembler.MethodNameBasedMBeanInfoAssembler;

@Configuration
public class BillingJmxConfig {

    @Bean
    public BillingWorker billingWorker() {
        return new BillingWorker();
    }

    @Bean
    public MethodNameBasedMBeanInfoAssembler billingAssembler() {
        MethodNameBasedMBeanInfoAssembler assembler =
                new MethodNameBasedMBeanInfoAssembler();

        assembler.setManagedMethods(
                "getPendingJobs",
                "isPaused",
                "setPaused",
                "retryFailedJobs"
        );
        return assembler;
    }

    @Bean
    public MBeanExporter billingExporter(
            BillingWorker billingWorker,
            MethodNameBasedMBeanInfoAssembler billingAssembler) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(billingAssembler);
        exporter.setBeans(Map.of(
            "com.example.billing:type=Worker,name=Billing",
            billingWorker
        ));
        return exporter;
    }
}
```

Here:

1. `billingWorker` is the bean executing the logic.
2. `billingAssembler` defines which methods are published.
3. `setBeans` maps an `ObjectName` to a specific bean.
4. The exporter uses the assembler to build metadata for the Model MBean.
5. MBeanServer stores the MBean for JMX clients to access.

In a real project example, you need to import the `BillingWorker` class. This configuration assumes no other exporter has registered the same `ObjectName`.

### Explicit array configuration

In some Java styles, you can construct an array:

```java
String[] allowed = {
    "getPendingJobs",
    "isPaused",
    "setPaused",
    "retryFailedJobs"
};
assembler.setManagedMethods(allowed);
```

This list acts as an **allowlist**. If you want to add an operation, add the method name and treat it as a JMX contract change that must be reviewed.

## 5. Equivalent XML configuration

Projects using XML can declare the assembler bean and attach it to the exporter:

```xml
<bean id="billingWorker" class="com.example.billing.BillingWorker"/>

<bean id="billingAssembler"
      class="org.springframework.jmx.export.assembler.MethodNameBasedMBeanInfoAssembler">
    <property name="managedMethods">
        <list>
            <value>getPendingJobs</value>
            <value>isPaused</value>
            <value>setPaused</value>
            <value>retryFailedJobs</value>
        </list>
    </property>
</bean>

<bean id="billingExporter"
      class="org.springframework.jmx.export.MBeanExporter">
    <property name="assembler" ref="billingAssembler"/>
    <property name="beans">
        <map>
            <entry key="com.example.billing:type=Worker,name=Billing"
                   value-ref="billingWorker"/>
        </map>
    </property>
</bean>
```

In XML, the `managedMethods` property accepts a list of strings representing method names. The exporter uses the configured assembler only if the `assembler` property is wired properly.

Distinguish this from:

```xml
<context:mbean-export/>
```

The `context:mbean-export` element is typically used to enable annotation-based export (such as `@ManagedResource` and `@ManagedOperation`). It **does not automatically use** the `MethodNameBasedMBeanInfoAssembler` bean you just declared for any other exporter. To select methods by name, configure the specific assembler on the exporter responsible for registering the bean.

When both mechanisms are active, avoid duplicate `ObjectName`s.

## 6. Method selection mechanism by name

`MethodNameBasedMBeanInfoAssembler` belongs to the name-based assembler family and matches Java method names considered for management exposure.

Design-wise, this means:

- `getPendingJobs()` is in the allowlist, so it is considered for export.
- `retryFailedJobs(int)` is in the allowlist, so it is considered for export.
- `reconcileLedger()` is not in the list, so it is not included in metadata under the allowlist.
- If the class has multiple overloaded methods with the same name, configuring **by name alone** is not a mechanism for picking a single overload based on parameter signatures.

Example:

```java
public void retryFailedJobs(int limit) { /* ... */ }

public void retryFailedJobs(String jobId) { /* ... */ }
```

If the allowlist contains `retryFailedJobs`, do not assume only the `int` overload is published. Check `MBeanInfo.getOperations()` or design distinct names, for example:

```java
public void retryUpTo(int limit) { /* ... */ }

public void retryById(String jobId) { /* ... */ }
```

When strict signature control is required for the JMX contract, consider a clear Standard MBean/MXBean interface, a management adapter, or a more suitable assembler/metadata approach.

## 7. Getters, setters, and JMX attributes

An important situation is the difference between a **Java method name** and a **JMX attribute name**.

Java methods:

```java
public int getPendingJobs();
public boolean isPaused();
public void setPaused(boolean paused);
```

Management metadata can represent this as:

```text
Attributes:
  PendingJobs    int      read-only
  Paused         boolean  read-write
```

That is how JavaBeans naming is typically parsed by Spring when building MBean metadata. Select a getter for reading; add a setter only when you truly want to allow state mutation via JMX.

If only `getPendingJobs` is in the allowlist, clients cannot modify `PendingJobs` by default. If `setPaused` is in the allowlist, users with write permission on `Paused` can alter application state.

**Do not treat setters as harmless.** Exporting `setEnabled`, `setTimeout`, or `setPaused` exposes a management control point much like an operation.

A method that does not follow getter/setter conventions, such as `pendingJobs()`, will generally be treated as an operation if published rather than automatically becoming a `PendingJobs` attribute.

## 8. Does MethodNameBasedMBeanInfoAssembler create a new Java interface?

No. The assembler provides a **management interface at the JMX metadata level**; it does not generate a new Java interface source file named `BillingWorkerMBean`.

The two models can deliver a similar JMX experience, but they define the contract differently:

**Standard MBean:**

```java
public interface BillingWorkerMBean {
    int getPendingJobs();
    void retryFailedJobs(int limit);
}
```

```java
public class BillingWorker implements BillingWorkerMBean {
    // ...
}
```

**Spring Model MBean with a name-based assembler:**

```text
BillingWorker (existing Java class)
    +
MethodNameBasedMBeanInfoAssembler
    +
MBeanExporter
    =
MBean with management metadata selected by method name
```

The benefit of the second approach is reducing the service class's dependency on a dedicated JMX interface. In return, the contract relies on strings in configuration and introspection rules, which must be tested after refactoring.

## 9. Comparing common assemblers

| Assembler type | Selection mechanism | When appropriate |
| --- | --- | --- |
| `SimpleReflectiveMBeanInfoAssembler` | Based on reflection of eligible methods | Demos/exploration; be careful due to broad exposed surface |
| `MethodNameBasedMBeanInfoAssembler` | List of managed method names | Need a simple allowlist without modifying the class |
| `MethodExclusionMBeanInfoAssembler` | List of excluded names | Need to exclude a few methods in a large API; must manage risk of new methods |
| `InterfaceBasedMBeanInfoAssembler` | Specified Java interfaces | Need a clear interface contract |
| `MetadataMBeanInfoAssembler` | Annotations/metadata via `JmxAttributeSource` | Need detailed documentation in code with `@Managed*` |

A useful selection rule:

- Want to expose a few methods from an existing class: **MethodNameBased**.
- Want a stable, strongly typed management contract: **InterfaceBased** or a Standard MBean adapter.
- Want methods, attributes, descriptions, and parameters documented near the code: **MetadataMBeanInfoAssembler** with appropriate annotations.

No option solves all of security by itself; every mechanism requires reviewing the scope of published methods.

## 10. Verifying results with MBeanInfo

After the Spring context starts and the exporter registers successfully, use the JMX API to read metadata.

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
        ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
        "com.example.billing:type=Worker,name=Billing"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException("Billing worker MBean was not registered");
}

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attr : info.getAttributes()) {
    System.out.printf(
        "Attribute: %s, read=%s, write=%s%n",
        attr.getName(),
        attr.isReadable(),
        attr.isWritable()
    );
}

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.printf(
        "Operation: %s, return=%s%n",
        op.getName(),
        op.getReturnType()
    );
}
```

The example above is only accurate if the exporter registers into the **platform `MBeanServer`**. With a custom MBeanServer, you must use a reference to that exact server.

To verify usage results:

```java
Object count = server.getAttribute(name, "PendingJobs");
System.out.println("Pending: " + count);
```

And invoke an operation:

```java
server.invoke(
    name,
    "retryFailedJobs",
    new Object[] { 5 },
    new String[] { "int" }
);
```

If `MBeanInfo` does not contain the expected operation or attribute, verify that the method name in `managedMethods` is spelled accurately and that the exporter evaluated it on the actual class.

## 11. Difference between method name and signature when invoking JMX

`managedMethods` operates at the **method selection for metadata creation** layer, whereas `MBeanServer.invoke` operates at the **calling a published operation** layer.

Configuration example:

```java
assembler.setManagedMethods("retryFailedJobs");
```

When calling the JMX operation, the exact signature is still required:

```java
server.invoke(
    name,
    "retryFailedJobs",
    new Object[] { Integer.valueOf(5) },
    new String[] { "int" }
);
```

If the parameter type declared in JMX metadata is `int`, you must pass `"int"`. Passing the signature `"java.lang.Integer"` is not equivalent. If overloads differ, passing the exact signature is mandatory.

It is best to read `MBeanOperationInfo.getSignature()` to learn the name and type of each parameter rather than guessing from the source method.

## 12. Spring AOP proxies and method selection

A Spring bean may be wrapped by a JDK proxy or CGLIB due to `@Transactional`, `@Async`, security, or custom advice.

If the exporter receives a proxy instead of the target, the actual set of methods and metadata may differ from the target class:

```text
MBeanExporter
    |
    v
Spring AOP proxy
    |
    v
BillingWorker target
```

Specifically for JDK dynamic proxies:

- The proxy only implements the specified interfaces.
- A public method that exists only on the target class and not on an interface may not be callable through the proxy.
- Name-based configuration does not automatically make the proxy expose additional methods.

With CGLIB/class-based proxies, the proxy class subclasses the target class, yet you still need to check which methods are actually intercepted and which public signatures the exporter uses.

The clean solution when the call path needs clarity is a **JMX adapter**:

```java
public interface BillingControlService {
    int pendingJobs();
    void retryFailedJobs(int maxCount);
}

public final class BillingJmxAdapter {
    private final BillingControlService delegate;

    public BillingJmxAdapter(BillingControlService delegate) {
        this.delegate = delegate;
    }

    public int getPendingJobs() {
        return delegate.pendingJobs();
    }

    public void retryFailedJobs(int maxCount) {
        if (maxCount < 1 || maxCount > 100) {
            throw new IllegalArgumentException("maxCount must be 1..100");
        }
        delegate.retryFailedJobs(maxCount);
    }
}
```

The exporter registers the adapter, and the assembler selects `getPendingJobs` and `retryFailedJobs`. The delegate can be a Spring proxy so transaction/security advice continues to apply on the service.

An adapter also helps avoid exposing sensitive business methods when new features are added to the service.

## 13. Risks when renaming methods or refactoring

A string-based allowlist is configuration that is **not compiler-checked** like a direct method call.

Suppose you rename:

```java
getPendingJobs()  -> getQueueDepth()
```

but forget to update:

```java
assembler.setManagedMethods("getPendingJobs");
```

When Spring builds MBean metadata, the old method no longer exists and the expected attribute can disappear. The rest of the application can still compile and run, causing the error to appear only in management tools.

Helpful practices:

1. Centralize the list of managed methods in a single configuration.
2. Write an integration test checking `MBeanInfo` after the context starts.
3. Document `ObjectName` and stable attributes/operations as an API contract.
4. When renaming, update dashboards, alerts, and scripts before removing the old name.
5. Do not use vague name patterns or broad exposure merely to make up for missing methods after refactoring.

If you need a strict, change-resistant contract, interface-based or controlled annotation metadata may be more suitable.

## 14. Security: do not expose too many methods

`MethodNameBasedMBeanInfoAssembler` helps reduce the number of published methods, but a method list **is not an authorization system**.

If `retryFailedJobs` is in the allowlist, a client with invoke capability can call that method according to its JMX permissions. An operation can mutate state, trigger retries, clear caches, or disrupt the service.

Combine it with:

- Exposing only methods with a clear operational management purpose.
- Validating parameters and limiting operation frequency/intensity.
- Never exporting methods returning secrets, tokens, or personal data.
- Configuring authentication, authorization, and TLS for remote JMX per policy.
- Restricting network access to the JMX port.
- Logging/auditing critical actions if traceability is required.
- Verifying whether security aspects are enforced when JMX calls into the bean.

Do not rely on JConsole displaying an operation as “read-only” or a friendly description to conclude it is safe.

## 15. Lifecycle and common pitfalls

`MBeanExporter` registers MBeans when the Spring context initializes and unregisters the MBeans it manages when the context closes cleanly.

Common issues:

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| MBean does not appear | Exporter not initialized, bean not mapped, different server | Check context, `setBeans`, `MBeanServer` |
| `InstanceAlreadyExistsException` | Duplicate ObjectName due to multiple exporters/contexts | Pick a single owner for registration |
| `NotCompliantMBeanException` | Bean unsuitable for export style or invalid proxy/contract | Check assembler, bean type, JMX contract |
| Only some attributes visible | Missing getter/setter names in `managedMethods` | Compare allowlist against runtime methods |
| Expected operation missing | Misspelled name or method was renamed | Check `MBeanInfo`, refactoring history |
| `ReflectionException` on invoke | Operation name or signature does not match metadata | Inspect `MBeanOperationInfo.getSignature()` |
| Operation runs without Spring advice | Target registered instead of proxy | Use an adapter or delegate proxy properly |
| Remote client cannot read data | Remote JMX/serialization or access permissions | Check connector, TLS, authentication, data types |

To diagnose, start with three questions: **Is the MBean registered? Does `MBeanInfo` have the expected names? Does the invocation signature match?**

## 16. Working with multiple beans and choosing the right configuration

Suppose an application has two workers:

```text
com.example.billing:type=Worker,name=Invoicing
com.example.billing:type=Worker,name=Reconciliation
```

If both share the same method structure, they can use the same assembler allowlist:

```java
exporter.setBeans(Map.of(
    "com.example.billing:type=Worker,name=Invoicing", invoicingWorker,
    "com.example.billing:type=Worker,name=Reconciliation", reconciliationWorker
));
exporter.setAssembler(billingAssembler);
```

When two beans need different sets of methods, a single shared allowlist may be wrong: an operation valid for one worker may not be appropriate for the other. In that case, consider creating separate exporters or assemblers with clear ownership, or using an assembler that distinguishes by bean key / dedicated management interface.

**Do not overuse creating new exporters** if it causes duplicate registrations or complicates lifecycle management. Each ObjectName should have only one registration owner within the same MBeanServer.

## 17. Practice exercises

1. Create a `BillingWorker` class with `getPendingJobs`, `isPaused`, `setPaused`, `retryFailedJobs`, and `reconcileLedger`. Configure `MethodNameBasedMBeanInfoAssembler` to publish only the first four methods.
2. Open JConsole or JMC and confirm `PendingJobs`, `Paused`, and `retryFailedJobs` appear; `reconcileLedger` is not in the contract.
3. Remove `setPaused` from the allowlist, reinitialize the context, and check whether `Paused` is still writable.
4. Create two overloads `retryFailedJobs(int)` and `retryFailedJobs(String)`. Inspect `MBeanInfo` to understand the limitation of name-based selection.
5. Rename `getPendingJobs` to `getQueueDepth` while keeping the old configuration; observe the impact on metadata and fix the allowlist.
6. Write an integration test verifying the ObjectName, expected attributes/operations, and cleanup when closing the context.
7. Try replacing the direct bean with an adapter calling through a Spring proxy; verify whether advice still executes on JMX invocation.

## 18. Self-check questions

- What does `MethodNameBasedMBeanInfoAssembler` decide during MBean export?
- Why is a `managedMethods` configuration an allowlist rather than an authorization system?
- How can a selected `getPendingJobs` getter be represented in JMX?
- Why are overloads a case requiring attention when selecting by method name?
- If a Java method is renamed and you forget to update XML, will the compiler necessarily catch the error?
- How does `MethodNameBasedMBeanInfoAssembler` differ from `MetadataMBeanInfoAssembler` and `InterfaceBasedMBeanInfoAssembler`?
- When a Spring AOP proxy does not expose a method, can the `managedMethods` list fix that situation by itself?
- What is the accurate way to verify that an operation has been exported?

**Key takeaway:** `MethodNameBasedMBeanInfoAssembler` is a Spring JMX tool for defining the management surface based on a **list of method names**. It lets you pick a small subset of methods from a Spring bean without modifying the class to add annotations. Configure the allowlist accurately, wire the assembler to the right `MBeanExporter`, inspect `MBeanInfo` after registration, and protect operations with side effects using proper permissions and validation.