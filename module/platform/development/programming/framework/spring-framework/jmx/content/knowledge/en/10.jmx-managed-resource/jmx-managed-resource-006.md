# Prototype vs. Singleton Beans and Suitability for Management via Spring JMX

## 1. Objectives

When exposing a Spring bean to JMX using \`@ManagedResource\` and \`MBeanExporter\`, you need to understand both the **Spring bean lifecycle** and the **lifecycle of the MBean registered in MBeanServer**. These two lifecycles are related, yet do not completely overlap.

The central question: should you use **singleton** or **prototype** when a bean is managed via JMX?

The common answer is: **a singleton or a singleton management adapter with a clear lifecycle is better suited for a stable management MBean**. Prototypes can be used in the system, but you should not assume each prototype instance automatically gets an MBean or that a JMX client can locate the exact prototype created at any arbitrary moment.

Spring JMX exposes an **object registered under a specific ObjectName**, whereas Spring bean scope determines how the container creates and manages instances. Both factors must be considered to avoid skewed observed state, ObjectName collisions, and resource leaks.

## 2. Reviewing Singleton and Prototype in Spring

### Singleton Scope

Within a Spring \`ApplicationContext\`, a bean with the default singleton scope has at most one instance created per bean definition. Every lookup of that bean definition in the same context returns the shared managed instance.

\`\`\`java
import org.springframework.stereotype.Component;

@Component
public class QueueMonitor {
    public int getQueueDepth() {
        return 42;
    }
}
\`\`\`

\`QueueMonitor\` does not declare \`@Scope\`, so it defaults to singleton. If the application has an application-level queue manager, a shared monitor usually reflects state in a way that is straightforward for JMX clients.

**Singleton does not mean JVM-wide singleton.** Two different ApplicationContexts can own separate singleton instances; a single context can also define multiple singleton beans of the same class type. If all of these instances export the same ObjectName into one MBeanServer, a name collision will occur.

### Prototype Scope

With prototype, Spring creates a new instance every time the container is asked for the bean:

\`\`\`java
import org.springframework.context.annotation.Scope;
import org.springframework.stereotype.Component;

@Component
@Scope("prototype")
public class JobWorker {
    private final long createdAtNanos = System.nanoTime();

    public long getCreatedAtNanos() {
        return createdAtNanos;
    }
}
\`\`\`

Example:

\`\`\`java
JobWorker first = context.getBean(JobWorker.class);
JobWorker second = context.getBean(JobWorker.class);

System.out.println(first == second); // false
\`\`\`

A commonly misunderstood point: **injecting a prototype into a singleton via ordinary dependency injection resolves the dependency only once when the singleton is created**. The singleton then holds a reference to that one injected prototype instance; it does not automatically receive a fresh instance on every method call.

To obtain a fresh prototype on demand, you can use \`ObjectProvider<JobWorker>\`, \`Provider<JobWorker>\`, or lookup method injection. However, these mechanisms do not make the new instances appear automatically under separate JMX ObjectNames.

## 3. JMX Manages MBeans by ObjectName, Not by Bean Scope

A JMX registry looks like:

\`\`\`text
MBeanServer
  |
  +-- com.example.jobs:type=QueueMonitor,name=Primary
  |       |
  |       +-- registered MBean instance or adapter
  |
  +-- com.example.jobs:type=WorkerPool,name=Main
          |
          +-- registered MBean instance or adapter
\`\`\`

Once an MBean is registered, clients use its **ObjectName** to locate it. JMX has no concept of "getting a fresh prototype" simply because a Spring bean has prototype scope.

Example of a \`@ManagedResource\` bean:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.jobs:type=QueueMonitor,name=Primary"
)
public class QueueMonitor {
    @ManagedAttribute
    public int getQueueDepth() {
        return 42;
    }
}
\`\`\`

When the exporter registers this bean, JMX clients access one MBean under the chosen ObjectName. When the exporter detects or retrieves the bean depends on exporter configuration, the bean definition, and the Spring context; do not infer that the annotation changes the bean's scope.

\`\`\`text
Spring container                JMX registry
-------------------------       -----------------------------
singleton QueueMonitor --export-> ObjectName QueueMonitor
prototype JobWorker #1
prototype JobWorker #2          (do not automatically get ObjectNames)
prototype JobWorker #3
\`\`\`

Spring manages bean creation; \`MBeanExporter\` manages MBean publication. The two systems connect during registration, yet there is no default rule turning every prototype into an automatic management endpoint.

## 4. Why Is Singleton Suitable for Typical Management MBeans?

### 4.1. Stable Identity

A JMX client, dashboard, or script typically saves an ObjectName to poll repeatedly:

\`\`\`text
com.example.jobs:type=QueueMonitor,name=Primary
\`\`\`

If each access corresponded to a different instance, clients would see discontinuous information. A singleton or singleton adapter maintains a stable endpoint, while the underlying implementation can change without forcing clients to discover new ObjectNames.

### 4.2. Consistent Observed State

Attributes such as \`ActiveWorkers\`, \`QueueDepth\`, and \`FailedJobs\` are usually system-wide or component-wide data. A singleton monitor aggregating from a shared service avoids each MBean accidentally reflecting a local prototype instance, which would yield confusing metrics.

### 4.3. Clear Lifecycle

The exporter can register MBeans when the context is active and unregister them when the exporter is destroyed. A context-managed singleton typically has a lifecycle closely aligned with the exporter, making it easy to predict when the ObjectName exists.

### 4.4. Reduced ObjectName Collisions

An ObjectName is unique within an MBeanServer at a given point in time. If multiple prototypes try to register:

\`\`\`text
com.example.jobs:type=JobWorker,name=Current
\`\`\`

only one MBean can exist under that name, unless a policy replaces or ignores existing objects. \`RegistrationPolicy.REPLACE_EXISTING\` is not an automatically suitable solution for managing multiple prototypes: clients may see an ObjectName unexpectedly switch to a different instance.

### 4.5. Bounded Management Overhead

Each MBean can incur metadata, listeners, object references, unregistration lifecycles, and observational data. Registering an MBean for thousands of short-lived objects increases registry size, query cost, and the risk of retaining references to objects that are no longer useful.

## 5. Preferred Design Example: Singleton Management Adapter

Suppose an application has many prototype-scoped workers allocated to run short-lived jobs. Instead of exporting each worker, create a **singleton management adapter** to monitor the service managing the workers.

\`\`\`java
package com.example.management;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.jobs:type=WorkerPool,name=Main",
    description = "Monitor and control the worker pool"
)
public class WorkerPoolManagement {
    private final WorkerPoolService poolService;

    public WorkerPoolManagement(WorkerPoolService poolService) {
        this.poolService = poolService;
    }

    @ManagedAttribute(description = "Number of active workers")
    public int getActiveWorkers() {
        return poolService.getActiveWorkerCount();
    }

    @ManagedAttribute(description = "Number of pending jobs")
    public long getPendingJobs() {
        return poolService.getPendingJobCount();
    }

    @ManagedOperation(description = "Request worker configuration refresh")
    public void requestRefresh() {
        poolService.requestConfigurationRefresh();
    }
}
\`\`\`

Here \`WorkerPoolService\` is a business service provided by the application with the illustrated methods; the purpose is to demonstrate adapter delegation. WorkerPoolManagement uses the default singleton scope, while internal workers can be prototypes, created and released as needed.

Export configuration:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
\`\`\`

The result is a stable management point:

\`\`\`text
com.example.jobs:type=WorkerPool,name=Main
  Attributes:
    ActiveWorkers
    PendingJobs
  Operation:
    requestRefresh()
\`\`\`

Clients do not need to know how many prototypes currently exist in the pool or whether they are created by \`ObjectProvider\`, a factory, a scheduler, or a thread pool.

## 6. Prototypes Are Not Necessarily Forbidden from Export

There are cases where you need to manage **a specific instance** instead of a group, such as:

- A processing session that lives long enough and needs individual operations.
- A dynamic connector with its own state, registered/unregistered under controlled conditions.
- A resource created at runtime with a unique ID and an application-managed lifecycle.

In these cases, you must explicitly solve:

1. Who creates the instance?
2. Who decides which instance gets exported?
3. What ObjectName is unique and stable for the instance's entire lifetime?
4. When the instance finishes, who unregisters the MBean?
5. How does a JMX client handle the MBean disappearing between two calls?
6. Does the registry have a limit on total MBean count?
7. Does the MBean hold references that prevent garbage collection?

Do not treat \`@Scope("prototype")\` + \`@ManagedResource\` as a recipe for "every getBean call creates another MBean". To truly manage dynamic instances, you need a component owning dynamic registration and cleanup.

## 7. Registering Dynamic MBeans for Individual Resources

When a dynamic resource needs to be exported, standard JMX allows registration under distinct ObjectNames. The following example uses an explicit Standard MBean.

**Management interface:**

\`\`\`java
package com.example.management;

public interface WorkerViewMBean {
    String getState();
    long getCompletedTasks();
}
\`\`\`

**Implementation:**

\`\`\`java
package com.example.management;

public class WorkerView implements WorkerViewMBean {
    private final WorkerSnapshotProvider provider;

    public WorkerView(WorkerSnapshotProvider provider) {
        this.provider = provider;
    }

    @Override
    public String getState() {
        return provider.state();
    }

    @Override
    public long getCompletedTasks() {
        return provider.completedTasks();
    }
}
\`\`\`

\`WorkerSnapshotProvider\` is an application interface/service with methods returning data for a single worker. Dynamic registration can be done via \`MBeanServer\`:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class WorkerMBeanRegistration {
    private final MBeanServer server;

    public WorkerMBeanRegistration(MBeanServer server) {
        this.server = server;
    }

    public ObjectName register(
            String workerId, WorkerViewMBean mbean) throws Exception {
        ObjectName name = new ObjectName(
            "com.example.jobs:type=Worker,id=" +
            ObjectName.quote(workerId)
        );
        server.registerMBean(mbean, name);
        return name;
    }

    public void unregister(ObjectName name) throws Exception {
        if (server.isRegistered(name)) {
            server.unregisterMBean(name);
        }
    }
}
\`\`\`

With Standard MBeans, the implementation must follow the \`WorkerView\` / \`WorkerViewMBean\` convention; the runtime type of the \`mbean\` parameter must be an eligible instance. When wrapping an arbitrary implementation, \`StandardMBean\` can be used to specify the management interface explicitly.

Record registered ObjectNames and unregister only **MBeans this component truly owns**, avoiding races if names are reused. Checking \`isRegistered\` before \`unregisterMBean\` is only a point-in-time check and does not eliminate race conditions. A registry/tracker synchronized by ID with cleanup in \`finally\` or a lifecycle callback is more suitable in production code.

Each dynamic MBean instance can carry its own \`id\`; however, IDs should be safe technical values without secrets or personal data.

## 8. Prototypes, Dependency Injection, and Data Consistency

A singleton management bean may depend on a prototype:

\`\`\`java
@Component
public class WorkerManagement {
    private final JobWorker worker;

    public WorkerManagement(JobWorker worker) {
        this.worker = worker;
    }
}
\`\`\`

If \`JobWorker\` is a prototype, Spring injects **one instance at the time \`WorkerManagement\` is created**. Thereafter, the singleton MBean reads that exact instance, not representing other workers.

If you want a fresh prototype worker each time:

\`\`\`java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Component;

@Component
public class WorkerFactoryClient {
    private final ObjectProvider<JobWorker> workerProvider;

    public WorkerFactoryClient(ObjectProvider<JobWorker> workerProvider) {
        this.workerProvider = workerProvider;
    }

    public void runWork() {
        JobWorker worker = workerProvider.getObject();
        // Use the new worker and manage resources if needed.
    }
}
\`\`\`

However, a management attribute should not call \`workerProvider.getObject()\` just to read "current state" because every poll creates a new instance, making the metrics meaningless. Instead, read from a \`WorkerRegistry\`, \`WorkerPoolService\`, or snapshot aggregator holding group-wide information.

### Anti-Pattern Example

\`\`\`java
@ManagedAttribute
public String getWorkerState() {
    return workerProvider.getObject().getState();
}
\`\`\`

Every time JConsole reads the attribute, it can instantiate a new worker, and if the worker has an expensive constructor or opens connections, monitoring itself impacts the application. The right approach is usually to read state from an actually managed object or aggregate.

## 9. Scope Does Not Determine Thread Safety

Singletons are shared across multiple threads; JMX clients can also read/invoke attributes and operations concurrently. Therefore, singleton management beans must be designed to be thread-safe, especially when both reading and mutating state.

Counter example:

\`\`\`java
private final java.util.concurrent.atomic.AtomicLong completed =
    new java.util.concurrent.atomic.AtomicLong();

@ManagedAttribute
public long getCompletedCount() {
    return completed.get();
}
\`\`\`

Or delegate to a service providing a synchronized snapshot. A few points:

- Use \`volatile\`, atomic types, or locks when state requires visibility/consistency.
- Do not hold locks while invoking external operations or notification callbacks if there is a risk of blocking the system.
- Monitoring getters should be fast, side-effect-free, and avoid heavy work.
- When returning multiple related metrics, use a consistent snapshot rather than reading multiple unsynchronized variables in arbitrary order.
- Prototypes are not automatically thread-safe: the same prototype instance can still be shared across threads if the application retains references and uses it concurrently.

**Bean scope and concurrency are two different axes.** Singleton governs instance reuse, while thread safety comes from state design and access patterns.

## 10. Spring Lifecycle: Who Is Responsible for Cleanup?

### Singleton

For singletons created and owned by the Spring container, Spring normally manages initialization and destruction callbacks when the context closes. \`MBeanExporter\` has a lifecycle tied to the context to unregister the MBeans it exported.

This makes singletons well-suited for dashboards staying connected to a fixed ObjectName throughout the application's lifetime.

### Prototype

Spring instantiates and configures prototypes upon request, but **does not automatically manage the complete destruction lifecycle of every prototype after handing out the instance** as it does for singletons. The application receiving the prototype is normally responsible for resource cleanup and destruction callbacks when the instance is no longer in use.

If a prototype is exported as an MBean, the MBeanServer can retain a reference to the object or adapter, preventing garbage collection from reclaiming the instance as expected. Timely unregistration is therefore essential. Do not treat "Spring created the prototype" as evidence that Spring will automatically unregister each such instance when its business task ends.

For short-lived resources, an aggregating singleton monitor is usually more effective. If per-resource MBeans are truly needed, build a lifecycle manager that owns both the resource and its registration/unregistration.

## 11. Duplicate ObjectName Across Multiple Contexts or Instances

For example, two Spring contexts both export:

\`\`\`text
com.example.jobs:type=WorkerPool,name=Main
\`\`\`

into the same platform MBeanServer. Because ObjectName must be unique within a server, the second exporter may encounter \`InstanceAlreadyExistsException\` or handle it according to \`RegistrationPolicy\`.

Main options:

- \`FAIL_ON_EXISTING\`: fail on duplicate; good for catching unexpected configuration.
- \`IGNORE_EXISTING\`: skip the new MBean if the same name already exists.
- \`REPLACE_EXISTING\`: replace the old MBean; requires thorough understanding of ownership and cleanup.

Do not use \`REPLACE_EXISTING\` to cycle through exposing multiple prototypes under the same name. Dashboards will lack a stable identifier per instance, and context shutdown can introduce ownership issues.

If there genuinely are multiple separate managed instances in the same MBeanServer, add an identifying key:

\`\`\`text
com.example.jobs:type=WorkerPool,name=Main,instance=alpha
com.example.jobs:type=WorkerPool,name=Main,instance=beta
\`\`\`

If each instance runs in a different JVM/MBeanServer, they can use the same ObjectName; clients distinguish them by server connection. You do not necessarily need an instance key solely because the application runs across multiple JVMs, unless your monitoring organization requires it.

## 12. Design Choices per Scenario

| Scenario | Business Scope | Recommended Management Endpoint | Reason |
| --- | --- | --- | --- |
| Application connection pool state | Singleton/pool | Singleton monitor | Stable identity and pool-wide data |
| Workers created per job | Prototype/short-lived | Singleton aggregator | Avoids one MBean per job |
| Application-wide scheduler | Singleton | Singleton MBean or adapter | Consistent operations and metrics |
| Multiple independent long-lived resources | Dynamic instances | Dedicated MBeans with unique ObjectNames and lifecycle manager | Need to observe/control individual resources |
| Request-scoped object | Request | Aggregate metrics on a singleton | No single stable request instance to manage via JMX |
| Singleton Spring bean holding an injected prototype | Singleton + prototype | Observe the exact injected dependency or aggregate | Prototype does not auto-refresh on each JMX call |
| Multiple ApplicationContexts in the same JVM | Multiple singletons | Clear naming policy and exporter ownership | Avoid MBean collisions |

Base your choice on **the unit of management clients need to see**, not merely the scope declared on the class.

## 13. Cost, Security, and Side Effects

When exporting an MBean from a bean of any scope, verify:

**Exposure:** Expose only \`@ManagedAttribute\` and \`@ManagedOperation\` members genuinely needed for operations. An internal prototype may contain personal data or sensitive business state; do not expose every field just for debugging convenience.

**Operation effects:** If a management MBean has \`reset()\` or \`stop()\`, know which object receives the command and the consequences of repeated calls. A proxy unexpectedly changing targets can cause operations to affect the wrong resource.

**Performance:** JConsole or monitoring systems may poll frequently. Getters must not instantiate expensive prototypes, run heavy queries, or hold locks long just to return status.

**Registry growth:** Every per-instance MBean increases registry and metadata size. For short-lived resources, frequent register/unregister calls can add overhead and race with querying clients.

**Security:** The \`@ManagedResource\` annotation does not configure remote JMX connector permissions. Secure the network, authentication/authorization, and validation for impactful operations just as with other MBeans.

## 14. Mental Model to Remember

\`\`\`text
Spring Scope
  |
  +-- Singleton: one bean instance / bean definition / ApplicationContext
  |      |
  |      +--> fits stable MBeans, fixed ObjectNames
  |
  +-- Prototype: created fresh when requested from container
         |
         +--> does NOT automatically create an MBean per instance
         |
         +--> if per-instance MBeans are needed:
                  lifecycle manager + unique ObjectName
                  + unregister when resource ends

JMX side:
  MBeanServer
     |
     +-- ObjectName -> one registered MBean
     +-- ObjectName -> one registered MBean
\`\`\`

**Conclusion:** For Spring Framework JMX, a singleton or a singleton management adapter is usually the right choice to provide a stable management endpoint with consistent metrics and a clear lifecycle. Prototype exists for on-demand instance creation; it does not implicitly mean "each instance is an MBean". When individual dynamic instances truly need management, actively design registration, naming, ownership, cleanup, and scale bounds.
