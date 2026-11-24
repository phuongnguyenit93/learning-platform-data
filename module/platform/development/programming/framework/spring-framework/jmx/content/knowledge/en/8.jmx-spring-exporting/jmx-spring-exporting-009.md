# Exporter Listeners Tracking MBean Registration and Unregistration in Spring

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain how **MBeanExporter** in Spring manages the MBean registration lifecycle with an **MBeanServer**.
- Understand the role of **MBeanExporterListener** and its two callbacks `mbeanRegistered(ObjectName)` and `mbeanUnregistered(ObjectName)`.
- Distinguish exporter callbacks from **JMX notifications** emitted by `MBeanServerDelegate` and from Spring `ApplicationContext` events.
- Configure one or more exporter listeners, receive registered/unregistered `ObjectName`s, and record logs or metrics with reasonable overhead.
- Recognize the limitations of callbacks in cases of failed registration, objects registered by other components, JVM crashes, and duplicate-name registration policies.
- Design MBean lifecycle observability without altering business behavior, avoiding heavy side effects, and preventing administrative data leaks.
- Verify the registration/unregistration sequence by starting and closing a Spring context.

## 2. Context: How Does the Exporter Manage MBeans?

In Java Management Extensions (JMX), an MBean must be registered with an `MBeanServer` under a specific `ObjectName` so management tools like JConsole can discover and access it.

In the Spring Framework, **`org.springframework.jmx.export.MBeanExporter`** adapts configured objects into MBeans or JMX adapters, registers them into an MBeanServer, and manages cleanup according to the exporter's lifecycle.

\`\`\`text
Spring ApplicationContext
          |
          | initializes beans and MBeanExporter
          v
MBeanExporter
          |
          +----> prepares ObjectName / JMX adapter
          |
          +----> MBeanServer.registerMBean(...)
          |                  |
          |                  v
          |           Registered MBean
          |                  |
          +----> MBeanExporterListener.mbeanRegistered(name)
          |
      Spring context active
          |
          v
      Context shutdown
          |
          +----> MBeanServer.unregisterMBean(...)
          |
          +----> MBeanExporterListener.mbeanUnregistered(name)
\`\`\`

An exporter listener is a **lifecycle hook**: it receives notifications after the exporter registers or unregisters MBeans within the scope it manages. Listeners are suitable for logging operational events, synchronizing local state, counting MBeans exported by the exporter, or assisting diagnostics.

**Important limitation:** an exporter listener does not automatically monitor every MBean across the entire MBeanServer. MBeans registered directly by other libraries or manual code may not trigger callbacks on the observed exporter.

## 3. Three Components and Responsibilities

| Component | Responsibility |
| --- | --- |
| `MBeanServer` | The actual JMX registry: holds `ObjectName`s, provides `registerMBean`, `unregisterMBean`, `isRegistered`, `queryNames`, and management operations. |
| `MBeanExporter` | Bridge between Spring and JMX: selects beans, creates/reads management metadata, registers MBeans, handles duplicate-name policies, and cleans up on shutdown. |
| `MBeanExporterListener` | Receives callbacks when the exporter successfully registers or unregisters MBeans, along with the corresponding `ObjectName`. |

A **Spring bean** in `ApplicationContext` is not an MBean by default. Conversely, an MBean registered directly via the JMX API does not automatically become a Spring bean.

Example JMX names:

\`\`\`text
com.example.orders:type=Cache,name=ProductReadCache
com.example.orders:type=Worker,name=ImportWorker
com.example.orders:type=Queue,name=RetryQueue
\`\`\`

A callback receives `ObjectName` to identify which MBean just changed lifecycle state; the listener does not need to and should not decode sensitive data from business beans.

## 4. The MBeanExporterListener Interface

In the Spring Framework, the listener interface resides in the package:

\`\`\`java
import org.springframework.jmx.export.MBeanExporterListener;
\`\`\`

The interface consists of two callbacks:

\`\`\`java
void mbeanRegistered(javax.management.ObjectName objectName);

void mbeanUnregistered(javax.management.ObjectName objectName);
\`\`\`

Meaning:

- **`mbeanRegistered(name)`**: the exporter has successfully registered the MBean with that name and notifies the listener.
- **`mbeanUnregistered(name)`**: the exporter has unregistered a managed MBean and notifies the listener.
- The **`ObjectName`** parameter is the JMX identifier, e.g., `com.example.orders:type=Worker,name=ImportWorker`.

These two callbacks do not receive the Java class, Spring bean name, event payload, or unregistration reason. If you want to map `ObjectName` back to a business component, establish a namespace convention or an application-managed mapping table.

The listener can be used to log, update counters, or trigger lightweight checks; it is not the right place for long-blocking work.

## 5. Simple Example: Logging on Registration and Unregistration

Create a concrete implementation:

\`\`\`java
package example.springjmx;

import javax.management.ObjectName;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jmx.export.MBeanExporterListener;

public final class LoggingMBeanExporterListener
        implements MBeanExporterListener {

    private static final Logger log =
        LoggerFactory.getLogger(LoggingMBeanExporterListener.class);

    @Override
    public void mbeanRegistered(ObjectName objectName) {
        log.info("JMX MBean registered: {}", objectName);
    }

    @Override
    public void mbeanUnregistered(ObjectName objectName) {
        log.info("JMX MBean unregistered: {}", objectName);
    }
}
\`\`\`

This is a stateless, easy-to-apply implementation. Logging MBean names helps trace the exporter's registrations and cleanups across the Spring context lifecycle.

Illustrative output example:

\`\`\`text
INFO  JMX MBean registered: com.example.orders:type=Worker,name=ImportWorker
INFO  JMX MBean unregistered: com.example.orders:type=Worker,name=ImportWorker
\`\`\`

**Privacy note:** `ObjectName` can accidentally contain sensitive data if naming is poorly designed. Use stable domain/key values, do not put tokens, personal emails, or secrets into MBean names, and limit what is written to logs.

## 6. Complete Example with Spring Java Configuration

To see the flow clearly, this example declares a **Standard MBean**, an **MBeanExporter**, and an explicitly attached listener.

### 6.1. Defining the Standard MBean

\`\`\`java
package example.springjmx;

public interface WorkerMonitorMBean {
    int getActiveWorkers();
    boolean isRunning();
}
\`\`\`

\`\`\`java
package example.springjmx;

public final class WorkerMonitor implements WorkerMonitorMBean {

    private volatile int activeWorkers = 3;
    private volatile boolean running = true;

    @Override
    public int getActiveWorkers() {
        return activeWorkers;
    }

    @Override
    public boolean isRunning() {
        return running;
    }
}
\`\`\`

The Spring exporter will expose `WorkerMonitor` to JMX according to configuration, without needing to call `MBeanServer.registerMBean` inside this class.

### 6.2. Configuring the Exporter and Listener

\`\`\`java
package example.springjmx;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxExportConfiguration {

    @Bean
    public WorkerMonitor workerMonitor() {
        return new WorkerMonitor();
    }

    @Bean
    public LoggingMBeanExporterListener loggingMBeanExporterListener() {
        return new LoggingMBeanExporterListener();
    }

    @Bean
    public MBeanExporter workerExporter(
            WorkerMonitor workerMonitor,
            LoggingMBeanExporterListener listener) {

        MBeanExporter exporter = new MBeanExporter();

        exporter.setBeans(Map.of(
            "com.example.orders:type=Worker,name=ImportWorker",
            workerMonitor
        ));

        exporter.setListeners(listener);

        return exporter;
    }
}
\`\`\`

Here:

1. `WorkerMonitor` is the managed object.
2. `MBeanExporter` uses `setBeans` to explicitly select the bean and `ObjectName` to register.
3. `setListeners(listener)` attaches the listener that will receive callbacks emitted by the exporter.
4. Once the exporter finishes registering, `mbeanRegistered` is called.
5. When the exporter unregisters during context close, `mbeanUnregistered` is called.

Spring Boot auto-configurations may create another exporter. If the application already has Spring Boot JMX auto-configuration, avoid exporting the same MBean twice; designate a single owner for each `ObjectName`.

### 6.3. Running the Context and Verifying Registration

\`\`\`java
package example.springjmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public final class ExporterLifecycleDemo {

    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example.orders:type=Worker,name=ImportWorker"
        );

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                    JmxExportConfiguration.class)) {

            System.out.println(
                "Registered: " + server.isRegistered(name)
            );

            System.out.println(
                "ActiveWorkers: " +
                server.getAttribute(name, "ActiveWorkers")
            );
        }

        System.out.println(
            "Registered after close: " + server.isRegistered(name)
        );
    }
}
\`\`\`

With the exporter using the platform MBeanServer and an environment free of name conflicts, the expected output is:

\`\`\`text
INFO  JMX MBean registered: com.example.orders:type=Worker,name=ImportWorker
Registered: true
ActiveWorkers: 3
INFO  JMX MBean unregistered: com.example.orders:type=Worker,name=ImportWorker
Registered after close: false
\`\`\`

This is a lifecycle example runnable in a Spring Framework application with JDK/JMX and appropriate Spring Context dependencies. When running in Spring Boot or another container, a default exporter or custom `MBeanServer` may exist; adjust the configuration to inspect the right registry.

## 7. An MBeanExporter Can Have Multiple Listeners

An exporter can invoke multiple configured listeners:

\`\`\`java
exporter.setListeners(
    new LoggingMBeanExporterListener(),
    new MetricsMBeanExporterListener()
);
\`\`\`

One listener writes logs; another counts events. However, both listeners execute on the registration/unregistration thread coordinated by the exporter; do not let any listener block for long or throw unhandled exceptions.

Example of a listener counting callback invocations:

\`\`\`java
package example.springjmx;

import java.util.concurrent.atomic.LongAdder;
import javax.management.ObjectName;
import org.springframework.jmx.export.MBeanExporterListener;

public final class MetricsMBeanExporterListener
        implements MBeanExporterListener {

    private final LongAdder registrations = new LongAdder();
    private final LongAdder unregistrations = new LongAdder();

    @Override
    public void mbeanRegistered(ObjectName objectName) {
        registrations.increment();
    }

    @Override
    public void mbeanUnregistered(ObjectName objectName) {
        unregistrations.increment();
    }

    public long getRegistrations() {
        return registrations.sum();
    }

    public long getUnregistrations() {
        return unregistrations.sum();
    }
}
\`\`\`

These two counters represent **the number of callbacks received**, not necessarily the number of MBeans currently in the MBeanServer because:

- MBeans registered by other components do not fire callbacks to this listener.
- There may be multiple registration/unregistration cycles for the same name.
- JDK system MBeans are typically not managed by the Spring exporter.
- Abrupt shutdown may not execute normal cleanup.
- Certain mid-step failures can cause callback counts to diverge from registry state if a listener or the system encounters an error.

If you need the current MBean count in the registry, use `MBeanServer.queryNames` or `getMBeanCount` within a specific scope instead of treating `registrations - unregistrations` as the sole source of truth.

## 8. When Are Callbacks Invoked?

### 8.1. Registration

In the normal processing path:

\`\`\`text
Spring initializes MBeanExporter
   -> identifies beans to export
   -> resolves/creates ObjectName
   -> calls MBeanServer.registerMBean(...)
   -> handles successful result
   -> notifies listener: mbeanRegistered(name)
\`\`\`

The registration event is notified **after** the exporter registers successfully. If registration fails before this step, you cannot assume the listener will receive `mbeanRegistered`. The notification mechanism does not replace exception logging or MBean export error handling.

### 8.2. Unregistration

Normal lifecycle when the Spring context closes:

\`\`\`text
ApplicationContext.close()
   -> MBeanExporter destroy lifecycle
   -> MBeanServer.unregisterMBean(name)
   -> notifies listener: mbeanUnregistered(name)
\`\`\`

Exact timing may depend on the exporter's lifecycle callbacks and Spring Framework version. Do not rely on callback ordering across different beans to drive business workflows.

### 8.3. No Guarantee on Abrupt JVM Death

If the JVM is hard-killed, the host loses power, the container is terminated bypassing shutdown hooks, or the process exits abnormally, cleanup code may not run. In those cases, receiving `mbeanUnregistered` is not guaranteed.

Therefore, do not use the unregistration callback as the sole reliable signal to clear state in a distributed system. For systems needing to detect dead instances, use health checks, leases, heartbeats, or corresponding infrastructure lifecycles.

## 9. How Do Duplicate MBean Name Policies Affect This?

`MBeanExporter` has configuration for handling situations where an `ObjectName` already exists, typically via registration policy. Main values include:

- **FAIL_ON_EXISTING:** rejects/reports an error when the name is already registered.
- **IGNORE_EXISTING:** skips the exporter's registration if the name already exists.
- **REPLACE_EXISTING:** allows replacing the existing MBean according to exporter policy.

Verify the Spring version and exact API when configuring; for example:

\`\`\`java
import org.springframework.jmx.support.RegistrationPolicy;

exporter.setRegistrationPolicy(
    RegistrationPolicy.FAIL_ON_EXISTING
);
\`\`\`

Regarding listeners:

- If the exporter **ignores** an already existing MBean, do not infer a registered callback for a new MBean managed by the exporter.
- If an MBean **is replaced**, callbacks/ownership must be interpreted according to the actual behavior of registration support and the configured policy.
- If registration **fails**, diagnose the exception/logs rather than waiting for a registered callback as an error signal.

In systems with multiple exporters or manual registrations, enforce clear ownership and avoid using `REPLACE_EXISTING` merely to hide misconfiguration.

## 10. How Do Exporter Listeners Differ from JMX Notifications?

This is the most important point when designing an MBean observation mechanism.

### 10.1. MBeanExporterListener: Observing the Exporter

`MBeanExporterListener` receives callbacks directly from the Spring exporter. It reflects only the actions that the exporter notifies within its own scope.

\`\`\`java
exporter.setListeners(loggingListener);
\`\`\`

It is suitable for logging which MBeans belonging to a Spring module were exported or unexported during the Spring lifecycle.

### 10.2. MBeanServerDelegate: Registry-Wide Notifications for That Server

JMX has a standard delegate MBean named:

\`\`\`text
JMImplementation:type=MBeanServerDelegate
\`\`\`

The delegate can emit `MBeanServerNotification` when MBeans are registered/unregistered on **that specific MBeanServer**, regardless of whether the operation was performed by a Spring exporter or another component.

For example:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.MBeanServerNotification;
import javax.management.NotificationListener;
import javax.management.ObjectName;

ObjectName delegateName = new ObjectName(
    "JMImplementation:type=MBeanServerDelegate"
);

NotificationListener listener = (notification, handback) -> {
    if (notification instanceof MBeanServerNotification event) {
        System.out.printf(
            "JMX registry event: type=%s, object=%s%n",
            event.getType(),
            event.getMBeanName()
        );
    }
};

server.addNotificationListener(
    delegateName,
    listener,
    null,
    null
);

try {
    // Register/unregister MBeans to observe.
} finally {
    server.removeNotificationListener(
        delegateName,
        listener
    );
}
\`\`\`

**Differences in event source:**

| Property | MBeanExporterListener | MBeanServerDelegate notification |
| --- | --- | --- |
| Emitter | Spring `MBeanExporter` | JMX `MBeanServerDelegate` |
| Scope | Changes notified by the exporter | Registry of a single MBeanServer |
| Registration mechanism | `MBeanExporter.setListeners(...)` | `MBeanServer.addNotificationListener(...)` |
| Payload | `ObjectName` | Notification type + `ObjectName` + notification metadata |
| Used for | Observing exporter lifecycle | Observing registry-wide register/unregister events |
| When MBean is registered by another party | No callback guaranteed | Can receive notification from the same server's delegate |
| Listener lifecycle dependency | Spring exporter | JMX listener registered on the server |

If the goal is *every* registration and unregistration in an MBeanServer, delegate notifications are more appropriate. If the goal is *MBeans managed by a Spring module's exporter*, the exporter listener is more appropriate.

### 10.3. Spring ApplicationEvent Differs from Both Mechanisms Above

`ContextRefreshedEvent` and `ContextClosedEvent` are Spring ApplicationContext events describing context lifecycle. They do not carry lists of individual MBeans just registered or unregistered. You can combine Spring events with exporter listeners for diagnostics, but do not confuse the two notification types.

## 11. Designing Fault-Tolerant Listeners

A good listener typically has these characteristics:

1. **Fast:** do not perform HTTP calls, database queries, heavy filesystem I/O, or long blocking inside callbacks.
2. **Idempotent when needed:** update state keyed by `ObjectName` safely in the face of duplicates or reordered processing.
3. **No cascading failures:** handle exceptions in auxiliary logic to avoid disrupting the exporter's lifecycle.
4. **No data leaks:** log well-designed ObjectNames and only essential metadata.
5. **Thread-safe:** if state is read/written across multiple threads, use appropriate concurrent data structures.
6. **No registry-wide assumptions:** keep in mind the listener only tracks the exporter.
7. **Does not replace business lifecycle:** listeners serve observability, not transactional business logic.

Example of a listener tracking the set of names that received a registered callback:

\`\`\`java
package example.springjmx;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import javax.management.ObjectName;
import org.springframework.jmx.export.MBeanExporterListener;

public final class TrackingMBeanExporterListener
        implements MBeanExporterListener {

    private final Set<ObjectName> observed =
        ConcurrentHashMap.newKeySet();

    @Override
    public void mbeanRegistered(ObjectName objectName) {
        observed.add(objectName);
    }

    @Override
    public void mbeanUnregistered(ObjectName objectName) {
        observed.remove(objectName);
    }

    public Set<ObjectName> observedNamesSnapshot() {
        return Set.copyOf(observed);
    }
}
\`\`\`

The `observed` set is the listener's internal state, not an authoritative JMX inventory. If a real application needs exact state, combine checking `server.isRegistered(name)` or `queryNames` at the right time while accounting for concurrent changes.

## 12. What Happens When a Callback Throws an Exception?

`MBeanExporterListener` does not declare checked exceptions in its callback signatures, yet code inside can throw runtime exceptions. If a listener throws an error on the thread where the exporter is registering/unregistering, the consequences depend on the implementation and when the callback fires; do not assume exceptions will be silently ignored.

A logging-focused listener generally should not throw. If recording metrics fails, it can be handled internally:

\`\`\`java
@Override
public void mbeanRegistered(ObjectName objectName) {
    try {
        metricsRecorder.recordRegistered(objectName);
    } catch (RuntimeException ex) {
        log.warn(
            "Could not record JMX registration for {}",
            objectName,
            ex
        );
    }
}
\`\`\`

In this example, `metricsRecorder` is an application-provided collaborator, not a built-in Spring API. Logging should avoid excessive cost or exposing secrets inside exceptions.

If a business requirement states "every registration must be durably persisted to the DB", an exporter listener is not the sole reliable choice. Separate transaction, retry, and reconciliation mechanisms are needed, because callbacks may not run when the JVM exits abnormally.

## 13. Relationship Between Listeners and the Spring Lifecycle

`MBeanExporter` manages the MBeans it registers according to the Spring lifecycle. This typically involves:

- Initializing beans and configuring the exporter.
- Completing MBean registration when the exporter initializes.
- MBeans operating throughout the context's lifetime.
- Unregistering MBeans when the exporter is destroyed or the context closes.

In code using `AnnotationConfigApplicationContext`, `try-with-resources` ensures `close()` is called and puts singleton beans through destruction. That is why the Section 6 example can observe the unregistered callback.

However, several factors can affect this:

- A manually altered singleton bean does not mean the exporter immediately re-registers the MBean.
- An exporter may skip registering a duplicate-named MBean depending on policy.
- MBeans registered by code outside the exporter can remain after the Spring context closes.
- If using a custom `MBeanServer`, verify against the exact instance when calling `isRegistered`.
- In applications with multiple Spring contexts, each exporter has its own lifecycle and risks ObjectName contention.

## 14. Illustrating a Lifecycle Integration Test

A simple test can use a listener to collect events without needing JConsole or a remote connector.

\`\`\`java
package example.springjmx;

import java.lang.management.ManagementFactory;
import java.util.ArrayList;
import java.util.List;
import javax.management.ObjectName;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.MBeanExporterListener;

public final class ExporterLifecycleCheck {

    static final class EventRecorder
            implements MBeanExporterListener {

        final List<String> events = new ArrayList<>();

        @Override
        public void mbeanRegistered(ObjectName objectName) {
            events.add("REGISTER " + objectName.getCanonicalName());
        }

        @Override
        public void mbeanUnregistered(ObjectName objectName) {
            events.add("UNREGISTER " + objectName.getCanonicalName());
        }
    }

    public static void main(String[] args) throws Exception {
        EventRecorder recorder = new EventRecorder();
        ObjectName name = new ObjectName(
            "com.example.orders:type=Worker,name=LifecycleCheck"
        );

        AnnotationConfigApplicationContext context =
            new AnnotationConfigApplicationContext();

        context.registerBean(
            "worker",
            WorkerMonitor.class,
            WorkerMonitor::new
        );

        context.registerBean(
            "exporter",
            MBeanExporter.class,
            () -> {
                MBeanExporter exporter = new MBeanExporter();
                exporter.setBeans(java.util.Map.of(
                    name.toString(),
                    context.getBean("worker")
                ));
                exporter.setListeners(recorder);
                return exporter;
            }
        );

        context.refresh();

        boolean registered =
            ManagementFactory.getPlatformMBeanServer()
                .isRegistered(name);

        context.close();

        boolean stillRegistered =
            ManagementFactory.getPlatformMBeanServer()
                .isRegistered(name);

        System.out.println("registered=" + registered);
        System.out.println("afterClose=" + stillRegistered);
        System.out.println(recorder.events);
    }
}
\`\`\`

This example demonstrates lifecycle behavior; when writing formal integration tests, isolate ObjectNames, handle cleanup even if assertions fail, and avoid depending on shared MBeanServer state from other tests. In automated testing, replace manual checks with JUnit and assert the callback events.

The verification goal is the REGISTER event when the exporter registers the MBean and UNREGISTER when the context cleans up, rather than testing the bean's business logic.

## 15. Common Errors

| Symptom | Possible Cause | Diagnostic Steps |
| --- | --- | --- |
| Registered callback not seen | Listener not attached to the right exporter; MBean not in export list; registration failed. | Check `setListeners`, `setBeans`, exporter logs, and `isRegistered`. |
| MBean appears in JConsole, yet listener receives nothing | MBean registered by another component or using a different exporter. | Verify the registering owner and MBeanServer. |
| Registered seen, yet unregistered never seen | JVM terminated abnormally; context did not close; MBean managed outside exporter. | Check shutdown lifecycle and ownership. |
| `InstanceAlreadyExistsException` | Duplicate ObjectName in the same MBeanServer. | Check registration policy and other exporters. |
| Unregistered occurs during refresh/redeploy | Context/exporter destroyed/recreated. | Log the lifecycle of each context. |
| Callback count does not equal total MBeans | Listener scope is exporter-only; JVM creates system MBeans. | Use `queryNames` for actual registry count. |
| Listener blocks long, slowing startup | Heavy synchronous logic inside callback. | Use lightweight logging or bounded asynchronous handoff. |
| Listener throws runtime exception | Error handling metrics/logging/auxiliary infrastructure. | Catch/handle exceptions in listener; isolate observation concerns. |
| Wrong MBean name in event | `ObjectName`/naming strategy differs from expected. | Log canonical name, check metadata and mappings. |

## 16. Misconceptions to Avoid

### 16.1. "The listener monitors every MBean in the JVM"

Incorrect. The listener is attached to a specific `MBeanExporter`, so it only receives callbacks emitted by that exporter. To observe the entire server registry, consider delegate notifications.

### 16.2. "If no unregistered callback was seen, the MBean definitely still exists"

Incorrect. The JVM may have stopped or the MBean may have been removed by another component. Callback state is not a global source of truth.

### 16.3. "MBeanExporterListener is JMX's NotificationListener"

Incorrect. The two interfaces and mechanisms differ: one belongs to Spring's export lifecycle, and the other belongs to the JMX Notification API.

### 16.4. "On a duplicate-name registration, the listener is called for the existing name"

You cannot assume that. Callbacks depend on the exporter successfully performing the corresponding operation and on the applied registration policy.

### 16.5. "With a listener, there is no need to check MBeanServer"

Incorrect. `MBeanServer.isRegistered` and `queryNames` remain the direct APIs to inspect the registry at a point in time.

### 16.6. "A network request must be made inside the callback to ensure synchronization"

Do not assume that. Callbacks are synchronous, and network dependencies can slow down or break the lifecycle. If events need to be sent to another system, design a queue, batching, or an appropriate retry mechanism.

## 17. Practice Exercises

### Exercise 1 — Logging One MBean

Create `WorkerMonitorMBean`, `WorkerMonitor`, `LoggingMBeanExporterListener`, and `MBeanExporter` as in Section 6. Run the context and observe the registered log; close the context and observe the unregistered log.

**Goal:** understand callbacks tied to the exporter lifecycle.

### Exercise 2 — Two Listeners on One Exporter

Attach a logging listener and a metrics listener. Start an exporter registering two MBeans; verify that both listeners receive the corresponding callbacks.

**Goal:** understand `setListeners` and the difference between event counts and registry size.

### Exercise 3 — Registering an MBean Outside the Exporter

Use `ManagementFactory.getPlatformMBeanServer().registerMBean(...)` to directly register another MBean. Observe that the exporter listener does not fire a callback for that object, yet `server.queryNames` still finds it.

**Goal:** distinguish exporter lifecycle from the full JMX registry.

### Exercise 4 — MBeanServerDelegate

Register a JMX `NotificationListener` on `JMImplementation:type=MBeanServerDelegate`. Try registering/unregistering via both a Spring exporter and direct JMX APIs.

**Goal:** distinguish event types and observation scopes.

### Exercise 5 — Duplicate Names

In an isolated test environment, create two exporters sharing one ObjectName. Test `FAIL_ON_EXISTING` and `IGNORE_EXISTING`, noting how the application starts and how the listener receives callbacks.

**Goal:** understand ownership policies and avoid guessing callbacks from pre-existing names.

### Exercise 6 — Abnormal Application Termination

In a lab environment, compare normal `context.close()` against abrupt JVM termination. Observe the differences in cleanup and callbacks.

**Goal:** understand that callbacks are not a reliable distributed event protocol.

## 18. Review Questions

**1. What information does MBeanExporterListener receive?** Two callbacks `mbeanRegistered` and `mbeanUnregistered`, each receiving the `ObjectName` of the relevant MBean.

**2. Does the listener monitor all MBeans in the JVM?** No. It only receives notifications emitted by the attached exporter.

**3. When is the registered callback typically invoked?** After a successful MBean registration operation via the exporter.

**4. When is the unregistered callback typically invoked?** After the exporter unregisters a managed MBean, typically during cleanup/shutdown.

**5. Is the unregistered callback guaranteed if the JVM is hard-killed?** No. Normal shutdown lifecycle hooks may not execute.

**6. To listen to all registry events in an MBeanServer, which API should you look at?** Notifications from `JMImplementation:type=MBeanServerDelegate`, registered via `MBeanServer.addNotificationListener`.

**7. Should a listener perform long network tasks?** No. Keep callbacks fast, handle errors, and hand off to an appropriate asynchronous mechanism if needed.

**8. Does registered minus unregistered always equal MBeanServer.getMBeanCount?** No. The listener only observes one exporter's scope, and callbacks do not necessarily represent every MBean.

**9. Why inspect `ObjectName`?** Because it is the identifier the JMX registry uses to distinguish MBeans, investigate conflicts, and look up state.

**10. Can a listener be used to execute mandatory business transactions?** Do not treat this callback as a durable event channel; business workflows with strict guarantees need proper transaction or event delivery mechanisms.

## 19. Summary

`MBeanExporterListener` is the mechanism for tracking **Spring's MBean export lifecycle**. When `MBeanExporter` registers or unregisters the MBeans it manages, the listener receives callbacks with the `ObjectName`. This lets applications log, count events, or observe changes at the Spring–JMX integration layer without polling the entire registry.

To understand its exact scope, distinguish this listener from **`MBeanServerDelegate` notifications** monitoring broader registry events and from **Spring ApplicationContext events**. Listeners should be lightweight, error-safe, free of sensitive data, and never treated as sole proof of system state during abnormal shutdowns.

## References

- Spring Framework Javadoc — `MBeanExporterListener`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporterListener.html
- Spring Framework Javadoc — `MBeanExporter`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Java SE 21 — `MBeanServer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 — `MBeanServerNotification`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerNotification.html
- Java SE 21 — `MBeanServerDelegate`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerDelegate.html