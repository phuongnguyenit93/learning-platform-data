# Inspecting the Registry with JConsole or Equivalent JMX Tools

## Objectives

After this lesson, you will be able to identify the `MBeanServer` running in a JVM, open the JMX registry with JConsole or an equivalent tool, inspect an MBean's `ObjectName`, attributes, operations, and metadata, and distinguish MBean registration failures from client connection, authentication, or display issues. Examples focus on Spring Framework JMX while using standard Java Management Extensions (JMX) concepts and APIs.

## 1. What Is the JMX Registry?

`MBeanServer` is where a JVM's Managed Beans (MBeans) are registered and looked up. Each registered MBean is identified by a unique `ObjectName` within **the same** `MBeanServer`, such as:

```text
com.example.monitoring:type=JobMonitor,name=primary
```

An `ObjectName` has the general form `domain:key=value,key=value`; `domain` typically represents the application's namespace, while key properties distinguish types and instances. Tools may normalize the display order of properties, so compare `ObjectName`s by the meaning of their domain and keys rather than relying solely on string ordering.

When opening the **MBeans** tab in JConsole, the left tree displays registered domains and MBeans. Seeing the Java process in the connection list **does not** prove that the application MBean has been registered. You must locate the exact name in the registry and verify the available metadata.

In the Spring Framework, a bean existing in `ApplicationContext` is not guaranteed to appear in JMX either. It must be registered directly with `MBeanServer` or exported by an exporter such as `MBeanExporter` / `AnnotationMBeanExporter`. If the system has multiple `MBeanServer`s or multiple JVMs, make sure the tool is connecting to the server containing the desired MBean.

## 2. Preparing an MBean for Observation

The following example creates a Standard MBean with two attributes and one operation. Create two Java files in the same package.

**JobMonitorMBean.java**

```java
package com.example.monitoring;

public interface JobMonitorMBean {
    int getProcessedCount();
    boolean isEnabled();
    void setEnabled(boolean enabled);
    void reset();
}
```

**JobMonitor.java**

```java
package com.example.monitoring;

import java.util.concurrent.atomic.AtomicInteger;

public class JobMonitor implements JobMonitorMBean {
    private final AtomicInteger processed = new AtomicInteger();
    private volatile boolean enabled = true;

    public void recordProcessedJob() {
        if (enabled) {
            processed.incrementAndGet();
        }
    }

    @Override
    public int getProcessedCount() {
        return processed.get();
    }

    @Override
    public boolean isEnabled() {
        return enabled;
    }

    @Override
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @Override
    public void reset() {
        processed.set(0);
    }
}
```

The `JobMonitorMBean` interface defines the JMX contract: `ProcessedCount` has a getter so it is read-only, `Enabled` has both getter and setter so it is read/write, and `reset` is an operation. The `recordProcessedJob` method is for internal use only; it does not appear as a management operation because it is not declared in the Standard MBean interface.

Registering with the JVM's platform server using the Java JMX API:

```java
package com.example.monitoring;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class JmxRegistryDemo {
    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
                "com.example.monitoring:type=JobMonitor,name=primary");

        JobMonitor monitor = new JobMonitor();
        server.registerMBean(monitor, name);

        System.out.println("PID JVM: " + ProcessHandle.current().pid());
        System.out.println("Registered: " + server.isRegistered(name));

        while (true) {
            monitor.recordProcessedJob();
            Thread.sleep(1000);
        }
    }
}
```

Run the program with the JDK, keeping the process alive so JConsole can connect. The loop here only keeps the example running and generates an easily observable counter; in real applications, metrics should reflect actual business activity. `registerMBean` can throw `NotCompliantMBeanException` if the class does not comply with the Standard MBean contract, or `InstanceAlreadyExistsException` if the name is already registered.

## 3. Connecting with JConsole

JConsole is a JMX monitoring tool included with many JDK distributions. If the JDK and this utility are available, launch it with:

```bash
jconsole
```

In the connection screen:

1. Select **Local Process** and the JVM process running the example. Match the PID printed on stdout if multiple Java processes are running.
2. Click **Connect**. Depending on platform and configuration, the tool may ask to confirm an insecure connection or require process access permissions.
3. Open the **MBeans** tab.
4. In the left tree, expand the `com.example.monitoring` domain.
5. Select the MBean with properties `type=JobMonitor`, `name=primary` (node grouping and ordering may vary across JMX clients).
6. Inspect the **Attributes**, **Operations**, **Info**, or corresponding sections of the UI.

Signs of successful registration: the MBeans tree has the expected entry; the metadata section shows the attributes and operations published by the interface. Some views require clicking **Refresh** or re-selecting the node to see updated data.

If `jconsole` is not in PATH, check `JAVA_HOME/bin/jconsole` and the JDK package in use. Minimal runtime images or container environments may omit GUI tools; in those cases, use a compatible JMX client or verify via the API in the next section.

## 4. Inspecting Attributes, Operations, and Metadata

For the example MBean, JConsole typically displays these elements:

| Group | Name | Meaning | How to Verify |
| --- | --- | --- | --- |
| Attribute | `ProcessedCount` | Number of recorded jobs | Read repeatedly; value increases with the loop |
| Attribute | `Enabled` | Flag allowing job recording | Change to `false`; count stops increasing |
| Operation | `reset` | Resets counter to 0 | Invoke and read back the counter |
| Metadata | Names, types, and access rights | Introspected management contract | Check `int`, `boolean` types, read/write capabilities |

When `Enabled=false`, the process keeps running, yet `recordProcessedJob` does not increment the counter. After `reset`, `ProcessedCount` returns to 0 and will resume incrementing if `Enabled=true`. Click order and invoke buttons vary by JConsole version.

You must distinguish **attributes** from **operations**. A JMX attribute can come from getters/setters; an operation is a method invocable by signature. For example, `reset()` is not a getter and appears under operations. Having a method on the Java class is not enough for it to appear if it is not in the MBean contract.

Do not test changing attributes or invoking operations on a production JVM without understanding their impact. Some operations can mutate real state, reset statistics, or disrupt the service.

## 5. Inspecting the Registry via the JMX API

When a graphical UI cannot be used, you can read the registry inside the JVM through `MBeanServer`:

```java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class InspectJmx {
    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
                "com.example.monitoring:type=JobMonitor,name=primary");

        System.out.println("Registered? " + server.isRegistered(name));

        Set<ObjectName> names = server.queryNames(
                new ObjectName("com.example.monitoring:*"), null);
        for (ObjectName item : names) {
            System.out.println(item.getCanonicalName());
        }

        if (server.isRegistered(name)) {
            MBeanInfo info = server.getMBeanInfo(name);
            for (MBeanAttributeInfo a : info.getAttributes()) {
                System.out.printf(
                        "Attribute: %s type=%s readable=%s writable=%s%n",
                        a.getName(), a.getType(), a.isReadable(), a.isWritable());
            }
            for (MBeanOperationInfo operation : info.getOperations()) {
                System.out.println("Operation: " + operation.getName());
            }
            System.out.println(
                    "Count = " + server.getAttribute(name, "ProcessedCount"));
        }
    }
}
```

**Important scope note:** the code above uses `getPlatformMBeanServer()` of the executing process itself. If you run `InspectJmx` as **a second JVM**, it cannot automatically see MBeans registered in the JVM running `JmxRegistryDemo`. To inspect properly, run this logic **inside the same JVM** (for example in a secure debug endpoint, diagnostic action, or application call), or use `JMXConnector` to connect to a remote JMX server if an endpoint has been configured.

To find all names in an application domain, `queryNames(new ObjectName("com.example.monitoring:*"), null)` returns the set of names matching the pattern. `isRegistered(name)` checks specifically whether a name exists. `getMBeanInfo` returns metadata according to the JMX contract. Having attributes/operations present in metadata proves the MBean server publishes that API, but does not prove every operation will succeed in every runtime state.

## 6. Equivalent JMX Tools

Beyond JConsole, you can use **VisualVM** with MBeans/JMX support appropriate for your version and installed plugins, or another JMX management client capable of browsing the MBean registry. These tools typically provide a list of processes or JMX connections, an `ObjectName` tree, attributes, and operations.

When using an alternative tool, follow the same verification workflow:

1. Identify the exact JVM or JMX service URL, not just a matching service name.
2. Locate the exact domain and key properties in `ObjectName`.
3. Read metadata and compare attribute/operation names and types.
4. Read a side-effect-free attribute and compare it with application state.
5. Only invoke a safe operation in a test environment to confirm requests reach the right MBean.

The Spring Framework does not require a specific JMX viewer. The management communication layer follows the Java JMX contract, so JConsole and compatible clients can access the same registry given the same connection and permissions.

## 7. Spring Framework: How to Know Whether the Exporter Registered?

For Spring beans configured to be exported to JMX:

- Check whether the application configures `MBeanExporter`, `AnnotationMBeanExporter`, or an equivalent mechanism.
- Match the bean name and the `ObjectName` used by the exporter; the name in the Spring container does not automatically determine the JMX domain/keys.
- Ensure the exporter targets the right `MBeanServer`. Applications using the platform server are convenient for JConsole to access per process.
- Check startup for registration errors, duplicate names, or invalid MBeans.
- With Spring Boot, JMX features and auto-export are affected by Boot configuration; check active settings before adding a manual exporter to avoid duplicate registration.

Example Spring Framework configuration registering a Standard MBean:

```java
package com.example.monitoring;

import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class MonitoringJmxConfiguration {
    @Bean
    public JobMonitor jobMonitor() {
        return new JobMonitor();
    }

    @Bean
    public MBeanServer mBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter monitorExporter(
            JobMonitor jobMonitor, MBeanServer mBeanServer) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(mBeanServer);
        exporter.setBeans(Map.of(
                "com.example.monitoring:type=JobMonitor,name=primary",
                jobMonitor));
        return exporter;
    }
}
```

Spring manages the exporter lifecycle; do not simultaneously register the same instance/`ObjectName` via manual `registerMBean` and the exporter in the same application. When using this configuration, run only one registration mechanism to avoid duplicate errors.

## 8. Diagnosing When an MBean Is Not Visible

| Symptom | Possibilities to Check | Action |
| --- | --- | --- |
| Java process not visible | Different OS user, attach permissions, container/host, or JVM stopped | Check PID, user account, runtime environment, and attach policy |
| Connected, but application domain missing | MBean not registered yet, wrong `MBeanServer`, wrong JVM | Check exporter logs, call `isRegistered` inside the right JVM |
| Domain present, but `ObjectName` missing | Different name assigned or registration failed | Use `queryNames`, match domain/keys |
| MBean present, but attribute/operation missing | Interface/metadata does not expose method or naming convention mismatch | Check `*MBean`, getters/setters, annotation metadata |
| `NotCompliantMBeanException` | MBean does not satisfy contract | Check public interface, class/interface names, and exposed types |
| `InstanceAlreadyExistsException` | Duplicate `ObjectName` in server | Change instance name intentionally or fix exporter lifecycle |
| Attribute not writable | No setter or read-only | Check `isWritable()` metadata, verify correct data type |
| Invoke failed | Wrong signature, access permissions, or operation threw an error | Read `MBeanOperationInfo`, check logs and root cause |
| Remote connection refused | Endpoint not enabled, firewall, authentication, or RMI/port config | Verify JMX service URL and network/security settings |

Local and remote JMX have different connection requirements. A successful local connection does not prove access from another machine will work. For remote JMX, configure authentication, encryption, and network restrictions appropriately; avoid opening public management endpoints just to use JConsole.

## 9. Repeatable Verification Procedure

To produce clear evidence for an MBean in a Spring application, record:

1. PID/Java process name and the client tool in use.
2. Full `ObjectName` (domain and key properties).
3. Result of `isRegistered` or its exact position in the registry tree.
4. List of attributes, data types, read/write capabilities, and operations.
5. An actual attribute value before and after a safe test state change.
6. Timestamp and runtime environment, as MBeans can be registered/removed during the application lifecycle.

Do not draw conclusions solely from JConsole being able to open the application. You must verify both MBean identity and the management contract against the expected API.

## 10. Hands-on Exercise

Create two `JobMonitor` instances under the names:

```text
com.example.monitoring:type=JobMonitor,name=primary
com.example.monitoring:type=JobMonitor,name=secondary
```

Open JConsole and verify that both entries exist independently. Change `Enabled=false` on `primary` and observe that `secondary` continues processing with its own state. Record the list of attributes/operations and invoke `reset` on one instance. Next, attempt to register a third MBean with an existing `ObjectName` and explain the error. Finally, run `queryNames` directly inside the application JVM and compare the result with the JConsole tree.

**Key takeaway:** Inspecting the JMX registry means verifying the right JVM, the right `MBeanServer`, the right `ObjectName`, and the right MBean metadata/values. JConsole provides a convenient UI, while the JMX API lets you automate the exact same verification checks.
