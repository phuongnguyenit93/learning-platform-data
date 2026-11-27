# Management Endpoint Returns 404, 401, or 403

The management endpoints of a Spring Cloud application are typically provided through Spring Boot Actuator. Spring Cloud adds several dedicated endpoints, such as `refresh` from Spring Cloud Context, yet HTTP mapping, endpoint exposure, and access control still depend on Spring Boot's management configuration and Spring Security. Consequently, the same URL can return `404 Not Found`, `401 Unauthorized`, or `403 Forbidden` depending on whether the endpoint exists, is exposed, and whether the request clears all security layers.

When troubleshooting, verify whether the request reaches the exact process, port, and path before changing access permissions. Do not open all Actuator endpoints or switch endpoints to `permitAll` just to make an error disappear.

## 1. Understanding the Layers Behind a Management Endpoint

In web applications, Spring Boot Actuator normally maps an endpoint ID to an HTTP path prefixed with `/actuator`. For example, the `health` endpoint ID defaults to `/actuator/health`. An endpoint can be called over HTTP only when it is both enabled/available and exposed over HTTP. These two conditions are independent: an endpoint can exist in the ApplicationContext yet not be exposed, or have access restricted at the Actuator level.

Spring Cloud Context adds management operations such as `refresh`. This endpoint refreshes `@RefreshScope` beans; it is not a default endpoint in every Spring Boot application. The application must include the appropriate Spring Cloud Context dependency and expose the `refresh` endpoint via Actuator. If using Spring Cloud Bus, `busrefresh` is a separate endpoint intended to broadcast refresh operations to instances via the Bus.

A request to a management endpoint typically passes through these layers:

1. DNS, load balancer, ingress, or API gateway routes the request to the right application and port.
2. The management server resolves the context path, management base path, and endpoint ID.
3. Actuator checks whether the endpoint is initialized, permitted, and exposed over HTTP.
4. Spring Security authenticates identity, verifies roles/authorities, and checks protections such as CSRF.
5. The endpoint validates the HTTP method and executes the corresponding operation.

An upstream layer can return an error before the request ever reaches downstream layers. For instance, a gateway may return `404` because no route matched; Spring Security may return `401` due to missing credentials; CSRF protection may reject a `POST` request with `403`.

## 2. Distinguishing 404, 401, and 403

| HTTP Code | Common Meaning | Cause Categories to Check |
|---|---|---|
| `404 Not Found` | Route or endpoint not found at the requested URL | Wrong host/port/path, endpoint absent from classpath, endpoint not exposed, endpoint disabled, or hidden by gateway |
| `401 Unauthorized` | Request is unauthenticated or credentials are invalid | Missing Basic credentials, bearer token, cookie, or expired/wrong issuer/audience token |
| `403 Forbidden` | Request was authenticated yet is not permitted to perform the action | Missing role/authority, wrong rule in `SecurityFilterChain`, missing/invalid CSRF token, or restricted Actuator access |
| `405 Method Not Allowed` | URL exists yet the HTTP method is unsupported by the endpoint | Calling `GET` instead of `POST`, or vice versa; check `Allow` header and endpoint docs |

This is an initial interpretation, not an absolute rule. An application may customize `AuthenticationEntryPoint`, `AccessDeniedHandler`, gateways, or reverse proxies to alter status codes—even returning `404` to conceal a resource's existence. Inspect response headers, bodies, and logs at each layer to pinpoint where the error originates.

## 3. Resolving 404: Endpoint or Path Not Published

### 3.1. Confirm Dependencies and Endpoint ID

Check runtime dependencies before checking URLs. The application needs Spring Boot Actuator to provide the HTTP management surface. For Spring Cloud endpoints, the corresponding Spring Cloud module must be on the runtime classpath. For example, `refresh` belongs to Spring Cloud Context; an application with only Spring Boot Actuator does not automatically include it.

If dependencies are present, confirm the endpoint is created under the current configuration. Some endpoints depend on application type, beans, or other libraries. For instance, `prometheus` requires a Prometheus registry; other integrated endpoints have similar conditions. Do not infer an endpoint exists merely because `spring-boot-starter-actuator` is present.

### 3.2. Check Exposure Configuration

Spring Boot exposes only the `health` endpoint over HTTP by default. Therefore, calling `/actuator/info`, `/actuator/metrics`, or `/actuator/refresh` may return `404` unless added to the exposure list.

For example, the configuration below exposes three endpoints for internal use:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,refresh"
```

`include` takes endpoint IDs, not full URLs. To expose the Spring Cloud Bus endpoint, add the `busrefresh` ID and confirm Bus dependencies/configuration are present. When `exclude` is also configured, `exclude` takes precedence over `include`; an endpoint may still be absent even if listed in `include`.

Do not use `include: "*"` as a default fix. Endpoints such as `env`, `configprops`, `beans`, `loggers`, `heapdump`, or `shutdown` can leak sensitive data or allow mutating application state. Expose only genuinely required endpoints and protect them via a management network and proper authentication.

### 3.3. Check Endpoint Access Permissions in Actuator

Exposure and endpoint access control are two separate settings. On Spring Boot versions supporting endpoint access properties, `management.endpoints.access.default`, `management.endpoint.<id>.access`, and `management.endpoints.access.max-permitted` can restrict access. For example, setting default access to `none` disables endpoints lacking explicit grants; an endpoint restricted at this level can be excluded from the ApplicationContext.

```yaml
management:
  endpoints:
    access:
      default: none
  endpoint:
    health:
      access: read-only
    refresh:
      access: unrestricted
```

This is an opt-in configuration example: only endpoints granted explicit access are available. `refresh` is a write operation, so `read-only` is unsuitable if the goal is invoking refresh. Also check `max-permitted`, because this global ceiling can block broader access configured on an individual endpoint. On older Spring Boot versions, check documentation for your running version before using these properties.

### 3.4. Verify Actual Port and Path

The default `/actuator/{id}` path can be altered by several settings:

- `management.endpoints.web.base-path` changes the prefix, e.g., `/manage`.
- `server.servlet.context-path` prepends a prefix for Spring MVC apps when the management server shares the port.
- `spring.webflux.base-path` affects WebFlux apps when the management server shares the port.
- `management.server.port` runs the management server on a separate port.
- `management.server.address` restricts the listening address; when bound only to loopback, external machines cannot connect directly.
- `management.endpoints.web.path-mapping` remaps the path of a specific endpoint.

For example, if the management server runs on port `8081` with base path `/manage`, the refresh endpoint is called at `http://localhost:8081/manage/refresh`, not `http://localhost:8080/actuator/refresh`:

```yaml
management:
  server:
    port: 8081
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: "health,info,refresh"
```

When an ingress or API gateway sits in front, inspect both the external URL and the internal URL received by the application. A prefix added at the gateway without rewriting, or rewritten twice, can route requests to a nonexistent path. Also verify whether the Service/Ingress forwards to the application port or the management port.

## 4. Resolving 401: Authentication Failed

If Spring Security is on the classpath and the application declares no custom `SecurityFilterChain`, Spring Boot automatically secures Actuator endpoints except `health`. In this case, unauthenticated requests normally receive `401`.

Check sequentially:

1. Does the client send the exact credential type required by the server: HTTP Basic, bearer token, session cookie, or another mechanism?
2. For Basic authentication, check username/password and `UserDetailsService` or identity provider configuration.
3. For bearer tokens, check signature, issuer, audience, expiration, clock skew, and scopes/claims used by the application to map authorities.
4. If requests traverse a gateway, verify the gateway forwards the `Authorization` header. Never log tokens or passwords while inspecting.
5. Check the `WWW-Authenticate` response header and authentication provider logs to identify the active authentication mechanism.

A common cause is that the application already declared a `SecurityFilterChain` for business APIs. Once such a bean exists, Spring Boot's automatic Actuator security configuration yields to the custom setup. If the new chain matches only `/api/**`, Actuator requests may match no chain or fail to receive intended protection rules. If a broader chain matches first, it may apply different rules than those meant for management endpoints.

In Spring MVC/Servlet apps, you can use `EndpointRequest` to match Actuator endpoints instead of hard-coding `/actuator/**`. The example below protects all Actuator endpoints with the `ENDPOINT_ADMIN` role while permitting health access:

```java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class ManagementSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
        http.securityMatcher(EndpointRequest.toAnyEndpoint())
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to("health")).permitAll()
                .anyRequest().hasRole("ENDPOINT_ADMIN"))
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

The example uses HTTP Basic for illustration; in real systems, replace it with the authentication mechanism used by your application, such as OAuth2 Resource Server with JWT. The second chain rules business requests; if the application already has its own chain, integrate matching rules into existing configuration. When declaring a custom chain for Actuator, do not forget to protect the remaining routes.

The role name in `hasRole("ENDPOINT_ADMIN")` is interpreted by Spring Security as authority `ROLE_ENDPOINT_ADMIN`. If your identity provider issues authority `ENDPOINT_ADMIN` without the `ROLE_` prefix, use `hasAuthority("ENDPOINT_ADMIN")` or adjust role mapping consistently.

## 5. Resolving 403: Authenticated but Denied

### 5.1. Check Roles and Authorities

When a request is authenticated yet the user lacks required permissions, Spring Security normally returns `403`. Inspect the actual principal, granted authorities list, and expressions inside `authorizeHttpRequests`. In particular, distinguish `hasRole("OPS")` from `hasAuthority("ROLE_OPS")`: `hasRole` automatically prepends `ROLE_`, whereas `hasAuthority` compares the exact declared authority string.

With multiple `SecurityFilterChain` beans, check `@Order` values and matchers on each chain. A higher-priority chain whose matcher matches the request applies first. A catch-all chain such as `anyRequest()` placed ahead of the Actuator chain can prevent specialized rules from ever being evaluated.

### 5.2. Check CSRF for Write Operations

Read endpoints usually use `GET`; state-changing endpoints may require `POST`, `PUT`, or `DELETE`. Spring Security enables CSRF protection by default. Hence, a write request missing or sending an invalid CSRF token can receive `403`, even with valid username/password or bearer tokens.

Spring Cloud Context uses `POST` for the `refresh` endpoint. If `GET /actuator/refresh` fails, verify which HTTP method the endpoint supports; if `POST` returns `403`, inspect CSRF before altering roles. Browser clients using session cookies must submit valid CSRF tokens. Only consider ignoring CSRF specifically for the management endpoint when the API serves purely machine-to-machine clients, does not rely on automatic browser cookies, and already enforces authentication plus network restrictions. Never disable CSRF application-wide just to fix a management request.

### 5.3. Check Actuator Access Restrictions

Spring Security rules may permit the request while Actuator itself still restricts the operation. On versions supporting access properties, check:

- `management.endpoints.access.default`: default access level for endpoints.
- `management.endpoint.<id>.access`: endpoint-specific access level.
- `management.endpoints.access.max-permitted`: global maximum access ceiling.

`read-only` suits read operations only. If an endpoint must perform a write operation, a read-only restriction will reject it. Distinguish Actuator rejections from Spring Security rejections using logs and request responses rather than blindly granting higher permissions to all endpoints.

## 6. Ordered Diagnostic Procedure

Run the procedure below against the same request, same environment, and same instance to avoid comparing mismatched results across nodes:

1. **Record the exact request:** HTTP method, scheme, hostname, port, path, query string, auth headers, and target instance. Mask tokens, cookies, and passwords when saving evidence.
2. **Call the management server directly:** if `management.server.port` is configured, test that exact port from a machine or container with access. Compare against requests via ingress/gateway to isolate the failing layer.
3. **Test a baseline endpoint:** call `health` on the same management port and base path. If `health` also returns `404`, focus on routing, port, context path, and Actuator web exposure. If `health` succeeds while another endpoint returns `404`, check endpoint ID, dependencies, exposure, and access.
4. **Verify effective configuration:** inspect profile-specific config, environment variables, command-line arguments, and remote Config Server. Pay attention to `management.endpoints.web.exposure.*`, `management.endpoints.web.base-path`, `management.server.*`, `management.endpoint.*.access`, and external overrides.
5. **Isolate the security layer:** inspect `SecurityFilterChain`, matchers, chain ordering, authentication providers, authorities, and CSRF. Temporarily enable `org.springframework.security` at DEBUG level in a test environment or briefly; do not leave sensitive logging enabled long-term.
6. **Resend with the right method:** use `GET` for reads and `POST` for refresh. If `405` is returned, inspect the `Allow` header; if `401` or `403` is returned, follow the authentication, authorization, and CSRF steps above.
7. **Verify after fixing:** confirm endpoints are exposed only on the right management port, valid clients succeed, unauthorized clients are still rejected, and business routes remain unaffected.

Example checking a management server running on port `8081` with base path `/manage`:

```bash
# Check path and response headers of the health endpoint
curl -i http://localhost:8081/manage/health

# Trigger refresh via POST; if CSRF is enabled, a valid token is required
curl -i -u "$OPS_USER:$OPS_PASSWORD" \
  -X POST http://localhost:8081/manage/refresh
```

If direct calls return `200` while gateway calls return `404`, focus on gateway routes and rewrite rules. If both return `401`, check credentials/tokens and authentication rules. If only `POST` operations return `403`, check CSRF and endpoint write permissions before changing roles.

## 7. Scenario Example: `/actuator/refresh` Returns 404 Then Turns into 403

A service using Spring Cloud Config needs to refresh `@RefreshScope` beans after remote configuration changes. Operations calls `POST /actuator/refresh` and receives `404`.

**Step 1 — Check whether the endpoint is exposed.** The application already includes Spring Cloud Context, yet configuration only exposes `health`. Add `refresh` to the exposure list:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,refresh"
```

After restarting or applying configuration per the application's deployment mechanism, the request reaches the right endpoint yet receives `403`.

**Step 2 — Check Spring Security and CSRF.** The operational principal is authenticated and holds the admin role, yet the `POST` request lacks a CSRF token. Because the application still uses session/cookie authentication for browser clients, CSRF protection is active. Operations must either supply a valid token under the current mechanism or design a dedicated machine-to-machine flow protected by tokens, network boundaries, and a CSRF rule scoped specifically to the appropriate endpoint.

**Step 3 — Verify the result.** Resend `POST /actuator/refresh` with matching authentication and CSRF handling. Confirm a successful response, logs showing the refresh operation ran, and `@RefreshScope` beans reinitializing on next access. If the application runs multiple instances, remember calling `refresh` affects only the instance receiving the request; use Spring Cloud Bus and the `busrefresh` endpoint when the architecture requires broadcasting refresh events to multiple instances.

## 8. Version and Safe Operations Notes

- Exposure settings and management paths must be checked against documentation for your exact running Spring Boot version. Do not assume every new Boot 4 property exists in Boot 3.x.
- In Spring Boot 3.x, `EndpointRequest` for Servlet resides in package `org.springframework.boot.actuate.autoconfigure.security.servlet`. Starting with Spring Boot 4.x, the package in official examples is `org.springframework.boot.security.autoconfigure.actuate.web.servlet`. When upgrading Boot, update imports according to your actual version.
- Choose a Spring Cloud release train compatible with Spring Boot. At the time of writing, the official release table lists Spring Cloud 2025.1.4 supporting Boot 4.0.9, Spring Cloud 2025.0.3 supporting Boot 3.5.15, and Spring Cloud 2024.0.3 supporting Boot 3.4.12. Do not infer compatibility solely from major version numbers; check the latest compatibility matrix before upgrading.
- Never use `permitAll`, `include: "*"`, or global CSRF disablement as a quick production fix. Expose only needed endpoints, place management servers on administrative networks, restrict roles, and monitor audit logs.
- The `refresh` endpoint modifies application runtime state. Grant access only to controlled operational accounts, rate-limit calls, and verify the impact on beans needing refresh.

## References

1. [Spring Boot 3.5 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html)
2. [Spring Boot 4.x — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
3. [Spring Boot — Monitoring and Management Over HTTP](https://docs.spring.io/spring-boot/reference/actuator/monitoring.html)
4. [Spring Cloud Commons — Spring Cloud Context: Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
5. [Spring Cloud Release — Release Train Reference Documentation](https://docs.spring.io/spring-cloud-release/reference/index.html)
