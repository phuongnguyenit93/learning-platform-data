# Testing Exporter Start and Stop in Spring Framework JMX

## 1. Goal

In Spring Framework JMX, `MBeanExporter` is responsible for registering Spring beans as MBeans in an `MBeanServer`. When the Spring `ApplicationContext` starts up, the exporter typically performs registration; when the context closes, the exporter must clean up the registrations under its management.

Testing **exporter start and stop** requires verifying the **registration/unregistration lifecycle**, not merely whether a class has annotations or whether a getter returns expected data.

Questions to answer:

1. Before initializing the exporter, is the ObjectName unregistered?
2. After initializing the exporter, does the MBean appear under the right `ObjectName`?
3. Are the MBean's attributes and operations accessible?
4. When closing the `ApplicationContext`, are MBeans managed by the exporter unregistered?
5. If startup fails or ObjectNames collide, how does the exporter report and handle it?
6. Does it accidentally unregister MBeans belonging to another owner?
7. If the context is recreated, can it re-register the same name without leaks?
8. Are listeners, connections, and dependent resources released appropriately?

This lesson distinguishes **exporter start/stop**, **application context start/stop**, and **business resource start/stop**. These lifecycles are related, but not always identical.

## 2. MBeanExporter Lifecycle Flow

A typical lifecycle:

~~~text
ApplicationContext not yet created
        |
        v
Spring creates business beans
        |
        v
Spring creates MBeanExporter
        |
        v
Exporter registers MBeans into MBeanServer
        |
        v
MBeanServer.isRegistered(ObjectName) = true
        |
        | Clients read attributes / invoke operations
        |
        v
ApplicationContext.close()
        |
        v
Exporter unregisters MBeans within its managed scope
        |
        v
MBeanServer.isRegistered(ObjectName) = false
~~~

**Do not assume `MBeanExporter` is a `SmartLifecycle` with `start()` and `stop()` methods in every version.** In common usage, the exporter is a Spring bean participating in bean initialization/destruction lifecycles; `afterPropertiesSet()` and `destroy()` or closing the context are the primary test points.

Saying "testing exporter start/stop" in this lesson means testing that the exporter **is initialized/registers** and **is destroyed/deregisters**, not necessarily the `Lifecycle.start()`/`stop()` API.

## 3. Required Components in the Test

| Component | Role |
| --- | --- |
| Isolated `MBeanServer` | Dedicated test registry, avoiding JVM platform MBeans |
| `MBeanExporter` | Component whose lifecycle is under test |
| Managed bean | MBean to be registered by the exporter |
| `ObjectName` | Identity verified before/after |
| `ApplicationContext` | Manages creation/destruction of the exporter |
| Assertions | Verify registry state and MBean contract |
| Cleanup | Close context, release MBeanServer |

A safe approach is creating a private MBeanServer via `MBeanServerFactory.newMBeanServer()`. This method creates a new MBeanServer without registering it in the factory's lookup list, reducing the risk of affecting other tests. In these examples, we choose this approach to avoid interfering with the platform MBeanServer used by JConsole or other libraries.

If application code requires `MBeanServerFactory.createMBeanServer()`, manage release per the factory's contract. Never release the platform server.

## 4. Sample MBean Used in Testing

To focus on lifecycle, use a Standard MBean following Java JMX conventions:

~~~java
package com.example.testjmx;

public interface CounterAdminMBean {
    long getCount();
    void reset();
}
~~~

~~~java
package com.example.testjmx;

import java.util.concurrent.atomic.AtomicLong;

public class CounterAdmin implements CounterAdminMBean {

    private final AtomicLong count = new AtomicLong(5);

    @Override
    public long getCount() {
        return count.get();
    }

    @Override
    public void reset() {
        count.set(0);
    }
}
~~~

`CounterAdmin` needs no Spring annotations; it is a Standard MBean when registered with the `CounterAdminMBean` interface. Interface naming and structure let JMX discover attributes and operations.

This is a simple test resource that accesses no network, database, or real resources. Therefore, tests can run repeatedly without external side effects outside the MBeanServer.

## 5. Spring Configuration with a Dedicated MBeanServer

You can create a Spring configuration managing the exporter and server:

~~~java
package com.example.testjmx;

import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

import java.util.Map;

@Configuration
public class JmxTestConfiguration {

    public static final String OBJECT_NAME =
        "com.example.test:type=Counter,name=primary";

    @Bean
    MBeanServer testMBeanServer() {
        return MBeanServerFactory.newMBeanServer();
    }

    @Bean
    CounterAdmin counterAdmin() {
        return new CounterAdmin();
    }

    @Bean
    MBeanExporter counterExporter(
            MBeanServer testMBeanServer,
            CounterAdmin counterAdmin
    ) {
        MBeanExporter exporter = new MBeanExporter();

        exporter.setServer(testMBeanServer);
        exporter.setBeans(Map.of(
            OBJECT_NAME,
            counterAdmin
        ));

        return exporter;
    }
}
~~~

**Note:** `@Configuration` only describes bean wiring; the exporter still has to actually be instantiated by Spring in the context. When the context closes, Spring invokes destruction lifecycle callbacks on the relevant beans, including the exporter.

In some project setups, another automatic exporter may exist. For this unit/integration test, use an isolated context and import only `JmxTestConfiguration` to avoid duplicate registrations.

## 6. Integration Test: MBean Appears When Context Starts

JUnit 5 can use `AnnotationConfigApplicationContext` to explicitly drive context lifecycle.

~~~java
package com.example.testjmx;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

public class MBeanExporterLifecycleTest {

    @Test
    void registersAndUnregistersMBean() throws Exception {
        AnnotationConfigApplicationContext context =
            new AnnotationConfigApplicationContext();

        context.register(JmxTestConfiguration.class);

        ObjectName name = new ObjectName(
            JmxTestConfiguration.OBJECT_NAME
        );

        // Not yet refreshed; exporter has not initialized or registered.
        context.refresh();

        MBeanServer server =
            context.getBean(MBeanServer.class);

        assertTrue(server.isRegistered(name));

        Object value = server.getAttribute(name, "Count");
        assertEquals(5L, value);

        context.close();

        assertFalse(server.isRegistered(name));
    }
}
~~~

This test illustrates the refresh → registered → close → unregistered flow. However, it does not observe `isRegistered=false` **before refresh**, because the MBeanServer is created by the context during refresh.

To strictly verify the precondition as well, create the MBeanServer outside the context and inject or register it before calling refresh; that pattern is shown in the next section.

### Note on Asserting Java Values

`MBeanServer.getAttribute` returns `Object`. For a primitive `long` attribute, the result is boxed as `Long`; `assertEquals(5L, value)` matches this behavior.

## 7. Complete Integration Test: Before, During, After

A more self-contained approach is creating the MBeanServer first, then passing it into the Spring context:

~~~java
package com.example.testjmx;

import java.util.Map;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.jmx.export.MBeanExporter;

import static org.junit.jupiter.api.Assertions.*;

class ExporterRegistrationTest {

    @Test
    void exporterRegistrationFollowsContextLifecycle()
            throws Exception {

        MBeanServer server = MBeanServerFactory.newMBeanServer();

        ObjectName name = new ObjectName(
            "com.example.test:type=Counter,name=primary"
        );

        assertFalse(server.isRegistered(name));

        AnnotationConfigApplicationContext context =
            new AnnotationConfigApplicationContext();

        // Register the existing MBeanServer into the context.
        context.getBeanFactory().registerSingleton(
            "testMBeanServer", server
        );

        context.registerBean(
            "counterAdmin", CounterAdmin.class
        );

        context.registerBean(
            "counterExporter",
            MBeanExporter.class,
            () -> {
                MBeanExporter exporter = new MBeanExporter();
                exporter.setServer(server);
                exporter.setBeans(Map.of(
                    name.toString(),
                    context.getBean("counterAdmin")
                ));
                return exporter;
            }
        );

        try {
            context.refresh();

            assertTrue(server.isRegistered(name));
            assertEquals(5L, server.getAttribute(name, "Count"));

        } finally {
            context.close();
        }

        assertFalse(server.isRegistered(name));
    }
}
~~~

Above, `context.registerBean` is a modern Spring Framework API; in older Spring versions, substitute an equivalent configuration class or bean definition registration.

The test targets three checkpoints:

~~~text
Before: MBean not yet registered
During: MBean registered and queryable
After:  MBean unregistered
~~~

Because the test uses a dedicated MBeanServer, results cannot be affected by an MBean of the same name in another application's platform MBeanServer.

## 8. Checking Operations Beyond Registration Status

An MBean appearing in the registry does not guarantee its metadata is right. You can also test operations:

~~~java
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;

MBeanInfo info = server.getMBeanInfo(name);

boolean hasReset = false;

for (MBeanOperationInfo operation : info.getOperations()) {
    if ("reset".equals(operation.getName())) {
        hasReset = true;
        break;
    }
}

assertTrue(hasReset, "Expected reset operation");

server.invoke(
    name,
    "reset",
    new Object[0],
    new String[0]
);

assertEquals(0L, server.getAttribute(name, "Count"));
~~~

Checking operations is useful because an exporter can register an MBean while metadata/assembler mapping does not match the contract. In lifecycle tests, use harmless operations like resetting a counter to avoid affecting real resources.

## 9. When Using an Annotation Exporter

Spring JMX lets you declare management metadata using:

- `@ManagedResource`
- `@ManagedAttribute`
- `@ManagedOperation`
- `@ManagedNotification`

Example:

~~~java
package com.example.testjmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.test:type=Worker,name=primary"
)
public class WorkerManagement {
    private volatile boolean paused;

    @ManagedAttribute
    public boolean isPaused() {
        return paused;
    }

    @ManagedOperation
    public void pause() {
        paused = true;
    }
}
~~~

For Spring to detect and export this bean, the context must include an annotation-capable exporter such as `AnnotationMBeanExporter` or equivalent configuration.

A dedicated test for annotation export should verify:

1. The bean is created in the right context.
2. The exporter reads `@ManagedResource`.
3. The MBean is registered under the ObjectName from the annotation or naming strategy.
4. Attribute `Paused` and operation `pause()` appear in `MBeanInfo`.
5. When the context closes, the MBean is unregistered.

Never infer that a class annotated with `@ManagedResource` becomes an MBean immediately; the annotation does not self-register a class not managed by Spring.

## 10. Testing Shutdown When Exceptions Occur

One risk in writing tests is that a mid-test assertion failure leaves the context unclosed. This can leave the MBean registered and break the next test.

Always use `try/finally`:

~~~java
AnnotationConfigApplicationContext context =
    new AnnotationConfigApplicationContext();

try {
    context.register(JmxTestConfiguration.class);
    context.refresh();

    // Assertions here.
} finally {
    context.close();
}
~~~

If a test holds multiple resources, manage the full lifecycle:

~~~text
Create MBeanServer
Create ApplicationContext
Refresh/export
Assert
Close ApplicationContext
Verify unregister
Release test-only resources
~~~

If using `MBeanServerFactory.createMBeanServer()`, you may need `MBeanServerFactory.releaseMBeanServer(server)` after the test per the factory's contract. With `newMBeanServer()`, there is no equivalent release requirement in the factory registry.

## 11. Testing Closing and Reopening the Context

A common bug is that the first run succeeds while the second run fails because the ObjectName lingers. Run a two-round test:

~~~java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

MBeanServer server = MBeanServerFactory.newMBeanServer();

ObjectName name = new ObjectName(
    "com.example.test:type=Counter,name=primary"
);

for (int attempt = 0; attempt < 2; attempt++) {
    AnnotationConfigApplicationContext context =
        createContextWithExporter(server);

    try {
        assertTrue(server.isRegistered(name));
    } finally {
        context.close();
    }

    assertFalse(
        server.isRegistered(name),
        "MBean leaked after context close"
    );
}
~~~

`createContextWithExporter(server)` is an illustrative helper to define in your fixture.

Expected flow:

~~~text
Attempt 1: register -> unregister
Attempt 2: register -> unregister
~~~

If the second attempt throws `InstanceAlreadyExistsException`, the exporter or another component may have retained the old registration.

Do not paper over test failures by enabling `REPLACE_EXISTING` by default; doing so hides leaks and ownership bugs.

## 12. Testing Registration Policies

Spring provides `RegistrationPolicy` for when an ObjectName is already taken.

### FAIL_ON_EXISTING

This is the appropriate behavior when name collisions must be detected:

~~~text
Existing MBean at ObjectName X
New exporter tries to register X
    -> fail with registration error
~~~

Tests should confirm the exporter raises an error and **the existing MBean is not replaced**.

### IGNORE_EXISTING

The exporter skips the new registration when the name already exists:

~~~text
Existing MBean X
New exporter wants X
    -> existing MBean retained
~~~

Tests must verify the new bean is not registered in its place, the old MBean still works, and context shutdown does not accidentally unregister a resource owned by someone else.

### REPLACE_EXISTING

The exporter replaces the existing MBean under the same ObjectName. Tests need to check:

- The new MBean is actually registered.
- Metadata and state reflect the new implementation.
- Whether the old MBean has lingering side effects or lifecycle tasks.
- When the context closes, the name is unregistered per exporter ownership.
- Clients reading/invoking during replacement may observe disruption.

**Replacing a live MBean is not guaranteed to be a zero-disruption atomic operation.** In production systems, test lifecycle and concurrency separately.

## 13. Testing Ownership: Do Not Unregister Another Party's MBean

Suppose a test registers MBean A manually, then creates exporter B mapped to ObjectName A.

Under `IGNORE_EXISTING`, after closing exporter B, MBean A should remain. This is a key invariant:

~~~text
MBean owned by A
    |
Exporter B sees same ObjectName
    |
B skips registration
    |
B stops
    |
MBean A should remain
~~~

With `REPLACE_EXISTING`, ownership is trickier because B unregistered A and then registered B. You must clearly decide who owns the name after replacement.

In simple tests, use `FAIL_ON_EXISTING` to catch conflicts early. Do not rely on `REPLACE_EXISTING` as a catch-all automatic fix for ObjectName collisions.

## 14. Testing Listener Registration and Cleanup

If the exporter configures `NotificationListenerBean`, lifecycle testing covers not only MBean registration but also listener bindings.

Example MBean supporting notifications:

~~~java
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;
import java.util.concurrent.atomic.AtomicLong;

public class EventMonitor extends NotificationBroadcasterSupport
        implements EventMonitorMBean {

    private final AtomicLong sequence = new AtomicLong();

    @Override
    public void fireEvent() {
        sendNotification(new Notification(
            "com.example.test.event",
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Test event"
        ));
    }
}
~~~

`EventMonitorMBean` is an interface that must be defined with `void fireEvent()`.

Test steps:

1. Context refreshes and the exporter registers the MBean.
2. The listener receives an event when the MBean emits one.
3. Context closes.
4. ObjectName is no longer registered.
5. The listener stops receiving events from the old exporter in new tests.
6. If any listener was registered outside the exporter, the test must clean it up to avoid reference leaks.

Notification lifecycles can vary by broadcaster and configuration. Do not infer from `isRegistered(false)` alone that every listener was released.

## 15. Testing Startup Failure: Invalid ObjectName

Example syntactically invalid ObjectName:

~~~text
com.example.test:type=Cache,name=foo,bar
~~~

This can result in `MalformedObjectNameException` or a Spring-wrapped exception at configuration/registration time.

A test can intentionally supply an invalid ObjectName to confirm:

- `ApplicationContext` reports an intelligible error.
- No partial MBean is registered under a broken name.
- Previously registered MBeans are properly cleaned up when startup fails.
- Test state does not pollute subsequent cases.

If an exporter registers multiple MBeans and one fails midway, do not assume registration is an atomic transaction. Verify the rollback and cleanup behavior of the Spring version in use.

## 16. Testing Failure Modes When Closing Context

An MBean may wrap underlying resources such as an executor, cache, or connection pool. Unregistering the MBean does not automatically guarantee the underlying resource stopped.

Distinguish:

~~~text
MBeanExporter.destroy()
    -> unregister JMX MBean

Business bean destroy()/close()
    -> stop worker / close resource / release connections
~~~

These steps can occur during the same context shutdown, yet belong to different responsibilities. A thorough integration test checks both:

- The MBean is no longer in the registry.
- Business resources were released per their own lifecycle.

Example checking a worker service:

~~~java
assertFalse(server.isRegistered(name));
assertTrue(workerService.isStopped());
~~~

The `workerService` type here is illustrative. Never assume `MBeanExporter` automatically shuts down an executor when unregistering an MBean.

## 17. Parallel Tests and ObjectName Collisions

When tests run in parallel, two tests may use the same platform MBeanServer and the same ObjectName, causing flaky failures.

Ways to reduce risk:

- Create an isolated MBeanServer per test.
- Use distinct ObjectNames when needed.
- Avoid mutable static shared exporters across tests.
- Ensure the context closes even when assertions fail.
- Do not register test MBeans on the platform server unless required.
- Do not use random suffixes to hide naming bugs if the test verifies naming stability.

### When the Platform MBeanServer Is Required

If you must test integration with platform MBeans/JVM management, you can use the platform server, but ensure ObjectNames do not collide and clean up carefully. Isolate these tests from unit tests running in parallel.

## 18. Testing MBeanInfo Across the Lifecycle

An MBean being present is not enough; metadata can be wrong if the assembler or proxy differs from expectations.

~~~java
import javax.management.MBeanInfo;
import javax.management.MBeanAttributeInfo;

MBeanInfo info = server.getMBeanInfo(name);

boolean hasCount = false;

for (MBeanAttributeInfo attr : info.getAttributes()) {
    if ("Count".equals(attr.getName())) {
        hasCount = attr.isReadable();
    }
}

assertTrue(hasCount);
~~~

For annotation exporters, verify that methods annotated with `@ManagedAttribute` and `@ManagedOperation` are present. If a class is wrapped in a Spring AOP proxy, you may need to check how the exporter discovers target metadata and proxy methods.

Once the context closes, any `getMBeanInfo` call against the unregistered ObjectName should fail per contract, unless another owner re-registered the same name.

## 19. Testing Unregistration via MBeanServerDelegate

JMX provides the `JMImplementation:type=MBeanServerDelegate` MBean, which emits registration/unregistration events.

You can monitor:

~~~text
JMX.mbean.registered
JMX.mbean.unregistered
~~~

Actual type names are defined by constants `MBeanServerNotification.REGISTRATION_NOTIFICATION` and `UNREGISTRATION_NOTIFICATION`.

Example:

~~~java
import javax.management.MBeanServerNotification;
import javax.management.NotificationListener;
import javax.management.ObjectName;
import java.util.concurrent.CopyOnWriteArrayList;

ObjectName delegate = new ObjectName(
    "JMImplementation:type=MBeanServerDelegate"
);

CopyOnWriteArrayList<MBeanServerNotification> events =
    new CopyOnWriteArrayList<>();

NotificationListener listener = (notification, handback) -> {
    if (notification instanceof MBeanServerNotification event) {
        events.add(event);
    }
};

server.addNotificationListener(
    delegate, listener, null, null
);
~~~

After exporter start/stop, filter events by `event.getMBeanName().equals(name)`. At the end of the test, remove the listener from the delegate.

**Note:** Event delivery depends on the notification mechanism; for asynchronous checks, use bounded waits. Calling `server.isRegistered(name)` remains the simplest assertion to determine registry state at each checkpoint.

## 20. Common Errors When Testing the Exporter

| Symptom | Cause | Resolution |
| --- | --- | --- |
| MBean missing after refresh | Exporter not created or wrong server | Check Spring config and MBeanServer |
| MBean exists but lacks operations | Wrong assembler/annotation metadata | Inspect `MBeanInfo` |
| Context closed but MBean remains | Exporter does not own registration or broken lifecycle | Check owner and `destroy` |
| Second test hits `InstanceAlreadyExistsException` | Previous test leaked or same ObjectName | Isolate server and close context |
| Test passes alone but fails in parallel | Shared platform MBeanServer | Dedicated `newMBeanServer` per test |
| Annotated but not exported | Bean not in context or missing annotation exporter | Check component registration and exporter |
| `REPLACE_EXISTING` makes broken test pass | Masks collisions/leaks | Use fail policy to expose bugs |
| Startup failure leaves MBean behind | Partial registration or missing cleanup | Test failure paths and `finally` |
| Exporter stops but resource still runs | Unregister is not business stop | Test service lifecycle separately |
| Listener receives duplicate notifications | Listener registered multiple times | Clean up / re-subscribe properly |
| Wrong MBeanServer | Test reads platform server instead of configured server | Inject the same server |
| Intermittent assertion failures | Startup/shutdown race or async test | Use latches / state observation |

## 21. Practice Exercises

**Goal:** Build tests verifying `MBeanExporter` lifecycle for both a Standard MBean and an annotation MBean.

### Part A — Standard MBean

1. Create `CounterAdminMBean` and `CounterAdmin`.
2. Create `MBeanServerFactory.newMBeanServer()`.
3. Create `AnnotationConfigApplicationContext`.
4. Register `MBeanExporter` mapping `CounterAdmin` to an ObjectName.
5. Before refresh, verify `isRegistered=false`.
6. After refresh, verify `isRegistered=true`.
7. Read the `Count` attribute.
8. Invoke `reset()` and verify `Count=0`.
9. Close the context in `finally`.
10. Verify `isRegistered=false`.

### Part B — Annotation MBean

1. Create `WorkerManagement` with `@ManagedResource`.
2. Enable `AnnotationMBeanExporter` in an isolated context.
3. Verify the ObjectName is registered.
4. Read `Paused`.
5. Invoke `pause()`.
6. Check `Paused=true`.
7. Close the context.
8. Verify the ObjectName is gone.

### Part C — Failure Paths

1. Pre-register an MBean under the same ObjectName.
2. Run the exporter with `FAIL_ON_EXISTING`.
3. Confirm startup fails and the existing MBean remains intact.
4. Run the `IGNORE_EXISTING` case with a clear owner.
5. Test that closing the context does not mistakenly unregister another owner's MBean.
6. Test restarting the context twice.
7. Run tests in parallel with dedicated MBeanServers to prevent collisions.

## 22. Self-Check Questions

**1. When does MBeanExporter register MBeans?**

Typically during Spring bean/exporter initialization lifecycle after dependencies are ready, under ApplicationContext control.

**2. Can you test exporter stop via `Lifecycle.stop()`?**

Do not assume so. With `MBeanExporter`, you normally test `destroy()` or context close and check the registry after shutdown.

**3. Why is a dedicated MBeanServer needed?**

To keep tests independent, avoid collisions with platform MBeans, and prevent polluting other tests.

**4. What does `isRegistered(false)` after context close prove?**

It proves the ObjectName is no longer registered in the inspected server. It does not by itself prove all resources or listeners were completely cleaned up.

**5. Why shouldn't you enable `REPLACE_EXISTING` just to keep tests passing?**

Because that policy can hide ObjectName leaks or ownership bugs.

**6. Should tests verify attributes and operations?**

Yes. Presence in the registry does not guarantee its metadata matches the expected contract.

**7. What if the exporter fails midway while registering multiple MBeans?**

Do not assume atomic rollback. Test failure paths, cleanup, and actual registry state.

**8. How is testing context restart useful?**

It catches stale registrations or listener leaks that cause the second run to fail or receive duplicate events.

## 23. Summary

Testing exporter start/stop in Spring Framework JMX means testing the **MBean registration lifecycle**:

~~~text
Before refresh: not registered
After refresh:  registered
After close:    not registered
~~~

For reliable results:

- Use a dedicated MBeanServer.
- Verify ObjectName before/after and metadata while running.
- Close `ApplicationContext` in `finally`.
- Test multiple start/stop cycles and conflict scenarios.
- Separate MBean unregistration from stopping business resources.
- Verify notification listener cleanup when the exporter manages listeners.
- Track ownership of each MBean to avoid accidental unregistration.

**`MBeanExporter` works properly when managed MBeans are registered during the context lifecycle and cleaned up on time, leaving behind no unowned registrations or listeners.**

### References

- Spring Framework Reference — JMX Exporting: https://docs.spring.io/spring-framework/reference/integration/jmx/exporting.html
- Spring Framework API — MBeanExporter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework API — AnnotationMBeanExporter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/AnnotationMBeanExporter.html
- Java SE API — MBeanServer: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE API — MBeanServerFactory: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerFactory.html
