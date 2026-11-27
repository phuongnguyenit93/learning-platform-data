# Do Not Use ID Tokens or UserInfo as a Substitute for Access Token Verification

In a **Spring Security OAuth 2.0/OIDC Resource Server** system, an application typically integrates with an Authorization Server (AS) or OpenID Provider (OP) to validate access tokens and enforce authorization. Because OAuth 2.0 and OpenID Connect (OIDC) appear together in a login flow, developers often mistakenly think **ID tokens**, **UserInfo responses**, and **access tokens** are equivalent ways to prove API access permissions.

That misconception can introduce severe vulnerabilities. An **ID token** serves the **Relying Party (OIDC client)** to confirm a user's login event/identity; the **UserInfo endpoint** serves the client to retrieve user claims; the **access token** is the credential the **Resource Server** must validate when requests hit protected resources. A valid ID token or UserInfo returning the user's `sub` **does not prove** the Bearer access token sent to the API was issued for that API, is still valid, or carries the required scopes.

> **Core principle:** A Resource Server authenticates and authorizes requests based on an **access token appropriate for its resource**, via JWT validation or OAuth 2.0 token introspection (or another trusted access-token validation mechanism supported by the protocol/contract). Never replace that step with ID token inspection, UserInfo calls, or profile checks alone.

This lesson belongs to the **Issuer Integration** chapter. We will define the trust boundaries in OAuth 2.0/OIDC, distinguish each token's purpose, explain why one issuer issues tokens with multiple audiences, configure Spring Security Servlet/WebFlux, examine special cases requiring dedicated design, and build testing strategies against **token substitution**, **audience confusion**, **confused deputy**, and object-level authorization flaws.

## 1. Three Components: Access Token, ID Token, and UserInfo

### 1.1. Quick Comparison

| Property | **OAuth 2.0 Access Token** | **OIDC ID Token** | **UserInfo Response** |
|---|---|---|---|
| Purpose | Lets a client call protected resources authorized by the AS | Lets a Relying Party verify the login event and receive identity | Provides End-User claims to a Relying Party |
| Intended recipient | Specific **Resource Server/API** | **OIDC client**, typically with audience = `client_id` | **OIDC client** that called the UserInfo endpoint |
| Where it is normally sent | `Authorization: Bearer ...` to the API | Token response returned to client, validated by client | HTTP response from the UserInfo endpoint |
| Format | Opaque or JWT, depending on AS/token profile | **JWT** per OIDC Core | JSON object (may be signed/encrypted per contract) |
| Key checks | Signature or `active` from introspection; `iss`, `aud`, time, token type, scopes | Signature, `iss`, `aud=client_id`, time, `nonce`/`azp`, and matching OIDC bindings | Trusted HTTPS source, UserInfo's access token, and `sub` matching the ID token at the RP |
| Represents permission to call Orders API? | Possibly, if issued for the API with matching scopes/permissions | **Not automatically** | **No** |
| Can represent a service without a user? | **Yes** (client credentials) | Typically does not appear in client-credentials flows | Typically inappropriate for flows without an End-User |

**The decisive distinction is audience/purpose**: the same issuer can emit a valid ID token for `orders-web-client` and a valid access token for `orders-api`. The Resource Server must know which credential type it is allowed to accept. A valid ID token signature only proves the OP issued it; it does not turn it into an API access token.

### 1.2. Visualizing the Two Journeys

```mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant RP as Web App / OIDC Client
    participant OP as OpenID Provider
    participant API as Orders Resource Server
    U->>RP: Clicks Sign In
    RP->>OP: Authorization Code + PKCE flow
    OP-->>RP: Authorization code
    RP->>OP: Exchanges code at token endpoint
    OP-->>RP: ID token + access token (and possibly refresh token)
    RP->>RP: Validates ID token for client identity/session
    opt User claims needed
        RP->>OP: GET /userinfo + appropriate access token
        OP-->>RP: UserInfo claims
        RP->>RP: Verifies sub matches ID token
    end
    RP->>API: GET /api/orders + Bearer access token
    API->>API: Validates access token for orders-api
    API->>API: Checks scope + tenant + ownership
    API-->>RP: Data if permitted
```

In this diagram, the client may perform **both ID token validation and API access-token validation**, yet each answers a different question. The API **does not inherit** the RP's ID-token validation result unless the architecture explicitly defines a secure, dedicated identity translation/delegation mechanism. A successful login at the RP does not automatically make a Bearer token sent to the API valid.

### 1.3. Distinguishing Two Questions

The OIDC client asks:

```text
Has the user been authenticated by the OP for my client?
Does this ID token have the right issuer, audience, nonce, and lifetime?
```

The Resource Server asks:

```text
Has this Bearer access token been verified by a trusted issuer?
Was the token issued for THIS SPECIFIC API?
Is the token still valid and does it have the required scope?
Is the principal authorized for the requested object/tenant?
```

You cannot take the answer to the first question as the conclusion for the second.

## 2. Why Cannot an ID Token Replace an Access Token?

Under **OpenID Connect Core 1.0**, an ID token is a JWT containing claims about an End-User's authentication event at the OP, issued to the Relying Party. In most login flows, the ID token's `aud` contains the **OIDC client ID**, such as `orders-web-client`.

An illustrative ID token:

```json
{
  "iss": "https://identity.example.com/realms/shop",
  "sub": "user-842",
  "aud": "orders-web-client",
  "iat": 1893459000,
  "exp": 1893459600,
  "auth_time": 1893458900,
  "nonce": "nonce-created-by-rp"
}
```

This payload is purely illustrative, not a signed JWT; timestamps do not represent real tokens. This token can be **completely valid when the OIDC client verifies** `aud=orders-web-client`, yet **invalid as an access token for the Orders API**, which requires `aud=orders-api`.

### 2.1. Two Tokens from the Same Issuer, for the Same User

ID token:

```text
typ: JWT (ID token)
iss: https://identity.example.com/realms/shop
sub: user-842
aud: orders-web-client
```

Access token for the API:

```json
{
  "iss": "https://identity.example.com/realms/shop",
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "client_id": "orders-web-client",
  "iat": 1893459000,
  "exp": 1893459600
}
```

Both may be signed by the OP/AS with **the same key set**. If the Resource Server only verifies the signature and `iss` while skipping `aud` or token type/profile, it can accept the **web client's ID token** as an API credential. This is a variant of **cross-JWT confusion/token substitution**.

### 2.2. Valid Signature Does Not Mean Right Token Type

```text
JWT signature valid
        |
        +-- Issuer belongs to trusted set
        |
        +-- Yet audience = orders-web-client
        |
        v
NOT SUFFICIENT to call Orders API.
```

A signature proves the **origin and integrity** of claims, not that the token may be used anywhere. Audience and token profile add the boundary of **who is permitted to accept that token**.

### 2.3. `sub` Is Not an Access Permission

When an ID token contains:

```json
{"sub":"user-842","email":"user@example.com"}
```

`sub` identifies the subject within the issuer, not the `orders.read` permission. Email, name, picture, locale, `preferred_username`, and profile claims are likewise not API permissions by default.

Even with a verified **access token**, `sub=user-842` does not grant permission to read other users' orders. The Resource Server must still verify ownership, tenant, state, and per-object policies.

### 2.4. ID Token Validation Is the OIDC Client's Job

The OIDC client must validate the ID token, including:

- Signature/issuer/trust chain against the OP.
- `aud` containing the exact client ID; handling `azp` if required by the OIDC contract.
- `exp`, `iat`, and time constraints.
- `nonce` when the request/flow used a nonce.
- Checks for `auth_time`, `acr`, and `amr` if the client requires an authentication level.
- Binding to the authorization response, state/PKCE, redirect URI, and client session.

That checklist serves **client login**, not the Resource Server's access token checklist.

## 3. Why Cannot UserInfo Replace Access Token Verification Either?

The OIDC **UserInfo endpoint** is a protected resource provided by the OpenID Provider. A Relying Party can call it with an appropriate access token to receive user claims authorized for sharing.

Example:

```http
GET /userinfo HTTP/1.1
Host: identity.example.com
Authorization: Bearer access-token-for-userinfo
```

Response:

```json
{
  "sub": "user-842",
  "name": "Example User",
  "preferred_username": "example-user",
  "email": "user@example.com",
  "email_verified": true
}
```

This can work well for the RP to display a name/avatar/email after user login, depending on scopes, consent, and OP contract. However, **it does not prove the bearer credential was issued for the Orders API**.

### 3.1. UserInfo Validates Tokens for the UserInfo Resource, Not Every API

Suppose token A is accepted by the OP at `/userinfo`:

```text
GET https://identity.example.com/userinfo
Authorization: Bearer token-A
-> 200 {"sub":"user-842"}
```

From that event, the Orders API **must never conclude**:

```text
token-A has aud=orders-api;
token-A has SCOPE_orders.read;
token-A is allowed to operate on order-123;
token-A matches the API's required access token profile;
token-A will remain valid for a subsequent operation.
```

The UserInfo endpoint has its own policy. A token may work for UserInfo without having any authorization at the Orders API. Conversely, a machine-to-machine API access token can be completely valid even though **calling UserInfo fails** because there is no End-User.

### 3.2. UserInfo Is a Profile Source, Not an Introspection Endpoint

Two HTTP endpoints with different contracts:

| Issuer API | Purpose | Typical Output |
|---|---|---|
| **UserInfo (OIDC)** | Returns End-User claims to a Relying Party | `sub`, `name`, `email`, and granted claims |
| **Introspection (RFC 7662)** | Lets authorized protected resources/clients query token status and metadata | `active`, `scope`, `sub`, `client_id`, `aud`, `iss`, `exp` if provided by AS |
| **Token endpoint** | Exchanges authorization code, refresh token, client credentials, etc. for tokens | Token response, not an API authorization decision |
| **JWKS endpoint** | Publishes public keys for verifiers to check token signatures per trust config | JWK Set; not an answer to "is this token active?" |

Do not call `/userinfo` and infer `active=true`, `aud=orders-api`, or scopes when the endpoint provides none of those proofs. **RFC 7662 introspection** defines the contract for querying access token status.

### 3.3. The OIDC Client's `sub` Rule

When a Relying Party consumes a UserInfo response, **OIDC Core requires verifying that UserInfo's `sub` matches the `sub` in the corresponding ID token**; otherwise, UserInfo claims must not be used.

```text
RP validated ID token:  sub = user-842
RP calls UserInfo:      sub = user-999
=> Do not use these UserInfo claims.
```

That rule protects **binding profile claims to the user logged in at the RP**. It is **not** an access-token authentication step for the API. Never interpret "the two `sub`s match" as "the Bearer token's scope/audience is valid."

### 3.4. Privacy and Load Risks

Calling UserInfo on every API request just to "authenticate" can:

- Trigger unnecessary network calls, increasing latency and coupling to OP availability.
- Collect email, profile, phone, or PII that the API does not need.
- Cause logs/metrics to inadvertently capture tokens or UserInfo responses.
- Conflate OAuth API scopes with user consent to share profile claims.
- Break client-credentials flows that have no End-User.

To verify tokens, use **access-token verification**; to display profiles to a client, use UserInfo for its intended OIDC purpose while respecting consent and data minimization.

## 4. Wrong Flow: Using an ID Token as a Bearer Access Token

Example where a client mistakenly sends:

```http
GET /api/orders/ORD-123 HTTP/1.1
Host: api.example.com
Authorization: Bearer ID_TOKEN_FOR_WEB_CLIENT
```

If the Resource Server does:

```text
parse token -> decode JWT -> signature valid -> read sub
-> create Authentication(user-842) -> allow
```

then the API lacks **audience/token-purpose binding**. An ID token issued for a web client can be sent to the API and treated as an authorizing credential. The risk escalates when a system has multiple clients sharing an issuer and JWKS.

### 4.1. The Right Authentication Path

```mermaid
flowchart TD
    A["Authorization: Bearer credential"] --> B{"Access-token profile supported by API?"}
    B -->|"No"| X["Reject authentication"]
    B -->|"JWT access token"| C["JwtDecoder with trusted issuer/key source"]
    B -->|"Opaque access token"| D["OpaqueTokenIntrospector with trusted AS"]
    C --> E{"Signature, iss, aud, time,<br/>type/profile valid?"}
    D --> F{"active + resource/audience<br/>and metadata contract valid?"}
    E -->|"No"| X
    F -->|"No"| X
    E -->|"Yes"| G["Authenticated Authentication"]
    F -->|"Yes"| G
    G --> H{"Required scope/authority?"}
    H -->|"No"| Y["403 / deny"]
    H -->|"Yes"| I{"Tenant, owner, and object policy?"}
    I -->|"No"| Y
    I -->|"Yes"| J["Allow processing"]
```

An ID token does not enter this branch merely because it is a signed JWT. For APIs accepting JWT access tokens under a specific profile like **RFC 9068**, the verifier can additionally require `typ=at+jwt` or other profile constraints. Follow the exact Authorization Server contract; never rely solely on file names, three-dot structure, or self-declared claims.

### 4.2. `at_hash` in an ID Token Also Does Not Replace Access Token Verification

In some OIDC flows, the ID token contains an `at_hash` claim so the Relying Party can check binding between the access token and ID token per OIDC rules. Yet `at_hash`:

- Does not prove the access token was issued for `orders-api`.
- Does not replace the Resource Server's `aud`/`scope`/issuer/time/active checks.
- Does not make the ID token an access token.
- Does not create permissions on business data.

`at_hash` belongs to token-binding checks on the **OIDC client** side for eligible flows. The API must still verify the **access token presented to the API**.

### 4.3. Special Cases Requiring Dedicated Design

Some systems have an **explicitly designed** protocol using an identity assertion or ID-token-like JWT for a specific service. Even then, it should not be treated as an OAuth 2.0 access token. Accepting such an assertion requires defining a **separate authentication protocol**: issuer, exact service audience, replay prevention, nonce/challenge where appropriate, lifetime, purpose, caller binding, permissions, and migration rules.

Never silently enable "accept ID tokens as API Bearer" just because an SDK sent the wrong token. If the goal is delegated API access, the standard solution is requesting an **access token with the right audience** or performing a **token exchange** through a trusted Authorization Server.

## 5. What Is an Access Token and What Must the Resource Server Verify?

An OAuth 2.0 access token is a credential used to access protected resources. **The format does not have to be JWT**: a token can be an opaque/reference string or a self-contained JWT depending on the AS implementation.

### 5.1. JWT Access Tokens

For a JWT access token targeting the Orders API, the API must verify:

1. **Source of trust:** `iss` matches the configured/allowlisted issuer, never an arbitrary issuer from the bearer token.
2. **Signature:** valid JWS signature using a trusted public key/key source and policy-allowed algorithm.
3. **Audience:** `aud` contains the exact resource identifier, such as `orders-api`.
4. **Time:** `exp`, `nbf`, clock skew, and matching token profile; reject expired tokens.
5. **Token purpose/profile:** it is an access token accepted by the API, not an ID token or another misused JWT; `typ`/`token_use` may be required per issuer contract.
6. **Authorities:** scopes/roles/permissions mapped from **verified** claims, never from client-sent headers.
7. **Business authorization:** is the user/client/tenant permitted to act on this object?

These are layered checks. No step may be replaced with `GET /userinfo`.

### 5.2. Opaque Access Tokens

With opaque tokens, the Resource Server does not need—and usually cannot—parse claims locally. It uses an `OpaqueTokenIntrospector` calling a trusted introspection endpoint under **RFC 7662**, receiving a principal or an error.

Illustrative response:

```json
{
  "active": true,
  "iss": "https://identity.example.com/realms/shop",
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read orders.update",
  "client_id": "orders-web-client",
  "exp": 1893459600
}
```

The AS may omit certain fields depending on token type/contract, while `active` is mandatory in an introspection response. The Resource Server needs a strong **token-resource binding** agreement—especially audience, issuer, and type when the AS serves multiple resources.

`active=true` does not mean "allowed to do anything": the token might lack the required scope or belong to a different tenant. Conversely, if introspection fails due to an AS timeout, **never** synthesize a principal with default scopes.

### 5.3. Scope, Audience, and Identity Answer Different Questions

| Property | Question Answered | Example |
|---|---|---|
| `iss` | Who is the trusted issuer? | `https://identity.example.com/realms/shop` |
| `aud` | Which resource/recipient is the token for? | `orders-api` |
| `sub` | Who is the subject within the issuer's scope? | `user-842` |
| `client_id` | Which OAuth client is associated with the token? | `orders-web-client` |
| `scope` | What operation scope was granted? | `orders.read` |
| `tenant_id` (extension) | Which tenant is the token bound to per contract? | `tenant-a` |
| Ownership/ACL in DB | May the actor access this order? | Order belongs to user in tenant A |

`email_verified=true` in an ID token or UserInfo cannot replace any `aud` or `scope` check here.

## 6. Why Are Tokens from the Same Issuer Easily Confused?

In an IdP implementing OAuth 2.0 + OIDC, the same OP/AS may issue:

- ID tokens for browser/desktop/mobile clients.
- Access tokens for the UserInfo endpoint or another resource.
- JWT access tokens for the Orders API.
- Opaque access tokens for the Billing API.
- Refresh tokens for clients to obtain fresh access tokens.
- JWT assertions for client authentication or token exchange.

Multiple types may share the same `iss`, same `sub`, and signatures from the same key. If the Resource Server merely does:

```java
if (jwtHasValidSignature && trustedIssuer.equals(jwt.getIssuer())) {
    allow();
}
```

it has not verified the right **token type/audience**. That opens the door to **cross-JWT confusion**: a token valid in context A gets replayed in context B.

### 6.1. Token Substitution

An example:

```text
OIDC web client: orders-web
API: orders-api

OP issues ID token:
  aud = orders-web
  sub = user-842
  signature = valid

Attacker/client sends ID token to:
  GET /api/orders/ORD-123

API checks only signature + iss + sub:
  -> mistakenly treats ID token as a bearer access token
```

**Mitigation:** the Resource Server must check the exact **API audience**, token profile, and scopes. Under RFC 9068, that is a dedicated JWT access token profile; with other ASs, an equivalent tested contract is required.

### 6.2. Confused Deputy from a Token Intended for Another API

A valid token:

```json
{
  "iss": "https://identity.example.com",
  "aud": ["billing-api"],
  "scope": "orders.read",
  "sub": "user-842"
}
```

if accepted by the Orders API merely because `scope=orders.read` is present, causes the API to accept a token never issued to it. Scope names can overlap across resources; **audience/resource binding** ensures the token was issued for the intended recipient.

### 6.3. UserInfo Response Substitution

An RP could receive UserInfo for user A and mistakenly store claims in user B's session due to a token/session mix-up. That is why the RP must verify `sub` matches the ID token before using claims. Even when they match, that only proves **the UserInfo response belongs to the right logged-in account at the RP**—not that an API Bearer token has the right audience, scopes, or active status.

## 7. Spring Security Servlet: Validating JWT Access Tokens Properly

An Orders API using **Spring Security Servlet** can configure a JWT Resource Server:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

In some Spring Boot versions, starter/resource-server dependencies already pull in compatible security modules; declarations can be trimmed per the current BOM. What matters is using the **Resource Server stack**, not the OAuth client login stack.

### 7.1. Declaring Issuer and Audience

Example configuration:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/realms/shop
          audiences:
            - orders-api
```

`issuer-uri` points to the trusted issuer. In Spring Boot versions supporting `audiences`, this property enforces recipient binding. If you are on an older version or supply a custom `JwtDecoder` bean, verify that an audience validator is actually attached; **never assume YAML alone makes every decoder check audience**.

### 7.2. Configuring HTTP Authorization

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
public class OrdersResourceServerSecurity {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            // Example pure Bearer-header API without browser cookies
            // as credentials for write requests.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
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
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

This is an illustrative Spring Security 6.x configuration. Spring Security relies on `JwtDecoder` to verify the access token, then maps scopes to authorities like `SCOPE_orders.read`. HTTP rules check **authorities from the verified access token**. Nowhere does the API call UserInfo or accept ID tokens.

Because `securityMatcher("/api/**")` only covers the selected URL group, the application must have another chain or fallback protecting endpoints outside `/api/**`. CORS/CSRF, actuator, health, and forward/error dispatches need separate policies matching the deployment model.

### 7.3. Explicit Validators When Strict Control Is Required

If you need explicit control over JWKS, algorithms, and per-issuer audience, build a `JwtDecoder`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Bean
JwtDecoder ordersJwtDecoder(
        @Value("${app.security.issuer}") String expectedIssuer,
        @Value("${app.security.jwks-uri}") String jwksUri,
        @Value("${app.security.audience}") String expectedAudience) {

    NimbusJwtDecoder decoder = NimbusJwtDecoder
        .withJwkSetUri(jwksUri)
        .jwsAlgorithm(SignatureAlgorithm.RS256)
        .build();

    OAuth2TokenValidator<Jwt> issuerAndDefaults =
        JwtValidators.createDefaultWithIssuer(expectedIssuer);

    OAuth2TokenValidator<Jwt> audience = jwt ->
        jwt.getAudience().contains(expectedAudience)
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Unexpected resource audience",
                    null));

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
            issuerAndDefaults, audience));

    return decoder;
}
```

Corresponding `application.yml`:

```yaml
app:
  security:
    issuer: https://identity.example.com/realms/shop
    jwks-uri: https://identity.example.com/realms/shop/jwks
    audience: orders-api
```

`jwks-uri` above is a **placeholder path** and must be replaced with the verified URI published by your issuer; never append an arbitrary path to the issuer and assume it works. `RS256` is only appropriate if the issuer contract uses that algorithm; never enable extra algorithms needlessly just "to make tokens pass."

**Important:** `setJwtValidator(...)` sets a new validator. If you pass only the audience validator and omit `issuerAndDefaults`, you accidentally lose issuer/timestamp checks. The example combines them. When using the **RFC 9068** JWT access token profile, also check `typ`/token-use and profile requirements supported by your library/AS version.

### 7.4. Never Treat a Manually Constructed `JwtAuthenticationToken` as Proof

Anti-pattern:

```java
// Wrong: building Authentication from claims not verified by a decoder.
Jwt forged = Jwt.withTokenValue(rawBearer)
    .header("alg", "none")
    .claim("sub", request.getParameter("user"))
    .claim("scope", "orders.delete")
    .build();

SecurityContextHolder.getContext()
    .setAuthentication(new JwtAuthenticationToken(forged));
```

`Jwt.withTokenValue(...).build()` is fine in a **test fixture** for a `Jwt` object, yet **never verifies signatures**. Production must use a trusted `JwtDecoder` inside the Resource Server authentication flow.

## 8. Spring Security Servlet: Opaque Access Tokens via Introspection

If the AS issues **opaque tokens**, the Resource Server can use:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://identity.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: "${INTROSPECTION_CLIENT_SECRET}"
```

Security chain:

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults()))
```

Depending on version, Spring Security uses an `OpaqueTokenIntrospector` implementation to call the endpoint and validate tokens. **This is token introspection**, not UserInfo. It requires trusted client credentials/HTTPS, timeouts, and `active`/audience/scope policies.

### 8.1. Introspection Response and Scope Mapping

```json
{
  "active": true,
  "iss": "https://identity.example.com/realms/shop",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "sub": "user-842",
  "client_id": "orders-web-client"
}
```

Standard opaque resource server flows map `orders.read` to `SCOPE_orders.read`. However, some ASs return minimal metadata; the Resource Server must establish a **resource-appropriate access token contract**. If audience checking is required and the AS returns `aud`, wrap the introspector to enforce it.

### 8.2. Decorator Without Replacing the Delegate

```java
import java.util.Collection;
import java.util.Objects;

import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection
    .BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection
    .OpaqueTokenIntrospector;

public final class OrdersAudienceIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;
    private final String audience;

    public OrdersAudienceIntrospector(
            OpaqueTokenIntrospector delegate,
            String audience) {
        this.delegate = Objects.requireNonNull(delegate);
        this.audience = Objects.requireNonNull(audience);
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        // Accept principal only after the delegate has verified the token.
        OAuth2AuthenticatedPrincipal principal =
            delegate.introspect(token);

        Object rawAudience = principal.getAttribute("aud");
        boolean matches =
            (rawAudience instanceof String value
                && audience.equals(value))
            || (rawAudience instanceof Collection<?> values
                && values.contains(audience));

        if (!matches) {
            throw new BadOpaqueTokenException(
                "Access token audience is not accepted");
        }
        return principal;
    }
}
```

The decorator merely **adds policy** on top of a trusted introspection result. It does not call UserInfo, fabricate `active=true`, or add `SCOPE_orders.read` if the AS did not grant it. If the delegate reports inactive or a network error, never create a fallback principal.

### 8.3. Inactive Tokens and AS Errors

| Response/Status | Behavior |
|---|---|
 `{"active":false}` | Authentication fails |
 `{"active":true,"scope":"orders.read"}` | Can authenticate; proceed to resource/authority policy |
 Wrong audience | Rejected per policy |
 AS timeout/5xx | No proof token is active; **fail closed** |
 Response missing contract-required info | Reject/raise error; never guess |

An AS infrastructure failure does not necessarily mean the token was permanently invalidated. The final HTTP status may differ from 401 depending on exception handlers, yet **requests must never be permitted** when verification cannot succeed.

## 9. WebFlux: APIs Must Also Verify Access Tokens

In **Spring WebFlux**, the Servlet equivalents are `SecurityWebFilterChain`/`ServerHttpSecurity`, `ReactiveJwtDecoder`, and `ReactiveOpaqueTokenIntrospector`.

### 9.1. JWT Resource Server in WebFlux

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive
    .EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveOrdersSecurity {

    @Bean
    SecurityWebFilterChain webFluxSecurity(ServerHttpSecurity http) {
        return http
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.create")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

This is a pure Bearer-header API. If browsers send cookies/sessions, configure a separate CSRF policy. The reactive decoder must still verify issuer/audience/time/signature/token profile; never accept an OIDC client ID token merely because it is a validly signed JWT.

### 9.2. Opaque Tokens in WebFlux

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults()))
```

Spring Security uses `ReactiveOpaqueTokenIntrospector` returning `Mono<OAuth2AuthenticatedPrincipal>`. The valid authentication path is:

```text
Bearer opaque access token
    -> ReactiveOpaqueTokenIntrospector
    -> Mono<OAuth2AuthenticatedPrincipal> (only when token is valid)
    -> Reactive Authentication
    -> Reactor SecurityContext
    -> authorizeExchange / method/domain authorization
```

Do not do this:

```java
// DO NOT DO THIS: UserInfo only returns profile, not an API token verifier.
return userInfoWebClient.get()
    .uri("/userinfo")
    .headers(h -> h.setBearerAuth(token))
    .retrieve()
    .bodyToMono(UserProfile.class)
    .map(profile -> authenticationWithAllScopes(profile.sub()));
```

This snippet treats UserInfo as the source granting `SCOPE_` for the Orders API; it completely lacks `aud`/token profile/resource-specific scope bindings. If UserInfo returns 200, broken code can grant every permission in its own policy.

### 9.3. Avoid Blocking in Reactive Authentication

Never use:

```java
return Mono.just(blockingUserInfoCall(token));
```

or:

```java
return introspector.introspect(token).block();
```

on the Netty event loop. Use the proper Spring Security reactive components. `Mono` defers work until subscription; never manually call `.subscribe()` detached from the security filter, as errors can be swallowed and race with business logic.

## 10. Applications Acting as Both OIDC Client and Resource Server

This is the easiest scenario to confuse:

```text
One Spring Boot application:
  /web/**  : OAuth2 Login / OIDC Relying Party
  /api/**  : OAuth2 Resource Server
```

The application may:

- Use `oauth2Login()` to sign in browser users; the Spring Security OAuth client handles OIDC ID tokens and UserInfo.
- Use `oauth2ResourceServer().jwt()` or `opaqueToken()` for REST endpoints receiving access tokens.

Both flows **can share the same issuer and user database**, yet have different **authentication contracts**.

### 10.1. Separating via Multiple Filter Chains

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SplitClientAndResourceSecurity {

    @Bean
    @Order(1)
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/web/**", "/login/**",
                "/oauth2/**", "/logout")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/oauth2/**", "/login/**")
                    .permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
```

This pattern **illustrates separation**, not a complete config for every endpoint; login callbacks, authorization-request base URIs, CSRF logout, routing, error dispatches, public assets, and fallback chains must all be reviewed per application. The key is that browser/OIDC login does not automatically authorize Bearer API access.

### 10.2. Browser Sessions Do Not Replace Bearer Tokens

A browser signed into `/web/**` may send `JSESSIONID` to the same host. If `/api/**` requires a Bearer access token, **do not allow the API to accidentally reuse an existing session Authentication** and bypass Bearer checks.

Similarly, an API request carrying an ID token:

```http
Authorization: Bearer <id_token>
```

must never become an authenticated request merely because the web login module understands that ID token in its OIDC client context.

### 10.3. Backend-for-Frontend (BFF) Must Separate Two Boundaries

In a BFF:

```text
Browser cookie -> protected BFF session (OIDC login)
BFF -> downstream Orders API with appropriate access token
```

The BFF can validate the browser session and call APIs server-side using an access token obtained by the authorized client. Downstream Resource Servers must still validate the **access token intended for them**. If a BFF intentionally acts as a trusted proxy using a different service-to-service protocol, that is a **separate trust delegation architecture** requiring mTLS/signatures/audience/authorization; never treat UserInfo or cookie sessions as access tokens.

## 11. Controlling Token Purpose and Audience During Issuer Integration

When onboarding an IdP/AS for the Orders API, you need an **access token contract**, not just metadata saying "the issuer works":

1. Exact Issuer URI of the Authorization Server.
2. Access token format (JWT or opaque); both may be supported if routed under strict control.
3. Orders API's audience/resource identifier.
4. Scope catalog and semantics: `orders.read`, `orders.create`, `orders.update`, `orders.delete`.
5. Token lifetime, refresh/revocation, and key rotation.
6. Signing algorithms/certificates or introspection endpoint/client credentials.
7. Token type/profile: RFC 9068, vendor-specific `typ`/`token_use`/`scp`, and parsing rules.
8. Identity model: how user access tokens differ from client-credentials tokens.
9. Tenant/membership/issuer binding.
10. Contract tests with tokens having **right and wrong audiences**, ID tokens, and tokens for other APIs.

### 11.1. Never Infer Issuer from an Unverified Token

A Resource Server can read `iss` from an unverified JWT to **select a decoder from a trusted registry** when supporting multiple issuers. Never do:

```java
String issuer = parseUnverifiedJwt(token).getIssuer();
JwtDecoder decoder = JwtDecoders.fromIssuerLocation(issuer);
```

without an issuer allowlist; an attacker can force the server to fetch discovery/JWKS from an unintended URL (**SSRF**) and instantiate a verifier trusting an unmanaged source. The selected decoder must also verify the signature and ensure the **final issuer** matches the selected issuer.

### 11.2. Same `sub` Does Not Mean Same Identity

Both Issuer A and Issuer B can issue `sub=user-842`. A safe identity key starts from:

```text
identity = (verified issuer, subject)
```

Matching `sub` in an OIDC ID token and UserInfo does not solve cross-issuer/cross-tenant identity for the API. Use controlled account linking rather than inferring identity from email.

### 11.3. Never Elevate Privileges from Profile Claims

Anti-pattern:

```java
if (userInfo.email().endsWith("@example.com")) {
    grant("SCOPE_orders.delete");
}
```

Email domains and UserInfo profiles are identity/display data, not default API authorization policies. Even verified emails do not replace token permissions and authoritative business data. If an organization pulls group memberships/entitlements from a separate authorization source, establish clear trust/audience/tenant contracts, mappings, freshness, and auditing—**never call UserInfo and treat every claim as a privilege**.

## 12. Machine-to-Machine: Cases Without ID Tokens or UserInfo

With the **OAuth 2.0 Client Credentials Grant**:

```mermaid
sequenceDiagram
    participant S as Order Worker
    participant AS as Authorization Server
    participant API as Orders API
    S->>AS: client_credentials, client auth, scope/resource
    AS-->>S: access token
    S->>API: Authorization: Bearer access-token
    API->>API: Verify JWT or introspect opaque token
    API->>API: Check aud, scope, service identity, tenant
    API-->>S: Allowed or denied
```

There is no interactive End-User, so this flow normally **has no ID token**; `/userinfo` also makes no sense for returning an End-User profile. Designing a Resource Server to assume "every Bearer token must be accompanied by an ID token" or "must call UserInfo to see who logged in" breaks machine-to-machine flows and encourages dangerous bypasses.

### 12.1. A Service Principal Is Not a User Principal

An access token may contain:

```json
{
  "iss": "https://identity.example.com",
  "aud": ["orders-api"],
  "client_id": "order-worker",
  "scope": "orders.reconcile",
  "exp": 1893459600
}
```

`sub` may be absent or carry client semantics depending on the AS. The Resource Server must verify **client identity/subject per token profile**, never inventing a `userId` from UserInfo to fit a human login model.

### 12.2. Risk of Forcing Service Tokens into User Models

If code tries:

```text
access token -> /userinfo -> no sub -> fallback admin
```

a service token can be assigned a human identity or untrusted admin privileges. The right design is a **service principal model** with dedicated scopes, resource audience, and business ACLs.

## 13. 401, 403, and Denial Decision Points

In a Resource Server, two common failure categories:

| Scenario | Layer | Typical Outcome |
|---|---|---|
| Missing Bearer access token | Authentication | 401 |
| Bearer is an ID token with `aud=orders-web-client` | Access token validation | **401** because it is not a valid API token |
| JWT bad signature/unknown issuer/expired | JWT decoder | 401 |
| Opaque token `active=false` | Introspection | 401 |
| Token for `billing-api` sent to Orders API | Audience validation | 401 |
| Valid token missing `SCOPE_orders.read` | Authorization | **403** |
| Valid token yet different tenant/owner | Domain authorization | 403 or 404 per policy |
| UserInfo returns profile yet access token has wrong audience | Access token validation | **401**, never overridden by profile |
| Introspection endpoint times out | Infrastructure/authentication unavailable | Must fail closed; HTTP status depends on exception handling |

Per RFC 6750, Bearer APIs may return `WWW-Authenticate: Bearer` with `invalid_token` or `insufficient_scope` where appropriate. Custom exception handlers or gateways may alter bodies/statuses, yet **must never turn an invalid token into an authenticated request**.

### 13.1. Never Turn a Bad Token into "Guest Logged In"

Anti-pattern:

```java
try {
    Authentication auth = validateAccessToken(token);
    return auth;
} catch (Exception ex) {
    // DO NOT DO THIS: granting permissions when validation fails.
    return new UsernamePasswordAuthenticationToken(
        "guest",
        null,
        List.of(new SimpleGrantedAuthority(
            "SCOPE_orders.read")));
}
```

Even if "guest" only gets a read scope, a client without valid credentials has been granted privileges. If an endpoint is genuinely public, declare `permitAll` properly and enforce data policies—**never fake a scoped principal**.

## 14. Issuer Integration Mistakes That Lead to Token Misuse

### 14.1. Frontend Sends ID Token Instead of Access Token

Some SDKs return multiple fields:

```json
{
  "id_token": "...",
  "access_token": "...",
  "token_type": "Bearer",
  "expires_in": 3600
}
```

If the client mistakenly picks `id_token` for `Authorization: Bearer`, the API returns 401 when audience/type validation is properly configured. The fix is **updating the client to send the resource-targeted access token**, not disabling validation on the API.

### 14.2. API Uses Client ID Instead of Resource Audience

In OIDC:

```text
ID token:     aud = orders-web-client
Access token: aud = orders-api
```

If the Resource Server sets `audience=orders-web-client` to test ID tokens conveniently, it will accept tokens issued for the RP rather than the API. The Resource Server audience must come from **API resource registration** or the issuer contract, never simply the web UI's OAuth client ID.

### 14.3. Requesting Only `openid` and Expecting to Call APIs

`openid` is the standard scope requesting OIDC authentication. It is **not by default** equivalent to `orders.read`. If a client needs to call the Orders API, it must request a token with the **resource/audience and API scopes** permitted by the AS.

You can use **RFC 8707** `resource` or an AS-specific audience parameter depending on the provider. Never assume every IdP issues access tokens for every API just because a user signed in.

### 14.4. AS Does Not Issue JWT Access Tokens

Some IdPs issue opaque access tokens. Having a client parse tokens as JWTs and fall back to the ID token because "the ID token is parseable" is wrong. The Resource Server must choose **opaque introspection** or an AS-supported access token verification contract, never repurposing the ID token.

### 14.5. Treating UserInfo as an "Active Check"

If a developer writes:

```text
UserInfo returns 200 -> token active -> create Authentication
```

the API still lacks proof of audience, permissions, and the API issuer contract. This is not RFC 7662 introspection, and a UserInfo endpoint may have different semantics/tolerances than the API. Call the **introspection endpoint** if the token is opaque and that is what the AS publishes.

### 14.6. Treating Every JWT as an Access Token Because They Share a Signing Key

An issuer may sign ID tokens, access tokens, logout tokens, client assertions, and security event tokens with related keys. Therefore, **a valid signature does not replace token-purpose validation**. For RFC 9068 JWT access tokens, the Resource Server checks the profile; for other tokens, define an equivalent policy.

### 14.7. Misunderstanding Token Exchange as "Relabeling"

When a client holds a token for resource A and needs to call resource B, never edit `aud` or relabel the token on the HTTP request. **OAuth 2.0 Token Exchange (RFC 8693)** lets a trusted AS issue a new token for the target resource per policy. The new token must be verified by Resource Server B. Not every system supports token exchange; follow the provider's contract.

## 15. Testing: Must Prove the API Rejects ID Tokens

A Resource Server test suite cannot stop at "good JWT access token -> 200." It must include **validly signed ID tokens with the wrong audience** and **validly signed tokens from the same issuer meant for another API**.

### 15.1. Critical JWT Matrix

| Input | Signature | Issuer | Audience/Type | Expectation |
|---|---|---|---|---|
| Valid profile access token with `orders.read` | Valid | Trusted | `orders-api` | Passes authentication; proceeds to authz/domain |
| ID token for `orders-web-client` | **Valid** | Trusted | `orders-web-client` | **Rejected** at API |
| JWT access token for `billing-api` | Valid | Trusted | `billing-api` | **Rejected** |
| Right audience yet bad signature | Invalid | Claimed trusted | `orders-api` | **Rejected** |
| Token from unallowlisted issuer | May be valid for other issuer | Untrusted | `orders-api` | **Rejected** |
| Expired token | Valid | Trusted | `orders-api` | **Rejected** |
| Wrong `typ`/token purpose per profile | Valid | Trusted | May have right audience | **Rejected** per token profile |
| Valid access token lacking `orders.read` | Valid | Trusted | `orders-api` | Authenticated yet **403** on read |
| Access token with scope, different order owner | Valid | Trusted | `orders-api` | **403/404** per domain policy |

**Crucially:** the test ID token must carry a **valid signature from the trusted issuer**. If the test merely sends garbage, you have not proven the API enforces **audience/purpose**, because the token was already rejected on signature.

### 15.2. Unit Testing the Issuer/Audience Validator

Example checking an audience validator with a test-constructed `Jwt` object:

```java
import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;

import static org.assertj.core.api.Assertions.assertThat;

class AccessTokenAudiencePolicyTest {

    @Test
    void idTokenAudienceMustNotMatchOrdersApi() {
        Jwt idTokenShapedFixture = Jwt.withTokenValue(
                "synthetic-id-token")
            .header("alg", "RS256")
            .issuer("https://identity.example.com/realms/shop")
            .audience(List.of("orders-web-client"))
            .issuedAt(Instant.now().minusSeconds(5))
            .expiresAt(Instant.now().plusSeconds(600))
            .subject("user-842")
            .build();

        assertThat(idTokenShapedFixture.getAudience())
            .doesNotContain("orders-api");
    }
}
```

This is a **test fixture** for audience conditions, **not** a signature verification test. Real validator unit tests should invoke the exact `OAuth2TokenValidator<Jwt>` wired into the decoder and assert failure, rather than only reading claims. And to prove the Resource Server rejects an ID token with a **valid signature**, run the decoder/filter with test keys.

### 15.3. Integration Test with Two JWTs Signed by the Same Issuer Key

Test setup:

```text
Test issuer:
  https://issuer.test
  JWKS: public key test-K
  Private key test-K only in test fixture

JWT #1:
  signed with test-K
  iss = https://issuer.test
  aud = orders-api
  typ/profile = access token
  scope = orders.read

JWT #2:
  signed with test-K
  iss = https://issuer.test
  aud = orders-web-client
  typ/profile = OIDC ID token

Resource Server:
  trusted issuer = https://issuer.test
  required audience = orders-api

Expected:
  JWT #1 -> authenticated (and potentially 200)
  JWT #2 -> 401, never reaches controller
```

This test catches **token substitution** directly. Never use production credentials/keys; use a test issuer/JWKS server or a `JwtDecoder` configured with test keys.

### 15.4. `mockMvc().with(jwt())` Does Not Prove the Decoder

In a Servlet test:

```java
mockMvc.perform(get("/api/orders/ORD-123")
    .with(jwt().authorities(
        new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
```

`jwt()` is a **test post-processor**: it typically populates a pre-built Authentication, bypassing the Bearer token decoder and JWT signature/audience validation. It is suited for testing **HTTP/method authorization**, not for proving the API rejects real ID tokens.

In WebFlux, `mockJwt()` has the same limitation. To test token type/issuer/audience, send **compact signed Bearer JWTs** through the filter chain with a real decoder and test keys.

### 15.5. Testing Opaque Introspection

Mock the introspection endpoint returning:

```json
{
  "active": true,
  "aud": ["orders-api"],
  "scope": "orders.read"
}
```

and:

```json
{
  "active": false
}
```

Test cases:

- `active=true` with matching audience/scope -> proceeds to authorization.
- `active=false` -> not authenticated.
- `active=true` with different audience -> decorator/policy rejects.
- Introspection timeout/5xx -> never creates a fallback scoped principal.
- UserInfo endpoint returns 200 while introspection returns `active=false` -> **not** authenticated at Orders API.
- M2M token is active while UserInfo is unsupported -> Resource Server still enforces the access token contract, **no UserInfo needed**.

### 15.6. Testing UserInfo/ID Tokens at the RP Separately

For the OIDC client, test:

- ID token with right issuer, audience, and nonce/time is accepted on login.
- ID token with wrong nonce/audience is rejected.
- UserInfo `sub` matches ID token -> profile claims are used per policy.
- UserInfo `sub` differs from ID token -> **claims are discarded**.
- UserInfo fails -> never assume login or API scopes succeeded by default.

These are **OIDC client** tests and do not replace JWT/opaque access-token verification tests at the Resource Server.

## 16. Business Authorization: A Valid Access Token Is Still Not Enough

An authenticated access token:

```json
{
  "iss": "https://identity.example.com/realms/shop",
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "tenant_id": "tenant-a"
}
```

does not mean the user can read every order. `orders.read` authorizes the **operation type**, while permission to read **ORD-123** belonging to another tenant must be checked in the domain.

### 16.1. Illustrative Service Authorization

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication
    .JwtAuthenticationToken;
import org.springframework.stereotype.Service;

@Service
public class AuthorizedOrderQueries {

    private final OrderRepository orders;

    public AuthorizedOrderQueries(OrderRepository orders) {
        this.orders = orders;
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public OrderView getOrder(
            String orderId,
            Authentication authentication) {

        if (!(authentication instanceof JwtAuthenticationToken jwtAuth)) {
            throw new AccessDeniedException(
                "JWT access token required");
        }

        var jwt = jwtAuth.getToken();
        String issuer = jwt.getIssuer().toString();
        String subject = jwt.getSubject();
        String tenant = jwt.getClaimAsString("tenant_id");

        return orders
            .findVisibleByIdAndActor(
                orderId, issuer, subject, tenant)
            .orElseThrow(OrderNotFoundException::new);
    }
}
```

This snippet illustrates a service receiving a Spring Security-authenticated `Authentication` and enforcing scope. `OrderRepository`, `OrderView`, `OrderNotFoundException`, and `AccessDeniedException` are domain types/APIs to import/define. In production, services should obtain the actor from the trusted security context rather than accepting an arbitrary `Authentication` parameter from an untrusted caller; method security requires `@EnableMethodSecurity` and invocation through a Spring proxy. For opaque tokens, write an appropriate principal adapter instead of casting every token to `JwtAuthenticationToken`.

### 16.2. When Tokens Contain "Admin"-Looking Roles

Do not do this:

```java
if (idToken.claim("admin") == true ||
    userInfo.groups().contains("admins")) {
    allowDeleteAnyOrder();
}
```

Role claims from ID tokens/UserInfo may be issued by the OP for **other client purposes**, not as API permissions by default. If the API truly consumes entitlements from a separate authorization service, define clear trust/audience/tenant contracts, mappings, and freshness—never read from an OIDC profile and mint unbounded authorities.

### 16.3. Do Not Mask Vulnerabilities by Returning 404

An API may return 404 for orders owned by someone else to avoid disclosing resource existence. However, that must result from a **real ownership/tenant policy**, not as a way to skip access token verification. Invalid tokens must be rejected before querying sensitive data.

## 17. Issuer Integration: Checklist When Receiving an SDK or IdP Docs

An integration guide sometimes provides only:

```text
OIDC discovery URL
client_id
client_secret
/userinfo endpoint
authorization endpoint
token endpoint
```

That is **not enough** to design a Resource Server. Also request:

- What **access token** format does the API receive?
- What are the JWT access token's issuer, audience, scopes, and token type/profile?
- What is the JWKS URI and which signing algorithms are allowed?
- If opaque, what are the introspection endpoint, client authentication, and response fields?
- Which parameter/registration issues access tokens for the **Orders API resource/audience**?
- How do `client_credentials` and authorization-code flows differ in emitted tokens?
- What are the revocation and TTL/caching recommendations?
- Does the token include tenant or permission fields, and what semantics does the AS guarantee?
- If the IdP supports multiple issuers/realms/tenants, how is the trust registry managed?
- What are the rotation/offboarding procedures and how are wrong-audience/ID tokens tested?

Never fall back to ID tokens or UserInfo just because a vendor guide omits access-token validation. If the contract is incomplete, finalize AS/API configuration or choose a supported access token verification mechanism.

### 17.1. Metadata Chain of Trust

For JWTs, fetch issuer metadata/JWKS only from **allowlisted issuers**. Never let a request arbitrarily supply `iss`/`jwks_uri` to instantiate a new decoder. For opaque tokens, the introspection URI and credentials must come from **managed configuration**, never from a bearer token or `X-Provider-URL` header.

### 17.2. Separating Points of Change

```text
OIDC CLIENT:
  authorize + token response
  validate ID token
  optionally call UserInfo
  client login/session

RESOURCE SERVER:
  receive Bearer access token
  validate JWT or introspect opaque token
  create Authentication + authorities
  enforce audience/scope/tenant/ownership
```

If an IdP change alters the UserInfo format, it should not force the API to alter its access-token validation policy. If the AS changes the JWT access-token audience, update the Resource Server validators/trust contract—not just the OIDC login UI.

## 18. Anti-Patterns and Fixes

| Anti-Pattern | Problem | Right Approach |
|---|---|---|
| Sending ID token as API Bearer token | ID token is for RP; invites token substitution | Send access token with right audience/API scopes |
| API checks only signature and `iss` | May accept ID tokens or JWTs for other APIs | Check `aud` and token purpose/profile |
| Calling UserInfo to "validate access token" | UserInfo is not RFC 7662 introspection | Use `JwtDecoder` or `OpaqueTokenIntrospector` |
| Granting `SCOPE_orders.read` when UserInfo returns `sub` | Profile claims are not API permissions | Map scopes/permissions from trusted authorization sources |
| Treating right email domain in ID token as sufficient permission | Email does not replace issuer/audience/scope/domain policy | Authoritative business authorization |
| Client requests only `openid` then calls API | OIDC login scope does not grant API scopes | Request token with resource/audience and matching scopes |
| API cannot parse opaque token so uses ID token instead | Misuses credential purpose | Use token introspection or AS-supported profile |
| Skipping access-token validation because `at_hash` matched | Only an RP flow-binding check | Resource Server still verifies access token |
| API uses OAuth client ID as default audience | Mistakenly accepts client-targeted ID tokens | Use API's audience/resource ID |
| Issuer A's ID token accepted in tenant B | Mixes issuer/subject/tenant boundaries | Verify issuer, aud, token profile, and tenant ACL |
| Raw JWT having "trusted" `iss` treated as enough | Unverified claims are attacker-controlled | Trusted registry + signature/issuer verification |
| Treating `Jwt.withTokenValue(...)` as a signature test | Test fixture does not verify signatures | Signed JWT + test decoder |
| `mockJwt()` proves API rejects ID tokens | Mock can bypass decoder | Integration test with compact signed token |
| Calling UserInfo on introspection timeout | Different purpose mechanism; risks fail-open | Fail closed, address AS availability |
| Treating M2M token failing UserInfo as admin | Lack of End-User is not an auth failure to bypass | Handle service principals via access token |
| Caching UserInfo as "token active forever" | Profile cache is not token-status cache | TTL/revocation policy based on access token |
| Disabling audience validator to stop client 401s | Opens door to token substitution | Fix audience/token issuance at IdP/client |
| Token has `scope` while object belongs to another owner | Scope only authorizes operation type | Domain policy for owner/tenant/state |

## 19. Practical Troubleshooting Workflow

### 19.1. Client Reports "Login Works Yet API Returns 401"

Check in order:

1. Is the client sending `access_token` or `id_token`?
2. Was the access token issued for **Orders API**? What is `aud`/the resource identifier?
3. Do issuer/token profile and signing keys match Resource Server config?
4. Is the token expired, not yet valid, or revoked?
5. If opaque, is the API using the right introspection endpoint/credentials?
6. Is the token a JWT access token or an ID token/other JWT assertion?
7. Were OAuth client ID and API audience confused?

**Never fix a 401 by** letting the API accept ID tokens or calling UserInfo in place of the decoder.

### 19.2. Client Reports "API Returns 403 Even Though UserInfo Has Email and Name"

The Resource Server may have authenticated the access token successfully, yet:

- `SCOPE_orders.read` is missing.
- The scope converter uses a prefix other than `SCOPE_`.
- An HTTP matcher requires a different authority.
- Tenant/owner/ACL denies access.
- The user/service identity lacks the required entitlement.

UserInfo returning name/email does not override a substantiated 403 decision. Inspect authorities on the **verified access token** and domain policies.

### 19.3. Another Client's ID Token Was Accepted by the API

This is a security incident requiring immediate action:

1. Check whether the Resource Server is missing audience/token type validation.
2. Update JWT decoder validators or the opaque introspection contract.
3. Add a test using a validly signed ID token with the client's `aud`.
4. Audit other APIs sharing the same verifier/issuer/keys.
5. Review logs/audits and execute incident response per policy.
6. Never expose raw tokens or personal data in public reports.

### 19.4. UserInfo Succeeds While Access Token Introspection Is Inactive

Never let a "successful" UserInfo call override introspection. The two endpoints have different policies, timing, and resources, and a UserInfo 200 does not carry the Orders API's `active=true` contract.

## 20. Summary in One Decision Tree

```mermaid
flowchart TD
    A["App holds token from OIDC/OAuth provider"] --> B{"Which role is handling it?"}
    B -->|"OIDC Client / RP"| C["Validate ID token for login"]
    C --> D{"Profile claims needed?"}
    D -->|"Yes"| E["Call UserInfo with suitable token<br/>and verify sub matches ID token"]
    D -->|"No"| F["Manage client session per policy"]
    E --> F
    B -->|"Resource Server / API"| G{"Is credential sent to API an access token<br/>matching the profile?"}
    G -->|"No"| X["401: never substitute ID token/UserInfo"]
    G -->|"Yes, JWT"| H["JwtDecoder: signature + issuer<br/>audience + time + type/profile"]
    G -->|"Yes, opaque"| I["OpaqueTokenIntrospector:<br/>active + resource metadata"]
    H --> J{"Token valid for API?"}
    I --> J
    J -->|"No"| X
    J -->|"Yes"| K{"Scope/authority sufficient?"}
    K -->|"No"| Y["403: insufficient permission"]
    K -->|"Yes"| L{"Owner/tenant/object state valid?"}
    L -->|"No"| Y
    L -->|"Yes"| M["Allow operation"]
```

An OIDC client can simultaneously call a Resource Server. Yet **the upper and lower paths are not interchangeable**: `ID token → UserInfo` belongs to the client; `Bearer access token → JWT validation/introspection → authorization` belongs to the API.

## 21. Conclusion

```text
OIDC / OAuth 2.0 TOKEN INTEGRATION

ID TOKEN
  audience is typically client_id
  intended for Relying Party / OIDC login
  validate per OIDC Core (iss, aud, exp, nonce, ...)
  DO NOT use in place of API access tokens

USERINFO
  provides End-User claims to Relying Party
  sub must match ID token when used by client
  NOT RFC 7662 introspection
  DOES NOT prove API audience/scope

ACCESS TOKEN
  credential for calling protected resources
  audience/resource must match the API
  JWT: verify signature + issuer + audience + time + type
  Opaque: trusted introspection + active + resource contract
  scope/authority only from verified sources
  domain: owner + tenant + object-level policy

NEVER AUTOMATICALLY:
  ID token valid -> API authorized
  UserInfo returns 200 -> API token valid
  email verified -> SCOPE_orders.delete
  AS timeout -> default authenticated principal
```

**A Resource Server must verify access tokens for itself.** An ID token may be valid for an OIDC client yet carry the wrong audience or token purpose for the API; a UserInfo response may return an accurate profile yet provide no API access-token verification contract. Spring Security provides `JwtDecoder` and `OpaqueTokenIntrospector` (along with their reactive counterparts) to enforce this exact trust boundary.

When integrating an issuer, explicitly specify the **access-token profile, issuer, audience, key source/introspection endpoint, scopes, and tenant policy**. Use ID tokens and UserInfo strictly in the Relying Party's role, and test with **validly signed tokens intended for the wrong purpose** so the API never mistakenly accepts an ID token or a token issued for another resource.

## References

- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token validation, UserInfo endpoint, `sub` matching, `nonce`, and `at_hash`.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): issuer, UserInfo endpoint, `jwks_uri`, and metadata.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): access tokens, scopes, client/Resource Server.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer credentials and HTTP 401/403.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): `active`, `scope`, `aud`, and introspection contract.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): `iss`, `aud`, `sub`, `exp`, and claims.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): audience validation, cross-JWT confusion, and token substitution.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): `typ=at+jwt` and JWT access token requirements.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): identifying protected resource/audience when requesting tokens.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): exchanging tokens for target services via a trusted AS.
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): issuer, audience, `JwtDecoder`, and `SCOPE_` mapping.
- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): token introspection and `OpaqueTokenIntrospector`.
- [Spring Security Reference — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): `ReactiveJwtDecoder` in WebFlux.
- [Spring Security Reference — Reactive Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html): `ReactiveOpaqueTokenIntrospector`.
- [Spring Security Reference — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): OAuth/OIDC login on the client side.
- [Spring Security Reference — OAuth 2.0 Client Core](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html): managing authorized clients/access tokens on the client.
- [Spring Security Reference — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): HTTP authorization and `hasAuthority`.
- [OWASP API Security Top 10 (2023) — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): per-resource authorization after token validation.