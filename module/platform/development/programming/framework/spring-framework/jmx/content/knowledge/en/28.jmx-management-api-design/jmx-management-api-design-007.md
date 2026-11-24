# Writing Operator Descriptions and Usage Examples in Spring JMX

## 1. Why Does a Management API Need Clear Documentation?

Seeing an MBean appear in JConsole or VisualVM does not mean operators know which methods are safe to invoke. Names like \`reset\`, \`reload\`, \`pause\`, or \`clear\` are usually too short to explain consequences and blast radius. In Spring Framework JMX, metadata and runbook documentation should help answer: which system the MBean serves, what units the metrics use, how fresh the data is, whether a command affects a single node or the entire cluster, what preconditions must be checked, and how to verify the outcome.

Management API documentation has two complementary parts:
- **Descriptions in MBeanInfo**: concise sentences describing the MBean, attributes, operations, and parameters, shown in JMX tools.
- **Operational README/runbook**: usage examples, preconditions, permissions, risks, expected duration, verification steps, and recovery procedures.

Never use descriptions as an authorization mechanism; a phrase like "admin only" does not stop a client with invoke permissions.

## 2. Which JMX Metadata Can Carry Descriptions?

\`MBeanInfo\` has \`getDescription()\`; \`MBeanAttributeInfo\`, \`MBeanOperationInfo\`, \`MBeanParameterInfo\`, and \`MBeanNotificationInfo\` also carry their own descriptions.

Spring provides commonly used annotations:
- \`@ManagedResource(description = "...")\` for the MBean itself.
- \`@ManagedAttribute(description = "...")\` for attributes.
- \`@ManagedOperation(description = "...")\` for operations.
- \`@ManagedOperationParameters\` and \`@ManagedOperationParameter\` for parameter names and descriptions.

These descriptions only appear in \`MBeanInfo\` when the exporter uses the corresponding metadata path, such as \`AnnotationJmxAttributeSource\` and \`MetadataMBeanInfoAssembler\`. If a bean is registered as a Standard MBean via a standard interface, descriptions may come from another mechanism. **Always inspect the registered \`MBeanInfo\` instead of guessing from source code.**

## 3. Rules for Writing Descriptions

A useful description usually states **subject + meaning + scope + operational behavior**. For attributes, specify unit, freshness, and read-only/writable status. For operations, specify impact, synchronous/asynchronous nature, preconditions, or cautions.

| Element | Generic Description | Operator-Helpful Description |
| --- | --- | --- |
| QueueDepth | Queue size | Number of pending jobs on this JVM; read-only snapshot |
| Paused | Paused state | True when this worker stops accepting new jobs |
| LastUpdatedAt | Last update | UTC timestamp of the latest management snapshot |
| pause() | Pause service | Request graceful pause for this node; active jobs continue |
| retryFailedJob | Retry job | Retry one failed job by ID; verify idempotency first |

Do not claim "real-time" if the figure is cached; do not promise an operation completes synchronously if it only enqueues a request. Avoid overly long descriptions that reduce scannability in UIs; move multi-step procedures into a runbook.

## 4. Example Documented Spring Management Adapter

~~~java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedOperationParameters;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.jobs:type=Worker,name=Primary",
    description = "Operational status and controls for the current worker node"
)
public final class WorkerJmxAdapter {
    private final WorkerManagement management;

    public WorkerJmxAdapter(WorkerManagement management) {
        this.management = management;
    }

    @ManagedAttribute(
        description = "Pending jobs on this JVM; read-only count"
    )
    public int getQueueDepth() {
        return management.snapshot().queueDepth();
    }

    @ManagedAttribute(
        description = "True if new jobs are rejected on this worker"
    )
    public boolean isPaused() {
        return management.snapshot().paused();
    }

    @ManagedAttribute(
        description = "UTC timestamp of the last management snapshot"
    )
    public String getLastUpdatedAt() {
        return management.snapshot().updatedAt().toString();
    }

    @ManagedOperation(
        description = "Request graceful pause on the current node"
    )
    public void pause() {
        management.requestPause();
    }

    @ManagedOperation(
        description = "Retry one failed job after validating job status"
    )
    @ManagedOperationParameters({
        @ManagedOperationParameter(
            index = 0,
            name = "jobId",
            description = "Non-empty failed job identifier from the job dashboard"
        )
    })
    public void retryFailedJob(String jobId) {
        management.retryFailedJob(jobId);
    }
}
~~~

JMX-independent business port:

~~~java
import java.time.Instant;

public interface WorkerManagement {
    WorkerSnapshot snapshot();
    void requestPause();
    void retryFailedJob(String jobId);
}

public record WorkerSnapshot(
    int queueDepth,
    boolean paused,
    Instant updatedAt
) {}
~~~

The adapter intentionally exposes only the needed management actions. Sensitive methods must validate inputs and check permissions at the appropriate layer; annotations do not grant authorization automatically. Getters should return a fast snapshot without executing expensive queries on every tool poll.

## 5. Ensuring the Spring Exporter Reads Metadata

A plain Spring Framework configuration might look like:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
class JmxExportConfig {
    @Bean
    AnnotationJmxAttributeSource attributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    MBeanExporter mBeanExporter(AnnotationJmxAttributeSource source) {
        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);

        MetadataNamingStrategy naming = new MetadataNamingStrategy();
        naming.setAttributeSource(source);

        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(naming);
        exporter.setAutodetect(true);
        return exporter;
    }
}
~~~

In Spring Boot, JMX auto-configuration may already provide an exporter. Do not create a second exporter before checking the existing configuration, because two exporters can try to register the same \`ObjectName\`.

If descriptions do not show up, verify which assembler exported the bean, whether annotations sit on the target class or a proxy, and whether the client is inspecting the right \`MBeanServer\`.

## 6. ObjectName Should Express Scope

JMX names follow the structure \`domain:key=value[,key=value]\`. Example:

~~~text
com.example.jobs:type=Worker,name=Primary,node=worker-a
com.example.jobs:type=Worker,name=Secondary,node=worker-b
~~~

\`domain\` groups by application, \`type\` states the component kind, \`name\` distinguishes logical instances, and \`node\` indicates scope. Names must be stable and canonically unique when multiple MBeans share one server.

If dynamic data contains commas or wildcards, use \`ObjectName.quote\` on the value portion only, never on the entire \`ObjectName\` string. Do not embed secrets, customer IDs, or sensitive data in MBean names.

A description like "Pause worker" is insufficient if an operation halts the entire cluster. State clearly whether the effect is local to the current node or system-wide in both the ObjectName/description and the runbook.

## 7. Attributes: Name, Unit, Freshness

Attribute documentation should cover:

~~~text
Name: QueueDepth
JMX type: int
Unit: jobs
Readable: true
Writable: false
Scope: current JVM
Freshness: snapshot refreshed every 5 seconds
Normal range: non-negative
Unavailable behavior: see SnapshotAvailable
~~~

If snapshots can go stale, provide \`LastUpdatedAt\` or \`SnapshotAvailable\`. Never use \`0\` to signify "data unavailable" if \`0\` is also a valid value.

For writable attributes, state the valid range and impact:

~~~java
@ManagedAttribute(
    description = "Maximum concurrent jobs on this node; valid range 1..64"
)
public int getConcurrencyLimit() {
    return management.getConcurrencyLimit();
}

@ManagedAttribute(
    description = "Update local concurrency; validate 1..64"
)
public void setConcurrencyLimit(int value) {
    management.setConcurrencyLimit(value);
}
~~~

The setter must enforce validation in code; the description is only an explanation. For risky changes, consider an explicit operation instead of a plain setter.

## 8. Operations: Presenting Safely for Operators

An operation needs:
1. Purpose and when to use it.
2. Target \`ObjectName\`/instance.
3. Approval requirements or operator role.
4. Preconditions (capacity, health, job state).
5. Input format and valid range.
6. Success behavior, side effects, sync/async behavior.
7. Timeout and retry safety.
8. Post-action state verification.
9. Rollback or escalation if irreversible.

Example runbook for \`pause()\`:

~~~text
Purpose: Stop accepting new jobs on current node.
Precondition: Other workers are healthy and have spare capacity.
Risk: Cluster throughput may temporarily decrease.
Invoke: pause() on the selected node MBean.
Expected: Request accepted; active jobs may continue.
Verify: Paused=true and ActiveJobs trends toward zero.
Rollback: resume() after capacity review and approval.
Do not: Pause every node in the cluster simultaneously.
~~~

If an operation only accepts an asynchronous command, \`invoke\` returning without error does not mean the final state has been reached; verify via attributes, notifications, or job status.

## 9. Using JConsole and VisualVM

An operational guide should specify the exact environment and permissions:

1. Connect to the right JVM or approved JMX URL.
2. Locate the \`com.example.jobs\` domain under MBeans.
3. Select the exact MBean instance by \`ObjectName\`.
4. Read \`QueueDepth\`, \`Paused\`, and \`LastUpdatedAt\`.
5. Assess snapshot freshness and the health of sibling nodes.
6. If authorized, open Operations and invoke \`pause()\`.
7. Observe \`Paused\` and related metrics.
8. To undo, invoke \`resume()\` per the runbook.

Never test side-effecting operations in production out of curiosity. Tool UIs vary across JDKs and MBean types, so runbooks should reference \`ObjectName\` and attribute names rather than UI pixel positions.

## 10. Java Example for Reading JMX State

~~~java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class WorkerReadProbe {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example.jobs:type=Worker,name=Primary"
        );

        if (!server.isRegistered(name)) {
            throw new IllegalStateException("Missing MBean: " + name);
        }

        int depth = (Integer) server.getAttribute(name, "QueueDepth");
        boolean paused = (Boolean) server.getAttribute(name, "Paused");

        System.out.printf(
            "queueDepth=%d paused=%s%n", depth, paused
        );
    }
}
~~~

This example fits code running inside the JVM hosting the MBean. A program running in another JVM must not grab its own platform server expecting to find a remote application's MBean; it needs a \`JMXConnector\` and \`MBeanServerConnection\`.

If using a custom server, obtain that server from the Spring container rather than assuming the platform server.

## 11. Example Invoking Operations via MBeanServerConnection

~~~java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public final class WorkerCommand {
    public static void requestPause(
            MBeanServerConnection connection,
            ObjectName name) throws Exception {

        if (!connection.isRegistered(name)) {
            throw new IllegalStateException("Missing target: " + name);
        }

        connection.invoke(
            name, "pause", new Object[0], new String[0]
        );
    }
}
~~~

For an operation with parameters:

~~~java
connection.invoke(
    name,
    "retryFailedJob",
    new Object[] { "job-123" },
    new String[] { "java.lang.String" }
);
~~~

Name and signature must match \`MBeanInfo\`. Never blindly retry a side-effecting operation after a client timeout: the action may already have completed on the server while the response was lost. Check actual state and idempotency before re-invoking.

For remote JMX, avoid hardcoding credentials. Connectors must use proper authentication, TLS, and network isolation.

## 12. Reading Actual Descriptions from MBeanInfo

~~~java
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanInfo info = server.getMBeanInfo(
    new ObjectName("com.example.jobs:type=Worker,name=Primary")
);

System.out.println("MBean: " + info.getDescription());

for (var attr : info.getAttributes()) {
    System.out.printf(
        "Attribute %s (%s): %s%n",
        attr.getName(), attr.getType(), attr.getDescription()
    );
}

for (var op : info.getOperations()) {
    System.out.println(
        "Operation " + op.getName() + ": " + op.getDescription()
    );

    for (var parameter : op.getSignature()) {
        System.out.printf(
            "  %s (%s): %s%n",
            parameter.getName(),
            parameter.getType(),
            parameter.getDescription()
        );
    }
}
~~~

This probe confirms the MBean actually publishes its descriptions. If metadata is missing, inspect the annotation assembler, target/proxy, Standard MBean interface, and the \`MBeanServer\` being read. Do not rely solely on annotations appearing on the class.

## 13. Name Operations Clearly and Avoid Ambiguity

| Ambiguous Name | Clearer Name | What Becomes Clear |
| --- | --- | --- |
| \`reset()\` | \`resetStatistics()\` | Does not delete data |
| \`clear()\` | \`clearExpiredCacheEntries()\` | Removes expired cache entries only |
| \`stop()\` | \`requestGracefulWorkerStop()\` | Graceful operation |
| \`reload()\` | \`reloadReadOnlyConfiguration()\` | Kind of config reloaded |
| \`retry(id)\` | \`retryFailedJob(jobId)\` | Scoped to a failed job |
| \`update(value)\` | \`setConcurrencyLimit(value)\` | Modifies concurrency |

Renaming an operation can break automation; if the API is already deployed, maintain versioning/migration and update runbooks and monitoring scripts.

## 14. Error Behavior and Warnings to Document

| Error | Common Cause | Operator Action |
| --- | --- | --- |
| MBean not found | Wrong ObjectName, wrong server, or exporter not registered | Query registered MBeans and check lifecycle |
| Missing attribute | Metadata/assembler did not expose it | Read \`MBeanInfo\`; do not guess names |
| \`InstanceNotFoundException\` | MBean unregistered after redeploy | Verify target JVM/deployment |
| Validation error | Parameter out of range or invalid state | Check inputs and preconditions |
| Authorization error | Insufficient JMX or business permissions | Follow access-granting procedure |
| Timeout | Unclear whether command executed | Verify state before retrying |
| Dependency unavailable | DB/cache/queue outage | Resolve dependency before continuing |

Descriptions should not promise every exception has the same exact class if a Spring JMX proxy or connector can wrap errors. Runbooks should explain how to inspect nested causes and avoid leaking sensitive information into logs.

## 15. Sample README/Runbook Template for Projects

~~~markdown
# Worker Management - Primary

## Target
ObjectName: com.example.jobs:type=Worker,name=Primary
Scope: Current JVM only.

## Read-only attributes
- QueueDepth: pending jobs, unit=jobs; snapshot every 5 seconds.
- Paused: true when worker does not accept new jobs.
- LastUpdatedAt: UTC timestamp of latest snapshot.

## Operations
### pause()
Purpose: Request graceful pause.
Precondition: Other workers have spare capacity.
Risk: Reduced throughput during drain.
Verify: Paused=true, ActiveJobs decreasing.
Rollback: resume() after operator approval.

### retryFailedJob(jobId)
Purpose: Retry exactly one failed job.
Input: job ID, example job-123.
Precondition: Job is failed, not already running.
Risk: Duplicate side effects if retried without idempotency.
Verify: Job status in monitoring dashboard.
Rollback: Not guaranteed; escalate if duplicate processing.

## Troubleshooting
- Missing MBean: verify ObjectName and correct MBeanServer.
- Stale data: check LastUpdatedAt.
- Invoke timeout: inspect real job state before retry.
~~~

Runbooks should be tied to the release/version of the management API so an outdated description does not mislead operators after an upgrade.

## 16. Testing Metadata and Documentation

An integration test should boot a real Spring context and inspect \`MBeanInfo\`:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Arrays;
import javax.management.MBeanServer;
import javax.management.ObjectName;

void assertDocumentation(MBeanServer server) throws Exception {
    var name = new ObjectName(
        "com.example.jobs:type=Worker,name=Primary"
    );
    assertTrue(server.isRegistered(name));

    var info = server.getMBeanInfo(name);
    assertNotNull(info.getDescription());
    assertFalse(info.getDescription().isBlank());

    var depth = Arrays.stream(info.getAttributes())
        .filter(a -> a.getName().equals("QueueDepth"))
        .findFirst().orElseThrow();

    assertTrue(depth.isReadable());
    assertFalse(depth.isWritable());
    assertTrue(depth.getDescription().contains("Pending"));

    var pause = Arrays.stream(info.getOperations())
        .filter(op -> op.getName().equals("pause"))
        .findFirst().orElseThrow();

    assertTrue(pause.getDescription().contains("graceful"));
}
~~~

The test must ensure the exporter uses annotation metadata. Also assert attribute/operation names, types, and signatures, because having right descriptions with a wrong runtime contract still causes failures. For mutating operations, test invocation only in a test environment with simulated data.

## 17. Operating the API as a Versioned Contract

Changes requiring description and runbook updates:

- Changing \`ObjectName\`/domain causes dashboards to lose targets.
- Changing attribute names or types prevents JMX clients from reading them.
- Changing units from ms to seconds while keeping the old name breaks alerts.
- Changing an operation from synchronous to asynchronous causes runbooks to verify prematurely.
- Changing scope from node-local to cluster-wide increases blast radius.
- Changing exception/error behavior or required permissions.

When making changes, update source code, metadata, tests, runbooks, automation scripts, and release notes together. For breaking changes, use a compatible migration plan instead of silently changing semantics.

## 18. Checklist for Management API Designers

1. \`ObjectName\` has a clear namespace and leaks no sensitive data.
2. MBean description clearly states component and scope.
3. Attribute descriptions specify meaning, unit, freshness, and read/write status.
4. Operation descriptions state action and impact.
5. Parameter descriptions state name, type, format/range, and safe examples.
6. Getters are lightweight, free of side effects, and safe for polling.
7. Critical operations enforce permissions, auditing, preconditions, and rollback.
8. Documentation includes JConsole/Java examples without credentials.
9. Registered MBean's \`MBeanInfo\` reflects actual descriptions.
10. README/runbook is versioned alongside the application release.
11. Monitoring/automation stays compatible with \`ObjectName\` and signatures.
12. Integration tests guard the contract and controlled invocations.

## 19. Key Takeaways

**Descriptions and usage examples are part of the JMX operational contract.** Spring provides \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\`, and parameter metadata to populate descriptions in \`MBeanInfo\`. READMEs and runbooks add preconditions, blast radius, verification, and recovery steps. Always verify against runtime \`MBeanInfo\`, never confuse descriptions with access control, and avoid undocumented dangerous operation examples.
