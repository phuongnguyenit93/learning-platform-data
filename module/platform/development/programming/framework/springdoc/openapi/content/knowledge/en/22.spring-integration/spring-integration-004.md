# Actuator and Choosing Whether to Expose Management Endpoints

Spring Boot Actuator provides operational endpoints for an application such as `health`, `metrics`, `info`, `loggers`, and `env`. These endpoints are useful for monitoring, orchestration, and troubleshooting, yet some endpoints can reveal configuration, topology, runtime information, or allow modifying system state. Therefore, separate decisions must be made for which endpoints are enabled, which are exposed over HTTP, who is allowed to access them, and whether they should be included in the OpenAPI documentation.

Springdoc can display Actuator endpoints in Swagger UI via `springdoc.show-actuator=true`. This option is for documentation purposes; it does not expose Actuator endpoints over the network on its own and does not replace Spring Boot security configuration. Decisions about publishing endpoints must be made consistently across Actuator exposure, Spring Security, management port configuration, and OpenAPI documentation.

## 1. What Does Actuator Provide?

Actuator adds management endpoints to a Spring Boot application. The library is typically added via the starter:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

For an application using Spring MVC and Swagger UI, you can use a Springdoc starter compatible with the project's Spring Boot version:

```xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>${springdoc.version}</version>
</dependency>
```

WebFlux applications use the corresponding WebFlux starter. Choose a Springdoc line compatible with the Spring Boot line in use; do not copy an arbitrary version from another example.

Some common Actuator endpoints:

| Endpoint ID | Purpose | Publishing notes |
| --- | --- | --- |
| `health` | Overall application status and health indicators | Can reveal database, broker, or dependency status if details are shown |
| `info` | Application-provided information such as build/version | Only include data allowed to be public in `info` |
| `metrics` | Runtime indicators and metrics recorded by Micrometer | Can reveal metric names, system structure, and load levels |
| `prometheus` | Metrics in Prometheus format when a suitable registry is present | Usually intended for internal monitoring systems |
| `loggers` | View or change logger levels | Write access can alter logging behavior while the application is running |
| `env` | Environment and configuration properties | Risks exposing sensitive values or deployment structure |
| `configprops` | Configuration properties bound to beans | Can reveal internal configuration and sensitive values if not properly masked |
| `beans` | List of beans in the ApplicationContext | Reveals internal application structure |
| `mappings` | Registered request mappings | Reveals routes and API surface |
| `threaddump` | Thread snapshot at query time | Can contain sensitive operational details and incur load |
| `heapdump` | Generates a heap dump for memory analysis | Can contain in-memory data; should not be broadly exposed |
| `shutdown` | Requests application shutdown when enabled | Directly impacts availability; this endpoint is disabled by default |

In current Spring Boot versions, only `health` is exposed over HTTP by default. Other endpoints may exist in the application without automatically appearing at the web management path. Access control settings and some defaults can change across versions; consult the documentation for the exact Spring Boot line in use.

## 2. Distinguishing Enabled, Exposed, and Authorized Endpoints

These three concepts are not the same:

1. **Enabled/available:** whether the endpoint is enabled and can be created in the application.
2. **Exposed:** whether the endpoint is made available over an access transport such as HTTP or JMX.
3. **Authorized:** whether the requester is permitted by Spring Security to access the endpoint.

For example, `env` may be enabled in the application while absent from the web exposure list. In that case, the endpoint does not appear at the HTTP management base path. Even if an endpoint is exposed over HTTP, Spring Security can still require an administrative role.

Similarly, adding `health` to `management.endpoints.web.exposure.include` does not mean all health details are public. `management.endpoint.health.show-details` and the authentication policy determine the level of detail returned.

Springdoc is also a separate layer: `springdoc.show-actuator` decides whether Actuator operations are included in the OpenAPI document. It does not replace the enabled/exposure steps and does not grant runtime access permissions.

## 3. Exposing Only Required Endpoints

Management endpoints usually have the default base path `/actuator`. You can expose only `health` and `info` over HTTP:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: when-authorized
      roles: OPS
```

In this example, `/actuator/health` and `/actuator/info` are exposed over HTTP. Health details are shown only to authenticated users with the `OPS` role. Overall health can be used by monitoring systems without exposing details of every dependency.

If metrics or Prometheus are needed for monitoring, add only the endpoints actually required:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
```

The `prometheus` endpoint requires a suitable registry dependency, such as `micrometer-registry-prometheus`. Adding an ID to `include` does not automatically install a registry or produce metrics if the application has not configured Micrometer accordingly.

You can exclude endpoints from the exposed list:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
        exclude: env,configprops,beans,shutdown,heapdump,threaddump
```

When using the `*` wildcard, wrap it in quotes so YAML does not treat it as a special symbol. `exclude` removes specific endpoints from the web exposure list, though a safer strategy is to include only the needed list.

## 4. Do Not Confuse Hiding an Endpoint with Disabling It

If an endpoint does not need to exist in the application, disable it via Spring Boot configuration. For example:

```yaml
management:
  endpoint:
    shutdown:
      enabled: false
```

If an endpoint should not be published over HTTP while still being needed for JMX or other administrative tools, keep the endpoint enabled and omit it from `management.endpoints.web.exposure.include`.

In Spring Boot versions supporting endpoint access control, endpoints can be restricted to access levels such as read-only or unrestricted using `management.endpoints.access.*` and `management.endpoint.<id>.access`. Exact syntax and support depend on the version; consult the Spring Boot documentation in use. Even with access control, still verify exposure and Spring Security.

Do not enable `shutdown` just for convenience in Swagger UI. An operational shutdown action can stop the application and requires its own controlled process.

## 5. Controlling Details of the Health Endpoint

Health is often the only endpoint broadly used by load balancers or orchestrators. However, returning full details to every caller can leak database names, message brokers, third-party service status, or internal details.

Example:

```yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      roles: OPS
```

Common options for `show-details` include:

| Value | Behavior |
| --- | --- |
| `never` | Do not show health details |
| `when-authorized` | Show details only to authenticated callers with an appropriate role |
| `always` | Always show details; use only when environment and policy permit |

In Kubernetes, health probes can be enabled to provide liveness and readiness:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
```

Liveness indicates whether the process needs to be restarted; readiness indicates whether the instance is ready to receive traffic. Do not include internal health details in public documentation if external clients have no corresponding operational need.

## 6. How Can Springdoc Include Actuator in OpenAPI?

By default, Springdoc does not display Actuator endpoints in OpenAPI documentation. When documenting them is desired, enable:

```yaml
springdoc:
  show-actuator: true
```

Springdoc adds a dedicated documentation group for Actuator endpoints. If the application does not yet have a separate API group, Springdoc can also create a default group for the application API. In Swagger UI, readers can select the Actuator group to view supported management operations.

This only controls whether endpoints appear in the documentation. To invoke an endpoint, Actuator must still be enabled and exposed over the corresponding transport; Spring Security, network policies, and the management server still determine who can access it.

For example, if `health` is exposed but `env` is not, enabling `springdoc.show-actuator=true` is not a reason to open `env` over HTTP. Inspect the generated Actuator group and compare it with endpoints that are actually reachable.

Do not enable `show-actuator` just to have a complete list of endpoints in Swagger UI. Determine whether documentation readers genuinely need to call management endpoints and whether that content is permitted to be disclosed to them.

## 7. When Should Actuator Be Included in OpenAPI Documentation?

| Scenario | Recommended decision | Reason |
| --- | --- | --- |
| Public API for customers | Usually exclude Actuator from public groups | Management endpoints are not part of the business contract for customers |
| Internal documentation for SRE/operations | Can create a separate Actuator group and protect by role | Operators need to inspect health, metrics, or perform authorized actions |
| Automated monitoring | Usually uses standard Actuator/Prometheus endpoints and formats | Monitoring does not need Swagger UI to scrape metrics periodically |
| Local/dev environments | Can be enabled for learning and debugging | Convenient for exploring endpoints in a controlled environment |
| Production with a dedicated management network | Publish documentation only on the management port if needed | Separates the management surface from the application port |

OpenAPI is generally suited to the API contract that clients integrate against. Actuator serves administration and operations. Both can be documented, but groups, target audiences, and access permissions should be clearly separated.

## 8. Separating Management Port from Application Port

Spring Boot allows serving Actuator on a dedicated management port:

```yaml
server:
  port: 8080

management:
  server:
    port: 9090
  endpoints:
    web:
      exposure:
        include: health,info,openapi,swagger-ui

springdoc:
  use-management-port: true
```

With Springdoc configuration supporting the Actuator management port, `openapi` and `swagger-ui` are Actuator endpoints registered by Springdoc to serve documentation on the management port. URLs typically look like:

```text
http://localhost:9090/actuator
http://localhost:9090/actuator/openapi
http://localhost:9090/actuator/swagger-ui
```

The management port must differ from the application port. When `springdoc.use-management-port=true`, ordinary Springdoc path customizations do not apply to endpoints exposed under the Actuator base path; use URLs under the configured management base path.

Only add `openapi` and `swagger-ui` to exposure when you genuinely want to serve documentation on the management port. If you want to expose `health` and `info` on the same port, add those IDs to the list. When using an explicit `include`, remember that endpoints omitted from the list will not be exposed over the web.

Separating ports does not create a complete security boundary on its own. Bind the management server to an appropriate interface, restrict access with firewalls, service networks, or internal ingress, and apply Spring Security. If the management port is published to the Internet, the benefits of port separation may be lost.

## 9. Combining `show-actuator` and Management Port

The two properties serve two distinct goals:

- `springdoc.show-actuator=true`: adds Actuator endpoints to the OpenAPI documentation, typically via a dedicated Actuator group.
- `springdoc.use-management-port=true`: serves OpenAPI/Swagger UI under the Actuator management port instead of the application port.

Both can be used together when the operations team wants to view Actuator documentation right on the management port:

```yaml
management:
  server:
    port: 9090
  endpoints:
    web:
      exposure:
        include: health,openapi,swagger-ui

springdoc:
  show-actuator: true
  use-management-port: true
```

In that setup, Swagger UI on the management port can provide the Actuator group. If `show-actuator` is enabled while `use-management-port` is not, Swagger UI continues to be served on the application port; the Actuator group is still added to the documentation. If Actuator endpoints reside on a different port, check CORS and access permissions for the actual paths.

When Swagger UI on the management port calls business endpoints on the application port, the two ports are two different origins under the browser's same-origin policy. If **Try it out** is needed, CORS must be configured on the application server for the Swagger UI origin, along with required methods/headers. CORS does not replace authentication.

## 10. Protecting Actuator with Spring Security

Exposure is not authentication. If `env` is exposed over HTTP, unauthorized callers can still invoke the endpoint unless Spring Security or the network layer blocks them.

Spring Security 6 example protecting management endpoints:

```java
package com.example.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/actuator/health").permitAll()
            .requestMatchers("/actuator/**").hasRole("OPS")
            .anyRequest().authenticated()
        );

        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
```

The example above uses the default path `/actuator`. If the application changes `management.endpoints.web.base-path`, you can use the dedicated `EndpointRequest` matcher to avoid depending on path strings:

```java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(EndpointRequest.to("health")).permitAll()
    .requestMatchers(EndpointRequest.toAnyEndpoint()).hasRole("OPS")
    .anyRequest().authenticated()
);
```

This matcher API is for servlet/Spring MVC applications. For WebFlux, use `SecurityWebFilterChain` and the corresponding reactive matchers. When declaring a custom `SecurityFilterChain`, Spring Boot backs off its automatic Actuator security configuration so the application assumes responsibility for all rules; verify you do not accidentally leave management endpoints open.

In the example, overall health can be probed without logging in; remaining Actuator endpoints require the `ROLE_OPS` authority. If health details also need protection, configure `show-details: when-authorized` and an appropriate role.

If Springdoc serves Swagger UI/OpenAPI on the management port, verify which security chain applies to the management context and URLs under `/actuator/openapi` and `/actuator/swagger-ui`. Do not assume the application port's matcher automatically protects a separately configured management context. With multiple `SecurityFilterChain` beans, check `securityMatcher`, `@Order`, and the actual matchers for each port.

For production environments, consider using an OAuth2 Resource Server or an internal SSO mechanism instead of HTTP Basic. Never embed administrative passwords or tokens into a committed `application.yml`.

## 11. Keeping Business Documentation Separate from Management Documentation

If an application has multiple documentation groups, establish clear boundaries:

```java
@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
        .group("public")
        .pathsToMatch("/api/**")
        .build();
}
```

The Actuator group created by `springdoc.show-actuator=true` is managed separately by Springdoc. Avoid accidentally adding `/actuator/**` paths to the public group via `pathsToMatch("/**")` if the goal is to keep management endpoints separated.

If consolidated internal documentation is needed, create a dedicated group and also protect that group's OpenAPI URL. However, OpenAPI groups only categorize content; they do not replace web exposure or Spring Security. An endpoint hidden from documentation can still be invoked if runtime exposes and permits access to it.

## 12. Verifying Actuator and OpenAPI Configuration

After starting the application, verify the URLs matching your configuration:

```bash
# Health
curl -i http://localhost:8080/actuator/health

# Info
curl -i http://localhost:8080/actuator/info

# Actuator endpoint discovery
curl -i http://localhost:8080/actuator

# OpenAPI document of the application
curl -i http://localhost:8080/v3/api-docs
```

If using a management port and `springdoc.use-management-port=true`:

```bash
curl -i http://localhost:9090/actuator
curl -i http://localhost:9090/actuator/openapi
curl -i http://localhost:9090/actuator/swagger-ui
```

Check against these questions:

1. Is the endpoint enabled and available in the application?
2. Is the endpoint exposed over HTTP?
3. What status code does an unauthenticated request receive?
4. Can a user with the operations role access it?
5. Are health details leaked to unauthorized users?
6. Does `springdoc.show-actuator` create the Actuator group as expected?
7. Are Swagger UI and the OpenAPI document served on the expected port?
8. Does the public group accidentally include management endpoints?

If an endpoint returns `404`, check the endpoint ID and web exposure. If it returns `401` or `403`, check Spring Security and roles. If the endpoint works but does not appear in Swagger UI, check `springdoc.show-actuator`, the Springdoc version, and document groups. If Swagger UI loads but cannot call APIs on another port, check CORS and authentication.

## 13. Common Mistakes

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| Actuator dependency present but `/actuator/metrics` returns `404` | Endpoint not exposed over web or missing suitable registry | Check `management.endpoints.web.exposure.include` and metrics dependencies |
| `env` listed in OpenAPI but cannot be called | Documentation describes operation while Actuator does not expose endpoint | Check enabled/exposure and Security independently |
| `/actuator/env` accessible without login | Endpoint exposed without authorization rule | Protect with Spring Security and restrict network access |
| `health` leaks database or broker info | `show-details: always` or overly broad role | Use `when-authorized`, restrict roles, and expose only overall status publicly |
| `springdoc.show-actuator` enabled but group missing | Incompatible Springdoc version/config or Actuator not detected | Check starter and version, Actuator endpoints, and OpenAPI output |
| Swagger UI still on application port | Only `show-actuator` enabled, `use-management-port` not enabled | Enable `springdoc.use-management-port` and configure a distinct management port |
| `/actuator/openapi` or `/actuator/swagger-ui` returns `404` | Actuator endpoints `openapi`/`swagger-ui` not exposed | Add both IDs to `management.endpoints.web.exposure.include` |
| Swagger UI on management port cannot call API | CORS between management port and application port not configured | Allow the UI origin on the target application endpoints |
| Endpoint still callable despite being hidden in Swagger UI | Confusing documentation with runtime exposure/security | Verify web exposure and authorization directly |
| Swagger UI disabled but Actuator still works | Both endpoint groups have independent configurations | Configure `springdoc` and `management` separately as intended |

## 14. Checklist for Deciding Whether to Expose Actuator

- [ ] Identified which endpoints serve health, monitoring, and operations.
- [ ] Only genuinely required HTTP endpoints are exposed.
- [ ] Sensitive endpoints such as `env`, `configprops`, `beans`, `mappings`, `heapdump`, `threaddump`, `loggers`, and `shutdown` have been reviewed individually.
- [ ] Distinguished between enabled, exposed, and authorized.
- [ ] Health details are not shown more broadly than operational needs require.
- [ ] Decided whether `springdoc.show-actuator=true` is needed.
- [ ] If Actuator documentation is published, separated its group and target audience from the public API.
- [ ] If using a management port, the port differs from the application port and exposure includes `openapi` and `swagger-ui` when needed.
- [ ] Management port is reachable only from allowed networks/interfaces.
- [ ] Spring Security protects management endpoints with appropriate roles/authorities.
- [ ] Tested both direct requests and OpenAPI/Swagger UI documentation.
- [ ] Verified CORS if the UI on the management port calls APIs on the application port.
- [ ] Do not rely on hiding endpoints in Swagger UI to protect runtime.

Actuator is the management and operational surface of the application. Choose which endpoints to enable, restrict which are exposed, protect requests with Spring Security, and include them in OpenAPI only when the target audience needs them. `springdoc.show-actuator` helps document management endpoints; `springdoc.use-management-port` helps serve documentation on a separate management port. These two options organize documentation, while actual access permissions must still be decided at Actuator, security, and network infrastructure layers.

## References

- [Spring Boot Reference — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Springdoc OpenAPI v2 — Actuator support](https://springdoc.org/v2/modules.html)
- [Springdoc OpenAPI v2 — Configuration properties](https://springdoc.org/v2/core-properties.html)
