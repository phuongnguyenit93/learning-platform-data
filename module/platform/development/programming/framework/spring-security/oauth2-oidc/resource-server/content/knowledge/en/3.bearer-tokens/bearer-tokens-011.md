# Distinguishing Input Credentials from Verified Identity

In Spring Security OAuth 2.0 Resource Server, a request typically carries an access token in the `Authorization: Bearer ...` header. This token string is an **input credential provided by the caller**. It represents an assertion that the caller holds a token the API might accept; however, the moment the request arrives, the Resource Server **has no basis yet to trust** the contents of that string.

Only after Spring Security verifies the token according to trusted configuration does the application obtain an authenticated `Authentication` object containing the **verified identity/security context** (*authenticated principal*) and authorities for further authorization. This transition from “client-sent Bearer string” to “verified principal” is a critical trust boundary in the API protection pipeline.

Example request:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

At the moment of receipt, the string `eyJhbGciOiJSUzI1NiIs...` **does not yet prove** the caller is `user-123`. If the token is valid and meets the API's issuer, audience, and validation requirements, Spring Security can create an authenticated principal with `sub = user-123`. Even then, the API **must still decide** whether the caller is allowed to read order `42`.

## 1. Four related but non-synonymous concepts

| Concept | Question | Example in Resource Server |
|---|---|---|
| **Input credential** | What does the caller submit to prove access? | Bearer access token string in `Authorization`. |
| **Authentication** | Is the credential valid per trusted sources and API rules? | JWT verification or opaque token introspection. |
| **Authenticated principal** | Under which security subject is the request now established? | `JwtAuthenticationToken`, `BearerTokenAuthentication`, `sub`/client info, and authorities. |
| **Authorization** | Is the authenticated subject permitted to act on the specific endpoint and object? | Checking `SCOPE_orders.read`, owner, tenant, and order state. |

**A credential is not a principal.** A client can attach any arbitrary token string to a request; the Resource Server must verify the token before trusting claims such as `sub`, `scope`, and `tenant_id`.

**An authenticated principal does not equal full access.** A valid token may still lack scopes, belong to the wrong tenant, or lack permissions on a specific resource.

For OIDC, an **ID Token** also serves a different purpose: it confirms the login event and identity claims for an OIDC Client. A Resource Server protecting an API must accept an **access token intended for that API**, never accepting an ID Token merely because it is a validly signed JWT.

## 2. How do Bearer tokens enter the system?

With OAuth 2.0 Bearer, whoever holds the access token can present it to attempt accessing a protected resource. Unlike proof-of-possession mechanisms, ordinary Bearer tokens do not require proving ownership of a private key per request. Therefore, the token must be protected as a credential.

```http
Authorization: Bearer <access-token>
```

From the Resource Server's perspective, `<access-token>` could be:

- A JWT with a valid signature, trusted issuer, and valid timestamps.
- A forged or expired JWT, or one with the wrong issuer, wrong audience, or disallowed algorithm/key.
- An opaque token that can only be verified via introspection or a matching mechanism.
- A token issued for a different API/Client, even from the same Authorization Server.
- A token representing a user, service, or another principal type depending on the OAuth grant/token profile.

The API **cannot tell which case applies merely from the presence of the header**.

### Other identity headers do not establish identity on their own

The following request contains three assertions from the client:

```http
GET /api/admin/report
Authorization: Bearer <token>
X-User-Id: admin
X-Role: ADMIN
```

The headers `X-User-Id` and `X-Role` do not prove the caller is an administrator. If the backend sits behind a gateway under an identity-forwarding header contract, the gateway must be authenticated, must strip any client-supplied copies of those headers, and the backend must restrict which sources may send those headers. Never trust identity headers arriving from the Internet.

> **Trust rule:** Data coming from the request is untrusted input that must be verified. Never derive a trusted `principal` from a raw token string, an unverified Base64-decoded JWT payload, or arbitrary client-supplied headers.

## 3. From Bearer credential to `Authentication`: the Spring Security flow

For a JWT Resource Server, the main Spring Security components play these roles:

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant F as BearerTokenAuthenticationFilter
    participant M as AuthenticationManager
    participant P as JwtAuthenticationProvider
    participant D as JwtDecoder
    participant S as SecurityContext
    participant A as Authorization / API

    C->>F: Request + Authorization: Bearer token
    F->>F: Extract unverified token
    F->>M: BearerTokenAuthenticationToken
    M->>P: Request authentication
    P->>D: Decode and validate JWT
    alt Invalid JWT
        D-->>P: Verification error
        P-->>F: AuthenticationException
        F-->>C: 401 Unauthorized
    else Valid JWT
        D-->>P: Verified Jwt
        P-->>M: JwtAuthenticationToken
        M-->>F: Authentication succeeded
        F->>S: Store Authentication for request
        S->>A: Principal and authorities
        A->>A: Check resource access permissions
        A-->>C: Result or authorization error
    end
```

| Component | Role | Trust state |
|---|---|---|
| `Authorization` header | Carries the credential from outside. | **Unauthenticated.** |
| `BearerTokenAuthenticationFilter` | Extracts the Bearer token and starts authentication. | Handles untrusted input. |
| `BearerTokenAuthenticationToken` | Represents an authentication **request** with the input token. | **Unauthenticated.** |
| `AuthenticationManager` | Routes the request to a capable provider. | Coordinates authentication. |
| `JwtAuthenticationProvider` / `JwtDecoder` | Validates the JWT and builds principal/authority context. | Establishes the trust boundary. |
| `JwtAuthenticationToken` | Authentication result after the JWT is accepted. | **Authenticated** when returned by a trusted provider. |
| `SecurityContext` | Holds the request's `Authentication` for downstream components. | Stores the result; does not verify credentials itself. |
| Authorization rules | Evaluates endpoint permissions and data-object permissions. | Relies on a valid principal and API policies. |

Common pitfall: the `Authentication` interface can represent **both an authentication request and an authentication result**. Not every object implementing `Authentication` means the caller has been verified.

```java
// Conceptual view of the internal flow:
Authentication pending =
    new BearerTokenAuthenticationToken(rawAccessToken);

Authentication verified =
    authenticationManager.authenticate(pending);
```

`pending` merely carries the credential for the provider to process; `verified` is the result accepted by the provider. In a standard Resource Server, the Spring Security filter executes this flow; controllers never need to instantiate `BearerTokenAuthenticationToken` manually.

**Never manually set `isAuthenticated = true` on an object you construct from the request and write it into `SecurityContext`.** Doing so can cause the application to skip token verification entirely. `isAuthenticated()` is only trustworthy within a properly configured pipeline.

## 4. “Readable JWT” vs. “Verified JWT”

A compact JWT typically has the structure:

```text
Base64URL(header).Base64URL(payload).Base64URL(signature)
```

Illustrative payload:

```json
{
  "iss": "https://login.example.com/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "exp": 1790000000,
  "nbf": 1789990000,
  "scope": "orders.read",
  "tenant_id": "tenant-a"
}
```

Anyone who receives an ordinary JWT can Base64URL-decode the first two parts to inspect their contents. Base64URL **neither encrypts secret contents nor proves the signature**. An attacker can easily craft a payload containing `sub: "admin"`.

The Resource Server may only rely on claims as security evidence **after** running appropriate checks:

1. **Signature and algorithm:** Verify with trusted keys/algorithms matching the issuer, never trusting keys referenced by arbitrary URLs supplied by the token itself.
2. **Issuer (`iss`):** Accept only Authorization Servers configured as trusted by the API.
3. **Timestamps (`exp`, `nbf`):** The token must be within its valid time window, accounting for validator clock skew.
4. **Audience (`aud`):** The token was issued for this API or an audience accepted by the API.
5. **Token profile constraints:** Such as token type, tenant, allowed clients, or custom requirements defined by the security contract.

Configuring `issuer-uri` in Spring Security enables issuer verification and default JWT validators. However, **do not assume the API's audience is automatically checked per business policy** merely because `issuer-uri` is set; configure an audience validator or the equivalent audience mechanism supported by your Spring Boot version.

### How far can claims be trusted?

| Claim | Role after verification | What not to infer |
|---|---|---|
| `iss` | Token issuing authority. | That it grants access permissions. |
| `sub` | Subject identifier within the issuer's context. | That it is always an end user or holds all permissions. |
| `aud` | Intended recipient of the token. | Read/write permissions. |
| `scope` / `scp` | Granted OAuth permissions, typically mapped to `SCOPE_*`. | Access to every record across every tenant. |
| `tenant_id` | Tenant context if defined by a trusted issuer/token profile. | Automatic access to all tenant data. |
| `email`, `name` | Profile attributes when issued and needed. | Immutable identifier or proof of admin roles. |

In OIDC, the **`iss` + `sub`** pair is generally a more stable identity key than email or display name. For tokens issued via `client_credentials`, the principal may represent a client/service; never assume `sub` is always an End-User.

## 5. If the Bearer is an opaque token, where does the principal come from?

An opaque token is not verified by the Resource Server reading a JWT payload directly. The application typically uses the Authorization Server's **token introspection**:

```http
POST /oauth2/introspect HTTP/1.1
Host: login.example.com
Authorization: Basic <resource-server-credentials>
Content-Type: application/x-www-form-urlencoded

token=<opaque-access-token>
```

An illustrative introspection response:

```json
{
  "active": true,
  "sub": "user-123",
  "client_id": "web-client",
  "scope": "orders.read",
  "exp": 1790000000
}
```

If the trusted introspection endpoint confirms the token is valid and satisfies API policy, Spring Security can create a `BearerTokenAuthentication` containing an `OAuth2AuthenticatedPrincipal` and authorities. If the token is invalid, no authenticated principal is created for authorization.

This mechanism differs from local JWT validation, yet the trust boundary remains identical:

```text
Opaque token from client
    -> introspection request to trusted Authorization Server
    -> evaluate response and API policy
    -> authenticated Authentication
    -> endpoint and resource authorization
```

**Introspection is not UserInfo.** Introspection returns access token status/metadata under the Authorization Server's protocol and contract. OIDC UserInfo is for a Client holding a suitable access token to retrieve user profile claims when needed. A successful UserInfo call does not prove the token has permission to call an API, nor does it replace authorization checks.

## 6. Where is the authenticated principal stored?

Upon success, Spring Security stores the `Authentication` in the request's `SecurityContext`. Downstream components can read it:

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

String name = authentication.getName();
Collection<? extends GrantedAuthority> authorities =
    authentication.getAuthorities();
```

This illustrates an authenticated request. On a `permitAll` endpoint, the context might contain no Bearer principal, or contain an anonymous authentication. Never assume `getAuthentication()` always represents an actual logged-in user account.

With a JWT Resource Server, the principal is typically `Jwt` and `Authentication` is typically `JwtAuthenticationToken`:

```java
JwtAuthenticationToken auth = ...; // Provided by Spring Security
Jwt jwt = auth.getToken();

String subject = jwt.getSubject();
String issuer = jwt.getIssuer().toString();
String principalName = auth.getName(); // Defaults typically to sub
```

If the application configures a custom `JwtAuthenticationConverter`, the principal name and authorities can differ. With opaque tokens, the principal is typically `OAuth2AuthenticatedPrincipal` inside `BearerTokenAuthentication`: **do not cast the principal to `Jwt`** when the API does not use JWTs.

### When is the principal a user vs. a service?

| Token source | Identifiable identity | What must be clarified |
|---|---|---|
| Authorization Code for a user | User and Client attributes depending on token profile. | `iss`, `sub`, granted permissions, and mapping to internal accounts. |
| Client Credentials | Client/service/workload. | Token represents an application; usually no End-User exists. |
| Delegated authority token | Subject/acting party depending on profile. | How actor, subject, and delegation limits are evaluated. |

You cannot look at a `sub` string and conclude it is always a human using a UI. Auditing, ownership, and authorization models must reflect the true semantics of the token issued by the Authorization Server.

## 7. Spring Boot example: let the framework authenticate before the controller reads identity

In Spring Boot 3 / Spring Security 6, add the dependencies:

```gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

Configure the issuer:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
```

The address above is illustrative; replace it with your real issuer and configure audience/token-profile constraints matching the API contract.

### Authenticating Bearer JWTs and authorizing endpoints

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/whoami")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
```

In this example:

- `oauth2ResourceServer(...jwt(...))` configures Bearer JWT **authentication** via the decoder/provider.
- `authenticated()` verifies the caller has a valid `Authentication`, without granting access to every resource.
- `hasAuthority("SCOPE_orders.read")` and `SCOPE_orders.write` **authorize** operations based on mapped scopes. By default, Spring Security typically converts `scope`/`scp` claim values into authorities prefixed with `SCOPE_`.
- `anyRequest().denyAll()` locks down endpoints without explicit rules.
- `STATELESS` reflects an API authenticated per request via tokens.

The example disables CSRF assuming the API uses only Bearer tokens sent explicitly in headers, without relying on browser-attached cookies for authentication. For endpoints that still use session/cookie login, evaluate and configure CSRF separately.

### Controller reading the verified `Jwt`

```java
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/api/whoami")
    public Map<String, String> whoami(@AuthenticationPrincipal Jwt jwt) {
        return Map.of(
            "issuer", jwt.getIssuer().toString(),
            "subject", jwt.getSubject()
        );
    }
}
```

Because the endpoint requires `authenticated()` and is handled by the JWT Resource Server, `@AuthenticationPrincipal Jwt jwt` represents the verified JWT provided by the framework after authentication. The controller **does not manually read the Bearer string from the header to decode it**.

The example returns only two fields to illustrate identity provenance. Real APIs should not dump entire JWTs or sensitive claims solely for debugging. For opaque tokens, use the appropriate principal type instead of `Jwt`.

### Enforcing audience when required by the API

If `orders-api` only accepts JWTs with audience `orders-api`, add a validator:

```java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class AudienceValidationConfig {

    private static final String ISSUER =
        "https://login.example.com/realms/shop";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(ISSUER).build();

        OAuth2TokenValidator<Jwt> defaults =
            JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audience =
            new JwtClaimValidator<List<String>>(
                "aud",
                values -> values != null &&
                    values.contains("orders-api"));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(defaults, audience));
        return decoder;
    }
}
```

When adding an audience validator, retain default validations such as issuer and timestamps. If your Spring Boot version provides a built-in audience configuration property, you can use that mechanism. Never accept a token meant for another API merely because it was signed by the same issuer.

## 8. Having a valid principal still requires checking resource permissions

Suppose the authenticated access token contains:

```json
{
  "iss": "https://login.example.com/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "tenant_id": "tenant-a"
}
```

The token may satisfy the rule to call `GET /api/orders/42`, yet **it does not prove order 42 belongs to `user-123`**.

Example service returning only orders matching both owner and tenant:

```java
import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class OrderService {

    private final OrderRepository orders;

    public OrderService(OrderRepository orders) {
        this.orders = orders;
    }

    public OrderDto findForCaller(long orderId, Jwt caller) {
        String subject = caller.getSubject();
        String tenantId = caller.getClaimAsString("tenant_id");

        if (tenantId == null) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN);
        }

        Order order = orders.findByIdAndTenantIdAndOwnerSubject(
                orderId, tenantId, subject)
            .orElseThrow(() ->
                new ResponseStatusException(HttpStatus.NOT_FOUND));

        return OrderDto.from(order);
    }
}
```

`OrderRepository`, `Order`, and `OrderDto` are illustrative domain types to be implemented. The controller passes the authenticated `Jwt` principal into the service; the `orders.read` permission is checked by `SecurityFilterChain` beforehand.

Querying by owner/tenant directly at the data source prevents returning out-of-scope objects. However, if the issuer is not authoritative for `tenant_id`, the Resource Server must verify tenant membership via an internal membership table or database. The `iss + sub` pair may also need to be mapped to an internal account ID to prevent identity collisions across multiple issuers.

Depending on the API contract, resources outside the caller's view permissions may return `403 Forbidden` or `404 Not Found` to avoid leaking record existence. Both differ from rejecting a credential at the authentication step.

## 9. HTTP 401 and 403 reflect two kinds of failure

| Scenario | Authentication | Authorization | Typical outcome |
|---|---|---|---|
| No Bearer token sent to an auth-required endpoint | Failed/absent | Cannot permit | `401 Unauthorized` |
| Token with bad signature or expired | Failed | Token permissions not evaluated | `401 Unauthorized` |
| JWT with wrong issuer/audience per validator | Failed | Not evaluated | `401 Unauthorized` |
| Valid token with only `orders.read` calling POST requiring `orders.write` | Succeeded | Missing scope | `403 Forbidden` |
| Valid token with right scope reading someone else's order | Succeeded | Lacks object permission | `403` or `404` |
| Valid token with right permissions and owner/tenant | Succeeded | Permitted | `2xx` if business logic succeeds |
| Endpoint configured `permitAll` and request carries no token | Bearer auth not required | Public route permitted | Proceeds per API logic |

In OAuth 2.0 Bearer, `401` responses typically include `WWW-Authenticate: Bearer`; invalid tokens may include `error="invalid_token"`. For authenticated tokens missing a scope, `403` responses may specify `insufficient_scope` depending on configuration.

Do not treat every `403` as “invalid token”: the token may be valid while lacking permissions. Likewise, do not treat printing `sub` from a decoded payload as “logged in”: that data may never have passed any verification step.

## 10. Practices that break the trust boundary

### 10.1. Manually decoding JWTs inside a controller

```java
// ANTI-PATTERN pseudocode; do not use in production.
String bearer = request.getHeader("Authorization");
String subject = decodePayloadWithoutVerification(bearer)
    .get("sub").toString();

return orderService.findOrdersFor(subject);
```

`decodePayloadWithoutVerification` only illustrates an incorrect operation, not a real API. An attacker can forge a payload with `sub = admin`. The right way is to use the JWT principal verified by Spring Security's `JwtDecoder`/provider.

### 10.2. Building an authenticated `Authentication` directly from headers

```java
// ANTI-PATTERN pseudocode; do not use.
Authentication fake =
    UsernamePasswordAuthenticationToken.authenticated(
        request.getHeader("X-User-Id"),
        null,
        List.of(new SimpleGrantedAuthority("ROLE_ADMIN")));

SecurityContextHolder.getContext().setAuthentication(fake);
```

An object marked authenticated has zero security value if constructed from untrusted input. Only a provider/filter that validates credentials according to policy should establish the request's principal.

### 10.3. Using an ID Token instead of an access token

An ID Token is for an OIDC Client to verify a login event and obtain claims. A Resource Server must accept access tokens matching the API's own audience and token profile. A valid signature alone is not enough to make an ID Token an API credential.

### 10.4. Believing `SCOPE_*` grants access to all data

A scope like `orders.read` authorizes calling the order-reading capability. It does not grant permission to read someone else's data. Enforce owner/tenant policies, internal roles, and business rules.

### 10.5. Putting tokens into logs, URLs, or responses

A Bearer token is a credential. Never write raw tokens, refresh tokens, or full `Authorization` headers into logs or traces. Avoid passing tokens in query strings where they end up in browser history, proxies, and analytics. For observability, log a request ID along with safe authentication status metadata.

## 11. Tracing a request accurately across both stages

When analyzing a `GET /api/orders/42` request, useful checkpoints are:

```text
[1] HTTP GET /api/orders/42
[2] Bearer extraction: token present (do not log raw token)
[3] JWT validation: issuer/signature/timestamps/audience valid
[4] Verified principal: issuer=..., subject=user-123
[5] Authorities: SCOPE_orders.read
[6] Endpoint authorization: permitted
[7] Object authorization: order 42 belongs to user-123, tenant-a
[8] Response: 200
```

A failure at `[3]` means the credential **was not authenticated**. A failure at `[6]` or `[7]` means the caller **was authenticated** but denied permission. Reading traces this way pinpoints where to fix issues: decoder/token issuer, authority mapping, or resource policies.

### Distinguish two types of testing

Spring Security Test provides the `jwt()` helper for MockMvc to populate a mocked JWT context for testing authorization policies. However, `jwt()` generally **does not execute real JWT signature verification through the decoder**. Therefore:

- Controller tests using a mock JWT prove how policy handles a simulated subject/scope.
- Integration tests for the decoder/introspection must verify that the API actually rejects forged, expired, wrong-issuer, and wrong-audience tokens.
- Data-layer tests must verify that even a valid principal cannot read objects belonging to another owner/tenant.

These are three separate test goals. Never use “mock JWT permits GET” as proof that the JWT verification layer in production is configured correctly.

## 12. One diagram for the entire trust boundary

```mermaid
flowchart TD
    A["Authorization: Bearer token"] --> B["Request credential: untrusted"]
    B --> C{"JWT validation or opaque introspection"}
    C -- "Invalid" --> D["401: no verified principal"]
    C -- "Valid" --> E["Authenticated Authentication"]
    E --> F["Principal + authorities in SecurityContext"]
    F --> G{"Permitted to call endpoint?"}
    G -- "No" --> H["403: insufficient permissions"]
    G -- "Yes" --> I{"Permitted on data object?"}
    I -- "No" --> J["403/404 per API policy"]
    I -- "Yes" --> K["Execute business logic"]
```

**Before** the verification boundary, the token is an untrusted credential sent by the client. **After** the verification boundary, accepted claims become the request's identity and authorities. And even when authentication succeeds, resource access remains a separate authorization decision.

When implementing Spring Security Resource Server, let the filter/provider authenticate the access token, consume the trusted `Jwt`/`Authentication` provided by the framework in controllers or services, and enforce permission policies by action and business object. **Verified identity is the result of credential validation — never a direct copy of self-asserted caller input.**
