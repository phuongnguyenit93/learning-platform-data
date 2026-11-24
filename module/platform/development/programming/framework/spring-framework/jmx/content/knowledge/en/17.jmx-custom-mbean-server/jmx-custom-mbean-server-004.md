# Spring Framework JMX: Registering Beans into an Existing MBeanServer

## 1. Objectives and Context

In Java Management Extensions (JMX), \`MBeanServer\` is where the registry of managed MBeans is stored. Spring Framework provides \`MBeanExporter\` to export Spring beans as MBeans and register them into a server.

In real-world applications, the server to use may **already exist** before the Spring context initializes:

- The JVM has a platform \`MBeanServer\` created by Java ManagementFactory.
- An application server or hosting framework has already created its own server.
- A platform module of the application has already created and registered an \`MBeanServer\` in the same JVM.
- Multiple \`ApplicationContext\` instances need to share one MBeanServer for consistent management.

In these cases, you should not create an extra MBeanServer just to export a few beans. The approach is to **identify the right existing server, pass that server to the exporter, register beans into it, and verify in the right registry**.

This lesson helps answer:

1. Distinguish the platform MBeanServer from other MBeanServers in the same JVM.
2. Locate or inject an existing MBeanServer.
3. Configure Spring \`MBeanExporter.setServer(...)\` or annotation-driven infrastructure to use that server.
4. Avoid duplicate ObjectName registration errors, double-exporting, and unclear cleanup lifecycles.
5. Verify from Java/JConsole that beans actually reside in the intended server.

\`\`\`text
                         One JVM
+------------------------------------------------------------+
|                                                            |
|  Existing MBeanServer                                      |
|  (platform or host-created server)                         |
|            ^                                               |
|            | registerMBean(Object, ObjectName)             |
|            |                                               |
|       MBeanExporter (Spring)                               |
|            ^                                               |
|            |                                               |
|     Spring ApplicationContext                              |
|       +-- serviceControl                                   |
|       +-- cacheControl                                     |
|       +-- queueControl                                     |
|                                                            |
|  JMX client --> right MBeanServer / endpoint --> MBeans    |
+------------------------------------------------------------+
\`\`\`

**Principle:** an ObjectName is unique only within the scope of a single MBeanServer. If the exporter registers a bean into server A while a client reads from server B, the client may report the MBean as not found even though the export step succeeded.

## 2. MBeanServer and MBeanServerFactory: Do Not Confuse the Two

Key JMX APIs:

| API | Role |
|---|---|
| \`javax.management.MBeanServer\` | MBean registry supporting register/unregister, read/write attributes, and invoke operations |
| \`java.lang.management.ManagementFactory.getPlatformMBeanServer()\` | Obtains the JVM's standard platform MBeanServer, creating it when needed |
| \`javax.management.MBeanServerFactory.createMBeanServer(...)\` | Creates a new MBeanServer and adds it to the list of MBeanServers discoverable via the factory |
| \`javax.management.MBeanServerFactory.findMBeanServer(...)\` | Finds MBeanServers registered/held by the factory in the JVM by agent ID |
| \`org.springframework.jmx.support.MBeanServerFactoryBean\` | Spring FactoryBean capable of locating an existing server or creating a new one depending on configuration |
| \`org.springframework.jmx.support.MBeanServerConnectionFactoryBean\` | Assists in obtaining a connection to an MBeanServer; distinguish local server from remote connection |
| \`org.springframework.jmx.export.MBeanExporter\` | Exports Spring beans as MBeans and registers them into the configured MBeanServer |

Two ways of obtaining/creating a server:

\`\`\`java
MBeanServer platform = ManagementFactory.getPlatformMBeanServer();
MBeanServer newServer = MBeanServerFactory.createMBeanServer(
    "com.example.private"
);
\`\`\`

These two references do not necessarily point to the same registry. \`platform\` is the server managed by the JVM; \`newServer\` is a different server. If the exporter uses \`newServer\`, JConsole or scripts viewing only the platform server may not see the MBean.

When the task is **registering into an existing server**, prioritize locating the right server or injecting a pre-created reference rather than proactively creating a new server unless required.

## 3. Simplest Approach: Using the Existing Platform MBeanServer

Java applications normally have a platform MBeanServer:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

MBeanServer platformServer =
    ManagementFactory.getPlatformMBeanServer();
\`\`\`

\`getPlatformMBeanServer()\` returns the standard platform server and initializes it if it has not yet been created; thus "already exists" here generally means the JVM already has or will provide the same platform server per contract.

Spring configuration:

\`\`\`java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PlatformJmxServerConfig {

    @Bean
    public MBeanServer managementMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }
}
\`\`\`

Then inject this \`MBeanServer\` bean into the exporter:

\`\`\`java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.jmx.export.MBeanExporter;

@Bean
public MBeanExporter exporter(
        MBeanServer managementMBeanServer,
        WorkerControl workerControl) {

    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(managementMBeanServer);
    exporter.setBeans(Map.of(
        "com.example.app:type=WorkerControl,name=primary",
        workerControl
    ));
    return exporter;
}
\`\`\`

Here, \`setServer\` matters more than the Spring bean name \`managementMBeanServer\`: the exporter receives the **specific MBeanServer object** and uses that object for registration.

If the context contains multiple beans of type \`MBeanServer\`, use \`@Qualifier\` or explicit dependency configuration to avoid injecting the wrong server.

## 4. Complete Example: Registering a Standard MBean into an Existing Server

Standard MBean definition:

\`\`\`java
package com.example.jmx;

public interface WorkerControlMBean {
    boolean isPaused();
    int getWorkerCount();
    void pause();
    void resume();
}
\`\`\`

Implementation:

\`\`\`java
package com.example.jmx;

public class WorkerControl implements WorkerControlMBean {
    private volatile boolean paused;
    private volatile int workerCount = 8;

    @Override
    public boolean isPaused() {
        return paused;
    }

    @Override
    public int getWorkerCount() {
        return workerCount;
    }

    @Override
    public void pause() {
        paused = true;
    }

    @Override
    public void resume() {
        paused = false;
    }
}
\`\`\`

Spring configuration:

\`\`\`java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class WorkerJmxConfig {

    @Bean
    public MBeanServer existingServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public WorkerControl workerControl() {
        return new WorkerControl();
    }

    @Bean
    public MBeanExporter workerExporter(
            MBeanServer existingServer,
            WorkerControl workerControl) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(existingServer);
        exporter.setBeans(Map.of(
            "com.example.app:type=WorkerControl,name=primary",
            workerControl
        ));
        return exporter;
    }
}
\`\`\`

This MBean has a management interface based on \`WorkerControlMBean\`. \`MBeanExporter\` handles registration, while the getter/operation contract is defined by Java Standard MBean rules.

If using Spring Boot or \`@EnableMBeanExport\` at the same time, check whether another exporter is trying to register the same object/name. A bean should have a single registration owner to avoid lifecycle conflicts.

## 5. If the Bean is a POJO with Spring JMX Annotations

A Spring POJO that does not implement \`XxxMBean\` can still be exported via metadata/ModelMBean.

Example:

\`\`\`java
package com.example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.app:type=CacheControl,name=products",
    description = "Controls the product cache"
)
public class CacheControl {

    private volatile boolean enabled = true;

    @ManagedAttribute(description = "Cache enabled flag")
    public boolean isEnabled() {
        return enabled;
    }

    @ManagedAttribute(description = "Update cache enabled flag")
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @ManagedOperation(description = "Clear cache content")
    public void clearCache() {
        // invoke actual cache component here
    }
}
\`\`\`

To configure an explicit exporter to the exact MBeanServer and use annotation metadata:

\`\`\`java
import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;

@Bean
AnnotationJmxAttributeSource jmxAttributeSource() {
    return new AnnotationJmxAttributeSource();
}

@Bean
MetadataMBeanInfoAssembler jmxAssembler(
        AnnotationJmxAttributeSource source) {
    MetadataMBeanInfoAssembler assembler =
        new MetadataMBeanInfoAssembler();
    assembler.setAttributeSource(source);
    return assembler;
}

@Bean
MBeanExporter cacheExporter(
        MBeanServer existingServer,
        CacheControl cacheControl,
        MetadataMBeanInfoAssembler assembler) {

    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(existingServer);
    exporter.setAssembler(assembler);
    exporter.setBeans(Map.of(
        "com.example.app:type=CacheControl,name=products",
        cacheControl
    ));
    return exporter;
}
\`\`\`

This configuration combines two independent parts:
- **Server selection:** \`setServer(existingServer)\`.
- **Member selection:** \`setAssembler(assembler)\`, reading metadata from annotations.

Do not confuse selecting the server with selecting JMX attributes/operations. Successfully registering into the right server does not guarantee the POJO exposes the intended members if the assembler differs from expectations.

## 6. Locating an MBeanServer Created by a Container/Application Server

In a single JVM there may be multiple MBeanServers. If the host already created a server before Spring starts, a mechanism to discover it or receive a direct reference is needed.

### 6.1. Finding by agentId via MBeanServerFactory

Java JMX supports:

\`\`\`java
import java.util.ArrayList;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

ArrayList<MBeanServer> servers =
    MBeanServerFactory.findMBeanServer(null);

for (MBeanServer server : servers) {
    System.out.println(server.getDefaultDomain());
}
\`\`\`

\`findMBeanServer(null)\` returns the list of servers held/known by the factory; it is not a guarantee of finding every MBeanServer created by any means or existing system-wide. The default domain name provides a hint but **is not a sufficiently unique identifier** across servers.

When the host provides a known agent ID, you can use:

\`\`\`java
ArrayList<MBeanServer> selected =
    MBeanServerFactory.findMBeanServer(agentId);
\`\`\`

Determine the agent ID according to the hosting environment's contract. Do not randomly pick the first element in the list if multiple servers match.

### 6.2. Receiving the Server Directly from the Container

Many server environments provide an API, JNDI binding, or Spring bean supplying the \`MBeanServer\`. When an official API exists, **injecting the reference** is the least ambiguous approach:

\`\`\`java
@Configuration
public class HostJmxConfiguration {

    @Bean("hostMBeanServer")
    public MBeanServer hostMBeanServer(
            HostMBeanServerProvider provider) {
        return provider.getMBeanServer();
    }
}
\`\`\`

Here \`HostMBeanServerProvider\` is a hypothetical interface provided by the integration environment, not a default Java/Spring class. The idea is to bridge the host adapter with Spring DI.

For specific containers, how to obtain the reference must follow that container's documentation and access rules. Do not treat a hypothetical class name as a real API.

## 7. Spring MBeanServerFactoryBean: Locate Existing and Fallback

Spring provides \`org.springframework.jmx.support.MBeanServerFactoryBean\`, commonly used when you want Spring to find an existing server or create one if none is found.

Example:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.jmx.support.MBeanServerFactoryBean;

@Bean
MBeanServerFactoryBean mbeanServerFactory() {
    MBeanServerFactoryBean factory =
        new MBeanServerFactoryBean();
    factory.setLocateExistingServerIfPossible(true);
    return factory;
}
\`\`\`

When \`locateExistingServerIfPossible\` is enabled, the factory attempts to find an existing server; depending on configuration, if none is found, it may create a new server.

**Important note:** if the requirement is *to strictly use the already-existing server*, a "create if not found" policy does not guarantee that goal. That is a fallback creating a new registry and can mask a failure to find the host's actual server.

For strict reuse requirements:
- Use injection from a host-supported provider.
- Or use a Spring locate-existing utility configured to fail if not found.
- Add an identity/marker MBean check after locating to confirm it is the exact intended server.

### 7.1. JmxUtils.locateMBeanServer

Spring has a helper:

\`\`\`java
import javax.management.MBeanServer;
import org.springframework.jmx.support.JmxUtils;

MBeanServer server = JmxUtils.locateMBeanServer();
\`\`\`

This method locates an MBeanServer using Spring-supported mechanisms and can throw if none is found. Overloads may accept an agent ID depending on the API. When multiple servers exist in the JVM, use exact parameters or selection logic rather than relying on search order.

The documentation for the Spring version in use is the authoritative source for specific behavior, especially with container-managed MBeanServers.

## 8. Configuring an Explicitly Injected MBeanServer Bean

One way to make ownership clear is to create a Spring bean with a fixed name for the server the application intends to use:

\`\`\`java
@Configuration
public class ExistingServerConfig {

    @Bean("applicationMBeanServer")
    public MBeanServer applicationMBeanServer() {
        return java.lang.management.ManagementFactory
            .getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter applicationExporter(
            @Qualifier("applicationMBeanServer")
            MBeanServer applicationMBeanServer,
            CacheControl cacheControl,
            MetadataMBeanInfoAssembler assembler) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(applicationMBeanServer);
        exporter.setAssembler(assembler);
        exporter.setBeans(Map.of(
            "com.example.app:type=CacheControl,name=products",
            cacheControl
        ));
        return exporter;
    }
}
\`\`\`

In this example, the corresponding imports \`Configuration\`, \`Bean\`, \`Qualifier\`, \`MBeanServer\`, \`MBeanExporter\`, \`Map\`, and domain classes are required. From a DI perspective, \`@Qualifier\` prevents ambiguity when multiple \`MBeanServer\` beans exist so Spring knows which instance to choose.

If the host already provides an \`MBeanServer\` bean, **it is not necessary to redeclare a new bean**; you can inject it directly into the exporter using the qualifier/bean name provided by the host. The best practice is to understand what the context already contains and reuse the existing reference.

## 9. Can an Annotation-Driven Exporter Use an Existing Server?

Yes. When using Spring annotation-driven JMX, the infrastructure exporter also needs a target server. In Java configuration, \`@EnableMBeanExport\` supports referencing the appropriate MBeanServer bean in the context:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport(server = "applicationMBeanServer")
public class AnnotationJmxConfig {

    @Bean("applicationMBeanServer")
    public MBeanServer applicationMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public CacheControl cacheControl() {
        return new CacheControl();
    }
}
\`\`\`

Meaning: the Spring annotation exporter is directed to the server bean named \`applicationMBeanServer\`, instead of relying implicitly on another server by convention or auto-configuration.

In a real project, check the annotation signature/attributes for your Spring version. If Boot also sets up JMX auto-configuration, ensure only one exporter is responsible for registering the same bean.

## 10. Bean Exported but Not Visible to the Client

A common error:

\`\`\`java
MBeanServer serverA =
    ManagementFactory.getPlatformMBeanServer();

MBeanServer serverB =
    MBeanServerFactory.createMBeanServer("other");

exporter.setServer(serverB);

// Client queries:
serverA.getAttribute(name, "MaxConnections");
\`\`\`

In this case, \`name\` may be registered in B but does not exist in A. The client throws \`InstanceNotFoundException\`.

How to diagnose:

\`\`\`java
boolean a = serverA.isRegistered(name);
boolean b = serverB.isRegistered(name);

System.out.printf(
    "serverA=%s, serverB=%s%n",
    a,
    b
);
\`\`\`

You usually need to determine:
- Which target server is the exporter actually using?
- Which Spring context owns the exporter?
- Which MBeanServer is JConsole/remote connector connected to?
- If multiple MBeanServers exist, which registry is the host's JMX endpoint publishing?

Do not resolve this by routinely registering beans into **every** MBeanServer: doing so can cause duplicate metrics, hard-to-control management permissions, and tangled ownership at shutdown.

## 11. Direct Registration via JMX API vs. Using Spring Exporter

Manual registration is possible:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "com.example.app:type=WorkerControl,name=primary"
);

server.registerMBean(new WorkerControl(), name);
\`\`\`

This path fits when the application actively manages the JMX lifecycle without using a Spring exporter. However, if the bean already lives in a Spring context, \`MBeanExporter\` is usually more convenient because:
- It can register multiple beans by mapping.
- It can use metadata assemblers to export POJOs.
- It provides naming strategies and registration policies.
- It integrates with the \`ApplicationContext\` lifecycle.
- It supports notification listeners and notification publishers.
- It avoids writing manual cleanup/unregistration for every bean.

Do not do both for the same ObjectName unless there is a genuine reason and explicit ownership rules; \`MBeanExporter\` does not automatically treat a manual registration as "its own".

## 12. ObjectName Collisions in a Shared MBeanServer

When multiple Spring contexts or modules share one server, ObjectName collision is an easy mistake:

\`\`\`text
Context A:
  com.example.app:type=WorkerPool,name=default

Context B:
  com.example.app:type=WorkerPool,name=default
\`\`\`

Both can use that name in code, but a single \`MBeanServer\` cannot hold two MBeans under the same ObjectName.

Design approaches:
1. If it is the **same resource**, only one context/exporter should own the registration.
2. If they are **two distinct resources**, add keys such as \`context\`, \`service\`, \`name\`, \`instance\` to distinguish them.
3. If bean A was already exported by the host, Spring should not register a duplicate.
4. Avoid enabling \`IGNORE_EXISTING\` or \`REPLACE_EXISTING\` to mask collisions without understanding the consequences.

Namespace example:

\`\`\`text
com.example.app:type=WorkerPool,context=admin,name=default
com.example.app:type=WorkerPool,context=public,name=default
\`\`\`

If multiple replicas of the same Spring application run in different JVMs, each JVM has its own MBeanServer and can use the same logical ObjectName. Monitoring should distinguish endpoints/targets rather than forcing pod IDs into every ObjectName.

## 13. Lifecycle: An Existing Server Does Not Mean Spring Owns the Server

A particularly important distinction:

- **Pre-existing MBeanServer**: usually managed by the JVM or host. Spring should not shut down or release the server unless the integration API explicitly specifies ownership.
- **MBeans registered by the exporter**: the exporter must manage unregistration when the ApplicationContext stops according to its lifecycle.
- **MBeans of other modules**: even on the same server, must not be unregistered arbitrarily.

Example:

\`\`\`text
Host starts
  |
  +-- creates/owns MBeanServer
  |
  +-- Spring Context A starts
  |       +-- exports MBean A
  |
  +-- Spring Context B starts
  |       +-- exports MBean B
  |
  +-- Context A stops
  |       +-- unregisters MBean A only
  |
  +-- Context B still running
  |       +-- MBean B remains registered
  |
  +-- Host stops
          +-- manages MBeanServer lifecycle
\`\`\`

Do not confuse \`unregisterMBean(name)\` with shutting down the entire \`MBeanServer\`.

With multiple exporters registering the same name under replace/ignore registration policies, ownership can become unpredictable. It is better for each ObjectName to have one clear owner.

## 14. Verifying Actual Registration

A small inspection utility class:

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class JmxRegistrationInspector {

    public static void inspect(
            MBeanServer server,
            ObjectName name) throws Exception {

        System.out.println("Registered: "
            + server.isRegistered(name));

        if (!server.isRegistered(name)) {
            return;
        }

        MBeanInfo info = server.getMBeanInfo(name);

        System.out.println("MBean class: "
            + info.getClassName());

        for (var attribute : info.getAttributes()) {
            System.out.printf(
                "Attribute=%s, type=%s, readable=%s, writable=%s%n",
                attribute.getName(),
                attribute.getType(),
                attribute.isReadable(),
                attribute.isWritable()
            );
        }

        for (var operation : info.getOperations()) {
            System.out.println(
                "Operation: " + operation.getName()
            );
        }
    }
}
\`\`\`

Usage:

\`\`\`java
ObjectName name = new ObjectName(
    "com.example.app:type=WorkerControl,name=primary"
);

JmxRegistrationInspector.inspect(existingServer, name);
\`\`\`

What to verify:
- Was the exact server injected from the host/platform?
- Is the ObjectName valid and actually registered?
- Does the JMX contract have the expected attributes/operations?
- Is the script/JConsole connected to the corresponding endpoint?
- Are other MBeans in the same domain/name missed or replaced?

To discover multiple MBeans, use a pattern:

\`\`\`java
ObjectName pattern = new ObjectName(
    "com.example.app:type=WorkerControl,*"
);

for (ObjectName candidate :
        existingServer.queryNames(pattern, null)) {
    System.out.println(candidate.getCanonicalName());
}
\`\`\`

## 15. Common Errors and How to Diagnose

| Symptom | Possible Cause | Resolution |
|---|---|---|
| \`InstanceAlreadyExistsException\` | Shared server already has an MBean with that ObjectName | Check owner, naming, and double-export |
| \`InstanceNotFoundException\` on client call | Client using a different server or wrong ObjectName | Compare \`isRegistered\` on the right server |
| Bean not visible in JConsole | Published endpoint/registry is not the server used by the exporter | Check host connector/server |
| \`NotCompliantMBeanException\` | Bean does not follow JMX contract and lacks a suitable adapter | Use Standard MBean or Spring ModelMBean assembler |
| \`MalformedObjectNameException\` | Invalid ObjectName syntax | Follow naming conventions, quote/validate values |
| Metadata missing operations | Assembler does not expose the member | Read \`MBeanInfo\`, check annotations |
| Spring startup error on server bean | Server cannot be located or multiple candidates | Check injection/qualifier/host API |
| Export succeeds but disappears after shutdown | Exporter unregisters MBean per lifecycle | Determine owner and context stop order |
| New server created unexpectedly | Factory has create fallback | Use strict locate/injection |
| Script reads platform server while MBean is in custom server | Registry mismatch | Use the same server/connection the exporter uses |

Exceptions may be wrapped by Spring inside a startup exception; inspect the underlying cause chain, especially \`InstanceAlreadyExistsException\` and \`NotCompliantMBeanException\`.

## 16. Application Rollout Procedure

An actionable procedure:

### Step 1 — Identify the Server Source

Choose one of:
- The JVM's platform MBeanServer.
- A server provided by the application server/container.
- A server pre-created by a foundational module.

If strict reuse is required, configuration must **fail fast** when the needed server does not exist, instead of silently creating a new one.

### Step 2 — Bring the Server Reference into Spring

Use a Spring \`MBeanServer\` bean, or inject the host's provider adapter. Use clear names/qualifiers if multiple servers exist.

### Step 3 — Design ObjectNames

Example:

\`\`\`text
com.example.platform:type=CacheControl,service=catalog,name=products
com.example.platform:type=QueueControl,service=orders,name=shipping
\`\`\`

Names must be unique within the server and stable across restarts when used by clients/dashboards.

### Step 4 — Choose the Exporter

- Standard/Dynamic MBean: can be exported directly with \`MBeanExporter\`.
- Spring POJO: use the corresponding \`MBeanInfoAssembler\`/annotation infrastructure.
- If annotation-driven, point the exporter to the identified server bean.

### Step 5 — Start Up and Verify

Read registration logs, run \`isRegistered\`, \`getMBeanInfo\`, and test read-only attributes through the server.

### Step 6 — Verify Shutdown

Stop one Spring context and confirm MBeans belonging to that context are unregistered; MBeans from the host or other contexts must remain if their owners have not stopped.

### Step 7 — Verify the Runtime Environment

Remote JMX must be protected with appropriate authentication, authorization, transport security, and network access controls. Never expose a JMX endpoint publicly just to "take a quick look".

## 17. Practice Exercises

### Exercise 1: Platform Server and New Server

Given:

\`\`\`java
MBeanServer a =
    ManagementFactory.getPlatformMBeanServer();

MBeanServer b =
    MBeanServerFactory.createMBeanServer("private");
\`\`\`

If a bean is exported to \`b\` while a client queries \`a\`, why can \`InstanceNotFoundException\` occur?

**Explanation:** \`a\` and \`b\` are two independent registries. A bean registered in \`b\` does not automatically appear in \`a\`.

### Exercise 2: Configuring the Exporter with the Right Server

Fill in the necessary part:

\`\`\`java
MBeanExporter exporter = new MBeanExporter();
// Set the injected server on the exporter
exporter.setServer(existingServer);
\`\`\`

### Exercise 3: Shared Server with Two Spring Contexts

Two contexts both export \`com.example.app:type=Worker,name=default\`. Propose a naming and ownership strategy.

**Hint:** add \`context=admin/public\` or a logical role; only one context should own each MBean. Do not use replace/ignore to hide misconfiguration.

### Exercise 4: Strict Reuse

Why might \`locateExistingServerIfPossible(true)\` be insufficient if the requirement is "must use the host-created server"?

**Hint:** if no server is found, the factory may create a new registry. Strict locate/injection and server identity verification are needed.

### Exercise 5: Post-Shutdown State

Context A exports MBean A and Context B exports MBean B into the same host MBeanServer. Context A stops; what should happen?

**Hint:** MBean A is cleaned up under owner A; MBean B remains registered if B is still active, and the host MBeanServer stays alive.

### Exercise 6: Plain Bean with Annotations

A \`CacheControl\` only has \`@ManagedResource\` and \`@ManagedAttribute\`, with no Standard MBean interface. Why is \`setServer(existingServer)\` alone not enough?

**Hint:** a metadata/ModelMBean adapter or properly configured annotation-driven export is also needed to build the JMX contract for the POJO.

## 18. Key Takeaways

**Registering Spring beans into an existing MBeanServer** is a matter of connecting the exporter to the **exact server reference**, not creating a new server. Obtain the server from the platform API or the host's provider, inject it into Spring, and configure \`MBeanExporter.setServer(existingServer)\` or annotation-driven infrastructure pointing to that server bean.

Clearly distinguish **the owner of the MBeanServer** from **the owner of each MBean registration**, ensure ObjectNames do not collide, and verify using \`isRegistered\` and \`MBeanInfo\` on the exact selected server. When a host has multiple servers, strict discovery and explicit injection help avoid "export succeeded but tools cannot see it" — a very common JMX issue in multi-context Spring applications.