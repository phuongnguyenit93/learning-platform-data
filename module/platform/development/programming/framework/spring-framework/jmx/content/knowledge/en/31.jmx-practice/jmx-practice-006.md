# Testing Registration Policy with Two Beans Sharing the Same Name

> **Topic:** Spring Framework JMX  
> **Knowledge Group:** Practice  
> **Lesson:** Testing registration policy with two beans sharing the same name

## 1. Practice Objectives

In an \`MBeanServer\`, each \`ObjectName\` can identify **only one registration at a time**. When Spring's \`MBeanExporter\` attempts to register another bean under an already existing name, \`RegistrationPolicy\` governs how it is handled.

After this lab, you will be able to:

- Create two independent JMX beans that intentionally use **the same ObjectName**.
- Create an isolated \`MBeanServer\` so experiments do not affect the JVM's platform MBeans.
- Observe the three policies: \`FAIL_ON_EXISTING\`, \`IGNORE_EXISTING\`, and \`REPLACE_EXISTING\`.
- Read actual values from the \`MBeanServer\` after each scenario to determine which bean remains registered.
- Distinguish registration errors from Java object, naming strategy, and metadata assembler errors.
- Understand the difference between "the old MBean stays in the registry" and "the new MBean replaced the registration".
- Write reproducible integration tests with isolated cases and proper lifecycle cleanup.
- Know why you should not pick \`REPLACE_EXISTING\` merely to hide accidental duplicate naming errors.

## 2. Background: ObjectName Is the Registry Key

Suppose two Java beans have different implementations:

\`\`\`text
FirstCounter   -> value=10
SecondCounter  -> value=20
\`\`\`

Yet both are assigned the same management name:

\`\`\`text
lab.registration:type=Counter,name=shared
\`\`\`

An \`MBeanServer\` cannot simultaneously allow:

\`\`\`text
lab.registration:type=Counter,name=shared -> FirstCounter
lab.registration:type=Counter,name=shared -> SecondCounter
\`\`\`

It must resolve the conflict. The plain JMX API \`registerMBean\` normally throws \`InstanceAlreadyExistsException\` when the ObjectName already exists.

Spring provides the enum:

\`\`\`java
import org.springframework.jmx.support.RegistrationPolicy;
\`\`\`

with the relevant options:

| Policy | When ObjectName Is Free | When ObjectName Already Exists |
|---|---|---|
| \`FAIL_ON_EXISTING\` | Registers the new bean | Fails with an error without intentionally replacing the old registration |
| \`IGNORE_EXISTING\` | Registers the new bean | Skips the new registration, keeping the old bean |
| \`REPLACE_EXISTING\` | Registers the new bean | Unregisters the old MBean then registers the new MBean |

The difference is only clearly observable when two registrations target **the same server and the same ObjectName**. Two beans in two different MBeanServers can share the same ObjectName without colliding.

## 3. Experiment Diagram

\`\`\`text
                          Test JVM
                             |
                   Isolated MBeanServer
                             |
           lab.registration:type=Counter,name=shared
                             ^
                             |
             +---------------+----------------+
             |                                |
       First exporter                  Second exporter
       bean value=10                    bean value=20
      registers first                  registers second
                                              |
                                              v
                                     RegistrationPolicy
                                      /       |       \
                                    FAIL    IGNORE   REPLACE
\`\`\`

The goal of the lab is to observe **the values read through JMX** after each case, rather than just checking whether \`setRegistrationPolicy\` was called.

## 4. Project Setup

You can use Maven with Spring Framework JMX and JUnit 5. In a Spring Boot application that already has an appropriate starter, some dependencies may already be provided by dependency management.

Example project layout:

\`\`\`text
src/
  main/
    java/example/jmx/
      CounterMBean.java
      Counter.java
  test/
    java/example/jmx/
      RegistrationPolicyTest.java
\`\`\`

APIs used:

- \`javax.management.MBeanServer\`
- \`javax.management.MBeanServerFactory\`
- \`javax.management.ObjectName\`
- \`org.springframework.jmx.export.MBeanExporter\`
- \`org.springframework.jmx.support.RegistrationPolicy\`
- \`org.junit.jupiter.api.Test\`

With Spring Framework 6.x or equivalent, use a JDK compatible with the chosen Spring version; rely on your project's dependency management instead of pinning incompatible versions arbitrarily.

This exercise does not require opening a remote JMX port, does not need JConsole, and needs no system administrator privileges.

## 5. Create a Small Standard MBean to Identify the Bean

### 5.1. Management interface

\`\`\`java
package example.jmx;

public interface CounterMBean {
    int getValue();
    String getId();
}
\`\`\`

This interface follows the Standard MBean convention: implementation \`Counter\` has an interface named \`CounterMBean\`.

### 5.2. Implementation

\`\`\`java
package example.jmx;

public class Counter implements CounterMBean {

    private final String id;
    private final int value;

    public Counter(String id, int value) {
        this.id = id;
        this.value = value;
    }

    @Override
    public int getValue() {
        return value;
    }

    @Override
    public String getId() {
        return id;
    }
}
\`\`\`

Two instances:

\`\`\`java
Counter first = new Counter("first", 10);
Counter second = new Counter("second", 20);
\`\`\`

The \`Id\` and \`Value\` values let us determine **which registration is actually present** in the JMX registry.

Note: a Java bean existing in memory does not mean it has been registered as an MBean. We must read via \`MBeanServer.getAttribute\` to see what a JMX client observes.

## 6. Use a Dedicated MBeanServer for Each Test

Do not test \`REPLACE_EXISTING\` directly against the platform server without a clear reason. Create an isolated server:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer server =
    MBeanServerFactory.newMBeanServer("registration.lab");
\`\`\`

And a fixed ObjectName:

\`\`\`java
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "lab.registration:type=Counter,name=shared"
);
\`\`\`

\`newMBeanServer\` creates a new server that is not registered in the discovery list the way \`createMBeanServer\` does. The important thing here is that the test holds a direct reference to the server and passes that exact server into the exporters.

Do not use:

\`\`\`java
ManagementFactory.getPlatformMBeanServer()
\`\`\`

for collision experiments if the test runner or another component might already be registering MBeans with the same name.

## 7. Configure Two MBeanExporters Using the Same Server

Idea:

\`\`\`java
MBeanExporter firstExporter = new MBeanExporter();
firstExporter.setServer(server);
firstExporter.setBeans(Map.of(name.toString(), first));

MBeanExporter secondExporter = new MBeanExporter();
secondExporter.setServer(server);
secondExporter.setBeans(Map.of(name.toString(), second));
secondExporter.setRegistrationPolicy(policy);
\`\`\`

Here:

- \`firstExporter\` owns the initial registration.
- \`secondExporter\` attempts to register another bean under **the same ObjectName**.
- \`policy\` applies only to the second exporter's registration attempt.
- Both exporters are given the same \`MBeanServer\`; otherwise the duplicate name would not cause a conflict.
- Only one ObjectName is used for the test so the results are easy to interpret.

For the exporters to actually run, they must go through Spring's initialization lifecycle. Do not conclude that calling \`setBeans\` registers the MBean immediately.

## 8. Exporter Lifecycle in This Lab

When Spring creates an exporter following its normal lifecycle, it handles initialization, MBean registration, and cleanup when destroyed.

In unit/integration tests, you might use a helper:

\`\`\`java
private static MBeanExporter exporter(
        MBeanServer server,
        ObjectName name,
        Object bean,
        RegistrationPolicy policy
) {
    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(server);
    exporter.setBeans(Map.of(name.toString(), bean));
    exporter.setRegistrationPolicy(policy);
    return exporter;
}
\`\`\`

After constructing the object, initialize the lifecycle properly, e.g., invoking the callbacks supported by the exporter in your Spring version:

\`\`\`java
exporter.afterPropertiesSet();
exporter.afterSingletonsInstantiated();
\`\`\`

In Spring versions where the exporter registers directly in \`afterPropertiesSet\`, avoid triggering duplicate registration via another callback. When managing lifecycle manually outside an ApplicationContext, follow your specific version's contract. An approach less dependent on lifecycle internals is creating exporters as Spring beans inside \`AnnotationConfigApplicationContext\` and letting the container invoke callbacks.

The lab below uses **separate ApplicationContexts** to test Spring's true behavior without manually calling internal lifecycle hooks.

## 9. Fixture Design: One Context per Exporter

Suppose a factory method creates a separate context, while both contexts receive the same externally created server:

\`\`\`text
Context #1:
  Counter(first, 10)
  MBeanExporter #1
        |
        v
  Shared isolated MBeanServer

Context #2:
  Counter(second, 20)
  MBeanExporter #2
  RegistrationPolicy selected
        |
        v
  Same isolated MBeanServer
\`\`\`

The contexts are closed at the end of the test in a sensible order. The key point is that **both exporters are genuinely managed by Spring**.

A helper function can register beans directly via \`GenericApplicationContext\`, keeping in mind that \`MBeanExporter\` performs registration when the context refreshes, and transaction/lifecycle extras are unnecessary for this lab.

## 10. Scenario FAIL_ON_EXISTING

Start with an empty server:

\`\`\`text
server.isRegistered(name) = false
\`\`\`

Exporter #1 registers \`Counter("first", 10)\`:

\`\`\`text
server.isRegistered(name) = true
Id    = first
Value = 10
\`\`\`

Exporter #2 has:

\`\`\`java
RegistrationPolicy.FAIL_ON_EXISTING
\`\`\`

and tries to register \`Counter("second", 20)\` under the same ObjectName.

Expected result:

- The second exporter fails with a conflict error during registration.
- The original MBean remains registered, unless other application/test lifecycle cleanup intervenes.
- \`getAttribute(name, "Id")\` returns \`"first"\`.
- \`getAttribute(name, "Value")\` returns \`10\`.

Do not assert the exact full exception message; messages can change across Spring/JDK versions.

## 11. Scenario IGNORE_EXISTING

Start the same way as above:

\`\`\`text
server: shared -> first/10
\`\`\`

The second exporter configures:

\`\`\`java
RegistrationPolicy.IGNORE_EXISTING
\`\`\`

When encountering an existing ObjectName, Spring skips the new registration instead of replacing the old one.

Expected result:

\`\`\`text
isRegistered = true
Id           = first
Value        = 10
\`\`\`

Note: the second exporter starting successfully **does not prove the second MBean was exported**. That is precisely what this lab demonstrates.

If a dashboard still shows stale values after a deployment, \`IGNORE_EXISTING\` may be the reason. Do not equate "startup had no errors" with "the new version claimed the ObjectName".

## 12. Scenario REPLACE_EXISTING

The second exporter configures:

\`\`\`java
RegistrationPolicy.REPLACE_EXISTING
\`\`\`

When the name already exists, Spring replaces the registration.

\`\`\`text
Before:
  shared -> first/10

During replacement:
  unregister old MBean
  register new MBean

After success:
  shared -> second/20
\`\`\`

Expected result:

\`\`\`text
isRegistered = true
Id           = second
Value        = 20
\`\`\`

**Do not treat replacement as an atomic hot swap.** Between unregister and register, a client may fail to find the ObjectName. Listeners attached to the old MBean do not automatically transfer to the new MBean either.

If the first exporter closes after being replaced by the second exporter, the first exporter's cleanup may affect the current registration depending on ownership tracking and lifecycle mechanics. Therefore, the test should keep both contexts alive until results are asserted, then clean up in a controlled order.

## 13. Sample Test with JUnit 5 and Spring GenericApplicationContext

The code below illustrates an integration approach independent of annotation scanning: registering exporter beans in separate contexts, each referencing the same server.

\`\`\`java
package example.jmx;

import java.util.Map;

import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.context.support.GenericApplicationContext;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

import static org.junit.jupiter.api.Assertions.*;

class RegistrationPolicyTest {

    private static final String OBJECT_NAME =
        "lab.registration:type=Counter,name=shared";

    private GenericApplicationContext createContext(
            MBeanServer server,
            Counter counter,
            RegistrationPolicy policy
    ) {
        GenericApplicationContext context =
            new GenericApplicationContext();

        context.registerBean(
            "exporter",
            MBeanExporter.class,
            () -> {
                MBeanExporter exporter = new MBeanExporter();
                exporter.setServer(server);
                exporter.setBeans(
                    Map.of(OBJECT_NAME, counter)
                );
                exporter.setRegistrationPolicy(policy);
                return exporter;
            }
        );

        context.refresh();
        return context;
    }

    private static String id(
            MBeanServer server,
            ObjectName name
    ) throws Exception {
        return (String) server.getAttribute(name, "Id");
    }

    private static int value(
            MBeanServer server,
            ObjectName name
    ) throws Exception {
        return (Integer) server.getAttribute(name, "Value");
    }

    @Test
    void failOnExistingKeepsFirstRegistration()
            throws Exception {
        MBeanServer server =
            MBeanServerFactory.newMBeanServer("registration.lab");
        ObjectName name = new ObjectName(OBJECT_NAME);

        try (GenericApplicationContext first =
                 createContext(
                     server,
                     new Counter("first", 10),
                     RegistrationPolicy.FAIL_ON_EXISTING
                 )) {

            assertEquals("first", id(server, name));

            assertThrows(
                RuntimeException.class,
                () -> {
                    try (GenericApplicationContext ignored =
                             createContext(
                                 server,
                                 new Counter("second", 20),
                                 RegistrationPolicy.FAIL_ON_EXISTING
                             )) {
                        fail("Expected duplicate registration failure");
                    }
                }
            );

            assertTrue(server.isRegistered(name));
            assertEquals("first", id(server, name));
            assertEquals(10, value(server, name));
        }
    }

    @Test
    void ignoreExistingKeepsFirstRegistration()
            throws Exception {
        MBeanServer server =
            MBeanServerFactory.newMBeanServer("registration.lab");
        ObjectName name = new ObjectName(OBJECT_NAME);

        try (GenericApplicationContext first =
                 createContext(
                     server,
                     new Counter("first", 10),
                     RegistrationPolicy.FAIL_ON_EXISTING
                 );
             GenericApplicationContext second =
                 createContext(
                     server,
                     new Counter("second", 20),
                     RegistrationPolicy.IGNORE_EXISTING
                 )) {

            assertEquals("first", id(server, name));
            assertEquals(10, value(server, name));
        }
    }

    @Test
    void replaceExistingPublishesSecondRegistration()
            throws Exception {
        MBeanServer server =
            MBeanServerFactory.newMBeanServer("registration.lab");
        ObjectName name = new ObjectName(OBJECT_NAME);

        GenericApplicationContext first = createContext(
            server,
            new Counter("first", 10),
            RegistrationPolicy.FAIL_ON_EXISTING
        );

        GenericApplicationContext second = null;

        try {
            second = createContext(
                server,
                new Counter("second", 20),
                RegistrationPolicy.REPLACE_EXISTING
            );

            assertTrue(server.isRegistered(name));
            assertEquals("second", id(server, name));
            assertEquals(20, value(server, name));
        } finally {
            // The second context now manages the new registration.
            if (second != null) {
                second.close();
            }
            first.close();
        }
    }
}
\`\`\`

The \`Counter\` and \`CounterMBean\` classes are the fixtures declared above. The sample uses \`GenericApplicationContext.registerBean\` (available in modern Spring releases). If your project uses an older Spring Framework without this overload, switch to equivalent Java configuration.

### Note on exception assertions

Duplicate registration failures may be wrapped by Spring in \`BeanCreationException\`, \`MBeanExportException\`, or an exception whose cause is \`InstanceAlreadyExistsException\`. Therefore, the test example uses \`RuntimeException\` for illustration and should narrow the exception type to match your actual library version when applied.

The core observation is that the first MBean remains present and readable after the failed second registration.

## 14. Expected Results Table

| Case | Exporter #2 | Startup Error? | \`Id\` After Second Registration | \`Value\` |
|---|---|---|---|---|
| Control | Not created | No | \`first\` | \`10\` |
| \`FAIL_ON_EXISTING\` | Yes | Yes, conflict error | \`first\` | \`10\` |
| \`IGNORE_EXISTING\` | Yes | Normally no | \`first\` | \`10\` |
| \`REPLACE_EXISTING\` | Yes | No if replacement succeeds | \`second\` | \`20\` |

This table assumes only two exporters in an isolated MBeanServer, that the first registration succeeds, and that no other lifecycle operations occur between reads.

## 15. Verification with MBeanInfo

Reading metadata:

\`\`\`java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attr : info.getAttributes()) {
    System.out.println(
        attr.getName() +
        " type=" + attr.getType() +
        " readable=" + attr.isReadable()
    );
}
\`\`\`

In the fixture, both the first and second beans share the same implementation class, so their metadata is virtually identical. Thus reading \`MBeanInfo\` alone is insufficient to distinguish which registration is active; you must read \`Id\` and \`Value\` as the test does.

With different implementations, \`MBeanInfo\` also confirms that the replaced contract may differ, though that is a separate compatibility concern.

## 16. Testing with the Plain JMX API for Comparison

If you bypass Spring's exporter and call directly:

\`\`\`java
server.registerMBean(
    new Counter("first", 10),
    name
);

server.registerMBean(
    new Counter("second", 20),
    name
);
\`\`\`

The second registration throws \`InstanceAlreadyExistsException\`.

Plain JMX has no \`RegistrationPolicy\` parameter on \`registerMBean\`. The IGNORE/REPLACE policies are behaviors added by Spring's exporter when handling registration exceptions.

This separates responsibilities:

\`\`\`text
JMX MBeanServer:
  protects ObjectName uniqueness

Spring MBeanExporter:
  decides how to handle duplicate registration
  according to RegistrationPolicy
\`\`\`

## 17. Testing Two Beans with the Same Name on Different Servers

Try:

\`\`\`java
MBeanServer serverA =
    MBeanServerFactory.newMBeanServer("lab.a");

MBeanServer serverB =
    MBeanServerFactory.newMBeanServer("lab.b");
\`\`\`

Register the same ObjectName into each server:

\`\`\`java
serverA.registerMBean(new Counter("first", 10), name);
serverB.registerMBean(new Counter("second", 20), name);
\`\`\`

Valid result:

\`\`\`text
serverA getAttribute(Id) = first
serverB getAttribute(Id) = second
\`\`\`

Because uniqueness applies **within each MBeanServer**, not across the entire JVM.

If you see two MBeans with "the same name" without an error, determine whether they actually reside on two different servers or simply have extra key properties forming distinct ObjectNames.

## 18. Distinguishing the Same ObjectName from Similar Names

The following ObjectNames are **different**:

\`\`\`text
lab.registration:type=Counter,name=first
lab.registration:type=Counter,name=second
\`\`\`

Whereas:

\`\`\`text
lab.registration:name=shared,type=Counter
lab.registration:type=Counter,name=shared
\`\`\`

are two ways of writing the same set of key properties, normalized via \`getCanonicalName()\`.

\`\`\`java
ObjectName a = new ObjectName(
    "lab.registration:type=Counter,name=shared"
);

ObjectName b = new ObjectName(
    "lab.registration:name=shared,type=Counter"
);

System.out.println(a.equals(b)); // true
\`\`\`

Therefore, do not rely on the order of key properties in a string to conclude two names differ. Use \`ObjectName.equals\` or canonical names.

## 19. Diagnosing When the IGNORE Case Behaves Unexpectedly

If \`IGNORE_EXISTING\` still reads \`second/20\`, possible causes include:

1. The first exporter never actually registered.
2. The two exporters use different MBeanServers and you are reading the second server.
3. The ObjectNames are not actually identical.
4. The policy was not applied to the exporter that ran.
5. Another exporter replaced the registration before the assertion.
6. Context lifecycle cleaned up the old registration.

Check:

\`\`\`java
assertTrue(server.isRegistered(name));
System.out.println(name.getCanonicalName());
System.out.println(server.getAttribute(name, "Id"));
\`\`\`

And review the actual configuration of \`setServer\`, \`setBeans\`, \`setRegistrationPolicy\`, and the order of context refreshes.

## 20. Diagnosing When the REPLACE Case Behaves Unexpectedly

If \`REPLACE_EXISTING\` does not show \`second/20\`, it may be because:

- The second exporter did not run registration.
- The second bean failed export rules.
- Replacement failed due to another exception.
- Different ObjectName or different MBeanServer.
- Cleanup from one context unregistered the name after replacement.
- A third exporter re-registered another MBean.

Do not try to fix it by repeatedly calling \`registerMBean\` or flipping policies. Collect exceptions and inspect the registry at each step.

## 21. Multiple Beans in a Single Exporter

This lab uses **two exporters** to deliberately create a conflict on the same server. If you write:

\`\`\`java
exporter.setBeans(Map.of(
    "lab.registration:type=Counter,name=shared", first,
    "lab.registration:type=Counter,name=shared", second
));
\`\`\`

then Java's \`Map.of\` throws a duplicate key error before the exporter is ever called. That is **not a RegistrationPolicy test**.

If a \`Map\` allows overwriting the same key, the second value simply overwrites the first inside the Java map, still failing to produce two independent registrations.

Thus, the right approach is two sequential registration attempts, such as via two exporters or a direct server registration before the new exporter initializes.

## 22. Testing Against a Bean Registered via Plain JMX

A shorter variation:

1. Create an isolated server.
2. Register \`first\` via \`server.registerMBean(first, name)\`.
3. Create an \`MBeanExporter\` for \`second\` with the same ObjectName.
4. Apply each policy and observe.

Pros: does not depend on the first exporter's lifecycle. Cons: only verifies how Spring handles conflict with an existing MBean, not interactions between two exporters/contexts.

Use this variation when isolating policy behavior, then run the two-exporter lab to understand lifecycle behavior.

## 23. Lifecycle Cleanup and Ownership

An important nuance of \`REPLACE_EXISTING\`: when the second exporter replaces the first exporter's registration, it does not make the first exporter the owner of the second MBean.

This scenario can arise:

\`\`\`text
Context A registers first/10
Context B replaces with second/20
Context A closes
Context B still active
\`\`\`

Depending on how Spring's exporter tracks registered ObjectNames, closing context A may affect the MBean currently under that name. Thus, do not experiment with these complex lifecycles on a shared production server without understanding ownership.

In tests:

- Assert results **while both contexts are alive**.
- Close context B first, then close context A in the replace case.
- Do not assume the \`first\` MBean is automatically restored after B closes.
- Clean up the dedicated test server if needed.
- If notification listeners were attached to the old MBean, do not assume listeners migrate to the new MBean.

## 24. Why FAIL_ON_EXISTING Is Often Useful

An ObjectName conflict is not always something to ignore or overwrite. It can signal:

- A bean was exported twice.
- Two ApplicationContexts manage the same logical name.
- Auto-configuration and a manual exporter overlap.
- An \`ObjectNamingStrategy\` is too broad.
- A service refactor caused duplicate names.
- A monitoring MBean was hijacked by another component.

In these cases, \`FAIL_ON_EXISTING\` surfaces the issue early instead of silently masking it.

\`IGNORE_EXISTING\` is helpful when you genuinely want to preserve an earlier registration, though it can leave a deployment running with an old MBean.

\`REPLACE_EXISTING\` is helpful when intentional replacement is explicitly designed, though it carries risks around lost listeners, state, or old contracts.

## 25. Policy Decision Table

| Question | What to Consider |
|---|---|
| Is a duplicate name a sign of misconfiguration? | \`FAIL_ON_EXISTING\` |
| Did another module register an MBean you want to keep untouched? | \`IGNORE_EXISTING\`, after verifying ownership |
| Do you intentionally want to replace an old MBean with a new version? | \`REPLACE_EXISTING\`, with a compatibility plan |
| Unsure which MBean currently owns the name? | Stop and inspect; do not use REPLACE blindly |
| Do both beans actually need to exist concurrently? | Change the ObjectName to be unique; do not use a policy to paper over bad naming |
| Are clients listening to old notifications? | Account for listener lifecycle and re-subscription |

Final point: registration policy does not replace naming strategy design and ownership.

## 26. Lab Extension: Testing Notification Listeners

If both old and new MBeans emit notifications, you can:

1. Register a listener on the old MBean.
2. Emit a notification to confirm the listener works.
3. Replace the registration using \`REPLACE_EXISTING\`.
4. Emit a notification from the new MBean.
5. Observe whether the old listener still receives events.
6. If not, re-register the listener and verify.

This scenario should only be run with an MBean fixture supporting \`NotificationBroadcaster\` or \`NotificationPublisherAware\`. The Standard MBean \`Counter\` above does not emit notifications by itself.

Do not use \`isRegistered\` returning true as proof that notification subscriptions were preserved.

## 27. Lab Extension: Comparing MBean Contracts

Try replacing \`Counter\` with an implementation having different metadata:

\`\`\`text
Old:
  Value : int
  Id : String

New:
  Total : long
  Source : String
\`\`\`

With the same ObjectName and \`REPLACE_EXISTING\`, an old client calling \`getAttribute("Value")\` will fail. A stable ObjectName does not guarantee attribute/operation compatibility.

When upgrading an MBean, review:

- Attribute names, types, and read/write flags.
- Operation names, signatures, and return types.
- Notification types.
- Client proxy/interface compatibility.
- ObjectName stability.
- State transition after replacement.

## 28. Self-Study Exercises

### Exercise A: Switch policies

Run all three cases and record a table:

\`\`\`text
Policy:
Startup status:
isRegistered:
Id:
Value:
Exception type:
\`\`\`

### Exercise B: Rename the second bean

Change the second exporter's ObjectName to:

\`\`\`text
lab.registration:type=Counter,name=other
\`\`\`

Expected result: no more conflict; both MBeans can coexist if the exporters and server are configured properly.

### Exercise C: Use two different servers

Point exporter #1 to server A and exporter #2 to server B while keeping the ObjectName identical. Prediction: no conflict because each server has its own registry.

### Exercise D: Close context A after B replaces it

Inspect the registry after A closes and note the behavior of your current Spring version. Do not assume lifecycle restoration. This is an advanced test to understand ownership when two exporters contend for the same name.

### Exercise E: Inspect metadata

Read \`MBeanInfo\` in all three cases. Explain why identical metadata is not enough to distinguish \`first\` and \`second\` when both use the same class.

## 29. Self-Check Questions

1. Why can two different Java beans not register under the same ObjectName in one MBeanServer?
2. What does \`FAIL_ON_EXISTING\` do when the name already exists?
3. Why does \`IGNORE_EXISTING\` not mean the second bean exported successfully?
4. What is the expected outcome of \`REPLACE_EXISTING\` with \`first=10\` and \`second=20\`?
5. Why must you read \`getAttribute\` instead of only checking \`isRegistered\`?
6. Do two MBeanServers in the same JVM share a registry?
7. Why can using two identical keys in \`Map.of\` not test \`RegistrationPolicy\`?
8. Why is replacement not an atomic hot swap?
9. When the old context closes after replacement, why must you consider lifecycle cleanup?
10. When should you fix the ObjectName instead of changing the registration policy?

## 30. Key Takeaways

\`\`\`text
First exporter:
  shared -> first / 10

Second exporter:
  shared -> second / 20

FAIL_ON_EXISTING:
  conflict error
  registry remains: first / 10

IGNORE_EXISTING:
  skips second registration
  registry remains: first / 10

REPLACE_EXISTING:
  unregister first
  register second
  registry: second / 20
\`\`\`

**Core principle:** test \`RegistrationPolicy\` using **two registrations with the same ObjectName on the same MBeanServer**, then read attributes to identify which bean is actually being managed. \`FAIL_ON_EXISTING\` surfaces conflicts, \`IGNORE_EXISTING\` preserves the old registration, and \`REPLACE_EXISTING\` replaces the registration along with lifecycle, state, listener, and JMX contract risks.