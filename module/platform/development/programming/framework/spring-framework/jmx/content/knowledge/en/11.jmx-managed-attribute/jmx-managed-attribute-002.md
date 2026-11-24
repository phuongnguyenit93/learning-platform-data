# Creating Read-Only Attributes with Getters Using @ManagedAttribute in Spring Framework JMX

## 1. Learning Objectives

In Spring Framework JMX, a getter method can become a **readable attribute** of an MBean when exposed through management metadata. The \`@ManagedAttribute\` annotation is a way to describe a getter or setter for Spring's export mechanism. If Spring only exposes the getter and does not expose the corresponding setter, JMX clients see the attribute as **read-only**.

For example:

\`\`\`java
@ManagedAttribute
public int getActiveSessions() {
    return activeSessions.get();
}
\`\`\`

When the bean is properly exported, clients can read the \`ActiveSessions\` attribute using \`MBeanServerConnection.getAttribute\` or JConsole. Clients cannot write to \`ActiveSessions\` if there is no valid managed setter.

After this lesson, you will be able to:

1. Understand the JavaBeans rules that turn \`getXxx()\` and \`isXxx()\` into JMX attributes.
2. Use \`@ManagedAttribute\` to allow reading management data only.
3. Distinguish regular Java getters from getters actually exposed by the MBean exporter.
4. Use \`MBeanInfo\` and \`MBeanAttributeInfo\` to inspect names, types, and readable/writable flags.
5. Read attributes via \`MBeanServerConnection\`, JConsole, and management tools.
6. Identify risks of exposing sensitive data, expensive computations, or unstable state from getters.
7. Test the read-only contract using Spring and JUnit examples.

## 2. How Do Java Getters and JMX Attributes Differ?

A getter by JavaBeans convention is a no-argument method, typically named:

\`\`\`java
public int getActiveSessions();
public boolean isEnabled();
\`\`\`

In JavaBeans, \`getActiveSessions()\` corresponds to the \`activeSessions\` property, and \`isEnabled()\` corresponds to the \`enabled\` property. In JMX, MBean metadata typically represents the attribute names as \`ActiveSessions\` and \`Enabled\` according to the MBean/JavaBeans management convention applied by the assembler.

Even if code has a getter, JMX clients **do not automatically see it**. An export process and an interface-determining mechanism are required:

- Standard MBean: a \`SomethingMBean\` interface defines getters/attributes.
- MXBean: an MXBean interface defines attributes with Open Types mapping.
- Spring JMX metadata: \`@ManagedAttribute\` along with the appropriate assembler/exporter determines exposed getters.
- DynamicMBean: an implementation that self-describes and handles attributes.

\`\`\`text
Java object with getActiveSessions()
               |
      @ManagedAttribute
               |
   Spring annotation metadata
               |
         MBeanExporter
               |
          MBeanServer
               |
    ActiveSessions (read-only)
               |
     JConsole / JMX client
\`\`\`

**Principle:** \`@ManagedAttribute\` describes the management interface, while \`MBeanExporter\` registers the object into the \`MBeanServer\`. The annotation alone is not enough to create an accessible MBean.

## 3. Why Does a Getter Create a Read-Only Attribute?

In JMX, an attribute has two access directions:

- **Read:** the client uses \`getAttribute(name, "ActiveSessions")\`.
- **Write:** the client uses \`setAttribute(name, new Attribute("ActiveSessions", value))\`.

If only a managed getter is provided, metadata reports \`readable=true\`, \`writable=false\`. There is no corresponding update path in the management interface.

Contract example:

\`\`\`text
ObjectName: training.spring:type=SessionMonitor,name=Primary

Attribute:
  Name       = ActiveSessions
  Type       = int
  Readable   = true
  Writable   = false

Client:
  getAttribute("ActiveSessions")  -> 12
  setAttribute("ActiveSessions")  -> rejected
\`\`\`

What matters is that **no setter is exposed**, not necessarily that the Java class completely lacks a setter. If the class has a setter for internal use only and the assembler does not expose it, the JMX attribute can still be read-only. Conversely, if the exporter configuration allows all public setters to be managed, annotating only the getter may not be enough to guarantee read-only behavior. Verify \`MBeanInfo\` on the registered MBean.

## 4. Example of Spring @ManagedResource and Getter @ManagedAttribute

### 4.1. Bean Exposing State Only

\`\`\`java
package example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

import java.util.concurrent.atomic.AtomicInteger;

@Component
@ManagedResource(
    objectName = "training.spring:type=SessionMonitor,name=Primary",
    description = "Read-only session monitoring")
public class SessionMonitor {

    private final AtomicInteger activeSessions =
        new AtomicInteger();

    @ManagedAttribute(
        description = "Number of sessions currently active")
    public int getActiveSessions() {
        return activeSessions.get();
    }

    public void sessionStarted() {
        activeSessions.incrementAndGet();
    }

    public void sessionEnded() {
        activeSessions.updateAndGet(
            previous -> Math.max(0, previous - 1));
    }
}
\`\`\`

Here:

- \`@ManagedResource\` describes the managed resource.
- \`@ManagedAttribute\` on \`getActiveSessions()\` enables the Spring assembler to build the attribute.
- No \`setActiveSessions(...)\` is exposed, so the attribute is expected to be read-only.
- The \`sessionStarted()\` and \`sessionEnded()\` methods update internal data but are not exposed as JMX operations.
- \`AtomicInteger\` provides thread-safe counter read/write at the single-variable level.

Note: clamping the decremented counter at 0 is merely simulated behavior; real systems must manage session lifecycles and handle duplicate/lost events using an appropriate model.

### 4.2. Enabling JMX Export in Spring Framework

In a Spring Framework application using Java configuration, you can use:

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@ComponentScan(basePackageClasses = SessionMonitor.class)
@EnableMBeanExport
public class AppConfig {
}
\`\`\`

\`@EnableMBeanExport\` activates MBean export support based on Spring's mechanism. In a project with multiple exporters, contexts, or separate MBeanServers, explicitly configure the server and ownership to avoid duplicate registrations. Specific options may vary across Spring Framework versions.

A test driver program:

\`\`\`java
package example.jmx;

import org.springframework.context.annotation
    .AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) throws Exception {
        try (var context =
                 new AnnotationConfigApplicationContext(
                     AppConfig.class)) {

            SessionMonitor monitor =
                context.getBean(SessionMonitor.class);

            monitor.sessionStarted();
            monitor.sessionStarted();

            System.out.println("JVM PID=" +
                ProcessHandle.current().pid());

            Thread.sleep(120_000);
        }
    }
}
\`\`\`

Use a compatible JDK and matching Spring Context dependency versions. While the application runs, launch \`jconsole\`, select the local JVM, and open the **MBeans** tab to inspect \`training.spring:type=SessionMonitor,name=Primary\`.

## 5. Inspecting Metadata via the JMX API

Reading the attribute directly is the first step. To prove it is read-only, inspect the metadata:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.*;

public class InspectSessionMonitor {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "training.spring:type=SessionMonitor,name=Primary");

        MBeanInfo info = server.getMBeanInfo(name);

        for (MBeanAttributeInfo attr : info.getAttributes()) {
            System.out.printf(
                "%s type=%s read=%s write=%s%n",
                attr.getName(),
                attr.getType(),
                attr.isReadable(),
                attr.isWritable());
        }

        System.out.println(
            "ActiveSessions=" +
            server.getAttribute(name, "ActiveSessions"));
    }
}
\`\`\`

The \`InspectSessionMonitor\` program above uses the **platform MBeanServer in the same JVM**. If run as a separate JVM, it will read the platform server of the \`InspectSessionMonitor\` process itself, not the MBeanServer of the \`Main\` application. To inspect another process, use JConsole or set up an authorized \`JMXConnector\` and obtain an \`MBeanServerConnection\` from the connector. Alternatively, integrate the inspection snippet directly into \`Main\` after the context starts.

Once connected to the right server, the expected metadata is:

\`\`\`text
ActiveSessions type=int read=true write=false
ActiveSessions=2
\`\`\`

The exact attribute name and type representation should be verified for the specific assembler and Spring version.

### 5.1. \`MBeanAttributeInfo\` Is the Source of Truth

\`\`\`java
boolean readable = attr.isReadable();
boolean writable = attr.isWritable();
String type = attr.getType();
String name = attr.getName();
\`\`\`

These flags are the contract visible to clients. Do not rely solely on the absence of a setter in the class without verifying the actual exporter/assembler.

### 5.2. Inspecting with JConsole

In JConsole, open the MBeans tab and select the registered MBean. The \`ActiveSessions\` attribute appears with its readable value and no valid way to write it if the metadata is read-only. UI details vary by JDK; what matters most remains \`MBeanAttributeInfo.isWritable() == false\`.

## 6. Boolean Getters: \`isEnabled()\` and \`getEnabled()\`

In JavaBeans, booleans commonly use:

\`\`\`java
@ManagedAttribute
public boolean isEnabled() {
    return enabled;
}
\`\`\`

or:

\`\`\`java
@ManagedAttribute
public Boolean getEnabled() {
    return enabled;
}
\`\`\`

Several rules to keep in mind:

- \`isXxx()\` in JavaBeans is normally reserved for primitive \`boolean\`.
- \`getXxx()\` can be used for primitive \`boolean\` or wrapper \`Boolean\`.
- The attribute name is derived from the property descriptor; for getter \`isEnabled\`, the managed name is typically \`Enabled\`.
- If both \`isEnabled()\` and \`getEnabled()\` exist with inconsistent rules, introspection can become unpredictable. Pick one consistent pattern.
- Do not arbitrarily name a method \`isActiveSessions()\` when the value is \`int\`; that is not a valid boolean getter.

Example:

\`\`\`java
@ManagedResource(
    objectName = "training.spring:type=Feature,name=Checkout")
public class CheckoutFeatureStatus {
    private volatile boolean enabled = true;

    @ManagedAttribute(description = "Feature switch state")
    public boolean isEnabled() {
        return enabled;
    }
}
\`\`\`

If no setter is exposed, the \`Enabled\` MBean attribute is read-only by design even though the state can be changed by internal application logic.

## 7. A Read-Only Getter Does Not Mean an Immutable Value

**Read-only** means JMX clients cannot write directly through that attribute. The value can still change with system state:

\`\`\`text
T0: ActiveSessions = 1
T1: ActiveSessions = 4
T2: ActiveSessions = 2
\`\`\`

All of these snapshots are valid for a read-only attribute. The distinction is that clients can observe but cannot call \`setAttribute\` to arbitrarily alter the counter.

Concept table:

| Concept | Meaning |
|---|---|
| Read-only attribute | No JMX write path through the attribute |
| Immutable field | Value does not change after initialization |
| Thread-safe read | Reads return consistent data per the applied synchronization mechanism |
| Cached metric | Value read from cache, with update latency |
| Derived metric | Getter computed from other state |

A managed getter should clearly document freshness, measurement unit, and semantics if it is an operational metric. For example, \`getActiveSessions()\` may need to distinguish authenticated sessions, transport sessions, or in-flight requests.

## 8. What Happens When Attempting to Write to a Read-Only Attribute?

A client might try to write:

\`\`\`java
connection.setAttribute(
    name,
    new Attribute("ActiveSessions", 99));
\`\`\`

For an MBean that genuinely exposes a read-only attribute, the write operation is unsupported. Depending on the MBean type, JMX implementation, and handling path, the client receives an appropriate exception, commonly \`AttributeNotFoundException\` when the attribute is not writable. Clients should handle errors per the JMX contract; do not assume all cases return the exact same exception type if implementations differ.

Simple test:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;

MBeanAttributeInfo active = java.util.Arrays.stream(
    connection.getMBeanInfo(name).getAttributes())
    .filter(attr -> attr.getName().equals("ActiveSessions"))
    .findFirst()
    .orElseThrow();

assertTrue(active.isReadable());
assertFalse(active.isWritable());

assertThrows(
    AttributeNotFoundException.class,
    () -> connection.setAttribute(
        name, new Attribute("ActiveSessions", 99)));
\`\`\`

For your specific application tests, verify the actual exception from the exporter in use. An assertion on \`isWritable()\` is generally more stable than relying solely on exception messages.

## 9. What Happens When Adding a Setter?

Suppose later the class adds:

\`\`\`java
@ManagedAttribute
public void setActiveSessions(int count) {
    activeSessions.set(count);
}
\`\`\`

If the assembler pairs the getter and setter into the same attribute, metadata can become:

\`\`\`text
ActiveSessions:
  readable=true
  writable=true
\`\`\`

Thus clients can change the counter via JMX. This opens **a new management capability**, which can be dangerous if the value reflects business data that must be computed from events rather than edited manually.

Do not add a managed setter just so "JConsole makes it convenient to edit." If a controlled reset is needed, use a well-defined operation:

\`\`\`java
@ManagedOperation(
    description = "Reset demonstration session count")
public void resetDemoCount() {
    activeSessions.set(0);
}
\`\`\`

An operation has a name describing business meaning and can be protected/audited per appropriate policies. However, marking an operation does not automatically provide authorization; access control must be designed at the appropriate layer.

## 10. When to Use @ManagedAttribute vs. @ManagedOperation?

| Requirement | Suggestion | Reason |
|---|---|---|
| Read current session count | Getter \`@ManagedAttribute\` | State metric |
| Read application version | Read-only getter | Near-immutable information |
| Read number of open connections | Read-only getter | Observation |
| Toggle a feature in a controlled way | Getter and setter, or operation | Requires considering permissions and audit |
| Reset statistics | \`@ManagedOperation\` | Clear action |
| Clear cache | \`@ManagedOperation\` | Has side effects and requires control |
| Restart worker | \`@ManagedOperation\` | Sensitive operational action |

An attribute is appropriate when the data makes sense as **state**. An operation is appropriate when the client requests an **action**. Keep getters cheap and free of side effects; avoid placing operational logic that mutates data inside getters.

## 11. Metadata and JMX Contract Compatibility

A JMX client may depend on:

\`\`\`text
ObjectName:
  training.spring:type=SessionMonitor,name=Primary
Attribute:
  ActiveSessions
Type:
  int
Readable:
  true
Writable:
  false
\`\`\`

Renaming a getter can rename the attribute if metadata maps via JavaBeans. Switching from \`int\` to \`String\`, changing measurement units, or altering metric semantics can also break dashboards/scripts even if the Java code compiles cleanly.

To protect the contract:

1. Use stable conventions for ObjectNames.
2. Choose attribute names that clearly describe meaning.
3. Keep types and measurement units consistent.
4. Test metadata via \`MBeanServerConnection\`.
5. Do not add unintended writable access.
6. If changes are intentional, document migration notes and update clients.
7. Be careful when swapping assemblers or exporters, as the exposed attribute set may change.

\`MBeanInfo\` and \`MBeanAttributeInfo\` should be treated as the management tool API contract.

## 12. Performance and Safety in Managed Getters

Not every getter is suitable for export. A monitoring tool may poll getters continuously, and multiple clients may even read concurrently.

### 12.1. Avoid Expensive Getters

Do not do this:

\`\`\`java
@ManagedAttribute
public long getTotalRecords() {
    return repository.countAllRecordsWithFullScan();
}
\`\`\`

If the method performs a full-table query, every JConsole or collector attribute read can cause heavy load. Consider:

\`\`\`java
private final java.util.concurrent.atomic.AtomicLong
    cachedTotal = new java.util.concurrent.atomic.AtomicLong();

@ManagedAttribute
public long getTotalRecords() {
    return cachedTotal.get();
}
\`\`\`

Updating \`cachedTotal\` should follow dedicated rules and document the staleness/latency of the metric.

### 12.2. Do Not Return Sensitive Data

Do not expose passwords, access tokens, session identifiers, emails, or unnecessary personal data. JMX tools can have broad read privileges; data classification and access control must still be considered.

### 12.3. Concurrent Data

If a getter reads multiple related variables, the snapshot may be inconsistent:

\`\`\`java
public String getSummary() {
    return "pending=" + pending + ",completed=" + completed;
}
\`\`\`

If the two variables change independently, the result can mix data from two different points in time. Use an immutable snapshot or appropriate synchronization if the contract requires consistency.

### 12.4. Avoid Side Effects

Getters must not reset counters, clear caches, send messages, or invoke unnecessary external APIs. A JConsole refresh should never inadvertently alter application state.

## 13. Testing with Spring ApplicationContext

An integration test should verify that the bean is exported and the attribute is genuinely read-only. For example:

\`\`\`java
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation
    .AnnotationConfigApplicationContext;

import javax.management.*;
import java.lang.management.ManagementFactory;
import java.util.Arrays;

import static org.junit.jupiter.api.Assertions.*;

class SessionMonitorJmxTest {

    @Test
    void activeSessionsIsReadOnly() throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(
                    AppConfig.class)) {

            MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

            ObjectName name = new ObjectName(
                "training.spring:type=SessionMonitor,name=Primary");

            assertTrue(server.isRegistered(name));

            MBeanAttributeInfo attr = Arrays.stream(
                server.getMBeanInfo(name).getAttributes())
                .filter(a -> a.getName().equals("ActiveSessions"))
                .findFirst()
                .orElseThrow();

            assertEquals("int", attr.getType());
            assertTrue(attr.isReadable());
            assertFalse(attr.isWritable());

            SessionMonitor monitor =
                context.getBean(SessionMonitor.class);
            monitor.sessionStarted();

            assertEquals(
                1,
                server.getAttribute(name, "ActiveSessions"));
        }
    }
}
\`\`\`

The example assumes the exporter uses the platform MBeanServer and the test runs in isolation so there are no duplicate registrations. In systems with multiple ApplicationContexts or parallel test execution, inject a dedicated MBeanServer and check the exact server used by the exporter.

**Do not use a test that only calls \`monitor.getActiveSessions()\` to conclude JMX has exposed the attribute.** The crucial part is client access through \`MBeanServer\`.

## 14. Common Errors

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Getter works in code but missing in JConsole | MBean not exported or annotation assembler not active | Check \`@EnableMBeanExport\`, exporter, ObjectName |
| MBean exists but \`ActiveSessions\` missing | Getter not exposed or naming not as expected | Read \`MBeanInfo\` and metadata |
| Attribute unintentionally becomes writable | Setter was also exported | Check \`isWritable()\` and assembler |
| \`getAttribute\` reports \`AttributeNotFoundException\` | Wrong name or connected to wrong server | Inspect actual attribute list |
| JConsole displays stale value | Getter returns cache or state not updated | Verify semantics, cache refresh |
| Getter slows down application | Expensive computation/query on each read | Use pre-updated snapshot/counter |
| Duplicate ObjectName conflict | Multiple exporters or contexts | Identify owner and registration policy |
| Remote JMX cannot read | Connector/TLS/auth/network | Check remote layer independently |

A common mistake when learning Spring JMX is thinking \`@ManagedAttribute\` automatically enables remote access. The annotation only describes the attribute; the remote access path resides in the JMX connector/management agent.

## 15. Practice Exercises

### Exercise A — Two Read-Only Getters

Create \`ApplicationStatus\` with two getters:

\`\`\`java
@ManagedAttribute
public int getRunningJobs() { ... }

@ManagedAttribute
public long getUptimeSeconds() { ... }
\`\`\`

Export the MBean, use JConsole or \`MBeanServerConnection\` to confirm both have \`readable=true\`, \`writable=false\`. Observe \`UptimeSeconds\` changing even though the attribute is read-only.

### Exercise B — Adding an Unintended Setter

Add \`@ManagedAttribute\` to the setter of \`RunningJobs\`. Re-read \`MBeanInfo\` and explain why the JMX API changed. Then remove the setter annotation and verify it returns to read-only.

### Exercise C — Boolean Getters

Create \`isHealthy()\` and \`getHealthy()\` in two different classes. Inspect attribute names via metadata, distinguishing primitive \`boolean\` from wrapper \`Boolean\`. Avoid creating both getters in the same class without a specific purpose.

### Exercise D — Testing an Expensive Getter

Create a getter that intentionally calls \`Thread.sleep(200)\` in a lab environment and measure read latency over JMX. Replace it with a cached value and compare. Derive performance requirements for polled management APIs.

### Exercise E — Contract Test

Write a JUnit 5 test verifying:
- The ObjectName is registered.
- The attribute is named \`ActiveSessions\`, type \`int\`.
- Readable true, writable false.
- After \`sessionStarted()\`, JMX reads the new value.
- An invalid write request is rejected according to the MBean contract.

## 16. Self-Check Questions

1. Why do regular Java getters not automatically become JMX attributes?
2. Which Spring components must \`@ManagedAttribute\` work with?
3. What is a read-only JMX attribute?
4. Can a read-only attribute change its value at runtime?
5. How do you verify \`isWritable=false\`?
6. What happens if a setter is also exposed?
7. How does \`isEnabled()\` differ from \`getActiveSessions()\` in JavaBeans rules?
8. Why should managed getters be lightweight and free of side effects?
9. Why should you test via \`MBeanServerConnection\` instead of only calling the method directly?
10. Does an annotation on a getter open a remote JMX connector?

## 17. References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — \`@ManagedAttribute\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedAttribute.html
- Spring Framework API — \`@ManagedResource\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedResource.html
- Java SE 21 API — \`MBeanAttributeInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanAttributeInfo.html
- Java SE 21 API — \`MBeanServerConnection\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html

**Remember:** a getter exposed with \`@ManagedAttribute\` alongside an appropriate exporter and assembler produces a readable JMX attribute. When no corresponding managed setter exists, the attribute is read-only. Verify the \`readable/writable\` flags on the actual MBean and ensure the getter is fast, safe, and has clear semantics.
