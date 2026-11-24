# Endpoints Existing, Enabled, Exposed, and Authorized

In Spring Boot Actuator, seeing an endpoint in documentation does not mean its URL can always be called. For example, `/actuator/metrics` may return `404 Not Found` even when the application is running normally; another endpoint might return `401 Unauthorized`, `403 Forbidden`, or `503 Service Unavailable`. These outcomes reflect **different layers of conditions** and should not all be blamed on a single configuration mistake.

To diagnose accurately, separate four questions:

1. **Does the endpoint exist in the application?** Are its implementation, dependencies, beans, and required conditions present?
2. **Is the endpoint enabled and permitted to run the operation?** Does Spring Boot allow that endpoint under enable/access configuration?
3. **Is the endpoint exposed over the channel being used?** HTTP and JMX have separate exposure lists.
4. **Is the caller authorized to access it?** Do Spring Security, authorization policies, networks, and deployment infrastructure let the request reach the endpoint?

These four questions form a logical diagnostic model, not four independent flags guaranteed to exist identically in every Spring Boot version. Some enable/access settings also directly affect whether the endpoint bean is created in the `ApplicationContext` at all.

## 1. What Is an Actuator Endpoint?

Spring Boot Actuator provides observability and management access points to inspect the state of a running application. Common endpoints include:

| Endpoint ID | Purpose |
|---|---|
| `health` | Application health status and health contributors |
| `info` | Configured application information to publish |
| `metrics` | Metric names and values recorded by Micrometer |
| `loggers` | Inspect and, if permitted, change log levels |
| `env` | Information about property sources in the `Environment` |
| `configprops` | Configuration beans bound via `@ConfigurationProperties` |
| `beans` | Information about beans in the `ApplicationContext` |
| `threaddump` | Thread information at the time of sampling |
| `prometheus` | Metrics in Prometheus format when the corresponding registry is present |
| `shutdown` | Request application shutdown when permitted |

Each endpoint has an **ID**. For example, `health` is the ID while `/actuator/health` is the typical default HTTP path, not the endpoint identifier itself.

An endpoint can provide different operations:

- `@ReadOperation`: read observability data.
- `@WriteOperation`: perform a state change.
- `@DeleteOperation`: delete or clear data according to the endpoint's function.

The HTTP mapping of an operation, the endpoint's permitted capabilities, and the caller's permissions are separate concepts that must be evaluated independently.

## 2. First Condition: The Endpoint Must Exist in the Application

To use common Actuator endpoints, a project typically needs the dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

With Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

The starter provides Actuator, Micrometer, and related auto-configuration components. However, that does not mean **every** endpoint listed in documentation will appear.

Some endpoints additionally depend on:

- Libraries present on the classpath.
- A specialized bean or feature having been configured.
- Auto-configuration conditions of the Spring Boot version.
- Corresponding extensions or integrations.
- Access/enable settings allowing the endpoint to be registered.

For example, to use the `prometheus` endpoint, the application normally needs the Prometheus registry:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Merely declaring HTTP exposure for `prometheus` without the suitable registry may result in the endpoint not being created. **Exposure cannot conjure up an endpoint that does not exist.**

### Custom Endpoints

An application can also define its own endpoints:

~~~java
import java.util.Map;

import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "buildstatus")
public class BuildStatusEndpoint {

    @ReadOperation
    public Map<String, String> status() {
        return Map.of("state", "available");
    }
}
~~~

The example uses ID `buildstatus` for a custom endpoint; the default web path (if the endpoint is enabled and exposed) is `/actuator/buildstatus`. Do not confuse `@Endpoint` with `@RestController`: both can lead to HTTP paths, yet use different discovery, enablement, and exposure mechanisms.

A Java class existing in source code does not automatically mean Spring created a bean for it. If the component is not scanned, not imported, or excluded by bean conditions, the endpoint is not yet present in the context.

## 3. Second Condition: The Endpoint Must Be Enabled or Granted Operation Access

Spring Boot has two groups of mechanisms to distinguish by version:

- **Traditional enabled/disabled mechanism:** uses `management.endpoint.<id>.enabled` and `management.endpoints.enabled-by-default`.
- **Modern Spring Boot endpoint access model:** uses `management.endpoint.<id>.access` and `management.endpoints.access.default`, with values such as `none`, `read-only`, and `unrestricted`.

The `access` model was introduced in modern Spring Boot lines (for example Spring Boot 3.4 and later). Projects on older versions must check the exact properties supported by that version; do not copy new access config into an old Boot project expecting it to work.

### 3.1. The `enabled` Mechanism in Versions Using These Properties

Illustrative example:

~~~yaml
management:
  endpoints:
    enabled-by-default: false
  endpoint:
    health:
      enabled: true
    info:
      enabled: true
~~~

Meaning of this model:

1. Endpoints are no longer enabled by default.
2. `health` and `info` are explicitly re-enabled.
3. Nothing in this example guarantees the endpoints are exposed over HTTP.
4. Nothing in this example configures authentication or authorization.

In versions with this enablement mechanism, a disabled endpoint is usually not created as a usable endpoint, so callers cannot invoke it merely by adding it to the exposure list.

### 3.2. The `access` Model in Supported Versions

Example:

~~~yaml
management:
  endpoints:
    access:
      default: none
  endpoint:
    health:
      access: read-only
    info:
      access: read-only
    metrics:
      access: read-only
~~~

The access values mean:

| Value | Meaning |
|---|---|
| `none` | No access permitted to the endpoint; in the modern access model, the endpoint may be excluded from the `ApplicationContext` |
| `read-only` | Only read operations are permitted |
| `unrestricted` | Operations are unrestricted at this access layer |

Key point: `unrestricted` **does not mean every Internet user is permitted access**. This is Actuator's endpoint access level, not Spring Security's authentication/authorization decision.

Conversely, `read-only` does not mean public HTTP GET; a caller can still receive `401` or `403` if the `SecurityFilterChain` requires authentication or an appropriate role.

Some versions support configuring a maximum permitted access level:

~~~yaml
management:
  endpoints:
    access:
      max-permitted: read-only
~~~

Depending on the version, this cap prevents endpoints from opening write operations even if an individual endpoint's config allows a higher level. It is helpful for systems needing observation only, though you must check desired management operations before enabling it.

### `enabled` and `access` Are Not Per-User Authorization

The two property groups above control endpoint availability and operation capability at the application level. They do not distinguish users `alice` and `bob` by role. Authorization by identity, token, principal, or role requires a security mechanism such as Spring Security or a gateway.

Do not equate:

~~~text
management.endpoint.loggers.access=read-only
~~~

with:

~~~text
Allow only users with role OPERATIONS to view the loggers endpoint.
~~~

The first specifies which operation types are allowed. The second is an authorization rule.

## 4. Third Condition: The Endpoint Must Be Exposed over the Right Channel

An endpoint can be present and enabled yet **not published over HTTP**. Actuator allows configuring exposure per technology, commonly HTTP and JMX.

Example to expose three endpoints over HTTP:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
~~~

By default, Spring Boot typically exposes only a small set of endpoints, with `health` being the primary default HTTP endpoint. Do not assume `env`, `beans`, `loggers`, or `metrics` already have reachable URLs just because the Actuator dependency is present.

The exposure list defines **which endpoints can be reached over a transport**. It does not grant permissions to specific callers.

### Include and Exclude

Example:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,loggers
        exclude: loggers
~~~

Under these exposure rules, `loggers` is excluded from HTTP exposure despite being listed in `include`. The `exclude` property takes precedence when both lists mention the same endpoint.

If you want to expose all HTTP endpoints, you can use:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
~~~

In YAML, wrap `"*"` in quotes because `*` has special syntax meaning in YAML. However, **do not use `include: "*"` unconditionally in production**: several endpoints reveal configuration, topology, thread dumps, or allow management operations.

A minimal exposure list matching actual needs combined with a clear security layer is usually the better choice.

### HTTP and JMX Have Separate Lists

Example:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
    jmx:
      exposure:
        include: health,info,metrics
~~~

In this configuration, `metrics` can be exposed over JMX while having no corresponding HTTP endpoint. Do not rely on JMX accessibility to conclude `GET /actuator/metrics` definitely works.

JMX has its own access, connection, and security mechanisms. If using remote JMX, secure the connection channel and configure proper authentication/authorization; HTTP `SecurityFilterChain` does not directly govern JMX sessions.

## 5. Endpoint URLs Can Differ from `/actuator/{id}`

The typical HTTP path of a web endpoint is:

~~~text
/actuator/{endpoint-id}
~~~

Examples:

~~~text
GET /actuator/health
GET /actuator/info
GET /actuator/metrics
~~~

However, the web base path can be changed:

~~~yaml
management:
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,info
~~~

Then the corresponding paths are typically:

~~~text
GET /manage/health
GET /manage/info
~~~

You can also remap individual endpoints:

~~~yaml
management:
  endpoints:
    web:
      base-path: /manage
      path-mapping:
        health: status
~~~

Then the health endpoint is mapped to:

~~~text
GET /manage/status
~~~

A caller requesting `/actuator/health` will not find the path even though the endpoint is present and exposed under the new URL.

### Management Port and Context Path

Spring Boot can serve Actuator on a separate port:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 9090
  endpoints:
    web:
      exposure:
        include: health,info
~~~

In this example, the application's web API runs on port `8080`, while Actuator endpoints can be served at:

~~~text
http://localhost:9090/actuator/health
~~~

Do not call port `8080` and conclude the endpoint is not exposed. When changing `server.servlet.context-path`, `management.server.base-path`, or reverse-proxy routing, the final path also depends on how the management context and proxy are arranged.

Practical rule: always write out **host + port + context path + Actuator base path + endpoint mapping** before diagnosing a `404`.

## 6. Fourth Condition: The Caller Must Be Authorized to Access It

Even when an endpoint is present, enabled, and exposed over HTTP, a request can still be rejected for security reasons.

Here you need to distinguish:

- **Authentication:** who is the caller? Do they have valid credentials, a session, or a token?
- **Authorization:** is that caller allowed to view or execute this operation?
- **Network reachability:** can the caller reach the port and route through firewalls, ingress, service mesh, or gateways?
- **Endpoint-level access:** if supported by the version, Actuator can restrict operations by `none`, `read-only`, or `unrestricted`.

When Spring Security is on the classpath and no custom `SecurityFilterChain` exists, Spring Boot can auto-configure Actuator protection using its defaults. Once an application defines its own `SecurityFilterChain`, understand the scope of each chain: Boot normally yields web security configuration to the application.

**Exposure does not replace security.** Without an appropriate security layer or network restriction, an exposed endpoint can become a public endpoint.

## 7. Example: Protecting Endpoints with Spring Security

Suppose an application needs to expose the health probe publicly for the orchestrator, while only operators with role `OPS` may read the remaining Actuator endpoints.

Exposure configuration:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,loggers
  endpoint:
    health:
      show-details: when-authorized
~~~

Illustrative Spring Security configuration for a servlet application with one `SecurityFilterChain`:

~~~java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(EndpointRequest.to("health"))
                    .permitAll()
                .requestMatchers(EndpointRequest.toAnyEndpoint())
                    .hasRole("OPS")
                .anyRequest()
                    .authenticated()
        );

        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

This is an example of authorization principles. A real application still needs an authentication source, provisioning of the `OPS` role, business API protection, and an appropriate CSRF policy.

Expected logical results:

| Request | Condition | Typical Result |
|---|---|---|
| GET `/actuator/health` | Endpoint exposed and permitted via `permitAll` | Allowed without login |
| GET `/actuator/metrics` | Unauthenticated | `401` or authentication challenge |
| GET `/actuator/metrics` | Authenticated but missing `ROLE_OPS` | `403` |
| GET `/actuator/metrics` | Has `ROLE_OPS` | Routed to the endpoint |
| GET `/actuator/env` | Not in exposure list | Usually no HTTP mapping, regardless of role |

Spring Security can generally integrate with `EndpointRequest` to match endpoints by ID instead of hardcoding URLs. This keeps endpoint rules independent of base path changes.

### When Using Multiple `SecurityFilterChain` Beans

If you declare a chain that applies only to Actuator:

~~~java
http.securityMatcher(EndpointRequest.toAnyEndpoint());
~~~

that chain **does not** cover business URLs. Another chain is required for application APIs if the app relies on Spring Security to protect them. Do not create a chain solely for Actuator and inadvertently leave business endpoints unprotected.

In WebFlux, security uses `SecurityWebFilterChain` instead of the Servlet API's `SecurityFilterChain`. The example above is for a Spring MVC/Servlet application.

### HTTP Write Operations and CSRF

Some endpoints have write operations, such as changing log levels. Even an authenticated and authorized user can receive `403` when sending a POST if a CSRF token is required and omitted from the request.

Do not disable CSRF for the entire application just to make one management endpoint work. Design authentication, CSRF, and operation permissions according to your real security model.

## 8. Example: Checking the Four Conditions for `metrics`

Suppose you need to access:

~~~text
GET http://localhost:8080/actuator/metrics
~~~

A useful checklist is:

**Step 1 — Does the endpoint exist?** Does the application have the Actuator dependency and relevant metric infrastructure? Could an auto-configuration condition prevent the endpoint from being registered?

**Step 2 — Is the endpoint enabled/granted access?** For the version in use, does `management.endpoint.metrics.enabled` or `management.endpoint.metrics.access` permit the endpoint? Is there a default deny or `max-permitted` limit?

**Step 3 — Exposed over HTTP?** Does `management.endpoints.web.exposure.include` contain `metrics`? Is an `exclude` overriding it? Are the path, port, and base path right?

**Step 4 — Is the caller authorized?** Does the `SecurityFilterChain` allow the current user/token to access the endpoint? Does ingress permit connections to the management port?

Example simple configuration for a Spring Boot version supporting the `access` model:

~~~yaml
management:
  endpoints:
    access:
      default: none
    web:
      exposure:
        include: health,metrics
  endpoint:
    health:
      access: read-only
    metrics:
      access: read-only
~~~

This configuration permits `health` and `metrics` for read usage and exposes them over HTTP; it **does not** configure authentication or role-based authorization by itself.

If the project uses an older Spring Boot version with the `enabled` mechanism, replace the `access` section with the corresponding properties supported by that version.

## 9. What Do 404, 401, 403, 405, and 503 Mean?

An HTTP code does not always pinpoint a single cause, but it narrows down what to inspect.

| HTTP status | Common Meaning | What to Check |
|---|---|---|
| `404 Not Found` | No mapping for the requested URL or a component intentionally hides the resource | Dependency, enable/access, exposure, port, base path, proxy route |
| `401 Unauthorized` | Unauthenticated or invalid credentials | Authentication, token, Basic auth, session, security chain |
| `403 Forbidden` | Caller lacks permission or request rejected by protections like CSRF | Authorization rules, roles, CSRF, endpoint operation |
| `405 Method Not Allowed` | URL may exist but HTTP method is unsupported | GET/POST/DELETE, endpoint operation type |
| `503 Service Unavailable` | Can be caused by health endpoint reporting `DOWN`/`OUT_OF_SERVICE`, or proxy/upstream error | Response body, health contributors, proxy logs |
| `200 OK` | Request processed successfully | Does not prove sensitive data should be exposed publicly |

Especially with `health`, an HTTP `503` response can mean **the endpoint exists, is exposed, and was allowed to be called**, yet the health report itself indicates the application is unhealthy or unready.

Example:

~~~text
HTTP/1.1 503 Service Unavailable
Content-Type: application/vnd.spring-boot.actuator.v3+json

{"status":"DOWN"}
~~~

This differs from a `503` caused by a reverse proxy being unable to connect to the management server. Distinguish them using the body, headers, logs, and where the response originated.

If you receive `404`, do not immediately enable `include: "*"`. Confirm whether the endpoint is registered and you are calling the right URL before broadening exposure.

## 10. Using `curl` to Verify From Outside the Application

You can call endpoints with `curl`:

~~~bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/info
curl -i http://localhost:8080/actuator/metrics
~~~

Depending on configuration, an endpoint may respond with `200`, `401`, `403`, `404`, or `503`. Inspect both the HTTP status and the response body rather than just checking whether the command returned output.

If using HTTP Basic for operators, let `curl` prompt for the password:

~~~bash
curl -i -u ops http://localhost:8080/actuator/metrics
~~~

Avoid putting secrets directly in commands because terminal history, process listings, and operational tool logs can retain them.

When the management server is on a separate port, test the exact URL:

~~~bash
curl -i http://localhost:9090/actuator/health
~~~

If requests from the same machine succeed while requests from another machine fail, the issue likely lies in the bind address, firewall, ingress, or network policy rather than endpoint availability in Spring.

## 11. The Discovery Page Is Not a Complete List of Every Endpoint

When HTTP exposure and the discovery page are enabled by configuration, the base path (typically `/actuator`) can return a list of links to exposed web endpoints.

Example:

~~~text
GET /actuator
~~~

However, there are several limitations:

- The list only reflects endpoints discovered for that transport, not every endpoint in source code.
- Endpoints not exposed over HTTP will not be listed there.
- The discovery page can be disabled via `management.endpoints.web.discovery.enabled=false`.
- Endpoints mapped on a different port or base path may not appear at the URL the caller is checking.
- Security may block viewing the discovery page.

Therefore, not seeing `metrics` under `/actuator` does not prove the endpoint bean does not exist at all. Conversely, seeing a link does not guarantee the caller has permission to view its contents after following that link.

## 12. Permission to View Details Differs from Permission to Call `health`

Being permitted to access an endpoint does not mean a user gets to see all the data the endpoint knows.

Example with `health`:

~~~yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      roles: OPS
~~~

This configuration controls **the level of health detail displayed** to a caller considered authorized by Actuator's health-detail mechanism. It does not replace `SecurityFilterChain` and does not create a principal with the `OPS` role.

One request might be allowed to call `/actuator/health` and receive only:

~~~json
{"status":"UP"}
~~~

while an appropriately authorized operator receives component details as well. Actual statuses, content, and display conditions depend on the Spring Boot version and health group configuration.

Similarly, `env` and `configprops` can hold sensitive configuration. `show-values` properties and Actuator's sanitization mechanisms must be configured for your version alongside exposure limits and authorization.

**Data minimization** and **caller restriction** are two complementary layers of defense, not substitutes for each other.

## 13. Read-Only Does Not Mean an Endpoint Has No Impact

In the modern endpoint access model, `read-only` restricts operations by Actuator operation type. It is not a guarantee that every GET request is lightweight, resource-safe, or non-sensitive.

For example:

- `threaddump` is a read operation yet provides detailed runtime information.
- `env` reveals property sources and configuration metadata.
- `metrics` can expose system details if improperly exposed publicly.
- A custom `@ReadOperation` written by the application could execute an expensive task.

Therefore, when choosing endpoints to expose, still evaluate **data sensitivity, processing cost, and authorized callers**.

Conversely, with `loggers`, reading the logger list differs from changing log levels at runtime. A read-only configuration must not be assumed to also permit write operations.

If write operations are needed, pair appropriate access levels with Security authorization and write-request protections. Do not set `unrestricted` on all endpoints just to make one management operation work.

## 14. The `shutdown` Endpoint: An Important Security Boundary Example

`shutdown` clearly illustrates the difference between existence, enable/access, exposure, and authorization.

Even when the Actuator starter contains shutdown endpoint infrastructure, Spring Boot does not open application shutdown to every HTTP caller by default. Enabling a shutdown operation requires meeting the exact conditions demanded by the Boot version and deployment config.

Questions to review:

1. Is the shutdown endpoint supported and registered?
2. Does enable/access config allow the required operation?
3. Is the endpoint exposed over HTTP?
4. Does security permit an authorized caller to execute the write operation?
5. Are the HTTP method and CSRF policy compatible?
6. Does stopping the application coordinate with the orchestrator, health probes, and graceful shutdown?

In production, it is normally better to use the orchestrator's process termination mechanism rather than exposing a shutdown endpoint over the network. This reduces attack surface and keeps shutdown aligned with managed application lifecycle.

## 15. Impact of Reverse Proxies and Management Ports

When an application sits behind a gateway or ingress, the story does not end at Spring Boot.

Example topology:

~~~text
Client / monitoring agent
           |
           v
     Ingress / gateway
           |
           +--> :8080 application API
           |
           +--> :9090 management server
                     |
                     v
                /actuator/*
~~~

A request may be denied or fail to reach the management server because:

- Ingress lacks a route for the management port.
- A firewall or network policy only allows traffic from the monitoring namespace.
- The management server binds only to loopback or a private interface.
- Proxy path rewriting mismatches `management.endpoints.web.base-path`.
- TLS termination or authentication at the gateway is misconfigured.
- The gateway intentionally returns `404` to avoid revealing endpoints.

Therefore, when `curl localhost` behaves differently from requests via a public domain, inspect the proxy path, routing, and network policies step by step. Do not blindly alter Actuator configuration if the endpoint already works internally.

### Which Path Should Health Probes Use?

If the management server runs on a separate port, the health endpoint on the management port may keep succeeding while the main web server is malfunctioning. For some systems, exposing probes on the application port as well is advisable, depending on Boot version capabilities:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

Additional paths are typically `/livez` and `/readyz` on the main port. However, verify actual routing, especially if the application has a context path or proxy layer.

This is a matter of confirming **the right path for health requests**, not merely confirming the health endpoint exists.

## 16. Practical Diagnostic Scenarios

### Scenario A: `health` Works, `metrics` Returns 404

A common cause is that `health` is exposed by default while `metrics` is not yet in the HTTP exposure list.

Check:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics
~~~

If it still returns `404`, next check endpoint access/enable, dependencies, base path, and management port. Do not jump to blaming Spring Security, since security typically responds with `401` or `403` when blocking via authentication/authorization, though actual config may vary.

### Scenario B: `metrics` Returns 401

This usually indicates the request reached a protected area while the caller is unauthenticated. Supply valid credentials or configure the monitoring client's authorization according to system policy.

Do not rush to make `metrics` public just to get rid of `401`.

### Scenario C: `metrics` Returns 403 Even When Logged In

Check roles, authorities, and `SecurityFilterChain`. If the request is a POST/DELETE to a management operation, also check CSRF and operation permissions.

Role `OPS` in code with `hasRole("OPS")` normally checks authority `ROLE_OPS`. Ensure the authentication system issues that exact authority.

### Scenario D: `prometheus` Missing Despite Being Included

Check the Micrometer Prometheus registry dependency. Listing an endpoint name in `include` does not conjure a missing integration.

Once the registry is present, verify access/enable permissions, HTTP exposure, URL, and security.

### Scenario E: `/actuator` Returns 404 Yet `/actuator/health` Returns 200

The discovery page may be disabled or the base path route does not publish links. Do not infer that all endpoints vanished. Test the specific endpoint path directly and verify `management.endpoints.web.discovery.enabled`.

### Scenario F: `health` Returns 503 When the Database Fails

If the response was generated by Actuator's health endpoint with status `DOWN`, this is a **health check result**, not necessarily a missing endpoint or permission error.

Review the health contributors, health-status-to-HTTP mapping policy, and the distinction between liveness and readiness. A failing external dependency should not necessarily fail the liveness probe.

### Scenario G: Same Configuration Produces Different Results Across Environments

Check active profiles, environment variables, command-line arguments, external config files outside the JAR, and actual dependencies in each environment. A higher-precedence property source can override a setting.

When an application uses multiple management contexts, sending the same URL to a different port or context can also cause confusion.

## 17. A Minimal, Intentional Observability Configuration

For an application needing health for orchestration and metrics for monitoring, you can start with minimal exposure:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
  endpoint:
    health:
      show-details: never
~~~

This configuration does not yet supply an authorization policy; protect `metrics` and `info` according to sensitivity and system needs using Spring Security, network restrictions, or both.

If using a version supporting the `access` model and wishing to permit read operations only:

~~~yaml
management:
  endpoints:
    access:
      default: none
    web:
      exposure:
        include: health,info,metrics
  endpoint:
    health:
      access: read-only
    info:
      access: read-only
    metrics:
      access: read-only
~~~

In environments needing `loggers` or other management write operations, configure that specific endpoint individually instead of opening all operations globally.

An easily maintainable deployment guideline is:

- **Expose the fewest endpoints needed to satisfy observability requirements.**
- **Prefer read-only access when write operations are unnecessary.**
- **Authenticate and authorize by identity for internal data.**
- **Restrict the management port via network policies, gateways, or private networks.**
- **Do not put secrets or sensitive information in responses.**
- **Verify endpoints along the exact path used by the monitoring client.**

## 18. Four-Condition Verification Workflow

When an Actuator endpoint does not work, go in order:

1. Confirm the Spring Boot version and dependencies for Actuator/the specific endpoint.
2. Confirm the endpoint can be registered in the `ApplicationContext`; inspect required auto-configuration conditions.
3. Check the endpoint enablement mechanism for your version: traditional `enabled` or modern `access`.
4. Check whether the needed operation is restricted by `read-only` or `max-permitted`.
5. Check exposure for the transport being used, distinguishing HTTP from JMX.
6. Check `include`, `exclude`, base path, path mapping, context path, and management port.
7. Verify the request can reach the application through firewalls, services, ingress, and gateways.
8. Check authentication, authorization, and, for write operations, CSRF.
9. Use the HTTP status and body to distinguish a missing mapping, a blocked request, and an endpoint reporting business/operational status such as health `DOWN`.
10. If behavior differs across environments, determine which property sources and profiles actually took effect.

The key takeaway is that **existing, enabled, exposed, and authorized are not a single state**. An endpoint can be fully implemented yet lack an HTTP mapping, have a mapping yet be rejected by Security, or be called successfully yet report health `DOWN`. Separating each condition lets you open observability intentionally, avoid over-exposure, and diagnose Spring Boot Actuator issues quickly and accurately.
