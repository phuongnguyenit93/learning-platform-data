# Inspecting Actuator MBeans with JConsole in Spring Boot

## 1. Lab Objectives

Spring Boot Actuator provides endpoints for observing and managing an application: health status, metrics, bean information, configuration, and other diagnostics depending on dependencies and configuration. Many developers are used to accessing Actuator over HTTP, such as `/actuator/health`, yet Actuator can also expose endpoints over **JMX**. In that case, endpoints appear as **MBeans**, and the JDK's **JConsole** tool can inspect them and invoke operations on them.

This lesson walks through verification from start to finish:

1. Add the Actuator dependency and enable appropriate JMX export.
2. Start the Spring Boot application and identify the right JVM/PID.
3. Connect with JConsole to the local process.
4. Locate Actuator's JMX domain and endpoint MBeans such as `Health`, `Info`, and `Metrics`.
5. Inspect `MBeanInfo`, read metadata, and invoke **read-only, safe** operations.
6. Distinguish an endpoint missing due to exposure, availability, or connecting to the wrong JVM.
7. Keep the management surface controlled without opening remote JMX just to run experiments.

**Important point:** Actuator HTTP and Actuator JMX are **two access technologies** to the endpoint system, each with its own exposure configuration. Enabling `management.endpoints.web.exposure.include` does not mean the endpoint is automatically exported over JMX. Conversely, an endpoint visible in JConsole might not be exposed over HTTP.

## 2. Architecture Flow: from Actuator Endpoint to JConsole

```text
                   Spring Boot Application
                            |
                    Spring ApplicationContext
                            |
                Actuator endpoint beans
                  /                    \
                 /                      \
         Web endpoint mapping       JMX endpoint exporter
                 |                      |
             HTTP server             MBeanServer
                 |                      |
         GET /actuator/...      ObjectName in JMX
                                        |
                                    JConsole
                                        |
                                MBeans -> Operations
```

Roles:

| Component | Responsibility |
|---|---|
| `spring-boot-starter-actuator` | Brings Actuator infrastructure and related endpoints into the application |
| `management.endpoints.jmx.exposure.*` | Controls which Actuator endpoints are exposed over JMX |
| `spring.jmx.enabled` | Controls Spring Boot's JMX export capability where applicable to the version |
| `MBeanServer` | Registry containing JMX MBeans |
| Actuator JMX exporter | Registers Actuator endpoints as MBeans |
| `JConsole` | JMX client for viewing metadata and invoking operations |
| `ObjectName` | Address of an MBean in the registry |

Not every endpoint has simple output like `String` or `int`. Actuator can return structured data, and JConsole's UI renders values using the JMX/OpenData types supported by the endpoint exporter.

## 3. Preparation: JDK and Spring Boot Application

This lesson uses a JDK containing `java`, `javac`, and `jconsole`, along with a Spring Boot project compatible with your Java version. Example Maven configuration:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
```

If you want an application without an HTTP server, you can use a suitable starter without `spring-boot-starter-web`; this lesson uses the web starter to easily compare HTTP and JMX, not because JMX requires HTTP.

Check the JDK:

```bash
java -version
jconsole
```

JConsole has a desktop GUI. If running inside a headless container or over SSH without a GUI, it may not open a window; in that case, use a desktop machine authorized to connect to the JVM or use a Java JMX client for observation. Do not open a public remote JMX port just to "work around" the lack of a GUI.

## 4. Minimal Spring Boot Application

Main class:

```java
package demo.actuatorjmx;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ActuatorJmxDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(
            ActuatorJmxDemoApplication.class,
            args
        );
    }
}
```

You can add a simple controller to generate requests for observation:

```java
package demo.actuatorjmx;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {
    @GetMapping("/hello")
    public String hello() {
        return "Hello from JMX demo";
    }
}
```

The controller is not required for Actuator JMX to work. It merely provides an HTTP entry point for the application, helping increment a few metrics during testing when a metrics backend is configured.

## 5. Enabling JMX and Configuring Actuator Exposure

`src/main/resources/application.properties` file used in this lesson:

```properties
# Enable Spring JMX in the lab environment.
spring.jmx.enabled=true

# Expose only selected Actuator endpoints over JMX.
management.endpoints.jmx.exposure.include=health,info,metrics

# Set an easily recognizable domain.
management.endpoints.jmx.domain=demo.actuator

# Independent HTTP exposure: allow only health/info in the lab.
management.endpoints.web.exposure.include=health,info
```

In Spring Boot versions that support these properties, the Actuator JMX exporter exports endpoints that are enabled and in the JMX exposure list. `management.endpoints.jmx.domain` helps you find the domain clearly in JConsole.

**Do not enable `management.endpoints.jmx.exposure.include=*` in shared environments** just for ease of learning. Some endpoints can disclose configuration, diagnostic data, or provide operations that should not be accessible to every client.

### 5.1. Distinguishing Enable and Exposure

There are at least two separate questions:

- Does the endpoint exist and is it enabled by conditions/classpath/configuration?
- Is that endpoint **exposed over JMX**?

An enabled endpoint does not mean it is exposed over every transport by default. If an endpoint has not been created or is disabled, adding its name to the exposure list will not make it appear.

Additionally, endpoints with sensitive data may apply separate detail-visibility, sanitization, and authorization policies. Do not assume JConsole will show the exact same JSON as the HTTP endpoint.

### 5.2. Wildcard Syntax

When you genuinely need to test all endpoints in an isolated test environment, the wildcard syntax in `application.properties` can be:

```properties
management.endpoints.jmx.exposure.include=*
```

In YAML, `*` must be quoted because it has syntactic meaning in YAML:

```yaml
management:
  endpoints:
    jmx:
      exposure:
        include: "*"
```

This is a syntax example only; do not use full-exposure settings as a production default.

## 6. Starting and Identifying the Process

With Maven Wrapper:

```bash
./mvnw spring-boot:run
```

On Windows you can use:

```powershell
.\mvnw.cmd spring-boot:run
```

Or build and run the jar file:

```bash
./mvnw package
java -jar target/actuator-jmx-demo-*.jar
```

The actual jar filename depends on `artifactId` and `version` in `pom.xml`. Keep the application running. You can open a second terminal to find the PID using `jps -l` if available in the JDK, or view the process list directly when opening JConsole.

When running via Maven, multiple Java processes may be involved; therefore, select the **JVM running the Spring Boot application**, not the Maven launcher or IDE daemon.

Signs that the application started successfully do not automatically prove Actuator JMX was exported. The next step is connecting and inspecting the registry.

## 7. Opening JConsole and Connecting Locally

Open another terminal:

```bash
jconsole
```

In the connection selection window:

1. Select the local Java process corresponding to the Spring Boot application.
2. Verify the PID or main class if multiple JVMs are present.
3. Connect and open the `MBeans` tab.
4. Locate the `demo.actuator` domain you configured.
5. Expand each MBean under the domain to inspect `Attributes`, `Operations`, `Notifications`, or metadata depending on the MBean type.

JConsole may display the domain and ObjectName tree differently from the raw ObjectName string. For example, a name like:

```text
demo.actuator:type=Endpoint,name=Health
```

might be shown under the `type=Endpoint` branch and then `name=Health`. This is an example of a common ObjectName shape; the actual name must be confirmed via the MBeans tree or the `queryNames` API on the running Boot version.

Do not try to guess a fixed JConsole tree ordering if the domain/naming config or Boot version differs.

## 8. Inspecting Actuator MBeans

### 8.1. Health

The `health` endpoint is commonly used to report application or health-group status. In the `MBeans` tree, find the MBean corresponding to `Health`.

For JMX endpoints, observational behavior typically lives under **Operations** (operations published by the endpoint exporter) rather than a simple JavaBeans property getter. Operation names and signatures depend on how Actuator translates endpoint operations to JMX.

Invoke a read-only operation, such as the health-read operation shown in the metadata. The return value may be a structure representing `status` and appropriate details.

**Do not assume the operation is always named `health()`, `getHealth()`, or `status()` across all versions.** Open `MBeanInfo` or JConsole Operations to confirm the name and parameters.

The health response may be affected by `management.endpoint.health.show-details` and access policies. An `UP` status does not prove all dependencies are always healthy; it reflects the health indicators at the time of the check.

### 8.2. Info

The `info` endpoint can expose descriptive information about the application when an appropriate `InfoContributor` is present. If the endpoint has no data, the output may be empty or have few fields; that is not necessarily a JMX error.

Do not confuse Spring Boot build info, git info, environment, and custom info. They depend on application dependencies, resources, and configuration.

### 8.3. Metrics

The `metrics` endpoint can list metric names and details for a metric, depending on the exported signature. In JConsole, check the operation's parameters before invoking. If the operation expects `requiredMetricName` or a tag selector, supply the correct type and value.

Do not assume metric names are identical across all projects. Some metrics only appear when corresponding workloads occur or when a Micrometer registry is configured. Cross-check the metric names present in your own application.

When a client reads a metric, distinguish **instantaneous gauges**, **cumulative counters**, **timers**, and other measurements. Do not assume all numbers share the same unit.

## 9. Example Table for Recording Results

When opening JConsole, fill in the actual data:

| Observed Target | Lab Expectation | What to Record |
|---|---|---|
| Selected JVM | Correct Spring Boot process | PID, Java version |
| Domain | `demo.actuator` | Actual domain |
| Health MBean | Present if endpoint is enabled and exposed | ObjectName, operation |
| Info MBean | Present if endpoint is enabled and exposed | ObjectName, output |
| Metrics MBean | Present if endpoint is available and exposed | Operation signature |
| Health read | Returns health information | Status, invocation timestamp |
| Metrics read | Returns metric data when metrics exist | Metric name, unit |
| JMX exposure change | MBeans change upon restart | Before/after and configuration |

This is a learning expectation table, not output from running this lesson. Actual values must come from your own JVM.

## 10. Inspecting via Java JMX API When JConsole Is Hard to Observe

JConsole is a graphical client; the JMX API lets you inspect the registry and metadata directly:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.MBeanInfo;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

for (ObjectName name : server.queryNames(
        new ObjectName("demo.actuator:*"), null)) {

    System.out.println("MBean = " + name);

    MBeanInfo info = server.getMBeanInfo(name);
    for (var operation : info.getOperations()) {
        System.out.println(
            "  Operation = " + operation.getName()
        );
    }
}
```

This code must run in the **same JVM** as the Spring Boot application when using the local platform MBeanServer. You can place the logic in an `ApplicationRunner` or a component running after startup and pass the right MBeanServer. To run from another process, you must connect through a configured and secured JMX connector; `ManagementFactory.getPlatformMBeanServer()` in a separate client JVM points only to that client's own server.

If the application exports MBeans into a separate `MBeanServer`, use that exact server; do not assume all MBeans always reside in the platform server.

### 10.1. Inspecting Operation Signatures in Detail

```java
for (var op : info.getOperations()) {
    System.out.println("Operation: " + op.getName());
    for (var param : op.getSignature()) {
        System.out.printf(
            "  %s : %s%n",
            param.getName(),
            param.getType()
        );
    }
}
```

From the metadata, you will see how many parameters an operation takes and which Java/JMX types are required. This is far more accurate than guessing signatures from a blog post written for a different Boot version.

## 11. HTTP Endpoints and JMX Endpoints Can Differ

An illustrative configuration:

```properties
management.endpoints.web.exposure.include=health
management.endpoints.jmx.exposure.include=health,info,metrics
```

Then `info` and `metrics` can appear over JMX while not exposed over web. That is the intended result of the two exposure lists.

Conversely:

```properties
management.endpoints.web.exposure.include=health,info,metrics
management.endpoints.jmx.exposure.include=health
```

can make JConsole see only the `Health` MBean from the exported Actuator endpoints, while HTTP also has `Info` and `Metrics`.

Note that an endpoint is also subject to enable and availability conditions. Do not use a successful HTTP URL to conclude 100% that JMX is enabled; and do not use JMX presence to infer an HTTP endpoint is publicly exposed.

## 12. How Do Regular Spring JMX and Actuator JMX Differ?

Spring Framework provides management annotations such as:

```java
@ManagedResource(objectName = "demo.custom:type=QueueMonitor")
public class QueueMonitor {

    @ManagedAttribute
    public int getDepth() {
        return 12;
    }
}
```

That is an **MBean from Spring JMX annotation export**. Meanwhile, an Actuator endpoint can be declared with:

```java
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "queueSummary")
public class QueueSummaryEndpoint {

    @ReadOperation
    public java.util.Map<String, Object> summary() {
        return java.util.Map.of("depth", 12);
    }
}
```

With an Actuator JMX exporter and appropriate exposure, the `queueSummary` endpoint can be published as a JMX MBean. It does not need `@ManagedResource`. These are two different export paths:

```text
Spring JMX:
  @ManagedResource + @ManagedAttribute
      -> AnnotationMBeanExporter
      -> MBeanServer

Spring Boot Actuator:
  @Endpoint + @ReadOperation
      -> Actuator JMX endpoint exporter
      -> MBeanServer
```

An application can use both. When inventorying in JConsole, distinguish custom MBean domains and ObjectNames from the Actuator domain. Both are JMX MBeans, yet their metadata and export rules are not the same.

## 13. Notes When Writing Custom Actuator Endpoints

The endpoint example above returns `Map<String,Object>`. With JMX, data can be converted into structures compatible with the endpoint exporter. However, do not export huge object graphs, user data, or credentials merely because a read operation can return a Map.

A good management endpoint:

- Has a stable name/id.
- Exposes only necessary metrics or state.
- Has simple, easily observable return types.
- Performs no side effects in `@ReadOperation`.
- Uses `@WriteOperation`/`@DeleteOperation` only when needed and with clear authorization.
- Does not assume HTTP security equals JMX connector security.
- Verifies exposure on each transport.

A custom endpoint can be disabled by id configuration; merely adding `@Component` does not prove the endpoint was exported over JMX.

## 14. When JConsole Does Not Show Actuator MBeans

Work through causes from simplest to most complex:

### 14.1. Wrong JVM Selected

When launching JConsole on a machine with multiple Java processes, it is easy to connect to a Maven daemon/IDE/other process by mistake. Cross-check PID, main class, VM summary, and command line. If it is the right process and the domain is still missing, check configuration.

### 14.2. Missing Actuator Dependency

Without `spring-boot-starter-actuator` or the required Actuator module, the application will not create the expected endpoints. Check the dependency tree/build configuration and runtime classpath.

### 14.3. JMX Is Disabled

Check `spring.jmx.enabled` in the effective configuration of that Spring Boot app. In some projects, the property may be overridden by environment variables, command-line arguments, or profile-specific properties. Do not look only at the default `application.properties` file.

### 14.4. Endpoint Is Not Exposed over JMX

Check `management.endpoints.jmx.exposure.include` and `exclude`. Web exposure configuration does not replace JMX exposure. If the endpoint name is excluded, adding it to include may not help.

### 14.5. Endpoint Does Not Exist or Is Disabled

An endpoint may depend on dependencies, auto-configuration, or enable properties. Check endpoint beans and the condition report if using Boot.

### 14.6. Domain Differs from Expected

If `management.endpoints.jmx.domain` is ineffective or overridden, the domain name may differ. Query existing ObjectNames via API or inspect all domains in JConsole instead of looking only for `demo.actuator`.

### 14.7. Exporter Uses a Different MBeanServer

Local JConsole typically inspects the platform MBeanServer. If the application configures a separate MBeanServer, you may need to query the exact registry or intentionally configure the exporter to use the platform server.

### 14.8. Registration Error or ObjectName Collision

Two exporters/MBeans may try to use the same ObjectName. Check startup logs and registration policy. Do not fix this by enabling `REPLACE_EXISTING` without knowing which object owns the MBean.

### 14.9. MBean Exists, Yet Operation Invocation Fails

Check signature from metadata, parameter types, endpoint availability, exceptions in the read operation, and security policy. Seeing an operation in JConsole does not guarantee it will always return successfully.

## 15. Health Endpoint: Be Careful with Sensitive Details

A health endpoint can include the status of databases, disks, messaging, or external systems. Even `UP`/`DOWN` alone carries operational meaning; details can contain hostnames, service names, or internal information.

Principles:

1. Do not treat local JMX as an excuse to export raw secrets.
2. Enable health details only as appropriate for authorized viewers.
3. Prevent custom endpoints from returning URLs with credentials, raw exception messages, or configurations.
4. When deep failure analysis is needed, use logging redaction and a separate safe diagnostic workflow.
5. When using remote JMX, manage access permissions at the connector/server rather than relying on the HTTP actuator endpoint being secured.

Do not invoke operations with side effects just to test JConsole. In this lesson, stick to read operations.

## 16. Remote JConsole and Security

This lab encourages a **local connection**: launching JConsole in an environment with appropriate permissions for the running JVM. If the application runs in a container/Kubernetes or on another machine, do not automatically open a public JMX RMI port.

Remote JMX requires:

- Appropriate authentication and authorization.
- TLS or a trusted encrypted channel.
- Firewall/network policies restricting connection sources.
- Managing both the RMI registry endpoint and remote object endpoint when using RMI.
- Securing credentials and truststores.
- Auditing management actions with side effects.

Do not use `com.sun.management.jmxremote.authenticate=false` or `com.sun.management.jmxremote.ssl=false` as a default configuration for shared environments. If no secure remote configuration exists, use a local JVM or write an in-process diagnostic to read metadata.

## 17. Example Checking Effective Configuration via ApplicationContext

You can add an `ApplicationRunner` to confirm endpoint MBeans after application startup:

```java
package demo.actuatorjmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class JmxDiagnosticsConfiguration {

    @Bean
    ApplicationRunner jmxInspection() {
        return args -> {
            MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

            for (ObjectName name : server.queryNames(
                    new ObjectName("demo.actuator:*"), null)) {
                MBeanInfo info = server.getMBeanInfo(name);
                System.out.println("Actuator MBean: " + name);
                System.out.println(
                    "Operations: " + info.getOperations().length
                );
            }
        };
    }
}
```

This is a post-startup metadata check and does not read sensitive values. If no MBean is found, check `spring.jmx.enabled`, JMX exposure, endpoint availability, and MBeanServer selection.

When using Actuator in production systems, limit metadata logging and use an appropriate structured logger; do not print all JMX attributes or endpoint responses to stdout.

## 18. Comparison with curl

If using the web starter and the `health` endpoint is exposed over HTTP:

```bash
curl http://localhost:8080/actuator/health
```

You may receive a response with `status` or other information depending on configuration. However, this lesson's goal is inspecting **Actuator MBeans via JConsole**, so `curl` is only for cross-checking.

A successful HTTP response confirms the web endpoint works; it does not confirm JMX registration. Conversely, JConsole calling health successfully does not prove the HTTP endpoint is exposed. This distinction is especially important when the application sets a separate management port or strict web endpoint policies.

## 19. Practice A: Toggle JMX Exposure and Observe

Run the application with:

```properties
spring.jmx.enabled=true
management.endpoints.jmx.exposure.include=health,info
management.endpoints.jmx.domain=demo.actuator
```

Inspect in JConsole and record the ObjectNames of `Health` and `Info`.

Then change to:

```properties
management.endpoints.jmx.exposure.include=health
```

Restart the application (do not assume config hot-reloads), reconnect JConsole, and compare. `Info` is expected to no longer appear in the JMX-exposed Actuator endpoints unless included through another mechanism.

Note that non-Actuator MBeans may still exist in other domains. This exercise compares only the **exported Actuator endpoint set**.

## 20. Practice B: Custom Endpoint

Create an endpoint:

```java
@Component
@Endpoint(id = "workerSummary")
public class WorkerSummaryEndpoint {
    @ReadOperation
    public java.util.Map<String, Object> read() {
        return java.util.Map.of(
            "activeJobs", 3,
            "mode", "RUNNING"
        );
    }
}
```

Add `workerSummary` to the JMX exposure list in configuration. After restarting, find this endpoint's MBean in JConsole and inspect its operation metadata.

Do not add `@WriteOperation` for a read-only exercise. If state-changing actions are needed later, include appropriate validation and permissions.

## 21. Practice C: Cross-Checking a Metric

To observe changing data, send a few requests to `/hello` and inspect the `metrics` endpoint via JConsole. Specific metric names can depend on Boot version, Micrometer, registry, and instrumentation.

Steps:

1. Verify the `Metrics` MBean appears.
2. Inspect the operation that lists metric names, if present.
3. Choose an existing metric.
4. Invoke the operation with parameters of the right type.
5. Record the measurement, unit, and timestamp.
6. Generate more requests and read again to compare.

Do not guess request counts from a single measurement without understanding the name, tags, sampling, and how the metric is aggregated. Rely on actual metadata and output.

## 22. Common Misconceptions

### 22.1. "Actuator has /health, so JConsole must have Health"

Not guaranteed: HTTP and JMX exposures are independent, JMX could be disabled, or a different server could be selected.

### 22.2. "JMX enabled means all endpoints are exposed"

No: endpoint availability and JMX exposure still restrict what is published.

### 22.3. "Every Actuator endpoint has a getStatus attribute"

No: endpoint operations are exported per the Actuator model; names, parameters, and outputs must be read from `MBeanInfo`.

### 22.4. "To see everything, turn on wildcard in production"

Avoid this: it enlarges the management surface and risk of leaking data/operations. Use an allowlist tailored to needs.

### 22.5. "Local JConsole always sees every MBeanServer in the JVM"

Do not assume this: multiple MBeanServers can exist. Check which registry the exporter uses.

### 22.6. "All health details can be read over JMX without worrying about permissions"

No: health details and endpoint output can be sensitive and need proper exposure and access control models.

### 22.7. "Missing metric definitely means Actuator is broken"

The endpoint may not be exposed, the meter may not have been created yet, the classpath may lack instrumentation, or the metric name may differ from expectations.

### 22.8. "Invoking every operation is a safe way to inspect"

Wrong: some operations have side effects or return sensitive data. Only test operations you understand in an appropriate environment.

## 23. Self-Check Questions

1. What is the role of `spring-boot-starter-actuator`?
2. What does `spring.jmx.enabled` relate to in Spring Boot?
3. How does `management.endpoints.jmx.exposure.include` differ from `management.endpoints.web.exposure.include`?
4. Why must you pick the right JVM/PID before searching for Actuator MBeans?
5. How does `management.endpoints.jmx.domain` help?
6. Why might the `Health` endpoint appear under Operations instead of Attributes?
7. What information does `MBeanInfo` provide before invoking an endpoint?
8. Why does `/actuator/health` working not guarantee JMX `Health` appears?
9. What risks arise when opening remote JMX to other machines?
10. When writing a custom `@Endpoint`, why should you avoid returning credentials or raw configuration?

## 24. Key Takeaways

**Actuator JMX is a way of publishing Spring Boot endpoints as MBeans so JMX clients like JConsole can access them.** To verify properly, enable Spring JMX, ensure the endpoint exists and is exposed over JMX, connect to the right JVM, locate the ObjectName in the configured domain, and inspect `MBeanInfo` before invoking operations.

Do not equate HTTP configuration with JMX, do not infer operation names from another version's source code, and do not open remote JMX or wildcard exposure without control. A reliable verification flow moves from dependencies and effective configuration to the actual registry and safe invocation results.
