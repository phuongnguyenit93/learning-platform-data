# Avoiding Duplicate Exporters in the Same ApplicationContext — Spring Framework JMX

## Objectives

Spring Framework JMX uses MBeanExporter and AnnotationMBeanExporter to register managed beans into an MBeanServer. When a single ApplicationContext simultaneously has @EnableMBeanExport, XML context:mbean-export, @Bean MBeanExporter, or Spring Boot JMX auto-configuration, multiple exporters may attempt to register the same ObjectName into the same MBeanServer. The result can be InstanceAlreadyExistsException, startup failures, unintended registration replacement, and cleanup errors when the context closes.

This lesson helps distinguish the exporter from the MBeanServer, identify configuration paths that create exporters, design one owner per registration, restrict autodetection, verify ObjectNames, and handle startup/shutdown safely.

## 1. Distinguishing the Components

| Component | Responsibility |
|---|---|
| Spring bean | Application object that can be exposed |
| MBeanExporter | Registers and manages MBean lifecycle |
| AnnotationMBeanExporter | Reads @ManagedResource metadata and related annotations |
| MBeanServer | JMX registry containing ObjectNames and MBeans |
| ObjectName | Unique key within one MBeanServer |
| JMXConnectorServer | Opens connections to the MBeanServer for remote clients |

The same ObjectName on two different MBeanServers does not collide in the registry; the same ObjectName on one MBeanServer cannot exist as two independent registrations at the same time. Two exporters with different Spring bean names can still attempt to register the same ObjectName.

~~~text
ApplicationContext
  ├── CatalogCacheMonitor
  ├── Exporter A ── register com.example:type=Cache,name=Catalog ──┐
  └── Exporter B ── register com.example:type=Cache,name=Catalog ──┤ MBeanServer
                                                               └─ collision
~~~

## 2. Sources That Create Duplicate Exporters

An application may enable annotation export via @EnableMBeanExport, use the XML namespace context:mbean-export, manually create an AnnotationMBeanExporter or MBeanExporter, or rely on Spring Boot auto-configuration. Internal starters and test configurations may also create additional exporters. Each mechanism does not necessarily create a duplicate in every version: Spring has bean-creation conditions and infrastructure that guards bean names. You must inspect the actual ApplicationContext rather than guessing from source code alone.

The risk also appears between parent/child contexts and modules sharing the platform MBeanServer. One context may shut down while another keeps running; if exporters replace each other's registrations, safe cleanup becomes difficult.

## 3. One Registration, One Owner Principle

For each MBean, you need to know: the full ObjectName; target MBeanServer; which exporter or code registered it; which ApplicationContext owns the exporter; when it is unregistered; and which name clients use. If two exporters have overlapping responsibilities, fix the registration scope rather than enabling replacement by default.

Example of clear ownership:

~~~text
Exporter Web:   com.example.web:type=Health,name=Api
Exporter Batch: com.example.batch:type=Worker,name=Import
Exporter Core:  com.example.shared:type=Cache,name=Catalog
~~~

All three can share the platform MBeanServer when ObjectNames differ and each exporter manages only its own registrations. Do not unregister everything by domain when a context closes, because the domain does not prove ownership.

## 4. Choosing One Primary Export Strategy

### 4.1 Annotation-driven

~~~java
@Configuration
@EnableMBeanExport(defaultDomain = "com.example.ops")
class JmxConfiguration { }

@Component
@ManagedResource(objectName = "com.example.ops:type=Worker,name=Import")
class ImportWorkerMonitor {
    @ManagedAttribute
    public long getCompletedCount() { return 0L; }
}
~~~

With this approach, do not create an additional manual AnnotationMBeanExporter scanning the same set of @ManagedResource beans. If running Spring Boot and JMX auto-configuration already meets your needs, check exporter creation conditions before adding @EnableMBeanExport.

### 4.2 Explicit MBeanExporter

~~~java
@Configuration
class ExplicitJmxConfiguration {
    @Bean
    MBeanExporter exporter(WorkerStatus worker, CacheStatus cache) {
        MBeanExporter result = new MBeanExporter();
        result.setServer(ManagementFactory.getPlatformMBeanServer());
        result.setBeans(Map.of(
            "com.example.ops:type=Worker,name=Import", worker,
            "com.example.ops:type=Cache,name=Catalog", cache));
        result.setAutodetect(false);
        return result;
    }
}
~~~

Here WorkerStatus and CacheStatus must be valid MBeans or have an appropriate assembler. Disabling autodetection keeps the registration set stable, without expanding simply because a developer adds a Spring bean. For production administration requiring a stable API, explicit mapping is easy to audit.

### 4.3 Spring Boot auto-configuration

The property spring.jmx.enabled=true is used in many Spring Boot versions to conditionally enable JMX infrastructure. Do not assume with certainty which exporter bean is created without checking the Boot version and condition report. If a starter provides a manual exporter, auto-configuration conditions may back off, or the system may still end up with two export paths with different scopes. Pick a primary owner and verify empirically.

## 5. Distinguishing Duplicate Exporters from Duplicate ObjectNames

Duplicate exporters means having multiple exporters with overlapping or potentially overlapping responsibilities. Duplicate ObjectName means having at least two requests to register the same name into the same server. You can have one exporter and two beans with the same ObjectName, which still fails. You can have two exporters with disjoint ObjectName sets, which does not fail. The count of exporters by itself is not a sufficient conclusion.

### Example of duplicate ObjectName from metadata

~~~java
@Component
@ManagedResource(objectName = "com.example.ops:type=Status,name=Main")
class BillingStatus { }

@Component
@ManagedResource(objectName = "com.example.ops:type=Status,name=Main")
class InventoryStatus { }
~~~

Even with a single AnnotationMBeanExporter, both beans request the same name. Changing the exporter's defaultDomain does not change an ObjectName that is already fully specified. The solution is to choose distinct explicit names or keep only one authorized owner to expose it.

## 6. Why Registration Policy Is Not the Default Solution

An exporter can be configured to handle an already-existing name by failing, ignoring, or replacing depending on the API/version. With IGNORE_EXISTING, an expected bean may silently fail to register. With REPLACE_EXISTING, exporter B may replace A's MBean, causing A/B lifecycles to conflict. Policies handle the collision outcome; they do not cure the cause: two configuration paths or two beans claiming one ObjectName.

If the system is encountering InstanceAlreadyExistsException, trace the ObjectName, MBeanServer, and registration path causing the error before fixing. Do not wipe an entire domain and do not arbitrarily replace another module's registry entries.

## 7. Overlapping XML and JavaConfig

The following XML configuration:

~~~xml
<context:mbean-export />
~~~

may coexist with JavaConfig:

~~~java
@Configuration
@EnableMBeanExport
class AnotherJmxConfig { }
~~~

What to check is which actual bean definitions are created by the two paths, whether they register the same @ManagedResource beans, and whether errors are Spring bean name conflicts or JMX ObjectName conflicts. BeanDefinitionOverrideException belongs to the Spring container, distinct from InstanceAlreadyExistsException in the MBeanServer. When migrating XML to JavaConfig, pick one dominant exporter configuration source and remove the redundant path via controlled source changes.

## 8. Modules and Starters: Provide Management Beans, Do Not Silently Export the Whole Context

Multi-module designs are usually cleaner when application bootstrap owns the exporter and MBeanServer. The inventory, billing, and worker modules provide management adapters or annotation metadata; the application decides what gets exported. If every starter creates an exporter automatically, scanned sets easily overlap, especially when using autodetection in the same context.

For modules that require a dedicated exporter, explicitly document the enablement condition, explicit MBean list, ObjectName namespace, lifecycle, and non-overlap tests. The presence of multiple exporters must be an architectural decision, not an accidental side effect of importing configurations.

## 9. MBeanServer and defaultDomain

### Server

~~~java
@Bean
MBeanServer managementServer() {
    return ManagementFactory.getPlatformMBeanServer();
}
~~~

With a direct exporter, pass the object via exporter.setServer(managementServer). With @EnableMBeanExport, the server attribute is the name of an MBeanServer bean, for example server = "managementServer". It is not a host, port, or Service URL.

### Domain

defaultDomain is used by the naming strategy when generating ObjectNames from configuration. If a bean already has @ManagedResource(objectName = "com.example.ops:type=Cache,name=Catalog"), changing defaultDomain does not overwrite this name. Having the same defaultDomain also does not mean using the same server; server and namespace are two independent choices.

## 10. Inventorying Active Exporters

~~~java
String[] exporters = context.getBeanNamesForType(
    MBeanExporter.class, true, false);
System.out.println(Arrays.toString(exporters));
~~~

This lookup applies to the queried context; parent/child hierarchies must be inspected deliberately. allowEagerInit=false helps avoid some unnecessary initialization when you only want to inventory types. Inspect each exporter's configuration class, target server, autodetect flag, explicit bean mappings, assembler, and naming strategy.

Do not rely solely on exporter count: two independent exporters can be a valid design; conversely, one exporter can also register multiple beans with colliding ObjectNames due to misgenerated names.

## 11. Inspecting the Actual Registry

~~~java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
Set<ObjectName> names = server.queryNames(
    new ObjectName("com.example.ops:*"), null);
names.forEach(n -> System.out.println(n.getCanonicalName()));
~~~

Draw conclusions only about the server being queried. If the exporter uses a custom MBeanServer different from the connector or platform server, a successfully registered MBean may not appear here. MBeanServer.queryNames by itself does not tell you the exporter owner; combine it with logs and bean definitions.

To view exposed members:

~~~java
MBeanInfo info = server.getMBeanInfo(
    new ObjectName("com.example.ops:type=Worker,name=Import"));
for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println(operation.getName());
}
~~~

Inspect operations with side effects, readable/writable attributes, and sensitive data. Duplicate exporters not only risk collisions but can also accidentally widen the management surface.

## 12. Startup Logs and Typical Errors

| Symptom | Possible Explanation |
|---|---|
| InstanceAlreadyExistsException | ObjectName already exists in the server |
| NotCompliantMBeanException | Bean does not satisfy MBean/assembler contract |
| BeanDefinitionOverrideException | Duplicate Spring bean definition or overriding blocked |
| MBean appears then disappears | Another exporter replaced/removed registration; unclear lifecycle |
| MBean not visible in JConsole | Connector points to a different server or wrong ObjectName |
| Duplicates after reload | Old context failed to unregister or new context re-exports |

The diagnostic workflow should trace from the ObjectName in the exception to the registering exporter, target server, candidate beans, configuration path, and lifecycle history. Never "fix" it by exposing all JMX endpoints to the Internet or disabling authentication.

## 13. Testing the Configuration

~~~java
@Test
void onlyOneExporterOwnsExpectedMBean() throws Exception {
    MBeanServer server = ManagementFactory.getPlatformMBeanServer();
    ObjectName expected = new ObjectName(
        "com.example.ops:type=Worker,name=Import");

    try (AnnotationConfigApplicationContext context =
             new AnnotationConfigApplicationContext(
                 JmxConfiguration.class, ImportWorkerMonitor.class)) {
        String[] exporters =
            context.getBeanNamesForType(MBeanExporter.class);
        assertEquals(1, exporters.length);
        assertTrue(server.isRegistered(expected));
    }

    assertFalse(server.isRegistered(expected));
}
~~~

Fixtures must avoid ObjectName collisions with other tests. If tests run in parallel, use a dedicated server or non-colliding test namespaces. Do not unregister an MBean not owned by the test. Asserting there is exactly one exporter is only appropriate when the fixture's architecture truly intends one exporter; do not apply it as a universal rule.

Negative contract tests are also useful: assert no InternalService MBean exists, no unintended dangerous operations are exposed, and closing the context does not remove MBeans belonging to another parent/child context.

## 14. Parent/Child Contexts

Parent, Web child, and Batch child contexts may share the same MBeanServer. If each context owns its own exporter, namespaces and MBean sets must be separated. Closing the Web context must not unregister MBeans belonging to Batch or Parent. Do not use domain wildcards as proof of ownership; only remove registrations that the context's own exporter successfully created.

If two contexts use the same explicit ObjectName, fix the naming or coordinate the handoff during redeployment. REPLACE_EXISTING can hide collisions while making shutdown unsafe.

## 15. Runbook Before and After JMX Changes

Before deployment: inventory exporters, identify auto-configuration and XML/Java configs, list MBeans to export, decide owners, set stable ObjectNames, configure suitable server/connectors, and add startup and shutdown tests.

When encountering errors: capture the ObjectName and target MBeanServer, trace back to the registering exporter, locate duplicate beans/configs, do not blindly enable replacement, narrow the scope or remove one export path, and re-run tests.

When upgrading Spring or Boot: review auto-configuration changes, verify the condition report, bean definitions, ObjectName set, and cleanup after context refresh. Do not assume bean overriding behavior or JMX defaults remain identical across every version.

## 16. Applied Exercises

1. An application has both @EnableMBeanExport and @Bean AnnotationMBeanExporter. State the risks and how to choose one export path.
2. Spring Boot already enables JMX, and a starter adds a manual exporter. How would you inspect bean conditions and ObjectNames?
3. Two exporters manage two different domains on the same platform MBeanServer. When are they valid?
4. Why is REPLACE_EXISTING not a fix for collisions across contexts with independent lifecycles?
5. Design an integration test verifying expected MBeans are present, forbidden MBeans are absent, and registrations are removed after context.close().
6. Parent/child contexts share a server: describe how to define ownership so closing the child does not delete the parent's MBeans.

## Summary

To avoid creating duplicate exporters in the same ApplicationContext, control annotation, XML, manual exporter, and Spring Boot auto-configuration paths. One primary export mechanism is usually easiest to maintain for the same group of beans; multiple exporters should only exist when MBean sets are disjoint and lifecycles have clear owners. Never use registration policies or change defaultDomain to hide bugs. Verify via exporter bean inspection, MBeanServer registry, MBeanInfo, and startup/shutdown integration tests.
