# Journey of a Request: From Access Token to Access Decision

In **Spring Security OAuth 2.0 Resource Server**, an access token does not automatically equate to access permission. The Resource Server must **recognize the token, validate the token, convert the verified information into an `Authentication`**, and then **evaluate the caller's permissions against the resource protection policy**. These steps are related, yet they answer different questions:

- **Authentication:** Is the token valid, issued by a trusted source, unexpired, and intended for this API? What is the principal/caller's identity?
- **Authorization:** Does the authenticated caller have permission to perform a specific operation on a specific resource?

This lesson traces the entire journey of a `GET /api/orders/42` request, from the moment the client sends `Authorization: Bearer ...` until Spring Security allows the controller to run or returns an error. The focus is on the **Resource Server receiving the access token**; user login, requesting an authorization code, or obtaining tokens from the Authorization Server belong to other parts of OAuth 2.0/OIDC.

## 1. Participating components

| Component | Responsibility in the journey |
|---|---|
| **Client** | Calls the API and sends a previously issued access token, typically in the `Authorization` header. |
| **Authorization Server / OpenID Provider** | Issues tokens; publishes metadata/JWKS when using JWTs; provides an introspection endpoint when using opaque tokens. |
| **Resource Server** | The API holding protected data/business logic, validating tokens and enforcing access rules. |
| **Spring Security filter chain** | Intercepts requests before the controller; performs bearer token authentication and URL-based authorization. |
| **Controller/service and method security** | Processes requests after passing the HTTP protection layer; can perform additional checks on business rules or individual data objects. |

HTTP example, where the token string is shortened for illustration:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
Accept: application/json
```

`Bearer` means that **whoever possesses and presents the token can exercise the rights bound to that token**, provided the Resource Server accepts it. Therefore, tokens must travel over HTTPS and must never be put into logs, URL queries, screenshots, or error messages.

## 2. Processing flow map

```mermaid
flowchart TD
    A[Client sends HTTP request] --> B[Spring SecurityFilterChain]
    B --> C{Bearer token present?}
    C -- No --> D[Continue as unauthenticated]
    C -- Yes --> E[BearerTokenAuthenticationFilter]
    E --> F{Configured authentication mechanism}
    F -- JWT --> G[JwtAuthenticationProvider and JwtDecoder]
    F -- Opaque --> H[OpaqueTokenAuthenticationProvider and introspection]
    G --> I{Valid token?}
    H --> I
    I -- No --> J[Return authentication error, typically 401]
    I -- Yes --> K[Create Authentication with authorities]
    K --> L[Store Authentication in SecurityContext]
    D --> M[AuthorizationFilter checks HTTP rules]
    L --> M
    M --> N{Request permitted?}
    N -- No, unauthenticated --> O[401 Unauthorized]
    N -- No, authenticated --> P[403 Forbidden]
    N -- Yes --> Q[Controller and method security]
    Q --> R{Permitted at business layer?}
    R -- Yes --> S[Execute, return data]
    R -- No --> P
```

The diagram shows the **typical logical flow**, without listing every filter in an application. A request to a `permitAll()` endpoint can proceed without a token; however, **if an invalid bearer token was sent**, the authentication filter may still reject the request before evaluating `permitAll()`.

## 3. Step 1 — The request enters `SecurityFilterChain`

The servlet container receives the HTTP request and passes it through `FilterChainProxy`, which selects the matching `SecurityFilterChain`. Spring Security runs security filters before dispatching the request to a Spring MVC controller. If the application declares multiple chains using `securityMatcher(...)`, the **selected chain** determines which authentication and authorization mechanisms apply.

For a typical Resource Server API, the chain includes key components:

1. `BearerTokenAuthenticationFilter`: extracts the bearer token and requests authentication.
2. `SecurityContext` management: stores the authentication result for the scope of request processing.
3. `ExceptionTranslationFilter`: translates certain authentication/authorization exceptions from later stages into appropriate HTTP responses.
4. `AuthorizationFilter`: enforces URL access policies configured via `authorizeHttpRequests(...)`.

There may also be filters for CORS, CSRF, exception handling, anonymous authentication, or other authentication mechanisms depending on configuration. **Filter ordering matters**: authorization decisions need to see the authentication information established earlier.

## 4. Step 2 — Extracting the bearer token

By default, `BearerTokenAuthenticationFilter` uses a `BearerTokenResolver` to look for a token in the header:

```http
Authorization: Bearer <access_token>
```

If no token is found, the filter does not automatically conclude that every endpoint is blocked; the request continues to the authorization step. Public endpoints can be accessed, while endpoints requiring authentication trigger a `401` response.

If the bearer header is malformed or violates token transmission rules, extraction can fail right at this step. Depending on the error, the response may be `400 invalid_request` rather than `401 invalid_token`. If a token is extracted, the filter creates a `BearerTokenAuthenticationToken` containing the **untrusted token string** and passes it to `AuthenticationManager` (or `AuthenticationManagerResolver` if dynamic resolution is configured).

> **Key takeaway:** The mere presence of a token in the header is not proof that the caller has been authenticated.

## 5. Step 3 — Branching by access token format

The Resource Server must be configured to know **how to validate the token**. Two common models are JWTs and opaque tokens.

| Aspect | JWT access token | Opaque access token |
|---|---|---|
| Shape | Typically three parts `header.payload.signature` | A string with no public meaning to the API |
| Verification | Verify signature with trusted keys and validate claims | Call the introspection endpoint to query token status/metadata |
| Spring Security components | `JwtAuthenticationProvider` → `JwtDecoder` | `OpaqueTokenAuthenticationProvider` → `OpaqueTokenIntrospector` |
| Network dependency per request | Usually no call to the Authorization Server per token; may need to fetch/refresh JWKS | Usually requires calling the introspection endpoint per configured policy |
| Revocation before expiration | Hard to detect immediately when validating JWTs locally only | Can reflect `active=false` status from the Authorization Server |

The Resource Server **must not guess whether a token is valid simply by seeing dots** in the string. Decoding/validation must follow the contract with the Authorization Server and the API's trust configuration. The JWT and opaque paths differ at the validation step, but **converge on an authenticated `Authentication` to perform authorization**.

### Branch A — JWT access tokens

A JWT has three Base64URL-encoded parts:

```text
base64url(header).base64url(payload).base64url(signature)
```

Illustrative payload example (**not a usable real token**):

```json
{
  "iss": "https://idp.example.com/realms/demo",
  "sub": "user-123",
  "aud": ["orders-api"],
  "exp": 1893456000,
  "iat": 1893452400,
  "scope": "orders.read profile"
}
```

Being able to read a JWT payload **does not mean the payload is trustworthy**. A client can craft an arbitrary JSON string; the Resource Server only uses claims for authentication/authorization **after** the signature and mandatory constraints have been successfully verified.

With `issuer-uri` configured, `JwtDecoder` uses the issuer's metadata to discover the required details and access the JWKS public signing key set. When processing a token, the decoder typically performs:

1. Reads the header, payload, and signature; checks that the signing algorithm matches the trusted configuration, rejecting arbitrary algorithms proposed by the token itself.
2. Locates the matching verification key from the trusted JWKS, for example by `kid`; verifies the signature.
3. Validates validity timestamps, especially `exp` (expiration) and `nbf` (not before), potentially allowing a reasonable clock skew tolerance.
4. Verifies that `iss` matches the trusted Authorization Server.
5. Validates **API-specific** constraints, especially ensuring `aud` contains the appropriate Resource Server identifier. Audience validation must be explicitly configured if the default setup does not enforce it.

Common claims:

| Claim | Meaning | How it is used |
|---|---|---|
| `iss` | Token issuer | Accept only issuers in the trusted configuration. |
| `sub` | Subject identifier | Typically the default `Authentication#getName()` for JWTs; not necessarily an email. |
| `aud` | Intended audience of the token | Prevents tokens meant for another API from being accepted by this API. |
| `exp`, `nbf`, `iat` | Timestamps | Checks token lifetime and validity window. |
| `scope` or `scp` | Granted scopes | Can be converted into `GrantedAuthority` instances for authorization checks. |
| `client_id`, `azp`, `jti` | Client info, authorized party, token ID (system-dependent) | Supports additional policies if required. |

`JwtDecoder` verifying a signature **does not mean** all Resource Server policies have been checked. If audience validation is skipped, a token validly signed by the same issuer but meant for another service can be wrongly accepted. If you need to distinguish user tokens from machine tokens or restrict token types, the API also needs additional policies aligned with the issuing system.

### Branch B — Opaque access tokens

When introspection is configured, the Resource Server sends the token to the Authorization Server's endpoint using the Resource Server's own credentials. The introspection response may contain:

```json
{
  "active": true,
  "sub": "user-123",
  "scope": "orders.read",
  "client_id": "web-client"
}
```

Only when the token is `active` and required conditions are met does Spring Security build an `Authentication`. The Resource Server must still check API access permissions; `active: true` does not mean the caller is allowed to operate on every order. For opaque tokens, the responsibility for and contents of returned claims depend on the Authorization Server's introspection contract; the API must define how to validate audience/resource if required by the system.

## 6. Step 4 — From a valid token to `Authentication`

After successfully validating a JWT, `JwtAuthenticationProvider` uses a `JwtAuthenticationConverter` to turn the `Jwt` into a `JwtAuthenticationToken`. For opaque tokens, the corresponding provider builds an authentication object containing a principal and authorities based on the introspection result.

`Authentication` typically exposes three pieces of information:

- **Principal:** The authenticated entity, such as a `Jwt` containing claims; this is not automatically a database `User` entity.
- **Credentials:** Proof material appropriate to the `Authentication` type, never a field to expose in responses.
- **Authorities:** Permissions as `GrantedAuthority` instances that Spring Security policies can evaluate.

For JWTs, `JwtGrantedAuthoritiesConverter` by default reads common scope claims (`scope` or `scp`) and adds the `SCOPE_` prefix:

```text
JWT:  "scope": "orders.read profile"
                 │
                 ▼
Authorities: SCOPE_orders.read, SCOPE_profile
```

Consequently, the matching Spring Security rule is typically written as:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
.hasAuthority("SCOPE_orders.read")
```

Distinguish between these two expressions:

- `hasAuthority("SCOPE_orders.read")` checks for the **exact** authority named `SCOPE_orders.read`.
- `hasRole("ADMIN")` by default checks for the authority `ROLE_ADMIN`. A JWT claim like `roles: ["ADMIN"]` does **not automatically** become `ROLE_ADMIN`; a custom converter is required when using this role model.

Do not assume that simply because a JWT has a `role`, `groups`, or `permissions` field, Spring Security will automatically understand all of them. Converting claims into authorities must be defined to match the issuer's actual token format and the application's needs.

## 7. Step 5 — Storing authentication in `SecurityContext`

When the provider returns a successful `Authentication`, the filter places it into the `SecurityContext` active for the request. In the standard servlet model, downstream code can read it from `SecurityContextHolder`, or use Spring MVC to inject the principal directly:

```java
@GetMapping("/api/me")
public Map<String, Object> me(@AuthenticationPrincipal Jwt jwt) {
    return Map.of(
        "subject", jwt.getSubject(),
        "issuer", jwt.getIssuer().toString()
    );
}
```

The example above applies to a Resource Server validating **JWTs**, where the principal is a `Jwt`. If using opaque tokens, the principal type differs; it can be accessed via `Authentication` or `OAuth2AuthenticatedPrincipal` depending on configuration. A stateless API typically validates the bearer token on **every request** and does not expect an HTTP session to reuse a prior login.

`SecurityContext` answers: *"Who has Spring Security authenticated, and what authorities are attached to this request?"* It **does not yet** answer: *"Is that person allowed to read order 42?"*

## 8. Step 6 — `AuthorizationFilter` decides by URL

`AuthorizationFilter` uses the rules declared in `authorizeHttpRequests(...)` to evaluate the current request against `Authentication`. Example:

```java
@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            // Only applies when the API uses Bearer tokens, without relying on cookies/sessions.
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
```

Key imports for the Java configuration above:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
```

Maven dependencies required in a Spring Boot application acting as a Resource Server:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
```

JWT issuer configuration in `application.yml`:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/demo
```

The issuer URL must match the accepted `iss` value and be an actual endpoint of the provider. Spring Security can fetch metadata/JWKS from the issuer, verify signatures, and check default constraints such as issuer/timestamps. **Specific requirements such as `aud=orders-api` must be configured and verified according to the application's configuration and security contract.**

In the example:

1. `GET /public/ping` is accessible without a token.
2. `GET /api/orders/42` requires the `SCOPE_orders.read` authority.
3. `POST /api/orders/42` requires `SCOPE_orders.write` (specific HTTP paths should be adjusted to match the actual REST design).
4. Other endpoints must at minimum have a valid `Authentication`; that **does not replace** fine-grained permission rules for sensitive endpoints.

Matchers are evaluated in declaration order: the first matching rule applies. Design specific matchers before general rules. `authenticated()` only requires authentication; it does not prove the caller has the right scope, role, or resource ownership.

> **CSRF note:** Disabling CSRF in the example is appropriate for APIs that strictly use bearer tokens explicitly sent in headers, without cookies/sessions for request authentication. If the system has cookie-based authentication or browser-sent credentials, you must evaluate and configure CSRF protection according to the actual architecture.

## 9. Step 7 — Method security and per-resource permissions

Passing `AuthorizationFilter` means the request satisfies the declared HTTP policy. Before or while running business logic, the application may still need to check:

- Is user A allowed to read **order 42** belonging to user B?
- Does the `orders.read` scope allow reading every order in the system, or only the caller's own orders?
- Does the caller belong to the right tenant, organization, project, or data region?

With `@EnableMethodSecurity`, Spring Security can enforce additional decisions at the method level:

```java
@Service
public class OrderService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public OrderDto findOrder(String orderId) {
        // Read the order from the data store; must check ownership/tenant
        // before returning data if the scope does not grant system-wide read access.
        return loadOrder(orderId);
    }

    private OrderDto loadOrder(String orderId) {
        // Illustrative example: implement with an actual repository/service.
        throw new UnsupportedOperationException("Implement order lookup");
    }
}
```

The snippet above only illustrates **method security**; it does not yet perform ownership checks. In a multi-user API, add a check on the relationship between `sub`/caller and `order.ownerId`, or an equivalent policy mechanism. Do not treat a broad `scope` or `authenticated()` as proof that a user owns a specific record.

In some architectures, resource permissions are enforced by database queries filtering on `tenant_id`, a business authorization service, a policy engine, or `@PreAuthorize` invoking a permission-check bean. The implementation location may vary, but the principle is **only return data after both operation permissions and record-level access permissions have been confirmed**.

## 10. Step 8 — Turning decisions into HTTP responses

Three statuses must be clearly distinguished:

| Status | Meaning in Resource Server | Example |
|---|---|---|
| `200 OK` (or appropriate success code) | Both authentication and authorization succeeded; controller can process the request. | Valid JWT, matching audience, has `SCOPE_orders.read`, owns the order. |
| `401 Unauthorized` | No valid authentication for a protected endpoint. | No token sent; expired JWT, invalid signature/issuer/audience. |
| `403 Forbidden` | Authenticated, but failed authorization policy. | Valid JWT, but missing `SCOPE_orders.read` or violates record-level access permissions. |

Example when a request without a token hits an endpoint requiring authentication:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

With an invalid access token, the response may contain:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

For an authenticated caller lacking sufficient scope, a typical response:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

`BearerTokenAuthenticationEntryPoint` handles scenarios requiring authentication; `BearerTokenAccessDeniedHandler` handles access-denied scenarios under bearer token configuration. `ExceptionTranslationFilter` also translates exceptions thrown during post-filter authorization steps into responses. The exact headers, error descriptions, and status codes depend on the specific failure branch, configuration, and where the exception originates; do not assume **every** token-related error produces `401`.

Some scenarios compared:

| Request | Authentication | Authorization | Typical outcome |
|---|---|---|---|
| `GET /api/orders/42`, no token | Missing | Endpoint requires authority | `401` |
| JWT with tampered signature or expired | Failed | Does not run as authenticated | `401`, typically `invalid_token` |
| JWT signed by trusted issuer but `aud` is for another API, with audience validator | Failed | Does not run as authenticated | `401` |
| Valid JWT, only has `SCOPE_profile` | Succeeded | Missing `SCOPE_orders.read` | `403` |
| Valid JWT with `SCOPE_orders.read`, accessing someone else's order | Succeeded | Ownership check denies | `403` or appropriate security convention, such as `404` to avoid disclosing existence |
| Valid JWT, sufficient permissions for the record | Succeeded | Permitted | Controller returns `200` if business logic succeeds |
| `GET /public/ping`, no token | Not required | `permitAll()` | Endpoint executes normally |

**Warning about `401` and `403`:** HTTP's name `401 Unauthorized` is easily misleading. In this context, `401` primarily reports **not validly authenticated**, whereas `403` reports **authenticated, but permission denied**.

## 11. Distinguishing OAuth 2.0 access tokens from OIDC ID tokens

OIDC builds an identity authentication layer on top of OAuth 2.0. After logging in, a client may receive multiple token types, each with a **different intended consumer**:

| Token type | Who uses it? | Role |
|---|---|---|
| **Access token** | Resource Server/API | Proves permission to access the API within granted scopes and API policies. |
| **ID token** | OIDC client/relying party | Conveys authentication event and identity info to the client; audience is typically the client ID. |
| **Refresh token** | Client and Authorization Server | Obtains a new access token per Authorization Server policy; never sent to a Resource Server to access resources. |

An ID token can also be a validly signed JWT, yet **that is no reason for a Resource Server to accept it as an access token**. You must check token usage intent, audience, and issuer constraints. Pointing `issuer-uri` to an OpenID Provider only establishes part of issuer trust; it does not mean the Resource Server is performing OIDC login, validating ID tokens for a client, or automatically enforcing complete API authorization policies.

## 12. Tracing a specific request from start to finish

Suppose `orders-api` trusts issuer `https://idp.example.com/realms/demo`, has audience validation configured for `orders-api`, and `GET /api/orders/{id}` requires `SCOPE_orders.read`.

**Access permitted scenario:**

1. The user has authenticated with the identity system; the client was issued an access token with `sub=user-123`, `aud=orders-api`, and `scope=orders.read`.
2. The client calls `GET /api/orders/42` over HTTPS, sending the token in the bearer header.
3. `BearerTokenAuthenticationFilter` extracts the token string and passes it to the authentication manager.
4. `JwtDecoder` verifies the signature against trusted JWKS, and validates timestamps, issuer, and configured audience.
5. The converter builds a `JwtAuthenticationToken` with authority `SCOPE_orders.read`; Spring Security stores the result in `SecurityContext`.
6. `AuthorizationFilter` sees `GET /api/orders/**` requires `SCOPE_orders.read` and the caller meets the requirement.
7. The service checks whether `user-123` is permitted to view order 42; the condition passes.
8. The controller returns the order data with an appropriate HTTP success status.

**Access denied due to missing scope scenario:** Authentication steps 1–5 can still succeed completely, yet the token only carries `scope=profile`. At step 6, `AuthorizationFilter` denies the request and the API returns `403` under standard configuration. This directly demonstrates that **a valid token does not guarantee every action is allowed**.

**Access denied due to expired token scenario:** The decoder fails at step 4; the process builds no trusted principal, and a request requiring authentication receives `401`. Fix this by obtaining a new access token through the proper OAuth 2.0 flow, rather than elevating permissions or disabling time checks.

## 13. Observing and troubleshooting at the right layer

When testing the API, you can use `curl` to inspect the status and response headers clearly:

```bash
# No token sent: protected endpoint typically returns 401.
curl -i https://api.example.com/api/orders/42

# Send access token issued for orders-api.
curl -i https://api.example.com/api/orders/42 \
  -H 'Authorization: Bearer <ACCESS_TOKEN>'
```

When an error occurs, identify **which layer it happens at**:

| Symptom | Where to check | How to address |
|---|---|---|
| `401` even with a freshly issued token | Bearer header, issuer, JWKS/signature, `exp`/`nbf`, audience | Verify the token is meant for this API; check trust configuration and clock skew. |
| `403` with a still-valid token | Authorities, matchers, method security, ownership/tenant | Compare granted scopes with `SCOPE_...`, inspect business rules. |
| Scope exists in JWT but `hasRole(...)` fails | Converter and authority prefix | Distinguish `SCOPE_` from `ROLE_`; configure a converter if genuinely using roles. |
| Public endpoint rejected when an invalid token is sent | Bearer authentication filter runs before authorization | Remove invalid header from public requests; fix token source. |
| Validly signed JWT accepted by the wrong API | Audience config and token-type policies | Add `aud`/token-purpose validation per Resource Server contract. |
| Request passes HTTP authorization yet reads another tenant's data | Object checks in service/query | Enforce ownership and tenant boundaries at the business/data layer. |

You can enable appropriate logging to trace the filter chain and access decisions in development, but **never write raw access tokens, refresh tokens, secrets, or sensitive data into logs**. Error codes returned to clients should suffice to identify the general cause without exposing keys, internal details, or granular policies.

## 14. Principles to keep the journey secure

1. **Restrict issuer and audience:** A valid signature only proves a token matches a trusted key, not that it was issued for your specific API. Check `iss`, `aud`, and token acceptance policies.
2. **Never trust claims before validation:** Do not Base64-decode and use `sub`, `scope`, or `roles` for authorization before verifying the token's signature/status.
3. **Separate scope from data permissions:** `orders.read` is permission to perform a category of action; permission to view *which specific order* may require additional checks.
4. **Use HTTPS and protect bearer tokens:** Avoid putting tokens in URLs, console output, logs, or inappropriate client storage; treat a leaked token like a leaked credential.
5. **Choose an appropriate validity strategy:** JWTs allow local API verification but do not inherently reflect early revocation; opaque introspection can reflect fresher state but depends on the introspection endpoint and its availability.
6. **Apply least privilege:** Enforce `hasAuthority(...)`/method security policies on sensitive endpoints rather than relying solely on `anyRequest().authenticated()`.
7. **Separate token roles:** A Resource Server accepts access tokens with the right intended purpose, never ID tokens or refresh tokens as arbitrary substitutes.

## 15. Connecting the layers of responsibility

You can remember the journey with the following sequence:

```text
HTTP Authorization: Bearer ...
    → BearerTokenAuthenticationFilter: extract token
    → AuthenticationManager / AuthenticationProvider: validate token
    → JwtDecoder or introspection: verify proof and constraints
    → Authentication + GrantedAuthority: represent authenticated caller
    → SecurityContext: provide result to downstream steps
    → AuthorizationFilter: check HTTP policies
    → Method security / business logic: check operation and data permissions
    → Allow controller execution, or return 401/403 depending on cause
```

When analyzing a blocked access attempt, ask the questions in exact order: **Was the token extracted? Which mechanism validated the token? Are the issuer/audience/timestamps valid? Which authorities were created? Which URL rule matched? Is access to the specific record permitted?** Following this order cleanly separates authentication configuration errors from authorization errors and reveals exactly why the Resource Server accepts or rejects a request.
