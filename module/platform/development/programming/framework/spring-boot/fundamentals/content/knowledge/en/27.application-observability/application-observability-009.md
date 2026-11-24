# Sensitive Configuration Data and Endpoint Exposure Policy

Spring Boot Actuator helps observe a running application through endpoints such as `health`, `info`, `metrics`, `env`, `configprops`, `loggers`, or `heapdump`. These endpoints are very useful for operations, yet not every endpoint should be reachable from every network or by every account.

A critical operational requirement is **publishing only necessary information to the right audience**. Endpoint names, access addresses, authentication state, response detail levels, and data placed into metrics/logs all affect the likelihood of information exposure.

For example, `/actuator/env` can reveal property source names, profiles, and configuration structure. `/actuator/configprops` reveals `@ConfigurationProperties` groups. `/actuator/heapdump` can contain data still residing in process memory. `/actuator/loggers` can alter log levels at runtime. Even read-only endpoints like `mappings`, `beans`, or `metrics` can disclose internal structure or data labels that should not be public.

This lesson focuses on Spring Boot **3.3**, Spring MVC, and Spring Security 6 in HTTP examples. It covers classifying sensitive data, configuring exposure, value-masking mechanisms, access permissions, health details, management networking, deployment policies, and testing to prevent accidental information disclosure.

## 1. Application Observability Does Not Mean Making All Data Public

Observability generally requires three signal sources: logs, metrics, and traces. Actuator provides several endpoints to read or control related components. However, an observability endpoint can return more information than a dashboard or health check genuinely needs.

For instance, different stakeholders have different needs:

| Stakeholder | Data Typically Needed | Should Not Be Granted by Default |
| --- | --- | --- |
| Load balancer/kubelet | Health or readiness status | Property sources, heap dumps |
| Metrics scraper | Selected metrics | Secrets, full bean map |
| Developer in test environment | Condition report, logger detail | Sensitive production data |
| SRE/operations | Selected internal diagnostic endpoints | Unrestricted write access to all endpoints |
| End users | Business APIs | Internal management endpoints |
| Audit systems | Appropriate access/admin events | Full memory dumps or credentials |

Therefore, “having an endpoint” and “opening an endpoint” are two separate decisions. An endpoint may be essential for diagnostics while still needing to be restricted to internal networks, authorized roles, and controlled access windows.

### 1.1. Types of Data Easily Exposed

Sensitive information is not just passwords. Examples:

- Passwords, API keys, access tokens, private keys, client secrets, session cookies.
- URLs containing credentials or sensitive query parameters.
- Database hostnames, internal service names, private IPs, or infrastructure endpoints.
- Bean names, class names, packages, and internal route mappings.
- Configuration values for a specific tenant.
- Request/response bodies, headers, or identifying info in HTTP exchanges.
- Metric labels containing user IDs, emails, tokens, or personal information.
- Thread stacks, heap objects, buffers, and data in memory dumps.

Not all information carries the same risk. Policies must be based on **the harm if information is disclosed or an endpoint is manipulated**, not merely whether an endpoint has the word “secret” in its name.

## 2. Control Layers of an Actuator Endpoint

For an Actuator endpoint to be callable over HTTP, separate at least three layers:

1. **Enablement**: whether the endpoint is enabled and exists in the application context.
2. **Exposure**: whether the endpoint is published over HTTP/JMX.
3. **Security/authorization**: whether the request passes authentication and permission checks.

An important fourth layer is **response disclosure**: even when permitted to call the endpoint, how much detail is the response allowed to reveal?

~~~mermaid
flowchart TD
    A["Endpoint present in application?"] --> B{"Endpoint enabled?"}
    B -->|No| X["No endpoint available"]
    B -->|Yes| C{"Exposed over HTTP/JMX?"}
    C -->|No| Y["Not accessible over that transport"]
    C -->|Yes| D{"Network + authentication + authorization?"}
    D -->|No| Z["Access denied"]
    D -->|Yes| E{"Data display policy"}
    E --> F["Permitted status / metadata"]
    E --> G["Masked values / restricted details"]
~~~

An **exposed** endpoint does not guarantee callers are allowed access. Conversely, an unexposed endpoint will not gain an HTTP URL from `SecurityFilterChain`. And an authenticated caller does not mean every secret should be returned verbatim.

### 2.1. Endpoint Enablement

In Spring Boot 3.3, most built-in endpoints are enabled by default except `shutdown`. You can disable an endpoint:

~~~properties
management.endpoint.env.enabled=false
~~~

Or switch to an opt-in model:

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

This configuration **enables only** `health` and `info`; other endpoints are not enabled by default. To make both appear over HTTP, web exposure configuration must also be considered.

A disabled endpoint is not merely hidden at a URL; it is no longer provided as an available endpoint in the context per Actuator's mechanism.

### 2.2. Endpoint Exposure

Default HTTP exposure in Spring Boot 3.3 is:

~~~properties
management.endpoints.web.exposure.include=health
~~~

JMX exposure also defaults to `health` only in the 3.3 line.

To also allow `info` and `prometheus` over HTTP:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,prometheus"
~~~

`prometheus` is only available when the application has the matching Micrometer registry dependency and configuration; listing a name in `include` does not install the dependency that creates that endpoint.

You can exclude endpoints via:

~~~properties
management.endpoints.web.exposure.include=health,info,env
management.endpoints.web.exposure.exclude=env
~~~

In include/exclude settings, **exclude takes precedence**. Thus `env` is not exposed over HTTP in this example.

### 2.3. Authentication and Authorization

If Spring Security is on the classpath and the application defines no custom `SecurityFilterChain`, Spring Boot 3.3 includes auto-configuration that protects exposed Actuator endpoints other than `health`.

However, if the application **declares its own `SecurityFilterChain`**, Boot's default Actuator protection configuration yields control to the application. You must then protect management endpoints yourself alongside the rest of the web application.

Do not rely on the mindset “Spring Security is in dependencies so every endpoint must already be properly protected.” Inspect the application's **actual filter chains and matchers**.

### 2.4. Response Detail Level

For instance, `health` can return overall status for public probes without returning specific database status or component structure.

`env` and `configprops` can return property names while masking values according to the `show-values` policy. This is a data-protection layer **after** the decision to let the request reach the endpoint.

## 3. Actuator Defaults in Spring Boot 3.3

Adding Actuator with Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Or Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

With a web application using standard configuration, the default URL for health is:

~~~http
GET /actuator/health
~~~

A simple response can be:

~~~json
{"status":"UP"}
~~~

Key defaults to remember in Spring Boot 3.3:

| Setting | Notable Default Value/Behavior |
| --- | --- |
| HTTP exposure | `health` only |
| JMX exposure | `health` only |
| Most endpoint enablement | Enabled, though not necessarily exposed |
| `shutdown` | Disabled |
| `health.show-details` | `never` |
| Values in `env`, `configprops`, `quartz` | Masked as `******` by default |
| Web base path | `/actuator` |

Exact behavior also depends on dependencies, application type, and custom config. For example, `prometheus`, `httpexchanges`, or `startup` have their own conditions for providing endpoints.

### 3.1. Distinguishing `enabled` and `exposed` by Example

Suppose:

~~~yaml
management:
  endpoint:
    env:
      enabled: true
  endpoints:
    web:
      exposure:
        include: "health,info"
~~~

`env` is enabled, yet **not in the HTTP include list**. Therefore `/actuator/env` does not become an exposed URL solely from `enabled: true`.

For `env` to have a URL, you must include `env` in web exposure; that is also the moment to decide whether it truly needs to be published.

### 3.2. Avoid Including Everything

A configuration requiring extreme caution:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
~~~

The `*` must be quoted in YAML. More importantly, this opens a very broad exposure scope that may include endpoints inappropriate for publication on the service's network.

Even when Spring Security is configured, the better policy is usually an **allowlist**: include only the endpoints needed for observability.

## 4. Risks of Individual Endpoint Groups

Not every endpoint is sensitive in the same way.

| Endpoint | Information/Behavior | Primary Risk |
| --- | --- | --- |
| `health` | Status and health contributor info | Leaks dependency topology/status if details are opened |
| `info` | Application info from config/contributors | Leaks version, commit, environment, or internal metadata |
| `metrics` | Metrics and available meter names/tags | Leaks operational metadata and unsafe labels |
| `prometheus` | Metrics in scrape format | Leaks metric labels and operational structure |
| `env` | Environment property sources and values per policy | Leaks property names, config topology, and secrets if values shown |
| `configprops` | `@ConfigurationProperties` groups and values per policy | Leaks structure and configuration data |
| `beans` | Bean names, types, dependencies | Leaks application architecture |
| `conditions` | Auto-configuration condition report | Leaks active libraries and feature flags |
| `mappings` | Request mappings | Leaks HTTP routes/internal endpoint structure |
| `loggers` | View and change logger levels | Runtime mutation can enable sensitive DEBUG/TRACE |
| `logfile` | Log file contents if configured | May contain tokens, headers, request data |
| `httpexchanges` | HTTP exchange info if repository exists | Can leak request/response metadata |
| `threaddump` | Thread stacks | Leaks implementations, class/method names, and state |
| `heapdump` | Process heap data | May contain secrets, PII, session data, buffers |
| `shutdown` | Request to stop application | Availability alteration risk |

This table does not claim every endpoint returns secrets. It emphasizes that **endpoints that can carry sensitive info or alter state require dedicated policies**.

### 4.1. Read-Only Can Still Be Dangerous

An endpoint using HTTP GET is not automatically safe to publish. `heapdump` is an example: downloading a memory dump can capture objects containing credentials or application data still in memory.

Even when transferred over HTTPS, recipients might save the file onto unmanaged machines. You must control **who may download, where files are stored, retention duration, and deletion**.

### 4.2. State-Changing Endpoints Need Stricter Controls

`loggers` supports changing levels via POST. `shutdown` stops the application if enabled. Other endpoints with write/delete operations can also alter state.

Do not merely authenticate callers; authorize specific operations and audit changes rather than granting them broadly to every logged-in account.

## 5. `env` and `configprops`: Why Value Masking Exists

`/actuator/env` provides info about `Environment` and property sources. `/actuator/configprops` summarizes beans bound via `@ConfigurationProperties`. Both help diagnose misconfiguration yet can also touch sensitive values.

An example application config:

~~~yaml
app:
  billing:
    endpoint: https://billing.internal.example
    connect-timeout: 3s
    api-key: ${BILLING_API_KEY}
~~~

Code can bind:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import java.time.Duration;

@ConfigurationProperties(prefix = "app.billing")
public record BillingProperties(
        String endpoint,
        Duration connectTimeout,
        String apiKey
) {}
~~~

`api-key` is data that should never be returned verbatim over a public management endpoint. Even `endpoint` may be internal info needing restriction depending on environment.

### 5.1. Default Sanitization in Spring Boot 3.3

In Spring Boot 3.3, `env`, `configprops`, and `quartz` endpoints **mask all values by default** (displayed as `******`). This is protective behavior even when a value looks non-sensitive.

Illustrative response data:

~~~json
{
  "property": {
    "value": "******",
    "origin": "class path resource [application.yml]"
  }
}
~~~

Actual endpoint JSON structure can differ by URL and version. Notice that the value is masked, **yet property names or origin/metadata may still appear**. Thus masking values does not make the endpoint safe for everyone.

### 5.2. `show-values` Has Three Modes

For sanitizable endpoints, the `show-values` property has levels:

| Value | Meaning |
| --- | --- |
| `never` | Always mask values |
| `when-authorized` | Allow callers deemed authorized to view values unmasked by this mechanism |
| `always` | Allow showing values to every caller reaching the endpoint, unless a custom sanitizing function still masks them |

Example:

~~~properties
management.endpoint.env.show-values=never
management.endpoint.configprops.show-values=never
~~~

This is an explicit configuration consistent with protective defaults.

**Do not use `show-values=always` in production just for quick debugging.** If the endpoint is exposed and reachable by callers, configuration info you never intended to disclose can be returned verbatim.

### 5.3. `when-authorized` Needs Explicit Roles

Example allowing only accounts with the Actuator admin role to view values in `env`:

~~~yaml
management:
  endpoint:
    env:
      show-values: when-authorized
      roles:
        - ACTUATOR_ADMIN
~~~

Over HTTP, the user must be authenticated and hold the configured role to be deemed authorized for value display. In Spring Boot 3.3, if no roles are configured for the endpoint, **any authenticated user** is typically treated as authorized when `when-authorized` is enabled.

Therefore:

~~~properties
management.endpoint.env.show-values=when-authorized
~~~

does not mean “only SRE/admins may view values.” Without setting roles, permissions may be broader than intended.

### 5.4. Roles for `env` and `configprops` Are Independent Settings

If both endpoints genuinely need to be opened for internal diagnostics:

~~~yaml
management:
  endpoint:
    env:
      show-values: when-authorized
      roles:
        - ACTUATOR_ADMIN
    configprops:
      show-values: when-authorized
      roles:
        - ACTUATOR_ADMIN
~~~

This **does not protect HTTP URLs** if filter chains or network policies allow others through. Pair it with an endpoint exposure allowlist and Spring Security authorization.

Additionally, even a user allowed to view values should not receive all secrets if business needs do not require it. Whenever possible, keep `show-values=never` and provide a dedicated diagnostics endpoint returning only safe metadata.

### 5.5. JMX Does Not Use the Same HTTP Authentication Mechanism

In Spring Boot 3.3, under the `show-values` policy of sanitizable endpoints, when accessed via JMX the caller is treated as authorized in Actuator's check. Thus `when-authorized` is not a JMX firewall equivalent to a Spring Security HTTP filter chain.

If your organization uses JMX, establish **separate JMX connector authentication, network access controls, and JMX exposure**, or keep JMX exposure strictly minimal.

## 6. `SanitizingFunction`: An Additional Value-Masking Layer

Spring Boot 3.3 has the `SanitizingFunction` extension point to customize masking of specific values as they pass through endpoint sanitization.

Key point: a custom sanitizing function can continue masking certain values even when `show-values` permits display.

One way to view the policy:

- `show-values` decides whether raw values are permitted in that context.
- `SanitizingFunction` allows adding tailored data-masking rules.
- HTTP authentication/authorization decides who can access the endpoint.
- Exposure and network policies restrict where the endpoint appears.

Do not rely solely on a regex matching `password`, `secret`, or `token`, because sensitive data can sit under keys without predictable keywords. For example, an internal URI with embedded credentials, a custom environment variable name, or an object whose `toString()` includes a secret still creates risk.

**The best strategy remains not exposing endpoints containing overly sensitive data when unnecessary**, rather than trying to write a filter that catches every case.

## 7. The `health` Endpoint: Publishing Status Differs From Publishing Details

`health` is usually the endpoint load balancers, container orchestrators, and monitoring systems need to call. However, those callers typically only need to know whether the application is ready, not database names, connection details, or all health contributors.

### 7.1. Details Hidden by Default

Configuration:

~~~yaml
management:
  endpoint:
    health:
      show-details: never
      show-components: never
~~~

In Spring Boot 3.3, `show-details` defaults to `never`. `show-components` also controls component structure visibility. Setting them explicitly expresses a clear disclosure policy.

A simple response:

~~~json
{"status":"UP"}
~~~

### 7.2. Show Details Only to Permitted Groups

~~~yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      roles:
        - ACTUATOR_ADMIN
~~~

When the user is unauthorized, the endpoint does not return the same level of detail as for an admin user. If you need to control the component list too, configure `show-components` appropriately.

Do not confuse `show-details=when-authorized` with automatically locking down the health URL. It is a **response policy**; the URL may still need unauthenticated access by health checkers to read status.

### 7.3. `always` Means Truly Publishing Details

~~~yaml
management:
  endpoint:
    health:
      show-details: always
~~~

If `/actuator/health` is publicly reachable, dependency health details can also be exposed publicly. Use only if details have been evaluated as safe and disclosure is intentional.

### 7.4. Liveness and Readiness

With Spring Boot running in an environment supporting application availability/probes, you can use endpoints:

~~~text
/actuator/health/liveness
/actuator/health/readiness
~~~

These endpoints are helpful for Kubernetes probes or monitoring. They serve narrower questions than the entire health contributor tree.

Example config when explicitly enabling probes:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
~~~

Do not attach every external dependency to liveness and let the orchestrator restart the app just because one dependency is temporarily unavailable. Readiness and liveness must match the operational meaning of each check.

## 8. Configuring HTTP Exposure With an Allowlist

A policy for production might need only:

- `health` for probes.
- `info` if content has been curated.
- `prometheus` if the system uses Prometheus with a secure scrape path.

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
          - prometheus
  endpoint:
    health:
      show-details: never
      show-components: never
    env:
      show-values: never
    configprops:
      show-values: never
~~~

In the example, `env` and `configprops` have value masking set, yet **they are not exposed over HTTP** because they are absent from the include list. This is defense in depth, not pointless duplication.

### 8.1. Why Not Use `exposure.include="*"` and Exclude a Few Endpoints?

Example:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
        exclude: "env,configprops,heapdump,shutdown"
~~~

This config can still publish many other endpoints: `beans`, `mappings`, `conditions`, `loggers`, or a new endpoint added after adding a dependency or upgrading the framework.

An allowlist has the advantage of **fail-closed**: endpoints outside the list do not suddenly appear over HTTP just because a new release introduces an endpoint.

### 8.2. JMX Needs Its Own Policy

The HTTP allowlist does not govern JMX exposure. If the application does not need JMX monitoring, apply a dedicated JMX policy, for example:

~~~properties
management.endpoints.jmx.exposure.include=health
~~~

Do not assume Spring MVC or WebFlux security rules protect a JMX connector; that is a different transport.

### 8.3. Do Not Use Renaming `base-path` as a Security Measure

Changing:

~~~properties
management.endpoints.web.base-path=/management
~~~

only alters the endpoint URL path; it performs no authorization. A hard-to-guess path does not replace network isolation, authentication, or permission checks.

## 9. How Does Spring Security Protect Actuator?

Spring Security can make decisions based on route matchers, principals, and roles/authorities.

With Spring MVC, Spring Boot provides `EndpointRequest` to build matchers for Actuator endpoints rather than hardcoding URL strings. This helps when the application changes its base path.

If the application configures a custom `SecurityFilterChain`, explicitly define rules for both Actuator and business APIs. Remember that a custom chain can cause Boot's Actuator security auto-configuration to yield control.

### 9.1. Example: Two Separate Filter Chains

Spring Security 6 / Spring Boot 3.3 example:

~~~java
package com.example.demo.security;

import static org.springframework.security.config.Customizer.withDefaults;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain actuatorSecurity(HttpSecurity http)
            throws Exception {

        http.securityMatcher(EndpointRequest.toAnyEndpoint());

        http.authorizeHttpRequests(requests -> requests
                .requestMatchers(EndpointRequest.to("health")).permitAll()
                .anyRequest().hasRole("ACTUATOR_ADMIN")
        );

        http.httpBasic(withDefaults());
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(requests -> requests
                .anyRequest().authenticated()
        );

        http.httpBasic(withDefaults());
        return http.build();
    }
}
~~~

This is an example of an **authorization policy**, not a complete production IAM/identity provider setup. In a real system, you must authenticate users or service identities and map authorities such as `ROLE_ACTUATOR_ADMIN`. Configure HTTPS/TLS and appropriate credential management.

Meaning:

1. The chain with `@Order(1)` applies to Actuator endpoints.
2. `health` allows unauthenticated calls because health checkers may need status.
3. Other Actuator endpoints require role `ACTUATOR_ADMIN`.
4. The `@Order(2)` chain handles remaining application HTTP requests, avoiding accidentally leaving business APIs unprotected.

**Note:** the example permits anonymous `health` through security, yet the exposure policy still must include `health`. It does not enable `env`, `configprops`, or `loggers`.

### 9.2. Do Not Configure One Chain Only for Actuator and Forget the API

An anti-pattern:

~~~java
@Bean
SecurityFilterChain actuatorOnly(HttpSecurity http) throws Exception {
    http.securityMatcher(EndpointRequest.toAnyEndpoint());
    http.authorizeHttpRequests(requests -> requests
            .anyRequest().authenticated()
    );
    return http.build();
}
~~~

If that is the **only chain** the application configures, requests outside the Actuator matcher may not be covered by this chain while default application security already stepped aside for the custom chain. Therefore, include a catch-all chain or configuration covering business APIs.

### 9.3. Role Names and `hasRole`

`hasRole("ACTUATOR_ADMIN")` normally checks for an authority prefixed with `ROLE_` by Spring Security default. If an identity provider supplies authorities under another convention, configure mapping or use `hasAuthority(...)` with the right name.

Do not assume an arbitrary JWT claim named `role` is automatically converted into a `GrantedAuthority`; verify the mapping in security configuration.

### 9.4. CSRF for Write Operations

In Spring Security using defaults, CSRF protection can cause POST requests to `/actuator/loggers` or `/actuator/shutdown` to return 403 when lacking a CSRF token, even if the caller is authenticated.

Do not solve this by **arbitrarily disabling CSRF globally**. For machine-to-machine clients, you can use a narrow security chain without browser sessions with a tailored CSRF policy, combined with strong authentication/authorization. Permit write operations only when truly necessary.

## 10. Exposure and Authorization Must Be Controlled Together

A misguided example:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
~~~

and then hoping “Actuator is protected by default” is enough. Risks:

- The application might define a custom `SecurityFilterChain` that fails to cover management URLs.
- New endpoints may be published without review.
- Authorization might be overly broad, e.g., any authenticated user can view diagnostics.
- Read endpoints can still carry sensitive info even with values masked.
- Access via reverse proxy/JMX or management ports might differ from expectations.

Better:

~~~text
Enable only truly needed endpoints
    -> Expose only over needed transports
        -> Route only on permitted networks
            -> Authenticate exact identities
                -> Authorize by role and operation
                    -> Limit returned details/values
                        -> Audit, monitor, and review periodically
~~~

Combining control layers reduces blast radius if one layer is misconfigured.

## 11. Management Port, Interface, and Internal Networks

Spring Boot lets you place management HTTP endpoints on a port different from the main application port.

Example:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 9001
  endpoints:
    web:
      exposure:
        include: "health,info,prometheus"
~~~

In this case, application APIs can run on port 8080 while management endpoints run on port 9001. With a separate management port, Boot can create a separate management context.

However, **changing the port is not an authentication mechanism**. If port 9001 is open to a public network, the risk remains.

### 11.1. Binding Loopback in Suitable Environments

If management access is needed only from the same host, consider:

~~~yaml
management:
  server:
    port: 9001
    address: 127.0.0.1
~~~

With Spring Boot, `management.server.address` is properly used when the management port is configured separately from the application port.

A loopback interface can prevent remote scrapes/probes from outside the host. In Kubernetes, kubelet typically calls the Pod IP rather than localhost inside the container's network namespace. So do not apply loopback binding mechanically to deployments requiring cluster probes.

### 11.2. Network Policy and Reverse Proxies

In container or cloud environments, you can restrict access using:

- Firewalls/security groups for the management port.
- Kubernetes `NetworkPolicy` and internal `Service`.
- API gateway/reverse proxy rules blocking `/actuator/**` from public ingress.
- Service identity or mTLS for internal traffic.
- RBAC/authorization per endpoint.
- IP allowlists if appropriate for topology and reliably managed.

Network isolation is important yet should not be the sole protection layer for endpoints holding highly sensitive data.

### 11.3. Separate Management Port Still Requires Security Verification

When using a separate management context, confirm that `SecurityFilterChain`s, authentication, and request matchers work properly on the management port for your actual version/configuration.

Do not assume a filter chain configured for the main web context always covers every request on the management context across all setups. Verify with integration tests or smoke tests on the **actual exposed port**.

## 12. `heapdump` and `threaddump`: Different Risks

`threaddump` can expose thread names, stack traces, and implementation details. `heapdump` is more sensitive because the dump can contain objects in the heap, including request data, caches, credentials, or tokens residing in memory.

### 12.1. Never Open `heapdump` Over Public Networks

A heap-dump download endpoint does not belong on public ingress. When a heap dump must be captured for an incident:

1. Require approval and restrict who can execute it.
2. Capture via a secure diagnostic environment.
3. Avoid taking/transferring heap dumps unnecessarily.
4. Encrypt at rest and in transit.
5. Limit retention and delete upon completion.
6. Monitor access permissions and audit download activity.

An account permitted to read health **should not** also default to permission to download heap dumps.

### 12.2. Thread Dumps Can Also Expose Details

Thread dumps do not contain the full heap, yet stack traces and thread names can still reveal implementation classes, job names, queue names, or system metadata. Treat it as an internal diagnostic endpoint.

## 13. `loggers` and `logfile`: Observability That Can Also Leak Data

`/actuator/loggers` allows viewing configured/effective log levels, and in suitable configurations changing levels while the application is running.

Example:

~~~http
GET /actuator/loggers/com.example.payment.PaymentService
~~~

Illustrative response:

~~~json
{
  "configuredLevel": null,
  "effectiveLevel": "INFO"
}
~~~

To change the level:

~~~http
POST /actuator/loggers/com.example.payment.PaymentService
Content-Type: application/json

{"configuredLevel":"DEBUG"}
~~~

Someone permitted to change log levels can make the application log far more detail. If code logs tokens, request payloads, or sensitive objects at DEBUG/TRACE, data-exposure risk rises.

### 13.1. Appropriate Policy for `loggers`

- Do not expose to the public Internet.
- Grant change permissions only to specific administrative roles.
- Audit who changed which logger, when, and why.
- Time-box DEBUG/TRACE activation.
- Restore the original level after diagnosis.
- Reduce the risk of logs containing secrets in source code in the first place.
- Avoid enabling root TRACE in production.

### 13.2. `logfile` Can Carry Personal Data

If `logfile` is exposed, a caller can download the contents of the configured application log file. Logs may contain headers, user IDs, error descriptions, or data accidentally logged by developers.

Do not assume log files are sanitized like `env`. Maintain a dedicated logging policy: redact/mask at the source, enforce role-based access, set retention, and control downloads.

### 13.3. Adding More Logs Cannot Fix Every Bug

Logging level determines which existing events are written; it cannot invent log statements that do not exist. When investigating bugs, use metrics/traces/logging appropriately rather than turning on every endpoint and TRACE everywhere.

## 14. Metrics, Prometheus, and Label Risks

Metrics are usually seen as aggregated data, yet tags/labels can contain sensitive information if developers build meters carelessly.

Example of **what not to do**—using uncontrolled dynamic values as tags:

~~~java
registry.counter(
        "payment.requests",
        "email", customerEmail,
        "token", accessToken
).increment();
~~~

Issues:

- `email` and `token` can leak identity/credential data.
- Each new value can create a new time series, exploding cardinality.
- Monitoring systems and anyone viewing metrics can retain those labels long-term.

Replace with low-cardinality, non-sensitive tags:

~~~java
registry.counter(
        "payment.requests",
        "outcome", "success",
        "method", "card"
).increment();
~~~

The labels `outcome` or `method` in the example come from a small, predefined set of values containing no personal info.

### 14.1. Scraping Does Not Need to Be Anonymous

A Prometheus scraper can be assigned a suitable service identity and permitted access only to `/actuator/prometheus`. `NetworkPolicy` and authentication ensure not every client can scrape metrics.

Not every monitoring server supports the exact same auth mechanism, so tailor it to your system's real topology.

### 14.2. Custom `HealthIndicator`s Can Leak Data Too

A custom `HealthIndicator` should not directly return connection strings with passwords, raw SQL exceptions containing sensitive data, or full remote responses.

Even when details are restricted, design health data on the principle of returning only what is necessary for the component's health decision.

## 15. The `info` Endpoint: Do Not Assume Metadata Is Always Harmless

`info` can provide build version, commit ID, application name, or custom metadata. That information aids release debugging, yet can help outsiders infer:

- Current framework/app versions.
- Internal environment names.
- Build timestamps.
- Source revisions.
- Internal organization/module names.

Policy might allow publishing selected fields (such as public release version) while withholding commit hashes or internal repository URLs if unnecessary.

Example intentional metadata config:

~~~yaml
info:
  app:
    name: public-catalog-api
    version: "1.2.0"
~~~

Review what is actually exposed via `info` according to `InfoContributor` and environment config. Never put API keys inside `info` assuming Actuator will mask arbitrary fields automatically.

## 16. `httpexchanges`, Custom Endpoints, and Returned Data

`httpexchanges` requires a suitable `HttpExchangeRepository` and can provide info on recorded HTTP exchanges. It helps diagnose requests yet requires reviewing URLs, statuses, headers, and data stored by the repository.

Headers like `Authorization` or `Cookie` are especially sensitive. When configuring HTTP exchange recording, retain only necessary info and avoid collecting/exposing credentials.

### 16.1. Custom `@Endpoint` Must Take Responsibility for Its Own Data

Example custom endpoint:

~~~java
import java.util.Map;
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "deployment")
public class DeploymentEndpoint {

    @ReadOperation
    public Map<String, String> current() {
        return Map.of(
                "state", "ready",
                "region", "apac"
        );
    }
}
~~~

This is a simple read endpoint. However, if the method returns:

~~~java
return Map.of(
        "dbPassword", databasePassword,
        "apiKey", apiKey
);
~~~

you have put sensitive values directly into the response. Do not assume every custom endpoint is automatically masked by the same mechanism as `env`/`configprops`.

Better yet, **never put secrets in the response in the first place**. If an endpoint does not need to be exposed to external systems, do not include the `deployment` ID in web exposure.

### 16.2. Endpoints Returning Objects Can Also Leak via Serialization

An object response can accidentally gain a new field as classes evolve. Use a dedicated DTO for publishing operational data with explicitly permitted fields, rather than returning `Environment`, `DataSourceProperties`, or a large domain object directly.

## 17. Sample Configuration: Maximally Restrictive Production Setup

Spring Boot 3.3 example with a policy focused on health/info and Prometheus within a controlled network:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,prometheus"
    jmx:
      exposure:
        include: "health"
  endpoint:
    health:
      show-details: never
      show-components: never
    env:
      show-values: never
    configprops:
      show-values: never
    quartz:
      show-values: never

info:
  app:
    name: example-service
    version: "1.0.0"
~~~

This is an **exposure policy sample**. It does not yet include deployment authentication, firewalls, or ingress configuration. If `prometheus` is exposed on the main HTTP port, add security/network policies so only the appropriate scraper can reach it.

### 17.1. Private Management Port Sample

If the environment supports a separate management port and internal scraping:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 9001
  endpoints:
    web:
      exposure:
        include: "health,info,prometheus"
  endpoint:
    health:
      show-details: never
~~~

Pair it with a network policy preventing 9001 from reaching public ingress and appropriate security rules. Changing the port alone does not guarantee safety.

### 17.2. Sample When `env`/`configprops` Are Genuinely Needed for Diagnostics

Use only in controlled environments:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,env,configprops"
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
~~~

Even with values masked, require an authenticated admin for `env` and `configprops` because property names, config sources, and bean structures can reveal topology.

If raw values must be viewed for an exceptional diagnostic task, consider lower-risk options: an internal command querying a specific key, a tightly controlled diagnostics endpoint, or temporary `when-authorized` with an explicit role, auditing, and time limits.

## 18. Policy by Environment: Local, Staging, Production

Not every environment should share the same endpoint list.

| Environment | Suggested Exposure | Key Conditions |
| --- | --- | --- |
| Local dev | Health, info, and needed diagnostics | Do not use real production data |
| Test/CI | Per test objective; masked env/configprops if needed | Isolated, mock credentials, never public |
| Staging | Close to production; temporary additions if needed | Auth and network policies matching production |
| Production | Health, reviewed info, metrics for scraper | Least privilege, audit, retention, TLS |

### 18.1. Profile-Specific Configuration

Base configuration:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info"
~~~

`application-dev.yml`:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,env,configprops,loggers"
~~~

When the `dev` profile is active, the exposure list changes according to property-source precedence. Ensure the `dev` profile can never be activated accidentally in production.

### 18.2. Do Not Rely on Profiles as the Sole Security Layer

If production is mistakenly configured with `spring.profiles.active=dev`, dev endpoints could open. Independent network/security controls and automated checks verifying actual runtime exposure remain necessary.

## 19. Factors to Consider When Designing an Exposure Policy

Before exposing an endpoint, answer:

1. **Purpose**: who needs this endpoint and to make what decision?
2. **Data**: does the endpoint return status, metadata, user data, secrets, or heap contents?
3. **Permissions**: can the caller read, mutate, delete, or shut down?
4. **Transport**: HTTP, JMX, or both?
5. **Network**: public internet, internal cluster, or localhost?
6. **Identity**: human admin or service account? Is authentication suitable?
7. **Response policy**: are raw details/values needed or only sanitized status?
8. **Duration**: must the endpoint stay open continuously or only during investigation?
9. **Audit**: can you tell who accessed, changed levels, or downloaded dumps?
10. **Review**: when upgrading Boot or adding dependencies, is exposure re-evaluated?

A real policy should be expressed in source-controlled configuration, infrastructure-as-code, and security tests rather than informal verbal agreements.

### 19.1. Least Privilege for Service-to-Service Observability

A Prometheus scraper usually needs only `prometheus`. A Kubernetes health probe needs only health/probe endpoints. A log collector needs no ability to alter log levels via `loggers`.

Use distinct service identities or corresponding network controls where possible, rather than sharing one admin credential across every operational tool.

### 19.2. Information Can Still Persist Outside Endpoints

Even after turning off endpoints, sensitive data can remain in:

- Logs shipped to a centralized system.
- Traces containing attributes.
- Metrics time series with unsafe labels.
- Crash/heap dumps created by external tools.
- CI/CD logs or environment dumps.
- Configuration managers/secret backends.

Actuator policy is one part of **observability data policy**, not a replacement for overall secrets management and data retention.

## 20. Testing Exposure and Authorization

A policy should have automated tests confirming which endpoints are accessible under which identities.

### 20.1. Testing Public Health, Unexposed `env`

With Spring Boot MVC, you can use `MockMvc` in an integration test:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties = {
        "management.endpoints.web.exposure.include=health,info",
        "management.endpoint.env.enabled=true"
})
@AutoConfigureMockMvc
class ActuatorExposureTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void healthIsAvailable() throws Exception {
        mvc.perform(get("/actuator/health"))
                .andExpect(status().isOk());
    }

    @Test
    void envIsNotExposedOverHttp() throws Exception {
        mvc.perform(get("/actuator/env"))
                .andExpect(status().isNotFound());
    }
}
~~~

This example assumes Actuator endpoints and the app's security/test setup match—e.g., health is permitted via `permitAll` and management runs on **the same server port**. With a separate management port, `MockMvc` attached to the main context may not observe the management context accurately; in that case use an integration test against the real port or a matching management context test approach.

`404` behavior can vary if the application has special routing/security/filters. When testing permissions, verify both that unauthorized callers receive no data and that the endpoint actually exists for authorized users if required.

### 20.2. Testing Role-Based Security With Spring Security Test

If using Spring Security and the earlier chain pattern, you can use `@WithMockUser` to simulate authorities in a web security integration test.

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.security.test.context.support.WithMockUser;

class ActuatorAuthorizationExample {

    // Test class needs @SpringBootTest / @AutoConfigureMockMvc configuration
    // along with an injected MockMvc and the appropriate endpoint exposed.

    @Test
    @WithMockUser(roles = "ACTUATOR_ADMIN")
    void adminCanReadProtectedEndpoint() throws Exception {
        // mvc.perform(get("/actuator/info")).andExpect(status().isOk());
    }
}
~~~

This is an illustrative skeleton; for real tests, add test context, bean injection, and runnable assertions. Requires the appropriate `spring-security-test` dependency (usually managed by the project's test starter/security test configuration).

### 20.3. Do Not Test Only Permitted Scenarios

An information-control policy needs negative tests too:

- Anonymous callers cannot read `env`, `configprops`.
- Regular users cannot modify `loggers`.
- No route exists to download `heapdump` from the public listener.
- Health probes receive only status, not raw connection details.
- Mock credentials or markers never appear verbatim in responses.
- Requests on the management port vs. ingress/public routes follow designed policy differences.

If tests only confirm admins can read an endpoint, you have not proven other users are blocked.

### 20.4. Testing Sanitization With a Fake Secret

In a test environment, place a **fake** marker—never real production credentials:

~~~properties
app.demo.fake-secret=FAKE_SECRET_DO_NOT_USE
management.endpoints.web.exposure.include=health,env
management.endpoint.env.show-values=never
~~~

When an authorized caller hits the endpoint, assert the marker value does not appear verbatim in the response. Tests like this catch accidental changes of `show-values` from `never` to `always`.

In real tests, do not print real secrets into failure output if an assertion fails.

## 21. A Risky Example: Custom `SecurityFilterChain` Opening Everything

Suppose a team has a chain:

~~~java
@Bean
SecurityFilterChain security(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(requests -> requests
            .anyRequest().permitAll()
    );
    return http.build();
}
~~~

If at the same time they configure:

~~~properties
management.endpoints.web.exposure.include=*
management.endpoint.env.show-values=always
~~~

they have exposed a large number of Actuator endpoints over HTTP **and** allowed anonymous callers to access them; `env` can display raw values. This is a very high-risk configuration.

Some endpoints have dependency, enablement, or method-specific conditions, yet you should never rely on those to mitigate overall risk.

How to fix:

1. Narrow `exposure.include` to an allowlist.
2. Keep `show-values=never` for configuration-bearing endpoints.
3. Define explicit chains for Actuator and app APIs.
4. Apply network isolation.
5. Test with anonymous/unauthorized callers.
6. Review logs, metrics, and custom endpoints to minimize sensitive data.

## 22. Typical Operational Scenarios

### 22.1. SRE Needs to Inspect a Misconfiguration

**Enabling `env.show-values=always` is not necessarily required.**

A lower-risk sequence:

- Inspect deployment/config source metadata.
- Use safe logs to confirm whether a property bound or a profile is active.
- If Actuator is needed, expose `env` only to matching networks/roles while keeping values masked.
- If a specific value is needed, use an authorized, audited internal channel rather than exposing the entire `Environment`.
- Once diagnosed, revoke access or close the endpoint if opened temporarily.

### 22.2. Monitoring Needs Prometheus

Expose only `prometheus` and `health` if that is the requirement; use a service identity or internal network. Verify metric tags contain no emails, user IDs, or tokens.

### 22.3. Incident Requires a Heap Dump

Do not open `heapdump` through public ingress. Collect over a restricted channel, protect the dump file with encryption/access controls, and delete per retention.

### 22.4. Operator Wants to Enable DEBUG

If using `loggers`, require an authenticated admin, auditing, time limits, and a plan to restore the level. Do not grant the same permission to a health checker.

### 22.5. Public Status Page Needs System Status

A public status page typically needs only overall status or aggregated data. Never expose the entire health contributor tree or dependency exceptions just to display the word “UP.”

## 23. Common Errors

| Symptom | Possible Cause | Where to Address |
| --- | --- | --- |
| `/actuator/env` returns 404 | Endpoint unexposed or disabled | Check `enabled` and web exposure separately |
| `/actuator/health` returns UP without details | Default `show-details=never` | Enable details only for authorized roles if needed |
| `env` returns `******` | Default sanitization | Intended protective behavior; do not rush to set `always` |
| `when-authorized` exposes raw values to too many users | `roles` not restricted | Specify explicit roles and verify HTTP security |
| Endpoint returns 401 | Unauthenticated | Use authorized identity and verify auth config |
| Endpoint returns 403 | Insufficient permission or CSRF on write request | Check authorities and CSRF policy |
| Custom filter chain drops Actuator protection | Default security backed off | Define chains for both Actuator and app |
| `/actuator/**` open through ingress | Overly broad reverse proxy route | Block public route and use internal management service |
| Prometheus cannot scrape | Missing registry dependency, unexposed, or blocked by network policy | Check registry/exposure/network |
| Heap dump accidentally downloadable publicly | Wildcard include and broad authorization | Disable exposure, restrict roles, audit access logs |
| Data still leaks despite `env` masking | Logs, metrics, info, other custom endpoints | Review entire observability data surface |
| Changed management port yet still reachable externally | Separate port still routed publicly | Add firewall/network policy and auth |
| Kubernetes readiness probe fails after localhost bind | Kubelet cannot reach loopback listener | Configure Pod networking and probes per topology |
| Actuator URL changed | Base path or management port modified | Check routes and `EndpointRequest` matchers |
| JMX access differs from HTTP | JMX bypasses Spring web filters | Configure JMX transport and authentication separately |

### 23.1. Safe Investigation Workflow

When an endpoint stops working or appears to leak data:

1. Identify the Spring Boot version and Actuator dependencies in use.
2. Check whether the endpoint is enabled and exposed over the intended transport.
3. Determine the actual management port/base path.
4. Inspect reverse proxy/ingress/network policies.
5. Check identity, role/authority mapping, and `SecurityFilterChain` matchers.
6. Check `show-details`, `show-components`, or `show-values`.
7. Inspect responses using an authorized test account, **without logging raw secrets**.
8. Test anonymous and unauthorized user cases.
9. Review custom endpoints, metric labels, and related log data.
10. Fix the policy and add a regression test so the mistake does not recur.

## 24. Hands-On Exercises

### Exercise 1 — Enabled Differs From Exposed

Create a Spring Boot app with Actuator. Enable `env` via `management.endpoint.env.enabled=true` while exposing only `health,info`. Call `/actuator/env` and explain why the endpoint is unreachable over HTTP.

### Exercise 2 — Allowlist vs. Wildcard

Compare two configurations:

~~~properties
management.endpoints.web.exposure.include=health,info
~~~

and:

~~~properties
management.endpoints.web.exposure.include=*
~~~

List additional endpoints that can appear in the second configuration and analyze their risks, not just the difference in URL count.

### Exercise 3 — Sanitization

Add a property with a fake marker in `application.yml`. Expose `env` only in a test environment and set `show-values=never`. Observe the masked value; then explain why property names/origins still require access restrictions.

### Exercise 4 — `when-authorized`

Set `management.endpoint.env.show-values=when-authorized` and role `ACTUATOR_ADMIN`. Write security tests with an anonymous user, a regular authenticated user, and an admin. Confirm the fake raw marker is visible only under the intended condition.

### Exercise 5 — Health Details

Set `health.show-details=never`, call the health endpoint, and record the response. Then change to `when-authorized` with an appropriate role. Compare a health checker reading status against an admin reading details.

### Exercise 6 — Two `SecurityFilterChain`s

Create a dedicated chain for Actuator and a chain for application APIs. Ensure `health` allows anonymous access, admins can read diagnostic endpoints, and business APIs do not accidentally become public.

### Exercise 7 — Management Port

Set `management.server.port` different from `server.port`. Verify routing and security on both ports. If using Docker/Kubernetes, explain why binding `127.0.0.1` can prevent external scrapes/probes from outside the container.

### Exercise 8 — The `loggers` Endpoint

In an isolated test environment, expose `loggers` to admins only. Test GET and POST. Explain the impact of CSRF, authentication, and changing DEBUG/TRACE on data security.

### Exercise 9 — Metric Label Review

Create a counter by `outcome` and a counter by `customerEmail`. Assess data-leakage risk and cardinality; redesign the second metric to exclude personal data.

### Exercise 10 — Incident Response

Suppose a heap dump is needed to investigate a production memory leak. Write a workflow for authorization, secure capture, encryption, storage, auditing, and deletion; explain why `exposure.include=*` should not be used.

### Exercise 11 — Policy Review

Create a policy table for `health`, `info`, `metrics`, `prometheus`, `env`, `configprops`, `loggers`, and `heapdump`: who needs it, whether it is exposed, over which transport, and whether a specific role is required.

### Exercise 12 — Security Regression Test

Write tests confirming anonymous callers cannot read `env` and admins cannot download `heapdump` over the public listener because the endpoint is unexposed. Use a fake marker to verify value-masking configuration without putting real secrets into tests.

## 25. References

- [Spring Boot 3.3 — Actuator Endpoints, Exposure, Security and Sanitization](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)
- [Spring Boot 3.3 — Spring Security](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html)
- [Spring Boot 3.3 — Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)

## 26. Takeaways

Spring Boot Actuator serves observability, yet **not every endpoint is suitable for publication**. In Spring Boot 3.3, only `health` is exposed over HTTP/JMX by default; an endpoint being enabled does not mean it has a reachable URL.

Distinguish four layers: **enablement**, **exposure**, **authentication/authorization**, and **response disclosure**. `env`, `configprops`, and `quartz` mask values by default; `show-values=when-authorized` requires matching roles and does not replace HTTP security. `health.show-details` defaults to `never`; health checkers usually need only overall status.

Real-world policies should use allowlists instead of `include="*"`, restrict management ports/networks, protect Actuator with Spring Security, and ensure custom `SecurityFilterChain`s do not leave other APIs exposed. `heapdump`, `logfile`, `loggers`, and metric labels demand distinct controls because they can hold sensitive data or alter runtime behavior.

An endpoint should only be published when you have clear answers for **who needs it, what data they need to see, over which network path, with what permissions, and for how long**. Add negative security tests and periodically review exposure whenever profiles, dependencies, Spring Boot versions, or deployment topologies change.
