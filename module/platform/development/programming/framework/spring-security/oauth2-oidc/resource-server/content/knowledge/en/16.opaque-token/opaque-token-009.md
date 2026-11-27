# Mapping `scope` from introspection responses to authorities

In a **Spring Security OAuth 2.0/OIDC Resource Server**, an access token does not have to be a JWT that the API can read and verify locally. An Authorization Server (AS) may issue an **opaque access token**: to the Resource Server, it is merely a credential string. To learn whether the token is still active and what permissions were granted to it, the Resource Server calls the **OAuth 2.0 Token Introspection Endpoint** per RFC 7662.

The introspection response typically includes attributes such as `active`, `sub`, `client_id`, `aud`, `exp`, and especially **`scope`**. Spring Security can turn each OAuth scope verified via introspection into a **`GrantedAuthority`** with the default `SCOPE_` prefix. Rules such as `hasAuthority("SCOPE_orders.read")` or `@PreAuthorize("hasAuthority('SCOPE_orders.write')")` therefore work seamlessly with opaque tokens without the API needing to know the token's internal structure.

The crucial point to understand: **`active: true` only indicates that the Authorization Server considers the token active; it does not automatically grant all permissions to every API**. The Resource Server remains responsible for verifying which resource the token is meant for, which scope matches the operation, and whether the caller has permission on the specific business object.

This lesson follows the chain **introspection response → principal → `GrantedAuthority` → authorization** and covers `scope` variations, default configuration, custom mapping, common pitfalls, testing, and operational boundaries.

## 1. The big picture: from opaque token to access permissions

A client holds an access token issued by the Authorization Server and wants to read an order at the Orders API:

```mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant API as Orders Resource Server
    participant AS as Authorization Server
    C->>API: GET /api/orders/123 + Bearer opaque-token
    API->>AS: POST /introspect (token + RS credentials)
    AS->>AS: Validate token and active-state policy
    AS-->>API: active=true, scope="orders.read", aud="orders-api", sub=...
    API->>API: Convert orders.read -> SCOPE_orders.read
    API->>API: Create Authentication with authorities
    API->>API: Check hasAuthority("SCOPE_orders.read")
    API->>API: Check owner/tenant of order 123
    API-->>C: 200 if both authentication and authorization pass
```

Division of responsibilities:

| Component | Responsible for | Should not take over from others |
|---|---|---|
| **Client** | Requesting access tokens with appropriate scopes, sending Bearer credential | Must never self-determine granted scopes |
| **Authorization Server** | Issuing tokens, managing validity, returning introspection metadata | Does not decide permissions on every record in Orders API without a contract |
| **Introspection endpoint** | Telling the Resource Server whether the token is active plus contracted trusted metadata | Not a public endpoint for arbitrary anonymous callers |
| **`OpaqueTokenIntrospector`** | Calling the endpoint, processing the response, building the principal | Does not replace HTTP/domain authorization |
| **`GrantedAuthority`** | Representing permissions in Spring Security's `Authentication` | Carries no inherent OAuth or ownership meaning unless the app defines it |
| **HTTP/method authorization** | Deciding which scopes/authorities may invoke an endpoint | Does not determine record owner or tenant |
| **Business service** | Enforcing resource, tenant, state, and business rules | Never trusts client payload to override verified token metadata |

A token can be valid yet granted only `orders.read`; write requests requiring `orders.write` are still denied. A token carrying `orders.read` still does not automatically allow reading another user's orders.

## 2. Token introspection under RFC 7662

### 2.1. Request to the introspection endpoint

The AS path and authentication mechanism are defined by the system. Example HTTP request under RFC 7662:

```http
POST /oauth2/introspect HTTP/1.1
Host: idp.example.com
Authorization: Basic BASE64_RESOURCE_SERVER_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

token=opaque-value-from-authorization-header
```

This is a **protocol template**, not real credentials. Spring Security normally handles calling the introspection endpoint when configured as an opaque Resource Server; the application does not manually craft HTTP requests in each controller.

In real deployments:

- Call only a trusted introspection endpoint over **HTTPS/TLS**.
- The Resource Server uses a client authentication method permitted by the Authorization Server, such as HTTP Basic with client ID/secret, or another contracted method.
- Protect the client secret using a secret manager or secure configuration; never put it in Git or logs.
- Never place bearer token strings in URLs/query strings or request logs.
- Account for timeouts, network outages, and request volume because introspection can sit on the hot path of every HTTP request.

### 2.2. Active introspection response

Illustrative response:

```json
{
  "active": true,
  "scope": "orders.read orders.write",
  "client_id": "shop-web",
  "token_type": "Bearer",
  "sub": "user-842",
  "aud": ["orders-api"],
  "iss": "https://idp.example.com/realms/shop",
  "iat": 1893456000,
  "exp": 1893459600
}
```

Timestamps are illustrative. Under RFC 7662:

- `active` is the **mandatory** attribute of the response, indicating active status per the AS.
- `scope` is a **space-delimited string of scopes**, matching OAuth 2.0's representation of scopes.
- `client_id`, `sub`, `aud`, `iss`, `exp`, `iat`, `nbf`, and other attributes may appear depending on the AS and metadata disclosure policies.
- Not every AS returns every field to every Resource Server; responses may be filtered per introspection caller.

The `orders.read` and `orders.write` scopes are **values confirmed as granted by the AS**, distinct from the `scope=orders.write` parameter a client originally requested when asking for a token. The Resource Server must base authorization decisions on AS-verified data, not the client's scope request.

### 2.3. Inactive token response

Example:

```json
{
  "active": false
}
```

Under RFC 7662, for an inactive token, the endpoint normally returns only `active: false` without disclosing additional metadata. This prevents an introspector from inferring details about tokens it has no right to inspect.

The Resource Server **must not** build an authenticated principal with permissions from such a token, even if the client sends scopes in a custom header:

```http
Authorization: Bearer invalid-token
X-Scope: orders.write
```

`X-Scope` in this example is caller-controlled input outside the authentication contract; it cannot turn an `active=false` token into one permitted to write.

### 2.4. Introspection does not necessarily mean the token is a "meaningless" string

Opaque Resource Server in Spring Security means **the API authenticates via introspection** instead of verifying a JWT locally with `JwtDecoder`. The underlying credential may be:

- A random reference token for which only the AS holds the corresponding record.
- A JWT where the Resource Server chooses to ask the AS for status/revocation checks.
- A token in a provider-specific format.

Thus, when we say "opaque token," we emphasize **how the Resource Server processes it**, rather than assuming the token cannot contain structured data. If the AS uses JWTs and the introspection endpoint accepts them, the Resource Server can still use the opaque path instead of decoding locally.

## 3. What does `scope` in the introspection response mean?

Scope is an OAuth 2.0 concept: a set of strings representing **the access scope granted to the access token**. The meaning of strings such as `orders.read` and `payments.refund` is agreed upon by the Authorization Server and Resource Server.

Example contract:

| Scope granted by AS | Permitted Orders API function | Default authority |
|---|---|---|
| `orders.read` | View orders the subject is permitted to read | `SCOPE_orders.read` |
| `orders.create` | Create new orders per business policy | `SCOPE_orders.create` |
| `orders.update` | Update valid orders matching owner/tenant | `SCOPE_orders.update` |
| `orders.cancel` | Request order cancellation per state and permission | `SCOPE_orders.cancel` |
| `orders.delete` | Delete resources per policy | `SCOPE_orders.delete` |

These are **hypothetical scope names**. Spring Security does not automatically invent `orders.cancel` just because an endpoint uses POST or a resource has a `CANCELLED` status.

### 3.1. Scopes are case-sensitive strings

Under OAuth, scope tokens are case-sensitive values. The following values are **not automatically equivalent**:

```text
orders.read
Orders.Read
orders.READ
```

Spring Security matches `GrantedAuthority#getAuthority()` against the exact string required by the rule. If a token was granted `Orders.Read`, the default converter may create `SCOPE_Orders.Read`, and `hasAuthority("SCOPE_orders.read")` will not match.

Never automatically lowercase every scope unless the issuer and API contract explicitly specify that normalization; inconsistent normalization can grant unintended access.

### 3.2. Scopes have no automatic hierarchy

OAuth does not define:

```text
orders.write -> implies orders.read
orders.admin -> implies all orders.*
```

Spring Security also does not interpret dots in scope names as parent-child hierarchies. If an API requires `SCOPE_orders.read`, a token holding only `SCOPE_orders.write` does not satisfy it automatically. To allow either permission, write the policy explicitly, e.g. `hasAnyAuthority("SCOPE_orders.read", "SCOPE_orders.write")`.

### 3.3. Scope differs from audience, subject, and tenant

A token might have:

```json
{
  "active": true,
  "scope": "orders.read",
  "sub": "user-842",
  "aud": ["payments-api"],
  "iss": "https://idp.example.com/realms/shop"
}
```

Even though the order-reading scope is present, the Orders API **must not** ignore that the token is intended for `payments-api`. Audience checking answers "which API is the token meant for?"; scope answers "what category of action is allowed?".

Similarly:

- `sub` identifies the subject per AS semantics, not automatically an interactive user.
- `client_id` identifies the client granted the token, not automatically an admin role.
- `tenant_id` (extension claim) requires a trusted source and its own business policy.
- `scope` does not list every individual order ID the subject may view, unless a system builds an extremely specific contract.

## 4. Spring Security's default mapping: `scope` → `SCOPE_...`

In a Spring Security Servlet Resource Server using opaque-token introspection, the typical processing path is:

```mermaid
flowchart TD
    A["Authorization: Bearer opaque-token"] --> B["BearerTokenAuthenticationFilter"]
    B --> C["OpaqueTokenAuthenticationProvider"]
    C --> D["OpaqueTokenIntrospector"]
    D --> E["HTTPS introspection endpoint"]
    E --> F{"Is active true and<br/>response valid?"}
    F -->|"No"| X["Authentication failed / 401"]
    F -->|"Yes"| G["OAuth2AuthenticatedPrincipal<br/>attributes + authorities"]
    G --> H["BearerTokenAuthentication"]
    H --> I["SecurityContextHolder"]
    I --> J{"hasAuthority('SCOPE_orders.read')?"}
    J -->|"No"| Y["Authorization failed / 403"]
    J -->|"Yes"| K["Controller / domain authorization"]
```

Spring Security's default opaque-token support **extracts `scope` from the introspection response and maps it to authorities prefixed with `SCOPE_`**. For the response:

```json
{
  "active": true,
  "scope": "orders.read orders.write"
}
```

we expect the request's `Authentication` to carry:

```text
GrantedAuthority("SCOPE_orders.read")
GrantedAuthority("SCOPE_orders.write")
```

These authorities are Spring Security objects, not claims emitted by the AS with a `SCOPE_` prefix already attached. The AS only needs to return raw scopes per contract:

```text
orders.read orders.write
```

**Never manually prepend `SCOPE_` to scopes issued by the AS** when using default mapping. If the AS returns `SCOPE_orders.read`, default mapping can produce `SCOPE_SCOPE_orders.read`, and `hasAuthority("SCOPE_orders.read")` will fail to match.

### 4.1. One scope equals one authority

Example response:

```json
{
  "active": true,
  "scope": "orders.read orders.create reports.read"
}
```

Default mapping creates three authorities:

```text
SCOPE_orders.read
SCOPE_orders.create
SCOPE_reports.read
```

An endpoint requiring only `SCOPE_orders.read` does not grant `reports.read`, and vice versa. Having multiple authorities in `Authentication` merely feeds authorization rules; there is no mechanism granting access to all routes just because a token carries at least one scope.

### 4.2. Empty or absent scope

Response:

```json
{
  "active": true,
  "sub": "user-842"
}
```

If `scope` is absent and the introspector assigns no custom authorities, `Authentication` may **be authenticated** yet **lack `SCOPE_orders.read`**. In that case:

```java
.hasAuthority("SCOPE_orders.read")
```

must deny access. Never add `SCOPE_orders.read` automatically just because `active=true` to "make the API work." If the API requires every access token to carry scopes, add a contract check and reject scopeless tokens.

### 4.3. String `scope`, array `scp`, and provider variations

Under RFC 7662, `scope` is a **space-separated string of scope values**. Example:

```json
{
  "active": true,
  "scope": "orders.read orders.update"
}
```

Some providers return instead:

```json
{
  "active": true,
  "scp": ["orders.read", "orders.update"]
}
```

or:

```json
{
  "active": true,
  "permissions": ["order:read", "order:write"]
}
```

The latter two variants **are not part of RFC 7662's default mapping expectations**. Never assume `OpaqueTokenIntrospector` automatically understands `scp`, `roles`, or `permissions` from any IdP. When using other fields, the team must:

1. Confirm the field is verified by the IdP and returned only to authorized Resource Servers.
2. Agree on semantics, formatting, and allowed values.
3. Choose an appropriate custom introspector/authority mapper.
4. Verify the actual resulting `GrantedAuthority` instances rather than guessing from field names.

Avoid turning an arbitrary response claim into a high-privilege role unless it is explicitly contracted as an authorization source.

## 5. Configuring an opaque Resource Server in Spring Boot

Example using Spring Boot 3.x / Spring Security Servlet:

```groovy
// build.gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

```yaml
# application.yml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: "${INTROSPECTION_CLIENT_SECRET}"
```

`INTROSPECTION_CLIENT_SECRET` must be provided via secure deployment configuration; never write real secrets into committed files. The URL is illustrative and must be replaced with the AS's actual endpoint.

When this configuration is supported by Spring Boot and not overridden by a custom bean, Boot auto-configures an appropriate `OpaqueTokenIntrospector`. Spring Security uses that introspector in the `opaqueToken()` branch to validate Bearer credentials.

Authorization example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            // Illustrative only for pure Bearer-header APIs not using
            // cookies/sessions for state-changing requests.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/health")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.create")
                .requestMatchers(HttpMethod.PUT, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.update")
                .requestMatchers(HttpMethod.DELETE, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.delete")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(Customizer.withDefaults()))
            .build();
    }
}
```

How it works:

1. `BearerTokenAuthenticationFilter` extracts the token from `Authorization: Bearer ...`.
2. `OpaqueTokenAuthenticationProvider` invokes `OpaqueTokenIntrospector`.
3. The introspector sends the token to the trusted endpoint and evaluates the response per library behavior.
4. The returned principal holds attributes and authorities; scopes map to `SCOPE_...` by default.
5. Spring Security builds `BearerTokenAuthentication` and stores it in `SecurityContext`.
6. `authorizeHttpRequests` checks authorities by HTTP method/path.
7. The business service checks permissions for the specific order.

**Note:** `csrf().disable()` here makes sense only for APIs genuinely authenticating via client-sent Bearer headers rather than browser-attached cookies/sessions. When an app handles cookie logins or browser state-changing requests via another mechanism, design CSRF protection separately.

### 5.1. HTTP rules do not call introspection themselves

The rule:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
```

only checks authorities already present on `Authentication`. It **does not send the token to the IdP itself**. Sending the token and constructing `Authentication` is handled by `opaqueToken()` and `OpaqueTokenIntrospector`. If the chain uses `jwt()`, it routes tokens through `JwtDecoder` instead of introspection unless explicitly customized.

### 5.2. Never enable both JWT and opaque simultaneously just to "see which token works"

Spring Security has two primary Bearer authentication paths for Resource Server: JWT decoder and opaque introspector. Choose **a strategy matching the token contract**; never assume enabling both means the framework safely falls back when one parser fails.

If an API needs multiple token profiles, route them through a controlled authentication design that preserves issuer/audience/token-type checks in each branch. A "if JWT fails, try a looser introspection branch" fallback can introduce downgrade or cross-protocol confusion bugs.

## 6. `BearerTokenAuthentication` and readable objects

With opaque tokens, the principal is normally an `OAuth2AuthenticatedPrincipal` holding introspection attributes and authorities. After authentication, the `Authentication` is typically `BearerTokenAuthentication`.

Related types:

```text
OpaqueTokenIntrospector
    |
    v
OAuth2AuthenticatedPrincipal
  - getName()
  - getAttributes()
  - getAttribute(name)
  - getAuthorities()
    |
    v
BearerTokenAuthentication
  - getPrincipal()
  - getAuthorities()
  - getCredentials()
  - getName()
```

Application code generally needs only `Authentication` or `@AuthenticationPrincipal OAuth2AuthenticatedPrincipal`, rather than coupling to a specific introspector implementation class.

### 6.1. Reading authorities in a controller

```java
import java.util.List;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CurrentAccessController {

    @GetMapping("/api/me/authorities")
    public List<String> currentAuthorities(Authentication authentication) {
        return authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();
    }
}
```

If introspection returns `scope: "orders.read orders.update"`, the illustrative API output might be:

```json
[
  "SCOPE_orders.read",
  "SCOPE_orders.update"
]
```

This is an illustrative/diagnostic endpoint. In production, exposing the full permission list is not always advisable; if provided, protect the route properly and avoid leaking other sensitive introspection metadata.

### 6.2. Reading attributes from `OAuth2AuthenticatedPrincipal`

```java
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping("/api/me")
public Map<String, String> currentActor(
        @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {

    String subject = principal.getAttribute("sub");
    String clientId = principal.getAttribute("client_id");

    return Map.of(
        "name", principal.getName(),
        "subject", subject != null ? subject : "",
        "clientId", clientId != null ? clientId : ""
    );
}
```

This example picks only a few fields for illustration; never return raw `principal.getAttributes()` as it may hold sensitive token metadata. Actual Java attribute types depend on the introspection endpoint and library conversion. `Authentication.getName()` or `principal.getName()` is not an email by default, and for client credentials it should not be treated as a human user.

**JWT vs. opaque:** `@AuthenticationPrincipal Jwt` fits the JWT branch, yet does not work when `BearerTokenAuthentication` holds an `OAuth2AuthenticatedPrincipal`. To share business code across both, map both principal types into a verified internal actor type.

### 6.3. `GrantedAuthority` in `Authentication` does not alter token metadata

If an authority converter adds `ROLE_ORDER_MANAGER`, the token and introspection response remain unchanged. Converters only build **in-memory permission representations inside Spring Security**; they do not ask the AS to upgrade scopes, modify `scope`, or issue new credentials to the client.

## 7. `hasAuthority`, `hasRole`, and permission boundaries

Spring Security matches the string in `GrantedAuthority#getAuthority()` against rules. For example:

```java
.hasAuthority("SCOPE_orders.read")
```

looks for the exact authority `SCOPE_orders.read`.

Whereas:

```java
.hasRole("ADMIN")
```

looks for `ROLE_ADMIN` per Spring Security's role-prefix convention. Thus:

```java
.hasRole("orders.read")            // looks for ROLE_orders.read
.hasAuthority("SCOPE_orders.read") // checks default OAuth scope mapping
```

These two checks are not equivalent. When checking default-mapped OAuth scopes, `hasAuthority("SCOPE_...")` is the clear, explicit expression.

### 7.1. Never mistake `scope` for `role`

An IdP might emit:

```json
{
  "active": true,
  "scope": "orders.read",
  "roles": ["ADMIN"]
}
```

These are two separate data sources. `roles` does not automatically become `ROLE_ADMIN` in default opaque support unless the application provides an explicit mapper. If an extension maps roles, verify:

- Was the `roles` claim genuinely asserted by the Authorization Server for this Resource Server?
- Which domain/tenant does this role belong to?
- Does `ADMIN` mean admin across the entire API or only within one client/realm?
- Should it be combined with an OAuth scope for sensitive operations?

Never write a rule "any user with role `ADMIN` in the IdP may refund all payments" unless the app explicitly defines and isolates that boundary.

### 7.2. Object-level permissions still must be checked

Token carries:

```json
{
  "active": true,
  "scope": "orders.read",
  "sub": "user-842",
  "tenant_id": "tenant-a"
}
```

Database:

```text
Order ORD-123:
  owner=user-842
  tenant=tenant-a

Order ORD-999:
  owner=user-901
  tenant=tenant-b
```

`SCOPE_orders.read` authorizes **the read operation category**, not access to every order. The service must verify owner, tenant, and current status. Having `hasAuthority` without object-level checks exposes the API to BOLA (*Broken Object Level Authorization*).

## 8. Method security using the same authorities

After enabling method security:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
```

you can write:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class OrderApplicationService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public OrderDto readOrder(String id) {
        return readWithBusinessChecks(id);
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.update')")
    public OrderDto updateOrder(String id, UpdateOrderCommand command) {
        return updateWithBusinessChecks(id, command);
    }
}
```

`OrderDto`, `UpdateOrderCommand`, and internal helper methods are illustrative domain components. `@PreAuthorize` is evaluated before the method's business logic runs (when invoked through the proxy), yet the service must still check owner/tenant and order state.

`@EnableMethodSecurity` does not care whether those authorities came from a JWT, an opaque token, or another mechanism: it reads `Authentication` from `SecurityContextHolder`. Therefore, the same `@PreAuthorize` rules work across both branches as long as **authority mappings and semantics are designed consistently**.

**Proxy note:** with standard Spring AOP proxies, self-invocation can bypass the method-security interceptor. Never treat annotations as a guarantee for internal calls unless they pass through the proxy or a domain authorization boundary.

## 9. Customizing introspection while preserving default scopes

Suppose the AS returns extra metadata such as:

```json
{
  "active": true,
  "scope": "orders.read",
  "permissions": ["order:approve"],
  "sub": "manager-842",
  "aud": ["orders-api"]
}
```

The application wants to keep `SCOPE_orders.read` and add an internal authority `PERMISSION_order:approve` when the AS confirms an approved permission.

Spring Security lets you provide a custom **`OpaqueTokenIntrospector`**. A clean pattern is **delegating to the standard introspector**, preserving the principal and authorities it verified, and adding constrained mappings.

### 9.1. Wrapping the standard introspector instead of replacing all processing

Java example using `NimbusOpaqueTokenIntrospector` (a common implementation in Spring Security 6.x; exact class/builder may vary by version):

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

public final class PermissionEnrichingIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;

    public PermissionEnrichingIntrospector(OpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        // Delegate handles verifying the token through the AS.
        OAuth2AuthenticatedPrincipal principal = delegate.introspect(token);

        // Preserve SCOPE_... authorities from standard introspection.
        Collection<GrantedAuthority> authorities =
            new ArrayList<>(principal.getAuthorities());

        // Accept only permissions defined by the contract.
        Object raw = principal.getAttribute("permissions");
        if (raw instanceof Collection<?> permissions) {
            for (Object permission : permissions) {
                if ("order:approve".equals(permission)) {
                    authorities.add(new SimpleGrantedAuthority(
                        "PERMISSION_order:approve"));
                }
            }
        }

        return new DefaultOAuth2AuthenticatedPrincipal(
            principal.getName(),
            principal.getAttributes(),
            List.copyOf(authorities)
        );
    }
}
```

Key characteristics:

1. **Delegate introspection first**; never read scopes from an unverified raw token.
2. **Preserve `principal.getAuthorities()`** so `SCOPE_orders.read` is not lost.
3. Map only the specific `order:approve` permission rather than turning arbitrary values into admin privileges.
4. Do not mutate attributes, identity, or token state at the Authorization Server.
5. Return an `OAuth2AuthenticatedPrincipal` suitable for `BearerTokenAuthentication`.

This is an **illustrative example of mapping from trusted IdP metadata**, not advice to grant order-approval rights for any AS. Before deploying, the contract must confirm that `permissions` in the introspection response is a trusted, AS-governed source scoped to the right audience/tenant.

### 9.2. Configuring the delegate and wrapper

Example constructing the introspector from configuration:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.introspection.NimbusOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

@Configuration
public class IntrospectionConfiguration {

    @Bean
    OpaqueTokenIntrospector opaqueTokenIntrospector(
            @Value("${app.security.introspection-uri}") String uri,
            @Value("${app.security.introspection-client-id}") String clientId,
            @Value("${app.security.introspection-client-secret}") String secret) {

        OpaqueTokenIntrospector delegate =
            new NimbusOpaqueTokenIntrospector(uri, clientId, secret);

        return new PermissionEnrichingIntrospector(delegate);
    }
}
```

```yaml
app:
  security:
    introspection-uri: https://idp.example.com/oauth2/introspect
    introspection-client-id: orders-resource-server
    introspection-client-secret: "${INTROSPECTION_CLIENT_SECRET}"
```

This snippet uses the `NimbusOpaqueTokenIntrospector` constructor available in common Spring Security 6.x releases; when using a newer release or switching to `SpringOpaqueTokenIntrospector`, pick the API/builder supported by that version. The **delegate + wrapper** pattern does not depend on a specific class name.

When an application declares an `OpaqueTokenIntrospector` bean, Spring Boot generally yields auto-configuration of the introspector to that bean. Verify that the security chain actually uses your custom bean:

```java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        OpaqueTokenIntrospector introspector) throws Exception {

    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2
            .opaqueToken(opaque -> opaque.introspector(introspector)))
        .build();
}
```

This example wires the explicit introspector into `SecurityFilterChain`; imports and other security settings follow your real application. If the app has multiple chains, verify which chain and introspector handle each route.

### 9.3. When changing all scopes to a different prefix

Suppose the IdP returns:

```json
{
  "active": true,
  "scope": "orders.read"
}
```

and the application deliberately creates `RIGHT_orders.read` instead of `SCOPE_orders.read`. This requires a custom mapping, and authorization rules must match:

```java
.hasAuthority("RIGHT_orders.read")
```

If you change the converter yet forget to update `hasAuthority("SCOPE_orders.read")`, requests with valid tokens will return 403 because the authority strings do not match. Normally, **keeping the `SCOPE_` prefix is the clearest, least surprising choice** for Resource Servers.

Never alter prefixes to mask an IdP failing to return scopes; prefixes are a Spring Security representation detail, not proof of granted permissions.

## 10. IdP returns `scp` or another format: contract-explicit mapping

Some providers do not return `scope` per RFC 7662, returning `scp` as a list instead. Example:

```json
{
  "active": true,
  "scp": ["orders.read", "orders.update"],
  "aud": ["orders-api"]
}
```

If the default introspector maps only `scope`, `Authentication` may lack `SCOPE_orders.read` even though `scp` is present. A custom wrapper can read `scp` **after introspection succeeds** and create the matching authorities.

Conceptual pattern:

```java
Object rawScp = principal.getAttribute("scp");
Collection<GrantedAuthority> authorities =
    new ArrayList<>(principal.getAuthorities());

if (rawScp instanceof Collection<?> scopes) {
    for (Object item : scopes) {
        if (item instanceof String scope
                && (scope.equals("orders.read")
                    || scope.equals("orders.update"))) {
            authorities.add(new SimpleGrantedAuthority("SCOPE_" + scope));
        }
    }
}
```

This snippet belongs inside an `OpaqueTokenIntrospector` wrapper that already called `delegate`, and applies only when the trusted AS actually uses `scp` with scope semantics. `principal` here is the result of `delegate.introspect(token)`, **not** client-supplied JSON.

### 10.1. Avoid blindly merging scopes from multiple claims

If the AS returns both simultaneously:

```json
{
  "active": true,
  "scope": "orders.read",
  "scp": ["orders.delete"]
}
```

you must know:

- Which claim is authoritative?
- Do both claims share the same meaning or serve different contexts?
- Which token profile introduced `scp`?
- Is **combining** permissions from both sources actually allowed?

Blindly merging them could let a field not intended for API permissions accidentally grant `SCOPE_orders.delete`. Merge only when the AS and API explicitly specify the semantics; otherwise choose one controlled source and reject inconsistent responses per policy.

### 10.2. When `scope` itself is an array in the `scope` field

Some AS implementations return:

```json
{
  "active": true,
  "scope": ["orders.read", "orders.write"]
}
```

This is not the RFC 7662 string representation of `scope`. Do not assume every introspector implementation accepts or normalizes it. You can:

- Adjust the AS configuration to return the standard string.
- Use a client/wrapper supporting that specific format with strict constraints.
- Reject non-conforming responses if your system requires strict compliance.

Never convert arbitrary JSON arrays into authorities without validating types, allowed values, and audience.

### 10.3. Scopes with spaces, commas, and colons

In a standard response:

```json
{ "scope": "orders.read orders.write" }
```

**Spaces** delimit scope tokens. `orders.read` and `orders.write` are two values; the dots are part of the scope names.

The response:

```json
{ "scope": "orders.read,orders.write" }
```

is not two comma-separated scopes under RFC 7662 representation; if an IdP uses commas, write explicit parsing rules rather than assuming the default converter splits on commas. Conversely, a scope such as `orders:read` is completely valid as **a single scope name** if agreed by AS and API.

## 11. Audience and issuer: an active scope is not enough to trust the token

Suppose Orders API and Payments API share an Authorization Server. Introspection returns:

```json
{
  "active": true,
  "iss": "https://idp.example.com/realms/shop",
  "aud": ["payments-api"],
  "scope": "orders.read",
  "sub": "user-842"
}
```

Orders API must still reject this under the audience contract. **An access token that is active and happens to carry a scope matching Orders API's naming does not become a token intended for Orders API.**

### 11.1. Difference between JWT decoder and opaque introspector

With JWTs, apps typically use `JwtValidators.createDefaultWithIssuer(...)` and an audience validator. With opaque introspection, the API receives metadata from the AS; checking `aud`, `iss`, timestamps, and token type depends on **the introspection contract and implementation**.

Never assume a custom `OpaqueTokenIntrospector` automatically applies `spring.security.oauth2.resourceserver.jwt.issuer-uri` or `jwt.audiences`. Those belong to JWT decoder configuration and do not automatically apply to the opaque introspection chain.

If the Resource Server requires `aud=orders-api`, you need:

- The AS/introspection endpoint verifying that tokens are only introspectable for the right resource; or
- The Resource Server validating `aud` from trusted metadata per contract; or
- Both combined per policy.

If the AS omits audience while the API needs audience binding, **update the contract with the AS** rather than dropping the audience check just to let requests succeed.

### 11.2. Audience-checking wrapper

Example logic checking audience after introspection:

```java
import java.util.Collection;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

public final class AudienceCheckingIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;
    private final String requiredAudience;

    public AudienceCheckingIntrospector(
            OpaqueTokenIntrospector delegate,
            String requiredAudience) {
        this.delegate = delegate;
        this.requiredAudience = requiredAudience;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        OAuth2AuthenticatedPrincipal principal =
            delegate.introspect(token);

        Object rawAudience = principal.getAttribute("aud");
        boolean allowed =
            (rawAudience instanceof String value
                && requiredAudience.equals(value))
            || (rawAudience instanceof Collection<?> values
                && values.contains(requiredAudience));

        if (!allowed) {
            throw new BadOpaqueTokenException(
                "Introspected token audience is not accepted");
        }
        return principal;
    }
}
```

This assumes the AS can return `aud` as a string or collection; the logic **fails closed** if audience is missing or mismatches. In practice, check the exact audience URI/identifier per contract, token type/issuer, and other critical claims. `BadOpaqueTokenException` signals an unacceptable token in the introspection branch so the framework handles it as an authentication failure.

Notice that the code checks audience **after** the delegate has authenticated the token through the AS. Never extract `aud` from a raw opaque token string or run a JWT parser on the string to trust unverified claims.

### 11.3. Client credentials do not always have a user subject

For a token issued to a backend service:

```json
{
  "active": true,
  "client_id": "nightly-order-job",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
```

The AS may omit `sub` or not give it interactive-user semantics, depending on token profile and protocol. Model the actor as a **service principal/client identity** for client credentials, rather than assuming "no `sub` means anonymous" or "`client_id` with read scope can view every tenant's orders."

## 12. Preserving business authorization after authority mapping

After introspection and mapping, the controller/service receives an `Authentication` carrying contract-trusted authorities. Yet the business service must still enforce object-level permissions.

Suppose the token yields:

```json
{
  "active": true,
  "scope": "orders.read",
  "sub": "user-842",
  "iss": "https://idp.example.com/realms/shop",
  "tenant_id": "tenant-a",
  "aud": ["orders-api"]
}
```

An internal actor:

```java
public record CurrentActor(
    String issuer,
    String subject,
    String tenantId
) {}
```

Example service method called after HTTP authority checks:

```java
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;

public OrderDto readOrder(Authentication authentication, String orderId) {
    OAuth2AuthenticatedPrincipal principal =
        (OAuth2AuthenticatedPrincipal) authentication.getPrincipal();

    CurrentActor actor = new CurrentActor(
        principal.getAttribute("iss"),
        principal.getAttribute("sub"),
        principal.getAttribute("tenant_id")
    );

    Order order = repository.findById(orderId)
        .orElseThrow(OrderNotFoundException::new);

    boolean sameTenant = order.getTenantId().equals(actor.tenantId());
    boolean isOwner =
        order.getOwnerIssuer().equals(actor.issuer())
        && order.getOwnerSubject().equals(actor.subject());

    if (!sameTenant || !isOwner) {
        throw new AccessDeniedException("Order access denied");
    }
    return mapper.toDto(order);
}
```

`Order`, `OrderDto`, `repository`, `mapper`, and the exceptions are illustrative domain components. In a real application, encapsulate principal-to-actor conversion in a safe adapter that handles missing claims/principal types and accepts metadata only from a trusted introspection endpoint.

Never use a client-supplied request body or header such as `X-Tenant-ID` to **replace** the authenticated tenant. If a client may select an active tenant, verify the chosen tenant is actually within the principal's authorized set per contract.

### 12.1. Enforcing permissions directly in queries

In multi-tenant APIs, instead of loading any order and checking afterward:

```java
repository.findByIdAndOwnerIssuerAndOwnerSubjectAndTenantId(
    orderId,
    actor.issuer(),
    actor.subject(),
    actor.tenantId());
```

Actor-scoped queries prevent accidentally loading another user's row. Either way, `SCOPE_orders.read` only blocks ungranted operation types; owner/tenant checks are separate **business authorization**.

### 12.2. Scopes do not update themselves when permissions change

Depending on the AS, introspection can reflect revoked tokens faster than offline JWT verification. Even when the response stays `active=true`, permissions on an order in the database may have changed since the token was issued.

When business state changes over time (ownership transfer, order locked, account suspended), the service must rely on **authoritative state at the time of the operation**, not solely a previously issued claim.

## 13. 401, 403, and `insufficient_scope`

Distinguish two failure layers:

| Scenario | Rejected at layer | Common HTTP outcome |
|---|---|---|
| No Bearer token on protected route | Authentication | 401 |
| Introspection returns `active:false` | Authentication | 401 |
| Introspection endpoint fails token auth | Authentication | 401, depending on error type |
| Token active yet audience invalid per policy | Authentication/token contract | 401 |
| Token active, scope only `orders.read`, POST needs `orders.create` | Authorization | 403 |
| Token active, right scope, user does not own order | Business authorization | 403 or 404 per policy |
| Introspection endpoint unreachable (timeout/5xx) | Auth system lacks trusted data | Must never auto-allow; status/error per fail-closed design |

Under RFC 6750 Bearer tokens, when required scopes are missing, the response may contain:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.create"
```

Spring Security provides handlers for Bearer authentication/access-denied; exact headers and bodies depend on configuration and case. Never assume every 403 includes all fields shown in the example, and never leak raw tokens/secrets in errors.

### 13.1. Active token with no scopes is not an all-powerful token

Suppose the AS returns:

```json
{
  "active": true,
  "sub": "user-842"
}
```

The Resource Server may authenticate the principal yet find no `SCOPE_orders.read`, leading to 403 on routes requiring that scope. If the contract mandates that every token carry scopes, treat responses missing `scope` as a token profile violation and reject early via a custom introspector. Align the policy with the AS and avoid a "fallback grant read" hack.

### 13.2. Network failure during introspection: never synthesize authorities

Anti-pattern:

```java
// DO NOT DO THIS: fallback granting authorities when introspection fails.
try {
    return introspector.introspect(token);
} catch (Exception unavailable) {
    return new DefaultOAuth2AuthenticatedPrincipal(
        "fallback-user",
        Map.of(),
        List.of(new SimpleGrantedAuthority("SCOPE_orders.read")));
}
```

If the AS temporarily fails to respond, the API has no proof the token is still active. Fabricating a principal with `SCOPE_orders.read` could grant access to revoked or forged tokens. The safe behavior is **fail closed**, with timeouts and proper operational error reporting.

Policy-driven caching of introspection results may be considered, yet that is a **deliberate trust-window and revocation trade-off**, not inventing authorities out of thin air.

## 14. Operations: performance, caching, and revocation timing

With introspection, every request can trigger a trip to the AS if uncached, affecting latency, load, and fault tolerance.

### 14.1. Benefits and trade-offs

| Approach | Benefit | Trade-off |
|---|---|---|
| Introspect every request | Generally reflects latest AS token state quickly | Adds network/latency and AS dependency |
| Short-lived introspection cache | Cuts load and latency | Newly revoked tokens remain active in cache until expiry |
| Local JWT signature verification | Minimal network dependency once keys are loaded; scales easily | Revocation state does not auto-update if checking only signature/claims |
| Overly long permission cache | Good steady-state throughput | Authorities/tenant/scopes go stale and stay allowed past revocation |

If caching is used, define:

- Cache keyed by **actual token** without logging raw tokens; if hashing keys, choose a design matching sensitivity and token predictability.
- Never cache `active=true` past the token's `exp` (if present) or revocation policy.
- A short negative TTL for `active=false` may reduce load, though policy must account for token issuance/propagation timing.
- Are cached responses and sensitive attributes protected in memory/cache stores?
- Once the AS revokes a token, how soon do all instances stop accepting it?
- During a network outage, does the system use cached metadata still valid under policy or fail closed?

Do not assume `OpaqueTokenIntrospector` in every Spring Security version caches introspection results automatically with identical TTLs. Custom caching must be explicitly configured and operated.

### 14.2. Authenticated principals must not be stored across requests

`SecurityContextHolder` normally scopes `Authentication` to the current request/thread. Never store a `BearerTokenAuthentication` or authority collection in a static/singleton field and reuse it across subsequent requests.

In a stateless bearer API, every request must be authenticated by its current credential (or a policy-valid cache entry), then checked by HTTP authorization. One user holding two access tokens with different scopes can have **different authorities on each request**, even with the same `sub`.

### 14.3. Never log raw tokens

A Bearer token is a replayable credential if leaked. Never log:

```text
Authorization: Bearer opaque-secret-token-...
token=opaque-secret-token-...
client_secret=...
```

Instead, log non-sensitive operational metadata such as correlation ID, configured introspection endpoint, latency, upstream HTTP status, sanitized authentication/authorization outcomes, and permitted internal identifiers.

Introspection responses can contain identity info, emails, tenants, or roles; never dump entire JSON responses or `principal.getAttributes()` into logs.

### 14.4. Trust boundaries of the introspection endpoint

`active:true` is trustworthy when:

1. The Resource Server calls **the trusted configured AS endpoint** over TLS.
2. Resource Server authentication toward the AS is protected.
3. The response comes over that trusted connection and passes library format validation.
4. The AS returns only trusted metadata to authorized Resource Servers.
5. Audience/issuer/token-type/scope and mandatory policies are enforced per contract.

If a proxy or custom wrapper substitutes responses without verifying the data source, all downstream authority mapping becomes a privilege escalation vulnerability. Never treat a client-sent `scope` header or form field as equivalent to `scope` returned by the AS.

## 15. Testing scope mapping and HTTP authorization

To verify the system thoroughly, separate:

1. **Introspection contract tests:** HTTP responses from the AS are parsed properly; `active`, `scope`, `aud`, and errors are handled.
2. **Mapping tests:** the post-introspection principal carries the right authorities, including `SCOPE_` prefixes.
3. **Authorization tests:** HTTP/method rules enforce the right scopes; missing scopes are denied.
4. **Business authorization tests:** owner/tenant and data state are enforced.

### 15.1. Unit tests for a custom authority wrapper

An illustrative test verifying **preserving default scopes while adding a permission**:

```java
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

import static org.assertj.core.api.Assertions.assertThat;

class PermissionEnrichingIntrospectorTest {

    @Test
    void preservesScopeAndAddsWhitelistedPermission() {
        OpaqueTokenIntrospector stub = token ->
            new DefaultOAuth2AuthenticatedPrincipal(
                "user-842",
                Map.of(
                    "sub", "user-842",
                    "scope", "orders.read",
                    "permissions", List.of("order:approve", "unknown-value")
                ),
                List.of(new SimpleGrantedAuthority("SCOPE_orders.read"))
            );

        OpaqueTokenIntrospector decorated =
            new PermissionEnrichingIntrospector(stub);

        OAuth2AuthenticatedPrincipal principal =
            decorated.introspect("test-token");

        assertThat(principal.getAuthorities())
            .extracting(authority -> authority.getAuthority())
            .contains(
                "SCOPE_orders.read",
                "PERMISSION_order:approve")
            .doesNotContain("PERMISSION_unknown-value");
    }
}
```

This test proves **the wrapper's logic**, not that the AS actually returns standard `scope` or that a token has `active:true`. Because the stub already returned `SCOPE_orders.read`, the test does not exercise default mapping from an HTTP introspection response. Separate integration tests are needed for the delegate/HTTP layer.

### 15.2. Testing realistic introspection responses

You can run a mock HTTP server for the introspection endpoint in tests, pointing `NimbusOpaqueTokenIntrospector` or your active implementation to that endpoint. Test responses:

| Mock introspection response | What to verify |
|---|---|
| `{"active":true,"scope":"orders.read"}` | Principal has `SCOPE_orders.read`, not `SCOPE_orders.write` |
| `{"active":true,"scope":"orders.read orders.write"}` | Both authorities present accurately |
| `{"active":true}` | Does not invent scope authorities |
| `{"active":false}` | No authenticated principal, token rejected |
| `{"active":true,"aud":["payments-api"],"scope":"orders.read"}` | Custom audience policy rejects for Orders API |
| `{"active":true,"scp":["orders.read"]}` | Mapped per contract only if custom mapper is configured |
| HTTP 401 from AS due to bad client credentials | Authentication/introspection fails, never falls back to granting access |
| Endpoint timeout/5xx | Never treats token as active without trusted proof |

The exact client-facing HTTP status during an AS outage depends on how the API handles infrastructure failures. The security invariant is **never granting permissions to an unverified token**.

### 15.3. Testing HTTP routes requiring exact authorities

Spring Security Test can simulate `Authentication` to test the authorization layer in isolation:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.opaqueToken;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrdersScopeAuthorizationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void allowsReadAuthority() throws Exception {
        mockMvc.perform(get("/api/orders/ORD-123")
            .with(opaqueToken().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isOk());
    }

    @Test
    void rejectsMissingReadAuthority() throws Exception {
        mockMvc.perform(get("/api/orders/ORD-123")
            .with(opaqueToken().authorities(
                new SimpleGrantedAuthority("SCOPE_other.read"))))
            .andExpect(status().isForbidden());
    }
}
```

This example assumes the test context includes the controller and data needed for GET to return 200 when authorized; business policy may deny or return 404 depending on fixtures. `opaqueToken().authorities(...)` is a Spring Security Test request post-processor that **simulates a principal/authorities** without sending a real request to the AS. Thus, it does not prove the introspector actually maps `scope` from HTTP responses.

To test the entire pipeline, send a Bearer token in the request against a mock introspection endpoint or a test double at the right boundary, confirming introspector selection, `active` handling, and authority mapping.

### 15.4. Testing sufficient permissions per HTTP method

| Request | Scope returned by introspection | Expected permission |
|---|---|---|
| GET `/api/orders/123` | `orders.read` | HTTP scope check passes |
| GET `/api/orders/123` | `orders.write` | Not allowed if API strictly requires read |
| POST `/api/orders` | `orders.create` | HTTP scope check passes |
| POST `/api/orders` | `orders.read` | Denied due to missing create |
| PUT `/api/orders/123` | `orders.update` | HTTP scope check passes |
| DELETE `/api/orders/123` | `orders.update` | Denied due to missing delete |
| GET `/api/orders/999` | `orders.read` but wrong tenant | Denied by domain authorization |
| Any protected route | `active:false` | Rejected at authentication before authorization |

"Passes HTTP scope check" does not guarantee the controller returns 200/201; payload validation, ownership, and business rules still apply.

## 16. Common pitfalls and how to spot them

| Symptom | Possible cause | How to resolve |
|---|---|---|
| Introspection returns read scope yet API always returns 403 | Rule checks `orders.read` instead of `SCOPE_orders.read` | Use the right authority prefix |
| Token was issued scopes yet authorities are empty | AS returns `scp`/`permissions` instead of `scope` | Standardize response or add custom mapping |
| API expects read yet AS puts `SCOPE_` inside the scope value | Mapping produces `SCOPE_SCOPE_...` | Emit raw scopes or adjust converter contract |
| `active:true` yet route still returns 403 | Token lacks the required scope authority | Check the scopes actually granted |
| Case change in scope causes 403 | Authority matching is exact string comparison | Standardize scope casing across AS/API |
| Token has `orders.write`, GET needing read still returns 403 | No automatic scope hierarchy | Define explicit policy or grant both scopes |
| Rule checks `ROLE_ADMIN` while AS only returns `scope=admin` | OAuth scopes do not automatically become roles | Use `SCOPE_admin` or a dedicated role converter |
| Active token with right scope yet wrong audience for API | Cross-resource token usage | Validate `aud` per contract |
| Valid-looking JWT gets 401 on opaque API | AS rejects/marks token inactive, or wrong introspection credentials | Check endpoint contract, issuer, client auth |
| Custom introspector returns empty authorities | Wrapper replaced instead of preserving `getAuthorities()` | Delegate first and keep default authorities |
| Custom wrapper turns arbitrary strings into `ROLE_ADMIN` | Authority escalation from unallowlisted mapping | Map only verified sources and allowlisted values |
| Only `@WithMockUser` tests pass | Tests skip HTTP introspection and mapping | Test introspector/delegate separately |
| Active token with right scope cannot view another's order | Denied by domain policy | Usually the right, intended behavior |
| Permissions changed in IdP yet API keeps honoring old ones | Introspection cache or still-valid token | Review TTL, revocation semantics, and business policy |
| Introspection endpoint fails and API falls back to granting read | Dangerous fail-open bug | Fail closed; never build privileged principals unverified |
| API configured `jwt()` while expecting introspection mapping | Wrong authentication branch | Configure `opaqueToken()` with the right introspector |
| CORS preflight gets 401 | Browser OPTIONS lacks Bearer header | Configure CORS/filters properly while keeping auth on real requests |

### 16.1. A 403 is not always a mapping bug

When hitting 403, distinguish:

1. Does the principal hold `SCOPE_orders.read`?
2. Does the `hasAuthority` rule use the exact string?
3. Which `SecurityFilterChain` and method/path rule matched the request?
4. Does method security impose extra conditions?
5. Did the business service deny access due to owner/tenant or resource state?

Never widen rules to `permitAll()` or `authenticated()` just to silence a 403. Locate the exact layer enforcing the denial.

### 16.2. Observing configuration without leaking secrets

When debugging, enable appropriate Spring Security log levels in a controlled environment and inspect:

```text
request correlation id
introspection endpoint (excluding tokens/credentials)
latency / timeout / upstream HTTP status
authenticated principal type
permitted granted authority names to record
matched security chain / route policy
authorization decision (allow/deny)
```

Never log Bearer headers, raw tokens, client secrets, or full introspection responses. Because scopes/roles themselves can be sensitive in some systems, log them only when genuinely needed and under data-protection policy.

## 17. Checklist for designing the introspection → authorities contract

Before going to production, the Authorization Server and Resource Server teams should agree on:

1. **Introspection path and authentication:** endpoint URL, TLS, client authentication method, secret rotation, introspection permissions.
2. **Scope format:** RFC 7662 space-delimited `scope` string, or `scp`/`permissions` extension? If an extension, who governs it and what are its semantics?
3. **Scope catalog:** exact names `orders.read`, `orders.create`, `orders.update`, etc.; which clients may obtain which scopes?
4. **Issuer/audience:** how are active tokens confirmed to target this API, and which metadata does introspection return to prove it?
5. **Principal model:** do `sub` and `client_id` represent users or services; how are tenants and actors mapped?
6. **Authority mapping:** keep `SCOPE_` or use another prefix? Are roles/permissions added, and from which source?
7. **Error policy:** how are `active:false`, missing scopes, wrong audiences, timeouts, and AS errors handled?
8. **Revocation/caching:** cache lifetime, exp/TTL bounds, maximum acceptable revocation lag.
9. **Authorization:** which HTTP/method rules require which authorities? Where do owner/tenant checks live?
10. **Testing:** standard/non-standard responses, missing scopes, multiple scopes, `active:false`, wrong audience, expired tokens, and network failures.
11. **Observability:** visibility into mappings/decisions without leaking tokens or sensitive attributes.
12. **Multi-instance consistency:** do all Resource Servers and gateways share the exact same mapping, caching, and revocation semantics?

### 17.1. Decision model

```mermaid
flowchart TD
    A["Receive Authorization: Bearer token"] --> B["OpaqueTokenIntrospector calls trusted AS"]
    B --> C{"active true and response valid?"}
    C -->|"No"| X["Reject authentication"]
    C -->|"Yes"| D{"aud / iss / token profile match?"}
    D -->|"No"| X
    D -->|"Yes"| E["Read standard scope or agreed extension"]
    E --> F["Map to GrantedAuthority: SCOPE_..."]
    F --> G{"HTTP/method has required authority?"}
    G -->|"No"| Y["Reject authorization"]
    G -->|"Yes"| H{"Owner / tenant / state valid?"}
    H -->|"No"| Y
    H -->|"Yes"| I["Allow operation"]
```

This is a logical model; **audience/issuer checks can be enforced by the AS per contract or by a trusted wrapper on the Resource Server**. Never assume default `opaqueToken()` automatically checks every extended attribute your system needs.

## 18. Conclusion

```text
OAuth access token
    |
    v
Authorization: Bearer opaque-token
    |
    v
Token introspection over trusted channel
    |
    +-- active=false -> no trusted Authentication
    |
    +-- active=true, scope="orders.read orders.write"
                |
                v
       OAuth2AuthenticatedPrincipal
                |
                v
       GrantedAuthority:
         SCOPE_orders.read
         SCOPE_orders.write
                |
                v
       BearerTokenAuthentication
                |
                v
       HTTP/method authorization
                |
                v
       Business owner/tenant/state checks
```

**OAuth `scope` in an introspection response is permission data confirmed by the Authorization Server; Spring Security `GrantedAuthority` is the permission representation used to evaluate rules at the Resource Server.** In standard opaque-token setups, each scope maps to a `SCOPE_`-prefixed authority, so `scope: "orders.read"` satisfies `hasAuthority("SCOPE_orders.read")`.

When the AS returns variants like `scp` or `permissions`, write custom mappings **deliberately and strictly from trusted sources**, never granting arbitrary permissions from untrusted JSON. More importantly, **`active:true` never replaces audience checks, scope authorization, and object-level business permissions**. The API must reject inactive tokens, tokens meant for other targets, and requests lacking required authorities, while still enforcing owner/tenant checks even when scopes match.

## References

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): `active`, `scope`, client authentication, and token metadata.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): scopes and access token issuance.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer credentials, 401/403, and `insufficient_scope`.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): access token resources/audiences.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access tokens, useful when comparing against opaque/introspection.
- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Token (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection configuration and mapping `scope` to `SCOPE_`.
- [Spring Security Reference — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): Bearer token authentication.
- [Spring Security Reference — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `hasAuthority`, matchers, and HTTP policies.
- [Spring Security Reference — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@PreAuthorize` and service-layer authorization.
- [Spring Security API — `OpaqueTokenIntrospector`](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/introspection/OpaqueTokenIntrospector.html): introspection interface.
- [Spring Security API — `BearerTokenAuthentication`](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/authentication/BearerTokenAuthentication.html): Authentication for opaque bearer tokens.
- [OWASP API Security Top 10 (2023) — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): per-object API authorization.
