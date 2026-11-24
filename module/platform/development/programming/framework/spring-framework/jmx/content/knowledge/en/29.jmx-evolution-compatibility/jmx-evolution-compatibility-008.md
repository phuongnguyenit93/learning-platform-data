# Spring Framework JMX — Aligning Configuration Between Spring Framework and Spring Boot

## 1. Context and Goal

Spring Framework provides foundational JMX components such as `MBeanExporter`, `@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation`, `ObjectNamingStrategy`, `MBeanInfoAssembler`, and `MBeanServer`. Spring Boot builds on Spring Framework, adding auto-configuration, properties, and application lifecycle integration. When upgrading or migrating a plain Spring Framework application to Spring Boot, keeping the old JMX configuration while also enabling the new auto-configuration can cause **duplicate MBean registrations, using the wrong MBeanServer, unintended ObjectName changes, or exporting unintended beans**.

This lesson explains how to align both configuration layers so the JMX management API maintains a stable interface, avoids duplicate exporters, and does not break dashboards, scripts, monitoring, or operational permissions.

```text
Spring Framework JMX primitives
   MBeanServer / MBeanExporter
   MetadataMBeanInfoAssembler
   ObjectNamingStrategy / annotations
                  ^
                  |
Spring Boot JMX auto-configuration
   spring.jmx.enabled
   naming domain / unique names / MBeanServer
                  |
                  v
One effective runtime JMX configuration
   -> stable ObjectName
   -> correct server
   -> intended attributes / operations
```

### After this lesson, you will be able to

1. Distinguish manual Spring Framework JMX configuration from Spring Boot automatic JMX configuration.
2. Choose **a single source of export ownership** to prevent two exporters from registering the same MBean.
3. Keep `ObjectName`, domain, and `MBeanServer` stable across migrations/upgrades.
4. Control `spring.jmx.enabled` and related properties according to the actual Spring Boot version.
5. Separate JMX exporting of Spring beans from Actuator endpoint exposure.
6. Write runtime compatibility tests and a safe migration plan.

## 2. What Does Spring Framework JMX Provide?

Spring Framework supports exporting Java beans as MBeans through `org.springframework.jmx.export.MBeanExporter`. A bean can be:

- A Standard MBean or DynamicMBean following the JMX contract.
- A POJO converted into a ModelMBean with an appropriate assembler.
- Annotated with Spring annotations: `@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation`, and related metadata.

Annotation-driven configuration example:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
```

Bean example:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.app:type=WorkerPool,name=primary",
    description = "Manage the primary worker pool"
)
public class WorkerPoolControl {
    private int maxWorkers = 8;

    @ManagedAttribute
    public synchronized int getMaxWorkers() {
        return maxWorkers;
    }

    @ManagedAttribute
    public synchronized void setMaxWorkers(int requested) {
        if (requested < 1 || requested > 64) {
            throw new IllegalArgumentException("Expected 1..64");
        }
        maxWorkers = requested;
    }

    @ManagedOperation(description = "Pause new jobs")
    public void pauseIntake() {
        // Perform administrative action.
    }
}
```

`@EnableMBeanExport` enables infrastructure that exports appropriately annotated beans. If the application also declares an explicit `MBeanExporter`, check whether an additional exporter comes from the annotation-driven infrastructure. Do not enable both simply because each appears in a different module.

## 3. What Does Spring Boot Add?

Spring Boot includes auto-configuration to integrate JMX when enabled by configuration. A common property is:

```properties
spring.jmx.enabled=true
```

In modern Spring Boot versions, JMX exporting is typically not enabled by default for all applications; consult the reference documentation of the **exact Boot version running** to determine defaults and auto-configuration conditions. Do not infer a default property on a newer version from a project running an older version.

Spring Boot can create or locate an `MBeanServer`, configure an exporter, and provide naming conventions. Commonly involved options:

```properties
spring.jmx.enabled=true
spring.jmx.default-domain=com.example.app
spring.jmx.unique-names=true
```

`default-domain` adjusts the default domain for generated names, while `unique-names` helps reduce ObjectName collisions when multiple contexts or beans exist. How these values are applied depends on the Boot version and MBean type. Explicit names from `@ManagedResource(objectName=...)` may not be altered the same way generated names are; verify against the actual registry.

**Key point:** Spring Boot does not replace Spring Framework's JMX API. It decides when to create default configuration and wiring; underneath remain `MBeanServer`, exporter, assembler, and naming strategy. When customizing, know which auto-configuration is active to avoid accidentally creating a second export path.

## 4. Three Configuration Models to Distinguish

### 4.1. Plain Spring Framework, Explicit Configuration

```java
@Configuration
@EnableMBeanExport
public class LegacyJmxConfiguration {
}
```

Or create a single `MBeanExporter` and configure `setBeans`, `setServer`, `setAssembler`, `setNamingStrategy`.

Characteristics: developers control the exporter and lifecycle directly; changing the server or names requires adjusting manual configuration.

### 4.2. Spring Boot Auto-Configuration

```properties
spring.jmx.enabled=true
```

Characteristics: Boot provides infrastructure conditionally, reducing manual configuration. Rely on properties and customizers/bean overrides supported in the active version rather than declaring a second identical exporter.

### 4.3. Combining Boot and a Custom Exporter

This may be necessary when a special group of MBeans must be exported with a custom naming policy. However, you must **isolate bean scope**, ObjectNames, and ownership between exporters. If the same Spring bean is exported via both the annotation-driven route and an explicit route, you risk `InstanceAlreadyExistsException` or replace/ignore policies masking conflicts.

## 5. Biggest Risk: Duplicate Exporters

Suppose a legacy application uses:

```java
@Configuration
@EnableMBeanExport
class OldJmxConfig {
}
```

After moving to Spring Boot, application properties also enable:

```properties
spring.jmx.enabled=true
```

If both mechanisms create an exporter and discover the same bean, both may attempt to register:

```text
com.example.app:type=WorkerPool,name=primary
```

Common consequences:

- Startup fails with `InstanceAlreadyExistsException`.
- Exporter A registers successfully while exporter B is rejected.
- An ignore/replace registration policy lets the application start, but MBean ownership becomes unpredictable.
- On context stop or restart, an MBean may be unregistered by the wrong owner exporter.

Do not treat `IGNORE_EXISTING` or `REPLACE_EXISTING` as a default solution. They can mask architectural mistakes and produce hard-to-control lifecycle behavior.

**Rule:** pick one primary exporter for application MBeans. If multiple exporters are required, explicitly define the bean list, MBeanServer, and ObjectNames for each exporter; test that they do not overlap.

## 6. Choosing a Single Source of Truth During Migration

A safe migration plan:

1. List existing MBeans from a server running the old version.
2. Record ObjectNames, attributes, operations, notification types, and authorization behavior.
3. Determine whether the old setup uses `@EnableMBeanExport`, explicit `MBeanExporter`, or both.
4. Decide whether to use Boot auto-configuration or continue with a manual exporter.
5. If switching to Boot, remove or isolate the old export configuration to avoid duplicates.
6. Preserve critical explicit names, especially ObjectNames already used by monitoring scripts.
7. Run integration tests comparing metadata/registry and testing operations without side effects.
8. Roll out only after confirming the server registry is accurate with no registration collisions.

Do not remove management annotations simply because `spring.jmx.enabled` is turned on; beans still need the proper JMX contract to expose the right members.

## 7. ObjectName and Default Domain

An ObjectName consists of a domain and key properties:

```text
com.example.app:type=WorkerPool,name=primary
```

During migration, replacing `com.example.app` with a new default domain can break clients:

```java
ObjectName expected = new ObjectName(
    "com.example.app:type=WorkerPool,name=primary"
);
```

If the name changes, scripts calling `getAttribute` or `invoke` will hit `InstanceNotFoundException` even though the MBean may be registered under another name.

Prefer keeping ObjectNames stable as a **public management API**. Do not automatically append random IDs or version suffixes to ObjectNames that clients already depend on. For multiple instances in the same MBeanServer, use stable logical keys such as `name`, `service`, `context`, or `tenant` when genuinely needed.

### Comparing Registered Names

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName pattern = new ObjectName("com.example.app:*");

for (ObjectName name : server.queryNames(pattern, null)) {
    System.out.println(name.getCanonicalName());
}
```

If the exporter uses an `MBeanServer` other than the platform server, query that exact server. Identical ObjectNames on two different MBeanServers are not the same registration.

## 8. The Right MBeanServer Matters More Than Spring Bean Names

In Spring Framework, you can configure:

```java
@Bean
public MBeanExporter exporter(
        MBeanServer targetServer,
        WorkerPoolControl control) {
    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(targetServer);
    exporter.setBeans(Map.of(
        "com.example.app:type=WorkerPool,name=primary", control
    ));
    return exporter;
}
```

If a host/container already supplies an MBeanServer, inject the exact reference. If Boot picks a different server, MBeans may appear in a registry that JConsole or the monitoring connector does not observe.

With annotation-driven configuration referencing a server bean:

```java
@Configuration
@EnableMBeanExport(server = "applicationMBeanServer")
public class JmxConfig {
    @Bean("applicationMBeanServer")
    MBeanServer applicationMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }
}
```

The example above only illustrates binding an exporter to a named MBeanServer bean. In a Boot application with auto-config active, pick one configuration to own the exporter so you do not accidentally create two exporter beans.

## 9. Spring Boot Actuator JMX Is a Separate Layer

Spring Boot Actuator can expose management endpoints over JMX when the required dependency and configuration are present. This is **different from** exporting a business bean annotated with `@ManagedResource`. Actuator-related properties typically look like:

```properties
management.endpoints.jmx.exposure.include=health,info
management.endpoints.jmx.domain=org.springframework.boot
```

Check exact property names and defaults for your Spring Boot version. `management.endpoints.jmx.exposure.*` controls which Actuator endpoints are exposed via JMX; it does not replace `@ManagedOperation` on a business bean. The domain for Actuator can also differ from the domain for application MBeans.

Do not assume turning off `spring.jmx.enabled` only disables Actuator without affecting Spring MBeans, or that enabling Actuator HTTP endpoints automatically enables JMX management. Verify these configuration layers separately.

## 10. Separating Annotation and Auto-Configuration Responsibilities

Spring annotations describe **which parts of a bean can be managed**:

```java
@ManagedResource(objectName = "com.example.app:type=Cache,name=products")
class ProductCacheControl {
    @ManagedAttribute
    public int getEntryCount() { return 0; }

    @ManagedOperation
    public void clearCache() { /* ... */ }
}
```

Spring Boot properties control **which infrastructure is initialized and default naming behavior**.

Therefore:

- Annotations do not guarantee an exporter exists.
- Boot auto-config does not turn every public method of a bean into a management operation.
- Metadata without registration still produces no MBean.
- Registration with the wrong assembler can miss attributes/operations.
- Having the right members with a changed ObjectName still breaks old clients.

## 11. Integration Testing via Runtime MBeanInfo

Migration verification should inspect actual metadata:

```java
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public void verifyJmxContract(MBeanServer server) throws Exception {
    ObjectName name = new ObjectName(
        "com.example.app:type=WorkerPool,name=primary"
    );

    if (!server.isRegistered(name)) {
        throw new AssertionError("Expected MBean missing: " + name);
    }

    MBeanInfo info = server.getMBeanInfo(name);

    boolean hasMaxWorkers = java.util.Arrays.stream(
        info.getAttributes()
    ).anyMatch(a -> a.getName().equals("MaxWorkers"));

    boolean hasPause = java.util.Arrays.stream(
        info.getOperations()
    ).anyMatch(op -> op.getName().equals("pauseIntake"));

    if (!hasMaxWorkers || !hasPause) {
        throw new AssertionError("JMX contract changed unexpectedly");
    }
}
```

In integration tests, you can test both a plain Spring context and a Spring Boot context with the same MBean fixture. Do not just assert that the application context starts cleanly; verify the registry, `MBeanInfo`, member names, and member types. If operations have side effects, test using a fake service/test MBean or isolated state fixture.

## 12. Comparing Configuration Before and After Upgrade

Before changing Spring or Boot versions, save a contract snapshot (containing no secrets):

```text
ObjectName: com.example.app:type=WorkerPool,name=primary
Attributes:
  MaxWorkers type=int readable=true writable=true
Operations:
  pauseIntake()
Notifications:
  jmx.attribute.change
```

On the new version, read `MBeanInfo` again and compare:

1. Do the old ObjectNames still exist?
2. Are domain and key properties unchanged?
3. Do getters/setters produce the expected read/write flags?
4. Have operation signatures changed due to primitive/wrapper types or overloads?
5. Are notification types still exposed?
6. Does the JMX connector retain read/write/invoke authorization policies?
7. Did auto-config/Actuator introduce unexpected extra MBeans?
8. Are there duplicate-registration warnings or errors?

Intentional differences must have a migration plan for dashboards/scripts. Unintentional differences should be resolved before rollout.

## 13. Profiles and Deployment Environments

Not every environment needs remote JMX. For example:

```properties
# application-dev.properties
spring.jmx.enabled=true
```

```properties
# application-prod.properties
spring.jmx.enabled=true
```

Enable it only when needed and when the remote connector is secured. `spring.jmx.enabled` does not automatically configure authentication/TLS for a remote JMX endpoint. These are two distinct concerns: bean export and remote transport security.

For container/Kubernetes environments:

- Prefer stable logical ObjectNames, independent of pod UIDs unless needed.
- Use monitoring target labels to distinguish JVM replicas.
- Never expose an unsecured remote JMX port publicly.
- Verify RMI registry/server ports and advertised hostnames if using remote RMI.
- Keep JMX export configuration separate from secrets/connector credentials.

## 14. Managing Multiple ApplicationContexts

An application may have parent/child contexts, test contexts, or multiple modules initializing exporters. Contexts sharing an MBeanServer can collide:

```text
Context A -> com.example.app:type=Cache,name=primary
Context B -> com.example.app:type=Cache,name=primary
```

To avoid this:

- Clearly define which context owns registration.
- Separate Beans/ObjectNames per context if they truly represent two distinct resources.
- If it is one shared resource, only one exporter registers it.
- Do not use ignore/replace registration policies to mask flawed design.
- Verify unregistration when one context stops: MBeans of the remaining context must stay registered.

In Spring Boot tests, multiple application contexts may coexist under the test runner. When JMX is enabled, test fixtures may need separate domains/unique naming to avoid collisions, though random naming should not be used in production if clients depend on stable names.

## 15. Versioning and Compatibility Policy

Spring Framework and Spring Boot must use **managed compatible versions**. In Boot projects, usually let Boot's dependency management govern Spring Framework module versions rather than overriding Framework versions arbitrarily.

When upgrading:

1. Read the release notes and migration guide of the target Boot version.
2. Inspect the dependency tree to check the actual Spring Framework version.
3. Check JMX properties that were renamed, changed defaults, or deprecated.
4. Check conditional auto-configuration and custom bean overrides.
5. Run regression tests for ObjectName/MBeanInfo/registration.
6. Roll out by environment while monitoring metrics and connector errors.

Do not rely on a JMX configuration copied from another Boot project without checking the version. A valid property can have different semantics or defaults across release lines.

## 16. Common Pitfalls

| Symptom | Possible cause | Investigation path |
|---|---|---|
| `InstanceAlreadyExistsException` at startup | Two exporters or contexts register the same ObjectName | Look for overlapping annotation-driven and Boot auto-config setups |
| Application runs but MBean is missing | JMX disabled, wrong server, or missing annotation/assembler | Check exporter, server, `queryNames` |
| ObjectName changed after migration | Default domain/naming strategy/unique names changed | Compare registry before/after |
| Only some operations appear | Metadata assembler/Standard MBean contract differs | Inspect `MBeanInfo` |
| Actuator MBeans appear unexpectedly | Actuator JMX exposure is enabled | Check `management.endpoints.jmx.exposure.*` |
| MBean disappears when one context stops | Overlapping registration ownership or lifecycle conflict | Review exporter ownership and unregister |
| JConsole connects but misses custom MBean | Exported to a different server than connector exposes | Compare MBeanServer reference/endpoint |
| Tests pass individually but fail in suite | Shared context/JMX registry with colliding names | Isolate contexts or names in tests |
| Remote JMX fails auth/TLS | Connector security is separate from bean export | Inspect server-side connector properties |

## 17. Practice Exercises

### Exercise 1: Two Export Mechanisms

An application has both `@EnableMBeanExport` and `spring.jmx.enabled=true`. Explain the risk if both export the same bean and propose choosing a single registration owner.

### Exercise 2: Changing Domain

Before migration: `com.example.app:type=WorkerPool,name=primary`. After migration: `org.springframework:type=WorkerPool,name=primary`. Analyze the impact on scripts using a fixed `ObjectName` and how to preserve compatibility.

### Exercise 3: Runtime Verification

Write a test using `MBeanServer.getMBeanInfo` verifying that the `WorkerPool` MBean has a writable `MaxWorkers` attribute and exposes `pauseIntake()`.

### Exercise 4: Actuator vs Application MBeans

Explain why `management.endpoints.jmx.exposure.include=health` does not replace `@ManagedResource` for exporting a business POJO as a JMX MBean.

### Exercise 5: Parent and Child Contexts

Two contexts share the platform MBeanServer and register the same ObjectName. Propose an ownership/namespace strategy and test cleanup when one context stops.

### Exercise 6: Production Security

Why is `spring.jmx.enabled=true` insufficient to expose remote JMX securely? Answer: the property governs exporting, whereas remote connectors require separate authentication, authorization, TLS, and network controls.

## 18. Migration Checklist

- Identify the Spring Boot/Framework versions and effective auto-configuration.
- Pick one primary export mechanism; avoid duplicate exporters.
- Keep ObjectNames and domains stable for existing clients.
- Identify the exact MBeanServer exposed by the JMX connector.
- Check assemblers, annotations, and MBean interfaces.
- Distinguish Actuator JMX endpoints from application MBeans.
- Verify unique naming when multiple contexts/instances exist.
- Regression-test attributes/operations/notifications and permissions.
- Secure remote connectors with auth/TLS/network isolation.
- Roll out cleanly while monitoring registration logs and JMX health.

## 19. Summary

Aligning JMX configuration between Spring Framework and Spring Boot is about establishing a **single source of truth for MBean exporting**, keeping the management API stable, and preventing auto-configuration from duplicating manual configuration. Spring Framework supplies the primitives and annotations; Boot supplies conditional wiring and properties. When upgrading or migrating, verify the exporter, MBeanServer, ObjectName, metadata, and Actuator exposure for your exact version. Runtime tests against `MBeanInfo` and the registry help ensure administration clients are not broken by unintended configuration changes.