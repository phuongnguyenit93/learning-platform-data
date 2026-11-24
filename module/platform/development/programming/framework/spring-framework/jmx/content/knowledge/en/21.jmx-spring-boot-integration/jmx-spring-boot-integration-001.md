# Spring Boot Actuator and Its Relationship with JMX

> **Topic:** Spring Framework JMX  
> **Knowledge Group:** Spring Boot integration  
> **Lesson:** Spring Boot Actuator and Its Relationship with JMX

## 1. Objectives

After this lesson, you will be able to:

- Explain what **Spring Boot Actuator** is and why it can expose management information over **JMX**.
- Distinguish between **Actuator endpoint**, **Spring JMX MBean**, **MBeanServer**, and **remote JMX connector**.
- Understand the relationship between \`management.endpoints.jmx.exposure.*\` and \`spring.jmx.enabled\`.
- Configure Actuator endpoints to appear in JMX appropriately for your Spring Boot version.
- Distinguish between management over HTTP \`/actuator/*\` and management over JMX.
- Verify actually registered endpoints and MBeans using JConsole or \`MBeanServerConnection\`.
- Avoid accidentally exposing sensitive endpoints, using the wrong server/port, or mixing up Spring Framework export mechanisms with Spring Boot auto-configuration.

## 2. The Big Picture

**Spring Boot Actuator** adds endpoints for observing and managing an application, such as health, info, metrics, loggers, beans, env, and others depending on the version, dependencies, and configuration.

An Actuator endpoint is an application-layer concept. It can be exposed over multiple technologies if the environment supports them:

\`\`\`text
                    Spring Boot Application
                              |
                              v
                   Actuator endpoint model
                              |
                   +----------+----------+
                   |                     |
                   v                     v
              HTTP exposure        JMX exposure
                   |                     |
                   v                     v
             /actuator/...         MBean adapter
                                         |
                                         v
                                    MBeanServer
                                         |
                                         v
                                 JConsole/JMX client
\`\`\`

The **HTTP** and **JMX** paths have different exposure and security configurations. Making an endpoint accessible over HTTP does not automatically mean it is exposed over JMX, and vice versa.

Spring Boot can also export **application MBeans** declared with \`@ManagedResource\`, \`@ManagedAttribute\`, and \`@ManagedOperation\`. These MBeans differ from Actuator endpoint MBeans, even though they reside in the same JMX registry.

## 3. Distinguishing the Four Layers

| Layer | Purpose | Example |
|---|---|---|
| Application management | Defines management information/state | Actuator \`health\`, \`metrics\` |
| Exposure technology | Exposes endpoints over HTTP or JMX | \`/actuator/health\`, Actuator JMX MBean |
| JMX registry | Registers and manages MBeans | \`MBeanServer\`, \`ObjectName\` |
| Transport connector | Allows local/remote clients to access JMX | Local attach, RMI/JMXConnector |

\`management.endpoints.jmx.exposure.include\` determines which group of Actuator endpoints is exposed over JMX by Boot's mechanism. It **does not automatically create a remote RMI listener**. Conversely, opening a remote JMX connector does not mean Actuator has been added to the application or that all endpoints are exposed.

## 4. Dependency for Using Actuator

For a Spring Boot project using Maven:

\`\`\`xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
\`\`\`

Gradle Groovy DSL:

\`\`\`groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
\`\`\`

After adding the starter, Boot auto-configures the Actuator components appropriate for the environment, dependencies, and configuration.

Do not assume that all endpoints exist or are exposed. Some endpoints are conditional on the classpath, corresponding beans/systems, enablement settings, and the Spring Boot version.

## 5. Two Separate Configuration Axes: Enablement and Exposure

**Enablement** concerns whether an endpoint is created/activated in the application context; **exposure** concerns whether that endpoint is published over a specific transport.

A configuration might look like:

\`\`\`properties
management.endpoints.enabled-by-default=true
management.endpoint.health.enabled=true
management.endpoints.jmx.exposure.include=health,info
\`\`\`

Check the exact property names and defaults for your Boot version. In modern Boot versions, \`management.endpoints.jmx.exposure.include\` and \`exclude\` control the JMX exposure list.

\`\`\`text
Endpoint enabled?
          |
          No ---> no endpoint to expose
          |
         Yes
          |
          v
In JMX exposure include
and not excluded?
          |
          No ---> not exposed over JMX
          |
         Yes
          |
          v
Actuator JMX adapter -> MBeanServer
\`\`\`

Do not use a wildcard for all endpoints just for convenient debugging in production, because some endpoints contain configuration, environment properties, logger state, thread dumps, or administrative data that should not be widely exposed.

## 6. Configuring JMX Exposure in application.properties

Example limiting to two endpoints:

\`\`\`properties
management.endpoints.jmx.exposure.include=health,info
management.endpoints.jmx.exposure.exclude=
\`\`\`

Or YAML:

\`\`\`yaml
management:
  endpoints:
    jmx:
      exposure:
        include: health,info
\`\`\`

This is **Actuator JMX exposure** configuration, not pure Spring Framework \`@EnableMBeanExport\`.

In some environments, you may want to also expose metrics:

\`\`\`properties
management.endpoints.jmx.exposure.include=health,info,metrics
\`\`\`

However, only enable it once you understand the data/operations the endpoint provides and who has permission to use the MBeanServer.

### Include and exclude

Example:

\`\`\`properties
management.endpoints.jmx.exposure.include=*
management.endpoints.jmx.exposure.exclude=env,beans
\`\`\`

Wildcard configuration depends on the property binding mechanism and version; this illustrates the meaning of include/exclude, **not a production recommendation**. When using YAML, quote \`'*'\` for the wildcard value because \`*\` has special meaning in YAML.

An explicit allowlist configuration is usually safer and easier to inventory than wildcard + exclude.

## 7. How Does spring.jmx.enabled Relate?

Spring Boot supports the \`spring.jmx.enabled\` property to control the application's JMX feature via auto-configuration in the corresponding versions.

Example:

\`\`\`properties
spring.jmx.enabled=true
\`\`\`

General meaning: allows Spring Boot to configure the appropriate JMX export infrastructure. However, you must read the documentation for your exact version, because defaults, auto-configuration conditions, and how Actuator manages JMX can change across Boot releases.

Do not confuse:

- \`spring.jmx.enabled\`: Boot's policy for JMX auto-configuration.
- \`management.endpoints.jmx.exposure.include\`: which Actuator endpoints are exposed over JMX.
- \`management.endpoints.web.exposure.include\`: which Actuator endpoints are exposed over HTTP.
- Remote connector agent flags: whether the MBeanServer can be accessed over the network.

Enabling \`spring.jmx.enabled=true\` does not mean the JVM automatically opens a remote JMX port.

## 8. Actuator Endpoints and @ManagedResource Are Two Different Paths

A custom-written bean:

\`\`\`java
@Component
@ManagedResource(
    objectName = "app.management:type=WorkerPool,name=primary"
)
public class WorkerPoolMonitor {

    @ManagedAttribute
    public int getActiveWorkers() {
        return 3;
    }

    @ManagedOperation
    public void resetCounters() {
        // ...
    }
}
\`\`\`

This is a **Spring JMX annotated bean**, not an Actuator endpoint just because it uses management annotations.

A custom-written Actuator endpoint can use \`@Endpoint\`:

\`\`\`java
import java.util.Map;
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "queueStatus")
public class QueueStatusEndpoint {

    @ReadOperation
    public Map<String, Object> status() {
        return Map.of(
            "active", true,
            "pending", 12
        );
    }
}
\`\`\`

This is an Actuator-level endpoint. With the appropriate exposure and technology adapter, this endpoint can be published over HTTP or JMX according to policy.

Two kinds of components:

\`\`\`text
@ManagedResource
    -> Spring JMX exporter -> MBean

@Endpoint / @ReadOperation
    -> Actuator endpoint model
    -> JMX exposure adapter -> MBean
\`\`\`

Therefore, a codebase can have both application MBeans and Actuator MBeans at the same time, but you must avoid duplicate \`ObjectName\`s, domains, and overlapping exporters.

## 9. Actuator MBean Naming Conventions

Actuator endpoints exposed over JMX are registered under an ObjectName determined by Boot's naming strategy and JMX domain. In many Boot configurations, the default domain relates to \`org.springframework.boot\`, and the key properties describe the endpoint.

You can customize the domain using a Boot property such as:

\`\`\`properties
management.endpoints.jmx.domain=com.example.management
\`\`\`

Depending on the Spring Boot version, the naming strategy and how ObjectNames are generated may vary. **Do not hardcode Actuator ObjectNames from memory**; use \`MBeanServer.queryNames\` or JConsole to inspect the actual registered names.

Example querying a domain:

\`\`\`java
ObjectName pattern = new ObjectName(
    "com.example.management:*"
);

for (ObjectName name :
        connection.queryNames(pattern, null)) {
    System.out.println(name.getCanonicalName());
}
\`\`\`

If multiple Spring application contexts exist in the same JVM, configuring different domains can help avoid name collisions and clarify ownership.

## 10. How Does Accessing Actuator over HTTP Differ from JMX?

HTTP example:

\`\`\`text
GET /actuator/health
GET /actuator/info
GET /actuator/metrics
\`\`\`

JMX can represent endpoints as MBean operations that clients invoke, with data types converted appropriately by the JMX technology adapter.

| Characteristic | HTTP Actuator | JMX Actuator |
|---|---|---|
| Entry point | HTTP server / management HTTP port | MBeanServer / connector |
| Identifier | Endpoint URL | ObjectName |
| Client | curl, browser, HTTP monitoring | JConsole, Java JMX client |
| Methods | HTTP GET/POST/DELETE per operation | JMX MBean operations/attributes depending on adapter |
| Security | HTTP security chain, network, auth | JMX connector security/host access |
| Exposure | \`management.endpoints.web.exposure.*\` | \`management.endpoints.jmx.exposure.*\` |
| Port opened | Web server / management port | Remote JMX connector if configured |

Do not infer that an endpoint permitted over HTTP will automatically have the same authorization when accessed over JMX. Security for the two channels must be designed independently.

## 11. Example Verification Using JConsole

After adding the Actuator starter and enabling JMX exposure:

1. Start the Spring Boot application and note the JVM's PID.
2. Open \`jconsole\` from the appropriate JDK.
3. Select the correct local Java process.
4. Open the **MBeans** tab.
5. Find the actual Actuator domain, for example \`org.springframework.boot\` or a custom domain.
6. Select the MBean corresponding to \`health\`, \`info\`, or \`metrics\`.
7. Read metadata/operations; only invoke operations that are safe in the running environment.
8. If the endpoint is not visible, check the starter, enablement, exposure, auto-configuration, and MBeanServer.

Some JDKs/JConsole versions may not render structured Actuator results as cleanly as HTTP JSON. That is a UI/adapter difference, not necessarily missing data.

## 12. Verification Using MBeanServerConnection

To avoid relying on a UI, you can query MBeans via API:

\`\`\`java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.MBeanInfo;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

Set<ObjectName> names =
    server.queryNames(
        new ObjectName("org.springframework.boot:*"),
        null
    );

for (ObjectName name : names) {
    MBeanInfo info = server.getMBeanInfo(name);
    System.out.println(name.getCanonicalName());
    System.out.println(info.getDescription());
}
\`\`\`

This snippet assumes Actuator exports MBeans on the **platform MBeanServer** and uses the corresponding domain. For a custom domain, change the pattern; for a custom server, obtain a connection to the exact server used by the exporter.

\`queryNames\` reflects the current registry. Not finding an ObjectName on the platform MBeanServer **does not prove** the application lacks Actuator; the endpoint might not be exposed, might use a different domain, or the exporter might use a different server.

## 13. Inspecting Operation Lists and Signatures

Actuator MBeans can expose operations with names and data types generated by the adapter. Read the metadata:

\`\`\`java
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.print(op.getName() + "(");

    MBeanParameterInfo[] ps = op.getSignature();

    for (int i = 0; i < ps.length; i++) {
        if (i > 0) {
            System.out.print(", ");
        }
        System.out.print(ps[i].getType());
    }

    System.out.println(") -> " + op.getReturnType());
}
\`\`\`

When you need to invoke an operation, use the exact signature from the metadata:

\`\`\`java
Object result = server.invoke(
    name,
    operationName,
    params,
    signature
);
\`\`\`

Do not guess that the \`health\` operation is named \`health()\` in JMX. The endpoint ID and the MBean operation name may differ from the HTTP representation. The actual metadata of the running version is the source for clients to construct invocations.

## 14. Custom Actuator Endpoints Can Have State-Changing Operations

Actuator supports annotations such as \`@ReadOperation\`, \`@WriteOperation\`, and \`@DeleteOperation\` for endpoints.

Example:

\`\`\`java
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.WriteOperation;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "cacheMaintenance")
public class CacheMaintenanceEndpoint {

    private final CacheMaintenanceService service;

    public CacheMaintenanceEndpoint(
            CacheMaintenanceService service
    ) {
        this.service = service;
    }

    @WriteOperation
    public void refresh(String cacheName) {
        service.refresh(cacheName);
    }
}
\`\`\`

\`CacheMaintenanceService\` is an illustrative application dependency. A write operation can affect real state. If an endpoint is exposed over multiple technologies, you must examine side effects and security on every access path.

Do not place data-deletion or sensitive configuration-changing operations on an endpoint and then expose it broadly just for convenience of observation.

## 15. Relationship with Spring Boot Auto-Configuration

Spring Boot can create JMX infrastructure beans based on the classpath and properties. This reduces manual configuration, but can easily cause confusion when the application already declares an exporter:

\`\`\`text
Boot auto-configuration
      |
      +-- JMX/Actuator infrastructure
      |
      v
MBeanServer

Developer configuration
      |
      +-- @EnableMBeanExport
      +-- Manual MBeanExporter bean
\`\`\`

If two exporters register the same Spring bean under the same ObjectName on one MBeanServer, a registration conflict can occur. Do not use \`RegistrationPolicy.REPLACE_EXISTING\` by default to mask duplicate exporter errors.

You should inventory the actual exporters, identify which component owns each MBean, and avoid duplicate registrations. With Boot, first check how the running version's auto-configuration behaves, and only add manual configuration when truly necessary.

## 16. Remote JMX Is Not the Management HTTP Port

Two kinds of ports can exist:

\`\`\`text
HTTP Management Port
  -> Spring Boot embedded web server
  -> /actuator/*

Remote JMX Port(s)
  -> JMXConnector/RMI
  -> MBeanServer
\`\`\`

\`management.server.port\` typically configures the HTTP management server port in appropriate Boot versions; it is **not** the property that specifies the JMX RMI registry port.

Remote JMX usually has its own agent/connector configuration, for example JDK system properties:

\`\`\`text
-Dcom.sun.management.jmxremote
-Dcom.sun.management.jmxremote.port=9010
-Dcom.sun.management.jmxremote.rmi.port=9011
-Djava.rmi.server.hostname=jmx.example.internal
\`\`\`

When enabling remote access, you must set up appropriate authentication, authorization, TLS, and firewall rules. Do not expose the JMX port to the public Internet just to monitor Actuator.

A client tool might connect to remote JMX successfully yet see no Actuator MBeans if the connector exposes a different server than the exporter uses; inspect the actual registry rather than checking only the URL.

## 17. HTTP Security and JMX Security Are Two Separate Problems

An HTTP example:

\`\`\`text
GET /actuator/env
\`\`\`

can be controlled by a Spring Security HTTP filter chain or a reverse proxy network layer. However, JMX access passes through JMX connectors and permissions, not necessarily through HTTP filters.

Therefore:

- Do not assume HTTP security policies protect JMX operations.
- Do not use wildcard exposure on both channels without evaluating the data.
- Only expose Actuator endpoints needed for operations.
- Restrict remote JMX by identity, network, and permissions.
- Avoid having custom endpoints return secrets or personal data.
- Verify sanitization and the actual data returned for your Boot version.
- Document ownership and purpose for each management endpoint.

In many systems, read-only monitoring information such as health/metrics is sufficient; there is no need to expose all endpoints capable of mutating state.

## 18. Health, Info, and Metrics

### Health

The health endpoint reflects application health and can have multiple contributors. If the JMX adapter exposes health, a client can invoke the corresponding operation to obtain the result.

Do not assume health details are always shown in full; visibility can depend on configuration, client roles, and the technology adapter.

### Info

The info endpoint contains configured information or data contributed by an \`InfoContributor\`. Do not place secrets, sensitive identifiers, or the entire environment into info just for convenient debugging.

### Metrics

The metrics endpoint provides a way to query meters/measurements managed by Micrometer and Boot according to configuration. It does not mean every metric automatically gets a separate JMX attribute.

For large-scale observability systems, Micrometer metrics can be exported via a dedicated metrics system. JMX is one management access option, not the only choice or always optimal for time-series collection.

## 19. A Verification Example Independent of MBean Name Assumptions

Suppose the application has the Actuator JMX domain:

\`\`\`properties
management.endpoints.jmx.domain=com.example.actuator
management.endpoints.jmx.exposure.include=health,info
\`\`\`

Client:

\`\`\`java
ObjectName pattern = new ObjectName(
    "com.example.actuator:*"
);

Set<ObjectName> objects =
    connection.queryNames(pattern, null);

for (ObjectName objectName : objects) {
    MBeanInfo info = connection.getMBeanInfo(objectName);

    System.out.println(objectName);
    System.out.println("Attributes: " + info.getAttributes().length);
    System.out.println("Operations: " + info.getOperations().length);
}
\`\`\`

Next, open JConsole and cross-check the discovered ObjectNames. This approach is better than hardcoding \`org.springframework.boot:type=Endpoint,name=Health\` for all versions/configurations.

## 20. Troubleshooting When Actuator MBeans Are Missing

| Symptom | Possible Cause | Check |
|---|---|---|
| No Actuator domain | Missing starter, JMX exposure off, exporter not active | Dependencies, application properties |
| HTTP endpoints exist but not JMX | The two exposures are independent | \`management.endpoints.jmx.exposure.*\` |
| Application MBeans exist but not Actuator | Annotation exporter works, Actuator JMX adapter not exposing | Actuator auto-configuration |
| Actuator MBeans exist but not custom \`@ManagedResource\` | Actuator MBeans and annotated beans are different mechanisms | Spring JMX exporter |
| Local JConsole cannot see it | Wrong JVM or server other than platform server | PID, MBeanServer |
| Remote JMX connects OK but endpoints are missing | Connector exposes a different registry or different domain | \`queryNames\`, exporter/server |
| Duplicate ObjectName on startup | Multiple exporters/endpoints with colliding names | Exporter ownership, naming |
| HTTP 404 but JMX has the MBean | HTTP endpoint not exposed or different base path | Web exposure |
| HTTP returns 401/403 but JMX works | Security policies are not identical | Check JMX permissions separately |
| Empty/hard-to-read metrics | Meter does not exist or adapter renders differently | Check meter registry, metadata |

## 21. Distinguishing Actuator from a JMX Metrics Exporter

Spring Boot Actuator has a **metrics endpoint**, while Micrometer can also use a **JMX meter registry** to export meters directly as MBeans in a separate metrics domain.

\`\`\`text
Micrometer MeterRegistry
         |
         +--> Actuator metrics endpoint
         |          |
         |          +--> HTTP/JMX exposure
         |
         +--> JMX meter registry
                    |
                    +--> Metrics MBeans
\`\`\`

These are different publication paths. If you see many metrics MBeans in JConsole, check which component registered them, which domain is used, and whether duplication exists.

Do not treat \`management.endpoints.jmx.exposure.include=metrics\` as equivalent to configuring a Micrometer JMX registry that exports every meter as an independent MBean.

## 22. Multi-ApplicationContext Environments

In applications with parent/child contexts or multiple Spring Boot applications in the same JVM, you may encounter:

- Multiple exporters.
- Multiple endpoints with the same ID.
- ObjectName collisions.
- Different MBeanServers.
- Overlapping JMX domains.
- A connector accessing only one server.

In such cases, determine:

1. Which context owns the endpoint?
2. Which exporter publishes the endpoint?
3. What is the exact ObjectName?
4. Which MBeanServer does the exporter use?
5. Which server is the client connecting to?

Sharing a JVM does not guarantee all MBeans reside in a single registry.

## 23. When to Choose HTTP Actuator vs. JMX?

**HTTP Actuator** is typically a good fit when infrastructure already uses HTTP monitoring, reverse proxies, health probes, or service discovery. It integrates easily with many observability systems, though it requires web exposure and HTTP security configuration.

**JMX Actuator** fits when operations tooling relies on JConsole or JMX clients/agents, or when you need to inspect the JVM registry alongside other MBeans. With local attachment, an HTTP endpoint may not be needed.

Both can coexist. The choice should not rely solely on "which is easier to turn on", but also on access permissions, network policy, data types, query frequency, and the tools your clients actually use.

## 24. Practice Exercises

### Exercise 1: Expose Only health and info over JMX

Add the Actuator starter and configure:

\`\`\`properties
spring.jmx.enabled=true
management.endpoints.jmx.exposure.include=health,info
\`\`\`

Run the application, open local JConsole, find the real Actuator domain, and inspect the metadata of the MBeans that appear. If none appear, check your Boot version, enablement, and MBeanServer.

### Exercise 2: Compare HTTP and JMX

Intentionally enable HTTP exposure as well:

\`\`\`properties
management.endpoints.web.exposure.include=health,info
\`\`\`

Compare \`/actuator/health\` data with the corresponding JMX operation. Note that representation, security, and details visibility may differ; do not draw conclusions solely from the displayed output string.

### Exercise 3: Custom endpoint

Create an \`@Endpoint(id = "queueStatus")\` with a \`@ReadOperation\` returning non-sensitive summary data. Configure JMX exposure; use \`queryNames\` and \`getMBeanInfo\` to confirm the actual endpoint.

### Exercise 4: Investigate the wrong MBeanServer

Create a custom MBeanServer and observe an exporter assigned to this server while local JConsole inspects the platform MBeanServer. Explain why the MBean is not visible and propose a configuration that unifies the server or uses an appropriate connector.

## 25. Self-Check Questions

1. Is an Actuator endpoint directly synonymous with \`@ManagedResource\`?
2. Why does \`@EnableMBeanExport\` not automatically open a remote JMX port?
3. What is the difference between \`management.endpoints.web.exposure.include\` and \`management.endpoints.jmx.exposure.include\`?
4. Why should you not guess an Actuator ObjectName solely from the endpoint ID?
5. In which registry does the JMX adapter publish endpoints?
6. Why does HTTP authorization not automatically protect a JMX operation?
7. How do \`spring.jmx.enabled\` and endpoint exposure carry two different meanings?
8. How does a JMX meter registry differ from the Actuator metrics endpoint?
9. If local JConsole does not see Actuator, which layers should you check?
10. When there are multiple exporters in the same JVM, what is the risk of registration conflicts?

## 26. Key Takeaways

\`\`\`text
Spring Boot Actuator
    |
    +--> Endpoint enablement
    |
    +--> HTTP exposure
    |       -> /actuator/*
    |
    +--> JMX exposure
            -> Actuator MBean adapter
            -> MBeanServer
            -> JConsole / JMX connector

Spring @ManagedResource
    -> Spring JMX exporter
    -> MBeanServer

Remote JMX connector
    -> network path to MBeanServer
    -> not automatically enabled just because Actuator is present
\`\`\`

**Core principle:** Actuator is Spring Boot's management endpoint model; JMX is one technology for exposing those endpoints. Spring's JMX annotation exporter is a separate path for publishing application MBeans. Control enablement, JMX/HTTP exposure, MBeanServer, remote connectors, and security independently so you know precisely **what** is published and **who** can use it.