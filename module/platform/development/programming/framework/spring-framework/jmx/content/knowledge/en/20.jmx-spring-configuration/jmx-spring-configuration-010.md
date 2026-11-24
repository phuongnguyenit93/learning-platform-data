# Migrating from XML Exporter to Java Config in Spring Framework JMX

## Learning Objectives

This lesson belongs to the **Spring configuration** section of Spring Framework JMX. After completing it, you will be able to:

- Migrate JMX configuration from XML to Java Config using \`@Configuration\` and \`@Bean\` without changing the semantics of exposed MBeans.
- Identify XML elements such as \`MBeanExporter\`, \`MBeanServer\`, \`assembler\`, \`namingStrategy\`, \`registrationPolicy\`, the \`beans\` map, and annotation-based exporting config.
- Preserve \`ObjectName\`, management interface, attributes/operations, duplicate-name handling, and container lifecycle.
- Distinguish explicit \`MBeanExporter\` from \`@EnableMBeanExport\` and \`AnnotationMBeanExporter\`.
- Verify the migration using \`MBeanServer\`, \`MBeanInfo\`, JConsole, and integration tests.
- Plan a migration with rollback capability, avoiding two exporters registering the same \`ObjectName\`.

## 1. Why Migrate?

Many older Spring Framework projects use \`applicationContext.xml\` or \`spring-jmx.xml\` to declare JMX management beans. As a codebase gradually transitions to Java Config, XML bean definitions can be replaced by \`@Bean\` factory methods, enabling type-safe Java dependency management, IDE navigation, and configuration closer to implementation.

Example legacy configuration:

\`\`\`xml
<bean id="mBeanExporter"
      class="org.springframework.jmx.export.MBeanExporter">
    <property name="beans">
        <map>
            <entry key="com.example.jobs:type=JobMonitor,name=primary"
                   value-ref="jobMonitor"/>
        </map>
    </property>
</bean>
\`\`\`

An equivalent Java Config in terms of goal:

\`\`\`java
@Bean
public MBeanExporter mBeanExporter(JobMonitor jobMonitor) {
    MBeanExporter exporter = new MBeanExporter();
    exporter.setBeans(Map.of(
            "com.example.jobs:type=JobMonitor,name=primary",
            jobMonitor));
    return exporter;
}
\`\`\`

The essence of migration is **preserving the runtime management contract**, not merely rewriting syntax from XML to Java. Monitoring tools depend on \`ObjectName\`, attribute names, operation signatures, and the JMX endpoint/server. Accidentally altering any of these factors can break dashboards or operational actions.

## 2. Architecture Before and After Migration

\`\`\`text
Before:
  XML BeanDefinitions
      |
      +-- jobMonitor
      +-- mBeanServer
      +-- mBeanExporter
             |
             +-- ObjectName -> jobMonitor
             v
          MBeanServer

After:
  @Configuration class
      |
      +-- @Bean JobMonitor
      +-- @Bean MBeanServer
      +-- @Bean MBeanExporter
             |
             +-- ObjectName -> jobMonitor
             v
          MBeanServer
\`\`\`

Both paths ultimately configure Spring beans. Java Config does not eliminate \`MBeanExporter\` or \`MBeanServer\`; it only changes how they are declared and wired.

You also do not have to migrate all XML in one shot. Spring can combine Java Config with XML via \`@ImportResource\`, though when migrating the JMX portion you must identify **which exporter is active** to avoid duplicate registration names.

## 3. Configuration Parts to Inventory Before Migrating

An important mapping table:

| In XML | In Java Config | What Must Be Preserved |
| --- | --- | --- |
| \`<bean id="jobMonitor" class="..."/>\` | \`@Bean JobMonitor jobMonitor()\` | Same managed object/lifecycle |
| \`<bean ... MBeanExporter>\` | \`@Bean MBeanExporter mBeanExporter(...)\` | One appropriate exporter |
| \`<property name="beans"><map>...\` | \`exporter.setBeans(Map.of(...))\` | Exact \`ObjectName\` keys |
| \`<property name="server" ref="..."/>\` | \`exporter.setServer(server)\` | Same \`MBeanServer\` |
| \`<property name="assembler" ref="..."/>\` | \`exporter.setAssembler(assembler)\` | Same attributes/operations |
| \`<property name="namingStrategy" ref="..."/>\` | \`exporter.setNamingStrategy(strategy)\` | Final JMX names |
| \`<property name="registrationPolicy" .../>\` | \`setRegistrationPolicy(...)\` | Duplicate-name handling |
| \`<context:mbean-export/>\` | \`@EnableMBeanExport\` | Matching annotation detection mode |
| \`<context:component-scan .../>\` | \`@ComponentScan\` or \`@Bean\` | Beans to export still present in context |

Do not assume two configurations are automatically equivalent if XML uses a custom assembler, naming strategy, or autodetection. In such cases, the migration must port **all related configuration**, not just \`beans\`.

## 4. Standard MBean Example for Migration

Suppose the system exposes a \`JobMonitor\` so JMX tools can read processed job counts.

**JobMonitorMBean.java**

\`\`\`java
package com.example.jmx;

public interface JobMonitorMBean {
    int getProcessedCount();
    boolean isEnabled();
    void setEnabled(boolean enabled);
    void reset();
}
\`\`\`

**JobMonitor.java**

\`\`\`java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicInteger;

public class JobMonitor implements JobMonitorMBean {
    private final AtomicInteger processed = new AtomicInteger();
    private volatile boolean enabled = true;

    public void recordProcessedJob() {
        if (enabled) {
            processed.incrementAndGet();
        }
    }

    @Override
    public int getProcessedCount() {
        return processed.get();
    }

    @Override
    public boolean isEnabled() {
        return enabled;
    }

    @Override
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @Override
    public void reset() {
        processed.set(0);
    }
}
\`\`\`

This is a Standard MBean: the \`JobMonitorMBean\` interface has the matching suffix for the \`JobMonitor\` implementation. When exported, JMX exposes attribute \`ProcessedCount\`, read/write attribute \`Enabled\`, and operation \`reset\`.

Method \`recordProcessedJob()\` is not in the Standard MBean interface, so it is not automatically exposed via that interface. This keeps the management API stable when switching configuration styles.

## 5. Complete XML Configuration Before Migration

A legacy example explicitly declaring the platform server and exporter:

\`\`\`xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
         http://www.springframework.org/schema/beans
         https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="jobMonitor"
          class="com.example.jmx.JobMonitor"/>

    <bean id="platformMBeanServer"
          class="org.springframework.jmx.support.MBeanServerFactoryBean">
        <property name="locateExistingServerIfPossible" value="true"/>
    </bean>

    <bean id="mBeanExporter"
          class="org.springframework.jmx.export.MBeanExporter">

        <property name="server" ref="platformMBeanServer"/>

        <property name="beans">
            <map>
                <entry
                    key="com.example.jobs:type=JobMonitor,name=primary"
                    value-ref="jobMonitor"/>
            </map>
        </property>
    </bean>
</beans>
\`\`\`

This configuration only illustrates how XML declares a server and exporter. \`MBeanServerFactoryBean\` in locate-existing-server mode may find an existing suitable server or create a new one if none exists; it **does not guarantee in every environment** that it selects the exact platform \`MBeanServer\`. To preserve the right server during migration, verify the actual server used beforehand.

If the legacy XML already had a different \`MBeanServer\` bean or the application runs inside an application server providing a JMX registry, use the same expected server instead of mechanically replacing it with the platform server.

## 6. Equivalent Java Config

**JmxConfiguration.java**

\`\`\`java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxConfiguration {

    @Bean
    public JobMonitor jobMonitor() {
        return new JobMonitor();
    }

    @Bean
    public MBeanServer platformMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter mBeanExporter(
            JobMonitor jobMonitor,
            MBeanServer platformMBeanServer) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(platformMBeanServer);
        exporter.setBeans(Map.of(
                "com.example.jobs:type=JobMonitor,name=primary",
                jobMonitor));
        return exporter;
    }
}
\`\`\`

Compared to XML, every dependency is injected via factory method parameters. Spring knows \`mBeanExporter\` depends on \`jobMonitor\` and \`platformMBeanServer\`, enabling intentional container lifecycle management.

**Another point to control:** this Java Config selects the platform server **explicitly**. If the legacy XML used a different automatically located server, this is a behavior change. When migration requires strict equivalence, inject the exact \`MBeanServer\` the application uses rather than switching merely for JConsole convenience.

## 7. Running the Java Config ApplicationContext and Verifying the MBean

\`\`\`java
package com.example.jmx;

import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class JmxMigrationDemo {
    public static void main(String[] args) throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                JmxConfiguration.class)) {

            JobMonitor jobMonitor = context.getBean(JobMonitor.class);
            MBeanServer server = context.getBean(MBeanServer.class);
            ObjectName name = new ObjectName(
                    "com.example.jobs:type=JobMonitor,name=primary");

            System.out.println("Registered: " + server.isRegistered(name));

            jobMonitor.recordProcessedJob();
            jobMonitor.recordProcessedJob();

            System.out.println(
                    "ProcessedCount via JMX: "
                    + server.getAttribute(name, "ProcessedCount"));

            System.out.println("PID: " + ProcessHandle.current().pid());
            System.in.read(); // Keep demo running to inspect with JConsole.
        }
    }
}
\`\`\`

Expected output is \`Registered: true\` and \`ProcessedCount via JMX: 2\`. Reading \`ProcessedCount\` through \`MBeanServer\` proves the MBean is genuinely exported and reflects the same Spring bean.

JConsole can attach to the application PID, open the **MBeans** tab, and locate the \`com.example.jobs\` domain. Existing management tools only need the \`ObjectName\` and management interface preserved to continue using the same names and metadata, provided the JMX endpoint is unchanged.

## 8. Do Not Run XML Exporter and Java Config Exporter Simultaneously

This is the most common migration mistake. A system may import legacy XML while the new Java Config is also loaded:

\`\`\`java
@Configuration
@ImportResource("classpath:spring-jmx.xml")
public class AppConfiguration {
    // If an @Bean MBeanExporter is also declared for the same ObjectName,
    // both exporters may attempt to register duplicates.
}
\`\`\`

If two exporters register the same \`ObjectName\` in one \`MBeanServer\`, the new registration can fail with \`InstanceAlreadyExistsException\`. If \`IGNORE_EXISTING\` is enabled, startup may succeed while the new exporter is silently skipped, leaving JMX clients reading the old instance. With \`REPLACE_EXISTING\`, it can replace the object that monitoring tools are actively using.

Proper migration sequence:

1. Identify the old exporter in XML and the names it registers.
2. Create the corresponding Java Config without **enabling both registrations in parallel** at runtime.
3. In an isolated test environment, replace the XML exporter with the Java Config exporter.
4. Verify \`ObjectName\`, \`MBeanInfo\`, attributes/operations, and lifecycle.
5. Once stable, remove or stop importing the old exporter definition.

If you need to keep other XML bean definitions, split out \`spring-jmx.xml\` so you can stop importing the export portion first without rewriting the entire system configuration at once.

## 9. Migrating registrationPolicy

In XML, you might have:

\`\`\`xml
<property name="registrationPolicy" value="FAIL_ON_EXISTING"/>
\`\`\`

In Java Config:

\`\`\`java
import org.springframework.jmx.support.RegistrationPolicy;

exporter.setRegistrationPolicy(
        RegistrationPolicy.FAIL_ON_EXISTING);
\`\`\`

Policies to know:

| Policy | If \`ObjectName\` Already Exists | Migration Implication |
| --- | --- | --- |
| \`FAIL_ON_EXISTING\` | Fails with a registration error | Catches overlapping XML/Java configs |
| \`IGNORE_EXISTING\` | Keeps the existing MBean | Can hide that the new exporter is inactive |
| \`REPLACE_EXISTING\` | Replaces the old MBean | Can cause unexpected ownership changes |

During migration, \`FAIL_ON_EXISTING\` is usually helpful in verification phases because duplicate errors are not masked. However, if legacy XML intentionally used another policy by design, an equivalent migration must preserve that behavior or change it deliberately with an impact assessment.

Older Spring Framework versions may use integer constants like \`REGISTRATION_FAIL_ON_EXISTING\` or different setters. Check your project version's API before copying verbatim.

## 10. Migrating MBeanInfoAssembler and the Management Interface

Some XML exporters do not export Standard MBeans, instead exporting POJOs through an \`MBeanInfoAssembler\`. In that case, migrating only \`setBeans\` is not enough: omitting the assembler can alter the exposed attributes/operations.

Example legacy XML using \`MethodNameBasedMBeanInfoAssembler\`:

\`\`\`xml
<bean id="jobAssembler"
      class="org.springframework.jmx.export.assembler.MethodNameBasedMBeanInfoAssembler">
    <property name="managedMethods">
        <list>
            <value>getProcessedCount</value>
            <value>reset</value>
        </list>
    </property>
</bean>

<bean id="mBeanExporter"
      class="org.springframework.jmx.export.MBeanExporter">
    <property name="assembler" ref="jobAssembler"/>
    <property name="beans">
        <map>
            <entry key="com.example.jobs:type=JobAdmin,name=primary"
                   value-ref="jobAdmin"/>
        </map>
    </property>
</bean>
\`\`\`

Equivalent Java Config:

\`\`\`java
import org.springframework.jmx.export.assembler.MethodNameBasedMBeanInfoAssembler;

@Bean
public MethodNameBasedMBeanInfoAssembler jobAssembler() {
    MethodNameBasedMBeanInfoAssembler assembler =
            new MethodNameBasedMBeanInfoAssembler();
    assembler.setManagedMethods("getProcessedCount", "reset");
    return assembler;
}

@Bean
public MBeanExporter mBeanExporter(
        JobAdmin jobAdmin,
        MBeanServer platformMBeanServer,
        MethodNameBasedMBeanInfoAssembler jobAssembler) {

    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(platformMBeanServer);
    exporter.setAssembler(jobAssembler);
    exporter.setBeans(Map.of(
            "com.example.jobs:type=JobAdmin,name=primary",
            jobAdmin));
    return exporter;
}
\`\`\`

This is **an alternative configuration** to the Standard MBean exporter in section 6; do not declare two \`@Bean\` methods both named \`mBeanExporter\` in the same configuration. The example also assumes \`JobAdmin\` is an existing application POJO with the two listed methods.

If the XML uses \`InterfaceBasedMBeanInfoAssembler\` or \`MetadataMBeanInfoAssembler\`, migrate the matching interface metadata or attribute source and naming strategy accordingly. Then read \`MBeanInfo\` to confirm the contract has not unintentionally expanded or narrowed.

## 11. Migrating namingStrategy

In XML you might have:

\`\`\`xml
<property name="namingStrategy" ref="jmxNamingStrategy"/>
\`\`\`

The equivalent Java Config passes the strategy via constructor/factory \`@Bean\` parameter and calls:

\`\`\`java
exporter.setNamingStrategy(jmxNamingStrategy);
\`\`\`

Common strategies:

- \`KeyNamingStrategy\`: resolves names via configuration keys/mappings.
- \`MetadataNamingStrategy\`: reads \`ObjectName\` from metadata such as \`@ManagedResource\`.
- \`IdentityNamingStrategy\`: distinguishes instances by runtime identity.

To avoid breaking existing dashboards, preserve the exact full \`ObjectName\` including domain and key properties. A migration that accidentally replaces \`name=primary\` with a class- or bean-name-derived name can break monitoring target lookups.

Keys such as \`type\`, \`name\`, \`pool\`, and \`tenant\` are project conventions, not Java requirements. When using attributes containing special characters, construct valid \`ObjectName\` values and quote/escape properly.

## 12. Migrating XML Annotation Exporter to @EnableMBeanExport

If the legacy XML enabled annotation exporting:

\`\`\`xml
<context:mbean-export
    xmlns:context="http://www.springframework.org/schema/context"
    default-domain="com.example.management"/>
\`\`\`

then the Java Config direction is usually:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport(defaultDomain = "com.example.management")
public class JmxAnnotationConfiguration {
}
\`\`\`

A managed bean can be annotated:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
        objectName = "com.example.management:type=CacheAdmin,name=primary")
public class CacheAdmin {

    @ManagedAttribute
    public int getCacheSize() {
        return 10;
    }

    @ManagedOperation
    public void resetCacheStatistics() {
        // Management logic...
    }
}
\`\`\`

For Spring JMX autodetection to find the class, the object must be registered as an \`ApplicationContext\` bean via \`@Bean\`, \`@Component\` + component scan, or an appropriate mechanism. \`@ManagedResource\` does not replace \`@Component\`.

A complete configuration:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport(defaultDomain = "com.example.management")
public class JmxAnnotationConfiguration {

    @Bean
    public CacheAdmin cacheAdmin() {
        return new CacheAdmin();
    }
}
\`\`\`

If the XML uses \`<context:mbean-export/>\` with specific assembler/naming options, verify the equivalent Java annotation support attributes in your actual Spring version; do not assume every XML attribute has an identical Java annotation attribute.

**Important:** Do not switch an explicit exporter to \`@EnableMBeanExport\` without checking which beans are discovered. Annotation mode and explicit \`setBeans\` may export different sets of objects.

## 13. Migrating MBeanServer and Server Ownership

XML often references an \`MBeanServerFactoryBean\` or a server created outside Spring:

\`\`\`xml
<bean id="applicationMBeanServer"
      class="org.springframework.jmx.support.MBeanServerFactoryBean">
    <property name="defaultDomain" value="com.example.management"/>
    <property name="locateExistingServerIfPossible" value="false"/>
</bean>
\`\`\`

Java Config:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.support.MBeanServerFactoryBean;

@Configuration
public class CustomServerConfiguration {

    @Bean(name = "applicationMBeanServer")
    public MBeanServerFactoryBean applicationMBeanServer() {
        MBeanServerFactoryBean factory = new MBeanServerFactoryBean();
        factory.setDefaultDomain("com.example.management");
        factory.setLocateExistingServerIfPossible(false);
        return factory;
    }
}
\`\`\`

\`MBeanServerFactoryBean\` is a Spring \`FactoryBean\`; other beans inject the \`MBeanServer\` produced by the factory. When the factory creates a dedicated server, Spring manages the factory's lifecycle to release the server responsibly. If the server is borrowed from the JVM or another container, closing the Spring context does not mean Spring owns releasing that server.

During migration, preserve the distinction between a **borrowed server** and an **application-created server**. Switching from a custom server to the platform server can change the registry scope and how JConsole/JMX connectors access it, even if \`ObjectName\` stays the same.

## 14. Incremental Migration While Other XML Remains

For large projects, migration can proceed in phases:

**Phase 1 — Keep business XML, replace JMX config.** Create \`JmxConfiguration\` with the new exporter; remove only the old exporter bean from XML while keeping remaining required XML bean definitions.

**Phase 2 — Unify bean references.** If \`JobMonitor\` already lives in XML, Java Config can inject that bean without creating a second \`@Bean JobMonitor\`:

\`\`\`java
@Bean
public MBeanExporter mBeanExporter(
        JobMonitor existingMonitor,
        MBeanServer existingServer) {
    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(existingServer);
    exporter.setBeans(Map.of(
            "com.example.jobs:type=JobMonitor,name=primary",
            existingMonitor));
    return exporter;
}
\`\`\`

This avoids the situation where JMX manages a new instance while business logic still uses the old XML instance.

**Phase 3 — Migrate remaining bean definitions.** Replace \`<bean>\` with \`@Bean\` or component scanning, while preserving \`@Qualifier\`, scopes, init/destroy callbacks, and dependency injection if those settings affect runtime behavior.

**Phase 4 — Remove legacy JMX XML.** Once no JMX config from the old XML is used, stop importing the old file. Verify there is no hidden exporter bean from another auto-configuration.

You do not have to migrate the whole system at once to change how JMX is declared, but you do need **a single owner per registration**.

## 15. Spring Boot: Avoid Overriding or Colliding with Auto-Configuration

When a Spring Boot project is configured to enable JMX, Boot can create export infrastructure based on dependencies and properties like \`spring.jmx.enabled\`, with version-dependent behavior. If you add a manual \`MBeanExporter\` via \`@Configuration\`, you may accidentally introduce a second exporter.

Before migrating in Spring Boot:

1. Check the Boot version and JMX auto-configuration status.
2. Identify the active exporter and exported beans.
3. Inventory the \`ObjectName\` values that must be preserved.
4. Decide whether to use auto-config/annotations or a manual exporter, without overlapping names.
5. Run integration tests with the application's actual profiles and environment.

Do not assume adding \`@EnableMBeanExport\` is mandatory in every Spring Boot application. In plain Spring Framework, that annotation activates annotation-driven exporting, whereas in Boot you must account for existing auto-configuration.

## 16. Integration Testing to Prove XML and Java Config Equivalence

A reliable migration verifies final behavior, not just bean declaration structure.

Java Config test example:

\`\`\`java
package com.example.jmx;

import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

class JmxMigrationTest {

    @Test
    void javaConfigExportsExpectedMBeanContract() throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                JmxConfiguration.class)) {

            MBeanServer server = context.getBean(MBeanServer.class);
            JobMonitor monitor = context.getBean(JobMonitor.class);
            ObjectName name = new ObjectName(
                    "com.example.jobs:type=JobMonitor,name=primary");

            assertTrue(server.isRegistered(name));

            MBeanInfo info = server.getMBeanInfo(name);

            assertTrue(java.util.Arrays.stream(info.getAttributes())
                    .anyMatch(a -> "ProcessedCount".equals(a.getName())));

            assertTrue(java.util.Arrays.stream(info.getOperations())
                    .anyMatch(o -> "reset".equals(o.getName())));

            monitor.recordProcessedJob();

            assertEquals(
                    1, server.getAttribute(name, "ProcessedCount"));

            server.invoke(name, "reset",
                    new Object[0], new String[0]);

            assertEquals(
                    0, server.getAttribute(name, "ProcessedCount"));
        }
    }
}
\`\`\`

The test verifies registration, attributes, and operations under the new configuration. To prove **equivalence with XML**, run the old and new configurations in two isolated test fixtures, retrieve \`MBeanInfo\`, and compare attribute names/types/access flags, operation signatures, and the full set of \`ObjectName\` values the application intends to expose.

Avoid starting XML and Java exporters with the same names on the same platform \`MBeanServer\` when tests run in parallel. Use two isolated MBean servers or run sequentially with thorough cleanup. When runtime data differs, compare contracts and defined behaviors rather than forcing every metric to hold identical values.

## 17. Behavior-Based Migration Checklist

| Item | Before/After Migration Check |
| --- | --- |
| MBean list | All expected \`ObjectName\` values remain present |
| JMX server | Exporter still uses the right server/connector |
| Metadata | Attributes, operations, types, and signatures match |
| Naming | Domain and key properties unchanged unless intentional |
| Assembler | No extra sensitive methods exposed, no required methods lost |
| Registration policy | Expected duplicate-name handling preserved |
| Managed instance | MBean references the exact Spring bean used by business logic |
| Lifecycle | Initialization, unregistration, and shutdown behave properly |
| Autodetection | No unintended extra beans exported or needed beans missed |
| Client | JConsole/dashboards/automation still see the right MBeans |
| Dual configuration | No two exporters own the same \`ObjectName\` |
| Rollback | Can revert to XML config cleanly without double registration |

## 18. Common Migration Errors

### Context fails to initialize due to duplicate names

**Cause:** the XML exporter is still loaded alongside the new Java exporter.

**Resolution:** disable the old definition in the new deployment instead of changing registration policy to hide the problem. Establish one owner per \`ObjectName\`.

### JConsole shows the MBean, but values differ

**Cause:** Java Config created a new bean instance, the exporter uses a different server, or the naming strategy changed.

**Resolution:** verify the injected Spring bean, server, and MBean identity in the registry. A valid JMX name does not guarantee the right target instance.

### Missing some attributes/operations

**Cause:** the migration dropped an assembler or annotation export setting, or the management interface differs.

**Resolution:** inspect \`MBeanInfo\` on both old and new configurations; port the exact \`MBeanInfoAssembler\`, interface, or metadata configuration.

### MBean not visible in client

**Cause:** the exporter uses a custom server while the client inspects the platform server, or the JMX name differs.

**Resolution:** check \`isRegistered\` on the server injected into the exporter; verify connector/endpoint alignment before altering config.

### Closing old context makes new MBean disappear

**Cause:** unclear ownership, replacement policy, or two exporters using the same name.

**Resolution:** prevent overlapping registrations, clarify lifecycle, create isolated test contexts/servers, and verify unregistration behavior.

### Tests pass but production fails

**Cause:** runtime environment includes an application server JMX registry, proxies/AOP, multiple contexts, or Boot auto-configuration differing from tests.

**Resolution:** run integration tests under production-like profiles; inspect exporter and server lists before deployment.

## 19. Security and Operations During Migration

A JMX migration can cause new methods to appear if the assembler or annotation autodetection changes. This is a management-surface change, not merely a config file edit.

- Do not expose secrets, customer data, or sensitive business methods via JMX.
- For operations such as \`reset\`, \`clearCache\`, \`reload\`, or \`shutdown\`, verify preconditions, repeatability, and runtime impact.
- If changing \`MBeanServer\` or connectors, preserve or strengthen authentication, encryption, and network restrictions for remote JMX.
- Record the migration timestamp and any intentional \`ObjectName\` changes so dashboards/alerts can be updated.
- With multiple instances/JVMs, \`ObjectName\` is unique only per server; monitoring needs to identify the JVM/endpoint as well.
- Use integration tests to assert **no extra methods** are exposed, not merely that the MBean is registered.

## 20. Practice Exercises

**Exercise 1 — Basic migration.** Create \`spring-jmx.xml\` with \`JobMonitor\` and \`MBeanExporter\`, and verify \`ProcessedCount\` via JMX. Then migrate to \`JmxConfiguration\` keeping the exact \`ObjectName\`.

**Exercise 2 — Incremental migration.** Keep \`JobMonitor\` as an XML bean while declaring the exporter in Java Config. Inject the existing bean; prove JMX reads the exact business instance.

**Exercise 3 — Assembler.** Create a POJO with \`getCount()\`, \`reset()\`, and \`deleteAll()\`. Configure \`MethodNameBasedMBeanInfoAssembler\` in XML, then migrate the assembler to \`@Bean\`. Compare metadata and confirm \`deleteAll()\` is not exposed.

**Exercise 4 — Dual configuration.** Intentionally run two exporters with the same \`ObjectName\` in an isolated test, observe the failure, and fix it by enabling only one exporter. Explain why \`IGNORE_EXISTING\` is not a proper migration solution.

**Exercise 5 — Annotation mode.** Replace \`<context:mbean-export/>\` with \`@EnableMBeanExport\`, keeping \`@ManagedResource\` beans. Check exactly which beans are autodetected and which methods are exposed.

**Exercise 6 — Rollback.** Design two deployment configurations differing only in Java vs. XML wiring, never active together. Verify switching back does not alter full \`ObjectName\` or the management contract.

## Conclusion

**Migrating from an XML exporter to Java Config** in Spring Framework JMX is more than replacing \`<bean>\` with \`@Bean\`. The goal is preserving the path **Spring-managed object → MBeanExporter → MBeanServer → JMX ObjectName** and the contract used by existing clients. During migration, preserve the exact managed instance, server, naming strategy, assembler, registration policy, and lifecycle; avoid two exporters registering the same name. Verify the migration against the registry and \`MBeanInfo\`, not merely by checking that the application context starts.
