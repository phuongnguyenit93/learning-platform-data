# Testing Restarts and Redeploys with Spring JMX Registration Policy

## 1. Why Do Restarts and Redeploys Easily Cause JMX Errors?

In Spring Framework JMX, `MBeanExporter` registers MBeans with an `MBeanServer` when the application starts. When the application or `ApplicationContext` closes, the exporter must release the registrations it owns. Problems arise if a module restarts, a new context is created in the same JVM, or an application redeploys while the registry still holds the old `ObjectName`.

Common symptoms include:

- The first startup succeeds, while the second throws `InstanceAlreadyExistsException`.
- Export configuration or bean names are changed, yet the old MBean still appears.
- Another application owning an MBean with the same name loses its MBean when the new module starts.
- Hot reload works, while a full redeploy fails due to incomplete shutdown.
- Tests pass individually, yet fail across the full suite due to the same `ObjectName` in the platform server.
- JConsole shows an MBean from the old context, or an operation invokes an object that was already closed.

`MBeanExporter` provides a **registration policy** to decide behavior when an ObjectName already exists. However, a policy does not replace lifecycle management. Restart/redeploy testing must verify **registration**, **conflict handling**, and **owner-correct unregistration**.

## 2. Lifecycle Model

```text
JVM / MBeanServer stays alive
        |
        +-- Context A startup
        |       +-- exporter registers ObjectName X -> MBean A
        |
        +-- Context A shutdown
        |       +-- exporter unregisters X (if owned)
        |
        +-- Context B startup
        |       +-- exporter registers ObjectName X -> MBean B
        |
        +-- Context B shutdown
                +-- cleans up registrations and connectors owned by B
```

In redeploy environments, the JVM/MBeanServer can outlive an `ApplicationContext` or a web application classloader. If an MBean retains references to old beans/classloaders, failing to unregister can cause resource and classloader leaks in addition to duplicate-name errors.

Distinguish three states: `ObjectName` **does not exist yet**, **already exists owned by the current exporter**, or **already exists owned by another party**. A sound policy must be clear in every state.

## 3. Three Registration Behaviors on Name Collisions

Spring `MBeanExporter` supports registration modes via values corresponding to `RegistrationPolicy`:

| Policy | When ObjectName Does Not Exist | When ObjectName Already Exists | Caution Needed |
| --- | --- | --- | --- |
| `FAIL_ON_EXISTING` | Registers | Fails with an error | Helps catch collisions, though startup may fail |
| `IGNORE_EXISTING` | Registers | Keeps existing MBean, skips new bean | New app may run while clients still see the old MBean |
| `REPLACE_EXISTING` | Registers | Replaces existing registration | May claim a name owned by another component |

Policy names illustrate the general semantics. When configuring specifically, use `setRegistrationPolicy(RegistrationPolicy....)` appropriate to your Spring version, or legacy `registrationBehavior` if a project still uses that API.

Example:

```java
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

MBeanExporter exporter = new MBeanExporter();
exporter.setRegistrationPolicy(RegistrationPolicy.FAIL_ON_EXISTING);
```

**Do not use `REPLACE_EXISTING` as a cure-all for restart errors.** Even if the policy lets a new context replace the old context's MBean, you must still know whether the old context is still running and who is responsible for cleanup. Replacing can cause a live system to lose its proper management endpoint.

## 4. Creating a Small MBean for Lifecycle Testing

A minimal Standard MBean:

```java
package com.example.jmx;

public interface LifecycleProbeMBean {
    String getGeneration();
}
```

```java
package com.example.jmx;

public final class LifecycleProbe implements LifecycleProbeMBean {
    private final String generation;

    public LifecycleProbe(String generation) {
        this.generation = generation;
    }

    @Override
    public String getGeneration() {
        return generation;
    }
}
```

`Generation` distinguishes instances before and after a restart. If you only check `isRegistered(name)`, a test may pass even though the registry holds an old MBean; reading an attribute representing the bean's generation confirms the right instance was registered.

## 5. Testing with an Isolated MBeanServer

When testing registration policies, isolate with `MBeanServerFactory.createMBeanServer()` and release resources after the test:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer server =
    MBeanServerFactory.createMBeanServer("com.example.test");

try {
    // Initialize exporters with this test server.
} finally {
    MBeanServerFactory.releaseMBeanServer(server);
}
```

An isolated server reduces collisions with JVM MBeans and other tests. However, **releasing from the factory does not automatically guarantee cleanup of other resources**: close the Spring context so the exporter unregisters, close connectors if the test created them, and avoid letting references outlive the test.

If you need to test integration against the platform server, use a unique domain/ObjectName per test and never unregister MBeans owned by other tests.

## 6. Configuring an Exporter with a Fixed ObjectName

Example using `MBeanExporter` explicitly:

```java
import java.util.Map;
import javax.management.MBeanServer;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

public final class ExporterFactory {
    public static MBeanExporter create(
            MBeanServer server,
            String generation,
            RegistrationPolicy policy) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(server);
        exporter.setBeans(Map.of(
            "com.example.test:type=Lifecycle,name=Primary",
            new LifecycleProbe(generation)
        ));
        exporter.setRegistrationPolicy(policy);
        return exporter;
    }
}
```

If the exporter is used as a bean inside a Spring context, the container invokes the appropriate initialization and destruction callbacks. If simply calling `new MBeanExporter()` in a plain test without placing it into Spring, invoke the exporter's corresponding lifecycle methods per the current API; the example here illustrates configuration and does not start the exporter on its own.

Verify that the MBean name is a valid Standard MBean, along with the naming strategy and server in use. When passing a map with full ObjectName keys, confirm the name mapping actually applied by the exporter in the final configuration.

## 7. Scenario A: Clean Shutdown Followed by Restart

This is the most basic scenario. Goal:

1. Context A starts, `ObjectName X` exists, attribute `Generation=A`.
2. Context A closes, `ObjectName X` is gone.
3. Context B starts with the same `ObjectName X`, startup succeeds, attribute `Generation=B`.
4. Context B closes, `ObjectName X` is gone.

Pseudo-flow:

```java
ObjectName name = new ObjectName(
    "com.example.test:type=Lifecycle,name=Primary"
);

ConfigurableApplicationContext contextA =
    startContext(server, "A", RegistrationPolicy.FAIL_ON_EXISTING);

assertTrue(server.isRegistered(name));
assertEquals("A", server.getAttribute(name, "Generation"));

contextA.close();
assertFalse(server.isRegistered(name));

ConfigurableApplicationContext contextB =
    startContext(server, "B", RegistrationPolicy.FAIL_ON_EXISTING);

assertEquals("B", server.getAttribute(name, "Generation"));

contextB.close();
assertFalse(server.isRegistered(name));
```

`startContext` is a test fixture to implement using the project's actual Spring configuration. The pseudo-flow cannot run verbatim without the fixture. The key idea is testing **two consecutive lifecycles on the same server**, not a brand-new server per lifecycle (since that would fail to catch lingering registry entries).

A test must close contexts in `finally` or try-with-resources if the context type implements `AutoCloseable`. If B's startup fails, A and the server must still be cleaned up.

## 8. Scenario B: New Startup When Old MBean Is Not Unregistered

Keep context A running and open context B with the same ObjectName:

```text
Context A -> MBean A registered as X
Context B -> attempts to register MBean B as X
```

With `FAIL_ON_EXISTING`, expect context B to fail clearly with a root cause related to `InstanceAlreadyExistsException`.

The test must verify:

- Startup of B fails specifically due to collision, not a missing dependency.
- MBean A still exists and `Generation` is still A.
- Context A continues operating normally.
- Post-test cleanup does not accidentally delete A's registration.

There is no need to launch JConsole to observe the conflict; `getAttribute(name, "Generation")` on the server is direct proof.

## 9. Scenario C: IGNORE_EXISTING

With `IGNORE_EXISTING`, B can start without replacing MBean A. Tests should explicitly demonstrate this consequence:

```text
A exports X -> Generation=A
B starts with IGNORE_EXISTING for X
X remains registered -> Generation=A
B does not own X's existing registration
```

The test should assert:

```java
assertEquals("A", server.getAttribute(name, "Generation"));
```

This may be intentional behavior in an MBean-sharing container. However, if the goal after redeploy is for monitoring tools to interact with the new bean, `IGNORE_EXISTING` can **mask a cleanup bug**. The system starts successfully while operations observe stale data.

When B closes, the registry must not lose MBean A because B does not own A's registration. When A closes, MBean A must be unregistered according to A's lifecycle.

## 10. Scenario D: REPLACE_EXISTING

With `REPLACE_EXISTING`, B replaces A's registration X. What needs testing is not only `Generation=B`, but also **ownership-aware cleanup**.

```text
A registers X -> Generation=A
B replaces X -> Generation=B
A closes -> must not accidentally remove B
B closes -> X cleaned up
```

Do not assume every version/framework has perfect ownership behavior when two exporters replace the same ObjectName. Actual tests must confirm which shutdown order the system supports. If A closes after B replaced the name and accidentally unregisters X, JMX tools lose MBean B even though B is still alive.

Because of that risk, when designing modules running concurrently in the same JVM:

- Prefer a single unique owner per `ObjectName`.
- Add an identifying `instance` or `context` key if two contexts genuinely must coexist.
- Restrict `REPLACE_EXISTING` to controlled takeover workflows.
- Use integration tests to prove the supported A/B shutdown order.

## 11. Scenario E: Web Application Redeploy

In an application server, the JVM and platform `MBeanServer` can outlive a web application. When deploying a new version:

1. The old web app is undeployed or stopped.
2. The old Spring context is closed.
3. The exporter unregisters the MBeans it owns.
4. The old web app's classloader and resources are released.
5. The new version creates its context and registers MBeans.

If steps 2–3 fail to run properly, the new version can hit `InstanceAlreadyExistsException`; even if `IGNORE_EXISTING` allows startup to succeed, the registry may still reference the old classloader.

A useful redeploy test scenario:

- Deploy version A, read `BuildVersion=A` from the MBean.
- Undeploy A, confirm the MBean disappears.
- Deploy version B, read `BuildVersion=B`.
- Undeploy B, confirm the MBean disappears.
- Repeat for multiple cycles, observing MBean counts per domain and retained resources.

Do not check only the application's HTTP health status; a deployment can report healthy while the JMX registry holds onto an old management endpoint.

## 12. Realistic Spring Context Test Fixture

An illustrative test setup creating an exporter per context:

```java
import java.util.Map;
import javax.management.MBeanServer;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

static AnnotationConfigApplicationContext startContext(
        MBeanServer server,
        String generation,
        RegistrationPolicy policy) {

    AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext();

    context.registerBean("lifecycleProbe",
        LifecycleProbe.class,
        () -> new LifecycleProbe(generation));

    context.registerBean("mbeanExporter",
        MBeanExporter.class,
        () -> {
            MBeanExporter exporter = new MBeanExporter();
            exporter.setServer(server);
            exporter.setBeans(Map.of(
                "com.example.test:type=Lifecycle,name=Primary",
                context.getBean("lifecycleProbe")
            ));
            exporter.setRegistrationPolicy(policy);
            return exporter;
        });

    try {
        context.refresh();
        return context;
    } catch (RuntimeException ex) {
        context.close();
        throw ex;
    }
}
```

This fixture illustrates creating an independent context and wiring the exporter; when using `registerBean` with a supplier that looks up another bean during refresh, be mindful of bean creation order—you can substitute a `@Configuration` class with explicit dependencies to avoid startup-order coupling. For production testing, use the same wiring style the real application uses rather than a purely theoretical simulation.

If the project uses Spring Boot JMX auto-configuration, do not accidentally create a second exporter; choose to test either a real Boot context or an isolated Spring Framework context. Tests must reproduce the exact policy used in production.

## 13. Automated Testing with JUnit

A lifecycle test skeleton:

```java
import static org.junit.jupiter.api.Assertions.*;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.jmx.support.RegistrationPolicy;

class MBeanRedeployTest {

    @Test
    void cleanRestartReRegistersFreshInstance() throws Exception {
        MBeanServer server =
            MBeanServerFactory.createMBeanServer("restart-test");

        ObjectName name = new ObjectName(
            "com.example.test:type=Lifecycle,name=Primary"
        );

        try {
            ConfigurableApplicationContext first = null;
            ConfigurableApplicationContext second = null;

            try {
                first = startContext(
                    server, "first", RegistrationPolicy.FAIL_ON_EXISTING
                );
                assertEquals(
                    "first", server.getAttribute(name, "Generation")
                );

                first.close();
                first = null;
                assertFalse(server.isRegistered(name));

                second = startContext(
                    server, "second", RegistrationPolicy.FAIL_ON_EXISTING
                );
                assertEquals(
                    "second", server.getAttribute(name, "Generation")
                );
            } finally {
                if (second != null) second.close();
                if (first != null) first.close();
            }

            assertFalse(server.isRegistered(name));
        } finally {
            MBeanServerFactory.releaseMBeanServer(server);
        }
    }
}
```

When testing policy B starting concurrently with A, use the same server/name but do not call `releaseMBeanServer` while a context is still alive. Set timeouts for startup/shutdown steps if the system has asynchronous connectors or workers so tests do not hang indefinitely.

## 14. Scenarios to Verify in Real Runs

| Scenario | Result to Verify |
| --- | --- |
| Clean startup | New MBean registered under expected ObjectName |
| Clean shutdown | Registrations owned by the context are removed |
| Restart in same JVM | New MBean replaces old generation after cleanup |
| Overlapping startup, FAIL_ON_EXISTING | B fails and A stays intact |
| Overlapping startup, IGNORE_EXISTING | A stays intact; B does not pretend export succeeded |
| Overlapping startup, REPLACE_EXISTING | B replaces; cleanup does not accidentally delete B |
| Context refresh fails midway | Registrations already made are cleaned up appropriately |
| Spring Boot DevTools restart | New context does not retain stale MBean/classloader |
| Redeploy into application server | No leaked MBeans from old deployment |
| Parallel tests | ObjectNames have distinct namespaces, no cross-test interference |

**You do not need to configure all three policies in production.** Test the policies relevant to your deployment decision; pay particular attention to `REPLACE_EXISTING` behavior when multiple owners coexist.

## 15. Observing MBean Count and Identity Over Time

A probe to detect leftover registry entries:

```java
import javax.management.MBeanServer;
import javax.management.ObjectName;

static void printOwnedNames(MBeanServer server) throws Exception {
    ObjectName pattern = new ObjectName("com.example.test:*");

    for (ObjectName name : server.queryNames(pattern, null)) {
        System.out.println(name.getCanonicalName());
    }
}
```

After each restart cycle, record the count and `ObjectName`s in the application's domain. If the count keeps growing, new names may be generated with timestamps/identities without unregistering old ones; if the count does not grow yet generation remains A, `IGNORE_EXISTING` may be keeping the old MBean.

Use stable names for a logical MBean; if multiple instances must run concurrently, add a properly quoted dimension such as `instance=... `. Avoid generating infinitely changing ObjectNames just to dodge collisions, as that hides lifecycle bugs and complicates dashboards.

## 16. Connectors and Listeners Must Follow the Lifecycle Too

MBean registrations are not the only things that can leak. If the application creates a `JMXConnectorServer`, the connector has its own socket/registry/resources and must call `stop()` on shutdown. For notification listeners attached to `MBeanServer`, listeners owned by the module must be removed.

During redeploys, leaving listeners or connectors behind can retain references to old classloaders, causing memory leaks and callbacks into expired objects.

A sensible shutdown order:

1. Stop accepting new management requests if possible.
2. Stop module-created connectors or entrypoints.
3. Remove module-owned listeners/notification handlers.
4. Close the exporter/context to unregister MBeans.
5. Release executors, schedulers, and subsystem resources.

The exact order may vary by application; the goal is leaving no invocation path into shut-down objects.

## 17. Do Not Fix Errors by Deleting MBeans Globally

When encountering `InstanceAlreadyExistsException`, do not call:

```java
for (ObjectName name : server.queryNames(null, null)) {
    server.unregisterMBean(name); // DANGEROUS
}
```

This can delete MBeans belonging to the JVM, libraries, and other applications. Unregister only the exact `ObjectName`s owned by your context/module, with a clear lifecycle.

Even unregistering all names in the `com.example:* ` domain can be too broad if multiple modules share that domain. Use specific namespaces and ownership.

## 18. Key Takeaways

**Restart/redeploy testing must prove the old MBean is gone and the new MBean genuinely represents the new instance.** `FAIL_ON_EXISTING` helps catch duplicate names, `IGNORE_EXISTING` can preserve an old endpoint without throwing an error, and `REPLACE_EXISTING` can introduce ownership risks when contexts overlap. Reuse the same `MBeanServer` across multiple lifecycles, read the `Generation` attribute to distinguish instances, verify unregistration at shutdown, and clean up strictly according to ownership.
