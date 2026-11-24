# Practice: Combining JMX with Spring Boot Actuator

## 1. Objectives and Expected Outcomes

Spring Boot Actuator provides administrative, diagnostic, and observability endpoints for an application, while JMX (Java Management Extensions) is a standard Java protocol and model for managing MBeans in an `MBeanServer`. When combining both mechanisms, you can:

- Expose **Actuator endpoints** such as Health, Info, or Metrics via JMX, alongside HTTP when configured.
- Create **custom Spring JMX MBeans** using `@ManagedResource`, `@ManagedAttribute`, and `@ManagedOperation`.
- Inspect MBeans in **JConsole** or through the `MBeanServer` API.
- Compare observed data across `/actuator/health`, `/actuator/metrics`, and the JMX tree.
- Distinguish Actuator exposure scope from Spring's MBean export configuration.
- Evaluate risks when expanding the management surface, especially with operations that have side effects.

This lab uses a small Spring Boot application containing a task-processing counter, a custom MBean, and Actuator. All steps run in a local JVM **without opening remote JMX**. This is the safe and simple default choice for learning.

Expected layout:

```text
Spring Boot process
    |
    +-- Spring ApplicationContext
    |       |
    |       +-- TaskService
    |       +-- TaskManagement (custom @ManagedResource)
    |       +-- Actuator endpoint beans
    |
    +-- Platform MBeanServer
            |
            +-- company.demo:type=TaskManagement,name=primary
            +-- actuator domain -> Health / Info / Metrics (depending on exposure)
            +-- java.lang / java.nio / other JVM MXBeans
```

Actual Actuator ObjectNames depend on your Spring Boot version and domain configuration. Therefore, this lab uses `queryNames` or JConsole to confirm the actual names rather than hardcoding a single ObjectName string for all versions.

## 2. How Do JMX and Actuator Differ?

Both mechanisms serve the same observability space, but are different abstractions.

| Aspect | Spring Framework JMX | Spring Boot Actuator |
|---|---|---|
| Core components | `MBeanExporter`, `MBeanServer`, MBean | Endpoint beans, auto-configuration, exposure |
| How APIs are defined | Standard MBean or `@ManagedResource` annotations | `@Endpoint` with `@ReadOperation`, `@WriteOperation`... |
| Access protocol | Local/remote JMX | HTTP and JMX when configured |
| Identifier | `ObjectName` | Endpoint ID, mapped to an ObjectName or URL |
| Monitoring | Attributes, notifications, operations | Health, info, metrics, custom endpoints |
| Administration | Writable attributes/operations | Write/delete operations depending on endpoint |
| Metric history | None by default | Actuator metrics typically rely on Micrometer; time-series backends if configured |

A bean annotated with `@ManagedResource` **does not automatically become an Actuator endpoint**. Conversely, `@Endpoint(id="tasks")` does not necessarily become a Spring annotation MBean via `@ManagedResource`. Actuator has its own export infrastructure to convert eligible endpoints into JMX MBeans.

When an application uses both, JConsole can show **both custom MBeans and Actuator endpoint MBeans**. Distinguish the domains and management permissions of each group.

## 3. Environment Setup

You need:

- A JDK compatible with the chosen Spring Boot version.
- Maven or Gradle, e.g., using Maven Wrapper.
- An optional IDE.
- JConsole bundled with a desktop JDK, or the Java JMX API for inspection if running headless.
- A free local HTTP port for the web example.

This lab does not require a remote JMX server. If the JVM runs inside Docker/Kubernetes, inspect via the Java API or a local desktop environment first. Never enable unauthenticated and unencrypted RMI just to make JConsole see the application.

### 3.1. Project structure

```text
actuator-jmx-lab/
  pom.xml
  src/main/java/example/actuatorjmx/
    ActuatorJmxApplication.java
    TaskService.java
    TaskManagement.java
    TaskController.java
    JmxInspectionConfiguration.java
  src/main/resources/
    application.properties
  src/test/java/example/actuatorjmx/
    TaskManagementJmxTest.java
```

This is an illustrative project. In practice, you can place these classes in appropriate modules and packages without changing the essence of the integration.

## 4. Spring Boot Actuator Dependencies

Example `pom.xml` using the Spring Boot parent selected for your operating version:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>actuator-jmx-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

This section assumes a Spring Boot parent/BOM is declared by the project or added when generating with Spring Initializr. Without a BOM or parent providing dependency versions, Maven requires explicit versions. `java.version=17` is only an example and must match the Spring Boot version in use.

A Prometheus dependency is not needed for the basic JMX/Actuator lab. If you want to export metrics to Prometheus, you can add `micrometer-registry-prometheus` with appropriate exposure configuration in the extension section.

## 5. Initialize the Spring Boot Application

```java
package example.actuatorjmx;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ActuatorJmxApplication {
    public static void main(String[] args) {
        SpringApplication.run(ActuatorJmxApplication.class, args);
    }
}
```

`@SpringBootApplication` enables auto-configuration and package component scanning. Place example classes in the same package or subpackages so they are discovered. If a class lies outside the scan scope, the bean may not exist despite having JMX annotations.

On application startup, Spring Boot may auto-configure infrastructure beans related to JMX and Actuator depending on classpath/properties/version. **Do not add another `MBeanExporter` by default**, as two exporters could discover and register the same custom MBean.

## 6. Create TaskService as the Single Source of State

The service below tracks completed tasks and currently active tasks:

```java
package example.actuatorjmx;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Service;

@Service
public class TaskService {
    private final AtomicLong completed = new AtomicLong();
    private final AtomicInteger active = new AtomicInteger();
    private volatile int warningThreshold = 10;

    public void startTask() {
        active.incrementAndGet();
    }

    public void completeTask() {
        active.updateAndGet(n -> Math.max(0, n - 1));
        completed.incrementAndGet();
    }

    public long completedCount() {
        return completed.get();
    }

    public int activeCount() {
        return active.get();
    }

    public int warningThreshold() {
        return warningThreshold;
    }

    public void setWarningThreshold(int value) {
        if (value < 1 || value > 1000) {
            throw new IllegalArgumentException(
                "warningThreshold must be 1..1000"
            );
        }
        warningThreshold = value;
    }

    public void resetCounters() {
        completed.set(0);
        active.set(0);
    }
}
```

This is a state holder for the lab, not a complete production queue model. `startTask()` and `completeTask()` increment and decrement counters for observation. Never call `resetCounters()` in production while real jobs are running.

Using a single service as the data source reduces the risk of custom MBeans and Actuator returning conflicting values due to maintaining separate counters.

## 7. Create a Custom JMX MBean Using Annotations

```java
package example.actuatorjmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "company.demo:type=TaskManagement,name=primary",
    description = "Demo task management"
)
public class TaskManagement {
    private final TaskService service;

    public TaskManagement(TaskService service) {
        this.service = service;
    }

    @ManagedAttribute(description = "Completed tasks")
    public long getCompletedTasks() {
        return service.completedCount();
    }

    @ManagedAttribute(description = "Active tasks")
    public int getActiveTasks() {
        return service.activeCount();
    }

    @ManagedAttribute(description = "Warning threshold")
    public int getWarningThreshold() {
        return service.warningThreshold();
    }

    @ManagedAttribute(description = "Update warning threshold")
    public void setWarningThreshold(int value) {
        service.setWarningThreshold(value);
    }

    @ManagedOperation(description = "Reset task counters")
    public void resetCounters() {
        service.resetCounters();
    }

    public String getInternalImplementationDetail() {
        return "not exported intentionally";
    }
}
```

The annotations define the desired JMX surface:

- `CompletedTasks` and `ActiveTasks`: read-only attributes.
- `WarningThreshold`: read-write attribute.
- `resetCounters`: operation with side effects, for lab use only.
- `getInternalImplementationDetail()`: public method on the Java class, **intentionally not marked for export**.

In a context with proper JMX annotation infrastructure, the exporter creates an MBean for this resource. This example uses `@ManagedResource` metadata; it does not need to implement a Standard MBean `TaskManagementMBean` interface.

Do not use an overly broad reflective assembler just to make methods show up in JConsole, as that can accidentally expose internal methods or sensitive data.

## 8. Configure Spring Boot JMX and Actuator Exposure

File `src/main/resources/application.properties`:

```properties
spring.application.name=actuator-jmx-lab
server.port=8080

# Enable Spring JMX export support in compatible Boot versions.
spring.jmx.enabled=true

# Expose only the required Actuator endpoints over JMX.
management.endpoints.jmx.exposure.include=health,info,metrics

# Dedicated domain for easy identification in JConsole.
management.endpoints.jmx.domain=company.actuator

# HTTP exposure is independent from JMX.
management.endpoints.web.exposure.include=health,info,metrics
```

`spring.jmx.enabled` controls whether Spring Boot creates the Spring JMX export infrastructure when auto-configuration conditions are met. Actuator endpoints over JMX are also governed by `management.endpoints.jmx.exposure.*` and individual endpoint enablement/availability.

**Do not equate `spring.jmx.enabled` with `management.endpoints.jmx.exposure.include`.** The first controls JMX export infrastructure, while the second decides which Actuator endpoints are exposed via JMX once that infrastructure is active.

The configuration above deliberately avoids wildcard `*` and does not open a remote connector. Different Spring Boot versions have different default exposures; explicit configuration makes the lab easier to observe.

### 8.1. Two JMX domains in the same JVM

You should be able to observe:

```text
company.demo
  type=TaskManagement, name=primary

company.actuator
  ... Health/Info/Metrics endpoints under their actual ObjectNames ...
```

`company.demo` is the custom MBean domain. `company.actuator` is the configured domain for Actuator JMX endpoints.

A domain is only part of the ObjectName; it is not a separate `MBeanServer`. Both can be registered in the same platform MBeanServer if the Boot/exporter configuration uses that server.

## 9. Launch the Application

With Maven Wrapper:

```bash
./mvnw spring-boot:run
```

On Windows:

```powershell
.\mvnw.cmd spring-boot:run
```

Or build and run the jar with the matching output name:

```bash
./mvnw package
java -jar target/actuator-jmx-lab-0.0.1-SNAPSHOT.jar
```

Keep the process running to practice with JConsole. When running from an IDE or Maven, multiple Java processes may exist. Select the process running `ActuatorJmxApplication`, not the launcher process.

You can test HTTP:

```bash
curl http://localhost:8080/actuator/health
curl http://localhost:8080/actuator/info
```

Results vary depending on `HealthIndicator`, `InfoContributor`, security configuration, and application data. A successful HTTP response does not prove Actuator JMX was exported; the next step verifies that.

## 10. Inspect the Custom MBean with JConsole

Open another terminal:

```bash
jconsole
```

In the UI:

1. Select the local Java process for `ActuatorJmxApplication`.
2. Connect and open the **MBeans** tab.
3. Find the **`company.demo`** domain.
4. Expand the MBean `type=TaskManagement,name=primary`.
5. Under **Attributes**, view `CompletedTasks`, `ActiveTasks`, and `WarningThreshold`.
6. Under **Operations**, locate `resetCounters`.

First, only read attributes. Do not call `resetCounters` when important state is active; this lab uses synthetic counters so you can call it once you understand the side effect.

If the MBean does not appear, check the process, the `spring.jmx.enabled` property, component scanning, exporter infrastructure, and `ObjectName`. If the domain appears without the expected attributes, check annotation metadata and `MBeanInfo`.

## 11. Inspect Actuator MBeans with JConsole

In the same **MBeans** tab, locate the `company.actuator` domain. Under that domain, enabled and JMX-exposed endpoints appear as MBeans.

For commonly used endpoints:

| Endpoint | Purpose | Operation Type |
|---|---|---|
| Health | Check application/dependencies status | Read operation |
| Info | Descriptive application info | Read operation |
| Metrics | List/inspect instrumented metrics | Read operations (possibly parameterized) |

Operation names, signatures, and output structure must be verified in JConsole or `MBeanInfo`; they depend on the export infrastructure and Boot version. **Do not assume Health is always a JMX attribute named `Status` or an operation `health()`**.

Actuator endpoints are typically designed as endpoint-level read/write/delete operations rather than JavaBeans getter conventions like `TaskManagement`'s custom `@ManagedAttribute`s.

### 11.1. HTTP and JMX exposure are two separate sets

Change:

```properties
management.endpoints.web.exposure.include=health
management.endpoints.jmx.exposure.include=health,info,metrics
```

HTTP now exposes only Health in this illustration, while JMX can also expose Info and Metrics if those endpoints are available and enabled.

Conversely, if HTTP exposes Metrics while JMX does not, JConsole will not see the Metrics endpoint merely because `/actuator/metrics` works.

## 12. Send Requests to Change Observable State

To generate observable data, you can add a simple controller:

```java
package example.actuatorjmx;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class TaskController {
    private final TaskService service;

    public TaskController(TaskService service) {
        this.service = service;
    }

    @PostMapping("/demo/tasks/start")
    public String start() {
        service.startTask();
        return "started";
    }

    @PostMapping("/demo/tasks/complete")
    public String complete() {
        service.completeTask();
        return "completed";
    }

    @GetMapping("/demo/tasks/summary")
    public String summary() {
        return "active=" + service.activeCount()
            + ", completed=" + service.completedCount();
    }
}
```

These POST endpoints are **for the lab environment only**. In production, never expose state-mutating endpoints without authentication, authorization, validation, and other controls. The sample omits security solely to keep the example focused on JMX/Actuator.

Run:

```bash
curl -X POST http://localhost:8080/demo/tasks/start
curl -X POST http://localhost:8080/demo/tasks/complete
curl http://localhost:8080/demo/tasks/summary
```

Then switch back to JConsole and read `ActiveTasks`/`CompletedTasks`. The numbers change with `TaskService`, proving the custom MBean reflects live application state.

## 13. Inspect Using the Java MBeanServer API

If JConsole is unsuitable in a headless environment, create a diagnostic bean that runs after startup:

```java
package example.actuatorjmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class JmxInspectionConfiguration {

    @Bean
    ApplicationRunner inspectMBeans() {
        return args -> {
            MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

            for (ObjectName name : server.queryNames(
                    new ObjectName("company.*:*"), null)) {
                System.out.println("MBean: " + name);

                MBeanInfo info = server.getMBeanInfo(name);
                System.out.println(
                    "  attributes=" + info.getAttributes().length
                    + ", operations=" + info.getOperations().length
                );
            }
        };
    }
}
```

This code only reads metadata and invokes no side-effecting operations. It uses the platform MBeanServer in the current JVM. If the application is configured to export to a different MBeanServer, inject and query that server instead of assuming the platform server.

Avoid logging all attribute values for debugging, as getters may return sensitive data or run expensive operations.

### 13.1. Check a specific ObjectName

```java
ObjectName taskName = new ObjectName(
    "company.demo:type=TaskManagement,name=primary"
);

boolean registered = server.isRegistered(taskName);
System.out.println("Custom MBean registered=" + registered);

if (registered) {
    System.out.println(
        "ActiveTasks=" +
        server.getAttribute(taskName, "ActiveTasks")
    );
}
```

This is a stronger check than merely seeing the `TaskManagement` bean in the Spring context: it verifies that the JMX registry and attribute read path actually work.

## 14. Add a Micrometer Counter to Observe via Actuator Metrics

In the basic example, `TaskService` values are only exposed via the custom JMX MBean. To make Actuator Metrics aware of completed tasks, instrument them into `MeterRegistry`.

Add to `TaskService`:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

@Service
public class TaskService {
    private final Counter completedMeter;
    private final AtomicLong completed = new AtomicLong();
    private final AtomicInteger active = new AtomicInteger();

    public TaskService(MeterRegistry registry) {
        this.completedMeter = registry.counter(
            "demo.tasks.completed",
            "component", "task-service"
        );
    }

    public void completeTask() {
        active.updateAndGet(n -> Math.max(0, n - 1));
        completed.incrementAndGet();
        completedMeter.increment();
    }

    // Remaining methods are the same as in the previous section.
}
```

This snippet is an update to the `TaskService` class, **not a second class to copy alongside it**. When applying it, keep the existing fields and methods, add the constructor accepting `MeterRegistry`, add the `Counter`, and update `completeTask`.

Since `spring-boot-starter-actuator` brings in Micrometer infrastructure in modern Boot releases, a `MeterRegistry` is typically auto-configured. If your application has multiple registries or customized auto-configuration, match injection to your actual setup.

After triggering events, try:

```bash
curl http://localhost:8080/actuator/metrics/demo.tasks.completed
```

The response depends on metric name/tags, web exposure, and security. You can also use the Actuator Metrics MBean in JConsole to explore the same metric if the endpoint is exposed over JMX.

### 14.1. Avoid mistaking a JMX attribute for a Micrometer meter

`getCompletedTasks()` exposed via the custom MBean **does not automatically create** a meter named `demo.tasks.completed` in Micrometer. Having `@ManagedAttribute` alone is not enough for `/actuator/metrics/demo.tasks.completed` to return data.

In this lab, the counter is created by `registry.counter(...)`, while the JMX attribute is created by `@ManagedAttribute`. Both reflect the same event through different export mechanisms.

If you use an external JMX collector to scrape `CompletedTasks` while also exporting the Micrometer Counter, avoid creating two semantically duplicate metrics and summing them on dashboards.

## 15. Practice Custom Actuator Endpoint

In addition to a custom Spring JMX MBean, you can build a custom Actuator endpoint:

```java
package example.actuatorjmx;

import java.util.Map;
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "taskSummary")
public class TaskSummaryEndpoint {
    private final TaskService service;

    public TaskSummaryEndpoint(TaskService service) {
        this.service = service;
    }

    @ReadOperation
    public Map<String, Object> summary() {
        return Map.of(
            "active", service.activeCount(),
            "completed", service.completedCount()
        );
    }
}
```

Add `taskSummary` to exposure:

```properties
management.endpoints.web.exposure.include=health,info,metrics,taskSummary
management.endpoints.jmx.exposure.include=health,info,metrics,taskSummary
```

Once the endpoint is detected and enabled under your Boot version's Actuator rules, you can query the HTTP endpoint and locate the `taskSummary` Actuator JMX MBean.

Some Actuator versions normalize endpoint IDs and paths according to specific rules; verify actual endpoint IDs/paths from the running application rather than guessing casing.

### 15.1. Comparing the three observation channels

The same `TaskService` state can surface in three ways:

```text
TaskService.completedCount()
   |
   +--> @ManagedAttribute -> custom MBean "CompletedTasks"
   |
   +--> @ReadOperation    -> Actuator endpoint "taskSummary"
   |
   +--> MeterRegistry    -> "demo.tasks.completed" Counter
```

Test results should reflect the same events, though data shapes and read timing may differ. A Counter is a cumulative metric, a custom MBean returns an instantaneous value, and an Actuator endpoint returns an object/read operation. Do not assume clients always read simultaneous snapshots.

## 16. Verify JMX Exposure with MBeanInfo

When viewing a custom or Actuator MBean, inspect metadata:

```java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanOperationInfo;

MBeanInfo info = server.getMBeanInfo(taskName);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "ATTR %s readable=%s writable=%s type=%s%n",
        attribute.getName(),
        attribute.isReadable(),
        attribute.isWritable(),
        attribute.getType()
    );
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println("OP " + operation.getName());
}
```

For the custom `TaskManagement`, metadata is expected to contain attributes `CompletedTasks`, `ActiveTasks`, `WarningThreshold` and operation `resetCounters` when the annotation exporter is working properly.

For Actuator endpoints, metadata may mainly show operations corresponding to endpoint read/write operations; do not assume every property is exported as a JMX attribute following JavaBeans conventions.

Inspecting metadata without invoking operations is the right first step when working on a live process.

## 17. Integration Testing the Custom MBean

A test can use `@SpringBootTest` to start the context in a test environment, enable JMX, and assert the ObjectName.

```java
package example.actuatorjmx;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
    properties = {
        "spring.jmx.enabled=true",
        "management.endpoints.jmx.exposure.include=health,info"
    }
)
class TaskManagementJmxTest {

    @Autowired
    MBeanServer mbeanServer;

    @Test
    void customMBeanIsRegistered() throws Exception {
        ObjectName name = new ObjectName(
            "company.demo:type=TaskManagement,name=primary"
        );

        assertTrue(mbeanServer.isRegistered(name));
        assertNotNull(
            mbeanServer.getMBeanInfo(name)
        );
    }
}
```

In the test project, ensure an `MBeanServer` bean is injected that matches the real exporter; if no bean is created under your Boot configuration, use `ManagementFactory.getPlatformMBeanServer()` in the test or configure a server bean explicitly. Never assume `@Autowired MBeanServer` works in every version/configuration.

Spring TestContext may cache contexts; if multiple tests share the platform MBeanServer and the same ObjectName, watch out for collisions during parallel runs. For isolated metadata tests, a dedicated `MBeanServerFactory.createMBeanServer(...)` is usually easier to control.

## 18. Do Actuator Health and JMX Health Have the Same Semantics?

Actuator Health reflects the configured `HealthIndicator` set and health aggregation/display policy. The same logical endpoint can be accessed over HTTP or JMX, yet output structure, detail level, and access permissions can vary by transport/security/version.

Do not use a custom MBean `getState() == "READY"` as a complete replacement for Actuator Health if health also needs to check databases, disk, brokers, or external systems.

Conversely, if you need a small domain-specific status such as `TaskServicePaused`, a custom MBean or custom Actuator endpoint may fit better than putting every status into global health.

A clean design:

- Health: application readiness/liveness or dependency status as appropriate.
- Metrics: time-series measurements.
- Custom MBean: scoped administrative attributes/operations.
- Custom Actuator endpoint: operational API with a clear contract across configured transports.

## 19. Security: Do Not Treat a Local Lab as Production Configuration

This lab includes a `resetCounters()` operation and simulated POST endpoints, so it must only be used in an isolated test environment.

In production:

1. Expose only necessary Actuator endpoints over HTTP/JMX.
2. Never use wildcard `management.endpoints.*.exposure.include=*` without review.
3. Protect HTTP management endpoints with authentication, authorization, and network policy.
4. For remote JMX, require authentication, TLS or a protected tunnel, firewall rules, and strict permissions.
5. Never export API keys, passwords, tokens, raw configuration, or user data through MBeans/Actuator.
6. Restrict writable attributes and side-effecting operations.
7. Audit important administrative actions.
8. Limit monitoring account permissions; read-only metrics accounts do not need reset/restart privileges.
9. Never expose RMI/JMX ports to the public Internet.
10. Re-check metadata and exposure after every dependency/Boot upgrade.

**Spring Security HTTP rules do not automatically give the JMX connector the same access policy.** Both access channels must be secured separately.

## 20. Diagnosing When the Custom MBean Is Missing

### 20.1. `spring.jmx.enabled` has not taken effect

Check the property by profile, environment variables, command-line arguments, and Spring Boot version. A correct `application.properties` file does not guarantee it is not overridden by a higher-priority configuration source.

### 20.2. `TaskManagement` is not a Spring bean

If the class is outside component scanning or missing `@Component`/`@Bean`, JMX annotations have no effect in the target context.

### 20.3. No matching metadata exporter

An `AnnotationMBeanExporter` or equivalent infrastructure is needed to process `@ManagedResource`. Check initialized exporter beans rather than just seeing the annotation in source code.

### 20.4. Unexpected ObjectName

Use `queryNames(new ObjectName("company.demo:*"), null)` to find the actual name. The naming strategy or explicit mapping may differ from the annotation.

### 20.5. Duplicate ObjectName

Two exporters/contexts registering the same name can cause collisions. Do not fix it by blindly setting `REPLACE_EXISTING` before determining ownership.

### 20.6. JConsole connected to the wrong JVM

Maven, the IDE, and the application may run multiple Java processes simultaneously. Match PID/main class and pick the right JVM.

### 20.7. JConsole is viewing a different MBeanServer

The platform server is the common choice for local JConsole. If the application creates a dedicated MBeanServer, custom MBeans may not appear in the registry JConsole shows.

## 21. Diagnosing When Actuator MBeans Do Not Appear

Causes differ from custom MBeans:

- Missing `spring-boot-starter-actuator`.
- Endpoint not enabled or not created by classpath/conditions.
- `management.endpoints.jmx.exposure.include` does not include that endpoint.
- `management.endpoints.jmx.exposure.exclude` excludes the endpoint.
- `spring.jmx.enabled` is disabled or ineffective.
- JMX domain differs from what you expected.
- Different MBeanServer or exporter than expected.
- Actuator version changes to endpoint availability/naming.

If `/actuator/health` works while JConsole does not show Health, do not conclude Actuator is broken. Verify JMX exposure independently, verify the MBeanServer, and inspect actual metadata.

## 22. Diagnosing When Actuator Metrics Does Not Show the Custom Counter

`@ManagedAttribute` on `TaskManagement` does not automatically create a Micrometer meter. Only when code instruments via `MeterRegistry` or a dedicated JMX scraper runs will the metrics backend receive corresponding data.

Check:

1. Is a suitable `MeterRegistry` present in the context?
2. Does the code call `registry.counter("demo.tasks.completed", ...)`?
3. Has an event occurred to increment the counter?
4. Is the Metrics endpoint enabled and exposed over HTTP/JMX?
5. Were the metric name and tags entered accurately?
6. If using Prometheus, are the registry dependency and scrape endpoint present?
7. Are duplicate metrics produced by both a JMX collector and Micrometer measuring the same thing?

MBean metadata, Actuator endpoints, and the Micrometer registry should be checked as three complementary layers; do not treat one layer as proof that the others work.

## 23. Extension Exercises

### Exercise 1 — Read custom attributes from JConsole

Trigger two task starts and one task complete. Read `ActiveTasks` and `CompletedTasks` in JConsole and compare with `/demo/tasks/summary`.

### Exercise 2 — Update a writable attribute

In the lab environment, set `WarningThreshold=25` via JConsole. Then use the Java JMX API or bean getter to verify the value. Try an out-of-range number and observe the validation error.

### Exercise 3 — Invoke a side-effecting operation

Read the counters first, invoke `resetCounters()` in JConsole, and read again. Explain why this operation must not be granted to every monitoring client.

### Exercise 4 — Different Web and JMX exposures

Configure HTTP to expose only `health`, while JMX exposes `health,info,metrics`. Compare `curl` and JConsole to prove the two transports are independent.

### Exercise 5 — Custom Actuator endpoint

Create `TaskSummaryEndpoint` with `@ReadOperation`. Expose it over HTTP/JMX and compare output with the custom MBean `TaskManagement`.

### Exercise 6 — Custom metric

Register `demo.tasks.completed` in Micrometer, perform tasks, then query `/actuator/metrics/demo.tasks.completed` and the JMX Metrics endpoint if available.

### Exercise 7 — Duplicate exporter

In an isolated test, create two exporters both attempting to register `company.demo:type=TaskManagement,name=primary`. Observe the collision error and explain the role of `RegistrationPolicy`.

### Exercise 8 — Multi-context configuration

Create root and child contexts with separate exporters. Identify the shared MBeanServer, the registered ObjectNames, and how to prevent duplicate registrations.

### Exercise 9 — Headless inspection

Without the JConsole GUI, use an `ApplicationRunner` calling `queryNames` and `getMBeanInfo`. Print only safe metadata.

### Exercise 10 — Security review

List exposed Actuator endpoints, custom MBean attributes, and operations. Classify which elements are read-only, which require admin privileges, and how to secure each transport.

## 24. Lab Completion Checklist

- [ ] Spring Boot application started.
- [ ] Actuator dependency present.
- [ ] `spring.jmx.enabled` effective as intended.
- [ ] Custom bean `TaskManagement` present in `ApplicationContext`.
- [ ] Custom MBean registered with the expected ObjectName.
- [ ] JConsole connected to the right JVM.
- [ ] Custom MBean attributes readable.
- [ ] Actuator Health/Info/Metrics MBeans visible when enabled and exposed.
- [ ] HTTP exposure differs from JMX exposure as configured.
- [ ] Custom Micrometer counter appears after instrumentation.
- [ ] No insecure remote JMX needed.
- [ ] No side-effecting operations exposed outside lab scope.

This is a learner activity checklist, not a verified compliance status for any specific environment.

## 25. Self-Check Questions

1. How do `@ManagedResource` and `@Endpoint` differ?
2. Does `spring.jmx.enabled` automatically expose all Actuator endpoints?
3. Why must `management.endpoints.jmx.exposure.include` be configured separately?
4. What conditions must `TaskManagement` meet to be registered as a custom MBean?
5. Where does JConsole discover MBeans from?
6. Why does `/actuator/health` working not guarantee Health appears over JMX?
7. Does `@ManagedAttribute` automatically create a Micrometer counter?
8. What metadata does `MBeanInfo` help verify?
9. Why can two exporters collide on an ObjectName?
10. When should you use a custom Actuator endpoint instead of a custom MBean?
11. What security controls are required if remote JMX is enabled?
12. How do you verify integration in a headless environment?

## 26. Summary

**Combining JMX with Spring Boot Actuator gives an application both custom management MBeans and standard Actuator observability endpoints in the same JVM.** Both can share an `MBeanServer` while having distinct declaration, exposure, and metadata mechanisms.

In this lab, configure `spring.jmx.enabled` explicitly, select Actuator JMX exposure via an allowlist, create a safe `@ManagedResource` bean, use JConsole or `MBeanServer` to verify actual registration, and compare against HTTP Actuator. When adding Micrometer, instrument meters explicitly instead of assuming custom MBeans generate metrics automatically.

In operational environments, uphold two principles: **export only necessary data and operations**, and **secure each HTTP/JMX access path under an appropriate permission model**.
