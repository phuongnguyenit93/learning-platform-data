# RegistrationPolicy.REPLACE_EXISTING in Spring Framework JMX

> **Topic:** Spring Framework JMX  
> **Knowledge group:** Registration policy  
> **Lesson:** RegistrationPolicy.REPLACE_EXISTING

## 1. Learning Objectives

After this lesson, you will be able to:

- Understand why two MBeans cannot be registered simultaneously under the same \`ObjectName\` in the same \`MBeanServer\`.
- Explain the meaning of Spring JMX exporter's \`RegistrationPolicy.REPLACE_EXISTING\`.
- Distinguish \`FAIL_ON_EXISTING\`, \`IGNORE_EXISTING\`, and \`REPLACE_EXISTING\`.
- Know what happens when the exporter encounters an existing MBean under the same \`ObjectName\`.
- Identify risks when replacing an MBean owned by another component, disrupting monitoring, notification listeners, or client proxies.
- Configure the policy intentionally, verify results using \`MBeanServer\`, and choose the appropriate policy for each environment.

## 2. Background: One ObjectName Points to One MBean at a Time

An \`MBeanServer\` is a registry that manages MBeans by \`javax.management.ObjectName\`.

\`\`\`text
MBeanServer
  |
  +-- app.monitoring:type=Cache,name=primary
  |      -> Existing MBean
  |
  +-- app.monitoring:type=WorkerPool,name=main
         -> Another MBean
\`\`\`

If a second exporter attempts to register a new MBean with the name:

\`\`\`text
app.monitoring:type=Cache,name=primary
\`\`\`

a name collision will occur. Under standard JMX rules, \`MBeanServer.registerMBean\` throws \`InstanceAlreadyExistsException\` when that name is already in use.

Spring provides \`org.springframework.jmx.support.RegistrationPolicy\` to decide how \`MBeanExporter\` handles conflicts at registration time.

\`\`\`text
Spring exporter wants to register a new bean
                 |
                 v
         ObjectName already exists?
             /         \
            No          Yes
            |            |
            v            v
       Register new   Apply RegistrationPolicy
                           |
                   +-------+--------+
                   |       |        |
                  FAIL   IGNORE   REPLACE
\`\`\`

**Important:** Registration policy governs how the exporter handles **MBean registration conflicts**. It does not alter ObjectName rules, authenticate client permissions, or make arbitrary MBeans compatible with one another.

## 3. What Does REPLACE_EXISTING Mean?

\`RegistrationPolicy.REPLACE_EXISTING\` instructs the Spring exporter to handle an existing name by **replacing the old registration with the new MBean**.

Model:

\`\`\`text
Before:
  MBeanServer
    app.monitoring:type=Cache,name=primary
        -> OldCacheMBean

New exporter:
    wants to register NewCacheMBean with the same ObjectName
    policy = REPLACE_EXISTING

During process:
    unregister old MBean
    register new MBean

After success:
  MBeanServer
    app.monitoring:type=Cache,name=primary
        -> NewCacheMBean
\`\`\`

In Spring, this is collision-handling behavior, **not an atomic hot swap** or an in-place implementation replacement inside the same MBean instance.

A client may observe a brief window where the MBean does not exist between unregistration and new registration. Therefore, clients should not treat replacement as completely transparent.

### Key Distinctions

- \`REPLACE_EXISTING\` does not create two MBeans simultaneously under the same name.
- It does not guarantee the new MBean has attribute/operation metadata compatible with the old MBean.
- It does not preserve listeners attached to the old MBean by default.
- It does not guarantee the old MBean's internal state is transferred to the new MBean.
- It does not turn the unregister/register sequence into a transaction with automatic rollback.
- It does not allow the exporter to bypass permission, initialization, or lifecycle errors.

## 4. Comparing the Three Registration Policies

| Policy | When ObjectName Does Not Exist | When ObjectName Already Exists | Operational Meaning |
|---|---|---|---|
| \`FAIL_ON_EXISTING\` | Registers new MBean | Fails with conflict error | Detects duplicate configuration without silently interfering with other MBeans |
| \`IGNORE_EXISTING\` | Registers new MBean | Keeps old MBean, skips new registration | Suitable when reusing an existing MBean without replacing it |
| \`REPLACE_EXISTING\` | Registers new MBean | Unregisters old MBean, then registers new MBean | Allows the exporter to claim an already-used ObjectName, but may break existing clients |

The enum values can be used via:

\`\`\`java
import org.springframework.jmx.support.RegistrationPolicy;

RegistrationPolicy policy =
    RegistrationPolicy.REPLACE_EXISTING;
\`\`\`

Default values and configuration options also depend on the specific Spring exporter and library version. When evaluating an existing application, inspect the actual configuration instead of assuming \`REPLACE_EXISTING\` is in use.

## 5. Configuring REPLACE_EXISTING in Spring

Example of explicit \`MBeanExporter\` configuration:

\`\`\`java
package example.jmx;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

@Configuration
public class JmxExportConfiguration {

    @Bean
    public MBeanExporter mbeanExporter(
            CacheManagementFacade cacheFacade
    ) {
        MBeanExporter exporter = new MBeanExporter();

        exporter.setBeans(Map.of(
            "app.monitoring:type=Cache,name=primary",
            cacheFacade
        ));

        exporter.setRegistrationPolicy(
            RegistrationPolicy.REPLACE_EXISTING
        );

        return exporter;
    }
}
\`\`\`

Assuming \`CacheManagementFacade\` is a Spring bean suitable for JMX export, such as a class with \`@ManagedResource\`/\`@ManagedAttribute\` metadata or implementing an MBean interface per the corresponding convention.

The \`setRegistrationPolicy\` method belongs to the export/registration mechanism that \`MBeanExporter\` inherits from its Spring JMX support class. It determines how existing names are handled on the MBeanServer used by the exporter.

### Avoid Creating Duplicate Exporters Unintentionally

If the application already uses \`@EnableMBeanExport\` or Spring Boot auto-configures a JMX exporter, adding another \`MBeanExporter\` can cause both to process the same bean/ObjectName.

\`\`\`text
AnnotationMBeanExporter  ----\
                              > same ObjectName -> conflict
Manual MBeanExporter    -----/
\`\`\`

\`REPLACE_EXISTING\` is not a good fix for an accidental duplicate exporter configuration. First determine which bean belongs to which exporter, then remove the unnecessary duplicate configuration. Only replace when it is an intentional lifecycle requirement.

## 6. MBean Example and Conflict Simulation

To observe registry behavior, create a simple Standard MBean.

### 6.1. Interface

\`\`\`java
package example.jmx;

public interface CounterMBean {
    int getCount();
    void increment();
}
\`\`\`

### 6.2. Implementation

\`\`\`java
package example.jmx;

public class Counter implements CounterMBean {

    private int count;

    public Counter(int initialValue) {
        this.count = initialValue;
    }

    @Override
    public synchronized int getCount() {
        return count;
    }

    @Override
    public synchronized void increment() {
        count++;
    }
}
\`\`\`

### 6.3. Conflict Scenario in Plain JMX

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "learning.jmx:type=Counter,name=primary"
);

server.registerMBean(new Counter(3), name);

// Registering the same name again will throw
// InstanceAlreadyExistsException:
server.registerMBean(new Counter(100), name);
\`\`\`

The second statement illustrates why the policy exists. Do not run this snippet without cleanup in a real test; if the name was already in use beforehand, the first registration can also fail.

**Spring's REPLACE_EXISTING** handles conflicts at the exporter layer. Plain JMX has no \`RegistrationPolicy\` parameter on \`registerMBean\`.

## 7. Replacement Cycle and Non-Atomic Consequences

Suppose the old MBean \`Counter(3)\` is registered under:

\`\`\`text
learning.jmx:type=Counter,name=primary
\`\`\`

The new exporter is configured with \`REPLACE_EXISTING\` for \`Counter(100)\` with the same name.

From a logical perspective:

\`\`\`text
1. Register the new MBean with ObjectName.
2. Detect InstanceAlreadyExistsException.
3. Policy requests replacement handling.
4. Unregister the old MBean.
5. Register the new MBean under the same ObjectName.
6. Record the new registration for lifecycle management.
\`\`\`

The exact steps and detailed exception handling are the Spring exporter's responsibility, but **the essence is mutating the registry**, not updating fields on the old object.

A client continuously calling:

\`\`\`java
connection.getAttribute(name, "Count");
\`\`\`

may observe:

\`\`\`text
Before replacement: Count = 3
During unregister/register window: MBean not found
After replacement: Count = 100
\`\`\`

This is an illustrative scenario. The actual timing depends on scheduling and how the client makes calls; an error might not be observed in a single attempt, yet the race still exists.

## 8. Risks of REPLACE_EXISTING

### 8.1. Accidentally Replacing an Unowned MBean

An MBean may have been registered by:

- Another Spring ApplicationContext.
- A monitoring agent or third-party library.
- Direct Java code via \`registerMBean\`.
- Another active application instance.
- JVM infrastructure.

If an exporter uses \`REPLACE_EXISTING\` on a colliding name, it risks unregistering an MBean owned by another component. When that happens, the original management resource can disappear from the registry.

Do not use this policy on broad domains or class-derived ObjectNames without controlling registration ownership.

### 8.2. Changing Attributes or Operations

The old MBean has:

\`\`\`text
Attribute: PendingJobs (int)
Operation: pause()
\`\`\`

The new MBean has:

\`\`\`text
Attribute: QueueDepth (long)
Operation: suspend(boolean)
\`\`\`

Even though the ObjectName is identical, an old client calling \`getAttribute("PendingJobs")\` may receive \`AttributeNotFoundException\`, and \`invoke("pause")\` may fail because the operation no longer exists.

**ObjectName stability does not automatically guarantee JMX contract compatibility.** Compare \`MBeanInfo\` when changing management versions.

### 8.3. Notification Listeners May Be Lost

If a client registered a \`NotificationListener\` on the old MBean, unregistering the MBean can drop registrations tied to the old broadcaster. Later, a new MBean with the same ObjectName does not automatically re-attach old listeners to the new instance.

Clients must track lifecycle events and be able to re-register listeners. Registration/unregistration events can be observed via \`MBeanServerDelegate\`.

### 8.4. State Is Not Migrated

If the old MBean stores a counter in a field and the new MBean initializes a different counter, replacement changes the observed state. \`REPLACE_EXISTING\` does not copy object state or business data.

When continuous state is needed, use a stable service/metrics repository or design a separate migration instead of relying on registration policy.

### 8.5. Replacement Does Not Necessarily Roll Back if New Registration Fails

If the old MBean was unregistered but registering the new MBean fails, do not assume Spring/JMX will restore the old MBean like a transaction. Inspect exceptions and design appropriate fallback/recovery, especially when registering an MBean that provides critical monitoring.

## 9. Lifecycle of the Spring Exporter

The Spring exporter manages the MBeans it registers according to the lifecycle of the Spring bean or ApplicationContext, depending on configuration.

\`\`\`text
ApplicationContext start
        |
        v
MBeanExporter initialization
        |
        +--> register MBean
        |       |
        |       +--> if collision:
        |             REPLACE_EXISTING
        |
        v
MBeanServer registry updated
        |
        v
ApplicationContext shutdown
        |
        v
Exporter cleans up registrations within its managed scope
\`\`\`

An important consequence of replacement: after the new exporter takes over the ObjectName and later closes its context, the registry will not automatically restore the old MBean that was unregistered. Do not treat \`REPLACE_EXISTING\` as a temporary override with rollback capability.

If multiple ApplicationContexts have overlapping lifecycles in the same JVM, design clear ownership so two exporters do not contend for the same name.

## 10. Checking Before and After Replacement

You can observe registration status:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "learning.jmx:type=Counter,name=primary"
);

System.out.println(
    "Registered: " + server.isRegistered(name)
);

if (server.isRegistered(name)) {
    Object count = server.getAttribute(name, "Count");
    System.out.println("Count = " + count);
}
\`\`\`

An \`isRegistered\` check and a \`getAttribute\` call are two separate operations, so the MBean can disappear in between. Handle \`InstanceNotFoundException\` when clients operate in an environment where the registry changes.

With JConsole:

1. Connect to the right JVM.
2. Open the **MBeans** tab.
3. Find the ObjectName of the MBean under test.
4. Observe attributes and operations before the exporter replaces it.
5. Trigger the application cycle configured with \`REPLACE_EXISTING\` in a test environment.
6. Refresh the MBeans list if needed.
7. Re-read attributes, operations, and notification metadata.
8. Confirm the current MBean actually belongs to the expected implementation.

Do not perform replacement experiments on an MBean serving production monitoring without a transition and recovery plan.

## 11. Using MBeanInfo to Verify the Contract After Replacement

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanOperationInfo;

MBeanInfo info = server.getMBeanInfo(name);

System.out.println(
    "MBean class: " + info.getClassName()
);

for (MBeanAttributeInfo a : info.getAttributes()) {
    System.out.printf(
        "Attribute: %s type=%s readable=%s writable=%s%n",
        a.getName(),
        a.getType(),
        a.isReadable(),
        a.isWritable()
    );
}

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.println(
        "Operation: " + op.getName()
            + " -> " + op.getReturnType()
    );
}
\`\`\`

After a successful replacement, verify:

- Does the ObjectName still exist?
- Do attributes used by clients still have the same names, types, and read/write permissions?
- Do operations still have the same parameter signatures and return types?
- Are notification types compatible with active listeners?
- Did state values change as expected?

Do not rely solely on \`info.getClassName()\`, because with Spring ModelMBeans/adapters, the metadata class name may not be the internal service class you want to identify.

## 12. Tracking Registry Changes with MBeanServerDelegate

JMX includes the system MBean \`JMImplementation:type=MBeanServerDelegate\`. It emits notifications when an MBean is registered or unregistered.

\`\`\`java
import javax.management.MBeanServerDelegate;
import javax.management.MBeanServerNotification;
import javax.management.NotificationListener;

NotificationListener listener =
    (notification, handback) -> {
        if (notification instanceof MBeanServerNotification event) {
            System.out.println(
                event.getType() + " : " + event.getMBeanName()
            );
        }
    };

server.addNotificationListener(
    MBeanServerDelegate.DELEGATE_NAME,
    listener,
    null,
    null
);

try {
    // Perform exporter initialization in the test environment.
} finally {
    server.removeNotificationListener(
        MBeanServerDelegate.DELEGATE_NAME,
        listener
    );
}
\`\`\`

When replacement occurs, a listener watching the registry can observe an unregistration event followed by a re-registration event under the same ObjectName.

This is one way to verify that the registry actually changed. However, event listeners also have their own lifecycle; if registered too late, they may miss events that already occurred. Do not treat registry notifications as a persistent history.

## 13. MBean Proxies and Replacement

A client can create a proxy:

\`\`\`java
import javax.management.JMX;

CounterMBean proxy = JMX.newMBeanProxy(
    connection,
    name,
    CounterMBean.class
);
\`\`\`

A proxy typically holds the \`ObjectName\` and connection, rather than a direct reference to the server-side implementation.

After replacement, the proxy can continue routing calls to the new MBean under the same name **if** operations/attributes remain compatible. However, the proxy may also encounter:

- \`InstanceNotFoundException\` or a proxy-wrapped exception during the unregister/register window.
- Errors when signatures change.
- Return-type errors if the old interface is no longer compatible.
- Unexpected logic if the new MBean holds different state.

Do not treat a proxy as proof of transparent replacement. For critical management services, plan compatibility and bounded retries where appropriate; avoid retrying operations with side effects when you do not know whether the previous call completed.

## 14. REPLACE_EXISTING Is Not a Hot Deployment Mechanism

Concepts that are easily confused:

| Mechanism | Goal | Automatically Transfers State? |
|---|---|---|
| Spring \`REPLACE_EXISTING\` | Resolves ObjectName conflicts by replacing registration | No |
| Hot reload bean/application | Replaces code or context during development | Not by default |
| Rolling deployment | Transitions service versions across multiple instances | Infrastructure-dependent |
| Stable MBean facade | Keeps management contract steady when implementation changes | Does not transfer state automatically, but can retain the same backing service |
| Stateful migration | Transfers data state from old version to new version | Requires custom design |

For products with external JMX clients, a better approach is usually to keep a stable MBean facade and swap the underlying dependency, rather than unregistering/re-registering the MBean every time the implementation changes.

## 15. When Might REPLACE_EXISTING Be Appropriate?

Some cases to consider:

- Test environments that need to re-register an MBean created by a previous setup round, with clearly controlled ownership.
- Restart/reload cycles of a component designed to replace its own registration.
- Coordinated migrations where the name is known to belong to the application's scope and clients can tolerate a brief interruption.
- An old/new MBean management setup with a clear cleanup plan.

Prerequisites before using it:

1. Confirm **who owns the existing ObjectName**.
2. Confirm replacement is the intended behavior, not a symptom of duplicate exporter configuration.
3. Verify the new contract is compatible with clients.
4. Have a plan for listener re-subscription.
5. Have a plan if registering the new MBean fails.
6. Have logging/telemetry to trace registration replacements.
7. Do not rely on the policy to “hijack” MBeans belonging to another library or the JVM.

## 16. When Should You Not Use It?

Avoid \`REPLACE_EXISTING\` as a default option when:

- The reason for the ObjectName collision is unknown.
- Multiple ApplicationContexts or modules coexist without clear ownership.
- The MBean has long-lived listeners or clients and replacement causes disruption.
- The naming strategy can be fixed so each MBean has its own name.
- The conflict comes from Spring Boot auto-configuration overlapping with a custom exporter.
- The old MBean holds management state that must not be lost.
- The MBean belongs to the system or an external library not managed by the application.

In these cases, \`FAIL_ON_EXISTING\` helps detect duplicate configurations early; \`IGNORE_EXISTING\` may fit if the intent is to preserve the existing registration, though contract and ownership must still be checked.

## 17. Distinguishing IGNORE_EXISTING and REPLACE_EXISTING

Suppose the server already has \`Counter(3)\` named \`learning.jmx:type=Counter,name=primary\`.

The exporter tries to register \`Counter(100)\` with the same name.

**IGNORE_EXISTING:**

\`\`\`text
MBeanServer still points to Counter(3)
Count = 3
\`\`\`

**REPLACE_EXISTING:**

\`\`\`text
MBeanServer points to Counter(100)
Count = 100
\`\`\`

**FAIL_ON_EXISTING:**

\`\`\`text
Reports conflict error
Old MBean is not intentionally replaced by policy
\`\`\`

Do not judge IGNORE as “no error so it must be safe” in all cases. If deployment expects the new MBean, ignoring may leave tools viewing stale metadata or state. Verify the actual outcome.

## 18. Protecting Access and Data

\`REPLACE_EXISTING\` is a registration policy, not a security policy. It does not:

- Authenticate JMX clients.
- Authorize operation invocations.
- Encrypt remote connectors.
- Validate operation input data.
- Prevent exporting secrets via attributes.
- Limit side effects of management operations.

If a new MBean exposes an additional dangerous \`@ManagedOperation\`, replacement can inadvertently expand the management surface under an ObjectName that clients already know.

Review \`MBeanInfo\` and authorization policies when changing versions, especially in environments with remote JMX connectors.

## 19. Example of Testing the Result in a Context with an Exporter

An integration test can create the old MBean using plain JMX APIs, then initialize a Spring context containing a new exporter with the \`REPLACE_EXISTING\` policy. Finally, read the attribute back to confirm the new MBean was registered.

Step outline:

\`\`\`text
1. Create a dedicated MBeanServer for the test.
2. Register Counter(3) under ObjectName X.
3. Create a Spring MBeanExporter pointing to the same server.
4. Configure the exporter with Counter(100) and REPLACE_EXISTING.
5. Initialize the exporter to register the new bean.
6. Assert MBeanServer.getAttribute(X, "Count") == 100.
7. Close the exporter/context.
8. Verify cleanup and release the test server if needed.
\`\`\`

In a real test, create a dedicated MBeanServer to avoid affecting the platform MBeanServer used by the JVM or other test runners.

Corresponding exporter configuration snippet:

\`\`\`java
MBeanExporter exporter = new MBeanExporter();
exporter.setServer(testMBeanServer);
exporter.setBeans(Map.of(
    "learning.jmx:type=Counter,name=primary",
    new Counter(100)
));
exporter.setRegistrationPolicy(
    RegistrationPolicy.REPLACE_EXISTING
);
exporter.afterPropertiesSet();
exporter.afterSingletonsInstantiated();
\`\`\`

This is an outline for testing the exporter lifecycle; in a real Spring context, Spring invokes the appropriate lifecycle callbacks. If instantiating the exporter manually, follow the lifecycle contract of your Spring version and invoke proper cleanup rather than assuming \`setBeans\` registers immediately.

## 20. Checklist Before Enabling REPLACE_EXISTING

- [ ] Verified the ObjectName to be replaced falls within the application's management scope.
- [ ] Know the exact reason for the registration conflict.
- [ ] Ruled out unintentional duplicate exporter configurations.
- [ ] New MBean exposes attributes/operations/notifications compatible with clients.
- [ ] Do not depend on retaining internal state from the old MBean.
- [ ] Clients can tolerate the unregister/register window.
- [ ] Long-lived listeners have a re-registration strategy.
- [ ] Have a way to observe exceptions and registration results.
- [ ] Have a fallback plan if replacement fails partway through.
- [ ] Evaluated JMX access permissions and the new management surface.
- [ ] Tested in an isolated MBeanServer or an environment that does not affect production.
- [ ] Have a plan to clean up registrations when the context closes.

## 21. Self-Check Questions

1. Why can't an MBeanServer hold two MBeans with the same ObjectName?
2. What does \`REPLACE_EXISTING\` do when the name does not exist yet?
3. What is the difference between \`REPLACE_EXISTING\` and \`IGNORE_EXISTING\`?
4. Why shouldn't REPLACE be used to hide a duplicate-exporter configuration error?
5. Do listeners registered on the old MBean automatically transfer to the new MBean?
6. Is a proxy holding the same ObjectName guaranteed to keep working after replacement?
7. Why can replacing a registration briefly cause clients to encounter \`InstanceNotFoundException\`?
8. Does \`REPLACE_EXISTING\` automatically copy state or roll back the old MBean?
9. Why should you inspect \`MBeanInfo\` after replacement?
10. When is \`FAIL_ON_EXISTING\` a better choice for production systems?

## 22. Key Takeaways

\`\`\`text
MBeanExporter
    |
    v
register MBean with ObjectName X
    |
    +-- X does not exist -> register normally
    |
    +-- X already exists
          |
          +-- FAIL_ON_EXISTING
          |       -> throw error
          |
          +-- IGNORE_EXISTING
          |       -> keep old MBean
          |
          +-- REPLACE_EXISTING
                  -> unregister old MBean
                  -> register new MBean
\`\`\`

**Core point:** \`RegistrationPolicy.REPLACE_EXISTING\` is Spring JMX's mechanism for handling **registration name conflicts**. It is not a zero-downtime upgrade, not a state transfer mechanism, and does not automatically solve ownership or API compatibility issues. Use it only when replacement is intentional, designed, and verified.