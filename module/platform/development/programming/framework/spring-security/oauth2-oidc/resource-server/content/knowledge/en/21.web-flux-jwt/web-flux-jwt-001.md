# ReactiveJwtDecoder and NimbusReactiveJwtDecoder

In a **Spring Security OAuth 2.0/OIDC Resource Server** application using **Spring WebFlux**, access tokens are typically sent by clients via the `Authorization: Bearer ...` HTTP header. If the access token is a **JWT** (JSON Web Token), the Resource Server must verify the JWS signature, select the appropriate trusted key, validate timestamps/issuer/audience, and convert the claims into an `Authentication` before deciding API access permissions.

In the Servlet stack, JWT decoding usually starts from the `JwtDecoder` interface with a synchronous result. In **WebFlux**, Spring Security provides the **`ReactiveJwtDecoder`** interface, which returns results asynchronously via Reactor `Mono<Jwt>`. An important implementation is **`NimbusReactiveJwtDecoder`**: it supports JWT verification based on Nimbus JOSE + JWT, uses issuer metadata, a JWK Set URI, or configured keys, and integrates validation according to the Resource Server contract.

This lesson focuses on the following questions:

- How does `ReactiveJwtDecoder` differ from `JwtDecoder`?
- How does `NimbusReactiveJwtDecoder` verify a JWT and fetch/read a JWK Set?
- When should you use `issuer-uri`, when should you use `jwk-set-uri`, and when should you create a custom decoder bean?
- How to validate issuer, audience, `exp`, `nbf`, signing algorithms, and custom claims.
- How to attach the decoder to `SecurityWebFilterChain` and map JWT claims into reactive authentication/authorities.
- How to distinguish a JWT access token from an OIDC ID token, and distinguish a JWT decoder from opaque token introspection.
- Designing WebFlux without blocking the event loop, handling JWKS/key rotation, and network failures.
- Testing HTTP authorization with `WebTestClient` and testing the decoder with targeted unit tests.

> **Principle:** `ReactiveJwtDecoder` decodes and **validates JWT validity according to configuration**; `NimbusReactiveJwtDecoder` is the concrete implementation. Having the decoder return a `Jwt` **does not automatically allow** the caller to view every endpoint or every record. Authority checks and object-level authorization are still required.

## 1. Position in the WebFlux Resource Server Architecture

A WebFlux API:

```text
Browser SPA / Mobile / Backend
             |
             | Authorization: Bearer <ACCESS_TOKEN>
             v
Spring WebFlux Orders API
             |
             +-- Reactive security web filters
             |       |
             |       +-- Bearer token extraction
             |       +-- ReactiveJwtDecoder
             |       +-- Jwt validation
             |       +-- Authentication + authorities
             |
             +-- Reactive authorization
             |       |
             |       +-- URL/action permissions
             |       +-- Method/domain permissions
             |
             +-- Reactive controller / service / repository
```

Example request:

```http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
Accept: application/json
```

The illustrative token has the payload:

```json
{
  "iss": "https://login.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "tenant_id": "shop-a",
  "iat": 1794715200,
  "nbf": 1794715200,
  "exp": 1794718800
}
```

The payload is only sample data: a valid-looking JSON **does not prove the JWT was signed by a trusted issuer**. Spring Security must verify the signature and validators before placing the claims into the security context.

### 1.1. Reactive Authentication Flow

```mermaid
flowchart TD
    A["HTTP request / WebFlux ServerWebExchange"] --> B["SecurityWebFilterChain"]
    B --> C["AuthenticationWebFilter / Bearer extraction"]
    C --> D["JwtReactiveAuthenticationManager"]
    D --> E["ReactiveJwtDecoder.decode(token)"]
    E --> F["NimbusReactiveJwtDecoder"]
    F --> G["Read JWS header, select key, and verify signature"]
    G --> H{"Signature and key valid?"}
    H -- "No" --> X["Authentication failure / usually 401"]
    H -- "Yes" --> I["Claims -> Jwt"]
    I --> J["Jwt validators: issuer, timestamps, audience, custom claims"]
    J --> K{"Valid?"}
    K -- "No" --> X
    K -- "Yes" --> L["JWT authentication converter"]
    L --> M["Authentication + GrantedAuthority"]
    M --> N["Reactor security context"]
    N --> O["AuthorizationWebFilter / method security"]
    O --> P{"Sufficient permissions?"}
    P -- "No" --> Q["Usually 403"]
    P -- "Yes" --> R["Reactive handler / Mono or Flux"]
```

The diagram illustrates **logical stages**, not the absolute internal class order across every version. What is mandatory is that **the signature and claims are validated before using them as the basis for granting permissions**.

### 1.2. Distinguishing the Four Layers

| Layer | Question | Typically involved components |
|---|---|---|
| Token decoding/signature | Does the JWT string have an acceptable signature and format? | `ReactiveJwtDecoder`, `NimbusReactiveJwtDecoder` |
| JWT claim validation | Does the token have the right issuer, audience, timestamps, and contract? | `OAuth2TokenValidator<Jwt>`, `JwtValidators` |
| Authentication conversion | Which principal and authorities do the claims produce? | `ReactiveJwtAuthenticationConverter` / adapter |
| Authorization | Which endpoints can the caller invoke and which objects can they read? | `authorizeExchange`, `@PreAuthorize`, service policy |

Even though they belong to the same request protection flow, these responsibilities **cannot replace one another**.

## 2. JWT and JWS: What Does the Decoder Actually Trust?

A JWT typically has a compact format:

```text
BASE64URL(protected header)
.
BASE64URL(payload)
.
BASE64URL(signature)
```

Example protected header:

```json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "key-2026-11"
}
```

- `alg`: JWS algorithm, such as RS256.
- `kid`: key identifier used to select a key in the JWK Set.
- `typ`: token type/profile per contract; not every issuer uses the same value.
- Payload: `iss`, `sub`, `aud`, `exp`, `scope`, and other claims.
- Signature: protects the integrity of the signed protected header and payload.

An application can **Base64URL-decode** to inspect the payload without needing a key. Doing so, however, **does not verify** the payload. An attacker can forge a fake JWT:

```json
{
  "sub": "admin",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write admin"
}
```

If the backend trusts an unverified payload, the system loses its entire security boundary. `ReactiveJwtDecoder` is the component that ensures the Resource Server **does not manually parse tokens and trust claims**.

### 2.1. Key Claims

| Claim | Function | What needs to be verified |
|---|---|---|
| `iss` | Issuer of the JWT | Matches a trusted issuer |
| `aud` | Audience, resource(s) permitted to receive the JWT | Must contain the Resource Server's identifier |
| `exp` | Expiration time | Must not be expired according to policy |
| `nbf` | Not-before | Must not be used before its effective time |
| `iat` | Issued-at | Can be used for token age policy, if defined |
| `sub` | Subject | Serves as identity per issuer contract; not assumed to be email |
| `scope` / `scp` | Permissions granted by the AS | Converted to authorities per contract |
| `azp` / `client_id` | Client/requester per token profile | Does not replace audience |
| `tenant_id` | System-specific claim | Validate contract and tenant authorization |
| `jti` | Token ID | Can support audit/replay/revocation depending on architecture |

A JWT access token may contain other fields depending on the Authorization Server. **Do not assume every claim is required or has the same type across all issuers**.

## 3. The `ReactiveJwtDecoder` Interface

In the Spring Security reactive stack, the interface has the core concept:

```java
public interface ReactiveJwtDecoder {
    Mono<Jwt> decode(String token) throws JwtException;
}
```

Here:

- Input: compact JWT string received by the Resource Server.
- Success output: `Mono<Jwt>` emitting a JWT that has passed decoding/validation.
- Error output: the publisher emits an error signal, typically related to `JwtException`/validation, or an error may be thrown before the publisher is returned per the API contract.
- `Mono` represents 0–1 value or error under the Reactor model; for a valid JWT, the expected result is a single `Jwt`.

### 3.1. Differences from Servlet `JwtDecoder`

| Aspect | Servlet stack | Reactive WebFlux |
|---|---|---|
| Interface | `JwtDecoder` | `ReactiveJwtDecoder` |
| Decode signature | `Jwt decode(String)` | `Mono<Jwt> decode(String)` |
| Nimbus decoder | `NimbusJwtDecoder` | `NimbusReactiveJwtDecoder` |
| Security configuration | `HttpSecurity` | `ServerHttpSecurity` |
| Filter chain bean | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Authorization DSL | `authorizeHttpRequests` | `authorizeExchange` |
| Request security model | Servlet filters/context | WebFilters + Reactor context |
| HTTP testing | MockMvc | WebTestClient |
| Token type for API | JWT access token | JWT access token |

**Do not copy Servlet code straight into WebFlux.** A `JwtDecoder` bean does not automatically replace a `ReactiveJwtDecoder` bean in a reactive Resource Server, just as `SecurityFilterChain` does not replace `SecurityWebFilterChain`.

### 3.2. Why Is the Result a `Mono<Jwt>`?

In some configurations, the decoder needs to query metadata or a JWK Set over HTTP. The reactive API allows those I/O operations to fit WebFlux and integrate with Reactor composition, rather than having the application make blocking HTTP calls on an event-loop thread.

Example of an application using the decoder:

```java
Mono<Jwt> verified = reactiveJwtDecoder.decode(token);

return verified.map(jwt -> jwt.getSubject());
```

This is an example of a pipeline. **Do not invoke the decoder manually in every controller** just to read the subject; Spring Security Resource Server already performs authentication and places the principal into the security context.

### 3.3. Reactor Context Instead of ThreadLocal Assumptions

The security context in WebFlux is bound to the reactive execution context; it is not used with the ThreadLocal assumptions of a traditional Servlet request.

Example of reading Authentication in a reactive pipeline:

```java
Mono<String> currentPrincipalName =
    ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication())
        .map(Authentication::getName);
```

Imports:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;
```

This is how you read the context in a reactive flow, **not a replacement for authorization**. If execution moves to a callback outside the Reactor context or uses blocking threads improperly, security context propagation may not behave as expected.

## 4. What Is `NimbusReactiveJwtDecoder`?

`NimbusReactiveJwtDecoder` is an implementation of `ReactiveJwtDecoder` built on Nimbus's JOSE/JWT processing capabilities, with Spring Security's reactive integration.

It can be configured from:

1. **Issuer location**: uses the issuer's metadata to discover key-related information.
2. **JWK Set URI**: knows the issuer's trusted JWKS URL in advance.
3. **Configured public key or secret key**: when the system has a specific key management contract, depending on the builder/algorithm and Spring Security version.

Most commonly used with an external Authorization Server are **issuer location** or **JWK Set URI**.

### 4.1. The Decoder Does Not Discover a Trusted Issuer from an Arbitrary Token

Architecturally wrong:

```text
Read unverified JWT payload
  -> take arbitrary iss self-declared by the token
  -> fetch JWK Set from an arbitrary URL
  -> trust the token if the signature matches the self-fetched key
```

An attacker can craft a token with an issuer/JWKS under their own control. The Resource Server must configure **trusted issuer(s)** and key discovery policy upfront; the `iss` field in the token is only compared against the allowed issuer(s).

### 4.2. `NimbusReactiveJwtDecoder` Does Not Grant Scopes

The decoder can produce a `Jwt` containing a `scope` claim, while converting scopes into `SCOPE_...` belongs to the authentication converter. Endpoint permissions are checked afterward in `authorizeExchange`, whereas permissions on a specific order/customer belong to the service policy.

## 5. Simplest Approach: Spring Boot Configuration with `issuer-uri`

For Spring Boot WebFlux, a common configuration is:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/shop
```

With compatible dependencies and auto-configuration, Spring Security creates a reactive JWT decoder from the trusted issuer, reading the issuer metadata and public keys needed to validate JWTs.

For a Resource Server, the issuer URI is the **expected issuer identifier**, not a login request URL and not the API's audience.

### 5.1. When to Use `ReactiveJwtDecoders.fromIssuerLocation`?

One way to build the decoder in Java:

```java
@Bean
ReactiveJwtDecoder jwtDecoder() {
    String issuer =
        "https://login.example.test/realms/shop";

    return ReactiveJwtDecoders.fromIssuerLocation(issuer);
}
```

Imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoders;
```

This method is a factory that creates a `ReactiveJwtDecoder` based on issuer discovery via the mechanism supported by Spring Security. It is useful when the application wants an explicit bean while still using issuer metadata.

For applications that only need issuer configuration and have no extra requirements, **property-based configuration is usually simpler** than writing a custom bean.

### 5.2. Configuring Audience If Supported by Your Spring Boot Version

Some Spring Boot versions support the audience property:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/shop
          audiences:
            - orders-api
```

Whether the audience property is applied depends on **the Spring Boot version and how you configure the decoder yourself**. If the application provides its own `ReactiveJwtDecoder` bean, do not assume Boot will still automatically attach all desired validators to that bean.

**Regardless of how it is configured, the Orders API must check that `aud` contains `orders-api`.** A token intended for the Payments API must not be accepted merely because the signature is valid and the issuer is the same.

## 6. Java Configuration: WebFlux `SecurityWebFilterChain`

A complete example for HTTP authorization in the Orders API:

```java
@Configuration
@EnableWebFluxSecurity
public class ReactiveApiSecurityConfiguration {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http) {

        return http
            .authorizeExchange(exchange -> exchange
                .pathMatchers(HttpMethod.GET, "/public/catalog")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")
                .pathMatchers(HttpMethod.POST, "/api/orders/*/cancel")
                    .hasAuthority("SCOPE_orders.cancel")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

Imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
```

Key points:

- `ServerHttpSecurity` is the builder for **WebFlux**, not Servlet `HttpSecurity`.
- `SecurityWebFilterChain` replaces `SecurityFilterChain`.
- `authorizeExchange` uses `pathMatchers`/`anyExchange`; not `authorizeHttpRequests`.
- `oauth2ResourceServer(...jwt...)` enables JWT Bearer authentication with the reactive decoder.
- `hasAuthority("SCOPE_orders.read")` checks the authority mapped from the access token.
- `anyExchange().denyAll()` is a fallback protecting undefined routes.

This is an illustrative configuration for JWT and HTTP authorization. For browser clients, an appropriate CORS/CSRF policy is still needed; for multi-tenant APIs, the service must still verify ownership and permissions on each order.

### 6.1. When You Need to Separate GET/POST by Scope

The same URL path `/api/orders/42` may serve both GET and PATCH. If you only write:

```java
.pathMatchers("/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
```

the rule could include HTTP mutations as well. Use the HTTP method in the matcher when business requirements call for separate read/write/cancel permissions.

### 6.2. Path Matching Does Not Know the Order's Owner

A token for `user-123` with `orders.read` does not prove the user is allowed to read `order-42`. The method/service needs to verify:

```text
caller has orders.read
AND order.tenant is within allowed tenants
AND (
    caller is owner
    OR share ACL permits
    OR authorized support assignment permits
)
```

The JWT decoder validates the token; it does not query the Orders database to authorize individual records.

## 7. Creating a `NimbusReactiveJwtDecoder` Bean from Issuer

When direct control over the decoder is needed:

```java
@Configuration
public class ReactiveJwtDecoderConfiguration {

    private static final String ISSUER =
        "https://login.example.test/realms/shop";

    @Bean
    ReactiveJwtDecoder jwtDecoder() {
        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder
                .withIssuerLocation(ISSUER)
                .build();

        decoder.setJwtValidator(
            JwtValidators.createDefaultWithIssuer(ISSUER)
        );

        return decoder;
    }
}
```

Imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
```

In Spring Security versions that provide the `withIssuerLocation(...)` builder, this approach uses issuer metadata to determine the key/decoder configuration. `setJwtValidator(...)` explicitly sets the desired validators.

**Version check:** builder/option names and discovery behavior may vary across Spring Security versions. For versions without this builder, use the `ReactiveJwtDecoders.fromIssuerLocation(...)` factory or the corresponding builder API supported by that version's documentation. Do not invent APIs when implementing.

### 7.1. Why Explicitly Specify `JwtValidators`?

A decoder needs two groups of checks:

1. **JWS cryptography/key:** the signature was created by a trusted key and an allowed algorithm.
2. **Claims/contract:** issuer, audience, timestamps, token type, or custom rules.

If an application creates a custom decoder and relies solely on signature validity, it may accept a token signed by the right key but with the wrong audience, expired, or violating the contract.

`JwtValidators.createDefaultWithIssuer(ISSUER)` provides the default validators along with the issuer per version. When audience or other claims are needed, you must **combine** them rather than replacing existing checks.

### 7.2. The Decoder Returns a Mono, While Validators Can Be Synchronous

An `OAuth2TokenValidator<Jwt>` checks claims on a `Jwt` already constructed by the decoder, which is typically minimal synchronous/CPU logic. That does not conflict with the reactive decoder.

However, if a "validator" performs a blocking database query or HTTP call on its own, it can harm WebFlux execution. If validation requires I/O, consider placing that logic in the appropriate reactive authentication/authorization or service layer, rather than hiding blocking calls inside a validator.

## 8. Creating a Decoder with `jwk-set-uri`

An issuer has a JWK Set URL:

```text
https://login.example.test/realms/shop/protocol/openid-connect/certs
```

It can be configured as:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/shop
          jwk-set-uri: https://login.example.test/realms/shop/protocol/openid-connect/certs
```

This directly provides the JWKS URL; depending on how Spring Boot/Spring Security initializes, the application can avoid having to discover issuer metadata to locate the JWKS URI. **Keep issuer validation as a separate responsibility**, however—never treat the JWK Set URI as an issuer check.

### 8.1. Java Bean Using JWK Set URI

```java
@Configuration
public class JwksDecoderConfiguration {

    private static final String ISSUER =
        "https://login.example.test/realms/shop";

    private static final String JWKS =
        "https://login.example.test/realms/shop/protocol/openid-connect/certs";

    @Bean
    ReactiveJwtDecoder jwtDecoder() {
        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder
                .withJwkSetUri(JWKS)
                .build();

        decoder.setJwtValidator(
            JwtValidators.createDefaultWithIssuer(ISSUER)
        );

        return decoder;
    }
}
```

Key imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
```

**If you only create a decoder from a JWK Set URI without setting an issuer validator**, the API may lack the condition that `iss` matches the expected issuer. The JWK URI proves the key comes from a configured source, while issuer/audience/purpose remain claims that must be validated per contract.

### 8.2. Choosing Issuer URI or JWK Set URI?

| Scenario | Configuration approach |
|---|---|
| AS has standard metadata and you want minimal configuration | `issuer-uri` |
| AS provides a stable JWKS URL but discovery is restricted | `jwk-set-uri` + issuer/audience validators |
| Need to reduce startup dependency on the discovery endpoint | Can configure an explicit JWK Set URL; distinguish startup vs. runtime fetch |
| AS rotates keys frequently | Use JWKS with an appropriate key rotation/caching plan |
| System has no network access to AS but has a fixed public key | Can use a public-key builder per contract, though key rotation needs separate operations |
| Multiple issuers | A resolver and per-decoder/validator trusting the corresponding issuer, never blindly trusting every token's `iss` |

Do not "open up all algorithms," remove the issuer check, or disable HTTPS to work around a temporary JWK incident. Doing so turns an operational issue into an authentication vulnerability.

## 9. Issuer Metadata Discovery and Network Dependencies

An OIDC/OAuth Authorization Server can publish metadata at discovery endpoints, including `issuer` and `jwks_uri`.

A logical flow:

```mermaid
sequenceDiagram
    participant C as Client
    participant API as WebFlux Resource Server
    participant AS as Authorization Server
    C->>API: Authorization: Bearer JWT
    Note over API: Decoder configures trusted issuer
    opt Discovery or JWK refresh needed
        API->>AS: HTTPS metadata/JWKS request
        AS-->>API: Trusted metadata / JWK Set
    end
    Note over API: Select key by kid/alg, verify signature
    Note over API: Validate iss, aud, exp, nbf
    API-->>C: 2xx if authorized / 401 or 403 if denied
```

Details of when discovery/fetching occurs depend on the version, Boot auto-configuration, and caching. Some configurations query metadata when initializing the bean; others defer the work until the first JWT arrives. **Do not assert a single fixed startup strategy for all Spring Security versions.**

### 9.1. Network State Does Not Prove a Token Is Valid

If the metadata/JWKS endpoint encounters DNS, TLS, timeout, or 5xx errors, the decoder may fail to retrieve the required key. The Resource Server **must not accept a token without verifying its signature just because the network failed**.

Some requests may still be validated using already-cached keys, depending on the decoder design; understand TTL/cache and failure behavior. Never fall back to parsing the JWT payload directly or accepting tokens with `alg=none`.

### 9.2. Verifying Issuer Metadata

A trusted issuer is configured:

```text
https://login.example.test/realms/shop
```

If metadata returns a different issuer or the JWT `iss` claim does not match the agreed value, the Resource Server must reject by default rather than automatically accepting whatever issuer the metadata server returns.

## 10. JWK Set, `kid`, and Key Rotation

A JWK Set is a collection of public keys published by an issuer, which may contain multiple active keys to support rotation.

Conceptual example:

```json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "key-old",
      "use": "sig",
      "alg": "RS256",
      "n": "<MODULUS>",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "key-new",
      "use": "sig",
      "alg": "RS256",
      "n": "<MODULUS>",
      "e": "AQAB"
    }
  ]
}
```

The `n` values here are placeholders, not real keys.

When the JWT header contains:

```json
{"alg": "RS256", "kid": "key-new"}
```

the decoder must select the key matching `kid`, algorithm, and key-use constraints to verify the signature.

### 10.1. When the Issuer Adds a New `kid`

A rotation may consist of:

1. The AS generates a new key.
2. The AS publishes the new public JWK on the JWKS endpoint while keeping the old key.
3. The AS starts signing new tokens with the private key corresponding to the new `kid`.
4. Resource Servers refresh the JWK Set via their cache/fetch mechanism.
5. The AS retains the old key long enough to verify tokens that are still valid.
6. After the transition window, the AS removes the old key.

**Do not remove the old key immediately** while tokens signed by that key are still unexpired and must be verified by the Resource Server. Conversely, keeping keys around indefinitely without control also carries risk if a private key has been compromised.

### 10.2. `kid` Is Not a URL for Fetching Keys

An attacker-crafted JWT may include header parameters such as `jku` or `x5u`. The Resource Server should not fetch keys from arbitrary URLs self-declared by the token; the trusted JWK Set URI must come from trusted configuration/issuer metadata.

`kid` is only a key identifier within an authorized key source; **it does not prove the key belongs to the issuer**.

### 10.3. JWKS Cache Is Not an Authentication Cache

Public JWKs can be cached to avoid hitting the AS for every signature verification. However, each JWT still requires signature/claim validation.

Do not conflate:

- JWK cache: caches the set of public keys.
- Access token cache: caches token/authentication results.
- HTTP response cache: caches API data.
- Refresh token: credential an OAuth client uses at the token endpoint.

They have different lifecycles and risks.

## 11. Accept Only Permitted Signing Algorithms

A JWT header may contain:

```json
{"alg":"RS256"}
```

but the `alg` value sent by the token is **untrusted** before verification. The decoder must have a configured list of algorithms for the issuer/key type, rather than choosing whichever algorithm the caller requests.

Example of configuring the Nimbus builder for an algorithm per contract, on a version supporting this option:

```java
NimbusReactiveJwtDecoder decoder =
    NimbusReactiveJwtDecoder
        .withJwkSetUri(JWKS_URI)
        .jwsAlgorithm(SignatureAlgorithm.RS256)
        .build();
```

Imports:

```java
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
```

If the issuer uses ES256, RS512, or other algorithms, select an algorithm/key configuration **compatible with the contract and Spring Security version**, rather than blindly trusting any `alg`.

### 11.1. Things to Avoid

- Do not accept `alg=none` for bearer JWT access tokens.
- Do not let an attacker switch from an asymmetric algorithm to a symmetric one via an arbitrary header.
- Do not use a public key as an HMAC shared secret.
- Do not disable JWS verification and read claims directly.
- Do not trust key URLs inside the token header.
- Do not add all algorithms to an allowlist just to let one failing token pass.

### 11.2. Algorithm and Issuer Are Two Conditions

A JWT with a valid RS256 signature under some public key **is not enough** if the token was not signed by a key from a trusted source, has the wrong issuer, or has the wrong audience. You need all of **trusted key + permitted algorithm + expected claims**.

## 12. Combining Issuer and Audience Validators

A cryptographically valid JWT access token that has:

```json
"aud": ["payments-api"]
```

must not be used to call the Orders API if the Orders API requires the `orders-api` audience.

Full example using a decoder bean:

```java
@Configuration
public class OrdersJwtDecoderConfiguration {

    private static final String ISSUER =
        "https://login.example.test/realms/shop";

    private static final String AUDIENCE =
        "orders-api";

    @Bean
    ReactiveJwtDecoder jwtDecoder() {
        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder
                .withIssuerLocation(ISSUER)
                .build();

        OAuth2TokenValidator<Jwt> defaultValidators =
            JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience().contains(AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }

            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Token is not intended for orders-api",
                    null
                )
            );
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                defaultValidators,
                audienceValidator
            )
        );

        return decoder;
    }
}
```

Imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
```

**This is the most important example in the lesson:** using `NimbusReactiveJwtDecoder` to decode/verify the JWT and `setJwtValidator(...)` to attach the **complete** set of token acceptance rules for the Orders API.

### 12.1. Why Not Just Write `decoder.setJwtValidator(audienceValidator)`?

The `setJwtValidator(...)` method sets the validator on the decoder. If you set only the audience validator, the application may lose default issuer/timestamp validation depending on the initial configuration.

That is why the example uses:

```java
new DelegatingOAuth2TokenValidator<>(
    JwtValidators.createDefaultWithIssuer(ISSUER),
    audienceValidator
)
```

It expresses **AND**: the token must pass the default validations with the issuer **and** the API's audience check.

### 12.2. Audience Differs from `client_id`

An OAuth client `web-portal` may request tokens for multiple APIs:

```text
Client ID: web-portal

Token A:
  aud = orders-api

Token B:
  aud = payments-api
```

The Orders API must accept Token A and reject Token B, **even though `client_id` is the same**. Do not use `client_id` in place of audience merely because the client is a familiar caller.

### 12.3. What If the Issuer Does Not Include `aud`?

Do not inject `aud=orders-api` during claim conversion. Fix the token issuance contract or AS configuration so tokens are scoped for the appropriate Resource Server.

If the system implements a token profile without `aud` and has another resource binding mechanism, design a policy appropriate for that profile. An application that requires an audience **should never fail open** just because the issuer omits the claim.

## 13. Timestamp Validation and Clock Skew

JWT uses NumericDate claims:

```json
{
  "iat": 1794715200,
  "nbf": 1794715200,
  "exp": 1794718800
}
```

Spring Security typically represents `exp`/`nbf` as appropriate Java time types when constructing `Jwt`, such as `Instant`.

The APIs:

```java
jwt.getIssuedAt();
jwt.getNotBefore();
jwt.getExpiresAt();
```

Default validators normally check time validity per contract and may apply clock skew. To configure skew explicitly, use `JwtTimestampValidator`:

```java
JwtTimestampValidator timestampValidator =
    new JwtTimestampValidator(Duration.ofSeconds(60));
```

Imports:

```java
import java.time.Duration;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;
```

When assembling the validator set yourself, still keep issuer and audience:

```java
OAuth2TokenValidator<Jwt> validators =
    new DelegatingOAuth2TokenValidator<>(
        new JwtTimestampValidator(Duration.ofSeconds(60)),
        new JwtIssuerValidator(ISSUER),
        audienceValidator
    );

decoder.setJwtValidator(validators);
```

Import:

```java
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
```

This snippet shows how to **manually assemble the timestamp/issuer/audience policy**; when using the default validator factory, you do not need to add a duplicate timestamp validator unless you intentionally want to change the skew logic.

### 13.1. Small Skew Does Not Mean Ignoring Expiration

An issuer and Resource Server may have clocks that differ by a few seconds. Skew helps reduce false rejections at time boundaries. However, skew should not be so large that it extends token lifetime well beyond security policy.

**Do not modify `exp` or strip `nbf`** to accept failing tokens. If clocks drift significantly, synchronize NTP or fix the issuer clock.

### 13.2. Optional Claims and the Token Contract

Not every JWT profile requires `nbf`/`iat`. An API contract may require `exp` or token type. When adding validators, make clear which claims are **required**, which are **optional**, and which data types are accepted.

If the API requires `exp` to be present, a dedicated validator can verify the presence of the claim rather than relying solely on default behavior.

## 14. Custom Claim Validation After Decoding

A multi-tenant system has claims:

```json
{
  "tenant_id": "shop-a",
  "token_use": "access"
}
```

You may want to reject tokens missing `tenant_id` or with a `token_use` that violates the contract.

Example validator:

```java
OAuth2TokenValidator<Jwt> tenantClaimValidator = jwt -> {
    Object raw = jwt.getClaim("tenant_id");

    if (raw instanceof String tenant && !tenant.isBlank()) {
        return OAuth2TokenValidatorResult.success();
    }

    return OAuth2TokenValidatorResult.failure(
        new OAuth2Error(
            "invalid_token",
            "Missing or invalid tenant_id",
            null
        )
    );
};
```

It can be combined:

```java
decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(ISSUER),
        audienceValidator,
        tenantClaimValidator
    )
);
```

### 14.1. Distinguishing Token-Wide Contract from Object-Level Authorization

A valid tenant claim only states that the token is bound to a tenant per contract. If the caller requests:

```http
GET /api/tenants/shop-b/orders/order-99
```

the service needs to check whether the principal has access to `shop-b` and `order-99`. A JWT validator cannot see all ownership/ACL relationships and should not be turned into a per-URL database policy.

### 14.2. Do Not Fabricate Claims to Grant Permissions

A converter can normalize valid data types issued by the AS. It must never:

- Add `ROLE_ADMIN` to every token.
- Rewrite the audience to the current API.
- Extend `exp`.
- Replace `sub` with a target user from the request.
- Populate tenant from a query parameter and treat it as a verified identity.

Such modifications undermine the meaning of the signature and token contract.

## 15. JWT Access Token Differs from OIDC ID Token

In OpenID Connect, a client can receive an **ID token** used to confirm an authentication event for the OIDC client. A Resource Server, on the other hand, needs an **access token** issued for the API.

An OIDC ID token can look like a JWT:

```json
{
  "iss": "https://login.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["web-portal"],
  "email": "user@example.test"
}
```

However, the audience `web-portal` is the client, not the Orders API. If the Orders API requires `aud=orders-api`, this token must be rejected even if the signature is valid.

### 15.1. Do Not Rely on Having the Same `sub`

An access token and an ID token may share `sub=user-123`. That does not make them tokens with the same purpose.

Distinguish clearly:

| Token type | Primary recipient | Purpose |
|---|---|---|
| OIDC ID token | OIDC client | Proves end-user authentication details to the client |
| OAuth access token | Intended Resource Server | Enables the API to validate the token and evaluate access permissions |
| Refresh token | Authorization Server/token endpoint via OAuth client | Requests a new access token under supported flows |

Do not send a refresh token or ID token to the Orders API as a substitute for an access token.

### 15.2. JWT Type and Profile

Some token profiles use `typ=at+jwt` or dedicated claims. If the contract mandates a JWT access-token profile (such as RFC 9068), configure appropriate validation. Do not assume a valid signature alone is enough to prevent **cross-JWT confusion** between ID tokens, access tokens, or other internal JWT types.

## 16. Authorities and `JwtAuthenticationToken` in WebFlux

After decoding, the JWT holds claims, but Spring Security still needs an `Authentication` with a principal and `GrantedAuthority` instances. In a typical setup, the `scope` claim:

```json
{
  "scope": "orders.read orders.write"
}
```

is converted into:

```text
SCOPE_orders.read
SCOPE_orders.write
```

Only then does authorization:

```java
.pathMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
```

have meaning.

### 16.1. Not Every `roles` Claim Automatically Gets `ROLE_...`

An issuer may emit:

```json
{
  "roles": ["ORDER_MANAGER"],
  "scope": "orders.read"
}
```

By default, Spring Security typically processes scopes using the `SCOPE_` convention. A `roles` claim needs an appropriate converter if the application wants to map it into dedicated authorities.

Do not use `hasRole("ORDER_MANAGER")` if the token converter has not produced `ROLE_ORDER_MANAGER` from a trusted source.

### 16.2. Authentication Converter Differs from JWT Decoder

| Tool | Role |
|---|---|
| `ReactiveJwtDecoder` | Verifies the JWT and returns `Mono<Jwt>` |
| `OAuth2TokenValidator<Jwt>` | Checks issuer/audience/claims |
| `JwtGrantedAuthoritiesConverter` | Reads permission claims and creates `GrantedAuthority` instances |
| `JwtAuthenticationConverter` | Converts `Jwt` into Authentication in the sync model |
| `ReactiveJwtAuthenticationConverterAdapter` | Adapter to use a sync converter with reactive authentication |
| `ReactiveJwtAuthenticationConverter` | Reactive converter for JWT in WebFlux |
| `SecurityWebFilterChain` | Applies authentication/authorization to WebFlux requests |

A JWT verified without mapping permissions means the client may be authenticated yet still receive 403 when an endpoint requires a specific authority.

## 17. Customizing Authorities with `ReactiveJwtAuthenticationConverterAdapter`

Suppose the AS grants permissions in a custom claim:

```json
{
  "permissions": ["orders:read", "orders:export"]
}
```

The API wants to map them into:

```text
PERM_orders:read
PERM_orders:export
```

One way to configure this is to create the familiar `JwtAuthenticationConverter` and wrap it with the reactive adapter:

```java
@Bean
SecurityWebFilterChain securityWebFilterChain(
        ServerHttpSecurity http) {

    JwtGrantedAuthoritiesConverter permissions =
        new JwtGrantedAuthoritiesConverter();

    permissions.setAuthoritiesClaimName("permissions");
    permissions.setAuthorityPrefix("PERM_");

    JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();

    converter.setJwtGrantedAuthoritiesConverter(permissions);
    converter.setPrincipalClaimName("sub");

    ReactiveJwtAuthenticationConverterAdapter reactiveConverter =
        new ReactiveJwtAuthenticationConverterAdapter(converter);

    return http
        .authorizeExchange(auth -> auth
            .pathMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("PERM_orders:read")
            .anyExchange().denyAll()
        )
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(jwt ->
                jwt.jwtAuthenticationConverter(reactiveConverter)
            )
        )
        .build();
}
```

Relevant imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtAuthenticationConverterAdapter;
import org.springframework.security.web.server.SecurityWebFilterChain;
```

**Condition:** the `permissions` claim must be issued by a trusted AS with a clear contract. Never map arbitrary user-supplied strings into `ROLE_ADMIN`.

### 17.1. The Adapter Does Not Make a Blocking Converter Non-Blocking

The adapter provides API type compatibility; it does not turn blocking database/HTTP logic into a safe reactive operation.

It is suitable for converting **claims already present in the JWT into authorities** via fast in-memory operations. If authority mapping requires calling a service, database, or network, use a proper reactive design and manage latency/backpressure instead of hiding `block()` inside the converter.

### 17.2. Choosing the Principal Name

By default, subject is usually a better principal name than a display username. If you use:

```java
converter.setPrincipalClaimName("preferred_username");
```

then `Authentication.getName()` may become a more readable login name, **at the risk of instability or collisions**. For ownership/tenant auditing, use identifiers from a trusted issuer and subject; with multiple issuers, consider an issuer namespace.

## 18. Reactive Method Security and Record-Level Permissions

WebFlux can use reactive method security:

```java
@Configuration
@EnableReactiveMethodSecurity
public class ReactiveMethodSecurityConfig {
}
```

Import:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
```

Service example:

```java
@Service
public class OrderService {

    private final ReactiveOrderRepository repository;

    public OrderService(ReactiveOrderRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public Mono<OrderDto> getOrder(
            String orderId,
            AuthenticatedActor actor) {

        return repository.findVisibleOrder(
                orderId,
                actor.tenantId(),
                actor.subject()
            )
            .switchIfEmpty(
                Mono.error(new OrderNotFoundException())
            )
            .map(OrderDto::from);
    }
}
```

Types `ReactiveOrderRepository`, `AuthenticatedActor`, `OrderDto`, and `OrderNotFoundException` are domain examples that must be implemented for the application. `AuthenticatedActor` must be built from the **verified Authentication**, not taken from the caller's JSON body.

Key points:

- `@PreAuthorize` checks the read operation permission.
- The repository queries objects **within the permitted tenant and ownership**.
- `Mono.error(...)` emits a reactive error signal if no visible record is found.
- Do not call `repository.findById(...).block()` just to check permissions afterward.
- Do not trust `tenantId` in a path/header as proof of membership.

### 18.1. Method Security Does Not Replace Object Policy

A user with `SCOPE_orders.read` who does not own `order-99` must still be denied. `@PreAuthorize("hasAuthority(...)")` **does not verify ownership on its own**.

You can combine a policy bean/`ReactiveAuthorizationManager` when complex logic is required. However, if the policy needs to query a reactive database, design the asynchronous composition at the right layer; avoid using blocking SpEL helpers to access the DB.

### 18.2. Self-Invocation and Proxy Semantics

When using annotation-based method security, internal calls within the same bean may bypass the proxy and not behave as expected. For sensitive use cases, design service boundaries and query/mutation conditions so that policies cannot be bypassed simply via an internal call.

## 19. Do Not Call `block()` in the Authentication Path

A typical mistake when migrating from Servlet to WebFlux:

```java
// Unsuitable on the WebFlux event-loop:
Jwt jwt = reactiveJwtDecoder.decode(token).block();
```

Or:

```java
public Mono<Jwt> decode(String token) {
    Jwt jwt = blockingJwtDecoder.decode(token);
    return Mono.just(jwt);
}
```

The second approach executes blocking work **before** returning the publisher. If there is synchronous I/O, it can block the event-loop thread and reduce throughput, causing latency or timeouts.

### 19.1. Proper Composition

Reactive style:

```java
return reactiveJwtDecoder.decode(token)
    .flatMap(jwt -> reactiveService.findOrderForActor(
        jwt.getSubject(),
        jwt.getClaimAsString("tenant_id"),
        orderId
    ));
```

In a normal Resource Server controller, manually calling the decoder is unnecessary; the example above merely illustrates composition. Auth is already handled by the Spring Security filter.

### 19.2. If You Must Integrate a Blocking Library

A legacy blocking segment can be isolated on `boundedElastic` when truly necessary:

```java
Mono<LegacyResult> result =
    Mono.fromCallable(() -> legacyClient.call())
        .subscribeOn(Schedulers.boundedElastic());
```

However, this is **not a reason to replace the reactive decoder with an arbitrary blocking implementation**. Using a scheduler does not solve concurrency limits, timeouts, bulkheads, memory, or resource exhaustion issues. For JWKS/metadata, prefer Spring Security's decoder and reactive HTTP integration.

### 19.3. Do Not Manually `subscribe()` to "Trigger Authentication"

Wrong example:

```java
reactiveJwtDecoder.decode(token)
    .subscribe(jwt -> securityContext.setAuthentication(...));

// Code continues immediately; authentication may not be finished yet.
```

A manual `subscribe()` call like this detaches execution from the security pipeline, potentially creating race conditions and failing to propagate context. Let Spring Security manage the authentication chain or return the publisher so the pipeline awaits the proper result.

## 20. Reactive Error Signals and HTTP Responses

When `ReactiveJwtDecoder.decode(...)` cannot validate a token, the publisher emits an error (or the implementation may throw early per contract). The Spring Security authentication manager/filter translates the failure into an appropriate HTTP error.

Common cases:

| Scenario | Detecting layer | Typical HTTP response |
|---|---|---|
| Missing Bearer token on protected route | Security authentication/authorization | `401 Unauthorized` with Bearer challenge |
| Malformed JWT | Decoder | `401 invalid_token` |
| Wrong JWT signature/mismatched key | Decoder | `401 invalid_token` |
| Expired JWT | Timestamp validator | `401 invalid_token` |
| Wrong JWT issuer | Issuer validator | `401 invalid_token` |
| JWT missing expected audience | Audience validator | `401 invalid_token` |
| Valid token, missing read authority | Authorization | `403 Forbidden` |
| Token has scope, object outside tenant/ownership | Service policy | `403` or `404` per contract |
| JWKS/metadata endpoint failure | Decoder/network | Authentication fails; HTTP status may depend on exception handling |
| Business logic error in API | Handler/service | Domain-specific status |

**Do not return `403` for an unauthenticated token, and do not return `401 invalid_token` for every object-level permission failure.**

### 20.1. Reactive Security Entry Points

WebFlux uses server-side components specifically built for reactive authentication/authorization, not Servlet classes like `BearerTokenAuthenticationEntryPoint` intended for `HttpServletResponse`.

When customizing JSON/Problem Details responses in WebFlux, choose the appropriate extension points on `ServerHttpSecurity` and preserve HTTP Bearer `WWW-Authenticate` semantics. Do not redirect API clients to an HTML login page if the architecture requires Bearer tokens.

### 20.2. Do Not Swallow Errors and Create a Fake `Jwt`

Wrong:

```java
return delegate.decode(token)
    .onErrorResume(error ->
        Mono.just(fakeJwtWithAdminScope)
    );
```

This snippet is an **unsafe** example: when the signature is invalid or JWKS fails, the server fabricates a valid principal. Authentication must **fail closed**. Never populate the SecurityContext when the decoder cannot validate the token.

## 21. `Jwt` Does Not Automatically Grant Access to Every Object

A JWT has:

```json
{
  "sub": "user-123",
  "tenant_id": "shop-a",
  "scope": "orders.read"
}
```

and request:

```http
GET /api/orders/order-99
```

Merely having a valid token with a read scope does not prove `order-99` belongs to `user-123`.

A good policy typically looks like:

```text
canReadOrder(actor, order):
  valid access token for orders-api
  AND actor has orders.read authority
  AND order.tenant belongs to actor allowed tenants
  AND (
       actor owns order
       OR valid share ACL
       OR assigned support policy permits
  )
```

A reactive repository should query only records **visible** to the actor, rather than loading all orders and filtering later or returning data before checking.

### 21.1. List/Export/Count Also Need Filtering

Not just the detail endpoint:

```text
GET /api/orders
GET /api/orders/search
GET /api/orders/count
GET /api/orders/export
```

must all restrict data according to tenant/owner/share policy. A token with `SCOPE_orders.read` is not permission to query the entire database.

## 22. WebFlux JWT Decoder and Opaque Token Are Two Separate Branches

An application may receive:

1. JWT access token: the Resource Server uses `ReactiveJwtDecoder` to verify JWS/claims.
2. Opaque access token: the Resource Server calls an introspection endpoint via `ReactiveOpaqueTokenIntrospector`.

For opaque tokens, the API must configure the appropriate `opaqueToken(...)` branch, rather than using `NimbusReactiveJwtDecoder` to try parsing a random opaque string.

### 22.1. Do Not Choose Token Type Based Solely on Dots

A token containing dots does not prove it is a valid JWT access token; an AS might issue tokens with a different profile. Choose the processing mode according to the **Resource Server and AS contract**, rather than branching on "3 segments means trust JWT, otherwise introspection" without a trust policy.

### 22.2. Opaque Introspection Has Revocation Differences

Self-contained JWTs can usually be verified locally by the Resource Server within the token's lifetime, whereas immediate revocation requires mechanisms beyond the signature such as short TTLs, a denylist, a token status service, or introspection depending on the architecture.

Opaque introspection can check token status online but increases dependency on the Authorization Server's latency/availability. Choosing JWT or opaque is an architectural decision; there is no single universally best choice for all systems.

## 23. Multi-Issuer and Multi-Tenant in WebFlux

A system may accept tokens from:

```text
Issuer A:
  https://login.example.test/realms/shop

Issuer B:
  https://login.example.test/realms/partners
```

Each issuer may have:

- A different trusted issuer URI.
- A different JWKS URI/key rotation schedule.
- Different audience mapping.
- Different algorithms/claim contracts.
- Different meanings for `sub` and `tenant_id`.

Therefore, a decoder that only trusts Issuer A should not accept tokens from Issuer B. When multi-issuer support is needed, use an appropriate **reactive authentication manager resolver** to select from allowlisted authentication managers/decoders and validate each branch's issuer/contract.

### 23.1. Do Not Arbitrarily Trust the Issuer from an Unverified JWT

A resolver may need to inspect the unverified issuer claim to select a decoder **from a list of already-trusted issuers**. If the issuer is not in the allowlist, it must reject rather than building a decoder from a URL supplied by the token itself.

In particular, avoid logic like:

```text
issuer = decodePayloadWithoutVerification(token).iss
decoder = NimbusReactiveJwtDecoder.withIssuerLocation(issuer).build()
accept if signature verifies
```

without checking that the issuer is in a managed allowlist. An attacker could stand up their own issuer/keys and token and force the Resource Server to trust their source.

### 23.2. Identity Often Must Consider `(iss, sub)`

Two issuers can both issue:

```json
"sub": "user-123"
```

Yet these may be two independent accounts. When mapping the JWT subject to business data, consider the issuer namespace, tenant, and internal mapping rather than matching on username or string equality of subject alone.

## 24. Testing HTTP Authorization with `WebTestClient`

Spring Security Test supports configuring an authenticated test JWT for reactive WebFlux via `mockJwt()`.

Conceptual example:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveOrderSecurityTests {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void readScopeCanReachGetOrderEndpoint() {
        webTestClient
            .mutateWith(mockJwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            ))
            .get()
            .uri("/api/orders/42")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void otherScopeCannotReachGetOrderEndpoint() {
        webTestClient
            .mutateWith(mockJwt().authorities(
                new SimpleGrantedAuthority("SCOPE_profile")
            ))
            .get()
            .uri("/api/orders/42")
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

Imports:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;
```

**Example conditions:** The test context must include the WebFlux `SecurityFilterChain`, controller, and data fixtures for `/api/orders/42`; status 200 only makes sense when the business service actually succeeds. In an environment without order 42, the test may receive 404 after passing HTTP authorization.

### 24.1. `mockJwt()` Does Not Verify Real Signatures

A test request using:

```java
.mutateWith(mockJwt())
```

typically simulates a JWT Authentication for testing security/authorization. It **does not prove** that `NimbusReactiveJwtDecoder` fetches JWKS and verifies the JWS signature properly.

Therefore, separate tests into:

- WebTestClient tests: HTTP routes, 401/403, authorities, method security.
- Decoder tests: issuer, audience, signature/key, expiry, JWK rotation.
- Integration tests: real decoder against an appropriate AS/JWKS test endpoint.
- Business tests: tenant/ownership/object permissions.

### 24.2. Testing Requests Missing a Token

For a protected route:

```java
webTestClient.get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isUnauthorized()
    .expectHeader().valueMatches(
        "WWW-Authenticate",
        "Bearer.*"
    );
```

The actual status/header depends on chain and entry-point configuration. For a typical WebFlux JWT Bearer Resource Server, an unauthenticated request to a protected endpoint usually receives `401` with a Bearer challenge.

### 24.3. Testing Missing Authority and Wrong Object

A token with read scope requesting someone else's order may pass HTTP authorization and then be rejected by business policy. To catch Broken Object Level Authorization, use fixtures for **at least two users and two tenants**, and test detail/list/export endpoints.

## 25. Unit Testing the Decoder with Key/JWT Fixtures

To test real signature/claim validation, you need a test JWT with:

- Appropriate `alg` header.
- `kid` matching a public JWK served by the test server.
- Signature generated with the corresponding test private key.
- Controlled `iss`, `aud`, `exp`, and other claims.

A test matrix:

| Test JWT | Key/signature | Claims | Expected decode result |
|---|---|---|---|
| Valid Orders access token | Correct trusted key | Correct issuer/audience/time | Success `Mono<Jwt>` |
| Invalid signature | Wrong key | Valid-looking claims | Error |
| Wrong issuer | Trusted signature | Different issuer | Error |
| Wrong audience | Trusted signature | `aud=payments-api` | Error |
| Expired | Trusted signature | `exp` in the past | Error |
| Before `nbf` | Trusted signature | Token not yet valid | Error |
| Missing required tenant | Trusted signature | Missing `tenant_id` | Error per custom policy |
| Disallowed algorithm | Not in allowlist | Any | Error |
| Newly published `kid` | Correct new key | Valid claims | Success once decoder updates keys |
| Unknown `kid` and unable to fetch key | No trusted key | Any | Fail closed |

Do not use base64-decoded payloads to test signatures. You must have **real signed tokens in the test environment**, or intentionally stub network/JWKS behavior to test the contract.

### 25.1. `StepVerifier` for Checking Reactive Results

Given a decoder and a validly signed test token:

```java
StepVerifier.create(decoder.decode(validToken))
    .assertNext(jwt -> {
        assertEquals("user-123", jwt.getSubject());
        assertTrue(jwt.getAudience().contains("orders-api"));
    })
    .verifyComplete();
```

For an invalid token:

```java
StepVerifier.create(decoder.decode(invalidToken))
    .expectError(JwtException.class)
    .verify();
```

Imports:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import org.springframework.security.oauth2.jwt.JwtException;
import reactor.test.StepVerifier;
```

The variables `decoder`, `validToken`, and `invalidToken` are fixtures provided by the test setup. For specific network failures, the exception type may differ; assert appropriately for the test scope.

### 25.2. Avoid Relying on Production JWKS in Unit Tests

Do not call the production AS from unit tests because:

- It causes flaky tests when the network experiences issues.
- It sends unexpected traffic.
- It makes key rotation and responses hard to control.
- It can leak environment secrets if misconfigured.

Instead, use a test JWKS HTTP server or dedicated test keys not used in production.

## 26. Checking Auto-Configuration and Bean Selection

A project might simultaneously have:

```yaml
spring.security.oauth2.resourceserver.jwt.issuer-uri: ...
```

and:

```java
@Bean
ReactiveJwtDecoder jwtDecoder() { ... }
```

When a developer defines a custom decoder bean, Spring Boot auto-configuration may **back off** and let that bean govern behavior. Therefore:

- Do not assume Boot still automatically applies `audiences` to a custom decoder.
- Do not assume default issuer validation remains after `setJwtValidator(...)` depending on configuration.
- Do not accidentally register multiple `ReactiveJwtDecoder` beans without knowing which bean is used.
- If a specific decoder is needed for a `SecurityWebFilterChain`, specify it explicitly via the JWT DSL appropriate for your version.

### 26.1. Explicitly Specifying the Decoder in the DSL

Some configurations allow:

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.jwt(jwt ->
        jwt.jwtDecoder(reactiveJwtDecoder)
    )
)
```

Here `reactiveJwtDecoder` is the appropriate bean/instance provided via dependency injection. This approach is useful when there are multiple decoders/issuers/chains, while ensuring no circular dependencies are created and another API's decoder is not used by mistake.

### 26.2. Multiple `SecurityWebFilterChain` Beans

If an application has:

```text
/api/orders/**   JWT Orders Resource Server
/api/admin/**    JWT Admin API
/web/**          Session browser UI
```

define the chain matchers and ordering properly. A catch-all chain ordered before an API chain can cause API requests to receive form login/session auth instead of Bearer JWT.

`SecurityWebFilterChain` instances can be distinguished using `ServerHttpSecurity`'s `securityMatcher(...)` and order; use explicit mappings rather than assuming `anyExchange().denyAll()` in one chain will protect every request across the entire application.

## 27. CORS and CSRF in a JWT WebFlux Resource Server

An SPA at:

```text
https://app.example.test
```

calling the API:

```text
https://api.example.test
```

via `Authorization: Bearer ...` is still subject to browser CORS policy even though the backend uses WebFlux.

For browser clients:

- Allowed origin must match scheme/host/port.
- Allowed headers must include `Authorization` if the frontend explicitly sends Bearer.
- JSON POST/PATCH may require `Content-Type` in allowed headers.
- CORS preflight `OPTIONS` requests usually do not carry an access token.
- WebFlux CORS must be processed before auth requires a bearer token for the actual request.
- `allowCredentials(true)` is not automatically needed merely because the client sends a Bearer header; it depends on cookie/session credentials behavior.
- CORS does not replace CSRF or OAuth authorization.

### 27.1. An Illustrative WebFlux CORS Configuration

```java
@Bean
CorsWebFilter corsWebFilter() {
    CorsConfiguration cors = new CorsConfiguration();

    cors.setAllowedOrigins(List.of(
        "https://app.example.test"
    ));

    cors.setAllowedMethods(List.of(
        "GET", "POST", "PATCH"
    ));

    cors.setAllowedHeaders(List.of(
        "Authorization", "Content-Type"
    ));

    cors.setExposedHeaders(List.of(
        "WWW-Authenticate"
    ));

    cors.setAllowCredentials(false);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();

    source.registerCorsConfiguration("/api/**", cors);

    return new CorsWebFilter(source);
}
```

Imports in WebFlux:

```java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsWebFilter;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;
```

**Do not confuse** `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource` with the similarly named Servlet class in Spring MVC. For a specific project, a different WebFlux CORS integration may be chosen; avoid registering two conflicting filters.

### 27.2. JWT Bearer Header and CSRF

If the API **only** accepts Bearer tokens via an Authorization header explicitly attached by the client, the CSRF threat model differs from cookie sessions. However, if the same application also uses cookies/sessions or BFF login, never disable CSRF globally just because one API branch uses JWT.

CORS grants the browser permission to read responses; CSRF controls prevent requests with automatically attached credentials from causing side effects. The two mechanisms are independent.

## 28. Scalability, Latency, and Reactive I/O

The Nimbus reactive decoder can incur costs for:

1. Parsing the compact JWT.
2. Fetching/selecting the trusted public key, which may involve cache/network.
3. Verifying the signature with cryptographic algorithms.
4. Constructing claim objects.
5. Running validators.
6. Converting authorities.

Not every step is "free" just because the API returns `Mono`. JWS verification is CPU work; JWKS fetching has network latency; claim conversion also consumes CPU/memory.

### 28.1. Do Not Assume "Reactive" Automatically Makes Token Verification Faster

Reactive is suited for heavy I/O where threads should not be held while waiting. It does not eliminate the cost of RSA/ECDSA, JSON parsing, or policy checks.

For high-traffic APIs, monitor:

- JWT decode duration.
- JWKS request counts and cache hit/miss rates.
- JWKS HTTP failures/timeouts.
- CPU usage for signature verification.
- 401/403 counts by route and issuer.
- Key rotation disruptions.
- Number of invalid/malformed tokens.
- Memory/backpressure in WebFlux pipelines.

### 28.2. Combine Timeouts and Retries Carefully

When the AS/JWKS is unavailable, unbounded retries can amplify load and hang requests. Use sensible timeout/backoff policies and caching managed by the decoder/HTTP client; **never skip security validation** for throughput.

### 28.3. Do Not Log Raw JWTs for Debugging

A bearer token can be replayed if leaked. Avoid logging:

```text
Authorization: Bearer eyJ...
token=<FULL_JWT>
```

Instead, log:

```text
request_id=req-123
route=GET /api/orders/{id}
authn=FAILED
reason=INVALID_AUDIENCE
issuer_alias=shop
http_status=401
```

Only log issuer/subject/tenant when needed and according to sensitive-data handling policies; do not log raw claims or secrets.

## 29. Common Pitfalls When Using `ReactiveJwtDecoder`

### Pitfall A — Installing the Servlet Starter and Configuring WebFlux

Spring Security Servlet `JwtDecoder` and `SecurityFilterChain` are not the types WebFlux expects. Use the right WebFlux starter and reactive security DSL, avoiding mixed dependencies that cause the application to pick the wrong stack.

### Pitfall B — Using `NimbusJwtDecoder` Instead of `NimbusReactiveJwtDecoder`

If the application must run reactive auth, prefer `ReactiveJwtDecoder`. Do not wrap a synchronous decoder with `Mono.just(blockingDecode(...))` and assume it is no longer blocking.

### Pitfall C — Configuring Only `jwk-set-uri` and Forgetting the Issuer

A key URL specifies the key source, not an automatic `iss` check. Set an issuer validator if the contract requires it, especially when creating a custom bean.

### Pitfall D — Checking Only Signature and `exp`

A token can be valid yet intended for the Payments API. Validate `aud` for the Orders API.

### Pitfall E — Losing Defaults When Adding an Audience Validator

`setJwtValidator(...)` sets the validator; combine `JwtValidators.createDefaultWithIssuer(...)` with the custom audience check.

### Pitfall F — Trusting the Algorithm in `alg` from the Token

Allow only configured algorithms and trust proper key material; do not pick from an untrusted header.

### Pitfall G — Trusting `iss` from the Token and Fetching Arbitrary JWKS

This can let an attacker control the issuer/keys. Accept only issuers in a trusted allowlist.

### Pitfall H — Failing to Distinguish Access Tokens from ID Tokens

An ID token may have a valid signature while its audience is the OAuth client. APIs must require an access token intended for the Resource Server itself.

### Pitfall I — Manually Base64URL-Decoding to Extract User/Role

Claims can be altered by an attacker when the signature is unverified. Use `Jwt` from Spring Security's authenticated principal.

### Pitfall J — Assigning Roles from Any Claim Named `roles`

Role/permission mapping must follow the issuer contract; do not grant `ROLE_ADMIN` from untrusted data.

### Pitfall K — `block()` or Blocking JDBC in the WebFlux Authentication Chain

This can stall the event-loop, degrade throughput, and hang requests. Use reactive composition or isolate blocking I/O by design.

### Pitfall L — Calling `subscribe()` Manually and Using SecurityContext

This causes race conditions and lost context. Return publishers and let Spring Security manage the reactive flow.

### Pitfall M — Assuming Every 401 Means an Expired Token

A 401 can stem from signature, issuer, audience, time, token type, or JWKS failures. Do not infinitely refresh tokens.

### Pitfall N — Treating a Valid Scope as Access to Every Record

`orders.read` does not prove the caller owns order 42. Check tenant/ownership/ACL in the service.

### Pitfall O — Disabling Validation During Key Rotation Incidents

Operate AS JWKS rotation properly, refresh/cache keys, and keep old public keys for an appropriate window. Never disable verification or accept any `kid`.

### Pitfall P — Using `mockJwt()` as Proof of Signature Verification

Mock JWT only tests the authorization flow, not decoder cryptography. Test with real signed JWTs.

### Pitfall Q — Forgetting CORS on Browser Requests

An API with valid JWTs can still have responses blocked by the browser when the frontend is on a different origin. CORS must be configured separately and does not replace scopes/security.

## 30. Practical Scenario Matrix

| Scenario | Decoder | Validation/authorization | Expected outcome |
|---|---|---|---|
| Properly signed JWT, valid issuer/audience/time, has read scope | Success | GET order succeeds if object policy permits | Allowed |
| Properly signed JWT, missing read scope | Success | HTTP rule lacks `SCOPE_orders.read` | Usually 403 |
| Properly signed JWT, wrong audience | Cryptographic success | Audience validator fails | Usually 401 |
| JWT signed with unknown key | Signature verification fails | No Authentication created | Usually 401 |
| Expired JWT | Timestamp validator fails | No Authentication created | Usually 401 |
| JWT missing tenant when contract requires it | Custom validator fails | No Authentication created | Usually 401 |
| Valid token, order in another tenant | Decoder success | Object policy denies | 403/404 |
| New `kid`, JWKS updated | Decoder selects/fetches new key | Claims valid | Success |
| New `kid` during JWKS outage | No trusted key | Fail closed | Authentication error |
| Browser SPA sends Authorization from disallowed origin | Decoder may not run due to preflight | Browser CORS rejects | JS cannot read response |
| Opaque token sent to JWT decoder | Cannot parse/verify under JWT contract | Fail closed | Authentication error |
| Token with `alg=none` | Disallowed algorithm | Fail closed | Authentication error |
| ID token with web client audience | Signature may be valid | Audience/API profile rejects | Authentication error |

The table shows that **decoder success** is only one part of the final request outcome. CORS, the JWT claims contract, scopes, object permissions, and domain state each play a distinct role.

## 31. WebFlux JWT Resource Server Architecture Checklist

Before implementation, answer:

1. **Is the stack truly WebFlux?** Use `ServerHttpSecurity`, `SecurityWebFilterChain`, and `ReactiveJwtDecoder`.
2. **Who is the trusted issuer?** Is there one or multiple allowed issuers?
3. **Using issuer metadata or a JWK Set URL?** Are HTTPS, caching, and a key rotation plan in place?
4. **What are the permitted signing algorithms?** Is there an allowlist matching the issuer/key type?
5. **What is the API's audience?** Must the token contain `orders-api` or another resource identifier?
6. **What is the expiry/nbf/skew policy?** Are the right validators and clock synchronization in place?
7. **What is the token type/profile?** Are JWT access tokens distinguished from OIDC ID tokens?
8. **Which custom claims are required?** Are types/values validated rather than filled with defaults?
9. **Where are authorities mapped from?** Is there a `SCOPE_`, `ROLE_`, or custom `permissions` claim convention?
10. **Are method/URL rules specific?** Is there a deny-all fallback and avoidance of overly broad wildcards?
11. **Where is object-level policy enforced?** Are list/detail/update/export all bound by tenant/owner/ACL?
12. **Is reactive execution free of blocking?** Are there any `block()`, JDBC, or sync HTTP calls in the auth path?
13. **Are CORS/CSRF aligned with the actual browser client?** How does a Bearer SPA differ from a cookie BFF?
14. **How are JWKS outages/key rotations operated?** Are metrics/timeouts/caching planned?
15. **Are tests split into the right layers?** Are MockJwt HTTP tests separated from decoder signature tests?
16. **Are secrets/logs protected?** Are Authorization headers, tokens, and private keys kept out of logs?

These questions relate directly to architecture and should not be treated as merely a few lines of `application.yml` configuration.

## 32. References

- [Spring Security Reference — OAuth 2.0 Resource Server JWT (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): configuring WebFlux JWT, issuer/JWKS, key rotation, and authorities.
- [Spring Security API — ReactiveJwtDecoder](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/ReactiveJwtDecoder.html): reactive decode contract.
- [Spring Security API — NimbusReactiveJwtDecoder](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html): Nimbus implementation and builders.
- [Spring Security API — ReactiveJwtDecoders](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/ReactiveJwtDecoders.html): factories for building a decoder from an issuer.
- [Spring Security Reference — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `ServerHttpSecurity` and `SecurityWebFilterChain`.
- [Spring Security Reference — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): reactive authorization at the method/service level.
- [Spring Security Reference — Testing Reactive Security](https://docs.spring.io/spring-security/reference/reactive/test/index.html): `WebTestClient` and testing authentication/authorization.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): registered claims, compact JWT.
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517): JWK and JWK Set.
- [RFC 7515 — JSON Web Signature](https://www.rfc-editor.org/rfc/rfc7515): JWS, protected header, signature.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): trusted algorithms, cross-JWT confusion, and safe JWT processing.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access tokens for Resource Servers.
- [Project Reactor Reference](https://projectreactor.io/docs/core/release/reference/): `Mono`, `Flux`, reactive composition, and context.

**Conclusion:** `ReactiveJwtDecoder` is the contract for decoding and validating JWTs via Reactor `Mono<Jwt>` in **WebFlux**; `NimbusReactiveJwtDecoder` is the common implementation capable of using trusted issuer metadata, JWK Sets, and JWS verification. Secure configuration requires **trusted keys and algorithms**, **issuer–audience–timestamp** validators, authority mapping from trusted claims, along with HTTP and object-level authorization. Keep the security pipeline truly reactive, never call `block()` in the auth path, never use unverified JWT payloads, and never disable validation when JWKS encounters issues.
