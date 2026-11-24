# Selecting an MBeanServer Using the server Property in Spring Framework JMX

## Objectives

This lesson explains the role of the `server` property in Spring `MBeanExporter`, how to select a custom `MBeanServer`, and how to verify that managed beans are actually registered in the right registry.

You will learn how to use Java configuration, XML, and `@EnableMBeanExport`, distinguish an MBeanServer from a JMX connector, manage lifecycles, and avoid ObjectName collisions across multiple Spring contexts.

## 1. MBeanServer is the MBean Registry

JMX provides MBeanServer to register and manage MBeans. Each registration uses an ObjectName:

```java
ObjectName name = new ObjectName("learning.jmx:type=CacheMonitor,name=Products");
server.registerMBean(cacheMonitor, name);
```

Clients locate MBeans in the server using `isRegistered`, `getAttribute`, `invoke`, and `queryNames`.

A JVM can have multiple MBeanServers. An MBean registered in server A does not automatically appear in server B. An ObjectName identifies a registration only within the scope of a single MBeanServer.

Typical platform MBeanServer:

```java
MBeanServer platform = ManagementFactory.getPlatformMBeanServer();
```

However, Spring can export to another server if configured.

## 2. The server Property of MBeanExporter

`MBeanExporter` is the Spring component that exports beans as JMX MBeans. The `server` property determines where they are registered:

```java
MBeanExporter exporter = new MBeanExporter();
exporter.setServer(chosenMBeanServer);
```

In XML:

```xml
<property name="server" ref="managementMBeanServer"/>
```

This property is a reference to an MBeanServer object, **not a hostname, port, JMX URL, or ObjectName**.

Diagram:

```text
Spring ApplicationContext
  |
  +-- CacheMonitor
  +-- MBeanExporter
         |
         | server = customMBeanServer
         v
     Custom MBeanServer
         |
         +-- learning.jmx:type=CacheMonitor,name=Products
```

Three decisions to keep separate:

| Decision | Configuration | Meaning |
|---|---|---|
| Which bean to export? | `setBeans` or autodetection | Select resource |
| Which name to register? | ObjectName or naming strategy | Select MBean name |
| Where to register? | `server` / `setServer` | Select MBeanServer |

A JMX connector is the layer that connects clients to the server and must be configured separately if used for access from another JVM.

## 3. When Should You Use a Custom MBeanServer?

Typical use cases:

- Integration tests that need isolation from the platform server and other tests.
- A single JVM running multiple ApplicationContexts that need separate registries.
- A framework or container providing a specific MBeanServer.
- A module that has its own management needs or its own connector.
- Needing to clearly verify the boundary between sets of MBeans.

Note that a separate server can cause MBeans not to appear in tools viewing the platform MBeanServer. This is not necessarily a registration error.

If the goal is to observe them alongside platform MBeans using standard tools, using the platform MBeanServer is usually simpler.

## 4. Creating a Standard MBean

File CacheMonitorMBean.java:

```java
package example.jmx;

public interface CacheMonitorMBean {
    int getEntryCount();
    void clear();
}
```

File CacheMonitor.java:

```java
package example.jmx;

import java.util.concurrent.atomic.AtomicInteger;

public class CacheMonitor implements CacheMonitorMBean {
    private final AtomicInteger count = new AtomicInteger(12);

    @Override
    public int getEntryCount() {
        return count.get();
    }

    @Override
    public void clear() {
        count.set(0);
    }
}
```

The CacheMonitor class and CacheMonitorMBean interface follow the Standard MBean convention. The `EntryCount` attribute and `clear` operation can be accessed by a JMX client after the bean is registered.

## 5. Java Configuration: Selecting a Custom MBeanServer

```java
package example.jmx;

import java.util.Map;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class CustomJmxConfiguration {

    @Bean(name = "managementMBeanServer")
    public MBeanServer managementMBeanServer() {
        return MBeanServerFactory.createMBeanServer("learning.management");
    }

    @Bean
    public CacheMonitor cacheMonitor() {
        return new CacheMonitor();
    }

    @Bean
    public MBeanExporter mbeanExporter(
            @Qualifier("managementMBeanServer") MBeanServer server,
            CacheMonitor monitor) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(server);
        exporter.setBeans(Map.of(
                "learning.jmx:type=CacheMonitor,name=Products",
                monitor
        ));
        return exporter;
    }
}
```

Here, the exporter receives the exact managementMBeanServer bean. Simply creating an MBeanServer without passing it to the exporter will not guarantee the exporter uses that server.

`Map.of` requires Java 9 or later; on Java 8, a regular `Map` can be used.

## 6. Verifying the Correct Server

```java
package example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class InspectServer {
    public static void main(String[] args) throws Exception {
        ObjectName name = new ObjectName(
            "learning.jmx:type=CacheMonitor,name=Products"
        );

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                    CustomJmxConfiguration.class)) {

            MBeanServer custom = context.getBean(
                "managementMBeanServer", MBeanServer.class
            );
            MBeanServer platform =
                ManagementFactory.getPlatformMBeanServer();

            System.out.println("Custom: " + custom.isRegistered(name));
            System.out.println("Platform: " + platform.isRegistered(name));
            System.out.println(
                "Entries: " + custom.getAttribute(name, "EntryCount")
            );
        }
    }
}
```

In an isolated environment, with no registration of the same name on the platform server, expected output:

```text
Custom: true
Platform: false
Entries: 12
```

If the platform server already has an independent MBean with the same ObjectName, the Platform line may be true. What needs to be confirmed is that the exporter is registering into the **custom server passed via setServer**.

## 7. XML Configuration

Spring XML supports MBeanServerFactoryBean and the server property:

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
         http://www.springframework.org/schema/beans
         https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="managementMBeanServer"
          class="org.springframework.jmx.support.MBeanServerFactoryBean">
        <property name="defaultDomain" value="learning.management"/>
        <property name="locateExistingServerIfPossible" value="false"/>
    </bean>

    <bean id="cacheMonitor" class="example.jmx.CacheMonitor"/>

    <bean id="mbeanExporter"
          class="org.springframework.jmx.export.MBeanExporter">

        <property name="server" ref="managementMBeanServer"/>

        <property name="beans">
            <map>
                <entry key="learning.jmx:type=CacheMonitor,name=Products"
                       value-ref="cacheMonitor"/>
            </map>
        </property>
    </bean>
</beans>
```

`ref="managementMBeanServer"` points to a Spring bean providing an MBeanServer. It is not a remote endpoint.

MBeanServerFactoryBean has properties related to locating or creating a server. In a multi-server environment, configure it consistently to avoid accidentally using a different registry than intended.

## 8. @EnableMBeanExport with the server Attribute

When using annotation-based JMX, Spring allows selecting an MBeanServer bean by name:

```java
package example.jmx;

import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport(server = "managementMBeanServer")
public class AnnotationJmxConfiguration {

    @Bean(name = "managementMBeanServer")
    public MBeanServer managementMBeanServer() {
        return MBeanServerFactory.createMBeanServer(
            "learning.management"
        );
    }

    @Bean
    public CacheManagement cacheManagement() {
        return new CacheManagement();
    }
}
```

Managed resource:

```java
package example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "learning.jmx:type=Cache,name=Products"
)
public class CacheManagement {

    @ManagedAttribute
    public int getEntryCount() {
        return 12;
    }
}
```

The `server` attribute of `@EnableMBeanExport` accepts an MBeanServer bean name, not a hostname or ObjectName. `@ManagedResource` defines the MBean and its name; the exporter is activated by the annotation configuration.

Only one appropriate exporter should be enabled for the same managed resource. Creating an additional manual MBeanExporter can cause duplicate registrations.

## 9. When server Is Not Explicitly Set

MBeanExporter has a mechanism for detecting a suitable MBeanServer based on configuration and environment, though details may depend on the Spring version and existing MBeanServers.

When the JVM has multiple servers, do not assume the exporter chose the server you want. Use explicit configuration:

```java
exporter.setServer(chosenServer);
```

Or:

```java
@EnableMBeanExport(server = "chosenServerBean")
```

Verify the MBeanServer actually being used by the exporter, not just an annotated class.

## 10. MBeanServerFactory and MBeanServerFactoryBean

Java API:

```java
MBeanServer server =
    MBeanServerFactory.createMBeanServer("learning.management");
```

Spring FactoryBean:

```xml
<bean id="managementMBeanServer"
      class="org.springframework.jmx.support.MBeanServerFactoryBean"/>
```

They both serve to provide an MBeanServer, but lifecycle and lookup are governed by their respective configurations.

A JVM can create two MBeanServers:

```java
MBeanServer a = MBeanServerFactory.createMBeanServer("learning.a");
MBeanServer b = MBeanServerFactory.createMBeanServer("learning.b");
```

After registering the MBean in a:

```java
a.isRegistered(name); // true
b.isRegistered(name); // false
```

Registries do not synchronize with one another.

## 11. JConsole and Remote JMX Connector

JConsole typically connects to a JVM or a specific JMX connector. It sees the registry provided by that connected connector or local management endpoint.

If the exporter uses a custom MBeanServer while JConsole is viewing the platform server, the custom MBean may not appear. This does not prove the exporter failed.

Compare:

```java
custom.isRegistered(name);
ManagementFactory.getPlatformMBeanServer().isRegistered(name);
```

Creating an MBeanServer does not automatically open a network endpoint. If you want remote JMX clients to access the custom server, a connector attached to that specific server is required.

Conceptual example:

```java
JMXConnectorServer connector =
    JMXConnectorServerFactory.newJMXConnectorServer(
        serviceUrl,
        connectorEnvironment,
        customServer
    );
```

A real-world program must also configure serviceUrl, transport, authentication, TLS, firewall, access permissions, and shutdown lifecycle. Do not expose unprotected remote JMX over a shared network.

## 12. Multiple Spring ApplicationContexts

A JVM can have multiple Spring contexts:

```text
JVM
  +-- Parent context
  +-- Child context A
  +-- Child context B
```

If two exporters register the same ObjectName on a shared server, InstanceAlreadyExistsException may occur.

Two approaches:

**Shared server:** use ObjectNames that clearly distinguish modules.

```text
learning.jmx:type=Cache,module=Billing,name=Primary
learning.jmx:type=Cache,module=Shipping,name=Primary
```

**Separate servers:** each exporter points to its corresponding MBeanServer.

Separate servers increase isolation but also require clients to know which registry/connector to use. Do not use multiple servers merely to mask an unclear ObjectName design.

## 13. RegistrationPolicy and ObjectName Collisions

Spring MBeanExporter has the following policies:

| Policy | Behavior |
|---|---|
| FAIL_ON_EXISTING | Throws an error when the ObjectName already exists |
| IGNORE_EXISTING | Ignores the new registration if the name already exists |
| REPLACE_EXISTING | Replaces the existing registration according to policy |

Example:

```java
exporter.setRegistrationPolicy(
    RegistrationPolicy.FAIL_ON_EXISTING
);
```

In a multi-module environment, FAIL_ON_EXISTING helps detect when two components own the same name.

Do not use REPLACE_EXISTING indiscriminately: it can overwrite a registration of an active context. When encountering a collision, first determine which server, which ObjectName, which exporter, and which component should actually own the registration.

## 14. Export and Unregister Lifecycle

When MBeanExporter is managed by Spring, it registers MBeans during context initialization and cleans up registrations within its scope when the context closes.

```text
ApplicationContext refresh
    -> MBeanExporter initialization
    -> register MBean into chosenServer
    -> ApplicationContext close
    -> MBeanExporter unregister MBean
```

The MBeanServer can continue to exist after the MBean is unregistered. Unexporting does not mean destroying the entire server or closing a JMX connector managed by another component.

Check:

```java
boolean before = chosenServer.isRegistered(name);
context.close();
boolean after = chosenServer.isRegistered(name);
```

If the exporter has normal ownership and cleanup:

```text
before = true
after = false
```

If the application registers MBeans manually outside the exporter, that code itself must manage unregistration.

### Releasing a Custom Server

When you own a server created via MBeanServerFactory and there are no remaining consumers, you may consider:

```java
MBeanServerFactory.releaseMBeanServer(chosenServer);
```

Do not release the platform MBeanServer or a shared server not owned by the test or application.

## 15. Integration Test Verifying the Target Server

JUnit Jupiter example:

```java
package example.jmx;

import static org.junit.jupiter.api.Assertions.*;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class CustomServerExportTest {

    @Test
    void registersIntoChosenServer() throws Exception {
        ObjectName name = new ObjectName(
            "learning.jmx:type=CacheMonitor,name=Products"
        );

        MBeanServer platform =
            ManagementFactory.getPlatformMBeanServer();

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                    CustomJmxConfiguration.class)) {

            MBeanServer chosen = context.getBean(
                "managementMBeanServer", MBeanServer.class
            );

            assertTrue(chosen.isRegistered(name));
            assertEquals(
                12,
                chosen.getAttribute(name, "EntryCount")
            );

            // Test isolation requirement: no registration
            // with the same name on the platform server.
            assertFalse(platform.isRegistered(name));
        }
    }
}
```

A lifecycle test:

```java
@Test
void unregistersAfterContextClose() throws Exception {
    AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext(
            CustomJmxConfiguration.class
        );

    MBeanServer chosen = context.getBean(
        "managementMBeanServer", MBeanServer.class
    );

    ObjectName name = new ObjectName(
        "learning.jmx:type=CacheMonitor,name=Products"
    );

    try {
        assertTrue(chosen.isRegistered(name));
    } finally {
        context.close();
    }

    assertFalse(chosen.isRegistered(name));
}
```

Must be run in an appropriate test environment. If multiple tests run in parallel, do not use a shared platform server and a shared ObjectName in a way that causes collisions.

## 16. Common Troubleshooting Table

| Symptom | Possible Cause | Resolution |
|---|---|---|
| JConsole does not see the MBean | Registered in custom server, client viewing platform server | Verify server identity and connector |
| InstanceNotFoundException | Incorrect ObjectName or server | Check isRegistered on each server |
| InstanceAlreadyExistsException | Two MBeans registered with the same name in one server | Determine ownership and policy |
| MBean registered in wrong server | Missing setServer or incorrect wiring | Use explicit configuration and @Qualifier |
| MBeanServer bean exists but is not used | Server was not passed to the exporter | Use server property, setServer, or @EnableMBeanExport(server=...) |
| Cannot access from another JVM | No connector attached to the custom server | Configure remote connector and security |
| Valid ObjectName but operation missing | Assembler/metadata did not export the operation | Inspect getMBeanInfo |
| Context closed but MBean remains | Registration performed by another exporter or manual code | Check ownership and cleanup |
| Test overwrites another MBean | Shared server and REPLACE_EXISTING | Separate servers or use distinct names |

## 17. Diagnostic Procedure

1. Identify the exporter and its current server configuration.
2. Identify the actual MBeanServer bean, avoiding confusion when multiple beans of the same type exist.
3. Verify the exact ObjectName via chosenServer.isRegistered(name).
4. Use chosenServer.queryNames(...) if you need to discover actual registered names.
5. Use chosenServer.getMBeanInfo(name) to inspect attributes/operations.
6. If clients do not see the MBean, determine which server the connector is serving.
7. When collisions occur, check all exporters/contexts registering the same name.
8. When the context closes, verify the exporter's MBean is unregistered.

## 18. Practice Exercises

**Exercise 1 — Two servers:** Create A and B via MBeanServerFactory. Register an MBean in A and prove B does not see that ObjectName.

**Exercise 2 — Change target:** Change exporter.setServer from the platform server to a custom server, keeping the same ObjectName, and compare isRegistered on both.

**Exercise 3 — XML:** Write an MBeanExporter with a server property pointing to managementMBeanServer. Explain why ref is not a hostname.

**Exercise 4 — Multiple contexts:** Two contexts want to export CacheMonitor with the same name. Compare using distinct ObjectNames in one server versus using two independent servers.

**Exercise 5 — Cleanup:** Start a context, verify registration; close the context, verify unregistration; explain releasing the server if it is a test-owned resource.

## 19. Key Takeaways

- The **server** property determines which MBeanServer MBeanExporter uses.
- An ObjectName only identifies an MBean within the selected registry.
- One JVM can contain multiple MBeanServers that do not share registrations.
- Java configuration uses setServer; XML uses the server property; @EnableMBeanExport has a server attribute to select the Spring bean providing the MBeanServer.
- An MBeanServer bean reference differs from a JMX connector URL.
- A custom server does not automatically appear in JConsole or remote clients without a corresponding connection path.
- Diagnose in the right order: exporter, server, ObjectName, MBeanInfo, connector, and lifecycle.
- With multiple ApplicationContexts or integration tests, server selection and ownership should be designed clearly.

## References

- Spring Framework JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring MBeanExporter API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring MBeanServerFactoryBean API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/support/MBeanServerFactoryBean.html
- Spring EnableMBeanExport API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/EnableMBeanExport.html
- Java SE MBeanServer: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE MBeanServerFactory: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerFactory.html
