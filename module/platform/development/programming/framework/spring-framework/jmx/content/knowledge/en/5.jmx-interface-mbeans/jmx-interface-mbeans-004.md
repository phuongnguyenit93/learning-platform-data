# Controlling What Is Public Without Exposing It in the MBean Interface

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish between a **public Java API** and the **management interface exposed via JMX**.
- Identify exactly which MBean attributes and operations JMX tools can see and invoke.
- Design Standard MBeans, MXBeans, or Spring-managed MBeans with a **minimal management contract**, avoiding exposing internal methods or sensitive data.
- Understand that restricting the MBean interface and configuring JMX access permissions are two complementary control layers that must be applied together.
- Build appropriate adapter classes, DTOs/snapshots, metadata, or annotations; verify exposure using \`MBeanInfo\` instead of guessing.
- Recognize common information leak paths through getters, operations, exceptions, notifications, \`ObjectName\`, and exporter configurations.

## 2. "Public" Has Three Meanings to Distinguish

In Java and JMX, the word *public* is easily misunderstood:

1. **Java public:** a method or class accessible to other Java code according to language visibility rules.
2. **JMX exposed:** an attribute or operation actually exposed by the MBeanServer through the MBean interface and its metadata.
3. **Network accessible:** an external client has a network path to the JMX connector and is permitted by authentication/authorization mechanisms.

These three scopes are **not identical**. A \`public void deleteEverything()\` in a service does not automatically become a JMX operation just because the method is declared public. Conversely, if a developer deliberately adds that method to a Standard MBean interface or exports it via Spring JMX metadata, it can become a dangerous management operation even if the server only runs internally.

\`\`\`text
Spring / Java Application
+--------------------------------------------------+
| Java Service                                     |
| public refreshInternalIndex()                    |
| public loadCredentials()                         |
| public getQueueDepth()                           |
|                                                  |
|     [MANAGEMENT CONTRACT FILTER]                 |
|     Select only operations-serving functions     |
|                  |                               |
|                  v                               |
| MBean interface / exporter metadata              |
|   getQueueDepth()          [READ]                |
|   refreshIndexSafely()     [CONTROLLED ACTION]   |
+------------------|-------------------------------+
                   v
             MBeanServer
                   |
             JMX connector
                   |
          [AUTHENTICATION / AUTHORIZATION]
                   |
             JMX client
\`\`\`

**Principle:** expose through JMX only the management capabilities that are truly necessary, with clearly controlled data types and side effects. Do not use "the method is public" as a criterion for automatically exporting to JMX.

## 3. The MBean Interface Is an Allowlist

With a **Standard MBean**, an interface following the \`ClassNameMBean\` convention creates an explicit JMX contract. The getters/setters and methods on that interface form the surface recognized by the MBeanServer under Standard MBean rules.

For example, a cache management service may have many public methods for the application:

\`\`\`java
package example.cache;

public final class ProductCacheService {
    public long size() { return 256L; }

    public void clearCacheInternal() {
        // Internal operation, may be expensive or mutate state.
    }

    public String loadSecretConfiguration() {
        return "sensitive-value"; // Illustrative only, do not use in real code.
    }
}
\`\`\`

Do not arbitrarily expose the entire service as a management interface. Create an adapter with an MBean interface that only allows access to the safe parts:

\`\`\`java
package example.cache;

public interface ProductCacheMonitorMBean {
    long getEntryCount();
    boolean isHealthy();
}
\`\`\`

\`\`\`java
package example.cache;

public final class ProductCacheMonitor
        implements ProductCacheMonitorMBean {

    private final ProductCacheService cache;

    public ProductCacheMonitor(ProductCacheService cache) {
        this.cache = cache;
    }

    @Override
    public long getEntryCount() {
        return cache.size();
    }

    @Override
    public boolean isHealthy() {
        return true; // Replace with actual health check.
    }

    // This public method does not belong to ProductCacheMonitorMBean.
    // The Standard MBean interface does not expose it as an operation.
    public void internalMaintenance() {
        cache.clearCacheInternal();
    }
}
\`\`\`

Thus, JMX clients observe \`EntryCount\` and \`Healthy\`; they cannot directly invoke \`internalMaintenance\` through the Standard MBean contract even though that method is public in Java.

Points to remember:

- The \`ProductCacheMonitorMBean\` interface itself is the allowlist of capabilities to expose.
- The name \`getEntryCount\` creates a read-only JMX attribute \`EntryCount\`.
- The name \`isHealthy\` creates a read-only JMX attribute \`Healthy\`.
- If the interface declared \`setEntryCount(long)\`, JMX would expose a corresponding setter; for metrics, such modification should not be allowed.
- The \`internalMaintenance\` method is not on the management interface, so it does not become an operation of the Standard MBean contract merely by being defined public.

## 4. Complete Example: Registering and Inspecting the Exposed Surface

The following example uses only the standard JDK to demonstrate the difference between Java public methods and the MBean interface.

### 4.1. Class Declarations

\`\`\`java
package example.jmx;

public interface WorkerMonitorMBean {
    int getActiveWorkers();
    boolean isPaused();
    void resume();
}
\`\`\`

\`\`\`java
package example.jmx;

public final class WorkerMonitor implements WorkerMonitorMBean {
    private volatile boolean paused;
    private volatile int activeWorkers = 4;

    @Override
    public int getActiveWorkers() {
        return activeWorkers;
    }

    @Override
    public boolean isPaused() {
        return paused;
    }

    @Override
    public void resume() {
        paused = false;
    }

    // Java public, but not part of WorkerMonitorMBean:
    public String readInternalConnectionString() {
        return "internal-example"; // Illustrative value, do not use a real secret.
    }

    public void stopAllServicesInternal() {
        // Not exposed through the management interface.
    }
}
\`\`\`

\`WorkerMonitorMBean\` allows reading \`ActiveWorkers\`, reading \`Paused\`, and invoking \`resume\`. It does not expose the \`stopAllServicesInternal\` or \`readInternalConnectionString\` operations.

### 4.2. Registering with MBeanServer and Discovering Metadata

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import java.util.Arrays;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class JmxExposureDemo {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example:type=WorkerMonitor,name=Primary"
        );

        server.registerMBean(new WorkerMonitor(), name);
        try {
            MBeanInfo info = server.getMBeanInfo(name);

            System.out.println("Attributes:");
            for (MBeanAttributeInfo attribute
                    : info.getAttributes()) {
                System.out.printf(
                    "%s readable=%s writable=%s%n",
                    attribute.getName(),
                    attribute.isReadable(),
                    attribute.isWritable()
                );
            }

            System.out.println("Operations:");
            for (MBeanOperationInfo operation
                    : info.getOperations()) {
                System.out.println(operation.getName());
            }

            System.out.println("ActiveWorkers = " +
                server.getAttribute(name, "ActiveWorkers"));
            server.invoke(
                name,
                "resume",
                new Object[0],
                new String[0]
            );
            System.out.println("Paused = " +
                server.getAttribute(name, "Paused"));
        } finally {
            server.unregisterMBean(name);
        }
    }
}
\`\`\`

Key result: the metadata shows that \`ActiveWorkers\` and \`Paused\` are read-only attributes; \`resume\` is an operation. Internal public methods do not appear. The \`import java.util.Arrays;\` line is unnecessary for the example's behavior and can be omitted in a minimal implementation.

This is the direct way to verify the runtime contract. When evaluating an MBean, do not just read the code and assume; use \`getMBeanInfo\` and test the permitted commands according to operational requirements.

### 4.3. Attempting to Invoke an Unexposed Method

\`\`\`java
try {
    server.invoke(
        name,
        "stopAllServicesInternal",
        new Object[0],
        new String[0]
    );
} catch (javax.management.ReflectionException expected) {
    System.out.println(
        "Unexposed operation: " +
        expected.getClass().getSimpleName()
    );
}
\`\`\`

With the Standard MBean above, this operation is not in the JMX contract, so \`invoke\` cannot route it as an exposed operation. The specific exception types may depend on the implementation and actual error; what must be verified is that the metadata does not contain the operation and the invocation fails.

## 5. Getters Are Also a Form of Exposure

A common mistake is thinking only operations are dangerous because operations "perform actions." Getters can also disclose a lot of information.

Examples of methods that **should not be exposed verbatim over JMX**:

\`\`\`java
String getDatabasePassword();
String getBearerToken();
Map<String, String> getAllEnvironmentVariables();
String getJdbcUrlWithCredentials();
List<Customer> getRecentCustomers();
Throwable getLastFailureWithSensitiveContext();
\`\`\`

Even a read-only getter can:

- Expose credentials, internal endpoints, tokens, or signing keys.
- Leak personal data, payloads, request headers, or user activity history.
- Produce oversized responses, consuming memory and bandwidth if returning an entire collection.
- Cause unclear side effects if the getter runs heavy queries or mutates state.
- Allow attackers to infer internal structure or task processing timing.

Instead of exposing raw data, export **aggregated metrics** or **bounded state**:

| Do Not Expose | Safer Management Form |
| --- | --- |
| Database connection password | \`DatabaseConnectionHealthy: boolean\` |
| All environment variables | \`ConfigurationLoaded: boolean\` |
| Customer list | \`ActiveCustomerCount: long\` |
| Full queue payload | \`QueueDepth: long\`, \`OldestMessageAgeMs: long\` |
| Full stack trace with request data | \`LastErrorCode: String\`, \`ErrorCount: long\` |
| List of active tokens | \`ActiveSessionCount: long\` |
| Detailed config with secrets | \`ConfigVersion: String\`, \`LastReloadStatus: String\` |

Even a value like \`LastErrorCode\` should be designed carefully: application-controlled error codes are generally safer than exposing raw exception messages from external libraries or services.

## 6. Operations Are Control Privileges and Must Be Intentionally Bounded

Operations can be observational or state-changing. Distinguish them to decide whether to expose them.

| Operation | Risk | How to Handle |
| --- | --- | --- |
| \`getStatus()\` | Low if data is filtered. | Can be exposed; prefer an attribute for simple reads. |
| \`refreshMetrics()\` | Can generate load. | Expose if rate-limited or reasonably cheap. |
| \`clearCache()\` | Mutates state, increases downstream load. | Open only for necessary operations, with appropriate permissions. |
| \`reloadConfiguration()\` | Can alter system behavior. | Ensure validation and result status reporting. |
| \`pauseConsumers()\` | Halts business processing. | Requires clear authorization and guardrails. |
| \`deleteAllRecords()\` | Destroys data. | Typically should not be exposed as a JMX operation. |
| \`executeCommand(String)\` | Arbitrary command execution surface. | Do not expose. |
| \`getFileContents(String)\` | Can leak files. | Do not expose arbitrarily. |

Ask these questions before adding an operation:

1. **Who actually needs this action?** Does the operations team have a defined need, or is it just convenient for debugging?
2. **Can it be made safer?** For example, "reload a validated configuration" instead of "write any configuration value."
3. **Is the action repeatable?** If the client times out, did the call already run?
4. **Is the cost bounded?** Avoid operations that cause heavy load or unbounded locks.
5. **Is there a way to check the outcome?** Expose state, last timestamp, or bounded result codes.
6. **Is additional authorization needed?** Permission to read the whole MBean should not automatically imply permission to reset/stop.

Do not treat JMX as an "internal-only channel so every operation is safe." Later, connectors may be enabled, monitoring tools may be granted access, and accounts may be used beyond their intended scope.

## 7. Separating the Management Adapter from the Business Service

A well-controlled design:

\`\`\`text
JMX client
     |
     v
MBeanServer
     |
     v
Management adapter (small, stable API)
     |
     | Read only aggregated metrics
     | Invoke controlled actions
     v
Service / Repository / Messaging infrastructure
     |
     v
Business data, secrets, internal configuration
\`\`\`

### 7.1. Advantages

- **Reduced exposure surface:** the adapter's interface contains only deliberately chosen elements.
- **Reduced coupling:** the MBean is not the entire Java API contract of the service.
- **Allows implementation changes:** the service can be refactored while JMX attribute names remain stable.
- **Easy to verify:** JMX metadata is a small set to compare against the expected contract.
- **Cost control:** the adapter can snapshot/cache metrics instead of querying large data directly.
- **Easy lifecycle management:** register and unregister the MBean along with the application lifecycle.

### 7.2. Example of a Read-Only and Controlled-Action Adapter

\`\`\`java
public interface ImportJobAdminMBean {
    boolean isRunning();
    long getProcessedCount();
    String getLastRunStatus();
    void requestGracefulStop();
}
\`\`\`

Do not expose \`getRawJobPayloads()\`, \`getSchedulerCredentials()\`, or \`terminateProcessNow()\` without a specific operational need and control policy. Calling \`requestGracefulStop()\` should forward a conditional stop request to the service, rather than directly destroying resources.

In a real system, add state checks (for instance, stop only when the job permits), record audit logs, and ensure the command handles idempotency appropriately.

## 8. Standard MBean, MXBean, DynamicMBean: Different Exposure Paths

### 8.1. Standard MBean

**Main rule:** the \`FooMBean\` interface determines which attributes/operations are exported to JMX. This approach is easy to read and especially suitable when the management surface is small and stable.

\`\`\`java
public interface OrderQueueMBean {
    long getBacklog();
    void pause();
}
\`\`\`

Other \`public\` methods on the object implementing the interface do not automatically become JMX operations if they are not part of the interface or corresponding export mechanism.

### 8.2. MXBean

MXBeans can map Java types to standard open data. This reduces reliance on custom classes at the client, but **does not automatically filter sensitive data**. If an MXBean interface exposes a getter containing a mappable sensitive field, that field can still cross over JMX.

\`\`\`java
import javax.management.MXBean;

@MXBean
public interface PoolHealthMXBean {
    int getActiveConnections();
    int getIdleConnections();
}
\`\`\`

Best practice: design the MXBean interface to include only intentionally exposed types and states, avoiding returning whole multi-field business objects without controlling the mapping schema.

### 8.3. DynamicMBean and Open MBean

With \`DynamicMBean\`, the developer implements:

- \`getAttribute\`, \`setAttribute\`.
- \`getAttributes\`, \`setAttributes\`.
- \`invoke\`.
- \`getMBeanInfo\`.

This allows controlling names and metadata at runtime, but also places responsibility on the developer to keep **metadata consistent with accepted commands**. If \`getMBeanInfo()\` hides an operation while \`invoke()\` still executes it, a client can try calling the hidden operation by name; that is not secure access control. Actual execution must be blocked inside \`invoke\`, not merely hidden from metadata.

**Open MBeans** use standard type metadata such as \`OpenType\`, \`CompositeType\`, and \`TabularType\`. They help clients understand data structures, but do not provide authorization or automatically redact sensitive fields.

## 9. Spring Framework: @ManagedResource, @ManagedAttribute, and @ManagedOperation

Spring JMX supports exporting beans via \`MBeanExporter\` and metadata annotations such as:

- \`@ManagedResource\`: describes the managed resource.
- \`@ManagedAttribute\`: marks a getter/setter exposed as an attribute.
- \`@ManagedOperation\`: marks a method exposed as an operation.
- \`@ManagedOperationParameter\`: describes an operation parameter.

Example:

\`\`\`java
package example.springjmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example:type=Worker,name=Import",
    description = "Safe import worker management"
)
public class ImportWorkerManagement {

    @ManagedAttribute
    public long getProcessedCount() {
        return 100L; // Fetch metric from actual service.
    }

    @ManagedAttribute
    public boolean isRunning() {
        return true; // Fetch actual status.
    }

    @ManagedOperation(description = "Request a safe stop")
    public void requestStop() {
        // Forward validated request to service.
    }

    // Without @ManagedAttribute/@ManagedOperation:
    public String internalDebugInformation() {
        return "internal";
    }
}
\`\`\`

With an **exporter configured to use annotation metadata** (such as \`MetadataMBeanInfoAssembler\` and \`AnnotationJmxAttributeSource\`), only appropriately annotated members are exposed. Do not draw conclusions from annotations in code without verifying which exporter is actually configured.

### 9.1. Explicit Exporter Configuration in Plain Spring

\`\`\`java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class JmxExportConfig {

    @Bean
    public MBeanExporter managementExporter(
            ImportWorkerManagement managementBean) {
        AnnotationJmxAttributeSource source =
            new AnnotationJmxAttributeSource();

        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);

        MetadataNamingStrategy naming =
            new MetadataNamingStrategy();
        naming.setAttributeSource(source);

        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(naming);
        exporter.setBeans(Map.of(
            "importWorkerManagement", managementBean
        ));
        return exporter;
    }
}
\`\`\`

This snippet illustrates a specifically configured exporter and selected bean list. In Spring Boot, JMX auto-configuration depends on dependencies and application settings, so avoid creating two exporters managing duplicate \`ObjectName\`s.

### 9.2. Pitfalls When Using Exporters

1. **Overly broad auto-detection:** unrestricted detection/exporter configurations may register more beans than intended, depending on the assembler and exporter strategy. Choose an explicit list or controlled detection rules.
2. **Exporting all getters:** some assembler strategies may use reflection on public methods. Do not assume annotations block unannotated methods unless the configuration uses an annotation-based assembler.
3. **ObjectNames carrying sensitive data:** avoid key properties containing user IDs, tokens, or personal information.
4. **Duplicate exporters or manual registration:** the same JMX name cannot be registered twice on the same MBeanServer.
5. **Config changes unintentionally opening operations:** after changing an assembler/exporter, inspect the actual \`MBeanInfo\`.
6. **Confusing with HTTP/Actuator:** web endpoint configuration and JMX export configuration are different surfaces; each mechanism must be evaluated separately.

## 10. Minimizing Exposed Data

There are two complementary questions:

- **Does this capability need to be exposed?** Keep only necessary operational capabilities.
- **If so, what specific data needs to leave the application?** Return only the minimal amount of information.

### 10.1. Filtered Snapshots

Instead of exposing:

\`\`\`java
public Map<String, String> getRuntimeConfiguration();
\`\`\`

provide:

\`\`\`java
public String getConfigurationVersion();
public boolean isConfigLoaded();
public long getLastSuccessfulReloadEpochMillis();
\`\`\`

When error information is needed, use controlled error codes/levels; avoid returning exception messages that could contain URIs, SQL, request payloads, or tokens.

### 10.2. Bounding Size and Cost

Getters are called repeatedly by monitoring tools; they should:

- Return aggregated numbers, not export entire business records.
- Set element count limits on exposed collections/tables.
- Not scan the entire database on every read.
- Not trigger unexpected side effects inside a getter.
- Use short-lived snapshots/caches if fetching the underlying data is expensive.
- Clearly define the timestamp and consistency level of metrics.

An interface that looks read-only can still be a load vector if \`getDetails()\` returns millions of objects or executes heavy queries.

## 11. Metadata Is Not a Security Wall

\`MBeanInfo\` helps clients discover the registered interface, but metadata only describes the API. Hiding an operation from metadata **does not replace** blocking the invocation.

With \`DynamicMBean\`:

\`\`\`java
@Override
public Object invoke(
        String action,
        Object[] params,
        String[] signature)
        throws MBeanException, ReflectionException {

    if ("refreshSafeSnapshot".equals(action)) {
        refreshSafeSnapshot();
        return null;
    }

    throw new ReflectionException(
        new NoSuchMethodException(action)
    );
}
\`\`\`

The code must reject any operation name outside the allowlist. Likewise, \`getAttribute\` must reject names not in the contract, and \`setAttribute\` must reject non-writable attributes. If a developer only edits \`getMBeanInfo()\` while letting \`invoke()\` call any method via reflection, the MBean risks unintended control.

Proper verification covers both **metadata** and **behavior**: inspect what appears, and also try invoking an unauthorized name to confirm it does not execute.

## 12. Restricting Access at the Connector and Authorization Layer

Even when the MBean interface is well designed, the JMX connector also determines who can connect and run commands. Operational principles:

- Do not enable remote JMX across all environments when there is no need.
- When remote access is required, protect the connector with appropriate authentication, encryption, and network source restrictions.
- Apply read/admin roles as supported by the platform and connector mechanism; monitoring-only accounts must not have permission to invoke state-changing operations.
- Protect credentials, TLS configurations, and secrets from insecure logs or files.
- Review the JMX agent, credential store, container runtime, and how RMI/JMX ports are opened per environment.
- Audit state-affecting actions at the appropriate application or infrastructure layer, especially dangerous operations.

**Two layers of control:**

\`\`\`text
Layer 1: MBean Contract
    Which exact attributes/operations exist?

Layer 2: Connection and Authorization
    Who can view or invoke them?

Both are equally important.
\`\`\`

If an interface already exposes a data-deletion method, strict permissions only reduce reachability; shrinking the MBean surface from the design stage remains essential.

## 13. Verifying the Actual JMX Surface

During deployment, retrieve metadata after registration:

\`\`\`java
MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attr : info.getAttributes()) {
    System.out.printf(
        "%s: read=%s, write=%s%n",
        attr.getName(),
        attr.isReadable(),
        attr.isWritable()
    );
}

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.println("operation=" + op.getName());
}
\`\`\`

Then compare against the designed contract. Example log:

\`\`\`text
Expected attributes:
- ActiveWorkers: readable=true, writable=false
- Paused:        readable=true, writable=false

Expected operations:
- resume():     allowed

Not exposed:
- readInternalConnectionString()
- stopAllServicesInternal()
\`\`\`

Also test rejected cases:

\`\`\`java
try {
    server.getAttribute(name, "InternalConnectionString");
    throw new AssertionError(
        "Sensitive attribute unexpectedly exposed"
    );
} catch (javax.management.AttributeNotFoundException expected) {
    // Expected: attribute is not exposed.
}
\`\`\`

With \`DynamicMBean\`, also confirm the implementation rejects calls absent from metadata. In applications with multiple connectors or exporters, test against the exact \`MBeanServer\` and \`ObjectName\` used by operational clients.

## 14. Organizing the Contract and Change Rules

A management contract can be more stable than internal classes:

\`\`\`text
com.example.orders:type=Queue,name=Import

Attributes:
  Backlog            Long    read-only
  Healthy            Boolean read-only
  LastProcessedAt    Long    read-only

Operations:
  requestPause()     void    state-changing
\`\`\`

When adding a new capability, follow this process:

1. Describe the operational need and user group.
2. Choose an attribute or operation with a clear name, type, and semantics.
3. Identify potentially exposed information, side effects, and maximum load.
4. Deliberately add it to the interface/metadata.
5. Verify runtime \`MBeanInfo\` and required connection permissions.
6. Document client compatibility if changing names, types, or signatures.
7. Observe usage after deployment and remove capabilities no longer needed.

Do not use wildcards or automatic reflection to export "every public method" without an allowlist control mechanism.

## 15. Design Scenarios and Decisions

### 15.1. Need to Know Whether the Cache Is Healthy

**Need:** operations tooling wants to check whether the cache is working.

**Design:** \`Healthy\`, \`EntryCount\`, \`HitRate\` (if computed stably), \`LastRefreshTime\`.

**Avoid:** \`dumpAllEntries()\`, \`getAllKeysWithCustomerIds()\`, \`getBackingStoreCredentials()\`.

### 15.2. Need to Reset a Failing Worker

**Need:** operations staff want to request that a worker recover.

**Design:** \`requestRestart()\` or \`requestGracefulStop()\` with state validation, not accepting dangerous arbitrary parameters.

**Avoid:** \`killProcess(int)\`, \`executeShell(String)\`, \`deleteCheckpoint(Path)\`.

If the request has an asynchronous effect, expose \`LastRestartStatus\` or \`CurrentState\` so clients can check the outcome instead of assuming completion as soon as \`invoke\` returns.

### 15.3. Need to Diagnose Database Errors

**Need:** know the degree of connection failures.

**Design:** \`ConnectionPoolActive\`, \`ConnectionPoolIdle\`, \`LastConnectionErrorCode\`, \`ConnectionHealthy\`.

**Avoid:** \`JdbcUrlWithPassword\`, \`LastSqlWithParameters\`, full stack traces containing business data.

### 15.4. Need Per-Tenant Statistics

**Need:** request and queue counts per tenant.

**Design:** aggregated metrics without PII; if using \`TabularData\`, cap row counts and consider tenant identifiers only at a permitted level.

**Avoid:** returning full lists of users, orders, tokens, or email addresses as JMX table indices.

## 16. Practice Exercises

### Exercise 1 — Design a Minimal Interface

Given a \`PaymentService\` with public methods \`getPendingCount()\`, \`getPaymentById(id)\`, \`refundPayment(id)\`, \`getProviderApiKey()\`, and \`getLastRetryStatus()\`.

Design \`PaymentMonitorMBean\` containing only the attributes needed for observation. Explain why \`getPaymentById\`, \`refundPayment\`, and \`getProviderApiKey\` should not be exposed via JMX.

**Hint:** \`PendingCount\` and \`LastRetryStatus\` are suitable candidates once the semantics of their return values are controlled.

### Exercise 2 — Prove the Interface Blocks Methods

Use \`WorkerMonitorMBean\` and \`WorkerMonitor\` from above. Register in the platform MBeanServer, call \`getMBeanInfo\`, and list operations. Try invoking \`stopAllServicesInternal\` via \`MBeanServer.invoke\`.

**Objective:** understand the difference between Java public visibility and exposed JMX operations.

### Exercise 3 — Spring Annotations

Create a \`@ManagedResource\` containing only two read-only \`@ManagedAttribute\`s and one safe \`@ManagedOperation\`. Configure an exporter using an annotation-based assembler; verify that unannotated public getters do not appear in metadata.

**Objective:** understand that annotations only take effect when the exporter applies the right strategy.

### Exercise 4 — Negative Test

Create a list of **unexposed** names such as \`Password\`, \`RawPayload\`, \`ExecuteCommand\`. Verify metadata does not contain them and try calling them through the JMX API to confirm those actions are rejected.

**Objective:** understand that metadata and runtime behavior must be consistent.

### Exercise 5 — Review a State-Mutating Operation

Evaluate exposing \`clearCache()\`: who needs it, maximum frequency, invocation preconditions, downstream load risk, post-call result, and required permission tier. Propose a safer interface if needed.

## 17. Review Questions

**1. Is every public method of a Java object a JMX operation?** No. For Standard MBeans, the interface contract determines exposed attributes and operations.

**2. Can a read-only getter be dangerous?** Yes. A getter can leak secrets, personal data, or cause heavy load.

**3. If an operation is hidden from \`getMBeanInfo\` while still handled in \`DynamicMBean.invoke\`, is it safe?** No. Clients can still try invoking it by name. The implementation must reject unauthorized operations.

**4. Does Spring \`@ManagedOperation\` automatically cause every bean with that method to export to JMX?** No. An MBean exporter and appropriate assembler configuration are required.

**5. Does restricting JMX connector access replace designing a minimal interface?** No. Both limiting exported capabilities and controlling who has access are needed.

**6. Why use a separate adapter?** To decouple the management API from the implementation, filter data, control side effects, and keep the contract stable.

**7. When should a reset/reload operation be added?** When there is a defined operational need, safe execution conditions, permission limits, result observation, and error handling.

**8. Why should a getter for the entire environment configuration not be exposed?** Because configuration may contain credentials, topology, sensitive data, or content unnecessary for monitoring.

## 18. Summary

**An MBean interface is the boundary for exposing management capabilities.** Java visibility, JMX metadata, and network accessibility are separate concepts. For Standard MBeans, the interface defines the list of attributes/operations; for MXBeans and DynamicMBeans, data type contracts and implementations must enforce corresponding control; for Spring, the exporter and assembler determine which metadata takes effect.

Good design starts with a small allowlist, minimal aggregated data, and controlled operations. Always inspect metadata on \`MBeanServer\`, ensure the implementation actually rejects out-of-contract actions, and then protect the connector and permissions at the operational layer.

## References

- Java SE 21 — JMX \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 — JMX \`MBeanInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html
- Java SE 21 — \`DynamicMBean\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/DynamicMBean.html
- Java SE 21 — JMX specification and API: https://docs.oracle.com/javase/tutorial/jmx/
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html