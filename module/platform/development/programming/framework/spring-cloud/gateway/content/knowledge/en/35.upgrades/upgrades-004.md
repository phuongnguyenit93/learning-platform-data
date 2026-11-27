# Migrating Security Configuration, Trusted Proxies, and Actuator

Upgrading Spring Cloud Gateway often brings changes in Spring Boot, Spring Security, and how the application identifies requests coming through a reverse proxy. If you only update dependencies while keeping old configuration, Gateway may start up yet apply wrong authentication rules, construct URLs with incorrect schemes or hosts, record wrong client addresses, or unintentionally broaden Actuator access.

This lesson explains how to migrate three closely related areas: WebFlux security configuration, the trusted proxy list, and Actuator management endpoints. Examples focus on Spring Cloud Gateway Server WebFlux. Always cross-check actual Spring Boot, Spring Cloud Gateway, and Spring Security versions before applying changes, because property names changed across generations.

## 1. Map Versions Before Editing Configuration

Spring Cloud Gateway ships alongside a specific Spring Boot and Spring Framework generation. Do not upgrade Spring Security or Spring Framework independently by forcing versions in the build file when the Spring Cloud release train already manages them.

| Generation | Typical accompanying platform | Gateway WebFlux config prefix | Boot forwarded-header config |
|---|---|---|---|
| Spring Cloud Gateway 4.x | Spring Boot 3.x, Spring Framework 6, Spring Security 6 | `spring.cloud.gateway.*` | `server.forward-headers-strategy` |
| Spring Cloud Gateway 5.x | Spring Boot 4.x, Spring Framework 7, Spring Security 7 | `spring.cloud.gateway.server.webflux.*` | `server.request.header.forwarded.strategy` |

This table guides by major release line. Check the Spring Cloud release train compatibility matrix and the documentation for the exact minor version before selecting JDK, Spring Boot, and Gateway. Gateway Server WebFlux and Gateway Server Web MVC also have separate namespaces in newer lines; do not copy MVC config into a WebFlux application.

Before upgrading, record the following information:

- Current JDK, Spring Boot, Spring Cloud release train, Spring Cloud Gateway, and Spring Security versions.
- Direct and transitive dependencies, especially security starters, OAuth2 resource server, Actuator, and service discovery.
- Complete `SecurityWebFilterChain` configurations, Gateway filters, CORS, forwarded headers, management port, and Actuator exposure.
- The list of IP addresses or network ranges of load balancers, ingress controllers, and reverse proxies that actually connect directly to Gateway.
- Current test results for public requests, JWT-protected requests, CORS preflight, client-address-based routes, and management endpoints.

Keep sample requests and pre-upgrade results to compare after migration. A configuration that merely runs does not prove the security policy remained intact.

## 2. Migrate WebFlux Security Configuration to SecurityWebFilterChain

Gateway Server WebFlux uses the reactive security stack. When migrating from legacy configs to Spring Security 6 or newer, declare access rules via a `SecurityWebFilterChain` bean taking `ServerHttpSecurity`. Do not use Spring MVC examples with `HttpSecurity`, `SecurityFilterChain`, or `authorizeHttpRequests` for Gateway WebFlux.

In older systems, a Servlet module might still contain a class extending `WebSecurityConfigurerAdapter`; that belongs to the Servlet stack and is not a replacement for Gateway WebFlux. For reactive Gateway, place access rules in `SecurityWebFilterChain` to cleanly separate public APIs, token-protected APIs, and operational endpoints.

Example JWT resource server configuration for APIs:

```java
import static org.springframework.security.config.Customizer.withDefaults;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ApiSecurityConfiguration {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/api/public/**").permitAll()
                        .pathMatchers("/api/admin/**").hasAuthority("SCOPE_gateway.admin")
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(withDefaults()))
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .build();
    }
}
```

Declare the issuer so Spring Security discovers metadata and JWT verification keys:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/realms/platform
```

In the example, scope `gateway.admin` maps to authority `SCOPE_gateway.admin`. Scope names must match claims issued by the Identity Provider or a custom authority converter configured by the application. When validating JWTs, check issuer, signature, expiration, and audience per the system's token contract. Do not treat a successfully decoded token as sufficient to grant access.

`csrf().disable()` is only appropriate for stateless APIs using bearer tokens in headers that do not rely on browser session cookies for authentication. If Gateway serves web UIs, uses session cookies, or exposes endpoints receiving state-changing actions from browsers, keep CSRF protection enabled and configure appropriate CSRF tokens. CORS is also a separate policy; allowing an origin is not equivalent to authenticating users.

### Separate security rules for Actuator

When an application declares its own `SecurityWebFilterChain`, Spring Boot's default security configuration may yield control to the application's config. Therefore, do not add rules only for `/api/**` and assume Actuator stays protected as before. Create a dedicated chain for management endpoints with higher priority than the API chain.

The example below permits public health checks and requires a token with an operational scope for remaining Actuator endpoints:

```java
import static org.springframework.security.config.Customizer.withDefaults;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Configuration
public class GatewaySecurityConfiguration {

    @Bean
    @Order(0)
    SecurityWebFilterChain actuatorSecurity(ServerHttpSecurity http) {
        return http
                .securityMatcher(ServerWebExchangeMatchers.pathMatchers("/actuator/**"))
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/actuator/health", "/actuator/health/**").permitAll()
                        .anyExchange().hasAuthority("SCOPE_ops"))
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(withDefaults()))
                .build();
    }

    @Bean
    @Order(1)
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/api/public/**").permitAll()
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(withDefaults()))
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .build();
    }
}
```

Chains are evaluated in order. The first chain matches only `/actuator/**`; the API chain handles the remaining requests. If you change `management.endpoints.web.base-path` from `/actuator` to `/manage`, update the matcher accordingly. If the management server uses a separate port, still protect that port with network policies or firewalls; application-level matchers do not replace network controls.

In the example, the `ops` scope must be intentionally issued only to operational accounts or workloads. Do not grant this scope to regular user tokens. If your organization uses HTTP Basic or a separate identity system for the management plane, adjust the authentication mechanism in the Actuator chain per organizational operational standards.

## 3. Migrate Trusted Proxies and Forwarded Headers

When requests pass through a load balancer or reverse proxy, Gateway sees the TCP connection coming from the proxy. The proxy may send metadata about the original request via the standard `Forwarded` header or common headers `X-Forwarded-For`, `X-Forwarded-Host`, `X-Forwarded-Port`, `X-Forwarded-Proto`, and `X-Forwarded-Prefix`.

These headers affect client address, HTTPS scheme, public host, redirect URLs, secure cookies, logs, and address-based route predicates. Trusting headers sent arbitrarily by clients allows attackers to spoof IPs, skew rate-limit decisions, or trick the application into generating redirects to untrusted hosts.

Distinguish two configuration layers:

1. **Spring Boot forwarded-header strategy** controls how the web server or Spring Framework interprets forwarded information to reconstruct the current request, such as the scheme and host seen by the application.
2. **Spring Cloud Gateway trusted proxies** defines which proxies are trusted when Gateway creates or appends `Forwarded` and `X-Forwarded-*` headers sent to downstream services.

The two configurations are related but do not replace each other. Boot config does not define the list of proxies Gateway trusts; Gateway properties do not isolate the Gateway port from external clients.

### Configuration by version

With Spring Boot 3 and Spring Cloud Gateway 4.x, WebFlux configuration can take the form:

```yaml
server:
  forward-headers-strategy: framework

spring:
  cloud:
    gateway:
      trusted-proxies: '^(?:10\.20\.0\.10|10\.20\.0\.11)$'
```

With Spring Boot 4 and Spring Cloud Gateway 5.x Server WebFlux, the namespace moved to:

```yaml
server:
  request:
    header:
      forwarded:
        strategy: web-server

spring:
  cloud:
    gateway:
      server:
        webflux:
          trusted-proxies: '^(?:10\.20\.0\.10|10\.20\.0\.11)$'
```

In both examples, `10.20.0.10` and `10.20.0.11` are only illustrative addresses of proxies connecting directly to Gateway. Replace them with real addresses in your infrastructure. The expression is a Java regular expression; check the actual address values the application receives in the deployment environment to ensure the regex matches properly.

In Boot 3, `framework` uses Spring Framework's forwarded-header support, where the reactive stack uses `ForwardedHeaderTransformer`; `native` uses the web server's capability if supported. In Boot 4, the property is reorganized into `server.request.header.forwarded.strategy`; pick `web-server` when the server supports it fully, or `framework` when Spring Framework's common mechanism is needed. Do not copy property names verbatim between Boot 3 and Boot 4.

If the Gateway application uses Web MVC in Spring Cloud Gateway 5.x, the corresponding namespace is `spring.cloud.gateway.server.webmvc.*`. Do not use `server.webflux.trusted-proxies` for MVC.

### Establish a trust boundary at the edge proxy

A secure trusted-proxy configuration needs matching network design:

- Allow only known load balancers or ingresses to connect to Gateway's port. Use security groups, firewalls, network policies, or private subnets to block direct access from the Internet.
- At the edge proxy, strip client-supplied `Forwarded` and `X-Forwarded-*` headers, then rewrite values based on the connection the proxy actually received.
- Trust only the addresses or network ranges of hops inside the controlled proxy chain. Never set `.*` or trust all proxies in production.
- When multiple proxy layers exist, document hop order and standardize header appending. Never assume the first element of `X-Forwarded-For` is always a trusted IP.
- Forward only fields downstream genuinely needs. Restrict `X-Forwarded-Host` if downstream services do not need the public host; validate against a host allowlist before using it to build URLs or redirects.

Gateway provides filters that generate `Forwarded` and `X-Forwarded-*` headers. When needed, you can toggle individual fields and control appending. Example enabling only required fields in SCG 5.x:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          x-forwarded:
            enabled: true
            for-enabled: true
            host-enabled: true
            port-enabled: true
            proto-enabled: true
            prefix-enabled: false
```

Corresponding property names in SCG 4.x sit under `spring.cloud.gateway.x-forwarded.*`. Enable `prefix` only if the proxy architecture actually strips a path prefix and downstream needs to reconstruct the original prefix. Do not let both the edge proxy and Gateway append the same values without a clear convention.

### Client address and the RemoteAddr predicate

By default, the `RemoteAddr` predicate may see the peer address directly connected to Gateway—meaning the load balancer address rather than the end client address. If routes or rate limiters need the client address, explicitly define the trusted address source and the allowed number of proxy hops.

Spring Cloud Gateway provides `XForwardedRemoteAddressResolver` to read addresses from `X-Forwarded-For`. For a fixed-structure proxy chain, choose `maxTrustedIndex(n)` matching the identified number of trusted proxies. Never use a resolver that trusts all forwarded values when requests can reach Gateway directly from the Internet. If the topology changes, update the index and re-test because picking the wrong hop breaks ACLs or rate limits.

Do not use a forwarded IP as the sole user identity. IPs can assist network controls or supplementary rate limiting; user authentication must still rely on tokens or an appropriate identity mechanism.

## 4. Migrate Actuator Configuration Safely

Actuator provides health, metrics, configuration info, and Gateway management endpoints. After upgrading, verify three conditions simultaneously: the endpoint is enabled, exposed via HTTP or JMX, and the caller is authorized. A missing endpoint may be unexposed or disabled; 401/403 errors usually stem from security policy.

Expose only necessary endpoints. For example, in Spring Boot 3.4+ or Boot 4, you can disable endpoint access by default and open read-only access for required operational endpoints:

```yaml
management:
  endpoints:
    access:
      default: none
    web:
      exposure:
        include: health,info,metrics,prometheus,gateway
  endpoint:
    health:
      access: read-only
    info:
      access: read-only
    metrics:
      access: read-only
    prometheus:
      access: read-only
    gateway:
      access: read-only
```

`access: read-only` restricts endpoint operations to reads. This is especially useful for the Gateway Actuator endpoint, which can expose route modification or refresh operations depending on version. Verify that the `gateway` endpoint exists and which operations are supported in your exact Spring Cloud Gateway version.

For Spring Boot 3.0 through 3.3, use that generation's enablement and exposure properties, and protect endpoints via security chains and network policies:

```yaml
management:
  endpoint:
    gateway:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus,gateway
```

In these versions, do not assume `management.endpoints.access.default` or `management.endpoint.<id>.access` is available. Check minor-version documentation rather than putting new properties into an older application and thinking access is restricted.

You can place the management server on a separate port and bind only to an internal interface:

```yaml
management:
  server:
    port: 8081
    address: 127.0.0.1
```

`127.0.0.1` works when a monitoring agent runs in the same network namespace as Gateway. In Kubernetes or environments where Prometheus scrapes from another pod, bind to an appropriate network interface and restrict access via NetworkPolicy, firewall, and authentication. A separate port is not automatically safe if it is still published to a public network.

Do not expose `*` just for testing convenience. Endpoints like `env`, `configprops`, `beans`, `heapdump`, `loggers`, or `gateway` can leak internal details or alter application behavior. If Prometheus needs to scrape without a bearer token, permit only the metrics endpoint on the internal scraping network; do not open all of Actuator to every source.

## 5. Compatibility Testing After Migration

After editing configuration, launch Gateway in a staging environment with a proxy topology matching production. Use a test suite covering both valid cases and deliberate spoofing attempts.

| Case | Expected result to verify |
|---|---|
| Public request to public route | Routed properly without requiring a token |
| Request to private API without token | Rejected with 401 |
| Token with invalid signature, issuer, audience, or expired | Rejected; never forwarded as an authenticated request |
| Token missing admin scope | Cannot access admin routes or management Actuator |
| `OPTIONS` preflight from allowed origin | Returns proper CORS headers; does not expose authenticated routes |
| Request through trusted proxy | Scheme, host, and client address reflect declared topology |
| Client sends spoofed `X-Forwarded-For` from untrusted source | Spoofed value is not used to determine IP or build downstream headers |
| Direct request to Gateway address from Internet | Blocked at network layer or cannot masquerade as a proxied request |
| `/actuator/health` | Open only according to chosen health check policy |
| `/actuator/gateway/routes` and `/actuator/metrics` | Readable only by operational accounts or networks |
| Gateway Actuator write operations | Blocked when environment allows read-only only |

Example of testing the health endpoint and management endpoint:

```bash
curl -i https://api.example.com/actuator/health

# Without operations token: expect 401 or 403
curl -i https://api.example.com/actuator/gateway/routes

# Token needs ops scope per security configuration
curl -i \
  -H 'Authorization: Bearer <OPS_ACCESS_TOKEN>' \
  https://api.example.com/actuator/gateway/routes
```

To verify forwarded headers, send requests through the real load balancer and inspect downstream logs or a test echo endpoint. Compare a request through a trusted proxy against a request with spoofed headers from an untrusted source. Do not check response headers alone; verify the values Gateway actually uses to evaluate route predicates, log entries, and upstream headers.

When TLS terminates at the load balancer, verify `X-Forwarded-Proto` or `Forwarded: proto=https` is processed properly. Redirect URLs and cookies must preserve the external HTTPS scheme. If the application generates HTTP redirects, check the forwarded-header strategy and proxy config. Do not work around errors by trusting all forwarded headers.

## 6. Controlled Migration Workflow

1. **Lock the version matrix:** select compatible Spring Boot and Spring Cloud release trains; let the BOM manage Gateway and Spring Security versions.
2. **Save the baseline:** record security rules, exposed Actuator endpoints, proxy config, address-dependent route predicates, and test requests.
3. **Migrate API security:** replace old configuration with reactive `SecurityWebFilterChain`; clearly define public routes, JWT-protected routes, scopes, and CSRF policy.
4. **Separate management policy:** add a dedicated chain for Actuator, set precedence order, and restrict read/write access per Boot version.
5. **Rename properties:** update Gateway prefixes when moving to SCG 5.x; update forwarded-header properties when moving to Boot 4. Do not rename from memory—check the target dependency's configuration metadata.
6. **Configure proxy trust:** update direct proxy lists, configure edge proxies to strip client-sent headers, and restrict network paths to Gateway.
7. **Run staging tests:** execute the matrix from the previous section, comparing logs, routes, redirects, IPs, statuses, and Actuator permissions against the baseline.
8. **Phased rollout:** monitor 401/403, 404, redirects, error rates, latency, and access logs; keep a rollback-ready configuration if the new policy causes issues.

When upgrading from Boot 3/SCG 4 to Boot 4/SCG 5, treat namespace migration as a controlled configuration change. Some legacy properties may be silently ignored while the application still boots normally; hence verify runtime values or actual behavior rather than relying solely on the absence of startup errors.

## 7. Common Migration Issues

| Symptom | Possible cause | How to check |
|---|---|---|
| All APIs unexpectedly require login | Custom chain replaced default config; `permitAll` rule missing | Check chain ordering and matchers; test public routes |
| API returns 403 despite valid JWT | Mismatched scope/authority, wrong audience, or CSRF rule applied to request | Inspect redacted token claims, check authority converter and HTTP method |
| Previously accessible Actuator now returns 401/403 | New chain captured management paths too | Check `/actuator/**` matcher, roles/scopes, and `@Order` |
| Actuator returns 404 after upgrade | Endpoint not exposed, not enabled, or management base path changed | Check `management.endpoints.web.exposure`, endpoint access, and base path |
| Gateway ignores trusted proxy after upgrade | Old prefix used on SCG 5.x or regex does not match peer address | Check `server.webflux` namespace and actual socket address |
| Client IP becomes the load balancer IP | Forwarded headers not processed or resolver selects wrong hop | Check Boot strategy, Gateway trusted proxies, and resolver hop count |
| Redirect produces HTTP URL or strange host | Forwarded scheme/host wrong or edge proxy did not overwrite client header | Check `Forwarded`, `X-Forwarded-Proto`, `X-Forwarded-Host`, and host allowlist |
| `RemoteAddr`-based route changes outcome | Predicate sees a different peer address after proxy topology change | Identify trusted IP sources and test each ingress path |

## 8. Hands-On Exercise

1. Take a Gateway WebFlux configuration using Spring Cloud Gateway 4.x. Record the `spring.cloud.gateway.*` prefix, `server.forward-headers-strategy` config, and existing security beans.
2. Migrate APIs to a `SecurityWebFilterChain` using JWT. Create a public route and a scope-protected route; confirm tokens missing or having the wrong scope are rejected.
3. Add an Actuator chain with `@Order(0)`. Allow health checks per your environment policy and require an operational scope for remaining endpoints.
4. Create two illustrative configuration profiles for SCG 4.x/Boot 3 and SCG 5.x/Boot 4. Compare trusted-proxy namespaces and forwarded-header strategies between the two profiles.
5. In staging, send requests through a trusted proxy and requests spoofing `X-Forwarded-For` from an untrusted source. Confirm the client IP recorded by Gateway cannot be chosen by the client.
6. Expose only required Actuator endpoints. Verify unauthorized users cannot read route lists or metrics, and write operations are blocked when endpoints are configured read-only.
7. Compare HTTPS redirects, CORS preflight, address-based route predicates, and request logs before/after the upgrade. Document all discrepancies to resolve before production deployment.

## References

- [Spring Cloud Gateway 4.3 – Configuration Properties](https://docs.spring.io/spring-cloud-gateway/reference/4.3/configprops.html)
- [Spring Cloud Gateway 5.0 – Configuration Properties](https://docs.spring.io/spring-cloud-gateway/reference/5.0/configprops.html)
- [Spring Cloud Gateway – HTTP Headers Filters](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/httpheadersfilters.html)
- [Spring Cloud Gateway – RemoteAddr Route Predicate and XForwardedRemoteAddressResolver](https://docs.spring.io/spring-cloud-gateway/docs/current/reference/html/index.html#the-remoteaddr-route-predicate-factory)
- [Spring Boot 3.5 – Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html)
- [Spring Boot 4.0 – Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/4.0/how-to/webserver.html)
- [Spring Boot – Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Security – WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security – Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
