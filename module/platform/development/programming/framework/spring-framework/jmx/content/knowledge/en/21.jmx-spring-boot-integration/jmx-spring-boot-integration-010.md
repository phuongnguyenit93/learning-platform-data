# Distinguishing JMX Exposure from HTTP Exposure in Spring Boot

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain Spring Boot Actuator **exposure** as permitting a management endpoint to be accessed over a specific **transport technology**.
- Distinguish **HTTP exposure** (via web endpoints/HTTP requests) from **JMX exposure** (via MBeanServer, ObjectName, and JMX clients).
- Understand that `management.endpoints.web.exposure.*` and `management.endpoints.jmx.exposure.*` operate **independently**.
- Distinguish Actuator endpoints exposed over JMX from **custom MBeans** with `@ManagedResource` or Standard/MXBean interfaces.
- Read and configure `spring.jmx.enabled`, `management.endpoints.jmx.domain`, `management.endpoints.web.base-path`, and related security settings in the context of a specific Spring Boot version.
- Recognize common errors: HTTP endpoint works but JMX MBean is missing, JMX is enabled yet `/actuator/...` returns 404, endpoint is disabled, wrong ObjectName, or misjudged authorization scope.
- Choose exposure settings for local, CI, staging, and production without accidentally publishing sensitive operations.

## 2. What Is Exposure and Why Does an Endpoint Have Multiple Channels?

In Spring Boot Actuator, an **endpoint** describes an operational capability, such as:

- `health`: checks operational health status.
- `info`: application information.
- `metrics`: queries metric data.
- `loggers`: views or changes logging levels per endpoint capability.
- `threaddump`: captures thread information.
- `env`: environment/configuration information filtered by security and sanitization.

An endpoint **can** be exposed over web or JMX if the corresponding extension/technology adapter is present and enabled per the Spring Boot version's conditions.

```text
                       Actuator endpoint "health"
                                  |
                      +-----------+-----------+
                      |                       |
                      v                       v
               HTTP exposure             JMX exposure
                      |                       |
                      v                       v
          GET /actuator/health       JMX MBean/ObjectName
                      |                       |
                      v                       v
               HTTP client              JMX client
               curl/browser             JConsole/JMC
```

These are two **different access paths** to the same type of management functionality. Enabling one path **does not automatically enable the other**.

One point to remember: JMX exposure does not mean the application opens a new HTTP URL; HTTP exposure does not mean an MBean appears in the MBeanServer.

## 3. Three Separate Decisions: Available, Enabled, and Exposed

When an Actuator endpoint is unreachable, separate three conditions:

1. **Is the endpoint available?** Do the Actuator dependency and bean/configuration conditions create the corresponding endpoint?
2. **Is the endpoint enabled?** Do version-specific access/enabled settings permit the endpoint to operate?
3. **Is the endpoint exposed over the desired technology?** Web and JMX have separate include/exclude and conditions.

This can be expressed as:

```text
Endpoint exists
      |
      v
Enabled / access permitted?
      |
      +-- No  --> not available
      |
      v
Technology exposure include?
      |
      +-- HTTP: web.exposure.include/exclude
      |
      +-- JMX: jmx.exposure.include/exclude
      |
      v
Do security + network settings allow client access?
```

In newer Spring Boot versions, **endpoint access** settings (such as restricted access levels) also exist, so `exposure.include` cannot be treated as the sole deciding mechanism. Consult the reference docs for the exact **version** running.

An exposed endpoint does not mean every client is permitted to use it. Authorization, authentication, network exposure, and access policies must still be configured.

## 4. HTTP Exposure: Publishing over the Web

HTTP exposure typically appears under Actuator's base path, for example:

```text
GET http://localhost:8080/actuator/health
GET http://localhost:8080/actuator/info
GET http://localhost:8080/actuator/metrics
```

The base path and port here are illustrative only. Endpoint names, existence, and exposure depend on dependencies/configuration. If a separate management server port is configured, the URL uses the corresponding management port.

An illustrative configuration:

```yaml
management:
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include: health,info,metrics
```

Meaning:

- Selects endpoint IDs to expose via HTTP technology.
- Uses `/actuator` as the base path for web management endpoints.
- Does not require the JMX exporter to run.
- Does not automatically alter the list of endpoints exposed via JMX.

If the application has a context path, custom management base path, or separate management port, the actual URL will differ. Do not hardcode `/actuator` paths in operations if configuration has been customized.

### Checking HTTP Exposure

You can test from an authorized host:

```bash
curl -i http://localhost:8080/actuator/health
```

The result can be 200, 503, 401, 403, 404, or another response depending on health status, security, and routing. Do not rely on a 404 status alone to assert the `health` endpoint does not exist: the port/path may be wrong, it may not be exposed or enabled, or some environments intentionally obscure information.

## 5. JMX Exposure: Publishing via MBeanServer

JMX (Java Management Extensions) provides `MBeanServer`, where MBeans are registered by `ObjectName`.

Actuator can expose endpoints as JMX MBeans for JConsole or JMX clients to access.

An illustrative configuration:

```yaml
management:
  endpoints:
    jmx:
      exposure:
        include: health,info,metrics
```

This configuration applies only to the **JMX technology of Actuator endpoints**; it does not set up an HTTP route.

Flow:

```text
Spring Boot Actuator endpoint
             |
             v
Actuator JMX endpoint infrastructure
             |
             v
MBeanServer
             |
             v
JMX ObjectName
             |
             v
JConsole / JMX client
```

The ObjectName of Actuator JMX endpoints is influenced by domain/naming settings and differs from HTTP URLs. Do not derive an ObjectName from a URL by replacing `/` with `:` or from an arbitrary HTTP endpoint ID.

### Checking JMX Exposure

Use JConsole to connect to the JVM and inspect the MBeans tree in the Actuator domain, or call the JMX API:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import java.util.Set;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

Set<ObjectName> names = server.queryNames(null, null);
for (ObjectName name : names) {
    if (name.getDomain().contains("endpoint")) {
        System.out.println(name.getCanonicalName());
    }
}
```

This is only a preliminary lookup: default or custom domains might not contain the word `endpoint`. When actually debugging, check `management.endpoints.jmx.domain` and query the chosen domain. If the exporter uses an MBeanServer other than the platform server, access that exact server.

## 6. Two Independent Exposure Configuration Namespaces

A Spring Boot configuration may specify:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
    jmx:
      exposure:
        include: health,info,metrics
```

From this configuration:

- `health` and `info` are selected for both technologies if the endpoints are valid and other conditions hold.
- `prometheus` is selected for HTTP, not automatically selected for JMX.
- `metrics` is selected for JMX, not automatically selected for HTTP.
- Dependency, enablement, and access conditions still decide whether an endpoint is actually present.
- `prometheus` is not necessarily present without the corresponding registry/dependency.

This can be summarized briefly:

```text
management.endpoints.web.exposure  !=
management.endpoints.jmx.exposure
```

Selecting an endpoint for HTTP does not automatically mean an equivalent JMX endpoint exists.

## 7. Comparison Table: HTTP Exposure vs. JMX Exposure

| Criterion | HTTP exposure | JMX exposure |
|---|---|---|
| Access channel | HTTP(S) | JMX/MBeanServer |
| Endpoint identifier | URL path | ObjectName + attributes/operations |
| Common clients | curl, browser, reverse proxy, HTTP monitoring | JConsole, JMC, JMX connector client |
| Include/exclude config | `management.endpoints.web.exposure.*` | `management.endpoints.jmx.exposure.*` |
| Base namespace | `management.endpoints.web.base-path` | `management.endpoints.jmx.domain` |
| Network | Web server/management HTTP server | Local MBeanServer or remote JMX connector |
| Authorization | Spring Security / web infrastructure | JMX authentication/authorization and connector controls |
| Common format | HTTP response, usually JSON/text | JMX attributes/operations per metadata |
| Direct browser access | Possible | Not via standard HTTP URLs |
| Port changes | `management.server.port` when a separate management web port is configured | Separate JMX remote config, not synonymous with management HTTP port |
| Best suited for | Web health checks, metrics scraping, HTTP automation | JVM management, JConsole, JMX-centric operations |
| Scope | HTTP clients permitted by network | JVM/JMX clients permitted by connector |

Neither technology is inherently "safer". Both need dedicated exposure and security design. HTTP/HTTPS has a broad ecosystem of proxies, auth, and observability; local JMX can be handy when debugging the JVM. Yet a misconfigured remote JMX connector also poses severe risks.

## 8. "Exposed" Does Not Mean "Public Internet"

In Spring Boot, **exposed** means the endpoint is included on the surface of the corresponding technology; it is not necessarily public.

For example, an HTTP endpoint might:

- Listen only on localhost.
- Listen on an internal management address.
- Be blocked by a reverse proxy or network policy.
- Require authentication/authorization.
- Be opened only in test environments.

A JMX endpoint might:

- Be readable only inside the same JVM via the platform MBeanServer.
- Have a remote connector only on a private network.
- Require JMX authentication/TLS.
- Be restricted by firewall or container policies.

Therefore, separate:

```text
Technology exposure
          !=
Network reachability
          !=
Authenticated identity
          !=
Authorized action
```

An endpoint include configuration should not be considered complete without security and networking policies.

## 9. HTTP Exposure Is Not a Regular Spring MVC Controller

Actuator web endpoints use a separate infrastructure to map endpoint IDs and operations onto HTTP routes. It relates to the active web stack (Spring MVC/WebFlux if present), yet you should not treat every endpoint like a manual `@RestController`.

For example, `health` is usually accessed with GET, though depending on Actuator endpoint operations, read/write/delete operations with different semantics can exist.

Spring Security configuration must cover management endpoints specifically. Some applications have a separate management context or port, so security chains and network policies must be verified in the actual deployment.

At the same time, a **custom MVC controller** at `/admin/status` is not an Actuator endpoint merely because its name sounds administrative. It does not automatically appear in `management.endpoints.jmx.exposure`.

## 10. JMX Exposure Is Not Every Custom MBean

This is an easy mistake when an application uses Spring Framework JMX alongside Spring Boot Actuator.

Custom MBean:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.shop.orders:type=Queue,name=outbox")
public class OrderQueueManagement {

    @ManagedAttribute
    public int getPendingCount() {
        return 12;
    }
}
```

If the bean is registered by the Spring JMX exporter, it appears under the configured ObjectName.

**However**, `management.endpoints.jmx.exposure.include=health,info` configures **Actuator JMX endpoint exposure**. It is not an allowlist applied directly to every custom `@ManagedResource` or JVM platform MBean.

Distinguish three sets:

1. **Actuator endpoints over HTTP.**
2. **Actuator endpoints over JMX.**
3. **Custom/platform MBeans registered directly or via Spring `MBeanExporter`.**

A custom MBean can exist even when HTTP Actuator exposure is off. Conversely, HTTP Actuator `/health` can work while a custom MBean has not been exported.

## 11. JVM Platform MBeans and Actuator JMX Endpoints Are Different

The JVM normally has platform MBeans such as:

```text
java.lang:type=Memory
java.lang:type=Threading
java.lang:type=Runtime
java.lang:type=ClassLoading
```

These are Java platform management MBeans. They are not created by Actuator's `management.endpoints.jmx.exposure.include`.

Configuring Actuator JMX exposure does not mean disabling platform MBeans. When JConsole connects to a JVM, you may see JVM, library, custom application, and Actuator MBeans together.

To avoid confusion:

| MBean Source | Who Creates/Registers It? | How Controlled |
|---|---|---|
| JVM platform | Java runtime/platform | JVM management facilities and JMX access |
| Spring custom `@ManagedResource` | Spring JMX exporter | Annotations/assembler/export configuration |
| Custom Standard/MXBean | App/library registration | Registration owner, ObjectName, MBeanServer |
| Actuator JMX endpoint | Spring Boot Actuator JMX infrastructure | Actuator endpoint enablement + JMX exposure |

Disabling an Actuator endpoint over JMX does not imply JVM `java.lang:type=Memory` disappears.

## 12. Understanding spring.jmx.enabled Correctly

In Spring Boot, `spring.jmx.enabled` usually relates to enabling Spring JMX integration/export. Example:

```yaml
spring:
  jmx:
    enabled: true
```

However, do not interpret it as a switch that "enables all remote JMX for the Internet". It does not automatically configure full remote JMX ports, network policies, authentication, or TLS.

For Actuator, JMX exposure capability also requires:

- The Actuator endpoint bean exists and is permitted to operate.
- JMX endpoint exposure is suitably configured.
- MBeanServer/export infrastructure is initialized.
- The client has a valid JMX access path.

Features and defaults change across Spring Boot versions, so consult the documentation for the version in use instead of mechanically copying configurations across major versions.

## 13. Actuator JMX Domain and HTTP Base Path

Two configurations often confused:

```yaml
management:
  endpoints:
    web:
      base-path: /manage
    jmx:
      domain: com.example.shop.actuator
```

**HTTP:** the `health` endpoint can reside under `/manage/health` given appropriate routing and exposure.

**JMX:** Actuator MBeans get domain `com.example.shop.actuator`, with ObjectNames generated by the corresponding infrastructure/naming convention.

Changing `web.base-path` does not change JMX ObjectNames. Changing `jmx.domain` does not change HTTP URLs.

Setting a custom domain can avoid collisions with other MBeans in the same server, though you must watch out for JMX exporters/dashboard clients still querying the old domain.

## 14. Include and Exclude

Example configuration groups:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
        exclude: env
    jmx:
      exposure:
        include: health,info
        exclude: shutdown
```

When an endpoint is in both include and exclude, exclude is generally used to remove the endpoint from the exposure surface per Spring Boot's logic; always verify your exact version.

You can use `include: "*"` to select many endpoints, yet doing so carries risk if applied in uncontrolled production environments. In YAML, `*` must be placed in a quoted string to avoid YAML alias syntax:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
```

Even when expose-all is configured, it does not automatically enable disabled endpoints or satisfy every security/access condition. Do not use include-all if the goal is only health/metrics.

## 15. Endpoint Enablement and Access by Version

Some Spring Boot versions use properties like `management.endpoint.<id>.enabled` and global enablement defaults, while newer versions have an **access** mechanism to specify endpoint-level permissions.

Concept:

```text
Endpoint bean
   |
   +-- has required dependencies/conditions?
   |
   +-- enabled / access permitted?
   |
   +-- technology exposure include?
   |
   +-- security/network allow actual client access?
```

If an endpoint is not enabled, adding it to `web.exposure.include` may not make it appear.

If an endpoint allows only read-only access, write operations may be restricted even though the endpoint is exposed over a given technology. Exact behavior depends on version and endpoint support.

Therefore, when troubleshooting, always identify the Spring Boot **version**, effective properties, existing endpoint list, and client error.

## 16. A Reference Production Configuration Example

An application primarily needing Kubernetes HTTP readiness/health and Prometheus scraping, while using JMX for internal JVM debugging:

```yaml
spring:
  jmx:
    enabled: true

management:
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include: health,info,prometheus
    jmx:
      exposure:
        include: health,info,metrics
  endpoint:
    health:
      show-details: when_authorized
```

**This is not a complete security template.** You still need:

- Appropriate Actuator and metrics registry dependencies.
- Verification of the Boot version's endpoint defaults.
- Spring Security rules for HTTP Actuator.
- Network policies/firewalls/management port.
- Remote JMX connector security if remote JMX exists.
- Access policies for endpoints with write operations.
- Verification of whether `info` contains sensitive data.
- Verification of who is permitted to receive health details.

A "safe" configuration depends on your threat model and deployment, not just two include lists.

## 17. Distinguishing management.server.port and Remote JMX Port

If you set:

```yaml
management:
  server:
    port: 9090
```

this configuration typically controls the **management HTTP server port** (when a separate web management server is active). It does not make a remote JMX connector listen on port 9090.

Remote JMX has its own configuration mechanism at the JVM/connector level. For example, JVM flags like `com.sun.management.jmxremote.port` are illustrative only and require careful review of how remote JMX is secured.

Avoid inferring:

```text
management.server.port = 9090
=> JMX remote port = 9090  (FALSE)
```

In containers, exposing the management HTTP port in a Kubernetes Service also does not mean JConsole can connect to MBeanServer over that same port.

## 18. Suitable Use Cases for Each Technology

### HTTP Exposure Fits When

- A load balancer or orchestrator needs a health endpoint.
- A Prometheus-compatible scraper pulls metrics over HTTP.
- DevOps tooling, API gateways, or automation use HTTP clients.
- You want security routing via the web stack.
- You use HTTP-endpoint-based monitoring/alerting.

### JMX Exposure Fits When

- Engineers need JConsole or JMC to inspect the JVM/MBeans.
- Java management tools rely on ObjectNames.
- You want to read MBean attributes/operations in the same JVM.
- You use a JMX collector to gather info from the JVM and application.
- You need to operate management functions designed specifically for JMX.

### Both Can Be Used

An application can use HTTP for health checks and monitoring, and JMX for JVM diagnostics. However, manage scope, access, and alerting separately; having both does not inherently increase security.

## 19. Case: HTTP Works Yet JMX Does Not Show the Endpoint

Example:

```text
GET /actuator/health -> 200
JConsole -> Actuator health MBean not visible
```

Hypotheses:

1. JMX exposure does not include `health`.
2. JMX export is disabled or unconfigured for the Boot version.
3. JConsole is connected to the wrong JVM or wrong MBeanServer/connector.
4. The Actuator JMX domain was changed, so you are looking under the wrong branch.
5. Endpoint MBean registration failed due to an ObjectName conflict.
6. Profile/property differences exist between environments.
7. The Actuator endpoint is not exposed over JMX due to technology support conditions.

Checks:

- Confirm active Spring profiles.
- Check `management.endpoints.jmx.exposure.*`.
- Check `spring.jmx.enabled` and corresponding config.
- Read startup logs for JMX registration.
- Query ObjectNames on the right server/domain.
- Read `MBeanInfo` if the ObjectName exists.

Do not alter HTTP security rules to fix an issue belonging to JMX registration without evidence linking them.

## 20. Case: JMX Shows the MBean Yet HTTP Returns 404

Example:

```text
JConsole -> Actuator metrics MBean exists
GET /actuator/metrics -> 404
```

Hypotheses:

1. `metrics` is not in web exposure include.
2. HTTP base path changed.
3. Management port/address differs.
4. No web endpoint infrastructure is in the deployment.
5. The endpoint is disabled or restricted by access policy.
6. Requests pass through a reverse proxy/router not forwarding properly.
7. Wrong URL due to context path or management context.

The fix is not "disable JMX" or "re-register the MBean". Check web endpoint conditions separately.

## 21. Distinguishing Authorization Errors from Exposure Errors

You may encounter:

| Outcome | Common Meaning | Check |
|---|---|---|
| HTTP 200 | Web endpoint responded successfully | Says nothing by itself about JMX |
| HTTP 401 | Authentication needed or invalid credentials | HTTP security |
| HTTP 403 | Authenticated yet unauthorized or denied by policy | HTTP authorization |
| HTTP 404 | No matching route or hidden | Web exposure, path, endpoint availability |
| JMX `InstanceNotFoundException` | ObjectName has no MBean | JMX registration/domain |
| JMX access denied | Client lacks permissions per JMX connector/security policy | JMX authentication/authorization |
| JMX operation not found | MBeanInfo/signature mismatch | JMX metadata/operation mapping |

Some security setups intentionally return 404 for unauthorized resources, so HTTP status alone is not definitive proof of cause. The key is **placing the error in the right technology** before changing configuration.

## 22. Testing HTTP Exposure

With Spring Boot tests, you can use an HTTP client/test framework to verify routes and status codes in the appropriate context.

curl example:

```bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/metrics
```

A test should verify:

- Permitted endpoints are accessible by an appropriate principal.
- Disallowed endpoints do not leak data.
- Web path and management port configuration are accurate.
- Health details do not leak secrets.

Do not assert only status 200 when the application uses authentication; use appropriate credentials/test principals.

## 23. Testing JMX Exposure

A JMX integration test can:

1. Start the Spring context with the Actuator/JMX config to test.
2. Obtain the MBeanServer used by Actuator JMX infrastructure.
3. Query ObjectNames for the expected domain.
4. Assert included Actuator MBeans appear.
5. Assert excluded endpoints do not appear.
6. Read MBeanInfo to verify attributes/operations.
7. Close the context and verify cleanup of context-owned registrations.

Example checking MBeanServer:

```java
import javax.management.MBeanServer;
import javax.management.ObjectName;
import java.util.Set;

public final class JmxEndpointInspection {
    public static void list(MBeanServer server, String domain)
            throws Exception {
        Set<ObjectName> names = server.queryNames(
                new ObjectName(domain + ":*"),
                null);

        names.stream()
                .map(ObjectName::getCanonicalName)
                .sorted()
                .forEach(System.out::println);
    }
}
```

The `domain` argument in the example should be a valid domain configured for Actuator, not taken directly from untrusted input. Executing in tests with a separate server helps avoid registration state from other applications/tests.

## 24. Testing Both Technologies Independently Together

In an integration test suite:

- **Test web exposure** with an HTTP test client and security configuration.
- **Test JMX exposure** with MBeanServer/ObjectName.
- **Test custom MBeans** with a separate exporter and MBeanInfo.
- **Test endpoint availability** via Spring context/configuration.

Do not use `GET /actuator/health = 200` to assert `health` is exposed over JMX. Nor should you use `isRegistered(ObjectName)` to assert an HTTP URL exists.

These are separate access contracts requiring separate assertions.

## 25. Exposure Policy by Environment

| Environment | HTTP exposure | JMX exposure | Security Notes |
|---|---|---|---|
| **Local** | Health/info/metrics for debugging | Can enable broadly for experiments | Do not open unprotected remote JMX |
| **CI** | Test allowed/disallowed endpoints | Test ObjectNames and metadata | Isolate servers, avoid test collisions |
| **Staging** | Mirror production | Mirror production if needed | Verify security, routing, monitoring |
| **Production** | Minimal operational allowlist | Only needed endpoints; restrict JMX access | Defense in depth, audit, and expose no secrets |

This table is a design guide, not Spring Boot defaults. A production project needing only HTTP metrics can disable Actuator JMX exposure if unused; a JMX-centric project can keep HTTP exposure minimal.

Do not enable all endpoints just to "avoid dashboard errors", because changing exposure can introduce new attack surfaces.

## 26. An Operational Example: Health over HTTP, Diagnostics over JMX

A shop service has:

```text
Business service: orders-service
HTTP health:      /actuator/health
HTTP metrics:     /actuator/prometheus
JMX diagnostics:  java.lang:type=Threading
                  java.lang:type=Memory
Custom JMX:       com.example.shop.orders:type=Queue,name=outbox
```

Design:

- The orchestrator calls HTTP health to know whether the instance is serving.
- A metrics scraper pulls time-series data through the HTTP endpoint.
- JConsole/approved JMX clients inspect JVM threads/memory during investigations.
- The custom queue MBean publishes `PendingCount` and may offer operations only to authorized operators.

Each access path serves a distinct goal. HTTP health does not need to go through JMX to fetch thread counts, and JMX does not necessarily have to be exposed remotely just because the app has Actuator.

## 27. Common Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| HTTP `/actuator/health` works yet JMX health is missing | JMX exposure/config differs from web | Check `jmx.exposure`, JMX enablement, and domain |
| JMX metrics exist yet HTTP metrics returns 404 | `metrics` not in web include / wrong path | Check web exposure/base-path/port |
| `/actuator/prometheus` returns 404 | Missing registry/dependency or not exposed | Check Prometheus registry and config |
| Spring `@ManagedResource` has no HTTP URL | Custom MBean is not an Actuator web endpoint | Use JMX client or deliberately create a web endpoint |
| Actuator JMX disabled yet `java.lang` MBeans remain | JVM platform MBeans are independent | Distinguish MBean sources |
| Remote JMX fails to connect despite `spring.jmx.enabled=true` | Remote connector/network unconfigured | Distinguish export from remote JMX |
| Changed `management.server.port` yet JConsole still fails | This port is for management HTTP | Check JMX connector separately |
| HTTP 403 | Security policy | Read HTTP security configuration |
| ObjectName conflict | Actuator/custom exporter name collision | Separate domain/owner; do not blindly replace |
| Opened `include:"*"` in production | Unintended exposure expansion | Use a minimal allowlist |

## 28. Practice Exercises

### Exercise 1 — Distinguish Configurations

Read the YAML:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
    jmx:
      exposure:
        include: health,metrics
```

Answer:

1. Which endpoint IDs are selected for HTTP?
2. Which endpoint IDs are selected for JMX?
3. Is `metrics` guaranteed to have an HTTP URL?
4. Is `info` guaranteed to have a JMX MBean?

**Guided answers:** (1) health/info; (2) health/metrics; (3) no, not included for web; (4) no, not included for JMX. Actual presence also depends on enablement/access/dependencies.

### Exercise 2 — Changing Base Path

Add:

```yaml
management:
  endpoints:
    web:
      base-path: /ops
```

Determine the new HTTP health path assuming unchanged port/context path, and explain why JMX ObjectNames do not change due to the web base path setting.

### Exercise 3 — Checking Security

A team wants `/actuator/health` public while keeping `/actuator/metrics` for internal monitoring only. Propose HTTP authorization and network policies per deployment. Also explain why this policy **does not automatically protect** a remote JMX connector.

### Exercise 4 — Custom MBean Without an HTTP Route

You export a `@ManagedResource` with ObjectName `com.example.shop:type=Queue,name=outbox`. JConsole can read `PendingCount`, yet GET `/actuator/queue` returns 404.

Explain why this is not necessarily a bug. A custom MBean does not automatically become an Actuator endpoint. If an HTTP API is wanted, build an appropriate endpoint/controller and apply separate security.

### Exercise 5 — Independent Tests

Write two tests:

- HTTP: the `health` endpoint is accessible by an authorized role.
- JMX: the Actuator domain contains a `health` MBean with expected metadata.

Explain why a JMX test cannot replace an HTTP test, or vice versa.

### Exercise 6 — Multi-Port Deployment

A service has `server.port=8080`, `management.server.port=9090`, and a separately configured remote JMX connector. Draw a diagram of the three access paths, highlighting that business HTTP, management HTTP, and remote JMX are independent channels.

## 29. Self-Check Questions

**1. Does enabling HTTP exposure for `metrics` automatically make the JMX `metrics` MBean appear?**

No. You must configure JMX exposure and satisfy other corresponding endpoint/JMX conditions.

**2. Does `management.endpoints.jmx.exposure.include` govern custom `@ManagedResource` beans?**

Not directly. It governs exposure of Actuator endpoints over JMX, not an allowlist for all custom MBeans.

**3. Does changing `management.endpoints.web.base-path` change the JMX domain?**

No. They are separate namespaces/configurations.

**4. Can standard JVM JMX MBeans exist when Actuator HTTP exposure is off?**

Yes. JVM platform MBeans are independent of Actuator HTTP technology.

**5. Does `spring.jmx.enabled=true` automatically open remote JMX over the Internet?**

No. Remote JMX connector/network/security require separate configuration.

**6. Do HTTP 401 and JMX `InstanceNotFoundException` share the same cause?**

No. HTTP 401 is typically authentication; JMX instance not found means the ObjectName is not registered on the queried server.

**7. Why should web and JMX exposure be tested separately?**

Because each technology has independent routing, identity, configuration, security, and client paths.

## 30. Key Takeaways

- Spring Boot Actuator can expose endpoints over **HTTP** and **JMX** as two separate technologies.
- `management.endpoints.web.exposure.*` and `management.endpoints.jmx.exposure.*` select endpoint IDs independently.
- HTTP uses URL/base path/management web server; JMX uses MBeanServer/ObjectName/JMX client.
- `spring.jmx.enabled` does not automatically open a remote JMX connector, and `management.server.port` is not a remote JMX port.
- Actuator JMX MBeans differ from custom `@ManagedResource` and JVM platform MBeans.
- An endpoint must exist and be enabled/permitted before exposure takes effect; authorization/network access remains a separate layer.
- Set HTTP/JMX exposure per operational need and safety level, avoiding uncontrolled `include: "*"` in production.
- Test HTTP routes and JMX ObjectNames with the tools appropriate for each technology.
- When errors occur, first determine whether the issue lies in **endpoint availability**, **technology exposure**, **routing/registration**, or **security**.

## 31. References

- Spring Boot Reference — Actuator Endpoints: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Spring Boot Reference — JMX: https://docs.spring.io/spring-boot/reference/actuator/jmx.html
- Spring Boot Reference — Monitoring and Management over HTTP: https://docs.spring.io/spring-boot/reference/actuator/monitoring.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Java SE 21 — `MBeanServer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
