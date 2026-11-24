# Export and Unexport Lifecycle When Spring Context Starts and Stops

## Learning Objectives

After this lesson, you will be able to:

- Describe when the Spring Framework registers (exports) a bean as a JMX MBean when ApplicationContext starts.
- Explain why MBeans must be unregistered (unexported) when the context closes and when lifecycle must be managed manually.
- Distinguish the lifecycles of a Spring bean object, MBeanExporter, MBeanServer, and MBean registration.
- Understand how ObjectName, RegistrationPolicy, and ApplicationContext lifecycle affect duplicate registration errors.
- Write Java configuration for MBeanExporter and observe registration/unregistration using MBeanServer.
- Avoid MBean leaks or operating on the wrong instance when the application restarts, runs multiple contexts, or uses a shared MBeanServer.

## 1. What Are Export and Unexport Really?

In the Spring Framework, **JMX export** is the process of registering a Spring-managed bean or a management object created from that bean into an **MBeanServer**. After exporting succeeds, JMX tools can locate the MBean by ObjectName, read attributes, or invoke exposed operations.

**Unexport** is unregistering the MBean from the MBeanServer. This removes the management name from the registry; it does not necessarily mean the Java object is immediately destroyed, the JVM terminates, or all JMX connectors shut down.

Diagram:

\`\`\`text
Spring ApplicationContext
        |
        | initializes beans + MBeanExporter
        v
MBeanExporter
        |
        | registers into MBeanServer
        v
MBeanServer
        |
        | ObjectName -> MBean exposed
        v
JConsole / JMX client
        |
        | ApplicationContext closes
        v
MBeanExporter unregisters
        |
        v
ObjectName is no longer in registry
\`\`\`

Two questions must be separated:

1. **Does the Java object still exist?** Depends on bean lifecycle, references, garbage collection, and the JVM.
2. **Can a JMX client still find the MBean by ObjectName?** Depends on registration/unregistration with the MBeanServer.

Unexport directly affects the second question.

## 2. Related Objects and Lifecycles

| Component | Responsibility | Typical Lifecycle |
|---|---|---|
| ApplicationContext | Creates and manages beans, handles context closing | From refresh to close |
| Spring-managed bean | Holds managed logic/state | According to Spring scope and configuration |
| MBeanExporter | Selects beans, creates/registers management interfaces, tracks registrations for cleanup | Infrastructure bean in the context |
| MBeanServer | JMX registry and API | Typically lives with the JVM, may be shared by multiple contexts |
| ObjectName | Identifies an MBean within an MBeanServer | Valid while registration exists |
| JMX connector/client | Allows tools to access MBeanServer | Has its own connection lifecycle, independent of exporter |

In a typical Java application, the platform MBeanServer is obtained via:

\`\`\`java
MBeanServer platformServer =
        ManagementFactory.getPlatformMBeanServer();
\`\`\`

The platform MBeanServer typically lives alongside the JVM. When a Spring context closes, the platform MBeanServer can still exist, and the JVM's platform MBeans remain present. Only registrations managed by the corresponding exporter fall within that exporter's cleanup scope.

## 3. When the Context Starts, When Does Exporting Happen?

In common configurations, MBeanExporter is an infrastructure Spring bean. It participates in ApplicationContext initialization and registers MBeans once the relevant beans are ready.

Conceptual flow:

1. The application creates or refreshes ApplicationContext.
2. Spring parses configuration and creates the required beans.
3. Spring initializes MBeanExporter and supplies MBeanServer, the map of objects to export, assembler, and naming strategy if any.
4. MBeanExporter registers the selected objects under their ObjectNames.
5. ApplicationContext becomes ready for the application and JMX clients to interact with the registered MBeans.

Do not confuse a bean being **initialized** with that MBean having been **exported**. An application can create a bean successfully yet fail to export it due to a duplicate ObjectName, an unsuitable MBeanServer, or an invalid JMX contract.

### Are Beans Created Before or After Export?

An object must exist in order to be registered, but the exact ordering across different beans also depends on the dependency graph, lazy initialization, exporter configuration, and proxy mechanisms. If code wants to use an MBean during another startup step, explicitly declare the dependency order or check registration rather than assuming every MBean is ready from the very start of refresh.

### Difference Between Container Running and MBean Ready

A log line saying "Spring context initialized" or "web server started" is not sufficient proof that every desired MBean has been registered. The direct way to verify is calling:

\`\`\`java
server.isRegistered(objectName)
\`\`\`

on the exact MBeanServer that the exporter uses.

## 4. Spring Framework Configuration Example with MBeanExporter

We build a Standard MBean, register it via MBeanExporter, and observe registration status.

### 4.1. Management Interface

File CacheMonitorMBean.java:

\`\`\`java
package example.jmx;

public interface CacheMonitorMBean {
    int getEntryCount();
    void clear();
}
\`\`\`

### 4.2. Implementation

File CacheMonitor.java:

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicInteger;

public class CacheMonitor implements CacheMonitorMBean {
    private final AtomicInteger entryCount =
            new AtomicInteger(10);

    @Override
    public int getEntryCount() {
        return entryCount.get();
    }

    @Override
    public void clear() {
        entryCount.set(0);
    }
}
\`\`\`

Here the MBean interface exposes the EntryCount attribute and the clear() operation. This is only an illustrative model. In a real system, clearing a cache must hook into the actual cache and enforce access control.

### 4.3. Exporter Configuration

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

@Configuration
public class JmxExportConfig {

    @Bean
    public CacheMonitor cacheMonitor() {
        return new CacheMonitor();
    }

    @Bean
    public MBeanExporter cacheMBeanExporter(CacheMonitor monitor) {
        MBeanExporter exporter = new MBeanExporter();

        exporter.setServer(
                ManagementFactory.getPlatformMBeanServer()
        );

        exporter.setBeans(Map.of(
                "learning.jmx:type=CacheMonitor,name=Primary",
                monitor
        ));

        exporter.setRegistrationPolicy(
                RegistrationPolicy.FAIL_ON_EXISTING
        );

        return exporter;
    }
}
\`\`\`

Notes:

- setServer() explicitly chooses the platform MBeanServer.
- setBeans() maps an ObjectName to the bean to export.
- CacheMonitor and CacheMonitorMBean follow the Standard MBean convention.
- FAIL_ON_EXISTING defines the behavior when the name is already taken.

Registration is managed by the exporter. Do not simultaneously call registerMBean() manually for the same name, as that easily causes duplicate registrations.

### 4.4. Creating and Closing ApplicationContext

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class JmxLifecycleDemo {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
                "learning.jmx:type=CacheMonitor,name=Primary"
        );

        System.out.println(
                "Before context: " + server.isRegistered(name)
        );

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                        JmxExportConfig.class)) {

            System.out.println(
                    "After refresh: " + server.isRegistered(name)
            );
        }

        System.out.println(
                "After close: " + server.isRegistered(name)
        );
    }
}
\`\`\`

When there are no external duplicate registrations and the exporter operates normally, the expected output is:

\`\`\`text
Before context: false
After refresh: true
After close: false
\`\`\`

This is the **expected result in an isolated test environment**. If the JVM already has an MBean at that ObjectName, the first line can be true and the FAIL_ON_EXISTING policy can cause refresh to fail.

The example wraps the context in try-with-resources so close() is called even if an error occurs after the context finishes starting.

## 5. When the Context Closes, How Does Unexport Happen?

The Spring Framework provides cleanup callbacks for lifecycle-managed beans. MBeanExporter performs cleanup when the exporter itself is destroyed, including unregistering MBeans within the scope it tracks.

Typical flow:

\`\`\`text
context.close()
    |
    v
Spring runs shutdown callbacks
    |
    v
MBeanExporter cleanup
    |
    v
unregisters MBeans managed by exporter
    |
    v
MBeanServer.isRegistered(name) -> false
\`\`\`

Unregistering enables:

- Releasing the ObjectName so a new context can register it.
- Preventing clients from continuing to operate on an MBean belonging to a closed context.
- Avoiding keeping unnecessary references in the registry.
- Clarifying which instance owns the management interface.

However, unexporting does not automatically guarantee that **every thread, socket, resource, or task** of the business bean has stopped. Those resource lifecycles are managed by the bean itself, container, executor, or corresponding component.

### close vs. Process Shutdown

If ApplicationContext closes while the JVM stays running, unregistering is critical. When the entire JVM exits, the process's MBeanServer disappears as well, yet letting Spring clean up properly whenever possible is still good practice. An application flow might recreate a context without restarting the JVM; in that case, lingering old registrations will cause conflicts if cleanup did not occur.

### Abnormal Termination

If the JVM is killed immediately, loses power, or crashes, destroy callbacks are not guaranteed to run. The MBeanServer disappears with the process, so the registry in the JVM heap does not need an unregister operation after a crash. However, resources or registrations **outside the JVM** may need separate cleanup mechanisms; MBeanExporter does not replace those mechanisms.

## 6. RegistrationPolicy and Duplicate Name Handling

When MBeanExporter attempts to register an ObjectName that already exists in the same MBeanServer, behavior depends on RegistrationPolicy.

Three key policies:

| Policy | Meaning | Scenario |
|---|---|---|
| FAIL_ON_EXISTING | Throws an error when the name already exists | Wanting to catch duplicate configuration/wrong ownership |
| IGNORE_EXISTING | Skips the new registration if the name already exists | Wanting to preserve the existing MBean without replacing it |
| REPLACE_EXISTING | Replaces the existing MBean with the new registration | Only use when ownership and impact are clearly understood |

**FAIL_ON_EXISTING** is generally helpful when learning about lifecycle because it immediately exposes registration leaks. If a new context fails to refresh due to InstanceAlreadyExistsException, determine which MBean is still holding the ObjectName.

**IGNORE_EXISTING** does not mean the new MBean was exported successfully. If the name is already held by another context, clients continue interacting with the existing MBean.

**REPLACE_EXISTING** can impact an MBean belonging to another component/context if both share the same MBeanServer. Do not use it as a default way to mask duplicate-name errors.

One important note: when an exporter ignores an existing registration, do not assume it owns or has the right to remove the skipped MBean. Cleanup scope must be evaluated against the actual registry and exporter behavior.

## 7. ObjectName and Managing Multiple ApplicationContexts

One JVM can contain multiple ApplicationContexts, for example:

- Parent context and child web context.
- Multiple contexts created by a test suite.
- One Java host containing multiple application modules.
- A new context refreshed in the same JVM before the old context has closed.

If the contexts share the platform MBeanServer and both export:

\`\`\`text
learning.jmx:type=CacheMonitor,name=Primary
\`\`\`

then they will collide on ObjectName.

Design approach:

1. Determine which context actually owns the management interface.
2. Export MBeans at one consistent context level.
3. Prevent parent/child contexts' exporters from scanning duplicate beans.
4. Choose ObjectNames distinct enough by service, module, or instance when multiple instances genuinely need to coexist.
5. Close the old context cleanly before opening a new context using the same name.
6. If using multiple MBeanServers, know clearly which server clients connect to.

Example of two distinct names:

\`\`\`text
learning.jmx:type=CacheMonitor,application=Billing,name=Primary
learning.jmx:type=CacheMonitor,application=Shipping,name=Primary
\`\`\`

The chosen name must be unique in the MBeanServer and clearly structured. There is no need to add a random ID on every startup if doing so makes it hard for tooling to locate the MBean again; choose a naming scheme tied to the deployment structure.

## 8. MBeanExporter Lifecycle Differs from MBeanServer Lifecycle

An MBeanExporter is a **Spring infrastructure object**. It uses an existing MBeanServer or one located/created by configuration. Yet when the exporter is destroyed, that does not mean the entire MBeanServer is destroyed.

For example:

\`\`\`java
MBeanServer server =
        ManagementFactory.getPlatformMBeanServer();
\`\`\`

This is the JVM's platform server. Platform MBeans such as memory, threads, or class loading can still exist even after a Spring context closes.

When verifying cleanup, do not assert that the total MBean count on the server must equal 0. Check the specific **ObjectNames managed by your context**.

\`\`\`java
boolean registered = server.isRegistered(
    new ObjectName("learning.jmx:type=CacheMonitor,name=Primary")
);
\`\`\`

The server-wide MBean count can change because of many other components and does not accurately reflect the lifecycle of a single bean.

## 9. Exporting and Spring Bean Lifecycle

Spring has many lifecycle callbacks such as constructors, dependency injection, BeanPostProcessors, init callbacks, ApplicationContext refresh, ContextClosedEvent, and destroy callbacks.

Do not assume the order of every callback in the system will always suit an independent piece of code accessing JMX. The safe design approach is declaring dependencies clearly and specifying when consumers begin needing the MBean.

### What happens if a bean is lazy?

A lazy bean may not be created until requested. If MBeanExporter is configured with a direct reference/mapping to the object/bean, exporting can influence initialization timing. Exact behavior depends on exporter configuration and reference style; do not assume every lazy bean is guaranteed to be exported right after context refresh.

When the goal is exporting MBeans at startup, configure dependencies and the exporter appropriately, then verify with isRegistered().

### What happens with prototype beans?

Prototype beans do not have the same automatic destroy-callback semantics as singletons. If you manually register a prototype object into MBeanServer, ensure someone owns and unregisters that object. Do not rely entirely on prototype lifecycle for unregistration.

An MBeanExporter with a defined set of managed resources can manage their registrations; however, if the application actively registers prototype/new instances outside the exporter, cleanup responsibility remains with the registering code.

### What if a bean reference changes?

MBeanServer can hold a reference to the registered object. If an internal component is swapped for another instance, ObjectName does not automatically point to the new instance unless there is a re-registration mechanism or an appropriately behaving wrapper/proxy.

Distinguish updating state inside an MBean from replacing the MBean object itself.

## 10. Manual Registration vs. Spring-Managed Export

### 10.1. Manual Registration

\`\`\`java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName("learning.jmx:type=Manual,name=One");

server.registerMBean(manualBean, name);
\`\`\`

When using this approach, **your code** is responsible for unregistering:

\`\`\`java
server.unregisterMBean(name);
\`\`\`

If a Spring bean registers an MBean itself in an init callback without unregistering on destroy, there is a risk of leaving the registration behind when the context closes while the JVM stays alive.

### 10.2. Spring's MBeanExporter

\`\`\`java
exporter.setBeans(Map.of(
        "learning.jmx:type=CacheMonitor,name=Primary",
        cacheMonitor
));
\`\`\`

The exporter tracks the registrations it manages and performs corresponding cleanup on destroy. This is usually a clearer assignment of responsibility when the MBean belongs to the Spring ApplicationContext.

### 10.3. Avoiding Double Registration

Do not both configure MBeanExporter for the same ObjectName and manually call registerMBean() in @PostConstruct for that same object, unless there is a clear reason and coordination mechanism.

Duplicate registration can lead to:

- InstanceAlreadyExistsException.
- Exporter startup failure.
- MBean unexpectedly replaced when using REPLACE_EXISTING.
- Unregistering the wrong name when one side is unaware the other replaced the registration.

Simple rule: **one ObjectName in one MBeanServer should have one clear lifecycle owner**.

## 11. Example of Managing Unregistration Yourself with Lifecycle Callbacks

If a problem strictly requires calling registerMBean() directly, pair registration and unregistration inside the same Spring-managed component.

Example:

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.InitializingBean;

public class ManualJmxRegistration
        implements InitializingBean, DisposableBean {

    private final MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

    private final ObjectName name;
    private boolean registered;

    public ManualJmxRegistration() throws Exception {
        this.name = new ObjectName(
                "learning.jmx:type=CacheMonitor,name=Manual"
        );
    }

    @Override
    public void afterPropertiesSet() throws Exception {
        server.registerMBean(new CacheMonitor(), name);
        registered = true;
    }

    @Override
    public void destroy() throws Exception {
        if (registered && server.isRegistered(name)) {
            server.unregisterMBean(name);
            registered = false;
        }
    }
}
\`\`\`

This example illustrates pairing init and destroy callbacks. In a real system, handle partial registration failures, ownership, thread safety, and cases where the MBean at that name was replaced by another component.

If MBeanExporter can be used, there is usually no need to write all this lifecycle management yourself.

## 12. Exporting on Context Refresh and Re-Registration Issues

An ApplicationContext can be refreshed in contexts that allow it, or an application may create a new context multiple times. When a new exporter begins registering MBeans in an already-running MBeanServer:

- If the previous context unregistered completely, the name can be reused.
- If the previous context is still running, duplicate registration can occur.
- If the previous context closed abnormally while the JVM kept running without cleanup being called, the registry may still hold the old MBean.
- If another MBean already claimed the name, establish ownership before using a replacement policy.

Do not pick REPLACE_EXISTING solely to make a test pass if in reality two contexts are registering the same name. Investigate the contexts' lifecycles and registration names.

### Testing with Standalone ApplicationContext

You can write an integration check (when needed) consisting of:

1. Reading isRegistered(name) before creating the context.
2. Creating AnnotationConfigApplicationContext.
3. Confirming isRegistered(name) is true.
4. Closing the context.
5. Confirming isRegistered(name) returns to false.
6. Creating a new context and confirming export succeeds again.

When tests run in parallel, use an isolated MBeanServer or properly partitioned ObjectNames so they do not conflict with other tests. Do not attempt to delete every MBean on the platform server because some may belong to other parts of the JVM.

## 13. Listening to Registration and Unregistration Events

An MBeanServer can also emit notifications when an MBean is registered or unregistered. In JMX, MBeanServerDelegate is the source providing registry-related management notifications.

Typical types defined by MBeanServerNotification:

\`\`\`java
MBeanServerNotification.REGISTRATION_NOTIFICATION
MBeanServerNotification.UNREGISTRATION_NOTIFICATION
\`\`\`

Distinguish:

- **MBeanServer registration notification:** indicates an ObjectName was registered/removed from the registry.
- **Business notification emitted by an MBean:** e.g., cache cleared, queue overloaded; this is that MBean's own contract.

The two notification types are not equivalent.

To monitor lifecycle, you can register a listener with MBeanServerDelegate under the system ObjectName, or simply check isRegistered() at necessary points. Avoid leaving management listeners alive longer than the lifecycle of the component that owns them.

## 14. Common Errors

| Symptom | Possible Cause | How to Handle |
|---|---|---|
| MBean missing after startup | Exporter has not run, bean missing from map, wrong MBeanServer, or registration error | Check configuration, export logs, and isRegistered() on the right server |
| InstanceAlreadyExistsException | Duplicate ObjectName | Identify the context/bean owning the name and RegistrationPolicy |
| MBean remains after context.close() | Manual registration, exporter does not own the name, destroy callback did not run, or context did not actually close | Trace where register/unregister happens and context state |
| MBean disappears after restart | Old JVM stopped or new context has not exported yet | Connect to the new JVM and inspect startup |
| JConsole still shows old name | Client has not refreshed, connected to wrong JVM, or real registration remains | Refresh and confirm via server.isRegistered() |
| MBean responds, yet target bean has stopped | Registry retains object/proxy beyond lifecycle | Check ownership, destroy, and unexport |
| Two contexts overwrite each other's MBeans | Same server, same ObjectName, REPLACE_EXISTING | Use clear naming scheme and ownership policy |
| Server-wide MBean count does not drop to 0 | Platform MBeans and other registrations still exist | Check specific ObjectNames |
| Cannot export Standard MBean | Wrong interface naming/metadata | Check Standard MBean contract, assembler, and NotCompliantMBeanException |
| Context refresh fails yet name still exists | Duplicate registration or leftover registration from another context | Read the exception and identify the owner before fixing |

## 15. Lifecycle-Based Diagnostics

When an error occurs, investigate step by step:

**A. Before startup**

- Which MBeanServer will be used?
- Which ObjectName is expected to be registered?
- Is any MBean already using that name?
- Which context is authorized to manage the registration?

**B. After context refresh**

- Has MBeanExporter initialized?
- Are there exceptions related to register/assembler/ObjectName?
- Does server.isRegistered(name) return true?
- Is the JMX client connected to the right JVM/server?

**C. When the context closes**

- Was context.close() actually called?
- Did destroy callbacks run?
- Does the exporter own the MBean you are checking?
- Does server.isRegistered(name) still return true after closing?

**D. On restart**

- Did the JVM/process change?
- Does the old MBean name still exist in the same server?
- Is a parent/child context or another instance exporting the same name?
- What is RegistrationPolicy doing when the name already exists?

The core question is: **who registered the ObjectName and who is responsible for unregistering it?**

## 16. Real-World Scenarios

### Scenario 1: Normal Spring Application Startup

The application has one context and one MBeanExporter. When context refresh completes, the MBean is registered; on close, the exporter unregisters it. This is the desired lifecycle.

### Scenario 2: Application with Parent and Child Contexts

A bean is exported twice under the same ObjectName. The second context may encounter InstanceAlreadyExistsException. Designate a single place responsible for exporting or use distinct names for genuinely distinct instances.

### Scenario 3: Re-Running Tests in the Same JVM

The first test creates a context without closing it. The next test creates a new context with the same ObjectName and fails. Fix by closing contexts properly per lifecycle, using appropriate resource management, or isolating MBeanServer/ObjectName in tests.

### Scenario 4: Directly Registered MBean

A @PostConstruct calls registerMBean(), yet there is no @PreDestroy or DisposableBean unregistration. Closing the context while the JVM continues running can leave the MBean in the registry. Pair a cleanup callback or switch to MBeanExporter.

### Scenario 5: Service Running in a Container

A JVM restart creates a new MBeanServer. A JMX client holding a connection to the old process does not automatically switch to the new process. Reconnect, check the ObjectName and security of the new endpoint, and keep in mind that new registrations only appear after startup.

## 17. Practice Exercises

**Exercise A — Observing Lifecycle**

Create the three classes CacheMonitorMBean, CacheMonitor, and JmxExportConfig as in the example. Run JmxLifecycleDemo and confirm:

\`\`\`text
Before context: false
After refresh: true
After close: false
\`\`\`

Explain why the server still exists after context.close() while the ObjectName has disappeared.

**Exercise B — Simulating Duplicate Names**

Keep context A running and try creating context B with the same JmxExportConfig, same platform MBeanServer, and same ObjectName. Predict the behavior with FAIL_ON_EXISTING. Then close A before creating B and observe the difference.

**Exercise C — Finding a Leaked MBean**

Create a Spring bean that registers itself in an init callback without unregistering. Close the context and check with isRegistered(name). Add an appropriate destroy callback, re-run, and compare.

**Exercise D — Evaluating Policies**

A system has two modules that both want to export ObjectName learning.jmx:type=CacheMonitor,name=Primary. Explain the risks of IGNORE_EXISTING and REPLACE_EXISTING, then propose an appropriate ObjectName or ownership model.

## 18. Takeaways

- **Export** registers an MBean into an MBeanServer; **unexport** unregisters it from the registry.
- When MBeanExporter is a Spring-managed bean, registration and cleanup are normally tied to ApplicationContext initialization and destruction.
- **Unexporting does not mean destroying the JVM**, wiping the entire MBeanServer, or stopping all other resources of the bean.
- Only check the specific ObjectName on the specific MBeanServer; do not use total MBean count as a lifecycle condition.
- Manual registration requires manual unregistration or corresponding lifecycle callbacks.
- **RegistrationPolicy** affects how duplicate ObjectNames are handled; it does not replace ownership design.
- With multiple contexts or tests in the same JVM, guarantee unique names or a single unified owner.
- When errors occur, trace the journey backwards: **context startup → exporter registration → MBeanServer → context close → exporter cleanup**.

## References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — MBeanExporter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework API — RegistrationPolicy: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/support/RegistrationPolicy.html
- Java SE 21 API — MBeanServer: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 API — MBeanServerNotification: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerNotification.html
