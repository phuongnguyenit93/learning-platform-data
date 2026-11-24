# management.endpoints.jmx.exposure.include in Spring Boot Actuator

## 1. Overview

In Spring Boot Actuator, **management endpoints** provide operational information and actions such as health, info, metrics, environment, beans, or loggers. An endpoint can be exposed over different technologies, typically **HTTP** and **JMX**, depending on configuration and capability support.

The property:

\`\`\`properties
management.endpoints.jmx.exposure.include=health,info
\`\`\`

specifies **which Actuator endpoint IDs are allowed to be exposed over JMX**. This is an endpoint-ID allowlist for the JMX technology, not a configuration to open a remote JMX connection port and not a mechanism to select all Spring beans to export as MBeans.

Key point to remember:

> **Exposure** decides which endpoints appear over a management technology; **access** decides whether an endpoint is available for access or restricted; **transport/security** decides which clients can actually connect and perform operations.

Spring Boot versions may change the default endpoint list, access properties, and JMX enabling conditions. When deploying, cross-check the documentation for the exact version in use.

### Lesson Objectives

After this lesson, you will be able to:

1. Explain the meaning of \`management.endpoints.jmx.exposure.include\`.
2. Configure include/exclude using \`application.properties\` or YAML.
3. Distinguish JMX exposure from HTTP exposure.
4. Understand the relationship between Actuator JMX endpoints, \`spring.jmx.enabled\`, \`MBeanExporter\`, and \`MBeanServer\`.
5. Weigh the risks of using \`*\` for broad exposure.
6. Verify whether an endpoint actually appears on the MBeanServer.
7. Troubleshoot situations where configuration looks right but a JMX client does not see the endpoint.

## 2. Actuator Endpoints and Exposure Technologies

Spring Boot Actuator uses endpoint IDs such as:

\`\`\`text
health
info
metrics
env
beans
loggers
threaddump
heapdump
configprops
conditions
mappings
scheduledtasks
\`\`\`

The actual list of endpoints depends on dependencies, Spring Boot version, auto-configuration, runtime conditions, and whether an endpoint is suitable for the exposure technology. Do not assume all IDs above always exist or always support both HTTP and JMX.

Model:

\`\`\`text
             Spring Boot Application
                        |
                        v
                Actuator endpoints
                 /            \
                /              \
        Web exposure        JMX exposure
             |                  |
     HTTP management        MBeanServer
           routes                |
             |                  |
       HTTP clients          JMX clients
\`\`\`

The two branches are configured independently:

\`\`\`properties
management.endpoints.web.exposure.include=health,info
management.endpoints.jmx.exposure.include=health,info,metrics
\`\`\`

In the example above, an endpoint can be exposed over JMX without being exposed over HTTP, or vice versa.

**Do not confuse** \`management.endpoints.jmx.exposure.include\` with \`management.endpoints.web.exposure.include\`: the former is for JMX, and the latter is for HTTP.

## 3. Syntax in application.properties

Configuring a few endpoints:

\`\`\`properties
management.endpoints.jmx.exposure.include=health,info,metrics
\`\`\`

Configuring just one endpoint:

\`\`\`properties
management.endpoints.jmx.exposure.include=health
\`\`\`

Configuring all endpoints eligible for JMX exposure:

\`\`\`properties
management.endpoints.jmx.exposure.include=*
\`\`\`

Using include and exclude together:

\`\`\`properties
management.endpoints.jmx.exposure.include=*
management.endpoints.jmx.exposure.exclude=env,beans
\`\`\`

In exposure configuration, **exclude is applied to remove included endpoints**. Thus, with \`include=*\` and \`exclude=env,beans\`, those two endpoint IDs are omitted from the JMX-exposed set.

However, this "open everything then subtract" style can cause new endpoints to appear when upgrading Spring Boot or adding dependencies. For environments with strict control requirements, an explicit allowlist is usually easier to review.

### What Does the Wildcard * Mean?

\`*\` selects all eligible endpoint IDs; it is not a JMX \`ObjectName\` pattern and not an HTTP route wildcard.

Specifically:
- \`include=*\` does not create endpoints that do not already exist.
- \`include=*\` does not bypass disabled endpoints, restricted access, or lack of JMX support.
- \`include=*\` does not enable a remote JMX connector or grant access permissions.
- \`include=*\` does not turn every Spring bean into an Actuator endpoint.

## 4. YAML Configuration

In \`application.yml\`:

\`\`\`yaml
management:
  endpoints:
    jmx:
      exposure:
        include: "health,info,metrics"
        exclude: "env"
\`\`\`

Or a YAML list:

\`\`\`yaml
management:
  endpoints:
    jmx:
      exposure:
        include:
          - health
          - info
          - metrics
\`\`\`

When using \`*\` in YAML, **you must put it in quotes**, because the asterisk has YAML alias syntax meaning:

\`\`\`yaml
management:
  endpoints:
    jmx:
      exposure:
        include: "*"
\`\`\`

Do not write:

\`\`\`yaml
management:
  endpoints:
    jmx:
      exposure:
        include: *
\`\`\`

because that is not a valid YAML scalar with the wildcard meaning you intend.

### Reading the Property Name

\`\`\`text
management . endpoints . jmx . exposure . include
    |            |       |       |         |
management   Actuator    JMX   exposed    included
                               over JMX     IDs
\`\`\`

This is a **Spring Boot Actuator** configuration, not a direct standard JMX API.

## 5. Per-Environment Configuration

An application may want different exposure between development and production.

\`application-dev.yml\`:

\`\`\`yaml
management:
  endpoints:
    jmx:
      exposure:
        include: "*"
\`\`\`

\`application-prod.yml\`:

\`\`\`yaml
management:
  endpoints:
    jmx:
      exposure:
        include: "health,info,metrics"
\`\`\`

These are illustrative examples only. In production, exposed endpoints must be based on the permission model and actual needs, not a default assumption that health/info/metrics are all harmless.

You can use environment variables via Spring Boot's relaxed binding rules, for example:

\`\`\`text
MANAGEMENT_ENDPOINTS_JMX_EXPOSURE_INCLUDE=health,info,metrics
\`\`\`

Precedence rules across configuration files, environment variables, command-line arguments, and other Spring Boot property sources still apply. If the runtime value does not match the config file, check the process's **effective configuration**, not just one \`application.yml\` file.

## 6. Relationship with spring.jmx.enabled

A related property with a different purpose is:

\`\`\`properties
spring.jmx.enabled=true
\`\`\`

\`spring.jmx.enabled\` controls whether Spring Boot enables the JMX export mechanism according to the corresponding version's configuration.

Meanwhile:

\`\`\`properties
management.endpoints.jmx.exposure.include=health,info
\`\`\`

specifies the set of **Actuator endpoints** exposed over JMX.

Differences:

| Property | Scope |
|---|---|
| \`spring.jmx.enabled\` | Enables/disables Spring Boot JMX export within auto-configuration |
| \`management.endpoints.jmx.exposure.include\` | Includes Actuator endpoint IDs over JMX |
| \`management.endpoints.jmx.exposure.exclude\` | Excludes endpoint IDs from JMX exposure |
| \`management.endpoints.web.exposure.include\` | Includes endpoint IDs over HTTP |
| \`management.endpoints.web.exposure.exclude\` | Excludes endpoint IDs from HTTP exposure |

If \`spring.jmx.enabled=false\` in the effective runtime configuration, setting Actuator JMX include is not a substitute for enabling the export infrastructure.

### An Illustrative Configuration

\`\`\`properties
spring.jmx.enabled=true

management.endpoints.jmx.exposure.include=health,info,metrics
management.endpoints.jmx.exposure.exclude=env
\`\`\`

This configuration expresses the intent: enable JMX integration and expose only the listed endpoint IDs (minus any overlapping excluded IDs).

Check your Spring Boot version because default values, endpoint access properties, and some auto-configuration behaviors can vary across Boot generations.

## 7. Exposure, Enablement, and Access Are Three Different Concepts

An endpoint only appears when all relevant conditions are satisfied.

### 7.1. Enablement

The endpoint must exist and be enabled by auto-configuration/endpoint enablement. A disabled endpoint will not be restored merely by \`exposure.include\`.

### 7.2. Exposure

An existing endpoint must be published over JMX. This is the role of \`management.endpoints.jmx.exposure.include\` and \`exclude\`.

### 7.3. Access

Newer Spring Boot versions may use \`management.endpoint.<id>.access\` or \`management.endpoints.access.default\` to specify access levels such as none, read-only, or unrestricted. These properties cannot replace exposure; they also depend on the specific version.

An interpretive model:

\`\`\`text
Endpoint definition exists?
          |
          v
Endpoint enabled?
          |
          v
Endpoint access permits operation?
          |
          v
Endpoint included for JMX?
          |
          v
JMX MBean available?
          |
          v
Connector/security permits caller?
          |
          v
Remote client can interact
\`\`\`

Internal ordering may differ by implementation, but operationally **all conditions** must be evaluated. Having a line \`include=health\` does not guarantee a health MBean exists on every JVM.

## 8. Include Only What Is Needed

Suppose you need three management goals:

- \`health\`: system health information per the endpoint contract.
- \`info\`: operational metadata configured to be provided.
- \`metrics\`: querying certain available metrics via Actuator.

Configuration:

\`\`\`properties
management.endpoints.jmx.exposure.include=health,info,metrics
\`\`\`

This is easy to inventory. When the application adds a dependency with a new endpoint, that endpoint is not automatically exposed over JMX unless added to the include list.

Still, check:
- Do health details contain infrastructure information?
- Do info contributors expose information that should not be published?
- Do metrics have high-cardinality tags or sensitive information?
- Are JMX callers permitted to read all of that data?
- Is remote JMX network-restricted?

A read-only endpoint can still leak system topology or sensitive operational information.

## 9. Risks of include=*

The configuration:

\`\`\`properties
management.endpoints.jmx.exposure.include=*
\`\`\`

can be convenient in development or testing to discover endpoints, but requires caution in production.

Risks:

1. **Expansion by dependency:** a new library/starter may provide an endpoint you have not reviewed.
2. **Expansion by upgrade:** a newer Boot version may introduce new endpoint IDs or exposure behaviors.
3. **Sensitive metadata:** some endpoints describe the environment, mappings, beans, or runtime configuration.
4. **State-changing operations:** depending on endpoint/access, some management actions may not be read-only.
5. **Hard to audit:** the effective set of endpoints is large and varies by environment.
6. **Difference between HTTP and JMX:** closing HTTP exposure does not mean JMX exposure is closed.

A more conservative configuration:

\`\`\`properties
management.endpoints.jmx.exposure.include=health,info
\`\`\`

The final choice depends on operational needs. Do not declare a fixed allowlist as always safe; every endpoint must still be reviewed for its data and usage permissions.

## 10. Actuator JMX Endpoints and MBeanServer

When an Actuator endpoint is exposed over JMX, Spring Boot manages registering that endpoint's MBean representation into \`MBeanServer\`.

Model:

\`\`\`text
Actuator endpoint "health"
              |
              v
Actuator JMX exposure infrastructure
              |
              v
MBeanServer
              |
              v
ObjectName (Actuator-managed)
              |
              v
JConsole / JMX client
\`\`\`

Important points:

- This is not necessarily the same class or same ObjectName as an application-created \`@ManagedResource\` bean.
- Actuator uses its own naming strategy and domain/rules based on Spring Boot configuration.
- Do not guess an ObjectName from an endpoint ID by arbitrary string concatenation.
- If multiple applications or multiple application contexts exist in the same JVM, check whether JMX names collide.
- \`MBeanServer\` may be the platform MBeanServer or a suitably configured server.

The reliable way to verify is to query the **actual MBeanServer** and see which ObjectNames have been registered.

## 11. Using JConsole to Verify

After starting an application with JMX support:

1. Connect JConsole to the **correct JVM**.
2. Open the **MBeans** tab.
3. Locate the domain containing the application's Actuator MBeans.
4. Compare the configured endpoint IDs with the actual MBeans.
5. Inspect exposed operations/attributes.
6. If an endpoint is missing, check effective configuration, enablement, access, and the JMX exporter.

Checking only the YAML file without inspecting runtime can easily miss:
- A production profile overriding the include list.
- \`spring.jmx.enabled\` being off.
- An endpoint not created due to dependencies/conditions.
- An endpoint restricted by access settings.
- Connecting to the wrong JVM or wrong MBeanServer.
- JMX export or registration failing with an error.

### A Programmatic Check

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

for (ObjectName name : server.queryNames(null, null)) {
    String canonical = name.getCanonicalName();

    if (canonical.contains("endpoint")) {
        System.out.println(canonical);
    }
}
\`\`\`

This is only a preliminary discovery example, not an official naming contract. In practice, choose the domain/pattern based on ObjectNames actually registered by Spring Boot rather than using \`contains("endpoint")\` as a mandatory test criterion.

Use \`getMBeanInfo()\` to inspect operations and descriptions:

\`\`\`java
MBeanInfo info = server.getMBeanInfo(objectName);

for (var operation : info.getOperations()) {
    System.out.println(operation.getName());
}
\`\`\`

If Spring Boot exports into an MBeanServer other than the platform server, query that exact server.

## 12. Complete Spring Boot Actuator Example

Maven dependency (version managed by the Spring Boot BOM):

\`\`\`xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
\`\`\`

\`application.yml\`:

\`\`\`yaml
spring:
  jmx:
    enabled: true

management:
  endpoints:
    jmx:
      exposure:
        include:
          - health
          - info
          - metrics
        exclude:
          - env
    web:
      exposure:
        include:
          - health
\`\`\`

Configuration intent:

- Include the Actuator dependency to provide the appropriate endpoints.
- Enable Spring Boot JMX export integration.
- Expose \`health\`, \`info\`, and \`metrics\` over JMX if the endpoints exist and access allows.
- Do not expose \`env\` over JMX under this configuration.
- Only expose \`health\` over HTTP per web include.

This is an exposure scope example, not a complete security configuration. If a remote connector exists, configure authentication/authorization/network protection separately.

### Why Manage HTTP and JMX Separately?

An organization may want:
- The HTTP health endpoint called by a load balancer.
- JMX metrics reserved for Java operations/monitoring tools.
- The JMX loggers endpoint not exposed because it changes runtime log levels.
- HTTP admin endpoints not exposed publicly over the internet.

The two technologies have different users and access models; separating include lists keeps intent clear.

## 13. JMX Endpoints Do Not Mean a Remote JMX Connector

A common misconception:

\`\`\`properties
management.endpoints.jmx.exposure.include=health,info,metrics
\`\`\`

**does not mean** the application starts listening on a TCP port for remote JMX.

To connect from another machine, a **JMXConnectorServer** or the JVM's remote management mechanism is required, such as a configured RMI connector.

\`\`\`text
Spring Boot Actuator
       |
       v
JMX endpoint MBeans
       |
       v
MBeanServer
       |
       v
JMXConnectorServer <-- configured separately
       |
       v
Remote JMX client
\`\`\`

Opening the port also involves:
- RMI registry/connector endpoint ports.
- Advertised hostname.
- Docker/Kubernetes port mapping.
- Firewall, ACLs, and routing.
- TLS and authentication.
- Operation invocation permission policies.

An endpoint "exposed through JMX" can be observable by local JMX tooling while still unreachable over the network, and that is not necessarily an error.

## 14. Security and Access Control

### Exposure Does Not Replace Security

You can picture it as:

\`\`\`text
Actuator endpoint exists
         |
         v
Enabled and accessible
         |
         v
Included in JMX exposure
         |
         v
Registered in MBeanServer
         |
         v
Connector accepts client
         |
         v
Authorization permits operation
\`\`\`

A client might fail to access an included endpoint because:
- The network is blocked.
- The JMX connector is not enabled.
- Credentials are wrong.
- The caller is not authorized to perform the operation.
- The endpoint's access level does not allow the desired operation.

Conversely, if remote JMX is configured too broadly, endpoint exposure can widen the management surface. Do not use \`include=*\` without evaluating the impact.

### Endpoints Requiring Special Consideration

Some types of endpoints may contain information about:
- Environment/property sources.
- Bean dependency graph.
- HTTP request mappings.
- Loggers configuration.
- Heap dumps or thread dumps.
- Application runtime state.

Sensitivity depends on how the application configures endpoints and data masking policies. **Do not assume that because an endpoint displays sanitized values, every value is safe to expose broadly.**

Operations can modify configuration, generate dumps, or affect performance. Evaluate them individually before granting caller access.

## 15. Include and Exclude: Reasoning About the Resulting Endpoint Set

Suppose the available endpoints are:

\`\`\`text
health, info, metrics, env, beans, loggers
\`\`\`

With:

\`\`\`properties
management.endpoints.jmx.exposure.include=health,info,metrics
management.endpoints.jmx.exposure.exclude=metrics
\`\`\`

The selected set to expose is:

\`\`\`text
health, info
\`\`\`

With:

\`\`\`properties
management.endpoints.jmx.exposure.include=*
management.endpoints.jmx.exposure.exclude=env,beans
\`\`\`

The selected set is all eligible endpoints except \`env\` and \`beans\`.

With:

\`\`\`properties
management.endpoints.jmx.exposure.include=
\`\`\`

the intent is to include no endpoints over JMX, though when configuring across multiple property sources or different Boot versions, check the effective bound value and applicable defaults. Do not treat an empty line in one file as final proof when the system has profile overrides.

### Do Not Confuse Endpoint-ID Include with an ObjectName Pattern

\`\`\`properties
management.endpoints.jmx.exposure.include=health,info
\`\`\`

is completely different from:

\`\`\`java
new ObjectName("org.springframework.boot:*");
\`\`\`

The first is an Actuator policy. The second is a JMX ObjectName query pattern, which can match many types of MBeans. Use the right conceptual layer when debugging.

## 16. Configuring Multiple Spring Boot Applications in One JVM

If multiple application contexts or Spring Boot components share an MBeanServer, ObjectName collisions can occur.

An application with Actuator JMX endpoints can use Boot's naming conventions and unique names. When multiple application contexts are created in the same JVM, consult the naming or domain options appropriate to your version, and verify in practice via \`queryNames()\`.

**Do not solve collision issues by expanding the include list.** Include decides which endpoints are exposed; it does not ensure unique names.

You need to:
- Have a stable naming convention.
- Know which exporter owns each MBean.
- Avoid creating multiple exporters with overlapping roles.
- Check for registration failures at startup.
- Verify cleanup when contexts close.

## 17. Difference Between Actuator JMX and @ManagedResource

This is a common point of confusion in projects that have both Spring Framework JMX and Boot Actuator.

### @ManagedResource

\`\`\`java
@ManagedResource(
    objectName = "com.example.monitoring:type=Cache,name=Products"
)
public class CacheMonitor {

    @ManagedAttribute
    public int getSize() {
        return 42;
    }
}
\`\`\`

The Spring JMX exporter mechanism creates an MBean according to management metadata.

### Actuator endpoint

\`\`\`java
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "customstatus")
public class CustomStatusEndpoint {

    @ReadOperation
    public String status() {
        return "UP";
    }
}
\`\`\`

The Actuator exposure infrastructure can expose the \`customstatus\` endpoint over JMX if:
- The endpoint is created.
- Enablement/access allows it.
- \`customstatus\` is included via \`management.endpoints.jmx.exposure.include\`.
- Suitable JMX integration is enabled.

The two annotation families serve two different abstractions. Adding \`@ManagedResource\` does not automatically create an Actuator endpoint ID \`cache\`; adding \`@Endpoint\` does not mean you created a Standard MBean under a custom name you chose yourself.

## 18. Common Errors and How to Handle Them

### 18.1. Included, Yet JConsole Does Not Show the Endpoint

Check:
- \`spring-boot-starter-actuator\` dependency.
- \`spring.jmx.enabled\` and JMX auto-configuration.
- Whether the endpoint exists.
- Endpoint enablement/access.
- Whether exclude removes the endpoint.
- Effective profile/property overrides.
- Whether the client is connected to the right JVM/MBeanServer.
- Registration errors or ObjectName collisions.

### 18.2. Visible Over HTTP, Not Over JMX

HTTP and JMX have separate include/exclude lists. An endpoint exposed over HTTP is not automatically exposed over JMX.

### 18.3. Visible in JMX, Yet Remote Client Cannot Connect

JMX exposure does not create a remote connector. Check RMI/JMX service URL, ports, firewall, credentials, host binding, and TLS.

### 18.4. YAML Errors When Using *

An unquoted \`*\` can be interpreted by the YAML parser as alias syntax. Use:

\`\`\`yaml
include: "*"
\`\`\`

### 18.5. Included Everything, Yet an Endpoint Is Still Missing

\`include=*\` only selects endpoints that can be exposed; it does not enable disabled endpoints, supply missing dependencies, or override access restrictions.

### 18.6. Spring Boot Upgrade Causes Unexpected Endpoints to Appear

If using a wildcard include, newly eligible endpoints can appear after an upgrade. Use an explicit allowlist and inventory ObjectNames in integration tests when strict control is required.

### 18.7. Confusing Endpoint Management with All JMX MBeans

A \`@ManagedResource\` exported by Spring JMX is not necessarily governed by \`management.endpoints.jmx.exposure.include\`. This property targets **Actuator endpoints**, not every MBean in the server.

## 19. Testing Configuration with Automated Tests

One testing strategy is to start a Spring Boot test application with property overrides, then inspect JMX MBeans or endpoint exposure state.

Example test configuration:

\`\`\`java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
    "spring.jmx.enabled=true",
    "management.endpoints.jmx.exposure.include=health,info",
    "management.endpoints.jmx.exposure.exclude=env"
})
class JmxExposureTests {

    @Test
    void contextStartsWithJmxExposureConfiguration() {
        // A full integration test can obtain the MBeanServer
        // from ApplicationContext and verify ObjectNames.
    }
}
\`\`\`

This is only a skeleton illustrating how to inject properties, not a complete assertion on exposure. To test effectively, you need to:
1. Obtain the exact MBeanServer used by the app.
2. Identify the Actuator JMX domain/naming convention in the Boot version running the test.
3. Query the actual ObjectNames.
4. Verify expected endpoint MBeans appear.
5. Verify excluded endpoints do not appear.
6. Avoid assuming unrelated infrastructure MBeans belong in the asserted set.

JMX tests may need to clean up MBeans after the Spring context closes to avoid collisions across tests running in the same JVM.

## 20. Safe Configuration Decision Framework

You can use the following questions:

| Question | Decision to Make |
|---|---|
| Which endpoints need monitoring over JMX? | Include only the IDs truly needed |
| Does an endpoint contain sensitive data? | Restrict or do not expose |
| Does an endpoint have state-changing operations? | Check access/authorization |
| Do clients use local attach or a remote connector? | Configure and protect the corresponding transport |
| Which Spring Boot version? | Check defaults and access properties for that exact version |
| Are there HTTP management endpoints? | Configure web exposure independently |
| Are there multiple contexts on the same MBeanServer? | Manage naming and collisions |
| Are dependency upgrades planned? | Review allowlist and ObjectNames after upgrade |

### An Easy-to-Control Sample Configuration

\`\`\`yaml
spring:
  jmx:
    enabled: true

management:
  endpoints:
    jmx:
      exposure:
        include:
          - health
          - info
          - metrics
    web:
      exposure:
        include:
          - health
\`\`\`

This is a **starting point for discussion**, not a security standard applicable to every system. Each endpoint must be chosen based on management needs and the environment's ability to protect JMX connections.

## 21. Practice Exercises

### Exercise A — Expose Only health

1. Add \`spring-boot-starter-actuator\`.
2. Enable appropriate JMX support.
3. Set \`management.endpoints.jmx.exposure.include=health\`.
4. Start the application and connect JConsole to the right JVM.
5. Record the ObjectName created for the health endpoint.
6. Verify that \`info\` and \`metrics\` do not automatically appear as Actuator JMX endpoints because only health was included.

### Exercise B — Include and Exclude

1. Configure include \`*\`.
2. Configure exclude \`env,beans\`.
3. Start the application.
4. Compare the set of endpoint MBeans with a configuration that includes only \`health,info\`.
5. Explain why exclude removes items yet an allowlist remains easier to manage across upgrades.

### Exercise C — Distinguish HTTP and JMX

1. Set web include to \`health\`.
2. Set JMX include to \`health,info,metrics\`.
3. Inspect the Actuator HTTP routes and exported MBeans.
4. Explain why the two sets are not identical.

### Exercise D — Remote Connector

1. Verify Actuator JMX MBeans via local JMX.
2. Configure a remote connector in a secured test environment.
3. Connect from a JMX client in another JVM.
4. Read endpoint MBeans via \`MBeanServerConnection\`.
5. Distinguish connector errors from include/exclude errors.

## 22. Self-Check Questions

**Question 1.** What does \`management.endpoints.jmx.exposure.include\` control?  
**Answer:** The list of Actuator endpoint IDs allowed to be exposed over the JMX technology.

**Question 2.** Does \`include=*\` turn all Spring beans into MBeans?  
**Answer:** No. It selects eligible Actuator endpoints, not all Spring beans.

**Question 3.** How is \`management.endpoints.web.exposure.include\` different?  
**Answer:** It selects Actuator endpoints for HTTP exposure, not JMX.

**Question 4.** Why is it necessary to pay attention to \`spring.jmx.enabled\`?  
**Answer:** Because JMX export integration must be suitably enabled for exposure configuration to take effect.

**Question 5.** Why might an included endpoint still not be visible?  
**Answer:** The endpoint might not exist, might be disabled/access restricted, excluded, JMX support might be off, or the client might be connected to the wrong server.

**Question 6.** Does \`include=*\` automatically open a JMX remote RMI port?  
**Answer:** No. The remote connector and security must be configured separately.

**Question 7.** Why should you inspect MBeanInfo and ObjectName after enabling JMX?  
**Answer:** To confirm the actual management surface, rather than only configuration intent from properties.

## 23. Key Takeaways

- \`management.endpoints.jmx.exposure.include\` is an **allowlist of Actuator endpoint IDs over JMX**.
- \`management.endpoints.jmx.exposure.exclude\` removes endpoint IDs from the JMX exposure set.
- \`management.endpoints.web.exposure.include\` operates independently for HTTP.
- \`spring.jmx.enabled\` relates to enabling Spring Boot's JMX export integration; include does not replace it.
- Exposure does not automatically enable a disabled endpoint, grant permissions, or create a remote JMX connector.
- Wildcard \`*\` is convenient but can unexpectedly widen the management surface; in YAML it must be quoted.
- Actuator JMX endpoints differ from Spring \`@ManagedResource\` beans exported via \`MBeanExporter\`.
- Verify effective configuration, ObjectNames, and MBeanInfo on the right MBeanServer.
- In production operations, combine an include allowlist with remote connector protection and access control.

### References

- Spring Boot Reference — Actuator Endpoints: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Spring Boot Reference — Monitoring and Management over JMX: https://docs.spring.io/spring-boot/reference/actuator/jmx.html
- Spring Boot Reference — Common Application Properties: https://docs.spring.io/spring-boot/appendix/application-properties/index.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Java SE 21 API — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
