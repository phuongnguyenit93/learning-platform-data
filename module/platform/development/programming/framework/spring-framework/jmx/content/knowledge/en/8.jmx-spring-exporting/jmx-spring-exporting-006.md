# Distinguishing MBeanExporter from MBeanServerFactoryBean in Spring Framework JMX

## 1. Lesson Objectives

When integrating Java Management Extensions (JMX) into the Spring Framework, two similarly named classes are often confused:

- **`MBeanExporter`**: exposes application objects (typically Spring beans) to the JMX management interface by registering them as MBeans.
- **`MBeanServerFactoryBean`**: provides an `MBeanServer` to the Spring container, either by locating an existing server or creating a new one according to configuration.

The two components perform different jobs yet work together: *the factory provides the place to register; the exporter puts objects into that place*. This lesson focuses on that relationship, lifecycle, configuration approaches, choosing an MBeanServer, and diagnosing errors.

After this lesson, you will be able to:

1. Explain the difference between an **MBeanServer** and a **registered MBean**.
2. Identify the responsibilities of `MBeanExporter` versus `MBeanServerFactoryBean`.
3. Configure an exporter to use a specified MBeanServer.
4. Distinguish locating an existing server, creating a new server, and using the platform MBeanServer.
5. Explain why having an MBeanServer does not mean the application's MBeans have already appeared.
6. Verify the registration/unregistration lifecycle when the Spring ApplicationContext starts and closes.
7. Avoid confusing these two components with a JMX connector server used for remote connections.

## 2. The Big Picture: Three Independent Layers

A Spring application may contain three layers related to JMX:

\`\`\`text
+------------------------------------------------------+
| Spring ApplicationContext                            |
|                                                      |
|  WorkerService, CacheMonitor, QueueMonitor           |
|             |                                        |
|             v                                        |
|      MBeanExporter                                   |
|             | registerMBean                          |
|             v                                        |
|      MBeanServer <----- MBeanServerFactoryBean       |
|             |                creates/locates/provides|
+-------------|----------------------------------------+
              |
      MBeanServerConnection
              |
   +----------+--------------+
   |                         |
Local JMX client       JMX ConnectorServer
   |                         |
JConsole                 Network / remote JMX
\`\`\`

**Point of distinction:** `MBeanServerFactoryBean` does not select which business beans will be exported, and `MBeanExporter` is not the server hosting MBeans. A connector for remote access belongs to yet another responsibility: forwarding JMX requests to an MBeanServer over a secured connection.

| Component | Question It Answers | Key Inputs | Result |
|---|---|---|---|
| `MBeanServerFactoryBean` | "Which MBeanServer will be provided?" | Agent ID, locating/creating configuration | An `MBeanServer` object |
| `MBeanExporter` | "Which objects are registered under which names?" | Beans, ObjectNames, assembler, naming strategy, server | MBeans registered in the server |
| `MBeanServer` | "Which MBeans does the registry manage?" | `ObjectName`, MBean instance | Registry and JMX management API |
| JMX ConnectorServer | "How do out-of-JVM clients connect?" | Server, protocol/URL, authentication, network | Remote access endpoint |

Do not treat creating an `MBeanServer` as "enabling remote JMX"; that operation does not open a network port.

## 3. What Does MBeanServerFactoryBean Do?

`org.springframework.jmx.support.MBeanServerFactoryBean` is a Spring `FactoryBean` used to supply a `javax.management.MBeanServer` instance. It can locate an existing server or create one according to appropriate configuration.

Relevant settings:

- `locateExistingServerIfPossible`: controls preferring/locating an already existing MBeanServer.
- `agentId`: supports searching for an MBeanServer registered with `MBeanServerFactory` by agent ID (depending on the locating mechanism).
- `defaultDomain`: default domain when creating a new server, which does not equate to a mandatory domain for every ObjectName.
- `registerWithFactory`: controls registering the created server with `MBeanServerFactory`, affecting discoverability via the factory API.
- Another configuration can supply an existing server directly, such as `ManagementFactory.getPlatformMBeanServer()`.

These choices matter when sharing a server with another part of the JVM or isolating an MBean registry for a test environment.

### 3.1. Why Does Spring Need a FactoryBean?

The Spring container normally manages beans by calling a constructor or factory method. `FactoryBean<T>` is a mechanism for a bean to provide a different object of type `T`. With `MBeanServerFactoryBean`, the Spring bean normally retrieved has type `MBeanServer` for injection into the exporter or other components.

You can picture it as:

\`\`\`text
Spring bean definition: mbeanServerFactory
          |
          v
    MBeanServerFactoryBean
          |
          v
     getObject() = MBeanServer
\`\`\`

This is a mechanism for creating/selecting a server, not a mechanism to automatically scan and register all Spring beans.

### 3.2. Platform MBeanServer vs. Another Server

The JDK provides the platform MBeanServer:

\`\`\`java
MBeanServer platformServer =
    java.lang.management.ManagementFactory.getPlatformMBeanServer();
\`\`\`

The JVM's platform MXBeans (Memory, Threading, Runtime, etc.) are typically attached to the platform MBeanServer. If the exporter registers application MBeans into the platform server, a local client connecting to the platform server can see both JVM MBeans and application MBeans.

A separately created server can serve as an isolated registry:

\`\`\`java
MBeanServer privateServer =
    javax.management.MBeanServerFactory.newMBeanServer();
\`\`\`

A client inspecting the platform MBeanServer **does not automatically see** MBeans registered on a different server. This is a common cause of the "MBeanExporter ran, yet JConsole does not show the bean" situation.

## 4. What Does MBeanExporter Do?

`org.springframework.jmx.export.MBeanExporter` is the component that supports exporting Spring-managed objects or configured objects as MBeans in a server.

Typical responsibilities:

1. Receive the set of objects to export, e.g., `Map<String, Object>`.
2. Generate appropriate ObjectNames (or use provided names).
3. Determine how to map Java beans into MBeans, using appropriate assemblers/metadata.
4. Register MBeans via `MBeanServer.registerMBean`.
5. Handle duplicate name registration policy according to `RegistrationPolicy`.
6. Track and unregister the MBeans managed by the exporter when the lifecycle ends.

Related components:

| Component | Role |
|---|---|
| `MBeanExporter` | Orchestrates MBean registration and unregistration |
| `MBeanInfoAssembler` | Determines exposed attributes, operations, and metadata |
| `ObjectNamingStrategy` | Determines the ObjectName |
| `MBeanServer` | Server receiving the registration |
| `RegistrationPolicy` | Strategy when the ObjectName already exists |
| `@ManagedResource` | Metadata annotation for the managed object |
| `@ManagedAttribute`, `@ManagedOperation` | Specify exposed members when using an annotation assembler |

**Note:** the exporter can accept a regular bean and turn it into an MBean via Spring mechanisms, or register an object that already conforms to a JMX contract. Exact behavior depends on assembler configuration, naming strategy, autodetection, and object type.

## 5. Spring Example: Creating an MBeanServer and Using MBeanExporter

Java configuration example for a Spring Framework application without depending on Spring Boot.

### 5.1. Managed Business Bean

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicInteger;

public class TaskMonitor {
    private final AtomicInteger completed = new AtomicInteger();
    private volatile boolean enabled = true;

    public int getCompletedTasks() {
        return completed.get();
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public void reset() {
        completed.set(0);
    }

    public void taskCompleted() {
        if (enabled) {
            completed.incrementAndGet();
        }
    }
}
\`\`\`

Initially, this class is a regular Java object. Having getters, setters, and a `reset` method is not enough for a JMX client to find it; it must be exported to an MBeanServer.

### 5.2. Explicit Configuration of Both Components

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.assembler.MethodNameBasedMBeanInfoAssembler;
import org.springframework.jmx.support.MBeanServerFactoryBean;
import org.springframework.jmx.support.RegistrationPolicy;

import javax.management.MBeanServer;
import java.util.Map;

@Configuration
public class JmxConfig {

    @Bean
    public TaskMonitor taskMonitor() {
        return new TaskMonitor();
    }

    @Bean
    public MBeanServerFactoryBean mbeanServer() {
        MBeanServerFactoryBean factory =
            new MBeanServerFactoryBean();
        factory.setLocateExistingServerIfPossible(true);
        return factory;
    }

    @Bean
    public MethodNameBasedMBeanInfoAssembler jmxAssembler() {
        MethodNameBasedMBeanInfoAssembler assembler =
            new MethodNameBasedMBeanInfoAssembler();
        assembler.setManagedMethods(
            "getCompletedTasks", "isEnabled",
            "setEnabled", "reset");
        return assembler;
    }

    @Bean
    public MBeanExporter mbeanExporter(
            MBeanServer mbeanServer,
            TaskMonitor taskMonitor,
            MethodNameBasedMBeanInfoAssembler jmxAssembler) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(mbeanServer);
        exporter.setAssembler(jmxAssembler);
        exporter.setBeans(Map.of(
            "example.jmx:type=TaskMonitor,name=Primary",
            taskMonitor));
        exporter.setRegistrationPolicy(
            RegistrationPolicy.FAIL_ON_EXISTING);
        return exporter;
    }
}
\`\`\`

Here:

1. `mbeanServer()` declares the FactoryBean to create/locate an MBeanServer.
2. Spring injects the factory's `MBeanServer` product into the exporter.
3. `jmxAssembler()` specifies the methods exposed via JMX.
4. `mbeanExporter()` registers `TaskMonitor` under a specific name.
5. Only a JMX client connecting to **that exact MBeanServer** will see the ObjectName.

This example illustrates the explicit mechanism. In real projects, choose an assembler and policy matching the management contract; do not automatically export all public methods of a service if they were not designed as a management API.

### 5.3. Running a Small ApplicationContext

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class Main {
    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(JmxConfig.class)) {

            MBeanServer server = context.getBean(MBeanServer.class);
            ObjectName name = new ObjectName(
                "example.jmx:type=TaskMonitor,name=Primary");

            System.out.println("Registered: " +
                server.isRegistered(name));

            System.out.println("CompletedTasks: " +
                server.getAttribute(name, "CompletedTasks"));

            context.getBean(TaskMonitor.class).taskCompleted();

            System.out.println("CompletedTasks after event: " +
                server.getAttribute(name, "CompletedTasks"));

            Thread.sleep(60_000);
        }
    }
}
\`\`\`

When run with the appropriate Spring Context dependencies and the example classes on the classpath, the expected output is:

\`\`\`text
Registered: true
CompletedTasks: 0
CompletedTasks after event: 1
\`\`\`

Verification note: `context.getBean(MBeanServer.class)` directly reads the server supplied by the factory. If you use `ManagementFactory.getPlatformMBeanServer()` while the exporter registered onto a different server, the `isRegistered` result may differ.

## 6. Distinguishing "Locating a Server" vs. "Creating a Server"

### 6.1. Locating an Existing Server

A JVM application may already have the platform MBeanServer or a server created by another component. When you want the application's JMX MBeans to appear on the server shared by management tools, configure the exporter to use that exact server.

You can explicitly choose the platform MBeanServer via Java configuration:

\`\`\`java
@Bean
public MBeanServer mbeanServer() {
    return java.lang.management.ManagementFactory
        .getPlatformMBeanServer();
}
\`\`\`

This is an alternative to the FactoryBean when you simply need the platform server; there is no need to create a new MBeanServer. If another FactoryBean simultaneously also provides an `MBeanServer`, use a qualifier or explicit wiring to avoid ambiguity.

### 6.2. Creating a New Server

An application may have reasons to isolate a server, such as testing, namespace isolation, or building a dedicated connector:

\`\`\`java
@Bean
public MBeanServer isolatedMBeanServer() {
    return javax.management.MBeanServerFactory.newMBeanServer(
        "isolated.training");
}
\`\`\`

In that case, the exporter must use `isolatedMBeanServer`. A local JConsole attached to the platform server will not necessarily see that separate server. If remote access to the isolated server is required, you must create and configure a JMXConnectorServer attached to that specific server.

### 6.3. FactoryBean and Server Lifecycle

`MBeanServerFactoryBean` can create a server and manage the lifecycle of the server it created. When the context closes, understand how the server is released and which MBeans still remain. In an environment sharing the platform server, do not arbitrarily release a server that other components are actively using.

Operational guidance:

- Server created exclusively for tests: clean up test resources when tests finish.
- Shared platform server: the exporter only manages the MBeans it registered.
- Multiple ApplicationContexts in one JVM: establish a clear naming and ownership strategy.
- Context restart: ensure unregistration before re-registering if using the same ObjectName.

## 7. Autodetection, Annotations, and the Exporter

You do not always have to declare `setBeans` for every object. Spring can detect eligible MBeans and support annotations, depending on configuration. For example:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "example.jmx:type=Worker,name=Primary")
public class WorkerManagement {
    private volatile boolean enabled = true;

    @ManagedAttribute
    public boolean isEnabled() {
        return enabled;
    }

    @ManagedAttribute
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @ManagedOperation
    public void disable() {
        enabled = false;
    }
}
\`\`\`

You can use `@EnableMBeanExport` or an `MBeanExporter` configured with `AnnotationJmxAttributeSource` and a metadata assembler to export this kind of bean. However:

- An annotation on a class is not an MBeanServer.
- The FactoryBean does not scan annotations and register beans by itself.
- An exporter must be configured, initialized by Spring, and pointed at an appropriate server.
- If the application already has an automatic exporter, do not add a second exporter registering the same ObjectName.

## 8. RegistrationPolicy: Behavior When a Name Already Exists

An `ObjectName` can represent only one MBean at a time within the same MBeanServer. When the exporter encounters a duplicate name, the registration policy determines the behavior.

Common policies:

| Policy | Meaning | Risk / Use Case |
|---|---|---|
| `FAIL_ON_EXISTING` | Throws an error when the name is already registered | Useful for catching duplicate configurations |
| `IGNORE_EXISTING` | Keeps the existing registration and ignores the new registration | Can cause clients to see the stale bean unexpectedly |
| `REPLACE_EXISTING` | Replaces the existing registration | Requires understanding ownership and impact on other clients |

In training examples, `FAIL_ON_EXISTING` makes errors easy to detect. In production, select the policy according to the lifecycle contract and management permissions. Do not use `REPLACE_EXISTING` as a default way to mask duplicate naming errors.

**Important:** the policy is the exporter's responsibility during registration, not a core function of `MBeanServerFactoryBean`.

## 9. MBeanServerFactoryBean Is Not ConnectorServerFactoryBean

Another source of confusion comes from Spring JMX class names:

- `MBeanServerFactoryBean`: provides an MBeanServer.
- `MBeanExporter`: registers MBeans.
- `ConnectorServerFactoryBean`: helps create a JMX connector server so clients can connect according to a configured URL/protocol.

Diagram example:

\`\`\`text
MBeanServerFactoryBean
         |
         v
    MBeanServer
      ^      ^
      |      |
MBeanExporter ConnectorServerFactoryBean
(register)       (remote access)
\`\`\`

Having an MBeanServer and a working exporter does not mean remote JMX is open. Enabling a remote connector must be treated as a high-security administrative operation: it requires a private network, access control, and appropriate encryption. Do not open public JMX ports just to view MBeans in JConsole.

### 9.1. RMI, Firewalls, and Credentials

Remote JMX/RMI can use a registry port and a separate connector server port. The address advertised in the RMI stub must be reachable from the client; if the hostname/port is wrong, the client may connect to the registry yet fail on the next step. Use security settings appropriate for the JDK and infrastructure; authentication and TLS must not be skipped in real deployments.

To learn `MBeanExporter` and `MBeanServerFactoryBean`, prefer calling APIs on the local MBeanServer or inspecting via local JConsole before configuring a remote connector.

## 10. Testing: Are the Exporter and Factory Working Properly?

You can use checks like the following in a Spring integration test:

\`\`\`java
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import static org.junit.jupiter.api.Assertions.*;

class SpringJmxWiringTest {

    @Test
    void exporterRegistersOnConfiguredServer() throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(
                    JmxConfig.class)) {

            MBeanServer server =
                context.getBean(MBeanServer.class);

            ObjectName name = new ObjectName(
                "example.jmx:type=TaskMonitor,name=Primary");

            assertTrue(server.isRegistered(name));
            assertEquals(
                0,
                server.getAttribute(name, "CompletedTasks"));

            server.setAttribute(name,
                new javax.management.Attribute("Enabled", false));
            assertEquals(
                false,
                server.getAttribute(name, "Enabled"));
        }
    }
}
\`\`\`

The value of this test is verifying the exact **server injected into the exporter**, not merely checking whether `ApplicationContext` contains the `TaskMonitor` bean.

Checks to perform depending on the problem:

1. The ObjectName is registered accurately.
2. Metadata and operations match the management contract.
3. Attributes are readable/writable as declared.
4. When the context closes, the exporter unregisters MBeans under its management.
5. No duplicate ObjectName errors occur upon repeated context startup.
6. If using an isolated server, clients query that exact server.
7. Remote connections (if any) are tested separately with security enabled.

## 11. Configuration Selection Scenarios

### Scenario A: Simple Spring Application Needing Only Local JMX

Goal: local JConsole views application MBeans alongside JVM MBeans.

Solution: export the application into the platform MBeanServer or let Spring configuration locate the appropriate server; a separate `MBeanServerFactoryBean` is not strictly necessary.

### Scenario B: Multiple Modules in the Same JVM Needing a Unified JMX Registry

Goal: MBeans appear together in a single MBeanServer.

Solution: configure exporters to inject the same `MBeanServer`, and design ObjectNames to avoid collisions across modules; avoid letting each module silently create its own registry.

### Scenario C: Independent Integration Testing

Goal: run tests in parallel without polluting the platform server.

Solution: use an isolated MBeanServer per test or fixture, inject it explicitly into the exporter, and clean up when the context closes.

### Scenario D: Remote JMX Requirements

Goal: management clients from another machine access permitted MBeans.

Solution: first establish the target MBeanServer and exporter, then configure a secure remote connector/agent; verify each layer (registration, connector, network, TLS, credentials) rather than just adding a FactoryBean.

### Scenario E: Spring Bean Exists in Context, Yet JConsole Does Not See It

Possible causes: no exporter present, exporter has not scanned/registered the bean, ObjectName differs from expected, or the exporter uses a different server from the platform server JConsole is connected to.

## 12. Common Errors and Root-Cause Identification

| Symptom | Possible Cause | How to Verify |
|---|---|---|
| `getBean(MBeanServer.class)` fails | Missing server bean or multiple candidates | Check bean definitions and wiring |
| `MBeanServer` exists, yet `isRegistered(name)=false` | Not exported yet or registered on wrong server/name | Check MBeanExporter and ObjectName |
| `InstanceAlreadyExistsException` | Two exporters or contexts registered the same name | Check lifecycle and registration policy |
| Local JConsole sees JVM MBeans but lacks Spring MBeans | Exporter uses a different server or export failed | Compare server identities and ObjectName lists |
| Remote JMX timeout | Wrong connector/RMI or network settings | Check endpoint, hostname, firewall |
| Bean has annotations but is not exported | Missing exporter/annotation assembler or scanning | Check `@EnableMBeanExport`, metadata |
| Stale MBean appears after restart | Improper cleanup/unregistration | Check ownership and context closing |
| Operation does not appear | Assembler only exposes selected methods | Inspect `MBeanInfo` of the actual MBean |

When debugging, gather evidence in sequence:

\`\`\`text
1. Does ApplicationContext have TaskMonitor?
2. Does ApplicationContext have MBeanServer?
3. Does MBeanExporter use that server?
4. MBeanServer.isRegistered(ObjectName) == true?
5. Does MBeanServer.getMBeanInfo(name) have the right metadata?
6. Is the JMX client connected to the right server?
7. If remote: are connector, hostname, TLS, network, auth correct?
\`\`\`

This chain helps distinguish export errors, registry errors, and remote connector errors without making random configuration changes.

## 13. Self-Check Questions

1. Does `MBeanExporter` automatically create a different MBeanServer for each bean?
2. Does `MBeanServerFactoryBean` automatically export all Spring beans?
3. If an MBeanServer exists yet no application MBean has been registered, what will JConsole see?
4. Why might an exporter use an isolated server while local JConsole does not see the MBean?
5. On which component is `RegistrationPolicy` configured?
6. What are the roles of `MBeanInfoAssembler` and `ObjectNamingStrategy`?
7. If a Spring bean has `@ManagedResource`, which component is responsible for placing it into the server?
8. What is the difference between `MBeanServerFactoryBean` and `ConnectorServerFactoryBean`?
9. When should you share the platform MBeanServer instead of creating a separate server?
10. How can you verify precisely which server an exporter registers MBeans into?

## 14. Exercises

### Exercise 1 — Changing the MBeanServer

Use the `JmxConfig` example and try:

- Configuring the exporter to inject the platform MBeanServer.
- Configuring the exporter to inject a newly created server via `MBeanServerFactory.newMBeanServer()`.
- Comparing the `isRegistered(name)` result on the platform server versus the isolated server.
- Explaining why a client only sees MBeans on the server it is connected to.

### Exercise 2 — Testing Duplicate ObjectNames

Create two beans both exported with `example.jmx:type=TaskMonitor,name=Primary`. Observe `FAIL_ON_EXISTING`; then study `IGNORE_EXISTING` and `REPLACE_EXISTING` in a lab environment to state the consequences of each policy.

### Exercise 3 — Checking Lifecycle

Start the context and confirm `isRegistered=true`. Close the context and check that the MBean no longer exists according to the exporter's unregistration contract. Restart the context with the same ObjectName and confirm there is no longer a conflict.

### Exercise 4 — Annotation Metadata

Replace `MethodNameBasedMBeanInfoAssembler` with an appropriate annotation assembler configuration, and add `@ManagedResource`, `@ManagedAttribute`, and `@ManagedOperation` to the bean. Observe the metadata before/after and draw conclusions about how the assembler decides which members are exposed.

## 15. References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — `MBeanExporter`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework API — `MBeanServerFactoryBean`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/support/MBeanServerFactoryBean.html
- Spring Framework API — `ConnectorServerFactoryBean`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/support/ConnectorServerFactoryBean.html
- Java SE 21 API — `MBeanServer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 API — `ManagementFactory`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html

**Takeaway:** `MBeanServerFactoryBean` selects or creates the place that stores MBeans; `MBeanExporter` determines which objects and ObjectNames are registered into that place. A JMX connector server, meanwhile, handles remote access. Distinguishing these three responsibilities is the key to configuring Spring JMX accurately and diagnosing issues effectively.
