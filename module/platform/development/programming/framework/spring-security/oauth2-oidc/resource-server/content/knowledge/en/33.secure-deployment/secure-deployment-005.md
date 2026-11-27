# Controlling Direct-Origin Calls and Verifying at the Designed API Boundary

In a **Spring Security OAuth 2.0 / OIDC Resource Server**, an API must independently verify requests at the boundary where it actually receives traffic. This is especially critical when a system has an API Gateway, reverse proxy, ingress controller, service mesh, or multiple internal access paths. If the backend relies solely on the assumption that a request passed through a gateway, a caller may find a path to call the service directly and bypass checks placed at earlier layers.

A secure architecture must clearly answer:

- Which clients are allowed to connect to the API?
- Do requests go through a gateway or can the origin be called directly?
- Which component verifies the Access Token's signature, issuer, audience, and lifetime?
- Which API is the resource server that receives the token and enforces scopes?
- At which routes, methods, and data objects are access permissions checked?
- From which hops can proxy-added headers be trusted?
- Which identity and token does a service use when calling another service?

**The verification boundary must sit at the API designed to receive and protect the resource.** A gateway can perform early authentication, filter traffic, rate limit, and normalize requests, yet the backend must still verify credentials and authorization for its own resources if the backend can be reached directly or sits in a separate trust boundary.

This lesson belongs to the **Secure Deployment** chapter, using **Java 17+, Spring Boot 3.x, and Spring Security 6.x** as context. It focuses on direct-origin access, defense in depth, OAuth audience/scope, tenant/object authorization, token relay and delegation, network ingress, proxy headers, Servlet/WebFlux configuration, CORS/CSRF, and testing bypass paths.

## 1. The API Boundary Is Where Request Authorization Is Decided

Consider an application consisting of a Gateway, Orders API, and Billing API:

~~~text
                         Internet
                            |
                            v
                    API Gateway / WAF
                      /           \
                     v             v
               Orders API       Billing API
                     |             |
                     v             v
                Orders DB      Billing DB
~~~

In an ideal deployment, public traffic flows through the gateway. However, if the Orders API has a public load balancer, published container ports, exposed internal DNS, or permissive network policies allowing direct caller access, the actual path can be:

~~~text
Caller -----------------------> Orders API
          bypasses Gateway
~~~

If the Gateway is the only place checking JWTs, a direct caller can reach the backend without undergoing verification. If the backend trusts headers commonly added by a gateway such as `X-User`, `X-Roles`, or `X-Authenticated`, a caller can send those headers directly.

You must distinguish:

- **Network boundary:** who can open a connection to the service.
- **Authentication boundary:** which identities/credentials the API verifies.
- **Authorization boundary:** which operations on which resources the API permits the subject to perform.
- **Trust boundary:** which components are permitted to supply assertions/headers that the API trusts.

One layer does not replace the others. Blocking direct access at the network layer is very useful, yet does not replace token verification at the API. Nor does a valid JWT automatically grant access to every endpoint or every tenant.

## 2. The Gateway Is an Additional Layer of Defense

A gateway can terminate TLS, perform preliminary token verification, route paths, enforce rate limits/WAF, bound request sizes, normalize trace headers, and relay tokens per configuration. The backend still needs to check properties pertaining to the resources it protects:

- Token was issued by a trusted issuer.
- Audience targets the current API.
- Token is not expired and is within its validity window.
- Scope/authorities suffice for the operation.
- Subject/tenant has permissions on the specific object.
- Token type and delegation conform to the contract.

| Check | Gateway | API Backend |
| --- | --- | --- |
| Reject requests missing a token | Can do | Yes, if the endpoint requires authentication |
| Verify signature/issuer | Can do | Must do itself if the API receives a Bearer Token |
| Target API audience | Can check by route | Must verify the resource's audience |
| Operation scope | Can pre-filter | Must check permissions the backend actually needs |
| Permissions on a specific order/account | Usually lacks sufficient domain context | Backend must check |
| Tenant isolation | May enforce coarse policy | Backend must apply to queries/data |
| Business invariants | Does not replace domain logic | Backend is responsible |

Never assume a request is valid simply because the gateway forwarded it. The backend must have sufficient verified data to make its own access decisions.

### 2.1. If the Backend Accepts Only the Gateway

You can design a topology where only the gateway is allowed to connect to the backend. In that case, network policies, firewalls/security groups, private subnets, service mesh authorization, and workload identity must actually enforce it.

Even in that topology, the backend should still verify the Access Token or a signed internal assertion with a clear trust source if the backend is responsible for authorization. Relying solely on source IP or unauthenticated headers is weak, especially in multi-workload environments.

### 2.2. Direct Calls Can Be a Legitimate Use Case

Not every direct call is a bypass. A mobile app, partner integration, or internal service may be designed to call the API origin directly. In that case:

1. The call path must be defined in the API contract.
2. Clients must use an accepted authentication mechanism.
3. The Resource Server verifies tokens at the origin.
4. Audience and scopes must target that API.
5. Network policies, rate limits, and monitoring must apply to the direct path.
6. Do not rely on headers that only a gateway is supposed to add.

The goal is to control every supported path, rather than assuming only one route exists.

## 3. Controlling Direct Calls at the Network Layer

~~~text
Internet
   |
   v
Public Load Balancer
   |
   v
Gateway / WAF
   |
   v
Private Service Network
   |
   +-- Orders API (private ingress only)
   |
   +-- Billing API (private ingress only)
   |
   +-- Inventory API (private ingress only)
~~~

Common measures:

- Do not publish backend ports to public networks unless needed.
- Use private load balancers or internal service discovery.
- Security groups/firewalls allow only designated source workloads/gateways.
- Kubernetes `NetworkPolicy` restricts ingress across namespaces/pods.
- Service mesh authorization policies restrict source and destination workloads.
- Use mTLS/workload identity for service-to-service connections.
- Separate management/actuator ports from public API ingress.
- Control DNS and routing so no unintended access paths exist.

### 3.1. Network Policies Do Not Replace Authorization

A service allowed to connect to the Orders API may still not be allowed to read every order. Network policies decide which workloads can open connections; token/scope/domain authorization decides what the caller can do.

~~~text
Network allow:
  inventory-service -> orders-api

Application authorization:
  inventory-service token aud=orders-api
  scope=orders.read
  operation=read-order-for-fulfillment
  tenant/order ownership policy passes
~~~

## 4. Access Tokens Must Target the Receiving API

A JWT may have a valid signature yet not be intended for the current resource:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-42",
  "aud": ["inventory-api"],
  "scope": "inventory.read",
  "exp": 1893456000
}
~~~

If this token is sent to the Orders API, the Orders API must reject it if its audience contract requires `orders-api`. A valid signature only proves the token was issued by the issuer and has not been tampered with; it does not prove the token was issued for every service.

### 4.1. Audience Is the Boundary Between Resource Servers

~~~text
Access Token T_inventory
  aud = inventory-api
  scope = inventory.read
       |
       +----> Inventory API: may accept
       |
       +----> Orders API: rejects mismatched audience
       |
       +----> Billing API: rejects mismatched audience
~~~

Do not use one overly broad shared audience across all APIs when resources have distinct trust boundaries and permissions. If an architecture uses a gateway/resource façade as a shared audience, clearly define the gateway as the actual resource and specify what assertions/delegations backends receive.

### 4.2. Scopes Must Be Checked at the API

Audience answers which resource the token is for; scope answers which group of actions is granted.

| API Operation | Illustrative Minimum Scope |
| --- | --- |
| Read order | `orders.read` |
| Create order | `orders.write` |
| View invoice | `billing.read` |
| View inventory | `inventory.read` |

The backend must never infer write permissions merely because a token is authenticated. Check scopes/authorities on every route or method.

### 4.3. Issuer and Algorithm Must Also Be Restricted

The Resource Server must trust only configured issuers, fetch JWKS from trusted endpoints associated with each issuer, accept signing algorithms per an allowlist, check audience, expiration/not-before, and profile claims. Never use token headers to choose JWKS URLs or issuer trust dynamically.

If the system is multi-issuer, use governed registrations/resolvers; never fetch discovery from an arbitrary issuer URL taken from the request.

## 5. Verifying at Route, Method, and Object Boundaries

~~~text
Authentication:
  Token signature valid
  iss trusted
  aud = orders-api
  exp valid
       |
       v
Route authorization:
  scope includes orders.read
       |
       v
Object authorization:
  user belongs to tenant
  AND user may read order-42
       |
       v
Return order
~~~

### 5.1. Route-Level Authorization

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/actuator/health").permitAll()
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .requestMatchers(HttpMethod.POST, "/api/orders/**")
                .hasAuthority("SCOPE_orders.write")
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2.jwt())
        .build();
}
~~~

This example illustrates the Servlet stack. In production, explicitly define which health endpoints are public, matcher ordering, HTTP methods, and rules for all routes. Never place a broad matcher ahead of stricter rules.

### 5.2. Method-Level Authorization

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

~~~java
@Service
public class OrderQueryService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public Order getOrder(String orderId) {
        return repository.findById(orderId)
            .orElseThrow(OrderNotFoundException::new);
    }
}
~~~

Method security is useful when a service has multiple callers, such as HTTP controllers, message listeners, or scheduled jobs. Still, scope checks remain insufficient when permissions depend on tenant, owner, or object state.

### 5.3. Object-Level Authorization

Never allow callers to supply an arbitrary order ID and check only scope. The backend must enforce tenant/owner/relationship checks in queries or domain services:

~~~java
public Mono<Order> getOrder(
        String orderId,
        String authenticatedTenantId) {
    return repository.findByIdAndTenantId(
        orderId,
        authenticatedTenantId);
}
~~~

Derive the tenant ID from the verified principal/claim or a contractually trusted internal context. Never take a tenant ID from the request body as proof the user belongs to that tenant.

## 6. Configuring a JWT Resource Server for a Servlet API

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfiguration {

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(
                "https://identity.example.test/oauth2/jwks")
                .build();

        OAuth2TokenValidator<Jwt> issuer =
            new JwtIssuerValidator(
                "https://identity.example.test");

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        OAuth2ErrorCodes.INVALID_TOKEN,
                        "Token is not intended for orders-api",
                        null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                new JwtTimestampValidator(Duration.ofSeconds(30)),
                issuer,
                audience));

        return decoder;
    }

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http)
            throws Exception {
        return http
            .sessionManagement(session -> session
                .sessionCreationPolicy(
                    SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers(
                    HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(
                    HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2.jwt())
            .build();
    }
}
~~~

In the example, the JWKS URI and issuer are server-side configuration; the timestamp validator checks time validity; the audience validator binds the token to the Orders API; route rules require appropriate scopes; and the stateless session policy avoids using HTTP sessions as implicit identity for a Bearer API.

This is a foundational example; configure error handling, CORS, CSRF, and method/object authorization for your application. Do not disable CSRF simply because the application uses Spring Security: disabling it is appropriate when the API only accepts Bearer tokens via the `Authorization` header and does not use cookies/session credentials automatically sent by browsers. If cookie authentication is present, CSRF must still be handled.

## 7. Configuring a Resource Server for WebFlux

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactiveApiSecurityConfiguration {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/actuator/health").permitAll()
                .pathMatchers(
                    HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(
                    HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2.jwt())
            .build();
    }
}
~~~

In WebFlux, authentication and authorization run inside the `WebFilter` chain. Do not use a Servlet `SecurityFilterChain` for a reactive application, and do not read `SecurityContext` via `ThreadLocal` in reactive code.

### 7.1. Reactive Method Security

~~~java
@Configuration
@EnableReactiveMethodSecurity
class ReactiveMethodSecurityConfiguration {
}
~~~

Methods can return `Mono`/`Flux` and use `@PreAuthorize`. Permission checks must execute within reactive execution; avoid calling `block()` to obtain the principal or wait on repositories.

## 8. Do Not Trust Client-Sent Identity Headers

Some systems use internal headers:

~~~http
X-Authenticated-User: alice
X-Authenticated-Roles: ADMIN
X-Tenant-Id: tenant-42
~~~

If an API accepts these headers directly from the Internet and trusts them, callers can impersonate users/roles/tenants.

### 8.1. Strip Incoming Headers at the Proxy

The gateway can strip all client-sent identity headers, authenticate the Access Token, generate internal assertions strictly per contract, and send assertions over an authenticated connection to the backend.

The backend must verify the assertion source, such as a signature, mTLS workload identity, or an internal token mechanism. If the backend also receives direct traffic, it must reject identity headers lacking a trusted source.

### 8.2. Header Forwarding Is Not Authentication

Headers such as `X-Forwarded-For`, `X-Forwarded-Proto`, `Forwarded`, and `X-Forwarded-Host` may be used to reconstruct client IP or external URLs, yet only when requests arrive from a configured proxy and the proxy has overwritten client-sent values.

Never use `X-Forwarded-For` to decide user identity or access rights. Clients can send forged headers if the edge proxy fails to strip/overwrite them properly.

### 8.3. Forwarded Headers and Host Poisoning

`Host`/forwarded host can affect redirect URLs, links generated in emails, callback URLs, and origin checks. Configure trusted proxy ranges and allowed hosts. Never use request-supplied `Host` values to dynamically construct issuer URIs, JWKS URIs, or redirect URIs.

## 9. Token Relay and Service-to-Service Calls

When the Orders API calls the Inventory API, choose an appropriate credential:

~~~text
User token T_orders
  aud = orders-api
       |
       v
Orders API
       |
       +-- relay T_orders to Inventory API?
       |       No, if audience does not include inventory-api.
       |
       +-- exchange/delegate at Authorization Server
               |
               v
           T_inventory
             aud = inventory-api
             scope = inventory.read
               |
               v
           Inventory API
~~~

### 9.1. When to Relay the Current Token

Relaying is only appropriate if the current token was already issued for the downstream resource and policy permits delegation. Never relay a token merely because two services sit in the same private network.

### 9.2. When Token Exchange Is Needed

If downstream is a different resource, use OAuth Token Exchange or a delegation mechanism supported by the Authorization Server to obtain a new token with the proper audience/resource and scopes. The backend selects the target resource via server-side policy; never let callers pick an arbitrary audience.

### 9.3. Client Credentials Do Not Automatically Represent the End User

A service can call downstream using client credentials. That token represents the client/service per policy, not the end user by default. If business logic requires per-user authorization, clear delegation/actor semantics and audit trails are required.

### 9.4. Do Not Send Tokens to Arbitrary URLs

Downstream URIs must come from a trusted service registry/configuration. Never take a URL from a request and attach the current Access Token to the outbound call. If fetching user-entered URLs is required, use a separate HTTP client carrying no OAuth credentials and apply SSRF controls.

## 10. CORS Is Not Authorization

CORS is a browser mechanism controlling which JavaScript origins may read responses. It does not block other clients such as `curl`, mobile apps, backend services, or custom scripts.

~~~text
Browser JavaScript from https://app.example
        |
        | CORS policy checked by browser
        v
API

curl / backend client
        |
        | Does not enforce browser CORS policy
        v
API
~~~

Therefore, a CORS allowlist does not replace JWT authentication; CORS does not replace scope/role/object authorization; requests without an `Origin` header must not be treated as trusted; and actual requests still require authentication/authorization even if `OPTIONS` preflight is allowed.

## 11. CSRF Depends on Browser-Auto-Sent Credentials

CSRF primarily concerns credentials automatically attached by browsers, such as session cookies. A Bearer token explicitly added by JavaScript to the `Authorization` header has different properties, yet if an application stores tokens in cookies or uses session cookies, CSRF can still occur.

| Authentication Type | Does CSRF Need Consideration? |
| --- | --- |
| Session cookie | Yes. |
| Access Token in cookie | Yes, because browsers send cookies automatically. |
| Bearer token in `Authorization` header explicitly attached by client | Lower traditional CSRF risk; XSS/token storage protection is still required. |
| Mixed cookie + Bearer API | Must evaluate all credentials and endpoints. |

Never disable CSRF globally just to make API testing easier. If cookie-authenticated endpoints and Bearer APIs coexist in the same application, separate `SecurityFilterChain` instances by matcher/order and configure CSRF appropriately for each chain.

## 12. Separating `SecurityFilterChain` for API and Browser Routes

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .csrf(csrf -> csrf.disable())
        .sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2.jwt())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain browserChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated())
        .oauth2Login(Customizer.withDefaults())
        .build();
}
~~~

This is an illustrative skeleton. The API chain disables CSRF only if the API genuinely uses no cookie/session authentication. The browser chain retains default CSRF protection appropriate for session/cookie login.

Ensure every request matches a chain with an explicit policy. A chain missing a matcher or having the wrong order can cause endpoints to fall into an unintended policy.

## 13. Controlling Direct Calls in a Service Mesh

~~~text
Orders workload identity
       |
       | mTLS identity: orders-service
       v
Inventory workload
       |
       +-- verifies source workload
       +-- validates user/delegated Access Token
       +-- checks inventory.read
~~~

mTLS authenticates the workload peer and secures transport. It does not by itself prove the end user has permission to read data. If an API requires both service identity and user delegation, check workload identity, subject/delegation, audience, scope/authorities, and tenant/object permissions.

Never use a single shared admin service account across all workloads.

## 14. Trust Proxy Configuration

When an app sits behind a reverse proxy, the framework may need to know the original scheme, host, and client address. Only trust managed proxies:

- The edge proxy strips incoming client-sent forwarded headers.
- The proxy rewrites headers using values it determines itself.
- The backend accepts traffic only from permitted proxies/workloads.
- Forwarded header strategy is configured per deployment.
- Host allowlists and redirect policies do not rely on arbitrary values.

Never configure trust-all-proxies in an environment where direct callers can reach the origin. If the backend still receives direct traffic, callers can craft forwarded headers themselves.

## 15. Multi-Tenant API Boundary

~~~text
Verified token
  sub = user-42
  tenant_id = tenant-A
  aud = orders-api
  scope = orders.read
       |
       v
Orders API
       |
       +-- route scope check
       +-- tenant context from verified principal
       +-- query constrained to tenant-A
       +-- object permission check
       |
       v
Return only tenant-A order
~~~

Principles:

- Only trust the tenant claim after token signature/issuer/audience are verified.
- Never allow request bodies/queries to override the authenticated tenant context.
- Every repository query must enforce tenant constraints per the domain model.
- Check tenant on both read and write paths.
- Never let batch/export/admin endpoints skip tenant filters.
- Service-to-service calls must preserve tenant/delegation context per a verified contract.

If a token lacks a tenant claim while the system has a membership database, resolve membership from the verified subject and enforce permissions in the domain service.

## 16. Error Responses at the API Boundary

| Case | Common Result |
| --- | --- |
| Missing credentials on protected route | 401 |
| Invalid token signature/issuer/audience/expired | 401 |
| Valid token but missing scope | 403 |
| Subject lacks permission on object | 403 or 404 per anti-enumeration policy |
| Issuer/introspection unavailable | Dependency error 5xx/503 per error contract |
| Direct path blocked by network policy | Connection refused/unroutable |

Never return stack traces, signing key details, client secrets, tokens, raw introspection responses, or internal topology to callers. Log correlation IDs and error categories internally; never log the `Authorization` header.

## 17. Testing Bypass Paths

A test suite that only calls endpoints through the Gateway does not prove the backend is safe. You must test directly against the origin or test network configuration to prove that path is blocked.

### 17.1. Test Matrix

| Call Path | Credential / Header | Expectation |
| --- | --- | --- |
| Public gateway, no token | None | 401 on protected routes |
| Public gateway, valid JWT for Orders API | Token `aud=orders-api`, sufficient scope | Allowed if object policy passes |
| Public gateway, token `aud=Inventory API` | Valid token but wrong audience | 401 |
| Public gateway, missing scope | Token with right `aud` | 403 |
| Direct origin, no token | None | Blocked by network or API returns 401 |
| Direct origin, valid token for Orders API | Bearer token | Allowed only if direct origin is a designed path |
| Direct origin, forged `X-Authenticated-User` | Forged header, no token | Not authenticated |
| Gateway path, client sends `X-User: admin` | Forged header | Proxy strips/overwrites; no privilege escalation |
| Forged forwarded headers from direct caller | `X-Forwarded-Host`/IP | Not trusted |
| Tenant A token accessing tenant B order | Valid token, sufficient scope | Denied by object/tenant policy |
| Service token with wrong `aud` | Valid workload mTLS | Denied at resource authorization |
| Token exchange for non-allowlisted resource | Request alters audience | Does not exchange/call downstream |
| CORS disallowed origin | Browser request | Browser cannot read response; API auth remains independent |
| Request without `Origin` | None | Not trusted by default |

### 17.2. Testing Authorization with MockMvc

~~~java
mockMvc.perform(get("/api/orders/42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());

mockMvc.perform(get("/api/orders/42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_inventory.read"))))
    .andExpect(status().isForbidden());
~~~

These are authorization tests with a mock `Authentication`. They do not verify signature or audience decoding. Use signed JWTs and the real Resource Server to test issuer/audience/time validation.

### 17.3. Testing WebFlux with `mockJwt`

~~~java
webTestClient.mutateWith(
        mockJwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")))
    .get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk();
~~~

Like `MockMvc`, the `mockJwt` helper bypasses the real decoder. Test the JWT decoder separately and run integration tests with real `Bearer` headers.

### 17.4. Testing Direct Origin

In integration/environment tests:

1. Call the public hostname through the gateway.
2. Call the private origin/service address from a permitted test workload.
3. Verify the direct path is blocked by network policy if the topology requires gateway-only access.
4. If the direct path is supported, send tokens with missing/wrong audience and confirm the API rejects them itself.
5. Send forged identity headers and confirm they are not trusted.
6. Verify audits/metrics record the appropriate ingress route.

Never use a test targeting only the public gateway URL to conclude the direct origin is unreachable. Check network policies/firewalls/deployment configuration in the actual environment.

## 18. Common Anti-Patterns

| Anti-Pattern | Risk | Mitigation |
| --- | --- | --- |
| Gateway authenticates, backend trusts all internal requests | Direct-origin bypass | Backend verifies tokens/trusted assertions |
| Backend trusts request-sent `X-User`/`X-Roles` | Header spoofing, privilege escalation | Strip and verify proxy assertions |
| One shared audience across all services | Cross-resource token reuse | Dedicated audience per resource boundary |
| Checking only scope, not object | IDOR/BOLA | Tenant/owner/object authorization |
| Using source IP as user identity | Shared NAT/proxy and spoofing | OAuth principal + workload identity |
| Using mTLS to replace all user authorization | Service identity confused with user identity | Check both workload and subject/delegation |
| Letting caller choose issuer/JWKS URL | SSRF and trust injection | Trusted issuer registry |
| Using CORS as authentication | Non-browser callers bypass CORS | Resource Server authentication |
| Disabling CSRF despite cookie auth | Cross-site request forgery | CSRF policy matching credential type |
| Trusting all forwarded headers | Host/IP spoofing | Trust only managed proxies |
| Token relay to any downstream | Credential disclosure / audience mismatch | Relay only matching audience or use token exchange |
| Client credentials representing end user | Incorrect audits and authorization | Explicit delegation/actor model |
| Testing only the gateway route | Misses direct access | Test both gateway and origin/network paths |
| Exposing all health/actuator endpoints publicly | Information disclosure and admin actions | Expose minimally, separate management ingress |

## 19. Design and Implementation Process

1. **Diagram all ingress paths:** public gateway, internal gateway, direct service DNS, load balancers, management ports, and service mesh.
2. **Define resource boundaries:** which API is a resource server, which issuers are trusted, and which audience represents that resource.
3. **Define client classes:** browser, mobile, partner, service workloads, and administrative clients.
4. **Choose credential contracts:** Bearer Access Tokens, workload mTLS, token exchange, or signed internal assertions.
5. **Enforce authentication at the API:** JWT decoder/opaque introspector configured with issuer/resource trust.
6. **Enforce authorization per operation:** route/method scopes and role policies.
7. **Check objects/tenants:** domain services and data access layers enforce ownership/membership.
8. **Restrict networks:** private origins, firewalls/security groups, `NetworkPolicy`, mesh authorization.
9. **Sanitize proxy headers:** strip incoming headers, overwrite at trusted proxies, never trust direct callers.
10. **Configure CORS/CSRF per credential type:** CORS for browsers; CSRF for browser-auto-sent credentials.
11. **Design service-to-service delegation:** appropriate token audiences, least privilege, and actor/subject auditing.
12. **Test bypasses:** gateway, direct origin, forged headers, wrong audience, missing scope, cross-tenant objects, and service identities.
13. **Observe production:** distinguish ingress paths, auth failures, authorization denials, and network rejections.

**Remember:** A gateway is an additional filtering and protection layer. The API must verify tokens and permissions at the resource boundary it protects, even if a direct call path exists. Verify **issuer, audience, lifetime, scopes, tenant, and object permissions**; never trust identity headers or forwarded headers from callers. Network policies/mTLS limit which workloads can connect, while OAuth authorization decides what the caller can do. Testing must cover both the gateway path and direct-origin paths, and authentication system failures must never default to granting access.

## References

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750).
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519).
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068).
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700).
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705).
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693).
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- [Spring Security — Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/index.html).
- [Spring Security — Reactive Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/index.html).
- [Spring Security — Reactive OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html).
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html).
- [OWASP API Security Top 10](https://owasp.org/API-Security/editions/2023/en/0x00-header/).
- [OWASP API1:2023 Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/).
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).
- [OWASP REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html).
