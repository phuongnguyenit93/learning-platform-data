# Testing Annotation Scanning in ApplicationContext

## Learning Objectives

In Spring Framework JMX, adding \`@ManagedResource\` to a class does not prove that the class has been registered as an MBean. After this lesson, you will be able to write an integration test that creates a real \`ApplicationContext\`, enables annotation-based JMX export, verifies \`ObjectName\` in \`MBeanServer\`, inspects exposed attributes and operations, and confirms that beans without management annotations are not exported unexpectedly.

You will also understand the differences between **component scanning**, **JMX autodetection**, **metadata assembly**, and **MBean registration**; and know how to isolate the JMX server so tests do not depend on JVM state or other tests.

## 1. What Steps Does "Annotation Scanning" Actually Include?

There are two kinds of discovery in an application using Spring JMX:

1. **Spring component scan** finds classes annotated with \`@Component\`, \`@Service\`, \`@Repository\`, or \`@Controller\`, creating bean definitions and Spring beans.
2. **JMX annotation autodetection** finds eligible beans in \`ApplicationContext\` (especially those carrying \`@ManagedResource\`), after which \`AnnotationMBeanExporter\` or an equivalent configuration constructs management metadata and registers them into \`MBeanServer\`.

These are two distinct stages. For instance, Spring JMX's \`@ManagedResource\` does not automatically replace \`@Component\` to register a bean in the container.

Expected execution chain:

\`\`\`text
Class on classpath
       |
       | @ComponentScan finds @Component
       v
Spring bean in ApplicationContext
       |
       | @EnableMBeanExport / AnnotationMBeanExporter
       | detects @ManagedResource
       v
JMX metadata from @ManagedAttribute / @ManagedOperation
       |
       | registers with MBeanServer
       v
ObjectName appears in registry
       |
       | MBeanServer.isRegistered/getMBeanInfo/getAttribute/invoke
       v
Integration test evidence
\`\`\`

A test using only \`context.containsBean("orderMetrics")\` checks the Spring bean creation stage and **does not prove JMX export**. A test using only reflection to check annotations also does not prove the MBean server registered the object.

## 2. Scope and Outcomes to Prove

Consider an application with \`OrderMetrics\`, marked with \`@ManagedResource\`, having one attribute and one operation. The test must prove three things:

- **Positive case:** Spring creates the bean, the exporter finds it, and the JMX registry has the right \`ObjectName\`.
- **Metadata case:** The MBean exposes the \`CompletedCount\` attribute and \`resetStatistics\` operation; business methods are not exposed.
- **Negative case:** An ordinary bean without \`@ManagedResource\` is not automatically exported to JMX merely because it resides in \`ApplicationContext\`.

Additionally, test lifecycle behavior: an MBean created by the context/exporter is removed when the context closes, provided no third party uses the same name or another replacement policy alters ownership.

The hands-on example uses **plain Spring Framework** and JUnit Jupiter, without requiring Spring Boot. It runs on Java 17+; examples fit Spring Framework 6.x and JDK 21.

## 3. Creating a Class with @ManagedResource

**OrderMetrics.java**

\`\`\`java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicLong;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
        objectName = "com.example.jmx:type=OrderMetrics,name=primary",
        description = "Order processing counters")
public class OrderMetrics {

    private final AtomicLong completed = new AtomicLong();

    public void recordCompleted() {
        completed.incrementAndGet();
    }

    @ManagedAttribute(description = "Number of completed orders")
    public long getCompletedCount() {
        return completed.get();
    }

    @ManagedOperation(description = "Reset completed counter")
    public void resetStatistics() {
        completed.set(0);
    }
}
\`\`\`

Role of each annotation:

| Annotation | Effect |
| --- | --- |
| \`@Component\` | Allows \`@ComponentScan\` to register \`OrderMetrics\` as a Spring bean |
| \`@ManagedResource\` | Marks the class as a managed object for the JMX annotation exporter mechanism |
| \`@ManagedAttribute\` | Exposes \`getCompletedCount()\` as the \`CompletedCount\` attribute |
| \`@ManagedOperation\` | Exposes \`resetStatistics()\` as an operation |
| Unannotated \`recordCompleted()\` | Business method not exported as an operation by default by the annotation assembler |

Inside Spring, this class can be injected into business services to record figures. JMX will observe the **same instance** if the exporter exports the Spring-managed bean.

## 4. Creating a Bean That Should Not Be JMX-Autodetected

**InternalService.java**

\`\`\`java
package com.example.jmx;

import org.springframework.stereotype.Component;

@Component
public class InternalService {

    public String internalStatus() {
        return "internal-only";
    }

    public void clearInternalState() {
        // Internal logic, not intended for JMX.
    }
}
\`\`\`

This class has \`@Component\` so it will be registered in \`ApplicationContext\`. However, it has no \`@ManagedResource\` or JMX MBean contract. When using the annotation exporter with appropriate defaults, \`InternalService\` is not a managed resource selected for exposure.

Such a negative case helps avoid the misconception that "Spring scanned the bean" means "JMX exported every public method".

## 5. Creating an ApplicationContext Configuration for Testing

To avoid depending on the JVM's platform \`MBeanServer\` and other tests, you can create an isolated MBean server for the test context.

**JmxTestConfiguration.java**

\`\`\`java
package com.example.jmx;

import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;
import org.springframework.jmx.support.MBeanServerFactoryBean;

@Configuration
@ComponentScan(basePackageClasses = {
        OrderMetrics.class,
        InternalService.class
})
@EnableMBeanExport(server = "testMBeanServer")
public class JmxTestConfiguration {

    @Bean
    public MBeanServer testMBeanServer() throws Exception {
        MBeanServerFactoryBean factory = new MBeanServerFactoryBean();
        factory.setDefaultDomain("test.spring.jmx");
        factory.afterPropertiesSet();
        return factory.getObject();
    }
}
\`\`\`

\`@ComponentScan\` scans classes in the package, \`@EnableMBeanExport\` enables exporting annotated MBeans, and \`server = "testMBeanServer"\` explicitly selects the JMX server for the exporter to use.

**Note on test server lifecycle:** \`MBeanServerFactoryBean\` manages creating and releasing the server itself. For simple tests, instead of creating \`MBeanServerFactoryBean\` inside a factory method and discarding the reference, you can define the factory bean managed directly by Spring:

\`\`\`java
@Bean(name = "testMBeanServer")
public MBeanServerFactoryBean testMBeanServerFactory() {
    MBeanServerFactoryBean factory = new MBeanServerFactoryBean();
    factory.setDefaultDomain("test.spring.jmx");
    factory.setLocateExistingServerIfPossible(false);
    return factory;
}
\`\`\`

With this approach, Spring invokes the lifecycle of \`MBeanServerFactoryBean\` and injects its produced \`MBeanServer\` into the exporter. This is the preferred choice in tests. **Choose one of the two ways** to declare the \`testMBeanServer\` bean; do not leave both methods with the same bean name in one configuration.

To keep the example easy to apply, the JUnit section below uses a \`@Bean\` configuration returning \`MBeanServerFactoryBean\` — the Spring container manages its lifecycle directly.

**Complete configuration used for the test:**

\`\`\`java
package com.example.jmx;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;
import org.springframework.jmx.support.MBeanServerFactoryBean;

@Configuration
@ComponentScan(basePackageClasses = {
        OrderMetrics.class,
        InternalService.class
})
@EnableMBeanExport(server = "testMBeanServer")
public class JmxTestConfiguration {

    @Bean(name = "testMBeanServer")
    public MBeanServerFactoryBean testMBeanServer() {
        MBeanServerFactoryBean factory = new MBeanServerFactoryBean();
        factory.setDefaultDomain("test.spring.jmx");
        factory.setLocateExistingServerIfPossible(false);
        return factory;
    }
}
\`\`\`

The test configuration should live in a package containing only the illustrative components. In a real project, you can use a dedicated test package or a \`@ComponentScan\` with filters selecting only the classes under test to avoid scanning unrelated beans.

## 6. Writing a JUnit Test Checking the Real Registry

Instead of mocking \`MBeanServer\`, the integration test should create an \`AnnotationConfigApplicationContext\` and inspect the real JMX registry.

**JmxAnnotationScanTest.java**

\`\`\`java
package com.example.jmx;

import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

class JmxAnnotationScanTest {

    private static final String METRICS_NAME =
            "com.example.jmx:type=OrderMetrics,name=primary";

    @Test
    void annotatedBeanIsExportedWithExpectedMetadata() throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                JmxTestConfiguration.class)) {

            assertNotNull(context.getBean(OrderMetrics.class));
            assertNotNull(context.getBean(InternalService.class));

            MBeanServer server = context.getBean(
                    "testMBeanServer", MBeanServer.class);
            ObjectName metricsName = new ObjectName(METRICS_NAME);

            assertTrue(server.isRegistered(metricsName),
                    "Annotated OrderMetrics must be registered");

            MBeanInfo info = server.getMBeanInfo(metricsName);

            assertTrue(
                    java.util.Arrays.stream(info.getAttributes())
                            .anyMatch(a -> "CompletedCount".equals(a.getName())),
                    "Expected CompletedCount attribute");

            assertTrue(
                    java.util.Arrays.stream(info.getOperations())
                            .anyMatch(o -> "resetStatistics".equals(o.getName())),
                    "Expected resetStatistics operation");

            assertFalse(
                    java.util.Arrays.stream(info.getOperations())
                            .anyMatch(o -> "recordCompleted".equals(o.getName())),
                    "Unannotated method must not be exported");

            OrderMetrics metrics = context.getBean(OrderMetrics.class);
            metrics.recordCompleted();

            assertEquals(1L,
                    server.getAttribute(metricsName, "CompletedCount"));

            server.invoke(
                    metricsName, "resetStatistics",
                    new Object[0], new String[0]);

            assertEquals(0L,
                    server.getAttribute(metricsName, "CompletedCount"));
        }
    }
}
\`\`\`

The test verifies from multiple angles:

- The beans exist in the Spring context.
- \`MBeanServer\` has the expected registration name.
- MBean metadata reflects the Spring annotations.
- Values read via JMX reflect **the exact bean** updated by the application.
- The exposed operation can be invoked via JMX and affects that instance.
- Public methods without JMX annotations are not exported as operations.

This is an integration test of the "scan → exporter → MBeanServer" path, rather than merely checking annotations via reflection.

## 7. Testing the Negative Case: Ordinary Beans Are Not Exported

An assertion should verify that the registry does not contain a name representing \`InternalService\`:

\`\`\`java
@Test
void ordinarySpringBeanIsNotExported() throws Exception {
    try (var context = new AnnotationConfigApplicationContext(
            JmxTestConfiguration.class)) {

        MBeanServer server = context.getBean(
                "testMBeanServer", MBeanServer.class);

        ObjectName hypotheticalName = new ObjectName(
                "com.example.jmx:type=InternalService,name=primary");

        assertFalse(server.isRegistered(hypotheticalName));

        assertNotNull(context.getBean(InternalService.class));
    }
}
\`\`\`

Asserting that one \`ObjectName\` does not exist only covers that specific name. To verify more strictly that \`InternalService\` is not exported under **any name chosen by the exporter**, actively control the naming strategy or list MBeans in the test domain and assert against the expected set of names.

Example checking the application's namespace:

\`\`\`java
var names = server.queryNames(
        new ObjectName("com.example.jmx:*"), null);

assertEquals(
        java.util.Set.of(new ObjectName(METRICS_NAME)),
        names);
\`\`\`

When the \`com.example.jmx\` domain is used exclusively by this test fixture, asserting the exact name set verifies no unexpected exports occurred. If the test has auxiliary MBeans in the same domain, account for them in the expected set or pick an isolated domain for the fixture.

## 8. Testing the ApplicationContext Lifecycle

The Spring-managed exporter is responsible for registering and cleaning up MBeans belonging to its lifecycle. A test can hold a reference to the server to verify after the context closes:

\`\`\`java
@Test
void exportedMBeanIsUnregisteredWhenContextCloses() throws Exception {
    var context = new AnnotationConfigApplicationContext(
            JmxTestConfiguration.class);

    MBeanServer server = context.getBean(
            "testMBeanServer", MBeanServer.class);
    ObjectName name = new ObjectName(METRICS_NAME);

    try {
        assertTrue(server.isRegistered(name));
    } finally {
        context.close();
    }

    assertFalse(server.isRegistered(name),
            "MBean should be unregistered with exporter lifecycle");
}
\`\`\`

With a Spring-managed \`MBeanServerFactoryBean\`, closing the context can also release the server. Therefore, when checking \`isRegistered\` after the server has been released, the \`server\` reference may no longer be in the JVM's server list even though the test still holds the Java object. To focus specifically on exporter-driven unregistration, you can use a server created and released explicitly outside the context, then pass it into the test context as a dependency rather than having the same context manage both the server and the exporter.

A stable fixture for this case:

\`\`\`java
MBeanServer server = javax.management.MBeanServerFactory.createMBeanServer(
        "isolated-test");
try {
    // Create a context with a @Bean MBeanServer returning this exact server.
    // Verify registered, close the context, then verify unregistered.
} finally {
    javax.management.MBeanServerFactory.releaseMBeanServer(server);
}
\`\`\`

Tests should avoid sharing a single platform server across parallel tests using the same \`ObjectName\`; doing so easily causes duplicate registration errors from other tests unrelated to the functionality under test.

## 9. Verifying Annotations via Metadata, Not Only by Name

A bean appearing in the registry might be a Standard MBean registered via another mechanism, or explicitly exported via a map. Thus, when proving **annotation-based export**, verify:

1. The test configuration creates the annotation exporter via \`@EnableMBeanExport\`.
2. \`OrderMetrics\` has \`@ManagedResource\`.
3. The registry contains the \`ObjectName\` from the annotation.
4. \`MBeanInfo\` exposes the exact attributes and operations marked by \`@ManagedAttribute\` and \`@ManagedOperation\`.
5. Unannotated methods do not appear unexpectedly.

You can expand by reading metadata:

\`\`\`java
MBeanInfo info = server.getMBeanInfo(metricsName);

for (var attribute : info.getAttributes()) {
    System.out.printf(
            "%s: type=%s, readable=%s, writable=%s%n",
            attribute.getName(),
            attribute.getType(),
            attribute.isReadable(),
            attribute.isWritable());
}

for (var operation : info.getOperations()) {
    System.out.println(operation.getName());
}
\`\`\`

If the lesson requirement is simply confirming registration, \`isRegistered\` already gives an important signal. If you want to prove exact exposure scope, \`getMBeanInfo\` is the necessary step.

## 10. Distinguishing @ManagedResource and Standard MBean Convention

There are two ways a class becomes a JMX MBean:

**Standard MBean convention**:

\`\`\`java
public interface JobMonitorMBean {
    int getProcessedCount();
}

public class JobMonitor implements JobMonitorMBean {
    public int getProcessedCount() { return 0; }
}
\`\`\`

When registered by convention, JMX uses the \`ClassNameMBean\` interface to determine the management contract. Spring's \`@ManagedResource\` is not needed.

**Spring annotation model**:

\`\`\`java
@ManagedResource(objectName = "com.example:type=JobMonitor")
public class JobMonitor {
    @ManagedAttribute
    public int getProcessedCount() { return 0; }
}
\`\`\`

Here, Spring's exporter/assembler uses annotations to construct metadata. The class does not have to implement a \`JobMonitorMBean\` interface.

When writing tests for **annotation scanning**, using a class that does not implement \`*MBean\` makes the evidence unambiguous: the MBean was registered by Spring's annotation exporter rather than by Standard MBean convention.

## 11. Alternative Configuration: Creating AnnotationMBeanExporter Directly

If not using \`@EnableMBeanExport\`, you can declare the exporter explicitly:

\`\`\`java
package com.example.jmx;

import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.annotation.AnnotationMBeanExporter;

@Configuration
public class ExplicitExporterConfiguration {

    @Bean
    public AnnotationMBeanExporter annotationMBeanExporter(
            MBeanServer testMBeanServer) {
        AnnotationMBeanExporter exporter = new AnnotationMBeanExporter();
        exporter.setServer(testMBeanServer);
        return exporter;
    }
}
\`\`\`

This snippet assumes the context already has an eligible \`MBeanServer\` bean. \`AnnotationMBeanExporter\` is designed to use Spring JMX metadata and automatically detect annotated beans. Do not declare both \`@EnableMBeanExport\` and a second exporter with overlapping responsibilities unintentionally, as two exporters may attempt to register the same \`ObjectName\`.

A good test should choose **one configuration path** per fixture and verify the exact outcome of that path.

## 12. Scan Scope, Parent/Child Contexts, and Bean Proxies

### ComponentScan Does Not Scan the Entire Classpath

\`@ComponentScan\` only examines configured packages, include/exclude filters, and conditions. If \`OrderMetrics\` lies outside scanned packages, \`@ManagedResource\` will not make it appear in the context on its own.

### Different ApplicationContexts Can See Different Bean Sets

With parent/child contexts, beans in the parent and child contexts have different visibility scopes; exporters in each context may see different bean sets depending on configuration. At the same time, both may share the platform \`MBeanServer\`, leading to duplicate \`ObjectName\` collisions if both try to export the same managed resource.

### AOP Proxies and Class Metadata

When a bean is proxied by Spring AOP, its runtime class can differ from the original class carrying \`@ManagedResource\`. How the exporter extracts annotations, metadata, and target bean types depends on introspection mechanisms and the Spring version. If a managed resource disappears after adding \`@Transactional\` or an aspect, inspect the proxy type, annotations on the target/interface, and exporter logs.

### Lazy Beans and FactoryBean

A lazy bean or the product of a \`FactoryBean\` can be affected by when the exporter inspects beans, determinable bean types, and initialization timing. Do not assume every instance created after the exporter finishes scanning will be exported automatically; if runtime registration is needed, use an explicit registration mechanism.

In an initial test fixture, prefer regular singleton beans to verify core principles; then expand to proxies, lazy beans, and multiple contexts.

## 13. Troubleshooting Common Test Failures

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| \`OrderMetrics\` missing from context | \`@ComponentScan\` wrong package or class missing \`@Component\` | \`getBeanNamesForType\`, inspect configuration |
| Spring bean exists but JMX MBean is missing | Missing \`@EnableMBeanExport\`, \`@ManagedResource\`, or wrong server on exporter | \`isRegistered\`, exporter bean list, and actual server |
| MBean registered but attributes are empty | Missing \`@ManagedAttribute\` or assembler not reading expected metadata | \`getMBeanInfo\`, annotations on getters |
| \`InstanceAlreadyExistsException\` | Duplicate \`ObjectName\` in the same server | Use isolated server, test domain, and distinct names |
| Test passes alone, fails in suite | Tests share registry or context, failing to close context | Use isolated server and try-with-resources |
| JConsole sees MBean but JUnit does not | JConsole attached to another JVM, test reads a different \`MBeanServer\` | Match PID, injected server, full \`ObjectName\` |
| MBean has unexpected operations | Different exporter/assembler or Standard MBean interface configuration | Read \`MBeanInfo\`, identify export mechanism |
| Context fails on startup due to invalid MBean | Invalid management metadata/data type or ObjectName | Read root cause in startup logs |
| Error when closing context | Conflicting MBean/server ownership or exporter lifecycle | Isolate server and identify who unregisters |

If \`isRegistered\` returns false, do not immediately modify annotations. First verify the bean is in the context, the exporter exists, which server is used, and whether the expected JMX name is exact.

## 14. Minimal Build Configuration and Running Tests

If a Java Gradle project uses Spring Framework and JUnit Jupiter, it needs Spring context/JMX and JUnit Jupiter dependencies. Groovy DSL example:

\`\`\`groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.0'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.0'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
\`\`\`

The versions above illustrate a valid-looking dependency set; in real repositories, pull versions from the BOM, dependency management, or version catalog in use to avoid conflicts. \`spring-context\` provides the IoC and JMX annotation exporter components in this example. JUnit Jupiter provides assertions and \`@Test\`.

Run:

\`\`\`bash
./gradlew test --tests 'com.example.jmx.JmxAnnotationScanTest'
\`\`\`

On Windows, use \`gradlew.bat test --tests com.example.jmx.JmxAnnotationScanTest\` or your project's appropriate wrapper command. The test does not require enabling remote JMX or opening JConsole; it accesses an \`MBeanServer\` directly inside the test JVM.

If the project already uses the Spring Boot test starter, you can use \`@SpringBootTest\` or \`ApplicationContextRunner\`, but verify whether Boot auto-configuration automatically creates an exporter/server. For clearly learning Spring Framework annotation scanning, a standalone \`AnnotationConfigApplicationContext\` fixture minimizes unrelated dependencies.

## 15. Extension Exercises

**Exercise 1 — Scope-accurate bean discovery.** Add \`CacheMetrics\` with \`@Component\`, \`@ManagedResource\`, and \`getCacheHits()\` with \`@ManagedAttribute\`. Prove the registry contains both \`OrderMetrics\` and \`CacheMetrics\`, while \`InternalService\` is not exported.

**Exercise 2 — Missing class annotation.** Remove \`@ManagedResource\` from \`OrderMetrics\` while keeping \`@ManagedAttribute\`; run the test and explain the difference between the bean still existing in the context and JMX autodetection not selecting it.

**Exercise 3 — Exposed methods.** Create \`resetStatistics()\` and test with/without \`@ManagedOperation\`. Compare \`getMBeanInfo\` rather than relying merely on successful compilation.

**Exercise 4 — Wrong server.** Intentionally configure the exporter with a separate \`MBeanServer\` while the test reads the platform server. Observe \`isRegistered=false\` on the wrong server and \`true\` on the right server. Then fix the test to inject the server from the context.

**Exercise 5 — Duplicate ObjectName.** Create two managed resources sharing the same \`objectName\` and observe the registration error in the test environment. Give them distinct names and confirm both appear.

**Exercise 6 — Lifecycle.** Close the context and verify the MBean is no longer registered on a server managed by the test outside the context. Explain the exporter's role in cleanup.

## Conclusion

Testing JMX annotation scanning in Spring Framework requires proving the entire path: **Spring component scan → managed bean → annotation exporter → MBeanServer registry → JMX metadata/values**. \`@ManagedResource\` identifies the managed object; \`@ManagedAttribute\` and \`@ManagedOperation\` define the exposed API; \`@EnableMBeanExport\` or \`AnnotationMBeanExporter\` activates discovery and registration. An integration test with an \`ApplicationContext\` and an isolated \`MBeanServer\` verifies these conditions accurately and reduces collisions across tests.
