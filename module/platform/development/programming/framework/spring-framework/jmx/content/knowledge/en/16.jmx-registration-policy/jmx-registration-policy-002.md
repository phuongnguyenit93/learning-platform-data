# RegistrationPolicy.FAIL_ON_EXISTING in Spring Framework JMX

## Objectives

After this lesson, you will be able to accurately explain the meaning of `RegistrationPolicy.FAIL_ON_EXISTING` when Spring exports MBeans over JMX, know when it is applied, how to configure it in `MBeanExporter`, how to distinguish it from `IGNORE_EXISTING` and `REPLACE_EXISTING`, and how to write tests proving that a duplicate `ObjectName` case does not silently overwrite an existing MBean.

This lesson belongs to the **Spring Framework JMX → Registration policy** topic. The focus is the registration policy, not choosing interfaces or setting up remote JMX connectors.

## 1. The Problem: An ObjectName Can Only Be Registered Once per MBeanServer

JMX identifies each MBean with `javax.management.ObjectName`, for example:

```text
com.example.payment:type=Queue,name=Primary
```

Within **one `MBeanServer`**, two MBeans cannot be registered simultaneously under the same `ObjectName`.

A Spring application can export MBeans in multiple ways: declaring a `beans` map on `MBeanExporter`, enabling annotation-driven export via `@EnableMBeanExport`, or using `<context:mbean-export/>` in XML. If two exporters register the same name, or one exporter tries to register a name already used by another component, a conflict occurs.

```text
MBeanServer
  |
  |-- com.example.payment:type=Queue,name=Primary
  |          ^
  |          | already registered
  |
Exporter B
  |
  +-- attempts to register the same ObjectName
             |
             v
      Registration policy decides how to handle it
```

In plain Java JMX, a duplicate registration call normally throws `InstanceAlreadyExistsException`. Spring introduces `RegistrationPolicy` so configuration authors can choose the behavior when encountering this situation.

## 2. What Does FAIL_ON_EXISTING Mean?

`org.springframework.jmx.support.RegistrationPolicy.FAIL_ON_EXISTING` means:

> When Spring attempts to register an MBean under an `ObjectName` that already exists in the target `MBeanServer`, **do not ignore it and do not replace the old MBean**; instead, report a registration error.

This is **fail-fast** behavior: the conflict is surfaced explicitly at export time rather than quietly hiding duplicate configuration.

Expected example:

```text
Initially:
  MBeanServer has "com.example.payment:type=Queue,name=Primary"

Spring MBeanExporter:
  wants to register another bean with the same name
  registrationPolicy = FAIL_ON_EXISTING

Result:
  The second registration fails
  The existing MBean remains intact
  Spring throws an error; context initialization may fail
```

Note: `FAIL_ON_EXISTING` handles **name collisions in the MBeanServer**. It does not validate business logic, access permissions, metadata quality, or uniqueness across different JVMs.

## 3. API and Policy Options

The `RegistrationPolicy` enum in Spring JMX has three common options:

| Policy | When ObjectName Already Exists | Primary Consequence |
| --- | --- | --- |
| `FAIL_ON_EXISTING` | Fails with an error | Detects conflicts immediately, without attempting to replace the existing MBean |
| `IGNORE_EXISTING` | Skips the new registration | The old MBean continues serving; the new bean may not be exported |
| `REPLACE_EXISTING` | Replaces the old MBean via Spring's registration mechanism | Requires understanding ownership; may affect other components |

Configuration example:

```java
import org.springframework.jmx.support.RegistrationPolicy;

exporter.setRegistrationPolicy(
    RegistrationPolicy.FAIL_ON_EXISTING
);
```

For a typical `MBeanExporter`, failing when a name already exists is the default behavior; declaring it explicitly helps maintainers understand the intent and prevents surprises when other configurations change.

Do not pick `IGNORE_EXISTING` or `REPLACE_EXISTING` just to “get the application to start” before identifying why two parties share the same ObjectName.

## 4. Standard MBean Example for Practice

Create a JMX interface following the Standard MBean convention:

```java
package com.example.payment.jmx;

public interface PaymentQueueMonitorMBean {
    int getPendingCount();
    boolean isPaused();
}
```

Implementation:

```java
package com.example.payment.jmx;

public final class PaymentQueueMonitor
        implements PaymentQueueMonitorMBean {

    private final int pendingCount;
    private final boolean paused;

    public PaymentQueueMonitor(int pendingCount, boolean paused) {
        this.pendingCount = pendingCount;
        this.paused = paused;
    }

    @Override
    public int getPendingCount() {
        return pendingCount;
    }

    @Override
    public boolean isPaused() {
        return paused;
    }
}
```

A valid `PaymentQueueMonitor` can be registered as a Standard MBean under the name:

```text
com.example.payment:type=Queue,name=Primary
```

If you create a second instance and try to register it under the exact same name, the JMX server detects the collision regardless of whether the two objects have the same class or the same attribute values.

**Uniqueness depends on the ObjectName, not on object identity or class.**

## 5. Configuring MBeanExporter with FAIL_ON_EXISTING

Java configuration example for Spring Framework:

```java
package com.example.payment.config;

import com.example.payment.jmx.PaymentQueueMonitor;
import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

@Configuration
public class PaymentJmxConfig {

    @Bean
    public PaymentQueueMonitor paymentQueueMonitor() {
        return new PaymentQueueMonitor(15, false);
    }

    @Bean
    public MBeanServer platformMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter paymentMBeanExporter(
            PaymentQueueMonitor paymentQueueMonitor,
            MBeanServer platformMBeanServer) {

        MBeanExporter exporter = new MBeanExporter();

        exporter.setServer(platformMBeanServer);
        exporter.setBeans(Map.of(
            "com.example.payment:type=Queue,name=Primary",
            paymentQueueMonitor
        ));
        exporter.setRegistrationPolicy(
            RegistrationPolicy.FAIL_ON_EXISTING
        );

        return exporter;
    }
}
```

Key parts:

1. `setServer`: selects the MBeanServer to register into.
2. `setBeans`: specifies the bean and its JMX name.
3. `setRegistrationPolicy`: defines how to react when the name already exists.
4. When ApplicationContext initializes, `MBeanExporter` registers the MBean following the Spring lifecycle.
5. If the ObjectName already exists, the error may be wrapped by Spring in a context initialization exception; the root cause is typically related to `InstanceAlreadyExistsException`.

If the application already has an `MBeanServer` configured elsewhere, use that server instead of creating an arbitrary new one. Also, do not assume every Spring bean can be registered as a Standard MBean without an appropriate interface or assembler.

## 6. XML Configuration

For Spring Framework applications using XML:

```xml
<bean id="paymentQueueMonitor"
      class="com.example.payment.jmx.PaymentQueueMonitor">
    <constructor-arg value="15"/>
    <constructor-arg value="false"/>
</bean>

<bean id="paymentExporter"
      class="org.springframework.jmx.export.MBeanExporter">
    <property name="beans">
        <map>
            <entry key="com.example.payment:type=Queue,name=Primary"
                   value-ref="paymentQueueMonitor"/>
        </map>
    </property>
    <property name="registrationPolicy" value="FAIL_ON_EXISTING"/>
</bean>
```

The `registrationPolicy` property uses the Spring enum. Use an XML schema/Spring version compatible with your project; the example above shows how to configure the `MBeanExporter` bean directly.

If the application uses:

```xml
<context:mbean-export/>
```

this is an annotation-driven export mechanism, distinct from manually configuring an exporter. Registration policy options may exist on the XML namespace element depending on the schema version; verify the actual configuration and avoid instantiating multiple exporters registering the same name.

**Do not enable two export paths just because both are available in the codebase.** Each ObjectName should have a clear owner.

## 7. How Does FAIL_ON_EXISTING Differ from Standard Java Errors?

Java JMX defines a rule: an `ObjectName` currently in use cannot have a second object registered under it without an appropriate unregistration step. With `MBeanServer.registerMBean`, the typical symptom is:

```text
javax.management.InstanceAlreadyExistsException
```

In Spring, the error may be wrapped via `MBeanExportException`, `BeanCreationException`, or other exception classes depending on initialization timing and how the exporter is configured.

Therefore, when analyzing logs:

- Read the **root cause** rather than only the outermost exception line.
- Find the specific colliding `ObjectName`.
- Identify which MBean was registered first.
- Check which exporter performed the second registration.
- Inspect the lifecycle: is an old bean still alive because a previous context was not closed?

An error caused by a duplicate ObjectName differs from `MalformedObjectNameException` (invalid name syntax) or `NotCompliantMBeanException` (object is not a valid MBean).

## 8. Testing Name Collisions with Plain Java MBeanServer

Before testing the Spring policy, you can verify the underlying JMX behavior with an isolated MBeanServer:

```java
import static org.junit.jupiter.api.Assertions.*;

import javax.management.InstanceAlreadyExistsException;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;

class DuplicateObjectNameTest {

    @Test
    void rejectsSecondRegistration() throws Exception {
        MBeanServer server =
            MBeanServerFactory.createMBeanServer("test.management");

        ObjectName name = new ObjectName(
            "com.example.payment:type=Queue,name=Primary"
        );

        try {
            server.registerMBean(
                new PaymentQueueMonitor(10, false), name
            );

            assertTrue(server.isRegistered(name));

            assertThrows(
                InstanceAlreadyExistsException.class,
                () -> server.registerMBean(
                    new PaymentQueueMonitor(99, true), name
                )
            );

            // Duplicate registration does not replace the initial MBean value.
            assertEquals(
                10,
                server.getAttribute(name, "PendingCount")
            );
        } finally {
            if (server.isRegistered(name)) {
                server.unregisterMBean(name);
            }
            MBeanServerFactory.releaseMBeanServer(server);
        }
    }
}
```

This test verifies the core JMX rule: an existing name causes the new registration to fail and the old object is not replaced.

However, **this is not yet an integration test of the Spring policy**. To prove `RegistrationPolicy.FAIL_ON_EXISTING`, you must run a Spring `MBeanExporter` with that policy when the server already holds an MBean with the same name.

## 9. Integration Test Proving FAIL_ON_EXISTING

Use a dedicated test server and pre-register an MBean. Then create a Spring context with an exporter trying to register a second MBean with the same name.

An illustrative test pattern:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.support.GenericApplicationContext;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

class FailOnExistingExporterTest {
    @Test
    void rejectsNameOwnedByAnotherComponent() throws Exception {
        MBeanServer server =
            MBeanServerFactory.createMBeanServer("test.management");
        ObjectName name = new ObjectName(
            "com.example.payment:type=Queue,name=Primary"
        );

        try {
            // Component A registers first.
            server.registerMBean(
                new PaymentQueueMonitor(10, false), name
            );

            GenericApplicationContext context =
                    new GenericApplicationContext();

            context.registerBean("exporter", MBeanExporter.class, () -> {
                MBeanExporter exporter = new MBeanExporter();
                exporter.setServer(server);
                exporter.setRegistrationPolicy(
                    RegistrationPolicy.FAIL_ON_EXISTING
                );
                exporter.setBeans(Map.of(
                    name.toString(),
                    new PaymentQueueMonitor(99, true)
                ));
                return exporter;
            });

            try {
                // Conflict error occurs during refresh/export.
                assertThrows(
                    RuntimeException.class,
                    context::refresh
                );

                // The first registered object remains the owner of the name.
                assertTrue(server.isRegistered(name));
                assertEquals(
                    10,
                    server.getAttribute(name, "PendingCount")
                );
            } finally {
                context.close();
            }
        } finally {
            if (server.isRegistered(name)) {
                server.unregisterMBean(name);
            }
            MBeanServerFactory.releaseMBeanServer(server);
        }
    }
}
```

In a real project, check the root cause of the exception to confirm the failure is due to a duplicate name rather than an unrelated error in `ApplicationContext`. Tests should not depend on an exact message string because wrapper exceptions and wording can vary across Spring versions.

Additionally, the test above uses an isolated `MBeanServer` so it does not affect system MBeans or other tests in the same JVM.

## 10. When Should You Choose FAIL_ON_EXISTING?

**Appropriate when:**

1. Each JMX ObjectName has a clear owner.
2. A duplicate name indicates a misconfiguration that must be fixed immediately.
3. You want to prevent an exporter from accidentally taking over management of another component's MBean.
4. Monitoring depends on a stable ObjectName contract and cannot accept silently keeping the wrong object.
5. The system startup process can detect and handle configuration errors before serving traffic.

For example, `PaymentService` has exactly one MBean `type=Queue,name=Primary` in the JVM. If two exporters export the same name, that is usually a wiring bug. Fail-fast helps surface the issue.

**Consider carefully when:**

- Multiple application contexts intentionally share the platform MBeanServer.
- An application redeploys within one JVM while the old context has not yet torn down.
- Another framework/instrumentation already owns the name and you only want to reuse its data.
- You need to hot-swap an MBean and have a well-designed ownership/handover mechanism.

In such cases, analyze lifecycle and ownership before choosing ignore or replace.

## 11. Distinguishing IGNORE_EXISTING and REPLACE_EXISTING

### IGNORE_EXISTING

If the server already has:

```text
com.example.payment:type=Queue,name=Primary -> monitor A
```

and the exporter wants to register monitor B under the same name, `IGNORE_EXISTING` skips registering B. JMX clients still see A.

Risk: the application may start up while operators assume they are reading B. If MBean A belongs to an old context, the data may be stale or fail to reflect the current application state.

### REPLACE_EXISTING

The exporter attempts to replace the existing MBean with the new MBean. This can fit when a component genuinely manages replacement lifecycles, but carries risks:

- The old MBean may belong to another subsystem.
- Client listeners may be affected by the unregister/register sequence.
- During replacement, clients may experience disruption.
- When the new context closes, you must understand which MBean will be unregistered.

`FAIL_ON_EXISTING` avoids these behaviors by reporting the conflict and letting administrators choose the proper fix.

## 12. Common Causes of Conflicts in Spring

### Two Independent MBeanExporters

One Java config declares a manual `MBeanExporter`, while annotation configuration enables another exporter. If both export the same bean under the same ObjectName, a collision is highly likely.

### Parent/Child ApplicationContexts

In web or modular applications, parent and child contexts may share the platform MBeanServer. If both export the same name, a conflict occurs even though the beans belong to different contexts.

### Duplicate Explicit Mapping

Two modules both use:

```text
com.example.payment:type=Queue,name=Primary
```

due to copied configuration or missing naming conventions. Either adjust the logical name or designate one owner.

### Varying / Uncanonicalized Names

The strings:

```text
com.example.payment:type=Queue,name=Primary
com.example.payment:name=Primary,type=Queue
```

are the same ObjectName even though the key order differs. Therefore, a simple string check can miss collisions; use `ObjectName.equals()` or `getCanonicalName()`.

### Old Context Not Unregistered

A context that is not closed properly can leave MBeans behind. When a new context re-registers the name, `FAIL_ON_EXISTING` will catch it. Fix the lifecycle/cleanup instead of appending a random UUID to the ObjectName.

## 13. Diagnosing Conflicts Using MBeanServer

If the logs report a duplicate, check the registered name:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.MBeanInfo;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.payment:type=Queue,name=Primary"
);

System.out.println("Registered: " + server.isRegistered(name));

if (server.isRegistered(name)) {
    MBeanInfo info = server.getMBeanInfo(name);
    System.out.println("MBean class: " + info.getClassName());
    System.out.println("ObjectName: " + name.getCanonicalName());
}
```

Note that `MBeanInfo.getClassName()` reveals the class/metadata exposed by JMX, **not conclusive proof of which Spring ApplicationContext or exporter registered it**. To determine the owner, combine startup logs, bean definitions, naming configuration, and each module's lifecycle.

If the exporter uses a custom MBeanServer, you must query that server rather than defaulting to the platform server.

## 14. Verifying the Unregister Lifecycle

An exporter that owns an MBean will normally unregister the MBeans it manages when the ApplicationContext closes cleanly.

In tests:

```java
ObjectName name = new ObjectName(
    "com.example.payment:type=Queue,name=Primary"
);

try (var context = new AnnotationConfigApplicationContext(
        PaymentJmxConfig.class)) {
    assertTrue(
        ManagementFactory.getPlatformMBeanServer()
            .isRegistered(name)
    );
}

assertFalse(
    ManagementFactory.getPlatformMBeanServer()
        .isRegistered(name)
);
```

This is an idealized pattern: the test must run in an environment where no other owner is using the name. If the test uses a shared platform MBeanServer, do not manually unregister MBeans owned by another application.

With `FAIL_ON_EXISTING`, the new exporter's registration **does not succeed** if the name already exists, so it must not treat the old MBean as an object it owns. Cleanup must respect the actual owner, and you must not delete another component's MBean just to let tests proceed.

## 15. Naming Rules to Avoid FAIL_ON_EXISTING

An ObjectName should be both unique and meaningful:

```text
com.example.payment:type=Queue,name=Primary
com.example.payment:type=Queue,name=Refund
com.example.payment:type=WorkerPool,name=Retry
```

Design key properties by resource:

- `domain`: module/service namespace.
- `type`: component type, such as `Queue`, `Cache`, `WorkerPool`.
- `name`: logical name of the instance/resource within the JVM.
- `component`, `tenant`, or `region`: add only when legitimate differentiation is needed.

There is no need to include a PID or per-restart UUID in the ObjectName if the logical resource has not changed. Stability helps operational scripts and dashboards locate the right MBean.

If multiple replicas run in separate JVMs, they **can use the same ObjectName** because each JVM has its own MBeanServer. Collisions checked by `FAIL_ON_EXISTING` only happen within the target server of the registration.

## 16. Handling Conflicts in Production Environments

A safe resolution workflow:

1. Record the ObjectName and target MBeanServer from the error.
2. Identify the component that registered first and the exporter that failed.
3. Check whether the two registrations represent **the same resource** or **two different resources**.
4. If the same resource: keep one exporter/owner and remove the duplicate registration path.
5. If different resources: choose distinct ObjectNames following a logical convention.
6. If an old context is still alive: fix teardown/lifecycle, do not delete MBeans arbitrarily.
7. If intentional replacement is needed: redesign ownership and handover procedures, and consider `REPLACE_EXISTING`.
8. Re-verify `isRegistered`, `getMBeanInfo`, and attributes from a JMX client after the change.

Do not call `server.unregisterMBean(name)` during application startup as a “generic workaround” for duplicate name errors: that command can remove an MBean currently serving clients of another module.

## 17. Hands-On Exercise

1. Create `PaymentQueueMonitorMBean` and two instances with different `PendingCount` values. Register them under the same ObjectName in an isolated MBeanServer and inspect the exception.
2. Configure Spring's `MBeanExporter` with `FAIL_ON_EXISTING`, pre-create an MBean with the same name in the server, and confirm the new context fails to export.
3. Try `IGNORE_EXISTING` in a test environment and compare the attribute visible to clients.
4. Try `REPLACE_EXISTING` in a test environment to observe the impact on the registered object; do not use it on a shared server without ownership.
5. Create two ObjectNames differing only in key property order. Compare `equals()` and observe the registration collision.
6. Split the configuration into two Spring contexts using the same platform server and a fixed name. Diagnose which exporter causes the conflict.
7. Write an integration test checking the duplicate `ObjectName` error and asserting that the old MBean is not replaced.

## 18. Self-Check Questions

- What does `FAIL_ON_EXISTING` do when an ObjectName already exists?
- How does this policy differ from `IGNORE_EXISTING` and `REPLACE_EXISTING`?
- In JMX, is an ObjectName unique across the entire cluster or within each MBeanServer?
- Why is `MBeanInfo.getClassName()` insufficient to pinpoint the exact exporter that owns an MBean?
- When two beans genuinely represent two different resources, how should the naming strategy be fixed?
- Why shouldn't you append a random UUID just to dodge a duplicate name error?
- What should you check if an application has both `@EnableMBeanExport` and a manually declared `MBeanExporter`?
- How do you prove in an integration test that the policy does not replace the old MBean?

**Key takeaway:** `RegistrationPolicy.FAIL_ON_EXISTING` protects MBean registration clarity: **if the ObjectName already exists, the new registration fails**, rather than being silently ignored or overwritten. This is usually the safest choice when a duplicate name indicates a configuration error. Manage stable ObjectNames, track the owner of each MBean, and test collision behavior against an isolated MBeanServer.