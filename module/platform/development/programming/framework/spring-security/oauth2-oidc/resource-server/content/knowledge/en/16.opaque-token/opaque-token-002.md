# Token format does not dictate local vs. remote verification

When building a **Spring Security OAuth 2.0/OIDC Resource Server**, learners often encounter a shorthand explanation:

> "JWTs are verified locally by the Resource Server; opaque tokens must be sent to the Authorization Server for introspection."

Those are **two very common deployment patterns**, but **not a mandatory rule dictated by the token format**. A JWT can be verified via a remote introspection service; conversely, an opaque token can be verified or looked up right inside the Resource Server's own infrastructure if the system holds the necessary trusted information, keys, or state.

To understand this accurately, you need to separate **two independent questions**:

1. **What does the token look like, and can the recipient interpret its contents?** This is a question of **token format/representation**: JWT, random opaque string, encrypted token, or proprietary format.
2. **Where does the Resource Server obtain proof of validity?** This is a question of **verification architecture**: checking cryptographic signatures/keys or local state, calling remote introspection, or combining multiple sources.

Within the **Opaque token** chapter of the **Spring Security OAuth 2.0 OIDC Resource Server** module, this lesson analyzes four frequently confused combinations, how Spring Security implements them, security constraints, and how to choose an approach based on the contract between the Authorization Server and Resource Server.

> **Scope:** primarily **OAuth 2.0 access tokens** sent via `Authorization: Bearer ...`. An **OIDC ID token** serves identity authentication for the client and is not automatically an access token for an API. All URIs, tokens, and identifiers in the examples are synthetic data.

## 1. Two independent axes: format and verification method

### 1.1. What does token format answer?

| Token form | What can the recipient observe? | Does it prove by itself that the token is valid? |
|---|---|---|
| **JWS-format JWT** | Compact string with header, claims, and signature; payload is usually readable via Base64URL decoding | **No**. Signature, algorithm, key, and claims must be verified per policy |
| **Random opaque token** | A string with no semantics published to the Resource Server/client; usually a handle | **No**. Must be checked against a trusted source of truth or internal verification mechanism |
| **Self-contained but encrypted token** | May look opaque to any party lacking the decryption key | **No**. Requires the right key, integrity verification, claims validation, and expiration checks |
| **Proprietary-format token** | May be a structured string or carry a custom signature/MAC | **No**. Requires a securely designed verification algorithm and contract |

A JWT is not merely a string "with three dots": a JWT is a standardized token structure protected by appropriate JOSE mechanisms. A signed compact JWS JWT normally has **three parts**; an encrypted compact JWE JWT normally has **five parts**. You should never choose a verification path simply by counting dots in an untrusted string.

**Opaque** is a statement about **the interface toward the token consumer**: the client or Resource Server is not expected to extract token semantics by reading its contents. From that alone, you **cannot conclude** that the token must be verified remotely in every architecture.

### 1.2. What does verification method answer?

| Verification approach | Source of trust | Required elements |
|---|---|---|
| **Local cryptographic** | Trusted public/secret keys or verification material | Signature/MAC check, issuer, audience, timestamps, and policy |
| **Local state-based** | A token/session/authorization store trusted by and synchronized with the Resource Server | Handle lookup, active/revoked status, expiry, client/audience/scope |
| **Remote introspection** | Authorization Server or trusted token verification service | Secure channel, introspection caller credentials, handling `active` and attributes |
| **Hybrid** | Local check combined with revocation data/cache/remote service | Freshness policy, consistency, fallback precedence when upstream fails |

**Remote** can be OAuth 2.0 Token Introspection under RFC 7662 or a dedicated verification service in an internal architecture. **Local** can mean signature verification **or** looking up application-owned state; it does not mean only "decoding a JWT".

### 1.3. Matrix of four possibilities

| | **Local verification** | **Remote verification** |
|---|---|---|
| **JWT** | Resource Server uses `JwtDecoder`, trusted JWKs/keys, and validators to verify the JWT | Resource Server sends the raw JWT to the introspection endpoint if the Authorization Server **supports** introspecting that JWT type |
| **Opaque token** | Resource Server looks up the handle in an internal/replicated token store, or verifies a cryptographically protected opaque format it is designed to understand | Resource Server sends the opaque token to the introspection endpoint; this is common when the API does not know the token structure |

These cells represent **architectural feasibility**, not a claim that Spring Security supports all of them out of the box without configuration.

~~~mermaid
flowchart TD
    A["Client sends Bearer access token"] --> B{"Chosen verification contract?"}
    B -->|"Local crypto"| C["Trusted decoder/logic verifies signature or MAC"]
    B -->|"Local state"| D["Look up token handle in trusted store"]
    B -->|"Remote introspection"| E["Call Authorization Server"]
    C --> F["Check token policy: timestamps, iss, aud, required state"]
    D --> F
    E --> F
    F --> G{"Accepted?"}
    G -->|No| H["Reject authentication"]
    G -->|Yes| I["Authentication + GrantedAuthority"]
    I --> J["HTTP/method/domain authorization"]
~~~

**Foundational takeaway:** token format tells you *how the token can be parsed*; verification method is the decision of *which source has authority to declare the token valid*.

## 2. JWT: having structure does not force local verification

A JWS-signed JWT access token may consist of:

~~~text
BASE64URL(JOSE_HEADER).BASE64URL(CLAIMS).BASE64URL(SIGNATURE)
~~~

Illustrative JOSE header:

~~~json
{
  "alg": "RS256",
  "kid": "auth-key-2026-11",
  "typ": "at+jwt"
}
~~~

Illustrative claims:

~~~json
{
  "iss": "https://login.example.test/realms/company",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "client_id": "shop-web",
  "iat": 1924988400,
  "exp": 1924992000
}
~~~

This is not a genuinely signed token. `typ=at+jwt` is an example from a token profile such as RFC 9068; token type identification and required claims must match the Authorization Server's contract.

### 2.1. Common approach: locally verified JWT

The Resource Server:

1. Fetches public keys from a trusted JWK Set (potentially cached).
2. Selects **allowed** keys and signing algorithms, without blindly trusting `alg`, `kid`, or `jku` supplied inside the JWT.
3. Verifies the JWS signature.
4. Validates issuer, `exp`/`nbf` timestamps, API audience, token profile, and other required claims.
5. Converts the verified JWT into a principal/authorities and applies HTTP and business authorization.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant R as Resource Server
    participant K as Trusted JWK Set
    C->>R: Authorization: Bearer <JWT>
    R->>K: Fetch/refresh public keys when needed
    K-->>R: Trusted JWK Set
    R->>R: Verify JWS, iss, exp, nbf, aud...
    R->>R: Create Authentication + authorities
    R-->>C: Business response or error
~~~

Advantage: no need to call the Authorization Server **on every request** just to verify the signature once keys are available. Still, do not equate this with "local JWT = zero network dependencies": fetching/refreshing JWKS, issuer metadata, key rotation, or supplementary revocation checks may still require contacting other systems.

### 2.2. A JWT can absolutely be introspected remotely

If the Authorization Server supports OAuth 2.0 Token Introspection for JWT access tokens, the Resource Server can send the **entire JWT string** to the introspection endpoint. The Authorization Server evaluates the token against its policy and returns metadata in which `active` indicates acceptance as defined by the server.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant R as Orders Resource Server
    participant A as Authorization Server
    C->>R: Authorization: Bearer <JWT>
    R->>A: POST /introspect, token=<JWT> + caller authentication
    A->>A: Validate token and authorization state
    A-->>R: active=true, sub, scope, aud, exp...
    R->>R: Apply policy for Orders API
    R-->>C: API response
~~~

From Spring Security's perspective, if you configure `opaqueToken()`, **that processing path uses introspection**, even when the token string has the shape of a JWT. The DSL name **`opaqueToken` describes the chosen authentication strategy**, not a parser rule requiring "the token must contain no dots".

Prerequisites:

- The Authorization Server actually allows introspection of that JWT access token type.
- The Resource Server is authorized to call introspection and protects its client credentials.
- The introspection response includes enough metadata for the Resource Server to enforce audience, timestamps, client/tenant, and scopes.
- `active`, `exp`, and other metadata fields are handled per contract; never assume every introspection endpoint returns all claims from the JWT.

An Authorization Server may **not support** introspection for JWTs, or may allow only certain clients to introspect certain token types. Thus, you cannot conclude "any JWT can be introspected" merely from the JWT format.

### 2.3. Why do organizations choose introspection for JWTs?

| Reason | Meaning |
|---|---|
| Near-real-time revocation checks | The AS can know a token was invalidated even before `exp` arrives |
| Dynamic policy | The AS enforces current user/client/session state or updated security policies |
| Avoiding JOSE/JWK management across many Resource Servers | Centralizes token verification in a dedicated service |
| Centralized audit/observability | Every request is checked through the AS or verification service |
| Controlling returned metadata | The AS can return only the claims/attributes the introspection caller is permitted to receive |

The trade-off is **network latency, query cost, dependency on AS availability**, and the question of introspection caching when higher performance is needed.

### 2.4. Decoding a JWT payload is not JWT validation

Code that merely Base64URL-decodes the claims segment:

~~~java
// ANTI-PATTERN — reads payload only, does NOT verify signature.
String[] parts = token.split("\\.");
String json = new String(
    java.util.Base64.getUrlDecoder().decode(parts[1]),
    java.nio.charset.StandardCharsets.UTF_8
);
~~~

Never extract `scope`, `sub`, or `role` from unverified JSON to build an `Authentication`. If you want local verification, use a trusted decoder/JOSE library. If you want remote verification, use a trusted introspection endpoint and validate the response. **There is no "readable JWT means trustworthy" option.**

## 3. Opaque token: unreadable does not mean impossible to verify locally

An opaque access token may look like:

~~~text
Authorization: Bearer opaque_7WxbS4N5KrFvXyN9Tq...<redacted>
~~~

This is an **illustrative string**, not a real credential. To a Resource Server that does not know how to interpret it, the content is only a token handle. It cannot extract `sub` or `scope` directly via Base64URL decoding like a JWT with a public payload.

### 3.1. Common case: remotely looked-up opaque token

The Authorization Server issues a random string, stores associated state, and exposes an introspection endpoint:

~~~text
Token handle:   unpredictable random value
AS token store:
    handle / fingerprint → active, exp, sub, aud, scope, client_id...

Resource Server:
    receives handle
    → calls AS introspection
    → checks active + metadata
    → builds principal and authorities
~~~

This fits when the Resource Server does not own the token store and has no internal information to determine which tokens remain active.

### 3.2. An opaque token can be checked locally with a trusted data store

Suppose **the same platform operates both token issuance and the Resource Server**, or has a state store reliably replicated/synchronized to the Resource Server's infrastructure:

~~~text
Client token:
  256-bit random bearer handle

Local trusted token store:
  digest(handle) → {
      subject,
      audience,
      scopes,
      expiresAt,
      revoked,
      issuer,
      clientId
  }
~~~

The Resource Server receives the handle, computes a properly designed fingerprint, **looks up the local record**, and checks expiration, revocation state, allowed resources, and other conditions.

There is no HTTP introspection on every request here, yet **there is still a trusted source of truth**: the local/replicated token store. This is **state-based** local validation, not "decoding an opaque string to guess identity".

Critical safety conditions:

- The token must have sufficiently high entropy so it cannot be guessed or enumerated.
- The store must never accept a handle that was never issued.
- Lookup and matching must not leak the token in logs or errors.
- Metadata attached to the token must come from a trusted source, with TTL/expiry and revocation state.
- Across multiple Resource Servers, data must be distributed consistently per policy.
- A token sent to a different API must not be accepted just because the handle exists: audience/resource must be checked.
- When the store fails or verification data is missing, you must **fail closed**, never synthesizing a principal.

If the Resource Server **lacks** the corresponding data store/keys/verification algorithm, an isolated opaque random string **does not contain enough information for local verification**. In that case, introspection or a pre-designed state-sharing mechanism is required.

### 3.3. Opaque to the client, cryptographically structured to the issuer

Not every opaque token is a random database key. An issuer can mint a token with an **authenticated encrypted** payload, or a custom format carrying a MAC/signature, without publishing the structure to clients.

If the Resource Server holds the appropriate keys, algorithm, and contract, it can:

1. Verify the token's integrity/authenticity.
2. Decrypt the contents when needed and authorized.
3. Validate timestamps, issuer, audience, and token type.
4. Build the principal and authorities from the verified claims.

From the client's standpoint, the token remains **opaque**: the client simply forwards the value without needing to understand its contents. From an authorized Resource Server's standpoint, it can carry self-contained data verifiable locally.

**Do not assume Spring Security can decrypt every opaque/encrypted token by default.** A `JwtDecoder` handles JWTs according to the formats and algorithms its implementation supports; encrypted tokens such as JWE or proprietary formats may require dedicated decryption/verification components and must follow the cryptographic contract. Never invent a "base64 encryption" scheme and treat it as authentication.

### 3.4. "Local opaque token" does not mean skipping revocation and expiry

If a local token store only maps `handle → subject` without `active/revoked/exp/aud`, the Resource Server could keep accepting expired or revoked tokens, or accept tokens meant for another API.

A safe local token validator requires at least these policy checks:

~~~text
Handle exists in trusted source?
AND token is active, not revoked?
AND not expired and past not-before (if applicable)?
AND issued for the current Resource Server?
AND issuer/client/tenant/profile satisfy the contract?
    ↓
Only when all pass, create Authentication
~~~

For self-contained tokens verified locally via cryptography without a state lookup, **immediate revocation** state may be unknown; consider short lifetimes, a denylist, state synchronization, or supplementary introspection.

## 4. RFC 7662: introspection is a protocol, not a token format

OAuth 2.0 Token Introspection (**RFC 7662**) defines how an authorized party queries an Authorization Server about a token. The operation takes a **token string** and returns a JSON response containing `active`. The internal token format used by the Authorization Server is not what determines whether this protocol applies.

### 4.1. Introspection request

Example:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: login.example.test
Authorization: Basic <ENCODED_INTROSPECTION_CLIENT_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=<ACCESS_TOKEN>&token_type_hint=access_token
~~~

Note:

- `Authorization: Basic ...` here carries the **credentials of the Resource Server calling introspection**, not the user's Bearer JWT.
- The `token` parameter carries the credential being inspected; **never log this request body**.
- `token_type_hint` is only a **hint**, not proof of token type; the Authorization Server may ignore the hint per the spec.
- The introspection endpoint must use HTTPS and enforce access control so unauthorized clients cannot probe arbitrary token states.
- Client authentication mechanisms other than Basic may be used if the Authorization Server supports them and the contract configures them properly.

### 4.2. Response when the token is accepted

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "active": true,
  "scope": "orders.read",
  "client_id": "shop-web",
  "sub": "user-123",
  "token_type": "Bearer",
  "exp": 1924992000,
  "iat": 1924988400,
  "iss": "https://login.example.test/realms/company",
  "aud": "orders-api"
}
~~~

This metadata is illustrative. **RFC 7662 does not require every active response to contain all of the fields above**. An Authorization Server can choose which fields to return based on the token and the introspection caller's privileges. The Resource Server must know **which fields are mandatory under the API contract** and reject/deny access when required information is missing.

An `active=true` response generally indicates the Authorization Server considers the token valid/active by its criteria. Still, the Resource Server must determine whether the token is allowed for **this resource**, carries the needed scope, and has permission on the specific target resource. Never assume `active=true` means "allow calling every endpoint".

### 4.3. Response when the token is inactive

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "active": false
}
~~~

This is an **HTTP-level successful** introspection response stating that the token **is not accepted**. Distinguish carefully:

| Scenario | Conclusion |
|---|---|
| Introspection returns HTTP 200 and `active=true` | Token is active per AS; continue enforcing resource/scope policy |
| Introspection returns HTTP 200 and `active=false` | **Do not create a successful authentication** |
| Introspection returns HTTP 401/403 to the introspection caller | Resource Server may have wrong client credentials/permissions; do not automatically conclude the user token is bad |
| Introspection timeout, TLS error, or AS 5xx | **Cannot verify safely**; do not let the token pass |
| Response missing `active` or malformed | Treat as an invalid response under the protocol/contract |
| `active=true` but missing required audience | Insufficient proof to grant API access if the contract requires audience |

Do not classify every network error as "user intentionally sent an invalid token" in internal telemetry. Yet regardless of operational classification, **never allow a request through without a trusted authentication result**.

### 4.4. Introspection differs from UserInfo, token endpoint, and revocation

| Endpoint/protocol | Purpose |
|---|---|
| **Token endpoint** | Issues access tokens/refresh tokens under an OAuth grant |
| **Token introspection** | Queries the status and metadata of a token |
| **Token revocation** | Requests token revocation within what the AS supports |
| **OIDC UserInfo** | Provides user claims to an authorized OIDC client |
| **JWKS endpoint** | Publishes public keys so verifiers can check signatures/tokens |

Do not call UserInfo in place of token introspection; a UserInfo response is not general proof that an access token matches a Resource Server's audience, scope, and profile. Nor is JWKS a list of "active" tokens: JWKS only publishes public keys.

## 5. Spring Security names its configuration by authentication strategy

Spring Security OAuth 2.0 Resource Server commonly has two configuration branches:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()));
~~~

and:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2.opaqueToken(withDefaults()));
~~~

These two calls are not a check for "does the token look like a JWT?":

- **`jwt()`**: uses `JwtDecoder` to verify JWTs with the appropriate key source/JOSE/validators.
- **`opaqueToken()`**: uses `OpaqueTokenIntrospector` to validate tokens via an introspection strategy and build the principal/authorities. The token **can be a JWT** if the introspection endpoint accepts it.

Related type names:

| Concern | JWT branch | Opaque/introspection branch |
|---|---|---|
| Servlet provider | `JwtAuthenticationProvider` | `OpaqueTokenAuthenticationProvider` |
| Validation extension point | `JwtDecoder` | `OpaqueTokenIntrospector` |
| Typical principal | `Jwt` | `OAuth2AuthenticatedPrincipal` |
| Resulting Authentication | `JwtAuthenticationToken` | `BearerTokenAuthentication` |
| Data source | Verified JWT claims | Trusted introspection attributes |
| Expiration/issuer/audience | Validators on the decoder | AS/introspector policy and contract additions |
| Authorities from scope | Usually `SCOPE_*` | Usually `SCOPE_*` if introspection provides scope |

These names describe the common pipeline in modern Servlet Spring Security; exact claims/authorities mapping details can depend on version and custom converters/introspectors.

### 5.1. Common dependencies

Example Servlet/Spring MVC application:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

For the JWT branch using JOSE, libraries supporting JWT/JWS are needed; modern Spring Boot's Resource Server starter typically brings in the appropriate dependencies. If managing dependencies manually or using older versions, check `spring-security-oauth2-jose` and related dependencies for your version.

## 6. Case A: JWT access token verified locally with `JwtDecoder`

This is appropriate when the issuer mints signed JWTs under a known profile and the Resource Server can trust a corresponding JWK Set/public key.

### 6.1. Declaring the issuer

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/company
~~~

Spring Boot/Spring Security can build a decoder from the issuer when the application does not provide another decoder bean. The decoder verifies JWS and runs default claim validations for that version. For a dedicated API, **audience validation** for a resource ID such as `orders-api` is typically also needed; never assume declaring an issuer alone proves the token was meant for your API.

### 6.2. `SecurityFilterChain`

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class OrdersJwtSecurity {

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

A valid token with `scope=orders.read` is typically converted by Spring Security into `SCOPE_orders.read`. Authorization on individual orders (owner/tenant) still belongs in the service/domain layer. The example above only illustrates HTTP authentication/authorization and does not provide full controllers, an audience validator, or a specific product's CSRF/CORS policy.

### 6.3. When the exact JWKS URL is already known

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/company
          jwk-set-uri: https://login.example.test/realms/company/protocol/openid-connect/certs
~~~

Where supported by the framework/version, the Resource Server can use the known JWKS URL instead of discovering it via metadata at startup, while still keeping issuer validation against the configured issuer. However, it **may still need the network** when fetching/refreshing keys.

Do not confuse:

~~~text
Local JWT verification ≠ no network ever
Local JWT verification ≠ immediate revocation knowledge
Local JWT verification ≠ automatic audience authorization
~~~

### 6.4. Building a custom decoder and keeping required validators

An example selecting a JWS algorithm and audience:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class LocalJwtDecoderConfiguration {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.issuer}") String issuer,
            @Value("${app.security.jwks-uri}") String jwksUri,
            @Value("${app.security.audience}") String audience) {

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwksUri)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> expectedAudience = jwt ->
            jwt.getAudience().contains(audience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "JWT audience is not accepted",
                        null
                    )
                );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                expectedAudience
            )
        );
        return decoder;
    }
}
~~~

This example uses application properties `app.security.*` (which must be declared explicitly), not magic Spring Boot properties. `setJwtValidator(...)` **replaces the validator** on the decoder, so explicitly compose `JwtValidators.createDefaultWithIssuer(...)` so you do not lose default issuer and timestamp checks. Other mandatory profile constraints (such as token type or requiring `exp` to be present) must be added when the contract requires them.

This is an example of **JWT verification at the Resource Server**. There is no per-request introspection once the decoder holds trusted key material.

## 7. Case B: JWT access token verified via introspection

Token shape **does not force** Spring Security to use `jwt()`. If the AS supports introspection for JWTs, you can configure the opaque-token/introspection branch.

### 7.1. Configuring the introspection endpoint

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.test/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

Values from environment variables in the example illustrate **not hardcoding client secrets** in source code. In production, use a secret manager and appropriate rotation/permission policies. The URL must be the introspection endpoint published by the AS over a trusted TLS channel; never read the URI from an unverified token.

### 7.2. HTTP security calling `opaqueToken()`

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class OrdersIntrospectionSecurity {

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(withDefaults()))
            .build();
    }
}
~~~

**If a client sends a JWT instead of an opaque random string**, the Resource Server still passes the **entire raw string** to the introspection strategy. It does not automatically switch to `JwtDecoder` just because it sees three Base64URL parts. Whether authentication succeeds depends on **the AS introspection actually recognizing the JWT**, client credentials, `active`, and any additional policies applied.

Do not place both `OrdersJwtSecurity` from section 6 and `OrdersIntrospectionSecurity` with unrestricted matchers in the same application without designing chain ordering/matchers; they are **two alternative configuration options** for the same API.

### 7.3. Principal when using introspection

On the introspection path, the principal is typically an `OAuth2AuthenticatedPrincipal` holding attributes from the introspection result; `BearerTokenAuthentication` holds the principal/authorities.

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class IntrospectedIdentityController {

    @GetMapping("/api/me")
    MeResponse me(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
        // Use only attributes permitted by the contract and already validated.
        return new MeResponse(principal.getName());
    }
}

record MeResponse(String displayName) {}
~~~

This illustrates a protected endpoint, not a recommendation to expose raw `principal.getName()` in every API: the name could be `sub` or sensitive information, so a deliberate response policy is needed. **Never return `principal.getAttributes()` or `BearerTokenAuthentication` directly** because introspection can carry sensitive data and token/credentials.

### 7.4. Trade-offs when JWTs are also introspected

| Characteristic | Local JWT | JWT via introspection |
|---|---|---|
| Where is the signature verified? | Resource Server/decoder | Typically handled by the AS or trusted introspection service |
| Call AS on every request? | Not necessarily once JWKs are available | Usually yes, unless caching is designed |
| Revocation before `exp` | Requires supplementary revocation data | AS can reflect `active=false` once revocation is processed |
| Direct JWT claims | Resource Server reads after verification | Resource Server receives introspection metadata; not guaranteed to include every claim |
| Runtime network dependency | Lower for verification once keys are cached | Higher if introspection is uncached |
| Managing JWK rotation per API | Must be handled via decoder/JWKS | Can be centralized at the AS/introspection service |
| Scope/role mapping | JWT claims → authorities | Introspection attributes → authorities |
| Outbound channel security | JWKS endpoint, trust/TLS | Introspection request carries token + client auth, must be carefully protected |

**Warning:** Using introspection **does not automatically guarantee instantaneous revocation**. An AS may have state synchronization lag; if the Resource Server caches `active=true` responses, it can continue accepting a token during the cache window even after the AS revoked it.

## 8. Case C: opaque random token verified via introspection

This model corresponds directly to common opaque-token Resource Server examples.

### 8.1. Overview

~~~mermaid
sequenceDiagram
    participant C as Client
    participant R as Orders Resource Server
    participant A as Authorization Server
    C->>R: GET /api/orders/42 + Bearer opaque handle
    R->>A: POST /introspect (token, client authentication)
    A->>A: Look up token, active/expired/revoked, policy
    A-->>R: active=true, scope=orders.read, sub, aud...
    R->>R: Check required metadata + build authorities
    R-->>C: Business response if authorized
~~~

The Resource Server does not need to understand the token's internal structure, but must trust that **the Authorization Server verified issuance and token status**. Upon receiving `active=false`, the request must be rejected at authentication.

### 8.2. Scope authorization after introspection

If the introspection response gives:

~~~json
{
  "active": true,
  "scope": "orders.read",
  "sub": "user-123",
  "aud": "orders-api",
  "exp": 1924992000
}
~~~

Spring Security opaque-token support typically maps `scope` to authorities shaped like:

~~~text
SCOPE_orders.read
~~~

Then `hasAuthority("SCOPE_orders.read")` can be enforced on the read endpoint. Still, **`active=true` only indicates validity**; permission to read a specific order must also be checked against user/tenant/domain rules.

### 8.3. The introspection server does not necessarily return issuer/audience

RFC 7662 defines standard metadata, but does not mandate that responses include every field in all situations. If the Orders API needs `aud=orders-api`, you should:

1. Agree with the AS that introspection responses for this caller include a trustworthy audience, **or** have the AS enforce specific resource binding when evaluating `active`.
2. Configure the introspector/authorization layer to check audience against the response contract.
3. **Reject when there is insufficient proof** that the token is intended for the Orders API.

Never adopt the habit of "introspection returned active so skip the audience check" if the Authorization Server only verifies that the token is alive without restricting the target resource.

### 8.4. Client authentication is not the user's access token

In remote introspection there are two independent credentials:

~~~text
Bearer access token from client → Resource Server

Resource Server credentials → Authorization Server introspection
~~~

They have different owners, permissions, and lifecycles. Never forward the introspection client secret back to an API client, and never log introspection requests containing both Basic credentials and the token under inspection.

## 9. Case D: opaque token verified locally via a state store

Architectural example for a platform **that controls token issuance** or is authorized to use an internal token store:

~~~mermaid
flowchart LR
    AS["Authorization Server"] -->|"Generate random handle + write record"| DB["Trusted token store"]
    AS -->|"Return token to client"| C["Client"]
    C -->|"Bearer opaque token"| R["Resource Server"]
    R -->|"Lookup digest(handle)"| DB
    DB -->|"issuer, aud, sub, scopes, exp, revoked"| R
    R --> V["Local validation and authorization"]
~~~

**There is no network request to the AS introspection endpoint per call** when the Resource Server has trusted lookup data locally. Yet there is still a data dependency: a local database, in-memory store, shared cache, or state replica.

### 9.1. Structure of a token record

An internal record might contain:

~~~text
tokenDigest        = digest of the random opaque handle (do not store raw token)
subject            = user-123
issuer             = https://login.example.test/realms/company
audience           = orders-api
clientId           = shop-web
scopes             = [orders.read]
issuedAt           = ...
expiresAt          = ...
revoked            = false
~~~

**Do not mistake this for the token format sent to the client**. The client only holds the random handle; the record and claims reside in the server's trusted store.

### 9.2. Local conditions for an active token

~~~text
1. Token handle must have sufficient entropy, unguessable.
2. Digest/lookup must find a record from the trusted store.
3. Record is not marked revoked or disabled.
4. expiresAt must be after the current time per clock policy.
5. Token must match issuer/client/audience per contract.
6. Scope/permissions are mapped to authorities in a controlled manner.
7. Request must still pass HTTP/method/domain authorization.
~~~

With a replicated state store, you must account for **revocation synchronization lag**. A record already revoked in the issuing system but not yet propagated to a local cache could still be accepted; local lookup does not solve freshness by itself.

### 9.3. When should you NOT build local opaque validation yourself?

- The Authorization Server is an external provider that does not give the Resource Server access to token issuance/state.
- There is no maintained schema or contract for token records.
- You cannot guarantee token entropy, signing/encryption, expiry, or revocation consistency.
- Multiple APIs share tokens without a safe state-synchronization mechanism.
- Dynamic session/tenant policies known only to the AS must be checked.
- Building local validation would cause the API to trust tokens that the AS no longer accepts.

In these scenarios, **remote introspection** or a trusted token-checking service is usually far more governable. **Never try to decode an opaque string** by guessing or trusting self-declared fields in the request.

### 9.4. The `OpaqueTokenIntrospector` extension point for a local store

Spring Security lets an application supply its own `OpaqueTokenIntrospector`. It receives the token string and must return an `OAuth2AuthenticatedPrincipal` **only when the token has been properly verified**.

An illustrative structure for an application with an internal token store:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.OAuth2IntrospectionException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

@Configuration
class LocalOpaqueTokenConfiguration {

    @Bean
    OpaqueTokenIntrospector localOpaqueTokenIntrospector(
            TrustedTokenRepository repository,
            TokenFingerprint fingerprint,
            Clock clock) {

        return token -> {
            if (token == null || token.isBlank()) {
                throw new OAuth2IntrospectionException("Invalid token");
            }

            // Compute a safe digest/fingerprint; NEVER log the raw token.
            String digest = fingerprint.of(token);
            StoredToken record = repository.findByDigest(digest)
                .orElseThrow(() ->
                    new OAuth2IntrospectionException("Token not active"));

            if (record.revoked()
                    || !record.expiresAt().isAfter(clock.instant())
                    || !"orders-api".equals(record.audience())
                    || !"https://login.example.test/realms/company"
                        .equals(record.issuer())) {
                throw new OAuth2IntrospectionException("Token not active");
            }

            List<GrantedAuthority> authorities = new ArrayList<>();
            for (String scope : record.scopes()) {
                authorities.add(
                    new SimpleGrantedAuthority("SCOPE_" + scope));
            }

            Map<String, Object> attributes = new HashMap<>();
            attributes.put("sub", record.subject());
            attributes.put("iss", record.issuer());
            attributes.put("aud", record.audience());
            attributes.put("client_id", record.clientId());
            attributes.put("scope", String.join(" ", record.scopes()));
            attributes.put("exp", record.expiresAt().getEpochSecond());

            return new DefaultOAuth2AuthenticatedPrincipal(
                record.subject(),
                attributes,
                authorities
            );
        };
    }

    interface TrustedTokenRepository {
        Optional<StoredToken> findByDigest(String digest);
    }

    interface TokenFingerprint {
        String of(String token);
    }

    record StoredToken(
        String subject,
        String issuer,
        String audience,
        String clientId,
        Instant expiresAt,
        boolean revoked,
        Set<String> scopes
    ) {}
}
~~~

**Limitations and conditions of this example:**

- `TrustedTokenRepository` and `TokenFingerprint` are illustrative interfaces only; running an application requires concrete implementations, a trusted data source, secret management, issuance/revocation flows, and an appropriate synchronization mechanism.
- The store assumes **high-entropy random token handles** and stores fingerprints/digests rather than raw tokens. Choosing SHA-256/HMAC or another scheme depends on your threat model and token storage policy; never use weak hashes or guessable tokens.
- `Clock` must be provided by application/test infrastructure; use a consistent clock and design skew limits per contract.
- Exceptions for invalid tokens must map properly to **Bearer authentication failures** in your version of Spring Security. The example uses `OAuth2IntrospectionException` to illustrate **never returning a principal for an invalid token**, while exact error categorization and exception types must match the active provider.
- If the store tracks `notBefore`, tenant, token type, disabled user, client binding, or other policies, validate all of those rather than only the fields shown in the sample.
- Only use a local store when the Resource Server **genuinely has authority** to trust that data. This is not a way to "replace introspection" for opaque tokens from a third-party IdP without a contract.
- Never place raw token information or sensitive records into responses or logs.

### 9.5. `SecurityFilterChain` keeps the `opaqueToken()` configuration

If an `OpaqueTokenIntrospector` bean like the one above is used by Spring Security, the HTTP DSL can still remain:

~~~java
http.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(withDefaults())
);
~~~

In this example, the **opaque token** branch does not necessarily call an **HTTP introspection endpoint** because `OpaqueTokenIntrospector` is an internal implementation supplied by the application. That is direct proof that **the DSL branch name does not mean remote verification**.

When an application both declares Spring Boot introspection properties and provides a custom bean, make sure you control exactly which decoder/introspector the chain uses; never assume properties are automatically merged into a custom implementation.

## 10. Can an opaque token be verified locally using cryptography?

Yes, if **the token format and security infrastructure are designed for it**. For example, a token that clients view simply as an uninterpretable string, while the issuer protects its contents with authenticated encryption. A Resource Server holding the keys and software matching that token profile can verify and extract claims locally.

However, distinguish carefully:

1. **Opaque random handle**: has no structure sufficient for cryptographic verification inside the string; requires a trusted token store/lookup.
2. **Encrypted/self-contained token**: contents can carry claims verified by algorithm, key, expiry, and issuer policy; a verifier can decrypt/check them when provisioned with the right keys.
3. **Signed but non-JWT proprietary token**: can be verified locally if the contract and secure signature/MAC are properly implemented.

### 10.1. Never invent a "secret token" using Base64

Logic like:

~~~text
token = Base64(userId + ":" + expiresAt + ":" + role)
~~~

does not produce a trustworthy credential: clients can decode and modify the role/expiry without cryptographic integrity protection. If self-contained tokens are required, use maintained standards and security libraries with clear key management, encryption/signature, token type, and audience.

### 10.2. Confidentiality and authenticity are two separate questions

An encrypted token can **hide contents from observers** if encryption is done properly, yet the Resource Server must still check whether the token was issued by a trusted issuer, has not expired, and is meant for this API. A signed token can **prove integrity/authenticity** without hiding the payload from the client at all.

Do not equate:

~~~text
Readable token    ≠ untrusted token
Unreadable token  ≠ trusted token
Encrypted token   ≠ automatically active/revocation-aware
Signed token      ≠ automatically confidential
~~~

### 10.3. A JWE-format JWT is not an ordinary JWS `NimbusJwtDecoder`

A JWT can be represented as an encrypted JWE. If a client/Resource Server uses a JWE token profile, appropriate decryption and verification components are required. **Do not assume `NimbusJwtDecoder.withJwkSetUri(...)` examples for verifying JWS-signed JWTs will automatically decrypt every JWE**.

Therefore, "opaque to the client" and "JWT inside" can both be true at once, but **a clear technical contract is required**, rather than guessing from the number of token segments.

## 11. Introspection can distribute revocation state, but it is not magic

A frequently cited benefit of choosing introspection is detecting tokens revoked before `exp`. It is important to distinguish between **knowing a token has not expired** and **knowing the AS still accepts the token**.

### 11.1. What does local JWT signature validation usually know?

If a JWT is self-contained and the Resource Server checks only:

~~~text
JWS signature valid
AND trusted issuer
AND exp/nbf valid
AND audience valid
AND profile/claims valid
~~~

then it knows the token satisfies **the evidence represented in the JWT and key configuration**. It may **not know** whether the AS just locked the user, revoked the client, terminated the session, or revoked the token after issuance.

If fast revocation is needed, architectural options include:

- Short JWT TTLs to limit the exposure window.
- A synchronized local denylist/allowlist or state lookup by `jti`/issuer/subject.
- Remote introspection or a policy service per request.
- A reliable push/revocation event mechanism to update state in near real time.

Each option has different operational costs and consistency guarantees. The JWT format **does not forbid** adding local or remote revocation lookups.

### 11.2. What does remote introspection know?

An introspection endpoint can return `active=false` when:

- The token is expired or not yet valid.
- The token has been revoked.
- The authorization grant/client/session is no longer accepted by the AS.
- The requesting Resource Server is not permitted to introspect the token.
- Another issuer policy renders the token inactive.

Specific reasons depend on the AS; **never guess the reason** solely from `active=false`. If the AS returns false, the Resource Server must reject the token. If operational root causes are needed, use the AS's separate audit/admin channels with proper authorization rather than exposing internals to clients.

### 11.3. Caching introspection responses changes freshness

Suppose:

~~~text
10:00:00 AS returns active=true
10:00:01 Resource Server caches result for 60 seconds
10:00:10 AS revokes token
10:00:20 Resource Server uses cached active=true
10:01:01 cache expires and re-checks
~~~

Without cache invalidation, a revoked token can continue to be accepted during the 60-second window. Thus, you cannot claim "using introspection gives instant revocation" when the application enables caching.

An appropriate TTL must consider:

~~~text
cacheTTL <= acceptable stale revocation window per risk policy

cacheExpiresAt <= token.expiresAt (when present and trusted)
~~~

These inequalities describe **design goals**, not an automatic property of every Spring Security version. For tokens without `exp` in the introspection response, never choose an "indefinite" cache simply because metadata is missing.

### 11.4. A local opaque store also has a consistency window

A replicated local store can receive revocation updates with delay:

~~~text
AS token store: revoked=true
Local RS cache: revoked=false
~~~

This is the exact same **freshness** problem; only the data distribution mechanism differs. The decision is not about JWT vs. opaque, but about the **state synchronization model**.

### 11.5. Signing key compromise and revocation

If a JWT private signing key is compromised, continuing to trust the old public key allows an attacker to forge tokens with valid signatures. Remote introspection can rely on a database/issuance registry to reject unissued tokens, **if** the AS checks that registry and is designed accordingly. Never assume introspection automatically checks an issuance registry for all JWTs; some AS implementations may only verify signatures and claims.

Conversely, an internal opaque random token store does not depend on JWKS rotation the way JWS JWTs do, but depends on protecting the handle/token database and state update permissions. Each architecture has its own trust boundaries.

## 12. Latency, availability, and scalability

Choosing local vs. remote directly affects system behavior when the Authorization Server or network fails.

| Property | Local JWT/JWS | Remote introspection | Local opaque store |
|---|---|---|---|
| Per-request verification | Crypto + validators at RS | HTTP request/response or cache | State/digest lookup at RS/store |
| Per-request AS dependency | Usually none after keys are obtained | Usually yes unless cached | Not directly if store is replicated |
| Latency concerns | Signature verification cost, JWK refresh | Network, AS processing, TLS, retries | Local DB/cache/read latency |
| Horizontal scaling | Easy given keys/policy | AS must handle total request volume | Store/replication must scale |
| Early revocation | Requires additional state | Possible via `active` | Possible if store updates quickly |
| Handling AS outage | Can continue verifying with still-trusted keys | May be unable to verify new/introspected tokens | Depends on store/replication health |
| Secret protection | Public JWKS/issuer trust; signing keys stay on AS | Client credentials + token on outbound channel | Token store and secret/hash policy |
| Cache staleness | Stale JWKS/revocation | Stale `active` response | Stale token state |

### 12.1. Fail closed when evidence is insufficient

If the introspection endpoint is unreachable and the Resource Server **has no sufficiently trusted verification result**, it must not accept tokens just to avoid downtime. Likewise, a disconnected local opaque store or a JWT decoder lacking a trusted verification key must never fabricate a "temporary" principal.

Not every infrastructure failure has to return HTTP 401 like an invalid token. A system can distinguish invalid authentication from temporary service errors in responses/telemetry according to its architecture, yet **must never allow an unverified request into protected business logic**.

### 12.2. Do not retry introspection indefinitely

If the AS is slow or experiencing an outage, unbounded retries can amplify load, exhaust thread/connection pools, and trigger cascading failures. You need timeout policies, bounded retries, circuit breakers/bulkheads where appropriate, observability separating `active=false` from HTTP 5xx, and capacity planning.

### 12.3. Caching must be tied to security, not just performance

When caching introspection results or a local token store:

- Never log raw tokens or use raw tokens as metric labels.
- If using tokens as cache keys, protect the cache from credential exposure; consider properly designed fingerprints and high token entropy.
- Partition caches by issuer/client/audience when required by contract; a token string alone may not disambiguate context across multiple tenants/AS instances.
- Never cache `active=true` results beyond token expiration.
- Set TTLs according to revocation freshness/SLA/risk policy, not arbitrary numbers.
- Define invalidation for when a token, client, or session is revoked.
- Never turn an outage into a "cache active forever" policy.

## 13. Audience, issuer, and scope must hold across all four models

Regardless of token format, the Resource Server still needs to know **who issued the token, who it is intended for, and what it allows**.

### 13.1. Local JWT

Typically checks:

~~~text
Trusted JWS key / allowed alg
AND iss = trusted issuer
AND aud contains orders-api
AND exp/nbf valid
AND required token profile claims
~~~

Then `scope`/`scp` is mapped to authorities, and endpoint rules decide which request requires which authority.

### 13.2. JWT or opaque via introspection

The Resource Server receives an **AS assertion** over HTTPS regarding `active` and metadata. If the AS returns:

~~~json
{
  "active": true,
  "aud": "billing-api",
  "scope": "orders.read",
  "sub": "user-123"
}
~~~

The Orders API **should not accept** the token just because the scope matches orders-reading permissions. The audience is `billing-api`; this token is intended for another resource. If the AS does not include audience in introspection, the Resource Server must have another trusted policy confirming resource binding, or reject for lack of evidence under the contract.

### 13.3. Local opaque store

Internal records must be clearly bound to issuer/client/audience/scope. A handle existing in a DB does not mean every API sharing that DB may trust the token. In microservice architectures, enforce access controls on the token store and distinguish resource audiences.

### 13.4. Role and scope are separate layers

Spring Security typically uses authorities:

~~~text
scope: "orders.read" → SCOPE_orders.read
role: "ADMIN"       → ROLE_ADMIN (if mapped appropriately)
~~~

`JwtAuthenticationConverter` or a custom introspector defines how authorities are built. `authorizeHttpRequests`/`@PreAuthorize` consume authorities to enforce policy. **Role/scope data is only trustworthy after the token is authenticated**, never simply because a claim appears in the string.

## 14. Spring Security does not choose the verification method by token shape

A common architectural flaw when an application wants to "accept both JWT and opaque":

~~~java
// ANTI-PATTERN: do not use untrusted token shape as trust policy.
if (token.split("\\.").length == 3) {
    return validateLikeJwt(token);
}
return introspectOpaque(token);
~~~

Problems:

1. The token string is **client-supplied input**; formatting can be forged or contain arbitrary dots.
2. JWTs can be encrypted or formatted differently—not every JWT is a three-part compact JWS.
3. An AS can issue opaque tokens containing dots, or JWT tokens that the Resource Server is required to introspect.
4. Falling back from a failed validation to a looser mechanism can create a **downgrade/bypass**.
5. Two providers can have different issuers, audiences, keys, and scopes; switching by shape easily produces inconsistent policies.

### 14.1. If multiple access token types must be supported

Define **an explicit contract**:

- Which gateway/endpoint or security chain accepts which token type?
- Which issuer mints each token type, and for which audience?
- Which trust/validation source does each Resource Server recognize?
- If a resolver exists, what evidence is allowed for routing before the token is verified?
- How do you guarantee it **never falls back to a weaker mechanism** when validation for the expected mechanism fails?
- How are distinct token profiles/algs/issuers/clients constrained?

In Spring Security, you can configure multiple `SecurityFilterChain` beans using `securityMatcher`, `@Order`, and respective `jwt()`/`opaqueToken()` strategies scoped by HTTP path. If the same endpoint must accept multiple token types, an `AuthenticationManagerResolver<HttpServletRequest>` or custom provider/decoder strategy may be needed, yet **routing and verification must be driven by trust design**, not merely a regex over the token.

### 14.2. Two chains illustrating per-endpoint policy, not per-token guessing

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class TwoApiValidationStrategies {

    @Bean
    @Order(1)
    SecurityFilterChain internalJwtApi(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/internal-api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().hasAuthority("SCOPE_internal.read")
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(withDefaults()))
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain partnerIntrospectionApi(
            HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/partner-api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().hasAuthority("SCOPE_partner.read")
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(withDefaults()))
            .build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain fallback(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().denyAll()
            )
            .build();
    }
}
~~~

This is a **conceptual configuration example**: to run it, you must provide proper `JwtDecoder` and `OpaqueTokenIntrospector` beans/properties, authorization profiles, and HTTP policies. The first two chains choose strategies by **URL scope**, rather than guessing from bearer token shape. The last chain closes off uncovered URLs. If CORS, CSRF, sessions, or other authentication mechanisms exist, configure them per product requirements.

In particular, `anyRequest().denyAll()` inside a chain only applies **within the matched chain**; the fallback chain in the example prevents routes outside the two API groups from being left unprotected by Spring Security.

## 15. Spring WebFlux: same principles, different interfaces

With **Spring WebFlux**, the Resource Server processes requests in a reactive pipeline. The API differences do not change the thesis: JWTs can be verified locally or via introspection; opaque tokens can be checked via a remote service or via securely built internal state/logic.

### 15.1. Corresponding interfaces

| Responsibility | Servlet / Spring MVC | Spring WebFlux |
|---|---|---|
| HTTP security | `HttpSecurity` | `ServerHttpSecurity` |
| Security chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Local JWT verification | `JwtDecoder` | `ReactiveJwtDecoder` |
| Nimbus JWT decoder | `NimbusJwtDecoder` | `NimbusReactiveJwtDecoder` |
| Opaque/introspection | `OpaqueTokenIntrospector` | `ReactiveOpaqueTokenIntrospector` |
| Introspection result | `OAuth2AuthenticatedPrincipal` | `Mono<OAuth2AuthenticatedPrincipal>` |
| Security context | `SecurityContextHolder` | `ReactiveSecurityContextHolder` |
| HTTP rules | `authorizeHttpRequests(...)` | `authorizeExchange(...)` |

Example dependencies:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

### 15.2. Reactive JWT verification

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class ReactiveJwtApiSecurity {

    @Bean
    SecurityWebFilterChain api(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

When the application has a `ReactiveJwtDecoder` from trusted configuration, tokens are verified by that decoder before authorities are applied. If the token profile demands a specific audience or claims, configure the appropriate validator; never infer that a token was issued for the API solely because its signature is valid.

### 15.3. Reactive introspection: JWT or opaque handle

You can likewise use:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class ReactiveIntrospectionApiSecurity {

    @Bean
    SecurityWebFilterChain api(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(withDefaults()))
            .build();
    }
}
~~~

With a `ReactiveOpaqueTokenIntrospector` from Spring Boot configuration or a custom bean, this pipeline verifies tokens according to the configured introspection strategy and **does not switch automatically to a JWT decoder** just because a token looks like a JWT. These two security config classes are **two alternatives**, not two global beans with identical matchers to be used regardless of order.

### 15.4. Local opaque on WebFlux

A custom `ReactiveOpaqueTokenIntrospector` can query a reactive token store:

~~~text
Bearer token
   |
   v
ReactiveOpaqueTokenIntrospector.introspect(token)
   |
   v
Mono<TrustedTokenRecord> from reactive repository/cache
   |
   v
validate active / exp / issuer / audience / scope
   |
   v
Mono<OAuth2AuthenticatedPrincipal>
~~~

This is an **architectural pattern**, not a built-in Spring Security API for accessing any arbitrary local token store. The application must provide the data source and verification code itself. Avoid calling blocking JDBC or synchronous HTTP clients directly on the Reactor event loop. If a blocking library is unavoidable, use a properly bounded and evaluated scheduling mechanism; prefer reactive repositories/clients whenever the architecture allows.

### 15.5. Opaque does not mean returning empty metadata

The result of a reactive or Servlet introspector can contain attributes for `sub`, `scope`, `client_id`, and `aud`. That gives controllers/services a principal and authorities for policy enforcement. The difference from local JWT is the **source of trusted data**: the introspection response or local record, not JWT claims verified by a decoder.

## 16. An architectural migration scenario: local JWT → JWT introspection

A system initially uses local JWTs to handle high request volume:

~~~text
2026, phase 1:
  Authorization Server issues RS256 JWTs
  Resource Server uses issuer-uri + JWKS
  Token TTL = 15 minutes
  Local JWT signature/claim validation
~~~

Later, the organization needs to revoke access faster in situations such as account lockouts or grant revocation. One option is to **keep JWT access tokens** while migrating the Resource Server to introspection:

~~~text
Phase 2:
  Authorization Server still issues RS256 JWTs
  Authorization Server supports RFC 7662 for JWTs
  Resource Server uses opaqueToken() + introspection-uri
  active=false reflects revocation per AS policy
~~~

Tokens **do not have to change from JWT to random opaque strings** in order to use introspection. What must change is **how the Resource Server obtains proof of token status**.

### 16.1. Checks when migrating

1. Confirm the AS actually introspects JWTs issued for the API, with the right client auth and permissions.
2. Confirm the introspection response includes sufficient `scope`, subject, audience, expiry, and token type per contract.
3. Evaluate throughput/latency: previously the Resource Server only verified signatures locally, whereas now it requires an HTTP call or cache lookup.
4. Choose timeouts, retries, and behavior when the AS loses connectivity; never accept unverified tokens.
5. Set cache TTL according to revocation freshness requirements if caching is enabled.
6. Protect the client secret and access token in HTTP client request/response logs.
7. Verify whether authorities produced by introspection match or intentionally differ from the JWT converter.
8. Do not conflate `active=false` with every client-side 401; many errors can stem from network or client credentials.

### 16.2. A change that can alter the principal type

Before migrating:

~~~text
JWT path:
  Authentication = JwtAuthenticationToken
  principal = Jwt
~~~

After migrating:

~~~text
Introspection path:
  Authentication = BearerTokenAuthentication
  principal = OAuth2AuthenticatedPrincipal
~~~

A controller declaring `@AuthenticationPrincipal Jwt jwt` will likely need to change how it accesses attributes; do not expect introspection to reconstruct a `Jwt` object merely because the raw token happened to be a JWT.

If the API wants consistent identity access across multiple strategies, introduce an **internal identity adapter layer** that accepts `Authentication` and builds a custom domain principal containing only permitted fields. Never serialize the framework principal straight to JSON.

## 17. Another migration scenario: remote opaque → local opaque

Suppose a platform issues random opaque access tokens and every microservice introspects via the Authorization Server:

~~~text
Phase 1:
    Resource Servers --HTTPS--> Central introspection endpoint
                                    |
                                    v
                                Token store
~~~

Because throughput is high and services sit within the same trust boundary, the organization considers distributing a trusted token-state cache to each Resource Server cluster:

~~~text
Phase 2:
    Authorization Server → token issuance/revocation events
                                  |
                                  v
                      Trusted replicated token state
                                  |
                                  v
                      Resource Servers local lookup
~~~

The opaque string stays **unchanged**. The Resource Server does not learn how to decode JWTs; it **switches its verification source from an HTTP call to a trusted data replica**.

### 17.1. Conditions for a safe replacement

| Requirement | Why it matters |
|---|---|
| AS owns and provides the authoritative data source | Prevents APIs from accepting forged tokens |
| Token handles have sufficient entropy | Prevents brute-forcing/guessing tokens |
| State includes expiry and revocation | Prevents accepting expired/revoked tokens |
| Reliable, ordered event delivery | Reduces stale state windows |
| Reconnect/reconcile mechanism after outages | Prevents accepting stale caches indefinitely |
| Issuer/audience distinction | Prevents accepting tokens for the wrong resource |
| Access/tenant controls protecting the store | Prevents unauthorized services from reading/modifying token state |
| Audits exclude raw tokens | Protects credentials in observability systems |

If these conditions cannot be met, local lookup can undermine the AS's safety guarantees. In that case, scaling AS capacity or controlled introspection caching may be a better alternative.

### 17.2. Risk of copying a token store into a "permanent cache"

A state replica that stays online without receiving new revocation events becomes a **stale data source**. When the AS deletes a token, a client loses permissions, or client consent changes, the Resource Server could still see the old record and allow access.

Therefore, local state requires:

- A **hard TTL** never exceeding token expiry.
- A **staleness bound**: an upper limit on acceptable synchronization lag.
- Detection for lagging consumers, dropped events, or untrustworthy snapshots.
- A mechanism to refresh a full snapshot or fall back to introspection per policy when state is insufficient.
- Fail-closed rules when data exceeds its trust age or provenance cannot be verified.

These are the operational costs of a local-state validation strategy, independent of whether the token is a dotless string.

## 18. Format-independent security rules

Below are requirements that apply regardless of whether tokens are JWT or opaque, verified locally or remotely.

### 18.1. Protect the bearer credential

A raw access token is a credential. Never:

- Write tokens to logs, metrics, traces, exception messages, or URL query strings.
- Return tokens in business API JSON responses.
- Push tokens onto unauthorized message queues/event buses.
- Use tokens as correlation IDs.
- Store tokens in unprotected browser/local environments.
- Copy real tokens into test fixtures or tickets.

In remote introspection, client credentials and the `token` in the form body must also be protected; never enable wire logging that captures Basic headers or request bodies.

### 18.2. Keep authentication distinct from authorization

~~~text
Authentication:
   is the token valid and trusted?
       |
       v
Authorities:
   what scopes/roles does the token/principal have?
       |
       v
HTTP authorization:
   what authority does the endpoint require?
       |
       v
Domain authorization:
   does the principal have permission on the specific record?
~~~

A valid token does not grant access to every order. Having `active=true` or a valid JWT signature is never enough to bypass owner/tenant policies.

### 18.3. Never let the sender choose the trust source

Avoid taking `iss`, `jku`, `x5u`, introspection URI, JWKS URI, or verifier hostnames from an unverified request/token without an allowlist. When supporting multiple issuers, maintain a trusted issuer registry and select the corresponding decoder/introspector.

### 18.4. Never trust "readable token means valid"

Being able to Base64URL-decode a JWT payload does not confer access. An opaque token matching an expected length or pattern does not mean it was issued. Proper cryptographic, state, or AS-assertion checks are mandatory.

### 18.5. Never trust an introspection result beyond the resource scope

If a response only returns `active=true` while lacking the information needed to prove audience/resource, enforce additional policy bindings or require the AS to provide proof under the contract. Never open an endpoint simply because "the Authorization Server recognized the token".

### 18.6. Never let requests pass when verification fails

Missing trusted keys, store failures, introspection timeouts, or malformed responses are all cases of **insufficient authentication basis**. Operational tooling can categorize errors, but must never turn them into an authenticated principal.

### 18.7. Token type must match its intended purpose

An OIDC ID token may be a valid JWT from the same issuer, yet is meant for the OIDC client and **not automatically usable as an access token**. A JWT access token profile may require `typ=at+jwt` and specific claims under RFC 9068; an opaque access token has its own introspection contract. The Resource Server must enforce which credential types it accepts.

## 19. What criteria should guide the decision?

A development team can use the table below when choosing a verification strategy.

| Design question | If the answer leans toward... | Option worth considering |
|---|---|---|
| Does the AS already issue signed JWTs and publish a trusted JWKS? | Yes, and the API wants fewer per-request dependencies | Local JWT verification |
| Does the AS require dynamic revocation/status checks on every request? | Yes, and introspection is supported | Remote introspection for JWT or opaque |
| Does the AS only issue opaque random handles without sharing a store? | Yes | Remote introspection |
| Do the API and AS jointly manage a securely designed token store? | Yes, and local lookup is permitted | Local opaque validation via state |
| Is the token encrypted/self-contained and does the verifier hold official keys/profile? | Yes | Local crypto validation with an appropriate implementation |
| Is AS introspection latency too high? | Yes | Consider TTL/risk-bounded caching, local JWT, or state replication |
| Must revocations be reflected very quickly? | Yes | Uncached introspection or state synchronization with an appropriate SLA |
| Cannot infrastructure operate a reliable local token state? | Yes | Prefer AS/issuer-owned validation |
| Multiple issuers and token profiles? | Yes | Design an allowlist, routing, and per-issuer policies |
| Does the API only want to "support both because tokens look different"? | No contract yet | **Stop to define the trust model**, do not sniff token strings |

### 19.1. Summary of the four cases in one sentence each

**JWT + local:** The Resource Server verifies JWS, keys, and claims using `JwtDecoder`.

**JWT + remote:** The Resource Server sends the JWT to an AS-supported introspection endpoint and trusts the response.

**Opaque + remote:** The Resource Server sends the token handle to introspection to query status and metadata.

**Opaque + local:** The Resource Server has an authoritative state/key source and official implementation to verify handles or specially designed opaque tokens.

None of these cases exempts you from issuer/audience checks, validity timestamps, scopes, resource-level permissions, and credential protection.

## 20. Test the actual architecture rather than inspecting token strings

For a Resource Server, tests should target the real **source of verification**. A fake token that "looks like a JWT" does not prove JWS validation works; a random string generated in a test does not prove introspection connects properly to the AS.

### 20.1. Scenario matrix for the four architectures

| System under test | Input | Evidence verified | Expectation |
|---|---|---|---|
| JWT local | JWT signed by trusted key, valid `iss/aud/exp` | `JwtDecoder` verifies JWS/validators | Authentication succeeds |
| JWT local | JWT with tampered payload and old signature | JWS signature | Rejected |
| JWT local | JWT with valid signature, `aud=billing-api` | Audience validator | Orders API rejects |
| JWT local | Expired JWT | Timestamp validator | Rejected |
| JWT remote | Valid JWT supported by AS introspection | RFC 7662 `active=true` and metadata | Authentication succeeds if policy passes |
| JWT remote | JWT with valid signature but revoked by AS | `active=false` from AS | Rejected |
| JWT remote | JWT not supported for introspection by AS | Response/token-state from AS | Not accepted merely because JWT parses |
| Opaque remote | Active handle, matching scope/audience | Introspection response | Authentication succeeds |
| Opaque remote | Non-existent or revoked handle | `active=false` | Rejected |
| Opaque remote | Endpoint timeout/5xx | No trusted AS assertion | Fail closed; classify operational error |
| Opaque local | Handle with active, unexpired record, right audience | Trusted token store | Authentication succeeds |
| Opaque local | Handle with no record | Local lookup | Rejected |
| Opaque local | Revoked record | Local revocation state | Rejected |
| Opaque local | Replica state too stale | Freshness policy | Fail closed or use approved fallback |
| All approaches | Authenticated principal lacking `SCOPE_orders.read` | HTTP authorization | Typically 403 |
| All approaches | Principal has scope but accesses another owner's order | Domain authorization | Rejected per policy |

### 20.2. Spring Security Test `jwt()` only mocks authentication results

With Spring MVC/Servlet:

~~~gradle
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Example HTTP rule test, assuming `GET /api/orders/42` exists and returns HTTP 200 for an authorized principal:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class JwtHttpAuthorizationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void readScopeCanReachReadEndpoint() throws Exception {
        mockMvc.perform(
                get("/api/orders/42")
                    .with(jwt().authorities(
                        new SimpleGrantedAuthority("SCOPE_orders.read")
                    ))
            )
            .andExpect(status().isOk());
    }
}
~~~

This test **does not mean Spring Security verified a JWS**, because `jwt()` injects a mocked authentication. It tests the `hasAuthority("SCOPE_orders.read")` rule and how the endpoint handles the principal, without proving the JWT decoder validates issuer/audience/time.

To test **real local JWT verification**, use a test JWT **signed by a test private key**, configure the decoder to trust the corresponding test public JWK, and exercise valid/invalid signatures, issuers, audiences, and expirations.

### 20.3. Testing with `opaqueToken()` has similar limitations

Spring Security Test supports mocking principals/attributes for opaque tokens as well. For example:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.opaqueToken;

mockMvc.perform(
        get("/api/orders/42")
            .with(opaqueToken().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            ))
    )
    .andExpect(status().isOk());
~~~

This snippet belongs to a Spring Security test context with `MockMvc` already set up. It illustrates testing **post-authentication HTTP authorization**, without proving that the introspection endpoint received the token or checked `active`. Add real integration tests using **test-only tokens** and an appropriate introspection service stub/fixture.

### 20.4. Testing remote introspection independently of token format

A test environment can run a mocked introspection endpoint:

~~~text
POST /introspect token=synthetic-jwt-looking-string
    → {active:true, aud:"orders-api", scope:"orders.read"}

POST /introspect token=synthetic-opaque-handle
    → {active:true, aud:"orders-api", scope:"orders.read"}

POST /introspect token=revoked-test-token
    → {active:false}
~~~

For both JWT-looking tokens and opaque handles, **the same `opaqueToken()` branch** can query the introspection endpoint. Verify that:

1. Requests go to the right URI over HTTPS in the appropriate environment.
2. Client authentication is correct (without logging secrets).
3. `active=true` builds the principal/authorities per the expected mapping.
4. `active=false` does not create a successful authentication.
5. Missing `aud`/wrong `aud` is handled per contract.
6. Timeout/5xx does not cause the system to grant access.
7. Cache TTL/revocation behaves according to the freshness policy.

In real deployments, stub tests only simulate the contract. An integration check against a real Authorization Server or authorized staging issuer confirms that **the AS supports JWT introspection** and returns the expected metadata.

### 20.5. Testing local opaque validation

With a simulated local token store:

~~~text
Repository:
  digest(handleA) → active, expiresAt future, audience orders-api
  digest(handleB) → revoked
  digest(handleC) → expired
  digest(handleD) → audience billing-api

Expected:
  handleA → authenticated
  handleB → rejected
  handleC → rejected
  handleD → rejected
  unknown → rejected
~~~

Beyond lookup logic, test store failures, stale caches, concurrent revocations, clock skew, and missing data. **Never place raw production access tokens in test fixtures**, source code, or CI logs.

## 21. Troubleshooting common errors from misunderstanding token formats

| Symptom | Possible misconception | How to analyze |
|---|---|---|
| JWT looks valid yet API returns 401 | Assuming a parseable JWT is enough | Check signature, issuer, audience, expiry, JWK/allowed algorithm, or introspection response depending on strategy |
| JWT sent to `opaqueToken()` gets 401 | Assuming Spring decodes JWTs automatically instead of introspecting | Confirm AS supports JWT introspection and caller has permission |
| Opaque token sent to `jwt()` fails parsing | Choosing JWT decoder for a non-JWT handle | Use opaque/introspection or a custom local token scheme |
| Local opaque accepts non-existent token | Assuming a well-formed handle is enough | Require a trusted record and active state |
| `active=true` yet Orders API has no audience | Assuming active means valid for every resource | Check audience/resource binding in AS/introspection contract |
| Introspection returns HTTP 200 with `active=false` | Assuming HTTP 200 means the token is valid | Read `active`, do not create a principal |
| Token revoked at AS yet Resource Server allows it | Assuming all remote introspection is instantaneous | Check cache TTL, replica lag, AS revocation semantics |
| Local JWT still works after logout | Assuming local JWT automatically knows session was revoked | Need TTL, denylist, state, or introspection per contract |
| Introspection timeouts slow down multiple APIs | Per-request network/AS dependency | Timeouts, capacity, cache freshness, resilience/fail closed |
| Same opaque token is sometimes valid, sometimes not | Inconsistent local store replicas | Check replication, lag, invalidation, and freshness bounds |
| Authentication succeeds yet returns 403 | Confusing authentication with authorization | Check authorities, scope prefix, HTTP/method/domain rules |
| JWT ID token from same issuer accepted by API | Confusing ID token with access token | Check token type/profile/audience and intended use |
| Bearer token appears in logs | Enabling wire logging on introspection/downstream | Redact headers/body, protect client secret, handle credential leak |
| Multiple token profiles handled only by checking dots | Choosing validation by untrusted shape | Design routing by issuer/endpoint/contract; prevent downgrade |

### 21.1. 401, 403, and network errors belong to different layers

- **401 Unauthorized** typically appears when the Resource Server cannot authenticate the token: expired, bad signature, `active=false`, or invalid credentials.
- **403 Forbidden** typically appears when the principal is authenticated but lacks permission to perform the request: missing `SCOPE_orders.read`, lacking a required role, or denied by business authorization.
- **Network/introspection/DB/JWK errors** may surface as service errors depending on exception handling, and do not necessarily return the same 401 code as a genuinely invalid token.

Some exception-handling configurations can also reject anonymous access with 401 even when the authorization rule is `denyAll`. Therefore, diagnose using the error source and security configuration rather than inferring the entire execution path solely from the HTTP status.

### 21.2. Fail closed and usability

An upstream failure does not mean "the customer deserved a 401"; yet it also never permits skipping verification and returning success. When the AS or token store has an outage, operations teams need clear error categorization for support/alerting without weakening security policy.

## 22. Self-check questions

**Question 1.** Must a JWT access token always be verified locally by the Resource Server?

**No.** If the Authorization Server supports introspection for JWTs and the Resource Server is authorized to use it, the JWT can be verified/queried remotely. Spring Security can use the `opaqueToken()` branch to introspect that JWT.

**Question 2.** Can a random opaque token be verified locally just by checking that the string is long enough?

**No.** Length or pattern does not prove a token was issued and is active. The Resource Server needs a trusted token store/lookup or a cryptographic protection mechanism designed for that token.

**Question 3.** Does `opaqueToken()` in Spring Security always mean "the token string must be opaque, not a JWT"?

**No.** That is the name of the strategy that processes tokens via `OpaqueTokenIntrospector`. If the introspector uses remote RFC 7662, it sends the token string to the AS, which may support JWTs or opaque handles. If the application supplies a custom introspector backed by local state, that branch does not even have to make network calls.

**Question 4.** Does a local JWT automatically know that a token was just revoked?

**No, if checking only self-contained signatures and claims.** You also need a state/revocation feed, denylist, or introspection per policy. Short-lived tokens only narrow the risk window; they are not equivalent to instant revocation.

**Question 5.** If introspection returns HTTP 200 with `active=false`, is the request authenticated?

**No.** HTTP 200 only indicates the introspection HTTP call was processed; `active=false` means the token is not accepted.

**Question 6.** Introspection returns `active=true` with no audience. Can it be allowed for every API by default?

**No.** If audience/resource binding is a mandatory requirement of the API, you need proof from introspection/AS policy or another trusted check. Without proof, access must not be granted.

**Question 7.** Why is a cryptographically structured encrypted token still called opaque?

Because "opaque" describes the fact that **the token consumer is not expected to understand its contents**. The issuer or a verifier holding the keys/contract can process the contents; the client merely holds the string to present.

**Question 8.** Why should you not select a strategy via `token.split("\\.").length`?

Because that is untrusted client-supplied data, token profiles vary, and shape-based fallback can create downgrade vulnerabilities. The strategy must be governed by policy/issuer/endpoint/contract.

**Question 9.** Does a 5-minute introspection cache preserve a promise of near-instant revocation?

**No.** Unless the cache is invalidated, `active=true` responses can continue to be reused for minutes after the AS revokes the token. Choose TTL/freshness per risk policy and token expiration.

**Question 10.** Once a token is successfully authenticated, is it allowed to view every order?

**No.** You still need scope/authority checks at the HTTP/method layer and owner/tenant/domain authorization for each individual record.

## 23. Conclusion: the source of trust is the core decision

Remember the four combinations:

~~~text
               LOCAL VERIFICATION          REMOTE VERIFICATION

JWT            JWS/JOSE + trusted keys       JWT introspection if AS supports it
               + claim validators            + AS active/metadata

Opaque         Trusted local token store     Handle introspection
               or crypto-aware verifier      + AS active/metadata
~~~

A secure Resource Server design must answer:

1. **Who is the trusted issuer?** Was the token issued for the right resource and under the right token profile?
2. **Which source verifies validity?** Keys/claims, a local token store, or Authorization Server introspection?
3. **How quickly are active/revoked changes reflected?** Is there cache/replication lag, and is that window acceptable?
4. **How does the Resource Server handle anomalies and outages?** Never accept tokens without sufficient proof.
5. **How do claims/attributes become permissions?** Scopes do not replace authorization for specific routes and resources.
6. **Where are credentials protected?** Headers, outbound introspection, logs, traces, caches, and error responses.

**Token format does not dictate local vs. remote verification.** JWTs are often convenient for local cryptographic verification; opaque random tokens are often convenient for introspection/state lookup. Yet those are **design tendencies**, not laws of engineering. Choosing a verification path must be grounded in the **token issuance contract, source of trust, revocation requirements, latency, availability, and authorization policy**—never solely on whether claims are visible inside the token string.

## References

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [Spring Security — Servlet OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — Servlet OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — OpaqueTokenIntrospector Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/introspection/OpaqueTokenIntrospector.html)
- [Spring Security — NimbusJwtDecoder Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
