# Avoiding Exposing Sensitive Endpoints in Production — Spring Boot and JMX

## 1. Lesson Objectives

Spring Boot makes it easy to deploy monitoring and management features via Spring Framework JMX, Spring Boot Actuator, and protocols such as HTTP or JMX. This convenience carries a significant risk: **an overly exposed endpoint or MBean can leak operational data or configuration, or allow unauthorized parties to alter application state**.

Examples of actions that must be controlled:

- Reading environment variables, system properties, or partial configuration.
- Viewing beans, mappings, thread dumps, and heap dumps.
- Invoking operations that change log levels, clear caches, close connections, or restart workers.
- Accessing Actuator endpoints capable of changing state if the application has corresponding extensions or integrations.
- Querying MBeans auto-exported by Spring or registered by third-party libraries.

This lesson guides you in designing the management surface under the **principle of least privilege**, isolating environments, securing connectors, verifying what is actually exposed, and testing before release.

After this lesson, you will be able to:

1. Distinguish exposure via HTTP Actuator, JMX Actuator, and Spring-managed MBeans.
2. Identify the configuration layers controlling whether an endpoint exists, is exposed, and is accessible.
3. Compile a list of endpoints that should be restricted in production.
4. Apply configurations that limit exposure, enforce network security, and require authentication/authorization.
5. Understand why hiding paths or renaming ObjectNames is not security.
6. Test the actual surface rather than merely trusting configuration files.
7. Establish a safe change workflow when opening additional management endpoints.

## 2. Three Management Surfaces to Distinguish

\`\`\`text
                         Spring Boot application
                                  |
              +-------------------+---------------------+
              |                   |                     |
              v                   v                     v
     Actuator over HTTP   Actuator over JMX     Spring/custom MBeans
              |                   |                     |
      HTTP management       MBeanServer             MBeanExporter
         endpoint                 ^                     |
              |                  |                     v
      Web server/router          +------------- MBeanServer
              |                                        |
       HTTP client                         Local / remote JMX client
\`\`\`

**HTTP and JMX are two distinct access surfaces.** A configuration restricting only HTTP exposure does not necessarily restrict JMX exposure. Alongside Actuator endpoints, the application or libraries can also register MBeans directly.

| Surface | Example | What to Check |
|---|---|---|
| Actuator HTTP | \`/actuator/health\`, \`/actuator/info\` | endpoint enabled, web exposure, HTTP authorization, network |
| Actuator JMX | Actuator endpoint exported as JMX MBean | JMX exposure, MBeanServer, JMX connector, and permissions |
| Spring JMX custom | \`@ManagedResource\`, \`@ManagedOperation\` | exporter/assembler, ObjectName, operations, connector |
| JVM platform MBeans | \`java.lang:type=Memory\`, \`java.lang:type=Threading\` | remote JMX access, principal/role, JVM settings |
| Third-party MBeans | Connection pool, message broker, cache | what libraries register, which sensitive operations exist |

An application might not expose \`/actuator/env\` over HTTP yet still expose a sensitive configuration attribute through a custom MBean. Security reviews must therefore examine the entire **management surface**, not just one set of URLs.

## 3. "Enabled", "Exposed", "Accessible", and "Authorized" Are Not Synonymous

Separate four questions:

1. **Is the endpoint created/enabled?** Do the corresponding bean and management function exist?
2. **Over which technology is the endpoint exposed?** HTTP, JMX, or a custom connector?
3. **Can clients reach that surface?** Network, routing, ports, connectors?
4. **Is the client permitted to view/invoke the function?** Authentication, authorization, roles, policies?

\`\`\`text
Endpoint implemented
       |
       v
Enabled?
       |
       v
Exposed over HTTP/JMX?
       |
       v
Reachable from client?
       |
       v
Authenticated?
       |
       v
Authorized for requested action?
\`\`\`

An endpoint absent from HTTP does not mean its management data is absent from another interface. A reachable endpoint does not mean everyone is permitted to invoke it.

### 3.1. Minimize Exposure First, Then Apply Security

The safe approach is **not exposing unneeded functionality**, rather than exposing everything and hoping filters/security settings are always right. Authentication and authorization are defense-in-depth layers, not an excuse to open all endpoints.

### 3.2. Do Not Treat "Internal Only" as Enough

An endpoint on a private network still faces risks from lateral movement, misconfigured proxies, container networks, VPNs, and compromised accounts. Sensitive management endpoints need multiple layers: network segmentation, identity, authorization, TLS, logging, and operation restrictions.

## 4. Exposure Configuration in Spring Boot Actuator

Spring Boot properties commonly used to control endpoints:

\`\`\`yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
    jmx:
      exposure:
        include: health,info
\`\`\`

Meaning:

- \`management.endpoints.web.exposure.include\`: selects endpoints exposed over web.
- \`management.endpoints.jmx.exposure.include\`: selects endpoints exposed over JMX.
- Exact defaults depend on the Spring Boot version, available endpoints, and enabled state.
- This is **one policy example** limiting the surface; it is not an absolute guarantee that all custom MBeans and JMX connectors are disabled.

If the application has no need for Actuator JMX, you can configure:

\`\`\`yaml
management:
  endpoints:
    jmx:
      exposure:
        exclude: "*"
\`\`\`

Depending on requirements, you can also consider Spring Boot's JMX enable/disable setting to reduce MBean exporters and related infrastructure. Check the Boot version in use and the impact on other monitoring tools to avoid accidentally losing needed telemetry.

### 4.1. Why Not Choose \`include: "*"\` in Production?

\`\`\`yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
\`\`\`

This widens the surface to whatever endpoints are enabled and can cause new endpoints to appear after an upgrade or adding dependencies. If an app uses broad exposure, it should have a clear security review, complete authorization rules, and automated tests on the actual endpoint list.

An **intentional allowlist** is easier to review than a wildcard.

### 4.2. \`exclude\` Does Not Replace Real Verification

Configuration:

\`\`\`yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
        exclude: env,beans
\`\`\`

controls exposure only within the corresponding scope and version; it does not remove other access paths to the same information, such as custom controllers or MBeans. Exclude lists are easily forgotten when new endpoints arrive. In production, you should usually define an explicit allowlist and verify which routes/MBeans are actually registered.

## 5. Endpoints Requiring Strict Evaluation

| Endpoint or Feature Group | Potential Risk | Production Recommendation |
|---|---|---|
| \`health\` | Leaks dependency details, infrastructure state | Expose only appropriate content and authorize details |
| \`info\` | Leaks build/version/host/metadata | Minimize unnecessary data |
| \`env\` | Configuration and environment information | Do not expose broadly; control data and roles |
| \`configprops\` | Bound configuration properties | Restrict access, verify sanitization |
| \`beans\` | Internal application structure | Use only in protected admin contexts |
| \`mappings\` | Route/API topology | Limit disclosure |
| \`threaddump\` | Thread names, stack traces, and internal logic | Authorized operations roles only |
| \`heapdump\` | Heap contains app data, potentially highly sensitive | Do not expose publicly; store and handle securely |
| \`loggers\` | Logging configuration info; may allow changing log levels | Separate read/write authorization |
| \`shutdown\` if enabled | Stops the application | Do not enable casually; restrict strictly |
| Custom endpoints/operations | Business-dependent; may have strong side effects | Classify and protect by impact |

**Version note:** endpoint lists and availability vary by Spring Boot version, dependencies, and configuration. An endpoint not present by default in your project does not mean every other Boot project behaves identically. Do not infer security solely from an endpoint's name.

## 6. Controlling the HTTP Management Surface

### 6.1. Separate the Management Port When Appropriate

Example:

\`\`\`yaml
server:
  port: 8080

management:
  server:
    port: 8081
    address: 127.0.0.1
  endpoints:
    web:
      exposure:
        include: health,info
\`\`\`

This is an example for local environments or deployments with an appropriate sidecar/tunnel. \`127.0.0.1\` binds the management listener to loopback inside the corresponding network namespace; if liveness probes from an orchestrator hit another address, design the network properly instead of copying verbatim.

Separating the port clarifies network policy, yet **does not create authentication or authorization on its own**. When the management port is published by a container/orchestrator or reverse proxy, inspect the actual access paths.

### 6.2. Using Authorization at the HTTP Layer

Illustrative Spring Security example:

\`\`\`java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ManagementSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain actuatorSecurity(HttpSecurity http)
            throws Exception {
        http.securityMatcher(EndpointRequest.toAnyEndpoint())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(EndpointRequest.to(HealthEndpoint.class))
                    .permitAll()
                .anyRequest().hasRole("OPS"))
            .httpBasic(basic -> {});
        return http.build();
    }
}
\`\`\`

This illustrates logical policy: health may be public at an appropriate level while other endpoints require an operations role. In production, configure a real authentication provider, TLS, remaining security filter chains, CSRF when state-changing actions exist, and specific rules for management paths. For other Spring Boot/Spring Security versions, verify the matching APIs.

When an application declares its own \`SecurityFilterChain\`, do not assume Boot still automatically applies a default security policy to all endpoints. Check matcher rules and filter chain ordering.

### 6.3. Health Details Are Also Data

A health response can reveal databases, message brokers, disks, and dependency statuses. You can restrict details by authorization:

\`\`\`yaml
management:
  endpoint:
    health:
      show-details: when_authorized
      roles: OPS
\`\`\`

Supported settings and how roles are checked depend on the version; test with both regular principals and principals holding the OPS role. Liveness/readiness probes may need dedicated paths or limited access without requiring full admin rights.

## 7. Actuator JMX Does Not Mean a Remote JMX Connector

Spring Boot can expose MBeans in the platform MBeanServer when JMX is enabled. However, you **cannot infer** from this that remote JMX is enabled. Remote clients need a JMX management agent or connector server.

\`\`\`text
Spring Boot Actuator JMX endpoint
               |
               v
          MBeanServer
               |
       +-------+---------+
       |                 |
  Local JMX          Remote connector
  access             (if opened)
                        |
                   Auth/TLS/network
\`\`\`

Therefore, a security review must separate:

- Which endpoints/MBeans are registered in the server?
- Is a remote connector active?
- Which server is the connector bound to?
- Who can connect to the endpoint?
- Who can invoke read/write/operations?

Changing only \`management.endpoints.jmx.exposure.*\` does not substitute for securing MBeans that the application or libraries register directly.

## 8. Remote JMX: Securing the Management Agent and RMI

Some JDKs/JVMs allow enabling remote JMX via system properties such as:

\`\`\`text
-Dcom.sun.management.jmxremote.port=9010
-Dcom.sun.management.jmxremote.rmi.port=9011
-Djava.rmi.server.hostname=jmx.internal.example
\`\`\`

This is **not a complete production configuration**. The illustrative ports and host should only be reachable within a controlled management network. When enabling remote JMX, evaluate authentication, TLS, truststores, password/access files, firewalls, and RMI characteristics (registry port, server port, hostname in the stub).

An operational policy should require:

1. Never expose management ports to the public Internet.
2. Allowlist only management sources or connect through an authorized tunnel.
3. Use TLS and authentication appropriate to the JDK/connector.
4. Protect secrets and credential files with filesystem permissions.
5. Authorize operations by role; do not grant every operator permission to invoke destructive operations.
6. Monitor connections, authentication failures, and configuration changes.
7. Close the connector when no longer needed.

Do not use:

\`\`\`text
-Dcom.sun.management.jmxremote.authenticate=false
-Dcom.sun.management.jmxremote.ssl=false
\`\`\`

as a default workaround for "easy connection" in production. If lab documentation demonstrates an unprotected setup, isolate the environment completely and never copy it verbatim to a real system.

## 9. Custom @ManagedResource and @ManagedOperation: an Overlooked Risk Source

An application can export its own beans:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;

@ManagedResource(
    objectName = "com.example:type=Maintenance,name=Primary")
public class MaintenanceControl {

    @ManagedAttribute
    public int getPendingJobs() {
        return 42;
    }

    @ManagedOperation
    public void restartWorker() {
        // Side effect: restart worker.
    }
}
\`\`\`

If the exporter registers this class, a JMX client with matching access can locate and invoke \`restartWorker\`. A custom bean not being an Actuator endpoint **does not make it safer**.

Classify members:

| Member | Meaning | Recommended Policy |
|---|---|---|
| \`getPendingJobs\` | Read-only metric | Can expose in an appropriate domain |
| \`getSystemConfiguration\` | Could disclose secrets | Do not export raw config directly |
| \`setEnabled(boolean)\` | Changes state | Write authorization and auditing |
| \`restartWorker()\` | Major side effect | Special restriction; consider another API |
| \`clearAllData()\` | Destroys data | Avoid exposing over JMX unless strictly governed |

**Do not confuse metadata with authorization:** \`@ManagedOperation\` exposes a method; the annotation does not check whether the operator has sufficient permissions.

### 9.1. Do Not Rely on Obscure Names

Renaming an ObjectName from \`Maintenance\` to \`XzQ42\` is not security. A JMX client with query rights can use \`queryNames("*:*")\` to discover MBeans. Protect connection and execution permissions, and restrict which methods are exported.

## 10. Reducing Sensitive Information in Attributes

A getter can accidentally expose data:

\`\`\`java
@ManagedAttribute
public String getJdbcUrl() {
    return jdbcUrl;
}
\`\`\`

Even when the URL omits the password, it can still reveal topology and infrastructure names. Worse:

\`\`\`java
@ManagedAttribute
public String getApiToken() {
    return apiToken;
}
\`\`\`

must not be exposed over JMX. Designers must choose **safe summaries** rather than returning raw configuration.

Better example:

\`\`\`java
@ManagedAttribute
public boolean isExternalServiceConfigured() {
    return credentialsPresent;
}

@ManagedAttribute
public String getExternalServiceStatus() {
    return lastCheckStatus; // e.g. "UP", "DOWN", "UNKNOWN"
}
\`\`\`

Avoid returning usernames, access tokens, full connection strings, private certificate material, payment information, or stack traces containing personal data. If deep diagnostics are unavoidable, use a temporary access process with auditing and appropriate retention limits.

## 11. Sanitization and Its Limits

Spring Boot Actuator includes sensitive-data handling/sanitization mechanisms for certain endpoints. However:

- Do not assume every custom endpoint is sanitized.
- Do not assume every MBean attribute passes through the same policy as \`/actuator/env\`.
- Values masked in a UI might still appear in another endpoint or in logs.
- Sanitization can vary by version and extension.
- Sensitive data should not be placed into responses in the first place if unnecessary.

Test concretely using a dummy secret (canary) to verify low-privilege clients cannot obtain the raw value via HTTP, JMX, or custom surfaces.

## 12. Separating Local, Test, and Production Configurations

A configuration suitable for local development may be unacceptable in production.

### 12.1. Local Development

\`\`\`yaml
# application-local.yml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
    jmx:
      exposure:
        include: health,info
\`\`\`

Even locally, do not bind external machine interfaces unnecessarily, as laptops can connect to public networks or VPNs.

### 12.2. Production

\`\`\`yaml
# application-prod.yml
management:
  endpoints:
    web:
      exposure:
        include: health,info
    jmx:
      exposure:
        include: health
  endpoint:
    health:
      show-details: when_authorized
\`\`\`

This configuration illustrates an allowlist only. Depending on infrastructure, monitoring might require metrics or a Prometheus endpoint; if so, protect them with proper networking and authentication. No single endpoint list fits every system.

### 12.3. Production Configuration Must Be Verified After Merging

Spring Boot loads configuration from many sources: files, profiles, environment variables, command-line arguments, and external configs. An \`application-prod.yml\` file can be overridden by environment variables or deployment manifests.

For instance, \`MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE=*\` (depending on binding and environment) can widen exposure beyond the YAML file. Therefore, reading the source repository is not enough; verify the **effective configuration** and actual endpoints after deployment.

## 13. Authorizing by Action Instead of One Broad Admin Role

You can tier access:

| Role | Suggested Permissions |
|---|---|
| Health probe | View minimal health status only |
| Monitoring reader | Read metrics and safe attributes |
| Operator | Access diagnostics per approved need |
| Administrator | Invoke state-changing operations under controlled workflows |

Some default JMX connectors offer \`readonly\`/\`readwrite\` permissions, but that is not equivalent to fine-grained authorization per business operation. If per-operation authorization is required, you may need a custom mechanism suited to the connector, MBeanServer, or management service.

Do not expose destructive MBean operations simply because the entire \`OPS\` role can read metrics. Design read permissions and state-changing permissions separately.

## 14. Auditing and Traceability

Sensitive management actions must leave sufficient audit trails:

- Who performed it (principal or service identity)?
- Which operation, on which ObjectName/endpoint?
- Timestamp and correlation/request ID?
- Result: succeeded, failed, or uncertain?
- Was approval or break-glass required?
- What scope of values changed, without logging raw secrets?

With JMX/RMI, do not assume every \`MBeanServer.invoke\` is automatically logged completely. Check audit layers at the connector, authorization middleware, and business operation. A Spring aspect can assist auditing for managed beans if calls go through the right proxy, yet do not rely solely on AOP if the exporter invokes bypassing proxies.

## 15. Verifying the Actual HTTP and JMX Surface

### 15.1. HTTP

In an authorized environment, check which endpoints are actually accessible via the management host/port with different principals:

\`\`\`bash
curl -i https://management.internal.example/actuator/health
curl -i https://management.internal.example/actuator/info
\`\`\`

For \`env\`, \`beans\`, \`configprops\`, and sensitive endpoints, do not send raw responses to public logs. Tests may assert only HTTP status or safe schemas, depending on policy.

### 15.2. JMX

In a test JVM or from an authorized JMX client:

\`\`\`java
MBeanServerConnection connection =
    ManagementFactory.getPlatformMBeanServer();

Set<ObjectName> names =
    connection.queryNames(
        new ObjectName("com.example:*"), null);

for (ObjectName name : names) {
    System.out.println(name.getCanonicalName());
}
\`\`\`

In this example, \`ManagementFactory.getPlatformMBeanServer()\` returns the local server of the current JVM. To inspect another process, use the corresponding JMX connector. Querying only tells you **which MBeans are registered on the target server**; it does not automatically test network exposure or remote principal permissions.

### 15.3. Checking MBeanInfo and Operations

\`\`\`java
MBeanInfo info = connection.getMBeanInfo(name);

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println(operation.getName());
}
\`\`\`

Use this list to review actions with side effects. An operation with a harmless-looking name can still mutate state; you must understand the implementation or business contract.

## 16. Security Testing Before Release

A test suite can cover:

1. **HTTP allowlist:** only approved endpoints are accessible.
2. **Authentication:** unauthenticated requests are rejected when authentication is required.
3. **Authorization:** a read-only principal cannot invoke state-changing endpoints.
4. **Health details:** public responses do not disclose dependency topology.
5. **Sensitive data canary:** dummy secrets do not appear in responses for low-privilege callers.
6. **JMX ObjectNames:** registered MBeans match management documentation.
7. **JMX operations:** destructive operations are not exposed or are properly protected.
8. **Remote network:** management ports are unreachable from unauthorized networks.
9. **Configuration overrides:** production environments do not receive wildcard exposure from environment/deploy settings.
10. **Upgrade regression:** after upgrading Boot/JDK/dependencies, the surface does not unexpectedly expand.

### 16.1. Simple HTTP Test Example

With Spring Boot Test and a web-server test setup:

\`\`\`java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment =
    SpringBootTest.WebEnvironment.RANDOM_PORT)
class ActuatorExposureTest {

    @Autowired
    TestRestTemplate http;

    @Test
    void sensitiveEndpointIsNotPubliclyAccessible() {
        var response = http.getForEntity(
            "/actuator/env", String.class);

        assertThat(response.getStatusCode().value())
            .isIn(401, 403, 404);
    }
}
\`\`\`

This is an **example checking unauthenticated access**, not a blanket conclusion about security. An endpoint might return \`404\` because it is not exposed, or \`401/403\` because of policy. Also test with authenticated principals and against specific authorization goals.

### 16.2. Do Not Test Status Codes Alone

A sensitive endpoint may return \`200\` to an authorized user, yet the response must still be checked to ensure it contains no secrets. Conversely, \`401\` on HTTP does not prove the corresponding JMX endpoint is safe. Tests must cover the actual surfaces.

## 17. Common Configuration Mistakes

| Mistake | Risk | Fix |
|---|---|---|
| \`include: "*"\` in production | New endpoints exposed unintentionally | Use an allowlist |
| Securing only HTTP while leaving remote JMX open | MBean operations exposed over connector | Secure/restrict JMX separately |
| Relying on internal network alone | Lateral movement and credential misuse | Defense in depth |
| MBean getter returning raw config | Secret and topology leakage | Return safe summaries |
| \`@ManagedOperation\` on destructive method | Anyone with JMX access can invoke action | Reduce exposure, authorize/audit |
| Using obscure names only | JMX queries still discover ObjectName | Enforce real access controls |
| Trusting YAML while ignoring env overrides | Production opens endpoints via deploy config | Verify effective config |
| Disabling auth/TLS to debug | Leaves management channel unprotected | Use an isolated lab or secure tunnel |
| Over-broad autodetection exporting many beans | Unintended large surface | Explicitly restrict managed interface |
| Giving admin role to monitoring readers | Write permissions exceed need | Separate read/write/admin |

## 18. Production Deployment Checklist

### Before Deploying

- [ ] List permitted HTTP Actuator endpoints.
- [ ] List JMX Actuator endpoints and custom MBeans.
- [ ] Confirm no unintended wildcard exposure.
- [ ] Verify management port/address and Kubernetes Service/Ingress.
- [ ] Ensure remote JMX is reachable only via authorized management networks.
- [ ] Verify TLS, authentication, authorization, and secrets handling.
- [ ] Review MBean operations with side effects.
- [ ] Verify sensitive data is not returned via attributes/HTTP.
- [ ] Configure auditing and alerts for anomalous management access.
- [ ] Have integration tests for exposure and access control.

### After Deploying

- [ ] Inspect exact effective routes and JMX registrations.
- [ ] Test from an unauthorized network/principal.
- [ ] Confirm authorized monitoring still works.
- [ ] Cross-check logs/audits against compliance requirements.
- [ ] Document any discrepancy from the approved inventory.

**Principle:** good configuration is necessary, yet **verifying actual runtime behavior** is what proves the policy is enforced.

## 19. Practice Exercises

### Exercise A — HTTP Allowlist

Create a Spring Boot Actuator app and configure \`management.endpoints.web.exposure.include=health,info\`. Check \`/actuator/health\`, \`/actuator/info\`, and \`/actuator/env\` with an unauthenticated test client. Explain the difference between an unexposed endpoint and an endpoint requiring authentication.

### Exercise B — JMX Inventory

Enable JMX in a lab, and use JConsole or \`queryNames\` API to list Actuator MBeans and custom MBeans. Classify read-only attributes, setters, and operations with side effects. Propose an appropriate production allowlist.

### Exercise C — Comparing HTTP and JMX Exposure

Block \`env\` on HTTP while keeping a custom MBean returning dummy configuration data. Observe that an authorized JMX client can still read the custom MBean. Draw conclusions about the independence of the two surfaces.

### Exercise D — Sanitization

Place a dummy secret in test configuration. Verify that a normal read principal does not receive the raw value via HTTP, JMX, or logs. Do not use real secrets in exercises.

### Exercise E — Production Config Overrides

Set an allowlist in \`application-prod.yml\`, then use an environment variable in a lab environment to alter exposure. Inspect the actual effective surface and add regression tests or deployment policies to prevent unintended wildcards.

### Exercise F — Role Separation

Design three roles: health probe, monitoring reader, and operator. Specify which endpoints and operations each role can access. Write tests proving the monitoring reader cannot invoke operations with side effects.

## 20. Self-Check Questions

1. What is the difference between "enabled", "exposed", "reachable", and "authorized"?
2. Why must HTTP exposure and JMX exposure be checked separately?
3. Does \`management.endpoints.web.exposure.include=health,info\` restrict all custom MBeans?
4. Does \`@ManagedOperation\` automatically authorize callers?
5. Why do \`heapdump\` and \`env\` need to be restricted?
6. Why should you use an allowlist instead of \`include: "*"\`?
7. Does a separate management port automatically create security?
8. Why is a hard-to-guess ObjectName not access control?
9. What should you check after environment overrides exist?
10. How do you prove an endpoint is not unintentionally public?

## 21. References

- Spring Boot Reference — Actuator Endpoints: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Spring Boot Reference — Monitoring and Management over JMX: https://docs.spring.io/spring-boot/reference/actuator/jmx.html
- Spring Security Reference: https://docs.spring.io/spring-security/reference/
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Oracle JDK — Monitoring and Management: https://docs.oracle.com/en/java/javase/21/management/

**Key takeaway:** production JMX/Actuator must follow the principles of least privilege and minimal exposure. Limit endpoints on both HTTP and JMX, secure remote connectors, never expose secrets through attributes, separate read/write permissions clearly, and verify the actual surface after every configuration change or upgrade.
