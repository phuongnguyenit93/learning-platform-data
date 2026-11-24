# Restricting Access When Using Actuator Diagnostic Information

## 1. Goal and Context

Spring Boot Actuator provides endpoints to observe and manage a running application. They are invaluable for investigating errors, monitoring health, inspecting bound configuration, checking auto-configuration conditions, metrics, thread dumps, or logs. However, diagnostic data can also expose **internal structure, deployment details, sensitive configuration, request traces, and operational state**.

For example:

- `/actuator/health` may return only `UP`, or it may expose database, Redis, broker, host, and per-component status if details are enabled.
- `/actuator/env` displays property sources and environment values; `/actuator/configprops` displays data bound into `@ConfigurationProperties`.
- `/actuator/beans`, `conditions`, and `mappings` can reveal bean names, configurations, and application routes.
- `/actuator/heapdump` can contain in-memory data such as tokens, sessions, or business payloads.
- `/actuator/logfile` can return logs containing personal data, headers, internal errors, or accidentally logged data.
- `/actuator/loggers` can modify log levels; `/actuator/shutdown` can stop the application when enabled.

**Lesson goal:** design access permissions according to data sensitivity, limit exposed endpoints, authenticate and authorize callers, preserve sanitization, and place the management server on an appropriate network. The lesson uses **Spring Boot 3.3.x, Java 17+, and Spring Security 6.3** as its baseline.

One principle to remember: **whether an endpoint is enabled, whether it is exposed, whether a caller is authorized, and whether returned values are sanitized are four separate decisions**. Doing only one of the four is not enough to protect diagnostic information.

## 2. What Can Actuator Expose?

| Endpoint | Operational Value | Risk If Unauthorized Parties Access It |
| --- | --- | --- |
| `health` | Overall status and readiness/availability | Details can leak dependency names, database/cache/broker states, or hostnames |
| `info` | Build, git, and application-supplied metadata | Can expose versions, commits, branches, environment info, or custom content |
| `env` | Property sources and environment settings | Can expose property names, config sources, URLs, hostnames, and sensitive values if unmasked |
| `configprops` | Values of `@ConfigurationProperties` beans | Can expose datasource, client, credential, or topology settings |
| `conditions` | Reasons auto-configurations were selected/skipped | Exposes classpath, configurations, and internal components |
| `beans` | List of beans in the context | Exposes architecture, class names, dependencies, and modules |
| `mappings` | HTTP request mappings | Exposes API paths, controllers, and endpoint structure |
| `metrics` / `prometheus` | Operational metrics | Metric names, tags, tenant identifiers, or labels can leak sensitive data if misdesigned |
| `httpexchanges` | Recent request/response traces | Can expose URIs, statuses, principals, or headers depending on repository and configuration |
| `threaddump` | Thread states, stack traces | Exposes class names, execution paths, resources, and runtime details |
| `logfile` | Log file contents | Can expose tokens, personal data, SQL, exceptions, or internal details |
| `heapdump` | JVM memory snapshot | Can contain application data and secrets in analyzable form |
| `loggers` | View and change log levels | Can alter logging behavior, increase sensitive output, or impact performance |
| `shutdown` | Controlled application shutdown | Administrative operation with direct impact on availability |

Not every endpoint has the same sensitivity level. Nor should `health` or `info` be assumed harmless by default: specific output depends on the application's health contributors and info contributors. Inspect actual responses in a test environment before opening endpoints.

## 3. Four Independent Control Layers

### 3.1. Enable: Is the Endpoint Registered?

In Spring Boot 3.3, most endpoints are enabled by default, except `shutdown` which is disabled by default. You can control this with:

```yaml
management:
  endpoints:
    enabled-by-default: false
  endpoint:
    health:
      enabled: true
    info:
      enabled: true
```

When using `management.endpoints.enabled-by-default=false`, explicitly enable only the endpoints you need with `management.endpoint.<id>.enabled=true`. Disabled endpoints are omitted from the ApplicationContext. This *opt-in* policy is useful when systems require restricting administrative capabilities.

### 3.2. Expose: Is the Endpoint Published Over HTTP or JMX?

An enabled endpoint may still not be exposed over a specific transport. Spring Boot 3.3 exposes only `health` over HTTP and JMX by default. Use:

- `management.endpoints.web.exposure.include` to select HTTP endpoints.
- `management.endpoints.web.exposure.exclude` to exclude HTTP endpoints.
- `management.endpoints.jmx.exposure.include` and `exclude` for JMX.

Example exposing only health and info:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info"
```

If an endpoint appears in both include and exclude, **exclude takes precedence**. When you need to expose an additional endpoint, add only the specific ID needed; do not open everything just for debugging convenience.

Do not use the broad configuration below as a production default:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
```

The `*` in YAML should be quoted. Even if broad exposure is genuinely needed in an isolated diagnostic environment, you must still establish network boundaries, authentication, authorization, and review each endpoint's payload.

### 3.3. Authenticate and Authorize: Who Is Allowed to Call?

- **Authentication** verifies the caller's identity.
- **Authorization** determines whether that caller has permission to access a specific endpoint/operation.

Merely exposing an endpoint does not create authentication. Without Spring Security or another protection layer, exposed endpoints can be accessed according to the current network configuration.

When Spring Security is on the classpath and there is no custom `SecurityFilterChain` bean, Spring Boot's auto-configuration protects actuators other than `/health`. If the application declares its own `SecurityFilterChain`, the default security auto-configuration backs off in favor of the application's configuration. This is a common source of mistakes: a custom filter chain that does not match endpoints properly can inadvertently leave actuator or business routes unprotected.

### 3.4. Sanitize: Should Authorized Callers See Raw Values?

Someone permitted to call `/actuator/env` should not necessarily see every configuration value. For `env`, `configprops`, and `quartz`, Spring Boot 3.3 **sanitizes all values** to `******` by default. If raw values need to be shown, these endpoints support `show-values`:

| Value | Behavior |
| --- | --- |
| `never` | Always masks values; this is the default |
| `when-authorized` | Only shows values to authenticated users possessing a role required by the endpoint |
| `always` | Shows values to everyone able to call the endpoint, unless a `SanitizingFunction` still applies |

For HTTP, a user is considered authorized when authenticated and holding one of the roles configured on the endpoint. If no roles are configured, **every authenticated user** is considered authorized by default. For JMX, Spring Boot treats all users as authorized for this sanitization check. Therefore, do not assume `show-values` `roles` restrict JMX in the same way as HTTP.

A custom `SanitizingFunction` still applies even when `show-values=always` or `when-authorized`. Keep `never` unless there is a genuine diagnostic need for raw values.

## 4. Sample Configuration for Environments with an Operations Team

The example below exposes only health and info over HTTP; health details are shown only to the operations role:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info"
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
      roles: ACTUATOR_ADMIN
```

If configuration diagnostics are needed for a limited time, you can add `env` and `configprops` with a value-visibility policy:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,env,configprops"
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
      roles: ACTUATOR_ADMIN
    env:
      show-values: when-authorized
      roles: ACTUATOR_ADMIN
    configprops:
      show-values: when-authorized
      roles: ACTUATOR_ADMIN
```

`show-values=when-authorized` does not replace endpoint authorization. It only controls whether sensitive values appear in the response. Users without endpoint access must still be blocked by Spring Security; authenticated users lacking the operations role only receive sanitized output if they are permitted to call the endpoint by the corresponding HTTP policy.

For a demo Basic Auth account, you can use this configuration:

```yaml
spring:
  security:
    user:
      name: actuator-admin
      password: ${ACTUATOR_ADMIN_PASSWORD}
      roles: ACTUATOR_ADMIN
```

`ACTUATOR_ADMIN_PASSWORD` must be supplied from a secret manager or deployment platform environment variable; never commit real passwords to Git, Docker images, sample configuration files, or logs. This is an example for a simple environment. In multi-user production, use an identity provider/OAuth2 Resource Server, LDAP, or centralized authentication system to grant identity-based roles and audit administrative actions.

## 5. Protecting HTTP Actuator with Spring Security

### 5.1. Using `EndpointRequest` Instead of Hard-Coding URLs

Spring Boot 3.3 provides `org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest` to build `RequestMatcher`s based on actual endpoints. For example:

- `EndpointRequest.to("health")` matches the health endpoint and its subpaths.
- `EndpointRequest.toAnyEndpoint()` matches actuator web endpoints.

The advantage is that matchers continue to work when `management.endpoints.web.base-path` or path mappings change, as long as the endpoints are configured through Actuator. Do not rely on the default URL always being `/actuator/**`.

### 5.2. One SecurityFilterChain Covering the Whole Application

The example below permits unauthenticated access to health; remaining actuators require role `ACTUATOR_ADMIN`; other business routes require authentication. This setup uses **one filter chain covering all HTTP requests**, so no path outside the actuator matchers slips through.

Save file `src/main/java/example/security/ActuatorSecurityConfiguration.java`:

```java
package example.security;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class ActuatorSecurityConfiguration {

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to("health")).permitAll()
                .requestMatchers(EndpointRequest.toAnyEndpoint())
                    .hasRole("ACTUATOR_ADMIN")
                .anyRequest().authenticated()
        );

        http.httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

Key points to understand:

1. `health` is publicly accessible at the HTTP authorization layer; health detail verbosity is still governed by `management.endpoint.health.show-details` and `roles`.
2. `toAnyEndpoint()` follows the health matcher, so all other actuators require the `ACTUATOR_ADMIN` role.
3. `anyRequest().authenticated()` protects the rest of the application.
4. `httpBasic` is a simple authentication example; production should use HTTPS and appropriate identity mechanisms rather than sending Basic credentials over unencrypted HTTP.

### 5.3. Warning When Separating a Filter Chain for Actuator

You can scope a filter chain solely to actuators using:

```java
http.securityMatcher(EndpointRequest.toAnyEndpoint());
```

However, once a custom `SecurityFilterChain` is declared, Spring Boot's security auto-configuration backs off. If that chain only matches actuators, you **must provide another `SecurityFilterChain`** handling the remaining application requests, with clearly designed `@Order` and matchers. Without a second chain, non-actuator routes may not pass through the rules you thought were protecting them.

This is a common misconfiguration when copying an actuator security snippet and forgetting security for the application itself.

## 6. Separating the Management Server and Restricting Networks

By default, Actuator HTTP typically shares the same port as the application. When needed, you can use a dedicated management port:

```yaml
management:
  server:
    port: 8081
    address: 127.0.0.1
```

In Spring Boot 3.3, you can change the port with `management.server.port` and the bind address with `management.server.address`. A separate address is only used when the management port differs from the main port. `127.0.0.1` makes the management server accept only loopback connections on that host/container; this works when a monitoring agent runs in the same network namespace, but not if a monitoring system on another machine needs to call it directly.

In infrastructure with external monitoring agents, bind to an appropriate internal interface, then use firewalls, Kubernetes NetworkPolicy, security groups, or a service mesh so only trusted sources can connect. A separate port **does not automatically create authentication** and does not replace role authorization.

If the management server uses a separate port, you can configure separate TLS via `management.server.ssl.*`. Ensure credentials and diagnostic responses are encrypted in transit. Changing `management.endpoints.web.base-path` from `/actuator` to `/manage` or an obscure path only changes the URL—**it is not a security measure**.

If the application does not need HTTP Actuator endpoints, you can disable HTTP endpoints completely:

```yaml
management:
  server:
    port: -1
```

JMX has its own exposure policy; disabling HTTP does not automatically disable all other management channels. Review `management.endpoints.jmx.exposure.*` and JMX connector/network settings as well.

## 7. Endpoints Requiring Special Governance

### 7.1. `env` and `configprops`

Both endpoints can return property names, property sources, and bound values. Sensitive values are masked by default, yet key names, source names, prefixes, or configuration structure can still help an observer infer internal architecture.

- Do not enable `show-values=always` in public environments.
- If raw values are genuinely required, use `when-authorized` and a dedicated operations role.
- Keep custom `SanitizingFunction` beans if your organization has redaction rules.
- Expose over HTTP only when needed; consider excluding from JMX if no equivalent JMX policy exists.
- Never paste full responses into public tickets/logs, as this can leak sensitive metadata.

### 7.2. `health`

`management.endpoint.health.show-details` and `show-components` default to `never`. You can use `when-authorized` with `management.endpoint.health.roles` so only the operations role sees details. Review your application's custom `HealthIndicator` implementations: detail entries you return yourself must also be vetted. Never put passwords, tokens, connection strings, or customer data into `Health.details`.

For Kubernetes, distinguish liveness from readiness. Liveness should indicate whether the application needs a restart; it should not depend on every external service, since a database outage could make Kubernetes restart pods en masse and cause a cascading failure. Readiness can check essential dependencies according to application policy. Probes do not need health details exposed to all callers just to receive status.

### 7.3. `conditions`, `beans`, `mappings`, and `threaddump`

These endpoints are very helpful when developers investigate startup or wiring issues, yet they can reveal the classpath, bean graph, internal URLs, controller mappings, and stack traces. Restrict them to responsible engineering staff, and enable them only during required deployment windows if there is no continuous operational need.

### 7.4. `logfile` and `heapdump`

These are high-risk data sources:

- Logs may contain request payloads, emails, identifiers, SQL, or tokens if the application logs improperly.
- Heap dumps can hold live objects containing credentials, sessions, request bodies, or business data in memory.
- Downloading large files can consume bandwidth, memory, and disk space, affecting application stability.

Never expose these endpoints to the internet. When collection is needed for an investigation, grant very narrow permissions, use encrypted transport, store with strict access controls, enforce short retention, and delete artifacts once finished.

### 7.5. `loggers` and `shutdown`

`loggers` supports changing log levels; `shutdown` can stop the application. `shutdown` is disabled by default in Spring Boot 3.3 and must be explicitly enabled if truly needed. Do not add `shutdown` to exposure just for a convenient restart API. Prefer your orchestration platform or audited deployment workflows.

Actuator write operations typically use HTTP POST, PUT, or DELETE. Spring Security enables CSRF protection by default; thus `shutdown` or `loggers` can return `403` without a valid CSRF token. Do not disable CSRF globally just to make an administrative operation work. Only consider a dedicated CSRF policy for non-browser client-to-service callers after locking down authentication, network, and operations.

## 8. CORS Is Not Authentication

CORS controls whether a browser allows JavaScript from another origin to read responses; it **does not authenticate callers** and does not block clients such as curl, scripts, service-to-service calls, or other network tools. An Actuator endpoint can still be accessed even if browsers are blocked by CORS.

Spring Boot 3.3 disables CORS for Actuator by default; CORS only activates when `management.endpoints.web.cors.allowed-origins` is configured. Only configure CORS for an operations frontend that genuinely needs access; do not use `allowed-origins=*` or treat CORS as a replacement for Spring Security and network ACLs.

## 9. Testing Access Permissions with MockMvc

A security rule should have tests for at least three states: anonymous, a user with the right role, and an authenticated user without the role. The test below uses Spring Security Test to simulate identities without hard-coding passwords.

### 9.1. Required Dependencies

In Maven, the test project needs dependencies whose versions are managed by the Spring Boot BOM/parent:

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
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

### 9.2. Complete Test File

Create `src/test/java/example/security/ActuatorSecurityTests.java`:

```java
package example.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
    classes = ActuatorSecurityTests.TestApplication.class,
    properties = {
        "management.endpoints.web.exposure.include=health,info",
        "management.endpoint.health.show-details=never"
    }
)
@AutoConfigureMockMvc
class ActuatorSecurityTests {

    @Autowired
    MockMvc mockMvc;

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import(SecurityConfiguration.class)
    static class TestApplication {}

    @Configuration(proxyBeanMethods = false)
    static class SecurityConfiguration {

        @Bean
        SecurityFilterChain applicationSecurity(HttpSecurity http)
                throws Exception {
            http.authorizeHttpRequests(authorize -> authorize
                    .requestMatchers(EndpointRequest.to("health"))
                        .permitAll()
                    .requestMatchers(EndpointRequest.toAnyEndpoint())
                        .hasRole("ACTUATOR_ADMIN")
                    .anyRequest().authenticated()
            );
            http.httpBasic(Customizer.withDefaults());
            return http.build();
        }
    }

    @Test
    void healthIsPublic() throws Exception {
        mockMvc.perform(get("/actuator/health"))
                .andExpect(status().isOk());
    }

    @Test
    void infoRejectsAnonymousUser() throws Exception {
        mockMvc.perform(get("/actuator/info"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void infoAllowsActuatorAdmin() throws Exception {
        mockMvc.perform(get("/actuator/info")
                        .with(user("ops").roles("ACTUATOR_ADMIN")))
                .andExpect(status().isOk());
    }

    @Test
    void infoRejectsAuthenticatedUserWithoutRole() throws Exception {
        mockMvc.perform(get("/actuator/info")
                        .with(user("reader").roles("USER")))
                .andExpect(status().isForbidden());
    }
}
```

### 9.3. Running the Tests and Reading Results

With Gradle wrapper:

```bash
./gradlew test --tests example.security.ActuatorSecurityTests
```

With Maven wrapper:

```bash
./mvnw -Dtest=ActuatorSecurityTests test
```

Expected result is **4 tests PASS**:

| Request | Identity | Expected HTTP Outcome | Meaning |
| --- | --- | --- | --- |
| `GET /actuator/health` | Anonymous | `200` | Health status is public |
| `GET /actuator/info` | Anonymous | `401` | Unauthenticated |
| `GET /actuator/info` | Role `ACTUATOR_ADMIN` | `200` | Authenticated and authorized |
| `GET /actuator/info` | Role `USER` | `403` | Authenticated but lacks permission |

`SecurityMockMvcRequestPostProcessors.user` attaches a mock principal to the request to test authorization. It **does not** test real Basic Auth protocol handling, TLS, reverse proxies, network policies, or secret managers. Those parts require separate integration/deployment tests. When changing `management.endpoints.web.base-path`, add tests verifying endpoint matchers still apply properly.

## 10. Review Checklist Before Opening Diagnostic Information

1. **List operational needs:** does monitoring only need health, or also info, metrics, env, configprops, thread dumps? Document the consumer of each endpoint.
2. **Classify data:** which endpoints only return status, which return metadata, and which can return in-memory/log data.
3. **Disable by default and opt in if appropriate:** use `management.endpoints.enabled-by-default=false` and enable each needed endpoint; if keeping default-enabled, still use an exposure allow-list.
4. **Expose only over needed transports:** HTTP/JMX have separate include/exclude settings. Review both; do not extrapolate from HTTP to JMX.
5. **Configure roles by function:** someone who only checks health should not have permission to read env or download heap dumps. Separate read-only, operator, and incident responder roles when systems have distinct operational duties.
6. **Preserve sanitization:** `show-values=never` is the safe default; switch to `when-authorized` only for specific operational cases, paired with dedicated endpoint roles.
7. **Place the management server on a trusted network:** port, address, firewall/security group/network policy, and TLS must fit the architecture.
8. **Test 401, 403, and 200:** check anonymous, wrong role, and right role; also test custom base paths and write operations if enabled.
9. **Inspect actual responses:** check health details, env/configprops, info contributors, logs, metric tags, and custom health indicators. Never put real sensitive data into screenshots, issues, or public docs.
10. **Monitor changes:** when adding dependencies/starters or custom endpoints, re-review exposure, security matchers, sanitizers, and network paths. New endpoints must never automatically become public data.

## 11. Common Mistakes and Fixes

- **Configuring exposure only and assuming the endpoint is secure.** Exposure only decides whether an endpoint is published on a transport; you must have authentication/authorization and network boundaries.
- **Using `include: "*"` for debugging and forgetting to narrow it.** Switch back to a needs-based allow-list; `exclude` takes precedence, yet you should not rely on a long blocklist when a short allow-list suffices.
- **Enabling `show-values=always` in production.** Use `never` or `when-authorized` with specific roles; review JMX and `SanitizingFunction` as well.
- **Omitting `roles` when using `show-values=when-authorized`.** By default any authenticated user is treated as authorized; configure roles if only the operations group should view values.
- **Creating a custom SecurityFilterChain only for actuators and forgetting the application chain.** Spring Boot's security auto-configuration backs off; if the chain only matches actuators, add a second chain for the rest.
- **Hard-coding `/actuator/**` in SecurityMatcher.** Use `EndpointRequest` to stay compatible with custom base paths and path mappings.
- **Opening health details to everyone.** Keep `show-details=never` or use `when-authorized` with roles; audit data added by custom HealthIndicators.
- **Renaming the path to “hide” an endpoint.** An obscure path does not replace authentication or authorization.
- **Treating CORS as an access control mechanism.** CORS primarily applies to browsers; other API clients can still call endpoints if network/security allows.
- **Disabling CSRF application-wide to call Actuator POST endpoints.** Evaluate CSRF tokens or dedicated policies for non-browser clients; never disable globally just to bypass a 403.
- **Exposing heapdump or logfile like ordinary monitoring endpoints.** These artifacts can hold highly sensitive data; grant tightly scoped investigation access under formal procedures.
- **Setting a separate management port yet opening the same public ingress.** A separate port is not network isolation; configure firewalls/network policies and test external reachability.
- **Securing HTTP while forgetting JMX.** Exclude sensitive endpoints from JMX if unused; remember that `WHEN_AUTHORIZED` treats JMX users as authorized in Boot's sanitization mechanism.
- **Failing to audit data returned by custom endpoints.** Custom `@Endpoint` and `@ReadOperation` methods can expose objects directly; review output like a public API and avoid returning raw secrets or full configuration objects.

## 12. Self-Check Questions

1. In Spring Boot 3.3, which endpoint is exposed over HTTP by default? **`health`.** Other endpoints do not appear over HTTP merely because they are enabled.
2. Does `management.endpoints.web.exposure.include=health,env` automatically authenticate callers? **No.** It only exposes endpoints; Spring Security or another control layer is required.
3. With `show-values=when-authorized` and no `roles` set on the endpoint, who can view values? **Any authenticated HTTP user**, by default under this mechanism.
4. How does `show-values=when-authorized` apply to JMX? **JMX users are treated as authorized** for sanitization decisions; JMX must be governed separately.
5. You have a custom `SecurityFilterChain` matching only `EndpointRequest.toAnyEndpoint()`. What must you remember? **Spring Boot's security auto-configuration backs off; you must have another chain protecting application requests.**
6. Does changing `management.endpoints.web.base-path` replace authentication? **No.** It only changes the path.
7. Should `/actuator/heapdump` be public if used only for debugging? **No.** Heap dumps can contain sensitive in-memory data.
8. What can cause a `403` on POST `/actuator/loggers`? **Default CSRF protection** if the request lacks a valid token; do not disable CSRF globally without reviewing the client model.
9. You opened a separate management port 8081; can you drop Spring Security? **No.** You need appropriate network ACLs, authentication, and authorization; a separate port is only part of network segmentation.
10. You want monitoring to receive `UP` status without seeing database hostnames or dependency details; which setting fits? **Set health details/components to `never` or `when-authorized` with a dedicated role**, and review custom HealthIndicators.

## 13. Official References

- [Spring Boot 3.3 — Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html): enable/disable, HTTP/JMX exposure, Spring Security, CSRF, sanitization, and health details.
- [Spring Boot 3.3 — Monitoring and Management Over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html): base path, management port, management address, separate SSL, and disabling HTTP endpoints.
- [Spring Boot 3.3 — EndpointRequest API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/security/servlet/EndpointRequest.html): matchers for actuator endpoints in Spring Security.
- [Spring Boot 3.3 — Actuator REST API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/index.html): endpoint paths and HTTP contracts.
- [Spring Boot 3.3 — Spring Security](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html): security auto-configuration and behavior when declaring custom filter chains.
