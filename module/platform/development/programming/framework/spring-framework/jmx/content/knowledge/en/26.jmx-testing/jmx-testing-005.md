# Testing Duplicate Registration by Policy in Spring Framework JMX

## Goal

This lesson guides you through testing scenarios where two Spring `MBeanExporter` instances or two components attempt to register MBeans under the same ObjectName in the same MBeanServer. You will distinguish the three `RegistrationPolicy` values: `FAIL_ON_EXISTING`, `IGNORE_EXISTING`, and `REPLACE_EXISTING`; verify the actual object exposed; test cleanup; and avoid interfering with MBeans owned by other contexts.

## 1. What Is Duplicate Registration?

In JMX, an MBeanServer cannot hold two MBeans with the same ObjectName at the same time. For example:

```text
learning.jmx:type=CacheMonitor,name=Primary
```

If context A has already registered MBean OLD under this name, context B attempting to register MBean NEW under the same name in that exact server encounters duplicate registration.

Two identical ObjectNames in two different MBeanServers do not conflict. Identical Java class names also do not cause an error if their ObjectNames differ.

```text
Context A -> MBeanExporter A --+
                               +--> one MBeanServer
Context B -> MBeanExporter B --+
                               |
                    same ObjectName -> collision
```

Because ObjectName is the management identity, the collision handling policy directly affects clients reading attributes or invoking operations.

## 2. Three Policies of Spring MBeanExporter

Spring Framework provides the enum `org.springframework.jmx.support.RegistrationPolicy`.

| Policy | When the name already exists | What to test |
|---|---|---|
| FAIL_ON_EXISTING | Fails with an error, does not register replacement | OLD remains intact, startup of B fails |
| IGNORE_EXISTING | Skips the new registration | OLD remains the object seen by clients |
| REPLACE_EXISTING | Unregisters old registration, registers new one | NEW is published under the old name |

Simply asserting that the Spring context starts up is insufficient. With IGNORE_EXISTING, context B can start cleanly while the queried MBean is still OLD. With REPLACE_EXISTING, the same ObjectName may point to a different management contract.

You must verify registration status, owner identity, attributes/operations, and cleanup.

## 3. Preparing a Standard MBean as a Test Fixture

To identify which object is currently exported, use an `OwnerId` attribute.

File `TestResourceMBean.java`:

```java
package example.jmx;

public interface TestResourceMBean {
    String getOwnerId();
}
```

File `TestResource.java`:

```java
package example.jmx;

public class TestResource implements TestResourceMBean {
    private final String ownerId;

    public TestResource(String ownerId) {
        this.ownerId = ownerId;
    }

    @Override
    public String getOwnerId() {
        return ownerId;
    }
}
```

An OLD object returns `OwnerId` as `"OLD"`, while a NEW object returns `"NEW"`. That way you can verify the object actually exposed via `getAttribute`, rather than checking `isRegistered` alone.

## 4. Creating a Dedicated MBeanServer

Do not default to using the platform MBeanServer for all integration tests because it may be shared by other tests or frameworks in the same JVM.

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

MBeanServer server =
    MBeanServerFactory.createMBeanServer("test.duplicate");

ObjectName name = new ObjectName(
    "learning.jmx:type=TestResource,name=Primary"
);
```

A dedicated server keeps tests independent, especially when the same ObjectName is used across cases.

Once contexts/exporters have closed and no consumers remain, the test can release the server it created:

```java
MBeanServerFactory.releaseMBeanServer(server);
```

Do not call release on the platform server or a shared server that the test does not own.

## 5. Creating the Old Registration Before Testing the Policy

```java
server.registerMBean(new TestResource("OLD"), name);

assertTrue(server.isRegistered(name));
assertEquals("OLD", server.getAttribute(name, "OwnerId"));
```

This is the precondition. If the name does not yet exist, you are not testing duplicate registration and all policies may behave identically.

A good test sets a clear precondition so FAIL, IGNORE, and REPLACE are verified against the same logical scenario.

## 6. Configuring MBeanExporter with a Policy

Example creating an exporter:

```java
import java.util.Map;

import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

MBeanExporter exporter = new MBeanExporter();
exporter.setServer(server);
exporter.setRegistrationPolicy(RegistrationPolicy.IGNORE_EXISTING);
exporter.setBeans(Map.of(
    "learning.jmx:type=TestResource,name=Primary",
    new TestResource("NEW")
));
```

In a Spring application, make the exporter a bean managed by `ApplicationContext` so register/unregister callbacks run with the Spring lifecycle.

The configuration above demonstrates setting the policy. Simply instantiating the exporter does not guarantee the full initialization/destroy lifecycle has run.

## 7. Helper to Build a Spring Context per Policy

You can write a helper for integration tests so each case uses a separate `ApplicationContext`.

```java
package example.jmx;

import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

public final class TestContexts {

    private TestContexts() {}

    public static AnnotationConfigApplicationContext start(
            MBeanServer server,
            RegistrationPolicy policy,
            String owner) {

        AnnotationConfigApplicationContext context =
            new AnnotationConfigApplicationContext();

        context.registerBean("testResource", TestResource.class,
            () -> new TestResource(owner));

        context.registerBean("mbeanExporter", MBeanExporter.class,
            () -> {
                MBeanExporter exporter = new MBeanExporter();
                exporter.setServer(server);
                exporter.setRegistrationPolicy(policy);
                exporter.setBeans(Map.of(
                    "learning.jmx:type=TestResource,name=Primary",
                    context.getBean(TestResource.class)
                ));
                return exporter;
            });

        try {
            context.refresh();
            return context;
        } catch (RuntimeException failure) {
            context.close();
            throw failure;
        }
    }
}
```

Benefit: one context owns one exporter. When the test closes the context, the exporter cleans up registrations within its scope. If refresh fails, the helper still closes the context so resources are not left dangling.

Each test creates a fresh server, avoiding any changes to other MBeans in the JVM.

## 8. Testing FAIL_ON_EXISTING

Expectation: exporter B must not overwrite OLD; startup is rejected and the ObjectName still points to OLD.

```java
@Test
void failOnExistingRejectsDuplicate() throws Exception {
    MBeanServer server =
        MBeanServerFactory.createMBeanServer("test.fail");

    ObjectName name = new ObjectName(
        "learning.jmx:type=TestResource,name=Primary"
    );

    server.registerMBean(new TestResource("OLD"), name);

    try {
        assertThrows(RuntimeException.class, () ->
            TestContexts.start(
                server,
                RegistrationPolicy.FAIL_ON_EXISTING,
                "NEW"
            )
        );

        assertTrue(server.isRegistered(name));
        assertEquals("OLD", server.getAttribute(name, "OwnerId"));
    } finally {
        if (server.isRegistered(name)) {
            server.unregisterMBean(name);
        }
        MBeanServerFactory.releaseMBeanServer(server);
    }
}
```

This is a relatively broad exception assertion for illustration. When high precision is required, inspect the root cause (e.g., duplicate registration error wrapped by Spring into a startup exception) rather than asserting an arbitrary `RuntimeException`.

Do not fix this error by switching to REPLACE_EXISTING unless replacing the old MBean is genuinely intended.

## 9. Testing IGNORE_EXISTING

Expectation: context B can start, but the ObjectName continues pointing to OLD. Closing B must not delete MBean OLD.

```java
@Test
void ignoreExistingKeepsOldRegistration() throws Exception {
    MBeanServer server =
        MBeanServerFactory.createMBeanServer("test.ignore");

    ObjectName name = new ObjectName(
        "learning.jmx:type=TestResource,name=Primary"
    );

    server.registerMBean(new TestResource("OLD"), name);

    AnnotationConfigApplicationContext context = null;

    try {
        context = TestContexts.start(
            server,
            RegistrationPolicy.IGNORE_EXISTING,
            "NEW"
        );

        assertTrue(server.isRegistered(name));
        assertEquals("OLD", server.getAttribute(name, "OwnerId"));
    } finally {
        if (context != null) {
            context.close();
        }
    }

    try {
        assertTrue(server.isRegistered(name));
        assertEquals("OLD", server.getAttribute(name, "OwnerId"));
    } finally {
        server.unregisterMBean(name);
        MBeanServerFactory.releaseMBeanServer(server);
    }
}
```

Key point to remember: IGNORE does not mean NEW was successfully exported. Skipping a registration is different from replacing a registration.

In production-grade tests, wrap cleanup in an outer `try/finally` so cleanup still runs if startup or assertions unexpectedly throw.

## 10. Testing REPLACE_EXISTING

Expectation: the new MBean is published and `OwnerId` becomes NEW. When exporter B closes and owns that registration, you can verify unexport.

```java
@Test
void replaceExistingPublishesNewRegistration() throws Exception {
    MBeanServer server =
        MBeanServerFactory.createMBeanServer("test.replace");

    ObjectName name = new ObjectName(
        "learning.jmx:type=TestResource,name=Primary"
    );

    server.registerMBean(new TestResource("OLD"), name);

    AnnotationConfigApplicationContext context =
        TestContexts.start(
            server,
            RegistrationPolicy.REPLACE_EXISTING,
            "NEW"
        );

    try {
        assertTrue(server.isRegistered(name));
        assertEquals("NEW", server.getAttribute(name, "OwnerId"));
    } finally {
        context.close();
    }

    try {
        assertFalse(server.isRegistered(name));
    } finally {
        MBeanServerFactory.releaseMBeanServer(server);
    }
}
```

With a manual old registration and one exporter B, this example demonstrates the effect of the policy. However, when both A and B are live Spring exporters, test closing contexts in different orders to observe ownership; do not assume REPLACE is a safe migration mechanism in every case.

## 11. Summary Test Matrix

| Scenario | FAIL | IGNORE | REPLACE |
|---|---|---|---|
| OLD already registered | Precondition | Precondition | Precondition |
| B initializes successfully | No | Yes | Yes |
| OwnerId after attempt | OLD | OLD | NEW |
| MBean overwritten | No | No | Yes |
| Does closing B delete OLD? | No | No | OLD was already replaced |
| Does closing B unregister NEW? | NEW not registered | NEW not registered | Yes if B owns it |
| Caution needed on shared ownership | Yes | Yes | Especially important |

A parameterized test over the enum can reduce boilerplate, though each case still needs an independent MBeanServer, ObjectName, and cleanup.

```java
@ParameterizedTest
@EnumSource(RegistrationPolicy.class)
void duplicatePolicyBehavior(RegistrationPolicy policy) {
    // Arrange: dedicated server, OLD registration.
    // Act: create exporter B with policy.
    // Assert: exception/OwnerId/registration/cleanup.
}
```

## 12. Also Inspecting MBeanInfo

`OwnerId` identifies the object, but does not prove contract compatibility.

```java
MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo a : info.getAttributes()) {
    System.out.println(a.getName() + ":" + a.getType());
}

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.println(op.getName());
}
```

With REPLACE, the new MBean may expose different attributes/operations even though the ObjectName stays the same. Monitoring scripts or JConsole may encounter `AttributeNotFoundException` or operation mismatches after replacement.

If you need to replace an MBean in a real environment, treat ObjectName, attributes, types, operation signatures, read/write semantics, and notification metadata as a contract requiring migration.

## 13. Two ApplicationContexts Alive Simultaneously

Another scenario is when both A and B own exporters:

```text
Context A -- exporter A --+
                          +--> shared MBeanServer
Context B -- exporter B --+
```

Sequence:

1. Start A and register the ObjectName.
2. Start B with REPLACE_EXISTING.
3. B replaces A's registration.
4. A or B closes.

Do not assume context A knows that B replaced the MBean. If exporter A still tracks the registration it created, closing A may affect that name depending on the implementation and ownership handling.

Tests should cover:

- Start A → Start B(IGNORE) → Close B: A remains registered.
- Start A → Start B(REPLACE) → Close B: observe whether B cleans up and whether A automatically restores itself.
- Start A → Start B(REPLACE) → Close A: observe whether B retains its registration.
- Start A → Start B(FAIL): B fails; A continues operating.

In system design, the usual solution is **a single owner per ObjectName**. If there are two logical resources, choose distinct ObjectNames.

## 14. RegistrationPolicy Is Not a JVM-Wide Policy

The property on the exporter:

```java
exporter.setRegistrationPolicy(
    RegistrationPolicy.REPLACE_EXISTING
);
```

only affects how that exporter performs registration. It does not change how manual `registerMBean` calls behave.

Direct JMX API example:

```java
server.registerMBean(new TestResource("OLD"), name);
server.registerMBean(new TestResource("NEW"), name);
```

The second call can throw `InstanceAlreadyExistsException` if the name is still registered. Manual replacement requires controlled unregister/register logic, which is the responsibility of code calling the JMX API.

Spring `RegistrationPolicy` is the configurable mechanism inside `MBeanExporter` to handle this situation.

## 15. Cleanup and Avoiding Impact on Other Tests

Never do blind cleanup on a shared platform server:

```java
if (platformServer.isRegistered(name)) {
    platformServer.unregisterMBean(name);
}
```

This snippet can delete another component's MBean if the test does not own that name.

A sound isolation workflow:

1. Create a dedicated MBeanServer for the test.
2. Create the OLD registration owned by the test.
3. Create exporter B with the policy.
4. Assert actual state.
5. Close ApplicationContext B if opened.
6. Unregister any registrations still owned by the test.
7. Release the MBeanServer if created via factory and no consumers remain.

When tests run in parallel, do not share the same MBeanServer and ObjectName unless sharing itself is the subject under test.

## 16. Common Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| FAIL does not error | Duplicate not created on the same server | Check server identity and ObjectName |
| IGNORE returns OwnerId NEW | OLD did not exist yet or wrong policy | Check precondition and exporter config |
| REPLACE still returns OLD | Exporter did not replace registration | Check logs and `getAttribute` |
| Flaky pass/fail tests | Shared platform server or multiple tests using same name | Use a dedicated server |
| Context B refresh failure leaves state | Not closed on startup error | Helper closes inside catch block |
| MBean vanishes after closing A | Shared ownership, cleanup affects replaced name | Test shutdown order, avoid two exporters owning same name |
| Contract changes after REPLACE | NEW has different metadata from OLD | Compare `MBeanInfo` |
| Test cleanup removes external MBeans | Blind unregister on shared server | Use isolated server and ownership |
| MBeanServerFactory retains references | Test server not released | Release when proper owner |
| Assertion fails for wrong reason | Overly broad `RuntimeException` assertion | Inspect root cause |

## 17. Testing Checklist

Before running:

1. Is there exactly one test MBeanServer?
2. Was OLD registered beforehand?
3. Do OLD and NEW share the exact same ObjectName in the same server?
4. Is the effective `RegistrationPolicy` set properly?
5. Is there a clear data-driven way to distinguish OLD/NEW?
6. Is the exception tested for FAIL?
7. Is preserving OLD tested for IGNORE?
8. Is replacing with NEW tested for REPLACE?
9. Are unregistration/cleanup tested per policy?
10. Are multiple contexts and close order tested if needed?
11. Is the shared platform server avoided?
12. Are attributes/operations verified with `MBeanInfo`?
13. Do you avoid releasing a server the test does not own?
14. Is the exception root cause checked when startup fails?

## 18. Practice Exercises

**Exercise 1:** Create OLD, test FAIL_ON_EXISTING, and assert the exception and that OLD is unchanged.

**Exercise 2:** Create OLD, test IGNORE_EXISTING, and assert context B succeeds while `OwnerId` remains OLD. Close B and verify OLD still exists.

**Exercise 3:** Create OLD, test REPLACE_EXISTING, assert `OwnerId` becomes NEW, then close B to verify cleanup.

**Exercise 4:** Create two contexts A/B on the same server, and test different close orders under REPLACE. Record registration states and explain the risk of shared ownership.

**Exercise 5:** Create NEW with a different `MBeanInfo` from OLD, compare metadata after REPLACE, and plan compatibility with JMX clients.

## 19. Key Takeaways

- Duplicate registration occurs when two registrations use the same ObjectName in the **same MBeanServer**.
- `FAIL_ON_EXISTING` throws an error and keeps the old MBean.
- `IGNORE_EXISTING` keeps the old MBean; it does not mean the new MBean was exported.
- `REPLACE_EXISTING` publishes the new MBean and can alter the contract under the same ObjectName.
- Proper tests check `OwnerId` or another distinguishing value, not merely `isRegistered`.
- With multiple live exporters, ownership and shutdown order are critical.
- Isolate MBeanServers per test, perform controlled cleanup, and inspect `MBeanInfo` to catch unintended changes.

## References

- Spring Framework JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring MBeanExporter API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring RegistrationPolicy API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/support/RegistrationPolicy.html
- Java SE MBeanServer API: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
