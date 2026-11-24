# Distinguishing Actuator Endpoints from Custom MBeans in Spring Boot

## Lesson Objectives

After this lesson, you will be able to:

- Distinguish **Spring Boot Actuator endpoints** from **custom JMX MBeans** in terms of purpose, programming model, and management.
- Understand that an Actuator endpoint can be exposed over multiple technologies, including HTTP and JMX, whereas a custom MBean is a direct JMX management object.
- Identify which components are controlled by \`management.endpoints.*\` settings and which depend on Spring Framework \`MBeanExporter\`, \`@ManagedResource\`, and \`@ManagedOperation\`.
- Know how to choose an Actuator endpoint, a custom MBean, or both for observability and management requirements.
- Avoid confusing **endpoint exposure** with **JMX remote access**, and do not treat enabling an endpoint as opening network JMX connections.
- Accurately verify what has been published in \`MBeanServer\`.

## 1. Why Are Actuator and MBeans Easily Confused?

Spring Boot has two groups of features that can appear together when observing an application via JMX:

1. **Spring Boot Actuator** provides operational endpoints such as health, info, metrics, beans, or custom endpoints defined with \`@Endpoint\`.
2. **Spring Framework JMX** allows exporting a Spring bean as an MBean with \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\`, or Standard MBean conventions.

Both can show up in JConsole, but they are not the same concept.

\`\`\`text
Spring Boot application
  |
  +-- Actuator endpoint model
  |     +-- HealthEndpoint
  |     +-- InfoEndpoint
  |     +-- MetricsEndpoint
  |     +-- @Endpoint custom
  |           |
  |           +-- HTTP exposure (if enabled)
  |           +-- JMX exposure  (if enabled)
  |
  +-- Spring Framework JMX model
        +-- @ManagedResource bean
        +-- Standard MBean
        +-- MBeanExporter
              |
              +-- MBeanServer
\`\`\`

Key point:

> **An Actuator endpoint is a Spring Boot operational abstraction; an MBean is a Java JMX contract.** Actuator can provide JMX adaptation, but that does not turn every Spring MBean into an Actuator endpoint.

## 2. Quick Comparison

| Criterion | Actuator endpoint | Custom MBean |
|---|---|---|
| Primary ecosystem | Spring Boot Actuator | Java JMX / Spring Framework JMX |
| How declared | \`@Endpoint\`, \`@ReadOperation\`, \`@WriteOperation\`, \`@DeleteOperation\` | \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\`, or \`*MBean\` interface |
| Management model | Abstract endpoints and operations | MBean with attributes, operations, notifications |
| HTTP | Can be exposed via web exposure | Does not automatically generate an HTTP endpoint |
| JMX | Can be exposed via JMX exposure | Registered directly in MBeanServer via exporter/registration |
| Identifier | Endpoint ID, e.g., \`health\` | ObjectName, e.g., \`learning.jmx:type=Queue,name=Primary\` |
| Exposure configuration | \`management.endpoints.web.exposure.*\`, \`management.endpoints.jmx.exposure.*\` | JMX exporter and MBeanServer configuration |
| Discovery via JMX | Via Actuator's JMX mapping mechanism | Via ObjectName created by exporter/registration |
| Remote access method | Depends on configured HTTP or JMX transport | Requires suitable JMX connector/attach |
| Best suited for | Health, metrics, diagnostics, operational APIs | Java-specific management, operations, notifications, custom MBean attributes |

Setting names and default values may change across Spring Boot versions. When deploying, consult the documentation for the exact version in use; the table above describes the core concepts and mechanisms.

## 3. What Is an Actuator Endpoint?

Actuator provides a set of built-in endpoints and allows creating custom endpoints. An endpoint is identified by an ID and its operations.

Custom example:

\`\`\`java
package example.boot;

import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "queueStatus")
public class QueueStatusEndpoint {

    private final QueueService queueService;

    public QueueStatusEndpoint(QueueService queueService) {
        this.queueService = queueService;
    }

    @ReadOperation
    public QueueSnapshot status() {
        return new QueueSnapshot(
            queueService.pendingJobs(),
            queueService.isPaused()
        );
    }

    public record QueueSnapshot(int pendingJobs, boolean paused) {
    }
}
\`\`\`

This is a **custom Actuator endpoint**, not an MBean declared with \`@ManagedResource\`.

Spring Boot can create adapters so this endpoint appears over one or more exposure technologies. For HTTP, the endpoint can get a URL based on the management web base path and endpoint ID; for JMX, it can be mapped into a management MBean by Actuator's mechanism.

However, **declaring \`@Endpoint\` does not automatically guarantee the endpoint is exposed on every transport**. You must check dependencies, enablement, exposure policy, and security.

### Actuator Annotations to Distinguish

- \`@Endpoint\`: an endpoint that can support multiple exposure technologies.
- \`@ReadOperation\`: an operation that reads state.
- \`@WriteOperation\`: an operation that changes state.
- \`@DeleteOperation\`: an operation that deletes/removes per the endpoint contract.
- \`@WebEndpoint\`: an endpoint specifically for web technology.
- \`@JmxEndpoint\`: an endpoint specifically for JMX technology.

Depending on the endpoint type, operations can be adapted to fit the technology. For example, a \`@WebEndpoint\` does not automatically become a JMX endpoint because it is designed specifically for web exposure.

## 4. What Is a Custom MBean?

An MBean is an object registered in a Java \`MBeanServer\` with an ObjectName and a management interface.

Spring Framework supports defining MBeans via annotations:

\`\`\`java
package example.boot;

import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;

@ManagedResource(
    objectName = "learning.jmx:type=QueueManagement,name=Primary",
    description = "Queue management through JMX"
)
public class QueueManagement {

    private final QueueService queueService;

    public QueueManagement(QueueService queueService) {
        this.queueService = queueService;
    }

    @ManagedAttribute(description = "Current pending job count")
    public int getPendingJobs() {
        return queueService.pendingJobs();
    }

    @ManagedOperation(description = "Pause accepting new jobs")
    public void pause() {
        queueService.pause();
    }
}
\`\`\`

When \`MBeanExporter\` and annotation metadata export are suitably enabled, the bean can be registered under the ObjectName:

\`\`\`text
learning.jmx:type=QueueManagement,name=Primary
\`\`\`

A JMX client can use:

\`\`\`java
Object pending = connection.getAttribute(
    new ObjectName("learning.jmx:type=QueueManagement,name=Primary"),
    "PendingJobs"
);
\`\`\`

Or invoke an operation:

\`\`\`java
connection.invoke(
    objectName,
    "pause",
    new Object[0],
    new String[0]
);
\`\`\`

**This MBean does not automatically become an Actuator endpoint** and does not automatically get an \`/actuator/queueManagement\` path.

## 5. Both Are "Custom", Yet a Custom Endpoint Differs from a Custom MBean

Two common phrases come up:

- "I wrote a custom endpoint with \`@Endpoint\`."
- "I wrote a custom MBean with \`@ManagedResource\`."

They differ right from their contract:

\`\`\`text
@Endpoint(id = "queueStatus")
  -> endpoint ID
  -> @ReadOperation, @WriteOperation ...
  -> Actuator exposure adapters

@ManagedResource(objectName = "learning.jmx:type=Queue,name=Primary")
  -> JMX ObjectName
  -> @ManagedAttribute, @ManagedOperation ...
  -> MBeanExporter / MBeanServer
\`\`\`

A bean using \`@Endpoint\` is handled by Actuator infrastructure; a bean using \`@ManagedResource\` is handled by Spring Framework JMX infrastructure. If an application has both kinds, operators may see two management entries related to the same subsystem.

Do not arbitrarily assume the two entries share the same state or the same security workflow. Design clear boundaries of responsibility.

## 6. Dependency and Exposure Configuration

To use built-in Actuator endpoints, Spring Boot typically needs the corresponding Actuator dependency, for example Maven:

\`\`\`xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
\`\`\`

Some properties-style settings to know:

\`\`\`properties
# Example explicitly exposing a set of endpoints over HTTP
management.endpoints.web.exposure.include=health,info,metrics

# Example explicitly exposing a set of endpoints over JMX
management.endpoints.jmx.exposure.include=health,info,metrics
\`\`\`

These lines illustrate two **different exposure sets**; they do not guarantee all three endpoints are enabled or present in every version, environment, and security configuration.

An endpoint can be:

1. Provided by a dependency.
2. Enabled or disabled.
3. Exposed or not exposed over web.
4. Exposed or not exposed over JMX.
5. Permitted or denied access by security/runtime policy.

Each of these decisions must be verified separately.

### Important Distinction

\`management.endpoints.jmx.exposure.include\` controls **Actuator endpoints exposed over JMX**. It is **not a list of ObjectNames for all custom MBeans** registered by \`MBeanExporter\`.

Conversely, registering a \`@ManagedResource\` does not cause that endpoint to automatically appear in \`management.endpoints.web.exposure.include\`.

## 7. Spring Boot JMX and MBeanExporter

In Spring Boot, JMX configuration may include a property controlling application JMX export, such as:

\`\`\`properties
spring.jmx.enabled=true
\`\`\`

The exact effect and default of this property must be checked against your Boot version. When using a custom \`@ManagedResource\`, ensure a suitable exporter is enabled.

Example of enabling JMX export directly via Spring Framework:

\`\`\`java
package example.boot;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxExportConfiguration {
}
\`\`\`

Do not configure multiple exporters for the same resource without control. In Spring Boot, auto-configuration may already provide an exporter; adding a manual exporter can cause duplicate ObjectName registrations.

### Does Enabling Actuator JMX Exposure Automatically Enable All Custom MBeans?

No. They are two different mechanisms:

- Actuator JMX exposure puts selected **Actuator endpoints** onto JMX.
- Spring Framework MBean exporter registers **managed beans** by annotation, convention, or mapping.

Both can exist in one MBeanServer. However, do not infer that a configuration for one mechanism controls all of the other.

## 8. ObjectName Differs from Endpoint ID

An Actuator endpoint has an ID:

\`\`\`text
health
metrics
queueStatus
\`\`\`

In JMX, Actuator maps the endpoint to an MBean naming scheme managed by Actuator. ObjectName details may depend on domain/naming strategy and Boot configuration.

A custom MBean has an ObjectName:

\`\`\`text
learning.jmx:type=QueueManagement,name=Primary
\`\`\`

**An endpoint ID is not an ObjectName.** Do not take \`queueStatus\` as an ObjectName and expect a JMX client to find the MBean that way.

To discover the exact registered names:

\`\`\`java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();

for (ObjectName name : server.queryNames(null, null)) {
    System.out.println(name);
}
\`\`\`

The output can include JVM platform MBeans, Actuator-exposed MBeans, and custom MBeans. Determine which actual server the exporters use.

## 9. Example Application with Both an Actuator Endpoint and a Custom MBean

Suppose we have a queue service:

\`\`\`java
package example.boot;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicBoolean;

public class QueueService {

    private final AtomicInteger pending = new AtomicInteger();
    private final AtomicBoolean paused = new AtomicBoolean();

    public int pendingJobs() {
        return pending.get();
    }

    public boolean isPaused() {
        return paused.get();
    }

    public void pause() {
        paused.set(true);
    }

    public void resume() {
        paused.set(false);
    }
}
\`\`\`

Spring configuration:

\`\`\`java
package example.boot;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class QueueConfiguration {

    @Bean
    QueueService queueService() {
        return new QueueService();
    }

    @Bean
    QueueStatusEndpoint queueStatusEndpoint(QueueService service) {
        return new QueueStatusEndpoint(service);
    }

    @Bean
    QueueManagement queueManagement(QueueService service) {
        return new QueueManagement(service);
    }
}
\`\`\`

In this example:

- \`QueueStatusEndpoint\` provides status for Actuator and can be exposed over web/JMX per policy.
- \`QueueManagement\` provides JMX-specific attributes and operations; it requires a Spring JMX exporter to register.
- Both call into \`QueueService\` and can reflect the same state.
- They do not need the same name or the same exposure mechanism.

**Note:** When a bean is declared via \`@Bean\`, do not simultaneously put \`@Component\` on it to create another instance of the same type unless you want duplicate beans/registrations.

## 10. When to Choose an Actuator Endpoint?

Actuator is usually a good fit when:

- You want to provide health, readiness, liveness, info, or metrics following Spring Boot conventions.
- You want an operational API that can be exposed over web or JMX per the appropriate technology.
- You want an abstraction layer more independent of JMX for reading state or configuration.
- You already have operations infrastructure and security for Actuator.
- You want to build a custom endpoint with \`@ReadOperation\` or \`@WriteOperation\`.

For example, if an operations team wants to read queue backlog over HTTP and integrate with a monitoring system, a custom Actuator endpoint or Micrometer metric is usually easier to integrate than requiring every client to use JMX.

Not every telemetry need should become a custom Actuator endpoint. High-frequency time-series data usually fits metrics instrumentation better, depending on system design.

## 11. When to Choose a Custom MBean?

A custom MBean is usually a good fit when:

- The management target is primarily used by Java/JMX tools.
- You need JMX-specific attributes, operations, and notifications.
- The system already has JMX clients and a stable ObjectName naming convention.
- You want to integrate with an MBeanServer used by a container or framework.
- You need to interact with the Java runtime or manage a component per a JMX contract.

For example, a system using JConsole or a JMX client to view pool status, reset statistics, and receive threshold notifications can use a custom MBean.

However, a custom MBean is not automatically safe just because it is "not HTTP". When a remote connector is present, it is still a network-accessible management surface.

## 12. When to Use Both?

There are valid cases for publishing the same data over both technologies:

\`\`\`text
QueueService
   |
   +-- Actuator / metrics: reading status for general operations
   |
   +-- Custom MBean: detailed management for JMX tooling
\`\`\`

However, you must address:

- Are there two contracts to maintain and version?
- Do the data share the same semantics, types, and units?
- Could sensitive operations be accidentally exposed over multiple paths?
- Do the two mechanisms share the same lifecycle and the same service instance?
- When monitoring reports different values, which source is authoritative?
- Are the requirements strong enough to justify parallel operational cost?

A good design uses a **shared business service/facade** as the source of state, while the Actuator endpoint and custom MBean are merely two adapters serving different needs.

## 13. Security: HTTP Exposure and Remote JMX Are Two Different Surfaces

Actuator endpoints can be exposed over HTTP. The HTTP path must be protected according to the web application's or management web server's security configuration.

Custom JMX MBeans and Actuator JMX exposure use the JMX management path. If accessed remotely, a separately secured JMX connector is required.

This leads to these principles:

1. Enabling HTTP authentication does not automatically protect a remote JMX connector.
2. Enabling JMX authentication does not automatically protect HTTP Actuator endpoints.
3. Do not assume remote JMX is read-only; MBeans can have writable attributes and operations.
4. Do not enable \`management.endpoints.web.exposure.include=*\` or overly broad JMX exposure without a clear need.
5. Apply least privilege to observation tools and administrative tools.
6. Do not expose passwords, tokens, or sensitive data in either Actuator endpoints or custom MBeans.
7. For operations with side effects, also evaluate auditing, approval, and rollback.

Security must be evaluated **per transport and per operation**, not based on labels like "Actuator" or "JMX".

## 14. Actuator Exposure Is Not Opening a Remote JMX Connector

This is an important misconception:

\`\`\`properties
management.endpoints.jmx.exposure.include=health,info
\`\`\`

This setting states that the selected endpoints may be exposed over JMX by Actuator infrastructure. It **does not automatically mean**:

- The JVM has opened a remote JMX port.
- Remote clients already have access.
- TLS, authentication, and authorization are configured.
- Another custom MBeanServer is also exposed.
- All MBeans in the JVM can be invoked remotely.

A remote JMX connector is a separate Java/JMX mechanism. With the JDK management agent, remote configuration can involve authentication, TLS, RMI ports, and hostnames. Do not disable security just to see an endpoint remotely.

Conversely, a local JConsole may see some MBeans without the application opening a remote port, depending on attach/local management and OS permissions.

## 15. Verifying in MBeanServer

To distinguish MBean groups, start by inspecting the registry:

\`\`\`java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
        ManagementFactory.getPlatformMBeanServer();

Set<ObjectName> all = server.queryNames(null, null);

all.forEach(System.out::println);
\`\`\`

Then check the specific name of the custom MBean:

\`\`\`java
ObjectName custom = new ObjectName(
    "learning.jmx:type=QueueManagement,name=Primary"
);

System.out.println(server.isRegistered(custom));
\`\`\`

To inspect attributes and operations:

\`\`\`java
MBeanInfo info = server.getMBeanInfo(custom);
\`\`\`

You can inspect:

\`\`\`java
for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.println(attribute.getName());
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println(operation.getName());
}
\`\`\`

In an application with a custom MBeanServer, the platform server does not necessarily hold all registrations. In that case, use the exact server chosen by the exporter, or a JMX connector to that server.

## 16. Testing the Differences with Integration Tests

A useful test should confirm:

- The custom MBean is registered under the expected ObjectName.
- JMX attributes/operations are published accurately.
- The Actuator endpoint exists in the application context.
- The endpoint is exposed over the transport that the test actually configures.
- No unexpected endpoints/operations appear.
- After the context closes, registrations managed by the exporter are cleaned up.

Example custom MBean test:

\`\`\`java
ObjectName name = new ObjectName(
    "learning.jmx:type=QueueManagement,name=Primary"
);

assertTrue(server.isRegistered(name));

assertNotNull(server.getAttribute(name, "PendingJobs"));

server.invoke(name, "pause", new Object[0], new String[0]);
\`\`\`

When testing Actuator, use the right adapter:

- For web exposure: use an HTTP test client against the management endpoint.
- For JMX exposure: use \`MBeanServer\` or \`MBeanServerConnection\` and the ObjectName generated by Actuator.
- For endpoint availability: verify enablement/exposure per your Boot version's configuration.

Do not use the mere existence of an \`@Endpoint\` class as sole proof that web/JMX clients can already access it.

## 17. Common Pitfalls

| Symptom | Misconception or Cause | What to Check |
|---|---|---|
| \`@ManagedResource\` does not appear at \`/actuator\` | Custom MBean is not an Actuator endpoint | Use JMX exporter/connector; create a separate Actuator endpoint if HTTP is needed |
| \`@Endpoint\` does not appear in JConsole | JMX exposure not enabled / endpoint not enabled | Check Actuator JMX configuration and MBeanServer |
| Actuator endpoint has HTTP but not JMX | Exposures are configured differently | Check each transport |
| Custom MBean is in JConsole but has no HTTP | JMX does not automatically create HTTP routes | Use Actuator/web API if genuinely needed |
| Actuator ObjectName differs from expected | Actuator naming strategy/domain | Query the actual MBeanServer |
| Duplicate MBean name on startup | Multiple exporters or contexts registering together | Check ObjectName, exporter, and ownership |
| Remote JMX cannot connect | Missing connector, firewall, TLS, or credentials | Check transport and security separately |
| HTTP security works yet JMX operations can still be invoked | Two surfaces have different security | Protect JMX connector and methods |
| Metrics differ from custom MBean values | Different definitions, units, or timing | Standardize semantics and state source |
| Boot property changed yet MBean remains | Property only governs Actuator, not custom exporter | Distinguish the two registration paths |

## 18. Real-World Scenarios

### Scenario A — Monitoring Wants to Read Queue Depth

If the monitoring system primarily collects time-series data, consider Micrometer metrics/Actuator or the corresponding metrics endpoint. You do not necessarily need to create a custom MBean just to expose a counter.

### Scenario B — JConsole Needs to Pause/Resume a Scheduler

If the environment already uses JMX tooling and the action needs Java runtime management, a custom MBean with \`@ManagedOperation\` can fit well. You still must authorize JMX access and assess the operation's risk.

### Scenario C — One API for Both HTTP and JMX

If a custom operation fits the Actuator model and needs multiple transports, an \`@Endpoint\` can help. However, test each transport's adapter and representation; do not assume all parameter/return types share identical semantics.

### Scenario D — Two Data Sources

Actuator metrics and a custom MBean both report active connection counts yet give different numbers. Check sampling time, definition of active, units, synchronization, and implementation, rather than rushing to blame one side just because both appear in JConsole.

### Scenario E — MBean Still Visible After Changing Config

The team changed \`management.endpoints.jmx.exposure.include\` and the custom \`@ManagedResource\` remained. This may be completely expected: Actuator properties do not control every custom Spring JMX registration.

## 19. Practice Exercises

### Exercise 1 — Classify

Given two classes:

\`\`\`java
@Endpoint(id = "queueStatus")
class QueueStatusEndpoint { ... }
\`\`\`

and:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=Queue,name=Primary"
)
class QueueManagement { ... }
\`\`\`

Identify which class uses the Actuator API, which uses JMX metadata, and why they do not automatically share the same endpoint.

### Exercise 2 — Choose a Solution

You need to expose readiness health, collect request rates, and provide a reset-statistics operation for Java engineers. Choose Actuator health/metrics, Micrometer, and/or custom MBeans for each requirement. Explain the trade-offs.

### Exercise 3 — Experiment with Exposure

Configure a custom Actuator endpoint, expose it over web and then over JMX in a test environment. Compare the HTTP route with the ObjectName generated by Actuator and note the differences.

### Exercise 4 — Experiment with a Custom MBean

Create a \`@ManagedResource\` with \`@ManagedAttribute\` and \`@ManagedOperation\`. Use \`MBeanServer.isRegistered\` and \`getMBeanInfo\` to confirm registration. Verify that creating a custom MBean alone does not create a web route.

### Exercise 5 — Security

A system enables both Actuator HTTP and remote JMX. List the authentication, authorization, TLS, and network policies to evaluate separately for each connection path.

## 20. Design Checklist

Before choosing how to expose management functionality:

1. Is the primary consumer an HTTP client, a metrics system, or a JMX tool?
2. Are Actuator's built-in health/metrics needed?
3. Are JMX-specific attributes, operations, or notifications needed?
4. Does the same functionality need to be exposed over multiple transports?
5. Do the data contract and parameter/return types fit each adapter?
6. Is the ObjectName or endpoint ID stable enough for tooling?
7. Which exporter registers the bean and in which MBeanServer?
8. Is there a risk of duplicate registration when Boot auto-configuration meets custom config?
9. Are exposure and enablement configured accurately for the Boot version?
10. Are HTTP security and JMX security evaluated separately?
11. Are there state-changing operations that require restriction/auditing?
12. Are there integration tests covering the actual connection paths?

## 21. Core Takeaways

- An **Actuator endpoint** is Spring Boot's management endpoint model; it can be exposed over web or JMX depending on endpoint type and configuration.
- A **custom MBean** is a Java JMX managed object, usually registered via Standard MBean conventions or Spring Framework's JMX exporter.
- \`@Endpoint\` is not \`@ManagedResource\`; \`@ReadOperation\` is not \`@ManagedAttribute\`.
- An Actuator endpoint ID is not a JMX ObjectName.
- \`management.endpoints.jmx.exposure.*\` controls Actuator JMX exposure, not all custom MBeans.
- Enabling JMX exposure does not mean opening a remote connector; each transport requires separate security and connectivity.
- When using both, maintain a unified business data source and clear contracts for each adapter.
- Verify actual outcomes through MBeanServer, HTTP test clients, and the application context, rather than relying solely on annotations.

## References

- Spring Boot Reference — Actuator Endpoints: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Spring Boot Reference — JMX: https://docs.spring.io/spring-boot/reference/actuator/jmx.html
- Spring Boot Reference — Metrics: https://docs.spring.io/spring-boot/reference/actuator/metrics.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — ManagedResource: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedResource.html
- Spring Boot API — Endpoint: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/actuate/endpoint/annotation/Endpoint.html
