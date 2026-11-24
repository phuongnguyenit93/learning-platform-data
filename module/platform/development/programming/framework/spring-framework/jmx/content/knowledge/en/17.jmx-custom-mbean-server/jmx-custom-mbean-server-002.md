# MBeanServerFactoryBean and exposePlatformMBeanServer in Spring Framework JMX

## 1. Lesson Objectives

In Spring Framework, an \`MBeanServer\` is where MBeans are registered so that JMX clients can read state or invoke operations. When configuring an application, we often want to **reuse the JVM's platform MBeanServer** instead of creating a new registry, because the platform server already contains many JVM MXBeans and is typically the server found by local management tools.

Spring's \`MBeanServerFactoryBean\` helps locate or create an \`MBeanServer\`. An important option is **\`exposePlatformMBeanServer\`**: a configuration mechanism related to prioritizing exposing the existing platform MBeanServer to Spring-managed components when no server is found otherwise.

It is important to clearly understand the difference between:

- **Locating an existing MBeanServer:** using a server that already exists.
- **Using the platform MBeanServer:** selecting the server provided by the JVM via \`ManagementFactory.getPlatformMBeanServer()\`.
- **Creating a new MBeanServer:** creating a different registry with its own lifecycle and set of MBeans.
- **Exporting a bean:** registering an object as an MBean into the selected server; this is performed by \`MBeanExporter\`, not by \`MBeanServerFactoryBean\`.

After this lesson, you will be able to choose the appropriate server configuration, avoid MBeans disappearing from JConsole due to registering into the wrong server, and test consistency between the Spring JMX exporter and platform JMX.

## 2. What Role Does MBeanServer Play?

An MBeanServer is an MBean registry and coordination API:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.ObjectName;
import java.lang.management.ManagementFactory;

MBeanServer platform =
    ManagementFactory.getPlatformMBeanServer();

ObjectName memory = new ObjectName("java.lang:type=Memory");
System.out.println(platform.isRegistered(memory));
\`\`\`

The JVM platform MBeanServer typically contains platform MXBeans, such as \`java.lang:type=Memory\`, \`java.lang:type=Threading\`, and \`java.lang:type=Runtime\`.

An MBeanServer is not a network port. Creating a server does not automatically open a JMX/RMI connector; conversely, a remote connector must be bound to a specific server and have its own security configuration.

\`\`\`text
Application bean
      |
      v
 MBeanExporter
      |
      | register MBean
      v
  MBeanServer
      |
      +--> Java platform MXBeans
      +--> Application MBeans
      |
      v
JMX client via MBeanServerConnection
      |
      +--> Local tooling
      +--> Connector (if configured)
\`\`\`

**Key takeaway:** a JVM can have **multiple MBeanServers**, but a JMX client only sees the MBeans residing on the server that the client actually connects to.

## 3. What is MBeanServerFactoryBean?

\`org.springframework.jmx.support.MBeanServerFactoryBean\` is a Spring \`FactoryBean<MBeanServer>\` used to provide an \`MBeanServer\` to the container. It can locate an existing server or create one according to the configured options.

Options to know:

| Option | Primary Meaning |
|---|---|
| \`locateExistingServerIfPossible\` | Attempt to locate an existing MBeanServer before creating a new one |
| \`agentId\` | Use an agent ID to locate the matching registered server |
| \`defaultDomain\` | Set the default domain when creating a new MBeanServer |
| \`registerWithFactory\` | Specify whether the newly created server is registered with \`MBeanServerFactory\` so it can be located later |
| \`exposePlatformMBeanServer\` | Adjust selection/exposure of the platform MBeanServer during server resolution |
| \`MBeanServer\` injected into exporter | Determine the exact registry containing application MBeans |

**Do not confuse:** the FactoryBean options relate to **creating or locating a server**. They do not decide which Spring beans become MBeans and do not automatically expose all beans in the ApplicationContext.

## 4. What Does exposePlatformMBeanServer Do?

The name \`exposePlatformMBeanServer\` easily leads learners to think this setting opens platform JMX outside the JVM. This is a misconception.

Fundamentally, the option related to the platform MBeanServer concerns **which server is provided/used inside the Spring container**. When a platform MBeanServer is provided, the exporter can register application MBeans in the same place as the JVM platform MXBeans.

\`\`\`text
JVM
 |
 +-- Platform MBeanServer
 |       |
 |       +-- java.lang:type=Memory
 |       +-- java.lang:type=Threading
 |       +-- com.example:type=Worker,name=Primary
 |
 +-- Custom MBeanServer (if created separately)
         |
         +-- custom.domain:type=Plugin,name=A
\`\`\`

If the exporter uses a custom server, a typical local JConsole observing the platform server will not by default see \`custom.domain:type=Plugin,name=A\`.

### 4.1. "Expose" Differs from "Remote access"

Make the distinction clear:

\`\`\`text
Expose platform server to Spring components:
  give beans/exporters in the JVM an MBeanServer reference

Expose JMX remotely:
  initialize a connector/management agent and configure
  network, RMI/transport, authentication, encryption
\`\`\`

\`exposePlatformMBeanServer\` does **not** mean the JVM opens a JMX TCP port. Remote JMX configuration is a separate responsibility and requires appropriate permissions, TLS, and management network controls.

### 4.2. Do Not Infer Defaults Without Checking

Spring Framework versions and ways of initializing \`MBeanServerFactoryBean\` may have different defaults or additional constraints. When a project requires ensuring the exact platform MBeanServer is used, the least ambiguous approach is explicit configuration:

\`\`\`java
@Bean
public MBeanServer mbeanServer() {
    return ManagementFactory.getPlatformMBeanServer();
}
\`\`\`

This is an alternative to relying indirectly on the FactoryBean. In projects using the FactoryBean, configure the setters supported by your specific Spring version and verify the actual server output.

## 5. Difference Between \`locateExistingServerIfPossible\` and \`exposePlatformMBeanServer\`

The two options have related goals but should not be treated as synonymous.

- \`locateExistingServerIfPossible\` expresses the intent to prefer using an existing MBeanServer rather than creating a new one.
- \`exposePlatformMBeanServer\` expresses the policy regarding the platform MBeanServer that Spring can use or provide during server lookup.
- \`agentId\` helps select the right server when multiple servers have been registered with MBeanServerFactory.
- \`defaultDomain\` applies when a server is **newly created**; it does not turn all MBean ObjectNames into a fixed domain.

An operational question to ask: **Is the resulting MBeanServer the exact object returned by \`ManagementFactory.getPlatformMBeanServer()\`?**

\`\`\`java
boolean sameInstance =
    configuredServer ==
    ManagementFactory.getPlatformMBeanServer();
\`\`\`

If \`sameInstance\` is \`true\`, an exporter registering into \`configuredServer\` will register on the platform server. If \`false\`, determine whether you are using a separate server or another pre-existing server.

### 5.1. When Multiple MBeanServers Exist

A JVM can hold multiple servers in the JMX factory's managed list. "Locating an existing server" is not sufficient to guarantee the selected server is the platform server if multiple candidates exist and no condition is specified.

In environments requiring high determinism, explicitly inject the platform server or use a server with a clear name/qualifier to avoid picking the wrong one.

## 6. Configuring Spring with MBeanServerFactoryBean

A Spring Framework configuration example:

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.support.MBeanServerFactoryBean;

@Configuration
public class ServerConfig {

    @Bean
    public MBeanServerFactoryBean mbeanServer() {
        MBeanServerFactoryBean factory =
            new MBeanServerFactoryBean();

        factory.setLocateExistingServerIfPossible(true);
        return factory;
    }
}
\`\`\`

When Spring initializes the bean, the \`FactoryBean\` provides an \`MBeanServer\` to other beans. In this example, the configuration requests locating an existing server if possible, though you should still verify the returned server in the actual environment.

If the Spring version you are using provides a setter for \`exposePlatformMBeanServer\`, consult the corresponding Javadoc before using it. Do not assume all versions place the option on the same class or keep the same signature.

**A clearer approach when the platform server is strictly required:**

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ExplicitPlatformServerConfig {
    @Bean
    public MBeanServer mbeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }
}
\`\`\`

Advantage: transparent server selection with minimal dependency on the state of other MBeanServers. Do not declare two identical \`MBeanServer\` beans simultaneously if the exporter injects by type without a qualifier, as that can cause ambiguity.

## 7. Combining MBeanServerFactoryBean with MBeanExporter

To export a Spring object, configure \`MBeanExporter\`:

\`\`\`java
package example.jmx;

import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.assembler.MethodNameBasedMBeanInfoAssembler;
import org.springframework.jmx.support.RegistrationPolicy;

@Configuration
public class ExporterConfig {

    @Bean
    public WorkerMonitor workerMonitor() {
        return new WorkerMonitor();
    }

    @Bean
    public MethodNameBasedMBeanInfoAssembler assembler() {
        MethodNameBasedMBeanInfoAssembler assembler =
            new MethodNameBasedMBeanInfoAssembler();
        assembler.setManagedMethods(
            "getCompletedJobs", "isEnabled", "setEnabled");
        return assembler;
    }

    @Bean
    public MBeanExporter mbeanExporter(
            MBeanServer mbeanServer,
            WorkerMonitor workerMonitor,
            MethodNameBasedMBeanInfoAssembler assembler) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(mbeanServer);
        exporter.setAssembler(assembler);
        exporter.setBeans(Map.of(
            "com.example:type=WorkerMonitor,name=Primary",
            workerMonitor));
        exporter.setRegistrationPolicy(
            RegistrationPolicy.FAIL_ON_EXISTING);
        return exporter;
    }
}
\`\`\`

Business bean:

\`\`\`java
package example.jmx;

public class WorkerMonitor {
    private volatile boolean enabled = true;
    private int completedJobs;

    public int getCompletedJobs() {
        return completedJobs;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public void jobCompleted() {
        if (enabled) {
            completedJobs++;
        }
    }
}
\`\`\`

This example focuses on illustrating **wiring** and management, not a production concurrency model. If the counter is updated from multiple threads, use synchronized/atomic primitives and define appropriate semantics.

### 7.1. Initialization Flow

\`\`\`text
Spring context refresh
     |
     +--> Create/locate MBeanServer
     |
     +--> Initialize WorkerMonitor
     |
     +--> Create MBeanExporter, inject the right MBeanServer
     |
     +--> Exporter registers WorkerMonitor under ObjectName
     |
     v
MBeanServer has application MBean
\`\`\`

Clients can then read \`CompletedJobs\` or \`Enabled\` from the registered ObjectName.

## 8. Verifying the Actual MBeanServer Used by the Exporter

A small Spring program:

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.context.annotation
    .AnnotationConfigApplicationContext;

public final class Main {
    public static void main(String[] args) throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(
                    ServerConfig.class,
                    ExporterConfig.class)) {

            MBeanServer configured =
                context.getBean(MBeanServer.class);

            MBeanServer platform =
                ManagementFactory.getPlatformMBeanServer();

            System.out.println(
                "Same as platform: " + (configured == platform));

            ObjectName name = new ObjectName(
                "com.example:type=WorkerMonitor,name=Primary");

            System.out.println(
                "Registered in configured server: " +
                configured.isRegistered(name));

            System.out.println(
                "Registered in platform server: " +
                platform.isRegistered(name));

            System.out.println(
                "CompletedJobs = " +
                configured.getAttribute(name, "CompletedJobs"));

            Thread.sleep(60_000);
        }
    }
}
\`\`\`

Expected results:

- \`configured.isRegistered(name)\` is \`true\` if the exporter registered successfully.
- \`platform.isRegistered(name)\` is \`true\` only when export goes to the platform server, or when that name was registered there via another path.
- \`configured == platform\` is direct proof of server identity.

If \`configured == platform\` is \`false\` and JConsole only looks at the platform server, not seeing the application MBean is not proof that the exporter failed.

## 9. What Are the Consequences of Creating a New MBeanServer?

A newly created MBeanServer is an independent JMX registry. Example:

\`\`\`java
MBeanServer isolated =
    javax.management.MBeanServerFactory.newMBeanServer(
        "isolated.example");
\`\`\`

It does not automatically contain all platform MXBeans like the server from \`ManagementFactory\`, unless they are registered via an appropriate mechanism. In many situations, only the platform server is needed for simple application management.

### 9.1. Benefits of a Separate Server

- Isolates integration tests, avoiding collisions with JVM and other application MBeans.
- Provides a dedicated registry for a module or plugin.
- Actively manages lifecycle and ObjectName sets as required.

### 9.2. Costs of a Separate Server

- Clients must know which server to connect to.
- Local JConsole may not see that registry.
- Remote access requires a connector bound to the separate server.
- Easy to accidentally configure exporter A on platform and exporter B on a custom server.
- Server and registration cleanup must be explicit.

If the goal is a unified dashboard for the JVM, creating multiple separate servers can introduce unnecessary difficulty.

## 10. Server Lifecycle and Ownership

Separate two types of lifecycles:

**MBeanServer lifecycle**: who creates it, who manages it, and whether the server needs to be released?

**MBean registration lifecycle**: which exporter registers and unregisters the ObjectName when the context closes?

\`\`\`text
MBeanServerFactoryBean (if creating server)
        |
        v
     MBeanServer
        ^
        |
   MBeanExporter --> register
   MBeanExporter --> unregister on context shutdown
\`\`\`

If using the platform MBeanServer, it belongs to the JVM and is shared by many components; the entire server should not be released when one context closes. The exporter should only unregister the MBeans under its own management.

If using a server created specifically by the FactoryBean, define the release policy according to the FactoryBean's lifecycle. Avoid keeping a remote connector active after the corresponding server/module has stopped.

## 11. Relationship with Spring Boot and Auto-Configuration

Spring Framework and Spring Boot do not have identical defaults across all versions. Spring Boot has JMX auto-configuration and settings such as \`spring.jmx.enabled\` in certain versions.

When using Boot, verify:

1. Is JMX auto-configuration currently enabled?
2. Which \`MBeanServer\` is Boot using?
3. Is there a custom \`MBeanServerFactoryBean\` or \`MBeanServer\` bean overriding it?
4. Is there an auto-configured \`MBeanExporter\` duplicating a custom exporter?
5. Do JMX Actuator endpoints (if enabled) collide in ObjectName or use a different domain?

Do not add a FactoryBean simply because you "need JMX" without checking whether Boot already provides an MBeanServer/exporter. Avoid duplicate exporter configurations that lead to \`InstanceAlreadyExistsException\`.

## 12. Diagnosing Errors Related to exposePlatformMBeanServer

| Symptom | Possible Cause | How to Verify |
|---|---|---|
| Spring exporter reports successful registration, JConsole does not see the MBean | Exporter uses a custom server | Compare \`configured == platform\` |
| Only JVM MXBeans visible, no app MBean | Exporter has not exported or wrong server/name | Check \`isRegistered\`, ObjectName, logs |
| \`MBeanServer\` not found in context | FactoryBean not declared or not scanned | Inspect bean definitions |
| Injection error due to multiple MBeanServer beans | Multiple configurations creating servers | Use qualifier or one clear primary bean |
| \`InstanceAlreadyExistsException\` | Two exporters registering the same name on one server | Check policy and ownership |
| Remote JMX does not see the MBean | Connector attached to a different server | Compare server reference and endpoint |
| Platform server has MBean but app still misses it | Annotation/assembler/exporter not active | Read MBeanInfo and config |
| Old MBean appears on context restart | Exporter failed to unregister or wrong ownership | Check lifecycle |
| \`exposePlatformMBeanServer\` option not visible in IDE | API/version or component mismatch | Check project version Javadoc |

If tests need to distinguish servers, compare \`MBeanServer\` **object identity** using \`==\`, not just default domain or class name strings.

## 13. When to Choose Which Approach?

| Need | Configuration Approach |
|---|---|
| Single app, want JConsole to see app MBeans alongside JVM MBeans | Explicitly inject the platform MBeanServer |
| Want Spring to select/locate an existing server | MBeanServerFactoryBean with appropriate locating settings |
| Want a separate server for integration tests | \`MBeanServerFactory.newMBeanServer()\` or factory configured to create new |
| Multiple ApplicationContexts sharing a registry | One shared \`MBeanServer\` injected into exporters |
| Plugin needing isolation | Consider separate server, lifecycle, and connector |
| Remote JMX | Configure ConnectorServer/management agent independently, with security |
| Spring Boot with JMX auto-configuration | Check existing configuration before adding exporter/factory |

A good principle is to **decide on the MBeanServer based on client observation requirements**, then configure the exporter. If a dashboard or JConsole expects the platform server, ensure the bean is actually registered there.

## 14. Practice Exercises

### Exercise A — Compare two servers

1. Obtain the platform server with \`ManagementFactory.getPlatformMBeanServer()\`.
2. Create a separate server with \`MBeanServerFactory.newMBeanServer()\`.
3. Register a demo Standard MBean into the separate server.
4. Check \`isRegistered\` on both servers.
5. Explain why local JConsole might not see the demo MBean in the separate server.

### Exercise B — Spring FactoryBean

1. Create an \`MBeanServerFactoryBean\` as in section 6.
2. Retrieve the \`MBeanServer\` from the Spring context.
3. Compare it with the platform server using \`==\`.
4. Change the locating/creating configuration according to the Spring version API used in the lab.
5. Record the server selection and explain it based on the configuration.

### Exercise C — Exporter wiring

1. Create \`WorkerMonitor\` and \`MBeanExporter\`.
2. Inject the server from the FactoryBean.
3. Check the ObjectName with \`isRegistered\`.
4. Call \`getAttribute\` on the **exact injected server**.
5. Switch the exporter's server to a different server and observe the difference.

### Exercise D — Context lifecycle

Start an ApplicationContext with an exporter, verify the ObjectName is registered, close the context, and verify unregistration. When using the platform server, confirm that JVM platform MXBeans still exist after the context closes.

### Exercise E — Spring Boot

In a Spring Boot test application, record which \`MBeanServer\` and \`MBeanExporter\` beans are present. Add an intentional custom configuration, then compare the set of ObjectNames before and after. Do not change remote JMX settings in this exercise.

## 15. Self-Check Questions

1. How do \`MBeanServerFactoryBean\` and \`MBeanExporter\` differ in responsibility?
2. What is special about the platform MBeanServer compared to a newly created server?
3. Why can the same JVM have multiple MBeanServers?
4. Does \`exposePlatformMBeanServer\` open a network port?
5. If an exporter uses a separate server, will local JConsole always see the app MBean?
6. How do you verify that two server references are the exact same object?
7. Does \`locateExistingServerIfPossible\` guarantee selecting the platform server when multiple servers exist?
8. When should you create a separate server for integration tests?
9. Why is \`RegistrationPolicy\` not a tool for selecting an MBeanServer?
10. When using Spring Boot, why should you check auto-configuration before adding a FactoryBean?

## 16. References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — \`MBeanServerFactoryBean\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/support/MBeanServerFactoryBean.html
- Spring Framework API — \`MBeanExporter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Java SE 21 — \`ManagementFactory\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html
- Java SE 21 — \`MBeanServerFactory\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerFactory.html
- Java SE 21 — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html

**Key takeaway:** \`MBeanServerFactoryBean\` determines which server is supplied to Spring; \`MBeanExporter\` places beans into that server. \`exposePlatformMBeanServer\` relates to selecting/exposing the platform server within the JVM, **not** opening a remote JMX port. The surest way to avoid registry confusion is to compare server identity and verify the ObjectName in the exact MBeanServer that the exporter is using.
