# Verifying the Signature Before Using Claims for Authorization Decisions

In **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Resource Server**, JWT access tokens commonly carry claims such as `sub`, `iss`, `aud`, and `scope`. An API can rely on these claims to determine who the caller is and what actions they may perform. However, **claims are only data asserted by the token**. Before using claims to authenticate the caller or authorize access, the Resource Server must ensure the JWT is protected by valid cryptography and issued by a trusted source.

Anyone can craft a JSON string containing `"scope": "orders.admin"` or `"role": "ADMIN"` and encode it with Base64URL. That data may look like a JWT payload, yet **it has zero authorization value until verified**.

> **Core rule:** A Resource Server must **verify the JWS signature/MAC using an approved key and algorithm**, then **validate token acceptance conditions** such as issuer, audience, lifetime, and intended usage, and only then **map claims to an identity and authorities to make access decisions**. Simple Base64URL decoding is not JWT verification.

## 1. Why is reading claims before verification dangerous?

Suppose the Orders API receives a request:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer <access-token>
~~~

The token payload visible after decoding:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "roles": ["ORDER_SUPPORT"],
  "exp": 1893459600
}
~~~

If code checks `scope` immediately after decoding the payload, the API can inadvertently **trust an assertion forged by the sender themselves**. Different scenarios can produce identical-looking payloads:

| Scenario | Can payload be decoded? | Can claims be trusted for authorization? |
| --- | --- | --- |
| Valid JWT, signed by trusted issuer and meant for Orders API | Yes | **Possibly**, after also checking lifetime, audience, scope, and business permissions |
| Payload altered from `orders.read` to `orders.admin` after signing | Yes | **No**, the signature is no longer valid |
| JWT signed by an unknown party using their own private key | Yes | **No**, no trust chain to the configured issuer/key |
| Validly signed JWT issued by a different issuer | Yes | **No**, if that issuer is not accepted by the API |
| Valid Billing API JWT carrying `aud = billing-api` | Yes | **No**, token is not intended for Orders API |
| Validly signed JWT that has expired | Yes | **No**, token is no longer accepted |
| Valid JWT with sufficient scope, but order 42 belongs to someone else | Yes | **No**, if the data policy does not allow it |

The first row only says the API **has grounds to trust the verified claims**. It does not mean every request bearing that token should receive data.

### An incorrect code example

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

// DO NOT use this result for authentication or authorization!
String[] parts = bearerToken.split("\\.");
String json = new String(
        Base64.getUrlDecoder().decode(parts[1]),
        StandardCharsets.UTF_8);

// Wrong if you parse "json" and trust scope/roles/sub to grant access.
~~~

The snippet above only performs a **Base64URL decode** of one token part; it does not:

- Verify the signature or MAC.
- Verify that the signing key belongs to a trusted issuer.
- Confirm that the token-protection algorithm is allowed.
- Check `iss`, `aud`, `exp`, `nbf`, or token purpose.
- Confirm the caller may access the specific record.

A JWT parsing library may allow reading claims from an unverified token. If the API uses that result to build an `Authentication`, construct a `GrantedAuthority`, or return data, the trust boundary has been breached.

## 2. How does JWS protect JWT content?

JWT is a representation of a **JWT Claims Set**; a JWT can be wrapped in JWS for integrity protection or JWE for content encryption. The typical case for an OAuth 2.0 Resource Server is a **signed JWT in JWS Compact Serialization**, which has three parts:

~~~text
BASE64URL(Protected Header).BASE64URL(Payload).BASE64URL(Signature)
~~~

Example header:

~~~json
{
  "alg": "RS256",
  "kid": "orders-signing-key-2026-01",
  "typ": "at+jwt"
}
~~~

The payload is the claims set:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "iat": 1893456000,
  "exp": 1893459600
}
~~~

`typ: "at+jwt"` is an example when an issuer uses the **JWT profile for OAuth 2.0 access tokens**; not every issuer uses the same `typ`. The API must know which token profile it accepts and validate strictly per contract.

### 2.1. Which part is actually signed?

With **JWS Compact Serialization** and standard JWT usage, the input to the signing algorithm is:

~~~text
ASCII(BASE64URL(Protected Header) + "." + BASE64URL(Payload))
~~~

The signature/MAC is computed over **both the protected header and the payload**. During verification, the JOSE library receives the token string, selects a matching key from a trusted source, verifies that the algorithm is allowed, and verifies the signature over this exact signing input.

~~~mermaid
flowchart TD
    Receive["Receive Bearer JWT"]
    Parts["Parse JWS Compact structure"]
    Policy["Select algorithm and key per trust policy"]
    Verify{"Valid signature/MAC?"}
    Claims["Claims can be used for token validation"]
    Reject["Reject token"]

    Receive --> Parts
    Parts --> Policy
    Policy --> Verify
    Verify -->|No| Reject
    Verify -->|Yes| Claims
~~~

The diagram illustrates the **trust boundary**: before JWS verification, the header and payload are untrusted data. In real implementations, a decoder must **read the unverified header** to learn `kid` and route to the configured key set. This is acceptable **provided the header values are used strictly as controlled hints within the key/algorithm policy**; never let the token arbitrarily dictate an algorithm or a key store that the API immediately trusts.

### 2.2. Readable does not mean modifiable while staying valid

Base64URL is merely a way to encode bytes into protocol-safe characters. The payload of a signed JWT is typically **not confidential**: anyone holding the token can read its claims. However, modifying `scope` or `sub` in the payload after the JWT is signed causes the original signature to **fail verification**.

Therefore, clearly separate:

~~~text
Decode JWT       -> inspect fields, not yet verified
Verify JWS       -> prove token is untampered and matches a trusted key
Validate claims  -> check whether token is acceptable to the API right now
Authorize        -> decide which actions on which data the caller may perform
~~~

**Signature verification does not protect payload confidentiality.** If claims must be hidden, manage what data is issued or use JWE/an appropriate encryption mechanism. Sending JWTs over HTTPS and protecting Bearer tokens from exposure remains essential.

## 3. A valid signature is only trustworthy with which key?

A cryptographic signature has security value only if the Resource Server verifies it using a **trusted key** and an appropriate algorithm.

### 3.1. Common case: asymmetric keys

For example, an Authorization Server issues JWTs signed with **RS256**:

- The Authorization Server keeps the **private key** and uses it to sign tokens.
- The Authorization Server publishes the **public key** or public JWKs via a JWKS endpoint.
- The Resource Server fetches or uses the public key **from a configured trusted source** to verify.

~~~mermaid
sequenceDiagram
    participant AS as Authorization Server
    participant JWKS as Trusted JWKS
    participant API as Resource Server

    AS->>AS: Sign JWT with private key
    AS->>JWKS: Publish public JWK per policy
    API->>JWKS: Fetch/refresh public keys
    JWKS-->>API: JWKS
    API->>API: Verify JWS with matching public key
    API->>API: Then validate iss, aud, lifetime, scope...
~~~

The API **does not need the private signing key** to verify asymmetrically signed JWTs. Never place the Authorization Server's private key in a Resource Server for this purpose.

Other algorithms used in JOSE:

| Category | Example | Operational implication |
| --- | --- | --- |
| Asymmetric RSA signature | `RS256`, `PS256` | AS signs with private key; API verifies with public key |
| Asymmetric EC signature | `ES256` | AS signs with EC private key; API verifies with EC public key |
| Symmetric-key MAC | `HS256` | Signer and verifier share the same secret |

With `HS256`, a Resource Server that wants to verify must hold the **shared secret**, and anyone possessing that secret can forge a valid MAC. Because of distribution concerns and limiting who can sign, many multi-API systems prefer asymmetric signing. Regardless of the algorithm chosen, **the list of accepted algorithms must be configured intentionally**.

### 3.2. `kid` selects a key, it does not create trust

The JOSE header may contain:

~~~json
{
  "alg": "RS256",
  "kid": "key-2026-01"
}
~~~

`kid` is a **key identifier** used to select a key when the JWKS holds multiple keys during rotation. The Resource Server can look up the JWK with a matching `kid` in the trusted issuer's key set; it must still verify the signature afterward.

Never assume that:

- A matching `kid` automatically means the signature is valid.
- A token may request loading a public key from an arbitrary URL and be trusted immediately.
- Keys from all issuers can be pooled into one shared “key bucket” without binding issuer and audience.
- A public JWKS allows adding arbitrary public keys from unmanaged sources.

`kid`, `jku`, or other key-referencing parameters, if supported, are all **untrusted inputs**. The key used must be bound to the issuer configuration, a controlled JWKS endpoint, and an algorithm policy.

### 3.3. Avoiding algorithm confusion and `alg: none`

Dangerous bugs can occur when an API:

- Accepts `"alg": "none"` as an authenticated token when the endpoint requires a signed token.
- Lets the token choose its own algorithm without restricting allowed algorithms in code.
- Mistakenly treats an asymmetric public key as a symmetric MAC secret.
- Skips signature verification when a parsing library returns a Claims Set.
- Accepts a token signed by a properly formatted key that does not belong to a trusted source.

These risks are commonly grouped in documentation as **JWT algorithm/key confusion**. The remedy is to use a trusted JOSE library, accept **strictly the configured algorithm/key/issuer**, and never allow tokens to arbitrarily alter verification rules.

## 4. A valid signature is necessary, not sufficient

After verifying the signature/MAC, the Resource Server must evaluate **whether the token is valid for this API's context**.

| Check | Question | If omitted |
| --- | --- | --- |
| **Issuer (`iss`)** | Was the token issued by an issuer trusted by the API? | API may accept tokens from another source |
| **Audience (`aud`)** | Was the token issued specifically for this API? | Tokens from other APIs can be replayed across services |
| **Expiration (`exp`)** | Is the token still valid at request time? | Expired tokens can still be used |
| **Not Before (`nbf`)** | Has the token reached its valid start time? | Not-yet-valid tokens are accepted |
| **Token type / profile** | Is this the exact token type the API accepts? | ID tokens may be confused with access tokens |
| **Client / subject / context** | Do client or subject claims match the grant type/policy? | Service tokens mistaken for user sessions |
| **Scope / authority** | Was the token granted the required action scope? | Callers can invoke unauthorized endpoints |
| **Data policy** | Is the caller permitted on this record/tenant/state? | Data leakage or unauthorized actions on records |

### 4.1. Checking issuer

Example token claim:

~~~json
{
  "iss": "https://id.dev.example.test/realms/shop"
}
~~~

The production Orders API trusts only:

~~~text
https://login.example.com/realms/shop
~~~

Even if the JWT is validly signed by a dev system key, **production must reject it** if the dev issuer is not configured as an allowed source. Sharing role/scope names across environments does not establish trust.

### 4.2. Checking audience

An Authorization Server may issue tokens for multiple different APIs:

~~~json
{
  "iss": "https://identity.example.test",
  "aud": ["billing-api"],
  "scope": "billing.read"
}
~~~

The Orders API requires `aud` to contain `orders-api`. Checking only the issuer and signature risks mistakenly accepting a Billing API token at the Orders API. **Audience is the boundary between Resource Servers**, not decorative payload metadata.

### 4.3. Checking lifetime

JWTs normally use NumericDate (seconds since the Unix epoch) in `exp`, `nbf`, and `iat`. The API must not accept a token at or after its expiration time, optionally applying a small policy-defined clock skew tolerance.

~~~json
{
  "iat": 1893456000,
  "nbf": 1893456000,
  "exp": 1893459600
}
~~~

Do not use millisecond timestamps when the profile expects NumericDate. Checking `iat` is meaningful only when policy defines an explicit constraint, such as rejecting issued-at timestamps too far in the future.

### 4.4. Distinguishing an ID token from an access token

An **OIDC ID token** proves user authentication results to an **OIDC Client**. An **OAuth 2.0 access token** is a credential for calling a Resource Server. Both may be JWTs signed by the same issuer.

Example:

~~~text
ID token:      aud = shop-web
               used at the OIDC Client to handle sign-in

Access token:  aud = orders-api
               scope = orders.read
               used at the Orders API
~~~

A Resource Server must accept the proper **access token** per profile/contract. In the JWT profile for OAuth 2.0 access tokens (RFC 9068), the `typ` header may be `at+jwt`, with specific validation rules. Other issuers may use different profiles; the API must coordinate with the issuer to enforce the right constraints and avoid accepting ID tokens merely because the signature is valid.

## 5. Order of trust in Spring Security Resource Server

For APIs using Bearer JWTs, Spring Security provides a standard processing pipeline:

~~~mermaid
flowchart TD
    HTTP["HTTP request<br/>Authorization: Bearer ..."]
    Extract["BearerTokenAuthenticationFilter<br/>extracts token"]
    Provider["JwtAuthenticationProvider"]
    Decoder["JwtDecoder<br/>verifies JWS and validates JWT"]
    Valid{"Valid token?"}
    Converter["JwtAuthenticationConverter<br/>builds principal, authorities"]
    Authz["AuthorizationFilter / method security<br/>checks endpoint"]
    Domain["Service / policy<br/>checks record, tenant, owner"]
    Success["Return data"]
    Reject401["401 Unauthorized"]
    Reject403["403 / 404 per policy"]

    HTTP --> Extract
    Extract --> Provider
    Provider --> Decoder
    Decoder --> Valid
    Valid -->|No| Reject401
    Valid -->|Yes| Converter
    Converter --> Authz
    Authz -->|Insufficient permissions| Reject403
    Authz -->|Sufficient scope| Domain
    Domain -->|Not permitted| Reject403
    Domain -->|Permitted| Success
~~~

This is a conceptual diagram. Exact error-to-status mapping and filter ordering depend on configuration. The key point is that **unverified claims must never be turned into a trusted principal or authorities**.

### 5.1. Components to understand

| Component | Responsibility |
| --- | --- |
| `BearerTokenAuthenticationFilter` | Extracts the Bearer token from the request per configured mechanism |
| `JwtAuthenticationProvider` | Invokes `JwtDecoder` to decode/verify the token, then converts the result into authentication |
| `JwtDecoder` / `NimbusJwtDecoder` | Processes JWS and configured validators; returns a valid `Jwt` only per contract |
| `JwtAuthenticationConverter` | Builds an `Authentication` from an accepted `Jwt`, optionally mapping `scope` to `GrantedAuthority` |
| `SecurityFilterChain` / method security | Evaluates authorities and endpoint/method access rules |
| Business/policy layer | Enforces permissions on records, tenant, owner, state, and specialized conditions |

In practice, the decoder must parse the header and payload to run validation, **but the application should only consume the `Jwt` object after the decoder completes verification**. Never manually parse claims from the Bearer token alongside Spring Security and use them in place of a trusted `Authentication`.

### 5.2. Why must authority mapping happen after verification?

A JWT might contain:

~~~json
{
  "sub": "user-842",
  "scope": "orders.read orders.cancel",
  "roles": ["ORDER_SUPPORT"]
}
~~~

Once the Resource Server has verified the token, `JwtAuthenticationConverter` can turn scopes into `SCOPE_orders.read` and `SCOPE_orders.cancel` authorities. Without verification, turning the `scope` string into authorities lets the sender **grant themselves their own permissions**.

By default, Spring Security maps scopes from the `scope` or `scp` claim into authorities prefixed with `SCOPE_`. Custom role claims like `roles` are not automatically interpreted uniformly across issuers; producing `ROLE_ORDER_SUPPORT` requires designing a matching converter and claim contract.

## 6. Configuring signed JWTs in Spring Boot

The example below uses **Spring Boot 3 / Spring Security 6** with an Orders API accepting JWT access tokens issued by an Identity Server.

### 6.1. Adding the dependency

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

### 6.2. Configuring trusted issuer and JWKS

`src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${OAUTH_ISSUER_URI}
          jwk-set-uri: ${OAUTH_JWKS_URI}

app:
  security:
    expected-audience: ${OAUTH_API_AUDIENCE}
~~~

Example environment variables:

~~~text
OAUTH_ISSUER_URI=https://identity.example.test/realms/shop
OAUTH_JWKS_URI=https://identity.example.test/realms/shop/protocol/openid-connect/certs
OAUTH_API_AUDIENCE=orders-api
~~~

These URIs are illustrative only. You must obtain the **actual issuer and JWKS endpoint published by your Authorization Server**; JWKS paths are not standardized across products. When using only `issuer-uri`, Spring Security can use discovery to locate keys. Providing `jwk-set-uri` as well can avoid metadata discovery calls at startup, though you must still validate the `iss` claim.

A Resource Server verifying asymmetrically signed JWTs usually uses **public keys**, and does not need the client secret of the Client that requested the token. If the system uses opaque tokens and introspection, the verification mechanism differs; the examples here focus on **signed JWTs**.

### 6.3. Creating a JwtDecoder with audience validation

To clearly illustrate the boundary between **cryptographic verification** and **claims contract validation**, `JwtDecoder` can be configured as follows:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtVerificationConfiguration {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}")
            String issuer,
            @Value("${spring.security.oauth2.resourceserver.jwt.jwk-set-uri}")
            String jwksUri,
            @Value("${app.security.expected-audience}")
            String expectedAudience) {

        // Use a JWKS endpoint configured as trusted.
        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withJwkSetUri(jwksUri)
                        .build();

        // Retain standard checks, including timestamps and issuer.
        OAuth2TokenValidator<Jwt> standardValidators =
                JwtValidators.createDefaultWithIssuer(issuer);

        // A valid signature is still not enough if the token is meant for another API.
        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            boolean intendedForThisApi =
                    jwt.getAudience().contains(expectedAudience);

            if (intendedForThisApi) {
                return OAuth2TokenValidatorResult.success();
            }

            return OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                            "invalid_token",
                            "Unexpected token audience",
                            null));
        };

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        standardValidators,
                        audienceValidator));

        return decoder;
    }
}
~~~

In this example:

1. `NimbusJwtDecoder` fetches/refreshes public JWKs from the **configured JWKS URI** and verifies signatures per decoder policy.
2. `JwtValidators.createDefaultWithIssuer(issuer)` applies standard JWT checks, including timestamp and issuer constraints.
3. `audienceValidator` rejects tokens lacking the `orders-api` audience.
4. If signature verification or validation fails, authentication fails; the token is never turned into a trusted principal for subsequent authorization.

The example uses the builder's default algorithm selection; in real systems, configure **the exact algorithm set agreed upon with the issuer** and token profile constraints. Never broaden the algorithm list just to get unexpected tokens accepted. If the application defines a custom `JwtDecoder` bean, avoid accidentally overwriting the default validators with a validator that checks only audience.

### 6.4. Protecting endpoints after JWT verification

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OrdersApiSecurity {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

This example assumes `/api/**` is a Bearer-token-only REST API that does not authenticate requests via session cookies. Accordingly, it disables CSRF and enforces statelessness on the API filter chain. If the application also serves cookie-based browser requests, design dedicated filter chains, session policies, and CSRF protection accordingly.

Upon receiving `GET /api/orders/42`, Spring Security verifies the token first; only after valid authentication does it check `SCOPE_orders.read`. If a token carries `scope = "orders.write"` without `orders.read`, the request is rejected under the policy above, even though the token is validly signed.

## 7. Reading claims from a verified Jwt

Only after Spring Security successfully builds an `Authentication` should a controller or service read principal details:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrdersController {

    private final OrderService orders;

    OrdersController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/{id}")
    OrderDto getOrder(
            @PathVariable String id,
            @AuthenticationPrincipal Jwt jwt) {

        String issuer = jwt.getIssuer().toString();
        String subject = jwt.getSubject();

        // Service must verify permission on the specific order.
        return orders.findVisibleOrder(id, issuer, subject);
    }
}
~~~

`OrderService` and `OrderDto` are illustrative domain types, not built-in Spring Security classes. `findVisibleOrder` must confirm that the resource belongs to an authorized subject/tenant and deny access if policy is not met. If the API also permits `client_credentials`, the service must distinguish a **service principal** from an **end user**; never assume every `sub` is a customer ID.

**A subtle bug to avoid:** A controller receives `@AuthenticationPrincipal Jwt`, yet also accepts a client-supplied `userId` parameter and uses that `userId` to bypass subject matching. Client-supplied input may identify *the target resource*, but permission on that resource must be decided using **trusted claims and server-side data**.

### Using method security when appropriate

With `@EnableMethodSecurity` enabled, scopes can be enforced at the service layer:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
class OrderQueryService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public OrderDto readOrder(String id) {
        // Load record and check owner/tenant in business logic.
        throw new UnsupportedOperationException("Example only");
    }
}
~~~

This snippet illustrates the **authorization attachment point**, not a complete service implementation; ownership and data policies still must be implemented. Method security does not replace JWT verification in `JwtDecoder`.

## 8. Scenarios: valid JWT that must still be rejected

### 8.1. Valid signature but wrong audience

A JWT signed by a trusted Authorization Server:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-842",
  "aud": ["billing-api"],
  "scope": "orders.read"
}
~~~

The Orders API requires audience `orders-api`. Despite the valid signature, the API must reject it **during token validation**. This is a common reason for 401 when a Client sends a token issued for another API.

### 8.2. Valid signature but expired

A JWT has `exp` earlier than the current time (accounting for accepted clock skew). The API must reject it because the token's lifetime has ended. Never ignore `exp` simply because `sub` or `scope` “is still the same”.

### 8.3. Valid issuer/audience but missing scope

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
~~~

When calling `POST /api/orders`, the API requires `SCOPE_orders.write`. After the JWT is verified successfully, the request must still be rejected with **403 Forbidden** due to lacking write permission.

### 8.4. Sufficient scope but lacking object-level permission

`user-842` holds a valid token with `orders.read`, yet order 42 belongs to `user-999` or another tenant. The endpoint must deny access per policy, returning **403** or **404** to avoid leaking resource existence. Never treat a scope as a license to read every record.

### 8.5. OIDC ID token sent to an API by mistake

A signing-in Client receives an ID token with audience `shop-web`. If that token is sent to the Orders API, the Resource Server must reject it based on audience/token profile even though it is signed by the same issuer. An ID token describes user authentication results for the Client; an access token is for calling APIs.

## 9. What changes when the access token is opaque?

Not every OAuth 2.0 access token is a JWT. If the Authorization Server issues **opaque tokens**, the Resource Server typically calls a **token introspection endpoint** to query token status and attributes.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant API as Resource Server
    participant AS as Authorization Server

    C->>API: Bearer opaque-token
    API->>AS: Introspection with appropriate credentials
    AS-->>API: active + token attributes
    API->>API: Check active, audience, scope, subject, policy
    API-->>C: Resource or rejection
~~~

In this mechanism, the API **does not verify a JWS signature locally** because the token is not a JWS. Instead, the API trusts the introspection response from the Authorization Server after establishing a secure channel and properly authenticating to the endpoint. The principle remains unchanged: **never use unverified/untrusted token information to grant permissions**.

Spring Security supports opaque tokens via `oauth2ResourceServer().opaqueToken(...)` and configuring the introspection URI/credentials. Choose JWT validation or opaque introspection based on the actual token contract; never “base64-decode” an opaque token and infer permissions.

## 10. Operating keys and JWKS securely

### 10.1. Key rotation

An Authorization Server can add a new key to the JWKS, begin signing JWTs with the new key, and retire the old key once still-valid tokens signed by the old key have expired per schedule. The Resource Server must support **fetching/refreshing the JWKS** and verifying multiple valid `kid` values during the transition window.

Do not:

- Hardcode a single public key in code without supporting updates when the issuer rotates keys.
- Temporarily disable signature verification if a new token carries an unrecognized `kid`.
- Accept any JWKS from a request-specified address to “avoid errors”.

If the Resource Server cannot find a matching key, inspect the metadata/JWKS and caching/rotation mechanism. An unknown `kid` is never a reason to accept a token by default.

### 10.2. Separating issuers and environments

Dev, staging, and production normally have distinct issuers, JWKS, and audiences. If a production Resource Server accidentally uses a dev public key or issuer, tokens may be properly rejected—or worse, create cross-environment trust risks if other policies are lax.

These values should come from environment configuration:

~~~text
OAUTH_ISSUER_URI=https://login.example.com/realms/shop
OAUTH_JWKS_URI=https://login.example.com/realms/shop/protocol/openid-connect/certs
OAUTH_API_AUDIENCE=orders-api
~~~

Do not automatically trust multiple issuers just because the same organization manages them. Each issuer needs its own key policy, audience, and claim mapping.

### 10.3. Signatures do not provide immediate JWT revocation

A JWT with a valid signature that has not expired can continue to be accepted during local validation even after a web session logs out or user permissions change, unless the system applies an additional revocation/status-checking mechanism.

For sensitive permissions, consider short-lived tokens, introspection, looking up current subject/permission state, or an architectural revocation mechanism. Signature verification guarantees token origin and integrity; **it does not guarantee the permission data inside the token reflects the latest state**.

## 11. Error handling and observability in real systems

When JWT verification or authorization fails, Spring Security produces common outcomes:

| Stage | Error example | Typical response |
| --- | --- | --- |
| Token extraction | Missing Bearer token for a protected endpoint | **401 Unauthorized** |
| JWS verification | Invalid signature, disallowed algorithm, no trusted key found | **401 Unauthorized** |
| JWT validation | Invalid issuer, audience, or timestamps | **401 Unauthorized** |
| Authority check | Valid token but missing `SCOPE_orders.write` | **403 Forbidden** |
| Data check | Has scope, but no permission on the specific order | **403** or **404** per policy |

These status codes reflect typical Bearer authentication behavior; exact responses also depend on entry point/access denied handler configuration. For Bearer tokens, the `WWW-Authenticate` header may carry RFC 6750 details such as `invalid_token` or `insufficient_scope` when appropriate.

To troubleshoot incidents, log **request ID, endpoint, verified issuer, error category, expected audience name, and policy outcome** according to logging governance rules. Avoid logging **raw access tokens**, refresh tokens, client secrets, private keys, or sensitive claim data.

### A practical operational checklist

1. Are issuer/JWKS/audience configured properly for the environment?
2. Is the token an OAuth 2.0 access token matching the token profile accepted by the API?
3. Are the algorithm and signing key within the trusted set?
4. Are `exp`/`nbf` valid and server clocks synchronized?
5. Are scope/role claims mapped to the right authority names?
6. Do endpoints and the business layer verify permissions, owner, and tenant?
7. Are errors logged with enough diagnostic detail without leaking credentials?

## 12. Common misconceptions

**“The JWT has three parts; decoding it to JSON is safe.”** No. The three-part format is merely characteristic of standard compact JWS. Without cryptographic verification, the data is still self-asserted by the sender.

**“Once a JWT is signed, all its claims remain valid forever.”** A signature only guarantees the signed content has not been altered relative to an accepted key. The token must still have the right issuer, audience, lifetime, and purpose; permission data can also change after issuance.

**“Having `scope = admin` means the API must allow access.”** No. Scopes/roles must be issued by a trusted issuer, carry an agreed meaning, and be enforced by the API per policy. The string `admin` carries no universal privilege.

**“If the signature is valid, the token works for any API.”** No. A token with `aud = payments-api` must not be automatically accepted at `orders-api`.

**“To verify a JWT, you must know the Authorization Server's private key.”** For asymmetrically signed JWS, the Resource Server verifies using the **public key**. The private signing key must stay secret on the signing side.

**“Seeing `kid` in the token proves the key is trustworthy.”** No. `kid` is only a hint to pick a key from a trusted set; the key must still be tied to the issuer and the signature must be verified.

**“JWT and JWE are always the same thing.”** No. JWT is the claims-representation structure; JWS protects integrity with a signature/MAC, while JWE encrypts for confidentiality. A Resource Server configured for signed JWTs does not automatically support arbitrary JWEs.

**“Reading `sub` from the JWT is enough to allow reading orders.”** No. `sub` identifies the subject per the token contract; it does not prove permission on individual orders, tenants, or operations.

**“A successful OIDC login grants permission to call every API.”** No. The ID token serves the OIDC Client; a Resource Server requires a valid access token with the proper audience, scopes, and data policy checks.

## 13. Self-check scenarios

**Question 1:** An application receives a JWT with payload `{"sub":"u1","scope":"orders.admin"}`. A developer simply calls `Base64.getUrlDecoder()` and grants admin access. What is wrong?

**Explanation:** The claims have not been verified for origin or integrity. The developer turned caller-controlled data into authorities. Use `JwtDecoder` to verify the JWS and token contract before mapping permissions.

**Question 2:** A JWT has a valid signature from the Authorization Server's key, yet `aud = reports-api`. Does the Orders API accept the token?

**Explanation:** No, if the contract requires `aud = orders-api`. A valid signature does not fix a mismatched audience.

**Question 3:** A verified JWT has `scope = orders.read`, and the user attempts to read another account's order. Should this be allowed?

**Explanation:** Only if the data policy permits it. Scope authorizes the action type; ownership/tenant must be checked separately.

**Question 4:** The Authorization Server changes `kid` after key rotation; the API cannot find the new JWK and returns 401. Should signature verification be disabled to keep the service running?

**Explanation:** No. Fix the JWKS source, refresh/caching behavior, and issuer rotation process while keeping verification intact.

**Question 5:** The access token is opaque and does not have three dot-separated parts. Can the API validate it like a JWT?

**Explanation:** No, if the token is not a JWT. Use introspection or an appropriate verification mechanism for that token type before trusting its attributes for authorization.

---

## Conclusion

When building a Spring Security OAuth 2.0 Resource Server, **do not start with `sub`, `scope`, or `roles` in the JWT string received from the Client**. Start with the question: *“Can I verify that this token was issued by a trusted issuer, is intended for my API, is still within its validity window, and matches its intended purpose?”*.

Only after `JwtDecoder` verifies the **signature, key, algorithm, and required token claims** may the Resource Server use the result to build an `Authentication`, map `GrantedAuthority` instances, and enforce endpoint access rules. The final decision still requires checking **permissions on the actual data**. That is the fundamental boundary preventing caller-controlled JSON from turning into application privileges.
