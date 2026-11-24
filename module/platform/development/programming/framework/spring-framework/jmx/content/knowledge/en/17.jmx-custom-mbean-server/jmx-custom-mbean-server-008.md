# Verifying the Actual Server Used by an Exporter

> **Topic:** Spring Framework JMX  
> **Knowledge Group:** Custom MBeanServer  
> **Lesson:** Verifying the Actual Server Used by an Exporter

## 1. Objectives

After this lesson, you will be able to:

- Distinguish **Spring ApplicationContext**, **MBeanExporter**, **MBeanServer**, and **JMXConnector**.
- Understand why an MBean can be exported successfully yet JConsole or a client cannot find it.
- Identify **the exact MBeanServer object used by the exporter**, rather than inferring it merely from the JVM having a platform MBeanServer.
- Compare the platform MBeanServer and a custom server created using \`MBeanServerFactory\` or Spring configuration.
- Verify the path from exporter to registry using \`isRegistered\`, \`queryNames\`, \`getMBeanInfo\`, and intentionally registering a test MBean.
- Design clear configurations using \`@EnableMBeanExport(server = "...")\` or \`MBeanExporter.setServer(...)\`, while preventing errors from multiple exporters using the wrong server.

## 2. A Common Problem

A Spring application has a bean annotated with \`@ManagedResource\` and \`@EnableMBeanExport\` enabled. Startup logs show no errors. Yet in JConsole, the **MBeans** tab does not show the expected ObjectName.

Hasty conclusion: "Spring did not export the MBean." In reality, there is another important possibility: **the exporter registered the MBean into a different MBeanServer than the one the tool is observing**.

\`\`\`text
                  Application JVM
      +-----------------------------------+
      | Spring ApplicationContext         |
      |     |                             |
      |     v                             |
      | MBeanExporter                     |
      |     |                             |
      |     +----> Custom MBeanServer     |
      |                                   |
      | Platform MBeanServer              |
      +--------------|--------------------+
                     |
                JConsole local attach
                     |
                     v
           Usually observes platform server

Result:
  Exporter uses custom server -> MBean exists
  JConsole uses platform server -> not visible
\`\`\`

Therefore, you must answer the right questions: **Which exporter is running, which MBeanServer is it using, and which server is the client connected to?**

## 3. Each Concept Has Its Own Responsibility

| Component | Role | What to Check |
|---|---|---|
| Spring bean | Business object/management facade | Was the bean created in the context? |
| \`@ManagedResource\` | Metadata for Spring JMX to recognize the resource | Is it processed by an appropriate exporter? |
| \`MBeanExporter\` | Registers beans as MBeans | Which exporter, which server configuration? |
| \`AnnotationMBeanExporter\` | Exporter using annotation metadata | Is it activated by Java config? |
| \`MBeanServer\` | JMX registry and execution gateway | Is the ObjectName registered on **this server instance**? |
| Platform MBeanServer | Standard JVM management server | Is the exporter using this server? |
| Custom MBeanServer | Additional server per application config | Was it supplied to the exporter? |
| \`JMXConnector\` | Provides client connectivity to a server | Which server is the connector exposing? |
| \`MBeanServerConnection\` | Local/remote server access interface | Is the client querying the right connection? |

An \`ObjectName\` identifies an MBean **within the scope of one MBeanServer**. Two servers in the same JVM can have different registries, and each server can register the same ObjectName pointing to different MBeans.

## 4. Platform MBeanServer Is Not Necessarily the Exporter's Server

The JDK provides:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

MBeanServer platform =
    ManagementFactory.getPlatformMBeanServer();
\`\`\`

This is an MBeanServer serving JVM platform management. JMX tools attaching to the JVM typically observe MBeans exported through this server.

However, the application can create another server:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer custom =
    MBeanServerFactory.createMBeanServer(
        "custom.management"
    );
\`\`\`

Then:

\`\`\`java
System.out.println(platform == custom); // false
\`\`\`

Two servers do not share a registry just because they reside in the same JVM. If the exporter is pointed at \`custom\`, querying \`platform\` will not automatically find the custom server's MBeans.

### Distinguishing create and find

\`MBeanServerFactory.createMBeanServer(domain)\` creates a new server and adds it to the list of MBeanServers discoverable by the factory under the corresponding mechanism. \`MBeanServerFactory.newMBeanServer(domain)\` also creates a new server but does not register it with the factory in the same way. This affects discoverability by other code.

Do not create multiple servers "just to be safe". Having multiple servers increases the chance that exporter and client diverge in registries.

## 5. How a Spring Exporter Selects an MBeanServer

In Spring JMX, \`MBeanExporter\` can be given an explicit \`MBeanServer\`. With annotation-driven export, Java configuration can specify the server via a Spring bean name.

Example:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport(server = "jmxServer")
public class JmxConfiguration {

    @Bean
    public MBeanServer jmxServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }
}
\`\`\`

\`server = "jmxServer"\` is a **bean name in the Spring context**, not a hostname, JMX URL, or JMX ObjectName.

With a manually created exporter:

\`\`\`java
import org.springframework.jmx.export.MBeanExporter;

MBeanExporter exporter = new MBeanExporter();
exporter.setServer(jmxServer);
\`\`\`

\`setServer\` accepts an **MBeanServer object**. Once explicitly configured, querying that server directly is more reliable than guessing which server the exporter will auto-select.

If not specified, Spring has a mechanism to locate an MBeanServer based on configuration and environment. In a system with multiple servers, an implicit choice may not be appropriate. Make selection explicit rather than relying on a general assumption about defaults.

## 6. Practical Example: One Exporter, One Specific Server

### 6.1. Managed Bean

\`\`\`java
package example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "learning.jmx:type=CacheMonitor,name=main"
)
public class CacheMonitor {

    private volatile long refreshCount;

    @ManagedAttribute
    public long getRefreshCount() {
        return refreshCount;
    }

    public void recordRefresh() {
        refreshCount++;
    }
}
\`\`\`

### 6.2. Configuration Using the Platform MBeanServer

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@ComponentScan(basePackageClasses = CacheMonitor.class)
@EnableMBeanExport(server = "jmxServer")
public class PlatformJmxConfig {

    @Bean
    public MBeanServer jmxServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }
}
\`\`\`

The configuration uses the same server for the exporter and verification. This is useful when the goal is viewing the MBean in local JConsole.

### 6.3. Launch and Verify

\`\`\`java
package example.jmx;

import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class JmxServerProbe {

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(
                     PlatformJmxConfig.class
                 )) {

            MBeanServer configured =
                context.getBean("jmxServer", MBeanServer.class);

            ObjectName name = new ObjectName(
                "learning.jmx:type=CacheMonitor,name=main"
            );

            System.out.println(
                "registered=" + configured.isRegistered(name)
            );
            System.out.println(
                "RefreshCount=" +
                    configured.getAttribute(name, "RefreshCount")
            );

            System.out.println(
                "PID=" + ProcessHandle.current().pid()
            );
            System.in.read();
        }
    }
}
\`\`\`

When the context initializes and exports successfully, \`registered=true\`. A JConsole client connected to the right JVM usually finds \`learning.jmx:type=CacheMonitor,name=main\` on the platform server.

Key point: \`context.getBean("jmxServer", MBeanServer.class)\` reads the **explicitly configured server**, rather than picking any server by domain name.

## 7. When There Is a Custom MBeanServer

An application can create its own server:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport(server = "isolatedMBeanServer")
public class IsolatedJmxConfiguration {

    @Bean
    public MBeanServer isolatedMBeanServer() {
        return MBeanServerFactory.createMBeanServer(
            "isolated.management"
        );
    }
}
\`\`\`

With this configuration, the exporter targets \`isolatedMBeanServer\`. If a client still queries:

\`\`\`java
ManagementFactory.getPlatformMBeanServer()
\`\`\`

it will very likely not see the exporter's MBean on the dedicated server.

To verify properly:

\`\`\`java
MBeanServer actual =
    context.getBean(
        "isolatedMBeanServer",
        MBeanServer.class
    );

boolean found = actual.isRegistered(
    new ObjectName(
        "learning.jmx:type=CacheMonitor,name=main"
    )
);
\`\`\`

Note: the default domain set when creating a server does not force every MBean into that domain. An MBean registered with a specific \`ObjectName\` still retains its own domain such as \`learning.jmx\`.

## 8. Verifying by Identity Rather Than Name Alone

If you have two variables:

\`\`\`java
MBeanServer platform =
    ManagementFactory.getPlatformMBeanServer();

MBeanServer configured =
    context.getBean("jmxServer", MBeanServer.class);
\`\`\`

you can check:

\`\`\`java
System.out.println(
    "sameInstance=" + (platform == configured)
);
\`\`\`

The \`==\` comparison is useful when you hold the exact local object reference passed to the exporter. It is not a mechanism for identifying a remote server and should not be used with different proxy/wrapper objects.

When an MBeanServer is wrapped by a delegating proxy or adapter, wrapper identities may differ even when accessing the same registry. In that situation, checking for the presence of a marker MBean or ObjectName alongside actual metadata is more valuable.

## 9. Using a Marker MBean to Distinguish Servers

When servers hold many similar MBeans, you can register a dedicated "marker" MBean for the test environment.

### 9.1. Marker Interface

\`\`\`java
package example.jmx;

public interface ServerMarkerMBean {
    String getMarker();
}
\`\`\`

### 9.2. Implementation

\`\`\`java
package example.jmx;

public class ServerMarker implements ServerMarkerMBean {

    private final String marker;

    public ServerMarker(String marker) {
        this.marker = marker;
    }

    @Override
    public String getMarker() {
        return marker;
    }
}
\`\`\`

### 9.3. Registering into the Expected Server

\`\`\`java
ObjectName markerName = new ObjectName(
    "learning.jmx:type=ServerMarker,name=probe"
);

configured.registerMBean(
    new ServerMarker("configured-server"),
    markerName
);
\`\`\`

Then compare:

\`\`\`java
System.out.println(
    "configured=" + configured.isRegistered(markerName)
);

System.out.println(
    "platform=" + platform.isRegistered(markerName)
);
\`\`\`

If only the configured server sees the marker, the two servers do not share the same registry. Do not register markers arbitrarily in production; use a non-colliding name, clean up with \`unregisterMBean\`, and only do so when you own the server.

A marker indicates which server the test code accessed; it does not by itself prove the exporter is using it. To prove the exporter → server link, combine this with \`setServer\` or \`@EnableMBeanExport(server = "...")\` configuration and an **actual MBean registered by the exporter**.

## 10. Procedure to Verify Which Server the Exporter Is Using

A verification sequence you can follow:

1. **Identify the exporter** in the Spring context: annotation exporter, explicit exporter, or auto-configuration.
2. **Identify the exporter's server configuration**: bean name in \`@EnableMBeanExport\` or object passed to \`setServer\`.
3. **Retrieve the exact server** from configuration, without assuming the platform server.
4. **Pick the ObjectName** of an MBean that genuinely belongs to the exporter.
5. **Call \`isRegistered\`** on the retrieved server.
6. **Call \`getMBeanInfo\`** to confirm the attributes/operations published by the bean.
7. **Compare against the platform server** when diagnosing why JConsole does not see it.
8. **Check the client connection**: which registry is JConsole/JMX connector pointing to.
9. **Record the findings** using the verified ObjectName, server identity, or marker.

\`\`\`text
Exporter config -> actual MBeanServer -> isRegistered(ObjectName)
                                 |
                                 v
                           getMBeanInfo
                                 |
                                 v
                     attribute/operation verified

Client config ----> MBeanServerConnection -> queryNames
                                 |
                                 v
                Compare whether it is the same registry
\`\`\`

## 11. Distinguishing isRegistered, queryNames, and getMBeanInfo

### isRegistered

\`\`\`java
boolean exists = server.isRegistered(name);
\`\`\`

Checks an exact ObjectName on the current server.

### queryNames

\`\`\`java
ObjectName pattern = new ObjectName(
    "learning.jmx:type=CacheMonitor,*"
);

Set<ObjectName> names =
    server.queryNames(pattern, null);
\`\`\`

Useful when uncertain about additional key properties, e.g. \`name=main\`, \`node=n1\`. \`queryNames\` returns the set of names at query time.

### getMBeanInfo

\`\`\`java
MBeanInfo info = server.getMBeanInfo(name);
\`\`\`

Helps inspect which attributes, operations, and notifications the MBean actually publishes. \`isRegistered=true\` only tells you **an MBean exists under that name**, not necessarily that it is the exact bean you intended to export.

### Note on Races

\`isRegistered\`, \`queryNames\`, and \`getMBeanInfo\` are separate operations. An MBean can be unregistered between calls. In systems with dynamic MBeans, clients still need to handle \`InstanceNotFoundException\`.

## 12. Multiple Exporters in the Same ApplicationContext

An application can have:

\`\`\`text
Spring ApplicationContext
   |
   +-- AnnotationMBeanExporter -> Server A
   |
   +-- Explicit MBeanExporter  -> Server B
\`\`\`

This situation easily causes confusion:

- A bean may be exported by more than one exporter if configurations overlap.
- An ObjectName may be registered on Server A but absent on Server B.
- Clients observing two different servers may see different lists of MBeans.
- Two exporters using the same server and the same ObjectName cause registration conflicts.
- \`RegistrationPolicy.REPLACE_EXISTING\` is not the default fix for duplicate exporter configurations.

If Spring Boot already auto-configures an exporter and you add \`@EnableMBeanExport\` or a manual \`MBeanExporter\`, clearly determine which exporter is the primary registration source. Depending on the Spring Boot version, JMX auto-configuration can be enabled/disabled with the appropriate property; do not infer solely from property names without observing the actual context.

## 13. Finding Exporters in the Spring Context

You can inventory beans by type:

\`\`\`java
import java.util.Map;
import org.springframework.jmx.export.MBeanExporter;

Map<String, MBeanExporter> exporters =
    context.getBeansOfType(MBeanExporter.class);

exporters.forEach((name, exporter) ->
    System.out.println(
        "Exporter bean: " + name
            + ", class=" + exporter.getClass().getName()
    )
);
\`\`\`

\`AnnotationMBeanExporter\` is a type of exporter, so it can appear in the results when within the matching inheritance hierarchy.

This list tells you which exporters are **known to the Spring context**, but does not by itself reveal the exact internal server if there is no public API to retrieve it. For implicitly selected servers, combine evidence from configuration, Spring startup/logging, and registered MBeans.

Do not use reflection to read private fields of an exporter in a production application just to identify the server. Explicit configuration is usually easier to verify and maintain.

## 14. Using Explicit Configuration to Eliminate Ambiguity

If you control the exporter, the most reliable approach is providing a clear server:

\`\`\`java
@Configuration
public class ExplicitJmxConfiguration {

    @Bean
    public MBeanServer managementServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter exporter(
            MBeanServer managementServer,
            CacheManagementFacade facade
    ) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(managementServer);
        exporter.setBeans(Map.of(
            "app.management:type=Cache,name=primary",
            facade
        ));
        return exporter;
    }
}
\`\`\`

This is the manual exporter option. If using annotation-driven export, replace it with \`@EnableMBeanExport(server = "managementServer")\` and appropriate metadata.

Do not accidentally use both approaches for the same bean/ObjectName in the same MBeanServer.

## 15. Checking JConsole and Remote Connector Connections

### Local JConsole

JConsole normally connects to a JVM by PID and displays MBeans in the platform management server provided by the JMX agent. If a dedicated custom server is not exposed to that attach path, its MBeans do not automatically appear.

Procedure:

1. Run the application and note the PID.
2. Run \`jconsole\` from the JDK and select the right local JVM.
3. Open the MBeans tab.
4. Locate the domain and ObjectName.
5. If missing, verify the MBean on the server used by the exporter via code.
6. If the server differs from platform, decide to use the platform server or provide an appropriate connector.

### Remote JMX

A \`JMXConnectorServer\` can be bound to a specific MBeanServer. The client receives an \`MBeanServerConnection\` from that connector and sees the registry of the server exposed by the connector.

\`\`\`text
Remote client
   |
   v
JMXConnector
   |
   v
MBeanServerConnection
   |
   v
Server configured by connector
\`\`\`

Knowing only the same host URL or same JVM is not enough to prove the exporter and connector share a registry. You must confirm which server the connector points to, or check an actual marker/MBean in the registry.

\`@EnableMBeanExport\` does not automatically open a remote JMX connector. When enabling remote access, configure authentication, authorization, TLS, and appropriate network access restrictions.

## 16. Testing Two Different Servers

A test that does not impact the platform server can create two separate MBeanServers:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

MBeanServer first =
    MBeanServerFactory.newMBeanServer("first");

MBeanServer second =
    MBeanServerFactory.newMBeanServer("second");

ObjectName name = new ObjectName(
    "test.management:type=ServerMarker,name=probe"
);

first.registerMBean(
    new ServerMarker("first"),
    name
);

System.out.println(first.isRegistered(name));  // true
System.out.println(second.isRegistered(name)); // false
\`\`\`

This exact result shows that ObjectName is not a JVM-wide global address; it only has meaning within the corresponding server's registry.

When the test finishes, unregister markers created by the test. Do not apply MBean deletion operations to a production server unless ownership is certain.

## 17. Scenarios Where the Client Does Not Find the MBean

### Scenario A: Exporter Uses a Custom Server

**Symptom:** verification code on the custom server returns \`true\`, local JConsole does not see it.

**Resolution:** use the same MBeanServer for the exporter and tooling, or configure a connector to access the custom server.

### Scenario B: Two Spring Contexts Exist

**Symptom:** context A has an exporter and MBeanServer A, context B has MBeanServer B.

**Resolution:** confirm where the bean is created and where the exporter registers; do not assume two contexts in the same JVM share a registry.

### Scenario C: Exporter Has Not Run

**Symptom:** the Spring bean exists, yet no ObjectName appears on any expected server.

**Resolution:** check \`@EnableMBeanExport\`, bean discovery, annotation metadata, exporter lifecycle, and startup exceptions.

### Scenario D: Wrong ObjectName

**Symptom:** domain or key properties differ from expectations.

**Resolution:** query \`queryNames\` on the right server, then read \`getCanonicalName()\` and metadata. Do not guess from class names or Spring bean names.

### Scenario E: Two Exporters Compete for the Same Name

**Symptom:** startup has a registration error or the MBean changes unexpectedly.

**Resolution:** inventory exporters in the context, ownership, and RegistrationPolicy, then remove unintended duplicate configurations.

### Scenario F: Remote Connector Not Enabled

**Symptom:** local code sees the MBean, yet remote JConsole cannot connect.

**Resolution:** configure the JMX connector, port/network address, authentication, and appropriate TLS; do not treat this as proof of export failure.

## 18. Logging and Startup Observability

In a multi-server environment, log useful evidence during application startup:

\`\`\`text
JMX export configuration:
  exporter = annotationMBeanExporter
  serverBean = managementServer
  serverMode = platform
  expectedObjectName = app.management:type=Cache,name=primary
  registered = true
\`\`\`

This is a desired log format emitted by the application itself, not a log that Spring always prints by default. Log only non-sensitive configuration data; do not dump credentials, userData, or object graphs.

Adding a health check or startup assertion in the management layer can help detect if the exporter accidentally switched servers after a refactor, config change, or adding another management library.

Assertion example:

\`\`\`java
ObjectName expected = new ObjectName(
    "app.management:type=Cache,name=primary"
);

if (!managementServer.isRegistered(expected)) {
    throw new IllegalStateException(
        "JMX MBean missing on configured server: " + expected
    );
}
\`\`\`

Execute the assertion **after the exporter completes registration**. If run too early inside a business bean's \`@PostConstruct\`, it may fail due to lifecycle ordering rather than the exporter registering into the wrong server.

## 19. Lifecycle and Ownership Considerations

When an exporter registers an MBean, it can also manage unregistration when the Spring context closes. If there is a custom MBeanServer, know who created it and who is responsible for releasing the server.

Operational points:

- Avoid calling \`MBeanServerFactory.releaseMBeanServer\` for a server not created by your module.
- Do not unregister another component's MBean just to clean up the registry.
- For tests, create a dedicated server and remove the exact test MBeans created.
- For multi-layer application contexts, identify which exporter/context owns each registration.
- For remote connectors, close the connector server/client according to the appropriate lifecycle.
- Use unique ObjectNames, but do not use naming policies as a way to mask incorrect server selection.

The goal is to avoid the "MBean disappeared" situation caused by the client observing a different server rather than the exporter actually unregistering it.

## 20. Practice Exercises

An application has two servers:

\`\`\`java
MBeanServer platform =
    ManagementFactory.getPlatformMBeanServer();

MBeanServer isolated =
    MBeanServerFactory.newMBeanServer("isolated");
\`\`\`

The Spring exporter registers \`app.management:type=Queue,name=orders\` into \`isolated\`.

**Question 1:** Must \`platform.isRegistered(name)\` return \`true\`?

No. The two servers have separate registries.

**Question 2:** Why might local JConsole not see the MBean?

Because JConsole normally observes the platform server, whereas the exporter registered on the isolated server.

**Question 3:** What should be checked first?

Determine which server the exporter configuration is assigned; query \`isRegistered\` on that exact instance.

**Question 4:** If you want local JConsole to see the MBean, what can you do?

Configure the exporter to use the platform MBeanServer when appropriate, or provide a connector/access mechanism to the custom server.

**Question 5:** If a remote client can already connect to the JVM yet does not see the MBean, does that prove the exporter failed?

No. The connector may be exposing a different server. Compare the registry served by the connector with the server used by the exporter.

## 21. Self-Check Questions

1. Is ObjectName a global identifier across all MBeanServers in the same JVM?
2. Is \`ManagementFactory.getPlatformMBeanServer()\` always the Spring exporter's server?
3. Does \`@EnableMBeanExport(server = "managementServer")\` accept a bean name or a hostname?
4. What type of object does \`MBeanExporter.setServer\` accept?
5. Why must \`isRegistered\` be called on the right server?
6. What is the purpose of \`MBeanInfo\` after seeing the ObjectName?
7. What does a marker MBean prove, and what does it not yet prove?
8. Why do multiple exporters in one context easily make JMX outcomes unpredictable?
9. How do \`MBeanServerFactory.createMBeanServer\` and \`newMBeanServer\` differ in discovery capability?
10. If local JConsole does not see the MBean while the custom server has it registered, what is the next logical troubleshooting step?

## 22. Key Takeaways

\`\`\`text
Spring bean
    |
    v
MBeanExporter
    |
    | must identify
    v
Actual MBeanServer
    |
    +-- isRegistered(ObjectName)
    +-- queryNames(pattern)
    +-- getMBeanInfo(ObjectName)
    |
    v
JMX client/connector must observe the SAME registry
\`\`\`

**Core principle:** do not infer the exporter's server merely from the JVM having a platform MBeanServer or from JConsole results. Configure the server explicitly, verify an exporter-registered ObjectName on the right registry, and cross-check against the client's connection path. When the exporter and client do not use the same MBeanServer, an MBean can be exported successfully yet remain "invisible" to the observing tool.