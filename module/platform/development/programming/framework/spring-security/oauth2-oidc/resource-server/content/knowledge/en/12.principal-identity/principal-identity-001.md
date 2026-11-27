# `Jwt`, `JwtAuthenticationToken`, and Post-Authentication Identity Data

In a **Spring Security OAuth 2.0 Resource Server**, an access token sent by a client over HTTP **does not automatically become a trusted identity**. For a JWT Bearer token, Spring Security must verify the token against the issuer, signature, timestamps, and API policies before the application uses claims to determine who is calling, which permissions are granted, and which data can be accessed.

Two types that are very easy to confuse are:

- **`Jwt`** (`org.springframework.security.oauth2.jwt.Jwt`): represents a JWT decoded and accepted by `JwtDecoder` according to configured validators. It provides the token value, headers, claims, and claim accessor methods such as `getSubject()`, `getIssuer()`, and `getAudience()`.
- **`JwtAuthenticationToken`** (`org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken`): represents the **Spring Security `Authentication`** result based on a verified JWT, binding the JWT with a principal name, `GrantedAuthority` instances, and the authentication state in `SecurityContext`.

The distinction can be visualized as follows:

```text
HTTP Authorization: Bearer <raw-token>
             |
             | Unverified, payload not trusted
             v
BearerTokenAuthenticationFilter
             |
             v
JwtAuthenticationProvider + JwtDecoder
             |
             | Verify signature, iss, exp/nbf, aud per policy
             v
           Jwt
             |
             | Map principal name + GrantedAuthority
             v
   JwtAuthenticationToken
             |
             v
   Request SecurityContext
             |
             v
Controller / Service / Authorization
```

**`Jwt` holds the token data accepted by the decoder; `JwtAuthenticationToken` is the authentication context that Spring Security uses for the request.** Neither implies that a user is allowed to perform every operation simply because the JWT is valid.

This content uses Spring Boot 3 / Spring Security 6 syntax on the Servlet stack. Custom configurations can change the principal name, principal type, or authorities, so you must read the actual application configuration.

## 1. Conceptual Layers: Credential, Verified JWT, Principal, Authorization

A request may contain:

```http
GET /api/orders/42 HTTP/1.1
Host: orders.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

At the moment the filter just reads the header, the Bearer string is an **input credential**, which may be valid, forged, expired, or not intended for this API. You must not manually Base64URL-decode the payload and assume `sub` is the authenticated user.

| Concept | Responsibility | In Spring Security JWT Resource Server |
| --- | --- | --- |
| **Bearer credential** | Data presented by the client to be authenticated. | The string from `Authorization` and `BearerTokenAuthenticationToken` used for the authentication request. |
| **Verified JWT** | Result of decoding, signature verification, and token validators. | The `Jwt` object returned upon success by `JwtDecoder.decode(...)`. |
| **Verified `Authentication`** | Caller security context with principal and authorities. | Typically `JwtAuthenticationToken`. |
| **Principal** | Representation of the subject after authentication. | Typically `Jwt` in a JWT Resource Server; the principal name is usually based on `sub`. |
| **Authorization** | Checking whether the caller is allowed to perform a specific action. | `hasAuthority`, `hasRole`, method security, and owner/tenant policies. |

The term **“authentication”** sometimes causes confusion because the `Authentication` interface in Spring Security can represent **both an uncompleted authentication request and an authentication result**. For example, `BearerTokenAuthenticationToken` only wraps the credential to be processed and does not carry the same trust semantics as `JwtAuthenticationToken` returned by the provider after validating the token.

In a normal application, let the Security filter chain and authentication provider execute the entire process. Do not construct an `Authentication` with `authenticated = true` from a self-asserted client header.

## 2. Inside a JWT: What Are Headers and Claims?

A compact JWT typically has three parts:

```text
Base64URL(header).Base64URL(payload).Base64URL(signature)
```

Example JWT header:

```json
{
  "alg": "RS256",
  "kid": "shop-key-2026-02",
  "typ": "at+jwt"
}
```

Example payload:

```json
{
  "iss": "https://identity.example.com/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "iat": 1890000000,
  "nbf": 1890000000,
  "exp": 1900000000,
  "client_id": "web-frontend",
  "scope": "orders.read profile.read",
  "tenant_id": "tenant-a",
  "email": "user@example.com"
}
```

These JSON snippets are for illustration only, **not a signed JWT**.

The **header** contains information about the token type, algorithm, and key identifier; the **payload** contains claims. They can be read directly from the JWT string because Base64URL is not an encryption mechanism. Anyone can craft an arbitrary payload with `sub = admin` or `scope = orders.write`, so the Resource Server must not trust that data before the signature and validators succeed.

For a JWT access token:

- `iss` identifies the token issuer.
- `sub` is the subject according to the issuer/token profile contract; it does not automatically always represent an End-User.
- `aud` identifies the intended recipients authorized to accept the token; the API must verify the token is meant for it.
- `exp` and `nbf` constrain the valid time window.
- `scope` or `scp` can be mapped by Spring Security into authorities.
- `client_id`, `tenant_id`, and `email` are attributes that should only be interpreted according to the issuer contract and application policy.

**Being able to read a claim does not equate to having the right to use that claim as security evidence.** The trust boundary is established by JWT validation, not by JSON parsing.

## 3. Where Does Spring Security Create `Jwt`?

Typical flow:

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant F as BearerTokenAuthenticationFilter
    participant M as AuthenticationManager
    participant P as JwtAuthenticationProvider
    participant D as JwtDecoder
    participant S as SecurityContext
    participant A as API

    C->>F: Authorization: Bearer JWT
    F->>M: BearerTokenAuthenticationToken
    M->>P: authenticate(...)
    P->>D: decode(rawJwt)
    alt Invalid JWT
        D-->>P: JwtException
        P-->>F: AuthenticationException
        F-->>C: Authentication failure (typically 401)
    else Valid JWT
        D-->>P: Verified Jwt
        P->>P: Convert Jwt to principal + authorities
        P-->>M: JwtAuthenticationToken
        M-->>F: Authentication succeeded
        F->>S: Store Authentication for request
        S->>A: Principal and authorities
        A->>A: Functional and resource authorization
        A-->>C: 2xx or 403/404 per policy
    end
```

In the JWT case, `JwtAuthenticationProvider` uses a `JwtDecoder` and a converter from JWT to `AbstractAuthenticationToken` (by default typically `JwtAuthenticationConverter`). Spring Security only places the authentication result into `SecurityContext` after the provider accepts the token.

Not every `JwtDecoder` is the same. A decoder can:

1. Verify the signature using the JWK Set from a trusted issuer.
2. Check `iss`, `exp`, `nbf`, and standard JWT validators.
3. Check `aud = orders-api` if the application configures audience validation.
4. Check token type/profile or other required claims per the contract.

Note: configuring only `issuer-uri` **should not be assumed to guarantee** all audience constraints of the API. When an issuer issues tokens for multiple protected resources, you must explicitly verify `aud` via properties or a supported validator in the version in use.

## 4. Structure of `Jwt`: How to Read Post-Authentication Data

A `Jwt` can provide:

```java
Jwt jwt = ...; // Provided by Spring Security after authentication

String subject = jwt.getSubject();
String issuer = jwt.getIssuer().toString();
Collection<String> audience = jwt.getAudience();
Instant expiresAt = jwt.getExpiresAt();
String tenantId = jwt.getClaimAsString("tenant_id");
List<String> roles = jwt.getClaimAsStringList("roles");
Map<String, Object> claims = jwt.getClaims();
Map<String, Object> headers = jwt.getHeaders();
```

This illustrative example assumes imports for `Jwt`, `Instant`, `Collection`, `List`, and `Map` are present and that issuer is present as required by the token profile. If a claim is optional, you must check for the case where it is **absent**; do not call `.toString()` on a null value.

Information groups in `Jwt`:

| Method | Result | Usage |
| --- | --- | --- |
| `getSubject()` | The `sub` claim as a string if present. | Identifies the subject within the issuer context; does not by itself imply user vs. application. |
| `getIssuer()` | URI from the `iss` claim. | Binds the issuing source to the identity and multi-issuer policies. |
| `getAudience()` | List of audiences in `aud`. | Inspects intended recipients; validation should live in the decoder. |
| `getIssuedAt()`, `getExpiresAt()` | Issued-at/expiration timestamps when present. | Diagnostics and required policies; expiration must be checked by a validator. |
| `getClaimAsString("tenant_id")` | Custom tenant claim. | Use per the issuer contract and verify internal tenant relationships when needed. |
| `getClaimAsStringList("roles")` | Role list if formatted accordingly. | Input data for authority mapping, **not automatically `ROLE_*`**. |
| `getClaims()` | All claims. | Use selectively; do not return verbatim or log indiscriminately. |
| `getHeaders()` | Parsed JWT headers. | Useful for diagnostics; never use `kid`/`alg` to arbitrarily choose a trusted key source. |
| `getTokenValue()` | **Raw JWT string**. | A sensitive Bearer credential; avoid logging or returning to clients. |

`Jwt` is a Spring Security object type, not proof that every claim becomes accurate and real-time business data. For instance, `email` may have changed after the token was issued; `tenant_id` may not immediately reflect the latest membership. Signature verification proves the token was issued by a trusted party and remains valid according to validators—**it does not turn time-varying attributes into real-time data**.

## 5. `JwtAuthenticationToken`: What `Jwt` Alone Does Not Provide

`JwtAuthenticationToken` is an `Authentication` implementation built on top of a verified JWT. It holds:

- **Principal**: typically the `Jwt` object itself.
- **Name**: a principal name string serving the `Authentication.getName()` interface.
- **Authorities**: `GrantedAuthority` instances such as `SCOPE_orders.read` or roles produced by a converter.
- **Authentication state**: set by the provider after verifying the token.
- **Token attributes**: the JWT claims accessible via `getTokenAttributes()`.

Example of reading the result:

```java
import java.util.Collection;
import java.util.Map;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

void inspect(JwtAuthenticationToken auth) {
    String principalName = auth.getName();
    boolean authenticated = auth.isAuthenticated();

    Jwt jwt = auth.getToken();
    Object principal = auth.getPrincipal();
    Collection<GrantedAuthority> authorities = auth.getAuthorities();
    Map<String, Object> tokenAttributes = auth.getTokenAttributes();

    // auth.getPrincipal() is normally the Jwt object.
    // auth.getAuthorities() is used for authorization.
    // tokenAttributes contains claims and should not be logged in full.
}
```

Key points to remember:

| Expression | In Default JWT Resource Server | Note |
| --- | --- | --- |
| `auth.getToken()` | Verified `Jwt`. | Can read claims, headers, token value. |
| `auth.getPrincipal()` | Usually the same `Jwt` object. | Not by default a `UserDetails` or database entity. |
| `auth.getName()` | Usually the `sub` string. | Can change if a custom converter/constructor selects a different principal claim. |
| `auth.getAuthorities()` | Mapped authorities from scopes/claims. | Does not contain every business permission on individual records. |
| `auth.getTokenAttributes()` | Token claims. | Should not be returned/logged in full due to sensitive data. |
| `auth.isAuthenticated()` | `true` for a result returned by a trusted provider. | Do not trust a spoofed object created from HTTP data by untrusted code. |

In controller/service examples, **reading the `Authentication` provided by Spring Security** is the safe approach; never manually construct a `JwtAuthenticationToken` from a payload that has not passed through `JwtDecoder`.

### Do Not Confuse Class Names with Object Purpose

`JwtAuthenticationToken` contains an object named `Jwt`, but that **does not mean** the Resource Server has logged a user in via OIDC. The API authenticates a Bearer **access token**. An OIDC Client may use `OidcUser` or `OidcIdToken` in an `oauth2Login()` flow, whereas a JWT Resource Server has `JwtAuthenticationToken` for incoming API requests. These are **two different security roles**.

## 6. Default Principal Name Is Usually `sub`

In the common configuration of `JwtAuthenticationConverter`, the principal name is taken from the `sub` claim:

```json
{
  "iss": "https://identity.example.com/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
```

When the JWT is verified and the default converter runs:

```java
JwtAuthenticationToken auth = ...;

auth.getName();             // Usually "user-123"
auth.getToken().getSubject(); // "user-123"
```

However, **`Authentication.getName()` is a mapped principal name**, not an API guarantee that “this is the user ID in the system's `users` table”. There are at least three things to consider:

1. **Issuer**: `sub = user-123` under two different issuers does not automatically represent the same account.
2. **Access token type**: `sub` can represent an End-User or a service/client depending on the token profile.
3. **Custom converter**: the application may override `principalClaimName`, making `getName()` no longer equal to `sub`.

Example of two distinct identities:

```text
iss = https://identity-a.example.com
sub = 123

iss = https://identity-b.example.com
sub = 123
```

Do not merge those two subjects merely because their `sub` strings match. For user accounts from OIDC, the **issuer + subject** pair is usually the right starting point to link to an internal account. For machine tokens, the domain may need a separate namespace for service identities.

### `Jwt` Is Not an Application User Entity

A system typically has two distinct groups of data:

```text
Verified JWT claims
    iss, sub, client_id, scope, aud ...
                |
                v
Internal identity mapping (if needed)
    external issuer + subject -> internal account/service
                |
                v
Queries and business policies
    membership, tenant, account status, ownership
```

Do not assume `sub` always has the same type/format as the `user_id` key in the database. In fact, a valid access token may represent a service that has no internal user record at all.

## 7. Where Does `JwtAuthenticationToken` Get Its Authorities?

In a Spring Security JWT Resource Server, the token often carries a claim:

```json
{
  "scope": "orders.read orders.write"
}
```

Spring Security's default converter typically uses `JwtGrantedAuthoritiesConverter` to read `scope` or `scp` and transform them into:

```text
SCOPE_orders.read
SCOPE_orders.write
```

For `Authentication`, authorities can be inspected:

```java
Collection<? extends GrantedAuthority> authorities =
    authentication.getAuthorities();
```

Corresponding rules:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.requestMatchers(HttpMethod.POST, "/api/orders")
    .hasAuthority("SCOPE_orders.write")
```

**`getAuthorities()` does not return the raw `scope` claim**; it returns `GrantedAuthority` objects created by the converter. If the application changes the prefix, claim source, or converter, `hasAuthority(...)` policies must match.

Example of a custom claim:

```json
{
  "roles": ["ADMIN", "SUPPORT"]
}
```

The `roles` claim **does not automatically** become `ROLE_ADMIN` and `ROLE_SUPPORT` in every application's default setup. A converter wired into the JWT DSL is required, and you should only trust roles that the issuer is authorized to grant.

| Attribute | Source | Used For |
| --- | --- | --- |
| `scope` / `scp` in `Jwt` | Verified access token. | Input data for OAuth permissions. |
| `SCOPE_*` in `auth.getAuthorities()` | Mapped result from the converter. | Checking with `hasAuthority(...)`. |
| `roles` in `Jwt` | Custom claim, if present. | Not a `GrantedAuthority` until mapped. |
| `ROLE_*` in `Authentication` | Configured converter or role-mapping mechanism. | Checking with `hasRole(...)` or `hasAuthority(...)`. |
| Permission on a specific order | Database/service policy. | Determining owner, tenant, and business conditions. |

## 8. Spring Boot: Minimal JWT Resource Server Configuration

With Gradle:

```gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

Declare the issuer:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/realms/shop
```

Configure a `SecurityFilterChain` for the API:

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
                .requestMatchers(HttpMethod.GET, "/api/me")
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

Here:

- `oauth2ResourceServer().jwt()` configures the API to use Bearer JWT authentication. `JwtDecoder` is auto-configured by Spring Boot or provided as an application bean.
- `authenticated()` requires a valid authentication result; it does not automatically grant permission to read all resources.
- `hasAuthority("SCOPE_orders.read")` checks a mapped access permission.
- `STATELESS` indicates the API does not rely on a server session to store login state.
- `securityMatcher("/api/**")` applies this chain only to matching URLs. If the application has other URLs, explicit chains or fallback protection are needed.

Disabling CSRF as shown is only appropriate when the API receives Bearer tokens explicitly in headers and does **not** rely on authentication cookies automatically sent by browsers. If the application also uses web login/session/cookies, design separate filter chains and CSRF rules per area.

### From Issuer to Principal

For a valid JWT, a typical Resource Server performs:

```text
issuer-uri / JwtDecoder bean
          |
          v
JwtDecoder verifies JWT
          |
          v
JwtAuthenticationConverter maps authorities/name
          |
          v
JwtAuthenticationToken in SecurityContext
```

If the application defines its own `JwtDecoder`, Spring Boot may back off in favor of that bean. In that case, the application must ensure the actual decoder still verifies signature, issuer, timestamps, and audience per policy. `JwtAuthenticationToken` cannot fix a decoder that skipped critical validators.

## 9. Reading `Jwt` in a Controller with `@AuthenticationPrincipal`

For an endpoint that already requires JWT authentication, a concise approach is:

```java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MeController {

    @GetMapping("/api/me")
    public Map<String, Object> me(@AuthenticationPrincipal Jwt jwt) {
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("issuer", jwt.getIssuer().toString());
        response.put("subject", jwt.getSubject());
        response.put("clientId",
            jwt.getClaimAsString("client_id"));
        return response;
    }
}
```

Spring MVC extracts `Jwt` from the principal of the current `Authentication`. Because the controller uses the **JWT Resource Server chain** and the endpoint is protected, this data has already passed through the corresponding decoder/validators; the controller does not need to manually extract the raw token from the header.

In real-world implementations:

- Do not assume an optional claim like `client_id` is always present.
- Return only the fields truly required by the API contract.
- Avoid returning the raw JWT, all claims, or unrelated personal attributes.
- If the endpoint also supports opaque-token authentication, the principal may **not be a `Jwt`**; do not cast to JWT unconditionally.

The snippet above only illustrates caller info; many systems do not need such an endpoint in production.

## 10. Reading `JwtAuthenticationToken` and Authorities in a Controller

When both claims and mapped authorities are needed, you can use `Authentication`:

```java
import java.util.List;
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CurrentCallerController {

    @GetMapping("/api/caller")
    public Map<String, Object> caller(Authentication authentication) {
        if (!(authentication instanceof JwtAuthenticationToken jwtAuth)) {
            throw new IllegalStateException(
                "Endpoint requires JWT authentication");
        }

        List<String> authorities = jwtAuth.getAuthorities()
            .stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return Map.of(
            "principalName", jwtAuth.getName(),
            "subject", jwtAuth.getToken().getSubject(),
            "authorities", authorities
        );
    }
}
```

For this endpoint to work, the security chain must include a rule for `/api/caller`, such as `.requestMatchers("/api/caller").authenticated()` placed before `anyRequest().denyAll()`. The example logic assumes `getName()` and `sub` are required by the token profile. Real applications should check for null on optional claims and provide proper error handling.

**`Authentication` is a good abstraction when multiple authentication mechanisms must be handled**, provided you check the type/token contract before casting to `JwtAuthenticationToken`. If you know for certain the path uses a JWT Resource Server, accessing `Jwt` directly via `@AuthenticationPrincipal` can be more concise.

### When to Use Which?

| Need | Commonly Used API |
| --- | --- |
| Only need subject, issuer, or JWT claims | `@AuthenticationPrincipal Jwt jwt` |
| Need authorities produced by the converter | `Authentication.getAuthorities()` or `JwtAuthenticationToken.getAuthorities()` |
| Need the principal name after mapping | `Authentication.getName()` |
| Need the full verified JWT | `JwtAuthenticationToken.getToken()` |
| Want to use in a service independent of HTTP | Pass an explicit identity/domain context from the application layer or use appropriate method security |
| Support opaque tokens or multiple authentication mechanisms | Use the `Authentication` abstraction and branch by valid principal type |

## 11. Is Authenticated Identity Data Always a “User”?

**Not always.** OAuth 2.0 allows access tokens to be issued in several contexts:

| Context | What Subject May Represent | Appropriate Interpretation |
| --- | --- | --- |
| Authorization Code with a user | End-User per the issuer contract. | Can link `iss + sub` to an internal account. |
| Client Credentials | Client/service account/workload. | Do not assume a logged-in End-User exists. |
| Token exchange / on-behalf-of | Subject and actor may be different principals. | Requires a token profile to interpret delegation. |
| Opaque access token | Subject from introspection metadata. | Principal is not a JWT; semantics still depend on the issuer. |

Example JWT in a machine-to-machine context:

```json
{
  "iss": "https://identity.example.com/realms/shop",
  "sub": "service-account-8735",
  "client_id": "inventory-worker",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
```

Some issuers may set `sub` equal to `client_id`, while others use a separate service account ID. **Do not assume `sub == client_id` as a universal rule**, nor assume a value resembling an email is definitely a human user.

When an API serves both user and service callers, separate the caller kind in the domain using a **trusted claim / issuer profile** or controlled issuer/client rules:

```java
public enum CallerKind {
    USER,
    SERVICE
}

public record CallerIdentity(
    CallerKind kind,
    String issuer,
    String subject,
    String clientId
) {}
```

This is an application-defined type, **not an object provided automatically by Spring Security**. `JwtAuthenticationToken` contains the JWT and authorities, but does not reliably determine `CallerKind` across every Authorization Server.

If the token profile lacks reliable information to distinguish users from services while the business logic requires classification, **do not guess based on the format of the `sub` string**. Align on the token issuance contract or reject operations requiring classification.

## 12. OIDC ID Tokens and JWT Access Tokens Are Not Interchangeable

An application may act both as an **OIDC Client** for user login and as an **OAuth 2.0 Resource Server** for APIs. However, the principal data in the two roles is not the same:

| Context | Related Token/Credential | Common Principal | Purpose |
| --- | --- | --- | --- |
| OIDC Client login via `oauth2Login()` | Authorization Code, ID Token, and related OIDC details. | `OidcUser`/`OAuth2AuthenticationToken` per client flow. | Establish Client login session and user profile. |
| JWT Resource Server | Bearer **access token** from API request. | `Jwt` inside `JwtAuthenticationToken`. | Authenticate and authorize protected API calls. |
| Opaque-token Resource Server | Bearer opaque access token. | `OAuth2AuthenticatedPrincipal` inside `BearerTokenAuthentication`. | Validate token via introspection and authorize API calls. |

In an **OIDC ID Token**, `sub` standardizes the End-User identifier for the OIDC Client. However, a Resource Server **cannot assume** that every incoming JWT is a valid access token merely because it contains `sub` or is signed by the same issuer.

For instance, an ID Token typically has `aud` targeting the OIDC Client, not the `orders-api` API. The API must reject tokens with the wrong purpose, audience, or token profile. This also explains why `JwtAuthenticationToken` **does not mean** “OIDC user session” or “the UserInfo endpoint was called”.

OIDC **UserInfo** is a protected resource that can supply profile claims to an OIDC Client when needed; it is not a default mandatory step for a Resource Server to create `JwtAuthenticationToken` on every API request.

## 13. Customizing the Principal Name with `JwtAuthenticationConverter`

By default, the principal name is usually based on `sub`. In some projects, developers want to change it to the `preferred_username` claim:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;

@Bean
JwtAuthenticationConverter customPrincipalNameConverter() {
    JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();

    converter.setPrincipalClaimName("preferred_username");
    return converter;
}
```

Then wire the converter **explicitly** into the JWT DSL:

```java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt
        .jwtAuthenticationConverter(customPrincipalNameConverter)))
```

In this example, `customPrincipalNameConverter` is the bean/converter injected into the chain builder method. For a valid token:

```json
{
  "sub": "user-123",
  "preferred_username": "alice"
}
```

`auth.getName()` can become `"alice"` while `auth.getToken().getSubject()` remains `"user-123"`.

**Important consequence:** if business code uses `authentication.getName()` as the owner key in the database, changing the converter can change the business identity without changing the token. `preferred_username` or email can also change over time and are not unique across issuers.

It is generally better to keep a **stable identifier** for authorization/auditing, such as issuer + subject or a mapping to an internal ID. Display names should be treated as UI attributes, not security keys.

## 14. Customizing Authorities from Role Claims While Keeping OAuth Scopes

Suppose the issuer emits:

```json
{
  "scope": "orders.read",
  "roles": ["SUPPORT"]
}
```

The API needs both `SCOPE_orders.read` and `ROLE_SUPPORT`. You can combine `JwtGrantedAuthoritiesConverter` for scopes with a separate role-mapping step:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

@Bean
JwtAuthenticationConverter roleAndScopeConverter() {
    JwtGrantedAuthoritiesConverter scopeConverter =
        new JwtGrantedAuthoritiesConverter();

    JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();

    converter.setJwtGrantedAuthoritiesConverter((Jwt jwt) -> {
        Collection<GrantedAuthority> result =
            new ArrayList<>(scopeConverter.convert(jwt));

        List<String> roles = jwt.getClaimAsStringList("roles");
        if (roles != null) {
            for (String role : roles) {
                if ("SUPPORT".equals(role)) {
                    result.add(new SimpleGrantedAuthority("ROLE_SUPPORT"));
                }
            }
        }

        return result;
    });

    return converter;
}
```

Wire it into the chain:

```java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt.jwtAuthenticationConverter(roleAndScopeConverter)))
```

This example only allows roles in the application's expected set (`SUPPORT`) rather than blindly prefixing every string from the token with `ROLE_*`. This **does not modify the token and does not re-run JWT signature validation**; the converter receives a `Jwt` already accepted by the decoder and maps it into authorities.

When using a custom converter:

- Ensure the JWT decoder still validates issuer, audience, and timestamps.
- Determine which claims the trusted Authorization Server is authorized to issue.
- Understand that `hasAuthority("SCOPE_orders.read")` differs from `hasRole("SUPPORT")` (which defaults to `ROLE_SUPPORT`).
- Do not treat `roles`/`scope` as permission to read every record; ownership/tenant policies are still required.
- A standalone converter bean **should not be assumed** to auto-attach to every chain; wire it into the JWT DSL as needed.

## 15. From `Jwt` to Internal Account: Do Not Trust Beyond the Contract

A verified access token proves the claims issued by the issuer within its validity period. It **does not necessarily provide current business state**, such as whether a customer has been suspended, a membership was just revoked, or which tenant an order belongs to.

Suppose the API receives a JWT:

```json
{
  "iss": "https://identity.example.com/realms/shop",
  "sub": "user-123",
  "scope": "orders.read",
  "tenant_id": "tenant-a",
  "email": "customer@example.com"
}
```

A system can use `iss + sub` to look up the **internal account**:

```text
external_identity
    issuer: https://identity.example.com/realms/shop
    subject: user-123
                  |
                  v
internal_user_id: 98765
                  |
                  v
account_status, active_memberships, tenant permissions
```

Layering data sources:

| Data | Initial Source of Trust | May Need Additional Verification? |
| --- | --- | --- |
| `iss`, `sub` | Verified JWT or introspection per contract. | Map to domain identity, issuer namespace. |
| `scope` | Access token issued by the issuer. | API policy and specific data constraints. |
| `tenant_id` in JWT | Issuer if agreed as authoritative source. | Current membership/tenant if policy requires. |
| `email`, `name` | Token profile claims. | Verified status, freshness, changes, and privacy. |
| Order ownership | Business database/authorization service. | Mandatory check when accessing records. |
| Account suspended after token issuance | Account system and revocation policy. | May require online check or short token lifetime. |

In multi-tenant systems, never let a client-sent `X-Tenant-Id` overwrite the tenant in the authentication context. A client-requested tenant can be a **selection parameter**, but the API must verify membership in that tenant from a trusted source.

## 16. Example Service Checking Owner After Obtaining a Valid `Jwt`

Suppose `/api/orders/{id}` requires `SCOPE_orders.read`. Even when the JWT is valid and the scope matches, the API must still prevent the caller from reading someone else's order.

An illustrative service:

```java
import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class OrderQueryService {

    private final OrderRepository repository;

    public OrderQueryService(OrderRepository repository) {
        this.repository = repository;
    }

    public OrderDto findVisibleOrder(long orderId, Jwt jwt) {
        String issuer = jwt.getIssuer().toString();
        String subject = jwt.getSubject();

        return repository
            .findByIdAndOwnerIssuerAndOwnerSubject(
                orderId,
                issuer,
                subject
            )
            .map(OrderDto::from)
            .orElseThrow(() ->
                new ResponseStatusException(HttpStatus.NOT_FOUND));
    }
}
```

`OrderRepository`, `Order`, and `OrderDto` are illustrative domain types to be implemented. The controller must receive `Jwt` via `@AuthenticationPrincipal` on a protected endpoint and pass it to the service; `SecurityFilterChain` checks `orders.read` beforehand.

In another application, `issuer + subject` may need to be mapped to an **internal user ID**, and ownership queried by that internal ID. If the token includes `tenant_id`, verify that the issuer actually has authority over tenants or confirm membership via dedicated data.

This example returns `404` when the record does not exist within the owner's scope to avoid leaking the existence of records outside the caller's view. Depending on the contract, the API may return `403`. What matters is that **object-level authorization** is enforced in the service/query rather than relying solely on a broad authority.

### Why Avoid Using `authentication.getName()` Unconditionally?

The following example contains a risky assumption:

```java
// Do not apply if getName() may have been customized
// or the token may represent a machine client.
String userId = authentication.getName();
return repository.findByOwnerUserId(userId);
```

If a converter changes the principal name from `sub` to `preferred_username`, owner data will be matched against a different key. If the token represents a service, `userId` does not reflect a human user. In systems with multiple caller types, pass a classified/mapped **domain caller identity** instead of relying on an uncontextualized `getName()` string.

## 17. How Does `SecurityContext` Exist During a Request?

After successful authentication, Spring Security stores `Authentication` in `SecurityContext` and makes it available to downstream components:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();
```

In a standard Servlet application, `SecurityContextHolder` defaults to a **ThreadLocal** strategy for the request thread. Therefore, you must not assume `Authentication` will automatically appear in any newly spawned thread or asynchronous callback outside the context propagated by the framework.

Cases to note:

- For requests that pass through the JWT Resource Server filter chain and authenticate successfully, the context holds the appropriate result for the remainder of the request.
- For `permitAll` endpoints, the context may have no Bearer principal or hold an anonymous authentication; handle null/anonymous if code reads it directly.
- For a stateless API, authentication is typically **rebuilt from the Bearer token on every request**, with no server login session assumed.
- When using `@Async`, executors, task queues, or asynchronous processing, if security context is truly needed, use Spring Security-supported propagation mechanisms or explicitly pass the minimal business identity.
- Never store `JwtAuthenticationToken` or raw JWTs in a shared cache or singleton to “reuse across future requests”; this can mix identities between callers.

For instance, when reading from a service that is not passed a `Jwt`, do not assume the context exists at every entry point (schedulers, batch jobs, event listeners). For flows not authenticated by the HTTP Resource Server, the system needs a **properly designed alternative identity source**, not a fake Bearer principal.

## 18. Principal Types When the Resource Server Receives an Opaque Token

Default with JWT authentication:

```text
Authentication: JwtAuthenticationToken
Principal: Jwt
Token data: Jwt claims
```

With an opaque token via introspection:

```text
Authentication: BearerTokenAuthentication
Principal: OAuth2AuthenticatedPrincipal
Token data: introspection attributes
```

An opaque-token API has corresponding configuration:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://identity.example.com/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

The chain must enable `.oauth2ResourceServer(oauth2 -> oauth2.opaqueToken(...))` instead of the usual JWT mechanism. **Do not cast `authentication.getPrincipal()` to `Jwt`** simply because the request carried a Bearer token. The principal type created depends on the authentication provider that verified the token.

If an application accepts both JWTs and opaque tokens across different endpoint groups, maintain a **shared domain identity abstraction** rather than letting every service depend on token-decoding specifics. The abstraction should preserve the issuer, subject, client type/actor, and truly required permissions.

## 19. What Happens When Authentication Fails?

An unaccepted token **must never be provided as a verified principal** to a protected endpoint:

| Scenario | Authentication | Authorization | Typical Outcome |
| --- | --- | --- | --- |
| Missing Bearer token on an endpoint requiring authentication. | No verified principal. | Cannot allow. | `401 Unauthorized`. |
| JWT with invalid signature, wrong issuer, or expired. | Fails at decoder/provider. | Token claims not used. | `401 Unauthorized`. |
| JWT with valid signature but wrong audience per API validator. | Fails per token policy. | Token claims not used. | `401 Unauthorized`. |
| Valid JWT but missing `SCOPE_orders.read`. | Succeeds, `JwtAuthenticationToken` created. | Insufficient authority. | `403 Forbidden`. |
| Valid JWT, sufficient scope, but wrong owner/tenant. | Succeeds. | Denied by domain policy. | `403` or `404`. |
| Valid JWT, right scope, and right resource. | Succeeds. | Allowed. | `2xx` if business processing succeeds. |
| `permitAll` endpoint without a Bearer token. | Verified JWT not required. | Public route allowed. | Proceeds per business logic. |

In OAuth 2.0 Bearer responses, a `401` may include the `WWW-Authenticate: Bearer` header, and invalid token errors may carry `invalid_token`. A successfully verified token lacking a required scope may lead to `insufficient_scope` depending on the access-denied handler.

**Do not conflate `401` errors with `403` errors**: the former typically indicates a rejected credential or missing authentication; the latter typically indicates a principal is present but lacks sufficient permissions.

## 20. Security-Prone Anti-Patterns

### 20.1. Base64-Decoding the JWT Payload and Trusting `sub`

```java
// ANTI-PATTERN pseudocode: do not use in production.
String rawToken = request.getHeader("Authorization");
String subject = decodePayloadWithoutSignatureCheck(rawToken)
    .get("sub").toString();

return orderService.getOrders(subject);
```

This snippet illustrates incorrect behavior; `decodePayloadWithoutSignatureCheck` is not a recommended Spring Security API. Anyone can forge a payload with `sub = admin`. The right approach is to receive a `Jwt` verified by the decoder or an `Authentication` from Spring Security.

### 20.2. Treating `Jwt` as an Internal User Entity

```java
String userId = jwt.getSubject();
userRepository.setAdmin(userId);
```

This abbreviated snippet skips issuer namespacing, caller kind checks, operation permission checks, and internal identity mapping. Never use `sub` as proof of permission to elevate account privileges.

### 20.3. Letting Clients Self-Declare Authorities Outside the Token

```http
GET /api/admin/reports
Authorization: Bearer <valid-user-token>
X-Role: ADMIN
X-User-Id: ceo
```

Client-sent `X-Role` and `X-User-Id` headers do not turn the caller into an admin. If an API gateway forwards authorized identity headers, the gateway/backend must enforce a trust boundary and strip spoofed headers from the Internet; never use arbitrary headers in place of the JWT principal.

### 20.4. Manually Constructing `JwtAuthenticationToken` from an Unverified Payload

In tests, you can create a mock `Jwt` and wrap it in a `JwtAuthenticationToken` to test policies. However, production code must never turn arbitrary HTTP input into an authenticated principal **without passing through JWT verification**. Having an object of type `JwtAuthenticationToken` does not prove the issuer or signature was checked if it was manually built from untrusted data.

### 20.5. Returning All Claims or the Raw Token from an API

`jwt.getTokenValue()` is a Bearer credential that can be replayed while still valid. `jwt.getClaims()` may contain email, name, tenant, and personal data. Never write raw tokens to logs, URLs, responses, exception messages, or telemetry; expose only attributes explicitly deemed necessary.

### 20.6. Checking Only `isAuthenticated()` to Grant Access to All Data

Having `SCOPE_orders.read` does not necessarily allow viewing everyone's orders. `authenticated()` requires a valid identity; `hasAuthority(...)` and domain policies determine actual permissions.

### 20.7. Changing a Converter and Forgetting Existing Rules

If you change the authority prefix or principal claim name, `hasAuthority("SCOPE_orders.read")`, audit identities, and owner lookups can change behavior. You must understand which converter is **actually used by the chain**; a converter bean declared without wiring it into the JWT DSL may not be applied.

## 21. Observing JWT Principals Without Leaking Credentials

When debugging requests with a Bearer JWT, logs should clearly separate the stages:

```text
[1] GET /api/orders/42
[2] Bearer extraction: token present (raw token not logged)
[3] JwtDecoder: signature/iss/timestamps/aud valid
[4] JwtAuthenticationToken created
[5] Principal: issuer=shop, subject=user-123
[6] Authorities: SCOPE_orders.read
[7] Endpoint policy: allowed
[8] Object policy: order 42 belongs to user-123 in tenant-a
[9] Response: 200
```

Conversely:

```text
[3] JWT invalid_signature
-> No verified JwtAuthenticationToken
-> Typically returns 401
```

Or:

```text
[3] Valid JWT
[4] JwtAuthenticationToken created
[6] Missing SCOPE_orders.write
-> Typically returns 403
```

These log entries are conceptual examples, not Spring Security's default logs. Real logs must comply with privacy policies and avoid logging raw tokens, full claims, and potentially sensitive identifiers when unnecessary.

Useful diagnostic signals include: configured issuer, authentication type, checked authority names, validator outcome by error category, trace ID, and endpoint path. In multi-issuer/multi-tenant systems, avoid logging only `sub` without issuer context and caller kind.

## 22. Testing Must Distinguish Principal Mapping from JWT Verification

Spring Security Test allows simulating a JWT principal in MockMvc, for example:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrdersApiTest {

    @Autowired
    MockMvc mvc;

    @Test
    void authenticatedJwtWithScopeCanReachEndpoint() throws Exception {
        mvc.perform(get("/api/orders/42")
            .with(jwt()
                .jwt(jwt -> jwt
                    .subject("user-123")
                    .claim("scope", "orders.read")
                    .claim("iss", "https://identity.example.com/realms/shop"))
            ))
            .andExpect(status().isOk());
    }
}
```

The test above is illustrative and assumes a controller/service returns `200` for order 42 belonging to user `user-123`; if data or rules differ, prepare appropriate fixtures/mocks. In Spring Security Test, `.with(jwt())` typically **creates a mock JWT `Authentication`** to test filter chain/authorization behavior, **without verifying a real JWT signature through the production `JwtDecoder`**.

Therefore, two distinct test groups are needed:

| Group | Goal | What Is Not Proven If Only This Group Is Tested |
| --- | --- | --- |
| **Authorization / principal mapping** with `jwt()` or a mock `JwtAuthenticationToken`. | Endpoint reads `Jwt`, `getName()`, and authorities properly; denies missing scope/wrong owner. | Does not prove the decoder actually rejects a JWT with a forged signature. |
| **JWT validation / integration** with tokens signed using test keys and a test issuer/JWKS. | Verifies signature, timestamps, issuer, audience, and creates `Authentication` through the real chain. | Does not by itself replace authorization tests across all business resources. |

Recommended test cases:

1. Request without a token to a protected API → authentication rejected.
2. JWT with invalid signature or expired → rejected by decoder/provider.
3. JWT with valid signature but invalid `iss` or `aud` → rejected by validator.
4. Valid JWT with `sub` and `scope` → creates principal and authorities per converter.
5. Valid JWT missing required scope → rejected by authorization.
6. Valid JWT with matching scope but different owner/tenant → rejected by domain policy.
7. User token vs. client-credentials token → service `sub` is not mistaken for a human user.
8. Custom principal claim name → `getName()` changes per converter while `jwt.getSubject()` still preserves `sub`.
9. Opaque principal → not cast to `Jwt` on paths supporting opaque tokens.

Separating these two test groups prevents “a controller test with a mocked JWT passed” from being misinterpreted as “API signature verification is working properly in production”.

## 23. API Lookup Table When Working with Post-Authentication Identity

| Developer Question | Component to Inspect | Reason |
| --- | --- | --- |
| Has the raw token been verified? | `JwtDecoder`, `JwtAuthenticationProvider`. | This is the trust boundary, not the controller. |
| What is the JWT's subject? | `Jwt.getSubject()`. | Reads the accepted `sub`. |
| Which issuer issued the subject? | `Jwt.getIssuer()`. | Avoids identifier collisions across issuers. |
| What principal name is Spring Security reporting? | `Authentication.getName()`. | May have been customized by a converter. |
| Which authorities does the API see? | `JwtAuthenticationToken.getAuthorities()`. | This is what `hasAuthority`/`hasRole` checks. |
| Can I inspect claims of the verified JWT? | `Jwt.getClaims()` or `getClaimAs...`. | Read only claims truly needed and per token profile. |
| Does the JWT have the right audience? | `JwtDecoder` + audience validator. | Must be verified before creating a trusted principal. |
| Is the subject a user or a service? | Issuer/token contract + domain identity resolver. | Cannot be inferred from the `JwtAuthenticationToken` class. |
| Is the caller allowed to read this order? | Scope + service/domain ownership policy. | A valid token alone does not grant access to a record. |
| Is an endpoint guaranteed to always have a JWT principal? | `SecurityFilterChain` matcher + authentication rule. | `permitAll`, opaque tokens, or other chains may yield another principal type. |
| How do I use the principal outside an HTTP request? | Explicitly passed identity context or proper security-context propagation. | Avoid relying on ThreadLocal in schedulers/async tasks. |

## 24. Decision Diagram When Reading Identity in a Resource Server

```mermaid
flowchart TD
    A["Request with Authorization: Bearer token"] --> B["Untrusted input credential"]
    B --> C{"Does decoder/provider accept token?"}
    C -- "No" --> D["Authentication fails, typically 401"]
    C -- "Yes, JWT" --> E["Jwt: verified headers + claims"]
    E --> F["JwtAuthenticationConverter"]
    F --> G["JwtAuthenticationToken: principal + name + authorities"]
    G --> H["SecurityContext"]
    H --> I{"Does endpoint have required scope/role?"}
    I -- "No" --> J["403 Forbidden"]
    I -- "Yes" --> K{"Valid caller kind, owner, tenant, policy?"}
    K -- "No" --> L["403/404 per policy"]
    K -- "Yes" --> M["Execute business logic"]
```

If the token is opaque, the success branch creates a different authentication/principal type, yet the principle holds: **identity must come from a trusted authentication result, and resource permissions are evaluated afterward**.

For all code working with `Jwt` and `JwtAuthenticationToken`, maintain three clear boundaries:

1. **Raw Bearer token → verified `Jwt`:** the token must pass through the decoder, signature check, and claim validators. Never trust an unverified payload.
2. **`Jwt` → `JwtAuthenticationToken`:** the converter produces the principal name and authorities from trusted claims; that is the context Spring Security uses, not an automatic user entity.
3. **`JwtAuthenticationToken` → business decision:** the API uses the principal/authorities per the token contract, checking subject type, issuer, ownership, tenant, and record-specific conditions.

**Key takeaway:** `Jwt` answers **what the verified token contains**; `JwtAuthenticationToken` answers **which principal and authorities Spring Security authenticates this request under**. What **that subject is allowed to do on which resources** must always be decided by appropriate authorization policies, and cannot be inferred solely from a `sub`, a scope, or the mere presence of a JWT.
