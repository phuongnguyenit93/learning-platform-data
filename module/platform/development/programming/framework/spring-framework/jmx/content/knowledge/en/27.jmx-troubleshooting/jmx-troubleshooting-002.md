# ObjectName Differs from Expected Name in Spring Framework JMX

## 1. Lesson Objectives

In Spring Framework JMX, you may configure a Spring bean named `paymentQueue`, place an `@ManagedResource(objectName = "...")` annotation, or declare an `MBeanExporter`, yet when opening JConsole/JMC you see the MBean under a different `ObjectName` than expected. This can cause dashboards to fail to find attributes, scripts invoking operations to fail, or two applications to accidentally share a management name.

This lesson belongs to **Spring Framework JMX → Troubleshooting**, focusing on causes and resolutions when the actual ObjectName differs from the expected ObjectName.

After this lesson, you will be able to:

- Distinguish **Spring bean name**, **Java class name**, **JMX domain**, and **ObjectName**.
- Determine the exact name under which an MBean was registered using `MBeanServer.queryNames`.
- Distinguish a **display string** difference from an **ObjectName identity** difference.
- Trace configurations of `MBeanExporter`, `ObjectNamingStrategy`, `MetadataNamingStrategy`, `@ManagedResource`, and bean keys.
- Recognize scenarios where JDK/CGLIB proxies and multiple exporters change the observed name.
- Verify the right `MBeanServer`/remote connector before concluding a name was set incorrectly.
- Write integration tests to prevent ObjectNames from changing unexpectedly after refactoring or redeployment.

## 2. First: What Is an ObjectName?

JMX identifies MBeans with `javax.management.ObjectName`:

```text
domain:key1=value1,key2=value2,...
```

For example:

```text
com.example.billing:type=Queue,name=Payment
```

Within an `MBeanServer`, this ObjectName identifies a unique registration. The Spring bean may be named `paymentQueueMonitor` and the Java class named `PaymentQueueMonitor`, yet the JMX name can still be `com.example.billing:type=Queue,name=Payment`.

Four commonly confused names:

| Concept | Example | Used For |
| --- | --- | --- |
| Spring bean name | `paymentQueueMonitor` | Looking up/injecting beans in ApplicationContext |
| Java class | `com.example.billing.PaymentQueueMonitor` | Defining type and implementation |
| JMX domain | `com.example.billing` | Grouping MBeans within a registry |
| JMX ObjectName | `com.example.billing:type=Queue,name=Payment` | Identifying an MBean inside MBeanServer |

**There is no rule requiring an ObjectName to match the Spring bean name or Java class.** If you want a stable naming contract, it must be configured and tested explicitly.

## 3. Common Symptoms

Some manifestations:

1. JConsole displays `com.example.billing:name=Payment,type=Queue` instead of `com.example.billing:type=Queue,name=Payment`.
2. The Spring bean is named `paymentQueue`, but the MBean is exported under the class name or a different domain.
3. `@ManagedResource(objectName = "...")` declares one name, but the actual exporter does not use annotation metadata as expected.
4. A JMX client querying a fixed name returns `InstanceNotFoundException`.
5. A dashboard fails to find the MBean after enabling Spring AOP or changing the naming strategy.
6. The MBean appears on a different JVM/connector, leading operators to think the name changed.
7. Two exporters exist—one using explicit mapping and another using autodetection—leading to unexpected results or name collision errors.

Diagnostics should be split into **name comparison**, **registry identification**, **name generation path**, and **export lifecycle**.

## 4. Different Key Order Is Not a Different ObjectName

The two strings:

```text
com.example.billing:type=Queue,name=Payment
com.example.billing:name=Payment,type=Queue
```

represent **the exact same ObjectName**. JMX does not rely on key property ordering to determine identity.

```java
import javax.management.ObjectName;

ObjectName expected = new ObjectName(
    "com.example.billing:type=Queue,name=Payment"
);

ObjectName actual = new ObjectName(
    "com.example.billing:name=Payment,type=Queue"
);

System.out.println(expected.equals(actual)); // true
System.out.println(expected.getCanonicalName());
System.out.println(actual.getCanonicalName());
```

Therefore:

- If `ObjectName.equals` is `true`, there is no need to change naming just because JConsole renders keys in a different order.
- `getCanonicalName()` is useful for logging and comparing canonical names.
- Do not use `String.equals` on two raw strings to conclude registrations are different.

This is the first step to avoid changing a configuration that is already correct.

## 5. Determining the Actually Registered ObjectName

Do not guess the MBean name from annotations or the Spring bean name. Query the server directly:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import java.util.Set;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName pattern = new ObjectName(
    "com.example.billing:*"
);

Set<ObjectName> names = server.queryNames(pattern, null);

for (ObjectName item : names) {
    System.out.println(item.getCanonicalName());
}
```

If the name is not found:

- The MBean may not have been registered yet.
- The actual domain may differ from `com.example.billing`.
- The exporter may be using a custom `MBeanServer`.
- The client may be connecting to the wrong JVM or endpoint.
- The bean may have been unregistered due to context shutdown.

If the domain is unknown, **in a controlled test/diagnostic environment** you can list domains via `getDomains()` or search on an identified server. Avoid scanning too broadly across a production system with many MBeans unless necessary.

### Checking a Specific Name

```java
ObjectName expected = new ObjectName(
    "com.example.billing:type=Queue,name=Payment"
);

System.out.println(
    "Expected name registered = " + server.isRegistered(expected)
);
```

`isRegistered == false` only proves **the server being queried** does not have that name; it does not prove Spring changed the name. Verify the target server before changing configuration.

## 6. Distinguishing Wrong ObjectName from Wrong MBeanServer

A single JVM can contain multiple MBeanServers:

```text
JVM
  |
  +-- Platform MBeanServer
  |     +-- java.lang:type=Memory
  |
  +-- Custom MBeanServer
        +-- com.example.billing:type=Queue,name=Payment
```

If the exporter uses:

```java
exporter.setServer(customServer);
```

while diagnostic code uses:

```java
ManagementFactory.getPlatformMBeanServer();
```

then `isRegistered(expected)` returns `false` even though the actual name is completely correct.

Check:

- Which server bean is injected into the exporter?
- Are `MBeanServerFactoryBean` or `MBeanServerFactory` used to create a custom server?
- Which registry is the JConsole/JMC client connected to?
- If using a remote connector, does the connector serve the platform server or the custom server?
- Are multiple JVMs or replicas using the same ObjectName?

**System-wide identity requires both the server/endpoint and the ObjectName.** Two JVMs can use the same name without conflict.

## 7. Sources of ObjectName Generation in Spring

Spring has several ways to determine the name when exporting an MBean.

### Approach 1: Explicit beans map

```java
import java.util.Map;
import org.springframework.jmx.export.MBeanExporter;

MBeanExporter exporter = new MBeanExporter();

exporter.setBeans(Map.of(
    "com.example.billing:type=Queue,name=Payment",
    paymentQueueMonitor
));
```

In this configuration, the map key provides the full JMX name. If the key is valid as an ObjectName, it can be used directly for registration depending on the configuration path.

### Approach 2: Annotation-based metadata

```java
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.billing:type=Queue,name=Payment"
)
public class PaymentQueueAdmin {
    // @ManagedAttribute / @ManagedOperation ...
}
```

When using an annotation exporter and an appropriate metadata naming strategy, the `objectName` information in `@ManagedResource` can be used to determine the name.

### Approach 3: ObjectNamingStrategy

An exporter can use an `ObjectNamingStrategy` such as `KeyNamingStrategy`, `MetadataNamingStrategy`, `IdentityNamingStrategy`, or a custom strategy.

```text
Spring bean / bean key
       |
       v
ObjectNamingStrategy
       |
       v
javax.management.ObjectName
       |
       v
MBeanServer.registerMBean(...)
```

If the name differs from expected, find out **which configuration path is actually active**. An annotation on a class is not necessarily prioritized if the exporter is using an explicit key or a different strategy.

## 8. MetadataNamingStrategy and @ManagedResource

For annotation-driven JMX, Spring typically combines:

```text
AnnotationJmxAttributeSource
        |
        v
MetadataNamingStrategy
        |
        v
@ManagedResource(objectName = ...)
        |
        v
ObjectName
```

If the annotation is detected and the supplied name is suitable, the strategy can use the declared name.

However, if you create an `MBeanExporter` manually and only call:

```java
exporter.setBeans(Map.of("paymentQueue", bean));
```

without configuring the appropriate metadata naming/assembler, do not assume the exporter will automatically pick up `@ManagedResource(objectName=...)` via the annotation-driven mechanism.

To check, determine:

1. Which exporter is in use.
2. That exporter's naming strategy.
3. Whether a metadata source/assembler is configured.
4. Whether the actual bean received by the exporter is the target or a proxy.
5. Whether the ObjectName in `MBeanServer` matches the expected metadata.

## 9. KeyNamingStrategy and Bean Key Differences

Suppose:

```java
exporter.setBeans(Map.of(
    "paymentQueue",
    paymentQueueMonitor
));
```

The key `paymentQueue` may be a logical key for the naming strategy, not a full ObjectName. In that case, the strategy decides the final name:

```text
paymentQueue -> com.example.billing:type=Queue,name=Payment
```

If the key is changed in configuration and the naming strategy uses the key to construct the name, the ObjectName may change accordingly. Conversely, if the explicit mapping uses a full ObjectName, changing the Spring bean name might not affect the JMX name.

Therefore, before refactoring bean IDs, know **which key is part of the management contract**. Do not use an unstable name just because it is convenient for dependency injection.

## 10. IdentityNamingStrategy and Runtime Names

One surprising cause is naming based on identity/class.

When a strategy uses runtime identity, the ObjectName may contain traces of the implementation class or object identity. Such a name is unsuitable when dashboards expect a fixed logical name.

Expected example:

```text
com.example.billing:type=Queue,name=Payment
```

yet in practice it exports a name containing class details or an instance-specific suffix.

The solution is usually to use:

- An explicit ObjectName for resources with a stable identity.
- Metadata naming with `@ManagedResource(objectName=...)`.
- A custom naming strategy mapping logical bean keys to stable names.

Do not merely "strip the suffix" on the client as a quick workaround. If the name can change across restarts, fix it at the **name generation source** and add an integration test.

## 11. How Spring AOP Proxies Affect Naming

A Spring bean can be wrapped by:

- A JDK dynamic proxy.
- A CGLIB/class-based proxy.

If a naming strategy directly uses:

```java
managedBean.getClass().getName()
```

then the runtime class name may differ from the target class:

```text
jdk.proxy2.$Proxy...
OrderQueueService$$SpringCGLIB$$...
```

This is a source of unstable names. With annotation-based JMX, the metadata source must locate annotations on the appropriate class/methods; the proxy type can also affect introspection capabilities.

You can diagnose this:

```java
import org.springframework.aop.framework.AopProxyUtils;
import org.springframework.aop.support.AopUtils;

Object bean = context.getBean("paymentQueueMonitor");

System.out.println("Runtime class: " + bean.getClass());
System.out.println("AOP proxy: " + AopUtils.isAopProxy(bean));
System.out.println(
    "Target class: " + AopProxyUtils.ultimateTargetClass(bean)
);
```

**Do not manually unwrap the target object from the proxy for export** without reviewing transaction/security advice; doing so can cause JMX operations to bypass necessary AOP logic. If the service proxy is complex, consider a dedicated JMX adapter.

## 12. MBeanExporter and Multiple Duplicate Exporters

An application may accidentally have:

```java
@EnableMBeanExport
```

alongside a manually declared `MBeanExporter` bean. If two exporters both detect the same resource:

- They may try to register the same ObjectName and throw `InstanceAlreadyExistsException`.
- They may use two different naming schemes, causing the same bean to appear multiple times under two ObjectNames.
- With `RegistrationPolicy.IGNORE_EXISTING`, a new registration may be skipped, leaving operators seeing the old MBean.
- With `REPLACE_EXISTING`, the existing resource may be replaced depending on ownership/configuration.

When the ObjectName differs from expected, inspect all exporters actually active in the ApplicationContext, not just the exporter whose source code you happen to be looking at.

Do not fix this by randomly deleting MBeans on the server: that MBean might belong to another module.

## 13. Java Configuration with a Stable Explicit ObjectName

An easily testable configuration example:

```java
package com.example.billing.config;

import com.example.billing.jmx.PaymentQueueMonitor;
import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

@Configuration
public class BillingJmxConfiguration {

    public static final String PAYMENT_QUEUE_OBJECT_NAME =
        "com.example.billing:type=Queue,name=Payment";

    @Bean
    public PaymentQueueMonitor paymentQueueMonitor() {
        return new PaymentQueueMonitor();
    }

    @Bean
    public MBeanServer platformMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter billingMBeanExporter(
            PaymentQueueMonitor paymentQueueMonitor,
            MBeanServer platformMBeanServer) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(platformMBeanServer);
        exporter.setBeans(Map.of(
            PAYMENT_QUEUE_OBJECT_NAME,
            paymentQueueMonitor
        ));
        exporter.setRegistrationPolicy(
            RegistrationPolicy.FAIL_ON_EXISTING
        );
        return exporter;
    }
}
```

In this example, `PaymentQueueMonitor` must be a valid MBean according to the chosen export method (Standard MBean interface or corresponding ModelMBean metadata). The key point is that the identifier lives in an intentionally managed constant and is covered by tests.

If the application has many MBeans, you can create a dedicated helper to construct ObjectNames using the `ObjectName` API instead of arbitrary string concatenation.

## 14. Testing the Expected ObjectName Against MBeanServer

An integration test should start a real context and assert the exact ObjectName:

```java
import static org.junit.jupiter.api.Assertions.*;

import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class BillingJmxNamingTest {

    @Test
    void registersWithStableObjectName() throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                BillingJmxConfiguration.class)) {

            MBeanServer server = context.getBean(MBeanServer.class);

            ObjectName expected = new ObjectName(
                BillingJmxConfiguration.PAYMENT_QUEUE_OBJECT_NAME
            );

            assertTrue(
                server.isRegistered(expected),
                "MBean missing: " + expected.getCanonicalName()
            );

            assertFalse(expected.isPattern());
        }
    }
}
```

For tests running in parallel, replace the platform server with a dedicated `MBeanServer` in the test configuration to avoid conflicts with production beans or other tests.

Read `MBeanInfo` if you want to further verify the contract:

```java
var info = server.getMBeanInfo(expected);

System.out.println("MBean class = " + info.getClassName());
System.out.println("Attribute count = " + info.getAttributes().length);
```

**Do not use `MBeanInfo.getClassName()` alone to determine the owner:** Spring ModelMBeans can have different metadata/classes than expected.

## 15. Inspecting Actual Names with queryNames

If the exact name is not found, query by domain or a stable key:

```java
ObjectName pattern = new ObjectName(
    "com.example.billing:type=Queue,*"
);

var candidates = server.queryNames(pattern, null);

for (ObjectName candidate : candidates) {
    System.out.println(candidate.getCanonicalName());
}
```

If you see:

```text
com.example.billing:name=Payment,type=Queue
```

compare using `equals`. If you see:

```text
com.example.billing:name=PaymentQueue,type=Queue
```

then the key property genuinely differs, and you need to trace the naming strategy or configuration.

If no candidates appear, verify the server. Do not change the expected name just to match another random resource that happens to exist in the namespace.

## 16. Errors Related to Domain, Keys, and Quoting

A few cases:

### Different Domain

```text
expected: com.example.billing:type=Queue,name=Payment
actual:   com.example.payment:type=Queue,name=Payment
```

This is a different ObjectName. Check the naming convention or metadata.

### Different Key

```text
expected: com.example.billing:type=Queue,name=Payment
actual:   com.example.billing:type=Queue,id=Payment
```

This is also a different ObjectName. `name` and `id` are not equivalent.

### Different Case in Value

```text
expected: com.example.billing:type=Queue,name=Payment
actual:   com.example.billing:type=Queue,name=payment
```

ObjectName key property values are case-sensitive. These two names are not equivalent.

### Special Characters

If a logical name contains `,`, `=`, `:`, `*`, or `?`, handle it according to ObjectName syntax. You can use:

```java
String logicalName = "Billing,Priority";
String objectNameText =
    "com.example.billing:type=Queue,name="
    + ObjectName.quote(logicalName);

ObjectName name = new ObjectName(objectNameText);
```

Do not concatenate untrusted input into an ObjectName without controlling syntax and values. A wildcard character can turn the name into a pattern rather than a concrete name suitable for registration.

## 17. Is the Actual Name Stable Across Restarts?

An important diagnostic test:

```text
Run 1:
  ObjectName = com.example.billing:type=Queue,name=Payment

Run 2:
  ObjectName = com.example.billing:type=Queue,name=Payment
```

If the ObjectName changes across restarts even though the logical resource is the same, check:

- Naming based on UUID/time/PID.
- Naming based on runtime class/proxy identity.
- Dynamically generated bean keys.
- Changes in environment or deployment properties.
- Differences between active profiles/configurations.
- Multiple exporters choosing different naming strategies.

Dashboards, alerts, and runbooks should rely on stable logical names, unless the goal is intentionally to distinguish instances using a meaningful key.

## 18. How to Investigate When Remote JMX Cannot Find the Name

A remote client might connect to another JVM that uses the same ObjectName. Therefore, when JConsole reports the MBean is missing:

1. Verify the `JMXServiceURL` or hostname/port.
2. Verify the environment (dev/staging/prod) and instance.
3. Successfully connect to the remote `MBeanServerConnection`.
4. Call `getDomains()`/`queryNames()` on that connection.
5. Compare the exact ObjectName.
6. If the MBean is absent, inspect the exporter on the target JVM.
7. Check whether a custom MBeanServer is not being served by the connector.

A valid ObjectName on the **wrong endpoint** will still fail to access the desired MBean. Do not alter the ObjectName just to match the wrong JVM.

## 19. Step-by-Step Diagnostic Workflow

```text
1. Write down expected ObjectName
          |
          v
2. Parse with new ObjectName(...)
          |
          v
3. Identify right MBeanServer / remote endpoint
          |
          v
4. isRegistered(expected)?
       /           \
     yes           no
      |             |
      v             v
5. Read MBeanInfo  6. queryNames(domain/pattern)
      |             |
      v             v
Correct name?      Any candidates?
                    /       \
                  yes       no
                   |         |
                   v         v
              Compare       Check exporter,
              canonical     server, context,
              name/key      lifecycle
                   |
                   v
              Trace source:
              bean key / strategy /
              annotation / proxy
```

Once the root cause is found, fix it at the name generation source and re-run the integration test. Do not patch it by hardcoding a random name spotted in JConsole without understanding its semantics.

## 20. Causes and Remedies Table

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| JConsole displays keys in a different order | Canonicalization | Compare with `ObjectName.equals()`, do not change |
| `isRegistered` is false | Wrong MBeanServer or exporter did not run | Check server/context/lifecycle |
| `@ManagedResource` not used as name | Exporter not using annotation metadata naming | Configure proper exporter/strategy |
| ObjectName changed after enabling AOP | Naming based on proxy runtime class | Use a stable logical ObjectName |
| MBean appears under two names | Two exporters or two export paths | Establish a single owner |
| `InstanceAlreadyExistsException` | Duplicate canonical ObjectName registration | Check ownership and policy |
| Name differs in letter case | Different input key/value | Normalize at naming source |
| Invalid name | Unquoted delimiters | Use `ObjectName.quote` or appropriate constructor |
| Wrong name after restart | Dynamic ID, different profile/config | Use a stable logical identifier |
| Remote MBean not visible | Connector serves another server or wrong JVM | Check endpoint and target server |

## 21. Tests to Prevent Naming Regressions

A test suite should include:

1. **Strategy unit test:** passing the same logical bean/key must produce the same `ObjectName`.
2. **Canonical equality test:** swapping key order remains equivalent.
3. **Special characters test:** names with commas, equals signs, and wildcards are handled properly.
4. **Exporter integration test:** ApplicationContext registers the exact ObjectName into the right server.
5. **MBeanInfo test:** verify the MBean has the corresponding attributes/operations.
6. **AOP proxy test:** enable AOP and verify the ObjectName does not change.
7. **Multi-context test:** two contexts do not unintentionally register the same ObjectName.
8. **Lifecycle test:** when closing the context, MBeans owned by the exporter are unregistered.
9. **Remote target test:** if using remote JMX, verify the endpoint along with the ObjectName and instance identity.

Tests using a dedicated MBeanServer are generally more reliable than a shared platform server in parallel JUnit runs.

## 22. Hands-on Exercises

1. Create two ObjectName strings with different key orderings and use `ObjectName.equals()` to explain why they represent the same MBean identity.
2. Configure a Spring exporter with an explicit key and verify `isRegistered` after context initialization.
3. Change `KeyNamingStrategy` or change the bean key and observe the resulting ObjectName.
4. Use `@ManagedResource(objectName=...)` with an annotation exporter; compare it against an exporter using an explicit beans map.
5. Enable a Spring AOP proxy on a service; observe the runtime class and compare class-based naming with explicit naming.
6. Create two exporters registering the same ObjectName on a test server; diagnose the duplicate name error.
7. Write a test that initializes the context twice to verify the name remains stable across restarts.
8. Point a JMX client at the wrong endpoint and trace the cause of `InstanceNotFoundException`.

## 23. Self-Check Questions

- Must a Spring bean name be an ObjectName?
- Do two ObjectNames differing only in key property order have different identities?
- Why must you verify the MBeanServer before concluding the naming strategy is wrong?
- Is `@ManagedResource(objectName=...)` always used by every `MBeanExporter`?
- How can a Spring proxy affect names generated from `bean.getClass()`?
- If a bean appears under two ObjectNames, which configurations should you inspect?
- Why is a stable ObjectName important for dashboards and alerts?
- When remote JMX cannot find an MBean, which endpoints must be verified?

**Key Takeaway:** When an ObjectName differs from expected, do not immediately change configuration. Distinguish display representation from true identity using `ObjectName.equals()`, verify the **right MBeanServer**, query the actual list of names, and trace back through the exporter, naming strategy, annotations, bean key, and proxy. Keep ObjectNames tied to stable logical identifiers and protect the naming contract with integration tests.