# Decoder or Introspector Converts Tokens into Verified Data

In a **Spring Security OAuth 2.0 Resource Server** running on the Servlet stack, an HTTP request typically carries an access token as a string:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

This string does not yet prove identity, access permissions, or even its issuing source. Spring Security must cross an **authentication boundary**: from a client-supplied token to data the Resource Server has a basis to trust.

There are two common mechanisms:

- **JWT:** `JwtDecoder` verifies the digital signature and constraints of a JSON Web Token, then returns a `Jwt` object.
- **Opaque token:** `OpaqueTokenIntrospector` queries the Authorization Server via an introspection endpoint, verifies status and receives confirmed attributes, then returns an `OAuth2AuthenticatedPrincipal`.

The output from the decoder or introspector is converted into an `Authentication` containing a principal and authorities. **Only after authentication succeeds** does Spring Security use that data to authorize the request.

This lesson traces the Servlet flow from the `Authorization` header to `SecurityContext`, clarifying what has been verified, what still requires configuration, and why **a successfully authenticated token is still not guaranteed permission to access a resource**.

## 1. Map of the Servlet Processing Chain

A request entering a Servlet application passes through `FilterChainProxy` and a matching `SecurityFilterChain` before reaching the controller.

Components involved with bearer tokens:

| Component | Responsibility | Input / output |
|---|---|---|
| `BearerTokenAuthenticationFilter` | Locate bearer token, request authentication | HTTP header → `BearerTokenAuthenticationToken` |
| `BearerTokenResolver` | Extract token from permitted HTTP locations | Default is primarily `Authorization: Bearer ...` |
| `AuthenticationManager` | Dispatch to the appropriate provider | Untrusted authentication request → result/error |
| `JwtAuthenticationProvider` | Authenticate JWT tokens | Calls `JwtDecoder` |
| `JwtDecoder` | Verify signature and JWT claims | JWT string → `Jwt` |
| `OpaqueTokenAuthenticationProvider` | Authenticate tokens via introspection | Calls `OpaqueTokenIntrospector` |
| `OpaqueTokenIntrospector` | Confirm token status/attributes with AS | Token string → `OAuth2AuthenticatedPrincipal` |
| `JwtAuthenticationConverter` | Map claims to name/authorities | `Jwt` → `JwtAuthenticationToken` |
| `SecurityContextHolder` | Store authentication result for the request | Authenticated `Authentication` |
| `AuthorizationFilter` | Evaluate HTTP policies | Permit/deny based on `Authentication` |
| Method security/service | Additional business permission checks | Scope, tenant, ownership, resource state |

```mermaid
flowchart TD
    A["HTTP request: Authorization Bearer TOKEN"] --> B["BearerTokenAuthenticationFilter"]
    B --> C["Unauthenticated BearerTokenAuthenticationToken"]
    C --> D["AuthenticationManager"]
    D --> E{"Configured Provider"}
    E -- "JWT" --> F["JwtAuthenticationProvider"]
    E -- "Opaque" --> G["OpaqueTokenAuthenticationProvider"]
    F --> H["JwtDecoder: signature and validators"]
    G --> I["OpaqueTokenIntrospector: status and attributes"]
    H --> J{"Token accepted?"}
    I --> J
    J -- "No" --> K["Authentication failure: usually 401"]
    J -- "Yes" --> L["Build Authentication and authorities"]
    L --> M["SecurityContext"]
    M --> N["AuthorizationFilter / method security"]
    N --> O{"Authorized?"}
    O -- "No" --> P["Usually 403"]
    O -- "Yes" --> Q["Controller and service"]
```

The diagram shows a typical logical flow rather than listing every filter. An application can configure multiple `SecurityFilterChain`s or authentication methods; the selected chain determines which mechanism is used.

## 2. Before Decoding: A Bearer Token Is Untrusted Data

The client sends:

```http
Authorization: Bearer <ACCESS_TOKEN>
```

`BearerTokenAuthenticationFilter` uses `BearerTokenResolver` to extract the token string. The filter creates `BearerTokenAuthenticationToken` and passes it to `AuthenticationManager`. This is an **authentication request**, not a successful authentication result.

At this point:

- The client might have sent a valid token, an expired token, a token from another issuer, or a forged string.
- The presence of `Bearer` in the HTTP header does not prove the token is trustworthy.
- A JWT with three dot-separated segments is not necessarily validly signed.
- A random-looking opaque token cannot be inferred to be active from its syntax.
- Unverified data **must never be used** as a `GrantedAuthority` or operation permission.

Incorrect example:

```java
// UNSAFE example: merely Base64URL-decoding the JWT payload
// and using unverified claims to grant access.
String role = unverifiedPayload.get("role").toString();
if ("ADMIN".equals(role)) {
    allowAdministration();
}
```

An attacker can craft a payload containing `role=ADMIN`. **Base64URL decoding is merely reading data, not verifying signatures or authenticating identity.**

## 3. Two Mechanisms for Validating Access Tokens

OAuth 2.0 does not require access tokens to be JWTs. Tokens may be issued as signed JWTs or as opaque tokens requiring introspection.

| Criterion | JWT with `JwtDecoder` | Opaque with `OpaqueTokenIntrospector` |
|---|---|---|
| Read directly by Resource Server? | Structurally yes; only trusted after verification | No, contents cannot be inferred from the string |
| Primary verification | Digital signature and token validators | Introspection result from trusted AS |
| Returned data | `Jwt` | `OAuth2AuthenticatedPrincipal` |
| Provider consuming data | `JwtAuthenticationProvider` | `OpaqueTokenAuthenticationProvider` |
| Typical `Authentication` created | `JwtAuthenticationToken` | `BearerTokenAuthentication` |
| Call AS on every request? | Usually no after public keys are obtained, except for refresh | Usually yes unless caching is applied |
| Know if token was revoked early? | Not automatically from signature verification alone | Can know if AS returns `active=false` |
| API-specific constraints | Must check `aud` and policy | Needs corresponding introspection metadata/resource contract |

Choosing the configuration must be based on the **access token contract with the Authorization Server**. Do not count dots in client-supplied tokens and arbitrarily pick mechanisms or trust sources. A JWT can also be validated via introspection if the system design mandates it, though that differs from local verification with signing keys.

## 4. The JWT Branch: A Decoder Does More Than Read Payload

### 4.1. Structure of a JWT Access Token

A JWS compact-signed JWT consists of:

```text
base64url(header).base64url(payload).base64url(signature)
```

Illustrative header:

```json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "signing-key-2026-11"
}
```

Illustrative payload:

```json
{
  "iss": "https://login.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "iat": 1794715200,
  "exp": 1794718800
}
```

These values are examples only, not a real signed JWT. Clients can read payloads, yet **payloads must never be treated as verified authentication information on their own**.

### 4.2. Where Does `JwtDecoder` Get Trusted Keys?

In the JWT branch, `JwtAuthenticationProvider` calls `JwtDecoder`. The standard implementation is `NimbusJwtDecoder`.

The Resource Server can obtain keys from:

- **Issuer discovery:** configuring `issuer-uri` allows Spring Security to discover OIDC/OAuth metadata and the appropriate `jwks_uri`, depending on version capabilities.
- **Fixed JWK Set URI:** configuring `jwk-set-uri` explicitly specifies where to fetch public keys.
- **Static trusted key:** configuring the decoder with a public key or dedicated trust mechanism when required by the token contract.

For RSA/ECDSA-signed JWTs, the Authorization Server holds the **private key** to sign; the Resource Server uses the **public key** to verify. JWKS typically holds multiple public keys to support key rotation.

```text
Configured Issuer
      │
      ▼
Trusted metadata → jwks_uri
      │
      ▼
JWKS: public keys (kid, kty, alg, n/e or crv/x/y...)
      │
      ▼
JwtDecoder selects matching key and verifies signature
```

The `kid` field is only a key selection hint, **not proof that the key is trustworthy**. Never allow an unverified JWT to specify an arbitrary key-fetching URL via headers like `jku`. The verifier must fetch keys only from allowed sources.

### 4.3. JWT Verification Steps

```mermaid
flowchart TD
    A["Untrusted JWT string"] --> B["Parse JWS structure"]
    B --> C["Check algorithm and select trusted public key"]
    C --> D{"Signature valid?"}
    D -- "No" --> X["JwtException / authentication failure"]
    D -- "Yes" --> E["Run OAuth2TokenValidator on Jwt"]
    E --> F{"exp, nbf, iss, aud, and policy pass?"}
    F -- "No" --> X
    F -- "Yes" --> G["Return decoder-accepted Jwt"]
```

Checks the decoder must enforce per configuration:

1. **Signing algorithm:** Never accept `alg=none` or arbitrary token-requested algorithms; only algorithms trusted by the Resource Server.
2. **Signature:** The selected public key must verify the JWS signature.
3. **Issuer `iss`:** The token must come from a trusted AS.
4. **Timestamps:** `exp`, `nbf`, and appropriate clock skew policies.
5. **Audience `aud`:** The token must be intended for the receiving API when required by contract.
6. **Token type:** Never accept an OIDC ID token as an access token; if the AS follows RFC 9068, verify the corresponding token type/profile.
7. **Specific constraints:** Tenant, client policy, or other claims if required by the system.

Critical point: **verifying the signature does not automatically verify the audience**. An issuer may sign tokens for multiple APIs. If a Resource Server does not configure an audience validator, a token issued by the right issuer for a different API can slip past authentication.

### 4.4. What Information Does the Returned `Jwt` Carry?

The `JwtDecoder` interface exposes:

```java
Jwt jwt = jwtDecoder.decode(tokenValue);
```

Once the decoder completes all configured checks, `Jwt` exposes headers and claims:

```java
String subject = jwt.getSubject();
String issuer = jwt.getIssuer().toString();
List<String> audiences = jwt.getAudience();
Map<String, Object> headers = jwt.getHeaders();
Map<String, Object> claims = jwt.getClaims();
```

"Verified" means the data **passed the decoder's actual configured validators**, not that every claim satisfies every business policy:

- `scope=orders.read` does not prove the user owns all orders.
- Having `email` in a JWT does not by default prove the email is verified per application policy.
- Having `aud` in a JWT does not mean "right API" unless the application compares it against the expected audience.
- `client_id` identifies the OAuth client per contract, not that the current caller holds a private key.

In a normal request, the controller **does not need to call `JwtDecoder.decode(...)` again**: Spring Security already verified the token at the filter/provider layer.

## 5. Configuring JWT in Spring Boot

### 5.1. Declaring Dependencies

Maven example:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
</dependencies>
```

### 5.2. Configuring Issuer and Audience

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

In Spring Boot versions supporting these properties:

- `issuer-uri` specifies the trusted issuer, enabling metadata/JWKS discovery and validating the `iss` claim.
- `audiences` requires the token to have audience `orders-api`.
- The decoder can fetch and cache public keys, then verify JWT signatures using the appropriate keys.
- Endpoint access permissions must still be defined separately via authorization rules.

If you need to specify the JWKS endpoint upfront without using discovery to locate the key URL:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/shop
          jwk-set-uri: https://login.example.test/realms/shop/protocol/openid-connect/certs
          audiences:
            - orders-api
```

Keep `issuer-uri` alongside `jwk-set-uri` so issuer validation still applies. Specifying only a JWKS URL **does not guarantee** the decoder validates `iss` unless the application configures the corresponding validator.

Auto-configuration behavior for `audiences` and when the AS is contacted can vary across Spring Boot/Spring Security versions, especially when declaring a custom decoder bean. Always ensure required validators are attached to the actual decoder in use.

### 5.3. Defining a Custom Audience Validator

Spring Security example:

```java
@Configuration
public class JwtDecoderConfig {

    private static final String ISSUER =
        "https://login.example.test/realms/shop";
    private static final String AUDIENCE = "orders-api";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(ISSUER).build();

        OAuth2TokenValidator<Jwt> defaults =
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
                defaults,
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
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
```

`JwtValidators.createDefaultWithIssuer(...)` preserves standard checks such as issuer and timestamps per version. The audience validator enforces the right Resource Server.

**Never replace the default validator with only an audience validator**, as doing so can drop issuer or timestamp checks. Never derive the expected audience from the `Host` header or from the caller-supplied JWT itself; the expected audience is a trusted server-side configuration.

## 6. `JwtAuthenticationProvider` Converts `Jwt` into `Authentication`

A successful decoder returns `Jwt` data; Spring Security must then construct the authentication object.

```text
BearerTokenAuthenticationToken
        │
        ▼
JwtAuthenticationProvider
        │ calls JwtDecoder.decode(...)
        ▼
Jwt {headers, validated claims}
        │
        ▼
JwtAuthenticationConverter
        │ maps name + GrantedAuthority
        ▼
JwtAuthenticationToken
        │
        ▼
SecurityContext → Authorization
```

With the common default configuration, `JwtGrantedAuthoritiesConverter` reads `scope` or `scp` and adds the `SCOPE_` prefix:

```text
JWT: "scope": "orders.read profile"
                 │
                 ▼
GrantedAuthority:
  - SCOPE_orders.read
  - SCOPE_profile
```

Therefore:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
```

requires authority `SCOPE_orders.read`. Meanwhile `hasRole("ADMIN")` by default checks `ROLE_ADMIN`; a `roles` claim does not automatically become roles unless a converter is configured.

Distinguish:

1. **Decode/validate:** Proves the token is trustworthy under configured validation conditions.
2. **Convert:** Represents accepted claims as a principal and authorities.
3. **Authorize:** Checks whether the caller has permission to perform the action on the specific resource.

Conflating these steps can trick an API into thinking "valid JWT" equals "allowed to access all data."

## 7. The Opaque Branch: Introspection Instead of Parsing JWTs

An opaque token may look like a random string:

```text
7R6aTmFoFm9XJkQ7p8V2QJcW...
```

The Resource Server does not know what claims are inside the string. The common mechanism is calling **OAuth 2.0 Token Introspection** per RFC 7662.

Illustrative request:

```http
POST /oauth2/introspect HTTP/1.1
Host: login.example.test
Authorization: Basic <introspection-credentials>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=<urlencoded-access-token>
```

The AS may return:

```json
{
  "active": true,
  "iss": "https://login.example.test/realms/shop",
  "sub": "user-123",
  "client_id": "web-portal",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1900000000
}
```

If the token is invalid/inactive:

```json
{
  "active": false
}
```

**`active=false` is not data to "retry and grant temporary access"**. The Resource Server must not construct a valid principal when the AS declares the token inactive.

### 7.1. What Does `OpaqueTokenIntrospector` Check?

Spring Security's interface provides:

```java
OAuth2AuthenticatedPrincipal principal =
    introspector.introspect(tokenValue);
```

A configured implementation typically:

1. Sends the token string to the AS's introspection endpoint over a protected connection.
2. Authenticates the Resource Server to the endpoint using the method required by the AS.
3. Receives the response and confirms the token is active per implementation logic.
4. Returns an `OAuth2AuthenticatedPrincipal` carrying attributes and authorities.
5. Throws an error if the token is invalid or introspection cannot accept the result.

When `introspect(...)` returns a principal, its data can be used for downstream decisions **according to the contract and verified conditions**.

Example accessing attributes:

```java
String subject = principal.getAttribute("sub");
Object audience = principal.getAttribute("aud");
Object clientId = principal.getAttribute("client_id");
Collection<? extends GrantedAuthority> authorities =
    principal.getAuthorities();
```

Do not assume every opaque token includes all of these claims. Under RFC 7662, many metadata fields are optional; an AS might omit `aud` or `iss` depending on configuration and token profile.

### 7.2. `active=true` Does Not Automatically Mean "Right API"

An introspection response may state the token is active, yet the AS may issue tokens for multiple APIs. The Resource Server needs a clear contract for **audience/resource binding**:

- The AS returns `aud` and the Resource Server verifies `aud` contains `orders-api`.
- Or introspection is scoped by the AS to the receiving resource, with a clear guarantee that `active=true` applies only to the current resource.
- Or another equivalent trusted mechanism determines that the token is intended for this API.

If the application requires an audience and introspection does not provide it with no alternative mechanism, do not skip that check just to make requests succeed.

**`client_id` identifies the application that requested the token, not the target API audience.** Likewise, `scope` describes permissions, not proof that the token was issued for the destination API.

### 7.3. Introspection Is Not UserInfo

An OpenID Provider may publish both `userinfo_endpoint` and `introspection_endpoint`. The two serve different purposes:

| Endpoint | Primarily serves | Data |
|---|---|---|
| OIDC UserInfo | OIDC clients fetching user info per flow and scopes | Claims about the end user |
| OAuth Token Introspection | Authorized parties checking token state | `active` and token metadata such as scope, client, subject, audience |

Do not call UserInfo and treat getting a username back as proof that an access token is valid for a Resource Server.

## 8. Configuring an Opaque Resource Server

Example `application.yml`:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.test/oauth2/introspect
          client-id: orders-resource-server
          client-secret: REPLACE_WITH_SECRET_FROM_SECRET_MANAGER
```

Notes:

- `introspection-uri` must be a trusted AS endpoint.
- `client-id` and `client-secret` here are the **Resource Server's credentials when calling introspection**. They are **different** from the `client_id` of the OAuth client such as `web-portal` that requested the token.
- In production, load secrets from environment variables or a secret manager; never store real secrets in Git or logs.
- Some ASs support other introspection authentication methods; configuration must follow the real contract.

Illustrative filter chain:

```java
@Configuration
public class OpaqueSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(Customizer.withDefaults()))
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
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
```

Spring Security typically maps scopes returned by introspection into `SCOPE_...` authorities. If the AS uses a custom permission structure, map authorities from verified data according to API policy.

When the application needs additional audience checks not performed by the default introspector, you can **wrap `OpaqueTokenIntrospector` with a custom validator**:

```text
OpaqueTokenIntrospector delegate = trusted configured introspector

introspect(token):
    principal = delegate.introspect(token)   // already verified active
    aud = principal.attributes["aud"]
    if aud does not contain "orders-api":
        fail token authentication
    return principal
```

This is **pseudocode**, not directly runnable Java. A real implementation must handle the exact type of `aud` returned by the AS (string or list), exceptions, and Spring Security version contracts. Additional checks must occur **before** treating authentication as successful.

## 9. From Introspection Principal to `BearerTokenAuthentication`

Flow after introspection:

```text
BearerTokenAuthenticationToken
        │
        ▼
OpaqueTokenAuthenticationProvider
        │ calls introspector.introspect(...)
        ▼
OAuth2AuthenticatedPrincipal
  attributes: sub, client_id, aud, scope, exp, ...
  authorities: SCOPE_orders.read, ...
        │
        ▼
BearerTokenAuthentication
        │
        ▼
SecurityContext → Authorization
```

Comparison with JWT:

| Provider input | Intermediate data | Typical `Authentication` | Principal |
|---|---|---|---|
| JWT bearer token | `Jwt` | `JwtAuthenticationToken` | Usually `Jwt` |
| Opaque bearer token | `OAuth2AuthenticatedPrincipal` | `BearerTokenAuthentication` | Usually `OAuth2AuthenticatedPrincipal` |

Because the principal types differ, controller code should pick the matching type.

With JWT:

```java
@GetMapping("/api/me")
public Map<String, Object> me(@AuthenticationPrincipal Jwt jwt) {
    return Map.of(
        "subject", jwt.getSubject(),
        "issuer", jwt.getIssuer().toString()
    );
}
```

With opaque tokens:

```java
@GetMapping("/api/me")
public Map<String, Object> me(
        @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
    return Map.of(
        "name", principal.getName(),
        "authorities", principal.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .toList()
    );
}
```

The example uses a Java version with `Stream.toList()`; production code should handle optional fields and limit returned information. Do not expose full tokens or sensitive claims via debug APIs.

When you want a controller independent of token format, accept `Authentication`:

```java
@GetMapping("/api/principal-name")
public Map<String, String> principal(Authentication authentication) {
    return Map.of("name", authentication.getName());
}
```

A properly built `Authentication` only appears after authentication; HTTP authorization rules use its authorities without re-invoking introspection or the decoder in the controller.

## 10. Trust Boundaries: How Much Can Each Layer of Data Be Trusted?

The table below helps prevent using data at the wrong layer:

| Stage | Available data | Considered authenticated? |
|---|---|---|
| `Authorization` header | Caller-supplied token string | **Not yet** |
| `BearerTokenAuthenticationToken` | Extracted token | **Not yet** |
| JWT payload read via Base64URL | Self-asserted claims | **Not yet** |
| `JwtDecoder` succeeds | `Jwt` with verified signature and applied validators | **Yes, per configured validation set** |
| `OpaqueTokenIntrospector` succeeds | `OAuth2AuthenticatedPrincipal` from AS | **Yes, per introspection contract and checked constraints** |
| Authentication provider succeeds | `JwtAuthenticationToken` or `BearerTokenAuthentication` | Usable as input to authorization |
| `AuthorizationFilter` succeeds | Matching HTTP permissions | Can proceed to controller/service |
| Method security and business policy | Record-specific permissions | Depends on enforced business policy |

Example token containing:

```json
{
  "iss": "https://login.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
```

Once properly authenticated, the API can trust that **the issuer granted** this subject/scope for the API. Yet nothing proves `user-123` is allowed to view **order 42** belonging to `user-456`. That permission must usually be checked in the service, repository, or method security.

### Authentication and Authorization Cannot Substitute for Each Other

```text
Token string
   │
   ▼
Decoder / Introspector → Valid token identity and attributes
   │
   ▼
AuthenticationProvider → Authentication with authorities
   │
   ▼
AuthorizationFilter / Method Security → Allow or deny
```

**Do not use `authenticated()` as the sole policy for sensitive endpoints** if the API also requires scopes, roles, tenants, or ownership. A request with a valid token can still be unauthorized to perform an operation.

## 11. Configuring HTTP Permissions for Both Mechanisms

Once you choose the JWT or opaque branch, the semantic authorization rules can be identical.

JWT Resource Server example:

```java
@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

To switch this configuration to opaque tokens per the AS contract, replace the JWT branch with:

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults()))
```

Changing only the authentication branch is **not enough** if attributes/scopes returned by introspection are structured differently from JWTs; adjust the converter or introspector accordingly.

The difference lies in **how the token is validated**. Downstream, `AuthorizationFilter` still inspects the generated authorities. In both branches, a user with `SCOPE_orders.read` is not automatically authorized to read every order; the service must still check data permissions if required by business logic.

## 12. How Do Decoder/Introspector Errors Appear as HTTP Responses?

In a Resource Server, authentication errors differ from authorization errors.

| Situation | Detection layer | Typical outcome |
|---|---|---|
| No token sent to protected endpoint | Authorization receives unauthenticated request | `401 Unauthorized` |
| Malformed bearer header | Bearer token resolution | May be `400 invalid_request` |
| JWT signature tampered | Decoder/JWT provider | `401 invalid_token` |
| Expired JWT, wrong issuer, wrong audience | JWT validators | `401 invalid_token` |
| Opaque token introspection returns `active=false` | Introspector/provider | `401 invalid_token` |
| Introspection TLS/timeout/credential failure | Verification infrastructure | Request not authenticated; exact HTTP depends on exception handling |
| Authenticated token missing required scope | Authorization | Usually `403 Forbidden` |
| Valid token, sufficient scope, wrong ownership/tenant | Business policy | `403` or `404` per data protection policy |
| Valid token, full permissions | Controller/service | Success HTTP such as `200` if business logic succeeds |

Invalid token example:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Valid token with insufficient scope example:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

Exact headers depend on the error type and configuration of `BearerTokenAuthenticationEntryPoint`, `BearerTokenAccessDeniedHandler`, `ExceptionTranslationFilter`, or custom handlers. Introspection infrastructure errors must never be masked by **letting tokens pass through**.

## 13. Caching, Key Rotation, and Availability

### 13.1. JWT: Local Verification, Dependent on Public Keys

With asymmetrically signed JWTs:

- The AS holds the private key and issues signed JWTs.
- The Resource Server uses public keys in JWKS to verify.
- JWTs can be verified locally once keys are fetched.
- During AS key rotation, JWKS may hold both old and new public keys during the transition window.
- If the decoder caches stale JWKS too long, a new token with an unknown `kid` may temporarily fail verification.
- A validly signed JWT does not indicate whether the token was revoked early unless the API applies an additional state mechanism.

Choose access token lifetimes and rotation strategies to match operational needs. Never disable signature verification simply because a new JWT does not match an old key.

### 13.2. Opaque: Introspection Can Reflect Fresher Status

The AS can return `active=false` immediately when a token is revoked. In trade-off:

- Introspection can trigger a network request per authentication.
- AS latency, timeouts, and availability affect the API.
- Caching responses reduces load, yet can extend the window during which a revoked token is accepted.
- Never cache `active=true` results indefinitely, ignore `exp`, or treat stale cache entries as valid proof.
- When the AS is temporarily unreachable, protected requests must **fail closed** per safe authentication policy.

### 13.3. Protecting Bearer Tokens and Introspection Credentials

Never record raw bearer tokens in application logs, proxy logs, URLs, or traces. Both JWTs and opaque tokens can be replayed if leaked. Credentials used to call the introspection endpoint must also be kept secret.

A safer way to log:

```text
request_id=req-123
route=/api/orders/{id}
authentication=FAILED
reason=INVALID_AUDIENCE
expected_audience=orders-api
```

Log entries must comply with data protection policies; avoid putting tokens, client secrets, or sensitive identifiers into logs.

## 14. Real-World Scenario Analysis

Assume the Orders API trusts issuer `https://login.example.test/realms/shop`, audience `orders-api`, and `GET /api/orders/**` requires `SCOPE_orders.read`.

### Scenario A — Valid JWT Signature but Wrong Audience

```json
{
  "iss": "https://login.example.test/realms/shop",
  "aud": ["payments-api"],
  "scope": "orders.read",
  "exp": 1900000000
}
```

With an audience validator configured, the decoder must reject it because the token is intended for `payments-api`. Having the right scope **cannot fix** a wrong audience. The typical result is `401`.

### Scenario B — Valid JWT Audience but Missing Scope

```json
{
  "iss": "https://login.example.test/realms/shop",
  "aud": ["orders-api"],
  "scope": "profile",
  "exp": 1900000000
}
```

The decoder can accept the JWT if its signature and other constraints pass. The converter creates `SCOPE_profile`, while `AuthorizationFilter` requires `SCOPE_orders.read` and denies the request, typically `403`.

### Scenario C — Inactive Opaque Token

Introspection returns:

```json
{"active": false}
```

The introspector must not return a trusted principal for an inactive token. The provider has no basis to build a valid `Authentication`; the request to the protected endpoint fails.

### Scenario D — Active Opaque Token Missing Audience

The AS returns `active=true`, `scope=orders.read`, without `aud`. If the contract requires proving the token is intended for the Orders API, verify resource binding through another AS-guaranteed mechanism or require the AS to supply metadata. **Never treat client ID as audience.**

### Scenario E — Valid Token, Wrong Ownership

The token has `sub=user-123`, `aud=orders-api`, and `scope=orders.read`. However, the request tries to view an order belonging to `user-456`. Authentication may succeed, yet the service must check ownership/tenant and deny access if unauthorized.

### Scenario F — Key Rotation

A new JWT has `kid=new-key`, while the cached JWKS only contains `old-key`. The decoder must obtain the matching key and verify the signature. While unable to verify, **never accept the token anyway**; fix key updates and JWKS handling.

### Scenario G — Introspection Timeout

The AS does not return token status due to a timeout. The Resource Server cannot affirm the token is active, so it must not grant access on guesswork. Log the infrastructure cause safely and enforce authentication failure policy.

### Scenario H — ID Token Sent to the API by Mistake

An OIDC ID token has `aud=web-portal`, not `orders-api`. Even if signed by the same issuer/JWKS, it is not an access token for the Orders API. The decoder and token-type/audience policies must reject it.

## 15. How to Pinpoint Which Step Failed

When receiving a report that "the API returns 401/403 even though the token looks valid," check in order:

1. **Was the Bearer token extracted cleanly from the header?** Is the header malformed or are there conflicting token sources?
2. **Which provider handled it?** JWT decoder or opaque introspector, under which token config/contract?
3. **Is the verification source trusted?** Correct issuer/JWKS, or valid AS introspection endpoint over proper HTTPS?
4. **Was the token proven valid?** Valid JWT signature, or introspection returning `active=true`?
5. **Were all validators applied?** Timestamps, issuer, audience, token type, and custom policies?
6. **What is the intermediate data type?** `Jwt` or `OAuth2AuthenticatedPrincipal`, and what actual claims/attributes exist?
7. **How were authorities mapped?** `scope`/`scp` turned into `SCOPE_...` or via a custom converter?
8. **Did the provider build an authenticated `Authentication`?** Was it stored in `SecurityContext`?
9. **Which authorization step blocked the request?** HTTP matchers, method security, ownership/tenant permissions?
10. **Is error handling safe?** No fail-open behavior and no leaked tokens or introspection credentials?

Separating these layers lets you distinguish an **unauthenticated token**, an **authenticated token lacking permissions**, and a **request authorized at HTTP level that still needs business-data checks**.

## 16. Related Technical References

- [Spring Security — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): Servlet Resource Server flow and security filters.
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): `JwtDecoder`, `NimbusJwtDecoder`, validators, authority conversion.
- [Spring Security — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): `OpaqueTokenIntrospector` and introspection.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): HTTP bearer rules and errors.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): JWT structure and claims.
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517): JWK/JWKS and signature verification keys.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): introspection endpoint, `active`, and token attributes.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token profile specification and token validation conditions.

**Final takeaway:** `JwtDecoder` helps the Resource Server verify JWTs using trusted keys and validators. `OpaqueTokenIntrospector` confirms token status and attributes with the AS. Providers convert the verified output into an `Authentication` with principal and authorities; the authorization layer then decides whether the request is permitted to access the specific resource.
