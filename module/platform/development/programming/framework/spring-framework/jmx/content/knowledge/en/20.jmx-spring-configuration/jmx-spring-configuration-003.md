# @EnableMBeanExport Across Multiple Profiles: Managing Spring JMX by Environment

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain the function of **\`@EnableMBeanExport\`** in Spring Framework and its relationship with **\`MBeanExporter\`**, **\`MBeanServer\`**, **\`@ManagedResource\`**, and other JMX annotations.
- Use Spring **\`@Profile\`** to decide which MBean export configuration is activated in \`dev\`, \`test\`, \`staging\`, and \`prod\` environments.
- Distinguish **enabling JMX export in the application** from **opening the JVM's remote JMX connector**; using profiles does not automatically secure a management port.
- Design profiles, \`ObjectName\` conventions, and ownership to avoid creating multiple exporters or multiple MBeans with the same name.
- Use plain Spring Java configuration or Spring Boot without confusing \`@EnableMBeanExport\` with \`spring.jmx.enabled\`.
- Inspect \`Environment.getActiveProfiles()\`, \`MBeanServer.isRegistered(...)\`, and \`MBeanInfo\` to confirm what is actually exported.
- Write integration tests proving that an MBean only appears in allowed profiles and is unregistered when the context closes.
- Identify risks caused by overlapping profiles, the default profile, AOP proxies, auto-configuration, parent/child contexts, and remote management.

## 2. Context: Why Does JMX Export Need Per-Profile Configuration?

A Spring application may be deployed across multiple environments with different management requirements:

| Environment | Common JMX Needs |
| --- | --- |
| \`dev\` | Need detailed visibility into caches, queues, workers, and ability to test management operations in an isolated environment. |
| \`test\` | Need to test the MBean contract or run integration checks, without MBeans causing tests to collide. |
| \`staging\` | Need to be close to production to test monitoring, access control, and lifecycle. |
| \`prod\` | Export only truly necessary MBeans, with strict control over content and permissions. |

Not all applications need remote JMX. Many systems only use the local platform MBeanServer to read JVM status or export metrics through another adapter. However, once a control operation such as \`clearCache()\`, \`pauseConsumers()\`, or \`reloadConfiguration()\` is exposed, restricting where that operation appears reduces the operational attack surface.

**Spring profiles** help decide *which configuration beans exist in the ApplicationContext*. When an \`@EnableMBeanExport\` configuration resides on a \`@Configuration\` class that is only active for a specific profile, the annotation-activated exporter can be created only in appropriate contexts.

\`\`\`text
Active profiles
   dev,local          prod          test
      |                |             |
      v                v             v
@Profile matching?
      |                |             |
      v                v             v
JMX configuration activated?
      |                |             |
      v                v             v
MBeanExporter created / configured
      |
      v
MBeanServer registers selected MBeans
      |
      v
JConsole / JMX client sees runtime contract
\`\`\`

**Note:** A profile is only a mechanism for selecting Spring configuration. It does not automatically restrict JMX permissions, encrypt transport, or distinguish read-only from read-write.

## 3. What Is the Role of @EnableMBeanExport?

In Spring Framework, the annotation:

\`\`\`java
import org.springframework.context.annotation.EnableMBeanExport;
\`\`\`

is used to enable JMX export support on a \`@Configuration\` class. The internal configuration import mechanism creates/configures the corresponding exporter infrastructure, allowing Spring to manage eligible beans according to the JMX configuration.

Basic example:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
\`\`\`

Beans with metadata such as \`@ManagedResource\`, \`@ManagedAttribute\`, and \`@ManagedOperation\` can be registered as MBeans depending on how the exporter detects them.

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example:type=Queue,name=Orders",
    description = "Order queue monitoring"
)
public class OrderQueueManagement {

    @ManagedAttribute(description = "Current queued messages")
    public long getQueueDepth() {
        return 42L; // Illustrative data only.
    }
}
\`\`\`

If the exporter is not enabled or the bean does not belong to the current ApplicationContext, the annotation on the class alone does not guarantee the MBean will appear. Conversely, if a bean is registered manually via \`MBeanServer.registerMBean\`, it can still exist even without using \`@EnableMBeanExport\`.

### 3.1. What Does @EnableMBeanExport Not Do?

It does not:

- Automatically open a remote JMX/RMI port.
- Grant JMX permissions or create operator accounts.
- Replace TLS, firewalls, or VPNs.
- Guarantee that all Spring beans are exported.
- Turn every public method into a management operation.
- Automatically inspect getter return values for sensitive data.
- Automatically convert metrics to Prometheus/OpenTelemetry.
- Manage database persistence for MBean state.

This is an important boundary so that Spring bean exporting is not confused with management layers outside the JVM.

## 4. The Spring @Profile Mechanism

The \`@Profile\` annotation sets conditions based on the **active profiles** of the Spring \`Environment\`:

\`\`\`java
import org.springframework.context.annotation.Profile;
\`\`\`

Example:

\`\`\`java
@Configuration
@Profile("dev")
public class DevelopmentOnlyConfiguration {
    // Beans in this configuration are only registered
    // when the dev profile is active.
}
\`\`\`

If the configuration containing \`@EnableMBeanExport\` is on a \`@Configuration\` class annotated with \`@Profile\`, importing the export configuration depends on the profile condition:

\`\`\`java
@Configuration
@Profile("dev")
@EnableMBeanExport
public class DevelopmentJmxConfiguration {
}
\`\`\`

When \`dev\` is inactive, the configuration class is excluded from relevant processing, so this configuration path does not activate the exporter. That **does not mean no other exporter exists**: Spring Boot auto-configuration or another \`@Configuration\` class can still create its own exporter.

### 4.1. Profile expressions

Spring supports profile expressions such as:

\`\`\`java
@Profile({"dev", "staging"})
\`\`\`

In this case, the condition across profile names normally works in the sense of *any profile in the list being active*. Logical expressions can take forms such as:

\`\`\`java
@Profile("dev | staging")
\`\`\`

or:

\`\`\`java
@Profile("!prod")
\`\`\`

However, \`!prod\` can be broader than intended: when the \`prod\` profile is absent, the configuration may be enabled even in unclassified environments. For a management surface, prefer an **explicit profile allowlist** rather than an overly broad negated configuration.

## 5. Example 1: Enable JMX Export Only in dev and staging

### 5.1. Profile-based config

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;
import org.springframework.context.annotation.Profile;

@Configuration
@Profile({"dev", "staging"})
@EnableMBeanExport
public class ManagementExportConfiguration {
}
\`\`\`

### 5.2. Managed bean

\`\`\`java
package example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example:type=Worker,name=Importer",
    description = "Import worker management"
)
public class ImportWorkerManagement {

    @ManagedAttribute(description = "Whether the worker is running")
    public boolean isRunning() {
        return true;
    }

    @ManagedAttribute(description = "Number of processed items")
    public long getProcessedCount() {
        return 100L;
    }

    @ManagedOperation(description = "Request a graceful worker pause")
    public void requestPause() {
        // Call the service to request a safe pause.
    }
}
\`\`\`

For a plain Spring Framework ApplicationContext, if there is no other exporter and annotation export is properly configured, when \`dev\` or \`staging\` is active, the MBean can be registered at:

\`\`\`text
com.example:type=Worker,name=Importer
\`\`\`

When the profile does not match, \`ManagementExportConfiguration\` does not activate export from this annotation. However, the \`ImportWorkerManagement\` bean can still exist as a Spring \`@Component\`; a profile condition on the **export configuration** does not automatically exclude the business bean.

### 5.3. Activating a profile

In Spring Boot:

\`\`\`bash
java -jar app.jar --spring.profiles.active=dev
\`\`\`

In \`application.properties\` (when appropriate for your deployment):

\`\`\`properties
spring.profiles.active=staging
\`\`\`

Or using an environment variable:

\`\`\`text
SPRING_PROFILES_ACTIVE=dev
\`\`\`

How profiles are activated depends on the deployment infrastructure. For production, use a configuration management system and release process, avoiding hardcoding dev-only profiles into shared source code.

## 6. Example 2: Profiles for Different Management Groups

An application might need *monitoring* MBeans in production while only allowing specialized operations in a lab environment.

There are two common approaches:

1. **Choose the export configuration:** which profile creates the exporter and which MBeans are exported.
2. **Separate managed resources:** always have read-only MBeans, while only registering MBeans containing control operations in allowed environments.

### 6.1. Read-only management adapter

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example:type=Worker,name=ImporterStatus"
)
public class ImporterStatusManagement {

    @ManagedAttribute
    public boolean isHealthy() {
        return true;
    }

    @ManagedAttribute
    public long getBacklog() {
        return 25L;
    }
}
\`\`\`

### 6.2. Control management adapter

\`\`\`java
import org.springframework.context.annotation.Profile;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@Profile({"dev", "staging"})
@ManagedResource(
    objectName = "com.example:type=Worker,name=ImporterControl"
)
public class ImporterControlManagement {

    @ManagedOperation(
        description = "Request graceful pause of importer"
    )
    public void requestPause() {
        // Forward the request to a service with validation.
    }
}
\`\`\`

Now the control bean is only created when a valid profile is active. Even if a global exporter scans the ApplicationContext, it cannot export this bean in production because the bean does not exist there.

**This is a clearer safeguard than merely changing descriptions**, though it does not replace connector authorization. If an operation has significant administrative impact in production, implement real authorization and auditing instead of relying solely on profiles.

### 6.3. When multiple exporter types exist

In a large project, an exporter can use an explicit bean list to control the management surface. Putting everything in a single exporter makes ownership easier to manage across multiple modules.

A configuration *should not* create two separate exporters scanning the same set of beans and sharing the platform MBeanServer, unless \`ObjectName\` collisions and lifecycle have been carefully controlled. If multiple MBean groups are needed, combine the selected bean lists or partition them clearly.

## 7. Example 3: Spring Boot and spring.jmx.enabled

Spring Boot includes JMX auto-configuration. In many Spring Boot versions, the property:

\`\`\`properties
spring.jmx.enabled=true
\`\`\`

enables auto-configuring Spring MBean export under the applicable conditions.

Example \`application-dev.properties\`:

\`\`\`properties
spring.jmx.enabled=true
\`\`\`

Example \`application-prod.properties\`:

\`\`\`properties
spring.jmx.enabled=false
\`\`\`

**Key points to understand:**

- \`spring.jmx.enabled\` controls **Spring Boot's JMX auto-configuration** depending on the version and specific conditions.
- \`@EnableMBeanExport\` placed directly on a \`@Configuration\` class is a **Spring Framework** configuration path.
- If you **explicitly add \`@EnableMBeanExport\`**, disabling auto-configuration with \`spring.jmx.enabled=false\` should not be assumed to disable that manual exporter as well.
- In an application that has both mechanisms, check the actual number of exporters and registered MBean names; avoid thinking of a profile as a "single switch" for all of JMX.

A simple strategy in Spring Boot is to use **one deliberately chosen JMX configuration path**. If using Boot auto-configuration, manage \`spring.jmx.enabled\` per profile and avoid duplicate \`@EnableMBeanExport\`. If deeper control via Framework config is needed, actively manage the exporter and related beans.

### 7.1. Profile-based application.yml

An example of organizing a Spring Boot configuration document:

\`\`\`yaml
spring:
  application:
    name: import-service
---
spring:
  config:
    activate:
      on-profile: dev
  jmx:
    enabled: true
---
spring:
  config:
    activate:
      on-profile: prod
  jmx:
    enabled: false
\`\`\`

YAML documents are applied per profile according to the Spring Boot Config Data mechanism of the version in use. For other profiles, set explicit defaults or define separate configuration files to avoid unpredictable states.

This configuration only illustrates Boot JMX auto-configuration. If the project has \`@EnableMBeanExport\` elsewhere, profile rules must account for that layer as well.

## 8. Overlapping Profiles and Multiple Active Profiles

In practice, multiple profiles can be active simultaneously:

\`\`\`text
spring.profiles.active=prod,debug
\`\`\`

Or:

\`\`\`text
spring.profiles.active=staging,observability
\`\`\`

\`@Profile\` expressions operate on the set of active profiles. If an annotation says:

\`\`\`java
@Profile("!prod")
\`\`\`

then with \`prod,debug\`, it normally will not match because \`prod\` is active. However, with an environment that has not declared \`prod\`, the negated condition may match unintentionally.

Another risk:

\`\`\`java
@Configuration
@Profile("dev")
@EnableMBeanExport
class DevJmxExportConfig {}

@Configuration
@Profile("observability")
@EnableMBeanExport
class ObservabilityJmxExportConfig {}
\`\`\`

If both \`dev\` and \`observability\` are active, both configurations may participate in importing the JMX mechanism. Do not assume there are "two exporters" merely because there are two annotations; how Spring imports bean definitions and handles infrastructure names depends on the version/configuration. Still, such a design creates **ownership ambiguity** and should be avoided by consolidating conditions.

Prefer a single configuration:

\`\`\`java
@Configuration
@Profile("dev | observability")
@EnableMBeanExport
public class JmxExportConfiguration {
}
\`\`\`

Or if finer control is needed, use conditional configuration and a clearly organized list of environments in the deployment system.

## 9. The Default Profile and the "No Profile" Trap

Spring has a **default profile**, typically named \`default\`, used when no explicit active profile is set. Therefore:

\`\`\`java
@Profile("default")
\`\`\`

can match in a local environment where no profile is configured.

If using:

\`\`\`java
@Profile("!prod")
\`\`\`

then JVMs started without the production profile may enable JMX export unexpectedly. For critical environments, maintain a **restrictive** default configuration, enabling advanced MBeans only via an allowlist.

Questions to ask:

- When no profile is set, is JMX export enabled?
- When both \`prod\` and a debug-support profile are active, what happens?
- Who has permission to set \`SPRING_PROFILES_ACTIVE\`?
- Do external configs, command-line arguments, or environment variables override properties?
- Does another Spring Boot auto-configuration create an exporter when the \`@Profile\` class is excluded?

These questions determine the actual management surface more than looking at a single annotation.

## 10. ObjectName Naming and Avoiding Collisions Across Profiles

JMX names typically follow the structure:

\`\`\`text
domain:key=value,key2=value2
\`\`\`

Examples:

\`\`\`text
com.example.import:type=Worker,name=Daily
com.example.import:type=Queue,name=Retries
\`\`\`

Different profiles usually run in **different JVMs**, so having the same \`ObjectName\` across two independent environments is not a conflict on the same MBeanServer. Collisions happen **within the same server** when two parties register the same name.

Cases to watch out for:

1. Two exporters in one ApplicationContext exporting the same bean.
2. A Spring parent context and child context sharing the platform MBeanServer.
3. An MBean previously registered by manual code.
4. Two modules using the same domain/type/name.
5. An unclosed test context leaving an old MBean in the platform server.
6. Multiple exporters with different registration policies competing for a name.

If a unique name per instance within the same JVM is needed, use a naming strategy or an additional key property without sensitive data. Do not add the profile into \`ObjectName\` just to mask a bug with two duplicate exporters; fix the ownership properly.

## 11. RegistrationPolicy in Multi-Profile Environments

Spring supports policies when an ObjectName already exists:

- \`FAIL_ON_EXISTING\`: fails if the ObjectName is already registered.
- \`IGNORE_EXISTING\`: skips the new registration if the name exists.
- \`REPLACE_EXISTING\`: replaces the existing MBean according to exporter policy.

Example:

\`\`\`java
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

MBeanExporter exporter = new MBeanExporter();
exporter.setRegistrationPolicy(
    RegistrationPolicy.FAIL_ON_EXISTING
);
\`\`\`

With multiple profiles and exporters, \`FAIL_ON_EXISTING\` usually helps catch configuration conflicts early. \`IGNORE_EXISTING\` can leave the application running with an old MBean or another module's MBean, misleading operators about state. \`REPLACE_EXISTING\` can overwrite an object not owned by the exporter and requires careful consideration.

**Registration policy is not a per-profile toggle mechanism.** It only handles name conflicts when a registration operation occurs.

## 12. Right MBeanServer and Right JVM

A Spring exporter can use the **platform MBeanServer** or a custom \`MBeanServer\`, depending on configuration. When checking:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();
\`\`\`

this is only accurate if the exporter actually registers into this server.

With a custom server, inject or retrieve the exact configured MBeanServer. A remote client might be connected to a different JVM or a connector pointing to a separate server. Thus, when \`isRegistered(name)\` is \`false\`, that alone is not enough to conclude the \`@EnableMBeanExport\` class is not working.

## 13. Checking Active Profiles at Runtime

You can retrieve \`Environment\` in Spring:

\`\`\`java
import java.util.Arrays;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ActiveProfileReporter {
    private final Environment environment;

    public ActiveProfileReporter(Environment environment) {
        this.environment = environment;
    }

    public void reportProfiles() {
        System.out.println(
            "Active profiles: "
                + Arrays.toString(environment.getActiveProfiles())
        );
    }
}
\`\`\`

If there are no explicit active profiles, \`getActiveProfiles()\` may return an empty array while default profiles are still in effect. To check default profiles, use \`getDefaultProfiles()\`.

Combine profile data with actual MBean state rather than just logging \`Active profiles: [dev]\` and concluding the exporter registered successfully.

### 13.1. Verifying the MBean is registered

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example:type=Worker,name=Importer"
);

boolean registered = server.isRegistered(name);
System.out.println("Registered = " + registered);
\`\`\`

With the \`@Profile({"dev", "staging"})\` example, expectations in a Spring Framework context with no other exporter are:

| Active profile | Expected target MBean |
| --- | --- |
| \`dev\` | Registered |
| \`staging\` | Registered |
| \`prod\` | Not registered via this config |
| \`test\` | Not registered via this config |
| No explicit profile | Not registered via this config, if default does not match |

These are results based on the example and its assumptions. In a real application, other exporter mechanisms can alter the outcome.

## 14. Reading MBeanInfo to Confirm the Exposed Interface

\`isRegistered=true\` only confirms an MBean exists under that name. To verify the actual interface:

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;

if (server.isRegistered(name)) {
    MBeanInfo info = server.getMBeanInfo(name);

    System.out.println("MBean class = " + info.getClassName());

    for (var attribute : info.getAttributes()) {
        System.out.println(
            "Attribute: " + attribute.getName()
                + ", writable=" + attribute.isWritable()
        );
    }

    for (MBeanOperationInfo operation : info.getOperations()) {
        System.out.println(
            "Operation: " + operation.getName()
        );
    }
}
\`\`\`

When production only allows reading state, verify that control operations are not accidentally exported. A \`@ManagedOperation\` present in a class is not necessarily excluded just because the \`prod\` profile has a different security policy; what must be verified is whether the resource containing that operation is exported at all.

## 15. Integration Testing for Profiles

To prevent configurations from silently changing after refactoring, create tests that start a Spring context with the corresponding profile.

### 15.1. Plain Spring test template

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public final class JmxProfileCheck {

    private static final ObjectName NAME;

    static {
        try {
            NAME = new ObjectName(
                "com.example:type=Worker,name=Importer"
            );
        } catch (Exception e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    static void runForProfile(
            String profile, boolean expected) {

        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext()) {

            context.getEnvironment()
                .setActiveProfiles(profile);

            context.register(ManagementExportConfiguration.class);
            context.register(ImportWorkerManagement.class);
            context.refresh();

            boolean actual = server.isRegistered(NAME);

            if (actual != expected) {
                throw new AssertionError(
                    "Profile=" + profile
                        + ", expected=" + expected
                        + ", actual=" + actual
                );
            }
        }
    }

    public static void main(String[] args) {
        runForProfile("dev", true);
        runForProfile("staging", true);
        runForProfile("prod", false);
        runForProfile("test", false);
    }
}
\`\`\`

The test above illustrates profiles and registration in one process. Ensure \`ImportWorkerManagement\` is a valid bean and the JMX exporter is enabled according to your actual Spring Framework configuration. If the Spring context or custom MBeanServer uses a different mechanism, adjust the test to match the implementation.

### 15.2. Test cleanup between profiles

Multiple integration tests running in the same JVM may share the platform MBeanServer. If a \`dev\` test does not close its context, the MBean remains and a \`prod\` test might see \`isRegistered=true\` even though the prod profile does not create an exporter.

Therefore:

- Use \`try-with-resources\` to close the context.
- When the test ends, confirm the exporter has unregistered the MBeans it owns.
- Use unique \`ObjectName\` values when tests run in parallel.
- Do not unregister MBeans belonging to other tests or running applications.
- Do not use \`REPLACE_EXISTING\` to mask poor isolation.

In JUnit/Spring Test you can use \`@ActiveProfiles\`, but pay attention to context caching: different profiles normally create different configured contexts, while the platform MBeanServer may still be shared within the test JVM.

## 16. Using @ActiveProfiles in Spring Test

In Spring Test, \`@ActiveProfiles\` is used to set profiles for the test context:

\`\`\`java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = {
    ManagementExportConfiguration.class,
    ImportWorkerManagement.class
})
@ActiveProfiles("dev")
class DevelopmentJmxExportTest {

    @Test
    void exportsManagementMBean() {
        // Inject MBeanServer or use the platform server,
        // then assert isRegistered(name).
    }
}
\`\`\`

This is a test-oriented example; matching Spring Test and JUnit Jupiter dependencies are required. When creating production-ready tests, assert actual state instead of leaving an empty test body.

A test for the \`prod\` profile should ensure the app has no other exporter enabled by auto-configuration. When using Spring Boot tests, you can include \`spring.jmx.enabled=false\` in the test environment configuration to control auto-export when appropriate for the test goal.

## 17. Multiple ApplicationContexts and Context Hierarchy

In a web application or large modular system, there may be:

\`\`\`text
Root ApplicationContext
        |
        +-- MBeanExporter A
        |
        +-- Child ApplicationContext
                   |
                   +-- MBeanExporter B
\`\`\`

If both A and B register into the same platform MBeanServer and use the same \`ObjectName\`, having different profiles on the two contexts will not prevent a conflict. Each context has its own \`Environment\` and bean definitions; profiles may be inherited or configured differently.

To avoid issues:

1. Determine which context owns the JMX exporter.
2. Determine which beans fall within the scan scope of each exporter.
3. Use one exporter per MBean set or partition namespaces clearly.
4. Do not allow the same MBean to be registered in both parent and child unintentionally.
5. Check shutdown lifecycle and unregistration when a child context closes before the root context.

In multi-tenant/multi-module setups, do not put tenant IDs or sensitive information directly into ObjectName without a clear policy.

## 18. Profile-Based JMX Export Does Not Mean Profile-Based Remote JMX

Distinguish two configuration layers:

\`\`\`text
Layer 1 — Spring JMX exporting:
    @EnableMBeanExport
    @ManagedResource
    MBeanExporter
    spring.jmx.enabled (Boot auto-configuration)

Layer 2 — JVM remote connector:
    -Dcom.sun.management.jmxremote
    -Dcom.sun.management.jmxremote.port=...
    -Dcom.sun.management.jmxremote.authenticate=...
    -Dcom.sun.management.jmxremote.ssl=...
\`\`\`

A \`@Profile("dev")\` configuration can ensure business MBeans are only exported in dev, but if the prod JVM still has remote JMX enabled, remote clients can still see JVM system MBeans or MBeans registered by other components.

Conversely, Spring can export an MBean in production even when the remote JMX connector is not open; the MBean still resides in the local MBeanServer.

**Do not use profiles as the sole security measure.** For remote JMX, configure authentication, TLS, network restrictions, and proper authorization, while controlling the API exposed by MBeans.

## 19. Distinction from Spring Boot Actuator

Spring Boot Actuator provides management endpoints over channels such as HTTP and JMX depending on dependencies and exposure configuration. Certain endpoints can be exported as MBeans when Boot/Actuator's JMX mechanism is enabled.

That raises additional questions:

- Does the \`prod\` profile enable Boot's JMX exporter?
- Which endpoints are in the Actuator JMX exposure allowlist?
- Is there a manual \`@EnableMBeanExport\` alongside auto-configuration?
- Are custom MBeans exported by the application?
- Do HTTP and JMX endpoints have different exposure scopes?
- Is there separate authorization for the JMX connector?

Example configuration to check in a Spring Boot project:

\`\`\`properties
spring.jmx.enabled=true
management.endpoints.jmx.exposure.include=health,info
\`\`\`

This is an example illustrating JMX channel configuration in Spring Boot/Actuator in versions that support those properties. When upgrading Boot, check the specific version's documentation for default endpoint exposure and exact syntax.

Do not assume \`management.endpoints.web.exposure.include\` automatically applies identically to JMX.

## 20. Diagnosing Common Issues

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| \`@EnableMBeanExport\` in dev but MBean is missing | Dev profile not active, bean not selected, or exporter did not run. | Check active profiles, exporter, ObjectName, and MBeanServer. |
| MBean still exists in prod | Another exporter, Spring Boot auto-configuration, manual registration, or old context. | Check owner, \`MBeanInfo\`, \`spring.jmx.enabled\`. |
| Two exporters collide on ObjectName | Overlapping profiles, multiple contexts, or auto-config + manual config. | Assign a single owner and check registration policy. |
| \`InstanceAlreadyExistsException\` | Same name already registered in MBeanServer. | Identify which exporter/bean holds the name. |
| Activating \`prod,debug\` exports unwanted MBeans | Profile condition too broad or debug config has another exporter. | Use an allowlist and inspect at runtime. |
| Prod test still sees dev MBean | Previous test did not clean up or shares platform server. | Close contexts and use unique test ObjectNames. |
| JConsole cannot connect remotely | Connector, port, TLS, hostname/RMI, firewall. | Separate connection errors from export issues. |
| MBean exists but operations are wrong | Assembler/interface/annotation changed. | Read \`MBeanInfo\` and compare contract. |
| Configured \`spring.jmx.enabled=false\` yet MBean still exists | Manual exporter or JDK/platform MBeans. | Check the registering party; do not confuse Boot property with all JMX. |
| Bean does not disappear when profile changes at runtime | Profiles normally decide bean definitions at context creation, not as a live switch. | Reinitialize context/redeploy per process and verify lifecycle. |

## 21. Does Changing the Profile While Running Automatically Remove MBeans?

Normally **no**. Spring profiles are primarily used when creating and refreshing the ApplicationContext to decide which bean definitions are loaded. Changing an OS environment variable after the JVM has started does not automatically cause beans in the current context to vanish or re-register.

To change profiles per deployment policy, you normally need to **restart/redeploy** or build a dedicated runtime reconfiguration mechanism.

Example:

\`\`\`text
Startup:
    spring.profiles.active=dev
    -> Exporter created
    -> MBean registered

Change env var on host:
    SPRING_PROFILES_ACTIVE=prod
    -> Running JVM does not auto-rebuild context
    -> MBean is not necessarily destroyed

Restart app with prod:
    -> Spring creates new context for prod
    -> Dev-only config is not loaded
\`\`\`

If changing profiles in a multi-instance system, ensure each instance is restarted according to plan and JMX state is observed after deployment.

## 22. Designing Safe Profiles in Practice

A decision pattern:

- **dev/local:** may enable additional MBeans for diagnostics and operations in an isolated environment.
- **test:** enable JMX only when tests require it; keep distinct ObjectNames and strict cleanup.
- **staging:** enable MBeans needed to test monitoring and auth, using a configuration close to production.
- **prod:** export a small set of MBeans, favoring read-only metrics/status, with control through strictly governed operations.
- **default/unknown:** enable only via transparent allow rules; avoid accidentally enabling sensitive administrative functions.

Design pattern:

\`\`\`text
Profile selection
    |
    +-- Monitoring adapter: always available where needed
    |
    +-- Debug/control adapter: dev/staging only
    |
    +-- JMX exporter: one owner, explicit policy
    |
    +-- Remote connector: separately secured and configured
\`\`\`

If the project requires production JMX, write tests verifying that MBeans are exported with the right contract and do not accidentally expose debug operations.

## 23. Practice Exercises

### Exercise 1 — dev/staging profile

Create \`ManagementExportConfiguration\` using \`@Profile({"dev", "staging"})\` and \`@EnableMBeanExport\`. Create a \`@ManagedResource\` with one read-only attribute. Run with \`dev\`, \`staging\`, and \`prod\`.

**Goal:** prove that the profile determines whether the configuration is loaded.

### Exercise 2 — Spring Boot properties

Create \`application-dev.properties\` with \`spring.jmx.enabled=true\` and \`application-prod.properties\` with \`spring.jmx.enabled=false\`. Boot with each profile, inspect the list of application MBeans, and identify the actual exporter.

**Goal:** distinguish Boot properties from Framework annotations.

### Exercise 3 — Multiple active profiles

Run with \`spring.profiles.active=prod,debug\`. Test one configuration using \`@Profile("!prod")\` and one using \`@Profile({"dev", "staging"})\`.

**Goal:** understand profile conditional logic and the risks of negated profiles.

### Exercise 4 — ObjectName collision

In two test contexts sharing the platform server, attempt to export the same ObjectName. Observe \`InstanceAlreadyExistsException\` with \`FAIL_ON_EXISTING\`, then adjust ownership and naming.

**Goal:** see that different profiles/contexts do not automatically prevent JMX name collisions.

### Exercise 5 — Inspecting MBeanInfo

For the production monitoring adapter, verify that only read-only \`Healthy\` and \`Backlog\` exist; the \`requestPause()\` operation is absent from MBeanInfo when the control adapter is excluded by profile.

**Goal:** protect the exposed surface instead of merely checking whether the exporter exists.

### Exercise 6 — Startup/shutdown

Create an integration test running with the \`dev\` profile, confirm MBean registration; close the context and confirm unregistration. Repeat in an isolated test JVM with \`prod\`.

**Goal:** prevent MBeans from a prior profile from affecting the next profile's test.

## 24. Review Questions

**1. What is \`@EnableMBeanExport\` used for?** Enabling Spring JMX exporting support on an eligible configuration.

**2. How does \`@Profile\` affect \`@EnableMBeanExport\`?** It decides whether the configuration class carrying the annotation is included in the context when profiles match.

**3. If \`spring.jmx.enabled=false\`, is a manually configured exporter guaranteed to be disabled?** No. The Boot property primarily controls Boot auto-configuration and does not necessarily suppress manually declared beans.

**4. Does \`@EnableMBeanExport\` automatically open a remote JMX port?** No. The remote connector is a separate JVM/agent configuration.

**5. Why can \`@Profile("!prod")\` be dangerous?** Because any environment without the prod profile can match, including unrecognized environments.

**6. When changing an environment variable to another profile, do MBeans immediately unregister?** Normally no; profiles are evaluated when creating/refreshing the context.

**7. When does an ObjectName collide?** When two MBeans are registered under the same name in the same MBeanServer.

**8. Can profiles replace JMX authentication/TLS?** No. Profiles only select configuration; they do not secure the connector.

**9. How do you confirm an MBean is actually exported?** Check \`MBeanServer.isRegistered(name)\` and \`MBeanInfo\` on the right server.

**10. If production still shows MBeans even though the dev configuration was excluded, what should you check?** Other exporters, Boot auto-configuration, manual registration, context hierarchy, or JDK platform MBeans.

## 25. Summary

Combining **\`@EnableMBeanExport\`** and **\`@Profile\`** helps Spring Framework choose JMX exporting configurations appropriate for each environment. This is useful when you need additional management in dev/staging while keeping the production surface minimal.

However, in applications with multiple profiles, Spring Boot auto-configuration, or multiple ApplicationContexts, do not assume a single profile controls all MBeans. Design **one clear owner for the exporter**, inspect ObjectNames and MBeanInfo at runtime, manage cleanup across contexts, and protect remote JMX connectors with dedicated mechanisms.

## References

- Spring Framework Javadoc — \`EnableMBeanExport\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/EnableMBeanExport.html
- Spring Framework Javadoc — \`Profile\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/Profile.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Reference — Bean definition profiles: https://docs.spring.io/spring-framework/reference/core/beans/environment.html
- Spring Boot Reference — JMX: https://docs.spring.io/spring-boot/reference/actuator/jmx.html
- Spring Boot Reference — Profiles: https://docs.spring.io/spring-boot/reference/features/profiles.html
- Java SE 21 — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html