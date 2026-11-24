# Creating a Read–Write Attribute with @ManagedAttribute in Spring Framework JMX

## 1. Practice Objectives

In this lesson, you will create a **read–write JMX attribute** using \`@ManagedAttribute\` in Spring Framework. The main example is the \`MaxConcurrentJobs\` property, which represents the limit on the number of jobs processed concurrently in a worker pool.

By the end of this lesson, you will be able to:

- Use \`@ManagedResource\` to mark a Spring bean as a JMX management resource.
- Annotate both getter and setter with \`@ManagedAttribute\` so JMX exposes a readable/writable attribute.
- Understand the rule that maps \`getMaxConcurrentJobs()\` and \`setMaxConcurrentJobs(int)\` to the same \`MaxConcurrentJobs\` attribute.
- Configure an exporter or annotation-driven export mechanism in Spring without creating multiple MBean registration owners.
- Use \`MBeanServer.getMBeanInfo()\`, \`getAttribute()\`, and \`setAttribute()\` to verify existence, data type, read/write permissions, and actual values.
- Handle validation, state synchronization, errors when a setter rejects a value, and the effects of runtime configuration changes.
- Distinguish JMX write permission from remote connector authentication/authorization.
- Create an integration test ensuring that the writable attribute adheres to its contract while unwanted operations are not exposed.

## 2. Real-World Problem

A queue-processing application has a limit on how many jobs can run concurrently. Initially configured in the application:

~~~text
maxConcurrentJobs = 8
~~~

When load changes, an operator wants to:

1. Read the current value via JConsole.
2. Adjust the limit to 12 without restarting the application.
3. Receive a clear error if the value is invalid, such as 0 or 100000.
4. Be confident the system is using the new limit, rather than just changing a display variable that has no effect on the worker pool.

JMX is suitable for a small set of dynamic administrative settings, but requires a clear **management contract** and **permission boundaries**. You should not turn every application property into a writable attribute.

Model:

~~~text
JConsole / JMX client
        |
        v
MBeanServer
        |
        v
Spring JMX management bean
    getMaxConcurrentJobs()
    setMaxConcurrentJobs(int)
        |
        v
WorkerConcurrencySettings (Spring bean)
        |
        v
Worker pool / scheduler
~~~

The management adapter is the administrative window; the business component remains the single owner of the applied configuration.

## 3. Environment Setup

The examples target a Java application using Spring Framework JMX and Java 17+; they can be adapted to suitable Spring versions after verifying API/version compatibility.

Required components:

- A Java JDK with the \`java.management\` module and JConsole or a suitable JMX client tool.
- Spring Context and JMX export support.
- An \`MBeanServer\`, typically the platform MBeanServer.
- A Spring bean representing the worker settings.
- A Spring management bean with JMX annotations.
- An annotation-aware export mechanism, via appropriate Spring configuration.

If using Spring Boot, check the Boot version and exporter auto-configuration before adding a manual exporter. Having \`@ManagedResource\` on a class does not by itself guarantee the bean appears in the \`MBeanServer\`.

To test **local** JMX, you do not need to open a remote JMX connector. Query the same MBeanServer inside the JVM or use a tool authorized for local connections. Do not set \`authenticate=false\` and \`ssl=false\` on a remote connector just for testing convenience.

## 4. Understanding JMX Read–Write Attributes

In JMX, an attribute has key metadata properties:

| Metadata | Meaning |
|---|---|
| Name | Attribute name used by the client |
| Type | Exposed Java/JMX type |
| Readable | Whether the client can call \`getAttribute\` |
| Writable | Whether the client can call \`setAttribute\` |
| Is | Whether it is a boolean getter following the \`isXxx\` convention |
| Description | Description for the operator |

In Spring annotation-driven JMX, for example:

~~~java
@ManagedAttribute
public int getMaxConcurrentJobs() {
    return 8;
}

@ManagedAttribute
public void setMaxConcurrentJobs(int value) {
    // Apply the new value.
}
~~~

Both methods correspond to a single JMX attribute named \`MaxConcurrentJobs\` when the assembler recognizes them according to JavaBean property conventions.

Client reading:

~~~java
Object value = server.getAttribute(name, "MaxConcurrentJobs");
~~~

Client writing:

~~~java
server.setAttribute(name, new Attribute("MaxConcurrentJobs", 12));
~~~

**Note:** A JMX attribute setter can be invoked by an authorized administrative tool. The setter must not merely mutate a field for JConsole to display; it should have clear semantics and take effect on the actual component.

## 5. Step 1 — Create the Settings Class Managing State

First, separate business state from the JMX adapter:

~~~java
package com.example.shop.jobs;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Component;

@Component
public class WorkerConcurrencySettings {

    public static final int MIN_CONCURRENCY = 1;
    public static final int MAX_CONCURRENCY = 64;

    private final AtomicInteger maxConcurrentJobs =
            new AtomicInteger(8);

    public int currentLimit() {
        return maxConcurrentJobs.get();
    }

    public void updateLimit(int newLimit) {
        if (newLimit < MIN_CONCURRENCY
                || newLimit > MAX_CONCURRENCY) {
            throw new IllegalArgumentException(
                    "MaxConcurrentJobs must be between 1 and 64");
        }

        maxConcurrentJobs.set(newLimit);
    }
}
~~~

This design demonstrates:

- A single source of truth for \`maxConcurrentJobs\`.
- A default value of 8.
- A valid range of 1..64.
- \`AtomicInteger\` providing atomic reads/writes and visibility across threads.
- Validation performed inside the component that owns the configuration, not solely in the JMX adapter.

**Limitation of the example:** \`AtomicInteger.set()\` only updates an in-memory value. The worker pool only truly changes concurrency if the scheduler/worker logic reads this value or another adapter applies the change to the actual orchestration mechanism. If using \`ThreadPoolExecutor\`, limits like \`corePoolSize\` and \`maximumPoolSize\` must be updated via the proper API and in a valid order; do not change those two numbers arbitrarily, as doing so can throw \`IllegalArgumentException\` or cause unexpected behavior.

For this lesson, we model the worker pool via a settings component to focus on the JMX read/write contract.

## 6. Step 2 — Create the Spring Management Bean

The management bean uses \`@ManagedResource\` and \`@ManagedAttribute\`:

~~~java
package com.example.shop.jobs;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
        objectName = "com.example.shop.jobs:type=WorkerSettings,name=primary",
        description = "Runtime worker concurrency settings")
public class WorkerSettingsManagement {

    private final WorkerConcurrencySettings settings;

    public WorkerSettingsManagement(
            WorkerConcurrencySettings settings) {
        this.settings = settings;
    }

    @ManagedAttribute(
            description = "Current maximum concurrent jobs")
    public int getMaxConcurrentJobs() {
        return settings.currentLimit();
    }

    @ManagedAttribute(
            description = "Maximum concurrent jobs, allowed range 1..64")
    public void setMaxConcurrentJobs(int maxConcurrentJobs) {
        settings.updateLimit(maxConcurrentJobs);
    }
}
~~~

Here:

1. \`@Component\`: creates a Spring bean via component scanning.
2. \`@ManagedResource\`: provides resource metadata and the desired ObjectName.
3. \`getMaxConcurrentJobs()\`: JMX getter, reading the current state.
4. \`setMaxConcurrentJobs(int)\`: JMX setter, calling the same settings service to write.
5. \`@ManagedAttribute\` on both methods: declares both read and write metadata for the annotation assembler.
6. Domain \`com.example.shop.jobs\`: custom JMX namespace for the application.
7. \`type=WorkerSettings,name=primary\`: MBean identity within an MBeanServer.

Do not add \`@ManagedOperation\` to a setter just to write an attribute. A setter is a **write attribute accessor**, not necessarily a separate JMX operation. Use semantically accurate exposure.

## 7. Step 3 — Ensure Component Scanning

If using Spring Boot:

~~~java
package com.example.shop;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.SpringApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

With package \`com.example.shop\` at the root, classes in \`com.example.shop.jobs.*\` are normally within the default component scanning scope.

If the application sets \`@SpringBootApplication(scanBasePackages=...)\`, ensure the management and settings packages are included.

With plain Spring Framework, you can use:

~~~java
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;

@Configuration
@ComponentScan("com.example.shop.jobs")
public class ApplicationConfiguration {
}
~~~

If the bean is not yet in the ApplicationContext, the exporter cannot autodetect it. That is a Spring bean registration issue, distinct from JMX registration.

## 8. Step 4 — Configure an Annotation-Aware MBeanExporter

An illustrative configuration that does not depend on Spring Boot auto-configuration:

~~~java
package com.example.shop.jobs;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class JmxConfiguration {

    @Bean
    AnnotationJmxAttributeSource jmxAttributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    MetadataMBeanInfoAssembler jmxAssembler(
            AnnotationJmxAttributeSource source) {
        MetadataMBeanInfoAssembler assembler =
                new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);
        return assembler;
    }

    @Bean
    MetadataNamingStrategy jmxNamingStrategy(
            AnnotationJmxAttributeSource source) {
        MetadataNamingStrategy naming =
                new MetadataNamingStrategy();
        naming.setAttributeSource(source);
        return naming;
    }

    @Bean
    MBeanExporter jmxExporter(
            MetadataMBeanInfoAssembler assembler,
            MetadataNamingStrategy naming) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(naming);
        exporter.setAutodetectModeName("AUTODETECT_ASSEMBLER");
        return exporter;
    }
}
~~~

Roles:

- \`AnnotationJmxAttributeSource\` reads \`@ManagedResource\` and \`@ManagedAttribute\`.
- \`MetadataMBeanInfoAssembler\` builds JMX metadata from annotation data.
- \`MetadataNamingStrategy\` uses managed resource metadata to construct the ObjectName.
- \`AUTODETECT_ASSEMBLER\` lets the exporter select beans matching the assembler criteria.
- \`MBeanExporter\` performs registration into the MBeanServer.

**Do not add this exact configuration when the application already has an exporter from Spring Boot or another configuration.** Two exporters registering \`com.example.shop.jobs:type=WorkerSettings,name=primary\` can cause a conflict. Identify the existing owner before creating a new exporter.

Another option is using \`AnnotationMBeanExporter\` or \`@EnableMBeanExport\` according to your Spring configuration/version. The goal is **one** clear annotation-driven export path.

## 9. Step 5 — Specify the Appropriate MBeanServer

A Spring exporter can use a discovered server or an explicitly configured one:

~~~java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;

@Bean
MBeanServer mbeanServer() {
    return ManagementFactory.getPlatformMBeanServer();
}
~~~

When needed, inject the server into the exporter:

~~~java
@Bean
MBeanExporter jmxExporter(
        MBeanServer server,
        MetadataMBeanInfoAssembler assembler,
        MetadataNamingStrategy naming) {
    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(server);
    exporter.setAssembler(assembler);
    exporter.setNamingStrategy(naming);
    exporter.setAutodetectModeName("AUTODETECT_ASSEMBLER");
    return exporter;
}
~~~

This is an **alternative variant** for \`jmxExporter\` from the previous section, not a second bean to add concurrently under the same name. In a real application, choose only one exporter configuration.

Setting the right MBeanServer ensures that JMX clients and tests read the same registry. If the application uses a custom MBeanServer, \`ManagementFactory.getPlatformMBeanServer()\` may not contain the custom MBean.

## 10. Step 6 — Verify the MBean Is Registered

Before opening JConsole, you can verify using the Java API:

~~~java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class JmxRegistrationCheck {
    public static void verify(MBeanServer server)
            throws Exception {
        ObjectName name = new ObjectName(
            "com.example.shop.jobs:type=WorkerSettings,name=primary");

        if (!server.isRegistered(name)) {
            throw new IllegalStateException(
                "WorkerSettings MBean not registered");
        }

        System.out.println("Registered: " + name);
    }

    public static void main(String[] args) throws Exception {
        verify(ManagementFactory.getPlatformMBeanServer());
    }
}
~~~

Note: running \`main\` in a standalone JVM checks the MBeanServer of **that JVM itself**, and does not automatically read the MBeanServer of another Spring Boot process. To verify registration properly, run the check inside the application JVM/test context or connect remotely via an authorized connector.

Having the MBean registered is a necessary condition, but not sufficient to prove the attribute is writable. The next step is inspecting metadata.

## 11. Step 7 — Inspect MBeanInfo and Read/Write Permissions

To see what attributes a JMX client actually observes:

~~~java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class AttributeMetadataCheck {

    public static void verify(MBeanServer server)
            throws Exception {

        ObjectName name = new ObjectName(
            "com.example.shop.jobs:type=WorkerSettings,name=primary");

        MBeanInfo info = server.getMBeanInfo(name);

        MBeanAttributeInfo target = null;
        for (MBeanAttributeInfo attribute : info.getAttributes()) {
            if ("MaxConcurrentJobs".equals(attribute.getName())) {
                target = attribute;
                break;
            }
        }

        if (target == null) {
            throw new AssertionError(
                "Missing JMX attribute MaxConcurrentJobs");
        }
        if (!target.isReadable()) {
            throw new AssertionError("Attribute not readable");
        }
        if (!target.isWritable()) {
            throw new AssertionError("Attribute not writable");
        }
        if (!"int".equals(target.getType())) {
            throw new AssertionError(
                "Unexpected type: " + target.getType());
        }

        System.out.println("Attribute is readable and writable");
    }
}
~~~

In JMX \`MBeanInfo\`, the attribute name is \`MaxConcurrentJobs\` per JavaBean property naming. The primitive type \`int\` typically appears as \`int\`, while values returned through the JMX client API are boxed into \`Integer\`.

If \`isWritable()\` is \`false\`, check:

- Does the setter exist and is it public?
- Does the setter have the exact signature \`setMaxConcurrentJobs(int)\`?
- Is \`@ManagedAttribute\` present on the setter?
- Is the exporter/assembler actually using annotation metadata, or another Standard MBean interface?
- Does an AOP proxy expose the setter?
- Is there a getter/setter type mismatch?
- Did another MBean claim the same ObjectName due to the registration policy?

Do not confuse \`isWritable()\` with a JMX remote principal's permissions. \`isWritable()\` only states that the contract allows setting; whether a specific client has write permission depends on the security layer.

## 12. Step 8 — Write the Attribute Using MBeanServer

JMX API operations:

~~~java
import javax.management.Attribute;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class UpdateWorkerConcurrency {

    public static void update(MBeanServer server)
            throws Exception {
        ObjectName name = new ObjectName(
            "com.example.shop.jobs:type=WorkerSettings,name=primary");

        Object before = server.getAttribute(name, "MaxConcurrentJobs");
        System.out.println("Before: " + before);

        server.setAttribute(
            name,
            new Attribute("MaxConcurrentJobs", 12));

        Object after = server.getAttribute(name, "MaxConcurrentJobs");
        System.out.println("After: " + after);
    }
}
~~~

A successful write means the setter was processed by the JMX invocation without errors. Checking the readback confirms the settings component is reporting the new value.

However, **reading back 12 is not enough to prove the worker pool actually applied the limit of 12** if the settings component is not integrated with the scheduler. In real deployments, test behavior or read metrics such as \`ConfiguredLimit\`, \`EffectiveLimit\`, and \`ActiveWorkers\` to avoid situations where a new configuration only changes superficially.

## 13. Step 9 — Test Writing an Invalid Value

The setter validates the range 1..64. Try the value 0 in a development/test environment:

~~~java
try {
    server.setAttribute(
        name, new Attribute("MaxConcurrentJobs", 0));
    throw new AssertionError("Expected validation failure");
} catch (Exception expected) {
    System.out.println(
        "Invalid value rejected: " +
        expected.getClass().getSimpleName());
}
~~~

This is a brief illustration. In real tests, do not catch any \`Exception\` and treat it as passing: verify **the error came from the expected validation** via the appropriate exception/cause for your JMX/Spring version. After the error, read \`MaxConcurrentJobs\` and confirm the previous value was not modified.

Relevant exceptions may include:
- \`InvalidAttributeValueException\` in applicable JMX invocation paths.
- \`MBeanException\` or an exception wrapped by the framework from the setter.
- \`AttributeNotFoundException\` if the name is wrong or not writable in the contract.
- \`ReflectionException\` when invocation/signature is incorrect.
- \`SecurityException\` or access denied due to security policy.

Do not "fix" a failing validation test by removing validation so that JConsole can set any value.

## 14. Spring JMX Metadata and the Setter Mechanism

In JavaBeans, a getter and setter are paired into a single property when they share the same name and compatible types:

~~~text
getMaxConcurrentJobs()      -> property MaxConcurrentJobs (read)
setMaxConcurrentJobs(int)   -> property MaxConcurrentJobs (write)
~~~

For booleans you can use:

~~~java
@ManagedAttribute
public boolean isPaused() {
    return paused;
}

@ManagedAttribute
public void setPaused(boolean paused) {
    this.paused = paused;
}
~~~

However, do not confuse \`@ManagedAttribute\` with \`@Value\` or \`@ConfigurationProperties\`. A Spring JMX setter can change a value at **runtime**, but it does not write back to \`application.yml\`, environment variables, or a config server.

When the JVM restarts, configuration may revert to values from property sources. If changes must survive restarts, design separate persistence/dynamic configuration with authentication, auditing, and rollback.

## 15. MBean Read/Write Capability vs. User Permissions

MBeanInfo may say an attribute is writable, yet a remote JMX connector can still restrict a specific client.

Distinguish between:

| Layer | Meaning |
|---|---|
| Attribute metadata \`isWritable()\` | MBean contract has a setter |
| JMX connector authentication | Who the client is |
| JMX connector authorization | What the client is allowed to do |
| Firewall/network policies | Where the client can connect from |
| TLS/encryption | Protecting traffic |
| Application-level validation | Valid values and safe impact |
| Audit | Who changed configuration, and when |

A writable MBean is not automatically protected by Spring Security HTTP rules. Remote JMX typically has its own security configuration. For safe production operation:
- Never expose unauthenticated remote JMX.
- Do not share administrative permissions with collectors that only need to read metrics.
- Restrict network access and credentials.
- Review setters that affect availability.
- Audit changes with operational impact.
- Have a way to restore the previous configuration.

## 16. Designing Setters to Avoid Dangerous Side Effects

Not every attribute should be writable.

Values to treat with caution:
- Thread pool concurrency limits.
- Cache capacity.
- Batch size.
- Retry interval.
- Queue draining switches.
- Traffic control.
- Feature flags affecting order processing.

Risks when a setter changes values:
1. Raising concurrency too high causes CPU/DB overload.
2. Dropping concurrency abruptly causes low throughput.
3. Violating other invariants such as min/max pool sizes.
4. Writing partial configuration without applying everything.
5. Multiple operators making consecutive changes causing races.
6. Runtime changes lost after a restart.
7. Monitoring reads the set value while the worker pool has not applied it.
8. No audit trail to investigate changes.

A good setter should have:
- Validation at the domain boundary.
- Synchronized updates and effective state.
- Clear semantics (applied immediately, deferred, or requires restart).
- Specific error reporting.
- Observability of current/effective state.
- Authorization and auditing aligned with sensitivity.

## 17. Updating Multiple Related Settings

\`@ManagedAttribute\` on two independent setters does not create a transaction:

~~~java
setCorePoolSize(int core);
setMaximumPoolSize(int max);
~~~

If a client calls both setters in sequence, the system may observe an invalid intermediate state. For example, lowering max before core causes \`ThreadPoolExecutor\` to reject the configuration.

When multiple parameters must change as an atomic update, consider:
- A management operation \`updatePoolSettings(core, max)\` with combined validation.
- An immutable settings object published atomically.
- A lock or consistent state machine.
- A version/generation number to detect competing updates.
- A staged apply-and-rollback workflow if the underlying API is not atomic.

Not every change has to be a JMX attribute setter. Purpose-built operations are often better suited for multi-step actions or actions with side effects.

## 18. Supporting Concurrent Updates

\`AtomicInteger\` ensures simple reads/writes do not suffer torn primitive updates. However, it does not automatically prevent **lost updates** in read-modify-write sequences:

~~~java
int current = settings.currentLimit();
settings.updateLimit(current + 1);
~~~

If two clients run this snippet concurrently, both might read 8 and both set 9, instead of reaching 10. If the application only needs "set absolute target", \`set(9)\` may have the right semantics; but if you want atomic "increment", you must use CAS or a dedicated operation.

You can expose:
- \`MaxConcurrentJobs\` (target value).
- \`ConfigurationGeneration\` (version counter incremented on each change).
- \`LastChangedEpochMillis\`.
- \`EffectiveConcurrency\` if the worker pool applies changes asynchronously.

A client can compare the generation before/after, though having a generation counter does not automatically create an optimistic transaction unless the setter checks the generation.

## 19. Do Not Change Persistent Configuration When Only Experimenting

When a setter only modifies in-RAM state:
- Restarting the JVM restores defaults or external config.
- Replicas do not automatically synchronize; each JVM has its own MBeanServer and settings.
- A JConsole client modifying pod A does not necessarily modify pod B.
- Config rollouts can overwrite runtime changes.

If cluster-wide changes are needed, use a controlled configuration/rollout system rather than sending \`setAttribute()\` individually to each pod without orchestration.

For experiments, clearly expose:
~~~text
Runtime-only override: yes
Applies to: current JVM
Persists across restart: no
Effective immediately: depends on worker integration
~~~

This information is important so operators do not misunderstand the scope of a change.

## 20. Practicing with JConsole

Steps on a JVM you are authorized to administer:

1. Start the application with the management bean and annotation-aware exporter configured.
2. Open JConsole/JMC and connect to the right JVM.
3. Select the **MBeans** tab.
4. Find the \`com.example.shop.jobs\` domain.
5. Open \`type=WorkerSettings,name=primary\`.
6. Select the \`MaxConcurrentJobs\` attribute.
7. View the current value (8).
8. Try writing 12 via the editing UI if supported.
9. Refresh and confirm the new value.
10. In a test environment, try 0 to observe the validation error.
11. Restore 8 if needed.
12. Observe whether the worker pool applies the change as designed by the contract.

JConsole's UI varies by JDK and accessibility. If the attribute is not editable, inspect metadata to confirm \`isWritable\`. If JConsole does not see the MBean, check the ObjectName, exporter, and MBeanServer rather than rushing to edit the setter.

## 21. Checking JMX Metadata Programmatically in Java

A helper can print all attributes:

~~~java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class JmxAttributeInspector {

    public static void print(MBeanServer server, ObjectName name)
            throws Exception {

        MBeanInfo info = server.getMBeanInfo(name);
        for (MBeanAttributeInfo a : info.getAttributes()) {
            System.out.printf(
                "%s type=%s readable=%s writable=%s%n",
                a.getName(),
                a.getType(),
                a.isReadable(),
                a.isWritable());
        }
    }
}
~~~

Expected output for this lesson:

~~~text
MaxConcurrentJobs type=int readable=true writable=true
~~~

If the output differs, inspect the exporter/assembler and the MBean the client is reading. Having \`@ManagedAttribute\` only on the getter normally leads to read-only if the setter is not exposed.

## 22. Integration Testing with Spring Test

A good integration test should build an ApplicationContext containing:
- \`WorkerConcurrencySettings\`.
- \`WorkerSettingsManagement\`.
- An annotation-aware exporter.
- A dedicated test MBeanServer.
- An explicit registration policy.

Required assertions:

1. The MBean is registered under the right ObjectName.
2. Attribute \`MaxConcurrentJobs\` exists.
3. \`isReadable\` and \`isWritable\` are both true.
4. \`getType()\` is \`int\`.
5. Initial value is 8.
6. \`setAttribute(...,12)\` succeeds.
7. Reading back returns 12.
8. The settings service reads 12, not just the JMX layer.
9. Value 0 is rejected and the old value remains intact.
10. Other beans are not unintentionally exported.
11. When the context closes, the exporter unregisters its registrations properly.

Tests should use JUnit/Spring Test with realistic configuration and a dedicated test MBeanServer instead of the shared platform MBeanServer of the entire test suite.

### Verification Pseudocode

~~~java
ObjectName name = new ObjectName(
    "com.example.shop.jobs:type=WorkerSettings,name=primary");

assertTrue(server.isRegistered(name));

MBeanInfo info = server.getMBeanInfo(name);
MBeanAttributeInfo attr = java.util.Arrays
        .stream(info.getAttributes())
        .filter(a -> "MaxConcurrentJobs".equals(a.getName()))
        .findFirst()
        .orElseThrow();

assertTrue(attr.isReadable());
assertTrue(attr.isWritable());
assertEquals("int", attr.getType());

assertEquals(8, server.getAttribute(name, "MaxConcurrentJobs"));

server.setAttribute(
    name,
    new javax.management.Attribute("MaxConcurrentJobs", 12));

assertEquals(12, server.getAttribute(name, "MaxConcurrentJobs"));
assertEquals(12, settings.currentLimit());
~~~

The snippet above is the assertion part, not a complete standalone test. You need to import JUnit assertions, start the context, and inject the right MBeanServer/settings.

## 23. Diagnosing Common Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| MBean does not appear | Bean not in context or exporter not enabled | Check component scanning/exporter |
| Attribute is read-only | Setter missing annotation or not recognized by metadata | Check getter/setter and MBeanInfo |
| Attribute does not exist | Wrong JavaBean property name or different export path | Read \`MBeanInfo\` |
| \`AttributeNotFoundException\` | Wrong name or not writable | Verify \`MaxConcurrentJobs\` |
| \`InvalidAttributeValueException\` | Invalid type or value | Check \`int\` and validation |
| \`MBeanException\` | Setter threw a business error | Read cause and logs |
| \`ReflectionException\` | Accessor signature/metadata mismatch | Compare setter/getter |
| \`InstanceAlreadyExistsException\` | Two exporters colliding on ObjectName | Single registration owner |
| Wrote 12 but workers still cap at 8 | Settings not applied by worker pool | Connect effective configuration |
| Change lost after restart | Runtime-only state | Design persistence if required |
| Only one pod changed | MBeanServer belongs to one JVM | Use cluster configuration control |
| Setter works locally, blocked remotely | Connector authorization | Check JMX permissions |
| Proxy prevents annotation recognition | Spring AOP interface/target resolution | Test annotation assembler with proxy |
| Setter causes overload | Value too large or missing bounds | Add validation and guardrails |

## 24. Self-Check Questions

**1. Why are both a getter and a setter needed for a read–write attribute?**  
Because the client needs both a read path and a write path for the same JavaBean property; the assembler must expose both.

**2. Why is \`@ManagedAttribute\` not equivalent to \`@ManagedOperation\`?**  
Because an attribute represents a property with a getter/setter, whereas an operation is an action invoked by name and signature.

**3. Does \`isWritable()\` guarantee every remote client can write?**  
No. It is MBean metadata, not the connector's authorization policy.

**4. Is using \`AtomicInteger\` enough to safely change thread pool concurrency?**  
Not yet. It protects the configuration value, but you still need a mechanism to apply it to the executor/worker scheduler, validation, and a runtime change policy.

**5. When setting 12 reads back 12, yet the worker is still capped at 8, where is the bug?**  
Management state is not being reflected in effective worker pool behavior.

**6. Does a JMX setter automatically write back to \`application.yml\`?**  
No. By default it only mutates the state managed by the setter's implementation.

**7. If two JVMs share the same ObjectName, does one write apply to both?**  
No. An ObjectName is scoped within each MBeanServer; a separate synchronization/rollout mechanism is needed.

**8. Should setters modifying sensitive settings be exposed on public remote JMX?**  
No. Only expose via a secure management channel with appropriate authentication, authorization, encryption, and network controls.

## 25. Extension Exercises

### Exercise A — Create a read–write boolean attribute

Add to the management bean:

~~~java
private final java.util.concurrent.atomic.AtomicBoolean paused =
        new java.util.concurrent.atomic.AtomicBoolean();

@ManagedAttribute
public boolean isPaused() {
    return paused.get();
}

@ManagedAttribute
public void setPaused(boolean value) {
    paused.set(value);
}
~~~

Use MBeanInfo to verify \`Paused\` has type \`boolean\` and is readable/writable. Discuss why flipping the flag alone does not pause workers unless the workers check the flag.

### Exercise B — Expose min/max limits as read-only

Expose:

~~~java
@ManagedAttribute
public int getMinimumConcurrency() {
    return WorkerConcurrencySettings.MIN_CONCURRENCY;
}

@ManagedAttribute
public int getMaximumConcurrency() {
    return WorkerConcurrencySettings.MAX_CONCURRENCY;
}
~~~

These two attributes should be read-only, helping JConsole users know the enforced bounds before writing.

### Exercise C — Desired state and effective state

Design \`RequestedLimit\` as writable and \`EffectiveLimit\` as read-only. When the worker pool takes a short time to apply changes, operators can see both the target and the applied state. Add \`LastAppliedEpochMillis\` and \`LastApplyError\` if needed.

### Exercise D — Validation testing

Try writing -1, 0, 65, and valid values 1, 32, 64. For each attempt, check:
- The right exception/cause type.
- State unchanged after an invalid value.
- Valid value written and read back.
- Worker component notified or updated properly.

### Exercise E — Two interdependent setters

Design \`MinWorkers\` and \`MaxWorkers\`. Explain why two independent setters are not transactional; propose an \`updateLimits(min,max)\` operation with combined validation, or an immutable settings snapshot published atomically.

### Exercise F — Permission testing

Use a test environment configured with two JMX principals: read-only and readwrite. Verify the reader can call \`getAttribute\` but cannot call \`setAttribute\`, while the authorized operator can write valid values. Do not perform this experiment by opening an unauthenticated remote connector.

## 26. Key Takeaways

- \`@ManagedResource\` marks the resource; \`@ManagedAttribute\` on getters/setters exposes a single readable/writable JMX property.
- \`getMaxConcurrentJobs\` / \`setMaxConcurrentJobs\` are mapped to the \`MaxConcurrentJobs\` attribute.
- The Spring bean must exist in the context and be processed by an appropriate exporter/assembler.
- Inspect \`MBeanInfo\` to verify what clients actually see (\`readable=true\` and \`writable=true\`).
- Use \`getAttribute()\` and \`setAttribute()\` to verify end-to-end.
- Setters should have validation, concurrency semantics, and only change configuration with clear impact.
- JMX writability is distinct from JMX connector authorization.
- Runtime JMX changes usually belong to one JVM and do not persist or replicate automatically.
- Do not create multiple MBean exporters registering the same ObjectName.
- For interdependent multi-field settings, use an operation or atomic configuration update rather than separate setters.

## 27. References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Javadoc — ManagedAttribute: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedAttribute.html
- Spring Framework Javadoc — ManagedResource: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedResource.html
- Spring Framework Javadoc — MBeanExporter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Java SE 21 — MBeanAttributeInfo: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanAttributeInfo.html
- Java SE 21 — MBeanServer: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
