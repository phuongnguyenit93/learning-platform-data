# Hiding methods outside the management interface in Spring Framework JMX

## Objectives

A Java class can have many \`public\` methods, yet not every \`public\` method should be callable by operators via JMX. In Spring Framework applications, the management surface typically needs to be **smaller, more stable, easier to understand, and narrower in impact** than a service's internal API. A **management interface** is a core technique for creating this boundary: explicitly defining which attributes and operations may be published, while other methods of the implementation continue serving internal Java/Spring callers without automatically becoming JMX operations.

This lesson focuses on **hiding methods that do not belong to the management interface**, not merely by making methods \`private\`, but by designing a bounded JMX contract, choosing the right export mechanism, and verifying actual metadata on the MBeanServer.

After this lesson, you will be able to:

- Distinguish a Java public API from a JMX management API.
- Explain how Standard MBeans/MXBeans publish only members of the management interface.
- Design a dedicated interface for observation/diagnostics/control instead of exporting an entire service.
- Understand the role of the \`StandardMBean\` wrapper when the interface name does not follow the naming convention.
- Distinguish interface-based export from Spring \`@ManagedResource\` and metadata assemblers.
- Watch out for Spring AOP proxies, multiple exporters, ObjectNames, lifecycle, and accidental exposure.
- Verify the actual attribute/operation list using \`MBeanInfo\`.
- Recognize security limits: not being exported via JMX differs from blocking access through all other paths.

## 1. The problem: public method does not mean allowed for management

Consider a business bean:

\`\`\`java
public class PaymentProcessor {
    public long getProcessedCount() { /* ... */ return 0; }
    public String getHealthSummary() { /* ... */ return "OK"; }
    public void reprocessPayment(String paymentId) { /* ... */ }
    public void deletePayment(String paymentId) { /* ... */ }
    public void changeAccountLimit(String accountId, long amount) { /* ... */ }
}
\`\`\`

In Java, \`public\` methods can be called by other code that holds a reference. However, the JMX surface should not include all of them by default:

\`\`\`text
PaymentProcessor Java public API
├── getProcessedCount()         [management: suitable]
├── getHealthSummary()          [management: possibly suitable]
├── reprocessPayment(id)        [business: should be restricted]
├── deletePayment(id)           [business: very sensitive]
└── changeAccountLimit(id, n)   [business: do not export arbitrarily]

Desired JMX management API
├── ProcessedCount (read-only)
└── HealthSummary (read-only)
\`\`\`

If a state-mutating method is exported by mistake, a JMX client with invoke permission can cause major impact without going through standard business workflows. Therefore, the good approach is **allowlisting through a management contract**, rather than hoping every developer remembers to avoid writing dangerous methods.

A management interface defines the exact set of methods to be exported. The implementation can contain additional public methods, yet Standard MBean introspection based on the management interface does not automatically expose public methods outside that interface.

## 2. Distinguishing three API layers

| Layer | Users | Purpose |
|---|---|---|
| Java internal API | Classes/services in the same JVM | Executing business logic, manipulating data, coordinating dependencies |
| Management interface | MBeanServer and JMX clients | Designed observation, diagnostics, and control |
| Remote JMX access | Management tools via connector | Accessing the management API according to permissions and network rules |

A method outside the management interface can remain \`public\` for other Java beans to use. That **does not create an extra JMX operation** if the MBean is registered properly under the Standard MBean contract. Conversely, adding a method to the management interface can change the JMX surface immediately on the next registration/export.

Do not confuse “hidden from JMX” with global security. If the same behavior is exposed via a REST endpoint, message handler, or another MBean, it can still be called through those channels. Every boundary needs its own controls.

## 3. Standard MBean: the interface is the published allowlist

A JMX Standard MBean relies on an interface with the \`MBean\` suffix by convention. Example:

\`\`\`java
package com.example.inventory;

public interface InventoryWorkerMBean {
    String getState();
    long getCompletedCount();
    int getQueueDepth();
    void requestPause();
}
\`\`\`

Implementation:

\`\`\`java
package com.example.inventory;

import java.util.concurrent.atomic.AtomicLong;

public class InventoryWorker implements InventoryWorkerMBean {

    private volatile String state = "RUNNING";
    private final AtomicLong completed = new AtomicLong();

    @Override
    public String getState() {
        return state;
    }

    @Override
    public long getCompletedCount() {
        return completed.get();
    }

    @Override
    public int getQueueDepth() {
        return 0; // Demo: read from a queue adapter in a real application.
    }

    @Override
    public void requestPause() {
        state = "PAUSE_REQUESTED";
    }

    // Public for Java callers, but NOT in InventoryWorkerMBean.
    public void rebuildInternalIndex() {
        // Internal work that can be resource-intensive.
    }

    // Public, but not part of the exposed JMX interface.
    public void deleteInternalCheckpoint(String checkpointId) {
        // Sensitive operation: do not include in the management interface.
    }

    protected void refreshLocalState() {
        // Implementation detail.
    }
}
\`\`\`

When registering an \`InventoryWorker\` as a Standard MBean:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
    "com.example.inventory:type=Worker,name=Sync");

server.registerMBean(new InventoryWorker(), name);
\`\`\`

JMX introspection recognizes \`getState()\`, \`getCompletedCount()\`, and \`getQueueDepth()\` as read-only attributes, along with \`requestPause()\` as an operation. The methods \`rebuildInternalIndex()\` and \`deleteInternalCheckpoint(String)\` are not present in the management interface, and therefore do not automatically appear as JMX operations in this Standard MBean model.

**Important:** the class/interface naming convention must be satisfied or the corresponding wrapper/registration API must be used. Otherwise, \`registerMBean\` can throw \`NotCompliantMBeanException\` rather than guessing which interface you meant to publish.

## 4. Getters, setters, and operations: more than just method names

In a Standard MBean:

\`\`\`java
public interface CacheMetricsMBean {
    long getHits();
    boolean isEnabled();
    void setEnabled(boolean enabled);
    String inspect(String key);
}
\`\`\`

When introspected by JavaBean/JMX rules:

- \`getHits()\` becomes a read-only attribute \`Hits\`.
- \`isEnabled()\` together with \`setEnabled(boolean)\` can form a readable/writable attribute \`Enabled\` as appropriate.
- \`inspect(String key)\` is an operation because it takes a parameter and does not follow the zero-arg attribute getter pattern.

**Omitting a setter from the interface** can keep an attribute read-only, even if the implementation has a public setter method for internal use.

Example:

\`\`\`java
public interface ThrottleStatusMBean {
    int getMaxConcurrency(); // Expose only the getter.
}

public class ThrottleStatus implements ThrottleStatusMBean {
    private volatile int maxConcurrency = 12;

    @Override
    public int getMaxConcurrency() {
        return maxConcurrency;
    }

    public void setMaxConcurrency(int value) {
        // Public Java method only; not exposed through this interface.
        maxConcurrency = value;
    }
}
\`\`\`

This is a tool for limiting runtime configuration changes via JMX. Yet hiding a setter alone does not replace authentication/authorization; the JMX connector and other API channels still need protection.

## 5. StandardMBean wrapper when the interface name does not match convention

An interface may be shared by multiple implementations or named by business role without matching the concrete class's prefix. In that case, you can explicitly specify the management interface with \`StandardMBean\`:

\`\`\`java
public interface QueueAdminMBean {
    int getDepth();
    String getState();
}
\`\`\`

\`\`\`java
public class KafkaQueueAdmin implements QueueAdminMBean {

    @Override
    public int getDepth() {
        return 42;
    }

    @Override
    public String getState() {
        return "RUNNING";
    }

    public void commitOffsetsForRepair() {
        // Not part of QueueAdminMBean.
    }
}
\`\`\`

Registration:

\`\`\`java
import javax.management.StandardMBean;
import javax.management.ObjectName;

KafkaQueueAdmin implementation = new KafkaQueueAdmin();
StandardMBean exposed = new StandardMBean(
    implementation,
    QueueAdminMBean.class
);

server.registerMBean(
    exposed,
    new ObjectName("com.example.queue:type=Admin,name=Kafka")
);
\`\`\`

The wrapper makes it explicit that \`QueueAdminMBean\` is the management contract. This is useful when you want to keep the management interface stable while swapping concrete implementations. It also avoids renaming a class and accidentally breaking Standard MBean naming rules.

Note that the interface must declare valid members according to Standard MBean rules. For complex types needing good compatibility with remote clients, consider MXBean instead of putting bulky objects into signatures.

## 6. MXBean also bounds the surface by interface

An MXBean is a type of management interface with rules for mapping data to Open Types. Example:

\`\`\`java
public interface QueueRuntimeMXBean {
    long getMessagesProcessed();
    int getActiveConsumers();
    String getEffectiveState();
}
\`\`\`

An implementation:

\`\`\`java
public class QueueRuntime implements QueueRuntimeMXBean {

    @Override
    public long getMessagesProcessed() {
        return 0L;
    }

    @Override
    public int getActiveConsumers() {
        return 4;
    }

    @Override
    public String getEffectiveState() {
        return "RUNNING";
    }

    public void purgeDeadLetters() {
        // Public Java method, but not part of the MXBean interface.
    }
}
\`\`\`

The MBeanServer can publish the \`QueueRuntimeMXBean\` interface by MXBean convention or via a \`StandardMBean\` wrapper configured in MXBean mode. Like Standard MBeans, only members belonging to the MXBean interface form the published management contract.

MXBeans differ in mapping data to types that exchange more cleanly across JMX clients, typically represented via Open MBean types. Even so, not every Java object type is automatically compatible; mapping rules and payload sizes must be respected.

## 7. Management interface as a minimal surface

Good design usually separates:

\`\`\`text
Business service
├── processBatch()
├── retryFailedPayment()
├── deleteTransaction()
├── changePolicy()
├── getHealthSnapshot()
└── getProcessedCount()

               |
               | adapter calls permitted methods
               v

Management adapter implements WorkerStatusMXBean
├── getHealthState()
├── getProcessedCount()
└── getPendingCount()
\`\`\`

Benefits:

1. Avoids coupling the domain service directly to JMX concepts.
2. Separates management semantics from business workflows.
3. Prevents a surface cluttered with dangerous operations added out of developer convenience.
4. Makes it easy to verify the JMX contract when refactoring the implementation.
5. Allows one management contract to serve multiple backend implementations.
6. Enables applying validation, rate limiting, redaction, and tailored response structures.

**A dedicated interface does not have to be implemented directly by the domain service.** You can use an adapter:

\`\`\`java
public interface ProcessingStatusMBean {
    long getCompletedCount();
    String getState();
}
\`\`\`

\`\`\`java
public final class ProcessingStatus
        implements ProcessingStatusMBean {

    private final ProcessingService service;

    public ProcessingStatus(ProcessingService service) {
        this.service = service;
    }

    @Override
    public long getCompletedCount() {
        return service.completedCount();
    }

    @Override
    public String getState() {
        return service.safeStateSummary();
    }
}
\`\`\`

Here \`ProcessingService\` is the application's business service, while \`ProcessingStatus\` exposes only the two required methods. Does \`ProcessingStatusMBean\` not follow the \`ProcessingStatusMBean\` convention? In this example the names match, so a Standard MBean can be used directly. If the implementation name differs, a \`StandardMBean\` wrapper helps specify the interface explicitly.

## 8. Spring Framework JMX: interfaces and exporters

Spring has multiple JMX export paths:

- Registering Standard MBeans/MXBeans directly via \`MBeanServer.registerMBean\`.
- Using Spring \`MBeanExporter\` to manage registration/lifecycle of selected beans.
- Using \`AnnotationMBeanExporter\` with \`@ManagedResource\`, \`@ManagedAttribute\`, and \`@ManagedOperation\`.
- Using an \`MBeanInfoAssembler\` or metadata assembler with an appropriate export strategy.

The key is: **you must understand which criteria the actual export mechanism uses to pick methods**. A Standard MBean management interface is an allowlist recognized by JMX introspection. Annotation export uses annotations/metadata rather than simply relying on a Standard MBean interface. If you configure an assembler that publishes more methods, the result can differ from “only methods in the interface”.

### 8.1 Using MBeanExporter with a Standard MBean adapter

Java configuration example:

\`\`\`java
import java.lang.management.ManagementFactory;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class ManagementExportConfiguration {

    @Bean
    public InventoryWorker inventoryWorker() {
        return new InventoryWorker();
    }

    @Bean
    public MBeanExporter managementExporter(InventoryWorker worker) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(ManagementFactory.getPlatformMBeanServer());
        exporter.setBeans(Map.of(
            "com.example.inventory:type=Worker,name=Sync",
            worker
        ));
        return exporter;
    }
}
\`\`\`

In this configuration, the \`InventoryWorker\` bean follows the Standard MBean convention through \`InventoryWorkerMBean\`. The Spring exporter registers the bean and manages the lifecycle of the registration it owns. Public methods outside the interface are not automatically published when JMX exports the bean under the Standard MBean contract.

When using a Spring version with different autodetection/assembler settings, inspect the actual exported metadata. Do not register the same \`ObjectName\` via both manual code and an exporter without a clear ownership model.

### 8.2 Do not equate @ManagedResource with a Standard MBean interface

Annotation example:

\`\`\`java
@Component
@ManagedResource(
    objectName = "com.example.inventory:type=Metrics,name=Sync")
public class InventoryMetrics {

    @ManagedAttribute
    public long getCompletedCount() {
        return 0L;
    }

    @ManagedOperation
    public void resetCounters() {
        // An operation with side effects.
    }

    public void dangerousInternalRepair() {
        // Not annotated.
    }
}
\`\`\`

When \`AnnotationMBeanExporter\` uses the corresponding annotation metadata, \`dangerousInternalRepair()\` does not appear automatically just because it is a public method. However, this is a **rule of annotation-driven export**, not the result of Standard MBean interface filtering. If the exporter uses another assembler or exports the same bean along a different path, re-verify.

A system can use both approaches, but never put the same bean into two export paths sharing an \`ObjectName\`.

## 9. Why simply changing a method from public to private is not enough

A common question: “I don't want JMX to see \`purge()\`, can I just make it \`private\`?” If the method is an implementation detail and does not need to be called from elsewhere, reducing Java visibility makes sense. Yet that alone does not solve the full management API design problem:

- A new public method might be added later.
- Proxies/AOP, other interfaces, or exporter configs can change introspection behavior.
- Dangerous operations might sit in an allowed method whose scope is too broad.
- There is no separate contract helping reviewers see what is permitted for publication.

A management interface helps keep an explicit list:

\`\`\`java
public interface CacheStatusMBean {
    long getEntryCount();
    long getEvictionCount();
    String getHealthSummary();
}
\`\`\`

Even if the implementation has public methods \`clearAll()\` or \`rebuildIndex()\`, they are not published in this Standard MBean contract. That bounds the surface **architecturally**, rather than relying entirely on individual method modifiers inside the class.

## 10. A Java interface is not an authorization mechanism

This is a critical distinction:

| Question | Solved by management interface? |
|---|---|
| Which methods are published by JMX in this contract? | Yes |
| Which operations can a JMX client see? | Yes, with proper export |
| Is the client authenticated? | No |
| Does the operator have permission to invoke the operation? | Not automatically |
| Are parameters valid and non-harmful? | No |
| Is the invocation audited? | No |
| Is the action idempotent or rollback-safe? | No |
| Can the same method be called via another API? | Not controlled |

A small interface is a **surface boundary**, not access control. If an operator has permission to invoke \`requestPause()\`, it can still alter runtime state. Protect the JMX connector, authentication/authorization, TLS/management network, auditing, and state-checking logic according to risk level.

Read-only operations can also incur high cost if they scan large datasets or query downstream systems. Keep getters lightweight and data-bounded.

## 11. Spring AOP proxies and interface export

A Spring bean may be wrapped by a JDK dynamic proxy or a CGLIB proxy due to \`@Transactional\`, \`@Async\`, AOP advice, and other mechanisms. This affects how exporters and JMX introspection see the class/interface.

Example:

\`\`\`text
Target: InventoryWorker implements InventoryWorkerMBean
        |
        v
Spring JDK Proxy
        |
        v
Bean seen by the exporter
\`\`\`

A JDK proxy only implements the interfaces selected for proxying, so confirm that the management interface is actually exposed on the proxy and that the exporter has a way to detect it. CGLIB proxies have different characteristics. If introspection cannot locate a Standard MBean interface, \`NotCompliantMBeanException\` or unexpected names/metadata may occur depending on the export path.

A design that reduces coupling is a **dedicated management adapter**:

\`\`\`text
Spring AOP-proxied service
         |
         | dependency injection
         v
ManagementAdapter implements ManagementAdapterMBean
         |
         v
MBeanExporter / MBeanServer
\`\`\`

The adapter calls the service through the real Spring proxy so advice stays effective, without needing to export the entire business class. This usually keeps the management contract stable when the service is refactored or adds new methods.

## 12. Can there be multiple management interfaces?

A Java class can implement multiple interfaces. However, Standard MBeans have rules identifying **one management interface for a specific registration** or requiring explicit configuration/wrappers. Never assume every interface a class implements is automatically merged into one MBean by JMX.

Example:

\`\`\`java
interface HealthView {
    String getState();
}

interface AdminControl {
    void requestPause();
}
\`\`\`

If you want to expose a specific set, create a purposeful management contract:

\`\`\`java
public interface WorkerAdminMBean {
    String getState();
    void requestPause();
}
\`\`\`

Or export separate adapters with distinct \`ObjectName\`s if you genuinely need to separate read-only and control surfaces. Note that splitting MBeans by interface does not create a permission boundary if the same connector allows any client to invoke any operation.

## 13. MBeanInfo metadata is the factual evidence

Do not just read code and guess. After registration, query the MBeanServer itself:

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanAttributeInfo;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.println("ATTRIBUTE: " + attribute.getName()
        + ", readable=" + attribute.isReadable()
        + ", writable=" + attribute.isWritable());
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println("OPERATION: " + operation.getName());
}
\`\`\`

If you expect \`deleteInternalCheckpoint\` to be hidden, assert it is **not** present in \`info.getOperations()\`. Also verify there are no unexpectedly writable attributes, as a public setter can turn into write access when exposed in an interface or assembler.

### 13.1 Negative contract test

An integration test can ensure internal methods are not exported:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;

import java.lang.management.ManagementFactory;
import java.util.Arrays;
import javax.management.*;

import org.junit.jupiter.api.Test;

class InventoryWorkerVisibilityTest {

    @Test
    void onlyManagementContractIsVisible() throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
            "com.example.test:type=InventoryWorker,name=Sample");

        InventoryWorker worker = new InventoryWorker();
        boolean registeredHere = false;

        try {
            server.registerMBean(worker, name);
            registeredHere = true;

            MBeanInfo info = server.getMBeanInfo(name);

            assertTrue(
                Arrays.stream(info.getOperations())
                    .anyMatch(op -> op.getName().equals("requestPause"))
            );

            assertFalse(
                Arrays.stream(info.getOperations())
                    .anyMatch(op -> op.getName().equals(
                        "deleteInternalCheckpoint"))
            );

            assertFalse(
                Arrays.stream(info.getOperations())
                    .anyMatch(op -> op.getName().equals(
                        "rebuildInternalIndex"))
            );

        } finally {
            if (registeredHere) {
                server.unregisterMBean(name);
            }
        }
    }
}
\`\`\`

In real tests, use a distinct namespace or separate \`MBeanServer\` to avoid \`ObjectName\` contention when running in parallel. The \`registeredHere\` flag in the example ensures cleanup removes only the entry registered by this test, not an MBean belonging to another test/process.

Negative testing is critical: verify not only that “desired metrics exist”, but also that “no out-of-contract commands exist”.

## 14. Diagnosing when methods outside the interface still appear

If JConsole still displays a method you did not put in the management interface, possible causes include:

1. **The MBean was exported via another mechanism**: a Spring metadata assembler or dynamic MBean may decide members using different rules.
2. **Registration did not use the expected StandardMBean wrapper**: the implementation class/management interface differs from what you think.
3. **Multiple MBeans represent the same logical resource**: the client is looking at a different \`ObjectName\` or a different exporter.
4. **Duplicate ObjectName or overwritten registration**: the live MBean is not the instance whose code you just read.
5. **Spring AOP proxy or class scanning**: the exporter detected target/proxy interfaces unexpectedly.
6. **Stale metadata in the JMX client**: the UI may cache views; query \`MBeanServer.getMBeanInfo\` directly on the right server and instance.
7. **Interface inherits the method**: the method lives on a superinterface of the management interface, so it still belongs to the contract even if not declared directly in the file you are viewing.

Investigation steps:

\`\`\`text
Identify the right JVM / JMX connector
    ↓
Identify the target MBeanServer
    ↓
Identify the actual ObjectName
    ↓
Read MBeanInfo from that server
    ↓
Identify exporter/assembler or StandardMBean wrapper
    ↓
Identify the recognized management interface
    ↓
Fix the contract or registration path
\`\`\`

Do not try to “hide” a method by piecemeal renaming if the root cause is another exporter publishing the entire bean.

## 15. Inherited methods and default methods on interfaces

A management interface can extend another interface:

\`\`\`java
public interface BasicStatus {
    String getState();
}

public interface WorkerStatusMBean extends BasicStatus {
    long getCompletedCount();
}
\`\`\`

The inherited \`getState()\` method is still part of the \`WorkerStatusMBean\` contract under Java interface inheritance. When evaluating the JMX surface, inspect not only directly declared methods; inspect the entire inheritance tree.

Similarly, if you place a default method on a management interface, consider the corresponding introspection behavior and compatibility with the JMX/Spring versions in use. Do not inherit from a huge business interface just to reuse one management getter, as that can accidentally pull many extra methods into the JMX contract.

A good management interface is typically small, stable, and free of complex inheritance.

## 16. Sensitive data and methods should not be exported via interface

Beyond control operations, also evaluate getters that return sensitive information:

\`\`\`java
public interface InternalDebugMBean {
    String getDatabasePassword(); // Should not be published.
    String getAccessToken();      // Should not be published.
    String getRawRequestBody();   // May contain PII/secrets.
}
\`\`\`

Even as read-only getters, publishing sensitive data over JMX remains a risk. A better contract:

\`\`\`java
public interface SafeRuntimeStatusMBean {
    String getDatabaseConnectionState();
    long getFailedRequestCount();
    long getLastSuccessfulSyncEpochMillis();
}
\`\`\`

Expose only non-sensitive aggregated status. Data types should be simple and size-bounded, especially for remote JMX clients. Do not return unbounded collections or internal objects with deep classloader dependencies.

## 17. Management interface design workflow

### Step 1: list real operational needs

Instead of exporting an entire service and trying to hide a few methods, start by asking:

- Which statuses do operators need to read?
- What diagnostics are needed during an incident?
- Are control commands truly necessary, or is there a better control plane?
- Who are the consumers—JConsole, a monitoring agent, or scripts?
- Must this API remain stable across releases?

### Step 2: choose a small interface

\`\`\`java
public interface ImportWorkerStatusMXBean {
    String getEffectiveState();
    long getBacklog();
    long getCompletedCount();
}
\`\`\`

If control is required, consider a separate interface/adapter with an appropriate security boundary. Splitting interfaces alone is insufficient for authorization if everyone uses the same JMX connector.

### Step 3: choose a single export path

Decide:
- Standard MBean by convention?
- MXBean?
- \`StandardMBean\` wrapper?
- Spring \`MBeanExporter\`?
- Annotation-driven export?

Avoid letting two mechanisms register the same bean/ObjectName without a clear owner.

### Step 4: manage ObjectName and lifecycle

The ObjectName must be unique in MBeanServer, contain no secrets, and stay stable for clients. The registering component must unregister when the context closes if it owns that registration. Do not release the platform MBeanServer merely because one Spring context is destroyed.

### Step 5: verify both presence and absence

Read \`MBeanInfo\` and verify:
- Required attributes exist with right read/write flags?
- Required operations exist with right signatures?
- Out-of-contract methods are truly hidden?
- No sensitive data or unintended operations?

### Step 6: maintain the contract

Every interface change is a management surface change that can break dashboards/scripts. For breaking changes, manage versioning and migration intentionally. If you only refactor the implementation without changing the interface, JMX clients do not need to know internal details.

## 18. Applied exercises

**Exercise 1 — Standard MBean.** Given class \`CacheControl\` with methods \`getHitCount()\`, \`getMissCount()\`, \`clearAll()\`, \`deleteByKey(String)\`, and \`rebuildIndex()\`. Write \`CacheControlMBean\` publishing only the two counters. Explain why the remaining methods can stay public in Java yet not become Standard MBean JMX operations.

**Exercise 2 — Hidden setter.** \`WorkerPool\` has \`getConcurrency()\` and \`setConcurrency(int)\`. The management interface declares only \`getConcurrency()\`. Will the \`Concurrency\` attribute on JMX be writable under the Standard MBean contract? No, unless a corresponding setter is exposed by the interface/assembler.

**Exercise 3 — Differently named interface.** \`RabbitQueueAdmin\` implements \`QueueAdminMBean\` instead of \`RabbitQueueAdminMBean\`. Use the \`StandardMBean\` wrapper to specify the management interface during registration.

**Exercise 4 — Spring proxy.** A \`@Transactional\` service is wrapped in a JDK dynamic proxy. The exporter fails to recognize the desired management interface. Propose an independent \`WorkerStatus\` adapter that injects the service proxy and exports the adapter, avoiding dependence on the domain service's proxy type.

**Exercise 5 — Negative test.** Write assertions on \`MBeanInfo\` proving operation \`requestPause\` exists while operation \`deleteAllData\` does not. Explain why testing absence is just as important as testing presence.

**Exercise 6 — Security.** Method \`resetStatistics()\` is in the management interface. Is it automatically safe because it was allowlisted? No: permissions, auditing, preconditions, and side-effect verification are still required.

## Summary

A management interface is the way to draw a clear boundary between an **internal Java API** and a **JMX management API**. In Standard MBeans and MXBeans, only members belonging to the chosen management interface are published; other public methods of the implementation do not automatically become JMX operations. Spring \`MBeanExporter\` can manage registration/lifecycle, while annotation-driven export uses different member selection rules, so you must identify the actual export path. Good design uses a small interface or management adapter, keeps ObjectNames and ownership clear, verifies the published list via \`MBeanInfo\`, and protects connectors/operations with appropriate permissions. That is the foundation for hiding methods outside the management interface intentionally, sustainably, and verifiably.
