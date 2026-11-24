# jcmd, JVM Flags, and Their Relationship with JMX

## 1. Objectives

When operating a Java/Spring Framework application, we commonly encounter three groups of tools and mechanisms:

- **\`jcmd\`**: a command-line tool that sends *diagnostic commands* to a running JVM.
- **JVM flags/system properties**: JVM startup parameters or diagnostic options that control certain JVM behaviors, including the management agent and remote JMX.
- **JMX (Java Management Extensions)**: an API and infrastructure that allows reading attributes and invoking management operations via an \`MBeanServer\`, either through a local client or a remote connector.

They are closely related but not synonymous. A JVM may allow \`jcmd\` to connect locally even when remote JMX is not enabled. An application may register MBeans in the platform MBeanServer even without a network endpoint. Conversely, opening a remote JMX port does not guarantee that Spring beans have been exported as MBeans.

After this lesson, you can:

1. Distinguish \`jcmd\` diagnostic commands from JMX operations/attributes.
2. List JVM processes and query the commands supported by each JVM.
3. Use \`jcmd\` to inspect the command line, system properties, flags, threads, and heap for the right purpose.
4. Understand the role of \`-Dcom.sun.management.jmxremote.*\`, \`-Djava.rmi.server.hostname\`, and other JVM flags.
5. Describe the path from the Spring JMX exporter to the MBeanServer and JMX client.
6. Isolate faults across local attach, JVM options, remote connector, RMI, networking, and Spring export.
7. Use diagnostic tools in a controlled manner without exposing management channels to the Internet.

## 2. Mental Model: Three Ways to Observe the Same JVM

\`\`\`text
                             JAVA / SPRING APPLICATION
                                      |
                    +-----------------+------------------+
                    |                                    |
             JVM diagnostics                      Platform MBeanServer
                    |                                    |
               Attach API                         JVM built-in MBeans
                    |                            + Spring-exported MBeans
                 jcmd PID                                 |
                    |                         +-----------+-------------+
                    |                         |                         |
             diagnostic commands         local JMX client           JMX connector
             (Thread.print, GC.*,        (JConsole, tooling)           |
              VM.flags, ...)                                      RMI/network/TLS/auth
                                                                       |
                                                                 remote JMX client
\`\`\`

All three paths can answer the same operational question, such as "How much heap is the JVM using?"; however, **their inputs, required permissions, connection mechanisms, and outputs** differ.

| Mechanism | Target Interacted With | Example | Characteristics |
|---|---|---|---|
| \`jcmd\` | Diagnostic command handler inside the target JVM | \`jcmd <pid> VM.flags\` | Typically via the local attach mechanism |
| JVM startup flags | The JVM at startup | \`-Xmx512m\`, \`-D...\` | Can determine initial configuration |
| JMX | MBeanServer and registered MBeans | \`getAttribute\`, \`invoke\` | Management API with metadata and ObjectNames |
| Remote JMX | Connector to MBeanServer | JConsole via service URL | Requires dedicated network and security configuration |

Do not infer that "running \`jcmd\` works" means the remote JMX port is open, or that "having remote JMX" means you can execute every diagnostic command.

## 3. What Is the jcmd Tool?

\`jcmd\` is distributed with the JDK. Common syntax:

\`\`\`text
jcmd [<pid> | <main-class>] <command> [arguments]
\`\`\`

Practical usage:

\`\`\`bash
jcmd -l
jcmd 12345 help
jcmd 12345 VM.version
jcmd 12345 VM.command_line
jcmd 12345 VM.flags
\`\`\`

\`12345\` is an example PID—replace it with the actual PID. When running \`jcmd -l\`, available JVM processes can be listed depending on the OS, permissions, and JVM attach mechanism. A JVM running in a different container, namespace, or under a different user may not appear in the list.

### 3.1. Why Check \`help\` per PID?

Available diagnostic commands vary by JDK release, vendor, build, and JVM settings; some commands are conditional or have operational impact. Therefore, instead of copying a "guaranteed command list," ask the target JVM directly:

\`\`\`bash
jcmd <pid> help
jcmd <pid> help Thread.print
jcmd <pid> help GC.heap_dump
\`\`\`

\`help <command>\` describes the actual syntax and options supported by that JVM.

### 3.2. Commonly Used Commands

| Diagnostic command | Main purpose | Use case |
|---|---|---|
| \`VM.version\` | View JVM information | Identify JDK version/vendor |
| \`VM.command_line\` | View JVM startup command line | Check JVM options and classpath/module path |
| \`VM.flags\` | View JVM flags | Verify current active values |
| \`VM.system_properties\` | View Java system properties | Confirm \`-D...\` or runtime properties |
| \`Thread.print\` | Print thread dump | Diagnose deadlocks, blocked threads |
| \`GC.heap_info\` | Heap information | Observe memory usage |
| \`GC.class_histogram\` | Instance statistics by class | Investigate memory consumption |
| \`GC.heap_dump\` | Write heap dump to a file | Deep memory issue analysis |
| \`JFR.start\` / \`JFR.dump\` | Control Java Flight Recorder when supported | Record time-based diagnostic data |
| \`ManagementAgent.status\` | Management agent status when supported | Check management/JMX agent |
| \`ManagementAgent.start\` / \`start_local\` / \`stop\` | Control management agent when supported | Lab or authorized operations |

**Note:** some commands such as heap dump or histogram can cause noticeable pauses, consume CPU/disk space, and generate files containing sensitive data. Use them only when you understand their impact and have operational authorization.

## 4. Practicing jcmd on a Small Java Application

A plain Java example to keep a process alive for observation:

\`\`\`java
// DemoJvm.java
public class DemoJvm {
    public static void main(String[] args) throws Exception {
        System.out.println("PID = " + ProcessHandle.current().pid());
        System.out.println("Application is running...");
        Thread.sleep(300_000);
    }
}
\`\`\`

Compile and start with the JDK:

\`\`\`bash
javac DemoJvm.java
java -Xms64m -Xmx256m -Ddemo.environment=lab DemoJvm
\`\`\`

Open another terminal, use the PID printed by the program or run:

\`\`\`bash
jcmd -l
\`\`\`

Next, replace \`<pid>\` with the actual PID:

\`\`\`bash
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
jcmd <pid> VM.system_properties
jcmd <pid> Thread.print
jcmd <pid> GC.heap_info
\`\`\`

Observations to check yourself:

- \`VM.version\` returns the running JVM version details.
- \`VM.command_line\` helps identify how the process was started.
- \`VM.flags\` shows applied JVM flags; it does not necessarily reflect every \`-D\` system property.
- \`VM.system_properties\` contains the property \`demo.environment=lab\`.
- \`Thread.print\` shows the \`main\` thread sleeping.
- \`GC.heap_info\` displays memory data according to the active collector/JDK.

Do not use \`VM.flags\` as the sole place to verify \`-Dcom.sun.management.*\`: those are system properties, so \`VM.system_properties\` and the command line are usually more appropriate.

## 5. Distinguishing JVM Flags from System Properties

It is easy for learners to lump every \`java ...\` parameter under one concept called "JVM flag." Technically, you should distinguish them:

### 5.1. JVM Options

\`\`\`bash
java -Xms128m -Xmx512m -XX:+UseG1GC DemoJvm
\`\`\`

\`-Xms\`, \`-Xmx\`, and \`-XX:...\` are options controlling the JVM. Valid options depend on the JVM version and vendor. \`jcmd <pid> VM.flags\` helps view many current flags; \`VM.command_line\` shows how it was started.

### 5.2. Java System Properties

\`\`\`bash
java -Ddemo.environment=lab -Dfeature.enabled=true DemoJvm
\`\`\`

\`-Dkey=value\` creates a Java system property, readable via:

\`\`\`java
String env = System.getProperty("demo.environment");
\`\`\`

This information can also be viewed via:

\`\`\`bash
jcmd <pid> VM.system_properties
\`\`\`

The \`com.sun.management.jmxremote.*\` settings are passed as **system properties** with the \`-D\` prefix. They relate to the management agent/JMX connector; do not call them \`-XX\` flags.

### 5.3. Not Every Setting Can Be Changed While the JVM Is Running

Some VM flags may support dynamic changes in the JVM; many others require a restart and have strict value ranges. Java code can modify a system property, but that **does not mean the management agent automatically re-reads it and reconfigures its endpoint**. For remote JMX, use the management agent mechanisms supported by the JVM and verify the actual state; if changing startup properties, a JVM restart with the new configuration is typically needed.

## 6. Where Does JMX Operate Inside the JVM?

The JVM provides built-in platform MXBeans, such as:

- \`java.lang:type=Memory\` for memory.
- \`java.lang:type=Threading\` for threads.
- \`java.lang:type=Runtime\` for runtime details.
- \`java.lang:type=ClassLoading\` for class loading.
- \`java.lang:type=OperatingSystem\` for OS/JVM information.

These MBeans can be accessed via \`ManagementFactory.getPlatformMBeanServer()\` within the same JVM:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class ReadMemoryMBean {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName memory =
            new ObjectName("java.lang:type=Memory");

        Object heapUsage =
            server.getAttribute(memory, "HeapMemoryUsage");

        System.out.println(heapUsage);
    }
}
\`\`\`

The \`HeapMemoryUsage\` value is represented as JMX Open Data when accessed through the generic MBeanServer API, typically as \`CompositeData\`; do not assume it is always a raw Java \`MemoryUsage\` object when using this API path.

**Distinction:** \`jcmd <pid> GC.heap_info\` and \`server.getAttribute(memory, "HeapMemoryUsage")\` both relate to the heap, but they go through two different APIs and data structures. Do not treat a diagnostic command as an MBean operation with the same name.

## 7. Which Layer Does Spring Framework JMX Sit At?

Spring Framework provides integration to export Spring-managed objects via JMX. Common components:

- \`@ManagedResource\` identifies a managed bean/resource.
- \`@ManagedAttribute\` exposes an attribute.
- \`@ManagedOperation\` exposes an operation.
- \`MBeanExporter\` registers beans with an \`MBeanServer\`.
- \`@EnableMBeanExport\` can enable annotation-driven export configuration.

Illustrative example:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "training.spring:type=Worker,name=Primary",
    description = "Worker runtime status")
public class WorkerStatus {
    private volatile boolean enabled = true;

    @ManagedAttribute
    public boolean isEnabled() {
        return enabled;
    }

    @ManagedAttribute
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
\`\`\`

With a properly configured JMX export setup, the MBean can be found using JConsole or a JMX client.

\`\`\`text
Spring bean
   ↓
Spring MBeanExporter / annotation metadata
   ↓
JVM MBeanServer
   ↓
Local JMX client or remote connector
\`\`\`

**MBeanExporter does not automatically open a remote JMX TCP port.** Remote access requires an appropriate connector/agent and separate security policies. At the same time, being able to run \`jcmd\` does not prove a Spring bean has been exported; you must check the actual ObjectName.

## 8. Local Attach, Local JMX, and Remote JMX

### 8.1. Local Attach

\`jcmd\` typically interacts with a JVM on the same host via the attach mechanism. Attach capability depends on the user/process owner, OS permissions, namespace/container, JDK/JVM implementation, and security configuration. Some JVMs may be started with an option restricting attach, such as \`-XX:+DisableAttachMechanism\` on HotSpot when supported.

Do not assume \`jcmd\` will work for every PID just because the process exists.

### 8.2. Local JMX

JConsole can connect to a local JVM via the attach/management agent mechanism supported by the JDK. From there, users see platform MBeans and application-registered MBeans.

\`\`\`bash
jconsole
\`\`\`

In the GUI, select an accessible Java process. Some local JMX cases require the management agent to be enabled or initialized; conditions vary by JDK, process, and permissions.

### 8.3. Remote JMX

Remote JMX requires a network-listening connector or an equivalent remote access mechanism. In HotSpot JDKs, the \`com.sun.management.jmxremote.*\` system properties are commonly used to configure the management agent supporting JMX/RMI.

Key setting groups:

| Property | Meaning |
|---|---|
| \`com.sun.management.jmxremote\` | Enables the management agent using the JVM-supported mechanism |
| \`com.sun.management.jmxremote.port\` | RMI registry port for remote monitoring |
| \`com.sun.management.jmxremote.rmi.port\` | RMI connector server port to avoid dynamic ports |
| \`java.rmi.server.hostname\` | Host/IP advertised by the RMI stub to clients |
| \`com.sun.management.jmxremote.authenticate\` | Authentication setting for the remote agent |
| \`com.sun.management.jmxremote.ssl\` | SSL/TLS setting for the remote agent |
| \`com.sun.management.jmxremote.password.file\` | Source of credentials when using a password file |
| \`com.sun.management.jmxremote.access.file\` | Access control policy when using an access file |

Valid settings and values must be checked against the documentation of **the deployed JDK version**. Remote JMX should only be enabled on a protected management network.

### 8.4. Why Can RMI Use Multiple Ports?

JMX/RMI usually involves a lookup step via the RMI registry followed by connecting to the advertised remote object. If the connector server port is chosen dynamically, a firewall may allow the registry yet block the subsequent connection. In addition to the port, \`java.rmi.server.hostname\` must point to an address the client can actually reach.

Common JMX/RMI URL example:

\`\`\`text
service:jmx:rmi:///jndi/rmi://jmx.internal.example:9010/jmxrmi
\`\`\`

This URL specifies where to look up the connector in the registry. It does not guarantee that the internal RMI stub advertises that same hostname/port.

## 9. Using jcmd to Inspect the Management Agent

Some JDK/HotSpot distributions provide these commands:

\`\`\`bash
jcmd <pid> help ManagementAgent.status
jcmd <pid> ManagementAgent.status
\`\`\`

If supported by the JVM, \`ManagementAgent.status\` lets you inspect the agent status. Depending on the version, \`ManagementAgent.start\`, \`ManagementAgent.start_local\`, or \`ManagementAgent.stop\` may allow starting/stopping management components.

**Do not run \`ManagementAgent.start\` on a production JVM just to experiment.** This command can alter management state and accessibility. First run \`help\`, and understand the syntax, permissions, ports, TLS/authentication, and operational impact.

Instead of assuming the agent is running from a single \`-D\` property, combine observations:

1. \`VM.command_line\` for startup configuration.
2. \`VM.system_properties\` for current property values.
3. \`ManagementAgent.status\` if available.
4. Actual JMX connection test from an authorized client.
5. Verification of the expected MBean ObjectName.

The presence of a property alone is not enough to prove remote clients can connect.

## 10. Comparing the Same Concern Using jcmd and JMX

### 10.1. Heap Memory

\`\`\`bash
jcmd <pid> GC.heap_info
\`\`\`

Via JMX:

\`\`\`java
Object usage = connection.getAttribute(
    new ObjectName("java.lang:type=Memory"),
    "HeapMemoryUsage");
\`\`\`

Both let you observe memory, though the data and presentation may differ.

### 10.2. Threads

\`\`\`bash
jcmd <pid> Thread.print
\`\`\`

Via JMX, \`java.lang:type=Threading\` provides thread-related attributes/operations. A client can call \`ThreadMXBean\` through a proxy or the JMX API, but there is no reason to expect an MBean operation named \`Thread.print\`.

### 10.3. JVM Arguments

\`\`\`bash
jcmd <pid> VM.command_line
\`\`\`

Via Java/JMX, RuntimeMXBean can provide input arguments:

\`\`\`java
var runtime = java.lang.management.ManagementFactory
    .getRuntimeMXBean();
System.out.println(runtime.getInputArguments());
\`\`\`

Both approaches suit different purposes. Command and argument data may contain sensitive information; avoid logging or sharing it verbatim in real environments.

### 10.4. Spring Business MBeans

\`\`\`text
training.spring:type=Worker,name=Primary
\`\`\`

This business MBean is exported by Spring (when configured properly). \`jcmd\` does not turn every Spring \`@ManagedAttribute\` into a diagnostic command. To read \`Enabled\`, use a JMX client:

\`\`\`java
connection.getAttribute(
    new ObjectName("training.spring:type=Worker,name=Primary"),
    "Enabled");
\`\`\`

## 11. Layered Troubleshooting Workflow

When JMX does not behave as expected, identify the failing layer first.

### Scenario A: \`jcmd -l\` Does Not List the JVM

Check same host/container namespace, user permissions, JDK tools, PID, and attach mechanism. If the JVM runs inside a container, you may need to run the tool inside the same namespace/container per operational policy. Do not default to blaming Spring.

### Scenario B: \`jcmd <pid> ...\` Fails to Attach

Check whether the process is running, OS permissions, process owner, filesystem/temp directory, attach capability, security policies, and JVM flags disabling attach. Some commands may not be supported by the target JVM even if attach succeeds.

### Scenario C: jcmd Works, JConsole Does Not See the Spring MBean

Check \`MBeanExporter\`, \`@EnableMBeanExport\`, annotation metadata, \`ObjectName\`, and target MBeanServer. \`jcmd\` and JMX export are two independent mechanisms.

### Scenario D: Local JConsole Sees the MBean, Remote JConsole Fails

Verify the remote connector/agent is enabled; inspect agent status, registry and RMI server ports, advertised hostname, firewall/routing, authentication, TLS, and truststore. Do not open only the first port and conclude the RMI configuration is correct.

### Scenario E: Remote Client Connects but Operation Fails

Distinguish missing ObjectName, mismatched method signature, insufficient permissions, or an exception thrown by the MBean execution. Check metadata via \`getMBeanInfo\`; do not blame the network when the JMX connection itself has succeeded.

### Scenario F: JVM Flag Configuration Is Not as Expected

Compare the startup command line, \`VM.flags\`, \`VM.system_properties\`, and configuration passed by the process manager/container. An argument may be overridden or misplaced on the command line. With \`java\`, JVM options typically must appear before the main class or \`-jar\` to be processed by the JVM.

## 12. Practice: From jcmd to JMX on the Same JVM

### Practice 1 — JVM Diagnostics

1. Run \`DemoJvm\` with \`-Xmx256m -Ddemo.environment=lab\`.
2. Use \`jcmd -l\` to find the PID.
3. Run \`VM.command_line\`, \`VM.flags\`, and \`VM.system_properties\`.
4. Identify which entries are JVM flags and which are Java system properties.
5. Run \`Thread.print\` to locate the main thread.

**Completion criteria:** you can explain the source of each value without confusing \`-D\` with \`-XX\`.

### Practice 2 — Inspecting a Platform MBean

1. Start a simple JVM using \`ManagementFactory.getPlatformMBeanServer()\`.
2. Print the \`ObjectName\` of \`java.lang:type=Memory\`.
3. Read \`HeapMemoryUsage\` via \`MBeanServerConnection\`.
4. Observe memory using \`jcmd GC.heap_info\`.
5. Explain the difference between a diagnostic command and an MBean attribute.

**Completion criteria:** understand that two observation channels for the same JVM can represent data differently.

### Practice 3 — Spring JMX

1. Create the \`WorkerStatus\` Spring bean.
2. Enable appropriate JMX export.
3. Connect local JConsole to the JVM.
4. Confirm \`training.spring:type=Worker,name=Primary\` appears.
5. Modify \`Enabled\` via JMX and verify the value.

**Completion criteria:** distinguish Spring exporting MBeans from the JDK managing the process.

### Practice 4 — Analyzing Remote JMX on Paper

Suppose the registry is on port 9010 and the RMI server is on port 9011, advertised with hostname \`jmx.internal.example\`. Diagram the connection path of a client in the management network and list:

- The registry and RMI server ports the firewall must allow.
- The DNS name or address in the RMI stub that the client must be able to resolve.
- Authentication, encryption, and source-host restriction measures.
- The \`jcmd\`/observation commands needed to verify whether the agent is enabled.
- A valid, non-mutating connection test that does not alter business state.

You do not need to open a live endpoint to understand the RMI architecture. When practicing in a lab, use an isolated environment and proper security configuration.

## 13. Common Misconceptions

| Misconception | Correct Understanding |
|---|---|
| "jcmd is a JMX command-line client for all MBeans." | jcmd runs diagnostic commands; it is not a general client for every MBean operation |
| "Enabling Spring JMX opens a remote port." | Spring exports to an MBeanServer; the remote connector is a separate configuration |
| "All \`-D...\` arguments are \`-XX\` JVM flags." | \`-D\` defines Java system properties |
| "\`jcmd -l\` must see every JVM on the host." | It is subject to permissions, namespaces, attach, and implementation limits |
| "Having \`jmxremote.port\` guarantees connectivity." | RMI endpoint, hostname, firewall, TLS, and authentication also matter |
| "Remote JMX connection fails so the MBean doesn't exist." | The MBean may still exist on the local MBeanServer |
| "Taking a heap dump is a lightweight read operation." | A heap dump can consume significant resources and contain sensitive data |
| "If \`VM.system_properties\` changed, the management agent reconfigures itself." | A supported agent mechanism or intentional restart/reconfiguration is required |

## 14. Self-Check Questions

1. What is the programmatic interface difference between jcmd and JMX?
2. What types of information do \`VM.flags\` and \`VM.system_properties\` provide?
3. Why can a Spring MBean exist even when no remote JMX port is open?
4. Why might remote JMX over RMI need to traverse two endpoints?
5. Which connection step does \`java.rmi.server.hostname\` affect?
6. When jcmd fails to attach, what factors should you check?
7. Why can't you use \`jcmd\` to arbitrarily invoke a \`@ManagedOperation\`?
8. When a remote client connects but cannot see an ObjectName, which layer is the issue in?
9. What are the operational risks of \`GC.heap_dump\` and \`VM.system_properties\`?
10. To verify that remote JMX is active, what evidence do you need beyond startup flags?

## 15. References

- Oracle JDK 21 — \`jcmd\` tool: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle JDK 21 — Monitoring and Management: https://docs.oracle.com/en/java/javase/21/management/
- Java SE 21 — \`ManagementFactory\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html
- Java SE 21 — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html

**Key takeaway:** \`jcmd\` diagnoses the JVM using diagnostic commands; JVM flags and system properties adjust startup configuration or runtime behavior; JMX provides a management contract through MBeanServer. When troubleshooting, verify the right layer and gather evidence from the target JVM before changing configuration or opening network access.
