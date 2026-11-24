# Registering MBeans in the Local JVM and Accessibility from Other Processes

## Learning Objectives

After this lesson, you will be able to:

- Explain how an MBean is registered into a **JVM's MBeanServer** and why successful registration does not mean other processes can automatically access it.
- Distinguish three roles: the MBean object, MBeanServer, and the JMX client/JMX connector.
- Understand the difference between access from the same JVM, local access from another process on the same machine, and remote connections from another machine.
- Register, look up, invoke attributes/operations on, and unregister an MBean using Java or the Spring Framework.
- Diagnose issues when an MBean is visible inside the process but does not appear in external tools, while designing secure management access controls.

## 1. Mental Model: Where Registration Lives vs. Access Path

The most important point of this topic:

> **An MBean is registered into an MBeanServer inside the JVM. Whether another process can observe or invoke it depends on the JMX connection mechanism, process accessibility, security configuration, and runtime environment.**

Picture two layers:

1. **Internal registration layer:** a Java application creates an MBean and places it into MBeanServer under an ObjectName.
2. **External access layer:** a client wanting to access that MBeanServer must have a valid connection path, such as an attach/local management mechanism or a configured JMX connector.

Registering an MBean is an action inside the running JVM. It **does not create an HTTP API**, does not open a network port by itself, and does not turn the object into a system-wide public object.

Diagram:

\`\`\`text
JVM A — application process
┌──────────────────────────────────────────────────────┐
│ Java/Spring component                                │
│       │                                              │
│       ▼                                              │
│    MBean ── registerMBean(...) ──► MBeanServer       │
│                                  │                   │
│                                  ├── local Java code │
│                                  └── JMX connector   │
└──────────────────────────────────┬───────────────────┘
                                   │ valid connection
                                   ▼
JVM B — management tool / JMX client
  JConsole / VisualVM / custom client
\`\`\`

A client in JVM B cannot directly invoke Java methods on an object living in JVM A's heap. The client interacts over a management protocol/connection, and the MBeanServer inside JVM A resolves the ObjectName and executes the operation in its own process.

## 2. What Are MBeanServer and ObjectName?

**MBeanServer** manages MBean registrations within a JVM. Clients can use it to:

- List or query MBean names.
- Read/write attributes according to permissions and published MBean capabilities.
- Invoke operations.
- Register or unregister MBeans if authorized.
- Register listeners for notifications when supported.

**ObjectName** is a management identifier, for example:

\`\`\`text
learning.jmx:type=JobQueue,name=Primary
\`\`\`

Where:

- `learning.jmx` is the domain.
- `type=JobQueue` and `name=Primary` are key properties.
- The name must follow ObjectName syntax; the same MBeanServer cannot register two MBeans with duplicate ObjectNames.

Note that ObjectName is **not a URL or network address**. The same ObjectName can exist independently in two different JVMs; you must identify the right JVM/connector to avoid operating on the wrong instance.

Each JVM can have multiple MBeanServers, though standard tools typically access the **platform MBeanServer** returned by `ManagementFactory.getPlatformMBeanServer()`. MBeans registered on a custom MBeanServer are not necessarily visible through a connector pointing to the platform server.

## 3. Registering an MBean Directly Within a JVM

A Standard MBean has an interface ending with `MBean` matching an implementation class. The example below creates a completed-job counter.

### 3.1. Management Contract

\`\`\`java
package example.management;

public interface JobCounterMBean {
    long getCompletedJobs();
    void reset();
}
\`\`\`

`getCompletedJobs()` is exposed as a readable attribute, while `reset()` is an operation. Being declared in the management interface determines what capabilities are exposed; arbitrary public methods on the class do not automatically become JMX operations.

### 3.2. Implementation Class

\`\`\`java
package example.management;

import java.util.concurrent.atomic.AtomicLong;

public class JobCounter implements JobCounterMBean {
    private final AtomicLong completedJobs = new AtomicLong();

    @Override
    public long getCompletedJobs() {
        return completedJobs.get();
    }

    public void recordJobCompleted() {
        completedJobs.incrementAndGet();
    }

    @Override
    public void reset() {
        completedJobs.set(0);
    }
}
\`\`\`

`recordJobCompleted()` only serves application code; it is not part of `JobCounterMBean`, so it is not an operation of this Standard MBean.

### 3.3. Registering and Unregistering

\`\`\`java
package example.management;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class RegisterLocalMBean {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        ObjectName name =
                new ObjectName("learning.jmx:type=JobCounter,name=Primary");

        JobCounter counter = new JobCounter();

        server.registerMBean(counter, name);

        System.out.println("Registered: " + server.isRegistered(name));
        System.out.println("MBean count: " + server.getMBeanCount());

        // Actual work can continue here.
        counter.recordJobCompleted();

        // Only unregister when the management interface is no longer needed.
        server.unregisterMBean(name);
    }
}
\`\`\`

These calls perform **internal registration**. To test with JConsole, keep the JVM running while observing, such as placing the logic inside a server application with a long enough lifecycle. The short `main` example only illustrates the registration/unregistration APIs; it exits too quickly to attach an external tool.

If `registerMBean` encounters an ObjectName already in use, the API throws `InstanceAlreadyExistsException`. If the object does not comply with MBean rules, `NotCompliantMBeanException` may be thrown. If unregistering a non-existent name, `InstanceNotFoundException` may occur.

## 4. Accessing an MBean from Code in the Same JVM

For code in the same process, MBeanServer can be used directly:

\`\`\`java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName name =
        new ObjectName("learning.jmx:type=JobCounter,name=Primary");

if (server.isRegistered(name)) {
    Object value = server.getAttribute(name, "CompletedJobs");

    System.out.println("Completed jobs: " + value);

    server.invoke(
            name,
            "reset",
            new Object[0],
            new String[0]
    );
}
\`\`\`

The attribute name `CompletedJobs` is derived from the `getCompletedJobs()` getter in the Standard MBean interface. Even though the example uses an object in the same JVM, this code still interacts through the MBeanServer management interface rather than holding a direct reference to `JobCounter`.

If you need to call a business component directly within the same application, dependency injection/service method calls are normally more natural. JMX is useful when a common management contract is needed for tooling and operators.

## 5. Do Other JVMs on the Same Machine Automatically See the MBean?

**Not automatically.** MBeanServer is not a machine-wide registry. Each JVM has its own memory space and its own list of MBeans.

However, JDK tools such as **JConsole** can discover some local JVMs and use the attach/local management mechanism supported by the JDK to connect, depending on OS, JVM vendor, user permissions, and security configuration. Thus, an application that has not explicitly configured a JMX port may still be visible to local management tools.

This often leads learners to misunderstand that an MBean registered in JVM A is "shared" with JVM B. In reality, JVM B receives access through an existing or enabled management connection path.

### Conditions That Commonly Affect Local Attach

- The target JVM must still be running, and the runtime must support the corresponding attach/local monitoring mechanism.
- OS user and security policies must permit operating on the target process.
- Some environments do not support or have disabled attach, such as via JVM flags or container policies.
- The tool and JVM must be compatible; management info may be restricted by permissions or runtime packaging models.
- Docker/containers, process namespaces, filesystem permissions, and user namespaces can prevent a JVM from appearing in the local list even on the same physical host.

Therefore, **"same host" does not guarantee accessibility**. Distinguish local connections via attach from remote JMX via a connector.

## 6. Accessing from Another Machine: A JMX Connector Is Required

A process on another machine cannot simply know the ObjectName and access MBeanServer. The application must provide a remote management connection mechanism, typically via the **JMX Remote API** and a JMX connector (commonly RMI-based in standard JDK setups).

Conceptual flow:

\`\`\`text
Remote JMX client
    │
    │ endpoint + transport + identity/permissions
    ▼
JMX Connector Server
    │
    ▼
MBeanServer in target JVM
    │
    ├── queryNames(...)
    ├── getAttribute(...)
    └── invoke(...)
\`\`\`

A common JDK configuration approach for controlled environments is providing remote management JVM system properties; for example:

\`\`\`text
-Dcom.sun.management.jmxremote
-Dcom.sun.management.jmxremote.port=9010
-Dcom.sun.management.jmxremote.rmi.port=9010
-Djava.rmi.server.hostname=<address-reachable-by-client>
\`\`\`

**This is only a reference skeleton**, not a configuration to copy verbatim into production. You must configure authentication, TLS/SSL, access permissions, and network restrictions appropriate for your JDK/runtime. Never disable authentication or TLS for connection convenience in environments accessible to others. Never expose a JMX port publicly to the Internet.

With RMI in particular, a client initially contacts one endpoint and then receives a stub containing a hostname/port for subsequent calls. Therefore, an open JMX port may still be unusable if the advertised hostname is `localhost`, a wrong internal IP, or an additional port is blocked by firewall/NAT. Configuring the same port for registry/RMI endpoints can simplify operations in suitable setups, though you must still verify against your actual runtime and infrastructure.

### Example JMX Client from Another Process

\`\`\`java
import java.util.Set;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public class RemoteJmxClient {
    public static void main(String[] args) throws Exception {
        JMXServiceURL url = new JMXServiceURL(
            "service:jmx:rmi:///jndi/rmi://jmx.internal.example:9010/jmxrmi"
        );

        // Supply the connection environment and authentication credentials
        // matching the server in a real deployment.
        try (JMXConnector connector =
                JMXConnectorFactory.connect(url)) {
            MBeanServerConnection connection =
                    connector.getMBeanServerConnection();

            Set<ObjectName> names =
                    connection.queryNames(
                        new ObjectName("learning.jmx:*"), null
                    );

            names.forEach(System.out::println);
        }
    }
}
\`\`\`

To run this client, there must be a **configured and accessible remote JMX server**; the hostname value is just an example. `JMXConnectorFactory.connect(url)` does not grant permissions or bypass authentication. If the server requires credentials, supply them via the environment map and an appropriate secrets management mechanism.

## 7. Which Server Does Spring Framework Register MBeans Into?

In the Spring Framework, `MBeanExporter` can register Spring-managed beans as MBeans. If a specific MBeanServer is not configured, how Spring locates or creates an MBeanServer is affected by lookup mechanisms and exporter configuration; do not assume every deployment uses the exact server an external tool is viewing.

Example:

\`\`\`java
package example.management;

import java.lang.management.ManagementFactory;
import java.util.Map;

import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxExportConfiguration {

    @Bean
    public JobCounter jobCounter() {
        return new JobCounter();
    }

    @Bean
    public MBeanExporter mBeanExporter(JobCounter counter) {
        MBeanServer platformServer =
                ManagementFactory.getPlatformMBeanServer();

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(platformServer);
        exporter.setBeans(Map.of(
            "learning.jmx:type=JobCounter,name=Primary",
            counter
        ));

        return exporter;
    }
}
\`\`\`

Here `setServer(platformServer)` is set intentionally so the MBean is registered in the **platform MBeanServer of the JVM running the application**. When Spring initializes and manages the exporter's lifecycle, the MBean is registered/unregistered according to that lifecycle.

**If using annotation-based MBeans:** Spring also supports `@ManagedResource`, `@ManagedAttribute`, and `@ManagedOperation`, along with a metadata assembler or appropriate exporter mechanism. Annotations only describe the contract; corresponding export configuration is needed for the MBean to actually appear.

**Spring Boot:** Spring Boot has JMX mechanisms related to Actuator, and enabling/disabling JMX varies by version, dependencies, and properties. Do not confuse MBeans published by the Spring Framework exporter with all Actuator endpoints; verify the actual MBeanServer and object names in the application.

## 8. Scenario: Registered Successfully, but JConsole Does Not See It

Suppose the application log shows:

\`\`\`text
Registered: true
\`\`\`

but the engineer's JConsole does not show `learning.jmx:type=JobCounter,name=Primary`.

Investigate along the closest chain of causes:

1. **Right JVM?** Verify PID, application, container, and runtime environment. Multiple JVMs can have the same ObjectName with completely different state.
2. **Is the application still running?** A demo program that exits after registering or unregisters before the operator connects will no longer have the MBean visible.
3. **Right MBeanServer?** If registered into a custom MBeanServer while the tool connects to the platform server, lists can differ.
4. **Actually registered?** Use `isRegistered(ObjectName)`, `queryNames(...)`, and check for registration errors. Verify exact domain and key properties; ObjectName is name-sensitive.
5. **Does the client have permission to connect to the target JVM?** Check OS permissions, JDK version, attach mechanism, policies, and process/container namespaces.
6. **Right connection type?** Local process attach differs from a remote JMX URL; remote requires a connector server, hostname, port, network, and proper authentication.
7. **Protocol/security errors?** Check connection failures, TLS, authentication, and RMI stub hostname/firewall instead of assuming the MBean was not registered.

The most reliable server-side verification:

\`\`\`java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName target =
    new ObjectName("learning.jmx:type=JobCounter,name=Primary");

System.out.println(server.isRegistered(target));
System.out.println(server.queryNames(
    new ObjectName("learning.jmx:*"), null
));
\`\`\`

This answers the question: **is the MBean registered in the platform MBeanServer of the current JVM?** It is not enough to prove that any external process already has an access path.

## 9. Security and Operational Permissions

JMX is a **management surface**, sometimes allowing configuration edits, side-effecting operations, viewing sensitive data, or impacting service health.

### When Management Is Only Needed Within One Machine or Container

Prefer an access path aligned with process permission boundaries. Do not configure a remote connector if unneeded; restrict who can attach to the process. Keep in mind that local OS privileges are powerful: someone able to attach/debug a JVM can sometimes already inspect sensitive data.

### When Remote JMX Is Needed

- Restrict ports within management networks/VPNs and firewalls; never expose to the public Internet.
- Enable authentication, protect credentials, and use encrypted transport when required by the environment.
- Authorize read/write/operation invocations appropriately; restart/reset/clear actions can alter application behavior.
- Limit exposed MBeans; avoid putting passwords, tokens, or personal data in attributes or notifications.
- Audit state-changing operations, recording target instance, identity, timestamp, and outcome.
- In Kubernetes, prefer temporary, controlled access mechanisms (e.g., restricted management network channels), avoiding uncontrolled shared port forwarding.
- Do not rely on ObjectName or package names as a security mechanism; ObjectName is only an identifier.

Remember: **local registration does not guarantee absolute safety**, and **having a remote connector does not mean everyone can access it**. Effective permissions depend on OS, network, JVM, and JMX configuration layers.

## 10. Comparing Four Access Models

| Model | Where Does the MBean Live? | Access Requirements | Best Fit |
|---|---|---|---|
| Same-JVM code calling MBeanServer | Application JVM | Reference to the right MBeanServer | Internal checks or in-process management integration |
| JConsole/VisualVM local attach | Another JVM on compatible host/namespace | JVM supports local attach; OS permissions and environment allow | Manual diagnostics on dev machines or managed servers |
| JMX remote connector | Application JVM on another or same host | Connector server, endpoint, network, authentication/TLS | Centralized management tools in a trusted network |
| HTTP management endpoint | Application JVM, exported via web contract | HTTP server, route, network, HTTP permissions | Automation/cross-platform tools with clear API contracts |

Both JMX local attach and remote JMX operate on the target MBeanServer through an appropriate connection; they do not transfer copies of Java objects across JVMs.

## 11. MBean Lifecycle and Common Errors

An MBean is a management resource tied to the object/application lifecycle:

- **Registration:** `registerMBean` or Spring `MBeanExporter`.
- **Existence:** discoverable via `queryNames` and accessible per permissions.
- **Unregistration:** `unregisterMBean` or Spring exporter lifecycle.
- **JVM termination:** MBeanServer and all registrations in that JVM disappear.

Errors worth recognizing:

| Symptom | Possible Cause | What to Check |
|---|---|---|
| `InstanceAlreadyExistsException` | Duplicate ObjectName on the same MBeanServer | Check double registration and naming scheme |
| `NotCompliantMBeanException` | Class/interface does not comply with Standard/Dynamic MBean | Check `*MBean` interface, methods, visibility |
| `InstanceNotFoundException` | Wrong ObjectName or already unregistered | Use `isRegistered`, `queryNames` |
| JConsole does not list the JVM | Missing attach permission, different PID/namespace/JDK | Check process, OS, container, and attach |
| Remote connection timeout | Wrong host/port, firewall, NAT, or RMI stub | Check connector URL and end-to-end network |
| Connected but operation denied | Insufficient management permissions | Check authentication/authorization |
| Platform MBeans visible, custom MBean missing | Registered in wrong server, wrong name, or lifecycle not reached | Verify MBeanServer and ObjectName |

## 12. Hands-on Exercise

Create a long-running Java or Spring Framework application registering `JobCounter` at:

\`\`\`text
learning.jmx:type=JobCounter,name=Primary
\`\`\`

Perform step by step:

1. Inside the application JVM itself, call `isRegistered(...)` and read `CompletedJobs`.
2. Open a local JMX tool on the same machine and try finding the `learning.jmx` domain. Note the PID and actual connection type.
3. Run a second JVM with code querying `ManagementFactory.getPlatformMBeanServer()`. Observe that the MBean in the first JVM **does not appear** in the second JVM's platform server without a connector.
4. In a controlled, authorized test environment, try connecting to a preconfigured JMX connector with a JMX client; use `queryNames` and `getAttribute`.
5. Unregister the MBean in the target JVM. Verify the name disappears from the same MBeanServer; if the tool caches data, refresh it.

**Self-check questions:**

- Why can two JVMs register the same ObjectName without conflict?
- What happens if a Spring exporter registers an MBean into a different server than the one JConsole connects to?
- If an application in Docker does not appear in JConsole's local process list, which layer should you inspect first?
- Why should you not open a remote JMX port without authentication/TLS just to observe one MBean?
- A client knows the ObjectName but not the JMX endpoint: does it have enough information to connect?

**Suggested answers:** An ObjectName is only unique within each MBeanServer; tools must connect to the right server; Docker changes namespaces/attach permissions; JMX exposes sensitive management privileges; and ObjectName does not replace the JMX connector endpoint.

## 13. Key Takeaways

- **Register MBean** means registering a managed object in the **JVM's MBeanServer**, not broadcasting it to all processes.
- **Local JVM** code can use MBeanServer directly; **other JVMs** require an actual management connection path.
- **Local JConsole** sometimes connects without configuring a remote port thanks to attach/local management, though it still depends on permissions and environment.
- **Remote JMX** requires a configured connector, proper networking, and security; ObjectName is not a connection address.
- In the Spring Framework, use **MBeanExporter** and specify the MBeanServer explicitly when ensuring MBeans appear in the expected platform server.
- To diagnose issues, verify sequentially: **right JVM → still running → right server → registered → connection authorized → network/protocol**.

## References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Java SE — `MBeanServer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE — `ManagementFactory`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html
- Java SE — JMX Remote API: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/package-summary.html
- Oracle Java Management Extensions Technology: https://docs.oracle.com/javase/8/docs/technotes/guides/jmx/
