# Verifying the Exporter Actually Uses the Expected MBeanServer in Spring Framework JMX

## 1. Objective and Design Problem

Spring Framework JMX allows exporting Spring-managed beans as MBeans through `MBeanExporter`. When there are multiple `MBeanServer` instances in a JVM, inside an application server, or when an application has a dedicated server, the fact that the exporter starts successfully **does not prove it chose the intended MBeanServer**. A bean may register successfully yet end up in a different registry from the one monitoring, JConsole, or `MBeanProxyFactoryBean` is using.

For example: an application creates a dedicated `MBeanServer` to isolate its management API, but the exporter discovers the platform server instead. Startup still succeeds, yet clients pointing to the dedicated server cannot find the ObjectName. Conversely, a bean may accidentally be exposed on a shared server or remote management connector.

**Lesson objective:** verify the end-to-end path from Spring bean, `MBeanExporter`, server reference, and ObjectName to the actual registry. Do not merely check that `server` appears in configuration; confirm that the exact same **MBeanServer instance** or connection is used on both the export side and the management side.

## 2. MBeanServer Is the JMX Registry

In JMX, `MBeanServer` manages MBean registrations by `ObjectName`, supports reading/writing attributes, invoking operations, and managing notification listeners.

```text
Spring-managed object
        |
        v
    MBeanExporter
        |
        | register MBean by ObjectName
        v
    MBeanServer
        |
        +-- queryNames
        +-- getMBeanInfo
        +-- getAttribute
        +-- invoke
        +-- notification listener registration
        |
        v
JConsole / local client / remote JMX connector
```

Within a single MBeanServer, an ObjectName is unique. Two different MBeanServers can hold the same ObjectName pointing to two different objects. Therefore, **MBeanServer + ObjectName** is the critical pair identifying the actual target.

```text
Server A:
  com.example.jobs:type=Queue,name=Main -> Queue A

Server B:
  com.example.jobs:type=Queue,name=Main -> Queue B
```

Querying Server A successfully does not imply Server B holds the same MBean.

## 3. Common Types of MBeanServers

| Server Type | How It May Appear | Key Considerations |
| --- | --- | --- |
| Platform MBeanServer | `ManagementFactory.getPlatformMBeanServer()` | Typically contains JVM MBeans such as `java.lang:type=Memory` |
| New server created by JMX | `MBeanServerFactory.createMBeanServer(...)` | Separate registry with its own default domain |
| Application container server | Provided by app server or runtime | May be shared across multiple applications |
| Server located/created by Spring factory | `MBeanServerFactoryBean` | Depends on locate/create choice and configuration |
| Remote connection | `JMXConnector.getMBeanServerConnection()` | Client view of target server; distinct from local `MBeanServer` object |

Multiple independent local `MBeanServer` instances can exist in a single JVM. An `MBeanServerConnection` supports management operations but is not necessarily a local `MBeanServer`; when verifying, distinguish **local server object identity** from **the server endpoint behind a connector**.

## 4. How Does MBeanExporter Choose a Server?

`MBeanExporter` has a `server` property of type `MBeanServer`. When no server is explicitly provided, Spring infrastructure has a mechanism to locate an appropriate `MBeanServer`, depending on configuration and environment. Do not assume the exporter **always** picks the platform MBeanServer, the first server, or a newly created server simply because an `MBeanServer` bean exists in the context.

Example explicit configuration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import javax.management.MBeanServer;

@Configuration
public class ExporterConfig {
    @Bean
    public MBeanExporter exporter(
            MBeanServer managementMBeanServer,
            QueueManagement management) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(managementMBeanServer);
        exporter.addExcludedBean("internalDebugBean");
        exporter.setBeans(java.util.Map.of(
            "com.example.jobs:type=Queue,name=Main", management
        ));
        return exporter;
    }
}
```

In this snippet, `setServer(managementMBeanServer)` is the explicit binding step. `addExcludedBean` is only an example of an autodetection-related option; it does not determine which server is chosen. What matters is that the injected `MBeanServer` bean is the exact target server operations expects to use.

## 5. Preparing a Simple MBean for Verification

Standard MBean example:

```java
package com.example.management;

public interface QueueManagementMBean {
    int getQueueDepth();
}
```

```java
package com.example.management;

public class QueueManagement implements QueueManagementMBean {
    @Override
    public int getQueueDepth() {
        return 7;
    }
}
```

Register using `MBeanExporter` with a known ObjectName:

```java
@Bean
public QueueManagement queueManagement() {
    return new QueueManagement();
}

@Bean
public MBeanExporter queueExporter(
        MBeanServer managementServer,
        QueueManagement queueManagement) {
    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(managementServer);
    exporter.setBeans(java.util.Map.of(
        "com.example.jobs:type=Queue,name=Main",
        queueManagement
    ));
    return exporter;
}
```

Do not register the same object via two exporters or via both manual JMX APIs and a Spring exporter. The example uses a single exporter as the sole owner of the ObjectName.

## 6. Using the Platform MBeanServer Explicitly

If you intend to export into the platform MBeanServer, declare it consistently:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;

@Bean
public MBeanServer managementServer() {
    return ManagementFactory.getPlatformMBeanServer();
}
```

Then both the exporter and local clients should inject the `managementServer` bean rather than each component looking up a different server on its own. `ManagementFactory.getPlatformMBeanServer()` returns the current JVM's platform server, suitable for many cases monitoring JVM metrics alongside application MBeans.

However, application servers may have different MBean registration policies; check connector management and where tools are connecting. Do not create a new MBeanServer automatically if you only want to read JVM metrics.

## 7. When a Dedicated MBeanServer Is Genuinely Needed

Example creating a dedicated server:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import org.springframework.context.annotation.Bean;

@Bean
public MBeanServer dedicatedManagementServer() {
    return MBeanServerFactory.createMBeanServer(
        "com.example.management"
    );
}
```

This is an independent registry. It may not appear in a default JConsole connection pointing to the platform server; monitoring/clients/connectors must be configured for the right server. Creating a new server does not automatically give it a remote port or TLS/authentication.

If multiple `MBeanServer` beans coexist in the context, injection by type can be ambiguous. Use an explicit name/`@Qualifier`:

```java
@Bean
public MBeanExporter queueExporter(
        @Qualifier("dedicatedManagementServer") MBeanServer server,
        QueueManagement queueManagement) {
    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(server);
    exporter.setBeans(java.util.Map.of(
        "com.example.jobs:type=Queue,name=Main", queueManagement
    ));
    return exporter;
}
```

Make sure to import `org.springframework.beans.factory.annotation.Qualifier`. Using `@Qualifier` only selects the Spring bean; runtime verification is still necessary to catch other exporters or connectors with separate configuration.

## 8. Checking Registration on the Expected Server

The most basic check is `isRegistered` on **the server the exporter is expected to use**:

```java
import javax.management.MBeanServer;
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "com.example.jobs:type=Queue,name=Main"
);

boolean present = managementServer.isRegistered(name);
System.out.println("Present in expected server: " + present);
```

If `present == true`, that server holds an MBean at that ObjectName. However, this **is not enough** to prove that your application's exporter registered it: the server could hold an old MBean or another component may have registered the same name. Additional checks on `MBeanInfo`, owner markers, and lifecycle are needed when collisions are possible.

Inspect metadata safely:

```java
import javax.management.MBeanInfo;

MBeanInfo info = managementServer.getMBeanInfo(name);
System.out.println("MBean class: " + info.getClassName());
for (var attr : info.getAttributes()) {
    System.out.println(
        "Attribute " + attr.getName() + ": " + attr.getType()
    );
}
```

Do not dump all attribute values just to verify the server: getters may have side effects, high cost, or leak secrets. Metadata and known target identity are usually enough for the first step.

## 9. Comparing Two Servers Using One ObjectName

Suppose an application has both `platform` and `dedicated`:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer platform =
    ManagementFactory.getPlatformMBeanServer();

MBeanServer dedicated = dedicatedManagementServer;

ObjectName expectedName = new ObjectName(
    "com.example.jobs:type=Queue,name=Main"
);

System.out.println(
    "platform registered=" + platform.isRegistered(expectedName)
);
System.out.println(
    "dedicated registered=" + dedicated.isRegistered(expectedName)
);
```

Possible outcomes:

| Platform | Dedicated | Possible Interpretation |
| --- | --- | --- |
| `true` | `false` | Exporter may be using platform or another component registered there |
| `false` | `true` | Exporter may be using dedicated as expected |
| `true` | `true` | Both registries have an MBean with the same name; compare owner/metadata |
| `false` | `false` | MBean unregistered, wrong name, exporter failed, or actually on a third server |

Do not draw conclusions solely from boolean flags when multiple exporters exist. Identify which exporter owns the name, the MBean's metadata, and its lifecycle path.

## 10. `queryNames` Helps Detect Differing Domains or Keys

If the exact ObjectName is missing, query names by domain:

```java
import java.util.Set;
import javax.management.ObjectName;

Set<ObjectName> names = managementServer.queryNames(
    new ObjectName("com.example.jobs:*") ,
    null
);

names.stream()
    .map(ObjectName::getCanonicalName)
    .sorted()
    .forEach(System.out::println);
```

This reveals whether the MBean is actually in the domain under a different `type`, `name`, or `instance`. `getCanonicalName()` normalizes key property ordering; `type=Queue,name=Main` and `name=Main,type=Queue` represent the same identity.

If nothing appears, check whether the exporter uses a different naming strategy, a different annotation ObjectName, a different MBeanServer, or a different profile creating the bean. Do not change `RegistrationPolicy` to fix a missing name error.

## 11. Verifying with a Spring Integration Test

In a test, create **two separate servers** and bind the exporter to the chosen server. It is important to assert **positive** on the target server and **negative** on the other server.

```java
import static org.junit.jupiter.api.Assertions.*;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;

class ExporterServerSelectionTest {
    @Test
    void registersOnlyInChosenServer() throws Exception {
        MBeanServer chosen =
            MBeanServerFactory.createMBeanServer("example-test");
        MBeanServer other =
            MBeanServerFactory.createMBeanServer("example-other");

        ObjectName name = new ObjectName(
            "com.example.test:type=Queue,name=Main"
        );

        try {
            // Initialize the Spring context with exporter.setServer(chosen)
            // and the QueueManagement bean exported into chosen.
            assertTrue(chosen.isRegistered(name));
            assertFalse(other.isRegistered(name));
        } finally {
            // Close the Spring context before releasing the servers.
            MBeanServerFactory.releaseMBeanServer(chosen);
            MBeanServerFactory.releaseMBeanServer(other);
        }
    }
}
```

This is an **illustrative test skeleton**; the Spring context initialization part must be implemented for the assertions to run meaningfully. Do not treat the two assertions above as a complete test without an exporter actually registering the MBean. In parallel test runs, dedicated MBeanServers help avoid collisions with production/JVM MBeans.

## 12. Complete Integration Test with AnnotationConfigApplicationContext

A more concrete example using local configuration and a known server:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

class ExactMBeanServerTest {
    @Configuration
    static class Config {
        @Bean
        MBeanServer testServer() {
            return MBeanServerFactory.createMBeanServer("test-domain");
        }

        @Bean
        QueueManagement queueManagement() {
            return new QueueManagement();
        }

        @Bean
        MBeanExporter exporter(
                MBeanServer testServer, QueueManagement target) {
            MBeanExporter exporter = new MBeanExporter();
            exporter.setServer(testServer);
            exporter.setBeans(Map.of(
                "com.example.test:type=Queue,name=Main", target
            ));
            return exporter;
        }
    }

    @Test
    void exporterUsesConfiguredServer() throws Exception {
        MBeanServer chosen;
        ObjectName name = new ObjectName(
            "com.example.test:type=Queue,name=Main"
        );

        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(Config.class)) {
            chosen = context.getBean(MBeanServer.class);
            assertTrue(chosen.isRegistered(name));
            assertFalse(
                java.lang.management.ManagementFactory
                    .getPlatformMBeanServer().isRegistered(name)
            );
            assertEquals(
                7, chosen.getAttribute(name, "QueueDepth")
            );
        }
        // The test may need to release the dedicated server after the context closes.
    }
}
```

`QueueManagement` must implement `QueueManagementMBean` as in the earlier example. The test verifies registration on the chosen server and confirms the platform server did not receive that MBean; if another test concurrently registers the same name on the platform server, stronger environment isolation is required. With `MBeanServerFactory.createMBeanServer`, manage server release after context close to avoid lingering registry references across the test suite.

## 13. Checking Client Proxies Use the Same Server

Spring's `MBeanProxyFactoryBean` must also use the right server/connection. If the exporter uses a dedicated server while the local proxy uses the platform MBeanServer, the proxy will not find the MBean.

```java
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.jmx.access.MBeanProxyFactoryBean;

@Bean
public MBeanProxyFactoryBean queueProxy(
        @Qualifier("dedicatedManagementServer") MBeanServer server)
        throws Exception {
    MBeanProxyFactoryBean proxy = new MBeanProxyFactoryBean();
    proxy.setServer(server);
    proxy.setObjectName(new ObjectName(
        "com.example.jobs:type=Queue,name=Main"
    ));
    proxy.setProxyInterface(QueueManagementMBean.class);
    return proxy;
}
```

The proxy routes by the **server + ObjectName** pair, and the interface must match actual `MBeanInfo`. Do not assume that merely matching ObjectName means the proxy and exporter use the same server.

## 14. Application Servers and Multiple ApplicationContexts

A single JVM can run multiple applications/WARs or multiple Spring contexts. When a shared MBeanServer exists:

```text
ApplicationContext A -> Exporter A ---+
                                    +--> Shared MBeanServer
ApplicationContext B -> Exporter B ---+
```

Conflicts can happen if two exporters pick the same ObjectName. Likewise, if a context accidentally uses the platform server instead of its intended dedicated server, MBeans may appear on a shared registry where operators do not want them.

During design review:

- Clearly identify the owner of each MBeanServer.
- Clarify which context creates the server and which contexts only consume it.
- Do not let multiple exporters auto-discover a server by default when isolation is required.
- Use qualifiers or explicit references rather than ambiguous bean injection.
- Verify cleanup on context close and redeploy.
- Do not call `unregisterMBean` on names owned by other modules.

Renaming an ObjectName to dodge collisions does not replace ensuring the exporter selects the right server.

## 15. Sources of Confusion When Using Spring Boot

In Spring Boot, custom Spring Framework MBeans and Actuator JMX endpoints may coexist. Actuator has its own JMX exposure settings; this does not guarantee a custom `MBeanExporter` uses the exact server you expect without explicit configuration.

Example property:

```properties
management.endpoints.jmx.exposure.include=health,info,metrics
```

This property controls Actuator endpoint exposure, **not MBeanServer selection for all custom MBeanExporters**. In applications with custom exporters, verify each exporter/server individually.

Do not confuse the management HTTP port (`management.server.port`) with a remote JMX connector. These are different management interfaces; an ObjectName identifies an MBean inside a server and carries no host/port information.

## 16. ObjectName Alone Is Not Enough to Identify the Right Instance

Even when `isRegistered` returns true on the expected server, **another MBean** could already occupy that name. For example, when using `RegistrationPolicy.IGNORE_EXISTING`, a new exporter may skip registration while queries continue returning the old MBean.

Three common policy values:

```java
RegistrationPolicy.FAIL_ON_EXISTING
RegistrationPolicy.IGNORE_EXISTING
RegistrationPolicy.REPLACE_EXISTING
```

`FAIL_ON_EXISTING` surfaces collisions; `IGNORE_EXISTING` does not guarantee the new bean was exported; `REPLACE_EXISTING` can overwrite another application's MBean. To verify ownership, use non-sensitive deployment metadata or test lifecycle with an isolated server.

Do not use `REPLACE_EXISTING` just to force `isRegistered` to return true. What you need to verify is the right **MBean instance, right server, and right owner**.

## 17. Lifecycle and Negative Assertions

A good integration test should verify:

1. Before the context exports the MBean, the target server does not contain the expected name (isolated test).
2. After context startup, the target server contains the ObjectName.
3. An out-of-scope server does not contain that ObjectName.
4. `MBeanInfo` matches the expected attributes/operations.
5. After closing the context, MBeans owned by the exporter are unregistered.

Example:

```java
ObjectName target = new ObjectName(
    "com.example.test:type=Queue,name=Main"
);

assertTrue(chosen.isRegistered(target));
assertFalse(other.isRegistered(target));

context.close();
assertFalse(chosen.isRegistered(target));
```

Do not clean up by unregistering every name in a domain, as that can delete MBeans not owned by the test context. Close only the context/owner that created the registration and release servers created by the test.

## 18. Warning About Remote JMX

If clients access remotely, `MBeanServerConnection` is obtained from `JMXConnector`:

```java
import javax.management.MBeanServerConnection;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://localhost:9010/jmxrmi"
);

try (JMXConnector connector = JMXConnectorFactory.connect(url)) {
    MBeanServerConnection connection =
        connector.getMBeanServerConnection();
    System.out.println(connection.getDefaultDomain());
}
```

The address is purely illustrative, not a secure connector configuration or a guarantee a server listens on that port. Remote connectors require network/authentication/authorization/TLS depending on environment; never expose unauthenticated remote JMX to debug.

To verify a client is connected to the right server, compare expected MBean lists, server identity metadata, or safe management attributes. `getDefaultDomain()` is only a supporting hint and **does not uniquely prove server identity**, because multiple servers can share the same default domain.

## 19. Quick Troubleshooting Table

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Exporter starts OK but client cannot find MBean | Exporter and client use different servers | Compare `isRegistered` across relevant servers |
| JConsole sees MBean, local code does not | JConsole connects to different JVM/server or wrong ObjectName | Compare connection/server/ID and canonical name |
| MBean appears on platform but not on dedicated server | Exporter uses wrong server | Inject server explicitly with `setServer` |
| Two servers both have the same ObjectName | Two independent registrations | Compare metadata/owner; do not delete blindly |
| `MBeanInfo` differs from expected | Stale MBean, another exporter, or different assembler | Check registration owner, profile, `MBeanInfo` |
| `InstanceAlreadyExistsException` | Two exporters register same name on same server | Fix ownership/naming, do not replace blindly |
| `isRegistered` false after redeploy | Exporter hasn't registered, unregistered early, or server changed | Inspect lifecycle/startup logs |
| Local proxy gets `InstanceNotFoundException` | Proxy uses different server/ObjectName | Compare server + name pair |
| Remote JMX timeout | Connector/network/security, not necessarily exporter | Check connection path and policies |
| Test via JConsole PASSES but production monitoring FAILS | Two tools connect to different servers/connectors | Test against the exact endpoint monitoring uses |

## 20. Design Review Checklist

- [ ] Target MBeanServer is clearly defined and owned.
- [ ] Exporter receives `MBeanServer` explicitly rather than relying on ambiguous lookup when multiple servers exist.
- [ ] If multiple `MBeanServer` beans exist, injection uses `@Qualifier` or an equivalent unambiguous mechanism.
- [ ] The `MBeanServer` in tests is the exact instance passed to `MBeanExporter.setServer`.
- [ ] `isRegistered` PASSES on the chosen server.
- [ ] Negative assertion confirms the name does not appear on out-of-scope servers.
- [ ] `MBeanInfo` matches the expected management contract.
- [ ] No stale MBean occupies the name due to `IGNORE_EXISTING` or leftover registration.
- [ ] JMX proxies/monitoring connect to the right server/connector.
- [ ] Cleanup/unregistration works properly on context shutdown.
- [ ] Raw sensitive attributes are not queried for debugging.
- [ ] Remote JMX is protected by authentication, authorization, and transport/network policy.

## 21. Mental Model

```text
Spring bean
    |
    v
MBeanExporter
    |
    +-- setServer(expectedServer)
    +-- ObjectNamingStrategy / ObjectName
    +-- MBeanInfoAssembler
    |
    v
Expected MBeanServer <--- isRegistered / getMBeanInfo
    |
    +-- assert MBean present
    |
Other MBeanServer <--- negative assertion
    |
    +-- assert MBean absent
    |
    v
Correct JMX client connection
```

**Conclusion:** verifying that `MBeanExporter` actually uses the intended MBeanServer must be grounded in **runtime registration and server identity**, not merely configuration that looks reasonable. The reliable approach is configuring `setServer` explicitly, checking the ObjectName on the target server, asserting absence on other servers, comparing `MBeanInfo`/ownership, and confirming unregistration when the context closes. Finally, ensure JMX proxies and monitoring connect to that exact registry; the right ObjectName on the wrong server is still an incorrect management design.
