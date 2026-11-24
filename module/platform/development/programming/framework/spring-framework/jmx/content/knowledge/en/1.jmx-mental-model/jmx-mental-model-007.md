# Exposing management capabilities outside the application without making domain code depend on JMX

## 1. The problem to solve

A Spring application may need to let the operations team view the number of running tasks, synchronization status, threshold limits, or explicitly request a configuration reload. These needs belong to the **management plane**, which differs from normal business flows. If you embed \`javax.management.*\` or \`jakarta.management.*\` into domain classes, business rules become coupled to a specific management protocol, making them harder to test and harder to reuse via HTTP, CLI, or schedulers.

The goal is to **expose an exact, controlled management surface externally**, while the business core knows only its own concepts and operations. Spring Framework supports exporting a bean via JMX using \`MBeanExporter\` and annotations such as \`@ManagedResource\`, \`@ManagedAttribute\`, and \`@ManagedOperation\`. Those are tools of the adapter layer, not a mandatory contract of the domain.

## 2. Mental model: two ports, one core

\`\`\`text
JConsole / VisualVM / JMX client
             |
         JMX MBean
             |
 Spring management adapter
 (@ManagedResource, @ManagedOperation)
             |
       Application port
             |
       Application service
             |
        Domain model
\`\`\`

- **Domain model** holds business invariants, decides valid states, and knows nothing about JMX.
- **Application service/port** provides state queries and management commands in the application's language, such as \`getSnapshot()\` or \`requestRefresh()\`.
- **Management adapter** translates the port into JMX attributes and operations, sets the ObjectName and descriptions, and handles authentication/permission checks at the operational boundary.
- **JMX agent/connector** handles the protocol and accessibility from operational tools. It has its own lifecycle and security policy.

The JMX surface should be stable, small, and observation-oriented. A management operation must have clear semantics, preconditions, an audit trail, and error handling.

## 3. Designing a protocol-independent port

Suppose the application orchestrates a data synchronization job. The application layer defines a contract that carries no JMX types:

\`\`\`java
public record SyncSnapshot(
    String state,
    long completedCount,
    java.time.Instant lastSuccessAt
) {}

public interface SyncManagement {
    SyncSnapshot snapshot();
    void requestRefresh();
}
\`\`\`

\`SyncSnapshot\` is a read-only value; do not directly return mutable entities, repositories, or internal structures that could be mutated unintentionally. \`requestRefresh()\` expresses a business intent without containing MBean or \`ObjectName\` concepts.

The implementing service can be invoked from a scheduler, an HTTP API, or a JMX adapter:

\`\`\`java
@Service
public class SyncApplicationService implements SyncManagement {
    private final java.util.concurrent.atomic.AtomicLong completed =
        new java.util.concurrent.atomic.AtomicLong();
    private volatile java.time.Instant lastSuccessAt;
    private final java.util.concurrent.atomic.AtomicBoolean running =
        new java.util.concurrent.atomic.AtomicBoolean(false);

    @Override
    public SyncSnapshot snapshot() {
        return new SyncSnapshot(
            running.get() ? "RUNNING" : "IDLE",
            completed.get(),
            lastSuccessAt
        );
    }

    @Override
    public void requestRefresh() {
        if (!running.compareAndSet(false, true)) {
            throw new IllegalStateException("Refresh already running");
        }
        try {
            // In a real application: dispatch the command to a managed queue or executor.
            // This abbreviated example only illustrates state and concurrency conditions.
            completed.incrementAndGet();
            lastSuccessAt = java.time.Instant.now();
        } finally {
            running.set(false);
        }
    }
}
\`\`\`

The example above only simulates an instantaneous task. For long-running work, submit the command to an application executor/queue and return quickly; do not let a JMX call block a control thread for minutes. Business rules must clearly specify duplicate commands, retries, timeouts, and idempotency.

## 4. Spring JMX adapter: wrapping only the contract

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.app:type=Sync,name=Primary",
    description = "Operational view of the sync service"
)
public class SyncJmxAdapter {
    private final SyncManagement management;

    public SyncJmxAdapter(SyncManagement management) {
        this.management = management;
    }

    @ManagedAttribute(description = "Current sync state")
    public String getState() {
        return management.snapshot().state();
    }

    @ManagedAttribute(description = "Number of completed sync cycles")
    public long getCompletedCount() {
        return management.snapshot().completedCount();
    }

    @ManagedAttribute(description = "Last successful completion in ISO-8601")
    public String getLastSuccessAt() {
        var last = management.snapshot().lastSuccessAt();
        return last == null ? "" : last.toString();
    }

    @ManagedOperation(description = "Request a synchronization refresh")
    public void refresh() {
        management.requestRefresh();
    }
}
\`\`\`

This adapter contains JMX metadata, while the interface and service do not import JMX libraries. The getters return simple types because JMX clients work smoothly with \`String\`, numbers, and standard JMX types; avoid exposing complex records or proxy beans to the interface without explicit mapping.

To make Spring read the management annotations and register the MBean:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
class JmxConfiguration {
    @Bean
    AnnotationJmxAttributeSource jmxAttributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    MBeanExporter mbeanExporter(
            AnnotationJmxAttributeSource source) {
        var assembler = new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);

        var naming = new MetadataNamingStrategy();
        naming.setAttributeSource(source);

        var exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(naming);
        exporter.setAutodetect(true);
        return exporter;
    }
}
\`\`\`

When using Spring Boot, MBean export configuration may be set up automatically depending on the version and application properties (e.g., \`spring.jmx.enabled=true\`). Do not declare an extra manual exporter if Boot already creates an appropriate one; choose a single clear configuration source to avoid duplicate registration.

## 5. Rules for designing the management surface

| Area | Do | Avoid |
| --- | --- | --- |
| Attributes | State, counters, timestamps, filtered thresholds | Mutable entities, secrets, customer data |
| Commands | \`refresh()\`, \`pause()\`, \`resume()\` with clear preconditions | \`executeSql(String)\`, \`invokeAny(String)\` |
| MBean name | Stable domain and key pairs, e.g., \`com.example.app:type=Sync,name=Primary\` | Random names on every startup |
| Error reporting | Useful operational messages without exposing sensitive info | Stack traces/credentials in exposed output |
| Concurrency | Commands safe on repeated calls, consistent snapshot state | Running long tasks directly on the JMX thread |
| Dependencies | Adapter depends on \`SyncManagement\` | Domain service depends on \`MBeanServer\` |

**Consistency note:** If snapshot fields must reflect the same point in time, construct the snapshot under the same synchronization mechanism or store an immutable snapshot in an \`AtomicReference\`. Multiple separate \`volatile\` fields do not automatically provide an atomic read transaction.

**Boundary note:** JMX is an operational control channel, not a place to expose the entire business API. High-impact commands such as deleting data, rotating keys, or shutting down the system require separate controls; do not add them merely because annotations make exporting operations easy.

## 6. Configuration and operations

There are two separate steps:

1. **Register the MBean inside the JVM** via the Spring exporter. At that point, the MBean exists in the platform \`MBeanServer\`; this is an in-JVM capability.
2. **Allow external clients to connect** via a JMX connector or an appropriate monitoring solution. Networking, authentication, TLS, firewalls, and access permissions are determined by the deployment environment.

Do not equate \`spring.jmx.enabled\` with having opened a secure remote JMX port. In particular, avoid configurations that disable authentication/SSL in production environments. If you only need metrics/health, a dedicated observability endpoint (such as Micrometer/Actuator in Spring Boot) may be more suitable than exposing remote MBean operations.

Assign object names in \`domain:key=value\` form, for example:

\`\`\`text
com.example.app:type=Sync,name=Primary
\`\`\`

If there are multiple instances on the same \`MBeanServer\`, add a stable distinguishing property to avoid \`InstanceAlreadyExistsException\`. Do not accidentally overwrite another MBean using replacement registration policies.

## 7. Testing the boundary

The goal of testing is not to prove that JConsole renders nicely, but to prove that the adapter delegates calls accurately and that the domain does not depend on JMX.

\`\`\`java
class SyncJmxAdapterTest {
    @org.junit.jupiter.api.Test
    void exposesSnapshotAndDelegatesRefresh() {
        class Fake implements SyncManagement {
            boolean requested;
            public SyncSnapshot snapshot() {
                return new SyncSnapshot("IDLE", 7, null);
            }
            public void requestRefresh() { requested = true; }
        }

        var fake = new Fake();
        var adapter = new SyncJmxAdapter(fake);

        org.junit.jupiter.api.Assertions.assertEquals("IDLE", adapter.getState());
        org.junit.jupiter.api.Assertions.assertEquals(7, adapter.getCompletedCount());
        org.junit.jupiter.api.Assertions.assertEquals("", adapter.getLastSuccessAt());
        adapter.refresh();
        org.junit.jupiter.api.Assertions.assertTrue(fake.requested);
    }
}
\`\`\`

Separate integration tests can start the Spring \`ApplicationContext\`, obtain the \`MBeanServer\`, verify \`isRegistered(ObjectName)\`, read attributes, and invoke operations through the JMX interface. Clean up the context and registrations after each test so state does not leak between test cases.

Architecture tests should block reverse dependencies from \`domain\` and \`application\` packages to \`org.springframework.jmx\`, \`javax.management\`/ \`jakarta.management\`, or \`SyncJmxAdapter\`. This can be checked with ArchUnit or module-separation build rules.

## 8. Usage scenarios

**Observation:** An SRE asks "is it running or idle?"; the adapter simply reads the snapshot and exposes the \`State\` attribute. No service changes are needed for JConsole's sake.

**Control:** An operator invokes \`refresh()\`; the adapter delegates to the port. The application service checks running state, enforces authorization per the deployment architecture, and decides whether to accept or reject the command. Do not put business logic inside the annotated method.

**Changing protocols:** Later, if you add an HTTP admin endpoint, CLI, or actuator endpoint, the new adapters call the same \`SyncManagement\`; you do not rewrite the domain model.

**Disabling JMX:** Omit registering the exporter or disable JMX configuration; business flows still run as before. This is an important test of separation.

## 9. Common mistakes and fixes

- **Putting \`@ManagedResource\` directly on an aggregate/domain service:** Move the annotation to an adapter and use an application interface.
- **Exporting all beans:** Select only necessary management beans, clearly distinguishing read-only queries from state-changing commands.
- **Returning complex DTOs as an attribute:** Map to simple values or intentionally define an Open MBean mapping.
- **Running long work inside \`@ManagedOperation\`:** Enqueue it, return quickly, and expose a separate status-tracking attribute.
- **Using JMX as the business authorization mechanism:** Enforce permissions at the operational channel and check conditions/authorization in the corresponding application layer.
- **Assuming MBeans are always reachable over the network:** Verify connector configuration and security policies separately.

## 10. Key takeaways

Core mental model: **JMX is a management adapter placed at the edge of the application**. The application port describes what can be observed and what commands are allowed; the domain enforces business rules; Spring JMX turns that contract into an MBean for operators. When you can remove JMX, swap protocols, or change monitoring tools without modifying the domain, the architectural boundary is doing its job.
